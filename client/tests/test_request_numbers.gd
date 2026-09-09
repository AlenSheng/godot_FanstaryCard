extends RefCounted

func run_test() -> Dictionary:
	var Gateway = load("res://network/gateway.gd")
	var response: Dictionary = JSON.parse_string('{"expectedVersion":7,"quantity":2,"priceGold":100}')
	var request: Dictionary = Gateway.normalize_request(response)
	var encoded := JSON.stringify(request)
	return {"ok": typeof(request.expectedVersion) == TYPE_INT and not ".0" in encoded and response.expectedVersion == 7.0, "message": "REST integer DTOs serialize as integers without mutating source"}
