-- V021 remains the legacy activation contract. Extra permanent copies live
-- separately; enabling the new policy never rewrites cards, levels or decks.
CREATE TABLE player_card_copy_modes (
    player_id uuid PRIMARY KEY REFERENCES players(user_id) ON DELETE CASCADE,
    enabled_by_config varchar(80) NOT NULL CHECK(length(enabled_by_config)>0),
    enabled_at timestamptz NOT NULL
);

CREATE TABLE player_card_reserves (
    player_id uuid NOT NULL REFERENCES player_card_copy_modes(player_id) ON DELETE CASCADE,
    card_id varchar(80) NOT NULL,
    extra_count integer NOT NULL CHECK(extra_count BETWEEN 0 AND 2147483646),
    PRIMARY KEY(player_id,card_id),
    FOREIGN KEY(player_id,card_id) REFERENCES player_cards(player_id,card_id) ON DELETE CASCADE
);

CREATE TABLE card_copy_ledger (
    movement_id uuid PRIMARY KEY,
    ledger_sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    player_id uuid NOT NULL REFERENCES player_card_copy_modes(player_id) ON DELETE CASCADE,
    card_id varchar(80) NOT NULL,
    delta integer NOT NULL CHECK(delta<>0),
    balance_after integer NOT NULL CHECK(balance_after>=0),
    reason varchar(80) NOT NULL,
    request_id varchar(128) NOT NULL,
    created_at timestamptz NOT NULL,
    UNIQUE(player_id,reason,request_id,card_id),
    FOREIGN KEY(player_id,card_id) REFERENCES player_cards(player_id,card_id) ON DELETE CASCADE
);

-- Enforce the cross-table invariant at commit so the base and reserve can be
-- updated atomically in either order. Archived seasons do not own these rows.
CREATE FUNCTION check_permanent_card_reserve() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM player_card_reserves r
        JOIN player_cards c USING(player_id,card_id)
        WHERE r.player_id=NEW.player_id AND r.card_id=NEW.card_id
          AND r.extra_count>0 AND (NOT c.unlocked OR c.copy_count<>1)
    ) THEN
        RAISE EXCEPTION 'Permanent card reserves require an activated base card'
            USING ERRCODE='23514';
    END IF;
    RETURN NULL;
END $$;

CREATE CONSTRAINT TRIGGER card_reserve_requires_base
    AFTER INSERT OR UPDATE ON player_card_reserves
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
    EXECUTE FUNCTION check_permanent_card_reserve();
CREATE CONSTRAINT TRIGGER activated_card_keeps_reserves
    AFTER UPDATE ON player_cards
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
    EXECUTE FUNCTION check_permanent_card_reserve();
