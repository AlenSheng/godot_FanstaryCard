extends SceneTree

const Gateway = preload("res://network/gateway.gd")
var cases: Array = []
var samples: Array = []
var results: Dictionary = {}
var pg_sessions: Dictionary = {}
var pg_initial: Array = []

class ShortTransportGateway extends "res://network/gateway.gd":
    func _request_http_transport(path: String, method: int, headers: PackedStringArray, body: PackedByteArray, _timeout_ms: int = 10000) -> Array:
        return await super._request_http_transport(path,method,headers,body,100)

func record(id: String, ok: bool, actual: Variant) -> void:
    cases.append({"case_id":id,"executed":true,"status":"Passed" if ok else "Failed","actual":actual,"profiles_executed":["OFFLINE"],
        "scope":"Real Godot gateway, binary HTTP and owned loopback fixture; Actual full Program and isolated PostgreSQL behind a declared fault proxy; final database postconditions are verified separately; no LIVE capacity or performance benefit claim"})

func fresh(short_timeout := false) -> Node:
    samples = []
    var gateway: Node = ShortTransportGateway.new() if short_timeout else Gateway.new()
    gateway.persist_session = false
    gateway.base_url = OS.get_environment("FANTASYCARD_SERVER_URL")
    gateway.use_reusable_http = OS.get_environment("FANTASYCARD_LOAD_HTTP_TRANSPORT") != "per-request"
    root.add_child(gateway)
    gateway.set_process(false)
    gateway.accept_session(pg_sessions.A.accessToken,pg_sessions.A.expiresAt,pg_sessions.A.player.userId)
    gateway.telemetry_context = {"cycle_id":"cycle-first","phase":"playing"}
    gateway.telemetry.connect(func(sample): samples.append(sample.duplicate(true)))
    return gateway

func dispatch(gateway: Node, path: String, name: String, method: int = HTTPClient.METHOD_GET) -> void:
    results[name] = await gateway.request(path,method,{"productId":"health_potion","quantity":1} if method==HTTPClient.METHOD_POST else null,[0,409,429,503])

func until(name: String) -> void:
    var deadline := Time.get_ticks_msec()+12000
    while not results.has(name) and Time.get_ticks_msec()<deadline: await process_frame

func for_path(path: String, kind: String) -> Array:
    if kind != "http_attempt": return samples.filter(func(row): return row.get("path","")==path and row.get("type","")==kind)
    var ids: Array = samples.filter(func(row): return row.get("path","")==path and row.get("type","")=="http").map(func(row): return row.logical_request_id)
    return samples.filter(func(row): return row.get("type","")==kind and (row.get("logical_request_id") in ids if not ids.is_empty() else row.get("route","")==path.get_slice("?",0)))

func proof(rows: Array) -> Array:
    return rows.map(func(row): return {"type":row.type,"logical_request_id":row.get("logical_request_id"),"phase":row.get("phase"),"cycle_id":row.get("cycle_id"),"attempt":row.get("attempt_no"),"result":row.get("result"),"duration_ms":row.get("duration_ms"),"status":row.get("status")})

func close(gateway: Node) -> void:
    gateway.end_session("",false)
    gateway.queue_free()

func _initialize() -> void: call_deferred("run_cases")

func initialize_pg_players() -> void:
    for side in ["A", "B"]:
        var gateway: Node = Gateway.new()
        gateway.persist_session = false
        root.add_child(gateway)
        gateway.set_process(false)
        gateway.base_url = OS.get_environment("FANTASYCARD_SERVER_URL")
        gateway.use_reusable_http = OS.get_environment("FANTASYCARD_LOAD_HTTP_TRANSPORT") != "per-request"
        var name: String = "test_pr13_http_" + OS.get_environment("PR13_HTTP_ARM") + "_" + side
        var login: Dictionary = await gateway.request("/api/v1/auth/local", HTTPClient.METHOD_POST, {"deviceId":name, "displayName":name})
        assert(login.ok and login.data.player.userId != "")
        pg_sessions[side] = login.data
        assert(gateway.accept_session(login.data.accessToken,login.data.expiresAt,login.data.player.userId))
        var mail: Dictionary = await gateway.request("/api/v1/mail")
        assert(mail.ok)
        var gold_mails: Array = mail.data.items.filter(func(item):return item.attachments.any(func(a):return a.kind=="Gold" and int(a.amount)==100000))
        assert(gold_mails.size()==1)
        var claim: Dictionary = await gateway.request("/api/v1/mail/"+str(gold_mails[0].id)+"/claim", HTTPClient.METHOD_POST, {})
        assert(claim.ok)
        var wallet: Dictionary = await gateway.request("/api/v1/economy/wallet")
        assert(wallet.ok and int(wallet.data.gold)==100000)
        pg_initial.append({"side":side,"user_id":login.data.player.userId,"initial_gold":wallet.data.gold,"gold_mail_claimed_via_production_API":true})
        close(gateway)

