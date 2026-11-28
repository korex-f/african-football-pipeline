"""
Tests for FootballScraper.validate_data().

validate_data() reports each match that has a required field without a
value. A value is missing if it is None, or if it is text that is empty or
that has only spaces. A score of 0 is a value: before this change, 'not 0'
made it a missing value.

The matches are dictionaries in the form of the exports (exports/legacy.py).
The tests do not use the network, the browser or the database.
"""

from typing import Any

from african_football.models.season_model import SeasonRecord, SeasonStatus
from african_football.scraping.scraper import FootballScraper
from african_football.utils.logger import PipelineLogger

# A season for the scraper. validate_data() does not use its URL.
SEASON = SeasonRecord(
    season="2023/2024",
    start_year=2023,
    end_year=2024,
    status=SeasonStatus.COMPLETED,
    url="https://www.rsssf.org/tablesn/nig2024.html",
)


def _scraper(league, tmp_path, source: str) -> FootballScraper:
    return FootballScraper(
        league,
        SEASON,
        PipelineLogger(log_dir=str(tmp_path / "logs")),
        raw_root=tmp_path,
        database_url="postgresql://unused",
        source=source,
    )


def _match(**changes: Any) -> dict[str, Any]:
    match: dict[str, Any] = {
        "home_team": "Enyimba",
        "away_team": "Rivers United",
        "home_score": "0",
        "away_score": "0",
        "date": "07.01.2024",
        "round": "Round 10",
        "stage": "NPFL 2023/24",
    }
    match.update(changes)
    return match


def test_new_scraper_has_no_missing_data(nigeria_npfl, tmp_path):
    scraper = _scraper(nigeria_npfl, tmp_path, "soccerway")
    assert scraper.stats["missing_data"] == []


def test_real_zero_zero_match_is_not_reported(nigeria_npfl, tmp_path):
    scraper = _scraper(nigeria_npfl, tmp_path, "soccerway")
    match = _match()
    scraper.validate_data([match])
    assert scraper.stats["missing_data"] == []


def test_zero_score_as_a_number_is_not_reported(nigeria_npfl, tmp_path):
    scraper = _scraper(nigeria_npfl, tmp_path, "soccerway")
    match = _match(home_score=0, away_score=0)
    scraper.validate_data([match])
    assert scraper.stats["missing_data"] == []


def test_truly_missing_score_is_reported(nigeria_npfl, tmp_path):
    scraper = _scraper(nigeria_npfl, tmp_path, "soccerway")
    match = _match(home_score=None)
    scraper.validate_data([match])
    assert scraper.stats["missing_data"][0]["issues"] == ["home_score"]


def test_empty_team_name_is_reported(nigeria_npfl, tmp_path):
    scraper = _scraper(nigeria_npfl, tmp_path, "soccerway")
    match = _match(home_team="")
    scraper.validate_data([match])
    assert scraper.stats["missing_data"][0]["issues"] == ["home_team"]
