"""
tables.py: read the final tables of the top league from an RSSSF season page,
and compare a table with the matches.

The project examined the tables of the 187 season pages of the NPFL, Ghana
and Egypt (decision 23):

- A final table has the heading 'Final Table:' (286 times), or 'Final
  Tables:' with groups (34 times). Other headings are not final: 'Table:'
  (a table in the middle of the season), 'Table before last round:',
  'Table at abandonment:'.
- The main row form is:

      1.Enyimba FC (Aba)        38  21  9  8  63-22  72  Champions
     10.Al-Jaish                26   7  9 10  23-33  30  [aka Army Club]
      1.Zamalek                 14  12  2  0  34- 9  26

  position, team, played, won, drawn, lost, goals for-against, points, and a
  note. About 200 rows of the 17,000 have other forms (only the goal
  difference, '+5??', a typo). The reader does not guess: such a row is a
  problem.
- In 'Final Tables:', a group heading is a plain line ('Group A', 'Group 1').
- A page can have the final table two times: before the results and after
  them. The first table of a stage is used. A later table of the same stage
  is compared with it: if it is different, it is a problem.

table_check() compares a table with the matches without team names. The
names in a table ('Enyimba FC (Aba)') are often not the names in the results
('Enyimba').
"""

import re
from dataclasses import dataclass
from typing import Optional

from pydantic import ValidationError

from african_football.models.source_match import MatchStatus, SourceMatch
from african_football.models.source_table import SourceTableRow
from african_football.sources.rsssf.parser import (
    _STAGE_TAG,
    _TABLE_ROW,
    _clean,
    _clean_line,
    _has_results,
    choose_league,
    season_part,
    split_competitions,
)

# The heading of a final table: 'Final Table:', 'Final Tables:',
# 'Final Table (given by press):'. Not 'Final table missing.'.
# Decision 26 adds up to 3 words before it ('Reported Final Table:', 'Super
# Division Final Table:'), a note in brackets ('Final (official) Table:'),
# 'Final Ranking:', 'Final Standings:' and 'Official Table ...:'. A heading
# that starts with 'Top' ('Top of Final Table:') has only the top rows: it
# is not a final table.
_FINAL_HEADING = re.compile(
    r"^\s*(?!top\b)(?:[\w.'-]+ ){0,3}"
    r"(?:final\s*(?:\([^)]*\)\s*)?(?:tables?|ranking|standings)|official\s+tables?)\b"
    # A heading ends with ':', or has only a note in brackets after the
    # words. Thus 'Final table missing.' and 'The final table was not
    # published.' are not headings.
    r"(?:[^:]*:|\s*\([^)]*\))?\s*$",
    re.IGNORECASE,
)

# The heading of a plain table (decision 26): 'Table:', 'Tables:',
# 'Reported Table:', 'Table (Jan 30):', 'Table [June 89]:'. Not a table
# that the author made from the known results ('Table (based on known
# results):'): it agrees with the results by construction, thus it is not
# an independent check.
_PLAIN_HEADING = re.compile(
    r"^\s*(?:Reported\s+)?Tables?\s*"
    r"(?:[(\[](?![^)\]]*(?:based on|known results|compiled|calculated))[^)\]]*[)\]])?"
    r"\s*:\s*$",
    re.IGNORECASE,
)

# Any other table heading ends a final table: 'Table:', 'Table before last
# round:'.
_OTHER_TABLE = re.compile(r"^\s*(?:\w+ )*Tables?\b.*:\s*$", re.IGNORECASE)

# 'drawn' can be two numbers: '13  7/ 5  5' (Nigeria 1991 and 1992, when a
# score draw and a goalless draw gave different points). Then drawn = 7 + 5.
_POSITION_TEAM = r"^\s*(?P<position>\d+)\.\s*(?P<team>\S(?:.*?\S)?)"
# The points, with an optional mark for a footnote ('5*'), and the note.
_POINTS_NOTE = r"\s+(?P<points>-?\d+)(?P<mark>\*)?(?:\s+(?P<note>\S.*?))?\s*$"
_ROW = re.compile(
    _POSITION_TEAM + r"\s+(?P<played>\d+)\s+(?P<won>\d+)"
    r"\s+(?P<drawn>\d+)(?:\s*/\s*(?P<drawn2>\d+))?\s+(?P<lost>\d+)"
    r"\s+(?P<gf>\d+)\s*-\s*(?P<ga>\d+)" + _POINTS_NOTE
)

