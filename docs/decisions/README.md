# Architecture Decisions

The project made these decisions in November 2026. At that time, the pipeline started to change from a Soccerway-only scraper to a multi-source system for historical data. Each decision shows what the decision is, why the project made it, and how the project applies it.

Each file is one decision. A decision file is not deleted. If the project changes a decision, a new file replaces it, and the old file shows this in its status line.

| # | Decision |
|---|---|
| 1 | [Cloud platforms are not in scope at this time](0001-no-cloud-platforms.md) |
| 2 | [The pipeline uses multiple sources with fallback](0002-multiple-sources-with-fallback.md) |
| 3 | [Each adapter keeps fetch and parse separate](0003-separate-fetch-and-parse.md) |
| 4 | [Sources and fetchers are different; the project does not use Firecrawl](0004-sources-and-fetchers-no-firecrawl.md) |
| 5 | [PostgreSQL comes after the source-neutral data model](0005-postgresql-after-source-neutral-model.md) |
| 6 | [Soccerway and Flashscore are one source](0006-soccerway-and-flashscore-are-one-source.md) |
| 7 | ["Verified" has a definition that you can test](0007-testable-definition-of-verified.md) |
| 8 | [Pydantic for data from a source, frozen dataclasses for internal data](0008-pydantic-and-frozen-dataclasses.md) |
| 9 | [Parsing runs in Python, not in the browser](0009-parse-in-python-not-in-browser.md) |
| 10 | [The raw store keeps pages as files, with a manifest](0010-raw-store-files-with-manifest.md) |
| 11 | [The adapter interface is a Protocol, not a base class](0011-adapter-interface-is-a-protocol.md) |
| 12 | [The type checker is basedpyright, in standard mode](0012-basedpyright-in-standard-mode.md) |
| 13 | [Build the new code next to the old code, and prove that they are equal](0013-build-new-code-next-to-old-code.md) |
| 14 | [The pipeline database is a separate PostgreSQL 18 container](0014-separate-postgresql-18-container.md) |
| 15 | [Plain SQL migrations with a small runner, not Alembic](0015-plain-sql-migrations-not-alembic.md) |
| 16 | [The database repeats the simple rules of SourceMatch](0016-database-repeats-sourcematch-rules.md) |
| 17 | [sqlfluff formats the SQL files](0017-sqlfluff-formats-sql.md) |
| 18 | [The loader records each run in three transactions, and keeps the matches that the source stops to show](0018-loader-records-each-run.md) |
| 19 | [The exports read from the database, and the coverage uses n × (n − 1)](0019-exports-read-from-the-database.md) |
| 20 | [One season label style for all sources](0020-one-season-label-style-for-all-sources.md) |
| 21 | [The RSSSF adapter: discovery from the list of champions, and polite plain HTTP](0021-rsssf-adapter-discovery-and-fetch.md) |
| 22 | [The RSSSF parser: the first competition with results, line rules, and visible problems](0022-rsssf-parser.md) |
| 23 | [Final tables are stored, and a table check compares them with the matches](0023-final-tables-and-the-table-check.md) |
