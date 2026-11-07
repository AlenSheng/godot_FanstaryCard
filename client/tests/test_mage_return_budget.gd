extends RefCounted

const Proto = preload("res://network/protobuf.gd")
const Details = preload("res://ui/battle_details.gd")
const CardDetails = preload("res://ui/card_details.gd")
const Index = preload("res://data/catalog_index.gd")
const Bundle = preload("res://data/config_bundle.gd")
const P = preload("res://ui/palette.gd")

func run_test() -> Dictionary:
	var checks := {}
	var proto := Proto.new()
	for name in ["credit-0", "credit-0.75", "credit-1", "credit-2", "original16"]:
		var fixture: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/sustain/" + name + ".original.json"))
		var envelope: Dictionary = proto.decode("ServerEnvelope", Marshalls.base64_to_raw(fixture.wire))
		var snapshot: Dictionary = proto.decode("RoomSnapshotEvent", envelope.payload)
		var numerical: Dictionary = snapshot.player.numerical_state
		checks[name + " wire decoded"] = proto.error.is_empty() and snapshot.config_version == fixture.Version
		if fixture.expected_credit == null:
			checks[name + " old fields absent"] = not numerical.has("fenxian_return_credit") and not numerical.has("fenxian_return_rate_basis_points")
		else:
			checks[name + " exact credit"] = numerical.get("fenxian_return_credit") == fixture.expected_credit
			checks[name + " exact rate"] = numerical.get("fenxian_return_rate_basis_points") == 500
	var store = preload("res://state/game_store.gd").new()
	var gateway = preload("res://network/gateway.gd").new()
	gateway.persist_session = false
	gateway.online = true
	store.gateway = gateway
	store.room = {"config_version": "season-v1-config-17", "player": {"hero_class": "Mage", "weapon_level": 0, "combat": {"hp": 70, "maximum_hp": 70, "shield": 0}, "battle_status": {"core_element": "Fire", "combo": 2, "bonuses": []}, "numerical_state": {"fenxian_policy": "SeasonRateBudgetedRhythm", "fenxian_return_credit": "0"}, "hand": [{"instance_id": "a", "card_id": "C01", "level": 0}, {"instance_id": "b", "card_id": "C02", "level": 0}, {"instance_id": "c", "card_id": "MAG-10", "level": 0}]}, "pve": {"battle_id": "preview", "current_target_id": "monster", "monsters": [{"monster_id": "monster", "hp": 10000, "shield": 0}]}}
	store.room["room_id"] = "budget-preview"
	store.room["allowed_actions"] = ["battle.play_cards"]
	for credit in [0.0, 0.75, 1.0, 2.0]:
		store.room.player.numerical_state.fenxian_return_credit = str(credit)
		var preview: Dictionary = store._calculate_combat_preview(["a", "b"])
		checks["instant bounded " + str(credit)] = preview.immediate_draw == mini(1, int(floor(credit + 1e-10))) and is_zero_approx(float(preview.draw_charge))
		preview = store._calculate_combat_preview(["a"])
		checks["single charge bounded " + str(credit)] = preview.immediate_draw == 0 and is_equal_approx(float(preview.draw_charge), minf(0.18, credit))
	store.room.player.numerical_state.fenxian_policy = "SeasonBoundedRhythm"
	var old_preview: Dictionary = store._calculate_combat_preview(["a", "b"])
	checks["old policy keeps charge plus instant"] = old_preview.immediate_draw == 1 and is_equal_approx(float(old_preview.draw_charge), 0.50)
	var reader := Bundle.new()
	var old_data := reader.decode(FileAccess.get_file_as_bytes("res://tests/sustain/original16.bytes"), "season-v1-config-16", "48e25ff33fed65928f059a6907dfacaa5b88f7c7e91d5fb558c3a1dbac0e0e8b")
	var old_index := Index.from_data(old_data)
	checks["original16 archive verified"] = not old_index.is_empty() and reader.error.is_empty()
	var prior := P.language()
	for locale in P.languages():
		P.set_language(locale)
		var text := Details.passive_text({"passive_kind": "FenXian"}, {"fenxian_policy": "SeasonRateBudgetedRhythm", "fenxian_return_credit": "0.75", "fenxian_return_rate_basis_points": 500})
		checks[locale + " budget translated"] = text.contains("0.75") and text.contains("5%") and not text.contains("battle_mage_return_budget")
		checks[locale + " old policy no invented credit"] = not Details.passive_text({"passive_kind": "FenXian"}).contains("0.75")
		checks[locale + " new card no printed draw"] = not CardDetails.face_description("MAG-10").contains(P.localized("card_face_draw") % "1")
		checks[locale + " old card printed draw preserved"] = CardDetails.face_description("MAG-10", 0, {}, old_index).contains(P.localized("card_face_draw") % "1")
	P.set_language(prior)
	store.free()
	gateway.free()
	return {"ok": checks.values().all(func(value): return value == true), "checks": checks, "no_game_matches": true}
