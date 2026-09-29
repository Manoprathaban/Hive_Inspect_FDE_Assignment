"""Integration + unit tests for the Spectora XLSX importer adapter.

The canonical fixture :file:`sample-data/sheet1.xml` (the committed Spectora
InterNACHI Residential worksheet export) is the primary integration artifact.
Small synthetic worksheets cover focused mapping and malformed-input cases.
"""

from __future__ import annotations

import io
import zipfile
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters.importers.spectora_xlsx import SpectoraXlsxImporter
from app.domain.exceptions import TemplateImportError
from app.domain.models.template import (
    AnswerType,
    CommentType,
    IssueType,
    OptionType,
    Template,
)
from app.protocols.importers.template_importer import TemplateImporter

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_SHEET = REPO_ROOT / "sample-data" / "sheet1.xml"
SECOND_SHEET = REPO_ROOT / "sample-data" / "commercial-rental.xml"

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _worksheet_xml(rows: list[list[str]]) -> bytes:
    """Build an OOXML worksheet part with inline strings for the given rows."""

    columns = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<worksheet xmlns="{NS}">',
        "<sheetData>",
    ]
    for row_number, row in enumerate(rows, start=1):
        cells = "".join(
            f'<c r="{columns[index]}{row_number}" t="inlineStr">'
            f"<is><t>{_xml_escape(text)}</t></is></c>"
            for index, text in enumerate(row)
        )
        lines.append(f'<row r="{row_number}">{cells}</row>')
    lines.append("</sheetData>")
    lines.append("</worksheet>")
    return "\n".join(lines).encode("utf-8")


def _xlsx_zip(*paths: tuple[str, bytes]) -> bytes:
    """Build an XLSX ZIP container from part path/bytes pairs."""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in paths:
            archive.writestr(path, content)
    return buffer.getvalue()


def _shared_strings_xml(values: list[str]) -> bytes:
    items = "".join(f"<si><t>{_xml_escape(value)}</t></si>" for value in values)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<sst xmlns="{NS}" uniqueCount="{len(values)}">{items}</sst>'
    ).encode()


def _all_comments(template: Template) -> list:
    return [
        comment
        for section in template.sections
        for item in section.items
        for comment in item.comments
    ]


# --------------------------------------------------------------------------- #
# Canonical sample
# --------------------------------------------------------------------------- #


def test_spectora_importer_satisfies_protocol() -> None:
    assert isinstance(SpectoraXlsxImporter(), TemplateImporter)


def test_imports_canonical_spectora_sample() -> None:
    importer = SpectoraXlsxImporter()
    template = importer.import_template(
        SAMPLE_SHEET.read_bytes(), filename="interNACHI-template.xlsx"
    )

    assert template.source == "spectora"
    assert template.source_filename == "interNACHI-template.xlsx"
    assert template.name == "interNACHI-template"
    assert len(template.sections) == 13
    assert sum(len(section.items) for section in template.sections) == 69
    assert len(_all_comments(template)) == 392

    first_section = template.sections[0]
    assert first_section.name == "Inspection Details"
    assert first_section.display_order == 0
    assert first_section.items[0].name == "General"

    comments = _all_comments(template)
    assert comments[0].source_row == 2
    assert comments[-1].source_row == 393


def test_sample_maps_comment_type_answer_type_and_category_counts() -> None:
    template = SpectoraXlsxImporter().import_template(
        SAMPLE_SHEET.read_bytes(), filename="sample.xml"
    )
    comments = _all_comments(template)

    assert Counter(c.comment_type for c in comments) == {
        CommentType.INFO: 78,
        CommentType.DEFECT: 302,
        CommentType.LIMIT: 12,
    }
    assert Counter(c.answer_type for c in comments) == {
        AnswerType.BOOLEAN: 315,
        AnswerType.CHECKBOX: 72,
        AnswerType.NUMBER: 4,
        AnswerType.TEXT: 1,
    }
    assert Counter(c.category for c in comments) == {0: 281, 1: 21, None: 90}


def test_sample_preserves_content_text_verbatim() -> None:
    template = SpectoraXlsxImporter().import_template(
        SAMPLE_SHEET.read_bytes(), filename="sample.xml"
    )
    comments = _all_comments(template)

    nonempty = [c.content for c in comments if c.content]
    assert len(nonempty) == 309
    # Single XML-entity decode, then preserved verbatim: the export double-escaped
    # ampersands, so the literal "&amp;" string must survive the first decode.
    assert any("&amp;" in content for content in nonempty)
    # Markup is preserved, not sanitised.
    assert any("<p>" in content and "<strong>" in content for content in nonempty)


