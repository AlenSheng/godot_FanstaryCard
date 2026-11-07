CREATE TABLE learned_season_recipes (
    recipe_id uuid PRIMARY KEY,
    player_id uuid NOT NULL,
    season_id varchar(80) NOT NULL,
    quality varchar(16) NOT NULL CHECK (quality IN ('Purple','Orange')),
    slot varchar(16) NOT NULL CHECK (slot IN ('Head','Chest','Hands','Legs','Feet')),
    element varchar(16) NOT NULL CHECK (element IN ('Fire','Wood','Earth','Metal','Water')),
    effect_affix varchar(16) CHECK (effect_affix IS NULL OR effect_affix IN ('Piercing','Bulwark','Vitality')),
    secondary_trait varchar(24) NOT NULL CHECK (secondary_trait IN ('DrawInterval','ForcedEscape')),
    stats_version varchar(80) NOT NULL,
    source_item_id uuid NOT NULL,
    learned_at timestamptz NOT NULL,
    CHECK (quality='Purple' OR effect_affix IS NOT NULL),
    CHECK (secondary_trait<>'ForcedEscape' OR slot='Feet'),
    FOREIGN KEY (player_id,season_id) REFERENCES player_season_state(player_id,season_id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX uq_season_recipe_template ON learned_season_recipes
    (player_id,season_id,quality,slot,element,COALESCE(effect_affix,''),secondary_trait);

-- Business actions retain replay and provenance after the short-lived HTTP cache expires.
CREATE TABLE season_equipment_actions (
    action_id uuid PRIMARY KEY,
    player_id uuid NOT NULL,
    season_id varchar(80) NOT NULL,
    action_kind varchar(32) NOT NULL CHECK (action_kind IN ('equipment.craft','recipe.learn','equipment.reforge')),
    request_id varchar(80) NOT NULL,
    request_hash varchar(64) NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    before_item jsonb,
    after_item jsonb,
    response_json jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    UNIQUE (player_id,action_kind,request_id),
    FOREIGN KEY (player_id,season_id) REFERENCES player_season_state(player_id,season_id) ON DELETE CASCADE
);
