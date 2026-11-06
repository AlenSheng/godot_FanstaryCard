CREATE TABLE player_cosmetics (
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    cosmetic_id varchar(80) NOT NULL,
    kind varchar(20) NOT NULL CHECK(kind IN ('AvatarFrame','CardBack','Title','Collection')),
    name_key varchar(120) NOT NULL,
    description_key varchar(120) NOT NULL,
    source_reward_id uuid NOT NULL,
    acquired_at timestamptz NOT NULL,
    PRIMARY KEY(player_id,cosmetic_id),
    FOREIGN KEY(source_reward_id,player_id) REFERENCES season_journey_reward_entitlements(reward_id,player_id)
);

CREATE TABLE player_cosmetic_profiles (
    player_id uuid PRIMARY KEY REFERENCES players(user_id) ON DELETE CASCADE,
    avatar_frame_id varchar(80),
    card_back_id varchar(80),
    title_id varchar(80),
    version bigint NOT NULL DEFAULT 0 CHECK(version>=0),
    FOREIGN KEY(player_id,avatar_frame_id) REFERENCES player_cosmetics(player_id,cosmetic_id),
    FOREIGN KEY(player_id,card_back_id) REFERENCES player_cosmetics(player_id,cosmetic_id),
    FOREIGN KEY(player_id,title_id) REFERENCES player_cosmetics(player_id,cosmetic_id)
);

CREATE TABLE season_journey_grant_ledger (
    reward_id uuid PRIMARY KEY,
    player_id uuid NOT NULL,
    season_id varchar(80) NOT NULL REFERENCES season_definitions(season_id),
    reward_level smallint NOT NULL CHECK(reward_level BETWEEN 1 AND 30),
    reward_kind varchar(24) NOT NULL CHECK(reward_kind IN ('EquipmentFragments','WarriorSoul','ClassSoul','CardPack','Cosmetic')),
    reward_amount integer NOT NULL CHECK(reward_amount>0),
    actual_card_copies integer NOT NULL CHECK(actual_card_copies=CASE WHEN reward_kind='CardPack' THEN 3 ELSE 0 END),
    grants_json jsonb NOT NULL CHECK(jsonb_typeof(grants_json)='array'),
    balance_after bigint CHECK(balance_after>=0),
    cosmetic_newly_owned boolean NOT NULL,
    created_at timestamptz NOT NULL,
    FOREIGN KEY(reward_id,player_id) REFERENCES season_journey_reward_entitlements(reward_id,player_id),
    UNIQUE(player_id,season_id,reward_level)
);
