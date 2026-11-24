# 3. Each adapter keeps fetch and parse separate

*Status: accepted (November 2026). [All decisions](README.md)*

- **What:** Each source adapter will have three steps:
  1. `discover_seasons` finds the available seasons.
  2. `fetch` downloads the raw pages and keeps them without changes.
  3. `parse` changes the stored pages into match records that do not depend on the source.
- **Why:** The pipeline keeps the raw pages. Thus, after a parser repair, the pipeline can parse the data again without a new scrape. The saved pages also become fixtures for regression tests. After an interruption, a run can continue and ignore the pages that it already has.
- **How (planned, roadmap step 2):** The project will first change the Soccerway scraper to this structure. The output will not change. To verify the change, compare the JSON before and after the change.
