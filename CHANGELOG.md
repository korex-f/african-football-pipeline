# Changelog

Each entry records what changed, why, how, the verification and the trade-offs. The newest entry is first.

## November 2026: Dates on RSSSF pages

**What happened:** The parser takes the years of a season from the page title for its dates, chooses the window of 12 months by a search, reads French and Portuguese month names and dates on group headings, and reports a season of more than 12 months.

**Why it was necessary:** The survey found 703 year-size jumps in 298 seasons. The list of champions gives one year for 375 seasons over two years (`2019` = `Angola 2018/19`), and the first month on a page is not always the first month of the season.

**How the project did it** ([decision 29](docs/decisions/0029-dates.md)): `title_years()`, `_date_window()`, `_month()`, `_ZONE` with group words, and `ParseResult.year_jumps`. The user chose the title for the dates only; the season labels do not change. Module README sections 28 and 29.

**Verification:**

1. **All survey seasons**, compared with `main`: year-size jumps 20 in 18 seasons (703 in 298). Dates outside the years of the page title: 3 (243). Matches with a date: 232,663 (232,195).
2. **Nigeria, Ghana and Egypt:** 10 seasons with other dates; 21,149 matches with a date (21,099). Nigeria 2001 now starts in November 2000.
3. 33 new tests, with 3 survey pages as fixtures. 10 deliberate breaks, each caught. Two rules were first tested with made-up data and the survey showed the error: the date with its year (Eritrea 2009) and the lower limit of the problem (Egypt 2019/20).

**Trade-offs:** A season of more than 12 months (Namibia 1997/98, the seasons of 2019/20 that stopped for COVID-19) has dates with a wrong year; 51 seasons show the problem. The season labels stay from the list, thus Angola `2019` has dates from 2018.
## November 2026: Season lines in the lists of champions

**What happened:** `parse_index()` reads season lines with a row number or italics before the link, seasons with `-` (`2021-22`), and a heading with a column label before it (`year    <b>PSL</b>`).

**Why it was necessary:** The survey found season links that the index did not read: all the seasons of Congo from 1979 to 1994 were missing, and South Africa's 30 PSL seasons were in the wrong list.

**How the project did it** ([decision 28](docs/decisions/0028-index-line-forms.md)): `_SEASON_LINE`, `_LABEL` and `_BOLD_LINE`. A script compared every link with a year in the 55 lists with the entries (module README section 27).

**Verification:**

1. **55 lists of the survey**, compared with `main`: 22 new entries, 30 entries in the correct section, 0 entries lost. Links not read: 11 of 2,762 (33), each with a reason. Nigeria, Ghana and Egypt do not change.
2. 14 new tests, with 2 lists of champions as fixtures (Congo, South Africa). 5 deliberate breaks, each caught.

**Trade-offs:** `1974,1`, `1966-68` and the typo `1990/00` are not read. A line with several columns keeps all of them in its champion text.

## November 2026: Table row forms on RSSSF pages

**What happened:** The table reader reads two more forms of a full row (goals in two columns, points first) and a mark after the points.

**Why it was necessary:** After decision 26, the survey had 1,180 table rows reported as "not read". About 280 of them are full rows in another order.

**How the project did it** ([decision 27](docs/decisions/0027-table-row-forms.md)): `_ROW_GOAL_COLUMNS`, `_ROW_POINTS_FIRST` and `_ROW_FORMS`, tried in sequence by `_table_row()`. The model refuses a row read in a wrong order. Module README section 26.

**Verification:**

1. **All survey seasons**, compared with `main`: 21,310 table rows (21,079) in 1,468 seasons (1,449). Problems: 975 (1,243). Table checks that agree: 903 (896). No season has fewer rows; no check is worse.
2. 7 new tests, with 3 survey pages as fixtures. 5 deliberate breaks, each caught.

**Trade-offs:** About 900 short rows (points only, played and points) stay problems: they need a model and database change (the user chose full forms only).

## November 2026: Final tables on RSSSF pages of all African countries

**What happened:** The table reader accepts more headings of a final table (`Reported Final Table:`, `Final(?) Table:`, `Final Ranking:`, `Official Table ...:`) and the group words `Poule`, `Groupe` and `Grupo`. A plain table (`Table:`, `Reported Table:`, or a group outside a final block) is the final table of its stage if its numbers show a complete double round-robin.

**Why it was necessary:** The survey of 56 countries found 500 seasons with a table that the reader did not read. Decision 24 corrected the largest cause. The other causes were the headings.

**How the project did it** ([decision 26](docs/decisions/0026-table-headings.md)):

- `_FINAL_HEADING`: up to 3 words before `Final`, a note in brackets, `Ranking`, `Standings`, `Official Table`. Not `Top ...`. A heading ends with `:`.
- `_PLAIN_HEADING` and the last plain table of each stage as a candidate. `_complete_double_round_robin()`: 3 or more teams, positions 1 to n, 2(n − 1) matches for each team. Not a table "based on known results".
- `_table_row()`: one function for a table row, for final and plain tables.
- The techniques are in the [module README](src/african_football/sources/rsssf/README.md), sections 24 and 25.

**Verification:**

