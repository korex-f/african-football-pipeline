"""
index.py: read an RSSSF list of champions, and find the season pages.

Each country on RSSSF has a page with the list of champions, for example
https://www.rsssf.org/tablesn/nigchamp.html. In the list, each season with a
page has a line of this form:

    <a href="nig2022.html">2021/22</a> Rivers United (Port Harcourt)

The project examined these pages for Nigeria, Ghana and Egypt (decision 21):

- The list is in <pre> blocks.
- A page can have lists of different competitions. A list has a heading:
  a <b> line in the <pre> block (Nigeria), or an <h4> before the block
  (Egypt). The same season page can be in two lists. For example, Egypt
  'egy49.html' 1948/49 is in the Cairo League list and in the National
  League list, with different champions. Thus the adapter selects the list
  with the heading in leagues.yaml (rsssf_section).
- The text of the link is the season. The file name is not: 'gha04.html' is
  2004/05 and 'gha05.html' is 2005.
- A link can have an anchor, because one page can have more than one season
  ('egy1913.html#bola1').
- A line without a link ('1957      no championship') has no season page.
- A link in the text before the list is not a season line. Only a link at
  the start of a line in a <pre> block is a season line.

This module does not use the network. RsssfAdapter gives it the HTML.
"""

import html
import re
from dataclasses import dataclass
from typing import Optional

# A heading (<h1> to <h4>) or a <pre> block, in the sequence of the page.
_BLOCK = re.compile(
    r"<h([1-4])[^>]*>(?P<heading>.*?)</h\1>|<pre[^>]*>(?P<pre>.*?)</pre>",
    re.IGNORECASE | re.DOTALL,
)

# A heading line in a <pre> block: <b>Lagos League</b>. The label of the
# first column can come before it: 'year    <b>PSL</b>' (South Africa,
# decision 28).
_BOLD_LINE = re.compile(r"^\s*(?:year\s+)?<b>(?P<text>.*?)</b>\s*$", re.IGNORECASE)

# A season line: <a href="nig2022.html">2021/22</a> Rivers United (Port Harcourt)
# Before the link, a line can have a row number (' 1 <a href=...', Congo)
# or the start of italics ('<i><a href=...', Sudan) (decision 28).
_SEASON_LINE = re.compile(
    r"^\s*(?:\d{1,3}\.?\s+)?(?:<i>\s*)?"
    r'<a\s+href="(?P<href>[^"]+)"\s*>(?P<label>[^<]*)</a>(?P<rest>.*)$',
    re.IGNORECASE,
)

# The season text: 2015, 2021/22, 1999/00, 2023/2024, or with '-' in place
# of '/' (2021-22, Lesotho; decision 28).
_LABEL = re.compile(r"^(?P<start>\d{4})(?:[/-](?P<end>\d{2}|\d{4}))?$")

_TAG = re.compile(r"<[^>]+>")
_NOTE = re.compile(r"\s*\[[^\]]*\]")
_SPACES = re.compile(r"\s+")


@dataclass(frozen=True)
class IndexEntry:
    """
    One season line in an RSSSF list of champions.

    section:    the heading of the list, for example 'National League'.
    href:       the link, relative to the index page, for example
                'nig2022.html' or 'egy1913.html#bola1'.
    label:      the season text of the link, for example '2021/22'.
    start_year: the first year of the season, for example 2021.
    end_year:   the last year of the season. For a calendar-year season,
                the same as start_year.
    champion:   the champion, without the notes in [ ], or None.
    """

    section: str
    href: str
    label: str
    start_year: int
    end_year: int
    champion: Optional[str]


def parse_season_years(label: str) -> Optional[tuple[int, int]]:
    """Give the start year and the end year of an RSSSF season text.

    '2015' gives (2015, 2015). '2021/22' and '2021-22' give (2021, 2022).
    '1999/00' gives
    (1999, 2000): the end year is the next year, also across a century.
    Text that is not a season, or a season longer than one year change
    ('1999/01'), gives None.
    """
    match = _LABEL.match(label.strip())
    if match is None:
        return None
    start = int(match["start"])
    end_text = match["end"]
    if end_text is None:
        return start, start
    if len(end_text) == 4:
        end = int(end_text)
    else:
        # Two digits: the end year is in the same century as start + 1.
        # 1999/00 -> 2000, 2021/22 -> 2022.
        end = (start + 1) // 100 * 100 + int(end_text)
    if end != start + 1:
        return None
    return start, end


def parse_index(page: str) -> list[IndexEntry]:
    """Give the season lines of an RSSSF list of champions, in page sequence.

    Each entry has the heading of its list. A <b> line in a <pre> block
    starts a new list. An <h1> to <h4> heading applies to the <pre> blocks
    after it, until the next heading.
    """
    entries: list[IndexEntry] = []
    section = ""
    for block in _BLOCK.finditer(page):
        if block["heading"] is not None:
            section = _clean(block["heading"])
            continue
        for line in block["pre"].splitlines():
            bold = _BOLD_LINE.match(line)
            if bold is not None:
                section = _clean(bold["text"])
                continue
            entry = _season_entry(line, section)
            if entry is not None:
                entries.append(entry)
    return entries


def select_section(entries: list[IndexEntry], section: str) -> list[IndexEntry]:
    """Give the entries of one list.

    The comparison ignores upper and lower case and extra spaces. An empty
    section gives all the entries.
    """
    if not section:
        return list(entries)
    wanted = _normal(section)
    return [e for e in entries if _normal(e.section) == wanted]


def _season_entry(line: str, section: str) -> Optional[IndexEntry]:
    """Make an IndexEntry from a season line, or give None."""
    match = _SEASON_LINE.match(line)
    if match is None:
        return None
    years = parse_season_years(_clean(match["label"]))
    if years is None:
        return None
    champion = _NOTE.sub("", _clean(match["rest"])).strip()
    return IndexEntry(
        section=section,
        href=html.unescape(match["href"]),
        label=_clean(match["label"]),
        start_year=years[0],
        end_year=years[1],
        champion=champion or None,
    )


def _clean(text: str) -> str:
    """Remove the HTML tags and entities, and collapse the spaces."""
    return _SPACES.sub(" ", html.unescape(_TAG.sub("", text))).strip()


def _normal(text: str) -> str:
    return _clean(text).casefold()
