extends SceneTree
func _initialize() -> void:
    call_deferred("run")
func run() -> void:
    var game=get_root().get_node("Game")
    game.set_process(false)
    game.gateway.set_process(false)
    game.gateway.persist_session=false
    game.gateway.reconnect_enabled=false
    game.gateway.socket.close()
    var sound=get_root().get_node("Sound")
    sound.stop_all()
    sound.set_process(false)
    var results := {}
    var ok := true
    var total := 0
    for name in ["test_season_equipment.gd","test_season_enhancement.gd","test_season_wallet_protocol.gd"]:
        print("START "+name)
        var row: Dictionary=await load("res://tests/"+name).new().run_test()
        results[name]=row
        ok=ok and row.ok
        total+=row.checks.size()
    FileAccess.open(OS.get_environment("FANTASYCARD_ART_EVIDENCE").path_join("checks.json"),FileAccess.WRITE).store_string(JSON.stringify({"ok":ok,"checks":total,"suites":results},"  "))
    print(JSON.stringify({"ok":ok,"checks":total}))
    quit(0 if ok else 1)
