# sample-data

Real-world inputs used to develop and test template importers.

## sheet1.xml

- **Source:** Spectora — InterNACHI Residential Home Inspection **template** worksheet export.
- **Commit origin:** added as `a035a34 "Add Spectora InterNACHI Residential template export"`.
- **Structure:** SpreadsheetML worksheet, range `A1:AP393` (42 columns × 393 rows).
  Row 1 is a header describing each column (e.g. `Section Name`, `Item Name`, `Comment
  Name`, `Comment Text`, `Comment Type`, `Category`, `units`, `recommendation`, `order`,
  answer types, defaults, `Last Modified`). Rows 2–393 contain the template content.
- **Role:** the canonical sample the `TemplateImporter` boundary is designed around — the
  exact file READ (byte-for-byte identical) as both the committed version and the
  developer's local working copy.

## commercial-rental.xml

- **Source:** synthetic. Written for this assignment to answer the brief's "We may try
  another export in the same HTML-text format" — it is **not** a real customer export and
  contains no customer data.
- **Structure:** the same SpreadsheetML worksheet format, but deliberately unlike
  `sheet1.xml`: 12 columns instead of 42, a different template (a commercial rental
  walkthrough), and an extra column the importer does not model.
- **What it exists to prove:** the importer is driven by the header row, not by the shape of
  the InterNACHI file. This fixture omits *every* optional column the importer models
  (estimates, recommendation, unit types, defaults) and adds one it has no home for
  (`Inspector Signature Required`), so it only imports correctly if the mapping is
  header-driven and optional columns are genuinely optional.
- **Also carries four dirty values** that must each surface as an import issue rather than
  being silently coerced — an unknown `Comment Type` (`observation`), an unknown
  `Answer Type` (`multi-select`), a non-integer `Category` (`critical`), plus the two
  unmodeled columns. These become 3 `INVALID_SOURCE_DATA` issues and 2
  `UNSUPPORTED_CONTENT` issues.
- **Covered by:** `test_second_export_*` in `backend/tests/test_spectora_importer.py`.

Future importer fixtures (other brands, mocked XLSX/CSV variants) go in this directory.
Each fixture should document its provenance and which importer it targets.