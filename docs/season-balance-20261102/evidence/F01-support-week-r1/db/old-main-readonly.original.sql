BEGIN READ ONLY; SELECT json_build_object('wallets',(SELECT json_agg(w) FROM(
 SELECT player_id::text AS "PlayerId",gold AS "Gold",equipment_fragments AS "EquipmentFragments",blueprint_marks AS "BlueprintMarks",orange_blueprint_marks AS "OrangeBlueprintMarks"
 FROM f01_calendar_0dc8096e62954cf8822706a3b3de3273.player_season_wallets WHERE season_id='f01-calendar-current17' ORDER BY player_id)w),
 'completed_matches',(SELECT count(*) FROM f01_calendar_0dc8096e62954cf8822706a3b3de3273.matches WHERE status='Completed'),
 'settlements',(SELECT count(*) FROM f01_calendar_0dc8096e62954cf8822706a3b3de3273.match_settlements),
 'ledger_rows',(SELECT count(*) FROM f01_calendar_0dc8096e62954cf8822706a3b3de3273.economy_ledger)); ROLLBACK;