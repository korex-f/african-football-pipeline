# 5. PostgreSQL comes after the source-neutral data model

*Status: accepted (November 2026). [All decisions](README.md)*

- **What:** PostgreSQL will become the single source of truth (roadmap step 3). The pipeline will make the JSON and TXT exports from the database, not directly from the scraper output.
- **Why:** The database tables must agree with the source-neutral match record from step 2. They must not agree with the page structure of Soccerway. If the project adds the database first, the tables will agree with the current Soccerway data. Then the project must change the tables again for RSSSF, because RSSSF often has no dates or rounds. Also, if the project makes one change at a time, it is easy to find the cause of a failure.
- **How (planned):** The project will use a dedicated database. This database is not the Airflow metadata database. It will contain tables for:
  - Raw page metadata
  - Match records from each source
  - Reconciled matches
  - Teams and team aliases
  - Season coverage
  - Collection runs
