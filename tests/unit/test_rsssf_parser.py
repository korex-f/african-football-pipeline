"""
Tests for sources/rsssf/parser.py.

Two kinds of tests:

- Page tests read real RSSSF season pages (tests/fixtures/rsssf/seasons/,
  with their authors in tests/fixtures/rsssf/README.md). Each page shows one
  form that the project found in the pages of Nigeria, Ghana and Egypt. The
  numbers in these tests come from the parser output, after a check against
  the page, and for Ghana 2023/24 against Soccerway.
- Line tests give a short text to one function, for one rule.

The tests do not use the network.
"""

from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from african_football.models.source_match import MatchStatus, SourceMatch
from african_football.sources.rsssf.http import decode_page
from african_football.sources.rsssf.parser import (
    Competition,
    ResultRow,
    match_ids,
    parse_lines,
    parse_page,
    split_competitions,
    to_source_match,
    top_league,
)

SEASONS = Path(__file__).parent.parent / "fixtures" / "rsssf" / "seasons"


def _page(name: str) -> str:
    return decode_page((SEASONS / name).read_bytes())


def _parse(
    name: str, start: int, end: int, anchor: str = ""
) -> tuple[list[SourceMatch], list[str]]:
    return parse_page(
        _page(name),
        league_code="npfl",
        season="test",
        start_year=start,
        end_year=end,
        timezone="Africa/Lagos",
        source_url=f"https://www.rsssf.org/x/{name}",
        raw_documents=("a" * 64,),
        anchor=anchor,
    )


def _find(matches: list[SourceMatch], home: str, away: str) -> list[SourceMatch]:
    return [m for m in matches if m.home_team_raw == home and m.away_team_raw == away]


def _rows(text: str, start: int = 2023, end: int = 2024) -> list[ResultRow]:
    return parse_lines(Competition("League", text), start, end).rows


# ---------------------------------------------------------------------------
# Page tests: structure A (<h4> and a <pre> block for each competition)
# ---------------------------------------------------------------------------


def test_nigeria_2023_24():
    matches, problems = _parse("nig2024.html", 2023, 2024)
    assert top_league(_page("nig2024.html")).name == "NPFL 2023/24"  # pyright: ignore[reportOptionalMemberAccess]
    # 20 teams: 380 matches, and 1 replay of an abandoned match.
    assert len(matches) == 381
    assert problems == []


def test_note_in_a_column_at_the_right():
    # The note of 'Gombe United 1-1 Rivers United' continues at the right of
    # the next two result lines. These two lines are results.
    matches, _ = _parse("nig2024.html", 2023, 2024)
    [enyimba] = _find(matches, "Enyimba", "Sporting Lagos")
    [akwa] = _find(matches, "Akwa United", "Abia Warriors")
    assert (enyimba.home_goals, enyimba.away_goals) == (2, 0)
    assert (akwa.home_goals, akwa.away_goals) == (3, 1)
    assert enyimba.match_date == date(2024, 1, 7)


def test_ghana_2023_24_agrees_with_soccerway():
    # Soccerway has 306 matches; RSSSF has them all with the same date and
    # score, and also the abandoned match before a replay.
    matches, problems = _parse("gha2024.html", 2023, 2024)
    assert len(matches) == 307
    assert problems == []
    dates = [m.match_date for m in matches if m.match_date]
    assert (min(dates), max(dates)) == (date(2023, 9, 15), date(2024, 6, 16))

    abandoned, replay = _find(matches, "Medeama", "Aduana")
    assert (abandoned.status, abandoned.match_date) == (
        MatchStatus.ABANDONED,
        date(2024, 3, 20),
    )
    assert (replay.status, replay.home_goals, replay.away_goals) == (
        MatchStatus.PLAYED,
        2,
        0,
    )
    assert replay.source_match_id.endswith("#2")


def test_awarded_score_from_the_note():
    # Great Olympics  awd Real Tamale United  [awarded 3-0, RTU forfeited]
    matches, _ = _parse("gha2024.html", 2023, 2024)
    [awarded] = _find(matches, "Great Olympics", "Real Tamale United")
    assert awarded.status is MatchStatus.AWARDED
    assert (awarded.home_goals, awarded.away_goals) == (3, 0)


