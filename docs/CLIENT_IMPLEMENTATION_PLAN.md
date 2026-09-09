# Godot client implementation

Primary engine: Godot 4.7.2, explicitly requested instead of GDD's Unity baseline.
Server and configuration remain authoritative. Reference: GDD v0.67,
GameFactory-3A/agent_skills/setting_overview.md, server/docs/CLIENT_INTEGRATION.md.

## Delivery sequence

1. Native project, REST gateway, schema-derived Protobuf codec and session store.
2. Login, three classes, lobby, codex/decks, inventory/loadouts/enhancement,
   gold shop/market, exploration preparation and matchmaking readiness.
3. Private room snapshots, 6x6 map, target/card selection, five hand slots,
   rewards, contextual actions, duel controls and settlement acknowledgement.
4. Blender environment props and presentation resources, followed by actual
   engine validation and representative interaction checks.

## Presentation

The supplied `ui_mockups_v058` set (15 modules) now drives screen composition.
Implementation order: audit usable slices and missing assets; compose native
camp/codex/loadout/preparation/economy screens; compose private exploration and
battle screens; build clean Blender scene backdrops; verify native layout and
interaction at 1920x1080 and 1280x720, then repeat the real-server main loop.
`docs/UI_MISSING_ASSETS.md` tracks generation requests separately from protocol
gaps and reusable texture slices. Never display baked screenshot data as live state.

1920x1080 scalable landscape canvas; Chinese text; charcoal/teal stone,
warm parchment cards, restrained gold borders. Fixed side-on combat camera.
Mouse navigation, 1-5 selects cards, Space plays, R refreshes room state.
Only flash/scale combat feedback; no projectile or skeletal attack animation.
No difficulty or diamond shop, no PVE escape, no hidden map intelligence.

## Assets and acceptance

- Blender portal/stone plinth: original procedural rigid assembly, no external
  licence dependencies; inspect silhouette, normals, framing and exported load.
- User-supplied Cards/Art and UI: 200 codex illustrations, three class portraits,
  three matching monster illustrations, clean panels, frames, inventory icons
  and battle controls imported with source hashes and an explicit ID mapping.
  Nine monster illustrations remain missing; frost_wraith has no matching ID.
- Shared card frame: 218x376 supplied quality textures with native runtime text;
  selected overlays must not obscure descriptions or intercept card input.
- Composite reference images with baked numerical state stay unused at runtime.
  Built-in imageGen is unavailable; full visual consistency remains to be reviewed.
- Typography: installed CJK font for local preview; redistribution requires a
  separately licensed bundled font before release.

## Acceptance and outstanding capabilities

Validate parsing and scene instantiation, Protobuf round trips and malformed
messages, real REST errors, room actions gated by allowed_actions, replay
deduplication and snapshot recovery. Run Hall -> preparation -> matching ->
battle -> reward -> extraction -> settlement against a running local server.
Record and review actual gameplay before claiming complete playability.
Server protocol currently exposes total combo damage, not per-element resolved
segments or authoritative combo preview. Do not invent those numbers in UI.
Steam/platform auth, store distribution and mobile export require separate
platform SDK integration and acceptance. Track actual evidence in client README.
