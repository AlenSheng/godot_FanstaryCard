extends SceneTree
func _initialize() -> void:
    call_deferred("run")
func run() -> void:
    var checks := {}
    for name in ["ui/main.gd", "ui/reference_ui.gd", "ui/monster_pool_view.gd", "ui/equipment_compare_dialog.gd", "ui/card_view.gd"]:
        var script = load("res://"+name)
        checks[name] = script != null and script.can_instantiate()
    print(JSON.stringify({"checks":checks,"rendered_frames":false}))
    quit(0 if checks.values().all(func(value): return value) else 1)
