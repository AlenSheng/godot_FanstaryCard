extends RefCounted

static var _body_font: FontFile = preload("res://assets/fonts/SourceHanSansSC-Regular.otf")
static var _title_font: FontFile = preload("res://assets/fonts/SourceHanSerifSC-SemiBold.otf")
static var _number_font: FontVariation
static var _fonts_ready := false
static var _language := "zh-CN"
static var _locale_config: Dictionary = {}
static var _source_aliases: Dictionary = {}
const LANGUAGE_SETTINGS_PATH := "user://fantasycard_language.cfg"

const INK := Color("172d35")
const PAPER := Color("efe3c7")
const MUTED := Color("a5bbb7")
const GOLD := Color("d3ae68")
const TEAL := Color("5cb9b0")
const QUALITY := {"White": Color("d0c9b6"), "Green": Color("789a70"), "Blue": Color("558cb8"), "Purple": Color("9979b1"), "Orange": Color("d99b48"), "Red": Color("ce5651")}
const ELEMENT := {"Fire": Color("f18751"), "Wood": Color("72c878"), "Water": Color("5bc6d3"), "Metal": Color("e8d38a"), "Earth": Color("b69a70"), "None": Color.WHITE}
const WORDS := {"Priest": "牧", "Mage": "法", "Guardian": "盾", "White": "白", "Green": "绿", "Blue": "蓝", "Purple": "紫", "Orange": "橙", "Red": "红", "Fire": "火", "Wood": "木", "Water": "水", "Metal": "金", "Earth": "土", "None": "直伤", "Head": "头部", "Helmet": "头部", "Chest": "胸甲", "Body": "胸甲", "Hands": "手部", "Gloves": "手部", "Legs": "腿部", "Feet": "鞋子", "Boots": "鞋子", "Gold": "金币", "EquipmentFragments": "装备碎片", "WarriorSoul": "勇士之魂", "ClassSoul": "职业之魂", "HealthPotion": "生命药剂", "Equipment": "装备", "CardPack": "卡包", "SoulPack": "勇士之魂包", "FragmentPack": "碎片包", "ClassSoulPack": "职业之魂包", "AdvancedBag": "高级背包", "TopBag": "顶级背包", "Card": "卡牌", "Bulwark": "载壁", "Piercing": "破击", "Vitality": "生息", "Damage": "伤害", "Heal": "回复", "Support": "辅助", "Pve": "交战", "Pvp": "决斗", "Choice": "战利品", "ActionBar": "探索", "Extracted": "撤离成功", "PveDeath": "探索失利", "PvpDeath": "决斗失利", "Death": "探索失利", "Dead": "探索失利"}
const CLASSES := {"Priest": ["潮听 · 临", "临渊杖", 80, "潮汐将至，听见生机。", "残血治疗 / 控场"], "Mage": ["余烬 · 凯", "焚弦薪", 70, "让最后一簇火，照亮归途。", "元素连携 / 快攻"], "Guardian": ["载山 · 敦", "载岳盾", 100, "山岳不移，守住每次归来。", "满血护盾 / 坚守"]}
const WORD_KEYS := {
	"priest":"word_priest", "mage":"word_mage", "guardian":"word_guardian", "warrior":"word_warrior", "white":"word_white", "green":"word_green", "blue":"word_blue", "purple":"word_purple", "orange":"word_orange", "red":"word_red", "fire":"word_fire", "wood":"word_wood", "water":"word_water", "metal":"word_metal", "earth":"word_earth", "none":"word_none", "head":"word_head", "helmet":"word_head", "chest":"word_chest", "body":"word_chest", "hands":"word_hands", "gloves":"word_hands", "legs":"word_legs", "feet":"word_feet", "boots":"word_feet", "gold":"word_gold", "goldearned":"word_gold", "equipmentfragments":"word_equipment_fragments", "fragmentpack":"word_equipment_fragments", "warriorsoul":"word_warrior_soul", "classsoul":"word_class_soul", "soulpack":"word_warrior_soul", "classsoulpack":"word_class_soul", "priestsoul":"word_priest_soul", "magesoul":"word_mage_soul", "guardiansoul":"word_guardian_soul", "healthpotion":"word_health_potion", "equipment":"word_equipment", "item":"word_item", "card":"word_card", "cardpack":"word_card_pack", "advancedbag":"word_advanced_bag", "topbag":"word_top_bag", "diamond":"word_diamond", "bulwark":"word_bulwark", "piercing":"word_piercing", "vitality":"word_vitality", "damage":"word_damage", "heal":"word_heal", "support":"word_support", "pve":"word_pve", "pvp":"word_pvp", "choice":"word_choice", "actionbar":"word_action_bar", "extracted":"word_extracted", "pvedeath":"word_pve_death", "pvpdeath":"word_pvp_death", "death":"word_death", "dead":"word_dead"
}
## UI copy is kept in localization_config.json; this alias table lets legacy module
## calls pass their existing Chinese source text without bypassing localization.
const TEXT_KEYS := {
	"营地":"nav_hall", "图鉴 / 编组":"nav_cards", "穿戴 / 强化":"nav_gear", "金币商店":"nav_shop", "金币市场":"nav_market", "探索准备":"nav_prep", "返回":"back", "切换账号":"switch_account",
	"混沌领域":"chaos_realm", "余火营地":"camp_title", "幻想牌域":"camp_title", "卡牌图鉴":"cards_title", "行装与本命":"gear_title", "碎片强化":"enhance_title", "旅人补给":"shop_title", "旅人集市":"market_title",
	"启程":"start", "账号名称":"account_name", "服务器地址":"server_address", "正在连接…":"connecting", "本地登录 / 注册":"local_login", "Steam 登录":"steam_login", "重新连接":"reconnect", "正在读取…":"loading", "设置":"settings", "语言":"language", "音效音量":"sound_volume", "静音":"mute",
	"保存编组":"save_deck", "还原":"restore", "卡牌与专属武器不占背包格":"deck_no_bag_space", "保存穿戴":"save_loadout", "保存五部位穿戴":"save_loadout", "强化专属武器":"enhance_weapon", "确认探索准备":"confirm_prep", "取消准备":"cancel_prep", "取消匹配 / 准备":"cancel_match", "开始匹配":"start_match", "正在匹配…":"matching", "准备就绪":"ready", "同步":"sync",
	"探索行囊":"explore_bag", "遗物检索":"relic_search", "当前穿戴":"equipped", "仓库装备":"stored_equipment", "暂无装备":"no_equipment", "仓库暂无装备，探索撤离后可带回战利品。":"no_equipment_hint", "背包":"bag", "临时背包":"temporary_bag", "生命药剂":"health_potion", "使用生命药剂":"use_health_potion", "安全格":"safe_slots", "刷新遗物":"refresh_relic", "遗物内容已变化，请刷新后选择。":"relic_changed", "这份遗物已不可检索，请返回当前格。":"relic_unavailable", "拾取":"take", "选择":"select", "装备对比":"compare_equipment", "对比 / 穿戴":"compare_equip", "穿戴":"equip", "卸下":"unequip", "未穿戴":"not_equipped", "空格":"empty_slot",
	"购买":"buy", "刷新":"refresh", "上架":"list_for_sale", "下架":"remove_listing", "上架物品":"list_item", "选择仓库装备":"select_stored_equipment", "购买 / 我的挂单":"buy_or_listings", "物品":"item", "操作":"action", "暂无商品，请稍后刷新":"no_products", "集市暂时没有挂单":"no_listings", "确认操作":"confirm_action", "确认":"confirm", "取消":"cancel",
	"已选":"selected", "本局怪物卡":"battle_monster_card", "怪":"monster", "插画待补":"illustration_missing", "生命":"hp", "护盾":"shield", "同格旅人":"same_cell_traveler", "双方离开":"leave_duel", "强制逃脱":"force_escape", "放":"play", "首领":"boss", "源泉":"spring", "自己":"self", "饮用源泉":"drink_spring", "撤离":"extract", "深入混沌":"enter_chaos", "行囊":"bag", "战利品":"loot", "留下你最需要的":"choose_reward", "装备碎片":"equipment_fragments", "升级成功，卡牌效果已提升":"upgrade_success", "编组已保存":"deck_saved", "操作成功":"operation_success"
}
const EXTRA_TEXT_KEYS := {
	"已激活":"activated",
	"幻想牌域":"camp_title", "营地":"nav_hall", "卡牌图鉴":"cards_title", "行装与本命":"gear_title", "装备穿戴":"gear_title", "碎片强化":"enhance_title", "旅人补给":"shop_title", "旅人集市":"market_title", "图鉴 / 编组":"nav_cards", "穿戴 / 强化":"nav_gear", "金币商店":"nav_shop", "金币市场":"nav_market", "探索准备":"nav_prep",
	"潮听 · 临":"class_priest_title", "余烬 · 凯":"class_mage_title", "载山 · 敦":"class_guardian_title", "临渊杖":"class_priest_weapon", "焚弦薪":"class_mage_weapon", "载岳盾":"class_guardian_weapon", "潮汐将至，听见生机。":"class_priest_flavor", "让最后一簇火，照亮归途。":"class_mage_flavor", "山岳不移，守住每次归来。":"class_guardian_flavor", "残血治疗 / 控场":"class_priest_role", "元素连携 / 快攻":"class_mage_role", "满血护盾 / 坚守":"class_guardian_role", "牧师":"class_priest", "法师":"class_mage", "守护者":"class_guardian", "勇士":"class_warrior",
	"品质：":"quality_label", "全部":"all", "色":"color_suffix", "搜索卡牌名称或效果":"search_cards", "点击卡牌查看详情 · 按住拖拽或使用滚轮浏览":"browse_cards", "已收集":"collected", "筛选结果":"filter_result", "持有数据未就绪，请重新进入图鉴刷新":"collection_not_ready", "没有符合条件的卡牌":"no_matching_cards", "编辑编组":"edit_deck", "完成编组":"finish_deck", "当前编组":"current_deck", "加入编组":"add_to_deck", "编组已满":"deck_full", "可用数量不足":"not_enough_copies", "仅限%s职业编组":"class_restriction", "当前编组正在使用，请先从编组移除并保存":"deck_in_use", "当前编组正在使用这张卡，请先从编组移除并保存":"card_in_deck", "已保存编组正在使用，请先调整并保存编组":"saved_deck_in_use", "卡牌详情":"card_details", "通用卡":"general_card", "职业卡":"class_card", "等级":"level", "已拥有":"owned_count", "未拥有":"not_owned", "合成后获得":"craft_after", "升级消耗":"upgrade_cost", "当前拥有":"current_owned", "分解返还":"dismantle_refund", "合成消耗":"craft_cost", "需额外同名卡":"extra_copies", "需要额外同名卡，并保留各编组所用副本":"extra_copy_hint", "只消耗魂材料":"soul_only", "总投入的 25%，向下取整；优先分解未升级副本":"dismantle_hint", "合成后可加入编组":"craft_hint", "暂未取得合成与分解报价，请重新进入图鉴刷新":"quote_unavailable", "已达最高等级":"max_level", "报价暂不可用":"quote_unavailable_short", "正在处理…":"processing", "读取中":"reading", "读取中…":"reading", "已达 +5":"max_level_short", "合成":"craft", "分解":"dismantle", "升级":"upgrade", "升至":"upgrade_to",
	"锁定武器":"locked_weapon", "锁定":"locked", "本命":"signature", "本命武器":"signature_weapon", "点击卸下":"click_unequip", "装备详情暂不可用":"equipment_unavailable", "未识别的装备部位":"unknown_equipment_slot", "仓库暂无装备，探索撤离后可带回战利品。":"no_equipment_hint", "安全格物品死亡后带回；身上防具不受保护":"safe_slot_hint", "拖动物品换格，或选中物品后点击目标格":"drag_inventory_hint", "选择包中物品查看详情。\n点击已穿防具可以卸下。":"inventory_detail_hint", "卸下这件防具并放入背包？":"unequip_confirm", "穿戴 · 旧装放回背包":"equip_replace", "对比 / 直接穿戴":"compare_equip_direct", "放回选中物品，再拾取":"replace_then_take", "先选右侧物品放回本堆":"select_item_to_return",
	"轻装行囊":"light_bag", "高级行囊":"advanced_bag_label", "顶级行囊":"top_bag_label", "免费":"free", "持有 高级":"owned_advanced", "顶级":"top", "最多携带":"carry_max", "当前格行动":"current_cell_action", "临时行囊":"temporary_bag", "临时背包":"temporary_bag", "打开行囊":"open_bag", "选择接下来的行动":"choose_next_action", "战利品三选一":"loot_three_choices", "此行收获":"run_reward", "收入背包":"added_to_bag", "碎片堆":"fragment_pile", "走邻格":"move_neighbor", "查看地图":"view_map", "进入中层":"enter_middle_layer", "进入后不能退回外层":"no_outer_return", "确认进入":"confirm_enter", "暂不进入":"do_not_enter", "随机撤离点不会显示在小地图":"hidden_extract_hint", "源泉常亮，可规划绕路回血":"spring_route_hint", "高亮邻格可前往":"reachable_hint", "向内探索后无法返回外层。\n源泉常亮，可规划补给路线。":"map_hint", "首领 / 源泉 / 自己":"map_legend", "只能同层横行或向内探索。":"map_move_hint", "抽牌":"draw", "牌库":"library", "弃牌":"discard", "预览":"preview", "正在计算所选牌效果…":"calculating_preview", "回复":"heal", "眩晕":"stun", "锁抽":"draw_lock", "自损":"self_damage", "充能":"charge", "抽牌间隔":"draw_interval", "等待行动":"waiting_action", "自己的手牌":"own_hand", "遭遇战":"encounter", "混沌战斗":"chaos_battle", "战斗属性 / 套装":"battle_stats_set", "对手属性":"opponent_stats", "已击败":"defeated", "蓄力":"charge_intent", "强化":"empower", "意图":"intent", "即将行动":"about_to_act", "逃脱中":"escaping", "逃脱读条":"escape_progress", "等待战利品":"waiting_loot", "本局刷新":"run_refresh", "刷新已用尽":"refresh_exhausted", "同核连放，加快抽牌":"passive_mage", "生命越低，治疗与控场越强":"passive_priest", "生命越高，上盾越厚":"passive_guardian", "本命 · ":"signature_prefix",
	"金币":"word_gold", "装备":"word_equipment", "装备碎片":"word_equipment_fragments", "生命":"word_hp", "生命上限":"word_max_hp", "护盾":"word_shield", "盾":"word_shield_short", "安全":"safe", "持有":"owned", "最多":"maximum", "今日":"today", "剩余":"remaining", "数量":"quantity", "件":"pieces", "格":"slots", "秒":"seconds", "次":"times", "点击":"click", "当前目标":"current_target", "选择目标":"select_target", "可前往":"reachable", "确认剩余":"confirm_remaining", "已确认":"confirmed", "属性":"stats", "费用":"cost", "所需":"required", "暂无":"none_available", "操作完成":"operation_done", "直伤":"direct_damage", "直接伤害":"direct_damage", "治疗":"healing", "上盾":"shield_gain", "减伤":"damage_reduction", "抗性":"resistance", "穿透":"penetration", "效果词缀为本件贡献，套装激活后生效":"affix_hint", "绑定 · 不可上架":"bound_unlisted", "套装激活后贡献":"set_contribution", "上盾适用所有职业；减伤仅盾卫生效":"bulwark_hint",
	"金币交易 · 上架上限 8 件 · 48 小时 · 手续费 10%（至少 1 金币）":"market_terms", "暂无商品，稍后刷新。":"no_products_later", "集市暂时没有挂单。":"no_listings", "选择仓库装备上架":"select_item_to_list", "上架单价":"listing_price", "手续费 10%（至少 1 金币）\n上架上限 8 件 · 最长 48 小时":"listing_terms", "花费":"spend", "购买此装备":"buy_equipment", "卖家实得":"seller_receives", "库存已满":"inventory_full", "请刷新库存":"refresh_inventory", "本次上架":"current_listing", "确认以":"confirm_price", "确认以 %s 金币上架？":"confirm_listing_price",
	"包满替换 · 换下物品会被系统回收":"bag_full_replace", "回收":"recycle", "直接穿戴新防具，同部位旧装会被系统回收。":"direct_equip_recycle", "回收 %s 并领取战利品？":"recycle_for_loot", "本次旅程已由服务器结算。":"settlement_synced", "旅程结束":"journey_end", "当前状态已改变，请重新选择操作":"state_changed", "请先选择存活目标":"select_living_target", "确认超时，席位已释放":"ready_timeout", "未连接":"disconnected", "操作未发出，请在连接恢复后重试":"request_not_sent", "请输入账号名称":"enter_account", "请输入 http:// 或 https:// 服务器地址":"invalid_server_url", "正式客户端需要 HTTPS 服务器地址":"https_required", "本地账号仅用于开发验证，请使用 Steam 登录":"local_login_dev_only", "此服务器未启用 Steam 登录":"steam_disabled", "此服务器未启用本地开发登录":"local_login_disabled", "服务器未返回有效登录凭证，请重试":"invalid_login_credential", "未提供版本":"version_missing", "服务器":"server", "大厅":"hall", "房间":"room", "准备":"preparation", "服务器配置与客户端不一致":"config_mismatch_prefix", "服务器不可用，请检查地址与服务器状态":"server_unavailable", "连接中断，正在重连":"connection_interrupted", "请求正在处理":"request_processing", "操作过快，请稍后重试":"operation_too_fast", "操作被拒绝":"operation_rejected", "服务器消息内容损坏":"server_message_corrupt", "无法解析服务器协议":"server_protocol_invalid", "实时协议需要二进制帧":"binary_frame_required", "登录已过期，请重新登录":"login_expired", "登录状态已改变，请重新登录":"login_state_changed", "已退出登录":"logged_out", "无法连接服务器":"server_connect_failed", "无法连接 Steam，请启动 Steam 并从游戏库启动游戏":"steam_connect_failed", "请先登录 Steam":"steam_login_required", "获取 Steam 登录票据超时，请重试":"steam_ticket_timeout", "Steam 登录票据无效，请重试":"steam_ticket_invalid", "Steam 登录正在处理":"steam_login_processing", "Steam 登录尚未配置游戏 AppID":"steam_app_id_missing", "Steam 登录尚未配置票据身份":"steam_identity_missing", "Steam 接入组件版本不支持当前登录方式":"steam_component_unsupported", "Steam 接入组件不支持网页登录票据回调":"steam_browser_callback_unsupported", "Steam 未能创建登录票据，请重试":"steam_ticket_create_failed", "Steam 未能提供有效登录票据，请重试":"steam_ticket_empty", "Steam 游戏身份与客户端配置不一致":"steam_config_mismatch"
}

