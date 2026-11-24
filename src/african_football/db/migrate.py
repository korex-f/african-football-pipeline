"""
migrate.py: apply the SQL migrations to the pipeline database.

A migration is one SQL file in the migrations/ folder. The name of the file
has the form NNN_name.sql, for example 001_initial.sql. NNN is the version.
The runner applies the files in the sequence of their versions.

The table schema_migrations keeps a record of each applied file: the version,
the file name, the sha256 of the file and the time. The runner applies a file
only one time. Each file and its record are applied in one transaction. If a
file fails, the runner stops, and the database does not change.

Do not change a file after the runner applied it. The runner compares the
sha256 of each applied file with its record, and stops if they are not the
same. To change the schema, add a new file with the next version.

To apply the migrations, run:

    uv run --env-file .env python -m african_football.db.migrate
"""

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

import psycopg

# The folder of the migration files of the pipeline.
MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# The name of a migration file, without ".sql": three digits for the version,
# "_", then a name that starts with a letter (lowercase letters, digits, "_").
FILENAME_PATTERN = re.compile(r"(?P<version>\d{3})_(?P<name>[a-z][a-z0-9_]*)")


@dataclass(frozen=True)
class Migration:
    """One migration file.

    version   the three digits at the start of the name, for example "001".
              It is text, thus the zeros at the start stay.
    name      the file name, for example "001_initial.sql".
    path      the full path of the file.
    checksum  the sha256 of the file, as 64 hexadecimal characters.
    """

    version: str
    name: str
    path: Path
    checksum: str


class MigrationError(Exception):
    """A migration file or the migration history is not correct.

    For example: a file has a bad name, two files have the same version,
    the SQL of a file fails, or an applied file was changed or removed.
    """


def discover(folder: Path = MIGRATIONS_DIR) -> list[Migration]:
    """Find the migration files in a folder.

    Only the .sql files are migrations. The function ignores other files,
    for example a README.

    Returns the migrations, sorted by version.
    Raises MigrationError if the folder does not exist, if a file name does
    not have the form NNN_name.sql, or if two files have the same version.
    """
    # Without this check, glob() gives no files for a wrong path, and the
    # runner then applies nothing without an error.
    if not folder.is_dir():
        raise MigrationError(f"Migration folder {folder} does not exist")

    migrations: list[Migration] = []

    # Sort the files by name. Thus the error for a duplicate version always
    # names the same file first. The migrations are sorted again at the end.
    sql_files = sorted(folder.glob("*.sql"))
    seen_versions: dict[str, str] = {}

    for sql_file in sql_files:
        # Check the name before the other steps use it.
        match = FILENAME_PATTERN.fullmatch(sql_file.stem)
        if not match:
            raise MigrationError(
                f"SQL file name {sql_file.name} does not match required name format 'NNN_name.sql'"
            )

        # seen_versions keeps the name of the first file with each version, for
        # the error message.
        version = match.group("version")
        if version in seen_versions:
            raise MigrationError(
                f"Duplicate migration version '{version}' (conflicts with '{seen_versions[version]}')"
            )

        seen_versions[version] = sql_file.name

        migrations.append(
            Migration(
                version=version,
                name=sql_file.name,
                path=sql_file,
                checksum=hashlib.sha256(sql_file.read_bytes()).hexdigest(),
            )
        )

    # Sort only after all the names are correct. All versions have three
    # digits, thus the text sequence is also the number sequence.
    migrations.sort(key=lambda m: m.version)
    return migrations


def migrate(conn: psycopg.Connection, folder: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply the new migrations in a folder to a database.

    Use a connection with autocommit=True. Then each migration has its own
    transaction.

    The steps are:
    1. Make the table schema_migrations, if it does not exist.
    2. Read the versions and the checksums that the table records.
    3. Make sure that each applied migration has its file, and that the
       file did not change. Do this before the runner applies new files.
    4. Apply each new migration in the sequence of the versions. Run the
       file and write its record in one transaction.

    Returns the versions that this call applied. If all migrations were
    applied before, the list is empty.
    Raises MigrationError if an applied file is missing or changed, or if
    the SQL of a file fails. A failed file changes nothing, and the runner
    stops before the next file.
    """
    # Step 0: check all the file names before the runner changes the database.
    migrations = discover(folder)

    # Step 1. "IF NOT EXISTS" is correct here, but not in a migration file.
    # The runner makes this table on each run, and after the first run the
    # table always exists.
    with conn.transaction():
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version text PRIMARY KEY,
                name text NOT NULL,
                checksum text NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )

    # Step 2. Each row is a (version, checksum) tuple. dict() makes a lookup
    # from the version to the checksum, for example {"001": "b016..."}.
    rows = conn.execute("SELECT version, checksum FROM schema_migrations").fetchall()
    applied = dict(rows)

    # A lookup from the version to the migration file, for step 3.
    migrations_by_version = {m.version: m for m in migrations}

    # Step 3. An applied file is history: the databases that applied it must
    # agree with it. Do all the checks before the runner applies a new file.
    for version, applied_checksum in applied.items():
        if version not in migrations_by_version:
            raise MigrationError(
                f"Version {version} was applied, but its file is missing"
            )

        migration = migrations_by_version[version]
        if migration.checksum != applied_checksum:
            raise MigrationError(f"{migration.name} was changed after it was applied")

    # Step 4. The list from discover() is sorted by version.
    newly_applied: list[str] = []
    for migration in migrations:
        if migration.version in applied:
            continue

        # The file and its record are in one transaction. If the file or the
        # record fails, neither stays. Thus the file is not applied a second
        # time without its record. The connection must have autocommit=True:
        # without it, this block is only a savepoint, and an error later in
        # the run also removes the migrations before it.
        try:
            with conn.transaction():
                # Use bytes: psycopg accepts a str only if it is a constant
                # (LiteralString). The text of a file is not a constant.
                conn.execute(migration.path.read_bytes())
                conn.execute(
                    """
                    INSERT INTO schema_migrations (version, name, checksum)
                    VALUES (%s, %s, %s)
                    """,
                    (migration.version, migration.name, migration.checksum),
                )
        # "from err" keeps the Postgres error as the cause of the
        # MigrationError. diag.message_primary is the short Postgres message.
        except psycopg.Error as err:
            raise MigrationError(
                f"Failed to apply migration ({err.diag.message_primary or err}), {migration.name}"
            ) from err

        newly_applied.append(migration.version)

    return newly_applied


def main() -> None:
    """Apply the migrations to the database in DATABASE_URL.

    Writes the applied versions, or a message that the database is up to
    date. Stops with an error message and exit code 1 if DATABASE_URL is not
    set, if the runner cannot connect to the database, or if a migration
    fails.
    """
    # SystemExit with a text writes the text to stderr and stops the program
    # with exit code 1, without a traceback.
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("Error: DATABASE_URL environment variable is not set.")

    # autocommit=True gives each migration its own real transaction. See the
    # comment in migrate().
    try:
        with psycopg.connect(database_url, autocommit=True) as conn:
            newly_applied = migrate(conn, MIGRATIONS_DIR)
    except MigrationError as err:
        raise SystemExit(f"Migration error: {err}") from err
    except psycopg.OperationalError as err:
        raise SystemExit(f"Database connection failed: {err}") from err

    if newly_applied:
        print(f"Applied {len(newly_applied)} migration(s):")
        for version in newly_applied:
            print(f"    - {version}")
    else:
        print("Database is already up to date.")


if __name__ == "__main__":
    main()
