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
from dataclasses import dataclass, field, replace
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
# The words in English, French and Portuguese: the pages of all African
# countries use them (decision 24).
_COMPETITION_HEADING = re.compile(
    r"^(?=[A-Z])(?=[^:\[\]]*\b(?i:League|Ligue|Liga|Division|Divis[aã]o|Level|Cup"
    r"|Coupe|Copa|Ta[çc]a|Shield|Championship|Championnat|Campeonato|Tournament"
    r"|Tournoi|Torneio|Trophy|Botola|Premiership|Supercoupe|Super ?Ta[çc]a)\b)"
    r"[^:\[\]]{3,80}$"
)

# The kinds of competition names, for choose_league() (decision 24).
_CUP = re.compile(
    r"\b(?:cup|coupe|copa|ta[çc]a|trophy|shield|super ?cup|supercoupe"
    r"|super ?ta[çc]a|charity|challenge|knock-?out|kass|tournament|tournoi"
    r"|torneio|trofeo)\b",
    re.IGNORECASE,
)
_LOWER = re.compile(
    r"\b(?:second|third|fourth|2nd|3rd|4th|deuxi[eè]me|2[eè]me|2e|troisi[eè]me"
    r"|3[eè]me|segunda|terceira|ii|iii|iv|two|three|lower|amateur|regional"
    r"|provincial|district|distrital|distrito|reserves?|youth|juniors?|women"
    r"|ladies|f[ée]minine?|u-?\d{2}|promotion|qualif\w*|stream)\b"
    # 'Régional 1' is the top league of Réunion: not lower.
    r"|\br[ée]gionale?\b(?!\s*1\b)"
    r"|\b(?:ligue|liga|division|divis[aã]o|level|d)\s*[2-9]\b"
    # '2ª Divisão', '2nd Division', '2ème Division'.
    r"|\b[2-9](?:ª|º|nd|rd|th|e|[eè]me)?\s*(?:divis|level|liga|ligue)"
    # 'Division Nationale B', 'Division 1 North'.
    r"|\bnationale?\s+[b-d]\b|\b(?:north|south|east|west)(?:ern)?\s*$"
    # 'Ligue Professionnelle 2'.
    r"|\s(?:[2-9]|ii|iii|iv|b)\s*$",
    re.IGNORECASE,
)
_PLAYOFF = re.compile(
    r"\b(?:play-?offs?|barrages?|mini-?league|final (?:round|stage|tournament))\b",
    re.IGNORECASE,
)
_LEAGUE_WORD = re.compile(
    r"\b(?:league|ligue|liga|division|divis[aã]o|championnat|campeonato"
    r"|championship|botola|premiership|ligi|super ?ligue|girabola)\b",
    re.IGNORECASE,
)
# The words of a part of a league: 'First Stage', 'Group A' (step 3).
_STAGE_WORD = re.compile(
    r"\b(?:stage|phase|round|group|groupe|grupo|poule|s[ée]rie|zone)\b",
    re.IGNORECASE,
)
# An abbreviation of a league name: NPFL, GPL, PSL. Upper case only, thus
# not a normal word.
_LEAGUE_ABBREVIATION = re.compile(r"\b[A-Z]{1,4}L\b")

_NATIONAL = re.compile(
    r"\b(?:national|nacional|nationale|premier|premi[eè]re|1[eè]re|1re|1st|first"
    r"|[ée]lite|primeira|primera|botola|ligi kuu|professional|professionnelle"
    r"|premiership|super ?league|super ?ligue|girabola|ligue ?1|liga ?1"
    r"|division ?(?:1|one|i))\b",
    re.IGNORECASE,
)
# Small words that a competition name can have: 'Championnat National de
# 1ère Division', 'Ligue du Protectorat Français au Maroc'.
_CONNECTORS = frozenset(
    "de da do das dos du des la le les l d of and e et del el au aux the".split()
)

