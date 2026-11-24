"""
parser.py: read the matches of the top league from an RSSSF season page.

An RSSSF season page has the results of one country and one season, often
for several competitions (the league, the cup, lower divisions). The
project examined the pages of Nigeria, Ghana and Egypt, and samples of
three more countries (decision 22). The pages have two structures:

    A (newer):  each competition has a heading <h4><a name="...">Name</a></h4>
                and its own <pre> block. In the block, <b> lines are stages
                and <u> lines are groups.
    B (older):  one <pre> block for the page. split_one_block() finds the
                competitions in it.

The parser does these steps:

    1. split_competitions(): the competitions of the page, with their text.
    2. top_league(): the first competition that has results.
    3. parse_lines(): one ResultRow for each result line, and the lines that
       look like a result but do not have the known form (unparsed).
    4. to_source_match(): a SourceMatch for each ResultRow.

A result line has the home team, the result and the away team. After the
away team, two spaces or a tab can start a note:

    Real Tamale United      1-0 Hearts of Oak
    Kwara\t\t3-0 Nationale
    Great Olympics          awd Real Tamale United      [awarded 3-0, RTU forfeited]
    FC De Leo               1-1 EFCC                    [4-5 pen]

A note can continue on the next lines, in a column at the right of the next
result lines:

    Gombe United            1-1 Rivers United           [Gombe United 3 points and 3 goals
    Enyimba                 2-0 Sporting Lagos           deducted due to fan misconduct
    Akwa United             3-1 Abia Warriors            (assault on match officials)]

The dates have no year: [Sep 15]. A calendar-year season gives the year. In
a season over two years, a month on or after the first month of the
competition is in the first year, and an earlier month is in the second
year.
"""

import html
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from pydantic import ValidationError

from african_football.models.source_match import MatchStatus, SourceMatch

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_H4_PRE = re.compile(
    r"<h4[^>]*>(?P<name>.*?)</h4>\s*<pre[^>]*>(?P<text>.*?)</pre>",
    re.IGNORECASE | re.DOTALL,
)
_PRE = re.compile(r"<pre[^>]*>(?P<text>.*?)</pre>", re.IGNORECASE | re.DOTALL)
_TITLE = re.compile(r"<h2[^>]*>(?P<title>.*?)</h2>", re.IGNORECASE | re.DOTALL)

# A stage or group heading in structure A: <b>Group Stage</b>, <u>Group A</u>.
_STAGE_TAG = re.compile(r"^\s*<(b|u)>(?P<text>.*?)</\1>\s*$", re.IGNORECASE)

_UNDERLINE = re.compile(r"^\s*={3,}\s*$")

# A competition heading without a line of '=' (structure B).
_COMPETITION_HEADING = re.compile(
    r"^(?=[A-Z])(?=[^:\[\]]*\b(?:League|Division|Level|Cup|Shield|Championship"
    r"|Tournament|Trophy)\b)[^:\[\]]{3,80}$"
)

# Lines that can come after a final table, in the same competition.
_AFTER_TABLE = re.compile(
    r"^\s*(?:-[ -]*$|NB|Promoted|Relegated|Champions|\(|\[)|^\s+\S", re.IGNORECASE
)

_MONTHS = {
    name: number
    for number, name in enumerate(
        [
            "jan",
            "feb",
            "mar",
            "apr",
            "may",
            "jun",
            "jul",
            "aug",
            "sep",
            "oct",
            "nov",
            "dec",
        ],
        start=1,
    )
}
# The first day of a date in [ ]: [Sep 15], [Sep 15, 2023], [Mar 24,25],
# [Feb 28/Mar 1?].
_DATE = (
    r"\[(?P<mon>[A-Za-z]{3})[a-z]*\.? (?P<day>\d{1,2})"
    r"(?:, ?(?P<year>\d{4}))?(?:[,/][^\]]*)?\??\]"
)
_DATE_LINE = re.compile(rf"^\s*{_DATE}")

# A round heading, with an optional date on the same line.
_ROUND = re.compile(
    r"^\s*(?P<name>(?:Replay )?(?:Round|Week|Matchday|Day) (?P<number>\d+)"
    r"|Final|Semi-?finals?|Quarter-?finals?|Third Place(?: Match)?)\s*"
    rf"(?:{_DATE})?\s*$",
    re.IGNORECASE,
)

