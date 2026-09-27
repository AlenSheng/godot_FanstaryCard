shader_type canvas_item;

uniform bool grayscale = false;
uniform bool reframe = false;
uniform bool monster_reframe = false;
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
	} else if (monster_reframe) {
		// The monster texture has a short portrait and extra transparent space
		// above its frame. Match the regular card's 4..363 visible bounds and
		// put its divider beneath the shared 285-pixel portrait.
		float y = min(uv.y * 376.0, 363.0);
		if (y < 4.0) {
			y = y * 16.5 / 4.0;
		} else if (y < 296.0) {
			y = mix(16.5, 236.0, (y - 4.0) / 292.0);
		} else {
			y = mix(236.0, 376.0, (y - 296.0) / 67.0);
		}
		uv.y = y / 376.0;
	}
	vec4 pixel = texture(TEXTURE, uv) * vertex_tint;
	if (monster_reframe && UV.y * 376.0 > 363.0) {
		pixel = vec4(0.0);
	}
	if (grayscale) {
		float luminance = dot(pixel.rgb, vec3(0.299, 0.587, 0.114));
		pixel.rgb = vec3(luminance * 0.86);
	}
	COLOR = pixel;
}
