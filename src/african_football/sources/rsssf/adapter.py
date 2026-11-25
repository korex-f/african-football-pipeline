"""
adapter.py: the RSSSF source adapter (roadmap step 4).

RSSSF (https://www.rsssf.org/) has tables and results of many African
leagues, also for old seasons that Soccerway does not have. The pages are
static HTML, thus the adapter uses plain HTTP, not a browser.

    1. discover_seasons: read the list of champions of the league
                         (rsssf_index in leagues.yaml), and give one
                         SeasonRecord for each season page.
    2. fetch:            get the season page into the raw store. A page that
                         the store has is not fetched again.
    3. parse:            read the matches of the top league from the stored
                         page (parser.py). The lines that the parser could
                         not read are in `problems`, and in the log.
    4. parse_tables:     read the final tables of the top league (tables.py).
                         This is not a method of the SourceAdapter Protocol:
                         the Soccerway results pages have no tables.

The season labels come from season_label(), thus a season has the same label
as from Soccerway (decision 20). The text of the link gives the years, not
the file name (decision 21).

The RSSSF pages are the work of their authors. Each page names them. The
licence of the pages permits copies if the authors are acknowledged.
"""

import asyncio
import re
from datetime import date
from typing import TYPE_CHECKING, Optional
from urllib.parse import urldefrag, urljoin

from african_football.models.league_model import LeagueConfig
from african_football.models.season_model import (
    SeasonRecord,
    SeasonStatus,
    season_label,
)
from african_football.models.source_match import SourceMatch
from african_football.models.source_table import SourceTableRow
from african_football.sources.base import RawDocument
from african_football.sources.rsssf.http import BASE_URL, RsssfHttp
from african_football.sources.rsssf.index import (
    IndexEntry,
    parse_index,
    select_section,
)
from african_football.sources.rsssf.parser import (
    LeagueChoice,
    choose_league,
    parse_page,
    season_part,
    split_competitions,
)
from african_football.sources.rsssf.tables import parse_tables
from african_football.utils.logger import PipelineLogger

if TYPE_CHECKING:
    from african_football.sources.raw_store import RawStore

# A champion text that tells that the season had no champion. The page of
# such a season can have results, but the season did not finish.
_NO_WINNER = re.compile(
    r"^(abandoned|not finished|not held|cancell?ed|annulled|void)\b",
    re.IGNORECASE,
)


class RsssfConfigError(Exception):
    """The configuration of a league or a season does not permit an RSSSF step."""