# A play-off of the league, for example 'Promotion/Relegation Playoff [May 4]'.
# It is a stage of the league, not a new competition.
_PLAYOFF_STAGE = re.compile(
    rf"^\s*(?P<name>[A-Z][\w/ -]*Play-?offs?(?: Final)?)\s*(?:{_DATE})?\s*$",
    re.IGNORECASE,
)

# A zone heading in a round: Zone 1 [Oct 1]
_ZONE = re.compile(rf"^\s*(?P<name>Zone \w+)\s*(?:{_DATE})?\s*$", re.IGNORECASE)

_RESULT_WORDS = "awd|abd|w/o|unk|bt|lt|drw"
_SCORE = r"\d{1,2}-\d{1,2}"

# After the away team: two spaces, a tab, or one space and '[', then the
# rest of the line. The rest is a note, or the next part of an open note.
_RESULT_LINE = re.compile(
    r"^(?P<home>\S(?:.*?\S)?)[ \t]+"
    rf"(?P<result>{_SCORE}|{_RESULT_WORDS})"
    r"[ \t]+(?P<away>[^\s\[](?:(?! {2}|\t).)*?[^\s\[]|[^\s\[])"
    r"(?:(?:[ \t]{2,}|\t|[ \t]+(?=\[))(?P<rest>.*?))?[ \t]*$"
)

# A line that looks like a result: a word, a result, a word.
_LOOKS_LIKE_RESULT = re.compile(rf"\S[ \t]+(?:{_SCORE}|{_RESULT_WORDS})[ \t]+\S")

_TABLE_ROW = re.compile(r"^\s*\d+\.\s*\S")
_FINAL_TABLE = re.compile(r"^\s*Final Table", re.IGNORECASE)
_LETTER = re.compile(r"[^\W\d_]")

# The start of a season in a page with many seasons, at the start of a line:
# <b><a name="72">1972</a></b> (Nigeria) or <a name="64">1963/64</a> (Ghana).
# An anchor after other text on its line (<u><a name="amachree71">) is a
# part of a season, not the start of a season.
_SEASON_ANCHOR = r'^[ \t]*(?:<b>\s*)?<a name="?{anchor}"?>'
_NEXT_SEASON = re.compile(
    r"^[ \t]*(?:<b>\s*)?<a name=|<h[1-4]|</pre>", re.IGNORECASE | re.MULTILINE
)

# Two or more scores on one line: a row of a results grid or a crosstable.
_SCORES = re.compile(r"(?<![\d-])\d{1,2}-\d{1,2}(?![\d-])")
_PENALTIES = re.compile(r"(?P<home>\d+)-(?P<away>\d+) ?pen")
_AWARDED = re.compile(
    r"awarded (?P<h1>\d+)-(?P<a1>\d+)|(?P<h2>\d+)-(?P<a2>\d+) awarded", re.IGNORECASE
)
_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Competition:
    """One competition of a season page: its name and the text of its block."""

    name: str
    text: str


@dataclass(frozen=True)
class ResultRow:
    """
    One result line, before it becomes a SourceMatch.

    result: the result text of the line: '2-1', 'awd', 'abd', 'w/o', 'unk',
            'bt' (the home team won, no score), 'lt' (the home team lost)
            or 'drw' (a draw, no score).
    note:   the note of the line, or None. A note in [ ] that continues on
            the next lines has only its first part here.
    """

    stage: str
    round_name: Optional[str]
    round_number: Optional[int]
    match_date: Optional[date]
    home: str
    away: str
    result: str
    note: Optional[str]


@dataclass
class ParseResult:
    """The rows of a competition, and the lines that the parser did not read."""

    rows: list[ResultRow] = field(default_factory=list)
    unparsed: list[str] = field(default_factory=list)
    # Lines with two or more scores: rows of a results grid or a crosstable.
    # The parser does not read this form.
    grid_lines: int = 0


# ---------------------------------------------------------------------------
# Steps 1 and 2: the competitions, and the top league
# ---------------------------------------------------------------------------


