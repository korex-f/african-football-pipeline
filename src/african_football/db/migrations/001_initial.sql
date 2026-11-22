-- 001_initial.sql: the first schema of the pipeline database.
--
-- This migration makes the six tables of roadmap step 3:
--   leagues, seasons    the leagues and the seasons that the pipeline collects.
--   collection_runs     one row for each collection of a season (the run log).
--   raw_documents       the data about each stored page. The pages stay on disk.
--   source_matches      one row for each match from one source.
--   season_coverage     the coverage status of each season.
--
-- The constraints repeat the simple rules of SourceMatch. Thus the database
-- stops bad data from all writers, not only from the Python code.
-- The migration runner applies this file in one transaction.

CREATE TABLE leagues (
    league_code text PRIMARY KEY,
    name        text NOT NULL,
    country     text NOT NULL,
    timezone    text NOT NULL
);

CREATE TABLE seasons (
    season_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    league_code text NOT NULL REFERENCES leagues (league_code),
    label       text NOT NULL,
    start_year  int NOT NULL,
    end_year    int NOT NULL,

    UNIQUE (league_code, label),
    CONSTRAINT chk_seasons_year_diff CHECK (
        end_year IN (start_year, start_year + 1)
    )
);

COMMENT ON CONSTRAINT chk_seasons_year_diff ON seasons IS
'Ensure end year is at most one more than start year';

CREATE TABLE collection_runs (
    run_id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    season_id        bigint NOT NULL REFERENCES seasons (season_id),
    source           text NOT NULL,
    pipeline_version text NOT NULL,
    started_at       timestamptz NOT NULL DEFAULT now(),
    finished_at      timestamptz,
    status           text NOT NULL DEFAULT 'running' CHECK (
        status IN ('running', 'succeeded', 'failed')
    ),
    pages_fetched    int CHECK (pages_fetched >= 0),
    matches_parsed   int CHECK (matches_parsed >= 0),
    error            text,

    CONSTRAINT chk_collection_runs_run_status CHECK (
        (status = 'running') = (finished_at IS NULL)
    )
);

COMMENT ON CONSTRAINT chk_collection_runs_run_status ON collection_runs IS
'A run is running when finished_at is null';

CREATE TABLE raw_documents (
    raw_document_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    season_id       bigint NOT NULL REFERENCES seasons (season_id),
    first_run_id    bigint NOT NULL REFERENCES collection_runs (run_id),
    source          text NOT NULL,
    url             text NOT NULL,
    path            text NOT NULL,
    timezone        text NOT NULL,
    sha256          text NOT NULL,
    fetched_at      timestamptz NOT NULL,

    UNIQUE (url, sha256),
    CONSTRAINT chk_raw_documents_sha256_validation CHECK (
        sha256 ~ '^[0-9a-f]{64}$'
    )
);

COMMENT ON CONSTRAINT chk_raw_documents_sha256_validation ON raw_documents IS
'sha256 has to be exactly 64 lowercase hex characters.';

CREATE TABLE source_matches (
    source_match_pk bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    season_id       bigint NOT NULL REFERENCES seasons (season_id),
    last_run_id     bigint NOT NULL REFERENCES collection_runs (run_id),
    source          text NOT NULL,
    source_match_id text NOT NULL,
    page_position   int NOT NULL CHECK (page_position >= 0),
    source_url      text,
    stage           text,
    round_name      text,
    round_number    int CHECK (round_number >= 1),
    match_date      date,
    kickoff_local   time,
    timezone        text NOT NULL,
    home_team_raw   text NOT NULL,
    away_team_raw   text NOT NULL,
    home_goals      smallint CHECK (home_goals >= 0),
    away_goals      smallint CHECK (away_goals >= 0),
    ht_home         smallint CHECK (ht_home >= 0),
    ht_away         smallint CHECK (ht_away >= 0),
    pen_home        smallint CHECK (pen_home >= 0),
    pen_away        smallint CHECK (pen_away >= 0),
    status          text NOT NULL CHECK (
        status IN (
            'played',
            'awarded',
            'abandoned',
            'postponed',
            'cancelled',
            'unknown'
        )
    ),
    raw_documents   text[] NOT NULL DEFAULT '{}',
    first_seen_at   timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),

    UNIQUE (source, source_match_id),
    CONSTRAINT chk_source_matches_teams_differ CHECK (
        home_team_raw <> away_team_raw
    ),
    CONSTRAINT chk_source_matches_ft_score_pair_validation CHECK (
        (home_goals IS NULL) = (away_goals IS NULL)
    ),
    CONSTRAINT chk_source_matches_ht_score_pair_validation CHECK (
        (ht_home IS NULL) = (ht_away IS NULL)
    ),
    CONSTRAINT chk_source_matches_pen_score_pair_validation CHECK (
        (pen_home IS NULL) = (pen_away IS NULL)
    )
);

COMMENT ON CONSTRAINT chk_source_matches_teams_differ ON source_matches IS
'Home team must be different from the Away team.';
COMMENT ON CONSTRAINT chk_source_matches_ft_score_pair_validation ON source_matches IS
'For each full-time goals pair, both values are null or neither is.';

CREATE INDEX source_matches_season_id_page_position_idx ON source_matches (
    season_id, page_position
);

CREATE TABLE season_coverage (
    season_id        bigint PRIMARY KEY REFERENCES seasons (season_id),
    expected_matches int CHECK (expected_matches >= 0),
    found_matches    int NOT NULL CHECK (found_matches >= 0),
    status           text NOT NULL CHECK (
        status IN (
            'verified',
            'complete_single_source',
            'incomplete',
            'failed',
            'unavailable'
        )
    ),
    last_run_id      bigint REFERENCES collection_runs (run_id),
    updated_at       timestamptz NOT NULL DEFAULT now()
);
