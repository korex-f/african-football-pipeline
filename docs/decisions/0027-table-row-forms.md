# 27. Table rows on RSSSF pages: two more full forms, and short forms stay problems

*Status: accepted (November 2026). Adds to the row form of [decision 23](0023-final-tables-and-the-table-check.md). [All decisions](README.md)*

- **What:** The table reader (`sources/rsssf/tables.py`) reads two more forms of a full table row, and a mark after the points. Short rows (points only, played and points) stay problems.
- **Why:** After decision 26, the survey had 1,180 table rows that the reader reported as "not read". About 280 of them are full rows in another order. The other 900 are short rows without won, drawn, lost or goals.
- **How the project did it:** A script put each row that was not read in a class by its numbers. The same comparison as decisions 24 to 26 then measured the change on all survey seasons.

## The debate

1. **Full forms only (the decision).** The new forms have all the numbers of a `SourceTableRow`. No change to the model or the database.
2. **Full and short forms.** Short rows need empty won, drawn, lost and goals: a model change, a migration, and a table check without goals. Decision 7's table check needs the goals, thus a short table adds little to verification.

The user chose option 1. A later change can add short rows.

## The forms

| Form | Example | Seasons |
|---|---|---|
| The main form (decision 23) | ` 1.Enyimba FC (Aba)  38 21  9  8  63-22  72` | — |
| Goals in two columns, without `-` | ` 1.Cotonsport Garoua  30 19  4  7  41  17  58` | Cameroon, Libya, South Africa, ... |
| The points first | ` 1.JS St Pierroise  65  22  13  4  5  33- 20` | Réunion (4 points for a win) |
| A mark after the points | ` 5.Swazi Rail Hawks  10  2  3  5  11-21   5*  ga 0.524` | the mark goes to the note |

`_table_row()` tries the forms in this sequence. The model then checks that won + drawn + lost is played. Thus a row read in a wrong order is a problem (`table row not valid`), not a wrong row.

## Result

All survey seasons, compared with `main`:

| | `main` | This change |
|---|---|---|
| Table rows | 21,079 | 21,310 |
| Seasons with a table | 1,449 | 1,468 |
| Table problems | 1,243 | 975 |
| Table checks that agree | 896 | 903 |

No season has fewer rows, and no check that agreed is worse. Examples: Cameroon 2011/12 and Réunion 1999 now agree with all 182 matches.

## Trade-offs

- About 900 short rows in about 100 seasons stay problems.
- Gambia 2005 has the goal difference between the goals and the points (`19-11 [+8] 29`): 10 rows, not read.
- A row with seven numbers in an order that is not known, but with won + drawn + lost = played by chance, is read in a wrong order. The table check shows such a table.
