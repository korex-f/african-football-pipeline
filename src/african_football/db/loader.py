"""
loader.py: write one collection run to the pipeline database.

A RunRecorder records one run of one source for one season:

    1. start():  writes the league and the season, and a collection_runs row
                 with the status 'running'. This is committed at once. Thus a
                 run that stops (for example, a crash) stays in the table as
                 'running', with no finished_at.
    2. load():   writes the stored pages (raw_documents) and the matches
                 (source_matches), and changes the run to 'succeeded'. This is
                 one transaction: the database never has a part of a run.
    3. fail():   changes the run to 'failed' and records the error.

load() also writes season_coverage from the matches of the run (decision 7):
expected = n * (n - 1) for n teams, found = the played and awarded matches.

A new run of the same season updates the matches. It does not add them again
(the key is source + source_match_id). A match keeps its first_seen_at.
updated_at changes only if the data of the match changed. A match that the
source does not show again stays in the table. load() counts these matches.

The connection must use autocommit=True. Then start() and fail() are committed
at once, and load() has its own transaction.

Typical usage:
    with psycopg.connect(url, autocommit=True) as conn:
        recorder = RunRecorder.start(conn, league, season, "soccerway", "1.1.0")
        try:
            summary = recorder.load(documents, matches)
        except Exception as error:
            recorder.fail(error)
            raise
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import LiteralString

import psycopg

from african_football.models.league_model import LeagueConfig
from african_football.models.season_model import SeasonRecord
from african_football.models.source_match import SourceMatch
from african_football.models.source_table import SourceTableRow
from african_football.sources.base import RawDocument

# The data columns of source_matches, in the sequence of the INSERT. The
# loader compares these columns to find a changed match. last_run_id and the
# times are not data, thus they are not in this list.
#
# The type LiteralString tells the type checker that the SQL text comes only
# from constants in this file, not from data. psycopg accepts only such text.
_MATCH_COLUMNS: tuple[LiteralString, ...] = (
    "season_id",
    "source",
    "source_match_id",
    "page_position",
    "source_url",
    "stage",
    "round_name",
    "round_number",
    "match_date",
    "kickoff_local",
    "timezone",
    "home_team_raw",
    "away_team_raw",
    "home_goals",
    "away_goals",
    "ht_home",
    "ht_away",
    "pen_home",
    "pen_away",
    "status",
    "raw_documents",
)

_COLUMN_LIST = ", ".join(_MATCH_COLUMNS)
_PLACEHOLDERS = ", ".join("%s" for _ in _MATCH_COLUMNS)
_UPDATE_LIST = ", ".join(f"{c} = EXCLUDED.{c}" for c in _MATCH_COLUMNS)
_OLD_ROW = ", ".join(f"source_matches.{c}" for c in _MATCH_COLUMNS)
_NEW_ROW = ", ".join(f"EXCLUDED.{c}" for c in _MATCH_COLUMNS)

# Insert a match, or update the match that has the same source and
# source_match_id.
# - updated_at changes only if a data column changed. "IS DISTINCT FROM"
#   compares the two rows, and it handles NULL correctly (NULL = NULL is not
#   true in SQL, but NULL IS NOT DISTINCT FROM NULL is true).
# - xmax = 0 only for a new row. This is a PostgreSQL detail: xmax is the
#   transaction that changed the row last, and it is 0 for a new row.
# - In one transaction, now() always gives the start time of the
#   transaction. Thus "updated_at = now()" is true for a row that this
#   transaction wrote.
_UPSERT_MATCH = f"""
    INSERT INTO source_matches ({_COLUMN_LIST}, last_run_id)
    VALUES ({_PLACEHOLDERS}, %s)
    ON CONFLICT (source, source_match_id) DO UPDATE SET
        {_UPDATE_LIST},
        last_run_id = EXCLUDED.last_run_id,
        updated_at = CASE
            WHEN ({_OLD_ROW}) IS DISTINCT FROM ({_NEW_ROW}) THEN now()
            ELSE source_matches.updated_at
        END
    RETURNING xmax = 0 AS inserted, updated_at = now() AS changed
"""


# Write the coverage of the season from the matches of this run (decision 7).
# - n is the number of different teams in the matches of the run. For a double
#   round-robin league, the expected number of matches is n * (n - 1).
# - found counts only the played and awarded matches. A postponed or
#   cancelled match is not a result.
# - Data of one source never replaces a 'verified' season. The WHERE of
#   DO UPDATE then writes nothing.
_UPSERT_COVERAGE = """
    WITH run_matches AS (
        SELECT home_team_raw, away_team_raw, status
        FROM source_matches WHERE last_run_id = %(run_id)s
    ),
    teams AS (
        SELECT home_team_raw AS team FROM run_matches
        UNION
        SELECT away_team_raw FROM run_matches
    ),
    counts AS (
        SELECT
            (SELECT count(*) FROM teams) AS n,
            (SELECT count(*) FROM run_matches
             WHERE status IN ('played', 'awarded')) AS found
    )
    INSERT INTO season_coverage
        (season_id, expected_matches, found_matches, status, last_run_id)
    SELECT
        %(season_id)s,
        n * (n - 1),
        found,
        CASE
            WHEN found > 0 AND found >= n * (n - 1) THEN 'complete_single_source'
            ELSE 'incomplete'
        END,
        %(run_id)s
    FROM counts
    ON CONFLICT (season_id) DO UPDATE SET
        expected_matches = EXCLUDED.expected_matches,
        found_matches = EXCLUDED.found_matches,
        status = EXCLUDED.status,
        last_run_id = EXCLUDED.last_run_id,
        updated_at = now()
    WHERE season_coverage.status <> 'verified'
    RETURNING expected_matches, status
