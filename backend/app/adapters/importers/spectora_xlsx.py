"""Spectora XLSX worksheet importer adapter.

Parses a Spectora HTML-text template export into the domain
:class:`~app.domain.models.template.Template` aggregate. Accepted input is either the
raw OOXML worksheet XML part (the committed sample :file:`sample-data/sheet1.xml`) or a
full XLSX ZIP container from which that worksheet part is read (shared strings included
when cells reference them). No third-party parsing dependency is used; ``xml.etree`` and
``zipfile`` are the parsers, kept at the adapter edge by the layered architecture.

Only columns the domain model can represent are mapped. Every other column that carries
data is surfaced, never silently dropped:

* ``UNSUPPORTED_CONTENT`` (warning) - one deduplicated issue per non-modelable column
  that contains any data, with the first value seen.
* ``SOURCE_DATA_MISSING`` (info) - one deduplicated issue per modelable optional column
  that is entirely empty across the export.
* ``INVALID_SOURCE_DATA`` (warning) - one issue per malformed value in a mapped field,
  with the row context and a safe fallback where one exists.

Fatal problems (unreadable bytes, wrong root element, missing required columns, blank
required values) raise :class:`app.domain.exceptions.TemplateImportError`.

Importer-owned decisions (documented for the contract):

* ``source`` is ``"spectora"``; ``source_filename`` preserves the upload filename.
* The template ``name`` is derived from the filename (base name without extension); this
  export family carries no explicit title to override it.
* Comment ``display_order`` is taken verbatim from the ``Order (w/i item)`` column when
  the value is a non-negative integer (duplicates are kept; a gap is kept); when the
  column is absent or a value is unusable, a 0-based first-appearance order is assigned.
* Text is preserved verbatim after a single XML-entity decode; reported/skipped columns
  keep their raw value as seen in the worksheet.
"""

from __future__ import annotations

import io
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree as ET

from app.domain.exceptions import TemplateImportError
from app.domain.models.template import (
    AnswerType,
    Comment,
    CommentOption,
    CommentType,
    ImportIssue,
    IssueSeverity,
    IssueType,
    Item,
    OptionType,
    Section,
    Template,
)

__all__ = ["SpectoraXlsxImporter"]

_WORKSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_WORKSHEET_TAG = f"{{{_WORKSHEET_NS}}}worksheet"

_XLSX_SHEET_PATH = "xl/worksheets/sheet1.xml"
_XLSX_SHARED_STRINGS_PATH = "xl/sharedStrings.xml"
_ZIP_MAGIC = b"PK\x03\x04"

_REQUIRED_COLUMNS = ("section name", "item name", "comment name", "comment type", "answer type")

_OPTIONAL_MODELABLE = (
    "comment text",
    "category",
    "multiple choice options",
    "unit type options",
    "recommendation",
    "order",
    "default value",
    "default value 2",
    "default unit type",
    "default estimate min",
    "default estimate max",
)


def _display_name(header_text: str) -> str:
    """Return the export's column name without its parenthetical hint.

    ``"Comment Type (info, limit, defect)"`` becomes ``"Comment Type"``. Used both as a
    stable ``source_field`` on issues and as the source for the mapping key.
    """

    return header_text.split(" (", 1)[0].strip()


def _column_key(header_text: str) -> str:
    """Normalise a header to the stable mapping key used by this importer."""

    return _display_name(header_text).lower()


def _column_index(cell_ref: str) -> int:
    """Convert an Excel column reference (``"AP1"``) into a 1-based column index."""

    index = 0
    for char in cell_ref:
        if not char.isalpha():
            break
        index = index * 26 + (ord(char.upper()) - 64)
    return index


def _cell_text(cell: ET.Element, shared: list[str] | None) -> str:
    """Extract the display text of a worksheet cell."""

    text_type = cell.get("t")
    if text_type == "inlineStr":
        inline = cell.find(f"{{{_WORKSHEET_NS}}}is")
        if inline is None:
            return ""
        return "".join(node.text or "" for node in inline.iter(f"{{{_WORKSHEET_NS}}}t"))
    value = cell.find(f"{{{_WORKSHEET_NS}}}v")
    if value is None or value.text is None:
        return ""
    if text_type == "s":
        if shared is None:
            return value.text
        try:
            return shared[int(value.text)]
        except (ValueError, IndexError):
            return value.text
    return value.text


