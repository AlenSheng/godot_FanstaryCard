CREATE TABLE season_journey_reward_entitlements (
    reward_id uuid PRIMARY KEY,
    player_id uuid NOT NULL,
    season_id varchar(80) NOT NULL,
    reward_level smallint NOT NULL CHECK(reward_level BETWEEN 1 AND 30),
    reward_key varchar(80) NOT NULL,
    config_version varchar(80) NOT NULL,
    config_sha256 char(64) NOT NULL,
    ruleset_id varchar(80) NOT NULL CHECK(ruleset_id='season-v1'),
    stats_version varchar(80) NOT NULL,
    required_experience integer NOT NULL CHECK(required_experience BETWEEN 1 AND 12525),
    experience_at_unlock integer NOT NULL CHECK(experience_at_unlock BETWEEN required_experience AND 12525),
    journey_version_at_unlock bigint NOT NULL CHECK(journey_version_at_unlock>=0),
    reward_kind varchar(24) NOT NULL CHECK(reward_kind IN ('EquipmentFragments','WarriorSoul','ClassSoul','CardPack','Cosmetic')),
    reward_amount integer NOT NULL,
    ownership varchar(24) NOT NULL,
    requires_class_choice boolean NOT NULL,
    cosmetic_id varchar(80),
    -- Card-pack outcomes are fixed with the entitlement, before any claim.
    pack_card_ids jsonb NOT NULL CHECK(jsonb_typeof(pack_card_ids)='array'),
    state varchar(16) NOT NULL DEFAULT 'Pending' CHECK(state IN ('Pending','Claimed')),
    created_at timestamptz NOT NULL,
    claimed_at timestamptz,
    hero_class_choice varchar(20),
    grant_json jsonb,
    response_json jsonb,
    FOREIGN KEY(player_id,season_id) REFERENCES player_season_journeys(player_id,season_id),
    UNIQUE(player_id,season_id,reward_level),
    UNIQUE(reward_id,player_id),
    CHECK(reward_key='journey-level-'||lpad(reward_level::text,2,'0')),
    CHECK((reward_kind='EquipmentFragments' AND reward_amount=10 AND ownership='SeasonalBound') OR
        (reward_kind='WarriorSoul' AND reward_amount=6 AND ownership='PermanentBound') OR
        (reward_kind='ClassSoul' AND reward_amount=2 AND ownership='PermanentBound') OR
        (reward_kind IN ('CardPack','Cosmetic') AND reward_amount=1 AND ownership='PermanentBound')),
    CHECK(requires_class_choice=(reward_kind='ClassSoul')),
    CHECK((reward_level<=20 AND reward_kind<>'Cosmetic' AND cosmetic_id IS NULL) OR
        (reward_level>20 AND reward_kind='Cosmetic' AND cosmetic_id IS NOT NULL)),
    CHECK(jsonb_array_length(pack_card_ids)=CASE WHEN reward_kind='CardPack' THEN 3 ELSE 0 END),
    CHECK((state='Pending' AND claimed_at IS NULL AND hero_class_choice IS NULL AND grant_json IS NULL AND response_json IS NULL) OR
        (state='Claimed' AND claimed_at IS NOT NULL AND grant_json IS NOT NULL AND jsonb_typeof(grant_json)='object'
            AND response_json IS NOT NULL AND jsonb_typeof(response_json)='object'
            AND ((reward_kind='ClassSoul' AND hero_class_choice IN ('Priest','Mage','Guardian') AND hero_class_choice IS NOT NULL)
                OR (reward_kind<>'ClassSoul' AND hero_class_choice IS NULL))))
);
CREATE INDEX ix_season_journey_rewards_owner ON season_journey_reward_entitlements(player_id,season_id,state,reward_level);