"""


@dataclass(frozen=True)
class LoadSummary:
    """
    The result of RunRecorder.load().

    pages_fetched:      the pages that the adapter got from the source in this
                        run. The other pages came from the raw store.
    documents_new:      the pages that the table raw_documents did not have
                        (a new URL, or new content at a known URL).
    matches_parsed:     the matches that the run wrote.
    matches_new:        the matches that the table did not have.
    matches_changed:    the known matches with different data.
    matches_not_seen:   the matches of the season and source in the table that
                        this run did not write. The source does not show them
                        now. They stay in the table.
    expected_matches:   n * (n - 1) for the n teams of this run.
    coverage_status:    the status in season_coverage after this run.
    table_rows:         the final table rows that the run wrote. 0: the run
                        had no table, and a stored table did not change.
    """

    pages_fetched: int
    documents_new: int
    matches_parsed: int
    matches_new: int
    matches_changed: int
    matches_not_seen: int
    expected_matches: int
    coverage_status: str
    table_rows: int = 0


# The columns of source_tables that come from a SourceTableRow, in the
# sequence of the INSERT.
_TABLE_COLUMNS: tuple[LiteralString, ...] = (
    "stage",
    "row_number",
    "position",
    "team_raw",
    "played",
    "won",
    "drawn",
    "lost",
    "goals_for",
    "goals_against",
    "points",
    "note",
)
_INSERT_TABLE_ROW = f"""
    INSERT INTO source_tables (season_id, run_id, source, {", ".join(_TABLE_COLUMNS)})
    VALUES (%s, %s, %s, {", ".join("%s" for _ in _TABLE_COLUMNS)})
