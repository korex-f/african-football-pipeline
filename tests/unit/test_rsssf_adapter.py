"""
Tests for sources/rsssf/adapter.py.

A fake HTTP client gives the fixture pages. The raw store is in a temporary
folder. The tests do not use the network.
"""

import asyncio
from datetime import date
from pathlib import Path

import pytest

from african_football.models.league_model import LeagueConfig
from african_football.models.season_model import SeasonRecord, SeasonStatus
from african_football.sources.base import SourceAdapter
from african_football.sources.raw_store import RawStore
from african_football.sources.rsssf.adapter import RsssfAdapter, RsssfConfigError
from african_football.sources.rsssf.http import decode_page
from african_football.utils.logger import PipelineLogger

FIXTURES = Path(__file__).parent.parent / "fixtures" / "rsssf"
TODAY = date(2026, 11, 24)


class FakeHttp:
    """Gives fixture pages by URL, and records the URLs."""

    def __init__(self, pages: dict[str, str]):
        self.pages = pages
        self.urls: list[str] = []

    def get(self, url: str) -> str:
        self.urls.append(url)
        return self.pages[url]


def _fixture(name: str) -> str:
    return decode_page((FIXTURES / name).read_bytes())


def _league(**changes) -> LeagueConfig:
    fields = dict(
        code="npfl",
        name="Nigeria Professional Football League",
        country="nigeria",
        slug="npfl",
        fetch_halftime=True,
        timezone="Africa/Lagos",
        rsssf_index="tablesn/nigchamp.html",
        rsssf_section="National League/Nigeria Football League",
    )
    fields.update(changes)
    return LeagueConfig(**fields)  # pyright: ignore[reportArgumentType]


@pytest.fixture
def logger(tmp_path) -> PipelineLogger:
    return PipelineLogger(log_dir=tmp_path / "logs")


def _adapter(logger, pages: dict[str, str]) -> tuple[RsssfAdapter, FakeHttp]:
    http = FakeHttp(pages)
    adapter = RsssfAdapter(logger, http=http, today=TODAY)  # pyright: ignore[reportArgumentType]
    return adapter, http


def test_adapter_is_a_source_adapter(logger):
    # The type checker compares RsssfAdapter with the Protocol at this line.
    adapter: SourceAdapter = RsssfAdapter(logger)
    assert adapter.name == "rsssf"


# ---------------------------------------------------------------------------
# discover_seasons
# ---------------------------------------------------------------------------


def _discover(logger, league: LeagueConfig, index: str) -> list[SeasonRecord]:
    url = f"https://www.rsssf.org/{league.rsssf_index}"
    adapter, _ = _adapter(logger, {url: _fixture(index)})
    return asyncio.run(adapter.discover_seasons(league))


def test_discover_nigeria(logger):
    seasons = _discover(logger, _league(), "nigchamp.html")

    first = seasons[0]
    assert (first.season, first.start_year, first.end_year) == ("1972", 1972, 1972)
    assert first.url == "https://www.rsssf.org/tablesn/nig72.html#72"
    assert first.status is SeasonStatus.COMPLETED
    assert first.champion == "Mighty Jets (Jos)"

    by_label = {s.season: s for s in seasons}
    # The labels have the same style as Soccerway (decision 20).
    assert by_label["2021/2022"].url == "https://www.rsssf.org/tablesn/nig2022.html"
    assert "2023" in by_label
    assert "2023/2024" in by_label


def test_abandoned_season_has_no_winner(logger):
    by_label = {s.season: s for s in _discover(logger, _league(), "nigchamp.html")}

    abandoned = by_label["2019/2020"]
    assert abandoned.status is SeasonStatus.NO_WINNER
    assert abandoned.champion is None
    assert not abandoned.is_scrapeable()


def test_not_finished_season_has_no_winner(logger):
    league = _league(
        code="eg_pl",
        rsssf_index="tablese/egychamp.html",
        rsssf_section="National League",
    )
    by_label = {s.season: s for s in _discover(logger, league, "egychamp.html")}

    assert by_label["2011/2012"].status is SeasonStatus.NO_WINNER
    assert by_label["1948/1949"].champion == "Al-Ahly"


def test_seasons_are_sorted_oldest_first(logger):
    league = _league(
        code="gh_pl", rsssf_index="tablesg/ghachamp.html", rsssf_section=""
    )
    seasons = _discover(logger, league, "ghachamp.html")

    years = [(s.start_year, s.end_year) for s in seasons]
    assert years == sorted(years)


