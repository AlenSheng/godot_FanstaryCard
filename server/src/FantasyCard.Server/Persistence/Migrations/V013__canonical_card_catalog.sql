ALTER TABLE player_cards DROP CONSTRAINT IF EXISTS player_cards_rarity_check;
ALTER TABLE player_cards
    ADD CONSTRAINT player_cards_rarity_check CHECK (rarity BETWEEN 1 AND 5);

CREATE TEMP TABLE card_id_upgrade(old_id varchar(80) PRIMARY KEY, new_id varchar(80) NOT NULL UNIQUE) ON COMMIT DROP;

INSERT INTO card_id_upgrade(old_id, new_id)
SELECT format('common-%s', to_char(value, 'FM00')), format('C%s', to_char(value, 'FM00'))
FROM generate_series(1, 30) AS value;

INSERT INTO card_id_upgrade(old_id, new_id)
SELECT prefix || '-' || to_char(value, 'FM00'), canonical || '-' || to_char(value, 'FM00')
FROM (VALUES ('priest', 'PRI'), ('mage', 'MAG'), ('guardian', 'GUA')) AS classes(prefix, canonical)
CROSS JOIN generate_series(1, 7) AS value;

DELETE FROM player_cards legacy
USING card_id_upgrade mapping
WHERE legacy.card_id = mapping.old_id
  AND EXISTS (
      SELECT 1 FROM player_cards canonical
      WHERE canonical.player_id = legacy.player_id AND canonical.card_id = mapping.new_id
  );

UPDATE player_cards cards
SET card_id = mapping.new_id
FROM card_id_upgrade mapping
WHERE cards.card_id = mapping.old_id;

UPDATE player_deck_cards cards
SET card_id = mapping.new_id
FROM card_id_upgrade mapping
WHERE cards.card_id = mapping.old_id;