static func word(value: Variant) -> String:
	if value == null: return ""
	var raw := str(value)
	var key: String = WORD_KEYS.get(_word_identifier(raw), "")
	return localized(key) if not key.is_empty() else WORDS.get(raw, raw)

## Display names for shop/catalog product kinds.  Keep this at the
## presentation boundary because the API may send PascalCase, snake_case,
## or legacy ids (for example `health_potion`).
static func product_name(value: Variant) -> String:
	if value == null: return ""
	var raw := str(value)
	var key: String = WORD_KEYS.get(_word_identifier(raw), "")
	return localized(key) if not key.is_empty() else word(raw)

## API/catalog identifiers use both PascalCase (HealthPotion) and snake_case
## (health_potion).  Normalize them before looking up display words so neither
## form can leak into a localized UI.
static func _word_identifier(value: String) -> String:
	return value.to_lower().replace("_", "").replace("-", "").replace(" ", "")

static func font(role: String = "body") -> Font:
	_ensure_locale()
	if not _fonts_ready:
		_body_font = load(_locale_config.languages[_language].fonts.body)
		_title_font = load(_locale_config.languages[_language].fonts.title)
		_body_font.allow_system_fallback = false
		_title_font.allow_system_fallback = false
		_title_font.fallbacks = [_body_font]
		_number_font = FontVariation.new()
		_number_font.base_font = _body_font
		# Source Han Sans ships equal-width default figures; keep proportional widths off.
		_number_font.opentype_features = {"pwid": 0}
		_fonts_ready = true
	match role:
		"title": return _title_font
		"number": return _number_font
	return _body_font

