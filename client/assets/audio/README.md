# FantasyCard sound library

An original, short-form sound library for the project's charcoal, weathered
stone, parchment, muted brass, and five-element fantasy style. It contains 33
short mono, 48 kHz, 16-bit PCM WAV cues plus two looping generated room
ambience beds. The module BGM is supplied separately as external MP3 assets
copied from `art/BGM`; the login video is supplied there as well.

## Source and license

The WAV cues and room ambience are synthesized locally by
`tools/generate_game_audio.py` from seeded random noise and mathematical
oscillators. The synthesis combines
band-limited noise, damped inharmonic material resonances, layered friction,
air envelopes, and water-drop pitch decay. The source script is the editable
production source; there are no missing recording sessions or sample packs.

The generated WAV files and their sound-design descriptions are dedicated to
the public domain under **CC0 1.0 Universal**. They may be used commercially,
modified, and redistributed, including inside exported game builds. Attribution
is welcome but is not required. No third-party asset credit is required.
See `LICENSE.txt` and <https://creativecommons.org/publicdomain/zero/1.0/>.
This dedication applies only to the generated WAV library, not to the external
MP3 BGM, login video, other project files, or third-party dependencies.

## Regenerate and verify

From the repository root:

```powershell
python -X utf8 tools/generate_game_audio.py
```

Production environment: Python 3.10.11, NumPy 2.2.6, SciPy 1.15.3. The seed is
`20260910`; each sound has a separate key-derived seed so adding another sound
does not alter existing sounds. For byte-identical regeneration, keep the
Python/NumPy/SciPy environment fixed. No network connection is used.

`manifest.json` records the resource paths, duration, peak/RMS level, active
duration, silence/tail checks, DC offset, SHA-256 checksum, and sound-design
description for every sound. The generator reads each rendered WAV back and
rejects clipping, an invalid format, silent/near-silent output, significant DC
offset, excessive leading silence, an abrupt tail, or an incorrect target peak.

The generator rebuilds only the short cues and generated ambience; it does not
create or overwrite the external MP3 BGM. It also writes these review artifacts
outside the game export:

- `artifacts/audio-font-validation/sound_preview.wav`: all short cues in manifest
  order, separated by 450 ms of silence; looping ambience is validated
  separately in the manifest and numeric report.
- `artifacts/audio-font-validation/sound_preview_index.json`: start times and
  descriptions for the listening reel.
- `artifacts/audio-font-validation/sound_validation.json`: numeric checks for
  all short cues and all looping tracks.

## Playback guidance

The files already contain layered event levels: frequent selection/movement
cues peak at -16/-17 dBFS, combat cues at -10/-11 dBFS, and major confirmations
at -12/-13 dBFS. `gain_db` in the manifest is therefore zero by default. These
peaks leave room for limited simultaneous effects; they do not replace a
dedicated SFX bus with a sensible user-adjustable master level.

Keep repeated UI clicks quiet, suppress duplicate or recovered network events,
and bound simultaneous voices. Choose one representative elemental impact for
a grouped hit instead of playing all damage groups at once. Extraction start
is a single notification, not a loop. Short cues are deliberately concise
(0.14-1.02 seconds). `ambience_hall.wav` and `ambience_battle.wav` are
24-second low-level loops. The runtime loads the named external MP3 module BGM,
crossfades between contexts, and exposes independent SFX, music, and ambience
levels in the settings panel.
