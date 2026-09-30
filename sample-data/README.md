# sample-data

Real-world inputs used to develop and test template importers.

Every importable fixture here has a committed **expected output** under `expected/`, and
`backend/tests/test_expected_output.py` fails if an import stops matching it. See
[Expected output](#expected-output) below for how to read and regenerate those files.

## Importable fixtures

| Fixture | Source | What it exists to prove |
| --- | --- | --- |
| `sheet1.xml` | **Real** Spectora export | The canonical integration artifact. |
| `commercial-rental.xml` | Synthetic | Importer is header-driven, not shape-driven. |
| `multiselect-checklist.xml` | Synthetic | Every answer type, options, defaults and estimates in one clean file. |
| `deep-nesting.xml` | Synthetic | `Order` is recorded verbatim, not resequenced. |
| `edge-cases.xml` | Synthetic | Exact text handling: entities, unicode, blank and whitespace cells. |
| `shared-strings-checklist.xlsx` | Synthetic, **real ZIP/XLSX** | The `sharedStrings` code path and a genuine binary upload. |

## Malformed fixtures

`invalid/` holds inputs that must be **rejected** (HTTP 422), for manual API testing:

| Fixture | Why it is rejected |
| --- | --- |
| `invalid/wrong-root.xml` | Well-formed XML, but not a Spectora worksheet. |
| `invalid/missing-answer-type.xml` | Missing the required `Answer Type` column. |

---

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
- **Imported shape:** 13 sections, 69 items, 392 comments, 520 comment options, 4 issues.

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

## multiselect-checklist.xml

- **Source:** synthetic, no customer data.
- **What it exists to prove:** a full-coverage mapping case. It populates **every column the
  importer models** — all six answer types (`boolean`, `checkbox`, `date`, `number`,
  `range`, `text`), multiple-choice and unit-type options, `default value`,
  `default value 2`, `default unit type`, and both estimate bounds — so it imports with
  **zero** issues. The `Comment Type (info, limit, defect)` header also exercises the
  importer's header normalisation (the parenthetical hint is stripped).
- **Reading the goldens:** `estimate_min`/`estimate_max` are serialised as strings because
  they are `Decimal` in the domain model, not floats.

## deep-nesting.xml

- **Source:** synthetic, no customer data.
- **What it exists to prove:** the `Order` column is **recorded, not enforced**. The
  `Roofing` item's rows declare `Third`=2, `First`=0, `Second`=1, and the importer keeps
  them in source-row order while storing the declared values as `display_order`. Ordering
  for display is applied later, by the Postgres repository (`ORDER BY item_id,
  display_order, id`), so the importer must not silently renumber someone else's data.
- **Why a synthetic fixture is required:** in the canonical `sheet1.xml` **no** item has a
  non-monotonic `Order` column, so the real export cannot distinguish "importer sorts" from
  "importer preserves". Only this fixture can.

## edge-cases.xml

- **Source:** synthetic, no customer data.
- **What it exists to prove:** the importer's exact text contract, which is asymmetric and
  therefore worth pinning:
  - names are `.strip()`ed — `"  Whitespace in name is trimmed  "` imports trimmed;
  - content is preserved **verbatim** — a whitespace-only cell stays `"   "`, and an empty
    cell becomes `""` (never `null`);
  - XML entities are decoded exactly **one** level — `&amp;` becomes `&`;
  - non-ASCII survives unchanged (`café`, `日本語`, `🔧`).
- **Related:** `sheet1.xml` contains the literal text `&amp;` in section and item names
  because the export wrote `&amp;amp;`. The importer preserves it rather than guessing.
  `test_canonical_export_double_escaped_ampersand_is_preserved_not_silently_fixed` pins
  both halves of that behaviour.

## shared-strings-checklist.xlsx

- **Source:** synthetic, no customer data. **Generated**, not hand-written — see below.
- **What it exists to prove:** a genuine ZIP/OOXML upload resolves cell values through
  `xl/sharedStrings.xml` (the index-based path), which is a different code path from the
  inline `SpreadsheetML` the other fixtures use. It is the fixture to upload when you want
  to prove a browser/API upload of a normal `.xlsx` file works end to end.

---

## Expected output

`expected/<fixture>.json` is the **expected import result** for the fixture of the same
name. Two shapes are used:

- **Full** — every section, item, comment, option and issue. Used for the small synthetic
  fixtures, where the whole mapping is meant to be reviewable by eye.
- **Summary** — counts, per-value tallies, section/item names and the issue list. Used for
  `sheet1.json` only: a full projection of 392 comments would be ~40k lines of noise, so
  the signal lives in the tallies and the `first_and_last_source_row` bounds instead.

### How to read one

Open the file and compare it against what the app shows. If the counts, the tallies, the
names or the issue list disagree with the upload you just did, the importer is doing
something you did not expect. Blank `default_value`/`recommendation`/`estimate_*` fields
mean *the source cell was empty*, not that the importer dropped something.

### How to regenerate

Expected output is a **derived** artifact — never hand-edit it, or the file stops being
evidence of anything. From `backend/`:

```bash
python -m scripts.refresh_expected_output            # rewrite all goldens + the .xlsx
python -m scripts.refresh_expected_output --check    # exit 1 if any golden is stale
python -m scripts.refresh_expected_output --only sheet1.xml
```

The command re-imports each fixture through the real importer, so a regenerated golden can
only differ from the old one if the importer's behaviour actually changed. Review that
diff before committing: it *is* the record of what changed.

`--check` never writes, which makes it the CI-safe mode. `backend/tests/test_expected_output.py`
performs the same comparison on every test run, and additionally fails if a fixture has no
golden, or a golden has no fixture.

### Verifying an upload by hand

1. Start the API (`POST /api/templates/import`, multipart field `file`, `Authorization:
   Bearer dev-token` locally).
2. Upload a fixture from this directory.
3. Compare the response against the matching `expected/*.json`:
   - full fixtures → compare section/item/comment order, then spot-check `content`,
     `answer_type`, `options` and `estimate_*`;
   - `sheet1.xml` → compare `counts` and `tallies`, and confirm all 4 issues are reported
     (the real export is *expected* to produce issues; silence would be the bug).
4. Confirm the rejected fixtures return 422.

The order you see in an API response may differ from the `display_order` values in a
golden: the API sorts by `display_order` on read, while the golden shows the importer's
in-memory order. The canonical export's orders are already monotonic, so for `sheet1.xml`
the two always agree.

---

Future importer fixtures (other brands, mocked XLSX/CSV variants) go in this directory.
Each fixture should document its provenance, which importer it targets, and what it exists
to prove. If you add one, add it to `FIXTURES` in
`backend/tests/test_expected_output.py` and regenerate the expected output.