def test_sample_parses_options_and_estimates() -> None:
    template = SpectoraXlsxImporter().import_template(
        SAMPLE_SHEET.read_bytes(), filename="sample.xml"
    )
    comments = _all_comments(template)

    with_choice = [
        c for c in comments if c.options and c.options[0].option_type == OptionType.MULTIPLE_CHOICE
    ]
    with_unit = [
        c for c in comments if any(o.option_type == OptionType.UNIT_TYPE for o in c.options)
    ]
    assert len(comments) - len(with_choice) - len(with_unit) == 392 - 72 - 3

    general = template.sections[0].items[0]
    attendance = next(c for c in general.comments if c.name == "In Attendance")
    assert [o.value for o in attendance.options] == [
        "Listing Agent",
        "Home Owner",
        "Client",
        "Client's Agent",
    ]
    assert all(o.option_type == OptionType.MULTIPLE_CHOICE for o in attendance.options)
    assert [o.display_order for o in attendance.options] == [0, 1, 2, 3]

    temperature = next(c for c in general.comments if c.name == "Temperature")
    assert [o.value for o in temperature.options] == ["Fahrenheit (F)", "Celsius (C)"]
    assert all(o.option_type == OptionType.UNIT_TYPE for o in temperature.options)

    assert all(
        c.estimate_min == Decimal("10") and c.estimate_max == Decimal("1000") for c in comments
    )
    assert all(c.estimate_min is not None and c.estimate_max is not None for c in comments)


def test_sample_preserves_source_order_verbatim() -> None:
    template = SpectoraXlsxImporter().import_template(
        SAMPLE_SHEET.read_bytes(), filename="sample.xml"
    )
    exterior = next(section for section in template.sections if section.name == "Exterior")

    doors = next(item for item in exterior.items if item.name == "Exterior Doors")
    assert len(doors.comments) == 8
    # Duplicate order values in the source are preserved, not resequenced.
    assert [c.display_order for c in doors.comments] == [0, 0, 1, 2, 3, 4, 5, 6]

    siding = next(item for item in exterior.items if item.name == "Siding, Flashing &amp; Trim")
    # Gaps in the source order are also preserved.
    assert siding.comments[0].display_order == 0
    assert siding.comments[1].display_order == 2


def test_sample_reports_issues_per_column_deduplicated() -> None:
    template = SpectoraXlsxImporter().import_template(
        SAMPLE_SHEET.read_bytes(), filename="sample.xml"
    )
    assert [issue.issue_type for issue in template.issues] == [
        IssueType.UNSUPPORTED_CONTENT,
        IssueType.UNSUPPORTED_CONTENT,
        IssueType.SOURCE_DATA_MISSING,
        IssueType.SOURCE_DATA_MISSING,
    ]

    unsupported, missing = template.issues[0:2], template.issues[2:4]
    assert [(i.source_field, i.raw_value, i.source_row) for i in unsupported] == [
        ("Uses", "0", 2),
        ("Last Modified", "09/28/2026 08:21:41", 2),
    ]
    assert [i.source_field for i in missing] == ["Default Value 2", "Default Unit Type"]
    assert all(i.source_row is None for i in missing)
    assert {i.severity for i in unsupported} == {"warning"}
    assert {i.severity for i in missing} == {"info"}


def test_import_without_filename_uses_default_name() -> None:
    template = SpectoraXlsxImporter().import_template(SAMPLE_SHEET.read_bytes())
    assert template.name == "Imported template"
    assert template.source_filename is None


# --------------------------------------------------------------------------- #
# XLSX container
# --------------------------------------------------------------------------- #


def test_imports_sample_inside_xlsx_zip_container() -> None:
    sheet_bytes = SAMPLE_SHEET.read_bytes()
    archive = _xlsx_zip(("xl/worksheets/sheet1.xml", sheet_bytes))

    from_zip = SpectoraXlsxImporter().import_template(archive, filename="interNACHI-template.xlsx")
    from_xml = SpectoraXlsxImporter().import_template(
        sheet_bytes, filename="interNACHI-template.xlsx"
    )

    assert from_zip == from_xml
    assert from_zip.source == "spectora"
    assert len(from_zip.sections) == 13


