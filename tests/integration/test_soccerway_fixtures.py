"""
test_soccerway_fixtures.py — Test the browser selectors on saved Soccerway pages.

The fixtures in tests/fixtures/soccerway/ are short copies of real
Soccerway pages. The fetch step of the adapter uses two selectors in
the browser: the 'Show more matches' button and the halftime score.
These tests run the two selectors on the fixtures in a local headless
browser. The parser tests (tests/unit/test_soccerway_parser.py) test
the other selectors without a browser.

If Soccerway changes its pages, get new fixtures and run this file again.

These tests do not use the network. They need the Playwright Chromium
installation.
"""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

from african_football.sources.soccerway.adapter import HALFTIME_SCORE, SHOW_MORE_BUTTON

FIXTURES = Path(__file__).parent.parent / "fixtures" / "soccerway"


async def _with_page(fixture: str, fn):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content((FIXTURES / fixture).read_text())
            return await fn(page)
        finally:
            await browser.close()


def test_show_more_button_is_found():
    async def count(page):
        return await page.locator(SHOW_MORE_BUTTON).count()

    assert asyncio.run(_with_page("league_results.html", count)) == 1


def test_halftime_score_selector():
    async def read(page):
        return (await page.locator(HALFTIME_SCORE).first.inner_text()).strip()

    assert asyncio.run(_with_page("match_page.html", read)) == "2 - 1"
