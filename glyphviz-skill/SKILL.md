---
name: glyphviz
description: Generate and validate CSV scene files for GlyphViz, a 3D hierarchical data visualization app. Creates gv_node.csv (and optional gv_tag.csv / Channels animation files) with correct columns, topologies, hierarchy, colors, and labels. Use when users want to visualize data in GlyphViz, build glyph hierarchies, convert data to GlyphViz format, or debug why a GlyphViz CSV doesn't load or render as expected.
---

# GlyphViz CSV Generation Skill

GlyphViz renders hierarchical data as interactive 3D scenes: each CSV row is a
**node** (a 3D glyph); `parent_id` links rows into trees; a parent's **topology**
(`topo`) decides how its children are arranged around it (on a sphere surface,
around a torus ring, stacked on a pin, along a plot line, …).

GlyphViz descends from the ANTz/GaiaViz format family but has its own native
conventions. **Do not apply GaiaViz lore to GlyphViz** — several well-known
GaiaViz rules are wrong here (see "GaiaViz myths" below).

## The one required file: `gv_node.csv`

A header row plus one row per node. Only **20 columns are required**:

```
id,type,parent_id,branch_level,translate_x,translate_y,translate_z,
rotate_x,rotate_y,rotate_z,scale_x,scale_y,scale_z,
color_r,color_g,color_b,color_a,geometry,hide,topo
```

Everything else is optional with sensible defaults — see
`references/node-csv-format.md` for the full column-by-column spec (including
the canonical 94-column ANTz-compatible dialect GlyphViz itself saves).
**No infrastructure rows are required**: no camera rows, no grid row. A single
optional `type=0` World row sets the background color via `color_r/g/b/a`.

Minimal working scene (a torus parent with three orbiting children):

```csv
id,type,parent_id,branch_level,translate_x,translate_y,translate_z,rotate_x,rotate_y,rotate_z,scale_x,scale_y,scale_z,color_r,color_g,color_b,color_a,geometry,hide,topo,ratio
1,5,0,0,0,0,0,0,0,0,1,1,1,242,121,61,255,7,0,3,0.15
2,5,1,1,0,0,0,0,0,0,0.4,0.4,0.4,230,230,230,255,3,0,0,0.1
3,5,1,1,120,0,0,0,0,0,0.4,0.4,0.4,230,230,230,255,3,0,0,0.1
4,5,1,1,240,0,0,0,0,0,0.4,0.4,0.4,230,230,230,255,3,0,0,0.1
```

## Hard rules (each verified against `glyphviz_core`)

1. `id` unique, ≥ 1. `parent_id = 0` means root. `branch_level`: roots are
   **0**, children 1, etc.
2. **Visible nodes need raw `scale_x/y/z` ≥ 0.2** — the renderer floors
   rendered scale at 0.2/axis, so smaller values silently render bigger than
   authored. Never encode size as huge-parent × tiny-child.
3. Colors are ints 0–255 (all four of r/g/b/a).
4. Save with **`encoding="utf-8"`** and CRLF line endings
   (`lineterminator='\r\n'`); sanitize control characters out of any label
   text — one bad byte can silently kill all tags.
5. `translate_x/y/z` are coordinates **in the parent's topology system**, not
   world units: lon/lat/alt under a Sphere parent, orbital-angle/tube-angle/
   elevation under a Torus parent, Cartesian under None/Plane.
6. Rotations: if you hand-pose `rotate_x/y/z`, add a `rotation_mode` column
   and write **0** (Euler XYZ — each field spins its own axis). A file
   *without* the column loads in ANTz Heading/Tilt/Roll mode (Z-X-Z). If all
   rotations are 0, omit the column.
7. Labels: prefer inline `text` (label) and `link` (URL/file for the U key)
   columns — GlyphViz-native and simpler than a tag file. Use a companion
   `gv_tag.csv` only for ANTz/GaiaViz compatibility (`table_id` must be 0
   there). Labels are off by default (T toggles); show-all mode draws at
   most 500 tags per frame. Full rules: `references/tags-and-labels.md`.
8. Node types: 5 = ordinary glyph; 0 = World (scene settings, never drawn);
   1 = Camera; 6 = World Grid (children attach explicitly via
   `parent_id = grid.id`, place by lon/lat); 7 = Link (edge `parent_id` →
   `child_id`).

## GaiaViz myths that do NOT apply to GlyphViz

- ~~"Files must have exactly 94 columns"~~ — 20 required; the rest default.
- ~~"The first 6 infrastructure rows are mandatory"~~ — none are.
- ~~"line_width must be > 0 or nodes won't display"~~ — `line_width` and
  `point_size` are round-trip-only in GlyphViz (Point size comes from `ratio`).
- ~~"size must be 420"~~ — round-trip-only (the saver defaults it to 420).
- ~~"branch_level starts at 1 for roots"~~ — GlyphViz roots are level 0.
- ~~"np_ prefixes"~~ — never author `np_` files; that dialect is read-side
  interop for genuine GaiaViz data only.

## Choosing topologies (`topo` on the PARENT arranges its children)

