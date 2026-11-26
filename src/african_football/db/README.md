# The `db` module

This folder has the code that writes to the pipeline database (PostgreSQL 18). For the setup and the connection, refer to [The Pipeline Database](../../../docs/database.md).

| File | What it does |
|---|---|
| `migrations/001_initial.sql` | The first schema: six tables with constraints ([decision 16](../../../docs/decisions/0016-database-repeats-sourcematch-rules.md)) |
| `migrate.py` | Applies the new migration files, and records them in `schema_migrations` ([decision 15](../../../docs/decisions/0015-plain-sql-migrations-not-alembic.md)) |
| `loader.py` | Writes one collection run: the league, the season, the run, the stored pages and the matches ([decision 18](../../../docs/decisions/0018-loader-records-each-run.md)) |
| `reader.py` | Reads the matches of the latest succeeded run of a season for the exports ([decision 19](../../../docs/decisions/0019-exports-read-from-the-database.md)) |
| `migrations/002_source_tables.sql` | The final tables of the seasons ([decision 23](../../../docs/decisions/0023-final-tables-and-the-table-check.md)) |

The sections below explain the techniques in this code. Each section gives what the technique is, why the code uses it, and how. The examples use the tables of `001_initial.sql`.

---

## 1. The upsert: `INSERT ... ON CONFLICT ... DO UPDATE`

**What:** One statement that adds a row, or changes the row that has the same key.

```sql
INSERT INTO leagues (league_code, name, country, timezone)
VALUES ('gh_pl', 'Ghana Premier League', 'ghana', 'Africa/Accra')
ON CONFLICT (league_code) DO UPDATE SET
    name = EXCLUDED.name,
    country = EXCLUDED.country,
    timezone = EXCLUDED.timezone;
```

**Why:** A second scrape of a season must update its matches, not add them again. A `SELECT` first and then an `INSERT` or an `UPDATE` needs two statements, and a different process can write the row between them.

**How:**
- `ON CONFLICT (league_code)` needs a unique constraint or a primary key on these columns. The conflict is a duplicate key. Without a unique constraint, there is no conflict to find.
- `EXCLUDED` is the row that the `INSERT` tried to add. `leagues.name` (or only `name`) is the row in the table.

## 2. `DO UPDATE` or `DO NOTHING`, and `RETURNING`

**What:** `RETURNING` gives values from the row that the statement wrote, without a second `SELECT`.

```sql
INSERT INTO seasons (league_code, label, start_year, end_year)
VALUES ('gh_pl', '2023/2024', 2023, 2024)
ON CONFLICT (league_code, label) DO UPDATE SET
    start_year = EXCLUDED.start_year,
    end_year = EXCLUDED.end_year
RETURNING season_id;
```

**Why:** With `DO NOTHING`, PostgreSQL writes no row for a season that exists. Then `RETURNING` gives **no row**, and the loader does not get the `season_id`. With `DO UPDATE`, there is always a written row, thus `RETURNING` always gives the ID.

**How:** The loader uses `DO NOTHING` only when it does not need a value back. An example is `raw_documents`: the same URL with the same sha256 is the same page. To know if a row was added, the loader reads `cursor.rowcount`: 1 for a new row, 0 when `DO NOTHING` did not write.

## 3. `xmax = 0`: was the row added or changed?

**What:**

```sql
INSERT INTO source_matches (...) VALUES (...)
ON CONFLICT (source, source_match_id) DO UPDATE SET ...
RETURNING xmax = 0 AS inserted;
```

`inserted` is true for a new row and false for an updated row.

**Why:** The loader counts the new matches and the changed matches of each run. An upsert does not tell which of the two it did.

**How:** `xmax` is a hidden system column of each PostgreSQL row. It records the transaction that removed or locked this version of the row. A new row has `xmax = 0`. An `ON CONFLICT DO UPDATE` locks the old row before it writes the new version, thus the new version has a value that is not 0. The project checked this in `psql`: the first upsert of a key gave `inserted = true`, the second gave `false`.

The column `xmax` is in the PostgreSQL documentation (system columns). Its value after an upsert is an internal detail, not a promise of the documentation, and it is not standard SQL. Many projects use it for this purpose. If a future PostgreSQL version changes it, the loader tests that count new and changed matches will fail.