static func _ensure_locale() -> void:
	if _locale_config.is_empty():
		_locale_config = JSON.parse_string(FileAccess.get_file_as_string("res://data/localization_config.json"))
		var module_config: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/localization_modules.json"))
		if module_config is Dictionary:
			for code in module_config.get("languages", {}):
				var target: Dictionary = _locale_config.get("languages", {}).get(code, {})
				var strings: Dictionary = target.get("strings", {})
				strings.merge(module_config.languages[code].get("strings", {}))
				target["strings"] = strings
				_locale_config.languages[code] = target
		var template_config: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/localization_templates.json"))
		if template_config is Dictionary:
			for code in template_config.get("languages", {}):
				var target: Dictionary = _locale_config.get("languages", {}).get(code, {})
				var strings: Dictionary = target.get("strings", {})
				strings.merge(template_config.languages[code].get("strings", {}))
				target["strings"] = strings
				_locale_config.languages[code] = target
		var brand_config: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/localization_brand.json"))
		if brand_config is Dictionary:
			for code in brand_config.get("languages", {}):
				var target: Dictionary = _locale_config.get("languages", {}).get(code, {})
				var strings: Dictionary = target.get("strings", {})
				strings.merge(brand_config.languages[code].get("strings", {}))
				target["strings"] = strings
				_locale_config.languages[code] = target
		var login_config: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/login_localization.json"))
		if login_config is Dictionary:
			for code in login_config.get("languages", {}):
				var target: Dictionary = _locale_config.get("languages", {}).get(code, {})
				var strings: Dictionary = target.get("strings", {})
				strings.merge(login_config.languages[code].get("strings", {}))
				target["strings"] = strings
				_locale_config.languages[code] = target
		var battle_config: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/localization_battle.json"))
		if battle_config is Dictionary:
			for code in battle_config.get("languages", {}):
				var target: Dictionary = _locale_config.get("languages", {}).get(code, {})
				var strings: Dictionary = target.get("strings", {})
				strings.merge(battle_config.languages[code].get("strings", {}))
				target["strings"] = strings
				_locale_config.languages[code] = target
		_language = str(_locale_config.get("default_language", "zh-CN"))
		var saved_language := _load_language()
		if _locale_config.get("languages", {}).has(saved_language):
			_language = saved_language
		_build_source_aliases()

