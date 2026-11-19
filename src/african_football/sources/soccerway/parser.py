"""
parser.py — Read stored Soccerway pages and make match records.

This module does not use a browser or the network. It reads HTML text
with BeautifulSoup. Thus, you can parse the pages in the raw store
again, and the tests do not need Chromium.

The module has three levels:

    1. extract_stages:    reads the results page. It returns the same
                          data as EXTRACT_STAGE_JS in the old scraper.
                          A parity test compares the two.
    2. parse_results_page and parse_match_page: give typed data with
                          the round and the stage of each row.
    3. to_source_match:   converts the data to a SourceMatch. The
                          SourceMatch model checks the values.

Selectors: Soccerway uses the Flashscore frontend. Class names that
start with 'wcl-' have a build hash, for example 'wcl-name_jjfMf'.
The hash changes at each release. Thus, the selectors use only
'event__*' classes, data-testid attributes, and class prefixes
without the hash ([class*=...]).
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Optional

from bs4 import BeautifulSoup
from bs4.element import Comment, NavigableString, Tag

from african_football.models.source_match import MatchStatus, SourceMatch

BASE_URL = "https://ng.soccerway.com"
SOURCE_NAME = "soccerway"

# Results page
STAGE_HEADER = "div.headerLeague__wrapper"
STAGE_TITLE = ".headerLeague__title-text"
ROW_DATE = '[data-testid="wcl-stageTime"] [class*="wcl-dateContent"]'
ROW_INDICATOR = '[data-testid="wcl-stageTime"] [class*="wcl-stageContent"]'
ROW_HOME_TEAM = '.event__homeParticipant [class*="wcl-name"]'
ROW_AWAY_TEAM = '.event__awayParticipant [class*="wcl-name"]'
ROW_LINK = "a.eventRowLink"

# Match page
HALFTIME_LABEL = '[data-testid="wcl-overline-02"]'
KICKOFF_TIME = ".duelParticipant__startTime"

# Indicator texts that show an awarded result. The teams did not play.
AWARDED_INDICATORS = {"awrd", "wo"}

SCORE_PATTERN = re.compile(r"^(\d+)\s*-\s*(\d+)$")
KICKOFF_PATTERN = re.compile(r"^\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}$")
DATE_PATTERN = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")


# ---------------------------------------------------------------------------
# Small text functions
# ---------------------------------------------------------------------------


def clean_score(value: Optional[str]) -> Optional[str]:
    """Return the score if it is a number. If not (for example '-'), return None."""
    if value is None:
        return None
    value = value.strip()
    return value if value.isdigit() else None


def parse_kickoff(text: Optional[str]) -> Optional[str]:
    """
    Get the kick-off date and time from the text of a match page.

    Args:
        text: The kick-off text, for example '15.09.2023 19:30'.

    Returns:
        The kick-off as 'DD.MM.YYYY HH:MM'. If the text does not have
        this format, return None.
    """
    if text is None:
        return None
    text = " ".join(text.split())
    return text if KICKOFF_PATTERN.match(text) else None


def parse_round(round_text: str) -> Optional[int]:
    """
    Get the round number from a round header, for example 'Round 12'.

    Args:
        round_text: The text of the round header.

    Returns:
        The round number. For a round with a name (for example
        'Semi-finals'), return None.
    """
    lowered = round_text.lower()
    if "round" not in lowered:
        return None
    num_str = lowered.replace("round", "").strip()
    return int(num_str) if num_str.isdigit() else None


# ---------------------------------------------------------------------------
# Level 1: the same data as EXTRACT_STAGE_JS
# ---------------------------------------------------------------------------


def _text(root: Tag, selector: str) -> Optional[str]:
    """Return the stripped text of the first match of `selector`, or None.

    This is the same as `el.textContent.trim()` in JavaScript.
    """
    el = root.select_one(selector)
    return el.get_text().strip() if el else None


def _score(row: Tag, side: str) -> dict[str, Optional[str]]:
    """Return the main score and the penalty score of one side of a row.

    The main score is the direct text of the score element. The penalty
    shootout score is in a <sup> child, for example 0<sup>(3)</sup>.
    """
    el = row.select_one(f".event__score--{side}")
    if el is None:
        return {"main": None, "pen": None}
    # Use only the direct text nodes, not the text of the <sup> child.
    # A comment is also a NavigableString. Do not use it.
    main = "".join(
        str(node)
        for node in el.children
        if isinstance(node, NavigableString) and not isinstance(node, Comment)
    )
    sup = el.find("sup")
    pen = sup.get_text().replace("(", "").replace(")", "").strip() if sup else None
    return {"main": main.strip() or None, "pen": pen}


def _has_class(el: Tag, name: str) -> bool:
    return name in (el.get("class") or [])


def extract_stages(html: str) -> list[tuple[str, list[dict[str, Any]]]]:
    """
    Read all stages of a results page.

    Each stage has a header. The round markers and the match rows of the
    stage are the sibling elements after the header, until the next header.

    Args:
        html: The HTML of the results page, after all rows are loaded.

    Returns:
        A list of (stage_name, elements). The elements are in page
        sequence. Each element is a dict with the same keys as the
        output of EXTRACT_STAGE_JS:
            {'type': 'round', 'text': ...} or
            {'type': 'match', 'id': ..., 'date': ..., 'indicator': ...,
             'home_team': ..., 'away_team': ..., 'home_score': ...,
             'away_score': ..., 'home_pen': ..., 'away_pen': ..., 'link': ...}
    """
    soup = BeautifulSoup(html, "html.parser")
    headers = soup.select(STAGE_HEADER)
    stages = []

    for idx, header in enumerate(headers):
        title = _text(header, STAGE_TITLE)
        stage_name = title if title else f"Stage {idx + 1}"
        next_header = headers[idx + 1] if idx + 1 < len(headers) else None
        elements: list[dict[str, Any]] = []

        for el in header.next_siblings:
            if el is next_header:
                break
            if not isinstance(el, Tag):
                continue
            if _has_class(el, "event__round"):
                elements.append({"type": "round", "text": el.get_text().strip()})
            elif _has_class(el, "event__match"):
                home = _score(el, "home")
                away = _score(el, "away")
                link = el.select_one(ROW_LINK)
                elements.append(
                    {
                        "type": "match",
                        "id": el.get("id") or "",
                        "date": _text(el, ROW_DATE),
                        "indicator": _text(el, ROW_INDICATOR),
                        "home_team": _text(el, ROW_HOME_TEAM),
                        "away_team": _text(el, ROW_AWAY_TEAM),
                        "home_score": home["main"],
                        "away_score": away["main"],
                        "home_pen": home["pen"],
                        "away_pen": away["pen"],
                        "link": link.get("href") if link else None,
                    }
                )
        stages.append((stage_name, elements))

    return stages


# ---------------------------------------------------------------------------
# Level 2: typed data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultRow:
    """
    One match row of a results page, with its stage and round.

    The values are the page text. The scores are not numbers yet.

    Attributes:
        match_id:     The Soccerway match ID, for example 'h4zYGtCC'.
        url:          The full URL of the match page, or None.
        stage:        The stage name, for example 'NPFL'.
        round_name:   The round text, for example 'Round 38', or None.
        round_number: The round number, or None.
        date:         The date text, for example '23.06.2024', or None.
        indicator:    The text below the date, for example 'Pen' or 'WO'.
        home_team:    The home team name, or None.
        away_team:    The away team name, or None.
        home_score:   The home score text, or None.
        away_score:   The away score text, or None.
        home_pen:     The home penalty shootout score text, or None.
        away_pen:     The away penalty shootout score text, or None.
    """

    match_id: str
    url: Optional[str]
    stage: str
    round_name: Optional[str]
    round_number: Optional[int]
    date: Optional[str]
    indicator: Optional[str]
    home_team: Optional[str]
    away_team: Optional[str]
    home_score: Optional[str]
    away_score: Optional[str]
    home_pen: Optional[str]
    away_pen: Optional[str]


@dataclass(frozen=True)
class MatchPage:
    """
    The data from one match page.

    Attributes:
        halftime: The halftime score as (home, away), or None.
        kickoff:  The kick-off date and time in the browser timezone, or None.
    """

    halftime: Optional[tuple[int, int]]
    kickoff: Optional[datetime]


def _absolute_url(link: Optional[str]) -> Optional[str]:
    if not link:
        return None
    return link if link.startswith("http") else f"{BASE_URL}{link}"


def parse_results_page(html: str) -> list[ResultRow]:
    """
    Read a results page and return one ResultRow for each match row.

    A round marker sets the round of the rows after it. A row without
    an ID is not included, because the pipeline cannot identify it.

    Args:
        html: The HTML of the results page, after all rows are loaded.

    Returns:
        The rows of all stages, in page sequence.
    """
    rows = []
    for stage_name, elements in extract_stages(html):
        round_name: Optional[str] = None
        round_number: Optional[int] = None
        for el in elements:
            if el["type"] == "round":
                round_name = el["text"]
                round_number = parse_round(el["text"])
                continue
            # The ID has the format 'g_1_h4zYGtCC'. The match ID is the last part.
            match_id = el["id"].rsplit("_", 1)[-1]
            if not match_id:
                continue
            rows.append(
                ResultRow(
                    match_id=match_id,
                    url=_absolute_url(el["link"]),
                    stage=stage_name,
                    round_name=round_name,
                    round_number=round_number,
                    date=el["date"],
                    indicator=el["indicator"],
                    home_team=el["home_team"],
                    away_team=el["away_team"],
                    home_score=el["home_score"],
                    away_score=el["away_score"],
                    home_pen=el["home_pen"],
                    away_pen=el["away_pen"],
                )
            )
    return rows


def parse_match_page(html: str) -> MatchPage:
    """
    Read a match page and return the halftime score and the kick-off.

    The halftime score is the element after the '1st Half' label.
    If a value is not on the page, it is None.

    Args:
        html: The HTML of the match page.

    Returns:
        A MatchPage.
    """
    soup = BeautifulSoup(html, "html.parser")

    halftime = None
    for label in soup.select(HALFTIME_LABEL):
        if label.get_text().strip() != "1st Half":
            continue
        value = label.find_next_sibling("span")
        found = SCORE_PATTERN.match(value.get_text().strip()) if value else None
        if found:
            halftime = (int(found.group(1)), int(found.group(2)))
        break

    kickoff = None
    kickoff_text = parse_kickoff(_text(soup, KICKOFF_TIME))
    if kickoff_text:
        kickoff = datetime.strptime(kickoff_text, "%d.%m.%Y %H:%M")

    return MatchPage(halftime=halftime, kickoff=kickoff)


# ---------------------------------------------------------------------------
# Level 3: SourceMatch
# ---------------------------------------------------------------------------


def _to_int(value: Optional[str]) -> Optional[int]:
    cleaned = clean_score(value)
    return int(cleaned) if cleaned is not None else None


def _row_date(text: Optional[str]) -> Optional[date]:
    if text and DATE_PATTERN.match(text.strip()):
        return datetime.strptime(text.strip(), "%d.%m.%Y").date()
    return None


def to_source_match(
    row: ResultRow,
    page: Optional[MatchPage],
    *,
    league_code: str,
    season: str,
    timezone: str,
    raw_documents: tuple[str, ...] = (),
) -> Optional[SourceMatch]:
    """
    Make a SourceMatch from a results row and its match page.

    Rules:
      - A row without two team names gives None.
      - The indicator 'AWRD' or 'WO' gives an awarded match. A walkover
        can have no score.
      - A row that is not awarded and has no score gives None. The old
        scraper has the same rule.
      - The date and the kick-off time come from the match page. If the
        page has no kick-off, the date comes from the results row.

    Args:
        row:           The results row.
        page:          The data from the match page, or None.
        league_code:   The league code, for example 'npfl'.
        season:        The season label, for example '2023/2024'.
        timezone:      The timezone that the browser used for the pages.
        raw_documents: The sha256 values of the pages that gave the data.

    Returns:
        A SourceMatch, or None if the row has no usable match.

    Raises:
        pydantic.ValidationError: The data breaks a rule of SourceMatch,
            for example a penalty shootout without a draw.
    """
    if not row.home_team or not row.away_team:
        return None

    awarded = (row.indicator or "").strip().lower() in AWARDED_INDICATORS
    home_goals, away_goals = _to_int(row.home_score), _to_int(row.away_score)
    has_goals = home_goals is not None and away_goals is not None
    if not has_goals and not awarded:
        return None
    if not has_goals:
        home_goals = away_goals = None

    pen_home = pen_away = None
    if not awarded:
        pen_home, pen_away = _to_int(row.home_pen), _to_int(row.away_pen)
        if pen_home is None or pen_away is None:
            pen_home = pen_away = None

    match_date: Optional[date] = None
    kickoff_local: Optional[time] = None
    if page and page.kickoff:
        match_date, kickoff_local = page.kickoff.date(), page.kickoff.time()
    else:
        match_date = _row_date(row.date)

    ht_home = ht_away = None
    if page and page.halftime and has_goals:
        ht_home, ht_away = page.halftime

    return SourceMatch(
        source=SOURCE_NAME,
        source_match_id=row.match_id,
        source_url=row.url,
        raw_documents=raw_documents,
        league_code=league_code,
        season=season,
        stage=row.stage,
        round_name=row.round_name,
        round_number=row.round_number,
        match_date=match_date,
        kickoff_local=kickoff_local,
        timezone=timezone,
        home_team_raw=row.home_team.strip(),
        away_team_raw=row.away_team.strip(),
        home_goals=home_goals,
        away_goals=away_goals,
        ht_home=ht_home,
        ht_away=ht_away,
        pen_home=pen_home,
        pen_away=pen_away,
        status=MatchStatus.AWARDED if awarded else MatchStatus.PLAYED,
    )
