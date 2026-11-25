"""
Tests for sources/rsssf/tables.py and models/source_table.py.

Page tests read the RSSSF season pages in tests/fixtures/rsssf/seasons/.
Line tests give a short page to parse_tables(), for one rule. The numbers
in the page tests come from the reader output, after a check against the
page. The tests do not use the network.
"""

from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from african_football.models.source_match import MatchStatus, SourceMatch
from african_football.models.source_table import SourceTableRow
from african_football.sources.rsssf.http import decode_page
from african_football.sources.rsssf.parser import parse_page
from african_football.sources.rsssf.tables import parse_tables, table_check

SEASONS = Path(__file__).parent.parent / "fixtures" / "rsssf" / "seasons"


def _tables(name: str, anchor: str = "") -> tuple[list[SourceTableRow], list[str]]:
    page = decode_page((SEASONS / name).read_bytes())
    return parse_tables(page, league_code="gh_pl", season="test", anchor=anchor)


def _page_tables(text: str) -> tuple[list[SourceTableRow], list[str]]:
    page = f"<h2>Ghana 2003</h2>\n<pre>\n{text}</pre>"
    return parse_tables(page, league_code="gh_pl", season="2003")


def _check(name: str, start: int, end: int):
    page = decode_page((SEASONS / name).read_bytes())
    matches, _ = parse_page(
        page,
        league_code="x",
        season="test",
        start_year=start,
        end_year=end,
        timezone="Africa/Accra",
        source_url="u",
        raw_documents=(),
    )
    rows, _ = parse_tables(page, league_code="x", season="test")
    return table_check(rows, matches)


# ---------------------------------------------------------------------------
# SourceTableRow
# ---------------------------------------------------------------------------


def _row(**changes: Any) -> SourceTableRow:
    fields: dict[str, Any] = dict(
        source="rsssf",
        league_code="gh_pl",
        season="2023/2024",
        stage="Ghana Premier League",
        row_number=1,
        position=1,
        team_raw="FC Samartex 1996",
        played=34,
        won=19,
        drawn=4,
        lost=11,
        goals_for=45,
        goals_against=28,
        points=61,
        note="Champions",
    )
    fields.update(changes)
    return SourceTableRow(**fields)


def test_valid_row():
    assert _row().points == 61


def test_results_must_add_up_to_played():
    with pytest.raises(ValidationError, match="is not played"):
        _row(won=20)


def test_points_can_be_negative():
    # A deduction can give a team fewer than 0 points.
    assert _row(won=0, drawn=1, lost=33, points=-2).points == -2


# ---------------------------------------------------------------------------
# Page tests
# ---------------------------------------------------------------------------


def test_ghana_2023_24_table_and_check():
    rows, problems = _tables("gha2024.html")
    assert problems == []
    # The page has the final table two times (before and after the
    # results). The rows are the same, thus there is one table.
    assert len(rows) == 18
    first = rows[0]
    assert (first.position, first.team_raw, first.played, first.points, first.note) == (
        1,
        "FC Samartex 1996",
        34,
        61,
        "Champions",
    )
    [check] = _check("gha2024.html", 2023, 2024)
    assert (check.table_matches, check.found_matches) == (306, 306)
    assert (check.table_goals, check.match_goals) == (628, 628)
    assert check.agrees


def test_group_tables_agree_with_their_matches():
    checks = _check("nig2019.html", 2019, 2019)
    assert [(c.stage, c.table_matches, c.table_goals, c.agrees) for c in checks] == [
        ("Group A", 132, 235, True),
        ("Group B", 132, 262, True),
        ("Playoff Stage", 15, 46, True),
    ]


def test_goal_deduction_shows_in_the_check():
    # 'Gombe United 3 points and 3 goals deducted': the table has 6 goals
    # fewer than the matches (845 and 851). The matches agree.
    [check] = _check("nig2024.html", 2023, 2024)
    assert (check.table_matches, check.found_matches) == (380, 380)
    assert (check.table_goals, check.match_goals) == (845, 851)
    assert not check.agrees


def test_page_without_results_has_its_table():
    rows, problems = _tables("egy95.html")
    assert (len(rows), problems) == (14, [])
    assert (rows[0].team_raw, rows[0].played, rows[0].points) == ("Al Ahly", 26, 58)


def test_table_of_a_season_part_without_a_heading():
    # ghahist.html: '<a name="64">1963/64</a>', then the rows.
    rows, _ = _tables("ghahist.html", anchor="64")
    assert len(rows) == 18
    assert rows[0].team_raw == "Asante Kotoko (Kumasi)"


def test_table_of_a_season_part_with_a_heading():
    rows, _ = _tables("nig72.html", anchor="72")
    assert len(rows) == 8
    assert rows[0].team_raw == "Mighty Jets (Jos)"


def test_row_that_does_not_add_up_is_a_problem():
    # 16.El-Kanemi Warriors: 12 + 18 + 14 is 44, not 34 (a typo on the page).
    rows, problems = _tables("nig99.html")
    assert len(rows) == 17
    assert len(problems) == 1
    assert problems[0].startswith("table row not valid: 16.El-Kanemi Warriors")


def test_two_different_final_tables_are_a_problem():
    _, problems = _tables("nig01.html")
    assert problems == ["two different final tables for the stage 'Nigeria 2001'"]


# ---------------------------------------------------------------------------
# Line tests
# ---------------------------------------------------------------------------


