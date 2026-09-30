"""Regenerate the committed expected-output files and the binary XLSX fixture.

Expected-output files are *derived* artifacts: hand-editing one defeats the point, and a
mapping change should be visible as a reviewable diff. This script re-imports each fixture
through the real importer and rewrites its golden, so a legitimate change is made by
running it and reviewing the diff — never by typing the new expectation by hand.

It also (re)builds ``shared-strings-checklist.xlsx``, the one fixture that must be a real
ZIP container, because a binary blob is not reviewable in a diff.

Usage
-----
From ``backend``::

    python -m scripts.refresh_expected_output            # rewrite every golden
    python -m scripts.refresh_expected_output --check    # exit 1 if any golden is stale
    python -m scripts.refresh_expected_output --only multiselect-checklist.xml

``--check`` is the CI-friendly mode: it never writes, so a stale golden fails the build
instead of being silently rubber-stamped.
"""

from __future__ import annotations

import argparse
import io
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.adapters.importers.spectora_xlsx import SpectoraXlsxImporter  # noqa: E402
from tests.golden import (  # noqa: E402
    EXPECTED_DIR,
    SAMPLE_DATA,
    full_projection,
    render,
    summary_projection,
)

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
PKG_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

XML_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'


def _part(body: str) -> bytes:
    """Wrap an XML fragment body in the declaration every part needs."""

    return f"{XML_DECL}{body}".encode()


def _default(extension: str, content_type: str) -> str:
    return f'<Default Extension="{extension}" ContentType="{content_type}"/>'


def _override(part_name: str, content_type: str) -> str:
    return f'<Override PartName="{part_name}" ContentType="{content_type}"/>'


def _relationship(rel_id: str, rel_type: str, target: str) -> str:
    return f'<Relationship Id="{rel_id}" Type="{rel_type}" Target="{target}"/>'


# filename -> summary instead of full. sheet1 has 392 comments; a full golden for it would
# be unreadable noise, so its signal lives in the counts/tallies instead.
SUMMARY_FIXTURES = {"sheet1.xml"}
FIXTURES = [
    "sheet1.xml",
    "commercial-rental.xml",
    "multiselect-checklist.xml",
    "deep-nesting.xml",
    "edge-cases.xml",
    "shared-strings-checklist.xlsx",
]


def _xlsx_fixture_bytes() -> bytes:
    """Build a genuine XLSX using sharedStrings (the other path, not inlineStr)."""

    header = [
        "Section Name",
        "Item Name",
        "Comment Name",
        "Comment Text",
        "Comment Type",
        "Answer Type",
        "Multiple Choice Options",
    ]
    rows = [
        [
            "Yard",
            "Fencing",
            "Gate latch secure",
            "Confirm the gate latches without a key.",
            "info",
            "boolean",
            "",
        ],
        [
            "Yard",
            "Fencing",
            "Material",
            "Identify the fencing material.",
            "info",
            "checkbox",
            "Wood, Vinyl, Aluminum, Chain Link",
        ],
        [
            "Yard",
            "Shed",
            "Flooring condition",
            "",
            "defect",
            "text",
            "",
        ],
    ]

    # Deduplicate into a shared string table, the way Excel writes one.
    table: list[str] = []

    def shared(value: str) -> int:
        if value not in table:
            table.append(value)
        return table.index(value)

    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    sheet_lines = [
        XML_DECL,
        f'<worksheet xmlns="{NS}">',
        "<sheetData>",
    ]
    for row_number, row in enumerate([header, *rows], start=1):
        cells = []
        for index, value in enumerate(row):
            if value:
                cells.append(
                    f'<c r="{letters[index]}{row_number}" t="s"><v>{shared(value)}</v></c>'
                )
        sheet_lines.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    sheet_lines.append("</sheetData>")
    sheet_lines.append("</worksheet>")
    sheet_xml = "\n".join(sheet_lines).encode()

    items = "".join(f"<si><t>{escape(value)}</t></si>" for value in table)
    shared_xml = _part(f'<sst xmlns="{NS}" uniqueCount="{len(table)}">{items}</sst>')

    content_types = _part(
        f'<Types xmlns="{PKG_NS}">'
        + _default("rels", "application/vnd.openxmlformats-package.relationships+xml")
        + _default("xml", "application/xml")
        + _override(
            "/xl/workbook.xml",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
        )
        + _override(
            "/xl/worksheets/sheet1.xml",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml",
        )
        + _override(
            "/xl/sharedStrings.xml",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml",
        )
        + "</Types>"
    )

    rels = _part(
        f'<Relationships xmlns="{PKG_NS}">'
        + _relationship("rId1", f"{DOC_REL}/officeDocument", "xl/workbook.xml")
        + "</Relationships>"
    )

    workbook = _part(
        f'<workbook xmlns="{NS}" xmlns:r="{DOC_REL}">'
        '<sheets><sheet name="Checklist" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )

    workbook_rels = _part(
        f'<Relationships xmlns="{PKG_NS}">'
        + _relationship("rId1", f"{DOC_REL}/worksheet", "worksheets/sheet1.xml")
        + _relationship("rId2", f"{DOC_REL}/sharedStrings", "sharedStrings.xml")
        + "</Relationships>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/sharedStrings.xml", shared_xml)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return buffer.getvalue()


def expected_name(filename: str) -> str:
    return f"{Path(filename).stem}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify instead of writing")
    parser.add_argument("--only", help="refresh a single fixture by filename")
    args = parser.parse_args()

    fixtures = [args.only] if args.only else FIXTURES
    importer = SpectoraXlsxImporter()
    EXPECTED_DIR.mkdir(parents=True, exist_ok=True)
    stale: list[str] = []

    for filename in fixtures:
        source = SAMPLE_DATA / filename
        if filename.endswith(".xlsx"):
            source.write_bytes(_xlsx_fixture_bytes())

        template = importer.import_template(source.read_bytes(), filename=filename)
        projection = (
            summary_projection(template)
            if filename in SUMMARY_FIXTURES
            else full_projection(template)
        )
        target = EXPECTED_DIR / expected_name(filename)
        payload = render(projection)

        if args.check:
            current = target.read_text(encoding="utf-8") if target.exists() else ""
            if current != payload:
                stale.append(filename)
            continue

        target.write_text(payload, encoding="utf-8")
        print(f"wrote {target.relative_to(SAMPLE_DATA.parent)} ({filename})")

    if args.check:
        if stale:
            print(
                "stale expected-output files: "
                + ", ".join(stale)
                + "\nrun: python -m scripts.refresh_expected_output",
                file=sys.stderr,
            )
            return 1
        print("all expected-output files are up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
