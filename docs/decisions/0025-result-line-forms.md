# 25. Result lines on RSSSF pages of all African countries: more forms, more guards, and full notes

*Status: accepted (November 2026). Adds to the result words of [decision 22](0022-rsssf-parser.md), and changes its trade-off "a note that continues in a column is skipped". [All decisions](README.md)*

- **What:** The RSSSF parser (`sources/rsssf/parser.py`) reads more forms of result lines. New guards stop lines that are not results. A note that continues on the next lines is now complete. An award that the note revokes does not count.
- **Why:** The survey of 56 African countries (decision 24) showed result lines that the parser of decision 22 did not read, for example scores with an en dash (`1–1`). It also showed lines that the parser read as matches but that are not matches: rows of a results grid, two-leg ties, and parts of sentences and notes. Both errors were silent.
- **How the project did it:** The same method as decision 24. A script compared each of 2,448 seasons with the parser of `main`: the chosen league, the matches by status, the lines not read, and the table check (decision 23). Each change was kept only after a check of the lines that it added or removed.

## The debate

1. **Two-leg lines** (`ex-Benfica Nampula  2-0  1-5 AD Pemba  [agg 3-5]`). Read two matches, or report the line. The line does not show the home team of the second leg, and some pages write the second score from the view of the first team. The decision: report the line (`5 lines of two-leg ties not read`). A wrong home team is worse than a visible gap.
2. **`n/p` with an award** (`n/p  [awarded 3-0, Hearts of Oak dns; ...`). Option 1: `n/p` is always CANCELLED. Option 2: an award in the note gives AWARDED, but not if the note revokes the award. Option 2 needs the full note, because the revocation is often on the next line. The comparison: option 1 gave 863 table checks that agree, option 2 gave 870, and option 1 made 2 seasons worse (Seychelles 2011, Uganda 2007). The decision: option 2.
3. **Team names in lower case.** A guard for parts of sentences (`abandoned at 1-0 in 72'`) first refused all teams that start in lower case. The comparison showed real teams in lower case (`kotoko`, `cmbelcourt`, `ex-Sporting Beira`). The decision: refuse a lower-case team only if one space comes before the score. Real lines have a column gap.
4. **`bye`, `vs` and `draw`** stay unread. On the survey pages, these words are in sentences or in fixtures without a result.

## New forms

| Form | Example | Status |
|---|---|---|
| A score with an en dash or an em dash | `MC Oran  2–1 ES Ben Aknoun` | PLAYED (the dash becomes `-`) |
| A score with a mark | `Jijel SD  3-0*CRE Constantine` | PLAYED (`*` usually means after extra time) |
| A score that is not known | `Wikki  3-? Pillars`, `?-?` | UNKNOWN |
| Teams first, then the score | `COD Meknes  - SA Sale  5-2`, `FC HellBourg. - US Ste Anne : 6-1` | PLAYED |
| `tie`, `---` | `Bo Rangers  --- Old Edwardians` | UNKNOWN |
| `ppd` | `Gombe  ppd Enyimba` | POSTPONED |
| `ann` | `Gabros  ann El Kanemi  [annulled; finished 1-0]` | CANCELLED |
| `n/p` | `Saint-Pierroise  n/p Parfin` | CANCELLED |
| `n/p` with an award | `Ranchers Bees  n/p Pillars  [0-3 awarded; Ranchers Bees dns]` | AWARDED, 0-3 |
| A result word in upper case | `Express  Ppd UEB`, `EEF Afoma  W/o FC Imango` | as in lower case |

A fixture without a score (`MC Alger  -  Paradou AC`) is not a result.

A numbered round with a line of `=` under it (`Round 1` / `=======`) is a part of the league, not a new competition. Before, Morocco 1995/96 had 30 competitions with the names `Round 1` to `Round 30`.

## New guards

| A line is not a result if | Example from the survey |
|---|---|
| it has 3 or more scores, or `xxx`, before its note: a row of a results grid | `Mbabane Sw 1-0 0-1 2-2 2-0 1-1 awd xxx 2-1 ...` |
| the away team starts with a second score: a two-leg tie | `Etoile du Congo  11-0 5-0 Racing Club Oualembo` |
| a team starts in lower case, and one space comes before the score | `losing 1-2 to SO Armée in Yamoussoukro` |
| the score is in a note: `[` is open in the home team, or `]` closes in the away team | `13 CS Hammam Lif  26 ... [0 1 1 2-3 1] Relegated` |

Scores in the note do not count for the grid rule: `Fovu  1-1 Canon  [awarded 3-0; originally 1-1, ...]` is a result line.

A heading with numbers (`Rounds 6-9 missing`, `Round 19 [postponed from Mar 2-4 ...]`) is not reported as "not read".

## Full notes