## 4. `IS DISTINCT FROM`, not `<>`

**What:** The loader changes `updated_at` only when the data of a match changed:

```sql
updated_at = CASE
    WHEN (source_matches.ht_home, source_matches.ht_away)
         IS DISTINCT FROM (EXCLUDED.ht_home, EXCLUDED.ht_away)
    THEN now()
    ELSE source_matches.updated_at
END
```

(The real statement compares all the data columns.)

**Why:** In SQL, a comparison with `NULL` does not give true or false. It gives `NULL`, which means "unknown":

| Expression | Result |
|---|---|
| `1 <> 2` | true |
| `NULL <> 1` | **NULL** |
| `(NULL, NULL) <> (1, 1)` | **NULL** |
| `NULL IS DISTINCT FROM 1` | true |
| `NULL IS DISTINCT FROM NULL` | false |

`CASE WHEN NULL` takes the `ELSE` branch. Thus with `<>`, a match whose halftime score changed from missing (`NULL`) to `1 - 1` is "not changed". `IS DISTINCT FROM` compares `NULL` as a normal value.

**How the project found it:** For a deliberate break, the project changed `IS DISTINCT FROM` to `<>`. All tests passed, except `test_changed_match_is_updated`, which adds a halftime score to a match that had none.

Use `IS DISTINCT FROM` (or `IS NOT DISTINCT FROM`) each time a column can be `NULL`.

## 5. `now()` and `clock_timestamp()`

**What:** In a transaction, `now()` always gives the **start time of the transaction**. `clock_timestamp()` gives the time at the moment of the call.

**Why:** The loader uses each function on purpose:
- `updated_at = now()`, then `RETURNING updated_at = now() AS changed`. The two `now()` give the same value, because they are in the same transaction. Thus `changed` is true only for the rows that this transaction changed.
- `finished_at = clock_timestamp()`. With `now()`, `finished_at` would be the time when `load()` started, not when it finished.

**How:** Use `now()` to mark all rows of one transaction with one time. Use `clock_timestamp()` to record when something occurred.

## 6. Transactions and `autocommit=True`

**What:** The connections use `psycopg.connect(url, autocommit=True)`, and the code puts each unit of work in `with conn.transaction():`.

**Why:** Without `autocommit=True`, psycopg starts a transaction at the first statement and keeps it open until the connection closes. Each `conn.transaction()` is then only a *savepoint* in that outer transaction. If an error stops the program, psycopg rolls back the outer transaction, and **all** the work goes, also the work of the blocks that completed.

**How:** With `autocommit=True`, each `conn.transaction()` block is a real `BEGIN` ... `COMMIT`. The loader uses three blocks for each run:

| Block | Why it is a different transaction |
|---|---|
| `start()` | Committed at once. A run that stops stays visible as `running`. A test reads it from a second connection, which sees only committed data. |
| `load()` | All pages and matches of the run, and the status `succeeded`. If one row fails, nothing of the run stays. |
| `fail()` | Records the error. |

**A surprise:** PostgreSQL runs a text with many statements (`CREATE TABLE c ...; SELECT 1/0;`) that it gets in one call as one *implicit* transaction. Thus a test that fails a migration file in its second statement passes also without `conn.transaction()`. The real reason for the transaction in `migrate.py` is to keep the file and its row in `schema_migrations` together. The test `test_file_and_its_record_are_one_transaction` tests exactly this.

## 7. `LiteralString`: SQL from constants only

**What:** psycopg accepts SQL text only of the type `LiteralString`: text that the type checker can prove comes from constants in the code.

**Why:** This stops SQL injection at the type check. Data must go into the `%s` placeholders, never into the SQL text:

```python
conn.execute("SELECT * FROM seasons WHERE label = %s", (label,))   # correct
conn.execute(f"SELECT * FROM seasons WHERE label = '{label}'")     # type error
```

**How:**
- The upsert of `source_matches` is made from a list of column names. The list has the type `tuple[LiteralString, ...]`. `", ".join(...)` and f-strings of `LiteralString` values are also `LiteralString`. Thus the type checker accepts the result, without `# pyright: ignore`.
- A migration file is not a constant. `migrate.py` gives it to psycopg as bytes (`path.read_bytes()`). psycopg accepts bytes.