static func _build_source_aliases() -> void:
	_source_aliases.clear()
	for language_config in _locale_config.get("languages", {}).values():
		var strings: Dictionary = language_config.get("strings", {})
		for key in strings:
			var source := str(strings[key])
			if source.length() < 2 or source == str(key): continue
			# Accept display text authored in either language. This keeps legacy
			# screens localizable while they migrate from text to stable keys.
			if not _source_aliases.has(source): _source_aliases[source] = str(key)

static func language() -> String:
	_ensure_locale()
	return _language

static func set_language(value: String) -> void:
	_ensure_locale()
	if not _locale_config.get("languages", {}).has(value): return
	if _language == value: return
	_language = value
	_fonts_ready = false
	_save_language()

static func _save_language() -> void:
	var settings := ConfigFile.new()
	settings.set_value("ui", "language", _language)
	settings.save(LANGUAGE_SETTINGS_PATH)

static func _load_language() -> String:
	var settings := ConfigFile.new()
	if settings.load(LANGUAGE_SETTINGS_PATH) != OK: return ""
	return str(settings.get_value("ui", "language", ""))

static func localized(key: String) -> String:
	_ensure_locale()
	var language_config: Dictionary = _locale_config.get("languages", {}).get(_language, {})
	var strings: Dictionary = language_config.get("strings", {})
	if strings.has(key): return str(strings[key])
	return str(language_config.get("mail_strings", {}).get(key, key))

