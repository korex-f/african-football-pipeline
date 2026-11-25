"""
source_table.py: one row of a final table, as one source gives it.

RSSSF pages have the final table of the league (roadmap step 4.3). The
table is a second record of the season: the number of matches and the
goals of the table must agree with the matches (decision 7). Thus the
pipeline keeps the tables.

The model is Pydantic, the same as SourceMatch (decision 8): the data comes
from a source, thus each row is checked. A row where won + drawn + lost is
not played is not a valid row.
"""

from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

Count = Annotated[int, Field(ge=0)]
Text = Annotated[str, Field(min_length=1)]


class SourceTableRow(BaseModel):
    """
    One row of a final table from one source.

    Attributes:
        source:        The source name, for example 'rsssf'.
        league_code:   The league code from leagues.yaml.
        season:        The season label, for example '2023/2024'.
        stage:         The stage or the group of the table, for example the
                       league name or 'Group A'.
        row_number:    The sequence of the row in its table, from 1. The
                       position can be the same for two rows; row_number is
                       always different.
        position:      The position that the source gives, for example 1.
        team_raw:      The team name, as the source writes it in the table.
        played, won, drawn, lost: The numbers of matches.
        goals_for, goals_against: The goals.
        points:        The points. Can be negative after a deduction.
        note:          The text after the points, for example
                       'Champions' or '[-3] Relegated', or None.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    source: Text
    league_code: Text
    season: Text
    stage: Text
    row_number: Annotated[int, Field(ge=1)]
    position: Annotated[int, Field(ge=1)]
    team_raw: Text
    played: Count
    won: Count
    drawn: Count
    lost: Count
    goals_for: Count
    goals_against: Count
    points: int
    note: Optional[str] = None

    @model_validator(mode="after")
    def _consistent(self) -> "SourceTableRow":
        if self.won + self.drawn + self.lost != self.played:
            raise ValueError(
                f"won + drawn + lost ({self.won} + {self.drawn} + {self.lost}) "
                f"is not played ({self.played})"
            )
        return self