class RsssfAdapter:
    """
    The SourceAdapter for RSSSF.

    The adapter needs no browser, thus it is not a context manager. http can
    be replaced in the tests. today gives the date for the ONGOING status,
    and can also be replaced in the tests.
    """

    name = "rsssf"

    def __init__(
        self,
        logger: PipelineLogger,
        http: Optional[RsssfHttp] = None,
        today: Optional[date] = None,
    ) -> None:
        self.logger = logger
        self.http = http or RsssfHttp()
        self.today = today or date.today()
        # The problems of the last parse(), for example the lines that look
        # like a result but that the parser could not read.
        self.problems: list[str] = []
        # The league choice of the last parse() (decision 24).
        self.league_choice: Optional[LeagueChoice] = None

    async def discover_seasons(self, league: LeagueConfig) -> list[SeasonRecord]:
        """Give the seasons of the league that RSSSF has, oldest first.

        Only seasons with a page are in the result. An ONGOING season (no
        champion, and the season is not over) is not in the result.
        """
        if not league.rsssf_index:
            raise RsssfConfigError(f"League '{league.code}' has no rsssf_index")
        index_url = urljoin(BASE_URL, league.rsssf_index)
        page = await asyncio.to_thread(self.http.get, index_url)

        entries = select_section(parse_index(page), league.rsssf_section)
        if not entries:
            raise RsssfConfigError(
                f"{index_url}: no season lines in the section {league.rsssf_section!r}"
            )

        seasons: dict[str, SeasonRecord] = {}
        for entry in entries:
            record = self._season_record(entry, index_url)
            if record is None:
                continue
            if record.season in seasons:
                self.logger.log(
                    f"RSSSF: season {record.season} is in the list two times; "
                    f"the adapter keeps the first ({seasons[record.season].url})",
                    level="WARNING",
                )
                continue
            seasons[record.season] = record
        return sorted(seasons.values(), key=lambda s: (s.start_year, s.end_year))

    async def fetch(
        self, league: LeagueConfig, season: SeasonRecord, store: "RawStore"
    ) -> list[RawDocument]:
        """Get the season page into the raw store, and give its document.

        The page is stored without the anchor of the season URL: the page is
        the same for all its anchors. The parser gets the anchor from
        season.url.
        """
        if not season.url:
            raise RsssfConfigError(f"Season {season.season} has no RSSSF page")
        page_url, _anchor = urldefrag(season.url)

        if store.has(page_url, league.timezone):
            document = store.get(page_url)
            assert document is not None
            return [document]

        self.logger.log(f"RSSSF: get {page_url}")
        page = await asyncio.to_thread(self.http.get, page_url)
        name = page_url.rsplit("/", 1)[-1]
        return [store.save(page_url, name, page, league.timezone)]

    def parse(
        self,
        league: LeagueConfig,
        season: SeasonRecord,
        documents: list[RawDocument],
        store: "RawStore",
    ) -> list[SourceMatch]:
        """Read the matches of the top league from the season page.

        The page is the first document. For a page with many seasons, the
        anchor of season.url selects the part of the season.
        """
        if not documents:
            raise RsssfConfigError(f"Season {season.season}: no stored page")
        if not season.url:
            raise RsssfConfigError(f"Season {season.season} has no RSSSF page")
        document = documents[0]
        _page_url, anchor = urldefrag(season.url)
        page = store.load(document)
        self._log_league_choice(page, anchor, league, season)
        matches, self.problems = parse_page(
            page,
            league_code=league.code,
            season=season.season,
            start_year=season.start_year,
            end_year=season.end_year,
            timezone=league.timezone,
            source_url=season.url,
            raw_documents=(document.sha256,),
            anchor=anchor,
            league_pattern=league.rsssf_league,
        )
        for problem in self.problems:
            self.logger.log(f"RSSSF {season.season}: {problem}", level="WARNING")
        return matches

    def parse_tables(
        self,
        league: LeagueConfig,
        season: SeasonRecord,
        documents: list[RawDocument],
        store: "RawStore",
    ) -> list[SourceTableRow]:
        """Read the final tables of the top league from the season page.

        The problems (rows that were not read) are added to `problems`, and
        written to the log.
        """
        if not documents:
            raise RsssfConfigError(f"Season {season.season}: no stored page")
        if not season.url:
            raise RsssfConfigError(f"Season {season.season} has no RSSSF page")
        _page_url, anchor = urldefrag(season.url)
        rows, problems = parse_tables(
            store.load(documents[0]),
            league_code=league.code,
            season=season.season,
            anchor=anchor,
            league_pattern=league.rsssf_league,
        )
        self.problems = self.problems + problems
        for problem in problems:
            self.logger.log(f"RSSSF {season.season}: {problem}", level="WARNING")
        return rows

    def _log_league_choice(
        self, page: str, anchor: str, league: LeagueConfig, season: SeasonRecord
    ) -> None:
        """Write the competition that choose_league() took, why, and the
        other competitions, to the log (decision 24). Thus a wrong choice is
        visible, and rsssf_league in leagues.yaml can correct it."""
        part = season_part(page, anchor) if anchor else page
        if part is None:
            return
        self.league_choice = choose_league(
            split_competitions(part), league.rsssf_league
        )
        name = (
            self.league_choice.competition.name
            if self.league_choice.competition
            else "no league"
        )
        others = "; ".join(self.league_choice.alternatives) or "none"
        self.logger.log(
            f"RSSSF {season.season}: league {name!r} ({self.league_choice.reason}); "
            f"other competitions: {others}"
        )

    def _season_record(
        self, entry: IndexEntry, index_url: str
    ) -> Optional[SeasonRecord]:
        """Make a SeasonRecord from a line of the list, or give None."""
        champion = entry.champion
        if champion is not None and _NO_WINNER.match(champion):
            status = SeasonStatus.NO_WINNER
            champion = None
        elif champion is not None:
            status = SeasonStatus.COMPLETED
        elif entry.end_year >= self.today.year:
            # No champion yet, and the season is not over.
            return None
        else:
            status = SeasonStatus.NO_WINNER

        return SeasonRecord(
            season=season_label(entry.start_year, entry.end_year),
            start_year=entry.start_year,
            end_year=entry.end_year,
            status=status,
            url=urljoin(index_url, entry.href),
            champion=champion,
        )
