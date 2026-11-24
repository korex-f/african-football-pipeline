"""
Tests for the database loader in db/loader.py, and for its use in
FootballScraper.

All tests need Postgres. Each test gets a new database with the migrations
(the pipeline_database fixture in tests/conftest.py). The tests use small
SourceMatch and RawDocument values, not real pages. The FootballScraper tests
use a fake adapter, thus they do not need a browser or the network.
"""

import asyncio
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, LiteralString

import psycopg
import pytest

from african_football.db.loader import RunRecorder
from african_football.models.league_model import LeagueConfig
from african_football.models.season_model import SeasonRecord, SeasonStatus
from african_football.models.source_match import MatchStatus, SourceMatch
from african_football.scraping.scraper import PIPELINE_VERSION, FootballScraper
from african_football.sources.base import RawDocument
from african_football.utils.logger import PipelineLogger

pytestmark = pytest.mark.db

SEASON = SeasonRecord(
    season="2023/2024",
    start_year=2023,
    end_year=2024,
    status=SeasonStatus.COMPLETED,
    url="https://example.com/results/",
)
OLD_TIME = datetime(2024, 1, 1, tzinfo=UTC)


def _match(match_id: str, **changes: Any) -> SourceMatch:
    """Make a valid played match. Use `changes` to replace fields."""
    fields: dict[str, Any] = dict(
        source="soccerway",
        source_match_id=match_id,
        source_url=f"https://example.com/match/?mid={match_id}",
        raw_documents=("a" * 64,),
        league_code="gh_pl",
        season="2023/2024",
        stage="Premier League",
        round_name="Round 1",
        round_number=1,
        match_date=date(2023, 9, 15),
        kickoff_local=time(15, 0),
        timezone="Africa/Accra",
        home_team_raw=f"Home {match_id}",
        away_team_raw=f"Away {match_id}",
        home_goals=2,
        away_goals=1,
        status=MatchStatus.PLAYED,
    )
    fields.update(changes)
    return SourceMatch(**fields)


def _document(name: str, sha: str = "a", fetched_at: datetime = OLD_TIME):
    return RawDocument(
        source="soccerway",
        url=f"https://example.com/{name}",
        path=f"{name}.html.gz",
        fetched_at=fetched_at,
        sha256=sha * 64,
        timezone="Africa/Accra",
    )


def _start(conn: psycopg.Connection, league: LeagueConfig) -> RunRecorder:
    return RunRecorder.start(conn, league, SEASON, "soccerway", PIPELINE_VERSION)


def _one(conn: psycopg.Connection, query: LiteralString, params: tuple = ()) -> tuple:
    row = conn.execute(query, params).fetchone()
    assert row is not None
    return row


@pytest.fixture
def conn(pipeline_database: str):
    with psycopg.connect(pipeline_database, autocommit=True) as connection:
        yield connection


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------


def test_start_writes_league_season_and_a_running_run(conn, ghana_pl):
    recorder = _start(conn, ghana_pl)

    assert _one(conn, "SELECT name, timezone FROM leagues") == (
        "Ghana Premier League",
        "Africa/Accra",
    )
    assert _one(conn, "SELECT label, start_year, end_year FROM seasons") == (
        "2023/2024",
        2023,
        2024,
    )
    status, finished_at, version = _one(
        conn,
        "SELECT status, finished_at, pipeline_version FROM collection_runs"
        " WHERE run_id = %s",
        (recorder.run_id,),
    )
    assert (status, finished_at, version) == ("running", None, PIPELINE_VERSION)


def test_start_is_committed_at_once(conn, pipeline_database, ghana_pl):
    # A run that stops before load() must stay visible. A second connection
    # sees only committed data.
    recorder = _start(conn, ghana_pl)

    with psycopg.connect(pipeline_database) as other:
        (status,) = _one(
            other,
            "SELECT status FROM collection_runs WHERE run_id = %s",
            (recorder.run_id,),
        )
    assert status == "running"


def test_second_start_uses_the_same_season_and_updates_the_league(conn, ghana_pl):
    first = _start(conn, ghana_pl)
    ghana_pl.name = "Ghana Premier League (new name)"
    second = _start(conn, ghana_pl)

    assert second.season_id == first.season_id
    assert second.run_id != first.run_id
    assert _one(conn, "SELECT count(*) FROM seasons") == (1,)
    assert _one(conn, "SELECT name FROM leagues") == (
        "Ghana Premier League (new name)",
    )


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------


