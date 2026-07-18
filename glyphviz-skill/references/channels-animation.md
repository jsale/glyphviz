# Channels animation — `gv_ch-map.csv` and `gv_ch-tracks.csv`

Time-series playback of node attributes. Drafted from working examples by a
skill-equipped Claude instance (The Breathing Century test, 2026-07), then
verified line-by-line against `glyphviz_core/channel_loader.py`,
`channel_engine.py`, and `glyphviz_gl/main_window.py` (2026-07-18) — every
formerly open question below is now source-confirmed.

## Model

Three pieces cooperate:

1. **Node file** — a node opts in by setting `ch_input_id` (canonical
   94-column slot 10) to a channel number; 0 or absent = not animated. The
   loader also accepts GaiaViz's `np_ch_in_id` name. Many nodes may share
   one channel; they all receive the same values.
2. **`gv_ch-map.csv`** — the patch bay. GlyphViz reads exactly **three
   columns**: `channel_id`, `track_id`, `attribute` — each row binds one
   channel to one node attribute, fed by one track. A channel may drive
   several attributes (multiple rows with the same `channel_id`), and
   several channels may read the same track. All other columns (`id`,
   `track_table_id`, `ch_map_table_id`, `record_id`, …) are **ignored** —
   include them as 0 only for GaiaViz-tool compatibility.
3. **`gv_ch-tracks.csv`** — the data. Every column named `ch<digits>` is
   track `<digits>`; **every other column is ignored, including
   `cyclecount`** (keep it anyway as a frame counter for readability /
   GaiaViz compatibility). Track columns do **not** need to be contiguous —
   `track_id` matches the number in the column name. **Each row is one
   frame**; total row count = the animation's frame count.

Values are **absolute attribute values, not deltas**: each frame the engine
replaces the bound attribute with the track's value for that row. Color
values are rounded and clamped to 0–255; `texture_id` is rounded with a
floor of 0. When playback stops (Stop button / Shift+Space), bound
attributes are restored to their CSV values.

## Bindable attributes (the complete list)

| Group | Attributes | Behavior |
|---|---|---|
| Position/orientation/size | `translate_x/y/z`, `rotate_x/y/z`, `scale_x/y/z` | hard-set each frame — **no interpolation between frames**; author enough frames for smooth motion (a GPS track played as `translate_x/y/z` works directly) |
| Velocities | `translate_rate_x/y/z`, `rotate_rate_x/y/z`, `scale_rate_x/y/z` | the channel sets the *speed*; the viewport integrates it at ~60 cycles/s. The integrated position/rotation persists after Stop (only the rate itself resets) |
| Color | `color_r/g/b/a` | literal 0–255 values; palettes play no role (see `color-palettes.md`) |
| Texture | `texture_id` | flip-book texture switching by `media/` index (see `textures-and-media.md`) |

Any other attribute name in the map is **silently skipped** — as is a
`track_id` with no matching `ch<id>` column, and a `ch_input_id` with no
matching `channel_id`. Nothing warns; validate the three-way join yourself
before shipping.

Animated `scale_*` is still subject to the 0.2 render floor.

## File discovery and playback (app behavior)

- **Auto-load on CSV open**: GlyphViz scans the node CSV's **folder** for
  files containing `ch-map` / `ch-track` in their names (`.csv`). It loads
  them only when exactly **one of each** matches — two candidate map files
  in a folder disable Channels entirely. So: one Channels scene per folder,
  and stem-style names (`myscene_gv_ch-map.csv`, `myscene_gv_ch-tracks.csv`)
  are convention, not a requirement.
- A Channels panel appears when bindings exist: frame slider, Play/Pause
  (Space), Stop (Shift+Space — resets to frame 0 and restores CSV values),
  an FPS slider (1–30, default 30), and a Loop checkbox (default on; off =
  playback pauses on the last frame).
- Frame indices clamp to `[0, frames − 1]`.

## Audio-synced playback (GlyphViz-only)

Put a one-line manifest named `<anything>_gv_audio.txt` next to the node
CSV containing a path (relative to that folder) to an audio file. On load,
frame advance is then driven by the audio's **real playback position**
instead of the FPS timer (the FPS slider disables) — render slowdowns cost
smoothness, never sync. Exactly one manifest per folder. This is the
supported way to sync animation to sound; video-texture audio cannot sync
(see `textures-and-media.md`).

## Authoring rules

- Validate the three-way join: every animated node's `ch_input_id` appears
  as a `channel_id` in the map; every map row's `track_id` has a `ch<id>`
  tracks column; every map row's `attribute` is in the table above.
- All tracks share one clock — one row count for the whole scene. Encode
  "not yet born" as `color_a` 0 rather than giving nodes different clocks,
  and carry a value forward through gaps in the source data (a hole
  desynchronizes that track from the rest).
- **Compression pattern**: nodes needing identical animation share one
  `ch_input_id` — e.g. ~1,700 glyphs animated with ~200 channels by keying
  channels on (birth year, final alpha) rather than per-node.
- Tracks files get wide fast; prefer fewer shared tracks over per-node
  tracks. UTF-8, CRLF, as everywhere.

## Recipes

- **Appear-and-stay timeline**: per-cohort step-function alpha track
  (`0,0,…,A,A,A`) bound to `color_a`.
- **Breathing glyph**: one track feeding `scale_x/y/z` via three map rows;
  keep the track's minimum ≥ 0.2.
- **Heat shift**: three tracks feeding `color_r/g/b`; precompute the
  gradient per frame (`color-palettes.md` has the built-in ramp formulas).
- **Path playback**: three tracks feeding `translate_x/y/z` directly —
  remember the values are coordinates in the *parent's topology system*
  (`topologies.md`).
- **Flip-book**: an integer track bound to `texture_id` steps through
  `media/` images.