1. **All survey seasons**, compared with `main`: 21,079 table rows (19,622 before) in 1,449 seasons (1,373). Table checks that agree: 896 (870). No season has fewer rows. One check that agreed does not agree now (Namibia 1993): it shows a wrong league choice (decision 26).
2. **Nigeria, Ghana and Egypt:** 2,481 table rows (2,305). Table checks that agree: 59 (57). Ghana 1999 and Ghana 2003 now agree with all 240 matches.
3. 30 new tests, with 5 pages of Ghana and Nigeria as fixtures. 1 page test has a new number (Niger 2003: two groups, `Poule A` and `Poule B`).
4. 18 deliberate breaks, each caught. One rule (`Final table missing`) did nothing that the heading form does not do: the survey has no such heading with `:`. It was removed.

**Trade-offs:**

- A single round-robin league with only a plain `Table:` has no table: it looks the same as a table at half-way.
- About 1,000 table rows in 108 seasons have another row form (points only, goals without `-`). They are reported, and they are the next fix.
## November 2026: Result lines on RSSSF pages of all African countries

**What happened:** The RSSSF parser reads more forms of result lines, and new guards stop lines that are not results. A note that continues on the next lines is now complete. An award that the note revokes does not count.

**Why it was necessary:** The survey of 56 countries (the entry below) showed result lines that the parser did not read, for example scores with an en dash (`1–1`): Algeria 1972/73 gave 1 match of 248. It also showed lines that the parser read as matches but that are not matches: rows of a results grid, two-leg ties, and parts of sentences and notes. Both errors were silent.

**How the project did it** ([decision 25](docs/decisions/0025-result-line-forms.md)):

- New forms: en and em dashes, `3-0*`, `3-?`, `?-?`, teams first (`COD Meknes  - SA Sale  5-2`), and the words `tie`, `---`, `ppd`, `ann`, `n/p`, in upper or lower case. `ppd` is POSTPONED; `ann` and `n/p` are CANCELLED, or AWARDED if the note gives an award.
- New guards: grid rows (3 scores or `xxx` before the note), two-leg lines (reported as a problem), parts of sentences (a lower-case team with one space before the score), and scores in a note.
- A numbered round with a line of `=` under it is a part of the league.
- `_result_parts()`: one function for "is this a result line" and its parts.
- The next parts of a note join the note of their row (`note_row` in `parse_lines()`). `_AWARD_REVOKED` finds an award that the note revokes.
- The techniques are in the [module README](src/african_football/sources/rsssf/README.md), sections 11, 14 and 21 to 23.

**Verification:**

1. **All 2,446 survey seasons**, compared with `main`: 237,900 matches (235,078 before). Table checks that agree: 870 of 1,500 (837 before). 349 seasons have more matches; 52 have fewer, and each lost row was a wrong read. 3 seasons agreed with their table before and do not agree now: in each, a wrong read gave the correct sum by chance (decision 25).
2. **Nigeria, Ghana and Egypt:** 21,256 matches (21,201 before). Table checks that agree: 57 (53 before). Egypt 2004/05 now has its 26 rounds of 7 matches.
3. 31 new tests, with 9 survey pages as fixtures (their authors are in `tests/fixtures/rsssf/README.md`). 6 page tests have new numbers, each checked against the lines that it added: for example `ppd` and `n/p` lines.
4. 28 deliberate breaks, each caught. Two rules that no test could prove were measured on all seasons: one changed nothing and was removed; the other changed one season, and its line became the test.

**Trade-offs:**

- Two-leg lines are not read. The problems show them.
- The revocation rule reads English words only.
- An abandoned match whose result stood has no score. The table check shows these seasons.
- São Tomé 1999 now gives an island league (1 match) and not the national final (1 match). `rsssf_league` corrects it when the project adds São Tomé.
- The other findings of the survey (table headings, the index, dates) come in their own changes. The dates of a round with the date on a group heading (`Group A [Aug 13]`) are one of them.

## November 2026: The national league on RSSSF pages of all African countries

**What happened:** The RSSSF parser and the table reader choose the national league of a page with new rules (`choose_league()`), not with "the first competition with results". `leagues.yaml` can correct a league (`rsssf_league`). The log shows each choice, its reason and the other competitions.

**Why it was necessary:** A survey ran the RSSSF code on all African countries: 2,321 season pages of 56 countries (54 CAF members, Zanzibar and Réunion), downloaded politely into `data/survey/` (not in the repository). The code did not crash on any page. But it chose a cup as the national league in 208 seasons, a sentence in 26, a play-off in 16, and an island league in 17, without a problem in the report.

**Correction of part 2:** The old rule also chose a cup in 22 seasons of Nigeria, Ghana and Egypt. Part 2 reported 21,334 matches for these leagues; 133 of them were cup matches (for example 31 matches of the Egypt Cup in 2010/11). The new number is 21,201. The tests of part 2 did not show it, because no fixture had a cup before a league without results.

**How the project did it:**

- `choose_league()`, `competition_kind()` and `LeagueChoice` in `sources/rsssf/parser.py` ([decision 24](docs/decisions/0024-choosing-the-national-league-on-a-page.md)): cups, lower levels, play-offs and sentences are not the league; a page of regional leagues only has no league; a national name replaces a first candidate without a league word.
- Words in English, French and Portuguese, also for the headings of structure B.
- `rsssf_league` in `LeagueConfig` and `leagues.yaml`. If it does not match a competition of the page, the page has no league.
- `RsssfAdapter.league_choice`, and the choice in the log.
- Each rule came from a comparison of all 2,448 seasons with the version before ([module README](src/african_football/sources/rsssf/README.md) section 19).

**Verification:**

