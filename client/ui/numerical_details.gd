extends RefCounted

const P = preload("res://ui/palette.gd")
const Model = preload("res://ui/equipment_compare_model.gd")
const GUARDIAN_REMAINDER_RULES := {
	"zh-CN": ["余量按十分之一确定积累，并非随机触发。只有成功出牌才更新；预览、重复请求或被拒绝的操作不增加余量。", "已经满盾或牌面护盾为零时保留余量。本次成功出牌恰好补满或超过护盾上限时，余量清零。", "离开当前格子时，护盾和余量同时清空。"],
	"zh-TW": ["餘量按十分之一確定累積，並非隨機觸發。只有成功出牌才更新；預覽、重複請求或被拒絕的操作不增加餘量。", "已經滿盾或牌面護盾為零時保留餘量。本次成功出牌恰好補滿或超過護盾上限時，餘量歸零。", "離開目前格子時，護盾和餘量同時清空。"],
	"en": ["Remainder accumulates deterministically in tenths, without a random trigger. Only a successful play updates it; previews, duplicate requests and rejected actions do not add remainder.", "An already full shield or a card with zero shield keeps the remainder. A successful play that exactly fills or exceeds the shield cap clears it.", "Leaving the current cell clears both shield and remainder."],
	"ja": ["端数は10分の1単位で確定的に蓄積し、ランダム発動ではありません。成功したプレイだけで更新され、プレビュー・重複要求・拒否された操作では増えません。", "既にシールドが上限に達している場合や、カードのシールドがゼロの場合は端数を保持します。成功したプレイで上限にちょうど達するか超えた場合は端数を消去します。", "現在のマスを離れると、シールドと端数を両方消去します。"],
	"ko": ["잔여량은 무작위 발동 없이 10분의 1 단위로 확정적으로 누적됩니다. 성공한 카드 사용만 갱신하며 미리보기, 중복 요청, 거부된 행동은 잔여량을 늘리지 않습니다.", "이미 보호막이 가득 찼거나 카드 보호막이 0이면 잔여량을 유지합니다. 성공한 카드 사용으로 한도에 정확히 도달하거나 초과하면 잔여량을 지웁니다.", "현재 칸을 떠나면 보호막과 잔여량이 함께 사라집니다."]
}
const GUARDIAN_IMPACT := {
	"zh-CN": {"title":"武器额外护盾：逐档对照", "columns":"武器等级 | 当前台阶 | 小数均值 | 变化", "row":"+%d | %.1f | %.1f | %+.1f", "warning":"+2、+4 档的武器额外盾均值下降；+1 改善不能抵消这些档位的下降。", "scope":"仅为武器额外盾均值；实际获得的盾受生命、牌面取整和护盾上限影响，不代表所有等级的生存提升。"},
	"zh-TW": {"title":"武器額外護盾：逐檔對照", "columns":"武器等級 | 目前階梯 | 小數均值 | 變化", "row":"+%d | %.1f | %.1f | %+.1f", "warning":"+2、+4 檔武器額外盾均值下降；+1 改善不能抵銷這些檔位的下降。", "scope":"僅為武器額外盾均值；實際護盾受生命、牌面取整與護盾上限影響，不代表所有等級的生存提升。"},
	"en": {"title":"Extra weapon shield: each level", "columns":"Weapon level | Current steps | Fractional mean | Change", "row":"+%d | %.1f | %.1f | %+.1f", "warning":"Levels +2 and +4 have lower mean extra weapon shield. The gain at +1 does not offset those declines.", "scope":"Weapon bonus means only. Health, card rounding and the shield cap affect usable shield; this does not imply better survival at every level."},
	"ja": {"title":"武器追加シールド：レベル別比較", "columns":"武器レベル | 現行段階 | 小数平均 | 変化", "row":"+%d | %.1f | %.1f | %+.1f", "warning":"+2・+4 の武器追加シールド平均は低下します。+1 の改善で他のレベルの低下は相殺されません。", "scope":"武器追加分の平均のみ。HP、カードの切り捨て、シールド上限が有効量に影響し、全レベルの生存改善を意味しません。"},
	"ko": {"title":"무기 추가 보호막: 레벨별 비교", "columns":"무기 레벨 | 기존 단계 | 소수 평균 | 변화", "row":"+%d | %.1f | %.1f | %+.1f", "warning":"+2, +4 레벨의 무기 추가 보호막 평균은 감소합니다. +1의 개선이 다른 레벨의 감소를 상쇄하지 않습니다.", "scope":"무기 추가량 평균만 표시합니다. 체력, 카드 버림, 보호막 한도가 유효량에 영향을 주며 모든 레벨의 생존 향상을 뜻하지 않습니다."}
}
const TEXT := {
	"zh-CN": {"title":"实际数值收益", "hint":"装备模拟预览；最终以服务端为准。非盾职业不享受载壁减伤。", "upgrade":"此装备强化前 → 强化后（假设穿戴）", "compare":"当前穿戴 → 替换后", "columns":"属性：理论值 / 生效值 / 超上限；随后为变化", "interval":"抽牌间隔（秒，越低越快）", "inactive":"未激活", "weapon":"专属盾余量：%d / 10", "unsupported":"红装独有词缀未开放，本面板不推算其效果。"},
	"zh-TW": {"title":"實際數值收益", "hint":"裝備模擬預覽；最終以伺服器為準。非盾職業不享受載壁減傷。", "upgrade":"此裝備強化前 → 強化後（假設穿戴）", "compare":"目前穿戴 → 替換後", "columns":"屬性：理論值 / 生效值 / 超上限；隨後為變化", "interval":"抽牌間隔（秒，越低越快）", "inactive":"未啟動", "weapon":"專屬盾餘量：%d / 10", "unsupported":"紅裝專有詞綴未開放，本面板不推算其效果。"},
	"en": {"title":"Effective numerical gains", "hint":"Equipment-only preview; the server is authoritative. Bulwark reduction only benefits Guardians.", "upgrade":"Before → after upgrade (assuming equipped)", "compare":"Current loadout → replacement", "columns":"Stat: raw / effective / capped excess; then effective change", "interval":"Draw interval (seconds; lower is faster)", "inactive":"Inactive", "weapon":"Weapon shield remainder: %d / 10", "unsupported":"Red unique affixes are not available; this panel does not estimate them."},
	"ja": {"title":"実際の数値変化", "hint":"装備のみの予測。最終結果はサーバーで確定。軽減は盾職のみ。", "upgrade":"強化前 → 強化後（装備時）", "compare":"現在の装備 → 交換後", "columns":"属性：理論値 / 有効値 / 上限超過；有効値の変化", "interval":"ドロー間隔（秒・短いほど速い）", "inactive":"未発動", "weapon":"専用盾の端数：%d / 10", "unsupported":"赤装備固有効果は未開放のため計算しません。"},
	"ko": {"title":"실제 수치 변화", "hint":"장비만의 예상치이며 서버가 최종 결정합니다. 피해 감소는 수호자에게만 적용됩니다.", "upgrade":"강화 전 → 강화 후 (장착 가정)", "compare":"현재 장비 → 교체 후", "columns":"능력치: 이론 / 유효 / 상한 초과; 유효 변화", "interval":"드로우 간격 (초, 낮을수록 빠름)", "inactive":"비활성", "weapon":"전용 보호막 잔여: %d / 10", "unsupported":"빨간 장비 고유 효과는 아직 계산하지 않습니다."}
}
const CAP_TEXT := {
	"zh-CN": {"not_applicable":"此职业不适用（不是超过上限）", "inactive_affix":"套装未激活（不是超过上限）", "resistance_stage":"元素抗性最高 60%；超过上限的部分不会提高生效抗性。", "draw_stage":"这里只显示装备抽牌间隔。战斗中先合并装备和临时加速，再限制到 1.8–6 秒；PVE 抽牌阻断转加速在限制后将间隔减半，结束后恢复。", "shield_stage":"护盾上限是职业基础生命的一半；请求护盾、实际获得和溢出分别统计。"},
	"zh-TW": {"not_applicable":"此職業不適用（不是超過上限）", "inactive_affix":"套裝未啟動（不是超過上限）", "resistance_stage":"元素抗性最高 60%；超過上限的部分不會提高生效抗性。", "draw_stage":"這裡只顯示裝備抽牌間隔。戰鬥中先合併裝備和暫時加速，再限制到 1.8–6 秒；PVE 抽牌阻斷轉加速在限制後將間隔減半，結束後恢復。", "shield_stage":"護盾上限是職業基礎生命的一半；請求護盾、實際獲得和溢出分別統計。"},
	"en": {"not_applicable":"Not applicable to this class (not capped excess)", "inactive_affix":"Set inactive (not capped excess)", "resistance_stage":"Element resistance is capped at 60%; excess adds no effective resistance.", "draw_stage":"This panel shows equipment-only draw intervals. Combat combines equipment and temporary speed, then clamps to 1.8–6 seconds. PVE draw-block conversion halves the interval after that clamp and expires normally.", "shield_stage":"Shield is capped at half the class base health. Requested, effective and overflow shield are counted separately."},
	"ja": {"not_applicable":"このクラスには適用されません（上限超過ではありません）", "inactive_affix":"セット未発動（上限超過ではありません）", "resistance_stage":"属性耐性の上限は60%。超過分で有効耐性は増えません。", "draw_stage":"装備のみのドロー間隔を表示。戦闘では装備と一時加速を合わせて1.8〜6秒に制限し、その後PVEのドロー阻害変換で間隔を半減します。終了すると元に戻ります。", "shield_stage":"シールド上限はクラス基本HPの半分。要求量・実効量・超過量は別々に記録します。"},
	"ko": {"not_applicable":"이 직업에는 적용되지 않음 (상한 초과가 아님)", "inactive_affix":"세트 비활성 (상한 초과가 아님)", "resistance_stage":"속성 저항 상한은 60%이며 초과분은 유효 저항을 늘리지 않습니다.", "draw_stage":"장비만의 드로우 간격입니다. 전투에서는 장비와 임시 가속을 합쳐 1.8~6초로 제한한 뒤 PVE 드로우 차단 변환이 간격을 절반으로 줄입니다. 종료되면 복원됩니다.", "shield_stage":"보호막 상한은 직업 기본 체력의 절반입니다. 요청량, 유효량, 초과량을 따로 기록합니다."}
}
const STAT_TEXT := {
	"zh-CN": {"damage":"%s元素增伤", "resistance":"%s元素抗性", "bulwark_shield_percent":"载壁 · 护盾增益", "bulwark_reduction_percent":"载壁 · 减伤", "piercing_percent":"破击 · 附加直伤", "vitality_heal_percent":"生息 · 回复增益", "vitality_overcap_percent":"生息 · 生命上限增益", "forced_escape":"强制逃脱"},
	"zh-TW": {"damage":"%s元素增傷", "resistance":"%s元素抗性", "bulwark_shield_percent":"載壁 · 護盾增益", "bulwark_reduction_percent":"載壁 · 減傷", "piercing_percent":"破擊 · 附加直傷", "vitality_heal_percent":"生息 · 回復增益", "vitality_overcap_percent":"生息 · 生命上限增益", "forced_escape":"強制逃脫"},
	"en": {"damage":"%s Damage Bonus", "resistance":"%s Resistance", "bulwark_shield_percent":"Bulwark · Shield Bonus", "bulwark_reduction_percent":"Bulwark · Damage Reduction", "piercing_percent":"Piercing · Bonus Direct Damage", "vitality_heal_percent":"Vitality · Healing Bonus", "vitality_overcap_percent":"Vitality · Max Health Bonus", "forced_escape":"Forced Escape"},
	"ja": {"damage":"%s属性ダメージ増加", "resistance":"%s属性耐性", "bulwark_shield_percent":"防壁 · シールド増加", "bulwark_reduction_percent":"防壁 · ダメージ軽減", "piercing_percent":"貫通 · 追加直接ダメージ", "vitality_heal_percent":"活力 · 回復増加", "vitality_overcap_percent":"活力 · 最大HP増加", "forced_escape":"強制脱出"},
	"ko": {"damage":"%s 속성 피해 증가", "resistance":"%s 속성 저항", "bulwark_shield_percent":"방벽 · 보호막 증가", "bulwark_reduction_percent":"방벽 · 피해 감소", "piercing_percent":"관통 · 추가 직접 피해", "vitality_heal_percent":"생명력 · 회복 증가", "vitality_overcap_percent":"생명력 · 최대 체력 증가", "forced_escape":"강제 탈출"}
}

