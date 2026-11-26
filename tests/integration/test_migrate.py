"""
Tests for the migration runner in db/migrate.py.

The tests for discover() do not use a database. The other tests need
Postgres. They get a new empty database from the empty_database fixture
(tests/conftest.py), and they are skipped when DATABASE_URL is not set.

Most tests use small migration files in a temporary folder. Thus each test
controls the migrations exactly. One test applies the real migrations in
src/african_football/db/migrations/.
"""

import hashlib
from pathlib import Path

import psycopg
import pytest

from african_football.db.migrate import (
    MIGRATIONS_DIR,
    MigrationError,
    discover,
    main,
    migrate,
    pending,
)

TABLES_OF_001 = {
    "leagues",
    "seasons",
    "collection_runs",
    "raw_documents",
    "source_matches",
    "season_coverage",
}


def _write(folder: Path, name: str, text: str) -> Path:
    path = folder / name
    path.write_text(text)
    return path


def _tables(url: str) -> set[str]:
    """Give the names of the tables in the public schema."""
    with psycopg.connect(url) as conn:
        rows = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall()
    return {row[0] for row in rows}


def _recorded(url: str) -> list[str]:
    """Give the versions in schema_migrations, in sequence."""
    with psycopg.connect(url) as conn:
        rows = conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
    return [row[0] for row in rows]


def _migrate(url: str, folder: Path) -> list[str]:
    with psycopg.connect(url, autocommit=True) as conn:
        return migrate(conn, folder)


# ---------------------------------------------------------------------------
# discover (no database)
# ---------------------------------------------------------------------------


def test_discover_sorts_by_version(tmp_path):
    _write(tmp_path, "002_second.sql", "SELECT 2;")
    _write(tmp_path, "001_first.sql", "SELECT 1;")
    _write(tmp_path, "README.md", "Not a migration.")

    found = discover(tmp_path)

    assert [m.version for m in found] == ["001", "002"]
    assert [m.name for m in found] == ["001_first.sql", "002_second.sql"]
    assert found[0].path == tmp_path / "001_first.sql"


def test_discover_gives_the_sha256_of_the_file(tmp_path):
    path = _write(tmp_path, "001_first.sql", "SELECT 1;\n")

    (migration,) = discover(tmp_path)

    assert migration.checksum == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("name", ["1_first.sql", "first.sql", "001-first.sql"])
def test_discover_refuses_a_bad_name(tmp_path, name):
    _write(tmp_path, name, "SELECT 1;")
    with pytest.raises(MigrationError, match=name):
        discover(tmp_path)


def test_discover_refuses_two_files_with_one_version(tmp_path):
    _write(tmp_path, "001_first.sql", "SELECT 1;")
    _write(tmp_path, "001_other.sql", "SELECT 1;")
    with pytest.raises(MigrationError, match="001"):
        discover(tmp_path)


def test_real_migrations_folder():
    found = discover(MIGRATIONS_DIR)
    assert found[0].name == "001_initial.sql"


# ---------------------------------------------------------------------------
# migrate (database)
# ---------------------------------------------------------------------------


@pytest.mark.db
def test_real_migrations_make_the_schema(empty_database):
    applied = _migrate(empty_database, MIGRATIONS_DIR)

    assert applied[:2] == ["001", "002"]
    assert TABLES_OF_001 | {"source_tables", "schema_migrations"} <= _tables(
        empty_database
    )


@pytest.mark.db
def test_migrate_records_each_file(empty_database, tmp_path):
    first = _write(tmp_path, "001_first.sql", "CREATE TABLE a (x int);")

    _migrate(empty_database, tmp_path)

    with psycopg.connect(empty_database) as conn:
        row = conn.execute(
            "SELECT version, name, checksum, applied_at FROM schema_migrations"
        ).fetchone()
    assert row is not None
    version, name, checksum, applied_at = row
    assert (version, name) == ("001", "001_first.sql")
    assert checksum == hashlib.sha256(first.read_bytes()).hexdigest()
    assert applied_at.tzinfo is not None


@pytest.mark.db
def test_second_run_does_nothing(empty_database, tmp_path):
    _write(tmp_path, "001_first.sql", "CREATE TABLE a (x int);")

    assert _migrate(empty_database, tmp_path) == ["001"]
    # A second CREATE TABLE a would fail. Thus this also proves that the
    # runner does not apply 001 again.
    assert _migrate(empty_database, tmp_path) == []
    assert _recorded(empty_database) == ["001"]


@pytest.mark.db
def test_only_new_files_are_applied(empty_database, tmp_path):
    _write(tmp_path, "001_first.sql", "CREATE TABLE a (x int);")
    _migrate(empty_database, tmp_path)

    _write(tmp_path, "002_second.sql", "CREATE TABLE b (y int);")

    assert _migrate(empty_database, tmp_path) == ["002"]
    assert {"a", "b"} <= _tables(empty_database)
    assert _recorded(empty_database) == ["001", "002"]


