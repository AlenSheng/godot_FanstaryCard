extends RefCounted

const P = preload("res://ui/palette.gd")
const CardDetails = preload("res://ui/card_details.gd")
const CatalogIndex = preload("res://data/catalog_index.gd")
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

static func open(host: Control) -> void:
    var pool: Dictionary = Game.room.get("player", {}).get("monster_pool", {})
    var dialog := AcceptDialog.new()
    dialog.title = text("title")
    dialog.min_size = Vector2i(680, 300)
    var box := VBoxContainer.new()
    box.custom_minimum_size.x = 640
    box.size.x = 640
    var active: Array = pool.get("active", [])
    var pending: Array = pool.get("pending", [])
    var heading := Label.new()
    heading.text = text("capacity") % [active.size(), int(pool.get("capacity", 5))]
    box.add_child(heading)
    var hint := Label.new()
    hint.custom_minimum_size.x = 640
    hint.size.x = 640
    hint.text = text("hint")
    hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    box.add_child(hint)
    var names := Label.new()
    names.custom_minimum_size.x = 640
    names.size.x = 640
    names.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    var titles := PackedStringArray()
    for card in active: titles.append(CardDetails.localized_name(str(card.get("card_id", "")), CatalogIndex.card(str(card.get("card_id", "")))))
    names.text = ", ".join(titles)
    box.add_child(names)
    if pending.is_empty():
        var empty := Label.new()
        empty.text = text("empty")
        box.add_child(empty)
    else:
        # One candidate per dialog avoids stale callbacks after another mutation.
        var candidate: Dictionary = pending[0]
        var card_label := Label.new()
        card_label.custom_minimum_size.x = 640
        card_label.size.x = 640
        card_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
        card_label.text = CardDetails.localized_name(str(candidate.get("card_id", "")), CatalogIndex.card(str(candidate.get("card_id", "")))) + "\n" + CardDetails.face_description(str(candidate.get("card_id", "")))
        box.add_child(card_label)
        var replace := OptionButton.new()
        replace.add_item(text("replace"))
        for card in active: replace.add_item(CardDetails.localized_name(str(card.get("card_id", "")), CatalogIndex.card(str(card.get("card_id", "")))))
        box.add_child(replace)
        var take := Button.new()
        take.text = text("accept")
        var full: bool = active.size() >= int(pool.get("capacity", 5))
        take.disabled = not Game.allowed("monster.choose") or full
        replace.item_selected.connect(func(index: int): take.disabled = not Game.allowed("monster.choose") or (full and index == 0))
        take.pressed.connect(func():
            var payload := {"candidate_id":str(candidate.get("instance_id", "")), "accept":true}
            if replace.selected > 0: payload["replace_instance_id"] = str(active[replace.selected - 1].get("instance_id", ""))
            Game.command("monster.choose", payload)
            dialog.queue_free())
        box.add_child(take)
        var skip := Button.new()
        skip.text = text("skip")
        skip.disabled = not Game.allowed("monster.choose")
        skip.pressed.connect(func():
            Game.command("monster.choose", {"candidate_id":str(candidate.get("instance_id", "")), "accept":false})
            dialog.queue_free())
        box.add_child(skip)
    dialog.add_child(box)
    host.add_child(dialog)
    dialog.confirmed.connect(dialog.queue_free)
    dialog.canceled.connect(dialog.queue_free)
    dialog.popup_centered()

static func loot(host: Control, items: Array) -> void:
    var dialog := AcceptDialog.new()
    dialog.title = text("loot")
    var lines := PackedStringArray()
    for item in items:
        var gear: Dictionary = item.get("equipment", {})
        lines.append("%s / %s / %s +%d" % [P.word(gear.get("quality", "")), P.word(gear.get("element", "")), P.word(gear.get("slot", "")), int(gear.get("level", 0))])
    dialog.dialog_text = "\n".join(lines)
    host.add_child(dialog)
    dialog.confirmed.connect(dialog.queue_free)
    dialog.canceled.connect(dialog.queue_free)
    dialog.popup_centered(Vector2i(620, 280))