1. **All 2,448 seasons:** a cup is chosen in 0 seasons (208 before). 427 seasons have a different choice. Table rows: 20,182 (18,480 before). Table checks that agree: 901 (899 before). No season that agreed with its table before is worse.
2. **Nigeria, Ghana and Egypt:** each of the 22 changes is a cup that is no longer the league; 231 more league table rows.
3. 61 new tests, with 12 survey pages as fixtures (their authors are in `tests/fixtures/rsssf/README.md`).
4. 10 deliberate breaks, each caught. Break 7 (text in brackets counts) needed a test with a real name of 10 words (Rwanda 2005).

**Trade-offs:**

- The rules are words. A league with an unknown name needs `rsssf_league`.
- A page with only lower or regional competitions gives one of them as a fallback, with its reason in the log.
- The other findings of the survey (result forms such as `n/p` and `1–1`, table headings, the index, dates) come in their own changes.

## November 2026: Final tables and the table check (roadmap step 4, part 3)

**What happened:** The RSSSF adapter now reads the final tables of the top league (`RsssfAdapter.parse_tables`). The loader writes them to the new table `source_tables` (migration 002). `table_check()` compares a table with the matches. The pipeline does not use RSSSF yet (part 4).

**Why it was necessary:** Decision 7: a season is verified when the number of matches is correct **and** an independent source agrees **or** the goals agree with a final table. The tables give the second test.

**How the project did it:**

- `models/source_table.py`: `SourceTableRow` (Pydantic). Won + drawn + lost must be played.
- `sources/rsssf/tables.py`: finds the `Final Table(s)` blocks of the top league and reads the rows. Rows in other forms are problems ([decision 23](docs/decisions/0023-final-tables-and-the-table-check.md)).
- `table_check()`: compares the number of matches and the goals by sums, without team names.
- `db/migrations/002_source_tables.sql`, `RunRecorder.load(..., tables)` and `read_season_tables()`. A run with table rows replaces the table of the season and the source; a run without table rows does not change it.
- The techniques are in the module READMEs: [rsssf](src/african_football/sources/rsssf/README.md) sections 16 to 18, [db](src/african_football/db/README.md) section 14.

**Verification:**

1. **All 187 pages:** 2,074 table rows of 131 seasons. 37 problems, each real: 26 rows in two short forms, 9 rows where won + drawn + lost is not played (typos on the pages), 2 pages with two different final tables.
2. **The check:** 53 of 86 tables agree exactly with the matches. Ghana 2023/24 agrees (306 matches, 628 goals), and Soccerway agrees with RSSSF for the same season: the two tests of decision 7. The other tables show real properties of the seasons: missing results, deductions of goals, replays, typos.
3. 28 new tests. The database tests check the replacement of a table, a run without a table, the table of a different source, and the `CHECK` constraint.
4. 12 deliberate breaks, each caught. Break 11 (a walkover without a score counted as a found match) needed a new test.
5. 369 tests pass. basedpyright gives 0 errors.

**Trade-offs:**

- The check uses sums, thus it does not show which team is wrong.
- Rows in other forms are not read.
- `parse_tables` is not in the `SourceAdapter` Protocol: only RSSSF gives tables.

## November 2026: RSSSF parser (roadmap step 4, part 2)

**What happened:** `RsssfAdapter.parse` now reads the matches of the top league from an RSSSF season page. The pipeline does not use RSSSF yet (part 4).

**Why it was necessary:** RSSSF has results for seasons that Soccerway does not have. The pages are hand-written by many authors, in many forms.

**How the project did it:**

- The adapter of part 1 got all 187 season pages of the NPFL, Ghana and Egypt into `data/sources/rsssf/`: 190 requests in 10.6 minutes, 0 failures.
- `sources/rsssf/parser.py`: finds the competitions of the page (two structures), takes the first with results, and reads its lines with rules for rounds, dates, stages, results and notes ([decision 22](docs/decisions/0022-rsssf-parser.md)).
- A report for each of the 187 seasons showed each new form of the pages. Examples: a note that continues in a column at the right of the next results, tables in the middle of a league, dates of two days, a page for 11 seasons with anchors.
- Lines that look like a result but were not read are problems: in `RsssfAdapter.problems` and in the log. They are not ignored, and they do not stop the season.
- The techniques are in [src/african_football/sources/rsssf/README.md](src/african_football/sources/rsssf/README.md), sections 10 to 15.

**Verification:**

1. **All 187 pages:** 21,334 matches. 0 dates outside the years of their season. 20 problems, each a real limit (an unknown opponent, or a results grid that the parser does not read).
2. **Two sources, one season.** Ghana 2023/24: all 306 Soccerway matches are in the RSSSF output with the same date and score; RSSSF also has an abandoned match before its replay. Ghana 2017: 238 of 240 agree; the 2 others differ between the sources.
3. 47 new tests. The page tests use 14 unchanged RSSSF season pages, one for each form; their README names the authors.
4. 10 deliberate breaks, each caught. Three were caught only after new tests: other rules hid them (layered defences, module README section 12).
5. 341 tests pass. basedpyright gives 0 errors.

**Trade-offs:**

- Results grids and crosstables are not read.
- Team names are raw; one page can write one club in four ways.
- The first competition with results is the league. A page with the cup first would give the cup.

## November 2026: RSSSF adapter, discovery and fetch (roadmap step 4, part 1)

**What happened:** The project added the second source adapter, for RSSSF. It finds the seasons of a league in the RSSSF list of champions, and gets the season pages into the raw store. The parser comes in part 2. The pipeline does not use RSSSF yet.

