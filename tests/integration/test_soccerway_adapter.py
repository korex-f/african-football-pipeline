"""
test_soccerway_adapter.py — Test the Soccerway adapter without the network.

Playwright stops each request of the browser and answers it with a
fixture page (page.route). Thus, the real fetch code runs: page loads,
the 'Show more' loop, the halftime wait and the raw store. No request
goes to Soccerway.

These tests need the Playwright Chromium installation.
"""

import asyncio
from datetime import time
from pathlib import Path
from typing import Any, Optional

import pytest

from african_football.models.league_model import LeagueConfig
from african_football.models.season_model import SeasonRecord, SeasonStatus
from african_football.models.source_match import MatchStatus
from african_football.scraping.scraper import FootballScraper
from african_football.sources.raw_store import RawStore
from african_football.sources.soccerway import adapter as adapter_module
from african_football.sources.soccerway.adapter import SoccerwayAdapter

FIXTURES = Path(__file__).parent.parent / "fixtures" / "soccerway"
RESULTS_URL = "https://ng.soccerway.com/nigeria/npfl-2023-2024/results/"
TZ = "Africa/Lagos"

# The match IDs in league_results.html. The third row (Rangers Int'l vs
# Enyimba, ld5oPq3t) is awarded, thus it has no match page.
AKWA = "h4zYGtCC"
BENDEL = "QiqHKOCm"