static func localized_text(value: String) -> String:
	if value.is_empty(): return value
	_ensure_locale()
	var localized_identifier := word(value)
	if localized_identifier != value: return localized_identifier
	var aliases := TEXT_KEYS.duplicate()
	aliases.merge(EXTRA_TEXT_KEYS)
	aliases.merge(_source_aliases)
	aliases.merge({"幻境牌旅":"game_title", "账号":"account", "试听 · 黄铜与纸牌":"sample_sound", "搜寻遗物，组合五行，带着战利品归来。":"login_subtitle", "输入唯一账号名称":"account_placeholder", "同名登录原账号，新名称自动注册新账号。":"account_hint", "每一次深入，都是新的抉择":"login_about_title", "三种职业 · 一套属于你的二十张牌":"login_feature_1", "五行连放 · 实时抽牌与目标选择":"login_feature_2", "只向内探索 · 在战斗与撤离之间取舍":"login_feature_3", "邮件":"mail", "全部已读":"mark_all_read", "一键全领":"claim_all", "删除已读":"delete_read", "关闭":"close", "暂无邮件":"no_mail", "领取":"claim", "已领取":"claimed", "删除":"delete", "已读":"read", "未读":"unread", "附件":"attachments", "发件人":"sender", "系统邮件":"system_mail", "收件箱":"inbox", "邮件详情":"mail_details", "选择一封邮件查看详情":"select_mail", "邮件附件已领取":"mail_claimed", "邮件附件已全部领取":"mail_all_claimed", "邮件已删除":"mail_deleted", "已读邮件已清理":"mail_read_deleted"})
	if aliases.has(value): return localized(aliases[value])
	var result := value
	var phrases: Array = aliases.keys()
	phrases.sort_custom(func(left, right): return str(left).length() > str(right).length())
	for phrase in phrases:
		if str(phrase).length() < 2 or not result.contains(str(phrase)): continue
		var translated := localized(str(aliases[phrase]))
		if translated != str(aliases[phrase]): result = result.replace(str(phrase), translated)
	return result