def test_stages_and_groups():
    matches, _ = _parse("nig2019.html", 2019, 2019)
    assert Counter(m.stage for m in matches) == {
        "Group A": 132,
        "Group B": 132,
        "Playoff Stage": 16,
    }


# ---------------------------------------------------------------------------
# Page tests: structure B (one <pre> block)
# ---------------------------------------------------------------------------


def test_tabs_and_replays():
    matches, problems = _parse("nig05.html", 2005, 2005)
    # 389 played and 4 postponed ('ppd') matches.
    assert len(matches) == 393
    assert problems == []
    [kwara] = _find(matches, "Kwara", "Nationale")  # 'Kwara\t\t3-0 Nationale'
    assert (kwara.home_goals, kwara.away_goals, kwara.match_date) == (
        3,
        0,
        date(2005, 2, 12),
    )
    assert Counter(m.round_name for m in matches)["Replay Round 20"] == 10


def test_table_in_the_middle_does_not_end_the_league():
    # nig01 has 'Table:' after round 10 and after round 20.
    matches, _ = _parse("nig01.html", 2001, 2001)
    # 242 played, 1 postponed ('ppd') and 1 annulled ('ann') match.
    assert len(matches) == 244
    assert {m.stage for m in matches} == {"Nigeria 2001"}


def test_heading_without_underline_ends_the_league():
    # 'Division One (Second Level) early 2003' starts the next competition.
    matches, problems = _parse("gha02.html", 2002, 2002)
    assert len(matches) == 240
    assert problems == []
    [match] = _find(matches, "Bofoakwa", "King Faisal")  # ' \t[also reported 1-0]'
    assert (match.home_goals, match.away_goals) == (1, 1)


def test_cup_after_the_final_table_is_not_the_league():
    # The Egypt Cup starts after the final table, without a heading. It has
    # 'bt' and 'drw' lines; the league has none.
    matches, _ = _parse("egy05.html", 2004, 2005)
    # 26 rounds of 7 matches. Round 19 has scores with an en dash ('3–1').
    assert len(matches) == 182
    assert {m.status for m in matches} == {MatchStatus.PLAYED}
    assert "Assiut Petrol." not in {m.home_team_raw for m in matches}


def test_underlined_heading_and_date_on_the_round_line():
    matches, _ = _parse("gha08.html", 2007, 2008)
    assert top_league(_page("gha08.html")).name == "Onetouch Premier League"  # pyright: ignore[reportOptionalMemberAccess]
    assert len(matches) == 241
    first = matches[0]  # 'Round 1 [Dec 2]'
    assert (first.round_name, first.match_date, first.home_team_raw) == (
        "Round 1",
        date(2007, 12, 2),
        "Liberty",
    )


def test_date_of_two_days_and_round_without_date():
    matches, _ = _parse("nig99.html", 1999, 1999)
    # 'Round 16 [Mar 24,25]' gives the first day.
    assert {m.match_date for m in matches if m.round_name == "Round 16"} == {
        date(1999, 3, 24)
    }
    # 'Round 21' has no date. Its matches must not get the date of round 20.
    assert {m.match_date for m in matches if m.round_name == "Round 21"} == {None}


# ---------------------------------------------------------------------------
# Page tests: pages with many seasons, and pages without results
# ---------------------------------------------------------------------------


def test_season_part_of_a_page_with_many_seasons():
    matches_77, _ = _parse("nig72.html", 1977, 1977, anchor="77")
    assert [(m.home_team_raw, m.away_team_raw) for m in matches_77] == [
        ("Racca Rovers", "IICC Shooting Stars"),
        ("IICC Shooting Stars", "Spartans (Owerri)"),
        ("Stationery Stores", "Enugu Rangers"),
    ]
    assert {m.match_date for m in matches_77} == {date(1977, 12, 8)}

    # 1972 has no results on the page: not the results of 1977.
    matches_72, problems = _parse("nig72.html", 1972, 1972, anchor="72")
    assert (matches_72, problems) == ([], [])


def test_anchor_without_bold():
    # ghahist.html: '<a name="64">1963/64</a>' without <b>. Tables only.
    assert _parse("ghahist.html", 1963, 1964, anchor="64") == ([], [])


def test_unknown_anchor_is_a_problem():
    assert _parse("ghahist.html", 1963, 1964, anchor="99") == (
        [],
        ["no season part for the anchor #99"],
    )


