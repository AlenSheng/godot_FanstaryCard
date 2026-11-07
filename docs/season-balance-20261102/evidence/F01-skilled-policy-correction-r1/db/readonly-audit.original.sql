SET search_path TO f01_calendar_0dc8096e62954cf8822706a3b3de3273; BEGIN READ ONLY;
 SELECT json_build_object(
 'season_wallet_mismatches',COALESCE((SELECT json_agg(x) FROM(
 SELECT w.player_id,w.gold,w.equipment_fragments,w.blueprint_marks,w.orange_blueprint_marks,
 COALESCE(sum(l.delta) FILTER(WHERE l.currency='Gold'),0) gold_sum,
 COALESCE(sum(l.delta) FILTER(WHERE l.currency='EquipmentFragments'),0) fragment_sum,
 COALESCE(sum(l.delta) FILTER(WHERE l.currency='BlueprintMarks'),0) blueprint_sum,
 COALESCE(sum(l.delta) FILTER(WHERE l.currency='OrangeBlueprintMarks'),0) orange_sum
 FROM player_season_wallets w LEFT JOIN economy_ledger l ON l.player_id=w.player_id AND l.season_id=w.season_id
 WHERE w.season_id='f01-calendar-current17' GROUP BY w.player_id,w.gold,w.equipment_fragments,w.blueprint_marks,w.orange_blueprint_marks
 HAVING w.gold<>COALESCE(sum(l.delta) FILTER(WHERE l.currency='Gold'),0)
 OR w.equipment_fragments<>COALESCE(sum(l.delta) FILTER(WHERE l.currency='EquipmentFragments'),0)
 OR w.blueprint_marks<>COALESCE(sum(l.delta) FILTER(WHERE l.currency='BlueprintMarks'),0)
 OR w.orange_blueprint_marks<>COALESCE(sum(l.delta) FILTER(WHERE l.currency='OrangeBlueprintMarks'),0))x),'[]'::json),
 'permanent_soul_mismatches',COALESCE((SELECT json_agg(x) FROM(
 SELECT m.player_id,m.warrior_soul,m.priest_soul,m.mage_soul,m.guardian_soul,
 COALESCE(sum(l.delta) FILTER(WHERE l.currency='WarriorSoul'),0) warrior_sum,
 COALESCE(sum(l.delta) FILTER(WHERE l.currency='PriestSoul'),0) priest_sum,
 COALESCE(sum(l.delta) FILTER(WHERE l.currency='MageSoul'),0) mage_sum,
 COALESCE(sum(l.delta) FILTER(WHERE l.currency='GuardianSoul'),0) guardian_sum
 FROM player_materials m LEFT JOIN economy_ledger l ON l.player_id=m.player_id
 GROUP BY m.player_id,m.warrior_soul,m.priest_soul,m.mage_soul,m.guardian_soul
 HAVING m.warrior_soul<>COALESCE(sum(l.delta) FILTER(WHERE l.currency='WarriorSoul'),0)
 OR m.priest_soul<>COALESCE(sum(l.delta) FILTER(WHERE l.currency='PriestSoul'),0)
 OR m.mage_soul<>COALESCE(sum(l.delta) FILTER(WHERE l.currency='MageSoul'),0)
 OR m.guardian_soul<>COALESCE(sum(l.delta) FILTER(WHERE l.currency='GuardianSoul'),0))x),'[]'::json),
 'activity_accounts',COALESCE((SELECT json_agg(a) FROM(SELECT player_id,event_id,earned,spent,version FROM player_season_activity_accounts ORDER BY player_id,event_id)a),'[]'::json),
 'activity_receipts',COALESCE((SELECT json_agg(r) FROM(SELECT player_id,event_id,rule_id,quantity,token_cost,reward_kind,reward_amount,state FROM season_activity_redemptions ORDER BY player_id,event_id,created_at)r),'[]'::json),
 'match_statuses',(SELECT json_object_agg(status,n) FROM(SELECT status,count(*) n FROM matches GROUP BY status)t),
 'human_settlements',(SELECT count(*) FROM match_settlements),
 'equipment_source_counts',(SELECT json_agg(q) FROM(SELECT source_kind,location,count(*) n FROM equipments GROUP BY source_kind,location ORDER BY source_kind,location)q),
 'ledger_rows',(SELECT count(*) FROM economy_ledger),
 'pending_holds',(SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'),
 'active_preparations',(SELECT count(*) FROM preparations WHERE status IN('Active','Queued')),
 'card_count',(SELECT count(*) FROM player_cards),
 'db_schema','f01_calendar_0dc8096e62954cf8822706a3b3de3273'); ROLLBACK;