static func localized_word(value: Variant) -> String:
	var keys := {"gold": "word_gold", "equipmentfragments": "word_equipment_fragments", "fragmentpack": "word_equipment_fragments", "healthpotion": "word_health_potion", "warriorsoul": "word_warrior_soul", "classsoul": "word_warrior_soul", "soulpack": "word_warrior_soul", "classsoulpack": "word_warrior_soul", "priestsoul": "word_priest_soul", "magesoul": "word_mage_soul", "guardiansoul": "word_guardian_soul", "equipment": "word_equipment", "item": "word_equipment", "card": "word_card", "cardpack": "word_card", "advancedbag": "word_advanced_bag", "topbag": "word_top_bag", "diamond": "word_diamond", "white": "word_white", "green": "word_green", "blue": "word_blue", "purple": "word_purple", "orange": "word_orange", "red": "word_red", "fire": "word_fire", "wood": "word_wood", "water": "word_water", "metal": "word_metal", "earth": "word_earth", "head": "word_head", "helmet": "word_head", "chest": "word_chest", "body": "word_chest", "hands": "word_hands", "gloves": "word_hands", "legs": "word_legs", "feet": "word_feet", "boots": "word_feet", "none": "word_equipment"}
	var key: String = keys.get(_word_identifier(str(value)), "")
	return localized(key) if not key.is_empty() else word(value)