def test_crosstable_is_reported():
    matches, problems = _parse("gha2013.html", 2012, 2013)
    assert len(matches) == 242
    assert problems == ["16 lines of a results grid or crosstable not read"]


def test_page_with_only_a_grid_is_reported():
    # 'Zamalek  0-0 2-2': the two results of one team against Zamalek.
    assert _parse("egy53.html", 1952, 1953) == (
        [],
        ["9 lines of a results grid or crosstable not read"],
    )


def test_page_with_a_table_only():
    # The only result-like line is 'Cup Final: Al Mokaoulun 2-0 Al Mehalla'.
    assert _parse("egy95.html", 1994, 1995) == ([], [])


# ---------------------------------------------------------------------------
# Line tests
# ---------------------------------------------------------------------------


def test_result_line_forms():
    rows = _rows(
        "[Sep 15]\n"
        "Real Tamale United      1-0 Hearts of Oak\n"
        "Kwara\t\t3-0 Nationale\n"
        "Bofoakwa\t      1-1 King Faisal \t[also reported 1-0]\n"
        "FC De Leo               1-1 EFCC                    [4-5 pen]\n"
    )
    assert [(r.home, r.result, r.away, r.note) for r in rows] == [
        ("Real Tamale United", "1-0", "Hearts of Oak", None),
        ("Kwara", "3-0", "Nationale", None),
        ("Bofoakwa", "1-1", "King Faisal", "also reported 1-0"),
        ("FC De Leo", "1-1", "EFCC", "4-5 pen"),
    ]


def test_lines_that_are_not_results():
    rows = _rows(
        " 1.Enyimba FC (Aba)                  38 21  9  8 63-22 72 Champions\n"
        "Cup Final: Al Mokaoulun 2-0 Al Mehalla\n"
        "Zamalek     0-0 2-2 [*1]\n"
        "NB: the 3-0 result was annulled\n"
        "  [Tamer Abdel Hamid 47, Sameh Youssef 53]\n"
        "[*14] w/o goals rd 14 (Liberty bt Goldfields by 1)\n"
    )
    assert rows == []


def test_scorer_list_over_two_lines():
    rows = _rows(
        "Zamalek       4-1 G Mehalla\n"
        "  [Tamer Abdel Hamid 47, Sameh Youssef 53, Tarek El-Sayed 56,\n"
        "   Abdel Halim Ali 80; Ikrami Abdel Aziz 45+2]\n"
        "Ahly          2-0 Masry\n"
    )
    assert [(r.home, r.away) for r in rows] == [
        ("Zamalek", "G Mehalla"),
        ("Ahly", "Masry"),
    ]


def test_line_that_looks_like_a_result_is_reported():
    parsed = parse_lines(
        Competition("League", "Sportnet                4-0     [?]\n"), 2002, 2002
    )
    assert parsed.rows == []
    assert parsed.unparsed == ["Sportnet                4-0     [?]"]


@pytest.mark.parametrize(
    ("dates", "expected"),
    [
        # A season over two years: a month before the first month is in the
        # second year.
        (["[Sep 15]", "[Dec 30]", "[Jan 2]", "[Jun 16]"], [2023, 2023, 2024, 2024]),
        # A date with its year.
        (["[Sep 15]", "[Jan 2, 2025]"], [2023, 2025]),
    ],
)
def test_year_of_a_date(dates, expected):
    text = "".join(f"{d}\nHome {i}   1-0 Away {i}\n" for i, d in enumerate(dates))
    assert [r.match_date.year for r in _rows(text)] == expected  # pyright: ignore[reportOptionalMemberAccess]


def test_calendar_year_season_has_one_year():
    rows = _rows("[Dec 30]\nA   1-0 B\n[Jan 2]\nC   1-0 D\n", 2015, 2015)
    assert [r.match_date for r in rows] == [date(2015, 12, 30), date(2015, 1, 2)]


def test_round_with_a_date_and_a_round_without():
    rows = _rows("Round 1 [Dec 2]\nA   1-0 B\nRound 2\nC   1-0 D\n")
    assert [(r.round_name, r.round_number, r.match_date) for r in rows] == [
        ("Round 1", 1, date(2023, 12, 2)),
        ("Round 2", 2, None),
    ]