class _RecordingLogger:
    """Keep the log messages in a list. Do not write to the console or a file."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def log(self, message: str, level: str = "INFO", to_console: bool = True) -> None:
        self.messages.append(message)

    def log_section(self, title: str) -> None:
        self.messages.append(title)


@pytest.fixture
def league() -> LeagueConfig:
    return LeagueConfig(
        code="npfl",
        name="Nigeria Professional Football League",
        country="nigeria",
        slug="npfl",
        fetch_halftime=True,
        timezone=TZ,
    )


@pytest.fixture
def season() -> SeasonRecord:
    return SeasonRecord(
        season="2023/2024",
        start_year=2023,
        end_year=2024,
        status=SeasonStatus.COMPLETED,
        url=RESULTS_URL,
    )


@pytest.fixture
def store(tmp_path) -> RawStore:
    return RawStore(tmp_path, "soccerway", "npfl", "2023/2024")


class _FakeSite:
    """Answer the browser requests with fixture pages. Count the requests."""

    def __init__(self, no_halftime: Optional[str] = None) -> None:
        self.no_halftime = no_halftime
        self.requests: list[str] = []
        self.results = (FIXTURES / "league_results.html").read_text()
        self.match_page = (FIXTURES / "match_page.html").read_text()
        # The same match page without the halftime block, but with the kick-off.
        self.match_page_without_halftime = self.match_page.replace(
            ">1st Half<", ">Summary<"
        )

    async def handle(self, route: Any) -> None:
        url = route.request.url
        if url == RESULTS_URL:
            self.requests.append(url)
            await route.fulfill(body=self.results, content_type="text/html")
        elif "/match/" in url:
            self.requests.append(url)
            body = self.match_page
            if self.no_halftime and self.no_halftime in url:
                body = self.match_page_without_halftime
            await route.fulfill(body=body, content_type="text/html")
        else:
            # Images, scripts, fonts: not necessary for the tests.
            await route.abort()


async def _fetch(
    league: LeagueConfig,
    season: SeasonRecord,
    store: RawStore,
    site: _FakeSite,
    logger: Optional[_RecordingLogger] = None,
) -> SoccerwayAdapter:
    """Run adapter.fetch with all requests sent to the fake site."""
    adapter = SoccerwayAdapter(logger or _RecordingLogger(), delay=(0, 0))  # type: ignore[arg-type]
    async with adapter:
        assert adapter._browser is not None
        original = adapter._browser.new_page

        async def new_page(**kwargs: Any):
            page = await original(**kwargs)
            await page.route("**/*", site.handle)
            return page

        adapter._browser.new_page = new_page  # type: ignore[method-assign]
        await adapter.fetch(league, season, store)
    return adapter


def test_fetch_stores_results_and_match_pages(league, season, store):
    site = _FakeSite()
    asyncio.run(_fetch(league, season, store, site))

    paths = sorted(d.path for d in store.documents())
    assert paths == [
        f"matches/{BENDEL}.html.gz",
        f"matches/{AKWA}.html.gz",
        "results.html.gz",
    ]
    assert all(d.timezone == TZ for d in store.documents())


def test_parse_makes_source_matches_from_stored_pages(league, season, store):
    asyncio.run(_fetch(league, season, store, _FakeSite()))
    adapter = SoccerwayAdapter(_RecordingLogger())  # type: ignore[arg-type]

    matches = adapter.parse(league, season, store.documents(), store)

    assert len(matches) == 3
    first = matches[0]
    assert first.source_match_id == AKWA
    assert (first.ht_home, first.ht_away) == (2, 1)
    assert first.kickoff_local == time(16, 0)
    assert len(first.raw_documents) == 2
    awarded = matches[2]
    assert awarded.status is MatchStatus.AWARDED
    assert len(awarded.raw_documents) == 1


def test_second_fetch_uses_the_raw_store(league, season, store):
    asyncio.run(_fetch(league, season, store, _FakeSite()))

    site = _FakeSite()
    asyncio.run(_fetch(league, season, store, site))

    assert site.requests == []


def test_match_page_without_halftime_is_kept_and_retried(
    league, season, store, monkeypatch
):
    monkeypatch.setattr(adapter_module, "HALFTIME_WAIT_MS", 300)
    logger = _RecordingLogger()
    site = _FakeSite(no_halftime=AKWA)

    adapter = asyncio.run(_fetch(league, season, store, site, logger))

    # The page was tried in all three passes. The old scraper stopped
    # after pass 2.
    akwa_requests = [u for u in site.requests if AKWA in u]
    assert len(akwa_requests) == 3
    assert any(m.startswith("Halftime pass 3") for m in logger.messages)
    akwa_url = akwa_requests[0]
    assert adapter.missing_halftime == [akwa_url]

    # The store keeps the page, because it has the kick-off time.
    matches = adapter.parse(league, season, store.documents(), store)
    assert matches[0].kickoff_local == time(16, 0)
    assert matches[0].ht_home is None

    # The next fetch gets only this page again.
    site_again = _FakeSite()
    asyncio.run(_fetch(league, season, store, site_again))
    assert site_again.requests == [akwa_url]


def test_damaged_match_page_is_fetched_again(league, season, store):
    asyncio.run(_fetch(league, season, store, _FakeSite()))
    document = next(d for d in store.documents() if AKWA in d.url)
    (store.folder / document.path).write_bytes(b"not gzip")

    site = _FakeSite()
    asyncio.run(_fetch(league, season, store, site))

    assert [u for u in site.requests if AKWA in u] == [document.url]


def test_football_scraper_uses_the_stored_pages(league, season, tmp_path):
    # Fill the raw store with complete pages. Then the scraper does not
    # need the network.
    raw_root = tmp_path / "sources"
    store = RawStore(raw_root, "soccerway", "npfl", "2023/2024")
    asyncio.run(_fetch(league, season, store, _FakeSite()))

    async def scrape():
        async with FootballScraper(
            league,
            season,
            _RecordingLogger(),  # type: ignore[arg-type]
            raw_root=raw_root,
        ) as scraper:
            return await scraper.scrape()

    data = asyncio.run(scrape())

    assert data["total_matches"] == 3
    assert data["pipeline_version"] == "1.1.0"
    [stage] = data["stages"]
    assert stage["stage_name"] == "NPFL"
    first = stage["matches"][0]
    assert first["date"] == "23.06.2024 16:00"
    assert first["half_time_score"] == "2 - 1"
    assert data["statistics"]["ht_scores_found"] == 2
    assert data["statistics"]["ht_scores_failed"] == []
    assert season.records_extracted == 3
