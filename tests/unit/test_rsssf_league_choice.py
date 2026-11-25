"""
Tests for the choice of the national league on an RSSSF season page
(choose_league() and competition_kind() in sources/rsssf/parser.py,
decision 24).

Page tests read real pages of the survey of 56 African countries
(tests/fixtures/rsssf/seasons/, with their authors in
tests/fixtures/rsssf/README.md). Each page shows one rule. Line tests give
names or short pages to one function.
"""

from pathlib import Path
from typing import Optional

import pytest

from african_football.sources.rsssf.http import decode_page
from african_football.sources.rsssf.parser import (
    Competition,
    LeagueChoice,
    choose_league,
    competition_kind,
    parse_page,
    split_competitions,
)
from african_football.sources.rsssf.tables import parse_tables

SEASONS = Path(__file__).parent.parent / "fixtures" / "rsssf" / "seasons"

RESULTS = "Round 1\nHearts of Oak   2-1 Kotoko\nKotoko   0-0 Hearts of Oak\n"
TABLE = (
    "Final Table:\n"
    " 1.Hearts of Oak     2  1  1  0  2-1  4\n"
    " 2.Kotoko            2  0  1  1  1-2  1\n"
)


def _page(name: str) -> str:
    return decode_page((SEASONS / name).read_bytes())


def _choice(name: str, pattern: str = ""):
    return choose_league(split_competitions(_page(name)), pattern)


def _name(choice: LeagueChoice) -> Optional[str]:
    return choice.competition.name if choice.competition else None


def _chosen(name: str) -> tuple[object, str]:
    choice = _choice(name)
    return (_name(choice) if choice.competition else None), choice.reason


def _counts(name: str, start: int, end: int) -> tuple[int, int]:
    page = _page(name)
    matches, _ = parse_page(
        page,
        league_code="x",
        season="test",
        start_year=start,
        end_year=end,
        timezone="Africa/Lagos",
        source_url="u",
        raw_documents=(),
    )
    rows, _ = parse_tables(page, league_code="x", season="test")
    return len(matches), len(rows)


# ---------------------------------------------------------------------------
# competition_kind
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("Premier League", "league"),
        ("Championnat National de 1ère Division", "league"),
        ("Championnat national de première division", "league"),
        ("Campeonato Nacional da 1ª Divisão", "league"),
        ("XXIV Girabola (Campeonato Nacional da 1ª Divisão)", "league"),
        ("Régional 1", "league"),  # the top league of Réunion
        ("NPFL 2023/24", "league"),
        ("Egypt 2004/05", "league"),  # a page title
        ("Coupe du Trône", "cup"),
        ("Taça Nacional", "cup"),
        ("Copa de Su Excelencia el Jefe de Estado", "cup"),
        ("Moi Golden Cup", "cup"),
        ("Torneio Domingos Ramos", "cup"),
        ("Second Level 2006", "lower"),
        ("Ligue Professionnelle 2", "lower"),
        ("Campeonato Nacional da 2ª Divisão", "lower"),
        ("Championnat Division Nationale B", "lower"),
        ("Division 1 North", "lower"),
        ("Northern Stream First Division", "lower"),
        ("Campeonato Distrital de Luanda", "lower"),
        ("Régional 2 Département", "lower"),
        ("Championship Playoff", "playoff"),
        ("Mini-League 2003", "playoff"),
        ("Winners qualify for CAF Cup.", "note"),
        ("Santo Antão (South Zone) no provincial championship held", "note"),
        (
            "Towards the end of the 2007/08 season, 11 of 16 Premier League clubs",
            "note",
        ),
        ("", "unnamed"),
    ],
)
def test_competition_kind(name, kind):
    assert competition_kind(name) == kind


def test_note_in_brackets_is_a_part_of_a_name():
    # The name of Rwanda 2005 has 10 words; more than 9 words is a sign of
    # a sentence. The words in [ ] do not count.
    name = "Championnat National de 1ère Division [aka Primus National Soccer League]"
    assert competition_kind(name) == "league"


# ---------------------------------------------------------------------------
# choose_league, line tests
# ---------------------------------------------------------------------------


def _c(name: str, text: str = RESULTS, is_title: bool = False) -> Competition:
    return Competition(name, text, is_title)


def test_cup_before_the_league():
    choice = choose_league([_c("Coupe du Cameroun"), _c("Premier League")])
    assert (_name(choice), choice.reason) == (
        "Premier League",
        "first league",
    )
    assert choice.alternatives == ("Coupe du Cameroun",)


def test_a_cup_is_never_the_league():
    choice = choose_league([_c("Cup Final"), _c("FA Cup")])
    assert (choice.competition, choice.reason) == (None, "none")


def test_place_name_then_national_name():
    choice = choose_league([_c("Boa Vista"), _c("Campeonato Nacional")])
    assert (_name(choice), choice.reason) == (
        "Campeonato Nacional",
        "national name",
    )


def test_league_word_keeps_the_first_league():
    # 'Nationwide League Division One' is the second level of Nigeria.
    choice = choose_league(
        [_c("Nigeria Football League"), _c("Nationwide League Division One")]
    )
    assert _name(choice) == "Nigeria Football League"


