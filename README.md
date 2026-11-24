# African Football Data Pipeline

This pipeline collects historical football data for African domestic leagues. It collects the match results for each season. It normalises the team names, validates the data, and exports the data as JSON and as OpenFootball text.

The pipeline runs on one local computer. It uses Python, Playwright, Airflow, and PostgreSQL. The project is changing PostgreSQL into the central store of the pipeline data (roadmap step 3). Cloud platforms are not in the scope of the project at this time. For the reasons, refer to [decision 1](docs/decisions/0001-no-cloud-platforms.md).

The code uses typed Python, automated tests, and conventional commits. The tests include regression tests that use saved copies of web pages.

## Table of Contents

- [Architecture](#architecture)
- [Data Flow](#data-flow)
- [Getting Started](#getting-started)
- [Data Quality](#data-quality)
- [Retry Logic](#retry-logic)
- [Currently Supported Leagues](#currently-supported-leagues)
- [Documentation](#documentation)
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
│   ├── season_model.py           ← SeasonStatus enum + SeasonRecord (two-phase population)
│   └── source_match.py           ← SourceMatch: the match record of one source (Pydantic)
├── config/
│   └── config_loader.py          ← YAML → validated LeagueConfig objects
├── scraping/
│   ├── url_builder.py            ← URL construction + archive URL builder
│   ├── season_discoverer.py      ← Discovers seasons + champions from archive pages
│   └── scraper.py                ← FootballScraper: entry point (fetch → parse → export)
├── sources/
│   ├── base.py                   ← SourceAdapter Protocol + RawDocument
│   ├── raw_store.py              ← RawStore: stored pages + manifest.json
│   └── soccerway/
│       ├── adapter.py            ← SoccerwayAdapter: fetch with Playwright, parse
│       └── parser.py             ← Reads stored HTML with BeautifulSoup
├── exports/
│   └── legacy.py                 ← SourceMatch → the current JSON match format
├── db/
│   ├── README.md                 ← The SQL techniques of the module (upsert, xmax, IS DISTINCT FROM)
│   ├── migrate.py                ← Migration runner (python -m african_football.db.migrate)
│   ├── loader.py                 ← RunRecorder: writes each run, its pages and its matches
│   └── migrations/
│       └── 001_initial.sql       ← The first schema: six tables
└── utils/
    ├── logger.py                 ← PipelineLogger (console + file)
    ├── file_saver.py             ← JSON/TXT export with SHA256 checksums
    └── team_normalizer.py        ← Exact + fuzzy matching with review log

main.py                           ← CLI orchestrator with batch selection + retry logic
tools/                            ← Standalone utilities (extract, merge, format teams)

airflow/
├── dags/scrape_leagues.py        ← Thin DAG: load configs → build jobs → scrape (parallel) → summarise
├── plugins/pipeline_tasks.py     ← Task logic calling the library
└── docker-compose.yaml           ← Local Airflow stack (includes the root docker-compose.yaml)

docker-compose.yaml               ← The pipeline database (pipeline-db, PostgreSQL 18)
.env.example                      ← DATABASE_URL for local work (copy to .env)

tests/
├── unit/                         ← Pure-function tests (no browser, no network)
├── integration/                  ← Component wiring + saved-page regression tests
└── fixtures/soccerway/           ← Trimmed copies of real Soccerway pages

data/
├── sources/{source}/{league}/{season}/ ← Raw pages (.html.gz) + manifest.json
├── raw/{country}/{league}/       ← Immutable JSON snapshots
├── exports/{country}/{league}/   ← Human-readable TXT exports
└── logs/unmatched_teams/         ← Flagged names for manual curation
```

> **Why are the modules separate?** The models, config, scraping, and utils modules are independent. Thus, the CLI and Airflow use the same library code. Airflow tasks import `SeasonDiscoverer`, `FootballScraper`, and `file_saver` directly. The DAG files do not contain pipeline logic.

For the early design choices (config-driven leagues, two-phase season records, capability flags, stable selectors), refer to [Design Notes](docs/design.md).

## Data Flow

```
leagues.yaml
    │
    ▼
SeasonDiscoverer ──→ archive page ──→ list of SeasonRecords
    │                                   (status, URL, champion)
    ▼
FootballScraper
    │
    ├──→ SoccerwayAdapter.fetch ──→ results page + match pages ──→ RawStore
    │                                (Playwright)                   data/sources/...
    │
    ├──→ SoccerwayAdapter.parse ──→ stored pages ──→ SourceMatch records
    │                                (BeautifulSoup, no network)
    │
    ├──→ legacy exporter ──→ match dictionaries in the current JSON format
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
- Docker with Docker Compose 2.20 or later (for the pipeline database)

### Installation

```bash
git clone https://github.com/idrisakorede/african-football-pipeline.git
cd african-football-pipeline

# Install dependencies
uv sync

# Install Playwright browser
uv run playwright install chromium

# Install the Git pre-commit hook (do this one time in each clone)
uv run pre-commit install

# Make your local settings file (do not commit .env)
cp .env.example .env

# Start the pipeline database and make the tables
docker compose up -d --wait
uv run --env-file .env python -m african_football.db.migrate
```

The pipeline database is a PostgreSQL 18 container (`pipeline-db`, `localhost:5433`). For the connection, the migrations and the use with Airflow, refer to [The Pipeline Database](docs/database.md).

### Running the Pipeline

```bash
uv run python main.py

# Also write each run to the pipeline database
uv run --env-file .env python main.py
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

# All tests, also the database tests (the pipeline database must run)
uv run --env-file .env pytest -v
```

The tests with the `db` marker need PostgreSQL. Without `DATABASE_URL`, pytest skips them. In CI, a missing `DATABASE_URL` is an error, not a skip. Each database test makes a new empty database, and deletes it after the test. Thus, the tests do not change the data in `football`.

The Soccerway tests use saved pages in `tests/fixtures/soccerway/`. They do not use the network:

- `tests/unit/test_soccerway_parser.py` tests the parser selectors. It does not need a browser.
- `tests/integration/test_soccerway_fixtures.py` tests the two selectors that the browser uses during `fetch`. It needs the Playwright Chromium installation.
- `tests/integration/test_soccerway_adapter.py` runs the real `fetch` code. Playwright stops each request of the browser and answers it with a fixture page (`page.route`). Thus, the tests examine page loads, the "Show more" loop, the halftime wait, retries and resume without a request to Soccerway.

If Soccerway changes its pages, get new fixtures from the live site. Then, run these tests. The failed tests show which selector does not work.

### Code Checks

A pre-commit hook runs Ruff, sqlfluff and file checks before each commit. GitHub Actions runs a `lint` job (Ruff, basedpyright, sqlfluff) and a `test` job (pytest with PostgreSQL 18). For the details and the version rules, refer to [Development](docs/development.md).

```bash
uv run pre-commit run --all-files   # all hooks on all files
uv run basedpyright                 # type check
```

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

| Country | League | Code | Submission Code | Timezone |
|---------|--------|------|-----------------|----------|
| Nigeria | Nigeria Professional Football League | npfl | ng1 | Africa/Lagos |
| Nigeria | Nigeria National League | nnl | ng2 | Africa/Lagos |
| Ghana | Ghana Premier League | gh_pl | gh1 | Africa/Accra |
| Egypt | Egypt Premier League | eg_pl | eg1 | Africa/Cairo |

Adding a new league:

```yaml
# config/leagues.yaml
- code: sa_pl
  name: South Africa Premier Division
  country: south-africa
  slug: premier-division
  fetch_halftime: true
  timezone: Africa/Johannesburg
  submission_code: sa1
```

The `timezone` field is necessary. It must be an IANA timezone name. The scraper shows all dates and kick-off times in this timezone. If the field is missing or the name is not known, the pipeline stops when it loads the configuration.

## Documentation

| Document | Content |
|---|---|
| [Architecture Decisions](docs/decisions/README.md) | One file for each decision: what, why, the options, how, and the trade-offs |
| [Changelog](CHANGELOG.md) | What each change did, why, how, and its verification |
| [The Pipeline Database](docs/database.md) | Connection, migrations, Airflow |
| [Development](docs/development.md) | The pre-commit hook, CI, and the version rules |
| [Design Notes](docs/design.md) | Config-driven leagues, capability flags, selectors, and other early design choices |

## Roadmap

At the end of each step, the pipeline works.

| Step | Work | Status |
|---|---|---|
| 1 | Repair the Soccerway scraper with stable selectors and saved-page fixtures | ✅ Done |
| 2 | Make a source-neutral match model and an adapter interface. Change Soccerway to fetch, parse, and raw storage. The output does not change. | ✅ Done |
| 3 | Add the PostgreSQL schema and loading. Make the exports from the database. Add a season coverage table. | In progress: parts 1 and 2 of 3 done (database, schema, migrations, loader) |
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
| Pydantic | Checks the match records from the source parsers |
| BeautifulSoup | Reads the stored HTML pages |
| Apache Airflow | Orchestration (local Docker) |
| PostgreSQL 18 | Central database (roadmap step 3), in Docker |
| psycopg 3 | PostgreSQL driver for Python |
| Docker Compose | Runs the pipeline database and the local Airflow stack |
| pytest | Testing framework |
| Ruff | Linting and formatting |
| sqlfluff | Linting and formatting of the SQL files |
| pre-commit | Runs the checks before each commit |
| GitHub Actions | CI: runs the checks and the tests on each pull request |
| basedpyright | Static type checking (CI and editors) |

## License

MIT — see [LICENSE](LICENSE) for details.
