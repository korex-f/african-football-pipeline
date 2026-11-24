# 16. The database repeats the simple rules of SourceMatch

*Status: accepted (November 2026). [All decisions](README.md)*

- **What:** `001_initial.sql` has six tables: `leagues`, `seasons`, `collection_runs`, `raw_documents`, `source_matches` and `season_coverage`. The constraints repeat the simple rules of `SourceMatch`: goals are not negative, the two values of a score are both present or both missing, the home team and the away team are different, and the status is one of the known values.
- **Why:** Pydantic checks only the data that goes through the Python code. The database checks the data from all writers: a manual fix in `psql`, a future RSSSF loader, or a bug. This is *defence in depth*. The project tested each constraint with an insert of bad data.
- **Schema rules:**
  - Primary keys are `bigint GENERATED ALWAYS AS IDENTITY`. A program cannot write its own ID by mistake. `bigint` costs 4 bytes more than `int`, but a later change of a key type changes all the foreign keys.
  - Times are `timestamptz`, which records an exact moment. `timestamp` has no timezone.
  - The allowed values are `CHECK (... IN (...))`, not an `ENUM` type. A `CHECK` is easier to change in a later migration.
  - A run is `running` only when `finished_at` is empty: `CHECK ((status = 'running') = (finished_at IS NULL))`. The two sides of `=` are true or false, thus the rule applies in the two directions.
  - `source_matches.page_position` records the sequence of the match on the results page. A table has no row sequence, but the legacy export must keep the page sequence. The column is not unique: during a new scrape, two matches can change positions in one transaction.
- **Not repeated:** the football rules, for example "a shootout needs a draw". In SQL, these rules are long and difficult to read. They stay in `SourceMatch` only.
- **Trade-offs:** some rules are in two locations. A change of a rule must change both.
