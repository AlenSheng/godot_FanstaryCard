SET search_path TO f01_calendar_0dc8096e62954cf8822706a3b3de3273; BEGIN READ ONLY;
 SELECT json_build_object(
 'card_nonzero_levels',(SELECT count(*) FROM player_cards WHERE player_id='01a1b30e-9664-7e73-8d18-f84674348ae2' AND level<>0), 'c01_level',(SELECT level FROM player_cards WHERE player_id='01a1b30e-9664-7e73-8d18-f84674348ae2' AND card_id='C01'), 'c02_level',(SELECT level FROM player_cards WHERE player_id='01a1b30e-9664-7e73-8d18-f84674348ae2' AND card_id='C02'),
 'weapon_nonzero_levels',(SELECT count(*) FROM class_weapons WHERE player_id='01a1b30e-9664-7e73-8d18-f84674348ae2' AND level<>0),
 'permanent_wallet',(SELECT gold+diamond FROM player_wallets WHERE player_id='01a1b30e-9664-7e73-8d18-f84674348ae2'),
 'permanent_materials',(SELECT warrior_soul+priest_soul+mage_soul+guardian_soul+equipment_fragments FROM player_materials WHERE player_id='01a1b30e-9664-7e73-8d18-f84674348ae2'),
 'consumables',(SELECT health_potion_count+advanced_bag_count+top_bag_count FROM player_consumables WHERE player_id='01a1b30e-9664-7e73-8d18-f84674348ae2'),
 'season_balance',(SELECT gold+equipment_fragments+challenge_marks+blueprint_marks+orange_blueprint_marks FROM player_season_wallets WHERE player_id='01a1b30e-9664-7e73-8d18-f84674348ae2' AND season_id='f01-calendar-current17'),
 'owned_equipment',(SELECT count(*) FROM equipments WHERE owner_id='01a1b30e-9664-7e73-8d18-f84674348ae2'),
 'preparations',(SELECT count(*) FROM preparations WHERE player_id='01a1b30e-9664-7e73-8d18-f84674348ae2'),
 'economy_ledger',(SELECT count(*) FROM economy_ledger WHERE player_id='01a1b30e-9664-7e73-8d18-f84674348ae2'),
 'movements',(SELECT count(*) FROM inventory_movements WHERE player_id='01a1b30e-9664-7e73-8d18-f84674348ae2'));
 ROLLBACK;