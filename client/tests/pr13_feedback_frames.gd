extends "res://tests/art_preview.gd"

func _run() -> void:
    DirAccess.make_dir_recursive_absolute(output)
    Game.gateway.set_process(false)
    Game.gateway.socket.close()
    Game.configuration_error = ""
    Game.busy = false
    var observations: Array = []
    var original_fps := Engine.max_fps
    var palette = preload("res://ui/palette.gd")
    var original_language: String = palette.language()
    for language in ["zh-CN","en"]:
        palette.set_language(language)
        for fps in [30,60,144]:
            Engine.max_fps = fps
            for resolution in [Vector2i(1920,1080),Vector2i(1280,720),Vector2i(960,540)]:
                get_window().size = resolution
                for hero in ["Mage","Priest","Guardian"]:
                    for delay_ms in [0,100,300]:
                        Game.gateway.online = true
                        Game.gateway.recovering = false
                        Game._pending_commands = {}
                        Game._latest_commands = {}
                        Game._pending_play = {}
                        Game.selected_cards = []
                        Game.room = {"room_id":"frame-room","match_id":"frame-match","room_revision":10,"config_version":Game.CATALOG.data.version,
                            "allowed_actions":["battle.play_cards","battle.select_target"],
                            "player":{"player_id":"preview-player","hero_class":hero,"phase":"Pve","combat":{"hp":60,"maximum_hp":100 if hero=="Guardian" else 70,"shield":0},
                                "hand":[{"instance_id":"card","card_id":"C01","level":0}],"battle_status":{}},
                            "pve":{"battle_id":"frame-battle","current_target_id":"fire-bat","monsters":[{"monster_id":"fire-bat","hp":40,"maximum_hp":44,"shield":0,"intent_kind":"Attack","intent_element":"Fire","intent_value":2}]}}
                        $UI._render()
                        await RenderingServer.frame_post_draw
                        var feedback := {"battle_id":"frame-battle","target_id":"fire-bat","attacker_id":"preview-player","source_id":"preview-player","damage_segments":[{"kind":"Fire","amount":9}],"hp_damage":9,"shield_damage":0,"heal":0,"shield_gain":0,"_request_id":"frame-feedback"}
                        if delay_ms>0: await get_tree().create_timer(float(delay_ms)/1000.0).timeout
                        var before_frame := Engine.get_frames_drawn()
                        var delivered_at := Time.get_ticks_usec()
                        Game._on_event("combat.hit",feedback)
                        await RenderingServer.frame_post_draw
                        var presented_at := Time.get_ticks_usec()
                        var frame_delta := Engine.get_frames_drawn()-before_frame
                        if language=="en" and resolution.x==960 and hero=="Guardian" and delay_ms==300:
                            var error := get_viewport().get_texture().get_image().save_png(output+"/feedback_"+str(fps)+".png")
                            if error!=OK: layout_errors.append({"screenshot_error":error})
                        var numbers: Array = $UI.find_children("CombatNumber*","Label",true,false).filter(func(node): return node.is_visible_in_tree() and node.text.contains("9"))
                        var card: Button = $UI._reference.get_node_or_null("Card_C01")
                        var usable: bool = card!=null and not card.disabled and Game.allowed("battle.play_cards")
                        if card!=null: card.pressed.emit()
                        usable = usable and "card" in Game.selected_cards
                        var no_prediction: bool = int(Game.room.pve.monsters[0].hp)==40
                        var before_old := $UI.find_children("CombatNumber*","Label",true,false).size()
                        var prior_feedback: Dictionary = feedback.duplicate(true)
                        prior_feedback.battle_id = "old-battle"
                        Game._on_event("combat.hit",prior_feedback)
                        var stale_ignored: bool = $UI.find_children("CombatNumber*","Label",true,false).size()==before_old
                        Game.gateway._schedule_reconnect()
                        var before_selection: Array = Game.selected_cards.duplicate()
                        Game.toggle_card("card")
                        var bounded_reconnect: bool = Game.selected_cards==before_selection and not Game.allowed("battle.play_cards")
                        Game.gateway.reconnect_enabled = false
                        Game.gateway.online = true
                        Game.gateway.recovering = false
                        Game._pending_commands = {}
                        Game._latest_commands = {}
                        Game._pending_play = {}
                        Game.room.pve.monsters[0].hp = 0
                        Game.play_cards()
                        var dead_rejected: bool = Game._pending_commands.is_empty() and Game._pending_play.is_empty()
                        var ok: bool = not numbers.is_empty() and frame_delta<=1 and frame_delta>=0 and usable and no_prediction and stale_ignored and bounded_reconnect and dead_rejected
                        observations.append({"language":language,"fps":fps,"resolution":[resolution.x,resolution.y],"hero":hero,"controlled_delivery_delay_ms":delay_ms,
                            "presented_frame_delta":frame_delta,"local_delivery_to_presentation_usec":presented_at-delivered_at,"visible_number_count":numbers.size(),"legal_card_usable":usable,
                            "authority_hp_unchanged":no_prediction,"old_feedback_ignored":stale_ignored,"reconnect_bounded":bounded_reconnect,"dead_target_rejected":dead_rejected,"passed":ok})
                        if not ok: layout_errors.append(observations.back())
    palette.set_language(original_language)
    Engine.max_fps = original_fps
    var all_passed: bool = observations.size()==162 and layout_errors.is_empty()
    var result := {"source_kind":"actual GPU renderer with declared controlled feedback delivery fixtures","display_driver":DisplayServer.get_name(),"renderer":RenderingServer.get_video_adapter_name(),"observations":observations,"errors":layout_errors,"cases":[]}
    for id in ["PR13-B10.4-T01","PR13-B10.4-T02","PR13-B10.4-T03"]:
        result.cases.append({"case_id":id,"executed":true,"status":"Passed" if all_passed else "Failed","profiles_executed":["OFFLINE","RENDER"],"actual":{"matrix_rows":162,"matrix_all_passed":all_passed,"row_fields":"See immutable actual frame observation records"},
            "scope":"Actual rendered frames, three FPS/resolutions/heroes, two languages, controlled 0/100/300ms delivery; no real network timing or human claim"})
    FileAccess.open(output+"/report.json",FileAccess.WRITE).store_string(JSON.stringify(result))
    print(JSON.stringify({"rows":observations.size(),"failed":layout_errors.size(),"display_driver":DisplayServer.get_name()}))
    get_tree().quit(0 if all_passed else 1)
