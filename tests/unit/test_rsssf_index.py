"""
Tests for sources/rsssf/index.py.

The fixtures are real RSSSF lists of champions (tests/fixtures/rsssf/, with
the authors in its README). The tests do not use the network.
"""

from pathlib import Path

import pytest

from african_football.sources.rsssf.http import decode_page
from african_football.sources.rsssf.index import (
    parse_index,
    parse_season_years,
    select_section,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "rsssf"
NPFL = "National League/Nigeria Football League"


def _entries(name: str, section: str = ""):
    page = decode_page((FIXTURES / name).read_bytes())
    return select_section(parse_index(page), section)


# ---------------------------------------------------------------------------
# parse_season_years
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "years"),
    [
        ("2015", (2015, 2015)),
        ("2021/22", (2021, 2022)),
        ("1999/00", (1999, 2000)),
        ("2009/10", (2009, 2010)),
        ("2023/2024", (2023, 2024)),
        # Decision 28: '-' in place of '/' (Lesotho).
        ("2021-22", (2021, 2022)),
        (" 1972 ", (1972, 1972)),
    ],
)
def test_season_years(label, years):
    assert parse_season_years(label) == years


@pytest.mark.parametrize(
    "label",
    # '1966-68' covers two seasons (Libya); '1974,1' is a part of a year;
    # '1990/00' is a typo for 1999/00 (Cape Verde).
    ["1999/01", "2021/2023", "1931-1945", "1966-68", "1974,1", "1990/00", "Final", ""],
)
def test_not_a_season(label):
    assert parse_season_years(label) is None


# ---------------------------------------------------------------------------
# Nigeria: <b> headings in one <pre> block
# ---------------------------------------------------------------------------


def test_nigeria_league_section():
    entries = _entries("nigchamp.html", NPFL)

    first = entries[0]
    assert (first.href, first.label, first.start_year, first.end_year) == (
        "nig72.html#72",
        "1972",
        1972,
        1972,
    )
    assert first.champion == "Mighty Jets (Jos)"
    assert entries[-1].label == "2025/26"


def test_nigeria_other_competition_is_not_in_the_section():
    # The Amachree Gold Cup 1971 is on the same page, under its own heading.
    labels = [e.label for e in _entries("nigchamp.html", NPFL)]
    assert "1971" not in labels


def test_file_name_is_not_the_season():
    # nig2022.html is the 2021/22 season, and nig2023.html is 2023.
    by_href = {e.href: e for e in _entries("nigchamp.html", NPFL)}
    assert (by_href["nig2022.html"].start_year, by_href["nig2022.html"].end_year) == (
        2021,
        2022,
    )
    assert (by_href["nig2023.html"].start_year, by_href["nig2023.html"].end_year) == (
        2023,
        2023,
    )


def test_note_in_brackets_is_not_in_the_champion():
    by_label = {e.label: e for e in _entries("nigchamp.html", NPFL)}
    assert by_label["1973"].champion == "Bendel Insurance (Benin City)"


# ---------------------------------------------------------------------------
# Egypt: <h4> headings before the <pre> blocks
# ---------------------------------------------------------------------------


def test_egypt_same_page_in_two_lists():
    # egy49.html 1948/49 is in the Cairo League list and in the National
    # League list, with different champions.
    all_entries = _entries("egychamp.html")
    both = [e for e in all_entries if e.href == "egy49.html"]
    assert {e.section for e in both} == {"Cairo League", "National League"}

    [national] = [
        e
        for e in _entries("egychamp.html", "National League")
        if e.href == "egy49.html"
    ]
    assert national.champion == "Al-Ahly"


def test_egypt_season_line_without_a_link_is_skipped():
    # '1951/52   not held' has no page.
    labels = [e.label for e in _entries("egychamp.html", "National League")]
    assert "1951/52" not in labels
    assert "1952/53" in labels


def test_egypt_anchor_is_kept():
    hrefs = [e.href for e in _entries("egychamp.html")]
    assert "egy1913.html#bola1" in hrefs


# ---------------------------------------------------------------------------
# Ghana: one <pre> block without headings
# ---------------------------------------------------------------------------


def test_ghana_all_seasons_without_a_section():
    entries = _entries("ghachamp.html")
    assert entries[0].label == "1956"
    assert entries[0].champion == "Hearts of Oak"  # without '[unofficial]'
    assert len(entries) == 67


def test_link_in_the_text_is_not_a_season_line():
    # The text before the list has a link to gha53.html.
    hrefs = [e.href for e in _entries("ghachamp.html")]
    assert "gha53.html" not in hrefs


def test_ghana_file_names_and_seasons():
    by_href = {e.href: e for e in _entries("ghachamp.html")}
    assert by_href["gha04.html"].label == "2004/05"
    assert by_href["gha05.html"].label == "2005"


def test_section_comparison_ignores_case_and_spaces():
    entries = _entries("egychamp.html")
    assert select_section(entries, "  national   LEAGUE ") == select_section(
        entries, "National League"
    )


def test_unknown_section_gives_no_entries():
    assert _entries("egychamp.html", "Premier League") == []


# ---------------------------------------------------------------------------
# Line forms of other countries (decision 28)
# ---------------------------------------------------------------------------


def test_congo_row_numbers_before_the_links():
    # ' 1 <a href="kong79.html">1979</a>  Etoile du Congo ...' to '14 ...'.
    entries = [e for e in _entries("kongchamp.html") if 1979 <= e.start_year <= 1994]
    assert len(entries) == 14
    assert (entries[0].href, entries[0].label) == ("kong79.html", "1979")
    assert (entries[-1].href, entries[-1].champion) == (
        "kong94.html",
        "abandoned due to civil war",
    )


def test_south_africa_column_label_before_the_heading():
    # 'year    <b>PSL</b>': the 30 PSL seasons are in their own section.
    psl = _entries("zafchamp.html", "PSL")
    assert len(psl) == 30
    assert (psl[0].label, psl[-1].label) == ("1996/97", "2025/26")


def test_south_africa_line_in_italics():
    # '<i><a href="zaf96.html">1996</a>    Kaizer Chiefs  [transitional ...]</i>'
    [entry] = _entries("zafchamp.html", "Coca Cola Challenge")
    assert (entry.href, entry.label, entry.champion) == (
        "zaf96.html",
        "1996",
        "Kaizer Chiefs",
    )


@pytest.mark.parametrize(
    ("line", "label"),
    [
        (' 1 <a href="kong79.html">1979</a>  Etoile du Congo', "1979"),
        ('14. <a href="x94.html">1994</a>  Club', "1994"),
        ('<i><a href="soed2024.html">2024</a>   Al-Hilal</i>', "2024"),
        ('<a href="leso2021.html">2021-22</a> Matlama FC (Maseru)', "2021-22"),
    ],
)
def test_season_line_forms(line, label):
    [entry] = parse_index(f"<pre>\n{line}\n</pre>")
    assert entry.label == label


@pytest.mark.parametrize(
    "line",
    [
        # A link in a sentence is not a season line.
        'additional information on <a href="nig31.html">1931-1945</a>;',
        'e.g. in <a href="burkf57.html">1956/57</a>.',
        '[*4] <a href="https://example.org/">around 1942</a>',
    ],
)
def test_links_in_text_are_not_season_lines(line):
    assert parse_index(f"<pre>\n{line}\n</pre>") == []
