-- 002_source_tables.sql: the final tables of the seasons, from each source.
--
-- A final table is a second record of a season. The number of matches and
-- the goals of the table must agree with the matches (decision 7 and
-- decision 23). One row of this table is one row of a final table, the
-- same as SourceTableRow in models/source_table.py.
--
-- The loader replaces the table of a season and a source when a run has
-- table rows. A run without table rows does not change the stored table.

CREATE TABLE source_tables (
    source_table_pk bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    season_id       bigint NOT NULL REFERENCES seasons (season_id),
    run_id          bigint NOT NULL REFERENCES collection_runs (run_id),
    source          text NOT NULL,
    stage           text NOT NULL,
    row_number      smallint NOT NULL CHECK (row_number >= 1),
    position        smallint NOT NULL CHECK (position >= 1),
    team_raw        text NOT NULL,
    played          smallint NOT NULL CHECK (played >= 0),
    won             smallint NOT NULL CHECK (won >= 0),
    drawn           smallint NOT NULL CHECK (drawn >= 0),
    lost            smallint NOT NULL CHECK (lost >= 0),
    goals_for       smallint NOT NULL CHECK (goals_for >= 0),
    goals_against   smallint NOT NULL CHECK (goals_against >= 0),
    points          smallint NOT NULL,
    note            text,

    UNIQUE (season_id, source, stage, row_number),
    CONSTRAINT chk_source_tables_results_add_up CHECK (
        won + drawn + lost = played
    )
);

COMMENT ON CONSTRAINT chk_source_tables_results_add_up ON source_tables IS
'Won, drawn and lost matches together are the played matches.';

CREATE INDEX source_tables_run_id_idx ON source_tables (run_id);
