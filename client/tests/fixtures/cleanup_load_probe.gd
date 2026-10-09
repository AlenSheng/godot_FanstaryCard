extends "res://tests/gameplay_load_client.gd"

# A transport contract fixture invokes the real cleanup method explicitly.
# It does not start the production login/expedition loop during construction.
func _ready() -> void:
	Game = get_node("/root/Game")