def test_page_title_is_the_league():
    choice = choose_league(
        [_c("Nigeria 2003", is_title=True), _c("Professional Division One")]
    )
    assert _name(choice) == "Nigeria 2003"


def test_stage_stays_unless_the_national_league_has_more_results():
    many = RESULTS * 5
    stage = choose_league([_c("First Stage", many), _c("Super League", RESULTS)])
    assert _name(stage) == "First Stage"
    national = choose_league(
        [_c("Group A", RESULTS), _c("National Premier League", many)]
    )
    assert _name(national) == "National Premier League"


def test_regional_leagues_only():
    places = [_c(name) for name in ["Boa Vista", "Brava", "Fogo", "Maio", "Sal"]]
    choice = choose_league(places)
    assert (choice.competition, choice.reason) == (None, "regional leagues only")


def test_years_are_not_places():
    seasons = [_c(name) for name in ["1938/39", "1939/40", "1940/41", "1941/42"]]
    assert choose_league(seasons).reason == "first league"


def test_table_without_results_is_data():
    choice = choose_league([_c("Cup Final"), _c("Premier League", TABLE)])
    assert (_name(choice), choice.reason) == ("Premier League", "tables only")


def test_fallback_is_not_a_cup_and_shows_its_kind():
    choice = choose_league([_c("Coupe Nationale"), _c("Regional Leagues")])
    assert (_name(choice), choice.reason) == (
        "Regional Leagues",
        "fallback (lower)",
    )


def test_override_from_leagues_yaml():
    competitions = [_c("Premier League"), _c("Girabola")]
    choice = choose_league(competitions, "girabola|campeonato nacional")
    assert (_name(choice), choice.reason) == ("Girabola", "leagues.yaml")


def test_override_without_a_match_gives_no_league():
    choice = choose_league([_c("Premier League")], "girabola")
    assert (choice.competition, choice.reason) == (None, "leagues.yaml: no match")


# ---------------------------------------------------------------------------
# Structure B headings
# ---------------------------------------------------------------------------


def _block(text: str) -> list[str]:
    return [
        c.name
        for c in split_competitions(f"<h2>Tunisia 1957</h2>\n<pre>\n{text}</pre>")
    ]


def test_french_heading_starts_a_competition():
    assert _block(RESULTS + "\nCoupe de Tunisie\n\n" + RESULTS) == [
        "Tunisia 1957",
        "Coupe de Tunisie",
    ]


def test_table_row_of_participants_is_not_a_heading():
    assert _block(
        RESULTS + "Liga Muçulmana     Maputo     Cidade de Maputo\n" + RESULTS
    ) == ["Tunisia 1957"]


def test_line_with_a_score_is_not_a_heading():
    assert _block(RESULTS + "Estrela Vermelha2-0 Liga Muçulmana\n" + RESULTS) == [
        "Tunisia 1957"
    ]


def test_sentence_is_not_a_heading():
    assert _block(RESULTS + "Winners qualify for CAF Cup.\n" + RESULTS) == [
        "Tunisia 1957"
    ]


# ---------------------------------------------------------------------------
# Page tests (survey pages)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("page", "start", "end", "league", "reason", "matches", "rows"),
    [
        # Nine island championships, no national league on the page.
        ("kaapv2024.html", 2023, 2024, None, "regional leagues only", 0, 0),
        ("kaapv95.html", 1994, 1995, "Campeonato Nacional", "first league", 8, 3),
        # The cup has results; the league has only its table.
        ("kam2011.html", 2010, 2011, "MTN Elite One", "tables only", 0, 14),
        ("maro2012.html", 2011, 2012, "GNF I", "tables only", 0, 16),
        ("egy2011.html", 2010, 2011, "First Level", "tables only", 0, 16),
        ("tun2026.html", 2025, 2026, "Ligue Professionnelle 1", "tables only", 0, 16),
        # The first stage (179 matches), not the final stage 'Super League'.
        ("nig06.html", 2006, 2006, "First Stage", "first league", 179, 20),
        # 'Group A' (4 matches), then 'National Premier League' (36).
        ("sier01.html", 2001, 2001, "National Premier League", "national name", 36, 10),
        # A French name in lower case is not a sentence.
        (
            "niger03.html",
            2003,
            2003,
            "Championnat national de première division",
            "first league",
            180,
            10,
        ),
        # A row of a table of participants is not a heading.
        (
            "moz08.html",
            2008,
            2008,
            "Liga Moçambicana [aka Moçambola]",
            "first league",
            182,
            14,
        ),
        # The first 'heading' is a sentence.
        (
            "ethi08.html",
            2008,
            2008,
            "Midroc Millennium Ethiopia Premier League",
            "first league",
            6,
            0,
        ),
        ("reunion2022.html", 2022, 2022, "Régional 1", "first league", 183, 14),
    ],
)
def test_survey_page(page, start, end, league, reason, matches, rows):
    assert _chosen(page) == (league, reason)
    assert _counts(page, start, end) == (matches, rows)


def test_cup_names_are_alternatives():
    assert _choice("kam2011.html").alternatives[0] == "Coupe du Cameroun"
