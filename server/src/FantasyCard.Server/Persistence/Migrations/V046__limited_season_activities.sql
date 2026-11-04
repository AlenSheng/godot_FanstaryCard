CREATE TABLE season_activity_events (
    season_id varchar(80) NOT NULL REFERENCES season_definitions(season_id),
    event_id varchar(80) NOT NULL,
    config_version varchar(80) NOT NULL,
    config_sha256 char(64) NOT NULL,
    ruleset_id varchar(80) NOT NULL,
    stats_version varchar(80) NOT NULL,
    activity_rule varchar(80) NOT NULL CHECK(activity_rule='season-limited-activity-v1'),
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL CHECK(ends_at>starts_at),
    token_cap integer NOT NULL CHECK(token_cap=12),
    completion_tokens integer NOT NULL CHECK(completion_tokens=4),
    exchange_json jsonb NOT NULL CHECK(jsonb_typeof(exchange_json)='array'),
    PRIMARY KEY(season_id,event_id)
);

CREATE TABLE player_season_activity_accounts (
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    season_id varchar(80) NOT NULL,
    event_id varchar(80) NOT NULL,
    earned integer NOT NULL DEFAULT 0 CHECK(earned BETWEEN 0 AND 12),
    spent integer NOT NULL DEFAULT 0 CHECK(spent>=0 AND spent<=earned),
    version bigint NOT NULL DEFAULT 0 CHECK(version>=0),
    PRIMARY KEY(player_id,season_id,event_id),
    FOREIGN KEY(season_id,event_id) REFERENCES season_activity_events(season_id,event_id)
);

CREATE TABLE season_activity_completions (
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    match_id uuid NOT NULL REFERENCES matches(match_id),
    settlement_id uuid NOT NULL REFERENCES match_settlements(settlement_id),
    season_id varchar(80) NOT NULL,
    event_id varchar(80) NOT NULL,
    difficulty_id varchar(20) NOT NULL,
    config_version varchar(80) NOT NULL,
    occurred_at timestamptz NOT NULL,
    credited_tokens integer NOT NULL CHECK(credited_tokens BETWEEN 0 AND 4),
    source_room_id uuid NOT NULL,
    source_revision bigint NOT NULL,
    PRIMARY KEY(player_id,match_id),
    FOREIGN KEY(player_id,season_id,event_id) REFERENCES player_season_activity_accounts(player_id,season_id,event_id)
);

CREATE TABLE season_activity_redemptions (
    reward_id uuid PRIMARY KEY,
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    season_id varchar(80) NOT NULL,
    event_id varchar(80) NOT NULL,
    config_version varchar(80) NOT NULL,
    rule_id varchar(80) NOT NULL,
    quantity integer NOT NULL CHECK(quantity BETWEEN 1 AND 4),
    token_cost integer NOT NULL CHECK(token_cost BETWEEN 3 AND 12),
    reward_kind varchar(40) NOT NULL CHECK(reward_kind IN ('bound_fragments','bound_warrior_soul','bound_class_soul','potion')),
    reward_amount integer NOT NULL CHECK(reward_amount>0),
    hero_class varchar(20),
    state varchar(20) NOT NULL CHECK(state IN ('Pending','Claimed')),
    created_at timestamptz NOT NULL,
    claimed_at timestamptz,
    claim_json jsonb,
    FOREIGN KEY(player_id,season_id,event_id) REFERENCES player_season_activity_accounts(player_id,season_id,event_id),
    CHECK((reward_kind='bound_class_soul' AND hero_class IS NOT NULL AND hero_class IN ('Priest','Mage','Guardian')) OR (reward_kind<>'bound_class_soul' AND hero_class IS NULL)),
    CHECK((state='Pending' AND claimed_at IS NULL AND claim_json IS NULL) OR (state='Claimed' AND claimed_at IS NOT NULL AND claim_json IS NOT NULL))
);
CREATE INDEX ix_season_activity_redemptions_owner ON season_activity_redemptions(player_id,season_id,event_id,created_at,reward_id);

CREATE TABLE season_activity_action_receipts (
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    action_kind varchar(20) NOT NULL CHECK(action_kind IN ('exchange','claim')),
    request_id varchar(80) NOT NULL,
    request_hash char(64) NOT NULL,
    response_json jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    PRIMARY KEY(player_id,action_kind,request_id)
);

CREATE TABLE season_activity_token_ledger (
    ledger_sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id uuid NOT NULL,
    season_id varchar(80) NOT NULL,
    event_id varchar(80) NOT NULL,
    delta integer NOT NULL CHECK(delta<>0),
    balance_after integer NOT NULL CHECK(balance_after BETWEEN 0 AND 12),
    reason varchar(40) NOT NULL CHECK(reason IN ('completion','exchange')),
    source_id uuid NOT NULL,
    created_at timestamptz NOT NULL,
    UNIQUE(player_id,season_id,event_id,reason,source_id),
    FOREIGN KEY(player_id,season_id,event_id) REFERENCES player_season_activity_accounts(player_id,season_id,event_id)
);

CREATE TABLE season_activity_reward_ledger (
    reward_id uuid PRIMARY KEY REFERENCES season_activity_redemptions(reward_id),
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    season_id varchar(80) NOT NULL,
    event_id varchar(80) NOT NULL,
    reward_kind varchar(40) NOT NULL,
    reward_amount integer NOT NULL CHECK(reward_amount>0),
    balance_after bigint NOT NULL CHECK(balance_after>=0),
    created_at timestamptz NOT NULL,
    FOREIGN KEY(season_id,event_id) REFERENCES season_activity_events(season_id,event_id)
);
