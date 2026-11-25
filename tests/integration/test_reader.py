"""
Tests for db/reader.py, and for the season coverage that db/loader.py writes.

All tests need Postgres (the pipeline_database fixture in tests/conftest.py).
"""

from datetime import date, time
from typing import Any, LiteralString

import psycopg
import pytest

from african_football.db.loader import RunRecorder
from african_football.db.reader import read_season_matches, read_season_tables
from african_football.models.league_model import LeagueConfig
from african_football.models.season_model import SeasonRecord, SeasonStatus
from african_football.models.source_match import MatchStatus, SourceMatch
from african_football.models.source_table import SourceTableRow

pytestmark = pytest.mark.db

SEASON = SeasonRecord(
    season="2023/2024",
    start_year=2023,
    end_year=2024,
    status=SeasonStatus.COMPLETED,
    url="https://example.com/results/",
)


def _match(match_id: str, home: str = "", away: str = "", **changes: Any):
    """Make a valid played match. Use `changes` to replace fields."""
    fields: dict[str, Any] = dict(
        source="soccerway",
        source_match_id=match_id,
        league_code="gh_pl",
        season="2023/2024",
        timezone="Africa/Accra",
        home_team_raw=home or f"Home {match_id}",
        away_team_raw=away or f"Away {match_id}",
        home_goals=1,
        away_goals=0,
        status=MatchStatus.PLAYED,
    )
    fields.update(changes)
    return SourceMatch(**fields)


def _round_robin(teams: list[str]) -> list[SourceMatch]:
    """All the matches of a double round-robin: n * (n - 1) matches."""
    return [
        _match(f"{home}-{away}", home, away)
        for home in teams
        for away in teams
        if home != away
    ]


def _start(conn: psycopg.Connection, league: LeagueConfig) -> RunRecorder:
    return RunRecorder.start(conn, league, SEASON, "soccerway", "1.1.0")


def _read(conn: psycopg.Connection) -> list[SourceMatch]:
    return read_season_matches(conn, "gh_pl", "2023/2024", "soccerway")


def _coverage(conn: psycopg.Connection) -> tuple:
    query: LiteralString = (
        "SELECT expected_matches, found_matches, status FROM season_coverage"
    )
    row = conn.execute(query).fetchone()
    assert row is not None
    return row


@pytest.fixture
def conn(pipeline_database: str):
    with psycopg.connect(pipeline_database, autocommit=True) as connection:
        yield connection


# ---------------------------------------------------------------------------
# read_season_matches
# ---------------------------------------------------------------------------


def test_read_gives_back_the_loaded_matches(conn, ghana_pl):
    # Each column must come back with the same value and type. SourceMatch
    # is frozen, thus == compares all the fields.
    matches = [
        _match(
            "full",
            source_url="https://example.com/match/?mid=full",
            raw_documents=("a" * 64, "b" * 64),
            stage="Premier League",
            round_name="Round 1",
            round_number=1,
            match_date=date(2023, 9, 15),
            kickoff_local=time(15, 30),
            ht_home=1,
            ht_away=0,
        ),
        _match(
            "shootout",
            home_goals=0,
            away_goals=0,
            pen_home=4,
            pen_away=3,
            round_name="Final",
        ),
        _match(
            "walkover", status=MatchStatus.AWARDED, home_goals=None, away_goals=None
        ),
        _match(
            "postponed", status=MatchStatus.POSTPONED, home_goals=None, away_goals=None
        ),
    ]
    _start(conn, ghana_pl).load([], matches)

    assert _read(conn) == matches


def test_read_keeps_the_page_sequence(conn, ghana_pl):
    _start(conn, ghana_pl).load([], [_match("a"), _match("b"), _match("c")])
    # The second scrape shows the matches in a different sequence.
    _start(conn, ghana_pl).load([], [_match("c"), _match("a"), _match("b")])

    assert [m.source_match_id for m in _read(conn)] == ["c", "a", "b"]


def test_read_gives_only_the_matches_of_the_latest_run(conn, ghana_pl):
    _start(conn, ghana_pl).load([], [_match("a"), _match("gone")])
    _start(conn, ghana_pl).load([], [_match("a")])

    assert [m.source_match_id for m in _read(conn)] == ["a"]
    # The match that the source does not show now stays in the table.
    assert conn.execute("SELECT count(*) FROM source_matches").fetchone() == (2,)


