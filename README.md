# African Football Data Pipeline

This pipeline collects historical football data for African domestic leagues. It collects the match results for each season. It normalises the team names, validates the data, and exports the data as JSON and as OpenFootball text.

The pipeline runs on one local computer. It uses Python, Playwright, and Airflow. PostgreSQL is planned. Cloud platforms are not in the scope of the project at this time. For the reasons, refer to [Architecture Decisions](#architecture-decisions).

The code uses typed Python, automated tests, and conventional commits. The tests include regression tests that use saved copies of web pages.

## Table of Contents

- [Architecture](#architecture)
- [Data Flow](#data-flow)
- [Getting Started](#getting-started)
- [Data Quality](#data-quality)
- [Retry Logic](#retry-logic)
- [Currently Supported Leagues](#currently-supported-leagues)
- [Architecture Decisions](#architecture-decisions)
- [Changelog](#changelog)
- [Roadmap](#roadmap)
- [Tech Stack](#tech-stack)

## Architecture

```
config/
├── leagues.yaml                  ← League definitions (add a league = add a YAML block)
└── canonical_teams/              ← Per-league team name mappings
    └── nigeria_npfl.yaml

src/african_football/
├── models/
│   ├── league_model.py           ← LeagueConfig dataclass with capability flags
│   └── season_model.py           ← SeasonStatus enum + SeasonRecord (two-phase population)
├── config/
│   └── config_loader.py          ← YAML → validated LeagueConfig objects
├── scraping/
│   ├── url_builder.py            ← URL construction + archive URL builder
│   ├── season_discoverer.py      ← Discovers seasons + champions from archive pages
│   └── scraper.py                ← Core Playwright scraper with HT enrichment
└── utils/
    ├── logger.py                 ← PipelineLogger (console + file)
    ├── file_saver.py             ← JSON/TXT export with SHA256 checksums
    └── team_normalizer.py        ← Exact + fuzzy matching with review log

main.py                           ← CLI orchestrator with batch selection + retry logic
tools/                            ← Standalone utilities (extract, merge, format teams)

airflow/
├── dags/scrape_leagues.py        ← Thin DAG: load configs → build jobs → scrape (parallel) → summarise
├── plugins/pipeline_tasks.py     ← Task logic calling the library
└── docker-compose.yaml           ← Local Airflow stack

tests/
├── unit/                         ← Pure-function tests (no browser, no network)
├── integration/                  ← Component wiring + saved-page regression tests
└── fixtures/soccerway/           ← Trimmed copies of real Soccerway pages

data/
├── raw/{country}/{league}/       ← Immutable JSON snapshots
├── exports/{country}/{league}/   ← Human-readable TXT exports
└── logs/unmatched_teams/         ← Flagged names for manual curation
```

> **Why are the modules separate?** The models, config, scraping, and utils modules are independent. Thus, the CLI and Airflow use the same library code. Airflow tasks import `SeasonDiscoverer`, `FootballScraper`, and `file_saver` directly. The DAG files do not contain pipeline logic.

### Design Decisions

**Config-driven, not code-driven.** Adding a new African league means adding a block to `leagues.yaml`. No code changes, no redeployment. The pipeline dynamically discovers seasons, builds URLs, and resolves file paths from config alone.

**Two-phase SeasonRecord population.** SeasonDiscoverer populates identity fields (season, URL, champion, status). FootballScraper populates ingestion metadata (scraped_at, records_extracted, checksum, pipeline_version). Thus, discovery and scraping can run independently. Airflow runs them as two different DAG tasks.

**Capability flags on LeagueConfig.** `fetch_halftime`, `fetch_venue`, `fetch_lineups`, `fetch_scorers`, `fetch_cards` — each defaults to `False` and is toggled per league in YAML. The scraper checks these flags to decide what to extract. New data dimensions are added without modifying existing scraping logic (Open/Closed Principle).

**Graceful normalisation skip.** If no canonical teams file exists for a league, the pipeline logs a warning and continues with raw team names. Raw data is still valuable without normalisation — the pipeline never crashes on missing reference data.

**Year-based ongoing season detection.** Instead of relying on empty winner columns (which breaks for historical data gaps like NPFL 2005), the pipeline combines `end_year >= current_year` with winner column state to classify seasons accurately as COMPLETED, NO_WINNER, or ONGOING.

**Awarded match detection.** The scraper finds walkover matches from the stage indicator adjacent to the match date. Leagues show `Awrd` and cups show `WO`. The output marks these matches with `awarded: true`. The scraper does not get halftime scores for these matches, because the teams did not play.

**Stable selectors in one location.** All Soccerway selectors are in one block at the top of `scraper.py`. The selectors use only stable attributes:

- BEM classes, for example `event__match`
- `data-testid` attributes
- Class prefixes without a hash, for example `[class*="wcl-name"]`

The selectors do not use class names that contain a build hash, for example `wcl-name_jjfMf`. The site changes these names at each release. The scraper reads all match rows in one pass in the browser. A pure function (`parse_match_row`) parses each row. The unit tests test this function without a browser.

## Data Flow

```
leagues.yaml
    │
    ▼
SeasonDiscoverer ──→ archive page ──→ list of SeasonRecords
    │                                   (status, URL, champion)
    ▼
FootballScraper ──→ results page ──→ raw match data
    │                                   (scores, dates, teams)
    │
    ├──→ HT enrichment ──→ individual match pages ──→ halftime scores
    │
    ▼
TeamNormalizer ──→ canonical YAML ──→ resolved team names
    │                                   (exact match → fuzzy → review log)
    ▼
file_saver ──→ data/raw/{country}/{league}/{season}.json    (immutable, checksummed)
           ──→ data/exports/{country}/{league}/{season}.txt  (human-readable)
```

## Getting Started

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)

### Installation

```bash
git clone https://github.com/idrisakorede/african-football-pipeline.git
cd african-football-pipeline

# Install dependencies
uv sync

# Install Playwright browser
uv run playwright install chromium
```

### Running the Pipeline

```bash
uv run python main.py
```

The CLI presents interactive menus:

1. **Select leagues** — pick one, multiple (`1,3,5`), a range (`1-5`), or all (`all`)
2. **For each league**, the pipeline discovers available seasons from Soccerway's archive
3. **Select seasons** — same flexible input format
4. **Pipeline runs**: scrape → normalise → save → report statistics

### Example Output

```
======================================================================
  PIPELINE RUN SUMMARY
======================================================================
  Total seasons:    1
  Succeeded:        1
  Failed:           0
  Total matches:    240
  Elapsed time:     0:24:35
  ──────────────────────────────────────────────────────────────────
  SUCCEEDED:
    Ghana Premier League 2016/2017 — 240 matches
      JSON: data/raw/ghana/gh_pl/2016-17.json
      TXT:  data/exports/ghana/gh_pl/2016-17_gh1.txt
======================================================================
```

### Running Tests

```bash
# All tests
uv run pytest -v

# Unit tests only
uv run pytest tests/unit/ -v

# Integration tests only
uv run pytest tests/integration/ -v
```

The Soccerway regression tests are in `tests/integration/test_soccerway_fixtures.py`. These tests run the selectors and the JavaScript of the scraper on saved HTML pages. They use a local headless Chromium browser. They do not use the network, but they need the Playwright browser installation. If Soccerway changes its pages, get new fixtures from the live site. Then, run these tests. The failed tests show which selector does not work.

### Standalone Tools

```bash
# Extract team names from TXT exports
uv run python tools/extract_teams.py

# Merge per-season team files into master list
uv run python tools/merge_teams.py

# Reformat TXT files with aligned columns
uv run python tools/format_matches.py
```

## Data Quality

### Validation

Every scrape run validates all matches for required fields (home/away teams, scores, date, round, stage). Missing data is logged with match details and URL for manual investigation.

### Change Detection

Raw JSON files include a SHA256 checksum computed from the serialised match data. When the same season is re-scraped, compare the checksums to find if the data changed. If the data did not change, you can ignore the new scrape.

### Team Name Normalisation

The `TeamNormalizer` resolves raw scraped names to canonical forms using a two-stage strategy:

1. **Exact matching** — checks against all known aliases (case-insensitive)
2. **Fuzzy matching** — `difflib.SequenceMatcher` with configurable thresholds:
   - Above 0.85: auto-applied
   - 0.70–0.85: applied but flagged for review
   - Below 0.70: kept as-is, logged to `data/logs/unmatched_teams/`

Canonical team files are YAML with explicit aliases, curated per league as the pipeline discovers new name variations.

### Awarded Matches

The scraper finds walkover matches and marks them with `awarded: true`. It does not get halftime scores for these matches. The TXT export shows these matches as `3-0 (awarded)`. If the source shows no score, the TXT export shows `awarded`. This is usual for walkovers in cups.

### Penalty Shootouts

For a match with a penalty shootout, `home_score` and `away_score` contain the shootout score. `full_time_score` contains the score before the penalties. The TXT export shows `3-4 pen (0-0)`. If the halftime score is known, the TXT export shows `3-4 pen (0-0 aet; 0-0)`.

## Retry Logic

Season-level retry with backoff: attempt 1 (immediate) → attempt 2 (10s delay) → attempt 3 (30s delay). If all attempts fail, the pipeline logs the failure and continues to the next season. The run summary shows what succeeded and what failed.

## Currently Supported Leagues

| Country | League | Code | Submission Code |
|---------|--------|------|-----------------|
| Nigeria | Nigeria Professional Football League | npfl | ng1 |
| Nigeria | Nigeria National League | nnl | ng2 |
| Ghana | Ghana Premier League | gh_pl | gh1 |
| Egypt | Egypt Premier League | eg_pl | eg1 |

Adding a new league:

```yaml
# config/leagues.yaml
- code: sa_pl
  name: South Africa Premier Division
  country: south-africa
  slug: premier-division
  fetch_halftime: true
  submission_code: sa1
```

## Architecture Decisions

The project made these decisions in November 2026. At that time, the pipeline started to change from a Soccerway-only scraper to a multi-source system for historical data. Each decision shows what the decision is, why the project made it, and how the project applies it.

### 1. Cloud platforms are not in scope at this time

- **What:** The project removed the planned phases for S3, Snowflake, and Databricks.
- **Why:** The main source stopped working. The larger problem was that the pipeline used only one source. Cloud platforms add cost and complexity, but they do not make bad data better. Thus, the project first makes a reliable local pipeline.
- **How:** The project removed all cloud references from this README and from the package description. The project will examine cloud platforms again when the multi-source pipeline is complete and verified.

### 2. The pipeline uses multiple sources with fallback

- **What:** A Source Manager will try the sources in a priority sequence for each season. Soccerway is first. RSSSF and other sources are next. The Source Manager uses the next source only if a season is incomplete, or if a person requests verification.
- **Why:** If the pipeline scrapes all sources for each season, the load on the sites increases. The run time and the risk of rate limits also increase. Usually, the primary source has all the data for a season. The pipeline needs the other sources only to fill gaps or to do cross-checks.
- **How (planned, roadmap step 6):** `leagues.yaml` will contain the source priorities for each league. The Source Manager will record the sources that it tried for each season. After an interruption, it will continue from the last successful step.

### 3. Each adapter keeps fetch and parse separate

- **What:** Each source adapter will have three steps:
  1. `discover_seasons` finds the available seasons.
  2. `fetch` downloads the raw pages and keeps them without changes.
  3. `parse` changes the stored pages into match records that do not depend on the source.
- **Why:** The pipeline keeps the raw pages. Thus, after a parser repair, the pipeline can parse the data again without a new scrape. The saved pages also become fixtures for regression tests. After an interruption, a run can continue and ignore the pages that it already has.
- **How (planned, roadmap step 2):** The project will first change the Soccerway scraper to this structure. The output will not change. To verify the change, compare the JSON before and after the change.

### 4. Sources and fetchers are different; the project does not use Firecrawl

- **What:** A *source* is the location of the data and the method to read it, for example Soccerway or RSSSF. A *fetcher* is the method to download pages, for example plain HTTP or Playwright. Version 1 does not use Firecrawl.
- **Why:** Firecrawl is a paid API. Its AI extraction does not always give the same result. The project must have collection that you can repeat and test. Playwright already reads pages that use JavaScript.
- **How:** If the project adds Firecrawl in the future, it will be a fetcher only. It will not parse data.

### 5. PostgreSQL comes after the source-neutral data model

- **What:** PostgreSQL will become the single source of truth (roadmap step 3). The pipeline will make the JSON and TXT exports from the database, not directly from the scraper output.
- **Why:** The database tables must agree with the source-neutral match record from step 2. They must not agree with the page structure of Soccerway. If the project adds the database first, the tables will agree with the current Soccerway data. Then the project must change the tables again for RSSSF, because RSSSF often has no dates or rounds. Also, if the project makes one change at a time, it is easy to find the cause of a failure.
- **How (planned):** The project will use a dedicated database. This database is not the Airflow metadata database. It will contain tables for:
  - Raw page metadata
  - Match records from each source
  - Reconciled matches
  - Teams and team aliases
  - Season coverage
  - Collection runs

### 6. Soccerway and Flashscore are one source

- **What:** Soccerway now uses the Flashscore platform. If the two sites agree, this is not an independent confirmation.
- **Why:** Reconciliation has a value only if the sources are independent. Two views of the same database always agree.
- **How:** Verification will use independent sources, for example RSSSF. One check compares the total goals of the matches with the final league table.

### 7. "Verified" has a definition that you can test

- **What:** A season is *verified* when these two conditions are true:
  - The number of matches is equal to the expected number.
  - An independent source agrees, or the total goals agree with a final table.

  If not, the season status is *complete (single source)*, *incomplete*, *failed*, or *unavailable*.
- **Why:** Without a clear rule, the word "verified" has no meaning. Many African league seasons are not regular. Examples are seasons cancelled because of COVID, seasons with groups, and cancelled matches. Thus, the rule needs exceptions for each season.
- **How (planned, roadmap step 5):** For a double round-robin league with *n* teams, the default expected number of matches is *n × (n − 1)*. The configuration can change this number for each season. Incomplete data never replaces verified data.

## Changelog

### November 2026: Soccerway scraper repair

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

- All selectors are now in one block in `scraper.py`. They use only stable attributes. Refer to [Design Decisions](#design-decisions).
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

## Roadmap

At the end of each step, the pipeline works.

| Step | Work | Status |
|---|---|---|
| 1 | Repair the Soccerway scraper with stable selectors and saved-page fixtures | ✅ Done |
| 2 | Make a source-neutral match model and an adapter interface. Change Soccerway to fetch, parse, and raw storage. The output does not change. | Planned |
| 3 | Add the PostgreSQL schema and loading. Make the exports from the database. Add a season coverage table. | Planned |
| 4 | Add an RSSSF adapter. Start with the NPFL. Read multiple page formats and the final tables. | Planned |
| 5 | Add reconciliation between sources, validation rules, and season statuses | Planned |
| 6 | Add the Source Manager with fallback and resume. The Airflow DAG calls the library. | Planned |
| 7 | Add more leagues from RSSSF, and federation and league sites | Later |

## Tech Stack

| Tool | Purpose |
|------|---------|
| Python 3.12 | Core language |
| uv | Package management |
| Playwright | Browser automation |
| PyYAML | Configuration |
| Apache Airflow | Orchestration (local Docker) |
| PostgreSQL | Central database (planned, roadmap step 3) |
| pytest | Testing framework |
| Ruff | Linting and formatting |
| Pylance | Static type checking |

## License

MIT — see [LICENSE](LICENSE) for details.