def _is_result(line: str) -> bool:
    """True for a result line.

    A table row (' 1.Enyimba  38 21 9 8 63-22 72') has a score-like text
    too, but it is not a result line. A line with a label and ':' before
    the teams ('Cup Final: Al Mokaoulun 2-0 Al Mehalla') is not a result
    line of the league: a team name never has ':'. A team name has a
    letter: in 'Zamalek  0-0 2-2' (the two results of one team against
    Zamalek), '2-2' is not a team.
    """
    if _TABLE_ROW.match(line):
        return False
    match = _RESULT_LINE.match(line)
    return (
        match is not None
        and ":" not in match["home"]
        and _LETTER.search(match["home"]) is not None
        and _LETTER.search(match["away"]) is not None
    )


def split_competitions(page: str) -> list[Competition]:
    """Give the competitions of a season page, in page sequence."""
    blocks = [Competition(_clean(m["name"]), m["text"]) for m in _H4_PRE.finditer(page)]
    if blocks:
        return blocks
    pre = _PRE.search(page)
    if pre is None:
        return []
    title = _TITLE.search(page)
    return split_one_block(pre["text"], _clean(title["title"]) if title else "")


def split_one_block(text: str, first_name: str) -> list[Competition]:
    """Split the one <pre> block of structure B into competitions.

    A new competition starts at:
    1. a heading with a line of '=' under it;
    2. a heading line with a competition word (League, Division, Cup, ...)
       and without ':', for example 'Division One (Second Level) early 2003';
    3. the first line after a final table, if the results came before the
       table, and if the line is not a round, a date or a result of the
       league. Some pages start the cup there without a heading. A table in
       the middle of a league ('Table:' after round 10) does not end it.
    """
    competitions: list[Competition] = []
    name = first_name
    current: list[str] = []
    has_results = False
    final_table = False
    in_table = False
    lines = text.splitlines()

    def close(new_name: str) -> None:
        nonlocal name, current, has_results, final_table, in_table
        if any(line.strip() for line in current):
            competitions.append(Competition(name, "\n".join(current)))
        name, current = new_name, []
        has_results = final_table = in_table = False

    for i, raw_line in enumerate(lines):
        line = _clean_line(raw_line)
        next_line = _clean_line(lines[i + 1]) if i + 1 < len(lines) else ""
        if _UNDERLINE.match(line):
            continue
        if line.strip() and _UNDERLINE.match(next_line):
            close(_clean(line))
            continue
        if _COMPETITION_HEADING.match(line) and not _is_result(line):
            close(_clean(line))
            continue
        if _FINAL_TABLE.match(line):
            final_table = True
        elif _TABLE_ROW.match(line):
            in_table = has_results and final_table
        elif in_table and line.strip() and not _AFTER_TABLE.match(line):
            in_table = final_table = False
            if not _continues_league(line):
                close("")
        if _is_result(line):
            has_results = True
        current.append(raw_line)
    close("")
    return competitions


def _continues_league(line: str) -> bool:
    """True for a numbered round, a date or a result line."""
    round_match = _ROUND.match(line)
    return (
        (round_match is not None and round_match["number"] is not None)
        or _DATE_LINE.match(line) is not None
        or _is_result(line)
    )


def season_part(page: str, anchor: str) -> Optional[str]:
    """Give the part of a page with many seasons that is one season.

    The part starts at the anchor and stops at the next season anchor, a
    heading, or the end of the <pre> block. The
    result is a page with one <pre> block (structure B). None if the page
    has no such anchor.
    """
    start = re.search(
        _SEASON_ANCHOR.format(anchor=re.escape(anchor)),
        page,
        re.IGNORECASE | re.MULTILINE,
    )
    if start is None:
        return None
    body_start = page.find("\n", start.end())
    if body_start == -1:
        return None
    end = _NEXT_SEASON.search(page, body_start)
    body = page[body_start : end.start() if end else len(page)]
    title = _clean(page[start.start() : body_start])
    return f"<h2>{title}</h2>\n<pre>{body}</pre>"


def top_league(page: str) -> Optional[Competition]:
    """Give the first competition of the page that has a result line."""
    for competition in split_competitions(page):
        if any(_is_result(_clean_line(line)) for line in competition.text.splitlines()):
            return competition
    return None


# ---------------------------------------------------------------------------
# Step 3: the lines
# ---------------------------------------------------------------------------


