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

# Install the Git pre-commit hook (do this one time in each clone)
uv run pre-commit install
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

### Code Checks

**Before each commit (pre-commit hook).** Git runs these checks when you do `git commit`. If a check fails, Git stops the commit. Some checks correct the files. Then, add the corrected files with `git add` and do the commit again.

| Check | What it does |
|-------|--------------|
| `ruff check --fix` | Finds code errors. Corrects the errors that it can. |
| `ruff format` | Formats the Python code. |
| `check-yaml`, `check-toml` | Finds syntax errors in YAML and TOML files, for example `config/leagues.yaml`. |
| `end-of-file-fixer`, `trailing-whitespace` | Removes spaces at line ends. Adds a newline at the end of each file. |
| `check-merge-conflict` | Finds merge-conflict markers, for example `<<<<<<<`. |
| `check-added-large-files` | Stops a commit that adds a large file. |

The hooks do not change the files in `tests/fixtures/`. These files are copies of real pages, and the tests need them without changes.

To run all checks on all files:

```bash
uv run pre-commit run --all-files
```

**On GitHub (CI).** GitHub Actions runs two jobs on each pull request and on each push to `main`:

| Job | Steps | Time |
|-----|-------|------|
| `lint` | `ruff format --check`, `ruff check`, `basedpyright` | Approximately 15 seconds |
| `test` | Install Chromium, then `pytest` | Approximately 1 minute |

The two jobs run at the same time. The `lint` job does not install a browser, thus it gives a result quickly.

The type checker (`basedpyright`) runs only in CI, not in the pre-commit hook. It checks the full project, not only the changed files, and it takes approximately 9 seconds on a laptop. A slow hook makes people skip it. Your editor shows the same type errors while you write the code (see the version rules below).

To run the type checker in your terminal:

```bash
uv run basedpyright
```

The `test` job runs in the `mcr.microsoft.com/playwright/python` Docker image. This image contains the system packages that Chromium needs. Before, CI installed these packages with `apt-get`. On a slow day, the Ubuntu package server made this step take 9 minutes.

**Version rules:**

- The pre-commit hook, CI and your terminal use the same Ruff version: the version in `uv.lock`. The hook runs `uv run ruff`. It does not install a different Ruff.
- The tag of the Docker image must agree with the Playwright version in `uv.lock`, for example `v1.65.1-noble` for Playwright 1.65.1. When you upgrade Playwright, change the tag in `.github/workflows/ci.yml` in the same pull request.
- CI and your terminal use the basedpyright version in `uv.lock`. The `[tool.pyright]` section of `pyproject.toml` sets `typeCheckingMode = "standard"`. An editor that uses basedpyright, Pyright or Pylance reads this section. The project setting replaces the setting of the editor. Thus, the editor shows the same errors as CI.

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

### 8. Pydantic for data from a source, frozen dataclasses for internal data

- **What:** The project uses two tools for data models. Each tool has a different job:

  | Data | Tool | Examples |
  |---|---|---|
  | Data from a source, after the parser reads it | Pydantic | `SourceMatch` |
  | Internal data that the code makes itself | Frozen dataclasses | `RawDocument`, `ResultRow`, `MatchPage` |
  | Data for output (files, database) | Dedicated serializers | The legacy JSON exporter (roadmap step 2) |

- **The debate:** The project examined three options.
  1. **Only dataclasses.** The project already used dataclasses, and they add no dependency. But you must write each check by hand. Rules that compare fields are easy to forget, for example "a penalty shootout needs a draw".
  2. **Only Pydantic.** Pydantic checks types and values when the code makes a record, and it converts records to and from JSON. But internal data does not need checks, because the code made it. Also, if the export uses `model_dump()`, the file format and the model become the same thing. Then a change to the model changes the files.
  3. **Both, with separate jobs (the decision).** Errors come into the pipeline at one location: where page text becomes data. Pydantic checks the data at this location. Inside the pipeline, simple frozen dataclasses are sufficient.