def test_load_writes_pages_matches_and_finishes_the_run(conn, ghana_pl):
    recorder = _start(conn, ghana_pl)
    matches = [_match("m1"), _match("m2", ht_home=1, ht_away=0), _match("m3")]

    summary = recorder.load([_document("results"), _document("m1", "b")], matches)

    assert summary.matches_parsed == 3
    assert summary.matches_new == 3
    assert summary.documents_new == 2
    assert summary.matches_not_seen == 0

    rows = conn.execute(
        "SELECT source_match_id, page_position, ht_home, raw_documents"
        " FROM source_matches ORDER BY page_position"
    ).fetchall()
    assert [(r[0], r[1]) for r in rows] == [("m1", 0), ("m2", 1), ("m3", 2)]
    assert rows[1][2] == 1
    assert rows[0][3] == ["a" * 64]

    status, finished_at, parsed = _one(
        conn,
        "SELECT status, finished_at, matches_parsed FROM collection_runs"
        " WHERE run_id = %s",
        (recorder.run_id,),
    )
    assert status == "succeeded"
    assert finished_at is not None
    assert parsed == 3


def test_load_keeps_the_values_of_each_column(conn, ghana_pl):
    match = _match(
        "m1",
        home_goals=0,
        away_goals=0,
        pen_home=4,
        pen_away=3,
        round_name="Final",
        round_number=None,
    )
    _start(conn, ghana_pl).load([], [match])

    row = _one(
        conn,
        "SELECT match_date, kickoff_local, timezone, home_goals, away_goals,"
        " pen_home, pen_away, round_name, round_number, status"
        " FROM source_matches",
    )
    assert row == (
        date(2023, 9, 15),
        time(15, 0),
        "Africa/Accra",
        0,
        0,
        4,
        3,
        "Final",
        None,
        "played",
    )


def test_pages_fetched_counts_only_the_pages_of_this_run(conn, ghana_pl):
    recorder = _start(conn, ghana_pl)
    new_page = _document("new", "b", fetched_at=datetime.now(UTC) + timedelta(1))

    summary = recorder.load([_document("old"), new_page], [])

    assert summary.pages_fetched == 1
    assert _one(conn, "SELECT pages_fetched FROM collection_runs") == (1,)


def test_second_run_with_the_same_data_changes_nothing(conn, ghana_pl):
    _start(conn, ghana_pl).load([_document("results")], [_match("m1")])
    before = _one(conn, "SELECT first_seen_at, updated_at FROM source_matches")

    second = _start(conn, ghana_pl)
    summary = second.load([_document("results")], [_match("m1")])

    assert (summary.matches_new, summary.matches_changed) == (0, 0)
    assert summary.documents_new == 0
    assert _one(conn, "SELECT count(*) FROM source_matches") == (1,)
    assert _one(conn, "SELECT count(*) FROM raw_documents") == (1,)
    after = _one(
        conn, "SELECT first_seen_at, updated_at, last_run_id FROM source_matches"
    )
    assert after[:2] == before
    assert after[2] == second.run_id


def test_changed_match_is_updated(conn, ghana_pl):
    _start(conn, ghana_pl).load([], [_match("m1")])
    (first_seen,) = _one(conn, "SELECT first_seen_at FROM source_matches")

    # The second scrape found the halftime score.
    summary = _start(conn, ghana_pl).load([], [_match("m1", ht_home=1, ht_away=1)])

    assert (summary.matches_new, summary.matches_changed) == (0, 1)
    ht, seen, updated = _one(
        conn, "SELECT ht_home, first_seen_at, updated_at FROM source_matches"
    )
    assert ht == 1
    assert seen == first_seen
    assert updated > first_seen


def test_match_that_the_source_does_not_show_stays(conn, ghana_pl):
    _start(conn, ghana_pl).load([], [_match("m1"), _match("m2")])

    summary = _start(conn, ghana_pl).load([], [_match("m1")])

    assert summary.matches_not_seen == 1
    assert _one(conn, "SELECT count(*) FROM source_matches") == (2,)


def test_new_content_at_a_known_url_is_a_new_document(conn, ghana_pl):
    first = _start(conn, ghana_pl)
    first.load([_document("results", "a")], [])

    second = _start(conn, ghana_pl)
    summary = second.load([_document("results", "a"), _document("results", "b")], [])

    assert summary.documents_new == 1
    rows = conn.execute(
        "SELECT left(sha256, 1), first_run_id FROM raw_documents ORDER BY sha256"
    ).fetchall()
    assert rows == [("a", first.run_id), ("b", second.run_id)]


