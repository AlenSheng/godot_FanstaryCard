extends RefCounted

const P = preload("res://ui/palette.gd")
const CardDetails = preload("res://ui/card_details.gd")
const CatalogIndex = preload("res://data/catalog_index.gd")
const CardView = preload("res://ui/card_view.gd")
const TEXT := {
    "zh-CN": {"title":"本局怪物卡", "capacity":"已吸收 %d / %d", "accept":"吸收", "skip":"跳过", "replace":"替换已吸收卡", "empty":"没有待处理的怪物卡", "hint":"只影响本局；新卡进入弃牌，不补抽。", "loot":"可搜刮战利品（与战斗装备分开）"},
    "zh-TW": {"title":"本局怪物卡", "capacity":"已吸收 %d / %d", "accept":"吸收", "skip":"略過", "replace":"替換已吸收卡", "empty":"沒有待處理的怪物卡", "hint":"只影響本局；新卡進入棄牌，不補抽。", "loot":"可搜刮戰利品（與戰鬥裝備分開）"},
    "en": {"title":"Run monster cards", "capacity":"Active %d / %d", "accept":"Absorb", "skip":"Skip", "replace":"Replace active card", "empty":"No pending monster cards", "hint":"This run only. New cards enter discard; no bonus draw.", "loot":"Searchable loot (separate from combat equipment)"},
    "ja": {"title":"探索中のモンスターカード", "capacity":"吸収済み %d / %d", "accept":"吸収", "skip":"スキップ", "replace":"吸収済みカードと交換", "empty":"保留中のカードはありません", "hint":"今回の探索のみ。新カードは捨て札へ。追加ドローなし。", "loot":"回収可能な戦利品（戦闘装備とは別）"},
    "ko": {"title":"이번 탐험 몬스터 카드", "capacity":"활성 %d / %d", "accept":"흡수", "skip":"건너뛰기", "replace":"활성 카드 교체", "empty":"대기 중인 카드가 없습니다", "hint":"이번 탐험에만 적용. 새 카드는 버린 카드 더미로 이동하며 추가 드로우는 없습니다.", "loot":"회수 가능한 전리품 (전투 장비와 별도)"}
}

static func text(key: String) -> String:
    var lang: String = P.language()
    var dictionary: Dictionary = TEXT.get(lang, TEXT.get(lang.get_slice("-", 0), TEXT.en))
    return str(dictionary.get(key, key))

static func _pool_theme() -> Theme:
    var result := P.theme()
    result.default_font_size = 26
    result.set_stylebox("panel", "AcceptDialog", P.box(Color("10272e"), P.GOLD))
    var frame := P.box(Color("10272e"), P.GOLD)
    frame.set_expand_margin(SIDE_TOP, 36)
    frame.content_margin_top = 36
    result.set_stylebox("embedded_border", "Window", frame)
    result.set_stylebox("embedded_unfocused_border", "Window", frame.duplicate())
    result.set_font("title_font", "Window", P.font("title"))
    result.set_font_size("title_font_size", "Window", 28)
    result.set_color("title_color", "Window", P.GOLD)
    result.set_stylebox("panel", "PopupMenu", P.box(Color("10272e"), P.GOLD))
    result.set_color("font_color", "PopupMenu", P.PAPER)
    return result

static func _pool_label(value: String, width: float, color: Color = P.PAPER) -> Label:
    var label := Label.new()
    label.custom_minimum_size.x = width
    label.size.x = width
    label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    label.text = value
    label.add_theme_color_override("font_color", color)
    return label

static func _active_title(card: Dictionary, index: int) -> String:
    var result := "%d. %s" % [index + 1, CardDetails.localized_name(str(card.get("card_id", "")), CatalogIndex.card(str(card.get("card_id", ""))))]
    for held in Game.room.get("player", {}).get("hand", []):
        if str(held.get("instance_id", "")) == str(card.get("instance_id", "")):
            return result + " · " + P.localized("own_hand")
    return result

