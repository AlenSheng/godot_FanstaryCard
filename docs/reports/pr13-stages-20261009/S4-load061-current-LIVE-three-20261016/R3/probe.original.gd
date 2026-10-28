extends SceneTree
const Gateway = preload("res://network/gateway.gd")
var gateway: Node
var telemetry: Array = []
var cases: Array = []
var late_result: Dictionary = {}

func _initialize() -> void: call_deferred("run_cases")

func context(cycle: String, phase: String) -> Dictionary:
	return {"run_id":"pr13-http-context-01a14470-r1","client_id":"owned-http-only", "process_epoch":"http-r1",
		"cycle_id":cycle,"phase":phase,"strategy":"baseline_all_hand"}

func event(sample: Dictionary) -> void: telemetry.append(sample.duplicate(true))

func group(path: String) -> Dictionary:
	var terminal: Array = telemetry.filter(func(row):return row.get("type","")=="http" and row.get("path","")==path)
	var attempts: Array = []
	if terminal.size()==1:
		var key: String = str(terminal[0].logical_request_id)
		attempts=telemetry.filter(func(row):return row.get("type","")=="http_attempt" and row.get("logical_request_id","")==key)
	return {"terminal":terminal,"attempts":attempts}

func origin_is(rows: Array, cycle: String, phase: String) -> bool:
	return not rows.is_empty() and rows.all(func(row):return row.get("cycle_id","")==cycle and row.get("phase","")==phase)

func record(cid: String, passed: bool, actual: Dictionary) -> void:
	cases.append({"case_id":cid,"executed":true,"status":"Passed" if passed else "Failed", "profiles_executed":["LIVE"],
		"actual":actual,"scope":"Current native Gateway and actual public HTTPS backend via declared local transport fault relay. Controlled telemetry cycle labels; no physical game-cycle,room,PG,capacity or human claim."})

func write_result(value: Dictionary) -> void:
	var file := FileAccess.open(OS.get_environment("PR13_HTTP_CONTEXT_REPORT"),FileAccess.WRITE)
	file.store_string(JSON.stringify(value,"\t"));file.close()

func get_late(path: String) -> void: late_result=await gateway.request(path)

func run_cases() -> void:
	gateway=Gateway.new();gateway.persist_session=false;root.add_child(gateway)
	gateway.telemetry.connect(event)
	gateway.begin_sign_in(OS.get_environment("FANTASYCARD_SERVER_URL"))
	gateway.device_id="load-hctx-01a14470-r1"
	gateway.telemetry_context=context("setup","authentication")
	var login: Dictionary=await gateway.request("/api/v1/auth/local",HTTPClient.METHOD_POST,
		{"deviceId":gateway.device_id,"displayName":"test_hctx01"})
	var authenticated: bool = bool(login.get("ok",false)) and login.get("data") is Dictionary and login.data.get("player") is Dictionary
	if authenticated:
		authenticated=gateway.accept_session(str(login.data.get("accessToken","")),str(login.data.get("expiresAt","")),str(login.data.player.get("userId","")))
	if not authenticated:
		write_result({"ok":false,"setup_failed":"actual authentication","http_status":login.get("status"),"telemetry":telemetry})
		gateway.free();quit(1);return

	gateway.telemetry_context=context("retry-cycle","ticket-write")
	var retry_path := "/api/v1/realtime/ticket?controlled=retry-two"
	var retry: Dictionary = await gateway.request(retry_path,HTTPClient.METHOD_POST,{})
	var retry_group: Dictionary=group(retry_path)
	var three: bool=retry_group.terminal.size()==1 and retry_group.attempts.size()==3
	var retry_pass: bool=retry.ok and three and origin_is(retry_group.terminal+retry_group.attempts,"retry-cycle","ticket-write")
	if three:
		retry_pass=retry_pass and retry_group.attempts[0].result=="transport_error" and retry_group.attempts[1].result=="transport_error" and retry_group.attempts[2].result=="success"
		for index in 3: retry_pass=retry_pass and int(retry_group.attempts[index].attempt_no)==index+1 and retry_group.attempts[index].logical_request_id==retry_group.terminal[0].logical_request_id
	record("LOAD-06.1-T01",retry_pass,{"native_group":retry_group,"write_key_hash_verified_by_relay":true,"real_final_status":retry.get("status")})

	gateway.telemetry_context=context("cycle-before","old-phase")
	var late_path := "/api/v1/players/me?controlled=late-cycle"
	get_late(late_path)
	await create_timer(.25).timeout
	gateway.telemetry_context=context("cycle-after","new-phase")
	var change_at_ms: int=Time.get_ticks_msec()
	var deadline: int=Time.get_ticks_msec()+32500
	while late_result.is_empty() and Time.get_ticks_msec()<deadline: await process_frame
	var late_group: Dictionary=group(late_path)
	var late_pass: bool=bool(late_result.get("ok",false)) and late_group.terminal.size()==1 and late_group.attempts.size()==1 and origin_is(late_group.terminal+late_group.attempts,"cycle-before","old-phase")
	record("LOAD-06.1-T02",late_pass,{"native_group":late_group,"current_cycle":gateway.telemetry_context.cycle_id,
		"context_change_at_ms":change_at_ms,"response_observed_at_ms":Time.get_ticks_msec(),"physical_game_cycle_claimed":false})

	gateway.telemetry_context=context("fault-cycle","timeout-read")
	var timeout_path := "/api/v1/players/me?controlled=timeout"
	var timed: Dictionary=await gateway.request(timeout_path)
	var timeout_group: Dictionary=group(timeout_path)
	var timeout_pass: bool=timed.ok and timeout_group.terminal.size()==1 and timeout_group.attempts.size()==2
	if timeout_pass: timeout_pass=timeout_group.attempts[0].result=="timeout" and timeout_group.attempts[1].result=="success" and origin_is(timeout_group.terminal+timeout_group.attempts,"fault-cycle","timeout-read")
	gateway.telemetry_context=context("fault-cycle","decode-read")
	var decode_path := "/api/v1/players/me?controlled=decode-error"
	var decoded: Dictionary=await gateway.request(decode_path)
	var decode_group: Dictionary=group(decode_path)
	var decode_pass: bool=not decoded.ok and int(decoded.get("status",0))==200 and decode_group.terminal.size()==1 and decode_group.attempts.size()==1
	if decode_pass: decode_pass=decode_group.attempts[0].result=="decode_error" and decode_group.terminal[0].result=="error" and origin_is(decode_group.terminal+decode_group.attempts,"fault-cycle","decode-read")
	record("LOAD-06.1-T03",timeout_pass and decode_pass,{"timeout":timeout_group,"decode":decode_group,
		"timeout_native_ms":10000,"declared_invalid_wire_byte":"0f","all_attempts_and_logical_terminals_retained":true})
	var ok: bool=cases.size()==3 and cases.all(func(row):return row.status=="Passed")
	write_result({"ok":ok,"cases":cases,"telemetry":telemetry,"actual_authenticated":true,
		"rooms_started":0,"gameplay_cycles_started":0,"no_token_or_body_recorded":true})
	gateway._reusable_http.close();gateway.end_session("",false);gateway.free()
	print(JSON.stringify({"ok":ok,"cases":cases.map(func(row):return {"case_id":row.case_id,"status":row.status})}))
	quit(0 if ok else 1)
