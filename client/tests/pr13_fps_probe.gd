extends SceneTree

# Actual engine FPS/monotonic observations only; no server or gameplay conclusion.
func _initialize() -> void:
    call_deferred("measure")

func measure() -> void:
    var ticks: Array = []
    for i in range(12):
        await process_frame
        ticks.append(Time.get_ticks_usec())
    var intervals: Array = []
    for i in range(1, ticks.size()):
        intervals.append(ticks[i] - ticks[i-1])
    var result := {"pid":OS.get_process_id(),"configured_max_fps":Engine.max_fps,
        "clock":"Time.get_ticks_usec local monotonic","intervals_usec":intervals}
    var output := FileAccess.open(OS.get_environment("PR13_FPS_REPORT"), FileAccess.WRITE)
    output.store_string(JSON.stringify(result))
    output.close()
    quit(0)