def test_failed_load_writes_nothing(conn, ghana_pl):
    # model_copy(update=...) does not run the Pydantic checks. Thus the
    # database constraint must stop the bad match (two equal team names).
    bad = _match("m2").model_copy(update={"away_team_raw": "Home m2"})
    recorder = _start(conn, ghana_pl)

    with pytest.raises(psycopg.errors.CheckViolation):
        recorder.load([_document("results")], [_match("m1"), bad])

    assert _one(conn, "SELECT count(*) FROM source_matches") == (0,)
    assert _one(conn, "SELECT count(*) FROM raw_documents") == (0,)
    assert _one(conn, "SELECT status FROM collection_runs") == ("running",)


def test_fail_records_the_error(conn, ghana_pl):
    recorder = _start(conn, ghana_pl)

    recorder.fail(TimeoutError("page did not load"))

    status, finished_at, error = _one(
        conn, "SELECT status, finished_at, error FROM collection_runs"
    )
    assert status == "failed"
    assert finished_at is not None
    assert error == "TimeoutError: page did not load"


# ---------------------------------------------------------------------------
# FootballScraper with a fake adapter
# ---------------------------------------------------------------------------


class FakeAdapter:
    """An adapter that gives fixed data. It does not use a browser."""

    name = "soccerway"
    network_errors = 0

    def __init__(self, matches: list[SourceMatch], error: BaseException | None = None):
        self.matches = matches
        self.error = error

    async def discover_seasons(self, league):
        return []

    async def fetch(self, league, season, store):
        if self.error is not None:
            raise self.error
        return [_document("results")]

    def parse(self, league, season, documents, store):
        return self.matches


def _scraper(ghana_pl, logger, tmp_path: Path, adapter, database_url):
    scraper = FootballScraper(
        ghana_pl,
        SeasonRecord(**vars(SEASON)),
        logger,
        raw_root=tmp_path,
        database_url=database_url,
    )
    # scrape() needs only _adapter. Thus the test does not start a browser.
    scraper._adapter = adapter  # pyright: ignore[reportAttributeAccessIssue]
    return scraper


@pytest.fixture
def logger(tmp_path):
    return PipelineLogger(log_dir=str(tmp_path / "logs"))


def test_scraper_writes_the_run(pipeline_database, ghana_pl, logger, tmp_path):
    adapter = FakeAdapter([_match("m1"), _match("m2")])
    scraper = _scraper(ghana_pl, logger, tmp_path, adapter, pipeline_database)

    data = asyncio.run(scraper.scrape())

    assert data["total_matches"] == 2
    assert scraper.load_summary is not None
    assert scraper.load_summary.matches_new == 2
    with psycopg.connect(pipeline_database) as conn:
        assert _one(conn, "SELECT status FROM collection_runs") == ("succeeded",)


def test_scraper_marks_a_failed_run(pipeline_database, ghana_pl, logger, tmp_path):
    adapter = FakeAdapter([], error=TimeoutError("page did not load"))
    scraper = _scraper(ghana_pl, logger, tmp_path, adapter, pipeline_database)

    with pytest.raises(TimeoutError):
        asyncio.run(scraper.scrape())

    with psycopg.connect(pipeline_database) as conn:
        assert _one(conn, "SELECT status, error FROM collection_runs") == (
            "failed",
            "TimeoutError: page did not load",
        )


def test_scraper_without_database_url(pipeline_database, ghana_pl, logger, tmp_path):
    scraper = _scraper(ghana_pl, logger, tmp_path, FakeAdapter([_match("m1")]), None)

    data = asyncio.run(scraper.scrape())

    assert data["total_matches"] == 1
    assert scraper.load_summary is None
    with psycopg.connect(pipeline_database) as conn:
        assert _one(conn, "SELECT count(*) FROM collection_runs") == (0,)


def test_scraper_marks_a_cancelled_run(pipeline_database, ghana_pl, logger, tmp_path):
    # Airflow cancels a task with asyncio.CancelledError. It is a
    # BaseException, not an Exception.
    adapter = FakeAdapter([], error=asyncio.CancelledError())
    scraper = _scraper(ghana_pl, logger, tmp_path, adapter, pipeline_database)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(scraper.scrape())

    with psycopg.connect(pipeline_database) as conn:
        assert _one(conn, "SELECT status FROM collection_runs") == ("failed",)
