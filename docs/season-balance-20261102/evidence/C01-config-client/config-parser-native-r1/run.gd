extends SceneTree
func _initialize() -> void:
    call_deferred("run")
func run() -> void:
    var reader = load("res://data/config_bundle.gd").new()
    var bytes := FileAccess.get_file_as_bytes("res://config.bytes")
    var data: Dictionary = reader.decode(bytes, "season-v1-config-stage-1", "54e52047f708874b6079b568145203d3613d39bc5efc9905a861636590467fcd")
    var checks := {"decoded":not data.is_empty(), "error_empty":reader.error.is_empty()}
    if not data.is_empty():
        var index: Dictionary = load("res://data/catalog_index.gd").from_data(data)
        checks["cards"] = index.get("cards",{}).size() == 232
        checks["levels"] = index.get("levels",{}).size() == 1320
        checks["server_scope_hidden"] = not data.tables.has("SeasonRedRules") and not data.tables.LootRules[0].has("gold")
        checks["bool_false"] = data.tables.Cards[0].is_class_reveal == false
    print(JSON.stringify({"checks":checks,"parser_error":reader.error}))
    quit(0 if checks.values().all(func(value): return value) else 1)