# Two more forms of a full row (decision 27). The goals in two columns,
# without '-': ' 1. Cotonsport Garoua  30 19  4  7  41  17  58  Champions'.
_ROW_GOAL_COLUMNS = re.compile(
    _POSITION_TEAM + r"\s+(?P<played>\d+)\s+(?P<won>\d+)\s+(?P<drawn>\d+)"
    r"\s+(?P<lost>\d+)\s+(?P<gf>\d+)\s+(?P<ga>\d+)" + _POINTS_NOTE
)
# The points first (Réunion, with 4 points for a win):
# ' 1.JS St Pierroise   65  22  13  4  5  33- 20'.
_ROW_POINTS_FIRST = re.compile(
    _POSITION_TEAM + r"\s+(?P<points>-?\d+)\s+(?P<played>\d+)\s+(?P<won>\d+)"
    r"\s+(?P<drawn>\d+)\s+(?P<lost>\d+)\s+(?P<gf>\d+)\s*-\s*(?P<ga>\d+)"
    r"(?P<mark>)(?:\s+(?P<note>\S.*?))?\s*$"
)
_ROW_FORMS = (_ROW, _ROW_GOAL_COLUMNS, _ROW_POINTS_FIRST)

# A table row has a number after a space, after the team name. A numbered
# list of teams ('1.Stationery Stores FC, Lagos;') has none. A team name can
# start with a digit ('9.3SC Shooting Stars'), thus the check looks for a
# number after a space, not for any digit.
_HAS_NUMBERS = re.compile(r"^\s*\d+\.\s*\S.*\s\d")

# A group heading in a 'Final Tables:' block: 'Group A', 'Group A:', and
# the French and Portuguese words (decision 26): 'Poule A', 'Groupe A',
# 'Grupo A'. A note in brackets can follow: 'Group A (Algiers):'.
_GROUP = re.compile(
    r"^\s*(?P<name>(?:Group|Groupe|Grupo|Poule|Zone|Pool|Conference) \w+)"
    r"\s*(?:\(.*\))?\s*:?\s*$",
    re.IGNORECASE,
)

# Lines that can be in a table: a separator line, or the next line of a note.
_IN_TABLE = re.compile(r"^\s*(?:[-=][ -=]*)?$|^\s{2,}\S")


@dataclass(frozen=True)
class TableCheck:
    """
    The comparison of one table (one stage) with the matches of that stage.

    table_matches:   the sum of 'played' in the table, divided by 2.
    found_matches:   the played and awarded matches with a score.
    table_goals:     the sum of 'goals for' in the table.
    match_goals:     the sum of the goals of the matches with a score.
    agrees:          True if the two numbers of matches agree and the two
                     numbers of goals agree.
    """

    stage: str
    table_matches: float
    found_matches: int
    table_goals: int
    match_goals: int

    @property
    def agrees(self) -> bool:
        return (
            self.table_matches == self.found_matches
            and self.table_goals == self.match_goals
        )


