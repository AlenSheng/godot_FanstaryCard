extends Node

func _ready() -> void:
	Game.gateway.set_process(false)
	Game.gateway.persist_session = false
	Game.gateway.online = true
	Game.connection = "美术预览 · 邮件系统"
	Game.lobby = {"player": {"userId": "mail-preview", "displayName": "旅人"}, "wallet": {"gold": 1280}}
	Game.mail = {
		"unreadCount": 2,
		"items": [
			{"id": "11111111-1111-1111-1111-111111111111", "title": "混沌领域 · 首通奖励", "body": "恭喜完成首次探索，以下奖励已发送至收件箱。", "sender": "系统", "read": false, "claimed": false, "attachments": [{"kind": "Gold", "amount": 500}, {"kind": "EquipmentFragments", "amount": 20}, {"kind": "HealthPotion", "amount": 2}]},
			{"id": "22222222-2222-2222-2222-222222222222", "title": "维护补偿", "body": "感谢你的耐心等待，请领取本次维护补偿。", "sender": "运营组", "read": false, "claimed": false, "attachments": [{"kind": "Gold", "amount": 200}]},
			{"id": "33333333-3333-3333-3333-333333333333", "title": "每日登录奖励", "body": "今日奖励已经领取，祝你探索顺利。", "sender": "系统", "read": true, "claimed": true, "attachments": [{"kind": "Gold", "amount": 100}]}
		]
	}
	# Ignore the startup gateway's delayed state notification while this offline
	# fixture is rendering its deterministic mail view.
	$UI.mail_modal_lock = true
	await get_tree().create_timer(0.3).timeout
	$UI.screen = "hall"
	$UI._render()
	await get_tree().create_timer(0.5).timeout
	$UI._reference._mail()
	await get_tree().create_timer(0.4).timeout
	var first_row: HBoxContainer = $UI._reference.get_node_or_null("MailModal/MailListScroll/MailListColumn/MailRow_11111111-1111-1111-1111-111111111111")
	assert(first_row != null and first_row.size.x >= 760.0, "Mail rows must preserve the list viewport width")
	var first_title: Label = first_row.get_node_or_null("MailOpenArea/MailTitle") if first_row != null else null
	assert(first_title != null and not first_title.text.is_empty(), "Mail row title must remain visible")
	RenderingServer.force_draw(false)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("res://../output"))
	get_viewport().get_texture().get_image().save_png(ProjectSettings.globalize_path("res://../output/mail_system_preview.png"))
	await get_tree().create_timer(60.0).timeout
	get_tree().quit()
