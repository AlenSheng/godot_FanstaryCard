extends RefCounted

func run_test() -> Dictionary:
	for path in ["res://ui/main.gd", "res://ui/palette.gd", "res://ui/card_pool.gd", "res://ui/card_grid_view.gd", "res://ui/deck_builder_view.gd", "res://ui/confirmation_modal.gd", "res://ui/equipment_compare_model.gd", "res://ui/item_visual.gd", "res://ui/equipment_compare_dialog.gd", "res://ui/art.gd", "res://ui/card_details.gd", "res://ui/exploration_view.gd", "res://ui/cell_index.gd", "res://data/catalog_index.gd", "res://state/element_rules.gd", "res://state/game_store.gd", "res://network/gateway.gd", "res://tests/integration.gd", "res://tests/art_preview.gd", "res://tests/codex_preview.gd", "res://tests/deck_builder_preview.gd", "res://tests/codex_integration.gd", "res://tests/test_client_hot_paths.gd", "res://tests/test_codex_open.gd", "res://tests/run_codex_open.gd"]:
		var script = load(path)
		if script == null or not script.can_instantiate():
			return {"ok": false, "message": "Cannot instantiate " + path}
	return {"ok": true, "message": "All shipped UI, network, state and integration scripts compile"}
