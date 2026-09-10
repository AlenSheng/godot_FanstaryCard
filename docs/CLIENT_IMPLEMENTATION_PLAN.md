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

The supplied `ui_mockups_v058` set (15 modules) informed the current composition.
Its source directory is absent from the current workspace and needs archive
restoration; the reference set was previously delivered and used.
Implementation order: audit usable slices and missing assets; compose native
camp/codex/loadout/preparation/economy screens; compose private exploration and
battle screens; build clean Blender scene backdrops; verify native layout and
interaction at 1920x1080 and 1280x720, then repeat the real-server main loop.
[The art and supporting resource checklist](UI_MISSING_ASSETS.md) tracks current
delivery, review and archive tasks separately from protocol gaps and reusable
texture slices. Never display baked screenshot data as live state.

1920x1080 scalable landscape canvas; Chinese text; charcoal/teal stone,
warm parchment cards, restrained gold borders. Fixed side-on combat camera.
Mouse navigation, 1-5 selects cards, Space plays, R refreshes room state.
The lower-left sound control adjusts volume/mute and previews an effect; F10
toggles mute. Settings persist locally.
Only flash/scale combat feedback; no projectile or skeletal attack animation.
No difficulty or diamond shop, no PVE escape, no hidden map intelligence.

## Assets and acceptance

- Blender portal/stone plinth: original procedural rigid assembly, no external
  licence dependencies; inspect silhouette, normals, framing and exported load.
- Imported Cards/Art and UI: 418 bitmaps, comprising 217 UI images, 200 codex
  illustrations and one monster-card background, with source hashes and explicit
  mappings for three classes and all 12 monster species, including both boss stages.
  All 28 PNGs from the original 27-item request list exist. The frost_wraith image
  awaits species identification because no matching server ID exists; no redraw
  is currently required for that item.
- Shared card frame: 218x376 supplied quality textures with native runtime text;
  selected overlays must not obscure descriptions or intercept card input.
- Composite reference images with baked numerical state stay unused at runtime.
  The monster-card top border, class-weapon frame and complete visual consistency
  still need review against the current resource checklist.
- Typography: complete, unmodified Source Han Serif SC SemiBold 2.003 for titles
  and Source Han Sans SC Regular 2.005 for body text and tabular digits, totaling
  39.3 MiB. Both ship under SIL OFL 1.1, with provenance, hashes and licenses in
  `client/assets/fonts`. Runtime roles disable system-font fallback.
- Audio: 22 original, mono 48 kHz PCM16 short WAV effects ship under CC0 1.0 in
  `client/assets/audio`; `tools/generate_game_audio.py` is the editable source.
  The `Sound` service maps gameplay/UI events to a dedicated effects bus with
  eight voices, a limiter, per-cue throttling and local volume/mute settings.
  Recovered, duplicate, obsolete-battle and preview events stay silent.
- Bundled font coverage/roles/tabular digits and audio event routing are included
  in the passing 14-test native suite. Asset checks, reproducibility and the
  separate mixer/settings preview record are tracked in
  [Font and audio integration](FONT_AUDIO_INTEGRATION_20260910.md). These checks
  do not replace the final full visual review or release-build acceptance.

## Acceptance and outstanding capabilities

Validate parsing and scene instantiation, Protobuf round trips and malformed
messages, real REST errors, room actions gated by allowed_actions, replay
deduplication and snapshot recovery. Run Hall -> preparation -> matching ->
battle -> reward -> extraction -> settlement against a running local server.
Record and review actual gameplay before claiming complete playability.
The realtime protocol now carries authoritative typed damage, pure card-play
previews, passive/set status, inventory slots and on-demand relic contents.
Equipment/card progression quotes come from the server. Steam integration and
Windows export preflight are implemented and locally exercised; real AppID,
native plugin, templates and platform acceptance remain release prerequisites.
Mobile export remains outside the prototype scope. Track current evidence in
FUNCTION_COMPLETION_20260910.md and the client README.
