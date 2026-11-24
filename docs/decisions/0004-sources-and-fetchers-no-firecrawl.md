# 4. Sources and fetchers are different; the project does not use Firecrawl

*Status: accepted (November 2026). [All decisions](README.md)*

- **What:** A *source* is the location of the data and the method to read it, for example Soccerway or RSSSF. A *fetcher* is the method to download pages, for example plain HTTP or Playwright. Version 1 does not use Firecrawl.
- **Why:** Firecrawl is a paid API. Its AI extraction does not always give the same result. The project must have collection that you can repeat and test. Playwright already reads pages that use JavaScript.
- **How:** If the project adds Firecrawl in the future, it will be a fetcher only. It will not parse data.