def parse_lines(
    competition: Competition, start_year: int, end_year: int
) -> ParseResult:
    """Read the result lines of a competition."""
    result = ParseResult()
    stage = competition.name
    round_name: Optional[str] = None
    round_number: Optional[int] = None
    current_date: Optional[date] = None
    first_month: Optional[int] = None
    open_note = False

    def to_date(match: re.Match[str]) -> Optional[date]:
        nonlocal first_month
        month = _MONTHS.get(match["mon"].lower())
        if month is None:
            return None
        if first_month is None:
            first_month = month
        if match["year"]:
            year = int(match["year"])
        elif start_year == end_year or month >= first_month:
            year = start_year
        else:
            year = end_year
        try:
            return date(year, month, int(match["day"]))
        except ValueError:
            return None

    for raw_line in competition.text.splitlines():
        stage_tag = _STAGE_TAG.match(raw_line)
        if stage_tag is not None:
            stage = _clean(stage_tag["text"])
            round_name = round_number = None
            current_date = None
            open_note = False
            continue

        line = _clean_line(raw_line)
        if not line.strip():
            continue

        # A line that starts with a space or a tab is a list of scorers, a
        # note, or the next part of a note. It is never a result line.
        if line[0] in (" ", "\t"):
            if "[" in line:
                open_note = "]" not in line[line.rindex("[") :]
            elif "]" in line:
                open_note = False
            continue
        if _TABLE_ROW.match(line) or line.startswith(("NB", "-", "(")):
            continue

        date_match = _DATE_LINE.match(line)
        if date_match is None and line.startswith("["):
            # A note at the start of a line, for example
            # '[*14] w/o goals rd 14 (Liberty bt Goldfields by 1)'.
            open_note = "]" not in line
            continue
        if date_match is not None:
            current_date = to_date(date_match)
            line = line[date_match.end() :].strip()
            if not line:
                continue

        round_match = _ROUND.match(line)
        if round_match is not None:
            round_name = _SPACES.sub(" ", round_match["name"]).strip()
            round_number = int(round_match["number"]) if round_match["number"] else None
            # A round without a date has no date: the date of the round
            # before it is not correct for it.
            current_date = to_date(round_match) if round_match["mon"] else None
            continue

        playoff = _PLAYOFF_STAGE.match(line)
        if playoff is not None:
            stage = _SPACES.sub(" ", playoff["name"]).strip()
            round_name = round_number = None
            current_date = to_date(playoff) if playoff["mon"] else None
            continue

        zone = _ZONE.match(line)
        if zone is not None:
            if zone["mon"]:
                current_date = to_date(zone)
            continue

        row = _RESULT_LINE.match(line) if _is_result(line) else None
        if row is None:
            if len(_SCORES.findall(line)) >= 2:
                result.grid_lines += 1
            elif _LOOKS_LIKE_RESULT.search(line):
                result.unparsed.append(line.strip())
            elif "]" in line:
                open_note = False
            continue

        rest = (row["rest"] or "").strip()
        note: Optional[str] = None
        if open_note:
            # The rest is the next part of an open note.
            if "]" in rest:
                open_note = False
        elif rest.startswith("["):
            note = rest[1:].split("]", 1)[0].strip()
            open_note = "]" not in rest
        result.rows.append(
            ResultRow(
                stage=stage,
                round_name=round_name,
                round_number=round_number,
                match_date=current_date,
                home=row["home"].strip(),
                away=row["away"].strip(),
                result=row["result"],
                note=note or None,
            )
        )
    return result


# ---------------------------------------------------------------------------
# Step 4: SourceMatch
# ---------------------------------------------------------------------------


