extends SceneTree

const Proto = preload("res://network/protobuf.gd")
const Http = preload("res://network/http_protocol.gd")

var failures: Array[String] = []
var checks := 0

func _initialize() -> void:
	call_deferred("run")

func check(condition: bool, label: String) -> void:
	checks += 1
	if not condition:
		failures.append(label)

func run() -> void:
	var proto = Proto.new(true)
	var body := Http.to_wire("EnhanceEquipmentRequest", {"expectedVersion": 7, "fragmentSourceSeasonId": "season-a"})
	check(proto.encode("EnhanceEquipmentRequest", body).hex_encode() == "08071a08736561736f6e2d61", "independent request tag golden")
	var empty := proto.encode("EnhanceEquipmentRequest", Http.to_wire("EnhanceEquipmentRequest", {"expectedVersion": 7, "fragmentSourceSeasonId": ""}))
	check(empty.hex_encode() == "08071a00", "explicit empty source retains presence")
	var legacy := proto.decode_http("EnhanceEquipmentRequest", "0807".hex_decode())
	check(legacy.expectedVersion == 7 and legacy.fragmentSourceSeasonId == null, "legacy request remains historical wallet")
	var decoded := proto.decode_http("EnhanceResult", "10642208736561736f6e2d61280b".hex_decode())
	check(proto.error.is_empty() and decoded.equipmentFragments == 100, "independent response golden")
	check(decoded.fragmentSourceSeasonId == "season-a" and decoded.fragmentWalletVersion == 11, "wallet identity reaches presentation")
	legacy = proto.decode_http("EnhanceResult", "1064".hex_decode())
	check(legacy.fragmentSourceSeasonId == null and legacy.fragmentWalletVersion == null, "legacy response has no inferred season")
	var large := {"equipment_fragments": 92, "fragment_source_season_id": "season-a", "fragment_wallet_version": 9007199254740993}
	decoded = proto.decode_http("EnhanceResult", proto.encode("EnhanceResult", large))
	check(decoded.fragmentWalletVersion is int and decoded.fragmentWalletVersion == 9007199254740993, "wallet version remains exact int64")
	var quote := proto.decode_http("EnhancementQuoteResponse", proto.encode("EnhancementQuoteResponse", {"available_fragments": 100, "fragment_source_season_id": "season-a", "fragment_wallet_version": 2}))
	check(quote.availableFragments == 100 and quote.fragmentSourceSeasonId == "season-a" and quote.fragmentWalletVersion == 2, "quote carries selected wallet metadata")
	var route := Http.route("/api/v1/class-weapons/Mage/enhancement-quote?fragmentSourceSeasonId=season-a", HTTPClient.METHOD_GET)
	check(route.get("response") == "EnhancementQuoteResponse", "wallet query retains canonical route")
	var inventory := proto.decode_http("InventoryResponse", "22180a0c416374697665536561736f6e1208736561736f6e2d61".hex_decode())
	check(inventory.scope.state == "ActiveSeason" and inventory.scope.seasonId == "season-a" and not inventory.scope.readOnly, "independent inventory scope golden")
	var bootstrap := proto.decode_http("BootstrapResponse", "9201080a06436c6f736564".hex_decode())
	check(bootstrap.season.state == "Closed" and not bootstrap.season.hasJoined and bootstrap.season.wallet == null, "independent closed-season bootstrap golden")
	print(JSON.stringify({"ok": failures.is_empty(), "checks": checks, "failures": failures}))
	quit(0 if failures.is_empty() else 1)