Some notes continue at the right of the next lines. Decision 22 kept only the first part. Now the parser adds each next part to the note of its row:

```text
Orlando Pirates   awd African Stars   [remaining 8'; African Stars dns;
[Jun 17]                              awarded 2-0; later annulled]
```

The note of this row is `remaining 8'; African Stars dns; awarded 2-0; later annulled`. A next part can be at the right of a date, of the next result, or on an indented line. After a date only: if a page does not close a note with `]`, the lines after it must not disappear into the note.

A list of scorers (`  [Tamer Abdel Hamid 47, ...`) is not a part of the note of a row.

## Awards that a note revokes

An `awd` or `n/p` row is CANCELLED, not AWARDED, if its note revokes the award. Two forms:

- the award and the word together: `award of 3-0 revoked`, `award revoked Aug 6`;
- the word at the start of a part of the note, after `;`, `,`, `-` or "but": `; decision revoked on appeal`, `; later annulled`, `- annulled`, `but later annulled`.

The first version of the rule was `award.*(revoked|annulled)`. The list of its 70 matches showed false matches, thus the rule became narrower. These notes do not revoke the award:

| Note | Why |
|---|---|
| `annulled; 0-3 awarded; originally 2-1` | The old result is annulled, and the award replaces it |
| `after a penalty award to Karonga was revoked` | A penalty award, not the award of the match |
| `... but that decision was revoked` | A different decision |
| `to be annulled?`, `award revoked?`, `award may have been revoked` | Not certain |

## Rules that the comparison removed

- **"A team name is not a word of text"** (`Round`, `Table`). The comparison of all seasons with and without this rule showed 0 changes: the lower-case guard and the note guard stop the same lines. Thus the rule was removed from the result check. It stays only to keep headings out of the "not read" report.
- **A separate branch for `3-?`** in `to_source_match()`. A deliberate break showed that the last branch (UNKNOWN) gives the same result.

## Result

All 2,446 survey seasons that the survey downloaded (`main` → this change):

| | `main` | This change |
|---|---|---|
| Matches | 235,078 | 237,900 |
| PLAYED | 230,682 | 231,758 |
| AWARDED | 2,295 | 2,302 |
| UNKNOWN | 1,524 | 2,286 |
| POSTPONED | 0 | 381 |
| CANCELLED | 0 | 595 |
| Table checks that agree (of 1,500) | 837 | 870 |
| Lines reported as "not read" | 45 | 52 |

- 349 seasons have more matches. The largest: Algeria 1972/73 (1 → 248, en dashes), Cameroon 2004 (1 → 145, a heading that was a "result"), Morocco 1995/96 (0 → 240, teams first and underlined rounds), Algeria 2025/26 (120 → 240, en dashes), South Africa 1996/97 (0 → 88, teams first).
- 52 seasons have fewer matches: 138 rows in total. Each row was a wrong read: grid rows, two-leg lines, sentences, and parts of notes.
- 23 seasons have a different league. 16 have no league now: their only "results" were grid rows or two-leg lines. One is not correct: São Tomé 1999 now gives the island league of Príncipe (1 match) and not the national final (1 match). `rsssf_league` in `leagues.yaml` corrects it when the project adds São Tomé.
- The "not read" report has 16 new lines, and 9 lines less. The 9 lines are table rows and headings. 10 of the 16 new lines were matches in `main`, for example `St Pauls win 5-4 on agg and are champions`. The 6 others are sentences that `main` did not report.
- **Nigeria, Ghana and Egypt:** 21,201 → 21,256 matches. Table checks that agree: 53 → 57. Egypt 2004/05 now has its 26 rounds of 7 matches (176 → 182): round 19 has en dashes.

Three seasons have a table check that agreed with `main` and does not agree now: Algeria 2009/10, Ivory Coast 2004 and Niger 2024/25. In each, `main` read a part of a note as a match, for example `[Aug 15]  abandoned at 1-0 in 72'` (home team "abandoned at", away team "in 72'"). The note belongs to a match whose result stood, thus the false match gave the correct sum by chance. The new parser adds this text to the note of its match. The match has no score in its result word (`awd` without a score in the note), thus the sum is now short. This is a known gap, not a regression: the old sum was correct for a wrong reason.

## Trade-offs

- Two-leg lines are not read. The problems show the 5 seasons that have them.
- The revocation rule reads English words. A note in French or Portuguese (`annulé`) is not found. On the survey pages, all such notes are in English.
- The guard for lower case uses the space before the score. A real team in lower case with one space before the score is not read, and it is reported as "not read".
- A note part is joined only after a date, after a result, or on an indented line. A note part on a line of its own without a date is lost, as before.
- An abandoned match whose result stood (`[...; 1-0 scoreline remains]`) has no score. The table check shows these seasons.
