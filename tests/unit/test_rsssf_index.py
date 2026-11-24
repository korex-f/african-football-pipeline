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
        (" 1972 ", (1972, 1972)),
    ],
)
def test_season_years(label, years):
    assert parse_season_years(label) == years


@pytest.mark.parametrize("label", ["1999/01", "2021/2023", "1931-1945", "Final", ""])
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
