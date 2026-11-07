-- Keep opaque historical ChallengeMarks unchanged. New blueprint types start at zero.
ALTER TABLE player_season_wallets
    ADD COLUMN blueprint_marks bigint NOT NULL DEFAULT 0 CHECK (blueprint_marks >= 0),
    ADD COLUMN orange_blueprint_marks bigint NOT NULL DEFAULT 0 CHECK (orange_blueprint_marks >= 0);
ALTER TABLE season_wallet_operations
    ADD COLUMN blueprints_after bigint NOT NULL DEFAULT 0 CHECK (blueprints_after >= 0),
    ADD COLUMN orange_blueprints_after bigint NOT NULL DEFAULT 0 CHECK (orange_blueprints_after >= 0);
ALTER TABLE economy_ledger DROP CONSTRAINT economy_ledger_currency_check;
ALTER TABLE economy_ledger ADD CONSTRAINT economy_ledger_currency_check
    CHECK (currency IN ('Gold','Diamond','WarriorSoul','ClassSoul','PriestSoul','MageSoul','GuardianSoul',
        'EquipmentFragments','ChallengeMarks','BlueprintMarks','OrangeBlueprintMarks'));

CREATE TABLE player_crafting_wishes (
    player_id uuid NOT NULL,
    season_id varchar(80) NOT NULL,
    quality varchar(16) NOT NULL CHECK (quality IN ('Purple','Orange')),
    slot varchar(16) NOT NULL CHECK (slot IN ('Head','Chest','Hands','Legs','Feet')),
    element varchar(16) NOT NULL CHECK (element IN ('Fire','Wood','Earth','Metal','Water')),
    wished_effect varchar(16) NOT NULL CHECK (wished_effect IN ('Piercing','Bulwark','Vitality')),
    failures integer NOT NULL DEFAULT 0 CHECK (failures BETWEEN 0 AND 2),
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (player_id,season_id,quality,slot,element,wished_effect),
    FOREIGN KEY (player_id,season_id) REFERENCES player_season_state(player_id,season_id) ON DELETE CASCADE
);