def test_row_forms():
    rows, problems = _page_tables(
        "Final Table:\n"
        " 1.Zamalek                 14  12  2  0  34- 9  26  Championship Playoff\n"
        " 2.Ismaily\t\t14  8  2  4  27-15  18\n"
        " 3.3SC Shooting Stars      14   7  1/ 2  4  20-15  23  [-1]\n"
    )
    assert problems == []
    assert [(r.team_raw, r.drawn, r.goals_against, r.note) for r in rows] == [
        ("Zamalek", 2, 9, "Championship Playoff"),
        ("Ismaily", 2, 15, None),
        # '1/ 2': a score draw and a goalless draw (Nigeria 1991, 1992).
        ("3SC Shooting Stars", 3, 15, "[-1]"),
    ]


def test_only_final_tables_are_read():
    rows, _ = _page_tables(
        "Table:\n"
        " 1.Hearts of Oak     10  7  2  1  20-8  23\n"
        "\n"
        "Table before last round:\n"
        " 1.Hearts of Oak     29 20  5  4  60-20  65\n"
        "\n"
        "Final table missing.\n"
    )
    assert rows == []


def test_groups_in_final_tables():
    rows, _ = _page_tables(
        "Final Tables:\n"
        "\n"
        "Group 1\n"
        " 1.Al-Ahly               2   2  0  0   5-1   4\n"
        " 2.Tersana               2   0  0  2   1-5   0\n"
        "\n"
        "Group 2\n"
        " 1.Zamalek               2   1  1  0   3-1   3\n"
        " 2.Olympic               2   0  1  1   1-3   1\n"
    )
    assert [(r.stage, r.row_number, r.team_raw) for r in rows] == [
        ("Group 1", 1, "Al-Ahly"),
        ("Group 1", 2, "Tersana"),
        ("Group 2", 1, "Zamalek"),
        ("Group 2", 2, "Olympic"),
    ]


def test_short_row_is_a_problem():
    rows, problems = _page_tables(
        "Final Table:\n 1.Hearts      26 54 (+23)  Champions\n"
    )
    assert rows == []
    assert problems == ["table row not read: 1.Hearts      26 54 (+23)  Champions"]


def test_list_of_teams_is_not_a_table():
    # No numbers after the team names: a list of the participants.
    assert _page_tables(
        "Final Table:\n 1.Stationery Stores FC, Lagos;\n 2.Bendel Insurance FC, Benin;\n"
    ) == ([], [])


def test_table_ends_at_other_text():
    rows, _ = _page_tables(
        "Final Table:\n"
        " 1.Hearts of Oak     2  2  0  0  3-1  6\n"
        " 2.Kotoko            2  0  0  2  1-3  0\n"
        "\n"
        "Promoted: Ashanti\n"
        "\n"
        " 1.Not a table row   2  2  0  0  3-1  6\n"
    )
    assert [r.team_raw for r in rows] == ["Hearts of Oak", "Kotoko"]


# ---------------------------------------------------------------------------
# table_check
# ---------------------------------------------------------------------------


def _match(home: str, away: str, home_goals, away_goals, **changes: Any) -> SourceMatch:
    fields: dict[str, Any] = dict(
        source="rsssf",
        source_match_id=f"{home}-{away}",
        league_code="gh_pl",
        season="2003",
        stage="Ghana 2003",
        match_date=date(2003, 3, 1),
        timezone="Africa/Accra",
        home_team_raw=home,
        away_team_raw=away,
        home_goals=home_goals,
        away_goals=away_goals,
        status=MatchStatus.PLAYED,
    )
    fields.update(changes)
    return SourceMatch(**fields)


TABLE = (
    "Final Table:\n"
    " 1.Hearts of Oak FC (Accra)  2  2  0  0  3-1  6\n"
    " 2.Asante Kotoko (Kumasi)    2  0  0  2  1-3  0\n"
)


def test_check_without_team_names():
    # The table names are not the match names. The check uses only sums.
    rows, _ = _page_tables(TABLE)
    matches = [_match("Hearts", "Kotoko", 2, 1), _match("Kotoko", "Hearts", 0, 1)]
    [check] = table_check(rows, matches)
    assert (check.table_matches, check.found_matches) == (2, 2)
    assert (check.table_goals, check.match_goals) == (4, 4)
    assert check.agrees


def test_check_counts_awarded_matches_with_a_score_only():
    rows, _ = _page_tables(TABLE)
    matches = [
        _match("Hearts", "Kotoko", 2, 1),
        _match("Kotoko", "Hearts", 0, 1, status=MatchStatus.AWARDED),
        _match(
            "Kotoko",
            "Hearts",
            None,
            None,
            source_match_id="x",
            status=MatchStatus.ABANDONED,
        ),
    ]
    [check] = table_check(rows, matches)
    assert check.found_matches == 2
    assert check.agrees


def test_check_finds_a_missing_match():
    rows, _ = _page_tables(TABLE)
    [check] = table_check(rows, [_match("Hearts", "Kotoko", 2, 1)])
    assert (check.table_matches, check.found_matches) == (2, 1)
    assert not check.agrees


def test_check_does_not_count_a_walkover_without_a_score():
    # 'w/o' gives AWARDED without a score: its goals are not known, thus it
    # is not a found match for the goal comparison.
    rows, _ = _page_tables(TABLE)
    matches = [
        _match("Hearts", "Kotoko", 2, 1),
        _match("Kotoko", "Hearts", None, None, status=MatchStatus.AWARDED),
    ]
    [check] = table_check(rows, matches)
    assert check.found_matches == 1
