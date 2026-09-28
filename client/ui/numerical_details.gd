extends RefCounted

const P = preload("res://ui/palette.gd")
const Model = preload("res://ui/equipment_compare_model.gd")
const TEXT := {
	"zh-CN": {"title":"实际数值收益", "hint":"装备模拟预览；最终以服务端为准。非盾职业不享受载壁减伤。", "upgrade":"此装备强化前 → 强化后（假设穿戴）", "compare":"当前穿戴 → 替换后", "columns":"属性：理论值 / 生效值 / 超上限；随后为变化", "interval":"抽牌间隔（秒，越低越快）", "inactive":"未激活", "weapon":"专属盾余量：%d / 10", "unsupported":"红装独有词缀未开放，本面板不推算其效果。"},
	"zh-TW": {"title":"實際數值收益", "hint":"裝備模擬預覽；最終以伺服器為準。非盾職業不享受載壁減傷。", "upgrade":"此裝備強化前 → 強化後（假設穿戴）", "compare":"目前穿戴 → 替換後", "columns":"屬性：理論值 / 生效值 / 超上限；隨後為變化", "interval":"抽牌間隔（秒，越低越快）", "inactive":"未啟動", "weapon":"專屬盾餘量：%d / 10", "unsupported":"紅裝專有詞綴未開放，本面板不推算其效果。"},
	"en": {"title":"Effective numerical gains", "hint":"Equipment-only preview; the server is authoritative. Bulwark reduction only benefits Guardians.", "upgrade":"Before → after upgrade (assuming equipped)", "compare":"Current loadout → replacement", "columns":"Stat: raw / effective / capped excess; then effective change", "interval":"Draw interval (seconds; lower is faster)", "inactive":"Inactive", "weapon":"Weapon shield remainder: %d / 10", "unsupported":"Red unique affixes are not available; this panel does not estimate them."},
	"ja": {"title":"実際の数値変化", "hint":"装備のみの予測。最終結果はサーバーで確定。軽減は盾職のみ。", "upgrade":"強化前 → 強化後（装備時）", "compare":"現在の装備 → 交換後", "columns":"属性：理論値 / 有効値 / 上限超過；有効値の変化", "interval":"ドロー間隔（秒・短いほど速い）", "inactive":"未発動", "weapon":"専用盾の端数：%d / 10", "unsupported":"赤装備固有効果は未開放のため計算しません。"},
	"ko": {"title":"실제 수치 변화", "hint":"장비만의 예상치이며 서버가 최종 결정합니다. 피해 감소는 수호자에게만 적용됩니다.", "upgrade":"강화 전 → 강화 후 (장착 가정)", "compare":"현재 장비 → 교체 후", "columns":"능력치: 이론 / 유효 / 상한 초과; 유효 변화", "interval":"드로우 간격 (초, 낮을수록 빠름)", "inactive":"비활성", "weapon":"전용 보호막 잔여: %d / 10", "unsupported":"빨간 장비 고유 효과는 아직 계산하지 않습니다."}
}

static func text(key: String) -> String:
	var lang: String = P.language()
	var words: Dictionary = TEXT.get(lang, TEXT.get(lang.get_slice("-", 0), TEXT.en))
	return str(words.get(key, key))

# All values are an equipment-only view; temporary acceleration is intentionally excluded.
static func inspect(loadout: Array, hero_class: String) -> Dictionary:
	var raw: Dictionary = Model.aggregate_attributes(loadout)
	var result := {}
	for key in raw:
		var value: float = float(raw[key])
		var effective: float = minf(0.60, value) if str(key).begins_with("resistance_") else value
		result[key] = {"raw":value, "effective":effective, "excess":maxf(0, value - effective)}
	var modifier: float = float(raw.get("draw_interval", 0.0))
	var seconds: float = 4.0 * (1.0 + modifier)
	var effective_seconds: float = clampf(seconds, 1.8, 6.0)
	result["interval_seconds"] = {"raw":seconds, "effective":effective_seconds, "excess":maxf(0.0, effective_seconds - seconds)}
	for kind in Model.AFFIXES:
		var state: Dictionary = Model.set_state(loadout, kind)
		var contributions := {}
		for field in Model.AFFIX_FIELDS[kind]: contributions[field] = 0.0
		for item in loadout:
			var contribution: Dictionary = Model.affix_contributions(item)
			if contribution.kind == kind:
				for field in contributions: contributions[field] += float(contribution.values.get(field, 0.0))
		var multiple: float = float(Model.MULTIPLIERS.get(clampi(int(state.count), 2, 5), 1.0))
		for field in contributions:
			var potential: float = floorf(float(contributions[field]) * 100.0 * multiple) / 100.0
			var effective: float = float(state.values.get(field, 0.0))
			if field == "bulwark_reduction_percent" and hero_class != "Guardian": effective = 0.0
			result[field] = {"raw":potential, "effective":effective, "excess":maxf(0, potential - effective), "active":state.active}
	return result

static func show_compare(host: Control, loadout: Array, selected: Dictionary, upgrade: bool = false) -> void:
	var before: Array = Model.replace_slot(loadout, selected) if upgrade else loadout
	var next: Dictionary = selected.duplicate(true)
	if upgrade:
		var gear: Dictionary = next.get("equipment", next)
		gear["level"] = mini(5, int(gear.get("level", 0)) + 1)
	var after: Array = Model.replace_slot(loadout, next)
	var lines := PackedStringArray([text("upgrade") if upgrade else text("compare"), text("hint"), text("columns"), ""])
	var unsupported := false
	for item in before + after:
		if str(Model.gear(item).get("quality", "")) == "Red": unsupported = true
	if unsupported:
		lines.append(text("unsupported"))
	else:
		var old: Dictionary = inspect(before, Game.hero_class)
		var current: Dictionary = inspect(after, Game.hero_class)
		var keys: Array = old.keys()
		for key in current.keys():
			if key not in keys: keys.append(key)
		keys.sort()
		for key in keys:
			if key == "draw_interval": continue
			var a: Dictionary = old.get(key, {"raw":0.0,"effective":0.0,"excess":0.0})
			var b: Dictionary = current.get(key, {"raw":0.0,"effective":0.0,"excess":0.0})
			if is_zero_approx(float(a.raw)) and is_zero_approx(float(b.raw)): continue
			var scale: float = 1.0 if key == "interval_seconds" else 100.0
			var label: String = text("interval") if key == "interval_seconds" else P.word(str(key))
			lines.append("%s\n  %.2f / %.2f / %.2f → %.2f / %.2f / %.2f  (%+.2f)" % [label, float(a.raw)*scale, float(a.effective)*scale, float(a.excess)*scale, float(b.raw)*scale, float(b.effective)*scale, float(b.excess)*scale, (float(b.effective)-float(a.effective))*scale])
	show_lines(host, lines)

static func show_remainder(host: Control) -> void:
	var state: Dictionary = Game.room.get("player", {}).get("numerical_state", {})
	show_lines(host, PackedStringArray([text("weapon") % int(state.get("guardian_remainder_tenths", 0)), str(state.get("guardian_policy", "CurrentSteps"))]))

static func show_lines(host: Control, lines: PackedStringArray) -> void:
	var dialog := AcceptDialog.new()
	dialog.title = text("title")
	dialog.min_size = Vector2i(850, 500)
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(820, 460)
	var label := Label.new()
	label.text = "\n".join(lines)
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(label)
	dialog.add_child(scroll)
	host.add_child(dialog)
	dialog.confirmed.connect(dialog.queue_free)
	dialog.canceled.connect(dialog.queue_free)
	dialog.popup_centered()
