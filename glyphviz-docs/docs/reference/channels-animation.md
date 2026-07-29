# Channels Animation

Channels play a time series into node attributes, one row per frame. The
complete list of drivable attributes is `_ATTR_TO_FIELD`
(`glyphviz_core/channel_engine.py:24-63`); anything not in that table is
silently ignored. Clamps below come from `_FIELD_RANGE`
(`channel_engine.py:105-118`), and the transform/non-transform split from
`_TRANSFORM_FIELDS` (`channel_engine.py:81-90`).

## The three files

| File | Role | What is actually read |
|---|---|---|
| Node CSV | opts a node in | `ch_input_id` — any nonzero value names a channel. GaiaViz's `np_ch_in_id` is accepted too. Many nodes may share one channel |
| `*_gv_ch-map.csv` | the patch bay | exactly three columns: `channel_id`, `track_id`, `attribute` (`channel_loader.py:41-56`). Every other column is ignored |
| `*_gv_ch-tracks.csv` | the data | every column named `ch<digits>` is that track; **every other column is ignored, including `cyclecount`** (`channel_loader.py:59-76`). One row = one frame |

GlyphViz finds the pair by scanning the node CSV's own folder for names
containing `ch-map` and `ch-track`, and loads them only when **exactly one of
each** matches (`channel_loader.py:7-14`) — so one Channels scene per folder.

## Playback semantics

Values are **absolute, not deltas**, and there is **no interpolation between
frames** — `apply_frame` reads the exact row at that index
(`channel_engine.py:214-227`). Any smooth fade must be precomputed at
generation time. All tracks share one clock, so one row count covers the whole
scene. Frame indices clamp to `[0, frames − 1]`. Stop (Shift+Space) restores
every touched attribute to its CSV value (`channel_engine.py:240-248`).

Integer-valued attributes are rounded and clamped to their own valid range;
float attributes are applied exactly as written, negatives included.

## Drivable attributes

### Position, orientation, size

`translate_x/y/z`, `rotate_x/y/z`, `scale_x/y/z` — hard-set each frame. A GPS
track played into `translate_x/y/z` works directly. Animated `scale_*` is
still subject to the renderer's 0.2-per-axis floor.

### Velocities

`translate_rate_x/y/z`, `rotate_rate_x/y/z`, `scale_rate_x/y/z` — the track
sets the *speed*; the viewport integrates it at ~60 cycles/s. The integrated
position or rotation persists after Stop; only the rate itself resets.

### Color

`color_r/g/b/a` — literal values, rounded and clamped 0–255.

### Palette color

`palette_id` (clamped 0–25) and `color_index` — resolved into literal
`color_r/g/b` **every frame** (`channel_engine.py:229-238`). This is the one
place palette resolution happens automatically rather than on a `=`/`-`/`Alt+=`
keypress. `color_index` wraps
within the palette's own size (20 for the distinct-color palettes, 128 for
gradients) and `color_a` is never touched.

A single track carrying a palette index replaces the three-track
`color_r`/`color_g`/`color_b` pattern whenever a built-in ramp is close
enough — useful when the track *is* a quantity (pitch class, intensity,
category) rather than a color.

### Shape

`ratio`, `topo` (clamped 0–17), `geometry` (clamped 0–28), `mesh_id` — morph
a glyph's form, not just its size. `mesh_id` selects among meshes imported at
runtime via *File → Import Mesh*.

`topo` and `geometry` are integer flip-books like `texture_id`: hold a value
for several frames rather than stepping it every frame, or the scene reads as
noise.

### Texture

`texture_id` — flip-book texture switching by `media/` index.

### Visibility

`hide`, `show_text` — flags. Any positive track value reads as on, `0` as off.
`hide` blanks the glyph outright (cheaper to author than an alpha ramp, and
better for beat-locked flashes); `show_text` pins or unpins that node's tag
label regardless of the scene-wide tag settings.

### Scene settings (World row only)

`render_mode` (clamped 0–6), `fog_enabled`, `fog_start`, `fog_end` — read only
off the **World row (type=0)**. Give that row a `ch_input_id` like any other
node. They are inert on any other node type.

The World row's own `color_r/g/b` is the scene **background color**, animated
through the ordinary color binding above. One channel on that single row
changes the entire scene's mood at once, with no per-glyph animation data.

## What cascades to children

`translate`/`rotate`/`scale` and their rates, plus the three shape fields
`ratio`, `topo` and `geometry`, change where a node's **descendants** sit — so
animating them on a parent re-places the whole subtree:

- `ratio` is the parent's placement radius on Torus/Ztorus topologies.
- `topo` *is* the child-placement rule; animating it re-lays-out the children
  into a different arrangement entirely.
- `geometry` matters on a World Grid (type=6), where sphere vs. non-sphere
  geometry switches children between globe (KML lon/lat) and flat-window
  placement.

Everything else — color, palette, texture, mesh, visibility, the World scene
settings — changes what is drawn but never where anything sits. The
distinction is what lets the playback fast path refresh only the subtrees that
actually moved.

## Transport

A Channels panel appears whenever bindings exist: frame slider, Play/Pause
(Space), Stop (Shift+Space, which resets to frame 0 and restores CSV values),
an FPS slider (1–30, default 30), and a Loop checkbox (on by default; off
pauses on the last frame).

## Audio-synced playback

Put a one-line manifest named `<anything>_gv_audio.txt` next to the node CSV
containing a path, relative to that folder, to an audio file
(`channel_loader.py:17-38`). Frame advance is then driven by the audio's real
playback position instead of the FPS timer, which disables. Render slowdowns
then cost smoothness, never sync. Exactly one manifest per folder.

## Authoring checklist

Nothing warns about a broken join — validate it yourself:

1. Every animated node's `ch_input_id` appears as a `channel_id` in the map.
2. Every map row's `track_id` has a matching `ch<id>` column in the tracks file.
3. Every map row's `attribute` is in the tables above.

Also: carry values forward across gaps in the source data (a hole
desynchronizes that track from the rest), encode "not yet born" as `color_a`
0 rather than giving nodes different clocks, and let nodes needing identical
animation share one `ch_input_id` — tracks files get wide fast.

## Worked examples

- `examples/Mood_Background_Example/` — background color, fog and blend mode
  animated from one channel on the World row.
- `examples/Channel_Parameters_Example/` — seven labeled stations, one per
  attribute group, as a visual reference bench.

Two traps both examples document, because each looks like a rendering bug:
**fog cancels Additive blending** (fog fades geometry toward the background
color, so thick fog over a near-black sky subtracts exactly what Additive
adds), and a **torus child at tube angle 0 is `ratio`-invariant** (major and
minor radii always sum to the overall radius, so the outer equator never
moves — put children at tube angle 90/270 to see the swell).
