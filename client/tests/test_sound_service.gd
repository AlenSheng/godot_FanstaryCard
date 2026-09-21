extends RefCounted

func run_test() -> Dictionary:
	return load("res://tests/sound_service_checks.gd").new().run_test()