| Data shape | Topology |
|---|---|
| Cyclical (months, hours, categories on a ring) | Torus (3) |
| Geographic / directional | Sphere (2) — children use lon/lat/alt |
| Sequential stack | Pin (5) or Rod (6) |
| Exactly ≤ 6 categories | Cube (1) — one face each via `facet` 1–6 |
| Matrix / small grid | Plane (8) |
| Helical / ranked spiral | Spiral (14) |
| Line plot, GPS track, time series path | Plot (16) |
| Heightfield, terrain, FFT | Surface (17) |
| Free manual placement | None (0) |
| Geo-registered map/globe scene | World Grid node (type 6) as the parent |

Z-variants (9–13) are the same shapes with children pulled to the
center/axis. Full placement math, coordinate meanings per topology, and
worked examples: `references/topologies.md`.

## Workflow

1. **Understand the data**: hierarchy depth, what's cyclical vs sequential vs
   geographic, what should map to color/size/position. Ask before assuming.
2. **Design the tree on paper first**: one row per node, levels and topologies
   chosen per the table above.
3. **Generate with a script** (pandas or csv module), never by hand-editing
   CSV text. Start ids at 1; give parents their topology; place children in
   the parent's coordinate system.
4. **Color**: write literal `color_r/g/b` for the on-load look, and *also*
   set `color_index` (+ optional `palette_id`, 26 built-in palettes) to
   pre-wire in-app recoloring with the =/− and Alt+=/Alt+− keys. Palette
   fields never repaint on load — they resolve only on keypress. Palette
   tables, gradient formulas, and the category-coloring recipe:
   `references/color-palettes.md`.
5. **Validate before delivering**: re-read the file with pandas; check
   required columns present, ids unique, every `parent_id` exists (or 0),
   colors in range, visible scales ≥ 0.2, UTF-8 clean.
6. **Hand off**: tell the user to open the node CSV in GlyphViz (File > Open,
   or drag the CSV / scene folder / zip onto the window); a name-paired tag
   file loads automatically. Suggest small first (dozens of nodes) before
   scaling to thousands.

## Animation options (quick pointers)

- **Rate fields**: `translate_rate_*` / `rotate_rate_*` / `scale_rate_*` are
  per-cycle velocities (~60 cycles/s) applied continuously — the cheapest way
  to add motion (spinning tori, drifting clouds). `freeze` ≠ 0 suspends a node.
- **Channels**: full time-series playback of node attributes via
  `gv_ch-map.csv` / `gv_ch-tracks.csv`, bound per-node with `ch_input_id`
  — positions, rotations, scale, rates, colors, even `texture_id`
  flip-books, optionally synced to an audio file. See
  `references/channels-animation.md`.
- **Link flow**: Link nodes (type 7) with geometry 28 (Prism) scroll their
  texture via `rotate_rate_z` — directed-graph flow animation.
- **Textures / video / audio**: `texture_id` is a 1-based index into the
  scene's `media/` folder (sorted: images, then videos; animated GIFs and
  videos animate automatically; video audio can be soloed to the selection).
  See `references/textures-and-media.md` before authoring any textured
  scene.

## Live-updating scenes

A generator may loop (fetch → rebuild → rewrite, e.g. a `--watch N`
flag) and pair with the app's **File > Watch and Reload** (Ctrl+R),
which polls the open node CSV's mtime and hot-reloads on change,
preserving the user's camera, selection, and Channels playback. Rules
for the generator side: write every file **atomically** (temp file +
`os.replace`), and write companion tag/channel files *first* and the
node CSV *last*, so a triggered reload never sees a torn or mismatched
scene. Worked exemplar: `examples/RSS_News/`.

## References

- `references/node-csv-format.md` — the complete, verified column spec
  (required/optional/94-column tables, node types, geometry & topology id
  tables, tag file format). **Read it before generating anything nontrivial.**
- `references/topologies.md` — per-topology placement math: coordinate
  meanings, formulas, outward-orientation rules, Plot/Surface overlay
  requirements, and engine-verified worked examples. **Read it before
  positioning children under any non-Cartesian topology.**
- `references/color-palettes.md` — the 26 palettes (full 20-color table,
  gradient formulas), `color_index`/`palette_id` resolution semantics, and
  coloring recipes for generated data.
- `references/textures-and-media.md` — how `texture_id` maps to `media/`
  files, animated GIF/video textures, and video audio (incl. Solo Audio to
  Selection).
- `references/channels-animation.md` — the ch-map/ch-tracks formats, the
  complete bindable-attribute list, playback/audio-sync behavior, and
  animation recipes. **Read it before generating any Channels files.**
- `references/tags-and-labels.md` — inline `text`/`link` vs the companion
  tag file, title encodings, display behavior (incl. the 500-per-frame
  cap), and the U-key link/app-launch rules.
- `references/world-grid.md` — geo-registered scenes: flat plates and
  globes, extents windows, the grid scale rule, multi-grid scenes, and
  engine-verified placement examples. **Read it before building any
  map/geographic scene.**
- `references/OUTLINE.md` — what's planned but not yet written; do not invent
  content for those areas, derive from `glyphviz_core/` source when available.
