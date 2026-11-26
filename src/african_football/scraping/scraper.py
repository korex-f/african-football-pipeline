"""
scraper.py — Collect one league season from one source.

FootballScraper is the entry point that main.py and the Airflow tasks use.
Since version 1.1.0, it does not read the pages itself. It uses these parts:

    1. adapter.fetch:          gets the pages into the raw store.
    2. adapter.parse:          makes SourceMatch records from the stored pages.
       adapter.parse_tables:   (RSSSF only) gives the rows of the final tables.
    3. RunRecorder.load:       writes the run, the pages, the matches and the
                               tables to the pipeline database (db/loader.py).
    4. read_season_matches:    reads the matches of the run back from the
                               database (db/reader.py).
    5. The legacy exporter:    makes the match dictionaries of the JSON files
                               from the matches of step 4.

Since roadmap step 3, part 3, the database is the single source of truth:
the exports show what the database has. Thus the scraper needs a database
URL.

The source is 'soccerway' (the default) or 'rsssf' (roadmap step 4, part
4). The Soccerway adapter uses a browser; the RSSSF adapter does not. The
output has the same format for both sources. The roadmap step 6 (Source
Manager) will replace this class.

Typical usage:
    from african_football.scraping.scraper import FootballScraper

    async with FootballScraper(league, season, logger) as scraper:
        data = await scraper.scrape()
"""

from contextlib import AsyncExitStack
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import psycopg

from african_football.db.loader import LoadSummary, RunRecorder
from african_football.db.reader import read_season_matches
from african_football.exports.legacy import to_legacy_stages
from african_football.models.league_model import LeagueConfig
from african_football.models.season_model import SeasonRecord
from african_football.models.source_table import SourceTableRow
from african_football.sources.base import SourceAdapter
from african_football.sources.raw_store import RawStore
from african_football.sources.rsssf.adapter import RsssfAdapter
from african_football.sources.soccerway.adapter import SoccerwayAdapter
from african_football.utils.logger import PipelineLogger

PIPELINE_VERSION = "1.2.0"

# The default folder of the raw store, relative to the working directory.
DEFAULT_RAW_ROOT = Path("data/sources")

# The sources that FootballScraper can use. The first is the default.
SOURCES = ("soccerway", "rsssf")


