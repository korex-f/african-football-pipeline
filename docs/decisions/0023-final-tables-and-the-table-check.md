# 23. Final tables are stored, and a table check compares them with the matches

*Status: accepted (November 2026). [All decisions](README.md)*

- **What:** `sources/rsssf/tables.py` reads the final tables of the top league from RSSSF season pages. Each row is a `SourceTableRow` (`models/source_table.py`). The loader writes the rows to the new table `source_tables` (migration `002_source_tables.sql`). `table_check()` compares a table with the matches of its stage.
- **Why:** [Decision 7](0007-testable-definition-of-verified.md) gives two conditions for a verified season. The second is "an independent source agrees, **or** the total goals agree with a final table". A final table is a second record of the season, made by its author from the full results. If the matches that the pipeline has agree with it, the season is very probably complete and correctly read.

## The debate

1. **Compare by team, or compare by sums.**
   - *By team* (each team's played, goals for and goals against): a difference shows the team. But the names in a table (`Enyimba FC (Aba)`) are often not the names in the results (`Enyimba`), thus the comparison needs the team normaliser first.
   - *By sums (the decision):* the sum of `played` ÷ 2 is the number of matches, and the sum of `goals for` is the number of goals. No names are necessary. A difference shows that something is wrong, but not which team. The comparison by team can come in roadmap step 5, after the normaliser.
2. **A second run of a season: replace the table, or update each row.**
   - *Update each row* (as for the matches, [decision 18](0018-loader-records-each-run.md)): a row that the new page does not have stays. But a table is one unit: a row of an old table and a row of a new table together are not a table.
   - *Replace the table (the decision):* a run with table rows deletes the stored table of the season and the source, and writes the new rows, in the `load()` transaction. A run **without** table rows does not change the stored table: a run that did not find the table (a parser problem, a page change) must not remove it.
3. **Which tables.** Only final tables: `Final Table:` and `Final Tables:` (groups). Not `Table:` (in the middle of a season), `Table before last round:` or `Table at abandonment:`.

## Rules that the pages required

The project read the tables of all 187 pages of the NPFL, Ghana and Egypt, and compared each with the matches.

| Rule | Example | What went wrong without it |
|---|---|---|
| A page can have the final table two times | `gha2024.html`: before and after the results | Each table was two times too large (760 matches for 380) |
| The first table of a stage is used; a different second table is a problem | `nig01.html` | — |
| A page without results has its table in the first competition | `egy95.html` | Seasons with only a table had no table rows |
| A part of a page with no heading and no results is one table | `ghahist.html#64` | The same |
| `drawn` can be two numbers: a score draw and a goalless draw | `13  7/ 5  5` (Nigeria 1991, 1992) | 32 rows were not read |
| A numbered list of teams is not a table | `1.Stationery Stores FC, Lagos;` | 16 false problems |
| A team name can start with a digit | `9.3SC Shooting Stars` | A team was skipped without a problem, in 5 seasons |
| Goals can have a space after the dash | `34- 9` | — (read from the start) |

## What the table check found

| Result | Seasons | Meaning |
|---|---|---|
| Matches and goals agree | 53 of 86 tables | Strong evidence that the season is complete and correctly read. Example: Ghana 2023/24, 306 matches and 628 goals — and Soccerway agrees too |
| The page has the table but few results | for example Ghana 1969 (2 of 132) | The season is incomplete on RSSSF |
| The matches agree, the goals do not | NPFL 2023/24: 845 and 851 | A deduction of goals ("Gombe United 3 points and 3 goals deducted") |
| More matches than the table | NPFL 2005: 388 and 380 | Replays, or annulled matches, are in the results |
| A table row is not valid | Ghana 2008/09: 10 + 10 + 13 is not 30 | A typo on the page. The row is a problem, thus the table has one row less |
| Play-off tables | Egypt 2024/25 | Their `played` includes the matches before the play-off |

Thus the check is a diagnostic. It is not a rule that gives a status. Roadmap step 5 decides how `season_coverage` uses it.

## Trade-offs

- The table is a record of the same author as the results. It is not a fully independent source. But the author made it from the official results at the time, not from the list of results on the page.
- The check does not show which team is wrong.
- Rows in other forms (only the points and the goal difference) are not read. They are problems.
- Only RSSSF gives tables now. `RsssfAdapter.parse_tables` is not in the `SourceAdapter` Protocol, because the Soccerway results pages have no tables.