def test_play_off_is_a_stage():
    rows = _rows("Round 30\nA   1-0 B\nRelegation Playoff [May 4]\nC   1-0 D\n")
    assert [r.stage for r in rows] == ["League", "Relegation Playoff"]


# ---------------------------------------------------------------------------
# to_source_match and match_ids
# ---------------------------------------------------------------------------


def _row(**changes: Any) -> ResultRow:
    fields: dict[str, Any] = dict(
        stage="League",
        round_name="Round 1",
        round_number=1,
        match_date=date(2023, 9, 15),
        home="Hearts of Oak",
        away="Kotoko",
        result="2-1",
        note=None,
    )
    fields.update(changes)
    return ResultRow(**fields)


def _match(row: ResultRow) -> SourceMatch:
    return to_source_match(
        row,
        match_id="id",
        source_url="https://www.rsssf.org/tablesg/gha2024.html",
        league_code="gh_pl",
        season="2023/2024",
        timezone="Africa/Accra",
        raw_documents=("a" * 64,),
    )


@pytest.mark.parametrize(
    ("result", "note", "status", "goals", "penalties"),
    [
        ("2-1", None, MatchStatus.PLAYED, (2, 1), (None, None)),
        ("1-1", "4-5 pen", MatchStatus.PLAYED, (1, 1), (4, 5)),
        ("1-1", "aet, 0-3 pen", MatchStatus.PLAYED, (1, 1), (0, 3)),
        # A penalty in a match that is not a draw is not a shootout.
        (
            "1-0",
            "Masry scored from a 1-0 pen",
            MatchStatus.PLAYED,
            (1, 0),
            (None, None),
        ),
        (
            "awd",
            "awarded 3-0, RTU forfeited",
            MatchStatus.AWARDED,
            (3, 0),
            (None, None),
        ),
        (
            "awd",
            "0-3 awarded; originally 1-1",
            MatchStatus.AWARDED,
            (0, 3),
            (None, None),
        ),
        ("awd", None, MatchStatus.AWARDED, (None, None), (None, None)),
        ("w/o", None, MatchStatus.AWARDED, (None, None), (None, None)),
        ("abd", "abandoned at 1-1", MatchStatus.ABANDONED, (None, None), (None, None)),
        ("unk", None, MatchStatus.UNKNOWN, (None, None), (None, None)),
        ("bt", None, MatchStatus.UNKNOWN, (None, None), (None, None)),
        ("lt", None, MatchStatus.UNKNOWN, (None, None), (None, None)),
        ("drw", None, MatchStatus.UNKNOWN, (None, None), (None, None)),
        # Decision 25.
        ("3-0*", "* aet", MatchStatus.PLAYED, (3, 0), (None, None)),
        ("3-?", None, MatchStatus.UNKNOWN, (None, None), (None, None)),
        ("?-?", None, MatchStatus.UNKNOWN, (None, None), (None, None)),
        ("tie", None, MatchStatus.UNKNOWN, (None, None), (None, None)),
        ("---", None, MatchStatus.UNKNOWN, (None, None), (None, None)),
        ("ppd", None, MatchStatus.POSTPONED, (None, None), (None, None)),
        (
            "ann",
            "annulled; finished 1-0",
            MatchStatus.CANCELLED,
            (None, None),
            (None, None),
        ),
        ("n/p", None, MatchStatus.CANCELLED, (None, None), (None, None)),
        (
            "n/p",
            "0-3 awarded; Ranchers Bees dns",
            MatchStatus.AWARDED,
            (0, 3),
            (None, None),
        ),
        # An award that the note revokes does not count.
        (
            "n/p",
            "awarded 3-0, Hearts of Oak dns; decision revoked on appeal",
            MatchStatus.CANCELLED,
            (None, None),
            (None, None),
        ),
        (
            "n/p",
            "first awarded 0-3, Forest dns; award revoked Aug 6",
            MatchStatus.CANCELLED,
            (None, None),
            (None, None),
        ),
        (
            "awd",
            "African Stars dns; awarded 2-0; later annulled",
            MatchStatus.CANCELLED,
            (None, None),
            (None, None),
        ),
        (
            "awd",
            "Kagera dns, awarded 2-0 - annulled",
            MatchStatus.CANCELLED,
            (None, None),
            (None, None),
        ),
        (
            "n/p",
            "Raadsan dns; awarded 3-0 but later annulled",
            MatchStatus.CANCELLED,
            (None, None),
            (None, None),
        ),
        # These notes do not revoke the award.
        (
            "awd",
            "annulled; 0-3 awarded; originally 2-1",
            MatchStatus.AWARDED,
            (0, 3),
            (None, None),
        ),
        (
            "awd",
            "awarded 0-2; abandoned at 0-1 after a penalty award to Karonga was revoked",
            MatchStatus.AWARDED,
            (0, 2),
            (None, None),
        ),
        (
            "awd",
            "awarded 2-0, Nakuru dns; to be annulled?",
            MatchStatus.AWARDED,
            (2, 0),
            (None, None),
        ),
        (
            "awd",
            "awarded 0-3, BA United used ineligible player; award revoked?",
            MatchStatus.AWARDED,
            (0, 3),
            (None, None),
        ),
    ],
)
def test_result_to_source_match(result, note, status, goals, penalties):
    match = _match(_row(result=result, note=note))
    assert match.status is status
    assert (match.home_goals, match.away_goals) == goals
    assert (match.pen_home, match.pen_away) == penalties
    assert match.source == "rsssf"
    assert match.kickoff_local is None


