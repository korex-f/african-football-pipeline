"""Tests for the SourceMatch model and its checks."""

from datetime import date, time

import pytest
from pydantic import ValidationError

from african_football.models.source_match import MatchStatus, SourceMatch


def _match(**changes) -> SourceMatch:
    """Make a valid played match. Use `changes` to replace fields."""
    fields = dict(
        source="soccerway",
        source_match_id="ttkJbibi",
        league_code="gh_pl",
        season="2023/2024",
        timezone="Africa/Accra",
        home_team_raw="Asante Kotoko",
        away_team_raw="Bofoakwa Tano",
        home_goals=3,
        away_goals=1,
        status=MatchStatus.PLAYED,
    )
    fields.update(changes)
    return SourceMatch(**fields)


def test_valid_played_match():
    m = _match(
        ht_home=3,
        ht_away=0,
        match_date=date(2024, 6, 16),
        kickoff_local=time(15, 0),
    )
    assert (m.home_goals, m.away_goals) == (3, 1)
    assert m.status is MatchStatus.PLAYED


def test_record_is_frozen():
    m = _match()
    with pytest.raises(ValidationError):
        m.home_goals = 4


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        _match(venue="Baba Yara Stadium")


@pytest.mark.parametrize("field", ["home_goals", "ht_home", "round_number"])
def test_strict_mode_rejects_text_numbers(field):
    # The parser must convert '3' to 3. The model does not do it.
    with pytest.raises(ValidationError):
        _match(**{field: "3"})


def test_strict_mode_rejects_text_date():
    with pytest.raises(ValidationError):
        _match(match_date="16.06.2024")


def test_negative_goals_are_rejected():
    with pytest.raises(ValidationError):
        _match(home_goals=-1)


def test_unknown_timezone_is_rejected():
    with pytest.raises(ValidationError, match="unknown timezone"):
        _match(timezone="Africa/Atlantis")


def test_same_teams_are_rejected():
    with pytest.raises(ValidationError, match="same"):
        _match(away_team_raw="Asante Kotoko")


@pytest.mark.parametrize(
    "changes",
    [
        {"away_goals": None},
        {"ht_home": 1},
        {"pen_home": 4, "home_goals": 1, "away_goals": 1},
    ],
)
def test_score_pair_with_one_value_is_rejected(changes):
    with pytest.raises(ValidationError, match="only one value"):
        _match(**changes)


def test_played_match_needs_score():
    with pytest.raises(ValidationError, match="must have a score"):
        _match(home_goals=None, away_goals=None)


def test_awarded_match_can_have_no_score():
    m = _match(status=MatchStatus.AWARDED, home_goals=None, away_goals=None)
    assert m.home_goals is None


@pytest.mark.parametrize("status", [MatchStatus.POSTPONED, MatchStatus.CANCELLED])
def test_postponed_or_cancelled_match_cannot_have_score(status):
    with pytest.raises(ValidationError, match="cannot have a score"):
        _match(status=status)


def test_halftime_needs_full_time():
    with pytest.raises(ValidationError, match="needs a full-time score"):
        _match(
            status=MatchStatus.ABANDONED,
            home_goals=None,
            away_goals=None,
            ht_home=1,
            ht_away=0,
        )


def test_valid_penalty_shootout():
    m = _match(home_goals=0, away_goals=0, pen_home=3, pen_away=4)
    assert (m.pen_home, m.pen_away) == (3, 4)


def test_penalty_shootout_needs_draw():
    with pytest.raises(ValidationError, match="needs a draw"):
        _match(pen_home=3, pen_away=4)


def test_penalty_shootout_cannot_end_in_draw():
    with pytest.raises(ValidationError, match="cannot end in a draw"):
        _match(home_goals=1, away_goals=1, pen_home=4, pen_away=4)


def test_kickoff_needs_date():
    with pytest.raises(ValidationError, match="needs a match date"):
        _match(kickoff_local=time(15, 0))
