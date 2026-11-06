CREATE TABLE season_difficulty_completions (
    match_id uuid NOT NULL,
    player_id uuid NOT NULL,
    settlement_id uuid NOT NULL UNIQUE REFERENCES match_settlements(settlement_id),
    season_id varchar(80) NOT NULL,
    difficulty_id varchar(2) NOT NULL CHECK (difficulty_id IN ('D0','D1','D2','D3','D4','D5')),
    ruleset_id varchar(80) NOT NULL,
    config_version varchar(80) NOT NULL,
    stats_version varchar(80) NOT NULL,
    elite_cleared boolean NOT NULL,
    boss_cleared boolean NOT NULL,
    completed_at timestamptz NOT NULL,
    PRIMARY KEY (match_id, player_id),
    FOREIGN KEY (match_id,player_id) REFERENCES match_players(match_id,player_id),
    FOREIGN KEY (player_id,season_id) REFERENCES player_season_state(player_id,season_id) ON DELETE CASCADE
);
CREATE INDEX ix_season_difficulty_completions_player ON season_difficulty_completions(player_id,season_id,difficulty_id);
