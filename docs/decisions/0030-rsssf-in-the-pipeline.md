# 30. RSSSF in the pipeline: a source option, a source folder for the files, and a check of the migrations

*Status: accepted (November 2026). Ends roadmap step 4. [All decisions](README.md)*

- **What:** `main.py --source rsssf` runs the pipeline with the RSSSF adapter: discovery from the list of champions, the pages, the matches and the final tables go to the pipeline database, and the JSON and TXT files come from the database. The RSSSF files are in a subfolder `rsssf/`. Before the menus, `main.py` stops if the database does not have all the migrations.
- **Why:** Parts 1 to 3 of step 4 made the RSSSF adapter, but no part of the pipeline used it. The first live run of the NPFL found a second problem: the pipeline database of the project did not have migration 002 (`source_tables`). Each season with a final table failed three times with an SQL error, with waits between the attempts.
- **How the project did it:** `FootballScraper(source=...)`, `parse_args()`, `discover()`, a `source` argument for the file paths, `pending()` in `db/migrate.py`, and longer waits in the RSSSF client. Then a live run of all NPFL seasons of RSSSF.

## The debate

**How to choose the source.** Three options: a command-line option (`--source rsssf`), a question in the menus, or a second script. The user chose the option: a small change, and step 6 (the Source Manager) will choose the sources automatically.

**Where the files of RSSSF go.** The paths `data/raw/{country}/{league}/{season}.json` and `data/exports/...` have no source. An RSSSF run of a season replaced the Soccerway file of the same season. Three options: a subfolder for RSSSF only, a subfolder for each source, or no files for RSSSF until step 5. The user chose the subfolder for RSSSF only: the Soccerway paths and the programs that read them do not change.

| Source | JSON | TXT |
|---|---|---|
| Soccerway | `data/raw/nigeria/npfl/2023-24.json` | `data/exports/nigeria/npfl/2023-24_ng1.txt` |
| RSSSF | `data/raw/nigeria/npfl/rsssf/2023-24.json` | `data/exports/nigeria/npfl/rsssf/2023-24_ng1.txt` |

## What changes for each source

| | Soccerway | RSSSF |
|---|---|---|
| Discovery | the season list of the league page (a browser) | the list of champions (`rsssf_index`, `rsssf_section`) |
| Browser | yes | no |
| Final tables | no | yes (`RunRecorder.load(..., tables)`) |
| Halftime scores | if `fetch_halftime` | never: the pages have none |
| Network errors in the statistics | counted | not counted (the client retries) |

## The check of the migrations

`pending(conn)` gives the migration files that the database does not have. It only reads: it does not make `schema_migrations`. `main.py` calls it before the menus and stops with the command:

```text
The database does not have the migrations 002_source_tables.sql. Run: uv run --env-file .env python -m african_football.db.migrate
```

Without the check, the error came in each season, after three attempts and 40 seconds of waits.

## Retries of the RSSSF client

The waits before the retries were 5, 15 and 45 seconds (about 1 minute). The network of the project has DNS failures that last some minutes: the survey lost 2 pages, and a `git pull` failed during this work. The waits are now 5, 15, 45, 120 and 300 seconds (about 8 minutes). The interval between two requests (3 seconds) does not change.

## The live run of the NPFL

All the NPFL seasons of RSSSF, with the pages from the raw store (discovery used the network):

| | |
|---|---|
| Seasons in the list | 51 (49 completed) |
| Runs | 49 succeeded, 0 failed |
| Matches | 7,983 |
| Coverage | 9 seasons `complete_single_source`, 40 `incomplete` |
| Seasons with a final table | 31; table checks that agree: 15 of 35 |

The numbers that do not agree have known causes:

- The expected number of matches comes from the teams in the matches. RSSSF writes one club in different ways, thus some seasons have too many teams (1998: 31 names, 930 matches expected). The team normaliser of step 5 corrects it.
- A table with a goal deduction does not agree on the goals. NPFL 2023/24: 380 matches on both sides, 845 goals in the table and 851 in the results ('Gombe United 3 points and 3 goals deducted'). The parser and the database give the same numbers.
- Many old seasons have no results on RSSSF, only a table or the champion.

## Trade-offs

- The source is an option of each run. A run of both sources for a league is two runs. Step 6 will choose and combine the sources.
- The Soccerway files have no source folder, and the RSSSF files have one. The paths are not the same form for the two sources.
- The migration check is in `main.py` only. Code that uses `FootballScraper` without `main.py` gets the SQL error as before.
