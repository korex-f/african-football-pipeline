"""
conftest.py — Shared pytest fixtures for the African football pipeline test suite.

Fixtures defined here are automatically available to all test modules
without needing to import them explicitly.
"""

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from african_football.models.league_model import LeagueConfig
from african_football.models.season_model import SeasonRecord, SeasonStatus


@pytest.fixture
def nigeria_npfl() -> LeagueConfig:
    "A sample LeagueConfig for the Nigerian first division."
    return LeagueConfig(
        code="npfl",
        name="Nigeria Professional Football League",
        country="nigeria",
        slug="npfl",
        fetch_halftime=True,
        timezone="Africa/Lagos",
        submission_code="ng1",
    )


@pytest.fixture
def ghana_pl() -> LeagueConfig:
    "A sample LeagueConfig for the Ghanian first division."
    return LeagueConfig(
        code="gh_pl",
        name="Ghana Premier League",
        country="ghana",
        slug="premier-league",
        fetch_halftime=False,
        timezone="Africa/Accra",
        submission_code="gh1",
    )


@pytest.fixture
def sample_league_yaml_data() -> dict:
    """A minimal valid leagues YAML data structure for config loader tests."""
    return {
        "leagues": [
            {
                "code": "npfl",
                "name": "Nigeria Professional Football League",
                "country": "nigeria",
                "slug": "npfl",
                "fetch_halftime": True,
                "timezone": "Africa/Lagos",
                "submission_code": "ng1",
            }
        ]
    }


@pytest.fixture
def sample_teams() -> list:
    """A minimal valid canonical teams list for normalizer tests."""
    return [
        {
            "canonical": "Enyimba FC",
            "slug": "enyimba",
            "aliases": ["Enyimba", "Enyimba International FC"],
        },
        {
            "canonical": "Kano Pillars FC",
            "slug": "kano-pillars",
            "aliases": ["Kano Pillars", "Pillars FC"],
        },
        {"canonical": "ENPPI SC", "slug": "enppi", "aliases": ["Enppi", "Enppi SC"]},
        {
            "canonical": "Orlando Pirates FC",
            "slug": "orlando-pirates",
            "aliases": ["Orlando", "Orlando pirates", "Orlando pirates FC"],
        },
    ]


@pytest.fixture
def completed_season() -> SeasonRecord:
    """A completed SeasonRecord for testing."""
    return SeasonRecord(
        season="2024/2025",
        start_year=2024,
        end_year=2025,
        status=SeasonStatus.COMPLETED,
        url="https://ng.soccerway.com/nigeria/npfl-2024-2025/results/",
        champion="Enyimba FC",
        champion_url="https://ng.soccerway.com/team/enyimba/abc123/",
    )


@pytest.fixture
def no_winner_season() -> SeasonRecord:
    """A no-winner SeasonRecord for testing."""
    return SeasonRecord(
        season="2019/2020",
        start_year=2019,
        end_year=2020,
        status=SeasonStatus.NO_WINNER,
    )


@pytest.fixture
def ongoing_season() -> SeasonRecord:
    """An ongoing SeasonRecord for testing."""
    return SeasonRecord(
        season="2025/2026",
        start_year=2025,
        end_year=2026,
        status=SeasonStatus.ONGOING,
    )


@pytest.fixture
def sample_data() -> dict:
    return {
        "stages": [
            {
                "matches": [
                    {
                        "home_team": "Enyimba",
                        "away_team": "Kano Pillars",
                    },
                    {
                        "home_team": "Enyimba International FC",
                        "away_team": "Pillars FC",
                    },
                ]
            }
        ]
    }


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def database_url() -> str:
    """Give the DATABASE_URL of the pipeline database.

    If DATABASE_URL is not set, the test is skipped. Thus the tests that
    need a database do not fail on a computer without Postgres.

    In CI (the CI variable is set), a missing DATABASE_URL is an error, not
    a skip. Without this rule, an error in the workflow file can skip all the
    database tests, and CI still shows a pass.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        if os.environ.get("CI"):
            pytest.fail("DATABASE_URL is not set in CI")
        pytest.skip("DATABASE_URL is not set")
    return url


@pytest.fixture
def empty_database(database_url: str) -> Iterator[str]:
    """Make a new empty database for one test, and give its URL.

    Each test gets its own database. Thus a test cannot change the data of
    the pipeline database or of a different test. The database is deleted
    after the test.
    """
    name = f"test_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(database_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield make_conninfo(database_url, dbname=name)
    finally:
        with psycopg.connect(database_url, autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )
