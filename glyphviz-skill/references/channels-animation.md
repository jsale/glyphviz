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
replaces the bound attribute with the track's value for that row.
Integer-valued attributes are rounded and clamped to their own valid range
(see the table); float attributes are applied exactly as written, negatives
included. When playback stops (Stop button / Shift+Space), bound attributes
are restored to their CSV values.

## Bindable attributes (the complete list)

| Group | Attributes | Behavior |
|---|---|---|
| Position/orientation/size | `translate_x/y/z`, `rotate_x/y/z`, `scale_x/y/z` | hard-set each frame — **no interpolation between frames**; author enough frames for smooth motion (a GPS track played as `translate_x/y/z` works directly) |
| Velocities | `translate_rate_x/y/z`, `rotate_rate_x/y/z`, `scale_rate_x/y/z` | the channel sets the *speed*; the viewport integrates it at ~60 cycles/s. The integrated position/rotation persists after Stop (only the rate itself resets) |
| Color | `color_r/g/b/a` | literal values, rounded and clamped 0–255 |
| Palette color | `palette_id`, `color_index` | resolved to literal `color_r/g/b` **every frame** — the one place palette resolution happens automatically instead of on a `=`/`-`/`Alt+=` keypress. `palette_id` clamps to 0–25, `color_index` wraps within the palette's own size (20 or 128), `color_a` is never touched. See `color-palettes.md` |
| Shape | `ratio`, `topo`, `geometry`, `mesh_id` | morph a glyph's *form*, not just its size. `topo` clamps 0–17, `geometry` 0–28, `mesh_id` floors at 0. All three of `ratio`/`topo`/`geometry` re-place a node's **children** as well (see below) |
| Texture | `texture_id` | flip-book texture switching by `media/` index (see `textures-and-media.md`) |
| Visibility | `hide`, `show_text` | flags — any positive track value reads as on, `0` as off. `hide` blanks the glyph without disturbing anything else; `show_text` pins/unpins its tag label |
| Scene settings (World node only) | `render_mode`, `fog_enabled`, `fog_start`, `fog_end` | read only off the **World row (type=0)** — give that row a `ch_input_id` like any other node. `render_mode` clamps 0–6, `fog_enabled` is a flag, the two fog distances are plain floats. Inert on any other node type. The World row's own `color_r/g/b` is the scene **background color**, animated through the ordinary Color binding above |

Any other attribute name in the map is **silently skipped** — as is a
`track_id` with no matching `ch<id>` column, and a `ch_input_id` with no
matching `channel_id`. Nothing warns; validate the three-way join yourself
before shipping.

Animated `scale_*` is still subject to the 0.2 render floor.

### What cascades to children

`translate`/`rotate`/`scale` (and their rates) plus the three shape fields
`ratio`, `topo`, `geometry` change where a node's **descendants** sit, so
animating them on a parent re-places the whole subtree:

- `ratio` is the parent's placement radius on Torus/Ztorus topologies.
- `topo` *is* the child-placement rule — animating it re-lays-out the
  children into a different arrangement entirely.
- `geometry` matters on a World Grid (type=6), where sphere vs. non-sphere
  geometry is what switches children between globe (KML lon/lat) and flat
  window placement. On an ordinary glyph it is purely cosmetic.

Everything else — color, palette, texture, mesh, `hide`, `show_text`, the
World scene settings — changes what is drawn but never where anything sits.

### One caution on animating `ratio`

A **Torus** glyph's mesh is rebuilt per distinct `ratio`, cached and never
freed, so the renderer quantizes it to 1% steps. Sweeping `ratio` on a torus
is fine and bounded; just don't expect sub-1% tube-thickness resolution.
Other geometries read `ratio` directly with no such cache.

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
- **One track, one color**: bind a single track to `color_index` and set the
  node's `palette_id` once in the node CSV. The track then carries a
  quantity directly — a pitch class into "20 Distinct Colors" (palette 0,
  wraps at 20), or a normalized 0–127 intensity into any gradient palette.
  Replaces the three-track `color_r/g/b` recipe above whenever a built-in
  ramp is close enough, and drops the tracks file to a third of the width.
- **Strobe / gate**: a 0-or-1 track bound to `hide`. Cheaper to author than
  an alpha ramp and it removes the glyph outright rather than fading it —
  good for beat-locked flashes. Bind `show_text` the same way to pop a label
  on a specific event.
- **Morphing glyph**: a track bound to `topo` re-lays-out a node's children
  into a different arrangement each time it steps; a track bound to
  `geometry` swaps the glyph's own shape. Both are integer flip-books like
  `texture_id` — hold a value for many frames rather than stepping it every
  frame, or the scene reads as noise.
- **Breathing torus**: a track bound to `ratio` swells a torus's tube (and
  moves its children's placement radius with it) without changing the
  glyph's overall size the way `scale_*` would.
- **Scene-wide mood**: give the World row (type=0) a `ch_input_id` and bind
  `color_r/g/b` for a background that shifts with the piece, `fog_start`/
  `fog_end` to pull depth in and out, or `render_mode` to switch the whole
  scene into Additive (1) for a glow-stacking chorus and back to Normal (0).
  One channel, four tracks, and every glyph is affected at once.