static func stat_name(key: String) -> String:
	if key == "interval_seconds": return text("interval")
	var language: String = P.language()
	var words: Dictionary = STAT_TEXT.get(language, STAT_TEXT.get(language.get_slice("-", 0), STAT_TEXT.en))
	for prefix in ["damage_", "resistance_"]:
		if key.begins_with(prefix): return str(words[prefix.trim_suffix("_")]) % P.word(key.trim_prefix(prefix))
	return str(words.get(key, P.word(key)))

static func text(key: String) -> String:
	var lang: String = P.language()
	var words: Dictionary = TEXT.get(lang, TEXT.get(lang.get_slice("-", 0), TEXT.en))
	var cap_words: Dictionary = CAP_TEXT.get(lang, CAP_TEXT.get(lang.get_slice("-", 0), CAP_TEXT.en))
	return str(words.get(key, cap_words.get(key, key)))

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
			var applicable: bool = field != "bulwark_reduction_percent" or hero_class == "Guardian"
			if not applicable: effective = 0.0
			var status := "NotApplicable" if not applicable else ("Active" if bool(state.active) else "Inactive")
			result[field] = {"raw":potential, "effective":effective, "excess":maxf(0, potential - effective) if applicable and bool(state.active) else 0.0, "active":state.active, "applicable":applicable, "status":status, "inactive_amount":potential if applicable and not bool(state.active) else 0.0, "not_applicable_amount":potential if not applicable else 0.0}
	return result

