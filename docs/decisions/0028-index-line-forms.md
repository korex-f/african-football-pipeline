# 28. Lists of champions on RSSSF: more season-line forms

*Status: accepted (November 2026). Adds to the season lines of [decision 21](0021-rsssf-adapter-discovery-and-fetch.md). [All decisions](README.md)*

- **What:** `parse_index()` (`sources/rsssf/index.py`) reads three more forms of a season line and one more form of a heading.
- **Why:** The survey of 56 African countries found season links that the index did not read. All the seasons of Congo from 1979 to 1994 were missing. In South Africa, the 30 PSL seasons were in the list "La Mercy Beach League".
- **How the project did it:** A script compared, on the 55 lists of champions of the survey, each link in a `<pre>` block with a year in its text to the entries of `parse_index()`. Before the change, it missed 33 of 2,762 links. The same script and a comparison with `main` measured each change.

## The forms

| Form | Example | Before |
|---|---|---|
| A row number before the link | ` 1 <a href="kong79.html">1979</a>  Etoile du Congo` | not read (Congo 1979–1994) |
| Italics before the link | `<i><a href="zaf96.html">1996</a>  Kaizer Chiefs</i>` | not read |
| `-` in place of `/` in the season | `2021-22` (Lesotho) | not read |
| A column label before a heading | `year    <b>PSL</b>` (South Africa) | not a heading: 30 seasons in the list before it |

## Not read, on purpose

| Form | Why |
|---|---|
| A link in a sentence: `additional information on <a ...>1931-1945</a>` | Only a link at the start of a line is a season line (decision 21) |
| `1966-68`, `1999/01` | Two seasons in one link: not one season |
| `1974,1` and `1974,2` (South Africa) | Two parts of one year, in a provincial list |
| `1990/00` (Cape Verde) | A typo for `1999/00`. The rule does not guess |
| Several headings in one line: `<b>NPSL Castle League</b>   <b>Mainstay League</b>` | One line gives the champions of several leagues. The section has the names together; the champion text has all the champions |

## Result

On the 55 lists of the survey, compared with `main`:

- 22 new entries: Congo 14, Somalia 4 (the inter-state list), Lesotho 1, Sudan 1, South Sudan 1, South Africa 1.
- 30 entries move to the correct section: South Africa, from "La Mercy Beach League" to "PSL".
- 0 entries lost. The lists of Nigeria, Ghana and Egypt do not change.
- Links that are not read: 11 of 2,762 (33 before), each in the table above.

## Trade-offs

- The champion text of a line with several columns has all the columns, for example the champion and the runner-up of Congo.
- A row number before the link is a number of 1 to 3 digits. A year (4 digits) before a link is not a row number, thus such a line is not read.