## 8. Python values and PostgreSQL types

| Python | PostgreSQL | Note |
|---|---|---|
| `datetime` with a timezone | `timestamptz` | A `datetime` without a timezone is not an exact moment. All times in the project have a timezone. |
| `date`, `time` | `date`, `time` | `kickoff_local` is a local time. The `timezone` column gives the zone. |
| `list[str]` | `text[]` | A **tuple** is not changed into an array. `SourceMatch.raw_documents` is a tuple, thus the loader changes it into a list. |
| `MatchStatus` | `text` | The loader writes `status.value`. The `CHECK` constraint allows only the known values. |

## 9. `BaseException`, not `Exception`

**What:** `FootballScraper.scrape()` marks the run `failed` with `except BaseException`, and then raises the error again.

**Why:** `KeyboardInterrupt` (Ctrl+C) and `asyncio.CancelledError` (Airflow cancels a task) are not subclasses of `Exception`. With `except Exception`, a cancelled run stays `running` for all time. A deliberate break proved this: `test_scraper_marks_a_cancelled_run` failed.

**How:** Catch `BaseException` only to record the failure, and always raise the error again. If the record of the failure also fails, for example because the database stopped, the scraper logs this second error. Then it raises the first error, because the first error is the cause.

## 10. A subquery that finds the latest run

**What:** `read_season_matches()` gives the matches of the latest succeeded run only:

```sql
SELECT ... FROM source_matches m JOIN seasons s USING (season_id)
WHERE s.league_code = %(league_code)s AND s.label = %(season)s
  AND m.last_run_id = (
      SELECT max(r.run_id) FROM collection_runs r
      WHERE r.season_id = s.season_id
        AND r.source = %(source)s
        AND r.status = 'succeeded')
ORDER BY m.page_position, m.source_match_id;
```

**Why:** The loader keeps the matches that a later run did not find ([decision 18](../../../docs/decisions/0018-loader-records-each-run.md)). The export must show what the source shows now. Only the matches of the latest succeeded run have its `run_id` in `last_run_id`.

**How:**
- The subquery uses `s.season_id` of the outer query. This is a *correlated subquery*: PostgreSQL calculates it for the season of the outer row.
- `run_id` is an identity column, thus a larger `run_id` is a later run. `max(run_id)` is the latest run.
- `status = 'succeeded'` is necessary. Without it, a failed run is the latest run. It has no matches, and the export is empty. A deliberate break proved this: `test_failed_run_does_not_change_the_export` failed.
- `USING (season_id)` is a short form of `ON m.season_id = s.season_id` for a column with the same name in the two tables.
- `%(name)s` placeholders take a dictionary. One value can be used two times in the SQL, for example `%(source)s`.
- A table has no row sequence. Without `ORDER BY`, the sequence can change after an update. `source_match_id` is the second sort key, thus two matches with the same `page_position` always have the same sequence.

## 11. Data from the database is checked again

**What:** The reader makes a `SourceMatch` from each row. Pydantic checks it again.

**Why:** The database constraints have only the simple rules ([decision 16](../../../docs/decisions/0016-database-repeats-sourcematch-rules.md)). A manual change in `psql` can make a row that the constraints accept, but that is not a valid match, for example a shootout after a 2-1 result. Such a row causes a `ValidationError`. It does not go into a file.

**How:** `SourceMatch` is strict, thus it does not change types. The reader changes two values:
- `MatchStatus(status)`: the column is `text`, and a strict model does not accept a `str` for an enum.
- `tuple(raw_documents)`: psycopg gives a PostgreSQL array as a `list`.

The test `test_read_gives_back_the_loaded_matches` loads matches with all the special values (a shootout, a walkover, a postponed match, a kick-off time) and compares the result of the reader with `==`. `SourceMatch` is frozen, thus `==` compares all the fields.

## 12. A CTE and UNION to count the teams

**What:** The coverage SQL counts the different teams of a run:

```sql
WITH run_matches AS (
    SELECT home_team_raw, away_team_raw, status
    FROM source_matches WHERE last_run_id = %(run_id)s
),
teams AS (
    SELECT home_team_raw AS team FROM run_matches
    UNION
    SELECT away_team_raw FROM run_matches
)
SELECT count(*) FROM teams;
```

