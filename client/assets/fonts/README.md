# Runtime typography

The game bundles original, complete regional font files from Adobe's Source Han
projects. These are not subsets of the current UI strings. Player names and
future game text can use the full character maps shipped by the font authors.

- Title: Source Han Serif SC SemiBold 2.003. The heavier Song/Ming strokes suit
  carved stone panels, brass frames, card names, and chapter/dialog headings.
- Body: Source Han Sans SC Regular 2.005. Neutral strokes keep card effects,
  equipment descriptions, tooltips, and form fields readable at smaller sizes.
- Number: Source Han Sans SC Regular's native tabular figures, with the OpenType
  `pwid` proportional-width feature explicitly disabled at runtime. All ten
  digits advance 555 units in a 1000-unit em. Counters and combat numbers retain
  consistent digit widths; this family does not advertise a `tnum` feature.

`res://ui/palette.gd` owns the `title`, `body`, and `number` roles. System font
fallback is disabled, so the shipped result does not depend on installed fonts.
The title font can fall back to the bundled body font. Text baked into existing
illustrations or UI textures remains part of those images.

## License and provenance

Both fonts use the SIL Open Font License 1.1 and may be embedded and redistributed
with the game. Keep `LICENSE-SourceHanSans.txt` and `LICENSE-SourceHanSerif.txt`
with distributions. These original font files have not been renamed, modified,
or reduced; Adobe reserves the font name `Source`. The licenses cover the fonts,
not the game code, UI artwork, or audio.

`manifest.json` records upstream release tags, file URLs, upstream Git blob IDs,
SHA-256 hashes, file sizes, and character-map coverage. `verification.json`
records the local binary, character-coverage, and numeric-metric checks.

Upstream projects:

- https://github.com/adobe-fonts/source-han-sans/releases/tag/2.005R
- https://github.com/adobe-fonts/source-han-serif/releases/tag/2.003R

Full CJK fonts are intentionally retained rather than trimming to current UI
copy. These families do not promise every Unicode emoji or every historic rare
ideograph; no UI behavior should rely on a machine's emoji font.

## Resolution-independent UI clarity

The shared palette explicitly configures grayscale antialiasing, full automatic
hinting, quarter-pixel positioning, 2x raster oversampling and mipmaps for normal
UI text. The settings are applied to the loaded font resources, so imported
cache defaults do not determine the shipped profile.

Card faces also have a fractional local transform. They use separate MSDF font
resources derived from the same complete bundled font data (96px source size,
8px distance range). This preserves sharp card text through both grid and window
scaling. Number variants retain the existing `pwid: 0` feature. No font binaries,
weights, license files or character coverage were replaced.

Actual side-by-side raster/full-hint/2x/MSDF comparisons were captured at
960x540,1280x720 and1920x1080. Standard text uses the 2x profile; transformed card
text uses MSDF. See the current UI review report for original evidence and final
multilingual layout validation.

Reference: https://docs.godotengine.org/en/stable/tutorials/ui/gui_using_fonts.html