static func open(host: Control) -> void:
    var pool: Dictionary = Game.room.get("player", {}).get("monster_pool", {})
    var dialog := AcceptDialog.new()
    dialog.title = text("title")
    dialog.theme = _pool_theme()
    var width := minf(1100.0, host.get_viewport_rect().size.x - 128.0)
    dialog.min_size = Vector2i(int(width) + 48, 560)
    var box := VBoxContainer.new()
    box.custom_minimum_size.x = width
    box.size.x = width
    box.add_theme_constant_override("separation", 12)
    var active: Array = pool.get("active", [])
    var pending: Array = pool.get("pending", [])
    var heading := _pool_label(text("capacity") % [active.size(), int(pool.get("capacity", 5))], width, P.GOLD)
    heading.add_theme_font_size_override("font_size", 28)
    box.add_child(heading)
    box.add_child(_pool_label(text("hint"), width, P.MUTED))
    var titles := PackedStringArray()
    for index in active.size(): titles.append(_active_title(active[index], index))
    if not titles.is_empty(): box.add_child(_pool_label(", ".join(titles), width))
    if pending.is_empty():
        box.add_child(_pool_label(text("empty"), width))
    else:
        # One candidate per dialog avoids stale callbacks after another mutation.
        var candidate: Dictionary = pending[0]
        var card_id := str(candidate.get("card_id", ""))
        var level := int(candidate.get("level", 0))
        var info := CardDetails.with_element(CatalogIndex.card(card_id), str(candidate.get("element_override", "")))
        var row := HBoxContainer.new()
        row.add_theme_constant_override("separation", 28)
        var preview := CardView.new()
        preview.name = "MonsterPoolCandidatePreview"
        preview.disabled = true
        preview.focus_mode = Control.FOCUS_NONE
        preview.mouse_filter = Control.MOUSE_FILTER_IGNORE
        preview.configure(card_id, info, CardDetails.face_description(card_id, level, info), false, {"preview":true, "level":level})
        row.add_child(preview)
        var details := VBoxContainer.new()
        details.size_flags_horizontal = Control.SIZE_EXPAND_FILL
        details.add_theme_constant_override("separation", 20)
        var detail_width := width - preview.custom_minimum_size.x - 28
        var title := _pool_label(CardDetails.localized_name(card_id, info), detail_width, P.GOLD)
        title.add_theme_font_size_override("font_size", 32)
        details.add_child(title)
        details.add_child(_pool_label(CardDetails.face_description(card_id, level, info), detail_width))
        row.add_child(details)
        box.add_child(row)
        var replace := OptionButton.new()
        replace.add_item(text("replace"))
        for index in active.size(): replace.add_item(_active_title(active[index], index))
        box.add_child(replace)
        var actions := HBoxContainer.new()
        actions.add_theme_constant_override("separation", 20)
        var take := Button.new()
        take.text = text("accept")
        take.size_flags_horizontal = Control.SIZE_EXPAND_FILL
        var full: bool = active.size() >= int(pool.get("capacity", 5))
        take.disabled = not Game.allowed("monster.choose") or full
        replace.item_selected.connect(func(index: int): take.disabled = not Game.allowed("monster.choose") or (full and index == 0))
        take.pressed.connect(func():
            var payload := {"candidate_id":str(candidate.get("instance_id", "")), "accept":true}
            if replace.selected > 0: payload["replace_instance_id"] = str(active[replace.selected - 1].get("instance_id", ""))
            Game.command("monster.choose", payload)
            dialog.queue_free())
        actions.add_child(take)
        var skip := Button.new()
        skip.text = text("skip")
        skip.size_flags_horizontal = Control.SIZE_EXPAND_FILL
        skip.disabled = not Game.allowed("monster.choose")
        skip.pressed.connect(func():
            Game.command("monster.choose", {"candidate_id":str(candidate.get("instance_id", "")), "accept":false})
            dialog.queue_free())
        actions.add_child(skip)
        box.add_child(actions)
    dialog.add_child(box)
    host.add_child(dialog)
    dialog.get_ok_button().text = P.localized("confirm")
    dialog.confirmed.connect(dialog.queue_free)
    dialog.canceled.connect(dialog.queue_free)
    dialog.popup_centered()

static func loot(host: Control, items: Array) -> void:
    var dialog := AcceptDialog.new()
    dialog.title = text("loot")
    dialog.theme = _pool_theme()
    var width := minf(940.0, host.get_viewport_rect().size.x - 128.0)
    dialog.min_size = Vector2i(int(width) + 48, 280)
    var lines := PackedStringArray()
    for item in items:
        var gear: Dictionary = item.get("equipment", {})
        lines.append("%s / %s / %s +%d" % [P.word(gear.get("quality", "")), P.word(gear.get("element", "")), P.word(gear.get("slot", "")), int(gear.get("level", 0))])
    var body := _pool_label("\n".join(lines) if not lines.is_empty() else P.localized("no_equipment"), width)
    body.name = "SearchableLootBody"
    dialog.add_child(body)
    host.add_child(dialog)
    dialog.get_ok_button().text = P.localized("confirm")
    dialog.confirmed.connect(dialog.queue_free)
    dialog.canceled.connect(dialog.queue_free)
    dialog.popup_centered()