_NOTE_WORDS = re.compile(
    r"\b(?:the|of|to|for|in|were|was|after|before|since|qualify|qualified"
    r"|withdrew|due|played|because|no|not|held|between|only)\b",
    re.IGNORECASE,
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

# The result words (decision 25): awarded, abandoned, walkover, unknown,
# beat, lost to, draw, tie (a draw), not played, postponed, annulled, and
# '---' (no result), in upper or lower case ('W/o', 'Ppd'). 'bye', 'vs' and
# 'draw' (in sentences) are not results.
_RESULT_WORDS = "awd|abd|w/o|unk|bt|lt|drw|tie|n/p|ppd|ann|---"
# A score; '3-0*' (a mark); '?-?', '3-?' (a score that is not known).
_SCORE = r"\d{1,2}-\d{1,2}\*?|\?-\?|\d{1,2}-\?|\?-\d{1,2}"

# After the away team: two spaces, a tab, or one space and '[', then the
# rest of the line. The rest is a note, or the next part of an open note.
_RESULT_LINE = re.compile(
    r"^(?P<home>\S(?:.*?\S)?)[ \t]+"
    rf"(?P<result>{_SCORE}|{_RESULT_WORDS})"
    r"[ \t]+(?P<away>[^\s\[](?:(?! {2}|\t).)*?[^\s\[]|[^\s\[])"
    r"(?:(?:[ \t]{2,}|\t|[ \t]+(?=\[))(?P<rest>.*?))?[ \t]*$",
    re.IGNORECASE,
)

# A line that looks like a result: a word, a result, a word.
_LOOKS_LIKE_RESULT = re.compile(
    rf"\S[ \t]+(?:{_SCORE}|{_RESULT_WORDS})[ \t]+\S", re.IGNORECASE
)

# Teams first, then the score: 'Al-Menya - Al-Ahly   1-3',
# 'FC HellBourg. - US Ste Anne : 6-1'. A fixture without a score
# ('MC Alger   -  Paradou AC') is not a result.
_TEAMS_FIRST = re.compile(
    r"^(?P<home>\S(?:.*?\S)?)[ \t]+-[ \t]+(?P<away>\S(?:.*?\S)?)"
    r"[ \t]*:?[ \t]+(?P<result>\d{1,2}-\d{1,2})(?:[ \t]+(?P<rest>.*?))?[ \t]*$"
)

# A heading with numbers, not a result: 'Rounds 6-9 missing', 'Round 19
# [postponed from Mar 2-4 ...]', 'Table (based on known results w/o ...)'.
# The parser does not report these lines as 'not read'.
_NOT_A_TEAM = re.compile(r"^(?:rounds?|tables?|results?|matches)\b", re.IGNORECASE)

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
# An award that the note revokes (decision 25). Two forms:
# - the award and the word together: 'award of 3-0 revoked', 'award revoked';
# - the word at the start of a part of the note, after ';', ',', '-' or
#   'but': '[awarded 3-0; ...; decision revoked on appeal]', '[awarded 2-0;
#   later annulled]', '[awarded 2-0 - annulled]'.
# Not: 'annulled; 0-3 awarded' (the old result is annulled), 'a penalty
# award to Karonga was revoked', 'that decision was revoked', and a word
# that is not certain: 'to be annulled?', 'award revoked?'.
_AWARD_REVOKED = re.compile(
    r"\baward(?:ed)?(?: of \d+-\d+)? (?:was )?(?:revoked|annulled)\b(?!\?)"
    r"|(?:[;,\-–]|\bbut) *(?:later |then )?(?:decision )?(?:revoked|annulled)\b(?!\?)",
    re.IGNORECASE,
)
_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Competition:
    """One competition of a season page: its name and the text of its block.

    is_title: True for the first part of a structure B page, which has the
    title of the page as its name ('Nigeria 2003'). This part is the league.
    """

    name: str
    text: str
    is_title: bool = False


@dataclass(frozen=True)
class ResultRow:
    """
    One result line, before it becomes a SourceMatch.

    result: the result text of the line: '2-1', 'awd', 'abd', 'w/o', 'unk',
            'bt' (the home team won, no score), 'lt' (the home team lost)
            or 'drw' (a draw, no score).
    note:   the note of the line, or None. A note in [ ] that continues on
            the next lines has all its parts here, with one space between
            them (decision 25).
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
    # Lines of a two-leg tie ('A  1-0 3-2  B'). The order of the second leg
    # is not certain from the line, thus the parser does not read them.
    two_leg_lines: int = 0


# ---------------------------------------------------------------------------
# Steps 1 and 2: the competitions, and the top league
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ResultParts:
    home: str
    result: str
    away: str
    rest: str


def _result_parts(line: str) -> Optional[_ResultParts]:
    """Give the parts of a result line, or None (decision 25).

    Two forms: 'Home  2-1 Away  [note]' and 'Home - Away  2-1'. A line is
    not a result line if:
    - it is a table row, or a row of a results grid (3 or more scores, or
      the diagonal mark 'xxx');
    - the away team starts with a second score: a line of a two-leg tie
      ('Etoile du Congo  11-0 5-0 Racing Club Oualembo');
    - a team has ':' (a label) or has no letter;
    - a team starts in lower case and only one space is before the score:
      a part of a sentence ('abandoned at 1-0 in 72'). Some pages have
      team names in lower case, with a wide gap ('kotoko      2-0 Hearts');
    - the score is in a note: '[' is open in the home team, or ']' closes
      in the away team ('[award of 3-0 revoked]').
    """
    if _TABLE_ROW.match(line) or _is_grid_row(line):
        return None
    match = _RESULT_LINE.match(line) or _TEAMS_FIRST.match(line)
    if match is None:
        return None
    home, away = match["home"].strip(), match["away"].strip()
    if _SCORES.match(away) or ":" in home:
        return None
    one_space = line[match.end("home") : match.start("result")] == " "
    for team in (home, away):
        if _LETTER.search(team) is None or (one_space and team[:1].islower()):
            return None
    if home.count("[") > home.count("]") or away.count("]") > away.count("["):
        return None
    return _ResultParts(
        home, match["result"].lower(), away, (match["rest"] or "").strip()
    )


def _is_grid_row(line: str) -> bool:
    """True for a row of a results grid: 3 or more scores, or 'xxx'.

    The parser does not count the scores in a note: 'Fovu  1-1 Canon
    [awarded 3-0; originally 1-1]' is a result line.
    """
    text = line.split("[", 1)[0]
    return len(_SCORES.findall(text)) >= 3 or re.search(r"\bxxx\b", text) is not None


def _is_two_leg(line: str) -> bool:
    """True for a line of a two-leg tie: a team, two scores, a team."""
    return (
        re.search(rf"\S[ \t]+(?:{_SCORE})[ \t]+(?:{_SCORE})[ \t]+[^\W\d_]", line)
        is not None
    )


def _is_result(line: str) -> bool:
    """True for a result line.

    A table row (' 1.Enyimba  38 21 9 8 63-22 72') has a score-like text
    too, but it is not a result line. A line with a label and ':' before
    the teams ('Cup Final: Al Mokaoulun 2-0 Al Mehalla') is not a result
    line of the league: a team name never has ':'. A team name has a
    letter: in 'Zamalek  0-0 2-2' (the two results of one team against
    Zamalek), '2-2' is not a team.
    """
    return _result_parts(line) is not None


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
            is_title = not competitions and name == first_name
            competitions.append(Competition(name, "\n".join(current), is_title))
        name, current = new_name, []
        has_results = final_table = in_table = False

    for i, raw_line in enumerate(lines):
        line = _clean_line(raw_line)
        next_line = _clean_line(lines[i + 1]) if i + 1 < len(lines) else ""
        if _UNDERLINE.match(line):
            continue
        # A numbered round with a line of '=' under it ('Round 1') is a
        # part of the league, not a new competition (decision 25).
        if (
            line.strip()
            and _UNDERLINE.match(next_line)
            and not _is_numbered_round(line)
        ):
            close(_clean(line))
            continue
        if (
            _COMPETITION_HEADING.match(line)
            and not _is_result(line)
            and not _is_note(line)
            # A row of a table of participants ('Liga Muçulmana    Maputo
            # Cidade de Maputo') has gaps of two or more spaces.
            and not re.search(r"\S {2,}\S|\t", line.strip())
            # A line with a score is a result, also without a space
            # ('Estrela Vermelha2-0 Liga Muçulmana').
            and not re.search(r"\d-\d", line)
        ):
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


def _is_numbered_round(line: str) -> bool:
    """True for a round heading with a number ('Round 12')."""
    round_match = _ROUND.match(line)
    return round_match is not None and round_match["number"] is not None


def _continues_league(line: str) -> bool:
    """True for a numbered round, a date or a result line."""
    return (
        _is_numbered_round(line)
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


@dataclass(frozen=True)
class LeagueChoice:
    """
    The competition of a page that choose_league() took as the league.

    competition:  the chosen competition, or None.
    reason:       why: 'leagues.yaml', 'national name', 'first league',
                  'tables only' or 'fallback'.
    alternatives: the names of the other competitions with results or a
                  table. The log shows them, thus a wrong choice is
                  visible.
    """

    competition: Optional[Competition]
    reason: str
    alternatives: tuple[str, ...] = ()


def competition_kind(name: str) -> str:
    """Give the kind of a competition name: 'unnamed', 'note', 'cup',
    'lower', 'playoff' or 'league'.

    'unnamed' is a part of a page without a heading, for example the text
    after a final table. It is something other than the league.

    'note' is a sentence that a page has at the place of a heading, for
    example 'Winners qualify for CAF Cup.'. 'league' is all other names: a
    league name, or a page title such as 'Egypt 2004/05'.
    """
    if not name.strip():
        return "unnamed"
    if _is_note(name):
        return "note"
    if _CUP.search(name):
        return "cup"
    if _LOWER.search(name):
        return "lower"
    if _PLAYOFF.search(name):
        return "playoff"
    return "league"


def choose_league(
    competitions: list[Competition], league_pattern: str = ""
) -> LeagueChoice:
    """Choose the national league among the competitions of a page.

    The steps (decision 24):
    1. leagues.yaml (league_pattern): the first competition whose name
       matches it, and that has results or a final table. If no name
       matches, the page has no league: the rules do not guess.
    2. The candidates: competitions with results or a final table whose
       kind is 'league' (not a cup, a lower level, a play-off or a note).
       If the first candidate and 3 or more others have only a place name
       ('Boa Vista', 'Brava', 'Fogo', ...), the page has regional leagues
       only: no league.
    3. If the first candidate has no league word (for example 'Boa Vista',
       an island league of Cape Verde) and a later candidate has a national
       name ('Campeonato Nacional'), the later candidate. An abbreviation
       that ends with L ('NPFL 2023/24') is a league word: else the NPFL
       page gives 'Nigeria National League', the second level. The title
       part of a structure B page ('Nigeria 2003') is the league: this step
       does not apply to it.
    4. Else the first candidate with results; else the first candidate (a
       page with tables only).
    5. Else the first competition with results that is not a cup, as a
       fallback. The reason gives its kind, for example 'fallback (lower)'.
    """
    with_data = [c for c in competitions if _has_results(c) or _has_table(c)]
    names = tuple(c.name for c in with_data)

    def choice(competition: Competition, reason: str) -> LeagueChoice:
        others = tuple(n for n in names if n != competition.name)
        return LeagueChoice(competition, reason, others)

    if league_pattern:
        for competition in with_data:
            if re.search(league_pattern, competition.name, re.IGNORECASE):
                return choice(competition, "leagues.yaml")
        # leagues.yaml names the league, and the page does not have it.
        return LeagueChoice(None, "leagues.yaml: no match", names)

    candidates = [c for c in with_data if competition_kind(c.name) == "league"]
    if candidates:
        first = candidates[0]
        # Many candidates with only a place name ('Boa Vista', 'Brava',
        # 'Fogo', ...): the page has the regional leagues of a season, and
        # not the national league.
        place_names = [
            c
            for c in candidates
            if not c.is_title
            and not _has_league_word(c.name)
            and not _STAGE_WORD.search(c.name)
            and not _NATIONAL.search(c.name)
            # A season of a page with many seasons ('1938/39') is not a
            # place.
            and not re.search(r"\b(?:18|19|20)\d{2}\b", c.name)
        ]
        if first in place_names and len(place_names) >= 4:
            return LeagueChoice(None, "regional leagues only", names)
        if not first.is_title and not _has_league_word(first.name):
            for competition in candidates[1:]:
                national = _NATIONAL.search(competition.name) and _LEAGUE_WORD.search(
                    competition.name
                )
                # A stage of the league ('First Stage') stays the choice
                # unless the national competition has more results.
                if national and (
                    not _STAGE_WORD.search(first.name)
                    or _result_count(competition) > _result_count(first)
                ):
                    return choice(competition, "national name")
        for competition in candidates:
            if _has_results(competition):
                return choice(competition, "first league")
        return choice(first, "tables only")

    # No competition of the kind 'league'. A cup is never the league. A
    # lower level, a play-off or a part without a name can be the only
    # league data of the page (for example the provincial championships of
    # Angola before 1979); the reason shows it.
    for competition in with_data:
        kind = competition_kind(competition.name)
        if kind != "cup" and _has_results(competition):
            return choice(competition, f"fallback ({kind})")
    return LeagueChoice(None, "none", names)


def top_league(page: str, league_pattern: str = "") -> Optional[Competition]:
    """Give the competition of the page that is the national league, or
    None if the page has no competition with results."""
    choice = choose_league(split_competitions(page), league_pattern)
    if choice.competition is None or not _has_results(choice.competition):
        return None
    return choice.competition


def _has_results(competition: Competition) -> bool:
    return any(_is_result(_clean_line(line)) for line in competition.text.splitlines())


def _has_table(competition: Competition) -> bool:
    """True for a final-table heading, or for 3 or more table rows. Some
    pages give the table of a league without a heading, directly under the
    name of the competition ('NSL League - Final Table 1986')."""
    lines = [_clean_line(line) for line in competition.text.splitlines()]
    if any(re.match(r"^\s*Final Tables?\b", line, re.IGNORECASE) for line in lines):
        return True
    rows = sum(bool(re.match(r"^\s*\d+\.\s*\S.*\s\d", line)) for line in lines)
    return rows >= 3


def _vocabulary_pattern() -> re.Pattern[str]:
    """The words of competition names, in all forms: a name in lower case
    ('Championnat national de première division') is not a sentence."""
    parts = [r.pattern for r in (_CUP, _LOWER, _PLAYOFF, _LEAGUE_WORD, _NATIONAL)]
    return re.compile("|".join(f"(?:{p})" for p in parts), re.IGNORECASE)


def _result_count(competition: Competition) -> int:
    return sum(_is_result(_clean_line(line)) for line in competition.text.splitlines())


def _has_league_word(name: str) -> bool:
    return bool(_LEAGUE_WORD.search(name) or _LEAGUE_ABBREVIATION.search(name))


def _is_note(name: str) -> bool:
    """True for a sentence, not a name.

    A sentence ends with '.', or is long, or has more than 5 words and words
    such as 'the', 'were', or has 3 or more words in lower case that are not
    connectors ('Santo Antão (South Zone) no provincial championship held').
    """
    # A note in brackets is a part of a name: 'Championnat National de 1ère
    # Division [aka Primus Ligue]'.
    name = re.sub(r"\[[^\]]*\]?|\([^)]*\)?", "", name).strip()
    words = name.split()
    lower = [
        w
        for w in words
        if w[:1].islower()
        and w.strip("(),'").lower() not in _CONNECTORS
        and not _VOCABULARY.search(w)
    ]
    return (
        name.rstrip().endswith(".")
        or len(words) > 9
        or (len(words) > 5 and _NOTE_WORDS.search(name) is not None)
        or len(lower) >= 3
    )


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
    # The index in result.rows of the row whose note is open, or None (an
    # open list of scorers, or no open note).
    note_row: Optional[int] = None

    def continue_note(text: str) -> None:
        """Add the next part of an open note to the note of its row."""
        nonlocal open_note, note_row
        part = text.split("]", 1)[0].strip()
        if note_row is not None and part:
            row = result.rows[note_row]
            note = f"{row.note} {part}" if row.note else part
            result.rows[note_row] = replace(row, note=note)
        if "]" in text:
            open_note = False
            note_row = None

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
            note_row = None
            continue

        line = _clean_line(raw_line)
        if not line.strip():
            continue

        # A line that starts with a space or a tab is a list of scorers, a
        # note, or the next part of a note. It is never a result line.
        if line[0] in (" ", "\t"):
            if "[" in line:
                open_note = "]" not in line[line.rindex("[") :]
                note_row = None
            elif open_note:
                continue_note(line)
            continue
        if _TABLE_ROW.match(line) or line.startswith(("NB", "-", "(")):
            continue

        date_match = _DATE_LINE.match(line)
        if date_match is None and line.startswith("["):
            # A note at the start of a line, for example
            # '[*14] w/o goals rd 14 (Liberty bt Goldfields by 1)'.
            open_note = "]" not in line
            note_row = None
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

        row = _result_parts(line)
        if row is None and open_note and note_row is not None and date_match:
            # The next part of the note of a row, in a column after a date:
            # '[Aug 15]                    abandoned at 1-0 in 72''. Only
            # after a date: if a page does not close a note, the other
            # lines must not disappear into the note.
            continue_note(line)
            continue
        if row is None:
            # A grid row first: a grid row also has two scores and a team.
            if _is_grid_row(line):
                result.grid_lines += 1
            elif _is_two_leg(line):
                result.two_leg_lines += 1
            elif len(_SCORES.findall(line)) >= 2:
                result.grid_lines += 1
            # A heading with numbers ('Rounds 6-9 missing') is not a result.
            elif _LOOKS_LIKE_RESULT.search(line) and not _NOT_A_TEAM.match(
                line.strip()
            ):
                result.unparsed.append(line.strip())
            elif "]" in line:
                open_note = False
            continue

        rest = row.rest
        note: Optional[str] = None
        if open_note:
            # The rest is the next part of an open note, in a column at the
            # right of this result line.
            continue_note(rest)
        elif rest.startswith("["):
            note = rest[1:].split("]", 1)[0].strip()
            open_note = "]" not in rest
            note_row = len(result.rows) if open_note else None
        result.rows.append(
            ResultRow(
                stage=stage,
                round_name=round_name,
                round_number=round_number,
                match_date=current_date,
                home=row.home,
                away=row.away,
                result=row.result,
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
    if re.fullmatch(r"\d{1,2}-\d{1,2}\*?", row.result):
        status = MatchStatus.PLAYED
        home_goals, away_goals = (int(x) for x in row.result.rstrip("*").split("-"))
        penalties = _PENALTIES.search(note)
        # A note can name a penalty in a match without a shootout, for
        # example '1-0 [Masry scored a pen]'. A shootout needs a draw.
        if penalties is not None and home_goals == away_goals:
            pen_home, pen_away = int(penalties["home"]), int(penalties["away"])
    elif row.result == "awd" and _AWARD_REVOKED.search(note):
        # '[awarded 2-0; later annulled]': the award does not count.
        status = MatchStatus.CANCELLED
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
    elif row.result == "ann":
        # Annulled: the match does not count (it is replayed later).
        status = MatchStatus.CANCELLED
    elif row.result == "n/p":
        # Not played. 'n/p  [awarded 2-0]' is an awarded match.
        awarded = _AWARDED.search(note)
        if awarded is not None and not _AWARD_REVOKED.search(note):
            status = MatchStatus.AWARDED
            home_goals = int(awarded["h1"] or awarded["h2"])
            away_goals = int(awarded["a1"] or awarded["a2"])
        else:
            status = MatchStatus.CANCELLED
    elif row.result == "ppd":
        status = MatchStatus.POSTPONED
    else:
        # unk, bt, lt, drw, tie, ---, '3-?', '?-?': the source does not
        # give a score.
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
    league_pattern: str = "",
) -> tuple[list[SourceMatch], list[str]]:
    """Give the matches of the top league of a page, and the problems.

    anchor: for a page with many seasons, the anchor of the season (from the
    season URL, for example '72' in nig72.html#72). The parser reads only
    the part of the page for that season.

    league_pattern: the rsssf_league of leagues.yaml, or ''. See
    choose_league().

    The problems are the lines that look like a result but were not read,
    and the rows that are not a valid SourceMatch.
    """
    if anchor:
        part = season_part(page, anchor)
        if part is None:
            return [], [f"no season part for the anchor #{anchor}"]
        page = part
    competition = top_league(page, league_pattern)
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
    if parsed.two_leg_lines:
        problems.append(f"{parsed.two_leg_lines} lines of two-leg ties not read")
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
    """Remove the HTML tags of a line, and keep its spaces and tabs.

    A score with an en dash or an em dash ('1–1') gets a hyphen ('1-1'). A
    score with a mark and no space after it ('3-0*CRE Constantine') gets a
    space after the mark (decision 25).
    """
    text = html.unescape(_TAG.sub("", line)).rstrip()
    text = re.sub(r"(?<=\d)[–—−](?=\d)", "-", text)
    return re.sub(r"(\d-\d{1,2}\*)(?=\S)", r"\1 ", text)


_VOCABULARY = _vocabulary_pattern()