def test_failed_run_does_not_change_the_export(conn, ghana_pl):
    _start(conn, ghana_pl).load([], [_match("a"), _match("b")])
    _start(conn, ghana_pl).fail(TimeoutError("page did not load"))

    assert [m.source_match_id for m in _read(conn)] == ["a", "b"]


def test_read_without_a_succeeded_run(conn, ghana_pl):
    _start(conn, ghana_pl)
    assert _read(conn) == []


def test_read_gives_only_the_requested_season(conn, ghana_pl):
    other = SeasonRecord("2022/2023", 2022, 2023, SeasonStatus.COMPLETED, url="x")
    RunRecorder.start(conn, ghana_pl, other, "soccerway", "1.1.0").load(
        [], [_match("old", season="2022/2023")]
    )
    _start(conn, ghana_pl).load([], [_match("new")])

    assert [m.source_match_id for m in _read(conn)] == ["new"]


# ---------------------------------------------------------------------------
# season_coverage
# ---------------------------------------------------------------------------


def test_coverage_complete_for_a_full_round_robin(conn, ghana_pl):
    # 3 teams: 3 * 2 = 6 matches.
    summary = _start(conn, ghana_pl).load([], _round_robin(["A", "B", "C"]))

    assert _coverage(conn) == (6, 6, "complete_single_source")
    assert (summary.expected_matches, summary.coverage_status) == (
        6,
        "complete_single_source",
    )


def test_coverage_incomplete_when_matches_are_missing(conn, ghana_pl):
    _start(conn, ghana_pl).load([], _round_robin(["A", "B", "C"])[:5])

    assert _coverage(conn) == (6, 5, "incomplete")


def test_coverage_does_not_count_a_postponed_match(conn, ghana_pl):
    matches = _round_robin(["A", "B", "C"])
    matches[0] = matches[0].model_copy(
        update={
            "status": MatchStatus.POSTPONED,
            "home_goals": None,
            "away_goals": None,
        }
    )
    _start(conn, ghana_pl).load([], matches)

    assert _coverage(conn) == (6, 5, "incomplete")


def test_coverage_of_a_run_without_matches(conn, ghana_pl):
    _start(conn, ghana_pl).load([], [])

    assert _coverage(conn) == (0, 0, "incomplete")


def test_failed_first_run_gives_failed_coverage(conn, ghana_pl):
    _start(conn, ghana_pl).fail(TimeoutError("page did not load"))

    assert _coverage(conn) == (None, 0, "failed")


def test_failed_run_keeps_the_coverage_of_an_earlier_run(conn, ghana_pl):
    _start(conn, ghana_pl).load([], _round_robin(["A", "B", "C"]))
    _start(conn, ghana_pl).fail(TimeoutError("page did not load"))

    assert _coverage(conn) == (6, 6, "complete_single_source")


def test_successful_run_replaces_failed_coverage(conn, ghana_pl):
    _start(conn, ghana_pl).fail(TimeoutError("page did not load"))
    _start(conn, ghana_pl).load([], _round_robin(["A", "B", "C"]))

    assert _coverage(conn) == (6, 6, "complete_single_source")


def test_single_source_never_replaces_verified(conn, ghana_pl):
    _start(conn, ghana_pl).load([], _round_robin(["A", "B", "C"]))
    # Step 5 (reconciliation) will set 'verified'. Here, the test sets it.
    conn.execute("UPDATE season_coverage SET status = 'verified'")

    summary = _start(conn, ghana_pl).load([], _round_robin(["A", "B", "C"])[:2])

    assert _coverage(conn) == (6, 6, "verified")
    assert summary.coverage_status == "verified"


def test_read_gives_back_the_loaded_table(conn, ghana_pl):
    rows = [
        SourceTableRow(
            source="rsssf",
            league_code="gh_pl",
            season="2023/2024",
            stage=stage,
            row_number=number,
            position=number,
            team_raw=team,
            played=2,
            won=won,
            drawn=0,
            lost=2 - won,
            goals_for=3,
            goals_against=1,
            points=won * 3,
            note=note,
        )
        for stage, number, team, won, note in [
            ("Group A", 1, "Hearts of Oak", 2, "Qualified"),
            ("Group A", 2, "Kotoko", 0, None),
            ("Group B", 1, "Medeama", 1, "[-3]"),
        ]
    ]
    RunRecorder.start(conn, ghana_pl, SEASON, "rsssf", "1.2.0").load([], [], rows)

    assert read_season_tables(conn, "gh_pl", "2023/2024", "rsssf") == rows
    assert read_season_tables(conn, "gh_pl", "2023/2024", "soccerway") == []