**Why it was necessary:** RSSSF has results for old seasons that Soccerway does not have, and final tables that can verify a season (decision 7).

**How the project did it:**

- A survey of 15 RSSSF pages of 6 countries, from 1990 to 2024, before the design ([decision 21](docs/decisions/0021-rsssf-adapter-discovery-and-fetch.md)).
- `sources/rsssf/index.py`: reads a list of champions. The season comes from the text of the link, not from the file name. Each entry has the heading of its list.
- `sources/rsssf/http.py`: one request at a time, 3 seconds between requests, retries after 5, 15 and 45 seconds, no retry for a 404. Pages without a declared character set are decoded as UTF-8, Windows-1252 or Latin-1.
- `sources/rsssf/adapter.py`: `RsssfAdapter` with `discover_seasons` and `fetch`. The labels come from `season_label()` (decision 20).
- `leagues.yaml`: `rsssf_index` and `rsssf_section` for the NPFL, Ghana and Egypt.
- The techniques are in [src/african_football/sources/rsssf/README.md](src/african_football/sources/rsssf/README.md).

**Verification:**

1. 37 new tests, without the network. The fixtures are the real lists of champions of Nigeria, Ghana and Egypt, without changes. Their README names the authors, as the licence of the pages requires.
2. Deliberate breaks. Each break made the correct tests fail:

   | Break | Tests that failed |
   |---|---|
   | The section is ignored | 7, for example the Egypt 1948/49 champion |
   | A 404 is retried | `test_404_is_not_retried` |
   | No interval between requests | `test_interval_between_two_requests` |
   | The anchor stays in the page URL | `test_fetch_stores_the_page_without_the_anchor` |
   | `abandoned` is a champion | `test_abandoned_season_has_no_winner`, `test_not_finished_season_has_no_winner` |
   | `1999/00` read as 1999 to 1900 | `test_season_years[1999/00]` |
   | `fetch` without its `store` parameter | basedpyright: `"RsssfAdapter" is not assignable to declared type "SourceAdapter"` |

3. A live check: discovery for the three leagues and one page for each, 6 requests in 18 seconds. NPFL 51 seasons (1972 to 2025/26), Ghana 67 (1956 to 2025/26), Egypt 69 (1948/49 to 2025/26). Each has 2 seasons without a winner. For each league, the label `2023/2024` gave the correct page.

**Trade-offs:**

- A season without a winner is not scraped. Some of these pages have results.
- The Nigeria National League has no list of champions on RSSSF.
- The pages are hand-written. A new format can break the parser of part 2.

## November 2026: Correct labels for calendar-year seasons (version 1.2.0)

**What happened:** The Soccerway discoverer gave a calendar-year season a label with two years. For example, the NPFL 2019 season (January to July 2019) had the label `2018/2019`. Now it has the label `2019`, and its files are `2019.json` and `2019_ng1.txt`. `PIPELINE_VERSION` is now `1.2.0`.

**Why it was necessary:** The RSSSF adapter (roadmap step 4) must give each season the same label as Soccerway ([decision 20](docs/decisions/0020-one-season-label-style-for-all-sources.md)). RSSSF calls this season `2019`.

**How the project did it:**

- `season_label()` in `models/season_model.py` makes all season labels.
- `SeasonDiscoverer._parse_years_from_href()` gives `(2019, 2019)` for `npfl-2019`, not `(2018, 2019)`.
- `build_season_str()` (before: `_build_season_str()`) gives `2019` for a calendar-year season. `main.py` and the Airflow tasks use it, not their own copy of the rule.

**Verification:**

1. The discoverer ran on the live Soccerway archive. Before the change: 12 NPFL seasons and 2 Ghana seasons had a wrong label. After the change: NPFL `2019`, `2018`, ..., `2012`, `2007`, `2006`, `2005` and Ghana `2018`, `2017`. These are the same labels as on RSSSF.
2. The old unit test expected the wrong rule (`2018` gave `2017` as its start year). The test now expects `(2018, 2018)`. With the old rule put back on purpose, the two single-year tests failed.
3. New tests for `season_label()` and for the file names of a calendar-year season. 248 tests pass.

**Trade-offs:**

- The 14 seasons get new file names. Files from before version 1.2.0 keep their old names.
- Soccerway `npfl-2022-2023` and RSSSF `2023` are the same season with different labels. Step 5 must connect them.

## November 2026: The exports read from the database (roadmap step 3, part 3)

**What happened:** The JSON and TXT exports now use the matches from the database. `FootballScraper` writes the run, reads the matches back, and makes the files from them. Each run also writes the coverage of the season. The pipeline needs the database now. The output did not change. Roadmap step 3 is complete.

**Why it was necessary:** [Decision 5](docs/decisions/0005-postgresql-after-source-neutral-model.md) makes PostgreSQL the single source of truth. Before this change, the files came from the data in memory, thus they could show data that the database did not have.

**How the project did it:**

- `db/reader.py`: `read_season_matches()` gives the matches of the latest succeeded run, in the sequence of the results page, as `SourceMatch` records ([decision 19](docs/decisions/0019-exports-read-from-the-database.md)).
- `db/loader.py`: `load()` writes `season_coverage` in its transaction: expected = n × (n − 1) for n teams, found = the played and awarded matches. `fail()` writes `failed` only for a season without coverage. A `verified` season does not change.
- `FootballScraper`: the database URL is necessary. The export uses the matches from `read_season_matches()`.
- `main.py` stops before its menus if `DATABASE_URL` is not set.
- The new SQL techniques are in [src/african_football/db/README.md](src/african_football/db/README.md): the correlated subquery for the latest run, a CTE with `UNION`, and the conditional upsert (`DO UPDATE ... WHERE`).