def test_imports_shared_strings_worksheet() -> None:
    shared = [
        "Section Name",
        "Item Name",
        "Comment Name",
        "Comment Type",
        "Answer Type",
        "Garage",
        "Door Opener",
        "Opener Works",
        "info",
        "boolean",
    ]
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{NS}"><sheetData>'
        '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c>'
        '<c r="C1" t="s"><v>2</v></c><c r="D1" t="s"><v>3</v></c><c r="E1" t="s"><v>4</v></c></row>'
        '<row r="2"><c r="A2" t="s"><v>5</v></c><c r="B2" t="s"><v>6</v></c>'
        '<c r="C2" t="s"><v>7</v></c><c r="D2" t="s"><v>8</v></c><c r="E2" t="s"><v>9</v></c></row>'
        "</sheetData></worksheet>"
    ).encode()
    archive = _xlsx_zip(
        ("xl/worksheets/sheet1.xml", worksheet),
        ("xl/sharedStrings.xml", _shared_strings_xml(shared)),
    )

    template = SpectoraXlsxImporter().import_template(archive, filename="garage.xlsx")

    assert template.sections[0].name == "Garage"
    assert template.sections[0].items[0].name == "Door Opener"
    comment = template.sections[0].items[0].comments[0]
    assert comment.name == "Opener Works"
    assert comment.comment_type == CommentType.INFO
    assert comment.answer_type == AnswerType.BOOLEAN
    assert comment.source_row == 2


# --------------------------------------------------------------------------- #
# Synthetic mapping behaviour
# --------------------------------------------------------------------------- #


def test_maps_supported_fields_and_deduplicates_issues() -> None:
    rows = [
        [
            "Section Name",
            "Item Name",
            "Comment Name",
            "Comment Text",
            "Comment Type",
            "Answer Type",
            "Multiple Choice Options",
            "Default Value",
            "Default Unit Type",
            "Default Photo 2",
            "Default Estimate Min",
        ],
        [
            "Kitchen",
            "Lighting",
            "Overhead lights",
            "Check bulb & fixture",
            "defect",
            "checkbox",
            "LED, CFL, Incandescent",
            "on",
            "",
            "https://img.test/1",
            "12",
        ],
        ["Kitchen", "Lighting", "Fixture outlet", "", "info", "boolean", "", "", "", "", "12"],
        ["Bathroom", "Plumbing", "Leak", "", "defect", "boolean", "", "", "", "", ""],
    ]
    template = SpectoraXlsxImporter().import_template(
        _worksheet_xml(rows), filename="synthetic.xlsx"
    )

    assert [s.name for s in template.sections] == ["Kitchen", "Bathroom"]
    assert [s.display_order for s in template.sections] == [0, 1]

    kitchen = template.sections[0]
    assert kitchen.items[0].name == "Lighting"
    first, second = kitchen.items[0].comments
    assert [c.display_order for c in kitchen.items[0].comments] == [0, 1]

    assert first.name == "Overhead lights"
    assert first.content == "Check bulb & fixture"
    assert first.comment_type == CommentType.DEFECT
    assert first.answer_type == AnswerType.CHECKBOX
    assert first.default_value == "on"
    assert first.estimate_min == Decimal("12")
    assert [o.value for o in first.options] == ["LED", "CFL", "Incandescent"]
    assert all(o.option_type == OptionType.MULTIPLE_CHOICE for o in first.options)
    assert [o.display_order for o in first.options] == [0, 1, 2]
    assert not second.content
    assert second.estimate_min == Decimal("12")

    bathroom_item = template.sections[1].items[0]
    assert bathroom_item.comments[0].name == "Leak"
    assert bathroom_item.comments[0].source_row == 4
    assert bathroom_item.comments[0].estimate_min is None

    assert [i.issue_type for i in template.issues] == [
        IssueType.UNSUPPORTED_CONTENT,
        IssueType.SOURCE_DATA_MISSING,
    ]
    assert template.issues[0].source_field == "Default Photo 2"
    assert template.issues[0].source_row == 2
    assert template.issues[1].source_field == "Default Unit Type"


def test_invalid_mapped_values_fall_back_with_issues() -> None:
    rows = [
        [
            "Section Name",
            "Item Name",
            "Comment Name",
            "Comment Type",
            "Answer Type",
            "Category",
            "Order",
        ],
        ["Garage", "Door Opener", "C1", "schmoo", "nope", "2", "0"],
        ["Garage", "Door Opener", "C2", "info", "boolean", "0", "-3"],
    ]
    template = SpectoraXlsxImporter().import_template(_worksheet_xml(rows), filename="bad.xlsx")

    item = template.sections[0].items[0]
    assert item.comments[0].comment_type == CommentType.INFO
    assert item.comments[0].answer_type == AnswerType.BOOLEAN
    assert item.comments[0].category is None
    assert item.comments[1].display_order == 1  # negative Order -> first-appearance fallback

    assert len(template.issues) == 4
    assert all(i.issue_type == IssueType.INVALID_SOURCE_DATA for i in template.issues)
    # Comment type, answer type and category come from row 2; the negative order
    # value comes from row 3.
    assert [i.source_row for i in template.issues] == [2, 2, 2, 3]


