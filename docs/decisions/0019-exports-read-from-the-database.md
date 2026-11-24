# 19. The exports read from the database, and the coverage uses n × (n − 1)

*Status: accepted (November 2026). [All decisions](README.md)*

- **What:** `FootballScraper` writes the run to the database, then reads the matches back with `read_season_matches()` (`db/reader.py`). The JSON and TXT exports use the matches from the database, not the matches in memory. Each successful run also writes `season_coverage`. The scraper needs `DATABASE_URL`.
- **Why:** [Decision 5](0005-postgresql-after-source-neutral-model.md) makes PostgreSQL the single source of truth. If the exports used the data in memory, the files could show data that the database does not have, for example after a database error. Now the files show only what the database has.
- **The debate:**
  1. **Which matches go into the export.**
     - *All rows of the season:* nothing in the database is left out. But a match that the source deleted, for example a duplicate, comes into the file, and the sequence mixes rows of different runs.
     - *Only the matches of the latest succeeded run (the decision):* the export is equal to what the source shows now. The matches that this run did not find stay in the database for a person to examine ([decision 18](0018-loader-records-each-run.md)). A failed run does not change the export.
  2. **The expected number of matches for the coverage.** [Decision 7](0007-testable-definition-of-verified.md) gives *n × (n − 1)* for a double round-robin league, and a value for each season in the configuration (planned for roadmap step 5).
     - *Keep it empty until step 5:* safe, but the status is `incomplete` for all seasons until then.
     - *n × (n − 1), with n from the teams of the run (the decision):* Ghana 2023/24 has 18 teams, thus 306 matches. The coverage is useful now.
  3. **When the database becomes necessary.** [Decision 18](0018-loader-records-each-run.md) made it optional until this part. Now the exports need it. `main.py` stops before its menus if `DATABASE_URL` is not set. `FootballScraper` raises `ValueError` before it starts the browser.
- **How:**
  - `read_season_matches()` finds the latest succeeded run with a subquery (`max(run_id)` of the season, the source and the status `succeeded`), and gives the rows with this `last_run_id`, sorted by `page_position`.
  - Each row becomes a `SourceMatch` again. Thus Pydantic checks the data from the database too.
  - The coverage SQL is in the `load()` transaction, thus the coverage always agrees with the matches.
  - Coverage rules:

    | Situation | Status |
    |---|---|
    | found ≥ expected, and found > 0 | `complete_single_source` |
    | found < expected, or no matches | `incomplete` |
    | the first run of the season failed | `failed` |
    | a later run failed | no change |
    | the status is `verified` | no change (data of one source never replaces it) |

    *found* counts only the `played` and `awarded` matches.
- **Trade-offs:**
  - If the source does not show a team at all, *n* is too small, and the expected number is too small. The value for each season in the configuration (step 5) corrects this.
  - The rule *n × (n − 1)* is wrong for a league with groups, play-offs or a single round-robin. These seasons show `incomplete` until step 5.
  - Two spellings of one team name count as two teams. The raw names of one source are usually the same in all matches.
  - The scraper needs Docker and the database, also for a test run of one season.
