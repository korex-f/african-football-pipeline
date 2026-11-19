"""
adapter.py — The Soccerway source adapter.

The adapter has the three steps of the SourceAdapter interface:

    1. discover_seasons: find the seasons in the Soccerway archive.
    2. fetch:            get the results page and the match pages of one
                         season with Playwright. Keep them in the raw store.
    3. parse:            read the stored pages with the Python parser and
                         make SourceMatch records. No browser, no network.

Resume: fetch does not get a page again if the raw store has a complete
copy. A match page is complete when it has a halftime score. If a match
page has no halftime score, the store keeps it (the page can contain the
kick-off time). The next fetch tries to get the page again.

Typical usage:
    async with SoccerwayAdapter(logger) as adapter:
        documents = await adapter.fetch(league, season, store)
        matches = adapter.parse(league, season, documents, store)
"""

import asyncio
import random
from typing import Any, Optional

from playwright.async_api import (
    Browser,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)
from pydantic import ValidationError

from african_football.models.league_model import LeagueConfig
from african_football.models.season_model import SeasonRecord
from african_football.models.source_match import MatchStatus, SourceMatch
from african_football.scraping.season_discoverer import SeasonDiscoverer
from african_football.sources.base import RawDocument
from african_football.sources.raw_store import RawStore, RawStoreError
from african_football.sources.soccerway.parser import (
    SOURCE_NAME,
    MatchPage,
    ResultRow,
    parse_match_page,
    parse_results_page,
    to_source_match,
)
from african_football.utils.logger import PipelineLogger

# ---------------------------------------------------------------------------
# Selectors for the browser steps. The parser has the selectors that read
# the stored pages. Use only stable selectors: see parser.py.
# ---------------------------------------------------------------------------
MATCH_ROW = "div.event__match"
SHOW_MORE_BUTTON = "[data-testid='wcl-buttonLink']:has-text('Show more matches')"
HALFTIME_SCORE = (
    "[data-testid='wcl-overline-02']:text-is('1st Half')"
    " >> xpath=following-sibling::span[1]"
)

RESULTS_NAME = "results.html"

# Number of passes for the match pages that have no halftime score.
HALFTIME_PASSES = 3

# Write a progress line after this number of match pages.
HALFTIME_PROGRESS_INTERVAL = 15

# Maximum time (milliseconds) to wait for the halftime score on a match page.
HALFTIME_WAIT_MS = 15000

# Pause (seconds) between two match pages. This decreases the load on the site.
DEFAULT_DELAY = (1.0, 2.0)


