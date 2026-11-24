# 20. One season label style for all sources

*Status: accepted (November 2026). [All decisions](README.md)*

- **What:** A season that crosses into the next year has the label `2023/2024`. A season that starts and ends in one year (a calendar-year season) has the label `2019`. The function `season_label()` in `models/season_model.py` makes all labels. Each source adapter must use it.
- **Why:** The `seasons` table has one row for each league and label. Reconciliation (roadmap step 5) compares the matches of one season from two sources. That is possible only if the two sources give the season the same label.
- **The problem that the project found:** Before version 1.2.0, the Soccerway discoverer read `npfl-2019` (the 2019 season, January to July 2019) as the years 2018 and 2019, thus the label was `2018/2019`. RSSSF calls the same season `2019`. The labels did not agree, and `2018/2019` usually means a season with a different shape. The project ran the discoverer on the live archive: 12 NPFL seasons (2005 to 2007, 2012 to 2019) and 2 Ghana seasons (2017, 2018) had the wrong label. A unit test had the wrong rule as its expected result.
- **The debate:**
  1. **Keep the Soccerway labels, and make the other sources copy the rule.** No change to the current output. But the labels stay wrong, and each new source must copy the rule.
  2. **Correct the label in the discoverer (the decision).** A calendar-year season starts and ends in the same year. The label and the file names of 14 seasons change, thus `PIPELINE_VERSION` is now `1.2.0`.
- **How:**
  - `season_label(start_year, end_year)` gives `"2019"` or `"2023/2024"`. Other year pairs cause `ValueError`. The `seasons` table has the same rule as a `CHECK` constraint.
  - `build_season_str()` in `utils/file_saver.py` gives the season part of the file names: `2019` or `2023-24`. `main.py` and the Airflow tasks used a copy of the old rule. Now they use this function.
- **Trade-offs:**
  - Output files from before version 1.2.0 have the old names, for example `2016-17.json` for the Ghana 2017 season. A new run writes `2017.json`. The old files do not change.
  - The label rule cannot connect two seasons that the sources divide differently. Soccerway's `npfl-2022-2023` is the season that RSSSF calls `2023` (a short season in 2023). Reconciliation (roadmap step 5), or a label for each season in the configuration, must connect them.
