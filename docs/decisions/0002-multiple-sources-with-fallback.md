# 2. The pipeline uses multiple sources with fallback

*Status: accepted (November 2026). [All decisions](README.md)*

- **What:** A Source Manager will try the sources in a priority sequence for each season. Soccerway is first. RSSSF and other sources are next. The Source Manager uses the next source only if a season is incomplete, or if a person requests verification.
- **Why:** If the pipeline scrapes all sources for each season, the load on the sites increases. The run time and the risk of rate limits also increase. Usually, the primary source has all the data for a season. The pipeline needs the other sources only to fill gaps or to do cross-checks.
- **How (planned, roadmap step 6):** `leagues.yaml` will contain the source priorities for each league. The Source Manager will record the sources that it tried for each season. After an interruption, it will continue from the last successful step.
