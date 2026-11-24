# The Pipeline Database

The pipeline database is a PostgreSQL 18 container with the name `pipeline-db`. The root `docker-compose.yaml` defines it. It is not the Airflow metadata database.

| Item | Value |
|---|---|
| Address from your computer | `localhost:5433` (only `127.0.0.1`, not the network) |
| Address from a container in the same Compose project | `pipeline-db:5432` |
| Database, user, password | `football`, `pipeline`, `pipeline` (local development values, not secrets) |
| Data | The Docker volume `african-football-pipeline-db` |

`DATABASE_URL` in `.env` gives the connection to the Python code. Commands that need the database use `uv run --env-file .env ...`.

```bash
# Open a SQL prompt
psql postgresql://pipeline:pipeline@localhost:5433/football

# Stop the container. The data stays in the volume.
docker compose down
```

Do not use `docker compose down -v`. The `-v` option deletes the volume and all the data.

**Migrations.** The schema is in SQL files in `src/african_football/db/migrations/`. The runner applies the new files in the sequence of their versions, and records each file in the table `schema_migrations`. To change the schema:

1. Add a new file with the next version, for example `002_add_teams.sql`. Do not put `BEGIN` or `COMMIT` in the file. The runner applies each file in one transaction.
2. Run `uv run --env-file .env python -m african_football.db.migrate`.

Do not change a file after the runner applied it. The runner records the sha256 of each file. If an applied file changes, the runner stops with an error.

**Airflow.** `airflow/docker-compose.yaml` includes the root `docker-compose.yaml`. Thus, `docker compose up` in `airflow/` also starts `pipeline-db`, and the Airflow tasks get `DATABASE_URL`. The two Compose projects use the same volume. Run only one `pipeline-db` at a time: do `docker compose down` in the root folder before you start Airflow.

**Collection runs.** When `DATABASE_URL` is set, `FootballScraper` writes each scrape to the database ([decision 18](decisions/0018-loader-records-each-run.md)):

- `collection_runs`: one row for each run, with the status `running`, `succeeded` or `failed`.
- `raw_documents`: one row for each stored page (the HTML stays in `data/sources/`).
- `source_matches`: one row for each match. A new run updates the row.

Without `DATABASE_URL`, the scraper logs a warning and does not use the database. To use the database with the CLI:

```bash
uv run --env-file .env python main.py
```

Useful queries:

```sql
-- The last 10 runs, with their duration and errors
SELECT r.run_id, s.league_code, s.label, r.source, r.status,
       r.started_at, r.finished_at - r.started_at AS duration,
       r.pages_fetched, r.matches_parsed, r.error
FROM collection_runs r JOIN seasons s USING (season_id)
ORDER BY r.run_id DESC LIMIT 10;

-- Runs that stopped without a status (a crash or a killed process)
SELECT run_id, started_at FROM collection_runs
WHERE status = 'running' AND started_at < now() - interval '2 hours';

-- Matches that the last successful run of the season did not find
SELECT m.source_match_id, m.home_team_raw, m.away_team_raw, m.last_run_id
FROM source_matches m
JOIN seasons s USING (season_id)
WHERE s.league_code = 'gh_pl' AND s.label = '2023/2024'
  AND m.last_run_id <> (
      SELECT max(run_id) FROM collection_runs r
      WHERE r.season_id = m.season_id AND r.source = m.source AND r.status = 'succeeded');

-- Matches whose data changed after the first scrape
SELECT source_match_id, home_team_raw, away_team_raw, ht_home, ht_away, updated_at
FROM source_matches
WHERE updated_at > first_seen_at
ORDER BY updated_at DESC;
```

For the SQL techniques of the loader (the upsert, `xmax = 0`, `IS DISTINCT FROM`), refer to the [db module README](../src/african_football/db/README.md).
