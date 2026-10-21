extends RefCounted

const P = preload("res://ui/palette.gd")
const Art = preload("res://ui/art.gd")
const CardDetails = preload("res://ui/card_details.gd")
const CatalogIndex = preload("res://data/catalog_index.gd")
const CardView = preload("res://ui/card_view.gd")
const TEXT := {
    "zh-CN": {"title":"本局怪物卡", "capacity":"已吸收 %d / %d", "accept":"吸收", "skip":"跳过", "replace":"替换已吸收卡", "empty":"没有待处理的怪物卡", "hint":"只影响本局；新卡进入弃牌，不补抽。", "loot":"可搜刮战利品（与战斗装备分开）", "active_header":"已吸收的怪物卡", "empty_active":"尚未吸收怪物卡", "full_hint":"容量已满，请先选择要替换的已吸收卡。"},
    "zh-TW": {"title":"本局怪物卡", "capacity":"已吸收 %d / %d", "accept":"吸收", "skip":"略過", "replace":"替換已吸收卡", "empty":"沒有待處理的怪物卡", "hint":"只影響本局；新卡進入棄牌，不補抽。", "loot":"可搜刮戰利品（與戰鬥裝備分開）", "active_header":"已吸收的怪物卡", "empty_active":"尚未吸收怪物卡", "full_hint":"容量已滿，請先選擇要替換的已吸收卡。"},
    "en": {"title":"Run monster cards", "capacity":"Active %d / %d", "accept":"Absorb", "skip":"Skip", "replace":"Replace active card", "empty":"No pending monster cards", "hint":"This run only. New cards enter discard; no bonus draw.", "loot":"Searchable loot (separate from combat equipment)", "active_header":"Active monster cards", "empty_active":"No monster cards absorbed yet", "full_hint":"Pool full. Select an active card to replace before absorbing."},
    "ja": {"title":"探索中のモンスターカード", "capacity":"吸収済み %d / %d", "accept":"吸収", "skip":"スキップ", "replace":"吸収済みカードと交換", "empty":"保留中のカードはありません", "hint":"今回の探索のみ。新カードは捨て札へ。追加ドローなし。", "loot":"回収可能な戦利品（戦闘装備とは別）", "active_header":"吸収済みモンスターカード", "empty_active":"まだカードを吸収していません", "full_hint":"上限に達しています。先に交換するカードを選んでください。"},
    "ko": {"title":"이번 탐험 몬스터 카드", "capacity":"활성 %d / %d", "accept":"흡수", "skip":"건너뛰기", "replace":"활성 카드 교체", "empty":"대기 중인 카드가 없습니다", "hint":"이번 탐험에만 적용. 새 카드는 버린 카드 더미로 이동하며 추가 드로우는 없습니다.", "loot":"회수 가능한 전리품 (전투 장비와 별도)", "active_header":"흡수한 몬스터 카드", "empty_active":"아직 흡수한 카드가 없습니다", "full_hint":"한도에 도달했습니다. 먼저 교체할 카드를 선택하세요."}
}

static func text(key: String) -> String:
    var lang: String = P.language()
    var dictionary: Dictionary = TEXT.get(lang, TEXT.get(lang.get_slice("-", 0), TEXT.en))
    return str(dictionary.get(key, key))