class FootballScraper:
    """
    Collect the match data of one league season from one source.

    Use the class as an async context manager. For Soccerway, the context
    manager starts the browser of the adapter and makes sure that it stops.

    Attributes:
        league:   The league configuration.
        season:   The season. scrape() adds the post-scrape metadata.
        logger:   The pipeline logger.
        headless: Run the browser without a window (Soccerway only).
        source:   'soccerway' or 'rsssf'.
        raw_root: The root folder of the raw store.
        database_url: The URL of the pipeline database. It is necessary.
                  The type is Optional because callers give
                  os.environ.get("DATABASE_URL"). With None, __init__
                  raises ValueError.
        stats:    The statistics of the last scrape.
        load_summary: What the last scrape wrote to the database, or None.
    """

    def __init__(
        self,
        league: LeagueConfig,
        season: SeasonRecord,
        logger: PipelineLogger,
        headless: bool = True,
        raw_root: Path = DEFAULT_RAW_ROOT,
        database_url: Optional[str] = None,
        source: str = SOURCES[0],
    ) -> None:
        if source not in SOURCES:
            raise ValueError(f"Unknown source {source!r}; use one of {SOURCES}")
        self.source = source
        self.league = league
        self.season = season
        self.logger = logger
        self.headless = headless
        self.raw_root = Path(raw_root)
        if not database_url:
            raise ValueError(
                "FootballScraper needs the pipeline database. Set DATABASE_URL, "
                "for example with 'uv run --env-file .env ...'."
            )
        self.database_url: str = database_url
        self.load_summary: Optional[LoadSummary] = None
        self._stack: Optional[AsyncExitStack] = None
        self._adapter: Optional[SourceAdapter] = None
        self.stats: dict[str, Any] = {
            "total_matches": 0,
            "stages": [],
            "ht_scores_found": 0,
            "ht_scores_failed": [],
            "network_errors": 0,
            "missing_data": [],
        }

    @property
    def halftime(self) -> bool:
        """True if the run collects halftime scores. RSSSF pages have none."""
        return self.league.fetch_halftime and self.source == "soccerway"

    async def __aenter__(self) -> "FootballScraper":
        """Make the adapter. For Soccerway, start its browser."""
        self._stack = AsyncExitStack()
        if self.source == "rsssf":
            self._adapter = RsssfAdapter(self.logger)
        else:
            self._adapter = await self._stack.enter_async_context(
                SoccerwayAdapter(self.logger, self.headless)
            )
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Stop the browser of the adapter, if it has one."""
        if self._stack is not None:
            await self._stack.aclose()

    async def scrape(self) -> dict[str, Any]:
        """
        Scrape all match data of the season.

        Returns:
            The output dictionary for file_saver: league, season, stages
            with matches, and ingestion metadata.

        Raises:
            RuntimeError: The scraper is not in an `async with` block.
            ValueError: The season has no URL.
        """
        if self._adapter is None:
            raise RuntimeError(
                "Browser not started. Use 'async with FootballScraper(...)' "
                "to ensure the browser is started before calling scrape()."
            )
        if not self.season.url:
            raise ValueError(
                f"SeasonRecord for {self.season.season} has no URL. "
                "Only COMPLETED seasons can be scraped."
            )

        source = self._adapter

        self.logger.log(f"Scraping {self.season.season} — {self.league.name}")
        self.logger.log(f"Source: {source.name}")
        self.logger.log(
            f"Halftime scores: {'Enabled' if self.halftime else 'Disabled'}"
        )

        store = RawStore(
            self.raw_root, source.name, self.league.code, self.season.season
        )

        # autocommit=True: RunRecorder needs it (see db/loader.py).
        with psycopg.connect(self.database_url, autocommit=True) as conn:
            recorder = RunRecorder.start(
                conn, self.league, self.season, source.name, PIPELINE_VERSION
            )

            # BaseException, not Exception: the run must also show 'failed'
            # if a person stops it (Ctrl+C) or Airflow cancels the task.
            try:
                documents = await source.fetch(self.league, self.season, store)
                parsed = source.parse(self.league, self.season, documents, store)
                tables: list[SourceTableRow] = []
                if isinstance(source, RsssfAdapter):
                    # The final tables (decision 23): only RSSSF has them.
                    tables = source.parse_tables(
                        self.league, self.season, documents, store
                    )
                self.load_summary = recorder.load(documents, parsed, tables)
            except BaseException as error:
                self._record_failure(recorder, error)
                raise
            self._log_load_summary(self.load_summary)

            # The exports use the matches from the database, not the parsed
            # matches in memory. The run is 'succeeded' at this point: an
            # error here is an export error, not a collection error.
            source_matches = read_season_matches(
                conn, self.league.code, self.season.season, source.name
            )

        stages_data = to_legacy_stages(source_matches)

        self.logger.log(f"Found {len(stages_data)} stage(s)")
        for stage in stages_data:
            self.logger.log(
                f"Stage '{stage['stage_name']}': {stage['total_matches']} matches",
                level="SUCCESS",
            )

        all_matches = [m for stage in stages_data for m in stage["matches"]]
        # Only the Soccerway adapter counts its network errors.
        self.stats["network_errors"] = getattr(source, "network_errors", 0)
        if self.halftime:
            self._halftime_statistics(stages_data, len(all_matches))

        self.validate_data(all_matches)
        self.stats["total_matches"] = len(all_matches)
        self.stats["stages"] = [
            {"name": s["stage_name"], "matches": len(s["matches"])} for s in stages_data
        ]

        data = self._build_output(stages_data, all_matches)

        # Add the post-scrape metadata to the SeasonRecord.
        self.season.scraped_at = data["scraped_at"]
        self.season.records_extracted = len(all_matches)
        self.season.pipeline_version = PIPELINE_VERSION

        return data

    def _log_load_summary(self, summary: LoadSummary) -> None:
        """Write what the run wrote to the database to the log."""
        self.logger.log(
            f"Database: {summary.matches_parsed} matches "
            f"({summary.matches_new} new, {summary.matches_changed} changed), "
            f"{summary.documents_new} new pages, "
            f"{summary.pages_fetched} pages fetched in this run",
            level="SUCCESS",
        )
        self.logger.log(
            f"Coverage: {summary.coverage_status} "
            f"({summary.matches_parsed} matches, {summary.expected_matches} expected)",
            level="SUCCESS"
            if summary.coverage_status in ("complete_single_source", "verified")
            else "WARNING",
        )
        if summary.matches_not_seen:
            self.logger.log(
                f"Database: {summary.matches_not_seen} matches of this season are "
                "in the database, but the source does not show them now. "
                "They stay in the database.",
                level="WARNING",
            )

    def _record_failure(self, recorder: RunRecorder, error: BaseException) -> None:
        """Mark the run 'failed'. Do not hide the first error.

        If the database also fails, log this second error. Then the caller
        raises the first error, which is the cause of the failure.
        """
        try:
            recorder.fail(error)
        except psycopg.Error as db_error:
            self.logger.log(
                f"Could not mark run {recorder.run_id} as failed: {db_error}",
                level="ERROR",
            )

    def _halftime_statistics(
        self, stages_data: list[dict[str, Any]], total: int
    ) -> None:
        """Count the halftime scores. Record the matches that have none."""
        found = 0
        for stage in stages_data:
            for idx, m in enumerate(stage["matches"]):
                if m.get("half_time_score"):
                    found += 1
                elif m.get("match_url") and not m.get("awarded"):
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
        self.stats["ht_scores_found"] = found
        pct = found / total * 100 if total > 0 else 0
        self.logger.log(
            f"Halftime scores: {found}/{total} ({pct:.1f}%)", level="SUCCESS"
        )

    def _build_output(
        self,
        stages_data: list[dict[str, Any]],
        all_matches: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Make the output dictionary for file_saver."""
        return {
            "league": self.league.code,
            "league_name": self.league.name,
            "country": self.league.country,
            "season": self.season.season,
            "start_year": self.season.start_year,
            "end_year": self.season.end_year,
            "champion": self.season.champion,
            "total_matches": len(all_matches),
            "has_halftime_scores": self.halftime,
            "source": self.source,
            "stages": stages_data,
            "scraped_at": datetime.now().isoformat(),
            "pipeline_version": PIPELINE_VERSION,
            "statistics": self.stats,
        }

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

        if self.halftime:
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
