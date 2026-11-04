CREATE TABLE player_season_journeys (
    player_id uuid NOT NULL REFERENCES players(user_id),
    season_id varchar(80) NOT NULL REFERENCES season_definitions(season_id),
    config_version varchar(80) NOT NULL,
    experience integer NOT NULL DEFAULT 0 CHECK (experience BETWEEN 0 AND 12525),
    version bigint NOT NULL DEFAULT 0 CHECK (version >= 0),
    PRIMARY KEY (player_id,season_id)
);

CREATE TABLE season_journey_sources (
    source_id uuid PRIMARY KEY,
    player_id uuid NOT NULL,
    season_id varchar(80) NOT NULL,
    room_id uuid NOT NULL,
    match_id uuid NOT NULL REFERENCES matches(match_id),
    settlement_id uuid NOT NULL REFERENCES match_settlements(settlement_id),
    source_key varchar(64) NOT NULL,
    completion_kind varchar(16) NOT NULL CHECK (completion_kind IN ('Outer','Middle','Elite','Boss','Extracted')),
    battle_id uuid,
    config_version varchar(80) NOT NULL,
    difficulty_id varchar(3) NOT NULL CHECK (difficulty_id IN ('D0','D1','D2','D3','D4','D5')),
    occurred_at timestamptz NOT NULL,
    base_experience integer NOT NULL CHECK (base_experience BETWEEN 0 AND 80),
    catch_up_experience integer NOT NULL CHECK (catch_up_experience BETWEEN 0 AND base_experience),
    credited_experience integer NOT NULL CHECK (credited_experience=base_experience+catch_up_experience),
    experience_before integer NOT NULL CHECK (experience_before BETWEEN 0 AND 12525),
    experience_after integer NOT NULL CHECK (experience_after=experience_before+credited_experience AND experience_after<=12525),
    recorded_at timestamptz NOT NULL,
    source_revision bigint NOT NULL CHECK (source_revision>=0),
    FOREIGN KEY (player_id,season_id) REFERENCES player_season_journeys(player_id,season_id),
    UNIQUE (player_id,room_id,source_key),
    CHECK ((completion_kind='Extracted' AND source_key='extraction' AND battle_id IS NULL)
        OR (completion_kind<>'Extracted' AND source_key LIKE 'cell:%' AND battle_id IS NOT NULL))
);

CREATE TABLE player_season_weekly_contracts (
    player_id uuid NOT NULL,
    season_id varchar(80) NOT NULL,
    week_number integer NOT NULL CHECK (week_number BETWEEN 1 AND 9),
    contract_id varchar(80) NOT NULL,
    completion_kind varchar(16) NOT NULL CHECK (completion_kind IN ('Extracted','Elite','Boss')),
    target integer NOT NULL CHECK (target BETWEEN 1 AND 100),
    experience_reward integer NOT NULL CHECK (experience_reward=300),
    progress integer NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND target),
    credited_experience integer NOT NULL DEFAULT 0 CHECK (credited_experience BETWEEN 0 AND experience_reward),
    opens_at timestamptz NOT NULL,
    completed_at timestamptz,
    PRIMARY KEY (player_id,season_id,week_number,contract_id),
    UNIQUE (player_id,season_id,week_number,completion_kind),
    FOREIGN KEY (player_id,season_id) REFERENCES player_season_journeys(player_id,season_id),
    CHECK ((progress=target AND completed_at IS NOT NULL) OR
        (progress<target AND completed_at IS NULL AND credited_experience=0))
);

CREATE TABLE season_weekly_contract_events (
    source_id uuid PRIMARY KEY REFERENCES season_journey_sources(source_id),
    player_id uuid NOT NULL,
    season_id varchar(80) NOT NULL,
    week_number integer NOT NULL,
    contract_id varchar(80) NOT NULL,
    progress_after integer NOT NULL CHECK (progress_after>0),
    FOREIGN KEY (player_id,season_id,week_number,contract_id)
        REFERENCES player_season_weekly_contracts(player_id,season_id,week_number,contract_id)
);

CREATE TABLE season_journey_ledger (
    sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id uuid NOT NULL,
    season_id varchar(80) NOT NULL,
    amount integer NOT NULL CHECK (amount BETWEEN 1 AND 300),
    balance_after integer NOT NULL CHECK (balance_after BETWEEN amount AND 12525),
    source_id uuid REFERENCES season_journey_sources(source_id),
    contract_week integer,
    contract_id varchar(80),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (player_id,season_id) REFERENCES player_season_journeys(player_id,season_id),
    FOREIGN KEY (player_id,season_id,contract_week,contract_id)
        REFERENCES player_season_weekly_contracts(player_id,season_id,week_number,contract_id),
    CHECK ((source_id IS NOT NULL AND contract_week IS NULL AND contract_id IS NULL) OR
        (source_id IS NULL AND contract_week IS NOT NULL AND contract_id IS NOT NULL))
);
CREATE UNIQUE INDEX season_journey_one_source_credit ON season_journey_ledger(source_id) WHERE source_id IS NOT NULL;
CREATE UNIQUE INDEX season_journey_one_contract_credit ON season_journey_ledger(player_id,season_id,contract_week,contract_id) WHERE source_id IS NULL;
CREATE INDEX season_journey_source_scope ON season_journey_sources(player_id,season_id,occurred_at);
