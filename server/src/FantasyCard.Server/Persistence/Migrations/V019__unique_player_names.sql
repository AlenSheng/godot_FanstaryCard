ALTER TABLE players
    ADD COLUMN display_name_key text
    GENERATED ALWAYS AS (lower(normalize(btrim(display_name), NFKC))) STORED;

CREATE UNIQUE INDEX ux_players_display_name_key ON players(display_name_key);

-- Preserve existing local players and assets while making their names usable across devices.
INSERT INTO external_identities(provider, external_subject, player_id, created_at)
SELECT 'local-name', p.display_name_key, p.user_id, i.created_at
FROM players p
JOIN external_identities i ON i.player_id = p.user_id AND i.provider = 'local';
