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

Future importer fixtures (other brands, mocked XLSX/CSV variants) go in this directory.
Each fixture should document its provenance and which importer it targets.