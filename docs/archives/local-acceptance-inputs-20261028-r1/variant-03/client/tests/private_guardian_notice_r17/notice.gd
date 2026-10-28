extends "res://tests/gameplay_ui_preview.gd"
class RenderGateway extends "res://network/gateway.gd":
 var sent:Array=[]
 var serial:=0
 func new_id() -> String:
  serial+=1
  return "rejected-render-%d"%serial
 func send(kind:String,payload:Dictionary={},request_id:String="") -> bool:
  sent.append({"kind":kind,"payload":payload.duplicate(true),"request_id":request_id})
  return true
 func connect_realtime() -> void:online=false
func _ready() -> void:
 super._ready()
 Game.gateway.set_process(false);Game.gateway.socket.close()
 var replacement=RenderGateway.new();replacement.persist_session=false;replacement.base_url="http://127.0.0.1:1";Game.add_child(replacement);replacement.set_process(false);replacement.event_received.connect(Game._on_event);replacement.failed.connect(Game.notice.emit);Game.gateway=replacement
func _run() -> void:
 DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output))
 for resolution in [Vector2i(1920,1080),Vector2i(1280,720)]:
  get_window().size=resolution
  for phase in ["ActionBar","Pve","Pvp"]:
   var combat=phase!="ActionBar"
   var suffix=phase.to_lower()+"_%d"%resolution.x
   Game._pending_commands.clear();Game._pending_play.clear();Game._latest_commands.clear();Game._queued_command={};Game._rejected_state_request={};Game._command_recovery_context={};Game.gateway.sent.clear();Game.gateway.online=true;Game.gateway.recovering=false;Game.connection="已连接"
   Game.hero_class="Guardian"
   var room=_room_fixture();room.player.hero_class="Guardian";room.player.combat={"hp":80,"maximum_hp":100,"effective_maximum_hp":100,"shield":6};room.player["numerical_state"]={"guardian_policy":"FractionalRemainder","guardian_remainder_tenths":5};room["match_id"]="rejected-preview-match";room["config_version"]=Game.CATALOG.data.version;room.allowed_actions.append("room.move")
   if combat:
    room.player.phase=phase;room.allowed_actions+=["battle.play_cards","battle.select_target"];room["pve"]={"battle_id":"completion-battle","current_target_id":"fire-bat","monsters":[{"monster_id":"fire-bat","maximum_hp":44,"hp":31,"shield":8,"intent_kind":"Attack","intent_value":5,"intent_element":"Fire"}]}
   if phase=="Pvp":room["duel"]={"duel_id":"completion-battle","opponent_id":"preview-opponent","opponent":{"hp":70,"maximum_hp":70,"shield":8},"escape_remaining_ms":0,"separate_loot":true,"searchable_loot":[]}
   Game.room=room;Game._adopt_room_context(room);Game.gateway.session_generation=9;Game.gateway.room_id=room.room_id;Game.gateway.current_match_id=room.match_id;Game.gateway.room_context_epoch=Game._room_context_epoch;Game.selected_cards=["hand-0","hand-1"]
   $UI.set_meta("inventory_open",false);$UI.set_meta("relic_pile","")
   var action="battle.play_cards" if combat else "room.move";var payload={"battle_id":"completion-battle","target_id":"fire-bat","card_instance_ids":["hand-0","hand-1"]} if combat else {"row":3,"column":3}
   Game._send_queued_command({"action":action,"payload":payload});var request=Game._pending_commands.keys()[0]
   var proto=load("res://network/protobuf.gd").new();Game.gateway._receive(proto.encode("ServerEnvelope",{"protocol_version":1,"type":"error.command_rejected","sequence":Game.gateway.last_sequence+1,"request_id":request,"payload":proto.encode("CommandRejectedEvent",{"code":"COMMAND_REJECTED","detail":"当前状态已变化，请等待同步"})}))
   _check(not Game.room.is_empty() and Game.has_pending_commands(),"One rejected state wait "+suffix)
   _check(not Game.allowed(action) and Game.selected_cards.is_empty(),"Stale action and selection disabled "+suffix)
   var reads=Game.gateway.sent.filter(func(row):return row.kind=="room.snapshot.read");_check(reads.size()==1,"One state read without error suppression "+suffix)
   if combat:_check(Game.combat_wait_state().reason=="recovering","Combat wait uses existing recovery feedback "+suffix)
   await _capture("rejected_wait_"+suffix)
   var fresh=room.duplicate(true);fresh.room_revision+=1;fresh["_request_id"]=reads[0].request_id;Game._on_event("room.snapshot",fresh)
   _check(Game.allowed(action) and not Game.has_pending_commands(),"Fresh state restores explicit controls "+suffix)
   if combat:Game.toggle_card("hand-0");Game.toggle_card("hand-1")
   await _capture("rejected_restored_"+suffix)
 var result={"geometry_samples":geometry_samples,"rendered_frames":0,"ok":not checks.values().has(false) and layout_errors.is_empty(),"screenshots":screenshot_count,"checks":checks,"layout_errors":layout_errors,"scope":"Offline actual product state and protobuf rejection plus real renderer;network none,no actual world/account/capacity or human experience"};FileAccess.open(output+"/report.json",FileAccess.WRITE).store_string(JSON.stringify(result))
 Game.set_process(false);Game._client_info_socket.close();Game.gateway.end_session("",false);Sound.set_process(false);Sound.set_music_context("");Sound.stop_all();Sound.stop_music();await get_tree().create_timer(.35).timeout;$UI.queue_free();await get_tree().process_frame;await get_tree().process_frame;get_tree().quit(0 if result.ok else 1)

var geometry_samples:Array=[]
func _capture(name:String,rebuild:bool=true) -> void:
 if rebuild:$UI._render()
 await get_tree().create_timer(.4).timeout
 var panel=$UI.tips_overlay.panel
 var current_rect:Rect2=panel.get_global_transform_with_canvas()*Rect2(Vector2.ZERO,panel.size)
 var start:Vector2=$UI.tips_overlay.start_position()
 var sweep:Rect2=Rect2(start-Vector2(0,$UI.tips_overlay.RISE_DISTANCE),panel.size+Vector2(0,$UI.tips_overlay.RISE_DISTANCE))
 var collisions:Array=[]
 for type in ["Label","Button"]:
  for node in $UI._reference.find_children("*",type,true,false):
   if not node.is_visible_in_tree() or node.text.is_empty():continue
   var rect:Rect2=node.get_global_transform_with_canvas()*Rect2(Vector2.ZERO,node.size)
   if sweep.intersects(rect):collisions.append({"name":str(node.name),"text":node.text,"rect":str(rect)})
 var inside:bool=get_viewport().get_visible_rect().encloses(sweep)
 _check(inside and collisions.is_empty(),"Notice full animation avoids visible Label and Button text "+name)
 if name.contains("pve") or name.contains("pvp"):_check($UI._reference.find_child("GuardianRemainder",true,false)!=null,"Actual Guardian remainder exists "+name)
 geometry_samples.append({"case":name,"notice_rect":str(current_rect),"full_animation_sweep":str(sweep),"inside_viewport":inside,"overlap":collisions})