**Verification:**

1. **Live run (the baseline).** The code of part 2 scraped Ghana 2023/24 into `data/sources/` and into the database: 306 matches, 305 halftime scores (the other match is awarded), 0 network errors, 1,304 seconds. This was also the first live run of the loader: 306 new matches and 306 new pages. The output is the baseline (`data/baselines/gh_pl_2023-24_v1.1.0.json`).
2. **Database round trip.** The reader read the 306 matches of the live run from the database. The legacy exporter made the stages. Comparison with the baseline: 306 matches, 4,590 fields, **0 differences**.
3. **The comparison can fail.** With one halftime score changed, the comparison found exactly 1 difference.
4. **The new scraper, offline.** The new `FootballScraper` ran on the raw store into a new empty database: 0 pages from the network, 51 seconds, 4,590 fields, **0 differences**. The coverage: 306 expected, `complete_single_source`.
5. 15 new tests (`tests/integration/test_reader.py`, and changed tests in `test_loader.py` and `test_soccerway_adapter.py`). The adapter test now goes from the fixture pages through the database to the output.
6. Deliberate breaks. Each break made the correct test fail:

   | Break | Test that failed |
   |---|---|
   | Export the parsed matches, not the matches from the database | `test_scraper_exports_the_matches_from_the_database` |
   | No `last_run_id` filter in the reader | `test_read_gives_only_the_matches_of_the_latest_run` |
   | No `status = 'succeeded'` in the reader | `test_failed_run_does_not_change_the_export` |
   | No `page_position` in `ORDER BY` | `test_read_keeps_the_page_sequence` |
   | No `WHERE` in the coverage upsert | `test_single_source_never_replaces_verified` |
   | `DO UPDATE` in place of `DO NOTHING` in `fail()` | `test_failed_run_keeps_the_coverage_of_an_earlier_run` |
   | Postponed matches counted as found | `test_coverage_does_not_count_a_postponed_match` |

7. 242 tests pass. basedpyright gives 0 errors.

**Trade-offs:**

- The pipeline needs Docker and the database, also for one season.
- The coverage rule *n × (n − 1)* is correct only for a double round-robin league. Other formats show `incomplete` until the value for each season comes into the configuration (roadmap step 5).
- The matches that a later run did not find are not exported. A person must examine them in the database (the query is in `docs/database.md`).

## November 2026: The loader writes each run to the database (roadmap step 3, part 2)

**What happened:** When `DATABASE_URL` is set, `FootballScraper` now writes each scrape to the pipeline database: the league, the season, the run, the stored pages and the matches. A new scrape updates the matches. The JSON and TXT exports did not change. They still come from the scraper output.

**Why it was necessary:** Part 3 makes the exports from the database. The database must first have the matches, and a record of each run. The run record also shows the runs that failed or stopped, which the log files showed before.

**How the project did it:**

- `db/loader.py`: `RunRecorder` with `start()`, `load()` and `fail()`, and `LoadSummary` ([decision 18](docs/decisions/0018-loader-records-each-run.md)). Three transactions for each run.
- `FootballScraper` has a new parameter `database_url`. `main.py` and the Airflow task give it `DATABASE_URL`. Without it, the scraper logs a warning and works as before.
- `page_position` records the sequence of each match on the results page. The exports of part 3 need it.
- The log shows what the run wrote: new and changed matches, new pages, and the matches that the source does not show now.
- The techniques are in [src/african_football/db/README.md](src/african_football/db/README.md): the upsert, `xmax = 0`, `IS DISTINCT FROM`, `now()` and `clock_timestamp()`, `LiteralString`.
- `docs/database.md`: how runs are recorded, and four queries for the runs and the matches.

**Verification:**

1. 16 new tests (`tests/integration/test_loader.py`) on a new database for each test. The scraper tests use a fake adapter, thus they do not need a browser.
2. Deliberate breaks. Each break made exactly one test fail:

   | Break | Test that failed |
   |---|---|
   | `load()` without its transaction | `test_failed_load_writes_nothing` |
   | `updated_at = now()` on each run | `test_second_run_with_the_same_data_changes_nothing` |
   | `<>` in place of `IS DISTINCT FROM` | `test_changed_match_is_updated` |
   | `except Exception` in place of `BaseException` | `test_scraper_marks_a_cancelled_run` |
   | `pages_fetched` counts all pages | `test_pages_fetched_counts_only_the_pages_of_this_run` |

3. The SQL facts in the module README were checked in `psql`: the `NULL` comparisons, `xmax` after an insert and after an update, and `now()` after a 0.2 second wait.
4. A load of 306 matches (the size of a Ghana season) takes 0.5 seconds.
5. The four queries in `docs/database.md` gave the expected rows on a database with a succeeded, a changed, a failed and a running run.
6. 227 tests pass. basedpyright gives 0 errors, without `# pyright: ignore`.

**Trade-offs:**

- The database is optional until part 3. A run without `DATABASE_URL` is not in the database.
- The matches that the source does not show again stay in the database. A person must examine them (the query is in `docs/database.md`).
- The scraper uses a synchronous connection in an async method. For one season at a time, this is sufficient.