def test_ongoing_season_is_skipped(logger):
    # A season without a champion that is not over yet.
    index = (
        "<pre>\n"
        '<a href="nig2026.html">2026</a>\n'
        '<a href="nig2025.html">2024/25</a> Remo Stars\n'
        "</pre>"
    )
    url = "https://www.rsssf.org/tablesn/nigchamp.html"
    adapter, _ = _adapter(logger, {url: index})

    seasons = asyncio.run(adapter.discover_seasons(_league(rsssf_section="")))

    assert [s.season for s in seasons] == ["2024/2025"]


def test_league_without_rsssf_index(logger):
    adapter, _ = _adapter(logger, {})
    with pytest.raises(RsssfConfigError, match="no rsssf_index"):
        asyncio.run(adapter.discover_seasons(_league(rsssf_index="")))


def test_wrong_section_is_an_error(logger):
    with pytest.raises(RsssfConfigError, match="Premier League"):
        _discover(logger, _league(rsssf_section="Premier League"), "nigchamp.html")


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------


def _season(url: str) -> SeasonRecord:
    return SeasonRecord("1972", 1972, 1972, SeasonStatus.COMPLETED, url=url)


def test_fetch_stores_the_page_without_the_anchor(logger, tmp_path):
    page_url = "https://www.rsssf.org/tablesn/nig72.html"
    adapter, http = _adapter(logger, {page_url: "Nigeria 1972 to 1979"})
    store = RawStore(tmp_path, "rsssf", "npfl", "1972")

    [document] = asyncio.run(adapter.fetch(_league(), _season(page_url + "#72"), store))

    assert http.urls == [page_url]
    assert document.url == page_url
    assert document.path == "nig72.html.gz"
    assert document.source == "rsssf"
    assert store.load(document) == "Nigeria 1972 to 1979"


def test_second_fetch_uses_the_raw_store(logger, tmp_path):
    page_url = "https://www.rsssf.org/tablesn/nig72.html"
    adapter, http = _adapter(logger, {page_url: "Nigeria 1972 to 1979"})
    store = RawStore(tmp_path, "rsssf", "npfl", "1972")
    asyncio.run(adapter.fetch(_league(), _season(page_url), store))

    # A new store object reads the manifest from the disk.
    again = RawStore(tmp_path, "rsssf", "npfl", "1972")
    [document] = asyncio.run(adapter.fetch(_league(), _season(page_url), again))

    assert http.urls == [page_url]
    assert document.url == page_url


def test_fetch_without_url(logger, tmp_path):
    adapter, _ = _adapter(logger, {})
    store = RawStore(tmp_path, "rsssf", "npfl", "1972")
    with pytest.raises(RsssfConfigError, match="no RSSSF page"):
        asyncio.run(adapter.fetch(_league(), _season(""), store))


def _stored_page(tmp_path, name: str, label: str):
    """Put a fixture season page in a raw store, and give the store and the document."""
    store = RawStore(tmp_path, "rsssf", "gh_pl", label)
    url = f"https://www.rsssf.org/tablesg/{name}"
    page = decode_page((FIXTURES / "seasons" / name).read_bytes())
    return store, store.save(url, name, page, "Africa/Accra"), url


def test_parse_gives_the_matches_of_the_stored_page(logger, tmp_path):
    store, document, url = _stored_page(tmp_path, "gha2024.html", "2023/2024")
    season = SeasonRecord("2023/2024", 2023, 2024, SeasonStatus.COMPLETED, url=url)
    adapter, http = _adapter(logger, {})
    league = _league(code="gh_pl", timezone="Africa/Accra")

    matches = adapter.parse(league, season, [document], store)

    assert len(matches) == 307
    assert http.urls == []  # parse does not use the network
    first = matches[0]
    assert (first.source, first.league_code, first.season, first.timezone) == (
        "rsssf",
        "gh_pl",
        "2023/2024",
        "Africa/Accra",
    )
    assert first.raw_documents == (document.sha256,)
    assert first.source_url == url
    assert adapter.problems == []


def test_parse_uses_the_anchor_and_logs_the_problems(logger, tmp_path):
    store, document, url = _stored_page(tmp_path, "ghahist.html", "1963/1964")
    season = SeasonRecord(
        "1963/1964", 1963, 1964, SeasonStatus.COMPLETED, url=url + "#99"
    )
    adapter, _ = _adapter(logger, {})

    assert adapter.parse(_league(), season, [document], store) == []
    assert adapter.problems == ["no season part for the anchor #99"]
    log = next((tmp_path / "logs").glob("*")).read_text()
    assert "no season part for the anchor #99" in log


def test_parse_without_a_document(logger, tmp_path):
    adapter, _ = _adapter(logger, {})
    store = RawStore(tmp_path, "rsssf", "npfl", "1972")
    with pytest.raises(RsssfConfigError, match="no stored page"):
        adapter.parse(_league(), _season("x"), [], store)
