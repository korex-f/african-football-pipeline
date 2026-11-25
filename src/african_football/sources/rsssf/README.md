# The `rsssf` module

This folder has the adapter for RSSSF, the Rec.Sport.Soccer Statistics Foundation (https://www.rsssf.org/). For the decisions, refer to [decision 21](../../../../docs/decisions/0021-rsssf-adapter-discovery-and-fetch.md).

| File | What it does |
|---|---|
| `index.py` | Reads a list of champions, and gives one `IndexEntry` for each season line |
| `http.py` | Gets pages: one at a time, with an interval, with retries |
| `parser.py` | Reads the matches of the top league from a season page ([decision 22](../../../../docs/decisions/0022-rsssf-parser.md)) |
| `tables.py` | Reads the final tables of the top league, and compares a table with the matches ([decision 23](../../../../docs/decisions/0023-final-tables-and-the-table-check.md)) |
| `adapter.py` | `RsssfAdapter`: `discover_seasons`, `fetch` and `parse` |

The RSSSF pages are the work of their authors. Their licence permits copies when the authors are acknowledged. The fixtures in `tests/fixtures/rsssf/` name the authors in their README.

The sections below explain the techniques in this code: what each technique is, why the code uses it, and how.

---

## 1. Regular expressions for a document with lines

**What:** `index.py` reads the list with regular expressions, not with BeautifulSoup.

**Why:** In a list of champions, the meaning is in the lines of a `<pre>` block:

```html
<pre>
<b>National League/Nigeria Football League</b>
<a href="nig72.html#72">1972</a>    Mighty Jets (Jos)
<a href="nig2022.html">2021/22</a> Rivers United (Port Harcourt)
</pre>
```

A season line **starts** with a link. A link in a sentence is not a season line. An HTML parser gives a tree of elements, and the lines are lost. With the text of the `<pre>` block, `splitlines()` gives the lines, and a regular expression with `^` finds the lines that start with a link.

**How:**
- `_BLOCK` finds the headings (`<h1>` to `<h4>`) and the `<pre>` blocks in the sequence of the page. Each match has a named group, `heading` or `pre`. The group that did not match is `None`.
- `re.DOTALL` makes `.` also match a line break, thus `.*?` can go over many lines of a `<pre>` block. The `?` makes it stop at the first `</pre>`, not at the last.
- `<h([1-4])[^>]*>(...)</h\1>`: `\1` is the same digit as the first group, thus `<h4>` must end with `</h4>`.
- `html.unescape()` changes `&ouml;` to `ö`.

## 2. The text of the link is the season, not the file name

| File | Season |
|---|---|
| `nig2022.html` | 2021/22 |
| `gha04.html` | 2004/05 |
| `gha05.html` | 2005 |
| `egy1913.html#bola1` | 1912/13 |

`parse_season_years()` reads the text. A two-digit end year goes into the century of the next year: `(start + 1) // 100 * 100 + end`. Thus `1999/00` is 1999 to **2000**, not 1999 to 1900. A deliberate break with `start // 100 * 100` made the `1999/00` test fail.

## 3. One heading for each list

A page can have lists of different competitions. The parser keeps the last heading that it found: an `<h4>` before a block, or a `<b>` line in a block. Each entry has its heading. `select_section()` keeps the entries of one heading, and ignores upper case, lower case and extra spaces.

Without this step, Egypt 1948/49 has two entries, with two different champions (Cairo League and National League).

## 4. URLs: `urljoin` and `urldefrag`

```python
urljoin("https://www.rsssf.org/tablesn/nigchamp.html", "nig72.html#72")
# 'https://www.rsssf.org/tablesn/nig72.html#72'

urldefrag("https://www.rsssf.org/tablesn/nig72.html#72")
# DefragResult(url='https://www.rsssf.org/tablesn/nig72.html', fragment='72')
```

`urljoin` makes a full URL from a link that is relative to the page. `urldefrag` removes the anchor (`#72`). The server ignores the anchor, thus the adapter gets and stores the page without it. The season keeps the anchor in `season.url`, for the parser.

## 5. Text without a declared character set

The pages do not tell their character set. `decode_page()` tries three in sequence:

| Encoding | Why in this sequence |
|---|---|
| UTF-8 | Strict: bytes that are not valid UTF-8 cause an error. If no error occurs, the text is very probably UTF-8. |
| Windows-1252 | The usual character set of old pages, written on Windows. It has curly quotes and `é`. Five byte values have no character in it. |
| Latin-1 | Each of the 256 byte values is a character. Thus this step never fails. |

## 6. A polite client that tests can control

**What:** `RsssfHttp` waits at least 3 seconds between two requests, and does retries after 5, 15 and 45 seconds.

**Why:** RSSSF is an archive that volunteers keep. The developer's network had DNS failures during the project.

**How:** The client gets its `sleep` and its `clock` as parameters. The tests give a fake clock and a fake `sleep` that only records the time. Thus a test of "wait 2 seconds" takes no time, and its result is exact:

```python
http.get("https://www.rsssf.org/a.html")
fake_time.now += 1.0          # the caller used 1 second
http.get("https://www.rsssf.org/b.html")
assert fake_time.waits == [2.0]
```

This is *dependency injection*: the code gets the things that it uses from outside, and a test can replace them.

## 7. Synchronous HTTP in an async adapter

**What:** `requests` is synchronous, but the adapter methods are `async`, because the `SourceAdapter` Protocol has `async def fetch`. The adapter calls `await asyncio.to_thread(self.http.get, url)`.

**Why:** A synchronous call in an `async` method stops the event loop until the page arrives. `asyncio.to_thread` runs the call in a different thread, and the event loop can do other work. The wait between requests (`time.sleep`) is also in that thread.

## 8. Status from the text of the list

| Text after the link | Status |
|---|---|
| A champion | `COMPLETED` |
| `abandoned`, `not finished`, ... | `NO_WINNER` (no champion) |
| Nothing, and the season is not over | ongoing: not in the result |

The regular expression `^(abandoned|not finished|...)\b` uses `\b` (a word boundary). Thus a team name that starts with one of these words but continues, is not a match.

## 9. The Protocol check

`test_adapter_is_a_source_adapter` has this line:

```python
adapter: SourceAdapter = RsssfAdapter(logger)
```

At this line, the type checker compares `RsssfAdapter` with the `SourceAdapter` Protocol ([decision 11](../../../../docs/decisions/0011-adapter-interface-is-a-protocol.md)). For a deliberate break, the project removed the `store` parameter of `fetch`. basedpyright gave the error `"RsssfAdapter" is not assignable to declared type "SourceAdapter"`.

## 10. A line parser with state

**What:** `parse_lines()` reads the lines of a competition from top to bottom. It keeps a *state*: the stage, the round, the date, and whether a note is open. Each line changes the state or gives a result.

```text
Round 19                                   -> round = 'Round 19', date = None
[Mar 20]                                   -> date = 2024-03-20
Medeama      abd Aduana   [abandoned ...   -> a row with round 19 and 2024-03-20
[Mar 21]                                   -> date = 2024-03-21
Medeama      2-0 Aduana                    -> a row (the replay)
```

**Why:** A result line does not have its round or its date. They come from the lines before it. A function that reads one line alone cannot know them.

**How:** The order of the checks is important. A line that starts with a space is a list of scorers or a note, never a result. A table row (` 1.Enyimba ...`) is not a result. Then the date, the round, the stage and the result rules are tried, in this sequence.

## 11. A note in a column

Some notes continue at the right of the next result lines:

```text
Gombe United            1-1 Rivers United           [Gombe United 3 points and 3 goals
Enyimba                 2-0 Sporting Lagos           deducted due to fan misconduct
Akwa United             3-1 Abia Warriors            (assault on match officials)]
```

The first parser skipped all the lines of an open note, thus it lost two matches, without a problem in the report. Now the result rule ends the away team at two spaces or a tab, and gives the remainder of the line as `rest`. When a note is open, `rest` is the next part of the note, and the left part is still a result.

The regular expression for the away team: `[^\s\[](?:(?! {2}|\t).)*?[^\s\[]`. `(?! {2}|\t)` is a *negative lookahead*: each character of the name must not be the start of two spaces or a tab. Thus a name can have single spaces (`Sporting Lagos`) but stops at the column gap.

## 12. Layered defences, and how to test each layer

Three rules stop a table row from being a result line:

1. `_TABLE_ROW` (`^\s*\d+\.`): a row starts with its position.
2. `_LETTER`: a team name has a letter. In `10.Kotoko  2 0 0 2  1-3  0`, the "away team" is `0`.
3. The order of the checks in `split_one_block()`: a single row cannot start "a table after results".

For a deliberate break, the project removed rule 1. The fixture tests did not fail: rules 2 and 3 also stopped the bug. A test for rule 1 must give a line that only rule 1 can stop: two relegated rows with single spaces (`10.Kotoko 2 0 0 2 1-3 0 Relegated`), thus the "away team" `0 Relegated` has a letter.

This is a general lesson: when a test does not fail after a deliberate break, either the rule is not necessary, or a different rule hides it. Find out which.

## 13. The year of a date without a year

A season over two years (for example 2023/24) has dates from September to June. The parser keeps the month of the first date of the competition. A month on or after it is in the first year; an earlier month is in the second year:

| Date | First month: September | Year |
|---|---|---|
| `[Sep 15]` | 9 ≥ 9 | 2023 |
| `[Dec 30]` | 12 ≥ 9 | 2023 |
| `[Jan 2]` | 1 < 9 | 2024 |

A calendar-year season (`2015`) has one year for all dates. A date with its year (`[Jan 2, 2025]`) keeps its year. The check: all 306 Ghana 2023/24 dates agree with Soccerway, and the 21,334 matches of the 187 pages have no date outside the years of their season.

## 14. Problems that are visible

The parser does not stop at a line that it cannot read, and it does not ignore the line. `parse_page()` gives the matches and a list of problems:

- `not read: Sportnet  4-0  [?]`: a line that looks like a result (a word, a result, a word) but does not have the known form.
- `not valid: Masry 1-0 ZED: ...`: a row that is not a valid `SourceMatch`.
- `16 lines of a results grid or crosstable not read`: one problem for each page, not one for each line.
- `no season part for the anchor #99`.

A page with only a results grid gives a problem. Thus it does not look the same as a page without results. The adapter puts the problems in `RsssfAdapter.problems` and in the log.

## 15. Measure on all the data, not on samples

The first version of the parser was correct for the 15 sample pages of the survey. On all 187 pages, a report for each season showed the problems: a league with 80 of 242 matches, 8 seasons with the same 5 matches, a page where the table was the league. The report compared the number of matches with n × (n − 1) for n teams, the dates with the years of the season, and the number of problems.

The fixtures in `tests/fixtures/rsssf/seasons/` are the pages that showed each form. Each fixture test has a number from this report, checked against the page.

## 16. A check without names: sums

**What:** `table_check()` compares a final table with the matches by two sums:

| | From the table | From the matches |
|---|---|---|
| Matches | sum of `played` ÷ 2 | played and awarded matches with a score |
| Goals | sum of `goals for` | sum of the goals of these matches |

**Why:** Each match is in the table two times: one time for each team. Thus the sum of `played` is two times the number of matches. Each goal is a `goal for` of one team. The sums do not need team names, and the names of a table (`Enyimba FC (Aba)`) are often not the names of the results (`Enyimba`).

**How:** A walkover without a score (`w/o`) is not counted: its goals are not known. An abandoned match is not counted: the table does not have it.

The check is a diagnostic. When it agrees, the season is very probably complete. When it does not agree, the kind of difference tells the cause: few matches (results missing), the same matches but different goals (a deduction of goals), more matches than the table (replays).

## 17. One copy of a table

Many pages have the final table two times, before and after the results. The reader keeps the first table of each stage. It compares a later table of the same stage with the first: a different copy is a problem, because a person must decide which is correct. Without this rule, each table was two times too large, and all the checks failed.

## 18. Silent losses in a filter

A filter that skips lines can lose data without a problem in the report. Two examples from the table reader:

- A rule skipped numbered lists of teams (`1.Stationery Stores FC, Lagos;`), with the test "no digit after the team name". `9.3SC Shooting Stars  38 ...` has a digit at the start of the name, thus the row was skipped. The check of 5 NPFL seasons showed 361 matches for 380: exactly one team of 38 matches.
- The next version required two number columns. Then `1. Leventis United  22-30` (a short table of 1986) was skipped too: it is a row that must be a problem, not a row that the reader must ignore.

The rule now: a table row has a number after a space, after the team name. The lesson: after a change to a filter, compare the totals before and after, not only the problems.

## 19. Choosing the league: rules that a comparison made

**What:** `choose_league()` chooses the national league among the competitions of a page ([decision 24](../../../../docs/decisions/0024-choosing-the-national-league-on-a-page.md)). It gives a `LeagueChoice`: the competition, the reason, and the alternatives. The adapter writes them to the log:

```text
RSSSF 2023/2024: league 'Ghana Premier League' (first league); other competitions: MTN FA Cup 2023/24; Super Cup 2024
```

**Why:** The rule of decision 22 ("the first competition with results") was tested on three countries. On 56 countries it took a cup in 208 seasons, without a problem in the report.

**How the rules were made:** Not from ideas, but from a comparison. A script (outside the repository) computed, for each of 2,448 seasons, the chosen competition, the matches, the table rows and the table check. After each change to the rules, it compared each season with the version before, and listed the changes. Each new rule made other changes, and some were wrong:

| Change | What the comparison showed | Correction |
|---|---|---|
| A national name replaces the first candidate | Nigeria: the second level replaced 'Nigeria Football League' | Only if the first candidate has no league word |
| — | 'NPFL 2023/24' has no league word | An abbreviation that ends with L is a league word |
| — | The page title 'Nigeria 2003' was replaced | The page title stays |
| A sentence has 3 lower-case words | 'Championnat national de première division' was a sentence | League words do not count |
| 'Stage' is a league word | 'Group A' (4 matches) stayed against the national league (36) | A stage stays only with more results |
| Regional leagues only (4 or more place names) | Years on pages with many seasons were place names | A name with a year is not a place |
| The table reader reads the first competition when no league is chosen | Cape Verde: the table of an island league | Only when the page has no competition with data |

The lesson: for rules with words, a test of one page shows that a rule works. A comparison of all pages shows what else the rule changes.

## 20. Regular expressions in more than one language

The rules use English, French and Portuguese words: `Coupe|Copa|Ta[çc]a`, `deuxi[eè]me|2[eè]me`, `divis[aã]o`. Character classes (`[çc]`, `[eè]`) accept a word with or without its accent, because some pages write `Taca` and some `Taça`. `re.IGNORECASE` also works for these letters in Python 3.

The words of all the rules together are one pattern, `_VOCABULARY`. The note rule uses it: a name in lower case ('Championnat national de première division') is not a sentence, because its lower-case words are league words. `_VOCABULARY` is made at the end of the module, after all the patterns that it joins.
