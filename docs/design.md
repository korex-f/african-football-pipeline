# Design Notes

**Config-driven, not code-driven.** Adding a new African league means adding a block to `leagues.yaml`. No code changes, no redeployment. The pipeline dynamically discovers seasons, builds URLs, and resolves file paths from config alone.

**Two-phase SeasonRecord population.** SeasonDiscoverer populates identity fields (season, URL, champion, status). FootballScraper populates ingestion metadata (scraped_at, records_extracted, checksum, pipeline_version). Thus, discovery and scraping can run independently. Airflow runs them as two different DAG tasks.

**Capability flags on LeagueConfig.** `fetch_halftime`, `fetch_venue`, `fetch_lineups`, `fetch_scorers`, `fetch_cards` — each defaults to `False` and is toggled per league in YAML. The scraper checks these flags to decide what to extract. New data dimensions are added without modifying existing scraping logic (Open/Closed Principle).

**Graceful normalisation skip.** If no canonical teams file exists for a league, the pipeline logs a warning and continues with raw team names. Raw data is still valuable without normalisation — the pipeline never crashes on missing reference data.

**Year-based ongoing season detection.** Instead of relying on empty winner columns (which breaks for historical data gaps like NPFL 2005), the pipeline combines `end_year >= current_year` with winner column state to classify seasons accurately as COMPLETED, NO_WINNER, or ONGOING.

**Awarded match detection.** The scraper finds walkover matches from the stage indicator adjacent to the match date. Leagues show `Awrd` and cups show `WO`. The output marks these matches with `awarded: true`. The scraper does not get halftime scores for these matches, because the teams did not play.

**Stable selectors in two locations.** The Soccerway selectors are in two blocks. `sources/soccerway/adapter.py` has the selectors that the browser uses during `fetch` (the "Show more" button and the halftime score). `sources/soccerway/parser.py` has the selectors that read the stored pages. The selectors use only stable attributes:

- BEM classes, for example `event__match`
- `data-testid` attributes
- Class prefixes without a hash, for example `[class*="wcl-name"]`

The selectors do not use class names that contain a build hash, for example `wcl-name_jjfMf`. The site changes these names at each release. The browser only gets the pages. The parser reads the stored HTML in Python, thus the parser tests do not need a browser.
