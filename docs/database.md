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
