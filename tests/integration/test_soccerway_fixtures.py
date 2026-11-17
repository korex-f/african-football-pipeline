"""
test_soccerway_fixtures.py — Regression tests against saved Soccerway pages.

The fixtures in tests/fixtures/soccerway/ are short copies of real
Soccerway pages. These tests run the selectors and the page JavaScript
of the scraper on the fixtures, in a local headless browser.

If Soccerway changes its pages, get new fixtures and run this file again.
The failed tests show which selector does not work.

These tests do not use the network. They need the Playwright Chromium
installation.
"""

import asyncio
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from african_football.scraping.scraper import (
    EXTRACT_STAGE_JS,
    HALFTIME_SCORE,
    SHOW_MORE_BUTTON,
    STAGE_HEADER,
    STAGE_TITLE,
    parse_match_row,
    parse_round,
)

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


def _parse_fixture(fixture: str) -> list[dict]:
    """Extract and parse the stage in a fixture. Use the same steps as the scraper."""

    async def extract(page):
        assert await page.locator(STAGE_HEADER).count() == 1
        stage = (await page.locator(STAGE_TITLE).first.inner_text()).strip()
        return stage, await page.evaluate(EXTRACT_STAGE_JS, 0)

    stage, elements = asyncio.run(_with_page(fixture, extract))
    matches, round_name, round_number = [], None, None
    for el in elements:
        if el["type"] == "round":
            round_name, round_number = el["text"], parse_round(el["text"])
        else:
            match = parse_match_row(el, round_name, round_number, stage)
            assert match is not None, f"row failed to parse: {el}"
            matches.append(match)
    return matches


@pytest.fixture(scope="module")
def league_matches() -> list[dict]:
    return _parse_fixture("league_results.html")


@pytest.fixture(scope="module")
def cup_matches() -> list[dict]:
    return _parse_fixture("cup_results.html")


def test_league_regular_match(league_matches):
    first = league_matches[0]
    assert first["stage"] == "NPFL"
    assert first["round"] == "Round 38"
    assert first["round_number"] == 38
    assert first["date"] == "23.06.2024"
    assert (first["home_team"], first["away_team"]) == ("Akwa United", "Rivers United")
    assert (first["home_score"], first["away_score"]) == ("3", "1")
    assert first["match_url"].startswith("https://ng.soccerway.com/match/")
    assert first["awarded"] is False


def test_league_awarded_match(league_matches):
    awarded = [m for m in league_matches if m["awarded"]]
    assert len(awarded) == 1
    assert awarded[0]["round_number"] == 35
    assert (awarded[0]["home_score"], awarded[0]["away_score"]) == ("3", "0")


def test_cup_penalty_shootout(cup_matches):
    final = next(m for m in cup_matches if m["round"] == "Final")
    assert final["penalty_shootout"] is True
    assert final["full_time_score"] == "0-0"
    assert (final["home_score"], final["away_score"]) == ("3", "4")
    assert final["penalty_winner"] == "away"


def test_cup_walkover_without_score(cup_matches):
    wo = next(m for m in cup_matches if m["round"] == "1/16-finals")
    assert wo["awarded"] is True
    assert wo["home_score"] is None and wo["away_score"] is None


def test_show_more_button_is_found():
    async def count(page):
        return await page.locator(SHOW_MORE_BUTTON).count()

    assert asyncio.run(_with_page("league_results.html", count)) == 1


def test_halftime_score_selector():
    async def read(page):
        return (await page.locator(HALFTIME_SCORE).first.inner_text()).strip()

    assert asyncio.run(_with_page("match_page.html", read)) == "2 - 1"
