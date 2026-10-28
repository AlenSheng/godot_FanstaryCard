extends SceneTree
const Proto = preload("res://network/protobuf.gd")
const Http = preload("res://network/http_protocol.gd")
func _initialize():
 var bytes = FileAccess.get_file_as_bytes("res://bootstrap.pb")
 var text = FileAccess.get_file_as_string("res://bootstrap.json")
 var proto = Proto.new(true)
 var wire = proto.decode("BootstrapResponse", bytes)
 var dto = JSON.parse_string(text)
 var rows = []
 for operation in ["protobuf_decode", "protobuf_encode", "json_decode", "json_encode"]:
  for i in range(5): execute(operation, proto, bytes, wire, text, dto)
  var start = Time.get_ticks_usec()
  for i in range(30): execute(operation, proto, bytes, wire, text, dto)
  rows.append({"operation":operation,"iterations":30,"main_thread_us_per_operation":float(Time.get_ticks_usec()-start)/30.0})
 print(JSON.stringify({"godot":Engine.get_version_info().string,"protobuf_bytes":bytes.size(),"json_bytes":text.to_utf8_buffer().size(),"compression":"none","measurements":rows}))
 quit()
func execute(operation, proto, bytes, wire, text, dto):
 match operation:
  "protobuf_decode": return Http.from_wire("BootstrapResponse", proto.decode("BootstrapResponse", bytes))
  "protobuf_encode": return proto.encode("BootstrapResponse", Http.to_wire("BootstrapResponse",dto))
  "json_decode": return JSON.parse_string(text)
  "json_encode": return JSON.stringify(dto)
