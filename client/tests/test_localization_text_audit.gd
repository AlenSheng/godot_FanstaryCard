extends RefCounted

const Audit = preload("res://tests/localization_text_audit.gd")

func run_test() -> Dictionary:
	var source := {"strings": {"welcome": "欢迎归来", "hp": "生命值", "shared": "確認", "dynamic": "本轮限时%s秒"},
		"card_names": {"a": "守護者"}, "nested": ["生命確認", "角色"]}
	var target := {"strings": {"welcome": "おかえりなさい", "hp": "生命値", "shared": "確認", "dynamic": "このターンは%s秒まで"},
		"card_names": {"a": "守護者"}, "nested": ["生命", "確認"]}
	var ja := Audit.new("ja", source, target)
	var checks := {
		"japanese_kanji_and_shared_source_copy_are_valid": ja.unexpected_han("確認：生命値 48 / 78 · 守護者").is_empty(),
		"chinese_unchanged_sentence_is_detected": not ja.unexpected_han("欢迎归来").is_empty(),
		"chinese_simplified_character_is_detected": not ja.unexpected_han("生命值 48 / 78").is_empty(),
		"chinese_dynamic_fragment_is_detected": not ja.unexpected_han("本轮限时3秒").is_empty(),
		"source_phrase_is_detected_even_when_every_character_is_known": not ja.unexpected_han("生命確認").is_empty(),
		"kana_and_numbers_are_valid": ja.unexpected_han("カードを3枚引く 48 / 78").is_empty(),
		"kanji_outside_the_chinese_source_vocabulary_is_not_guessed_as_chinese": ja.unexpected_han("骨").is_empty(),
		"other_locales_keep_the_previous_han_rejection": not Audit.new("ko", source, target).unexpected_han("生命").is_empty(),
		"chinese_baseline_accepts_chinese": Audit.new("zh-CN", source, target).unexpected_han("欢迎归来").is_empty()
	}
	return {"ok": not checks.values().has(false), "checks": checks,
		"scope": "Source-copy detection with legitimate Japanese Kanji, shared homographs, dynamic Chinese fragments and unchanged non-Japanese checks"}
