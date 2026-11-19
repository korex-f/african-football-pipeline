"""
Tests for the legacy exporter in exports/legacy.py.

The parity tests compare two methods on the same fixture pages:
    - Old: parse_match_row from the old scraper.
    - New: the Python parser, then SourceMatch, then the legacy exporter.
The output must be the same.

These tests do not use a browser. The data of extract_stages is the same
as the data of the JavaScript parser (see test_soccerway_parser_parity.py).
"""

from datetime import date, time
from pathlib import Path
from typing import Any, Optional

import pytest

from african_football.exports.legacy import to_legacy_match, to_legacy_stages
from african_football.models.source_match import MatchStatus, SourceMatch
from african_football.scraping.scraper import parse_match_row
from african_football.sources.soccerway.parser import (
    MatchPage,
    extract_stages,
    parse_match_page,
    parse_results_page,
    parse_round,
    to_source_match,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "soccerway"
CONTEXT: dict[str, Any] = dict(
    league_code="npfl", season="2023/2024", timezone="Africa/Lagos"
)


def _old_method(html: str) -> list[dict[str, Any]]:
    """Make the match dictionaries with the old scraper functions."""
    matches = []
    for stage_name, elements in extract_stages(html):
        round_name, round_number = None, None
        for el in elements:
            if el["type"] == "round":
                round_name, round_number = el["text"], parse_round(el["text"])
            else:
                match = parse_match_row(el, round_name, round_number, stage_name)
                if match:
                    matches.append(match)
    return matches


def _new_method(html: str, page: Optional[MatchPage] = None) -> list[dict[str, Any]]:
    """Make the match dictionaries with the parser and the legacy exporter."""
    matches = []
    for row in parse_results_page(html):
        source_match = to_source_match(row, page, **CONTEXT)
        if source_match:
            matches.append(to_legacy_match(source_match))
    return matches


def _match(**changes: Any) -> SourceMatch:
    """Make a valid played match. Use `changes` to replace fields."""
    fields: dict[str, Any] = dict(
        source="soccerway",
        source_match_id="h4zYGtCC",
        source_url="https://ng.soccerway.com/match/a/b/?mid=h4zYGtCC",
        stage="NPFL",
        round_name="Round 38",
        round_number=38,
        match_date=date(2024, 6, 23),
        home_team_raw="Akwa United",
        away_team_raw="Rivers United",
        home_goals=3,
        away_goals=1,
        status=MatchStatus.PLAYED,
        **CONTEXT,
    )
    fields.update(changes)
    return SourceMatch(**fields)


# ---------------------------------------------------------------------------
# Parity with the old scraper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fixture", ["league_results.html", "cup_results.html"])
def test_exporter_gives_same_output_as_old_scraper(fixture):
    html = (FIXTURES / fixture).read_text()
    old, new = _old_method(html), _new_method(html)

    assert len(new) == len(old)
    for new_match, old_match in zip(new, old):
        # Compare the key sequence too. The JSON files must have the same text.
        assert list(new_match) == list(old_match)
        assert new_match == old_match


def test_exporter_gives_same_output_with_match_page():
    # The old scraper changes 'date' and 'half_time_score' after it reads
    # the match page. The values come from the match page fixture.
    html = (FIXTURES / "league_results.html").read_text()
    page = parse_match_page((FIXTURES / "match_page.html").read_text())

    old = _old_method(html)[0]
    old["date"] = "23.06.2024 16:00"
    old["half_time_score"] = "2 - 1"

    assert _new_method(html, page)[0] == old


# ---------------------------------------------------------------------------
# to_legacy_match
# ---------------------------------------------------------------------------


def test_regular_match():
    m = to_legacy_match(_match(ht_home=2, ht_away=1, kickoff_local=time(16, 0)))
    assert m["date"] == "23.06.2024 16:00"
    assert (m["home_score"], m["away_score"]) == ("3", "1")
    assert m["half_time_score"] == "2 - 1"
    assert m["awarded"] is False and m["awarded_reason"] is None
    assert m["penalty_shootout"] is False and m["penalty_winner"] is None
    assert m["full_time_score"] is None


def test_penalty_shootout_uses_the_legacy_rule():
    m = to_legacy_match(_match(home_goals=0, away_goals=0, pen_home=3, pen_away=4))
    assert (m["home_score"], m["away_score"]) == ("3", "4")
    assert m["full_time_score"] == "0-0"
    assert m["penalty_shootout"] is True
    assert m["penalty_winner"] == "away"


def test_penalty_winner_home():
    m = to_legacy_match(_match(home_goals=1, away_goals=1, pen_home=5, pen_away=4))
    assert m["penalty_winner"] == "home"


def test_walkover_without_score():
    m = to_legacy_match(
        _match(status=MatchStatus.AWARDED, home_goals=None, away_goals=None)
    )
    assert m["home_score"] is None and m["away_score"] is None
    assert m["awarded"] is True
    assert m["awarded_reason"] == "walkover"


def test_no_date_gives_empty_text():
    assert to_legacy_match(_match(match_date=None))["date"] == ""


# ---------------------------------------------------------------------------
# to_legacy_stages
# ---------------------------------------------------------------------------


def test_stages_keep_sequence_and_counts():
    matches = [
        _match(source_match_id="a", stage="Group A", round_number=2),
        _match(source_match_id="b", stage="Group A", round_number=5),
        _match(
            source_match_id="c", stage="Final", round_name="Final", round_number=None
        ),
    ]
    stages = to_legacy_stages(matches)

    assert [s["stage_name"] for s in stages] == ["Group A", "Final"]
    assert [s["total_matches"] for s in stages] == [2, 1]
    assert stages[0]["total_rounds"] == 5
    assert stages[1]["total_rounds"] == 0
    assert list(stages[0]) == ["stage_name", "total_rounds", "total_matches", "matches"]


def test_no_matches_gives_no_stages():
    assert to_legacy_stages([]) == []