@pytest.mark.db
def test_file_with_many_statements(empty_database, tmp_path):
    _write(
        tmp_path,
        "001_first.sql",
        "-- A comment.\nCREATE TABLE a (x int);\nCREATE TABLE b (y int);\n",
    )

    _migrate(empty_database, tmp_path)

    assert {"a", "b"} <= _tables(empty_database)


@pytest.mark.db
def test_failed_file_is_rolled_back_and_the_run_stops(empty_database, tmp_path):
    _write(tmp_path, "001_first.sql", "CREATE TABLE a (x int);")
    # 002 makes table c, then fails. The transaction must remove table c.
    _write(tmp_path, "002_bad.sql", "CREATE TABLE c (x int);\nSELECT 1 / 0;")
    _write(tmp_path, "003_third.sql", "CREATE TABLE d (x int);")

    with pytest.raises(MigrationError, match="002_bad.sql"):
        _migrate(empty_database, tmp_path)

    tables = _tables(empty_database)
    assert "a" in tables
    assert "c" not in tables
    assert "d" not in tables
    assert _recorded(empty_database) == ["001"]


@pytest.mark.db
def test_file_and_its_record_are_one_transaction(empty_database, tmp_path):
    # The SQL of this file is correct, but it also writes the record of
    # version 001. Thus the record that the runner writes after the file
    # fails (the version is the primary key). Table a must then be removed
    # too: a file is applied together with its record, or not at all.
    _write(
        tmp_path,
        "001_first.sql",
        "CREATE TABLE a (x int);\n"
        "INSERT INTO schema_migrations (version, name, checksum)"
        " VALUES ('001', 'x', 'x');",
    )

    with pytest.raises(MigrationError, match="001_first.sql"):
        _migrate(empty_database, tmp_path)

    assert "a" not in _tables(empty_database)


@pytest.mark.db
def test_error_keeps_the_database_error_as_its_cause(empty_database, tmp_path):
    _write(tmp_path, "001_bad.sql", "SELECT 1 / 0;")

    with pytest.raises(MigrationError) as caught:
        _migrate(empty_database, tmp_path)

    assert isinstance(caught.value.__cause__, psycopg.Error)


@pytest.mark.db
def test_changed_applied_file_is_an_error(empty_database, tmp_path):
    _write(tmp_path, "001_first.sql", "CREATE TABLE a (x int);")
    _migrate(empty_database, tmp_path)

    # Someone edits a file that the database already has.
    _write(tmp_path, "001_first.sql", "CREATE TABLE a (x bigint);")
    _write(tmp_path, "002_second.sql", "CREATE TABLE b (y int);")

    with pytest.raises(MigrationError, match="001_first.sql"):
        _migrate(empty_database, tmp_path)
    # The runner stops before it applies new files.
    assert _recorded(empty_database) == ["001"]


@pytest.mark.db
def test_applied_file_that_is_missing_is_an_error(empty_database, tmp_path):
    first = _write(tmp_path, "001_first.sql", "CREATE TABLE a (x int);")
    _migrate(empty_database, tmp_path)

    first.unlink()

    with pytest.raises(MigrationError, match="001"):
        _migrate(empty_database, tmp_path)


# ---------------------------------------------------------------------------
# main (the command line)
# ---------------------------------------------------------------------------


@pytest.mark.db
def test_main_uses_database_url(empty_database, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", empty_database)

    main()

    assert TABLES_OF_001 <= _tables(empty_database)


def test_main_without_database_url_stops(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(SystemExit, match="DATABASE_URL"):
        main()


# ---------------------------------------------------------------------------
# pending (roadmap step 4, part 4)
# ---------------------------------------------------------------------------


def _pending(url: str, folder: Path) -> list[str]:
    with psycopg.connect(url) as conn:
        return pending(conn, folder)


def test_pending_on_a_database_without_migrations(empty_database, tmp_path):
    _write(tmp_path, "001_first.sql", "CREATE TABLE a (id int);")
    _write(tmp_path, "002_second.sql", "CREATE TABLE b (id int);")
    assert _pending(empty_database, tmp_path) == ["001_first.sql", "002_second.sql"]
    # pending() only reads: it does not make schema_migrations.
    assert "schema_migrations" not in _tables(empty_database)


def test_pending_gives_only_the_new_files(empty_database, tmp_path):
    # The database of the project had 001, and not 002 (November 2026).
    _write(tmp_path, "001_first.sql", "CREATE TABLE a (id int);")
    _migrate(empty_database, tmp_path)
    _write(tmp_path, "002_second.sql", "CREATE TABLE b (id int);")
    assert _pending(empty_database, tmp_path) == ["002_second.sql"]
    _migrate(empty_database, tmp_path)
    assert _pending(empty_database, tmp_path) == []
