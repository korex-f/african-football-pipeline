# The `rsssf` module

This folder has the adapter for RSSSF, the Rec.Sport.Soccer Statistics Foundation (https://www.rsssf.org/). For the decisions, refer to [decision 21](../../../../docs/decisions/0021-rsssf-adapter-discovery-and-fetch.md).

| File | What it does |
|---|---|
| `index.py` | Reads a list of champions, and gives one `IndexEntry` for each season line |
| `http.py` | Gets pages: one at a time, with an interval, with retries |
| `adapter.py` | `RsssfAdapter`: `discover_seasons`, `fetch`, and later `parse` |

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