## Server-side validation details are not localization keys.  Use this only at
## presentation boundaries (such as transient tips) to avoid exposing English
## diagnostics in the Simplified Chinese client.
static func is_unlocalized_english_sentence(value: String) -> bool:
	if language() != "zh-CN": return false
	var letters := 0
	var has_sentence_separator := false
	for character in value:
		if character.to_lower() != character.to_upper(): letters += 1
		if character in " .,!?:;": has_sentence_separator = true
	return letters >= 3 and has_sentence_separator

static func languages() -> Dictionary:
	_ensure_locale()
	return _locale_config.get("languages", {})

static func font_for_text(value: String, size: int = 24) -> Font:
	var numeric := not value.is_empty()
	for character in value:
		if character not in "0123456789+-−.,:%/ ×":
			numeric = false
			break
	if numeric: return font("number")
	return font("title") if size >= 32 and value.length() <= 26 and not value.contains("\n") else font("body")

static func fit_font_size(typeface: Font, requested: int, height: float, width: float = -1.0, value: String = "") -> int:
	var fitted := requested
	# Keep the authored rectangles stable; reduce only the text size when a translation is wider.
	while fitted > 1:
		if height > 0.0 and ceilf(typeface.get_height(fitted)) > height:
			fitted -= 1
			continue
		if width > 0.0 and not value.is_empty():
			var longest := 0.0
			for line in value.split("\n"):
				longest = maxf(longest, typeface.get_string_size(line, HORIZONTAL_ALIGNMENT_LEFT, -1.0, fitted).x)
			if longest > width:
				fitted -= 1
				continue
		break
	return fitted

