extends RefCounted

class Host extends "res://ui/main.gd":
	var confirmation: Callable
	var confirmation_text := ""
	func _ready() -> void: pass
	func _render() -> void: pass
	func _schedule_render() -> void: pass
	func _confirm(message: String, action: Callable, _options: Dictionary = {}) -> void:
		confirmation = action
		confirmation_text = message

class Gateway extends Node:
	var session_generation := 40
	var online := true
	var recovering := false
	var base_url := "https://fixture.invalid"
	var commands: Array = []
	var sequence := 0
	func new_id() -> String:
		sequence += 1
		return "fixture-command-" + str(sequence)
	func capture_context() -> Dictionary:
		return {"session_generation": session_generation, "base_url": base_url}
	func send(action: String, body: Dictionary, request_id: String = "") -> bool:
		commands.append({"action": action, "body": body.duplicate(true), "request_id": request_id})
		return true

func _reset(host: Host, gateway: Gateway, full: bool = false) -> Dictionary:
	Game.room = {"room_id": "room-original", "match_id": "match-original", "room_revision": 8, "allowed_actions": ["choice.pick"], "player": {"phase": "Choice", "inventory_capacity": 1 if full else 20, "inventory": [{"item_id": "original-safe-potion", "kind": "HealthPotion", "quantity": 1, "is_safe": true}] if full else []}}
	var option := {"option_id": "original-offer", "kind": 1, "quantity": 1, "equipment": {"slot": "Head", "quality": "Blue"}}
	Game.room["reward_choice"] = {"options": [option]}
	Game.configuration_error = ""
	Game._pending_commands.clear(); Game._latest_commands.clear(); Game._queued_command.clear()
	Game._rejected_state_request.clear(); Game._terminal_room_context.clear()
	Game._room_context_epoch += 1
	host.confirmation = Callable(); host.confirmation_text = ""
	gateway.commands.clear()
	return option

func _frames() -> void:
	await Game.get_tree().process_frame
	await Game.get_tree().process_frame

func run_test() -> Dictionary:
	var checks := {}
	Game.set_process(false)
	Game.get_window().gui_embed_subwindows = true
	var original: Node = Game.gateway
	var gateway := Gateway.new(); Game.add_child(gateway); Game.gateway = gateway
	var host := Host.new(); Game.get_tree().root.add_child(host)
	var option := _reset(host, gateway)
	host._claim(option, true)
	checks["direct equip always asks confirmation"] = host.confirmation.is_valid() and gateway.commands.is_empty()
	Game.room.room_id = "another-room"
	host.confirmation.call()
	checks["old direct equip cannot target another room"] = gateway.commands.is_empty()
	option = _reset(host, gateway)
	host._claim(option, true); host.confirmation.call()
	checks["current direct equip submits original intent"] = gateway.commands.size() == 1 and gateway.commands[0].action == "reward.choice.claim" and gateway.commands[0].body == {"option_id": "original-offer", "equip": true}
	option = _reset(host, gateway, true)
	host._claim(option)
	await _frames()
	var dialog := host.get_node("RewardReplacementDialog") as AcceptDialog
	checks["bag candidate selection sends no command"] = gateway.commands.is_empty() and dialog.get_ok_button().text == preload("res://ui/palette.gd").localized("cancel")
	dialog.find_child("RewardReplacement_original-safe-potion", true, false).pressed.emit()
	checks["replacement requires second confirmation"] = host.confirmation.is_valid() and gateway.commands.is_empty()
	gateway.session_generation += 1
	host.confirmation.call()
	checks["account change invalidates replacement confirmation"] = gateway.commands.is_empty()
	await _frames()
	option = _reset(host, gateway, true)
	host._claim(option); await _frames()
	dialog = host.get_node("RewardReplacementDialog") as AcceptDialog
	Game.room.reward_choice.options = [{"option_id": "new-offer"}]
	dialog.find_child("RewardReplacement_original-safe-potion", true, false).pressed.emit()
	checks["changed offer cannot open a stale replacement confirmation"] = not host.confirmation.is_valid() and gateway.commands.is_empty()
	await _frames()
	option = _reset(host, gateway, true)
	host._claim(option); await _frames()
	dialog = host.get_node("RewardReplacementDialog") as AcceptDialog
	dialog.find_child("RewardReplacement_original-safe-potion", true, false).pressed.emit()
	host.confirmation.call()
	checks["current replacement keeps exact safe item and offer IDs"] = gateway.commands.size() == 1 and gateway.commands[0].body == {"option_id": "original-offer", "equip": false, "replace_item_id": "original-safe-potion"}
	Game._pending_commands.clear(); Game._sound_commands.clear(); Game._pending_play.clear()
	Game.room = {}; Game.gateway = original; host.free(); gateway.queue_free()
	return {"ok": not checks.values().has(false), "checks": checks, "scope": "Native realMain callbacks with fakegateway; no live server/match claim."}