def to_source_match(
    row: ResultRow,
    *,
    match_id: str,
    source_url: str,
    league_code: str,
    season: str,
    timezone: str,
    raw_documents: tuple[str, ...],
) -> SourceMatch:
    """Make a SourceMatch from a ResultRow.

    Raises pydantic.ValidationError if the row is not a valid match, for
    example a penalty shootout after a match that was not a draw.
    """
    home_goals = away_goals = pen_home = pen_away = None
    note = row.note or ""
    if re.fullmatch(_SCORE, row.result):
        status = MatchStatus.PLAYED
        home_goals, away_goals = (int(x) for x in row.result.split("-"))
        penalties = _PENALTIES.search(note)
        # A note can name a penalty in a match without a shootout, for
        # example '1-0 [Masry scored a pen]'. A shootout needs a draw.
        if penalties is not None and home_goals == away_goals:
            pen_home, pen_away = int(penalties["home"]), int(penalties["away"])
    elif row.result == "awd":
        status = MatchStatus.AWARDED
        awarded = _AWARDED.search(note)
        if awarded is not None:
            home_goals = int(awarded["h1"] or awarded["h2"])
            away_goals = int(awarded["a1"] or awarded["a2"])
    elif row.result == "w/o":
        status = MatchStatus.AWARDED
    elif row.result == "abd":
        status = MatchStatus.ABANDONED
    else:
        # unk, bt, lt, drw: the source does not give a score.
        status = MatchStatus.UNKNOWN

    return SourceMatch(
        source="rsssf",
        source_match_id=match_id,
        source_url=source_url,
        raw_documents=raw_documents,
        league_code=league_code,
        season=season,
        stage=row.stage or None,
        round_name=row.round_name,
        round_number=row.round_number,
        match_date=row.match_date,
        timezone=timezone,
        home_team_raw=row.home,
        away_team_raw=row.away,
        home_goals=home_goals,
        away_goals=away_goals,
        pen_home=pen_home,
        pen_away=pen_away,
        status=status,
    )


def match_ids(rows: list[ResultRow], league_code: str, season: str) -> list[str]:
    """Give a stable ID for each row: league/season/stage/home-away.

    A second meeting of the same teams in the same stage (for example a
    replay) gets '#2' at the end.
    """
    seen: dict[str, int] = {}
    ids = []
    for row in rows:
        key = f"{league_code}/{season}/{row.stage}/{row.home}-{row.away}"
        seen[key] = seen.get(key, 0) + 1
        ids.append(key if seen[key] == 1 else f"{key}#{seen[key]}")
    return ids


def parse_page(
    page: str,
    *,
    league_code: str,
    season: str,
    start_year: int,
    end_year: int,
    timezone: str,
    source_url: str,
    raw_documents: tuple[str, ...],
    anchor: str = "",
) -> tuple[list[SourceMatch], list[str]]:
    """Give the matches of the top league of a page, and the problems.

    anchor: for a page with many seasons, the anchor of the season (from the
    season URL, for example '72' in nig72.html#72). The parser reads only
    the part of the page for that season.

    The problems are the lines that look like a result but were not read,
    and the rows that are not a valid SourceMatch.
    """
    if anchor:
        part = season_part(page, anchor)
        if part is None:
            return [], [f"no season part for the anchor #{anchor}"]
        page = part
    competition = top_league(page)
    if competition is None:
        # No result lines. A page with the results only as a grid must not
        # look the same as a page without results.
        grid_lines = sum(
            len(_SCORES.findall(_clean_line(line))) >= 2
            for c in split_competitions(page)
            for line in c.text.splitlines()
            if not _TABLE_ROW.match(_clean_line(line))
        )
        if grid_lines:
            return [], [f"{grid_lines} lines of a results grid or crosstable not read"]
        return [], []
    parsed = parse_lines(competition, start_year, end_year)
    problems = [f"not read: {line}" for line in parsed.unparsed]
    if parsed.grid_lines:
        problems.append(
            f"{parsed.grid_lines} lines of a results grid or crosstable not read"
        )
    matches = []
    for row, match_id in zip(parsed.rows, match_ids(parsed.rows, league_code, season)):
        try:
            matches.append(
                to_source_match(
                    row,
                    match_id=match_id,
                    source_url=source_url,
                    league_code=league_code,
                    season=season,
                    timezone=timezone,
                    raw_documents=raw_documents,
                )
            )
        except ValidationError as error:
            reason = error.errors()[0]["msg"]
            problems.append(f"not valid: {row.home} {row.result} {row.away}: {reason}")
    return matches, problems


def _clean(text: str) -> str:
    return _SPACES.sub(" ", html.unescape(_TAG.sub("", text))).strip()


def _clean_line(line: str) -> str:
    """Remove the HTML tags of a line, and keep its spaces and tabs."""
    return html.unescape(_TAG.sub("", line)).rstrip()