static func fit_control_font(control: Control, typeface: Font, requested: int, horizontal_padding: float = 0.0) -> void:
	if not is_instance_valid(control): return
	var update := func() -> void:
		if not is_instance_valid(control): return
		var value := str(control.get("text"))
		var width := maxf(1.0, control.size.x - horizontal_padding)
		var height := control.size.y
		control.add_theme_font_size_override("font_size", fit_font_size(typeface, requested, height, width, value))
	control.resized.connect(update)
	update.call_deferred()

static func box(color: Color = INK, border: Color = Color("47626a"), width: int = 2) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = color
	style.border_color = border
	style.set_border_width_all(width)
	style.set_corner_radius_all(12)
	style.content_margin_left = 24
	style.content_margin_right = 24
	style.content_margin_top = 16
	style.content_margin_bottom = 16
	return style

static func theme() -> Theme:
	var result := Theme.new()
	result.default_font = font("body")
	result.default_font_size = 24
	result.set_font("font", "Button", font("title"))
	result.set_font("font", "LineEdit", font("body"))
	result.set_font("font", "TextEdit", font("body"))
	result.set_font("normal_font", "RichTextLabel", font("body"))
	result.set_color("font_color", "Label", PAPER)
	result.set_color("font_color", "Button", PAPER)
	result.set_color("font_hover_color", "Button", Color.WHITE)
	result.set_color("font_disabled_color", "Button", Color("73837f"))
	result.set_stylebox("normal", "Button", box())
	result.set_stylebox("hover", "Button", box(Color("254650"), GOLD))
	result.set_stylebox("pressed", "Button", box(Color("38615f"), TEAL, 3))
	result.set_stylebox("focus", "Button", box(Color(0, 0, 0, 0), GOLD, 3))
	result.set_stylebox("disabled", "Button", box(Color("1e3034"), Color("33464b")))
	result.set_stylebox("normal", "LineEdit", box(Color("10272e")))
	result.set_stylebox("panel", "PanelContainer", box())
	result.set_constant("separation", "VBoxContainer", 18)
	result.set_constant("separation", "HBoxContainer", 20)
	result.set_constant("h_separation", "GridContainer", 16)
	result.set_constant("v_separation", "GridContainer", 16)
	return result