def test_missing_order_column_uses_first_appearance_order() -> None:
    rows = [
        ["Section Name", "Item Name", "Comment Name", "Comment Type", "Answer Type"],
        ["Kitchen", "Lighting", "A", "info", "boolean"],
        ["Kitchen", "Lighting", "B", "info", "boolean"],
        ["Kitchen", "Appliances", "C", "defect", "boolean"],
    ]
    template = SpectoraXlsxImporter().import_template(_worksheet_xml(rows), filename="noorder.xlsx")

    assert [c.display_order for c in template.sections[0].items[0].comments] == [0, 1]
    assert template.sections[0].items[1].comments[0].display_order == 0
    assert template.issues == []


def test_unsupported_column_deduplicated_across_rows() -> None:
    rows = [
        ["Section Name", "Item Name", "Comment Name", "Comment Type", "Answer Type", "Locked"],
        ["K", "I", "A", "info", "boolean", "true"],
        ["K", "I", "B", "info", "boolean", "false"],
    ]
    template = SpectoraXlsxImporter().import_template(_worksheet_xml(rows), filename="locked.xlsx")

    assert len(template.issues) == 1
    issue = template.issues[0]
    assert issue.issue_type == IssueType.UNSUPPORTED_CONTENT
    assert issue.source_field == "Locked"
    assert issue.raw_value == "true"
    assert issue.source_row == 2


# --------------------------------------------------------------------------- #
# Malformed input
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("source", "match"),
    [
        (b"this is not a worksheet at all", "unreadable worksheet XML"),
        (b"<foo/>", "not a recognised Spectora template export"),
    ],
)
def test_unparseable_input_raises(source: bytes, match: str) -> None:
    with pytest.raises(TemplateImportError, match=match):
        SpectoraXlsxImporter().import_template(source)


def test_bad_zip_container_raises() -> None:
    with pytest.raises(TemplateImportError, match="ZIP"):
        SpectoraXlsxImporter().import_template(b"PK\x03\x04garbage-not-a-real-zip")


def test_zip_without_worksheet_raises() -> None:
    archive = _xlsx_zip(("hello.txt", b"hi"))
    with pytest.raises(TemplateImportError, match="sheet1.xml"):
        SpectoraXlsxImporter().import_template(archive)


def test_missing_required_column_raises() -> None:
    rows = [
        ["Section Name", "Item Name", "Comment Name", "Comment Type"],
        ["K", "I", "A", "info"],
    ]
    with pytest.raises(TemplateImportError, match="answer type"):
        SpectoraXlsxImporter().import_template(_worksheet_xml(rows))


def test_missing_required_row_value_raises() -> None:
    rows = [
        ["Section Name", "Item Name", "Comment Name", "Comment Type", "Answer Type"],
        ["K", "I", "", "info", "boolean"],
    ]
    with pytest.raises(TemplateImportError, match="Comment Name"):
        SpectoraXlsxImporter().import_template(_worksheet_xml(rows))


def test_header_only_worksheet_raises() -> None:
    rows = [["Section Name", "Item Name", "Comment Name", "Comment Type", "Answer Type"]]
    with pytest.raises(TemplateImportError, match="no template data rows"):
        SpectoraXlsxImporter().import_template(_worksheet_xml(rows))


# ---------------------------------------------------------------------------
# A second, structurally different export in the same format.
#
# The assignment says "We may try another export in the same HTML-text format", so
# these tests pin the claim that the importer is driven by the header row rather than
# by the shape of the committed InterNACHI file. SECOND_SHEET carries 12 of the 42
# columns, an extra column the importer does not model, and four dirty values.
# ---------------------------------------------------------------------------


def test_second_export_imports_without_the_canonical_columns() -> None:
    """A leaner export with none of the optional InterNACHI columns still imports."""
    template = SpectoraXlsxImporter().import_template(
        SECOND_SHEET.read_bytes(), filename="commercial-rental.xml"
    )

    assert template.name == "commercial-rental"
    assert template.source == "spectora"
    assert [section.name for section in template.sections] == ["Exterior", "Interior", "Systems"]
    assert sum(len(section.items) for section in template.sections) == 4
    assert len(_all_comments(template)) == 6