- **Why the settings of `SourceMatch` are strict:**
  - `strict=True`: the parser converts text to values, for example `'3'` to `3`. The model only checks the values. In the default mode, Pydantic converts `'3'` to `3` silently. Then a parser error that sends text is not found. In strict mode, the error occurs at the location of the problem.
  - `frozen=True`: after the parser makes a record, no step can change it. Many steps use the same records: export, database and reconciliation.
  - `extra="forbid"`: a field name with a spelling error causes an error. It is not ignored.
  - Model validators compare fields, for example: a played match must have a score, and a halftime score needs a full-time score.
- **Not now:** A domain `Match` model (frozen dataclass) comes in roadmap step 5. With only one source, there is nothing to reconcile. A `Match` model now would be a copy of `SourceMatch` with no logic.
- **Trade-offs:**
  - Contributors must know two model styles.
  - Pydantic is one more runtime dependency.
  - Strict mode makes more work for each parser: it must convert all values itself.
  - The model and the file format are separate. Thus, the legacy JSON format needs its own exporter code.

### 9. Parsing runs in Python, not in the browser

- **What:** Playwright only gets the pages. BeautifulSoup reads the stored HTML in Python. Before, a JavaScript function (`EXTRACT_STAGE_JS`) read the page in the browser.
- **Why:**
  - The pipeline can parse the stored pages again in seconds, without a browser and without the network.
  - The parser tests do not need Chromium.
  - The RSSSF adapter will parse text in Python too. Thus, all sources use the same method.
- **The debate:** Option 1 was to keep the JavaScript parser and load each stored page into a headless browser to parse it again. This keeps the tested code, but each parse needs a browser. Option 2 (the decision) was to write the parser again in Python. The cost is a rewrite of approximately 60 lines of JavaScript.
- **How:**
  - The parser has three levels. Level 1 (`extract_stages`) gives exactly the same data as the JavaScript function. Level 2 adds the stage and the round to each row. Level 3 (`to_source_match`) converts the text to values and makes a `SourceMatch`.
  - A parity test runs the JavaScript and the Python parser on the same fixture pages. The two outputs must be equal. To make sure that the test can fail, the project broke the Python parser on purpose. The test found the error.
  - The parser uses `html.parser`, which is part of Python. The pages come from a browser, thus the HTML is correct. Speed is not important for approximately 300 pages for each season.
- **Trade-offs:**
  - Until roadmap step 2 is complete, two parsers exist. The parity test keeps them equal. When the old scraper is removed, the parity test is removed too.
  - `lxml` is faster than `html.parser`, but it is one more dependency.

### 10. The raw store keeps pages as files, with a manifest

- **What:** The store keeps the pages of one season in one folder: `data/sources/{source}/{league}/{season}/`. Each page is a `.html.gz` file. A `manifest.json` file has an entry for each page: the URL, the file path, the fetch time (UTC), the sha256 value and the timezone.
- **Why:**
  - **Parse again:** after a parser repair, the pipeline reads the stored pages. It does not scrape the site again.
  - **Resume:** a new run reads the manifest and does not get a page again.
  - **Test fixtures:** a stored page can become a fixture for a regression test.
- **How:**
  - The store writes the page file first, then the manifest. If the process stops between the two writes, the manifest does not refer to a missing file.
  - The store writes the manifest to a temporary file, then renames it. A rename is atomic. Thus, the manifest is never half written.
  - The sha256 value comes from the HTML text, not from the gzip file. The gzip header contains a time. Thus, the same page gives different gzip bytes.
  - When the store reads a page, it compares the sha256 value. A damaged file causes an error. It does not give wrong data.
  - The store rejects unsafe file names, for example names with `..`. The match IDs in the file names come from the web page, and the store must not trust them.
  - `has(url, timezone)` compares the timezone too. Soccerway shows times in the browser timezone. Thus, a page from a different timezone is different data.
- **Trade-offs:**
  - Disk space: an estimate is 10–30 MB for each season, compressed. The project has not measured this value yet. The `data/` folder is not in git.
  - The store writes the full manifest at each save. For approximately 300 pages in each season, this is fast.
  - In roadmap step 3, the page metadata can move from the manifest into PostgreSQL.

### 11. The adapter interface is a Protocol, not a base class