## November 2026: The pipeline database and the migration runner (roadmap step 3, part 1)

**What happened:** The project added the pipeline database, its first schema and a migration runner. CI now runs the database tests against PostgreSQL 18. The pipeline does not write to the database yet, thus the output did not change.

**Why it was necessary:** Roadmap step 3 makes PostgreSQL the single source of truth ([decision 5](docs/decisions/0005-postgresql-after-source-neutral-model.md)). The loader (part 2) and the exports from the database (part 3) need the tables, a way to change them, and tests against a real database.

**How the project did it:**

- `docker-compose.yaml`: the `pipeline-db` container ([decision 14](docs/decisions/0014-separate-postgresql-18-container.md)). `.env.example` gives `DATABASE_URL`.
- `db/migrations/001_initial.sql`: six tables with constraints ([decision 16](docs/decisions/0016-database-repeats-sourcematch-rules.md)).
- `db/migrate.py`: the migration runner ([decision 15](docs/decisions/0015-plain-sql-migrations-not-alembic.md)). Run it with `uv run --env-file .env python -m african_football.db.migrate`.
- `tests/conftest.py`: the fixture `empty_database` makes a new database for each test and deletes it after the test. The `db` marker shows the tests that need PostgreSQL.
- CI: a PostgreSQL 18 service in the `test` job, and a step that applies the migrations. `sqlfluff lint` in the `lint` job ([decision 17](docs/decisions/0017-sqlfluff-formats-sql.md)).
- `airflow/docker-compose.yaml` includes the root Compose file, and gives `DATABASE_URL` to the Airflow tasks.
- New dependencies: `psycopg[binary]` (the PostgreSQL driver) and `sqlfluff` (dev).

**Verification:**

1. The container is healthy, and the port is open only on `127.0.0.1`. The data stays after `docker compose down` and `up`.
2. 15 inserts of bad data: each one stopped at the correct constraint. The correct inserts passed.
3. The runner applies `001` on an empty database. A second run applies nothing. The checksum in `schema_migrations` is the same as the `sha256sum` of the file.
4. 19 runner tests pass. With the transaction removed, `test_file_and_its_record_are_one_transaction` fails ([decision 15](docs/decisions/0015-plain-sql-migrations-not-alembic.md)).
5. With `CI=true` and no `DATABASE_URL`, the 11 database tests fail. They do not skip.
6. `docker compose -f airflow/docker-compose.yaml config` shows `pipeline-db` and the volume `african-football-pipeline-db`.

**Trade-offs:**

- Docker is necessary for the database tests and for the pipeline database.
- The `test` job in CI starts a PostgreSQL container. This adds some seconds to each run.
- The migration files are now history. A change to an applied file stops the runner. A schema change needs a new file.

## November 2026: Soccerway adapter and the switch (roadmap step 2, part 3b)

**What happened:** `FootballScraper` now uses the new parts of step 2. The pipeline gets the pages into the raw store, parses the stored pages in Python, and makes the JSON with the legacy exporter. The output did not change. Roadmap step 2 is complete. `PIPELINE_VERSION` is now `1.1.0`.

**Why it was necessary:** Before, the scraper read the pages in the browser and made the output in one step. A parser repair needed a new scrape of approximately 30 minutes for each season. An interrupted run started again from the beginning.

**How the project did it:**

- `sources/soccerway/adapter.py`: `SoccerwayAdapter` with `discover_seasons`, `fetch` and `parse`. The adapter starts and stops the browser.
- `fetch` keeps each page that it loads. A match page is *complete* when the store has it in the league timezone **and** the parser finds a halftime score in it. Only incomplete pages are loaded again. The adapter keeps a page without a halftime score, because the page can contain the kick-off time.
- `parse` reads the stored pages. It does not use a browser or the network.
- `FootballScraper` is now a short wrapper: fetch, parse, legacy exporter, statistics. Its public methods did not change. Thus, `main.py` and the Airflow tasks did not change, but Airflow now puts the raw store in the mounted `data/` folder.
- `FootballScraper` assigns the adapter to a variable of the type `SourceAdapter`. Thus, basedpyright compares the adapter with the Protocol ([decision 11](docs/decisions/0011-adapter-interface-is-a-protocol.md)).
- The project removed the old code: the JavaScript parser, `parse_match_row`, the halftime loop and the parity tests (approximately 450 lines).
- The adapter keeps the parsed match pages by sha256. Thus, `fetch` and `parse` do not parse the same page two times.

**A bug that the new code corrected:** In the old scraper, a page that loaded without a halftime score was tried again only after pass 1. In pass 2, the scraper did not record it, thus pass 3 did not try it, and the log showed "0 failed". The baseline run showed this: pass 3 reported 0 failures, but two matches had no halftime score. The adapter tries such a page in each pass, and again in the next run.

**Verification:**

1. **Baseline.** The old scraper (version 1.0.1) scraped Ghana 2023/24 in Africa/Accra time: 306 matches. Two halftime scores were missing because of slow pages. A manual check of the two pages gave the values (0 - 1 and 0 - 0). The project added the two values to the baseline and kept the original file.
2. **Live run of the new code:** 306 matches, 305 halftime scores, 0 network errors, 1,236 seconds. The new code found the two halftime scores itself. They agree with the manual check.
3. **Comparison:** 306 matches, 4,590 match fields: **0 differences**. To make sure that the comparison can fail, the project compared the new output with the original baseline. The comparison found exactly the two missing halftime scores.
4. **Run again from the raw store:** no requests to Soccerway, the same output. 92 seconds. With the cache of parsed pages: 47 seconds, 26 times faster than the live run.
5. **Tests that were broken on purpose:**
   - A wrong return type in `SoccerwayAdapter.parse`: basedpyright gave an error at the `SourceAdapter` variable.
   - The old retry rule: the retry test failed (2 passes instead of 3).
