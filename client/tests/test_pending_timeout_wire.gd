extends RefCounted

class DelayedGateway extends "res://network/gateway.gd":
	var reconnects := 0
	func connect_realtime() -> void:
		reconnects += 1
		online = false

func _pump(gateway: Node, peer: WebSocketPeer) -> void:
	gateway.socket.poll()
	peer.poll()
	while gateway.socket.get_available_packet_count() > 0:
		gateway._receive(gateway.socket.get_packet())

func _envelope(codec: RefCounted, kind: String, schema: String, sequence: int, payload: Dictionary, request_id: String = "") -> PackedByteArray:
	return codec.encode("ServerEnvelope", {"protocol_version": 1, "type": kind, "sequence": sequence,
		"request_id": request_id, "room_revision": 11, "payload": codec.encode(schema, payload)})

func run_test() -> Dictionary:
	var checks := {}
	var listener := TCPServer.new()
	var peer := WebSocketPeer.new()
	var gateway := DelayedGateway.new()
	gateway.persist_session = false
	gateway.base_url = OS.get_environment("FANTASYCARD_SERVER_URL")
	gateway.token = "controlled-loopback-only"
	gateway.token_expires_at = Time.get_unix_time_from_system() + 60
	gateway.session_generation = 4
	gateway.room_context_epoch = 7
	gateway.room_id = "wire-room"
	gateway.current_match_id = "wire-match"
	gateway.room_revision = 10
	var store: Node = load("res://state/game_store.gd").new()
	store.gateway = gateway
	store._room_context_epoch = 7
	store._room_context_room_id = gateway.room_id
	store._room_context_match_id = gateway.current_match_id
	gateway.event_received.connect(store._on_event)
	gateway.connection_changed.connect(store._on_connection_changed)
	var codec: RefCounted = load("res://network/protobuf.gd").new()
	var opened := listener.listen(0, "127.0.0.1") == OK
	var accepted := false
	if opened:
		gateway.socket.connect_to_url("ws://127.0.0.1:" + str(listener.get_local_port()))
		var until := Time.get_ticks_msec() + 3000
		while Time.get_ticks_msec() < until:
			gateway.socket.poll()
			if not accepted and listener.is_connection_available():
				peer.accept_stream(listener.take_connection())
				accepted = true
			if accepted: peer.poll()
			if gateway.socket.get_ready_state() == WebSocketPeer.STATE_OPEN and peer.get_ready_state() == WebSocketPeer.STATE_OPEN: break
			await Engine.get_main_loop().process_frame
		opened = gateway.socket.get_ready_state() == WebSocketPeer.STATE_OPEN
	checks["owned real binary WebSocket is open"] = opened
	if opened:
		gateway.online = true
		store.room = {"room_id": "wire-room", "match_id": "wire-match", "room_revision": 10,
			"allowed_actions": ["battle.play_cards"], "player": {"player_id": "owner", "phase": "Pve", "hand": [{"instance_id": "spent-card"}]},
			"pve": {"battle_id": "wire-battle", "current_target_id": "monster", "monsters": [{"monster_id": "monster", "hp": 84}]}}
		store.selected_cards = ["spent-card"]
		store.play_cards()
		var until := Time.get_ticks_msec() + 1000
		while peer.get_available_packet_count() == 0 and Time.get_ticks_msec() < until:
			_pump(gateway, peer)
			await Engine.get_main_loop().process_frame
		var command: Dictionary = codec.decode("ClientEnvelope", peer.get_packet()) if peer.get_available_packet_count() > 0 else {}
		var original := str(command.get("request_id", ""))
		var modeled_server_writes := 1 if command.get("type") == "battle.play_cards" else 0
		checks["actual first wire write contains the selected card"] = modeled_server_writes == 1 and codec.decode("BattlePlayCardsCommand", command.get("payload", PackedByteArray())).get("card_instance_ids", []) == ["spent-card"]
		var waiting_started := Time.get_ticks_msec()
		while Time.get_ticks_msec() - waiting_started < 3200:
			_pump(gateway, peer)
			store._process(0)
			await Engine.get_main_loop().process_frame
		checks["unchanged real3second deadline enters authority recovery without another write"] = gateway.reconnects == 1 and gateway.recovering and store.room.is_empty() and not store.command("battle.play_cards", {"battle_id": "wire-battle", "target_id": "monster", "card_instance_ids": ["spent-card"]})
		peer.send(_envelope(codec, "battle.combo_resolved", "BattleComboResolvedEvent", 1,
			{"battle_id": "wire-battle", "attacker_id": "owner", "target_id": "monster", "damage": 1, "card_instance_ids": ["spent-card"]}, original))
		until = Time.get_ticks_msec() + 1000
		while gateway.last_sequence < 1 and Time.get_ticks_msec() < until:
			_pump(gateway, peer)
			await Engine.get_main_loop().process_frame
		checks["late real ACK alone cannot restore the stale hand"] = gateway.last_sequence == 1 and store.room.is_empty() and store._settlement_match_id() == "wire-match"
		peer.send(_envelope(codec, "session.connected", "SessionConnectedEvent", 2, {"player_id": "owner"}))
		until = Time.get_ticks_msec() + 1000
		while not gateway.online and Time.get_ticks_msec() < until:
			_pump(gateway, peer)
			await Engine.get_main_loop().process_frame
		checks["transport connection marker still cannot authorize a stale write"] = gateway.online and store.room.is_empty() and not store.command("battle.play_cards", {"battle_id": "wire-battle", "target_id": "monster", "card_instance_ids": ["spent-card"]})
		peer.send(_envelope(codec, "room.snapshot", "RoomSnapshotEvent", 3,
			{"room_id": "wire-room", "match_id": "wire-match", "room_revision": 11, "config_version": store.CATALOG.data.version,
				"allowed_actions": ["battle.play_cards"], "player": {"player_id": "owner", "hero_class": "Mage", "phase": "Pve", "combat": {"hp": 70, "maximum_hp": 70}, "hand": [{"instance_id": "new-card", "card_id": "C01", "level": 1}]},
				"pve": {"battle_id": "wire-battle", "phase": "Active", "current_target_id": "monster", "monsters": [{"monster_id": "monster", "hp": 83}]}}))
		until = Time.get_ticks_msec() + 1000
		while store.room.is_empty() and Time.get_ticks_msec() < until:
			_pump(gateway, peer)
			await Engine.get_main_loop().process_frame
		checks["fresh scoped binary authority restores only the new hand and legal70HP"] = not gateway.recovering and store.room.get("player", {}).get("hand", []).map(func(card): return card.instance_id) == ["new-card"] and store.room.get("player", {}).get("combat", {}).get("maximum_hp") == 70
		store.selected_cards = ["new-card"]
		store.play_cards()
		until = Time.get_ticks_msec() + 1000
		var new_write := {}
		while Time.get_ticks_msec() < until and new_write.is_empty():
			_pump(gateway, peer)
			while peer.get_available_packet_count() > 0:
				var value: Dictionary = codec.decode("ClientEnvelope", peer.get_packet())
				if value.get("type") == "battle.play_cards":
					modeled_server_writes += 1
					new_write = value
			await Engine.get_main_loop().process_frame
		checks["only explicit new-card write proceeds after fresh authority"] = modeled_server_writes == 2 and str(new_write.get("request_id", "")) != original and codec.decode("BattlePlayCardsCommand", new_write.get("payload", PackedByteArray())).get("card_instance_ids", []) == ["new-card"]
	gateway.socket.close()
	peer.close()
	listener.stop()
	store.free()
	gateway.free()
	return {"ok": not checks.values().has(false), "checks": checks,
		"scope": "Actual local WebSocket/Gateway/Store/Protobuf and real3second timer; server apply/late ACK and new state are controlled, no real account/PG/natural game or capacity acceptance"}