def test_same_teams_cannot_play():
    with pytest.raises(ValidationError):
        _match(_row(away="Hearts of Oak"))


def test_match_ids_are_stable_and_unique():
    rows = [
        _row(),
        _row(stage="Playoff"),
        _row(),
        _row(home="Kotoko", away="Hearts of Oak"),
    ]
    assert match_ids(rows, "gh_pl", "2023/2024") == [
        "gh_pl/2023/2024/League/Hearts of Oak-Kotoko",
        "gh_pl/2023/2024/Playoff/Hearts of Oak-Kotoko",
        "gh_pl/2023/2024/League/Hearts of Oak-Kotoko#2",
        "gh_pl/2023/2024/League/Kotoko-Hearts of Oak",
    ]


def test_split_competitions_of_structure_a():
    names = [c.name for c in split_competitions(_page("gha2024.html"))]
    assert names[:3] == ["Ghana Premier League", "MTN FA Cup 2023/24", "Super Cup 2024"]


# ---------------------------------------------------------------------------
# Structure B boundaries: forms that the fixtures do not show alone
# ---------------------------------------------------------------------------


def _one_block(text: str) -> str:
    return f"<h2>Ghana 2003</h2>\n<pre>\n{text}</pre>"


def test_final_table_before_the_results():
    # The table rows are not results. Thus 'Top scorers:' after the table
    # does not end the league, and the results after it are in the league.
    # A row from 10 has no space at the start. With single spaces and a word
    # after the points, '10.Kotoko 2 0 0 2 1-3 0 Relegated' has the form of
    # a result line ('0 Relegated' as the away team) without the table rule.
    # Two such rows (the relegated teams) start a 'table after results'.
    page = _one_block(
        "Final Table:\n"
        " 9.Hearts of Oak     2  2  0  0  3-1  6\n"
        "10.Kotoko 2 0 0 2 1-3 0 Relegated\n"
        "11.Ashanti 2 0 0 2 0-2 0 Relegated\n"
        "\n"
        "Top scorers: Ofori 2\n"
        "\n"
        "Round 1\n"
        "Hearts of Oak   2-1 Kotoko\n"
    )
    league = top_league(page)
    assert league is not None
    assert [r.home for r in parse_lines(league, 2003, 2003).rows] == ["Hearts of Oak"]


def test_table_in_the_middle_with_text_after_it():
    # Only a 'Final Table' can end the league, not a table after round 1.
    page = _one_block(
        "Round 1\n"
        "Hearts of Oak   2-1 Kotoko\n"
        "Table:\n"
        " 1.Hearts of Oak     1  1  0  0  2-1  3\n"
        "Top scorers after round 1: Ofori 2\n"
        "Round 2\n"
        "Kotoko          1-1 Hearts of Oak\n"
    )
    league = top_league(page)
    assert league is not None
    assert len(parse_lines(league, 2003, 2003).rows) == 2