**Why:** A team plays at home and away. The number of teams *n* gives the expected number of matches, *n × (n − 1)* ([decision 19](../../../docs/decisions/0019-exports-read-from-the-database.md)).

**How:**
- `WITH name AS (...)` is a *common table expression* (CTE): a named query that the next parts use as a table. It makes a long query easier to read.
- `UNION` removes the duplicate rows. `UNION ALL` keeps them. With `UNION ALL`, each team counts once for each match.

## 13. A conditional upsert: `DO UPDATE ... WHERE`

**What:**

```sql
INSERT INTO season_coverage (...) SELECT ...
ON CONFLICT (season_id) DO UPDATE SET status = EXCLUDED.status, ...
WHERE season_coverage.status <> 'verified'
RETURNING expected_matches, status;
```

**Why:** [Decision 7](../../../docs/decisions/0007-testable-definition-of-verified.md): data of one source never replaces a verified season.

**How:**
- The `WHERE` of `DO UPDATE` applies to the row in the table. If it is false, PostgreSQL does not change the row.
- Then `RETURNING` gives **no row**, the same as `DO NOTHING` ([section 2](#2-do-update-or-do-nothing-and-returning)). The loader then reads the coverage with a `SELECT`.
- `fail()` uses `DO NOTHING`: a failed run writes the status `failed` only for a season that has no coverage. Thus a failed run does not remove the result of an earlier run.

## 14. Replace a unit: DELETE, then INSERT, in one transaction

**What:** A run with table rows deletes the stored table of the season and the source, and writes the new rows:

```sql
DELETE FROM source_tables WHERE season_id = %s AND source = %s;
INSERT INTO source_tables (...) VALUES (...);   -- one for each row
```

**Why:** A table is one unit. An upsert of each row (section 1) keeps a row that the new table does not have, and then the stored table is a mix of two tables. For the matches, the loader keeps such rows on purpose ([decision 18](../../../docs/decisions/0018-loader-records-each-run.md)); for a table, a mix is wrong.

**How:** The `DELETE` and the `INSERT` are in the `load()` transaction. Another connection sees the old table or the new table, never no table and never half a table. The `DELETE` has `AND source = %s`: the table of a different source stays. A run without table rows does not `DELETE`: a run that did not find the table must not remove a good table.

## 15. How the tests use the database

- **One database for each test.** The fixture `empty_database` (`tests/conftest.py`) makes a new database with a random name, and removes it after the test (`DROP DATABASE ... WITH (FORCE)`). `pipeline_database` also applies the migrations. Thus a test cannot change the data of a different test or of `football`.
- **A database constraint tested from Python.** `SourceMatch` does not allow a bad match. `model_copy(update={...})` makes a copy without the Pydantic checks, thus the test can give a bad match to the database, and the `CHECK` constraint must stop it.
- **A fake adapter.** The scraper tests give `FootballScraper` an object with the adapter methods, and fixed data. They do not use a browser or the network.
- **A test that proves the data path.** `test_scraper_exports_the_matches_from_the_database` replaces `read_season_matches` with a function that gives a different match than the parser. The output must show the match of the reader. Without this test, an export from the matches in memory gives the same output, and no test fails.
- **Deliberate breaks.** For each important line, the project broke the code on purpose, and one test had to fail. For the loader: the transaction of `load()`, `IS DISTINCT FROM`, the `CASE` of `updated_at`, `BaseException`, and the count of `pages_fetched`. For the reader and the coverage: the export from memory, the `last_run_id` filter, `status = 'succeeded'`, `page_position`, the `WHERE` of the conditional upsert, `DO NOTHING` in `fail()`, and the count of postponed matches.

## 16. A check that only reads, before the work starts

**What:** `pending(conn)` gives the migration files that the database does not have. `main.py` calls it before the menus ([decision 30](../../../docs/decisions/0030-rsssf-in-the-pipeline.md)).

**Why:** The first live run of RSSSF found a database without migration 002. The error (`relation "source_tables" does not exist`) came in each season, after three attempts with waits. A check before the work gives one message with the command that corrects it.

**How:** The check does not change the database: it does not make `schema_migrations` (`migrate()` does). `to_regclass('schema_migrations')` gives NULL for a table that does not exist, without an error. Then the check compares the versions in the table with the files in `migrations/`.
