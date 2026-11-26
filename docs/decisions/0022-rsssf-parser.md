# 22. The RSSSF parser: the first competition with results, line rules, and visible problems

*Status: accepted (November 2026). The rule for the top league ("the first competition with results") is replaced by [decision 24](0024-choosing-the-national-league-on-a-page.md). [Decision 25](0025-result-line-forms.md) adds result forms and keeps the full text of a note in a column. [Decision 29](0029-dates.md) replaces the rule for the year of a date. [All decisions](README.md)*

- **What:** `sources/rsssf/parser.py` reads the matches of the top league from an RSSSF season page. `RsssfAdapter.parse` uses it. The lines that the parser cannot read are in `RsssfAdapter.problems` and in the log.
- **Why:** RSSSF pages are hand-written by many authors over 30 years. A parser for such pages makes mistakes. The design question is how to find the mistakes.
- **How the project built it:** The parser was developed on all 187 season pages of the NPFL, Ghana and Egypt (`data/sources/rsssf/`, 2.0 MB), not on samples only. After each change, a report gave the matches, the teams, the dates and the problems for each season. Each new problem in the report showed a new form of the pages.

## The two structures

| Structure | Pages | How the parser finds the competitions |
|---|---|---|
| **A** (newer) | for example `nig2015.html`, `gha2024.html` | each competition has `<h4>` and its own `<pre>` block. In the block, `<b>` lines are stages and `<u>` lines are groups |
| **B** (older) | for example `nig05.html`, `egy05.html` | one `<pre>` block. A new competition starts at (1) a heading with `===` under it, (2) a heading with a competition word (`League`, `Division`, `Cup`, ...) and without `:`, or (3) the first line after a **final** table, if the results came before it, and if the line is not a round, a date or a result |

The top league is the **first competition that has result lines**. In all pages that the project examined, the league is before the cup and the lower divisions.

## The debate

1. **One general parser, or one parser for each country or era.**
   - *One parser for each format:* each is simple. But nobody knows how many formats there are, and a page can change its format when a new author updates it.
   - *One parser with line rules (the decision):* each rule reads one form of line (a round, a date, a result, a note). A new form of page needs a new rule, not a new parser. The 187 pages need 4 kinds of headings, 7 result words and 3 forms of notes.
2. **What to do with a line that the parser cannot read.**
   - *Ignore it:* the output looks complete, but data is missing, and nobody knows it.
   - *Stop with an error:* one bad line stops the whole season.
   - *Read what is possible, and report each line that looks like a result but was not read (the decision).* A row that is not a valid `SourceMatch` is also a problem, not an error. A page with only a results grid gives a problem, thus it does not look the same as a page without results.
3. **Results grids and crosstables.** Some pages give the results as a matrix (Ghana 2012/13) or as the results of one team (Egypt 1950s). To read a matrix, the parser must know the sequence of its columns. The project did not do this now. The parser counts these lines and gives one problem for each page.

## Rules that the pages required

| Rule | Example | What went wrong without it |
|---|---|---|
| A note can continue in a column at the right of the next result lines | `[Gombe United 3 points and 3 goals` / `Enyimba  2-0 Sporting Lagos   deducted due to ...` | 3 to 6 matches of a season were lost, and not reported |
| A table row is not a result line | `10.Kotoko 2 0 0 2 1-3 0 Relegated` | The table was the "league", with 0 matches |
| A team name has a letter, and no `:` | `Zamalek  0-0 2-2`; `Cup Final: Al Mokaoulun 2-0 Al Mehalla` | `2-2` was a team; a cup final was a league match |
| Only a `Final Table` can end the league | `Table:` after round 10 | NPFL 2001 had 80 matches, not 242 |
| A date of two days gives the first day | `[Mar 24,25]`, `[Feb 28/Mar 1?]` | The matches got the date of the round before |
| A round without a date has no date | `Round 21` | The same as above |
| A month before the first month of the season is in the second year | `[Sep 15]` ... `[Jan 2]` | (tested: all 306 Ghana 2023/24 dates agree with Soccerway) |
| Penalties only after a draw | `1-0 [Masry scored from a pen]` | The match failed the `SourceMatch` checks and was lost |
| A season of a page with many seasons starts at its anchor | `nig72.html#77`, `ghahist.html#64` | All 8 seasons of 1972 to 1979 had the same 5 matches |

## Result words

| Word | Status | Score |
|---|---|---|
| `2-1` | `PLAYED` | the score; penalties from a note such as `[4-5 pen]` for a draw |
| `awd` | `AWARDED` | from the note: `[awarded 3-0 ...]` or `[0-3 awarded ...]` |
| `w/o` | `AWARDED` | none |
| `abd` | `ABANDONED` | none (the score at the time of the stop is not a result) |
| `unk`, `bt` (beat), `lt` (lost to), `drw` (draw) | `UNKNOWN` | none: the source does not give one |

## Verification

- **All 187 pages:** 21,334 matches. 0 dates outside the years of their season. 20 reported problems: unknown opponents (`bt [N.N.]`) and results grids. 63 seasons give no matches: their pages have a table only, a results grid (reported as a problem), or no results.
- **Two sources, one season.** Ghana 2023/24: all 306 Soccerway matches are in the RSSSF output with the same date and score. RSSSF has one more: an abandoned match before its replay. Ghana 2017: 238 of 240 agree. The 2 others are differences between the sources (a date, and an awarded result).
- **Fixtures:** 14 unchanged season pages, one for each form above.
- **Deliberate breaks:** 10. Three were not found by the page tests at first, because other rules also protected against the same bug (*layered defences*). Each of them got a test that only that rule can pass.

## Trade-offs

- The first competition with results is the league. A page that puts the cup first gives the cup. The coverage check (n × (n − 1)) and the comparison with Soccerway can show such a season.
- Team names are raw. One page can write one club in 4 ways (`BA United`, `B.A. United`, `BA Untd`, `Brong-Ahofu United`). The team normaliser must give them one name.
- The results grids and crosstables are not read. The problems show which seasons have them.
- A note that continues in a column is skipped. Its text after the first line is not in `ResultRow.note`.
- The parser uses regular expressions on lines. A rule can match a line that it should not match. The corpus report and the fixtures show such mistakes, but only for the pages that the project has.
