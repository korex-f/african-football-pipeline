"""
base.py — The interface that each data source adapter must have.

An adapter connects the pipeline to one data source, for example
Soccerway or RSSSF. Each adapter does three tasks:

    1. discover_seasons: find the seasons that the source has.
    2. fetch:            get the pages of one season and keep them
                         in the raw store. This step uses the network.
    3. parse:            read the stored pages and make SourceMatch
                         records. This step does not use the network.

Because fetch and parse are different steps, you can parse the
stored pages again after you correct a parser error. You do not
need to get the pages from the source again.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from african_football.models.league_model import LeagueConfig
from african_football.models.season_model import SeasonRecord
from african_football.models.source_match import SourceMatch

if TYPE_CHECKING:
    from african_football.sources.raw_store import RawStore


@dataclass(frozen=True)
class RawDocument:
    """
    One page that a source adapter got and kept in the raw store.

    Attributes:
        source:     The source name, for example 'soccerway'.
        url:        The URL of the page.
        path:       The file path in the season folder, for example
                    'matches/h4zYGtCC.html.gz'.
        fetched_at: The date and time (UTC) when the adapter got the page.
        sha256:     The sha256 value of the page HTML, before compression.
        timezone:   The browser timezone when the adapter got the page.
                    Soccerway shows dates and times in this timezone.
    """

    source: str
    url: str
    path: str
    fetched_at: datetime
    sha256: str
    timezone: str


class SourceAdapter(Protocol):
    """
    The methods that each source adapter must have.

    This is a Protocol, not a base class. An adapter does not inherit
    from it. A class that has these methods is a SourceAdapter.
    A type checker, for example pyright, makes sure that the methods
    and their types are correct.
    """

    name: str

    async def discover_seasons(self, league: LeagueConfig) -> list[SeasonRecord]:
        """Return the seasons of the league that the source has."""
        ...

    async def fetch(
        self, league: LeagueConfig, season: SeasonRecord, store: "RawStore"
    ) -> list[RawDocument]:
        """Get the pages of one season and keep them in the store.

        Do not get a page again if the store has it already.
        """
        ...

    def parse(
        self,
        league: LeagueConfig,
        season: SeasonRecord,
        documents: list[RawDocument],
        store: "RawStore",
    ) -> list[SourceMatch]:
        """Read the stored pages and return one SourceMatch for each match."""
        ...