def _parse_shared_strings(xml_bytes: bytes) -> list[str]:
    """Parse an XLSX ``sharedStrings.xml`` part into the ordered string table."""

    root = ET.fromstring(xml_bytes)
    return [
        "".join(node.text or "" for node in item.iter(f"{{{_WORKSHEET_NS}}}t"))
        for item in root.findall(f"{{{_WORKSHEET_NS}}}si")
    ]


def _extract_worksheet(source: bytes) -> tuple[bytes, list[str] | None]:
    """Return ``(worksheet_xml_bytes, shared_strings_or_None)`` for any accepted input."""

    if source[:4] != _ZIP_MAGIC:
        return source, None
    try:
        with zipfile.ZipFile(io.BytesIO(source)) as archive:
            names = archive.namelist()
            if _XLSX_SHEET_PATH not in names:
                raise TemplateImportError(
                    f"expected XLSX worksheet '{_XLSX_SHEET_PATH}' not found in the archive"
                )
            worksheet = archive.read(_XLSX_SHEET_PATH)
            if _XLSX_SHARED_STRINGS_PATH not in names:
                return worksheet, None
            return worksheet, _parse_shared_strings(archive.read(_XLSX_SHARED_STRINGS_PATH))
    except zipfile.BadZipFile as exc:
        raise TemplateImportError(
            "file is a ZIP container but is not a readable ZIP archive"
        ) from exc
    except ET.ParseError as exc:
        raise TemplateImportError(f"unreadable shared strings table: {exc}") from exc


def _invalid_issue(row_number: int, source_field: str, raw_value: str, message: str) -> ImportIssue:
    """Build an ``INVALID_SOURCE_DATA`` issue with the row context."""

    return ImportIssue(
        message=message,
        issue_type=IssueType.INVALID_SOURCE_DATA,
        severity=IssueSeverity.WARNING,
        source_row=row_number,
        source_field=source_field,
        raw_value=raw_value,
    )


def _parse_comment_type(
    raw: str, row_number: int, field_name: str, issues: list[ImportIssue]
) -> CommentType:
    """Map a ``Comment Type`` cell to the enum, with a safe fallback for bad values."""

    try:
        return CommentType(raw.lower())
    except ValueError:
        issues.append(
            _invalid_issue(
                row_number,
                field_name,
                raw,
                f"unknown Comment Type value {raw!r}; 'info' used instead",
            )
        )
        return CommentType.INFO


def _parse_answer_type(
    raw: str, row_number: int, field_name: str, issues: list[ImportIssue]
) -> AnswerType:
    """Map an ``Answer Type`` cell to the enum, with a safe fallback for bad values."""

    try:
        return AnswerType(raw.lower())
    except ValueError:
        issues.append(
            _invalid_issue(
                row_number,
                field_name,
                raw,
                f"unknown Answer Type value {raw!r}; 'boolean' used instead",
            )
        )
        return AnswerType.BOOLEAN


def _parse_category(
    raw: str, row_number: int, field_name: str, issues: list[ImportIssue]
) -> int | None:
    """Map a ``Category`` cell to ``-1``/``0``/``1``, or ``None`` when invalid."""

    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        issues.append(
            _invalid_issue(row_number, field_name, raw, f"Category value {raw!r} is not an integer")
        )
        return None
    if value not in (-1, 0, 1):
        issues.append(
            _invalid_issue(
                row_number, field_name, raw, "Category must be one of -1 (Low), 0 (Med), 1 (High)"
            )
        )
        return None
    return value


def _parse_estimate(
    raw: str, row_number: int, field_name: str, issues: list[ImportIssue]
) -> Decimal | None:
    """Map an estimate cell to :class:`decimal.Decimal`, or ``None`` when malformed."""

    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        issues.append(
            _invalid_issue(row_number, field_name, raw, f"estimate value {raw!r} is not a number")
        )
        return None


def _parse_options(raw: str, option_type: OptionType) -> list[CommentOption]:
    """Split a comma-separated options cell into ordered :class:`CommentOption` rows."""

    return [
        CommentOption(option_type=option_type, value=part.strip(), display_order=index)
        for index, part in enumerate(raw.split(","))
        if part.strip()
    ]