static func _pool_theme() -> Theme:
    var result := P.theme()
    result.default_font_size = 26
    result.set_stylebox("panel", "AcceptDialog", Art.style("UI/CardCodex/card_codex_dialog_panel_normal.png"))
    var frame := Art.style("UI/CardCodex/card_codex_dialog_panel_normal.png")
    frame.set_expand_margin(SIDE_TOP, 36)
    frame.content_margin_top = 36
    result.set_stylebox("embedded_border", "Window", frame)
    result.set_stylebox("embedded_unfocused_border", "Window", frame.duplicate())
    result.set_font("title_font", "Window", P.font("title"))
    result.set_font_size("title_font_size", "Window", 28)
    result.set_color("title_color", "Window", P.GOLD)
    result.set_stylebox("panel", "PopupMenu", Art.style("UI/CardCodex/card_codex_dialog_panel_normal.png"))
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
    dialog.name = "MonsterPoolDialog"
    var width := minf(1280.0, host.get_viewport_rect().size.x - 128.0)
    dialog.min_size = Vector2i(int(width) + 48, 560)
    var box := VBoxContainer.new()
    box.custom_minimum_size.x = width
    box.size.x = width
    box.add_theme_constant_override("separation", 12)
    var active: Array = pool.get("active", [])
    var pending: Array = pool.get("pending", [])
    var title_bar := PanelContainer.new()
    title_bar.custom_minimum_size.y = 64
    title_bar.add_theme_stylebox_override("panel", Art.style("UI/CardCodex/card_codex_title_bar_normal.png"))
    var caption := _pool_label(text("title"), width - 64, P.GOLD)
    caption.add_theme_font_override("font", P.font("title"))
    caption.add_theme_font_size_override("font_size", 32)
    caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    title_bar.add_child(caption)
    box.add_child(title_bar)
    var heading := _pool_label(text("capacity") % [active.size(), int(pool.get("capacity", 5))], width, P.GOLD)
    heading.add_theme_font_size_override("font_size", 28)
    box.add_child(heading)
    box.add_child(_pool_label(text("hint"), width, P.MUTED))
    var titles := PackedStringArray()
    for index in active.size(): titles.append(_active_title(active[index], index))
    if pending.is_empty():
        dialog.min_size.y = 280
        box.add_child(_pool_label(text("empty"), width))
        if not titles.is_empty():
            # Opening the run pool after a decision must still show every
            # absorbed instance, even when there is no next candidate.
            var active_scroll := ScrollContainer.new()
            active_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
            active_scroll.custom_minimum_size.y = minf(210.0, maxf(60.0, titles.size() * 48.0 + 12.0))
            active_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
            active_scroll.add_child(_pool_label("\n".join(titles), width - 32))
            box.add_child(active_scroll)
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
        preview.size = preview.custom_minimum_size
        # CardView authors its children at218x376. Scale it inside a plain
        # wrapper so the row container cannot reset the preview scale.
        var card_space := Control.new()
        card_space.custom_minimum_size = Vector2(274, 470)
        preview.scale = Vector2(1.25, 1.25)
        card_space.add_child(preview)
        row.add_child(card_space)
        var details := VBoxContainer.new()
        details.size_flags_horizontal = Control.SIZE_EXPAND_FILL
        details.add_theme_constant_override("separation", 14)
        var detail_width := width - card_space.custom_minimum_size.x - 28
        var title := _pool_label(CardDetails.localized_name(card_id, info), detail_width, P.GOLD)
        title.add_theme_font_size_override("font_size", 32)
        details.add_child(title)
        details.add_child(_pool_label(CardDetails.face_description(card_id, level, info), detail_width))
        var active_panel := PanelContainer.new()
        active_panel.name = "MonsterPoolActiveCards"
        active_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
        var active_frame := P.box(Color("0b252d"), Color("47626a"))
        for side in [SIDE_LEFT, SIDE_RIGHT]: active_frame.set_content_margin(side, 16)
        active_panel.add_theme_stylebox_override("panel", active_frame)
        var active_body := VBoxContainer.new()
        active_body.add_theme_constant_override("separation", 10)
        active_body.add_child(_pool_label(text("active_header"), detail_width - 40, P.GOLD))
        var active_scroll := ScrollContainer.new()
        active_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
        active_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
        active_scroll.custom_minimum_size.y = 210
        active_scroll.add_child(_pool_label("\n".join(titles) if not titles.is_empty() else text("empty_active"), detail_width - 64, P.MUTED))
        active_body.add_child(active_scroll)
        active_panel.add_child(active_body)
        details.add_child(active_panel)
        row.add_child(details)
        box.add_child(row)
        var replace := OptionButton.new()
        replace.custom_minimum_size.y = 64
        Art.button(replace, "UI/CardCodex/card_codex_action_button_blue.png")
        replace.add_item(text("replace"))
        for index in active.size(): replace.add_item(_active_title(active[index], index))
        box.add_child(replace)
        var actions := HBoxContainer.new()
        actions.add_theme_constant_override("separation", 20)
        var take := Button.new()
        take.text = text("accept")
        take.size_flags_horizontal = Control.SIZE_EXPAND_FILL
        var full: bool = active.size() >= int(pool.get("capacity", 5))
        if full: box.add_child(_pool_label(text("full_hint"), width, P.GOLD))
        take.custom_minimum_size.y = 64
        Art.button(take, "UI/CardCodex/card_codex_action_button_orange.png")
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
        skip.custom_minimum_size.y = 64
        Art.button(skip, "UI/CardCodex/card_codex_action_button_blue.png")
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
    # Candidate decisions already have their two explicit actions. The
    # default AcceptDialog confirm only dismisses the window without choosing.
    dialog.get_ok_button().visible = pending.is_empty()
    Art.button(dialog.get_ok_button(), "UI/CardCodex/card_codex_action_button_blue.png")
    dialog.confirmed.connect(dialog.queue_free)
    dialog.canceled.connect(dialog.queue_free)
    if pending.is_empty(): dialog.reset_size()
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
    var margin := MarginContainer.new()
    for side in ["left", "right", "top", "bottom"]:
        margin.add_theme_constant_override("margin_" + side, 28)
    var content := VBoxContainer.new()
    content.add_theme_constant_override("separation", 16)
    var title_bar := PanelContainer.new()
    title_bar.custom_minimum_size.y = 64
    title_bar.add_theme_stylebox_override("panel", Art.style("UI/CardCodex/card_codex_title_bar_normal.png"))
    var title := _pool_label(text("loot"), width - 64, P.GOLD)
    title.add_theme_font_override("font", P.font("title"))
    title.add_theme_font_size_override("font_size", 28)
    title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    title_bar.add_child(title)
    content.add_child(title_bar)
    content.add_child(body)
    margin.add_child(content)
    dialog.add_child(margin)
    host.add_child(dialog)
    dialog.get_ok_button().text = P.localized("confirm")
    Art.button(dialog.get_ok_button(), "UI/CardCodex/card_codex_action_button_blue.png")
    dialog.confirmed.connect(dialog.queue_free)
    dialog.canceled.connect(dialog.queue_free)
    dialog.popup_centered()
