CREATE TABLE IF NOT EXISTS player_wallets (
    player_id uuid PRIMARY KEY REFERENCES players(user_id) ON DELETE CASCADE,
    gold bigint NOT NULL DEFAULT 0 CHECK (gold >= 0),
    diamond bigint NOT NULL DEFAULT 0 CHECK (diamond >= 0),
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0)
);

CREATE TABLE IF NOT EXISTS player_materials (
    player_id uuid PRIMARY KEY REFERENCES players(user_id) ON DELETE CASCADE,
    warrior_soul bigint NOT NULL DEFAULT 0 CHECK (warrior_soul >= 0),
    priest_soul bigint NOT NULL DEFAULT 0 CHECK (priest_soul >= 0),
    mage_soul bigint NOT NULL DEFAULT 0 CHECK (mage_soul >= 0),
    guardian_soul bigint NOT NULL DEFAULT 0 CHECK (guardian_soul >= 0),
    equipment_fragments bigint NOT NULL DEFAULT 0 CHECK (equipment_fragments >= 0),
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0)
);

CREATE TABLE IF NOT EXISTS player_cards (
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    card_id varchar(80) NOT NULL,
    hero_class smallint NULL CHECK (hero_class BETWEEN 1 AND 3),
    rarity smallint NOT NULL CHECK (rarity BETWEEN 1 AND 4),
    is_monster boolean NOT NULL DEFAULT false,
    unlocked boolean NOT NULL DEFAULT true,
    copy_count integer NOT NULL DEFAULT 1 CHECK (copy_count >= 0),
    level integer NOT NULL DEFAULT 0 CHECK (level BETWEEN 0 AND 5),
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    PRIMARY KEY (player_id, card_id)
);

CREATE TABLE IF NOT EXISTS player_decks (
    deck_id uuid PRIMARY KEY,
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    hero_class smallint NOT NULL CHECK (hero_class BETWEEN 1 AND 3),
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    updated_at timestamptz NOT NULL,
    UNIQUE (player_id, hero_class)
);

CREATE TABLE IF NOT EXISTS player_deck_cards (
    deck_id uuid NOT NULL REFERENCES player_decks(deck_id) ON DELETE CASCADE,
    slot_index integer NOT NULL CHECK (slot_index BETWEEN 0 AND 19),
    card_id varchar(80) NOT NULL,
    PRIMARY KEY (deck_id, slot_index)
);

CREATE TABLE IF NOT EXISTS class_weapons (
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    hero_class smallint NOT NULL CHECK (hero_class BETWEEN 1 AND 3),
    level integer NOT NULL DEFAULT 0 CHECK (level BETWEEN 0 AND 5),
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    PRIMARY KEY (player_id, hero_class)
);

CREATE TABLE IF NOT EXISTS player_consumables (
    player_id uuid PRIMARY KEY REFERENCES players(user_id) ON DELETE CASCADE,
    health_potion_count integer NOT NULL DEFAULT 0 CHECK (health_potion_count >= 0),
    advanced_bag_count integer NOT NULL DEFAULT 0 CHECK (advanced_bag_count >= 0),
    top_bag_count integer NOT NULL DEFAULT 0 CHECK (top_bag_count >= 0),
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0)
);
