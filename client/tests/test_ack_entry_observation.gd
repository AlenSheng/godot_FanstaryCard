extends RefCounted
const AckFixture = preload("res://tests/pr13_ack_stop_cycles.gd")
class Store extends "res://state/game_store.gd":
	func _ready() -> void: set_process(false)
class QuietGateway extends "res://network/gateway.gd":
	func _ready() -> void: set_process(false)
func _case() -> Dictionary:
	var game := Store.new()
	var gateway := QuietGateway.new()
	gateway.persist_session = false
	gateway.online = true
	gateway.room_id = "room"
	gateway.current_match_id = "match"
	gateway.room_context_epoch = 7
	game.gateway = gateway
	game._room_context_epoch = 7
	game.room = {"room_id":"room","match_id":"match","room_revision":10,"player":{"player_id":"self","phase":"Pve","hand":[],"combat":{"hp":70}},"pve":{"battle_id":"battle","monsters":[]}}
	var p = AckFixture.LoadProbe.new()
	p.Game = game;p.run_id="run";p.client_id="client";p.process_epoch="process";p.own_user_id="self";p.stage="playing";p.active_match_id="match"
	return {"probe":p,"game":game,"gateway":gateway}
func _free(c:Dictionary) -> void:
	c.probe.free();c.game.free();c.gateway.free()
func run_test() -> Dictionary:
	var checks := {}
	var c := _case();var p = c.probe
	p._on_event("room.snapshot",c.game.room.duplicate(true))
	checks["actual owned snapshot establishes one entry without a start callback"] = p.entered_matches == ["match"]
	p._on_event("room.snapshot",c.game.room.duplicate(true));p._on_event("room.started",{"match_id":"match"})
	checks["duplicate snapshot and start cannot duplicate entry"] = p.entered_matches == ["match"]
	checks["entry observation invents no completed cycle or ACK"] = p.completed_events.is_empty() and p.cycles_completed == 0
	p.stop_requested = true
	checks["real observed entry keeps STOP partition nonnegative"] = p.entered_matches.size()-p.cycles_completed-1 == 0
	c.game.room.match_id="next-match";c.gateway.current_match_id="next-match"
	p._on_event("room.snapshot",c.game.room.duplicate(true))
	checks["STOP late state cannot invent another entry"] = p.entered_matches == ["match"]
	_free(c)
	for scenario in ["empty_room","foreign_route","foreign_player","terminal","recovering","old_epoch","unknown_owner","cleanup"]:
		c=_case();p=c.probe
		match scenario:
			"empty_room":c.game.room={}
			"foreign_route":c.gateway.current_match_id="foreign-match"
			"foreign_player":c.game.room.player.player_id="someone-else"
			"terminal":c.game.room.player.phase="Dead"
			"recovering":c.gateway.recovering=true
			"old_epoch":c.gateway.room_context_epoch=6
			"unknown_owner":p.own_user_id=""
			"cleanup":p.stage="cleanup"
		p._on_event("room.snapshot",c.game.room.duplicate(true))
		checks[scenario+" cannot fabricate entry"] = p.entered_matches.is_empty()
		_free(c)
	return {"ok":not checks.values().has(false),"checks":checks,"scope":"OFFLINE actual ACK/STOP fixture consumer and owned room controls; no server world, SQL result backfill or real STOP-ACK acceptance"}