6. **Offline tests of `fetch`** (`test_soccerway_adapter.py`): Playwright answers each request with a fixture page. A second fetch sends no request. A damaged page is loaded again, and only that page.
7. 192 tests pass. basedpyright gives 0 errors.

**Trade-offs:**

- The raw store uses disk space: 24 MB for this season.
- A run from the raw store is not instant. Most of the 47 seconds is the parse of 305 large pages.
- The adapter loads each match page in the browser, also for a page that the store has but that is not complete. For a season with many slow pages, a run can take some minutes.
- `FootballScraper` stays until the Source Manager (roadmap step 6).

## November 2026: Legacy exporter (roadmap step 2, part 3a)

**What happened:** The project added `exports/legacy.py`. It makes the current JSON match format from `SourceMatch` records. The pipeline does not use it yet. Thus, the output did not change.

**Why it was necessary:** `SourceMatch` keeps goals and penalty goals in different fields, and it uses numbers and dates. The current JSON and TXT files use a different format. The exporter keeps the special rules of this format in one location:

- For a penalty shootout, `home_score` and `away_score` contain the shootout score, and `full_time_score` contains the score before the shootout (`0-0`, without spaces).
- All scores are text. The halftime score has spaces (`2 - 1`).
- The date is `DD.MM.YYYY`, or `DD.MM.YYYY HH:MM` if the kick-off time is known.
- An awarded match always has the `awarded_reason` `walkover`.
- The keys have the same sequence as before. The checksum of `file_saver` sorts the keys, but the JSON files show the keys in their sequence.

**How:** `to_legacy_match` changes one `SourceMatch` into one dictionary. `to_legacy_stages` puts the dictionaries into stages, with `total_rounds` and `total_matches`. See [decision 13](docs/decisions/0013-build-new-code-next-to-old-code.md) for the parity tests.

**Verification:**

- Parity tests on the league fixture and the cup fixture: all dictionaries are equal to the output of `parse_match_row`, also in key sequence. A third test adds the match page (kick-off time and halftime score).
- The project broke the exporter two times on purpose: spaces in `full_time_score`, and two keys in a different sequence. The tests failed with the exact differences.
- 10 new tests. All 209 tests pass. basedpyright gives 0 errors.

**Trade-offs:** The exporter keeps the special rules of the legacy format alive. New outputs, for example the database in roadmap step 3, must use `SourceMatch` directly, not this format.

## November 2026: Type checking in CI

**What happened:** The `lint` job in CI now runs `basedpyright`.

**Why:** [Decision 11](docs/decisions/0011-adapter-interface-is-a-protocol.md) showed a gap. Only a type checker examines the `SourceAdapter` Protocol, but no type checker ran automatically.

