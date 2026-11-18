"""
source_match.py — The match record that a source parser makes.

A SourceMatch holds the data that one source gives for one match.
It is not the final match record. If two sources give different
data, each source keeps its own SourceMatch. A later step compares
the records and makes the final record.

The parser converts the page text to Python values, for example
'3' to 3. This model does not convert values. It only checks them.
Thus, strict mode is on: a wrong type causes an error. It does not
silently become a different value.
"""

from datetime import date, time
from enum import StrEnum
from typing import Annotated, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# A number of goals. It cannot be less than zero.
Goals = Annotated[int, Field(ge=0)]

# A text that must contain one or more characters.
Text = Annotated[str, Field(min_length=1)]


class MatchStatus(StrEnum):
    """
    The result state of a match, as the source shows it.

    Attributes:
        PLAYED:    The teams played the match. The score is known.
        AWARDED:   An official decision gave the result. The teams did
                   not play the full match, for example a walkover.
                   The score is optional.
        ABANDONED: The match started but did not finish.
        POSTPONED: The match moved to a different date.
        CANCELLED: The match did not occur and will not occur.
        UNKNOWN:   The source does not show the state.
    """

    PLAYED = "played"
    AWARDED = "awarded"
    ABANDONED = "abandoned"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


# A match with one of these states has no score.
_NO_SCORE_STATUSES = {MatchStatus.POSTPONED, MatchStatus.CANCELLED}


class SourceMatch(BaseModel):
    """
    The data that one source gives for one match.

    Attributes:
        source:          The source name, for example 'soccerway'.
        source_match_id: The match identifier in the source.
        source_url:      The URL of the match in the source, if known.
        raw_documents:   The sha256 values of the stored pages that the
                         parser read to make this record.
        league_code:     The league code from leagues.yaml, for example 'gh_pl'.
        season:          The season label, for example '2023/2024'.
        stage:           The stage name, for example 'Premier League'.
        round_name:      The round text, for example 'Round 34' or 'Final'.
        round_number:    The round number, if the round has a number.
        match_date:      The date of the match in the league timezone.
        kickoff_local:   The kick-off time in the league timezone.
        timezone:        The IANA timezone of the date and the time.
        home_team_raw:   The home team name, as the source writes it.
        away_team_raw:   The away team name, as the source writes it.
        home_goals:      The home goals at the end of play. For a penalty
                         shootout, this is the score before the shootout.
        away_goals:      The away goals at the end of play.
        ht_home:         The home goals at halftime.
        ht_away:         The away goals at halftime.
        pen_home:        The home goals in the penalty shootout.
        pen_away:        The away goals in the penalty shootout.
        status:          The result state of the match.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    # Where the data came from
    source: Text
    source_match_id: Text
    source_url: Optional[str] = None
    raw_documents: tuple[str, ...] = ()

    # Context
    league_code: Text
    season: Text
    stage: Optional[str] = None
    round_name: Optional[str] = None
    round_number: Optional[Annotated[int, Field(ge=1)]] = None

    # When
    match_date: Optional[date] = None
    kickoff_local: Optional[time] = None
    timezone: Text

    # Teams
    home_team_raw: Text
    away_team_raw: Text

    # Result
    home_goals: Optional[Goals] = None
    away_goals: Optional[Goals] = None
    ht_home: Optional[Goals] = None
    ht_away: Optional[Goals] = None
    pen_home: Optional[Goals] = None
    pen_away: Optional[Goals] = None
    status: MatchStatus

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"unknown timezone: {value!r}") from None
        return value

    @model_validator(mode="after")
    def _consistent(self) -> "SourceMatch":
        # The checks below compare fields. Pydantic runs them after it
        # checks each field.
        if self.home_team_raw == self.away_team_raw:
            raise ValueError("the home team and the away team are the same")

        _check_pair("goals", self.home_goals, self.away_goals)
        _check_pair("halftime", self.ht_home, self.ht_away)
        _check_pair("penalty", self.pen_home, self.pen_away)

        has_goals = self.home_goals is not None
        if self.status is MatchStatus.PLAYED and not has_goals:
            raise ValueError("a played match must have a score")
        if self.status in _NO_SCORE_STATUSES and has_goals:
            raise ValueError(f"a {self.status} match cannot have a score")
        if self.ht_home is not None and not has_goals:
            raise ValueError("a halftime score needs a full-time score")
        if self.pen_home is not None:
            if self.status is not MatchStatus.PLAYED:
                raise ValueError("a penalty shootout needs a played match")
            if self.home_goals != self.away_goals:
                raise ValueError("a penalty shootout needs a draw")
            if self.pen_home == self.pen_away:
                raise ValueError("a penalty shootout cannot end in a draw")
        if self.kickoff_local is not None and self.match_date is None:
            raise ValueError("a kick-off time needs a match date")
        return self


def _check_pair(name: str, home: Optional[int], away: Optional[int]) -> None:
    """Raise an error if one value of a score pair is missing."""
    if (home is None) != (away is None):
        raise ValueError(f"the {name} score has only one value")