"""


class RunRecorder:
    """
    Record one collection run in the pipeline database.

    Make a RunRecorder with RunRecorder.start(), not with RunRecorder().
    """

    def __init__(
        self,
        conn: psycopg.Connection,
        run_id: int,
        season_id: int,
        source: str,
        started_at: datetime,
    ) -> None:
        self.conn = conn
        self.run_id = run_id
        self.season_id = season_id
        self.source = source
        self.started_at = started_at

    @classmethod
    def start(
        cls,
        conn: psycopg.Connection,
        league: LeagueConfig,
        season: SeasonRecord,
        source: str,
        pipeline_version: str,
    ) -> "RunRecorder":
        """Write the league and the season, and start a run.

        The league and the season are updated if they exist. Thus a change in
        leagues.yaml, for example a new league name, goes into the table.
        """
        with conn.transaction():
            conn.execute(
                """
                INSERT INTO leagues (league_code, name, country, timezone)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (league_code) DO UPDATE SET
                    name = EXCLUDED.name,
                    country = EXCLUDED.country,
                    timezone = EXCLUDED.timezone
                """,
                (league.code, league.name, league.country, league.timezone),
            )
            # DO UPDATE, not DO NOTHING: with DO NOTHING, RETURNING gives no
            # row for a season that exists, and the loader needs its ID.
            season_row = conn.execute(
                """
                INSERT INTO seasons (league_code, label, start_year, end_year)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (league_code, label) DO UPDATE SET
                    start_year = EXCLUDED.start_year,
                    end_year = EXCLUDED.end_year
                RETURNING season_id
                """,
                (league.code, season.season, season.start_year, season.end_year),
            ).fetchone()
            assert season_row is not None
            season_id: int = season_row[0]

            run_row = conn.execute(
                """
                INSERT INTO collection_runs (season_id, source, pipeline_version)
                VALUES (%s, %s, %s)
                RETURNING run_id, started_at
                """,
                (season_id, source, pipeline_version),
            ).fetchone()
            assert run_row is not None

        return cls(conn, run_row[0], season_id, source, run_row[1])

    def load(
        self,
        documents: list[RawDocument],
        matches: list[SourceMatch],
        tables: Sequence[SourceTableRow] = (),
    ) -> LoadSummary:
        """Write the pages, the matches and the tables, and mark the run
        'succeeded'.

        Give the matches in the sequence of the source page. The position of
        each match in the list goes into page_position. The exports use it to
        keep the page sequence.

        tables: the rows of the final tables of the season (decision 23). If
        there are rows, they replace the stored table of the season and the
        source: a table is one unit, and a newer page supersedes it. If there
        are no rows, the stored table does not change: a run that did not
        find the table must not remove it.

        This is one transaction. If a write fails, nothing of this method
        stays, and the run stays 'running'. Call fail() then.
        """
        with self.conn.transaction():
            documents_new = 0
            for doc in documents:
                cur = self.conn.execute(
                    """
                    INSERT INTO raw_documents (season_id, first_run_id, source,
                        url, path, timezone, sha256, fetched_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (url, sha256) DO NOTHING
                    """,
                    (
                        self.season_id,
                        self.run_id,
                        doc.source,
                        doc.url,
                        doc.path,
                        doc.timezone,
                        doc.sha256,
                        doc.fetched_at,
                    ),
                )
                # rowcount is 0 when DO NOTHING skipped the row.
                documents_new += cur.rowcount

            matches_new = 0
            matches_changed = 0
            for position, match in enumerate(matches):
                row = self.conn.execute(
                    _UPSERT_MATCH,
                    (*self._match_values(match, position), self.run_id),
                ).fetchone()
                assert row is not None
                inserted, changed = row
                if inserted:
                    matches_new += 1
                elif changed:
                    matches_changed += 1

            not_seen_row = self.conn.execute(
                """
                SELECT count(*) FROM source_matches
                WHERE season_id = %s AND source = %s AND last_run_id <> %s
                """,
                (self.season_id, self.source, self.run_id),
            ).fetchone()
            assert not_seen_row is not None

            coverage_row = self.conn.execute(
                _UPSERT_COVERAGE,
                {"season_id": self.season_id, "run_id": self.run_id},
            ).fetchone()
            if coverage_row is None:
                # The season is 'verified'. The WHERE of DO UPDATE kept it.
                coverage_row = self.conn.execute(
                    "SELECT expected_matches, status FROM season_coverage"
                    " WHERE season_id = %s",
                    (self.season_id,),
                ).fetchone()
                assert coverage_row is not None

            if tables:
                self.conn.execute(
                    "DELETE FROM source_tables WHERE season_id = %s AND source = %s",
                    (self.season_id, self.source),
                )
                for table_row in tables:
                    self.conn.execute(
                        _INSERT_TABLE_ROW,
                        (
                            self.season_id,
                            self.run_id,
                            self.source,
                            *(getattr(table_row, c) for c in _TABLE_COLUMNS),
                        ),
                    )

            pages_fetched = sum(
                1 for doc in documents if doc.fetched_at >= self.started_at
            )

            # clock_timestamp() is the time now. now() would give the start
            # time of this transaction.
            self.conn.execute(
                """
                UPDATE collection_runs SET
                    status = 'succeeded',
                    finished_at = clock_timestamp(),
                    pages_fetched = %s,
                    matches_parsed = %s
                WHERE run_id = %s
                """,
                (pages_fetched, len(matches), self.run_id),
            )

        return LoadSummary(
            pages_fetched=pages_fetched,
            documents_new=documents_new,
            matches_parsed=len(matches),
            matches_new=matches_new,
            matches_changed=matches_changed,
            matches_not_seen=not_seen_row[0],
            expected_matches=coverage_row[0],
            coverage_status=coverage_row[1],
            table_rows=len(tables),
        )

    def fail(self, error: BaseException) -> None:
        """Mark the run 'failed', and record the error.

        If the season has no coverage yet, its coverage becomes 'failed'.
        A season that has coverage keeps it: a failed run does not remove
        the result of an earlier run.
        """
        message = f"{type(error).__name__}: {error}"
        with self.conn.transaction():
            self.conn.execute(
                """
                UPDATE collection_runs SET
                    status = 'failed',
                    finished_at = clock_timestamp(),
                    error = %s
                WHERE run_id = %s
                """,
                (message, self.run_id),
            )
            self.conn.execute(
                """
                INSERT INTO season_coverage
                    (season_id, found_matches, status, last_run_id)
                VALUES (%s, 0, 'failed', %s)
                ON CONFLICT (season_id) DO NOTHING
                """,
                (self.season_id, self.run_id),
            )

    def _match_values(self, match: SourceMatch, position: int) -> tuple:
        """Give the values of one match, in the sequence of _MATCH_COLUMNS."""
        return (
            self.season_id,
            match.source,
            match.source_match_id,
            position,
            match.source_url,
            match.stage,
            match.round_name,
            match.round_number,
            match.match_date,
            match.kickoff_local,
            match.timezone,
            match.home_team_raw,
            match.away_team_raw,
            match.home_goals,
            match.away_goals,
            match.ht_home,
            match.ht_away,
            match.pen_home,
            match.pen_away,
            match.status.value,
            # psycopg changes a list into a PostgreSQL array. A tuple is not
            # changed into an array.
            list(match.raw_documents),
        )
