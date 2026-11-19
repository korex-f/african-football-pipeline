"""
test_soccerway_parser_parity.py — Compare the Python parser with the JavaScript parser.

The old scraper reads the results page with EXTRACT_STAGE_JS in the
browser. The new parser reads the same page with BeautifulSoup. These
tests run the two parsers on the same fixtures. The output must be
the same.

When the old scraper is removed, remove this file too.

These tests need the Playwright Chromium installation.
"""

import asyncio
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from african_football.scraping.scraper import (
    EXTRACT_STAGE_JS,
    STAGE_HEADER,
    STAGE_TITLE,
)
from african_football.sources.soccerway.parser import extract_stages

FIXTURES = Path(__file__).parent.parent / "fixtures" / "soccerway"


async def _javascript_stages(html: str) -> list[tuple[str, list[dict]]]:
    """Read all stages with the old scraper method: Chromium and EXTRACT_STAGE_JS."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(html)
            stages = []
            headers = await page.locator(STAGE_HEADER).all()
            for idx, header in enumerate(headers):
                name = (await header.locator(STAGE_TITLE).inner_text()).strip()
                stages.append((name, await page.evaluate(EXTRACT_STAGE_JS, idx)))
            return stages
        finally:
            await browser.close()


@pytest.mark.parametrize("fixture", ["league_results.html", "cup_results.html"])
def test_python_parser_gives_same_output_as_javascript(fixture):
    html = (FIXTURES / fixture).read_text()

    expected = asyncio.run(_javascript_stages(html))
    actual = extract_stages(html)

    # Compare the rows one by one first. If a row is different, the
    # failure message then shows only that row.
    assert len(actual) == len(expected)
    for (py_name, py_rows), (js_name, js_rows) in zip(actual, expected):
        assert py_name == js_name
        assert len(py_rows) == len(js_rows)
        for py_row, js_row in zip(py_rows, js_rows):
            assert py_row == js_row
    assert actual == expected
