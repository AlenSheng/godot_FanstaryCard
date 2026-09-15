UPDATE player_cards
SET copy_count = CASE WHEN unlocked THEN 1 ELSE 0 END,
    level = CASE WHEN unlocked THEN level ELSE 0 END;

ALTER TABLE player_cards DROP CONSTRAINT IF EXISTS player_cards_copy_count_check;
ALTER TABLE player_cards ADD CONSTRAINT player_cards_copy_count_check
    CHECK ((unlocked AND copy_count = 1) OR (NOT unlocked AND copy_count = 0));
