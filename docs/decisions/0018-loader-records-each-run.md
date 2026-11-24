# 18. The loader records each run in three transactions, and keeps the matches that the source stops to show

*Status: accepted (November 2026). [All decisions](README.md)*

- **What:** `db/loader.py` writes each scrape to the pipeline database. `RunRecorder.start()` writes the league, the season and a `collection_runs` row with the status `running`. `load()` writes the stored pages and the matches, and changes the run to `succeeded`. `fail()` changes the run to `failed`. A new scrape of a season updates the matches. It does not add them again.
- **The debate:**
  1. **When to write the run.**
     - *One transaction at the end:* simple. But a run that stops (a crash, a killed process) leaves no row. Nobody can see that it started.
     - *Three transactions (the decision):* `start()` is committed at once, thus a run that stops stays visible as `running` with no `finished_at`. `load()` is one transaction, thus the database never has a part of a season. `fail()` records the error in its own transaction.
  2. **A match that the source does not show again** (the source deleted it, or a page loaded only a part of the list).
     - *Delete it:* the database is always equal to the last scrape. But one bad scrape deletes good data.
     - *Keep it and report it (the decision):* the row stays. Its `last_run_id` is older than the current run, thus a query finds it. The loader counts these matches, and the scraper logs a warning. A person decides what to do.
  3. **Must the scraper have a database in this step?**
     - *Required now:* less code. But `main.py` and Airflow need Docker from this step.
     - *Optional until step 3, part 3 (the decision):* with `DATABASE_URL`, each run goes into the database. Without it, the scraper logs a warning and works as before. Part 3 makes the exports read from the database. Then the database becomes necessary.
  4. **What `updated_at` means.**
     - *The time of the last scrape:* this is the same as the time of `last_run_id`, thus it adds no information.
     - *The time of the last change of the data (the decision):* a scrape with the same data changes only `last_run_id`. Thus `updated_at` shows when the source changed a match, for example a late halftime score.
- **How:** refer to the [db module README](../../src/african_football/db/README.md) for the SQL techniques: the upsert, `xmax = 0`, `IS DISTINCT FROM`, `now()` and `clock_timestamp()`.
- **Trade-offs:**
  - The rows of a failed `load()` are not in the database. The pages stay in the raw store, thus the next run can parse them again without the network.
  - A match that the source shows again with a new ID is a new row. The old row stays as "not seen". Reconciliation (roadmap step 5) must find such pairs.
  - The scraper uses a synchronous database connection in an async method. The database calls take less than a second for a season, thus they do not stop the browser work for long. If many seasons run at the same time in one process (roadmap step 6), the project must examine the async connection of psycopg.
  - `load()` writes one row at a time (approximately 300 matches for a season). This is sufficient now. For many seasons, a batch write is faster.
