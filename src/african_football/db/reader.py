"""
reader.py: read the matches of a season from the pipeline database.

The exports use this module (roadmap step 3, part 3). Thus the database is
the single source of truth: the JSON and TXT files show what the database
has, not what the scraper has in memory.

read_season_matches() gives the matches of the latest succeeded run of a
season and a source, in the sequence of the results page (page_position).
The matches that this run did not find stay in the database
(decision 18), but they are not in the result.

Typical usage:
    with psycopg.connect(url, autocommit=True) as conn:
        matches = read_season_matches(conn, "gh_pl", "2023/2024", "soccerway")
"""

import psycopg

from african_football.models.source_match import MatchStatus, SourceMatch
from african_football.models.source_table import SourceTableRow

# The latest succeeded run of the season and the source. Only its matches
# have last_run_id equal to its run_id.
_READ_MATCHES = """
    SELECT m.source, m.source_match_id, m.source_url, m.raw_documents,
           s.league_code, s.label, m.stage, m.round_name, m.round_number,
           m.match_date, m.kickoff_local, m.timezone,
           m.home_team_raw, m.away_team_raw,
           m.home_goals, m.away_goals, m.ht_home, m.ht_away,
           m.pen_home, m.pen_away, m.status
    FROM source_matches m
    JOIN seasons s USING (season_id)
    WHERE s.league_code = %(league_code)s
      AND s.label = %(season)s
      AND m.source = %(source)s
      AND m.last_run_id = (
          SELECT max(r.run_id) FROM collection_runs r
          WHERE r.season_id = s.season_id
            AND r.source = %(source)s
            AND r.status = 'succeeded'
      )
    ORDER BY m.page_position, m.source_match_id
"""


def read_season_matches(
    conn: psycopg.Connection, league_code: str, season: str, source: str
) -> list[SourceMatch]:
    """Give the matches of the latest succeeded run of a season and a source.

    The matches are in the sequence of the results page. If the season has
    no succeeded run, the list is empty.

    Each row becomes a SourceMatch again, thus Pydantic checks it again. A
    row that is not a valid SourceMatch (for example after a manual change
    in psql) causes a pydantic.ValidationError. It is not exported.
    """
    rows = conn.execute(
        _READ_MATCHES,
        {"league_code": league_code, "season": season, "source": source},
    ).fetchall()
    return [_to_source_match(row) for row in rows]


def _to_source_match(row: tuple) -> SourceMatch:
    """Make a SourceMatch from one row of _READ_MATCHES."""
    (
        source,
        source_match_id,
        source_url,
        raw_documents,
        league_code,
        season,
        stage,
        round_name,
        round_number,
        match_date,
        kickoff_local,
        timezone,
        home_team_raw,
        away_team_raw,
        home_goals,
        away_goals,
        ht_home,
        ht_away,
        pen_home,
        pen_away,
        status,
    ) = row
    return SourceMatch(
        source=source,
        source_match_id=source_match_id,
        source_url=source_url,
        # A PostgreSQL array becomes a list. SourceMatch keeps a tuple.
        raw_documents=tuple(raw_documents),
        league_code=league_code,
        season=season,
        stage=stage,
        round_name=round_name,
        round_number=round_number,
        match_date=match_date,
        kickoff_local=kickoff_local,
        timezone=timezone,
        home_team_raw=home_team_raw,
        away_team_raw=away_team_raw,
        home_goals=home_goals,
        away_goals=away_goals,
        ht_home=ht_home,
        ht_away=ht_away,
        pen_home=pen_home,
        pen_away=pen_away,
        # SourceMatch is strict: it accepts only a MatchStatus, not a str.
        status=MatchStatus(status),
    )


_READ_TABLES = """
    SELECT t.source, s.league_code, s.label, t.stage, t.row_number,
           t.position, t.team_raw, t.played, t.won, t.drawn, t.lost,
           t.goals_for, t.goals_against, t.points, t.note
    FROM source_tables t
    JOIN seasons s USING (season_id)
    WHERE s.league_code = %(league_code)s
      AND s.label = %(season)s
      AND t.source = %(source)s
    ORDER BY t.source_table_pk
"""


def read_season_tables(
    conn: psycopg.Connection, league_code: str, season: str, source: str
) -> list[SourceTableRow]:
    """Give the final table rows of a season and a source.

    The rows are in the sequence of the page (the sequence of the INSERT).
    Each row becomes a SourceTableRow again, thus Pydantic checks it again.
    """
    rows = conn.execute(
        _READ_TABLES,
        {"league_code": league_code, "season": season, "source": source},
    ).fetchall()
    fields = (
        "source league_code season stage row_number position team_raw played "
        "won drawn lost goals_for goals_against points note"
    ).split()
    return [SourceTableRow(**dict(zip(fields, row))) for row in rows]
