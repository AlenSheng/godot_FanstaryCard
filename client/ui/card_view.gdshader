shader_type canvas_item;

uniform bool grayscale = false;
uniform bool reframe = false;
varying vec4 vertex_tint;

void vertex() {
	vertex_tint = COLOR;
}

void fragment() {
	vec2 uv = UV;
	if (reframe) {
		// Retain the existing frame art while giving its portrait a 2:3 window.
		float y = uv.y * 376.0;
		if (y < 26.0) {
			y = y * 38.0 / 26.0;
		} else if (y < 296.0) {
			y = mix(38.0, 246.0, (y - 26.0) / 270.0);
		} else {
			y = mix(246.0, 376.0, (y - 296.0) / 80.0);
		}
		uv.y = y / 376.0;
	}
	vec4 pixel = texture(TEXTURE, uv) * vertex_tint;
	if (grayscale) {
		float luminance = dot(pixel.rgb, vec3(0.299, 0.587, 0.114));
		pixel.rgb = vec3(luminance * 0.86);
	}
	COLOR = pixel;
}