func run_cases() -> void:
    await initialize_pg_players()
    var gateway := fresh()
    var path := "/api/v1/players/me?mode=retry-five"
    dispatch(gateway,path,"retry")
    var deadline := Time.get_ticks_msec()+2000
    while for_path(path,"http_attempt").is_empty() and Time.get_ticks_msec()<deadline: await process_frame
    gateway.telemetry_context = {"cycle_id":"cycle-next","phase":"settlement"}
    await until("retry")
    var attempts := for_path(path,"http_attempt")
    var terminals := for_path(path,"http")
    var minimum_wait: bool = not terminals.is_empty() and terminals[0].duration_ms>=5000 and results.get("retry",{}).get("ok",false)
    var stable: bool = attempts.size()==2 and terminals.size()==1 and attempts.all(func(row): return row.logical_request_id==terminals[0].logical_request_id)
    record("LOAD-08.3-T01",minimum_wait,{"attempts":proof(attempts),"logical":proof(terminals),"server_minimum_ms":5000})
    record("LOAD-06.1-T01",stable,{"attempts":proof(attempts),"logical":proof(terminals)})
    record("PR13-A06.3-T02",stable and attempts.all(func(row): return row.phase=="playing") and terminals[0].phase=="playing",{"attempts":proof(attempts),"logical":proof(terminals),"current_phase":"settlement"})
    close(gateway)

    gateway = fresh()
    path = "/api/v1/players/me?mode=slow-context"
    dispatch(gateway,path,"slow")
    gateway.telemetry_context = {"cycle_id":"cycle-next","phase":"settlement"}
    await until("slow")
    terminals = for_path(path,"http")
    var original: bool = terminals.size()==1 and terminals[0].cycle_id=="cycle-first" and terminals[0].phase=="playing"
    record("LOAD-06.1-T02",original,{"logical":proof(terminals),"current_cycle":"cycle-next"})
    record("PR13-A06.3-T01",original,{"logical":proof(terminals),"current_cycle":"cycle-next"})
    path = "/api/v1/players/me?mode=singleflight"
    dispatch(gateway,path,"joined-a"); dispatch(gateway,path,"joined-b")
    await until("joined-a"); await until("joined-b")
    var stats: Dictionary = await gateway.request("/api/v1/client-info")
    record("LOAD-08.2-T01",results.get("joined-a",{}).get("ok",false) and results.get("joined-b",{}).get("ok",false) and results["joined-a"].data==results["joined-b"].data and stats.data.counts.get(path,0)==1,{"http_count":stats.data.counts.get(path,0),"same_body":results.get("joined-a",{}).get("data")==results.get("joined-b",{}).get("data")})
    var other := fresh()
    other.end_session("",false)
    other.accept_session(pg_sessions.B.accessToken,pg_sessions.B.expiresAt,pg_sessions.B.player.userId)
    path = "/api/v1/players/me?mode=separate-players"
    dispatch(gateway,path,"player-a"); dispatch(other,path,"player-b")
    await until("player-a"); await until("player-b")
    var write_path := "/api/v1/shop/purchases?mode=overlap-write"
    dispatch(gateway,write_path,"write-a",HTTPClient.METHOD_POST); dispatch(gateway,write_path,"write-b",HTTPClient.METHOD_POST)
    await until("write-a"); await until("write-b")
    stats = await gateway.request("/api/v1/client-info")
    record("LOAD-08.2-T03",stats.data.counts.get(path,0)==2 and results["player-a"].data.userId!=results["player-b"].data.userId and results["write-a"].ok!=results["write-b"].ok,
        {"player_http_count":stats.data.counts.get(path,0),"distinct_players":results["player-a"].data.userId!=results["player-b"].data.userId,"write_successes":int(results["write-a"].ok)+int(results["write-b"].ok),"write_merged":false})
    close(other)
    # Both overlapping requests complete with their own path and response body.
    dispatch(gateway,"/api/v1/players/me?mode=overlap-a","overlap-a")
    dispatch(gateway,"/api/v1/players/me?mode=overlap-b","overlap-b")
    await until("overlap-a"); await until("overlap-b")
    record("PR13-A06.2-T02",results["overlap-a"].ok and results["overlap-b"].ok and results["overlap-a"].data.userId==pg_sessions.A.player.userId and results["overlap-b"].data.userId==pg_sessions.A.player.userId,{"a":results["overlap-a"].data.displayName,"b":results["overlap-b"].data.displayName})
    close(gateway)

    gateway = fresh()
    path = "/api/v1/players/me?mode=stop-retry"
    dispatch(gateway,path,"stop")
    deadline = Time.get_ticks_msec()+2000
    while for_path(path,"http_attempt").is_empty() and Time.get_ticks_msec()<deadline: await process_frame
    var stop_at := Time.get_ticks_msec()
    gateway.telemetry_context = {"cycle_id":"drain-current","phase":"cleanup"}
    gateway.end_session("",false)
    await until("stop")
    terminals = for_path(path,"http")
    record("LOAD-08.3-T02",terminals.size()==1 and terminals[0].result=="cancelled" and terminals[0].cycle_id=="cycle-first" and Time.get_ticks_msec()-stop_at<1000,{"logical":proof(terminals),"cancel_elapsed_ms":Time.get_ticks_msec()-stop_at})
    record("PR13-A06.3-T03",terminals.size()==1 and terminals[0].result=="cancelled" and terminals[0].phase=="playing",{"logical":proof(terminals),"drain_start_monotonic_ms":stop_at,"drain_end_monotonic_ms":Time.get_ticks_msec(),"business_phase_retained":true})
    close(gateway)

    gateway = fresh()
    path = "/api/v1/shop/purchases?mode=lost-write"
    var mutation: Dictionary = await gateway.request(path,HTTPClient.METHOD_POST,{"productId":"health_potion","quantity":1},[503])
    stats = await gateway.request("/api/v1/client-info")
    attempts = for_path(path,"http_attempt")
    record("LOAD-08.3-T03",mutation.ok and stats.data.fixtureMutations==1 and stats.data.writeStable and attempts.size()==2,{"fixture_mutations":stats.data.fixtureMutations,"body_and_key_stable":stats.data.writeStable,"attempts":proof(attempts),"asset_scope":"in-memory fixture only"})
    close(gateway)

    gateway = fresh()
    var baseline: Dictionary = await gateway.request("/api/v1/players/me")
    assert(baseline.ok)
    path = "/api/v1/players/me?mode=stale-get"
    dispatch(gateway,path,"stale-old")
    deadline = Time.get_ticks_msec()+3000
    while Time.get_ticks_msec()<deadline:
        stats = await gateway.request("/api/v1/client-info")
        if stats.data.get("staleCaptured",false):break
        await process_frame
    assert(stats.data.get("staleCaptured",false))
    var written: Dictionary = await gateway.request("/api/v1/players/me",HTTPClient.METHOD_PUT,{"selectedClass":"Mage","expectedVersion":baseline.data.version})
    assert(written.ok)
    dispatch(gateway,path,"stale-new")
    await until("stale-new")
    var stable_new: Dictionary = results.get("stale-new",{}).duplicate(true)
    await until("stale-old")
    stats = await gateway.request("/api/v1/client-info")
    record("LOAD-08.2-T02",stable_new.get("ok",false) and results.get("stale-old",{}).get("ok",false) and stable_new.data.version==written.data.version and results["stale-old"].data.version==baseline.data.version and stable_new==results["stale-new"] and stats.data.counts.get(path,0)==2,
        {"old_version":results["stale-old"].data.version,"new_version":stable_new.data.version,"committed_version":written.data.version,"real_profile_mutation":true,"underlying_GET_count":stats.data.counts.get(path,0),"new_result_retained":stable_new==results["stale-new"]})
    close(gateway)

    gateway = fresh(true)
    path = "/api/v1/players/me?mode=timeout"
    var timeout: Dictionary = await gateway.request(path,HTTPClient.METHOD_GET,null,[0])
    var timeout_attempts := for_path(path,"http_attempt")
    var timeout_logical := for_path(path,"http")
    path = "/api/v1/players/me?mode=decode-error"
    var invalid: Dictionary = await gateway.request(path,HTTPClient.METHOD_GET,null,[200])
    var decode_attempts := for_path(path,"http_attempt")
    var decode_logical := for_path(path,"http")
    record("LOAD-06.1-T03",not timeout.ok and not invalid.ok and timeout_attempts.size()==3 and timeout_logical.size()==1 and decode_attempts.size()==1 and decode_logical.size()==1,
        {"timeout_attempts":proof(timeout_attempts),"timeout_logical":proof(timeout_logical),"decode_attempts":proof(decode_attempts),"decode_logical":proof(decode_logical),"controlled_transport_deadline_ms":100})
    close(gateway)
    await process_frame
    var file := FileAccess.open(OS.get_environment("PR13_HTTP_REPORT"),FileAccess.WRITE)
    if file==null: quit(1); return
    file.store_string(JSON.stringify({"cases":cases,"initial_players":pg_initial,"two_actual_logins":true,"tokens_not_in_evidence":true,"transport":OS.get_environment("FANTASYCARD_LOAD_HTTP_TRANSPORT")})); file.close()
    print(JSON.stringify({"cases":cases.size(),"failed":cases.filter(func(row): return row.status!="Passed").map(func(row): return row.case_id)}))
    quit(0 if cases.all(func(row): return row.status=="Passed") else 1)