class SoccerwayAdapter:
    """
    Get and parse Soccerway pages for one league season.

    Use the adapter as an async context manager. The context manager
    starts the browser and makes sure that the browser stops.

    Attributes:
        name:          The source name, 'soccerway'.
        network_errors: The number of page loads that failed with a
                        network error or a timeout during the last fetch.
        missing_halftime: The URLs of the match pages that had no halftime
                          score after the last fetch.
    """

    name = SOURCE_NAME

    def __init__(
        self,
        logger: PipelineLogger,
        headless: bool = True,
        delay: tuple[float, float] = DEFAULT_DELAY,
    ) -> None:
        """
        Args:
            logger:   The pipeline logger.
            headless: Run the browser without a window. Use False to see it.
            delay:    The minimum and maximum pause between two match pages.
                      The tests use (0, 0).
        """
        self.logger = logger
        self.headless = headless
        self.delay = delay
        self.network_errors = 0
        self.missing_halftime: list[str] = []
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        # The parsed match pages, by sha256. A real match page has approximately
        # 450 KB of HTML and takes approximately 150 ms to parse. fetch and
        # parse both read the match pages, thus the cache prevents a second
        # parse. The sha256 identifies the content, thus the cache is safe.
        self._match_pages: dict[str, MatchPage] = {}

    async def __aenter__(self) -> "SoccerwayAdapter":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    # -----------------------------------------------------------------------
    # Step 1: discover_seasons
    # -----------------------------------------------------------------------

    async def discover_seasons(self, league: LeagueConfig) -> list[SeasonRecord]:
        """Return the seasons of the league in the Soccerway archive."""
        async with SeasonDiscoverer(league, self.logger, self.headless) as discoverer:
            return await discoverer.discover()

    # -----------------------------------------------------------------------
    # Step 2: fetch
    # -----------------------------------------------------------------------

    async def fetch(
        self,
        league: LeagueConfig,
        season: SeasonRecord,
        store: RawStore,
        refresh: bool = False,
    ) -> list[RawDocument]:
        """
        Get the pages of one season and keep them in the store.

        Args:
            league:  The league configuration.
            season:  The season. It must have a results URL.
            store:   The raw store for this season.
            refresh: If True, get all pages again. If False, use the
                     complete pages that the store has.

        Returns:
            All documents in the store.

        Raises:
            RuntimeError: The adapter is not in an `async with` block.
            ValueError: The season has no URL.
        """
        if self._browser is None:
            raise RuntimeError("Use 'async with SoccerwayAdapter(...)' before fetch().")
        if not season.url:
            raise ValueError(f"Season {season.season} has no URL.")

        self.network_errors = 0
        self.missing_halftime = []
        timezone = league.timezone

        # Show dates and kick-off times in the local timezone of the league.
        page = await self._browser.new_page(timezone_id=timezone)
        try:
            results = await self._fetch_results_page(
                page, season.url, store, timezone, refresh
            )
            if league.fetch_halftime:
                targets = self._match_page_targets(league, season, store.load(results))
                pending = [
                    t
                    for t in targets
                    if refresh or not self._is_complete(store, t[1], timezone)
                ]
                self.logger.log(
                    f"Match pages: {len(targets)} needed, "
                    f"{len(targets) - len(pending)} complete in the raw store, "
                    f"{len(pending)} to get"
                )
                for pass_num in range(1, HALFTIME_PASSES + 1):
                    if not pending:
                        break
                    if pass_num > 1:
                        await asyncio.sleep(3 if self.delay[1] > 0 else 0)
                    pending = await self._fetch_match_pages(
                        page, store, pending, timezone, pass_num
                    )
                self.missing_halftime = [url for _, url in pending]
        finally:
            await page.close()

        return store.documents()

    async def _fetch_results_page(
        self,
        page: Page,
        url: str,
        store: RawStore,
        timezone: str,
        refresh: bool,
    ) -> RawDocument:
        """Return the stored results page. Get it if the store does not have it."""
        stored = store.get(url)
        if stored is not None and not refresh and store.has(url, timezone):
            self.logger.log("Results page: complete in the raw store")
            return stored

        self.logger.log(f"Loading: {url}")
        await page.goto(url, timeout=60000)
        await page.wait_for_load_state("networkidle")
        await self._load_all_matches(page)
        return store.save(url, RESULTS_NAME, await page.content(), timezone)

    async def _load_all_matches(self, page: Page) -> None:
        """Click 'Show more matches' until all matches are on the page."""
        clicks = 0
        rows = page.locator(MATCH_ROW)
        while True:
            try:
                button = page.locator(SHOW_MORE_BUTTON)
                if await button.count() == 0:
                    break
                before = await rows.count()
                await button.first.scroll_into_view_if_needed()
                await self._pause()
                await button.first.click()
                clicks += 1
                await self._pause(2)
                # Stop if the button stays on the page but gives no new rows.
                if await rows.count() <= before:
                    self.logger.log(
                        "'Show more' click loaded no new matches; stopping",
                        level="WARNING",
                    )
                    break
            except Exception as e:
                self.logger.log(f"Error clicking show more: {e}", level="INFO")
                break
        self.logger.log(
            f"Loaded {await rows.count()} matches ({clicks} clicks)", level="SUCCESS"
        )

    def _match_page_targets(
        self, league: LeagueConfig, season: SeasonRecord, results_html: str
    ) -> list[tuple[str, str]]:
        """
        Return (match_id, url) for each match page that the pipeline needs.

        The pipeline needs the match page of each match that has a URL and
        is not awarded. An awarded match has no halftime score.
        """
        targets = []
        for row in parse_results_page(results_html):
            if not row.url:
                continue
            match = self._to_source_match(league, season, row, None, ())
            if match is not None and match.status is not MatchStatus.AWARDED:
                targets.append((row.match_id, row.url))
        return targets

    def _is_complete(self, store: RawStore, url: str, timezone: str) -> bool:
        """Return True if the store has the match page with a halftime score."""
        document = store.get(url)
        if document is None or not store.has(url, timezone):
            return False
        try:
            return self._match_page(store, document).halftime is not None
        except RawStoreError:
            return False

    def _match_page(self, store: RawStore, document: RawDocument) -> MatchPage:
        """Return the parsed match page. Parse each page content one time only."""
        page = self._match_pages.get(document.sha256)
        if page is None:
            page = parse_match_page(store.load(document))
            self._match_pages[document.sha256] = page
        return page

    async def _fetch_match_pages(
        self,
        page: Page,
        store: RawStore,
        targets: list[tuple[str, str]],
        timezone: str,
        pass_num: int,
    ) -> list[tuple[str, str]]:
        """
        Get the match pages and keep them in the store.

        The function keeps a page also if it has no halftime score, because
        the page can contain the kick-off time.

        Returns:
            The targets that have no halftime score after this pass.
        """
        pending = []
        total = len(targets)
        for count, (match_id, url) in enumerate(targets, 1):
            try:
                await self._pause()
                # Do not wait for the full page load. Ads and trackers can keep
                # the page busy for more than 30 seconds.
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                try:
                    await page.locator(HALFTIME_SCORE).first.wait_for(
                        timeout=HALFTIME_WAIT_MS
                    )
                    found = True
                except PlaywrightTimeoutError:
                    found = False
                store.save(
                    url, f"matches/{match_id}.html", await page.content(), timezone
                )
                if not found:
                    pending.append((match_id, url))
            except Exception as e:
                if "timeout" in str(e).lower() or "network" in str(e).lower():
                    self.network_errors += 1
                pending.append((match_id, url))

            # Show progress at each interval and at the last page.
            if count % HALFTIME_PROGRESS_INTERVAL == 0 or count == total:
                self.logger.log(
                    f"Halftime pass {pass_num}: {count}/{total} matches done, "
                    f"{len(pending)} failed"
                )
        return pending

    async def _pause(self, factor: float = 1) -> None:
        low, high = self.delay
        if high > 0:
            await asyncio.sleep(random.uniform(low * factor, high * factor))

    # -----------------------------------------------------------------------
    # Step 3: parse
    # -----------------------------------------------------------------------

    def parse(
        self,
        league: LeagueConfig,
        season: SeasonRecord,
        documents: list[RawDocument],
        store: RawStore,
    ) -> list[SourceMatch]:
        """
        Read the stored pages and return one SourceMatch for each match.

        The function uses the match pages only if the league has
        fetch_halftime: true. A row that does not give a valid SourceMatch
        is not included. The log shows the row.

        Raises:
            ValueError: The documents do not contain the results page.
        """
        by_url = {document.url: document for document in documents}
        results = by_url.get(season.url or "")
        if results is None:
            raise ValueError(f"No stored results page for {season.season}.")

        matches = []
        for row in parse_results_page(store.load(results)):
            page = None
            raw_documents: tuple[str, ...] = (results.sha256,)
            match_document = by_url.get(row.url or "")
            if league.fetch_halftime and match_document is not None:
                page = self._match_page(store, match_document)
                raw_documents += (match_document.sha256,)

            match = self._to_source_match(league, season, row, page, raw_documents)
            if match is None:
                self.logger.log(
                    f"Skipping unparseable match row {row.match_id}", level="WARNING"
                )
                continue
            matches.append(match)
        return matches

    def _to_source_match(
        self,
        league: LeagueConfig,
        season: SeasonRecord,
        row: ResultRow,
        page: Optional[MatchPage],
        raw_documents: tuple[str, ...],
    ) -> Optional[SourceMatch]:
        """Call to_source_match. Return None if the data breaks a rule."""
        try:
            return to_source_match(
                row,
                page,
                league_code=league.code,
                season=season.season,
                timezone=league.timezone,
                raw_documents=raw_documents,
            )
        except ValidationError as e:
            self.logger.log(
                f"Match row {row.match_id} breaks a SourceMatch rule: "
                f"{e.errors()[0]['msg']}",
                level="WARNING",
            )
            return None