- **What:** `SourceAdapter` is a `typing.Protocol` with `discover_seasons`, `fetch` (both async) and `parse`.
- **Why:** An adapter does not inherit from a base class. A class that has these methods is an adapter. Thus, the adapters do not depend on a shared base module, and there is no class hierarchy. `fetch` uses the network, thus it is async. `parse` reads files only, thus it is not async.
- **Trade-offs:** Python does not examine a Protocol when the program runs. Only a type checker finds an adapter with a wrong method. CI runs a type checker (basedpyright, see decision 12). But a type checker examines a Protocol only where the code uses it, for example `adapter: SourceAdapter = SoccerwayAdapter()`. At this time, no code uses `SourceAdapter`. A test proved this: a wrong return type in the Protocol gave no error. The real check starts with the Soccerway adapter (roadmap step 2, part 3).

### 12. The type checker is basedpyright, in standard mode

- **What:** CI runs `basedpyright` in the `lint` job. The project sets `typeCheckingMode = "standard"` in `pyproject.toml`.
- **The debate:**
  1. **Pyright** is the type checker from Microsoft. Its default mode is `standard`. It needs Node.js on the computer.
  2. **basedpyright** is a community fork of Pyright. It uses the same type-checking engine and follows the Pyright releases. It adds more rules, a *baseline* function, and editor functions that are not open source in Pylance. The PyPI package contains Node.js. Its default mode is `recommended`, which is much stricter.
  3. **The decision: basedpyright.** The editors of the project author (Neovim and Zed) use basedpyright. If CI used Pyright and the editors used basedpyright, the two tools would show different errors. This is the same problem as two Ruff versions.
- **Why standard mode:** The project measured the two modes on the same code:

  | Mode | Result |
  |---|---|
  | `standard` | 21 errors, all on one line of a test helper |
  | `recommended` | 82 errors and 1,501 warnings, most in the old scraper code |

  In standard mode, Pyright and basedpyright gave the same 21 errors. The project corrected the line (a `dict[str, Any]` type annotation). A new CI check must start with no errors. If not, it stops each pull request until a person corrects the old code.
- **How:** `basedpyright` is a dev dependency, thus `uv.lock` sets its version. The `[tool.pyright]` section has the settings. basedpyright, Pyright and Pylance all read this section. To make sure that the check can fail, the project changed a return type in `RawStore.get` on purpose. basedpyright found the error.
- **Trade-offs:**
  - basedpyright is a fork. A new Pyright release can come to basedpyright some days later.
  - Standard mode does not find all problems, for example values with an unknown type.
  - Later, when the old scraper is removed, the project can use `recommended` mode with a baseline. The baseline file records the current warnings. Then CI fails only on new warnings.

### 13. Build the new code next to the old code, and prove that they are equal

- **What:** The project does not replace a part of the pipeline in one step. It builds the new part next to the old part. A *parity test* runs the two parts on the same input and compares the outputs. Only after the outputs are equal does the pipeline change to the new part. Then the project removes the old part and its parity test.
- **The debate:**
  1. **Replace in one step.** This is faster to write. But if the output changes, it is difficult to find the cause, because many parts changed together.
  2. **Build next to the old code (the decision).** Each pull request adds one new part and one parity test. The old code stays the reference until the switch.
- **How:** Step 2 uses this method three times:

  | Pull request | New part | Parity test |
  |---|---|---|
  | Part 2 | Python parser | `extract_stages` and `EXTRACT_STAGE_JS` give the same rows (Chromium) |
  | Part 3a | Legacy exporter | Parser, `SourceMatch` and exporter give the same dictionaries as `parse_match_row` (no browser) |
  | Part 3b | Soccerway adapter | A live scrape gives the same JSON as a new baseline from the old scraper |

  The tests of part 3a do not need a browser, because the parity test of part 2 already proved that `extract_stages` gives the same rows as the JavaScript.

  For each parity test, the project broke the new code on purpose. The test must fail. A test that never failed proves nothing.
- **Trade-offs:**
  - For some time, the project has two versions of the same function. A person must not change only one of them.
  - Parity tests use fixtures. A fixture does not have all the special cases of the live site. Thus, part 3b also has a live check.
  - The parity tests are temporary. The project must remember to remove them after the switch.

## Changelog

### November 2026: Legacy exporter (roadmap step 2, part 3a)

