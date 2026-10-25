extends RefCounted
class Probe extends "res://tests/gameplay_load_client.gd":
 func _ready() -> void:set_process(false)
 func _strategy_wait_state() -> Dictionary:return {"reason":"fixture","legal_opportunity":false,"hand_count":1}
class Store extends "res://state/game_store.gd":
 func _ready() -> void:set_process(false)
 func _process_client_info() -> void:pass
 func _check_shop_rotation() -> void:pass
class QuietGateway extends "res://network/gateway.gd":
 var recovery_requests:=0
 func _ready() -> void:set_process(false)
 func connect_realtime() -> void:recovery_requests+=1
func _case() -> Dictionary:
 var game=Store.new();var gateway=QuietGateway.new();gateway.persist_session=false;game.gateway=gateway
 var probe=Probe.new();probe.Game=game;probe.run_id="run";probe.client_id="client";probe.process_epoch="process";probe.own_user_id="self";probe.stage="playing";probe.active_match_id="match"
 return {"probe":probe,"game":game,"gateway":gateway}
func _room(duel:bool=false,other:bool=false) -> Dictionary:
 var hand=[{"instance_id":"pve-card"}]
 if duel:hand=[{"instance_id":"duel-card1"},{"instance_id":"duel-card2"},{"instance_id":"duel-card3"}]
 var value={"room_id":"room-new" if other else "room","match_id":"match-new" if other else "match","player":{"player_id":"self","phase":"Pvp" if duel else "Pve","hand":hand,"combat":{"hp":80,"maximum_hp":70,"shield":0},"library_count":19,"discard_count":0},"pve":{"battle_id":"pve-new" if other else "pve","monsters":[{"monster_id":"rat","hp":21,"shield":0,"stun_remaining_ms":0}]},"allowed_actions":["battle.play_cards"]}
 if duel:value["duel"]={"duel_id":"duel","opponent_id":"opponent","opponent":{"hp":70,"shield":0}}
 return value
func _summaries(probe,battle:String) -> Array:
 return probe.telemetry.filter(func(row):return row.get("event_type")=="battle.summary" and row.get("battle_id")==battle)
func _free(c:Dictionary) -> void:c.probe.free();c.game.free();c.gateway.free()
func _prepare_gap(c:Dictionary,duel:bool=false) -> void:
 c.game.room=_room(duel);c.game.room["room_revision"]=10
 c.game._room_context_epoch=7;c.game._room_context_room_id="room";c.game._room_context_match_id="match"
 c.gateway.session_generation=4;c.gateway.room_context_epoch=7;c.gateway.room_id="room";c.gateway.current_match_id="match"
 c.game.network_telemetry.connect(c.probe._on_telemetry)
func _expire_write(c:Dictionary) -> void:
 c.game._pending_commands["gap-write"]={"deadline":Time.get_ticks_msec()-1,"action":"battle.play_cards","room_id":"room","session_generation":4,"room_context_epoch":7,"origin_context":{"room_id":"room","match_id":"match","cycle_id":"client:1"}}
 c.game._process(0.0)
func _restore_authority(c:Dictionary,duel:bool=false) -> void:
 var fresh=_room(duel);fresh["room_revision"]=20;fresh["config_version"]=c.game.CATALOG.data.version
 c.game._on_event("room.snapshot",fresh)