def parse_tables(
    page: str,
    *,
    league_code: str,
    season: str,
    anchor: str = "",
    league_pattern: str = "",
) -> tuple[list[SourceTableRow], list[str]]:
    """Give the rows of the final tables of the top league, and the problems.

    The top league is the same competition as in parser.parse_page(), or the
    first competition of a page without results. A
    problem is a row in a final table that does not have the main form, or
    that is not a valid SourceTableRow.
    """
    if anchor:
        part = season_part(page, anchor)
        if part is None:
            return [], []
        page = part
    # A page with only tables (no results) has no top league in
    # parser.top_league(). Its first competition is the league.
    # The same choice as parser.parse_page() (decision 24). A page with only
    # tables has no competition with results: choose_league() then gives the
    # first league with a final table, else the first competition.
    competitions = split_competitions(page)
    if not competitions:
        return [], []
    choice = choose_league(competitions, league_pattern)
    if choice.competition is not None:
        competition = choice.competition
    elif choice.alternatives:
        # The page has competitions with data, and the rules decided that
        # none of them is the league (for example regional leagues only).
        return [], []
    else:
        # No competition with results or a final-table heading: a season
        # part with only a table (the history pages).
        competition = competitions[0]
    has_results = _has_results(competition)
    lines = competition.text.splitlines()

    tables: dict[str, list[SourceTableRow]] = {}
    current: list[SourceTableRow] = []
    problems: list[str] = []
    stage = competition.name
    # A part of a page with only a table, without a heading (the history
    # pages: '<a name="64">1963/64</a>' and then the rows) is a final table.
    in_final = not has_results and not any(
        _FINAL_HEADING.match(_clean_line(line)) or _OTHER_TABLE.match(_clean_line(line))
        for line in lines
    )
    row_number = 0

    # A plain table ('Table:', 'Reported Table:', or a group heading outside
    # a final block) can be the final table of its stage (decision 26). The
    # last plain table of each stage is a candidate: (rows, all rows read).
    plain_stage: Optional[str] = None
    plain_rows: list[SourceTableRow] = []
    plain_read = True
    candidates: dict[str, tuple[list[SourceTableRow], bool]] = {}

    def close_table() -> None:
        """Keep the rows of the table that ends now."""
        nonlocal current
        if current:
            first = tables.setdefault(current[0].stage, current)
            if first is not current and _values(first) != _values(current):
                problems.append(
                    f"two different final tables for the stage {current[0].stage!r}"
                )
        current = []

    def close_plain() -> None:
        """Keep the plain table that ends now as the candidate of its stage."""
        nonlocal plain_stage, plain_rows, plain_read
        if plain_stage is not None and (plain_rows or not plain_read):
            candidates[plain_stage] = (plain_rows, plain_read)
        plain_stage, plain_rows, plain_read = None, [], True

    for raw_line in lines:
        stage_tag = _STAGE_TAG.match(raw_line)
        if stage_tag is not None:
            close_table()
            close_plain()
            stage = _clean(stage_tag["text"])
            in_final = False
            continue
        line = _clean_line(raw_line)

        if _FINAL_HEADING.match(line):
            close_table()
            close_plain()
            in_final = True
            row_number = 0
            continue

        if in_final:
            group = _GROUP.match(line)
            if group is not None:
                close_table()
                stage = _clean(group["name"])
                row_number = 0
                continue
            if _TABLE_ROW.match(line):
                if not _HAS_NUMBERS.search(line):
                    # A numbered list of teams ('1.Stationery Stores FC,
                    # Lagos;'), not a table row.
                    continue
                row_number += 1
                row, problem = _table_row(line, league_code, season, stage, row_number)
                if row is not None:
                    current.append(row)
                if problem is not None:
                    problems.append(problem)
                continue
            if (
                _IN_TABLE.match(line)
                or _OTHER_TABLE.match(line) is None
                and row_number == 0
            ):
                # A blank line, a separator, the next line of a note, or a
                # line between the heading and the first row ('NB: ...').
                continue
            # Any other line ends the final table. It can be the heading of
            # a plain table.
            close_table()
            in_final = False

        plain_heading = _PLAIN_HEADING.match(line)
        group = _GROUP.match(line)
        if plain_heading is not None or group is not None:
            close_plain()
            plain_stage = _clean(group["name"]) if group is not None else stage
            continue
        if plain_stage is None:
            continue
        if _TABLE_ROW.match(line) and _HAS_NUMBERS.search(line):
            row, problem = _table_row(
                line, league_code, season, plain_stage, len(plain_rows) + 1
            )
            if row is None or problem is not None:
                plain_read = False
            else:
                plain_rows.append(row)
            continue
        if _IN_TABLE.match(line) or (not plain_rows and plain_read):
            # A blank line, a separator, a next line of a note, or a line
            # between the heading and the first row.
            continue
        close_plain()
    close_table()
    close_plain()

    for plain_stage_name, (stage_rows, all_read) in candidates.items():
        if (
            plain_stage_name not in tables
            and all_read
            and _complete_double_round_robin(stage_rows)
        ):
            tables[plain_stage_name] = stage_rows

    rows = [row for stage_rows in tables.values() for row in stage_rows]
    # A row that is not valid is in the first table and in the copy: report
    # it one time.
    return rows, list(dict.fromkeys(problems))


