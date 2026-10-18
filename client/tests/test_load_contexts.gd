extends RefCounted
class Probe extends "res://tests/gameplay_load_client.gd":
 func _ready() -> void:set_process(false)
class StubGame extends Node:
 var room: Dictionary={}
func run_test() -> Dictionary:
 var checks: Dictionary={};var probe:=Probe.new();var game:=StubGame.new();probe.Game=game;probe.run_id="observer-current-run";probe.client_id="observer-current-client";probe.process_epoch="observer-current-process";probe.cycles_completed=6;probe.stage="settlement";probe.active_match_id="current-match";game.room={"room_id":"current-room","match_id":"current-match"}
 var origin: Dictionary={"run_id":"dispatch-run","client_id":"dispatch-client","process_epoch":"dispatch-process","cycle_id":"dispatch-client:1","phase":"playing","room_id":"old-room","match_id":"old-match","logical_request_id":"stable-logical"}
 probe._on_telemetry(origin.merged({"type":"http","status":200},true));var row: Dictionary=probe.telemetry[-1]
 checks["captured source identity remains immutable"] = origin.keys().all(func(k):return row.get(k)==origin[k]) and row.observer_context.client_id=="observer-current-client"
 probe._on_telemetry({"type":"http","logical_request_id":"missing-origin","room_id":"","match_id":"","status":200});row=probe.telemetry[-1]
 checks["missing asynchronous context is Unknown not current cycle"] = row.origin_context_state=="Unknown" and row.cycle_id=="Unknown" and row.phase=="Unknown" and row.room_id=="" and row.match_id==""
 probe.stop_requested=true;probe._on_telemetry(origin.merged({"type":"http_attempt","status":200},true));row=probe.telemetry[-1]
 checks["STOP drain window is separate from original business phase"] = row.observation_phase=="drain" and row.phase=="playing" and row.cycle_id=="dispatch-client:1"
 probe._on_telemetry({"type":"lifecycle","event_type":"local.control"});row=probe.telemetry[-1]
 checks["local synchronous context remains local"] = row.origin_context_state=="Local" and row.cycle_id=="observer-current-client:7" and row.phase=="settlement"
 probe._on_telemetry({"type":"http","logical_request_id":"null-origin","_origin_context":null});row=probe.telemetry[-1]
 checks["malformed null origin remains explicitly unknown"] = row.origin_context_state=="Unknown" and row.phase=="Unknown"
 checks["no diagnostic HTTP traffic becomes gameplay progress"] = probe.telemetry.all(func(v):return not v.gameplay_progress)
 probe.free();game.free();return {"ok":not checks.values().has(false),"checks":checks,"scope":"OFFLINE production recorder context contract with explicit fixture values,no world or network"}
