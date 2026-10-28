extends RefCounted

class Probe extends "res://tests/gameplay_load_client.gd":
	func _ready() -> void: set_process(false)

func run_test() -> Dictionary:
	var checks := {}
	var probe := Probe.new()
	var room := {"room_id":"room","match_id":"match","room_revision":1,
		"player":{"player_id":"self","phase":"Pve","stun_remaining_ms":0,
			"combat":{"hp":80,"maximum_hp":70,"effective_maximum_hp":80},
			"hand":[{"instance_id":"second"},{"instance_id":"first"}]},
		"allowed_actions":["battle.play_cards"],"pve":{"battle_id":"battle"}}
	var original := room.duplicate(true)
	var state: Dictionary = probe._command_room_state(room)
	checks["valid hand retains authoritative instance order"] = state.hand_instance_ids_valid and state.hand_instance_ids == ["second","first"]
	checks["trace does not mutate gameplay state or classify legal80over70"] = room == original and state.player_hp == 80 and state.base_maximum_hp == 70
	room.player.hand[0].instance_id = "changed"
	checks["captured instance IDs remain an independent observation"] = state.hand_instance_ids == ["second","first"]
	for value in [null,"bad",[{"instance_id":""}],[{"instance_id":42}],[{"instance_id":"same"},{"instance_id":"same"}],["not-an-instance"]]:
		room.player.hand = value
		state = probe._command_room_state(room)
		checks["invalid hand is not trusted "+str(checks.size())] = not state.hand_instance_ids_valid and state.hand_instance_ids.is_empty()
	room.player.erase("hand")
	state = probe._command_room_state(room)
	checks["absent hand does not become trusted empty hand"] = not state.hand_instance_ids_valid
	room.player.hand = []
	state = probe._command_room_state(room)
	checks["explicit empty hand is captured without inventing cards"] = state.hand_instance_ids_valid and state.hand_instance_ids.is_empty()
	probe.free()
	return {"ok":not checks.values().has(false),"checks":checks,"scope":"OFFLINE trace input integrity;zero live worlds"}
