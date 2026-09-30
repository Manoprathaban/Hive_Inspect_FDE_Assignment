"""Expected-output ("golden") tests for every committed import fixture.

:mod:`tests.golden` projects an imported template into plain JSON; each fixture has a
committed file under ``sample-data/expected/`` produced by
``python -m scripts.refresh_expected_output``. These tests re-import each fixture through
the real importer and compare, so a mapping regression fails with a readable diff instead
of silently changing what a reviewer would see in the app.

Two things this deliberately does *not* do:

* It does not hand-edit expectations. Goldens are regenerated and reviewed, so a changed
  golden is always a deliberate, visible decision.
* It does not try to re-assert what ``test_spectora_importer.py`` already asserts. This
  module covers what the goldens add: whole-tree equality per fixture, fixture/golden
  completeness, and the committed malformed-input artifacts.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from app.adapters.importers.spectora_xlsx import SpectoraXlsxImporter
from app.domain.exceptions import TemplateImportError
from tests.golden import (
    EXPECTED_DIR,
    SAMPLE_DATA,
    full_projection,
    summary_projection,
)

# The canonical export is compared as a summary (counts/tallies/issues): a full
# projection of 392 comments is unreadable and adds no signal beyond the tallies.
SUMMARY_FIXTURES = frozenset({"sheet1.xml"})

FIXTURES = (
    "sheet1.xml",
    "commercial-rental.xml",
    "multiselect-checklist.xml",
    "deep-nesting.xml",
    "edge-cases.xml",
    "shared-strings-checklist.xlsx",
)

INVALID_FIXTURES = {
    "wrong-root.xml": "not a recognised Spectora template export",
    "missing-answer-type.xml": "answer type",
}


def _committed_fixtures() -> set[str]:
    """Importable fixture files committed at the top level of ``sample-data``."""

    return {
        path.name
        for path in SAMPLE_DATA.iterdir()
        if path.is_file() and path.suffix.lower() in {".xml", ".xlsx"}
    }


# --------------------------------------------------------------------------- #
# Golden equality
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("filename", FIXTURES)
def test_fixture_matches_committed_expected_output(filename: str) -> None:
    source = SAMPLE_DATA / filename
    assert source.is_file(), f"fixture {filename} is missing"

    template = SpectoraXlsxImporter().import_template(source.read_bytes(), filename=filename)
    projection = (
        summary_projection(template) if filename in SUMMARY_FIXTURES else full_projection(template)
    )

    expected_file = EXPECTED_DIR / f"{source.stem}.json"
    assert expected_file.is_file(), (
        f"no expected output for {filename}; run python -m scripts.refresh_expected_output"
    )
    assert projection == _load(expected_file), (
        f"{filename} no longer matches {expected_file.name}; "
        f"if the change is intended run python -m scripts.refresh_expected_output "
        f"and review the diff"
    )


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def test_every_committed_fixture_has_expected_output() -> None:
    """A new fixture without a golden would be silently unreviewed."""

    committed = _committed_fixtures()
    assert committed == set(FIXTURES), (
        "sample-data gained/lost a fixture; add it to FIXTURES and regenerate goldens"
    )
    for filename in committed:
        assert (EXPECTED_DIR / f"{Path(filename).stem}.json").is_file(), filename


def test_no_orphan_expected_output_files() -> None:
    fixtures = {Path(name).stem for name in FIXTURES}
    orphans = {path.stem for path in EXPECTED_DIR.glob("*.json")} - fixtures
    assert not orphans, f"expected-output files with no fixture: {sorted(orphans)}"


# --------------------------------------------------------------------------- #
# Canonical export: the artifact the assignment is judged on
# --------------------------------------------------------------------------- #


def test_canonical_summary_pins_aggregate_shape() -> None:
    expected = _load(EXPECTED_DIR / "sheet1.json")
    assert expected["counts"]["sections"] == 13
    assert expected["counts"]["items"] == 69
    assert expected["counts"]["comments"] == 392
    # Data starts on row 2 (row 1 is the header) and runs to the last populated row.
    assert expected["first_and_last_source_row"] == [2, 393]


def test_canonical_summary_pins_value_tallies() -> None:
    expected = _load(EXPECTED_DIR / "sheet1.json")
    assert expected["tallies"]["comment_type"] == {"defect": 302, "info": 78, "limit": 12}
    assert expected["tallies"]["answer_type"] == {
        "boolean": 315,
        "checkbox": 72,
        "number": 4,
        "text": 1,
    }


def test_canonical_summary_pins_reported_issues() -> None:
    """The real export is *expected* to report issues; silence would be the bug."""

    expected = _load(EXPECTED_DIR / "sheet1.json")
    assert [(i["issue_type"], i["source_field"]) for i in expected["issues"]] == [
        ("UNSUPPORTED_CONTENT", "Uses"),
        ("UNSUPPORTED_CONTENT", "Last Modified"),
        ("SOURCE_DATA_MISSING", "Default Value 2"),
        ("SOURCE_DATA_MISSING", "Default Unit Type"),
    ]


def test_canonical_export_double_escaped_ampersand_is_preserved_not_silently_fixed() -> None:
    """The source cells contain the literal text ``&amp;``.

    The export wrote ``&amp;amp;``, which decodes once to ``&amp;``. The importer decodes
    exactly one level and preserves the rest, per the "preserve text/content" rule. The
    golden records this on purpose: if someone later "fixes" the unescaping, the diff here
    makes the behaviour change visible rather than silent.
    """

    expected = _load(EXPECTED_DIR / "sheet1.json")
    assert "Basement, Foundation, Crawlspace &amp; Structure" in expected["section_names"]
    # Sanity-check the premise: the same importer decodes a normal entity correctly,
    # so the preserved "&amp;" above is source data, not a decoding failure.
    edge = _load(EXPECTED_DIR / "edge-cases.json")
    names = [c["name"] for s in edge["sections"] for i in s["items"] for c in i["comments"]]
    assert "HTML & markup <b>bold</b>" in names


# --------------------------------------------------------------------------- #
# Ordering contract
# --------------------------------------------------------------------------- #


def test_deep_nesting_records_declared_order_verbatim_without_resequencing() -> None:
    """The importer records the ``Order`` column; it does not sort by it.

    Source rows for ``Roofing`` are Third(2), First(0), Second(1). The importer keeps
    source-row order and stores the declared value as ``display_order``; the Postgres
    repository is what sorts on read (``ORDER BY item_id, display_order, id``). The
    canonical export has no non-monotonic item, so only a synthetic fixture can pin this.
    """

    expected = _load(EXPECTED_DIR / "deep-nesting.json")
    roofing = expected["sections"][0]["items"][0]
    assert roofing["name"] == "Roofing"
    assert [c["name"] for c in roofing["comments"]] == ["Third", "First", "Second"]
    assert [c["display_order"] for c in roofing["comments"]] == [2, 0, 1]
    assert [c["source_row"] for c in roofing["comments"]] == [2, 3, 4]


# --------------------------------------------------------------------------- #
# Text-handling contract
# --------------------------------------------------------------------------- #


def test_edge_cases_pin_trim_versus_verbatim_text_handling() -> None:
    expected = _load(EXPECTED_DIR / "edge-cases.json")
    comments = {
        c["name"]: c for s in expected["sections"] for i in s["items"] for c in i["comments"]
    }

    # Names are stripped...
    assert "Whitespace in name is trimmed" in comments
    # ...while content is preserved byte-for-byte, including whitespace-only content.
    assert comments["Whitespace in name is trimmed"]["content"] == "   "
    # An absent cell becomes "", never null.
    assert comments["Blank text"]["content"] == ""
    # Non-ASCII survives the round trip.
    assert "Unicode: café, naïve, 日本語, emoji 🔧" in comments


# --------------------------------------------------------------------------- #
# Real XLSX container
# --------------------------------------------------------------------------- #


def test_xlsx_fixture_is_a_real_zip_container() -> None:
    """Guards the fixture from being replaced by a text file with an .xlsx name."""

    path = SAMPLE_DATA / "shared-strings-checklist.xlsx"
    assert zipfile.is_zipfile(path)
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
    assert "xl/worksheets/sheet1.xml" in names
    assert "xl/sharedStrings.xml" in names


def test_xlsx_fixture_exercises_the_shared_string_table() -> None:
    expected = _load(EXPECTED_DIR / "shared-strings-checklist.json")
    assert expected["counts"] == {
        "sections": 1,
        "items": 2,
        "comments": 3,
        "options": 4,
        "issues": 0,
    }
    fencing = expected["sections"][0]["items"][0]
    assert [o["value"] for o in fencing["comments"][1]["options"]] == [
        "Wood",
        "Vinyl",
        "Aluminum",
        "Chain Link",
    ]


def test_xlsx_generator_reproduces_every_part_of_the_committed_fixture() -> None:
    """The binary fixture is generated, so the generator must stay working.

    If this breaks, `sample-data/shared-strings-checklist.xlsx` becomes an unreproducible
    blob that nobody can regenerate or explain. Parts are compared by name and content
    rather than by raw bytes: ZIP entries carry a build timestamp, so byte equality is not
    a property the build can have.
    """

    from scripts.refresh_expected_output import _xlsx_fixture_bytes

    with zipfile.ZipFile(io.BytesIO(_xlsx_fixture_bytes())) as fresh:
        fresh_parts = {name: fresh.read(name) for name in fresh.namelist()}

    with zipfile.ZipFile(SAMPLE_DATA / "shared-strings-checklist.xlsx") as committed:
        committed_parts = {name: committed.read(name) for name in committed.namelist()}

    assert fresh_parts == committed_parts


def test_xlsx_generator_output_is_importable_on_its_own() -> None:
    """A freshly built workbook must import, not just match bytes."""

    from scripts.refresh_expected_output import _xlsx_fixture_bytes

    template = SpectoraXlsxImporter().import_template(
        _xlsx_fixture_bytes(), filename="generated.xlsx"
    )
    assert template.sections[0].name == "Yard"
    assert len(template.issues) == 0


# --------------------------------------------------------------------------- #
# Committed malformed-input artifacts
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("filename", "match"), sorted(INVALID_FIXTURES.items()))
def test_invalid_fixture_is_rejected(filename: str, match: str) -> None:
    path = SAMPLE_DATA / "invalid" / filename
    assert path.is_file(), f"invalid fixture {filename} is missing"
    with pytest.raises(TemplateImportError, match=match):
        SpectoraXlsxImporter().import_template(path.read_bytes(), filename=filename)
