extends SceneTree
const Reusable = preload("res://network/reusable_http_client.gd")
const Gateway = preload("res://network/gateway.gd")
const Http = preload("res://network/http_protocol.gd")
var observations: Array = []
var cases: Array = []

func _initialize() -> void: call_deferred("run")
func digest(data: PackedByteArray) -> String:
    var hash := HashingContext.new()
    assert(hash.start(HashingContext.HASH_SHA256)==OK)
    if not data.is_empty(): assert(hash.update(data)==OK)
    return hash.finish().hex_encode()
func record(cid: String, passed: bool, actual: Dictionary) -> void:
    cases.append({"case_id":cid,"executed":true,"status":"Passed" if passed else "Failed","actual":actual,"profiles_executed":["POSTGRES"],"scope":"Actual production transport and authenticated full Program/PostgreSQL response bytes behind owned TLS framing faults; no capacity/performance benefit claim"})
func raw_request(client: RefCounted, origin: String, mode: String, token: String) -> Array:
    var result: Array = await client.request(self,origin,"/api/v1/players/me?mode="+mode,HTTPClient.METHOD_GET,PackedStringArray(["Accept: application/protobuf","Authorization: Bearer "+token]),PackedByteArray(),5000)
    observations.append({"mode":mode,"result":result[0],"status":result[1],"bytes":result[3].size(),"body_sha256":digest(result[3]),"reused":result[4]})
    return result
func fail_setup(step: String, result: Dictionary) -> void:
    FileAccess.open(OS.get_environment("PR13_TLS_REPORT"),FileAccess.WRITE).store_string(JSON.stringify({"ok":false,"setup_failed":step,"status":result.get("status",0),"error":result.get("error","")}))
    quit(1)
func run() -> void:
    var origin: String = OS.get_environment("FANTASYCARD_SERVER_URL")
    var gateway: Node = Gateway.new()
    gateway.persist_session = false
    root.add_child(gateway)
    gateway.set_process(false)
    gateway.base_url = origin
    gateway.use_reusable_http = false
    var login: Dictionary = await gateway.request("/api/v1/auth/local",HTTPClient.METHOD_POST,{"deviceId":"tls-framing-device","displayName":"test_tls_pg_A"})
    if not login.ok: fail_setup("real_TLS_login",login);return
    if not gateway.accept_session(login.data.accessToken,login.data.expiresAt,login.data.player.userId): fail_setup("accept_actual_session",{});return
    var fallback: Dictionary = await gateway.request("/api/v1/players/me")
    if not fallback.ok: fail_setup("original_per_request_TLS_control",fallback);return
    var client := Reusable.new()
    var expected: Array = await raw_request(client,origin,"expected",str(login.data.accessToken))
    var expected_ok: bool = expected[0]==HTTPRequest.RESULT_SUCCESS and expected[1]==200
    if not expected_ok: fail_setup("original_reusable_TLS_control",{});return
    var original: PackedByteArray = expected[3]
    var closed: Array = await raw_request(client,origin,"close-length",str(login.data.accessToken))
    var reconnected: Array = await raw_request(client,origin,"after-close",str(login.data.accessToken))
    var eof_closed: Array = await raw_request(client,origin,"close-body",str(login.data.accessToken))
    var chunked: Array = await raw_request(client,origin,"complete-chunk",str(login.data.accessToken))
    var full_ok: bool = [closed,reconnected,eof_closed,chunked].all(func(r):return r[0]==HTTPRequest.RESULT_SUCCESS and r[1]==200 and r[3]==original)
    record("LOAD-08.1-T01",full_ok and not bool(reconnected[4]) and fallback.data.userId==login.data.player.userId,{"complete_original_body_after_peer_close":full_ok,"next_request_reconnected":not bool(reconnected[4]),"original_body_bytes":original.size(),"original_body_sha256":digest(original),"original_per_request_TLS_control_passed":fallback.ok})
    var truncated: Array = await raw_request(client,origin,"truncated-length",str(login.data.accessToken))
    var truncated_chunk: Array = await raw_request(client,origin,"truncated-chunk",str(login.data.accessToken))
    var recovery: Array = await raw_request(client,origin,"after-truncation",str(login.data.accessToken))
    var failures_ok: bool = [truncated,truncated_chunk].all(func(r):return r[0]!=HTTPRequest.RESULT_SUCCESS and r[3].is_empty())
    record("LOAD-08.1-T02",failures_ok and recovery[0]==HTTPRequest.RESULT_SUCCESS and recovery[3]==original,{"incomplete_content_length_and_chunked_bodies_rejected":failures_ok,"no_partial_success_body":truncated[3].is_empty() and truncated_chunk[3].is_empty(),"next_original_body_recovered":recovery[3]==original})
    var oversize: Array = await raw_request(client,origin,"oversized-optional",str(login.data.accessToken))
    var invalid: Array = await raw_request(client,OS.get_environment("PR13_TLS_UNTRUSTED_ORIGIN"),"invalid-cert",str(login.data.accessToken))
    var final_valid: Array = await raw_request(client,origin,"after-invalid",str(login.data.accessToken))
    var invalid_ok: bool = invalid[0]!=HTTPRequest.RESULT_SUCCESS and invalid[3].is_empty()
    var oversize_ok: bool = oversize[0]==HTTPRequest.RESULT_BODY_SIZE_LIMIT_EXCEEDED and oversize[3].is_empty()
    record("LOAD-08.1-T03",invalid_ok and oversize_ok and final_valid[0]==HTTPRequest.RESULT_SUCCESS and final_valid[3]==original,{"untrusted_TLS_rejected_without_body":invalid_ok,"original_2MiB_limit_retained":oversize_ok,"valid_TLS_still_verified_after_negative":final_valid[3]==original,"insecure_TLS_options_used":false})
    client.close()
    gateway.end_session("",false)
    gateway.queue_free()
    await process_frame
    var ok: bool = cases.size()==3 and cases.all(func(r):return r.status=="Passed")
    FileAccess.open(OS.get_environment("PR13_TLS_REPORT"),FileAccess.WRITE).store_string(JSON.stringify({"ok":ok,"cases":cases,"observations":observations,"actual_player_id":login.data.player.userId,"original_profile_version":fallback.data.version,"actual_authenticated_TLS_login":true,"credentials_not_in_evidence":true}))
    quit(0 if ok else 1)