def _table_row(
    line: str, league_code: str, season: str, stage: str, row_number: int
) -> tuple[Optional[SourceTableRow], Optional[str]]:
    """Give the SourceTableRow of a table line, or the problem of the line.

    The forms are tried in sequence: the main form, the goals in two
    columns, the points first. The first form that matches is used. The
    model then checks that won + drawn + lost is played: a row read in a
    wrong order is a problem, not a row.
    """
    row = next((m for m in (form.match(line) for form in _ROW_FORMS) if m), None)
    if row is None:
        return None, f"table row not read: {line.strip()}"
    note = " ".join(part for part in (row["mark"], row["note"]) if part) or None
    try:
        return (
            SourceTableRow(
                source="rsssf",
                league_code=league_code,
                season=season,
                stage=stage,
                row_number=row_number,
                position=int(row["position"]),
                team_raw=row["team"],
                played=int(row["played"]),
                won=int(row["won"]),
                drawn=int(row["drawn"]) + int(row.groupdict().get("drawn2") or 0),
                lost=int(row["lost"]),
                goals_for=int(row["gf"]),
                goals_against=int(row["ga"]),
                points=int(row["points"]),
                note=note,
            ),
            None,
        )
    except ValidationError as error:
        return None, f"table row not valid: {line.strip()}: {error.errors()[0]['msg']}"


def _complete_double_round_robin(rows: list[SourceTableRow]) -> bool:
    """True if each of the n teams (3 or more) played 2(n - 1) matches, and
    the positions go from 1 to n.

    A plain table with this property is the final table of a double
    round-robin (decision 26). A table after the first half of such a
    season has n - 1 matches for each team, thus it does not pass. A single
    round-robin (n - 1) does not pass either: it looks the same as a table
    at half-way. The positions find a part of a table: Benin 2017 gives the
    rows 2, 3 and 6 of a play-off, with 4 matches each.
    """
    n = len(rows)
    return (
        n >= 3
        and rows[0].position == 1
        and rows[-1].position == n
        and all(row.played == 2 * (n - 1) for row in rows)
    )


def table_check(
    rows: list[SourceTableRow], matches: list[SourceMatch]
) -> list[TableCheck]:
    """Compare each table (one for each stage) with the matches of the stage.

    A table stage with the same name as a match stage ('Group A' in both) is
    compared with the matches of that stage. The other table stages are
    compared together with all the other matches. This is the usual case:
    the league table has the name of the competition, and the matches too;
    or a page has the groups only as plain lines in the tables.
    """
    by_stage: dict[str, list[SourceTableRow]] = {}
    for row in rows:
        by_stage.setdefault(row.stage, []).append(row)
    match_stages = {m.stage for m in matches}

    checks = []
    pooled_rows: list[SourceTableRow] = []
    pooled_names: list[str] = []
    for stage, stage_rows in by_stage.items():
        if stage in match_stages:
            checks.append(
                _check(stage, stage_rows, [m for m in matches if m.stage == stage])
            )
        else:
            pooled_rows += stage_rows
            pooled_names.append(stage)
    if pooled_rows:
        other = [m for m in matches if m.stage not in by_stage]
        checks.append(_check(" + ".join(pooled_names), pooled_rows, other))
    return checks


def _check(
    stage: str, rows: list[SourceTableRow], matches: list[SourceMatch]
) -> TableCheck:
    scored = [
        m
        for m in matches
        if m.status in (MatchStatus.PLAYED, MatchStatus.AWARDED)
        and m.home_goals is not None
        and m.away_goals is not None
    ]
    return TableCheck(
        stage=stage,
        table_matches=sum(r.played for r in rows) / 2,
        found_matches=len(scored),
        table_goals=sum(r.goals_for for r in rows),
        match_goals=sum(_goals(m.home_goals) + _goals(m.away_goals) for m in scored),
    )


def _values(rows: list[SourceTableRow]) -> list[tuple]:
    """The data of a table, for the comparison of two copies."""
    return [
        (
            r.team_raw,
            r.played,
            r.won,
            r.drawn,
            r.lost,
            r.goals_for,
            r.goals_against,
            r.points,
        )
        for r in rows
    ]


def _goals(value: Optional[int]) -> int:
    return value or 0