class SpectoraXlsxImporter:
    """Implements :class:`TemplateImporter` for Spectora HTML-text template exports."""

    def import_template(self, source: bytes, *, filename: str = "") -> Template:
        """Parse a Spectora worksheet export into a :class:`Template`."""

        worksheet_bytes, shared = _extract_worksheet(source)
        columns, data_rows = self._read_rows(worksheet_bytes, shared)

        column_by_key = {_column_key(text): index for index, text in columns.items()}
        display_by_key = {key: key.title() for key in (*_REQUIRED_COLUMNS, *_OPTIONAL_MODELABLE)}
        display_by_key.update(
            {_column_key(text): _display_name(text) for _, text in columns.items()}
        )
        display_by_index = {index: _display_name(text) for index, text in columns.items()}

        missing = [key for key in _REQUIRED_COLUMNS if key not in column_by_key]
        if missing:
            raise TemplateImportError(
                "not a recognised Spectora template export; "
                f"required column(s) missing: {', '.join(missing)}"
            )

        modelable_columns = {
            column_by_key[key]
            for key in (*_REQUIRED_COLUMNS, *_OPTIONAL_MODELABLE)
            if key in column_by_key
        }

        sections: list[Section] = []
        section_index: dict[str, int] = {}
        item_index: dict[tuple[int, str], int] = {}
        order_cursor: dict[tuple[int, str], int] = {}

        populated = set[str]()
        unsupported: dict[int, tuple[str, int, str]] = {}
        invalid: list[ImportIssue] = []

        def value(row: dict[int, str], key: str) -> str:
            index = column_by_key.get(key)
            return row.get(index, "") if index is not None else ""

        for row_number, row in data_rows:
            section_name = value(row, "section name").strip()
            item_name = value(row, "item name").strip()
            comment_name = value(row, "comment name").strip()

            blanks = [
                label
                for label, raw in (
                    ("Section Name", section_name),
                    ("Item Name", item_name),
                    ("Comment Name", comment_name),
                )
                if not raw
            ]
            if blanks:
                raise TemplateImportError(
                    f"row {row_number}: cannot import; "
                    f"required value(s) missing: {', '.join(blanks)}"
                )

            if section_name not in section_index:
                section_index[section_name] = len(sections)
                sections.append(Section(name=section_name, display_order=len(sections)))
            section = sections[section_index[section_name]]

            item_key = (section_index[section_name], item_name)
            if item_key not in item_index:
                item_index[item_key] = len(section.items)
                section.items.append(Item(name=item_name, display_order=len(section.items)))
            item = section.items[item_index[item_key]]

            order_raw = value(row, "order").strip()
            display_order = order_cursor.get(item_key, 0)
            if order_raw:
                populated.add("order")
                try:
                    order_value = int(order_raw)
                except ValueError:
                    invalid.append(
                        _invalid_issue(
                            row_number,
                            display_by_key["order"],
                            order_raw,
                            (
                                f"Order value {order_raw!r} is not an integer; "
                                "first-appearance order used"
                            ),
                        )
                    )
                else:
                    if order_value >= 0:
                        display_order = order_value
                    else:
                        invalid.append(
                            _invalid_issue(
                                row_number,
                                display_by_key["order"],
                                order_raw,
                                "Order value is negative; first-appearance order used",
                            )
                        )
            order_cursor[item_key] = order_cursor.get(item_key, 0) + 1

            comment_type_raw = value(row, "comment type").strip()
            answer_type_raw = value(row, "answer type").strip()
            content = value(row, "comment text")
            if content.strip():
                populated.add("comment text")

            category_raw = value(row, "category").strip()
            if category_raw:
                populated.add("category")
            estimate_min = _parse_estimate(
                value(row, "default estimate min").strip(),
                row_number,
                display_by_key["default estimate min"],
                invalid,
            )
            estimate_max = _parse_estimate(
                value(row, "default estimate max").strip(),
                row_number,
                display_by_key["default estimate max"],
                invalid,
            )
            if value(row, "default estimate min").strip():
                populated.add("default estimate min")
            if value(row, "default estimate max").strip():
                populated.add("default estimate max")

            recommendation = _optional_text(
                value(row, "recommendation"), "recommendation", populated
            )
            default_value = _optional_text(value(row, "default value"), "default value", populated)
            default_value_2 = _optional_text(
                value(row, "default value 2"), "default value 2", populated
            )
            default_unit_type = _optional_text(
                value(row, "default unit type"), "default unit type", populated
            )

            options: list[CommentOption] = []
            multiple_raw = value(row, "multiple choice options").strip()
            if multiple_raw:
                populated.add("multiple choice options")
                options.extend(_parse_options(multiple_raw, OptionType.MULTIPLE_CHOICE))
            unit_raw = value(row, "unit type options").strip()
            if unit_raw:
                populated.add("unit type options")
                options.extend(_parse_options(unit_raw, OptionType.UNIT_TYPE))

            for column_index, cell_value in row.items():
                if column_index in modelable_columns:
                    continue
                stripped = cell_value.strip()
                if stripped:
                    unsupported.setdefault(
                        column_index, (display_by_index[column_index], row_number, stripped)
                    )

            item.comments.append(
                Comment(
                    name=comment_name,
                    content=content,
                    comment_type=_parse_comment_type(
                        comment_type_raw, row_number, display_by_key["comment type"], invalid
                    ),
                    answer_type=_parse_answer_type(
                        answer_type_raw, row_number, display_by_key["answer type"], invalid
                    ),
                    display_order=display_order,
                    category=_parse_category(
                        category_raw, row_number, display_by_key["category"], invalid
                    ),
                    recommendation=recommendation,
                    default_value=default_value,
                    default_value_2=default_value_2,
                    default_unit_type=default_unit_type,
                    estimate_min=estimate_min,
                    estimate_max=estimate_max,
                    source_row=row_number,
                    options=options,
                )
            )

        issues: list[ImportIssue] = []
        issues.extend(invalid)
        issues.extend(
            ImportIssue(
                message=f"Source column '{name}' contained data that cannot be represented.",
                issue_type=IssueType.UNSUPPORTED_CONTENT,
                severity=IssueSeverity.WARNING,
                source_row=row_number,
                source_field=name,
                raw_value=raw_value,
            )
            for name, row_number, raw_value in unsupported.values()
        )
        issues.extend(
            ImportIssue(
                message=f"Source column '{name}' was empty; the field was left unset.",
                issue_type=IssueType.SOURCE_DATA_MISSING,
                severity=IssueSeverity.INFO,
                source_field=name,
            )
            for key in _OPTIONAL_MODELABLE
            if key in column_by_key and key not in populated
            for name in (display_by_key[key],)
        )

        return Template(
            name=Path(filename).stem if filename else "Imported template",
            source="spectora",
            source_filename=filename or None,
            sections=sections,
            issues=issues,
        )

    @staticmethod
    def _read_rows(
        worksheet_bytes: bytes, shared: list[str] | None
    ) -> tuple[dict[int, str], list[tuple[int, dict[int, str]]]]:
        """Parse the worksheet into ``(header_columns, [(row_number, cells_by_column)])``."""

        try:
            root = ET.fromstring(worksheet_bytes)
        except ET.ParseError as exc:
            raise TemplateImportError(f"unreadable worksheet XML: {exc}") from exc
        if root.tag != _WORKSHEET_TAG:
            raise TemplateImportError(
                "not a recognised Spectora template export "
                "(expected the OOXML worksheet root element)"
            )

        sheet_data = root.find(f"{{{_WORKSHEET_NS}}}sheetData")
        if sheet_data is None:
            raise TemplateImportError("worksheet contains no sheetData")
        row_elements = sheet_data.findall(f"{{{_WORKSHEET_NS}}}row")
        if not row_elements:
            raise TemplateImportError("worksheet contains no rows")

        rows: list[tuple[int, dict[int, str]]] = []
        for position, element in enumerate(row_elements, start=1):
            row_ref = element.get("r") or ""
            row_number = int(row_ref) if row_ref.isdigit() else position
            cells: dict[int, str] = {}
            column_cursor = 1
            for cell in element.findall(f"{{{_WORKSHEET_NS}}}c"):
                ref = cell.get("r") or ""
                column = _column_index(ref)
                if column == 0:
                    column = column_cursor
                column_cursor = column + 1
                text = _cell_text(cell, shared)
                if text:
                    cells[column] = text
            if cells:
                rows.append((row_number, cells))

        if not rows:
            raise TemplateImportError("worksheet contains no rows with data")
        columns = rows[0][1]
        if not columns:
            raise TemplateImportError("worksheet header row is empty")
        if len(rows) < 2:
            raise TemplateImportError("worksheet contains no template data rows below the header")
        return columns, rows[1:]


def _optional_text(raw: str, key: str, populated: set[str]) -> str | None:
    """Return a trimmed optional string, recording that the column carried data."""

    stripped = raw.strip()
    if stripped:
        populated.add(key)
        return stripped
    return None