func _authority_gap_checks() -> Dictionary:
 var checks={}
 for duel in [false,true]:
  var c=_case();var p=c.probe;var g=c.game;var battle="duel" if duel else "pve";var label="PVP" if duel else "PVE"
  _prepare_gap(c,duel);p._observe_battle()
  p._on_event("battle.combo_resolved",{"attacker_id":"self","battle_id":battle,"card_instance_ids":["before"],"hp_damage":2})
  var original_start=p.battle_started_ms;var gap_start=Time.get_ticks_msec();p.last_progress_ms=1
  _expire_write(c);p._observe_battle()
  checks[label+" real store timeout temporarily clears authority"]=g.room.is_empty() and g.room_authority_recovering() and c.gateway.recovery_requests==1
  checks[label+" authority gap does not terminate the live battle"]=p.current_battle_id==battle and p.battle_metrics.get("actions",-1)==1 and not p.terminal_battle_ids.has(battle) and _summaries(p,battle).is_empty()
  p._on_event("battle.combo_resolved",{"attacker_id":"self","battle_id":battle,"hp_damage":9})
  p._on_event("pong",{});c.gateway.online=true;c.gateway.recovering=false;p._observe_battle()
  checks[label+" unverified gap packets and connection marker invent no gameplay"]=p.last_progress_ms==1 and p.battle_metrics.get("actions",-1)==1
  while Time.get_ticks_msec()-gap_start<60:await Engine.get_main_loop().process_frame
  _restore_authority(c,duel);p._observe_battle()
  checks[label+" same scoped fresh authority ends recovery"]=not g.room_authority_recovering() and not g.room.is_empty()
  checks[label+" same battle resumes its original counters"]=p.current_battle_id==battle and p.battle_metrics.get("actions",-1)==1 and p.battle_metrics.get("hp_damage",-1)==2
  checks[label+" recovery time is not hidden as suspended combat time"]=p.battle_started_ms==original_start and p.battle_suspended_ms==0 and Time.get_ticks_msec()-original_start>=60
  checks[label+" unchanged restored hand is not a fake new opportunity"]=p.last_progress_ms==1 and p.battle_metrics.get("observed_cards_drawn",-1)==0
  p._on_event("battle.combo_resolved",{"attacker_id":"self","battle_id":battle,"card_instance_ids":["after"],"hp_damage":3})
  checks[label+" resumed real positive combo advances gameplay"]=p.last_progress_ms>1 and p.last_gameplay_progress_reason=="effective_combo" and p.battle_metrics.get("effective_actions",-1)==2 and p.battle_metrics.get("hp_damage",-1)==5
  p.last_progress_ms=1;p._on_event("battle.combo_resolved",{"attacker_id":"self","battle_id":battle,"hp_damage":0})
  checks[label+" resumed zero effect combo still cannot keep gameplay alive"]=p.last_progress_ms==1 and p.battle_metrics.get("effective_actions",-1)==2
  p._on_event("battle.combo_resolved",{"attacker_id":"self","battle_id":battle,"hp_damage":1,"battle_ended":true});p._observe_battle()
  var final_rows=_summaries(p,battle)
  checks[label+" real terminal battle remains closed after late snapshot"]=p.current_battle_id.is_empty() and p.terminal_battle_ids.has(battle) and final_rows.size()==1 and final_rows[0].metrics.outcome=="Victory" and final_rows[0].metrics.hp_damage==6
  checks[label+" legal80over70 still passes through recovery"]=g.room.get("player",{}).get("combat",{}).get("hp")==80 and g.room.get("player",{}).get("combat",{}).get("maximum_hp")==70
  _free(c)
 var c=_case();var p=c.probe;var g=c.game
 _prepare_gap(c);p._observe_battle();p._on_event("battle.combo_resolved",{"attacker_id":"self","battle_id":"pve","hp_damage":2});_expire_write(c);p._observe_battle()
 c.gateway.session_generation+=1;g.room=_room(false,true);p.last_progress_ms=1
 p._on_event("battle.combo_resolved",{"attacker_id":"self","battle_id":"pve","hp_damage":9})
 checks["changed room cannot inherit gap battle progress before next poll"]=p.last_progress_ms==1
 p._observe_battle();var old=_summaries(p,"pve")
 checks["changed room retires original scoped metrics and starts fresh"]=p.current_battle_id=="pve-new" and p.battle_metrics.get("actions",-1)==0 and old.size()==1 and old[0].get("room_id")=="room" and old[0].get("match_id")=="match" and old[0].metrics.hp_damage==2
 _free(c)
 c=_case();p=c.probe;g=c.game;_prepare_gap(c);p._observe_battle();p._on_event("battle.combo_resolved",{"attacker_id":"self","battle_id":"pve","hp_damage":2})
 g.room=_room(true);p._observe_battle();_expire_write(c);p._observe_battle()
 checks["authority gap in duel keeps its frozen PVE provenance"]=p.current_battle_id=="duel" and p._suspended_pve_metrics.has("pve") and _summaries(p,"pve").is_empty()
 _restore_authority(c,true);p._observe_battle();p._on_event("battle.combo_resolved",{"attacker_id":"self","battle_id":"duel","hp_damage":3,"battle_ended":true})
 g.room=_room();p._observe_battle()
 checks["fresh duel authority still resumes one original PVE afterward"]=p.current_battle_id=="pve" and p.battle_metrics.get("hp_damage",-1)==2 and _summaries(p,"duel").size()==1 and _summaries(p,"pve").is_empty()
 _free(c)
 return checks