**What happened:** The project added `exports/legacy.py`. It makes the current JSON match format from `SourceMatch` records. The pipeline does not use it yet. Thus, the output did not change.

**Why it was necessary:** `SourceMatch` keeps goals and penalty goals in different fields, and it uses numbers and dates. The current JSON and TXT files use a different format. The exporter keeps the special rules of this format in one location:

- For a penalty shootout, `home_score` and `away_score` contain the shootout score, and `full_time_score` contains the score before the shootout (`0-0`, without spaces).
- All scores are text. The halftime score has spaces (`2 - 1`).
- The date is `DD.MM.YYYY`, or `DD.MM.YYYY HH:MM` if the kick-off time is known.
- An awarded match always has the `awarded_reason` `walkover`.
- The keys have the same sequence as before. The checksum of `file_saver` sorts the keys, but the JSON files show the keys in their sequence.

**How:** `to_legacy_match` changes one `SourceMatch` into one dictionary. `to_legacy_stages` puts the dictionaries into stages, with `total_rounds` and `total_matches`. See decision 13 for the parity tests.

**Verification:**

- Parity tests on the league fixture and the cup fixture: all dictionaries are equal to the output of `parse_match_row`, also in key sequence. A third test adds the match page (kick-off time and halftime score).
- The project broke the exporter two times on purpose: spaces in `full_time_score`, and two keys in a different sequence. The tests failed with the exact differences.
- 10 new tests. All 209 tests pass. basedpyright gives 0 errors.

**Trade-offs:** The exporter keeps the special rules of the legacy format alive. New outputs, for example the database in roadmap step 3, must use `SourceMatch` directly, not this format.

### November 2026: Type checking in CI

**What happened:** The `lint` job in CI now runs `basedpyright`.

**Why:** Decision 11 showed a gap. Only a type checker examines the `SourceAdapter` Protocol, but no type checker ran automatically.

**How:** See decision 12 and [Code Checks](#code-checks). The project corrected the 21 errors before it added the check. Thus, the check started with no errors.

**Trade-offs:** The `lint` job takes approximately 4 seconds more. The type checker is not in the pre-commit hook, because it takes approximately 9 seconds on a laptop.

### November 2026: Source-neutral model and Python parser (roadmap step 2, parts 1 and 2)

**What happened:** The project added the first parts of the multi-source structure. The pipeline does not use them yet. Thus, the output did not change.

- Part 1: the `SourceMatch` model, the `SourceAdapter` interface, and the raw page store (`RawStore`). See decisions 8, 10 and 11.
- Part 2: a Python parser for the stored Soccerway pages, with a parity test against the JavaScript parser. See decision 9.

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

### November 2026: Faster CI and a pre-commit hook

**What happened:** CI took 7–9 minutes for each run. Now it takes less than 1 minute.

**Why:** The step that installs the system packages for Chromium used `apt-get`. The Ubuntu package server was slow (64 kB/s). Each check, also the format check, waited for this step.

**How:** See [Code Checks](#code-checks). The `lint` job does not install a browser. The `test` job runs in the Playwright Docker image, which contains the system packages. A pre-commit hook runs Ruff and file checks before each commit.

**Trade-offs:**

- The tag of the Docker image must agree with the Playwright version in `uv.lock`. A person must change the two together.
- The Docker image download takes approximately 20 seconds of each run.
- Each clone must run `uv run pre-commit install` one time.

### November 2026: Kick-off times in local league time

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
| 2 | Make a source-neutral match model and an adapter interface. Change Soccerway to fetch, parse, and raw storage. The output does not change. | In progress (parts 1, 2 and 3a done; part 3b next) |
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
| Pydantic | Checks the match records from the source parsers |
| BeautifulSoup | Reads the stored HTML pages |
| Apache Airflow | Orchestration (local Docker) |
| PostgreSQL | Central database (planned, roadmap step 3) |
| pytest | Testing framework |
| Ruff | Linting and formatting |
| pre-commit | Runs the checks before each commit |
| GitHub Actions | CI: runs the checks and the tests on each pull request |
| basedpyright | Static type checking (CI and editors) |

## License

MIT — see [LICENSE](LICENSE) for details.
