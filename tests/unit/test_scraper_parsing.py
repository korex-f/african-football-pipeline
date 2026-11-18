"""
test_scraper_parsing.py — Unit tests for Soccerway match row parsing.

parse_match_row and parse_round are pure functions. Thus, these tests
do not use a browser or the network.
"""

import asyncio

import pytest

from african_football.models.season_model import SeasonRecord, SeasonStatus
from african_football.scraping import scraper as scraper_module
from african_football.scraping.scraper import (
    FootballScraper,
    parse_kickoff,
    parse_match_row,
    parse_round,
)


def _row(**overrides) -> dict:
    """Return a raw match row like EXTRACT_STAGE_JS returns. Apply the overrides."""
    row = {
        "type": "match",
        "id": "g_1_abc",
        "date": "23.06.2024",
        "indicator": None,
        "home_team": "Akwa United",
        "away_team": "Rivers United",
        "home_score": "3",
        "away_score": "1",
        "home_pen": None,
        "away_pen": None,
        "link": "https://ng.soccerway.com/match/akwa/rivers/?mid=abc",
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize(
    ("text", "expected"),
    [("Round 12", 12), ("round 1", 1), ("Semi-finals", None), ("Round A", None)],
)
def test_parse_round(text, expected):
    assert parse_round(text) == expected


def test_regular_match():
    match = parse_match_row(_row(), "Round 38", 38, "NPFL")
    assert match is not None
    assert match["home_team"] == "Akwa United"
    assert (match["home_score"], match["away_score"]) == ("3", "1")
    assert match["date"] == "23.06.2024"
    assert match["round_number"] == 38
    assert match["awarded"] is False
    assert match["penalty_shootout"] is False
    assert match["full_time_score"] is None


def test_relative_link_is_made_absolute():
    match = parse_match_row(_row(link="/match/a/b/?mid=x"), None, None, "S")
    assert match is not None
    assert match["match_url"] == "https://ng.soccerway.com/match/a/b/?mid=x"


@pytest.mark.parametrize("indicator", ["Awrd", "WO"])
def test_awarded_match(indicator):
    match = parse_match_row(_row(indicator=indicator), None, None, "S")
    assert match is not None
    assert match["awarded"] is True
    assert match["awarded_reason"] == "walkover"


def test_walkover_without_score_is_kept_with_null_scores():
    row = _row(indicator="WO", home_score="-", away_score="-")
    match = parse_match_row(row, None, None, "S")
    assert match is not None
    assert match["home_score"] is None and match["away_score"] is None


def test_penalty_shootout_uses_shootout_score_and_keeps_full_time():
    row = _row(
        indicator="Pen", home_score="0", away_score="0", home_pen="3", away_pen="4"
    )
    match = parse_match_row(row, "Final", None, "Federation Cup")
    assert match is not None
    assert match["penalty_shootout"] is True
    assert (match["home_score"], match["away_score"]) == ("3", "4")
    assert match["full_time_score"] == "0-0"
    assert match["penalty_winner"] == "away"


def test_penalty_winner_compares_numerically():
    row = _row(home_score="1", away_score="1", home_pen="10", away_pen="9")
    match = parse_match_row(row, None, None, "S")
    assert match is not None
    assert match["penalty_winner"] == "home"


@pytest.mark.parametrize(
    "overrides",
    [{"home_team": None}, {"away_team": ""}, {"home_score": None}, {"away_score": "-"}],
)
def test_incomplete_row_is_rejected(overrides):
    assert parse_match_row(_row(**overrides), None, None, "S") is None


class _RecordingLogger:
    """Keep the log messages in a list. Do not write to the console or a file."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def log(self, message: str, level: str = "INFO", to_console: bool = True) -> None:
        self.messages.append(message)


def test_halftime_progress_is_logged_at_each_interval(nigeria_npfl, monkeypatch):
    season = SeasonRecord(
        season="2023/2024",
        start_year=2023,
        end_year=2024,
        status=SeasonStatus.COMPLETED,
        url="https://example.invalid/results/",
    )
    logger = _RecordingLogger()
    scraper = FootballScraper(nigeria_npfl, season, logger)  # type: ignore[arg-type]

    async def fake_details(page, url):
        return (None, None) if url.endswith("/7") else ("1 - 0", None)

    async def no_sleep(_):
        return None

    monkeypatch.setattr(scraper, "_get_match_details", fake_details)
    monkeypatch.setattr(scraper_module.asyncio, "sleep", no_sleep)

    matches = [(i, {"match_url": f"https://example.invalid/{i}"}) for i in range(31)]
    failed = asyncio.run(scraper._fetch_halftime_scores(None, matches, 1))  # type: ignore[arg-type]

    progress = [m for m in logger.messages if m.startswith("Halftime pass")]
    assert progress == [
        "Halftime pass 1: 15/31 matches done, 1 failed",
        "Halftime pass 1: 30/31 matches done, 1 failed",
        "Halftime pass 1: 31/31 matches done, 1 failed",
    ]
    assert len(failed) == 1


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("15.09.2023 19:30", "15.09.2023 19:30"),
        ("  15.09.2023\n19:30 ", "15.09.2023 19:30"),
        ("15.09.2023", None),
        ("Postponed", None),
        (None, None),
    ],
)
def test_parse_kickoff(text, expected):
    assert parse_kickoff(text) == expected


def test_kickoff_from_match_page_replaces_date(nigeria_npfl, monkeypatch):
    season = SeasonRecord(
        season="2023/2024",
        start_year=2023,
        end_year=2024,
        status=SeasonStatus.COMPLETED,
        url="https://example.invalid/results/",
    )
    scraper = FootballScraper(nigeria_npfl, season, _RecordingLogger())  # type: ignore[arg-type]

    async def fake_details(page, url):
        if url.endswith("/0"):
            return "1 - 0", "15.09.2023 19:30"
        return "0 - 0", None

    async def no_sleep(_):
        return None

    monkeypatch.setattr(scraper, "_get_match_details", fake_details)
    monkeypatch.setattr(scraper_module.asyncio, "sleep", no_sleep)

    with_time = {"match_url": "https://example.invalid/0", "date": "15.09.2023"}
    without_time = {"match_url": "https://example.invalid/1", "date": "16.09.2023"}
    matches = [(0, with_time), (1, without_time)]
    asyncio.run(scraper._fetch_halftime_scores(None, matches, 1))  # type: ignore[arg-type]

    assert with_time["date"] == "15.09.2023 19:30"
    assert without_time["date"] == "16.09.2023"
