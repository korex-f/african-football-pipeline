# 21. The RSSSF adapter: discovery from the list of champions, and polite plain HTTP

*Status: accepted (November 2026). [All decisions](README.md)*

- **What:** `RsssfAdapter` (`sources/rsssf/`) is the second source adapter. `discover_seasons` reads the RSSSF list of champions of a league and gives one `SeasonRecord` for each season page. `fetch` gets a season page into the raw store. `parse` comes in roadmap step 4, part 2.
- **Why:** RSSSF has results for many old seasons that Soccerway does not have, and its final tables can verify a season ([decision 7](0007-testable-definition-of-verified.md)).
- **How the project examined RSSSF:** Before the design, the project read 15 pages of 6 countries (Nigeria, Ghana, Egypt, South Africa, Kenya, Tunisia), from 1990 to 2024. The pages are written by hand, by different volunteers. The facts below come from this survey.
- **The debate:**
  1. **How to find the seasons.**
     - *From the file names* (`nig2015.html` is 2015): simple, but wrong. `nig2022.html` is 2021/22, `gha04.html` is 2004/05 and `gha05.html` is 2005.
     - *From the text of each link in the list of champions (the decision):* one request for each league gives all the seasons. The text is the season (`2021/22`), and the label comes from `season_label()` ([decision 20](0020-one-season-label-style-for-all-sources.md)).
  2. **Which list on the page.** A list of champions can have lists of different competitions. The same season page can be in two lists: Egypt `egy49.html` 1948/49 is in the Cairo League list (champion Zamalek) and in the National League list (champion Al-Ahly). Thus `leagues.yaml` has `rsssf_section`, the heading of the correct list. A heading is a `<b>` line in the `<pre>` block (Nigeria) or an `<h4>` before the block (Egypt). Ghana has one list without a heading, thus its `rsssf_section` is empty.
  3. **A browser or plain HTTP.** The pages are static HTML, thus plain HTTP (`requests`) is sufficient. It is faster, and it needs no browser installation.
  4. **Regular expressions or BeautifulSoup for the list.** The meaning of the list is in its lines: a season line starts with a link in a `<pre>` block. An HTML parser does not keep lines. A few regular expressions read the lines directly. The Soccerway parser uses BeautifulSoup, because its pages have a deep tree with CSS classes.
- **Politeness (RSSSF has no `robots.txt` and no API):**
  - One request at a time, at least 3 seconds between two requests.
  - The User-Agent tells what the client is.
  - The raw store keeps each page, thus the adapter gets a page only one time.
  - Retries after 5, 15 and 45 seconds for network errors and server errors. During the project, DNS failures occurred often. A 404 is not retried.
- **Status of a season:**

  | Line in the list | Status |
  |---|---|
  | A champion | `COMPLETED` |
  | `abandoned`, `not finished`, `not held`, `cancelled`, `annulled`, `void` | `NO_WINNER`, no champion |
  | No champion, and the season is not over | not in the result (ongoing) |
  | No link (`1951/52   not held`) | not in the result (no page) |

- **Character set:** the pages do not declare one. `decode_page()` tries UTF-8, then Windows-1252, then Latin-1. Latin-1 can decode all bytes.
- **Licence:** the pages permit copies when the authors are acknowledged. The fixtures in `tests/fixtures/rsssf/` are unchanged copies, and their README names the authors of each page.
- **Trade-offs:**
  - A `NO_WINNER` season is not scraped (`is_scrapeable()` is false), the same as for Soccerway. Some of these pages have the results of the matches before the season stopped. A later change can collect them.
  - The Nigeria National League (`nnl`) has no list of champions on RSSSF. Its results are on the same season pages as the NPFL. Its discovery needs a different method later.
  - A season that two sources divide differently cannot be connected by the label. Soccerway `npfl-2022-2023` is RSSSF `2023` (decision 20).
  - Each page is a hand-written document. A new author or a new format can break the parser of part 2. The fixtures and the tests show such a break.