func run_test() -> Dictionary:
 var checks={};var c=_case();var p=c.probe;var g=c.game
 g.room=_room();p._observe_battle();p._on_event("battle.combo_resolved",{"attacker_id":"self","battle_id":"pve","card_instance_ids":["pve-card"],"hp_damage":2})
 checks["PVE initial observer and effective action"]=p.current_battle_id=="pve" and p.battle_metrics.actions==1
 var pve_before_start=Time.get_ticks_msec()
 while Time.get_ticks_msec()-pve_before_start<60:
  await Engine.get_main_loop().process_frame
 var pve_before_elapsed=Time.get_ticks_msec()-pve_before_start
 p.last_progress_ms=1;g.room=_room(true);p._observe_battle()
 checks["active duel wins over retained frozen PVE snapshot"]=p.current_battle_id=="duel"
 checks["PVP observation excludes frozen PVE monsters"]=p.telemetry[-1].get("event_type")=="battle.observed" and p.telemetry[-1].get("monsters",[]).is_empty()
 checks["suspension does not invent gameplay progress"]=p.last_progress_ms==1
 var timer_wall_start=Time.get_ticks_msec()
 while Time.get_ticks_msec()-timer_wall_start<200:
  await Engine.get_main_loop().process_frame
 var timer_wall_elapsed=Time.get_ticks_msec()-timer_wall_start
 p._on_event("battle.combo_resolved",{"attacker_id":"self","battle_id":"duel","card_instance_ids":["duel-card1"],"hp_damage":3,"battle_ended":true})
 var duel_rows=_summaries(p,"duel")
 checks["PVP summary owns only its action"]=duel_rows.size()==1 and duel_rows[0].metrics.actions==1 and duel_rows[0].metrics.hp_damage==3
 g.room=_room();p._observe_battle()
 checks["surviving PVP resumes same PVE with original counters"]=p.current_battle_id=="pve" and p.battle_metrics.actions==1 and p.battle_metrics.hp_damage==2
 checks["PVP reset hand is not counted as PVE draws"]=p.battle_metrics.observed_cards_drawn==0
 var pve_after_start=Time.get_ticks_msec()
 while Time.get_ticks_msec()-pve_after_start<60:
  await Engine.get_main_loop().process_frame
 var pve_after_elapsed=Time.get_ticks_msec()-pve_after_start
 p._close_battle_metrics("Stopped");var pve_rows=_summaries(p,"pve");var metrics=pve_rows[0].get("metrics",{}) if pve_rows.size()==1 else {}
 checks["one summary per resumed PVE battle"]=pve_rows.size()==1
 checks["wall duration preserved and suspended duration explicit"]=int(metrics.get("suspended_ms",-1))>=150 and int(metrics.get("observed_ms",0))==int(metrics.get("active_observed_ms",-1))+int(metrics.get("suspended_ms",-1)) and metrics.get("observed_clock","")=="wall"
 checks["active duration retains real PVE time around PVP"]=int(metrics.get("active_observed_ms",-1))>=pve_before_elapsed+pve_after_elapsed and int(metrics.get("active_observed_ms",0))>=120
 checks["legal80over70HP untouched"]=g.room.player.combat.hp==80 and g.room.player.combat.maximum_hp==70
 _free(c)
 c=_case();p=c.probe;g=c.game;g.room=_room();p._observe_battle();g.room=_room(true);p._observe_battle();p._close_battle_metrics("Stopped")
 var stop_duel=_summaries(p,"duel");var stop_pve=_summaries(p,"pve")
 checks["STOP closes duel and censors suspended PVE separately"]=stop_duel.size()==1 and stop_duel[0].metrics.outcome=="Stopped" and stop_pve.size()==1 and stop_pve[0].metrics.outcome=="Censored" and not str(stop_pve[0].metrics.get("censor_reason","")).is_empty()
 _free(c)
 c=_case();p=c.probe;g=c.game;g.room=_room();p._observe_battle();g.room=_room(true);p._observe_battle();p.cycles_completed=3;g.room=_room(false,true);p._observe_battle();var old=_summaries(p,"pve")
 checks["old frozen battle summary keeps original room match cycle"]=old.size()==1 and old[0].get("room_id")=="room" and old[0].get("match_id")=="match" and old[0].get("cycle_id")=="client:1"
 checks["new room owns a new active observer"]=p.current_battle_id=="pve-new"
 p._close_battle_metrics("Stopped");_free(c)
 c=_case();p=c.probe;g=c.game;g.room=_room();p._observe_battle();p._on_event("battle.combo_resolved",{"attacker_id":"self","battle_id":"pve","card_instance_ids":["pve-card"],"hp_damage":2})
 var repeat_paused=0
 for index in range(2):
  var round_duel="duel-repeat-%d"%index
  g.room=_room(true);g.room.duel.duel_id=round_duel;p._observe_battle()
  var pause_start=Time.get_ticks_msec()
  while Time.get_ticks_msec()-pause_start<40:
   await Engine.get_main_loop().process_frame
  repeat_paused+=Time.get_ticks_msec()-pause_start
  p._on_event("battle.combo_resolved",{"attacker_id":"self","battle_id":round_duel,"card_instance_ids":["duel-card1"],"hp_damage":3,"battle_ended":true})
  g.room=_room();p._observe_battle()
 p._close_battle_metrics("Stopped");var repeated_pve=_summaries(p,"pve")
 checks["two successive duels keep one PVE observer and separate counters"]=repeated_pve.size()==1 and repeated_pve[0].metrics.actions==1 and repeated_pve[0].metrics.hp_damage==2 and repeated_pve[0].metrics.observed_cards_drawn==0 and _summaries(p,"duel-repeat-0").size()==1 and _summaries(p,"duel-repeat-1").size()==1
 checks["PVE suspension duration accumulates across successive duels"]=repeated_pve.size()==1 and int(repeated_pve[0].metrics.get("suspended_ms",-1))>=repeat_paused and repeat_paused>=80
 _free(c)
 c=_case();p=c.probe;g=c.game;g.room=_room();p._observe_battle();p._close_battle_metrics("Victory");p._observe_battle()
 checks["late terminal snapshot does not resurrect battle"]=p.current_battle_id.is_empty() and _summaries(p,"pve").size()==1
 _free(c)
 checks.merge(await _authority_gap_checks())
 return {"ok":not checks.values().has(false),"checks":checks,"clock_debug":{"timer_wall_ms":timer_wall_elapsed,"PVE_before_ms":pve_before_elapsed,"PVE_after_ms":pve_after_elapsed,"PVE_metrics":metrics},"scope":"OFFLINE real store expiry and recorder, frozen-PVE and active-duel producer fixtures;no actual server world or capacity acceptance"}
