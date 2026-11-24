# 10. The raw store keeps pages as files, with a manifest

*Status: accepted (November 2026). [All decisions](README.md)*

- **What:** The store keeps the pages of one season in one folder: `data/sources/{source}/{league}/{season}/`. Each page is a `.html.gz` file. A `manifest.json` file has an entry for each page: the URL, the file path, the fetch time (UTC), the sha256 value and the timezone.
- **Why:**
  - **Parse again:** after a parser repair, the pipeline reads the stored pages. It does not scrape the site again.
  - **Resume:** a new run reads the manifest and does not get a page again.
  - **Test fixtures:** a stored page can become a fixture for a regression test.
- **How:**
  - The store writes the page file first, then the manifest. If the process stops between the two writes, the manifest does not refer to a missing file.
  - The store writes the manifest to a temporary file, then renames it. A rename is atomic. Thus, the manifest is never half written.
  - The sha256 value comes from the HTML text, not from the gzip file. The gzip header contains a time. Thus, the same page gives different gzip bytes.
  - When the store reads a page, it compares the sha256 value. A damaged file causes an error. It does not give wrong data.
  - The store rejects unsafe file names, for example names with `..`. The match IDs in the file names come from the web page, and the store must not trust them.
  - `has(url, timezone)` compares the timezone too. Soccerway shows times in the browser timezone. Thus, a page from a different timezone is different data.
- **Trade-offs:**
  - Disk space (measured): Ghana 2023/24 has 306 pages and uses 24 MB, compressed. The results page is 117 KB. The manifest is 99 KB. The `data/` folder is not in git.
  - The store writes the full manifest at each save. For approximately 300 pages in each season, this is fast.
  - In roadmap step 3, the page metadata can move from the manifest into PostgreSQL.