def test_competition_heading_without_underline():
    page = _one_block(
        "Round 1\n"
        "Hearts of Oak   2-1 Kotoko\n"
        "\n"
        "Division One (Second Level) early 2003\n"
        "\n"
        "Round 1\n"
        "Voradep         1-0 Delorm Royals\n"
    )
    assert [c.name for c in split_competitions(page)] == [
        "Ghana 2003",
        "Division One (Second Level) early 2003",
    ]
    league = top_league(page)
    assert league is not None
    assert [r.home for r in parse_lines(league, 2003, 2003).rows] == ["Hearts of Oak"]


# ---------------------------------------------------------------------------
# Result-line forms (decision 25)
# ---------------------------------------------------------------------------


def test_algeria_1972_73_scores_with_an_en_dash():
    # All scores have an en dash ('1–1'). Before decision 25, 1 match.
    # The page gives round 10 two times (the same 8 lines): 240 + 8.
    matches, problems = _parse("alg73.html", 1972, 1973)
    assert len(matches) == 248
    assert problems == []
    assert Counter(m.round_name for m in matches)["Round 10"] == 16
    [match] = _find(matches, "CS Constantine", "MC Alger")[:1]
    assert (match.home_goals, match.away_goals) == (1, 1)


def test_morocco_1995_96_teams_first_and_underlined_rounds():
    # 'COD Meknes      - SA Sale           5-2'. Each 'Round N' has a line
    # of '=' under it: a round of the league, not a new competition.
    matches, problems = _parse("maro96.html", 1995, 1996)
    assert top_league(_page("maro96.html")).name == "Morocco 1995/96"  # pyright: ignore[reportOptionalMemberAccess]
    assert len(matches) == 240
    assert problems == []
    [match] = _find(matches, "COD Meknes", "SA Sale")
    assert (match.round_name, match.home_goals, match.away_goals) == ("Round 1", 5, 2)


def test_two_leg_lines_are_reported():
    # 'ex-Benfica Nampula  2-0  1-5 AD Pemba  [agg 3-5]': the order of the
    # second leg is not certain. The parser does not read these lines.
    matches, problems = _parse("moz78.html", 1978, 1978)
    assert len(matches) == 11
    assert problems == ["5 lines of two-leg ties not read"]
    assert _find(matches, "ex-Benfica Nampula", "AD Pemba") == []


def test_grid_rows_with_a_mark_are_reported():
    # 'Simunye FC 0-2 1-1 awd 0-3 ... xxx 0-2': not 'Simunye FC 0-2 1-1'.
    matches, problems = _parse("swaz97.html", 1997, 1997)
    assert len(matches) == 13
    assert problems == ["16 lines of a results grid or crosstable not read"]


def test_score_in_a_note_is_not_a_result():
    # '[Sep 26]       as a 2-0 win]' ends the note of 'Stade  awd
    # Bingerville', in a column at the right: it is a part of that note.
    matches, problems = _parse("ivo04.html", 2004, 2004)
    assert len(matches) == 182
    assert problems == []
    league = top_league(_page("ivo04.html"))
    assert league is not None
    rows = parse_lines(league, 2004, 2004).rows
    [row] = [r for r in rows if (r.home, r.away) == ("Stade", "Bingerville")]
    assert row.note is not None and row.note.endswith("as a 2-0 win")


def test_sentence_with_numbers_is_not_a_result():
    # 'Rounds 10-14 and final tables missing.'
    matches, problems = _parse("burkf98.html", 1997, 1998)
    assert len(matches) == 8
    assert problems == []


def test_team_name_in_lower_case():
    # 'kotoko           2-0 New Edubiase': a wide gap, thus not a sentence.
    matches, _ = _parse("gha2010.html", 2009, 2010)
    assert len(matches) == 240
    assert len(_find(matches, "kotoko", "New Edubiase")) == 1


def test_scores_in_a_note_do_not_make_a_grid_row():
    # 'Fovu  1-1 Canon  [awarded 3-0; originally 1-1, ...': three scores,
    # two of them in the note.
    matches, problems = _parse("kam2015.html", 2015, 2015)
    assert len(matches) == 309
    assert problems == []
    assert len(_find(matches, "Fovu", "Canon")) == 1


def test_result_word_in_upper_case():
    # 'Express   Ppd UEB'
    matches, _ = _parse("oeg97.html", 1997, 1997)
    assert Counter(m.status for m in matches) == {
        MatchStatus.PLAYED: 91,
        MatchStatus.POSTPONED: 4,
    }


