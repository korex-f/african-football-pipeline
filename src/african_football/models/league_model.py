"""
models.py - Core data models for the African football pipeline.

Defines structured configuration objects used across the pipeline
to represent league metadata and scraping capabilties.
"""

from dataclasses import dataclass


@dataclass
class LeagueConfig:
    """
    Represents the configuration and scraping capabilities for a single football league.

    Attributes:
        code: Unique identifier for the league (e.g. 'npfl').
        name: Human-readable league name.
        country: Country slug as it appears in Soccerway URLs (e.g. 'nigeria').
        slug: League slug as it appears in Soccerway URLs (e.g. 'npfl').
        fetch_halftime: Whether halftime scores are available for this league.
        timezone:       The IANA timezone of the league, for example
                        'Africa/Accra'. The scraper shows all dates and
                        kick-off times in this timezone.
        fetch_venue:     Whether to scrape match venue (stadium). Defaults to False.
        fetch_lineups:   Whether to scrape match lineups. Defaults to False.
        fetch_scorers:   Whether to scrape goalscorers. Defaults to False.
        fetch_cards:     Whether to scrape bookings (yellow/red cards). Defaults to False.
        rsssf_index:     The RSSSF page with the list of champions, relative to
                         https://www.rsssf.org/, for example 'tablesn/nigchamp.html'.
                         Empty: the league has no RSSSF source.
        rsssf_section:   The heading of the list on rsssf_index that is this
                         league, for example 'National League'. Some pages have
                         lists of different competitions with the same seasons.
                         Empty: use all the lists on the page.
        rsssf_league:    A regular expression for the name of the national
                         league on the RSSSF season pages, for example
                         'Girabola|Campeonato Nacional'. Empty: the rules of
                         choose_league() decide (decision 24). Use it only
                         when the rules choose wrongly for this league.
    """

    code: str
    name: str
    country: str
    slug: str
    fetch_halftime: bool
    timezone: str
    submission_code: str = ""
    fetch_venue: bool = False
    fetch_lineups: bool = False
    fetch_scorers: bool = False
    fetch_cards: bool = False
    rsssf_index: str = ""
    rsssf_section: str = ""
    rsssf_league: str = ""
