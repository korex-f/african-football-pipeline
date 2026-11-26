"""
Tests for the source choice of FootballScraper (roadmap step 4, part 4).

The tests do not use the network, the browser or the database.
"""

import pytest

from african_football.models.season_model import SeasonRecord, SeasonStatus
from african_football.scraping.scraper import FootballScraper
from african_football.utils.logger import PipelineLogger

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


def test_unknown_source_stops(nigeria_npfl, tmp_path):
    with pytest.raises(ValueError, match="Unknown source"):
        _scraper(nigeria_npfl, tmp_path, "flashscore")


def test_rsssf_has_no_halftime_scores(nigeria_npfl, tmp_path):
    # The NPFL collects halftime scores from Soccerway; RSSSF pages have none.
    assert nigeria_npfl.fetch_halftime
    assert _scraper(nigeria_npfl, tmp_path, "soccerway").halftime
    assert not _scraper(nigeria_npfl, tmp_path, "rsssf").halftime