**How:** See [decision 12](docs/decisions/0012-basedpyright-in-standard-mode.md) and [Code Checks](docs/development.md#code-checks). The project corrected the 21 errors before it added the check. Thus, the check started with no errors.

**Trade-offs:** The `lint` job takes approximately 4 seconds more. The type checker is not in the pre-commit hook, because it takes approximately 9 seconds on a laptop.

## November 2026: Source-neutral model and Python parser (roadmap step 2, parts 1 and 2)

**What happened:** The project added the first parts of the multi-source structure. The pipeline does not use them yet. Thus, the output did not change.

- Part 1: the `SourceMatch` model, the `SourceAdapter` interface, and the raw page store (`RawStore`). See decisions 8, 10 and 11.
- Part 2: a Python parser for the stored Soccerway pages, with a parity test against the JavaScript parser. See [decision 9](docs/decisions/0009-parse-in-python-not-in-browser.md).

**Why it was necessary:** The old scraper reads the page in the browser and makes the output in one step. Thus, a parser repair needed a new scrape, and the data format followed the Soccerway page. The new parts keep the raw pages, parse them in Python, and make records that do not depend on the source.

**How the project did it:**

- `models/source_match.py`: `SourceMatch` and `MatchStatus`. Goals and penalty goals are in different fields. `MatchStatus` replaces the `awarded` and `penalty_shootout` flags.
- `sources/base.py`: `SourceAdapter` and `RawDocument`.
- `sources/raw_store.py`: `RawStore`.
- `sources/soccerway/parser.py`: the parser. The functions `parse_round` and `parse_kickoff` moved here from the old scraper. The old scraper imports them, thus each function exists one time only.

**Verification:**

- 20 tests for `RawStore` and 22 tests for `SourceMatch`.
- 18 parser tests without a browser, and 2 parity tests with Chromium.
- All 199 tests pass.

**Next (part 3):** the legacy JSON exporter (part 3a), then the Soccerway adapter (`fetch` and `parse`) and the change from the old scraper to the adapter (part 3b). The project will verify the change against a saved live scrape of Ghana 2023/24. The JSON output must be the same.

## November 2026: Faster CI and a pre-commit hook

**What happened:** CI took 7–9 minutes for each run. Now it takes less than 1 minute.

**Why:** The step that installs the system packages for Chromium used `apt-get`. The Ubuntu package server was slow (64 kB/s). Each check, also the format check, waited for this step.

**How:** See [Code Checks](docs/development.md#code-checks). The `lint` job does not install a browser. The `test` job runs in the Playwright Docker image, which contains the system packages. A pre-commit hook runs Ruff and file checks before each commit.

**Trade-offs:**

- The tag of the Docker image must agree with the Playwright version in `uv.lock`. A person must change the two together.
- The Docker image download takes approximately 20 seconds of each run.
- Each clone must run `uv run pre-commit install` one time.

## November 2026: Kick-off times in local league time

**What happened:** After the Soccerway repair, the results page showed only the match date (`15.09.2023`). The kick-off time was not in the data.

**Why it was necessary:** The kick-off time is useful data. During this work, the project also found a larger problem: Soccerway shows all dates and times in the timezone of the browser. Thus, the data changed with the computer that ran the scraper. For example, the same match showed 16:00 in Lagos, 15:00 in Accra and 18:00 in Cairo. All earlier data used West Africa Time (WAT), also for Ghana and Egypt. In a Docker container, the timezone is usually UTC, so Airflow runs gave different times again.

**How the project changed it:**

- Each league in `leagues.yaml` now has a necessary `timezone` field. The configuration loader stops if the field is missing or not known.
- The scraper sets the browser timezone to the league timezone. Thus, all dates and kick-off times are in local league time on all computers.
- The scraper reads the kick-off from the match page (`15.09.2023 18:30`). It uses the same page load as the halftime score, so there are no extra page loads.
- The Airflow tasks now use `dataclasses.asdict()` for the league configuration. Before, a manual list of fields would lose new fields, for example `timezone`.

**Limits:**

- The scraper gets the kick-off time only for leagues with `fetch_halftime: true`. For other leagues, the data has the date only.
- Awarded matches have the date only, because the scraper does not open their match pages.
- The earlier JSON files contain WAT times. For Ghana and Egypt, these times are not local times. Scrape these seasons again to get the correct times.

**Verification:** A live check used the scraper code and the league configuration. For Ghana, the kick-off times were one hour earlier than the earlier WAT data (for example 19:30 WAT became 18:30 Africa/Accra). This is correct. For Nigeria, the time did not change (16:00 Africa/Lagos), because WAT is the local time.

## November 2026: Soccerway scraper repair

**What happened:** Soccerway changed the structure of its pages. The scraper then gave incomplete data and did not show an error. Season discovery continued to work. But on the results pages, these problems occurred:

| Problem | Old selector | Result |
|---|---|---|
| The "Show more matches" button moved to a new element | `a.wclButtonLink` | Only the first 100 matches of a season loaded |
| The match date element has a new name | `div.event__time` | Each row had a timeout on the date, and the scraper lost the matches |
| The awarded and penalty indicator moved into the date cell | `.event__stage--block` | The scraper did not mark awarded matches |
| The score layout changed (penalties now show as `0(3)`) | `.event__part` | Penalty matches lost their full-time score |
| The halftime score structure changed | `1st Half` → `span//div` | The scraper found no halftime scores |

**Why it occurred:** Soccerway now uses the Flashscore frontend. Its class names contain a build hash, and the hash changes at each release. Some selectors used these names, or used elements that the site removed.

**How the project repaired it:**

- All selectors are now in one block in `scraper.py`. They use only stable attributes. Refer to [Design Decisions](docs/design.md).
- The scraper reads each match row in one JavaScript pass in the page. Before, it used approximately seven browser calls for each row. Thus, scraping is also faster.
- A pure function, `parse_match_row`, parses each row. Unit tests test this function.
- The project saved fixtures from the live site: a league round, an awarded match, a cup penalty shootout, a cup walkover, and the halftime block of a match page. Tests run the selectors on these fixtures without the network.
- If a "Show more" click loads no new matches, the scraper stops. This prevents an infinite loop.
- The halftime step writes a progress line to the log after each 15 match pages. Before, the log showed nothing during this step, and the step can take 40 minutes.
- On a match page, the scraper now waits only for the halftime score, not for the full page load. Before, ads and trackers kept some pages busy for more than 30 seconds, and the halftime step took more than one hour for one season. Now most pages take 3 to 5 seconds.
- The JSON output format did not change. Thus, the TXT export did not need changes.

The repair also corrected these bugs:

- The scraper compared penalty scores as text. Thus, `"10"` was less than `"9"`. Now the scraper compares the scores as numbers.
- A walkover row with no score (`-`) showed as `- - - (awarded)` in the export. Now it shows as `awarded`.
- Before, the scraper marked as a penalty shootout each match that had an indicator and partial scores. This gave an incorrect result for some matches that ended after extra time. Now the scraper finds a shootout only from the penalty score.

**Verification:** On 2026-11-17, the repaired scraper did a live scrape of Ghana Premier League 2023/2024. The project compared the result with an earlier scrape of the same season, match by match:

- The scraper found 306 matches. The earlier scrape also had 306 matches, with the same match IDs.
- The scraper found 305 halftime scores. The one match without a halftime score is an awarded match.
- All fields are the same, except the date format. Soccerway now shows `15.09.2023` (with the year, without the kick-off time). Before, it showed `15.09. 19:30`.
- The full run took 40 minutes. In the first halftime pass, 8 of 305 match pages failed. All 8 were successful in the second pass.
