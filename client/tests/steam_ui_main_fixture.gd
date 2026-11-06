extends "res://ui/main.gd"

var fixture_ready := false

func _steam_unavailable_reason() -> String:
	return "" if fixture_ready else "Owned missing Steam fixture"
