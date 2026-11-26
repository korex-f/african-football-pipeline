# 26. Final tables on RSSSF pages of all African countries: more heading words, and complete plain tables

*Status: accepted (November 2026). Changes the rule "which tables" of [decision 23](0023-final-tables-and-the-table-check.md). [All decisions](README.md)*

- **What:** The table reader (`sources/rsssf/tables.py`) accepts more headings of a final table, and the group words of French and Portuguese pages. A plain table (`Table:`) is also the final table of its stage, if its own numbers show a complete double round-robin.
- **Why:** The survey of 56 African countries found 500 seasons with a table of 4 or more rows that the reader did not read. Decision 24 corrected the largest cause (a cup chosen as the league). The other causes are the headings: `Reported Final Table:` (a word before `Final`), `Final Ranking:`, `Poule A` in place of `Group A`, and pages that give the final table under a plain `Table:`.
- **How the project did it:** The same method as decisions 24 and 25. A script compared each survey season with the reader of `main`: the table rows, the stages, the problems, and the table check. A second script put each table block of the seasons without a table in a group by its heading, and tested if the table was complete.

## The debate

The question was decision 23's rule: "only `Final Table:` is final; `Table:` is a table in the middle of a season".

1. **Keep the rule.** Safe, but a page that gives its final table under `Table:` has no table. Ghana 1999 is one: its `Table:` has 30 matches for each of 16 teams, and it agrees with all 240 matches.
2. **Accept every `Table:`.** The survey showed that this is wrong: of 123 last `Table:` blocks that the reader can read, only 21 show a complete season. The others are tables of a season in progress (the pages of 2026/27) or of a season that stopped.
3. **Accept a plain table if its numbers show that it is complete (the decision).** A complete double round-robin of n teams has 2(n − 1) matches for each team. The first test also accepted n − 1 (a single round-robin). The survey showed 31 interim tables (`Halfway Table:`, `Table at mid-season:`) that passed it: after the first half of a double round-robin, each team has n − 1 matches. With 2(n − 1) only, 0 interim tables pass.

The project chose option 3 with 2(n − 1) only. A single round-robin league with only a plain `Table:` stays without a table.

## The headings

| Heading | Final table? |
|---|---|
| `Final Table:`, `Final Tables:` | yes (decision 23) |
| Up to 3 words before it: `Reported Final Table:`, `Super Division Final Table:` | yes |
| A note in brackets: `Final(?) Table:`, `Final (official) Table:` | yes |
| `Final Ranking:`, `Final Standings:`, `Official Table from FECAFOOT:` | yes |
| `Top of Final Table:`, `Top Final Table:` | no: only the top rows |
| `Final table missing.`, `The final table was not published` | no: a heading ends with `:`, or has only a note in brackets after its words |
| `Table:`, `Tables:`, `Reported Table:`, `Table (Jan 30):`, `Table [from Nando 7/7/00]:` | a **plain** table: see below |
| A group heading outside a final block: `Zone A`, `Poule B` | a plain table of the group |
| `Table (based on known results):` | no: the author made it from the results, thus it agrees with them by construction. It is not an independent check |
| `Halfway Table:`, `Table at abandonment:`, `Table before last round:` | no (decision 23) |

Group headings in a final block: `Group`, `Zone`, `Pool`, `Conference` (decision 23), and now `Poule`, `Groupe` and `Grupo`, with an optional `:` or a note in brackets (`Group A (Algiers):`).

## Plain tables

For each stage, the last plain table is a candidate. At the end of the competition, the candidate is the final table of its stage only if:

1. the stage has no final table with a `Final` heading;
2. the reader read all its rows (else the number of teams is not certain);
3. it has 3 or more teams (2 teams are a two-leg tie, not a league);
4. its positions go from 1 to n;
5. each team played 2(n − 1) matches.

Rule 4 came from the comparison. In Benin 2017, a play-off note gives the rows 2, 3 and 6 of a group "for the sake of completeness". The 3 teams played 4 matches each, thus 2(n − 1) for n = 3, by chance.

## Result

All survey seasons, compared with `main` (with decision 25):

| | `main` | This change |
|---|---|---|
| Table rows | 19,622 | 21,079 |
| Seasons with a table | 1,373 | 1,449 |
| Table checks | 1,500 | 1,583 |
| Table checks that agree | 870 | 896 |
| Table problems | 1,042 | 1,243 |

- No season has fewer table rows.
- The 201 new problems are rows of the newly found final tables that have another row form (for example points only: `1.Atlético Sport Aviação  17 pts`). They are visible, as decision 23 requires.
- Nigeria, Ghana and Egypt: 2,305 → 2,481 table rows, 145 → 156 seasons with a table, 57 → 59 checks that agree. Ghana 1999 and Ghana 2003 now agree with all 240 matches.
- One check that agreed does not agree now: Namibia 1993. The page's top league (`Premier League`) has only a table, thus decision 24 chooses `Etosha National League`, a regional second level with 3 play-off results. `main` compared a 3-row play-off table with these 3 matches. Now the reader also finds Etosha's `Reported Final Table` (90 matches), and the check shows the difference. The cause is the league choice, not the table reader.
- Many new group tables do not agree with the matches: when only some groups are complete, the check (decision 23) compares them with the matches of all groups. The difference is visible; it is not a false agreement.

## Trade-offs

- A single round-robin league with only a plain `Table:` has no table.
- A complete table of a season with a withdrawal (one team with fewer matches) does not pass rule 5. A `Final` heading is necessary for such a table.
- Rule 5 uses the table's own numbers. A table with a typo in `played` does not pass.
- The row forms are not changed. About 1,000 rows in 108 seasons have another form (points only, goals in two columns without `-`). They are the next fix.