def test_second_export_maps_the_columns_it_does_carry() -> None:
    template = SpectoraXlsxImporter().import_template(SECOND_SHEET.read_bytes())
    comments = _all_comments(template)

    roofing = next(c for c in comments if c.name == "Roofing Material")
    assert roofing.comment_type is CommentType.INFO
    assert roofing.answer_type is AnswerType.CHECKBOX
    assert roofing.category == 0
    assert [o.value for o in roofing.options] == [
        "Asphalt",
        "Composition",
        "Metal",
        "Tile",
        "Wood Shake",
    ]
    assert all(o.option_type is OptionType.MULTIPLE_CHOICE for o in roofing.options)

    age = next(c for c in comments if c.name == "Estimated Age")
    assert age.content == "Enter the age of the covering in years."
    assert age.answer_type is AnswerType.NUMBER
    assert age.category == -1

    joist = next(c for c in comments if c.name == "Joist Support")
    assert joist.comment_type is CommentType.DEFECT
    assert joist.category == 1


def test_second_export_absent_optional_columns_are_left_unset() -> None:
    """Columns the export omits must not be invented, and must not raise."""
    template = SpectoraXlsxImporter().import_template(SECOND_SHEET.read_bytes())

    for comment in _all_comments(template):
        assert comment.estimate_min is None
        assert comment.estimate_max is None
        assert comment.recommendation is None
        assert comment.default_unit_type is None
        assert comment.default_value_2 is None


def test_second_export_preserves_ordering_from_the_export() -> None:
    """Section/item/comment order comes from the export, not from row position."""
    template = SpectoraXlsxImporter().import_template(SECOND_SHEET.read_bytes())

    assert [s.display_order for s in template.sections] == [0, 1, 2]
    systems = template.sections[2]
    assert [i.name for i in systems.items] == ["Electrical", "Plumbing"]
    assert [i.display_order for i in systems.items] == [0, 1]
    plumbing = systems.items[1]
    assert [c.name for c in plumbing.comments] == ["Water Heater", "Supply Condition"]
    assert [c.display_order for c in plumbing.comments] == [0, 1]
    assert [c.source_row for c in plumbing.comments] == [6, 7]


def test_second_export_surfaces_dirty_values_instead_of_coercing_silently() -> None:
    """Every bad value in the second export is reported, not quietly fixed."""
    template = SpectoraXlsxImporter().import_template(SECOND_SHEET.read_bytes())
    by_field = {issue.source_field: issue for issue in template.issues}

    assert set(by_field) == {
        "Comment Type",
        "Answer Type",
        "Category",
        "Inspector Signature Required",
        "Last Modified",
    }
    for issue in template.issues:
        assert issue.severity.value == "warning"

    # Data that is present but wrong is INVALID_SOURCE_DATA; a column with nowhere to go
    # is UNSUPPORTED_CONTENT. Both are reported; neither is dropped.
    invalid = {
        i.source_field for i in template.issues if i.issue_type is IssueType.INVALID_SOURCE_DATA
    }
    assert invalid == {"Comment Type", "Answer Type", "Category"}

    # The bad values fall back to something safe, and the fallback is reported.
    assert "observation" in by_field["Comment Type"].message
    assert "multi-select" in by_field["Answer Type"].message
    assert "critical" in by_field["Category"].message

    water_heater = next(c for c in _all_comments(template) if c.name == "Water Heater")
    assert water_heater.comment_type is CommentType.INFO
    assert water_heater.answer_type is AnswerType.BOOLEAN
    assert water_heater.category is None
    # Data in a column the schema has no home for is still preserved as an option value.
    assert [o.value for o in water_heater.options] == ["Gas", "Electric", "Solar"]


def test_second_export_reports_unmodeled_column_as_unsupported_content() -> None:
    """A column the importer cannot represent is surfaced, never dropped in silence."""
    template = SpectoraXlsxImporter().import_template(SECOND_SHEET.read_bytes())

    unsupported = [i for i in template.issues if i.issue_type is IssueType.UNSUPPORTED_CONTENT]
    assert {i.source_field for i in unsupported} == {
        "Inspector Signature Required",
        "Last Modified",
    }
    # One issue per unmodeled column, not one per data row.
    assert len([i for i in unsupported if i.source_field == "Last Modified"]) == 1
