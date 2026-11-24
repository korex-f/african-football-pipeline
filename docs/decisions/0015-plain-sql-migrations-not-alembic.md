# 15. Plain SQL migrations with a small runner, not Alembic

*Status: accepted (November 2026). [All decisions](README.md)*

- **What:** The schema is in numbered SQL files (`001_initial.sql`). `db/migrate.py` applies them and records them in `schema_migrations`.
- **The debate:**
  1. **Alembic.** This is the standard tool for SQLAlchemy projects. It can make migrations from Python models, and it can undo a migration. But the project does not use SQLAlchemy models. Alembic would add a dependency and a second way to describe the schema.
  2. **Plain SQL with a runner (the decision).** The schema is in SQL, which PostgreSQL reads directly. A reviewer sees the exact SQL that runs. The runner is one file of approximately 240 lines, most of them docstrings and comments. The project author wrote it to practise SQL and transactions.
- **How the runner works:**
  - A file name must have the form `NNN_name.sql`. Two files with the same version are an error.
  - Before it applies a new file, the runner makes sure that each applied file exists and did not change (sha256).
  - The runner applies a file and writes its record in one transaction. If the SQL fails, neither stays, and the runner stops.
  - The connection uses `autocommit=True`. Without it, psycopg puts all the work in one outer transaction. Then each `conn.transaction()` is only a savepoint, and an error in file 002 also removes file 001.
- **Tests:** 19 tests in `tests/integration/test_migrate.py`. The test author wrote them before the runner, as its specification. A test found a bug in `001_initial.sql` (a comment that used an old constraint name).
  For the deliberate break ([decision 13](0013-build-new-code-next-to-old-code.md)), the project removed the transaction. The obvious test (a file that fails after `CREATE TABLE`) still passed: PostgreSQL runs a string with many statements as one implicit transaction. Thus, the test `test_file_and_its_record_are_one_transaction` makes the record fail after a correct file. Only this test fails without the transaction.
- **Trade-offs:**
  - There is no command to undo a migration. To undo a change, add a new migration.
  - The runner does not lock the database. Two runners at the same time can try to apply the same file. The second runner then fails (the tables exist, or the version is already in `schema_migrations`), and its transaction changes nothing. For one local computer, this is sufficient.