def test_new_result_line_forms():
    rows = _rows(
        "MC Oran \t\t1–1 JSM Tiaret\n"
        "Académica   1-0  0-2* Desportivo\t[* aet]\n"
        "Jijel SD    3-0* CRE Constantine\n"
        "Jijel SD    3-0*CRE Constantine\n"
        "Sharks      ?-? Lobi\n"
        "Wikki       3-? Pillars\n"
        "Bo Rangers  --- Old Edwardians\n"
        "Gombe       ppd Enyimba\n"
        "Gabros      ann El Kanemi   [annulled; finished 1-0]\n"
        "Kenya Rlys  tie Lake Warriors\n"
        "Al-Menya - Al-Ahly   1-3\n"
        "FC HellBourg. - US Ste Anne : 6-1\n"
    )
    assert [(r.home, r.result, r.away) for r in rows] == [
        ("MC Oran", "1-1", "JSM Tiaret"),
        ("Jijel SD", "3-0*", "CRE Constantine"),
        ("Jijel SD", "3-0*", "CRE Constantine"),
        ("Sharks", "?-?", "Lobi"),
        ("Wikki", "3-?", "Pillars"),
        ("Bo Rangers", "---", "Old Edwardians"),
        ("Gombe", "ppd", "Enyimba"),
        ("Gabros", "ann", "El Kanemi"),
        ("Kenya Rlys", "tie", "Lake Warriors"),
        ("Al-Menya", "1-3", "Al-Ahly"),
        ("FC HellBourg.", "6-1", "US Ste Anne"),
    ]


def test_new_lines_that_are_not_results():
    parsed = parse_lines(
        Competition(
            "League",
            "MC Alger   -  Paradou AC\n"
            "Round 19 [postponed from Mar 2-4 due to a strike]\n"
            "Table (based on known results w/o some goals):\n"
            "losing 1-2 to SO Armée in round 13\n"
            "Fovu  1-1 Canon  [award of 3-0 revoked\n"
            "Denver Sun 1-0 xxx 1-0 2-1\n"
            "Buffles du Borgou        XXX    1-0    XXX    0-0    3-1\n"
            "13 CS Hammam Lif   \t26   6   8  12  22  30   26  [0 1 1 2-3 1] Relegated\n"
            "Etoile du Congo  11-0 5-0 Racing Club\n",
        ),
        2003,
        2003,
    )
    assert [(r.home, r.away) for r in parsed.rows] == [("Fovu", "Canon")]
    # A table row without '13.' has the form of a result: it is reported.
    assert parsed.unparsed == [
        "losing 1-2 to SO Armée in round 13",
        "13 CS Hammam Lif   \t26   6   8  12  22  30   26  [0 1 1 2-3 1] Relegated",
    ]
    assert (parsed.grid_lines, parsed.two_leg_lines) == (2, 1)


def test_note_parts_in_a_column_join_their_note():
    # The next parts of a note are at the right of the next lines: after a
    # date, or after the next result.
    rows = _rows(
        "Orlando Pirates   awd African Stars     [African Stars dns;\n"
        "[Jun 17]                                 awarded 2-0; later annulled]\n"
        "Tema Youth        n/p Hearts of Oak     [awarded 3-0, Hearts of Oak dns;\n"
        "King Faisal       1-1 Heart of Lions     3 points deducted;\n"
        "[Oct 22]                                 decision revoked on appeal]\n"
        "Kotoko            2-0 Hearts of Oak\n"
        "Fovu              1-1 Canon             [awarded 3-0; Canon used an\n"
        "                                         ineligible player]\n"
    )
    assert [(r.home, r.note) for r in rows] == [
        ("Orlando Pirates", "African Stars dns; awarded 2-0; later annulled"),
        (
            "Tema Youth",
            "awarded 3-0, Hearts of Oak dns; 3 points deducted; "
            "decision revoked on appeal",
        ),
        ("King Faisal", None),
        ("Kotoko", None),
        ("Fovu", "awarded 3-0; Canon used an ineligible player"),
    ]
    assert rows[3].match_date == date(2023, 10, 22)


def test_scorers_do_not_join_the_note_of_a_result():
    rows = _rows(
        "Zamalek       4-1 G Mehalla   [replay;\n"
        "  [Tamer Abdel Hamid 47,\n"
        "   Abdel Halim Ali 80]\n"
    )
    assert rows[0].note == "replay;"
