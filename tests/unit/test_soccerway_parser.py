"""
Tests for the Soccerway parser in sources/soccerway/parser.py.

These tests read the saved fixture pages as text. They do not use a
browser or the network.
"""

from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Optional

import pytest
from pydantic import ValidationError

from african_football.models.source_match import MatchStatus, SourceMatch
from african_football.sources.soccerway.parser import (
    MatchPage,
    ResultRow,
    parse_match_page,
    parse_results_page,
    to_source_match,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "soccerway"


def _convert(
    row: ResultRow,
    page: Optional[MatchPage] = None,
    raw_documents: tuple[str, ...] = (),
) -> Optional[SourceMatch]:
    """Call to_source_match with the league context of the tests."""
    return to_source_match(
        row,
        page,
        league_code="npfl",
        season="2023/2024",
        timezone="Africa/Lagos",
        raw_documents=raw_documents,
    )


def _match(
    row: ResultRow,
    page: Optional[MatchPage] = None,
    raw_documents: tuple[str, ...] = (),
) -> SourceMatch:
    """Call _convert, and make sure that the result is a SourceMatch."""
    m = _convert(row, page, raw_documents)
    assert m is not None
    return m


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


@pytest.fixture(scope="module")
def league_rows() -> list[ResultRow]:
    return parse_results_page(_read("league_results.html"))


@pytest.fixture(scope="module")
def cup_rows() -> list[ResultRow]:
    return parse_results_page(_read("cup_results.html"))


def _row(**changes) -> ResultRow:
    """Make a played league row. Use `changes` to replace fields."""
    fields: dict[str, Any] = dict(
        match_id="h4zYGtCC",
        url="https://ng.soccerway.com/match/a/b/?mid=h4zYGtCC",
        stage="NPFL",
        round_name="Round 38",
        round_number=38,
        date="23.06.2024",
        indicator=None,
        home_team="Akwa United",
        away_team="Rivers United",
        home_score="3",
        away_score="1",
        home_pen=None,
        away_pen=None,
    )
    fields.update(changes)
    return ResultRow(**fields)


# ---------------------------------------------------------------------------
# parse_results_page
# ---------------------------------------------------------------------------


def test_results_page_regular_row(league_rows):
    first = league_rows[0]
    assert first.match_id == "h4zYGtCC"
    assert first.url.startswith("https://ng.soccerway.com/match/")
    assert (first.stage, first.round_name, first.round_number) == (
        "NPFL",
        "Round 38",
        38,
    )
    assert first.date == "23.06.2024"
    assert (first.home_team, first.away_team) == ("Akwa United", "Rivers United")
    assert (first.home_score, first.away_score) == ("3", "1")


def test_results_page_keeps_round_for_later_rows(league_rows):
    # Each row gets the round of the last round marker before it.
    # The fixture has two rows in Round 38, then one row in Round 35.
    assert [r.round_number for r in league_rows] == [38, 38, 35]


def test_results_page_penalty_row(cup_rows):
    final = next(r for r in cup_rows if r.round_name == "Final")
    assert (final.home_score, final.away_score) == ("0", "0")
    assert (final.home_pen, final.away_pen) == ("3", "4")
    assert final.round_number is None


def test_results_page_walkover_row(cup_rows):
    wo = next(r for r in cup_rows if r.round_name == "1/16-finals")
    assert wo.indicator == "WO"
    assert wo.home_score is None or not wo.home_score.isdigit()


def test_results_page_without_stages():
    assert parse_results_page("<html><body></body></html>") == []


# ---------------------------------------------------------------------------
# parse_match_page
# ---------------------------------------------------------------------------


def test_match_page_halftime_and_kickoff():
    page = parse_match_page(_read("match_page.html"))
    assert page.halftime == (2, 1)
    assert page.kickoff == datetime(2024, 6, 23, 16, 0)


def test_match_page_without_data():
    page = parse_match_page("<html><body><p>Not found</p></body></html>")
    assert page == MatchPage(halftime=None, kickoff=None)


# ---------------------------------------------------------------------------
# to_source_match
# ---------------------------------------------------------------------------


def test_played_match_with_match_page():
    page = MatchPage(halftime=(2, 1), kickoff=datetime(2024, 6, 23, 16, 0))
    m = _match(_row(), page, raw_documents=("aa", "bb"))
    assert m.status is MatchStatus.PLAYED
    assert (m.home_goals, m.away_goals) == (3, 1)
    assert (m.ht_home, m.ht_away) == (2, 1)
    assert m.match_date == date(2024, 6, 23)
    assert m.kickoff_local == time(16, 0)
    assert m.timezone == "Africa/Lagos"
    assert m.source == "soccerway"
    assert m.source_match_id == "h4zYGtCC"
    assert m.raw_documents == ("aa", "bb")


def test_date_from_row_when_no_match_page():
    m = _match(_row())
    assert m.match_date == date(2024, 6, 23)
    assert m.kickoff_local is None
    assert m.ht_home is None


def test_penalty_shootout_keeps_goals_and_penalties_apart():
    row = _row(home_score="0", away_score="0", home_pen="3", away_pen="4")
    m = _match(row)
    assert (m.home_goals, m.away_goals) == (0, 0)
    assert (m.pen_home, m.pen_away) == (3, 4)
    assert m.status is MatchStatus.PLAYED


def test_walkover_without_score():
    row = _row(indicator="WO", home_score="-", away_score="-")
    m = _match(row)
    assert m.status is MatchStatus.AWARDED
    assert m.home_goals is None and m.away_goals is None


def test_awarded_match_with_score():
    row = _row(indicator="AWRD", home_score="3", away_score="0")
    m = _match(row)
    assert m.status is MatchStatus.AWARDED
    assert (m.home_goals, m.away_goals) == (3, 0)


@pytest.mark.parametrize(
    "changes",
    [
        {"home_team": None},
        {"away_team": ""},
        {"home_score": "-", "away_score": "-"},
        {"away_score": None},
    ],
)
def test_unusable_row_gives_none(changes):
    assert _convert(_row(**changes)) is None


def test_bad_penalty_data_is_an_error():
    # A shootout after a 2-1 result is not possible.
    row = _row(home_score="2", away_score="1", home_pen="4", away_pen="3")
    with pytest.raises(ValidationError, match="needs a draw"):
        _convert(row)


def test_fixture_pages_give_valid_source_matches(league_rows, cup_rows):
    # All rows in the fixtures must give a valid SourceMatch, or None.
    for row in league_rows + cup_rows:
        _convert(row)
