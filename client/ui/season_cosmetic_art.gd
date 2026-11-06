extends RefCounted

const Art = preload("res://ui/art.gd")
const P = preload("res://ui/palette.gd")
const Model = preload("res://ui/season_journey_reward_model.gd")
const ASSETS := {
	"trail-seeker": "UI/SeasonJourney/trail-seeker.png",
	"veilbound-seal": "UI/SeasonJourney/veilbound-seal.png",
	"relicbound-pathfinder": "UI/SeasonJourney/relicbound-pathfinder.png",
	"waymark-seal": "UI/SeasonJourney/waymark-seal.png",
	"convergent-sigil": "UI/SeasonJourney/convergent-sigil.png",
	"first-threshold": "UI/SeasonJourney/first-threshold.png",
	"fivefold-chronicle": "UI/SeasonJourney/fivefold-chronicle.png"
}

static func inventory() -> Dictionary:
	var value: Variant = Game.lobby.get("cosmetics", {})
	return value if value is Dictionary and Model.valid_inventory(value) else {}

static func equipped(slot: String) -> String:
	var owned := inventory()
	if owned.is_empty():
		return ""
	var field: String = {"AvatarFrame": "avatarFrameId", "CardBack": "cardBackId", "Title": "titleId"}.get(slot, "")
	var id: Variant = owned.selection.get(field)
	return str(id) if id is String else ""

static func entry(id: String) -> Dictionary:
	for item in inventory().get("owned", []):
		if item.get("cosmeticId") == id:
			return item
	return {}

static func texture(id: String) -> Texture2D:
	return Art.texture(str(ASSETS[id])) if ASSETS.has(id) else null

static func title() -> String:
	var item := entry(equipped("Title"))
	return P.localized(str(item.nameKey)) if not item.is_empty() else ""

static func portrait(ui: Control, rect: Rect2, hero: String, frame_id: String, node_prefix: String = "") -> void:
	var portrait_texture: Texture2D = Art.texture("UI/Hall/class_card_portrait_%s.png" % hero.to_lower())
	var inset := rect.size * 0.175 if not frame_id.is_empty() else Vector2.ZERO
	ui.picture(portrait_texture, Rect2(rect.position + inset, rect.size - inset * 2.0)).name = node_prefix + "CosmeticProfilePortrait"
	var frame := texture(frame_id)
	if frame != null:
		ui.picture(frame, rect).name = node_prefix + "EquippedAvatarFrame"
