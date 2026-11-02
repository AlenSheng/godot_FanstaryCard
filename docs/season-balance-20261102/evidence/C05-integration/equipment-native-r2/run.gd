extends SceneTree
func _initialize() -> void:
    call_deferred("run")
func run() -> void:
    var game=get_root().get_node("Game")
    var sound=get_root().get_node("Sound")
    game.set_process(false)
    game.gateway.set_process(false)
    game.gateway.persist_session=false
    game.gateway.reconnect_enabled=false
    game.gateway.socket.close()
    sound.stop_all()
    sound.set_process(false)
    var test=load("res://tests/test_season_equipment.gd").new()
    var result: Dictionary=await test.run_test()
    FileAccess.open(OS.get_environment("FANTASYCARD_ART_EVIDENCE").path_join("checks.json"),FileAccess.WRITE).store_string(JSON.stringify(result,"  "))
    print(JSON.stringify(result))
    quit(0 if result.ok else 1)
