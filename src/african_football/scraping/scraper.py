"""
scraper.py — Core match data scraper for the African football pipeline.

Scrapes match data for a single league season from Soccerway using
Playwright. Handles multi-stage seasons, penalty shootouts, and
optional halftime score enrichment based on league configuration.

Typical usage:
    from african_football.scraping.scraper import FootballScraper

    async with FootballScraper(league, season, logger) as scraper:
        data = await scraper.scrape()
"""

import asyncio
import random
from datetime import datetime
from typing import Any, Optional

from playwright.async_api import (
    Browser,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from african_football.models.league_model import LeagueConfig
from african_football.models.season_model import SeasonRecord
from african_football.sources.soccerway.parser import (
    AWARDED_INDICATORS,
    SCORE_PATTERN,
    clean_score,
    parse_kickoff,
    parse_round,
)
from african_football.utils.logger import PipelineLogger

PIPELINE_VERSION = "1.0.1"

BASE_URL = "https://ng.soccerway.com"

# ---------------------------------------------------------------------------
# Selectors
#
# Soccerway uses the Flashscore frontend. Its utility class names contain a
# build hash, for example 'wcl-name_jjfMf'. The hash changes at each release.
# Thus, these selectors use only stable attributes:
#   - BEM classes, for example 'event__*'
#   - data-testid attributes
#   - class prefixes without a hash, with [class*=...]
# Keep all selectors in this block. If the site changes, you then change
# only this block.
# ---------------------------------------------------------------------------
STAGE_HEADER = "div.headerLeague__wrapper"
STAGE_TITLE = ".headerLeague__title-text"
MATCH_ROW = "div.event__match"
SHOW_MORE_BUTTON = "[data-testid='wcl-buttonLink']:has-text('Show more matches')"
HALFTIME_SCORE = (
    "[data-testid='wcl-overline-02']:text-is('1st Half')"
    " >> xpath=following-sibling::span[1]"
)

# The kick-off date and time on a match page, for example '15.09.2023 19:30'.
KICKOFF_TIME = ".duelParticipant__startTime"

# Write a progress line after this number of match pages in the halftime step.
HALFTIME_PROGRESS_INTERVAL = 15

# Maximum time (milliseconds) to wait for the halftime score on a match page.
HALFTIME_WAIT_MS = 15000

# Read the sibling elements that follow the stage header at `idx`.
# Return the round markers and the match rows in the sequence of the page.
EXTRACT_STAGE_JS = """
(idx) => {
    const text = (root, sel) => {
        const el = root.querySelector(sel);
        return el ? el.textContent.trim() : null;
    };
    // The main score is the direct text of the element.
    // The penalty shootout score is in a <sup> child, for example 0<sup>(3)</sup>.
    const score = (row, side) => {
        const el = row.querySelector('.event__score--' + side);
        if (!el) return { main: null, pen: null };
        let main = '';
        el.childNodes.forEach(n => {
            if (n.nodeType === Node.TEXT_NODE) main += n.textContent;
        });
        const sup = el.querySelector('sup');
        return {
            main: main.trim() || null,
            pen: sup ? sup.textContent.replace(/[()]/g, '').trim() : null,
        };
    };

    const headers = Array.from(
        document.querySelectorAll('div.headerLeague__wrapper')
    );
    const next = headers[idx + 1];
    const out = [];
    let el = headers[idx].nextElementSibling;

    while (el && el !== next) {
        if (el.classList.contains('event__round')) {
            out.push({ type: 'round', text: el.textContent.trim() });
        } else if (el.classList.contains('event__match')) {
            const home = score(el, 'home');
            const away = score(el, 'away');
            const link = el.querySelector('a.eventRowLink');
            out.push({
                type: 'match',
                id: el.id,
                date: text(el, '[data-testid="wcl-stageTime"] [class*="wcl-dateContent"]'),
                indicator: text(el, '[data-testid="wcl-stageTime"] [class*="wcl-stageContent"]'),
                home_team: text(el, '.event__homeParticipant [class*="wcl-name"]'),
                away_team: text(el, '.event__awayParticipant [class*="wcl-name"]'),
                home_score: home.main,
                away_score: away.main,
                home_pen: home.pen,
                away_pen: away.pen,
                link: link ? link.getAttribute('href') : null,
            });
        }
        el = el.nextElementSibling;
    }
    return out;
}
"""


def parse_match_row(
    row: dict[str, Any],
    round_name: Optional[str],
    round_number: Optional[int],
    stage_name: str,
) -> Optional[dict[str, Any]]:
    """
    Make a match record from a raw row that EXTRACT_STAGE_JS returns.

    This is a pure function. It does not use a browser. Thus, unit tests
    can test it with saved page fixtures.

    The TXT export of file_saver uses these score rules:
        - Regular or awarded match: home_score and away_score contain
          the final score.
        - Penalty shootout: home_score and away_score contain the
          shootout score. full_time_score contains the score before
          the penalties.

    Args:
        row:          The raw match row from EXTRACT_STAGE_JS.
        round_name:   The name of the current round.
        round_number: The number of the current round, or None.
        stage_name:   The name of the current stage.

    Returns:
        A match dictionary. If a necessary field is missing, return None.
    """
    home, away = row.get("home_team"), row.get("away_team")
    home_score = clean_score(row.get("home_score"))
    away_score = clean_score(row.get("away_score"))
    indicator = (row.get("indicator") or "").strip().lower()
    is_awarded = indicator in AWARDED_INDICATORS

    if not home or not away:
        return None
    # A walkover can have no score ('-'). All other matches must have a score.
    if (home_score is None or away_score is None) and not is_awarded:
        return None

    link = row.get("link")
    url = f"{BASE_URL}{link}" if link and not link.startswith("http") else link
    home_pen = clean_score(row.get("home_pen"))
    away_pen = clean_score(row.get("away_pen"))

    match: dict[str, Any] = {
        "stage": stage_name,
        "round": round_name,
        "round_number": round_number,
        "date": (row.get("date") or "").strip(),
        "home_team": home.strip(),
        "away_team": away.strip(),
        "home_score": home_score,
        "away_score": away_score,
        "half_time_score": None,
        "match_url": url,
        "awarded": False,
        "awarded_reason": None,
        "full_time_score": None,
        "penalty_shootout": False,
        "penalty_winner": None,
    }

    if is_awarded:
        match["awarded"] = True
        match["awarded_reason"] = "walkover"
    elif home_pen is not None and away_pen is not None:
        match["full_time_score"] = f"{home_score}-{away_score}"
        match["home_score"] = home_pen
        match["away_score"] = away_pen
        match["penalty_shootout"] = True
        match["penalty_winner"] = "home" if int(home_pen) > int(away_pen) else "away"

    return match


class FootballScraper:
    """
    Scrapes match data for a single league season from Soccerway.

    Handles both single-stage and multi-stage seasons, penalty
    shootouts, and optional halftime score enrichment driven by
    the league configuration. Populates post-scrape metadata fields
    on the SeasonRecord after scraping completes.

    Uses async context manager pattern to guarantee browser cleanup
    even if scraping fails mid-run.

    Attributes:
        league:   League configuration driving scraping behaviour.
        season:   SeasonRecord for the season being scraped.
        logger:   Pipeline logger for progress and error reporting.
        headless: Whether to run browser in headless mode.
        stats:    Scraping statistics accumulated during the run.
    """

    def __init__(
        self,
        league: LeagueConfig,
        season: SeasonRecord,
        logger: PipelineLogger,
        headless: bool = True,
    ) -> None:
        """
        Initialise the FootballScraper.

        Args:
            league:   League configuration for the season being scraped.
            season:   SeasonRecord containing URL and season metadata.
            logger:   Pipeline logger instance.
            headless: Whether to run the browser in headless mode.
                      Set to False during development for visibility.
                      Defaults to True for pipeline use.
        """
        self.league = league
        self.season = season
        self.logger = logger
        self.headless = headless
        self._browser: Browser | None = None
        self.stats: dict[str, Any] = {
            "total_matches": 0,
            "stages": [],
            "ht_scores_found": 0,
            "ht_scores_failed": [],
            "network_errors": 0,
            "missing_data": [],
        }

    async def __aenter__(self) -> "FootballScraper":
        """Start the Playwright browser."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Close the Playwright browser."""
        if self._browser:
            await self._browser.close()
        await self._playwright.stop()

    async def scrape(self) -> dict[str, Any]:
        """
        Scrape all match data for the season.

        Navigates to the season results page, loads all matches,
        extracts stage and match data, optionally enriches with
        halftime scores, validates the data, and populates
        post-scrape metadata on the SeasonRecord.

        Returns:
            A structured dictionary containing league, season,
            match data, and ingestion metadata ready for file_saver.

        Raises:
            RuntimeError: If called outside of async context manager.
            ValueError: If the SeasonRecord has no valid URL.
        """
        if self._browser is None:
            raise RuntimeError(
                "Browser not started. Use 'async with FootballScraper(...)' "
                "to ensure the browser is started before calling scrape()."
            )

        if not self.season.url:
            raise ValueError(
                f"SeasonRecord for {self.season.season} has no URL. "
                "Only COMPLETED seasons can be scraped."
            )

        self.logger.log(f"Scraping {self.season.season} — {self.league.name}")
        self.logger.log(
            f"Halftime scores: "
            f"{'Enabled' if self.league.fetch_halftime else 'Disabled'}"
        )
        self.logger.log(f"Loading: {self.season.url}")

        # Show dates and kick-off times in the local timezone of the league.
        page = await self._browser.new_page(timezone_id=self.league.timezone)

        try:
            await page.goto(self.season.url, timeout=60000)
            await page.wait_for_load_state("networkidle")

            await self._load_all_matches(page)
            stages_data = await self._extract_all_stages(page)

            if self.league.fetch_halftime:
                for stage in stages_data:
                    stage["matches"] = await self._enrich_matches(
                        page, stage["matches"]
                    )
        finally:
            await page.close()

        all_matches = [m for stage in stages_data for m in stage["matches"]]
        self.validate_data(all_matches)

        self.stats["total_matches"] = len(all_matches)
        self.stats["stages"] = [
            {"name": s["stage_name"], "matches": len(s["matches"])} for s in stages_data
        ]

        data = self._build_output(stages_data, all_matches)

        # Populate post-scrape metadata on SeasonRecord
        self.season.scraped_at = data["scraped_at"]
        self.season.records_extracted = len(all_matches)
        self.season.pipeline_version = PIPELINE_VERSION

        return data

    def _build_output(
        self,
        stages_data: list[dict[str, Any]],
        all_matches: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Build the final output dictionary from scraped data.

        Args:
            stages_data: List of stage dictionaries with match data.
            all_matches: Flat list of all matches across all stages.

        Returns:
            A structured output dictionary ready for file_saver.
        """
        return {
            "league": self.league.code,
            "league_name": self.league.name,
            "country": self.league.country,
            "season": self.season.season,
            "start_year": self.season.start_year,
            "end_year": self.season.end_year,
            "champion": self.season.champion,
            "total_matches": len(all_matches),
            "has_halftime_scores": self.league.fetch_halftime,
            "stages": stages_data,
            "scraped_at": datetime.now().isoformat(),
            "pipeline_version": PIPELINE_VERSION,
            "statistics": self.stats,
        }

    async def _load_all_matches(self, page: Page) -> None:
        """
        Click 'Show more matches' until all matches are loaded.

        Args:
            page: The Playwright page loaded at the season results URL.
        """
        clicks = 0
        rows = page.locator(MATCH_ROW)
        while True:
            try:
                btn = page.locator(SHOW_MORE_BUTTON)
                if await btn.count() == 0:
                    break
                before = await rows.count()
                await btn.first.scroll_into_view_if_needed()
                await asyncio.sleep(random.uniform(1, 2))
                await btn.first.click()
                clicks += 1
                await asyncio.sleep(random.uniform(2, 4))
                # Stop if the button stays visible but loads no new matches.
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

    async def _extract_all_stages(self, page: Page) -> list[dict[str, Any]]:
        """
        Extract match data grouped by stage from the results page.

        Finds all stage header elements and extracts matches between
        consecutive headers using JavaScript evaluation to traverse
        sibling DOM elements.

        Args:
            page: The Playwright page with all matches loaded.

        Returns:
            A list of stage dictionaries each containing stage_name,
            total_rounds, total_matches, and matches.
        """
        headers = await page.locator(STAGE_HEADER).all()
        self.logger.log(f"Found {len(headers)} stage(s)")
        stages_data = []

        for idx, header in enumerate(headers):
            try:
                name_elem = header.locator(STAGE_TITLE)
                stage_name = (
                    await name_elem.inner_text()
                    if await name_elem.count() > 0
                    else f"Stage {idx + 1}"
                ).strip()

                elements = await page.evaluate(EXTRACT_STAGE_JS, idx)
                stage_matches = self._build_stage_matches(elements, stage_name)

                if stage_matches:
                    round_numbers: list[int] = [
                        m["round_number"]
                        for m in stage_matches
                        if m.get("round_number") is not None
                    ]
                    stages_data.append(
                        {
                            "stage_name": stage_name,
                            "total_rounds": max(round_numbers) if round_numbers else 0,
                            "total_matches": len(stage_matches),
                            "matches": stage_matches,
                        }
                    )
                    self.logger.log(
                        f"Stage '{stage_name}': {len(stage_matches)} matches",
                        level="SUCCESS",
                    )
                else:
                    self.logger.log(
                        f"Stage '{stage_name}': no matches found",
                        level="WARNING",
                    )

            except Exception as e:
                self.logger.log(f"Error extracting stage {idx}: {e}", level="ERROR")

        return stages_data

    def _build_stage_matches(
        self,
        elements: list[dict[str, Any]],
        stage_name: str,
    ) -> list[dict[str, Any]]:
        """
        Make the match records for one stage from its round and match elements.

        A round element sets the current round. The function parses each
        match element with the current round.

        Args:
            elements:   The elements from EXTRACT_STAGE_JS, in page sequence.
            stage_name: The name of the current stage.

        Returns:
            A list of match dictionaries for this stage.
        """
        matches = []
        current_round_name: Optional[str] = None
        current_round_number: Optional[int] = None

        for element in elements:
            if element["type"] == "round":
                current_round_name = element["text"]
                current_round_number = parse_round(element["text"])
            elif element["type"] == "match":
                match = parse_match_row(
                    element, current_round_name, current_round_number, stage_name
                )
                if match:
                    matches.append(match)
                else:
                    self.logger.log(
                        f"Skipping unparseable match row {element.get('id')}",
                        level="WARNING",
                    )

        return matches

    async def _enrich_matches(
        self,
        page: Page,
        matches: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Enrich match data with halftime scores from individual match pages.

        Attempts to fetch halftime scores for all matches with a URL.
        Retries failed matches up to two additional times before logging
        them as permanently failed.

        Args:
            page:    The Playwright page for navigation.
            matches: List of match dictionaries to enrich.

        Returns:
            The same list with half_time_score populated where available.
        """
        to_enrich = [
            (i, m)
            for i, m in enumerate(matches)
            if m.get("match_url") and not m.get("awarded")
        ]
        self.logger.log(f"Enriching {len(to_enrich)} matches with halftime scores")

        failed = await self._fetch_halftime_scores(page, to_enrich, 1)
        for retry in range(1, 3):
            if not failed:
                break
            await asyncio.sleep(3)
            failed = await self._fetch_halftime_scores(page, failed, retry + 1)

        ht_found = sum(1 for m in matches if m.get("half_time_score"))
        self.stats["ht_scores_found"] += ht_found

        # After all retry passes, find matches that still have no halftime score
        missing_ht = [
            (i, m)
            for i, m in enumerate(matches)
            if m.get("match_url")
            and not m.get("awarded")
            and m.get("half_time_score") is None
        ]

        if missing_ht:
            for idx, m in missing_ht:
                self.stats["ht_scores_failed"].append(
                    {
                        "match_index": idx + 1,
                        "stage": m.get("stage"),
                        "round": m.get("round"),
                        "home_team": m["home_team"],
                        "away_team": m["away_team"],
                        "url": m["match_url"],
                    }
                )

        total = len(matches)
        pct = ht_found / total * 100 if total > 0 else 0
        self.logger.log(
            f"Halftime scores: {ht_found}/{total} ({pct:.1f}%)",
            level="SUCCESS",
        )
        return matches

    async def _fetch_halftime_scores(
        self,
        page: Page,
        matches_list: list[tuple[int, dict[str, Any]]],
        pass_num: int,
    ) -> list[tuple[int, dict[str, Any]]]:
        """
        Fetch halftime scores for a list of matches.

        Args:
            page:         The Playwright page for navigation.
            matches_list: List of (index, match) tuples to process.
            pass_num:     Current pass number for logging context.

        Returns:
            List of (index, match) tuples that failed and need retry.
        """
        failed = []
        total = len(matches_list)
        for count, (idx, m) in enumerate(matches_list, 1):
            try:
                await asyncio.sleep(random.uniform(1, 2))
                ht, kickoff = await self._get_match_details(page, m["match_url"])
                # The results page shows only the date. The match page also
                # shows the kick-off time.
                if kickoff:
                    m["date"] = kickoff
                if ht:
                    m["half_time_score"] = ht
                elif pass_num == 1:
                    failed.append((idx, m))
            except Exception as e:
                if "timeout" in str(e).lower() or "network" in str(e).lower():
                    self.stats["network_errors"] += 1
                failed.append((idx, m))

            # Show progress at each interval and at the last match.
            if count % HALFTIME_PROGRESS_INTERVAL == 0 or count == total:
                self.logger.log(
                    f"Halftime pass {pass_num}: {count}/{total} matches done, "
                    f"{len(failed)} failed"
                )
        return failed

    async def _get_match_details(
        self, page: Page, url: str
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Get the halftime score and the kick-off from one match page.

        Args:
            page: The Playwright page for navigation.
            url:  The URL of the match page.

        Returns:
            A tuple (halftime_score, kickoff). The halftime score has the
            format '1 - 0'. The kick-off has the format 'DD.MM.YYYY HH:MM'.
            If a value is not found, it is None.
        """
        # Do not wait for the full page load. Ads and trackers can keep the
        # page busy for more than 30 seconds. Wait only for the halftime score.
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        ht_loc = page.locator(HALFTIME_SCORE).first
        try:
            await ht_loc.wait_for(timeout=HALFTIME_WAIT_MS)
            ht_text = (await ht_loc.inner_text()).strip()
            ht = ht_text if SCORE_PATTERN.match(ht_text) else None
        except PlaywrightTimeoutError:
            ht = None

        # The page header loads before the halftime block. Thus, do not wait.
        kickoff_loc = page.locator(KICKOFF_TIME).first
        kickoff = None
        if await kickoff_loc.count() > 0:
            kickoff = parse_kickoff(await kickoff_loc.inner_text())
        return ht, kickoff

    def validate_data(self, matches: list[dict[str, Any]]) -> None:
        """
        Validate all matches for required fields and log any issues.

        Checks each match for the presence of required fields and
        records any missing data in self.stats for reporting.

        Args:
            matches: Flat list of all match dictionaries to validate.
        """
        self.logger.log_section("DATA VALIDATION")
        required_fields = [
            "home_team",
            "away_team",
            "home_score",
            "away_score",
            "date",
            "round",
            "stage",
        ]

        for i, m in enumerate(matches, 1):
            issues = [f for f in required_fields if not m.get(f)]
            if issues:
                info = {
                    "match_index": i,
                    "stage": m.get("stage"),
                    "round": m.get("round"),
                    "teams": (
                        f"{m.get('home_team', '?')} vs {m.get('away_team', '?')}"
                    ),
                    "issues": issues,
                }
                self.stats["missing_data"].append(info)
                self.logger.log(
                    f"Match {i}: {info['teams']} — {', '.join(issues)}",
                    level="WARNING",
                )

        if not self.stats["missing_data"]:
            self.logger.log("All matches have complete data", level="SUCCESS")

    def get_statistics_report(self) -> str:
        """
        Generate a human-readable statistics report for this scrape run.

        Returns:
            A formatted string summarising scraping statistics.
        """
        lines = [
            "\n" + "=" * 70,
            "SCRAPING STATISTICS",
            "=" * 70,
            f"League:  {self.league.name} ({self.league.code.upper()})",
            f"Season:  {self.season.season}",
            f"Matches: {self.stats['total_matches']}",
        ]

        if self.stats["stages"]:
            lines.append("\nStages:")
            lines.extend(
                f"  - {s['name']}: {s['matches']} matches" for s in self.stats["stages"]
            )

        if self.league.fetch_halftime:
            total = self.stats["total_matches"]
            found = self.stats["ht_scores_found"]
            pct = found / total * 100 if total > 0 else 0
            lines.append(f"\nHalftime scores: {found}/{total} ({pct:.1f}%)")

        if self.stats["ht_scores_failed"]:
            lines.append("\nMissing halftime scores:")
            for m in self.stats["ht_scores_failed"]:
                lines.append(
                    f"  - {m['home_team']} vs {m['away_team']} "
                    f"({m['round']}) - {m['url']}"
                )

        lines.extend(
            [
                f"Network errors:  {self.stats['network_errors']}",
                f"Missing data:    {len(self.stats['missing_data'])}",
                "=" * 70,
            ]
        )
        return "\n".join(lines)
