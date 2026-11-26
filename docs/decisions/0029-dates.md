# 29. Dates on RSSSF pages: the years from the page title, a tested window, and more month names

*Status: accepted (November 2026). Replaces the rule "the year of a date without a year" of [decision 22](0022-rsssf-parser.md). [All decisions](README.md)*

- **What:** The parser gives a year to a date without a year (`[Mar 7]`) with three changes. The years of the season come from the page title. The window of 12 months for the dates is the best of all windows. The month names can be French or Portuguese, and a group heading can have a date. A season of more than 12 months is a problem in the report.
- **Why:** The survey of 56 countries found 703 "year-size jumps": a date more than 250 days from the date before it on the page. That is the sign of a wrong year. The causes:
  1. The list of champions gives one year for 375 seasons over two years: `2019` links to the page `Angola 2018/19`. The parser used the years of the list, thus the dates of October 2018 were in October 2019.
  2. The window started at the first month on the page. Chad 2008 lists August before July, thus July was in 2009.
  3. A calendar-year season had all dates in one year. Burkina Faso 2001 starts on 23 December 2000.
- **How the project did it:** A script compared the dates of each survey season with `main`, in page sequence, and counted the year-size jumps and the dates outside the years of the page title.

## The debate

**Which source gives the years of a season?** In about 425 seasons, the list of champions and the page title give different years (375 times: one year in the list, a season over two years in the title). Three options:

1. The title for the dates only (the decision). The season label and the season identity stay from the list (decisions 20 and 21). No change to the discovery, the database or the comparison with Soccerway.
2. The title for the dates and the labels. Correct labels (for example NPFL 2022/23 in place of 2023), but the discovery must get each season page, and the identity of seasons in the database changes.
3. The list only. 375 seasons keep a wrong year for a part of their dates.

The user chose option 1. The label question stays for step 5 (Nigeria 2023 is `Nigeria 2022/23`).

**How to find the window.** Two rules failed on the survey before the decision:

- "The first month on the page starts the season", with the year moved back if most dates are then in the next year: 11 seasons became worse, because pages do not always start with the first month (Chad 2008, Seychelles 2019).
- "The month after the longest run of months without a date": long seasons with a short break (the Africa Cup in January) started at the wrong month (Tunisia 2011/12, Algeria 2022/23).

Thus the parser tests all windows and keeps the best.

## The window

A date without a year is in the first year if its month is on or after the first month, else in the next year. `_date_window()` tests each first month (1 to 12) with each first year (the year before the season, the start year, the end year), and keeps the window with:

1. the fewest jumps of more than 250 days **back** between two dates in page sequence. A wrong year makes such a jump. A postponed match listed in its round makes a smaller one. A long gap forward is not a jump: a page can have rounds without dates;
2. then the fewest dates outside the years of the season;
3. then, for a season over two years, the fewest dates in the wrong half: July to December in the start year, January to June in the end year;
4. then the first month nearest to the first date on the page (the rule of decision 22).

A date with its year on the page (`[Dec 28, 2008]`) does not count, and it keeps its year. Counted as a December without a year, the two dates of 2008 in Eritrea 2009 made the window December 2009 to November 2010.

## Month names and group headings

| Form | Example |
|---|---|
| English, full or short | `[Sep 15]`, `[Sept 15]`, `[September 15]` |
| French | `[Mai 19]`, `[Févr 3]`, `[Juin 2]`, `[Juil 4]`, `[Août 8]`, `[Déc 1]` |
| Portuguese | `[Maio 5]`, `[Fev 3]`, `[Abr 4]`, `[Ago 8]`, `[Set 9]`, `[Out 12]`, `[Dez 1]` |
| A date on a group heading | `Group A [Aug 13]`, `Poule B [Feb 15,16]` |

`_month()` removes the accents and compares the first 3 letters. `juin` and `juil` have the same first 3 letters, thus they are full words.

## Result

All survey seasons, compared with `main`:

| | `main` | This change |
|---|---|---|
| Matches with a date | 232,195 | 232,663 |
| Year-size jumps | 703 in 298 seasons | 20 in 18 seasons |
| Dates outside the years of the page title (a calendar year: ±1 year) | 243 | 3 |

- 418 seasons have other dates. Nigeria, Ghana and Egypt: 10 seasons, 21,099 → 21,149 matches with a date. Nigeria 2001 now starts in November 2000.
- 2 seasons have more year-size jumps: Namibia 1997/98 and Sudan 2019/20. Their dates go over more than 12 months (July 1997 to July 1998; August 2019 to October 2020). No window of 12 months can hold them.
- A new problem shows such seasons: "N dates more than 200 days before the date before them". 51 survey seasons have it, also the seasons of 2019/20 that stopped for COVID-19 (Egypt, Morocco, Mali, South Africa, Sudan, ...). The limit of the problem (200 days) is lower than the limit of the window (250 days): the problem tells a person to look. Egypt 2019/20 goes back 210 days.

## Trade-offs

- A season of more than 12 months has dates with a wrong year. The problem shows it.
- The season label can be different from the years of the dates (Angola `2019` has dates from 2018). Step 5 must use the label for the identity and the dates for the matches.
- A page with many seasons (an anchor) has one title for all its seasons, thus the parser uses the years of the list for it.
- `[21 Dec.]` (the day first) is not read. The survey has 5 or fewer.