static func show_compare(host: Control, loadout: Array, selected: Dictionary, upgrade: bool = false) -> void:
	var before: Array = Model.replace_slot(loadout, selected) if upgrade else loadout
	var next: Dictionary = selected.duplicate(true)
	if upgrade:
		var gear: Dictionary = next.get("equipment", next)
		gear["level"] = mini(5, int(gear.get("level", 0)) + 1)
	var after: Array = Model.replace_slot(loadout, next)
	var lines := PackedStringArray([text("upgrade") if upgrade else text("compare"), text("hint"), text("columns"), ""])
	lines.append(text("resistance_stage"))
	lines.append(text("draw_stage"))
	lines.append(text("shield_stage"))
	lines.append("")
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
			var label: String = stat_name(str(key))
			lines.append("%s\n  %.2f / %.2f / %.2f → %.2f / %.2f / %.2f  (%+.2f)" % [label, float(a.raw)*scale, float(a.effective)*scale, float(a.excess)*scale, float(b.raw)*scale, float(b.effective)*scale, float(b.excess)*scale, (float(b.effective)-float(a.effective))*scale])
			if str(b.get("status", "Active")) == "NotApplicable": lines.append(text("not_applicable"))
			elif str(b.get("status", "Active")) == "Inactive": lines.append(text("inactive_affix"))
	show_lines(host, lines)

