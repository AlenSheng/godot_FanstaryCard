extends RefCounted

func run_test() -> Dictionary:
	for path in ["res://ui/main.gd", "res://ui/palette.gd", "res://state/game_store.gd", "res://network/gateway.gd", "res://tests/integration.gd", "res://tests/art_preview.gd"]:
		var script = load(path)
		if script == null or not script.can_instantiate():
			return {"ok": false, "message": "Cannot instantiate " + path}
	return {"ok": true, "message": "All shipped UI, network, state and integration scripts compile"}
