# 9. Parsing runs in Python, not in the browser

*Status: accepted (November 2026). [All decisions](README.md)*

- **What:** Playwright only gets the pages. BeautifulSoup reads the stored HTML in Python. Before, a JavaScript function (`EXTRACT_STAGE_JS`) read the page in the browser.
- **Why:**
  - The pipeline can parse the stored pages again in seconds, without a browser and without the network.
  - The parser tests do not need Chromium.
  - The RSSSF adapter will parse text in Python too. Thus, all sources use the same method.
- **The debate:** Option 1 was to keep the JavaScript parser and load each stored page into a headless browser to parse it again. This keeps the tested code, but each parse needs a browser. Option 2 (the decision) was to write the parser again in Python. The cost is a rewrite of approximately 60 lines of JavaScript.
- **How:**
  - The parser has three levels. Level 1 (`extract_stages`) gives exactly the same data as the JavaScript function. Level 2 adds the stage and the round to each row. Level 3 (`to_source_match`) converts the text to values and makes a `SourceMatch`.
  - A parity test runs the JavaScript and the Python parser on the same fixture pages. The two outputs must be equal. To make sure that the test can fail, the project broke the Python parser on purpose. The test found the error.
  - The parser uses `html.parser`, which is part of Python. The pages come from a browser, thus the HTML is correct.
- **Trade-offs:**
  - Until roadmap step 2 is complete, two parsers exist. The parity test keeps them equal. When the old scraper is removed, the parity test is removed too.
  - Speed (measured in part 3b): a real match page has approximately 450 KB of HTML. The test fixture has 14 KB. `html.parser` takes approximately 150 ms for each real page, thus approximately 46 seconds for the 305 match pages of a season. The first version of this decision said that speed is not important. That statement came before a measurement on real pages.
  - `lxml` took approximately 97 ms for each page and gave the same results. This is 1.5 times faster. The project did not add `lxml`, because the gain is small for one more dependency. Instead, the adapter parses each page one time only (see the changelog of part 3b).
