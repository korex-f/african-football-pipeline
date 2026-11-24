# 13. Build the new code next to the old code, and prove that they are equal

*Status: accepted (November 2026). [All decisions](README.md)*

- **What:** The project does not replace a part of the pipeline in one step. It builds the new part next to the old part. A *parity test* runs the two parts on the same input and compares the outputs. Only after the outputs are equal does the pipeline change to the new part. Then the project removes the old part and its parity test.
- **The debate:**
  1. **Replace in one step.** This is faster to write. But if the output changes, it is difficult to find the cause, because many parts changed together.
  2. **Build next to the old code (the decision).** Each pull request adds one new part and one parity test. The old code stays the reference until the switch.
- **How:** Step 2 uses this method three times:

  | Pull request | New part | Parity test |
  |---|---|---|
  | Part 2 | Python parser | `extract_stages` and `EXTRACT_STAGE_JS` give the same rows (Chromium) |
  | Part 3a | Legacy exporter | Parser, `SourceMatch` and exporter give the same dictionaries as `parse_match_row` (no browser) |
  | Part 3b | Soccerway adapter | A live scrape gives the same JSON as a new baseline from the old scraper: 306 matches, 4,590 fields, 0 differences |

  The tests of part 3a do not need a browser, because the parity test of part 2 already proved that `extract_stages` gives the same rows as the JavaScript.

  For each parity test, the project broke the new code on purpose. The test must fail. A test that never failed proves nothing.
- **Trade-offs:**
  - For some time, the project has two versions of the same function. A person must not change only one of them.
  - Parity tests use fixtures. A fixture does not have all the special cases of the live site. Thus, part 3b also has a live check.
  - The parity tests are temporary. The project must remember to remove them after the switch.
