extends SceneTree
func _initialize() -> void:
    call_deferred("run")
func run() -> void:
    Game.set_process(false)
    Game.gateway.set_process(false)
    Game.gateway.persist_session=false
    Game.gateway.reconnect_enabled=false
    Game.gateway.socket.close()
    Sound.stop_all()
    Sound.set_process(false)
    var test=load("res://tests/test_season_equipment.gd").new()
    var result: Dictionary=await test.run_test()
    FileAccess.open(OS.get_environment("FANTASYCARD_ART_EVIDENCE").path_join("checks.json"),FileAccess.WRITE).store_string(JSON.stringify(result,"  "))
    print(JSON.stringify(result))
    quit(0 if result.ok else 1)
