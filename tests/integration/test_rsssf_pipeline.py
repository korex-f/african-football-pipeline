"""
Integration tests: FootballScraper with the RSSSF adapter and the pipeline
database (roadmap step 4, part 4).

The raw store has the page before the run, thus the adapter does not use the
network. The page is the fixture nig2024.html (NPFL 2023/24).
"""

import asyncio
from pathlib import Path

import psycopg
import pytest

from african_football.models.season_model import SeasonRecord, SeasonStatus
from african_football.scraping.scraper import FootballScraper
from african_football.sources.raw_store import RawStore
from african_football.sources.rsssf.http import decode_page
from african_football.utils.logger import PipelineLogger

pytestmark = pytest.mark.db

PAGE_URL = "https://www.rsssf.org/tablesn/nig2024.html"
FIXTURE = (
    Path(__file__).parent.parent / "fixtures" / "rsssf" / "seasons" / "nig2024.html"
)
SEASON = SeasonRecord(
    season="2023/2024",
    start_year=2023,
    end_year=2024,
    status=SeasonStatus.COMPLETED,
    url=PAGE_URL,
)


def _run(nigeria_npfl, tmp_path: Path, database_url: str) -> FootballScraper:
    store = RawStore(tmp_path, "rsssf", nigeria_npfl.code, SEASON.season)
    store.save(
        PAGE_URL,
        "nig2024.html",
        decode_page(FIXTURE.read_bytes()),
        nigeria_npfl.timezone,
    )

    async def run() -> FootballScraper:
        async with FootballScraper(
            nigeria_npfl,
            SeasonRecord(**vars(SEASON)),
            PipelineLogger(log_dir=str(tmp_path / "logs")),
            raw_root=tmp_path,
            database_url=database_url,
            source="rsssf",
        ) as scraper:
            scraper.data = await scraper.scrape()  # pyright: ignore[reportAttributeAccessIssue]
            return scraper

    return asyncio.run(run())


def test_rsssf_run_writes_the_matches_and_the_table(
    pipeline_database, nigeria_npfl, tmp_path
):
    scraper = _run(nigeria_npfl, tmp_path, pipeline_database)

    # 20 teams: 380 matches, and 1 replay of an abandoned match.
    data = scraper.data  # pyright: ignore[reportAttributeAccessIssue]
    assert data["total_matches"] == 381
    assert (data["source"], data["has_halftime_scores"]) == ("rsssf", False)
    with psycopg.connect(pipeline_database) as conn:
        run = conn.execute("SELECT source, status FROM collection_runs").fetchall()
        tables = conn.execute(
            "SELECT count(*) FROM source_tables WHERE source = 'rsssf'"
        ).fetchone()
        matches = conn.execute(
            "SELECT count(*) FROM source_matches WHERE source = 'rsssf'"
        ).fetchone()
    assert run == [("rsssf", "succeeded")]
    assert tables == (20,)
    assert matches == (381,)


def test_second_rsssf_run_changes_nothing(pipeline_database, nigeria_npfl, tmp_path):
    _run(nigeria_npfl, tmp_path, pipeline_database)
    scraper = _run(nigeria_npfl, tmp_path, pipeline_database)

    summary = scraper.load_summary
    assert summary is not None
    assert (summary.matches_new, summary.matches_not_seen) == (0, 0)