static func show_remainder(host: Control) -> void:
	var state: Dictionary = Game.room.get("player", {}).get("numerical_state", {})
	var lines := PackedStringArray([text("weapon") % int(state.get("guardian_remainder_tenths", 0))])
	if state.get("guardian_policy", "CurrentSteps") == "FractionalRemainder":
		var labels: Dictionary = GUARDIAN_IMPACT.get(P.language(), GUARDIAN_IMPACT["zh-CN"])
		for rule in GUARDIAN_REMAINDER_RULES.get(P.language(), GUARDIAN_REMAINDER_RULES["zh-CN"]):
			lines.append(str(rule))
		lines.append("")
		lines.append(labels.title)
		lines.append(labels.columns)
		var current := [1.0, 1.0, 2.0, 2.0, 3.0, 3.0]
		var mean := [1.0, 1.4, 1.8, 2.2, 2.6, 3.0]
		for level in range(6):
			lines.append(labels.row % [level, current[level], mean[level], mean[level] - current[level]])
		lines.append("")
		lines.append(labels.warning)
		lines.append(labels.scope)
	show_lines(host, lines)

static func show_lines(host: Control, lines: PackedStringArray) -> void:
	var dialog := AcceptDialog.new()
	dialog.title = text("title")
	var dialog_theme := P.theme()
	dialog_theme.default_font_size = 26
	dialog_theme.set_stylebox("panel", "AcceptDialog", P.box(Color("10272e"), P.GOLD))
	var window_frame := P.box(Color("10272e"), P.GOLD)
	window_frame.set_expand_margin(SIDE_TOP, 36)
	window_frame.content_margin_top = 36
	dialog_theme.set_stylebox("embedded_border", "Window", window_frame)
	dialog_theme.set_stylebox("embedded_unfocused_border", "Window", window_frame.duplicate())
	dialog_theme.set_font("title_font", "Window", P.font("title"))
	dialog_theme.set_font_size("title_font_size", "Window", 28)
	dialog_theme.set_color("title_color", "Window", P.GOLD)
	dialog.theme = dialog_theme
	var available := host.get_viewport_rect().size
	var popup_size := Vector2i(mini(1320, int(available.x) - 96), mini(860, int(available.y) - 96))
	dialog.min_size = Vector2i(mini(1080, popup_size.x), mini(640, popup_size.y))
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(popup_size.x - 64, popup_size.y - 128)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	var label := Label.new()
	label.text = "\n".join(lines)
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(label)
	dialog.add_child(scroll)
	host.add_child(dialog)
	dialog.get_ok_button().text = P.localized("confirm")
	dialog.confirmed.connect(dialog.queue_free)
	dialog.canceled.connect(dialog.queue_free)
	dialog.popup_centered(popup_size)
