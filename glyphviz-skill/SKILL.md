---
name: glyphviz
description: Generate and validate CSV scene files for GlyphViz, a 3D hierarchical data visualization app. Creates gv_node.csv (and optional gv_tag.csv / Channels animation files) with correct columns, topologies, hierarchy, links, colors, and labels. Use when users want to visualize data in GlyphViz, build glyph hierarchies, graphs/networks or branching structures, convert data to GlyphViz format, or debug why a GlyphViz CSV doesn't load or render as expected.
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
`references/node-csv-format.md` for the full column-by-column spec. This
minimal dialect is also what GlyphViz itself saves; the canonical 94-column
ANTz-compatible layout is an opt-in interop format, not what you will get back
out of the app.
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
2. **Author visible nodes at raw `scale_x/y/z` ≥ 0.2.** Scale renders exactly
   as written, but the viewer has an optional clamp (View → Enforce Minimum
   Glyph Size, off by default) that lifts rendered scale to 0.2/axis, and a
   sub-0.2 glyph is also hard to click. Staying above 0.2 makes a scene read
   the same either way. Never encode size as huge-parent × tiny-child.
3. **Author against Global Scale = 1.0**, and put any given distance in only
   one place. The viewer applies a base scale **B** that the CSV does *not*
   record (Properties → Global Scale, default **1.0**). B multiplies two
   things: every glyph's rendered size (`scale_x/y/z × B`), and the placement
   radius of a child on a **surface-riding** topology — a Sphere/Torus/
   Cylinder/Cube parent seats its children at `B × parent scale`, plus the
   child's own `translate_z` on top. B does **not** move Cartesian children
   (None, Plane), root nodes, or World Grid children: those are literal
   coordinates. The trap is mixing the two idioms in one scene — a ring whose
   radius comes from its parent's `scale` tracks B, while a marker pushed out
   by its own `translate_z` does not, so the two line up at one setting and
   drift apart at another. Measured: a Sphere child at `translate_z = 5` sits
   6.0 units out at B = 1 and 8.0 at B = 3, while its sibling on the surface
   goes 1.0 → 3.0. See `references/topologies.md`.
4. Colors are ints 0–255 (all four of r/g/b/a).
5. Save with **`encoding="utf-8"`** and CRLF line endings
   (`lineterminator='\r\n'`); sanitize control characters out of any label
   text — one bad byte can silently kill all tags.
6. `translate_x/y/z` are coordinates **in the parent's topology system**, not
   world units: lon/lat/alt under a Sphere parent, orbital-angle/tube-angle/
   elevation under a Torus parent, Cartesian under None/Plane.
7. The parent's optional **`topo_scale`** (default **1.0**) says how far one
   unit of a child's `translate` reaches, on exactly the axes that parent's
   topology reads as a **distance** rather than an angle. Angular axes
   (longitude, latitude, orbital/tube angle) are never scaled, so no value of
   it can distort a circular layout. Leave it at 1.0 for Cartesian-authored
   scenes; set **1/180 ≈ 0.005556** (the ANTz convention: a linear axis spans
   the parent's own extent) when you author a layout **in degrees** and want it
   to survive a switch between an angular and a linear topology — without it,
   0…360 on a Cube face is 360 *world units* and children fly out of sight.
   See `references/topologies.md`.
8. **Aiming a glyph is the topology's job, not `rotate_*`'s.** Under a Sphere
   (2), Point (7), Torus (3), Ztorus (11) or Cube (1) parent the engine already
   orients every child from its own coordinates: it applies a base rotation
   that puts the child's local **+Z** along the outward direction there
   (surface normal, or face normal on a Cube). And **+Z is the pointing axis of
   every directional geometry** — Cylinder (18/19), Cone (4/5) and Pin (16/17)
   are elongated along it; the flat shapes (20/21 Grid, 24/25/26
   Circle/Cross/Star) face along it. Put those together: a Cylinder child of a
   Sphere parent with **all three rotate fields 0** is a spoke pointing
   straight out, and the direction you want is its `translate_x` (longitude),
   *not* a rotation. Use `rotate_x/y/z` only to pose a glyph **relative to**
   that frame (a twist, a deliberate lean) — never to aim one the topology
   already aims. Hand-posed rotations compose *on top of* the base rotation, so
   fighting it is what turns an intended starburst into a flat stacked fan.
   If you do hand-pose, add a `rotation_mode` column and write **0** (Euler
   XYZ — each field spins its own axis); a file *without* the column loads in
   ANTz Heading/Tilt/Roll mode (Z-X-Z). If all rotations are 0, omit the
   column. Per-topology aim table, geometry axes, and the spokes recipe:
   `references/topologies.md`.
9. Labels: prefer inline `text` (label) and `link` (URL/file for the U key)
   columns — GlyphViz-native and simpler than a tag file. Use a companion
   `gv_tag.csv` only for ANTz/GaiaViz compatibility (`table_id` must be 0
   there). Labels are off by default (T toggles); show-all mode draws at
   most 500 tags per frame. Full rules: `references/tags-and-labels.md`.
10. Node types: 5 = ordinary glyph; 0 = World (scene settings, never drawn);
    1 = Camera; 6 = World Grid (children attach explicitly via
    `parent_id = grid.id`, place by lon/lat); 7 = Link (edge `parent_id` →
    `child_id`).
11. A **Link** has no pose — its `translate`/`rotate`/`scale` are ignored and
    both endpoints must resolve or it draws nothing. Its `geometry` picks how
    the edge looks: 27 (Line) for bulk graphs, 28 (Prism) for animated flow,
    or **any solid/wire glyph id, which renders that shape stretched from A to
    B** (a Cone points its apex at the B-end — an arrowhead). Thickness is
    `ratio`, never `scale_*`. See `references/links-and-edges.md`.

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
| Branching structure (tree, fern, dendrite) | Point (7) + Link limbs |
| **Graph / network** — nodes with no hierarchy, related by edges | **None (0)**, as flat ROOT rows whose `translate_x/y/z` are the world positions a 3-D force layout computed, plus Link rows. See "Laying out a graph" in `references/links-and-edges.md` |
| **Spokes from a hub** — clock face, starburst, wind rose, needles, rays | **Point (7)** (`translate_z` = full reach from the center) or **Sphere (2)** (`translate_z` = height above the surface). Both aim each child outward for you — see rule 8 |
| Free manual placement | None (0) |
| Geo-registered map/globe scene | World Grid node (type 6) as the parent |

Z-variants (9–13) are the same shapes with children pulled to the
center/axis. Full placement math, coordinate meanings per topology, and
worked examples: `references/topologies.md`.

Pick the topology to match the **shape of the data**, then set the parent's
`topo_scale` to match the **units you author children in** (rule 7): degrees
throughout → 1/180 on the linear-axis topologies, world units → leave 1.0.
Mixing the two within one scene is fine — `topo_scale` is per-parent.

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
6. **Check the geometry you actually promised — not just the file's validity.**
   The checks above pass on scenes that render completely wrong, because they
   only test the *file*. Ask what the scene claims visually and re-derive
   exactly that:
   - *positions* — compute each child's **world** coordinate from the parent's
     topology formula (`references/topologies.md`) and confirm the pattern:
     "12 spokes 30° apart, all at z = 0, all the same distance out."
   - **directions** — if the scene's meaning depends on which way a glyph
     *points* (spokes, needles, arrows, cones, tree limbs, anything elongated),
     positions are not enough: a set of correctly-placed rods can still be
     aimed wrong. Re-derive each glyph's aimed axis — under a Sphere/Point/
     Torus/Ztorus parent with rotations 0 it is the outward direction at that
     child's own `(translate_x, translate_y)` — and confirm it matches the
     direction the design calls for.
   - *counts and extremes* — the far end of the longest branch, the child
     nearest the parent's center, the one at a wrap point (360°/0°).

   Then **say what you checked and what you couldn't**. You cannot see the
   render, so a scene that "validated" has had its numbers checked and its
   appearance assumed — state that plainly when handing it over, and name the
   specific things the user should eyeball (here: "12 should point up, 3
   right"). One good look at the scene diagnoses in seconds what no amount of
   file validation can catch — see "Closing the loop" below for how to get one
   in a single round trip instead of many.
7. **Hand off**: tell the user to open the node CSV in GlyphViz (File > Open,
   or drag the CSV / scene folder / zip onto the window); a name-paired tag
   file loads automatically. Suggest small first (dozens of nodes) before
   scaling to thousands.

### Closing the loop — getting a picture

You cannot see the render, and a scene that "validated" has had its numbers
checked and its appearance assumed. The slow way to fix that is to hand the
scene over and wait for the user to open the app, orbit to a useful angle and
grab the screen — once per question, for as many questions as it takes. The
fast way is to ask for the right artifact **once**, or to render it yourself.

**If you have a shell** and the user's checkout with GlyphViz's Python
environment, render it and look, before handing anything over:

```bash
python tools/export_frame.py --csv scene_gv_node.csv --out check.png \
    --angles three-quarter,front,top --report
```

**If you don't** — the usual case, since this skill normally runs with no
GlyphViz install — ask the user to run exactly that one command and paste back
both the image and the report text. One command, one image, one paste.

- **`--angles` writes one labelled contact sheet.** A glyph that reads
  correctly from one viewpoint is routinely wrong from another (a starburst
  and a flat fan look identical head-on), so three views in one file is what
  makes a single paste conclusive. Choices: `three-quarter`, `front`, `back`,
  `side`, `top`, `bottom`.
- **`--report` is plain text**, so it costs nothing to paste and often answers
  the question outright — scene extents, **rendered** glyph size per hierarchy
  level (authored `scale` is not what you see; it is multiplied by every
  ancestor's scale and by Global Scale), how far each parent's children sit in
  multiples of the parent's own radius, whether the textures actually loaded,
  and how many labels are pinned versus hidden. **Ask for the report first**:
  most "I thought this was right and it isn't" gaps are visible in it, and it
  is cheaper for both of you than an image.
- Its defaults match how the app opens a file — Global Scale 1.0, labels off
  except `show_text = 1` nodes. Pass `--base-scale` or `--tags` when you need
  to see it another way, and say which you asked for.

**If the user has only the packaged app**, there is no CLI — `GlyphViz.exe`
takes no arguments. Ask for a screenshot, but ask well: name the viewpoint you
want (the Camera toolbar has Top / Front / Side), state what you expect to see
there, and batch your questions into one shot instead of one shot per
iteration. **GlyphViz Web** (`iluvdata.org/glyphvizweb/`) opens the same CSV in
a browser with nothing to install, which is often the quickest way for them to
look at all.

**Do not build your own previewer.** Rendering these CSVs "yourself" in a
small three.js or matplotlib scene means reimplementing the placement math —
and that math is precisely what is under suspicion whenever a scene looks
wrong, so a disagreement between your previewer and the app proves nothing and
you will end up debugging the previewer. If you want an independent check, make
it a *numbers* check: re-derive positions from the formulas in
`references/topologies.md` and compare them against what the design intended.

### When the app can build it faster than a script

Generating CSV is the right tool for *data*. For a **repeating composite
glyph** with no data behind it — the shape itself is the deliverable — the app
has interactive builders that write the same format, and pointing the user at
one beats scripting it blind:

- **Tools > Glyph Composer** (Ctrl+G) — describe a glyph one level at a time
  (count, geometry, topology, distribution, color ramp, Topology Scale with an
  Auto fit), preview it live, then insert it into the scene, save it as a JSON
  template, or use it as a Draw Mode brush. A level can also emit a **Link back
  to each object's parent**, which is what turns a stack of nested shells into a
  jointed, branching structure.
- **Hyperglyph Tree Designer** — a browser tool (no install) that designs
  branching, tree-like hyperglyphs with a live 3-D preview and exports them as
  Glyph Composer templates. Reach for it for trees, ferns, and dendrites.
- **Hyperglyph Lab** — batch/random generation of composite glyph designs.
- **Timeline Tower Designer** — a browser tool
  (`iluvdata.org/glyphviz/twitter_lab/tut_designer.html`) that turns an **X
  (Twitter) archive** into a finished scene: every post a needle radiating from
  a vertical time axis, height = when, bearing = time of day, rings on each
  needle carrying likes, reposts, hashtags and keyword hits. If a user asks for
  their X archive visualized, send them here rather than writing a generator —
  it reads the archive in the browser and uploads nothing.

These are GUI tools, not something this skill drives. Use them as a
recommendation; generate CSV yourself whenever real data is involved. The
placement math they rest on is documented either way — see "Direction-relative
branching" in `references/topologies.md` if you'd rather generate a tree
directly.

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
  texture via `rotate_rate_z` — directed-graph flow animation. Edges follow
  their endpoints every frame, so any animation that moves a node drags its
  edges with it.
- **Textures / video / audio**: `texture_id` is a 1-based index into the
  scene's `media/` folder (sorted: images, then videos; animated GIFs and
  videos animate automatically; video audio can be soloed to the selection).
  It applies to every **solid** geometry including the flat markers
  Circle/Cross/Star (24/25/26) — but is silently ignored by the wireframes,
  Point (22), Mesh (23), and plain Line links (27). See
  `references/textures-and-media.md` before authoring any textured scene.

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
  Two shape families there are easy to miss because they answer a request
  phrased as a *look* rather than as data: the **interior** geometries (29–32)
  for anything meant to be seen from within — a 360° video sphere, a panorama,
  a room — and the **Flat Ring** (33) for a ring that has to carry legible
  text or graduations, which a torus cannot.
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
- `references/links-and-edges.md` — Link (type 7) rows: the drawing modes
  (line / flow prism / any glyph stretched between the ends), `ratio` as
  thickness, recipes for directed graphs, weighted edges, bonds, and tree
  limbs, **and how to lay a graph out in 3D** — flat root rows carrying world
  positions, and the inverse-square repulsion law a 2D force layout gets wrong.
  **Read it before generating a graph, network, or branching scene.**
- `references/tags-and-labels.md` — inline `text`/`link` vs the companion
  tag file, title encodings, display behavior (incl. the 500-per-frame
  cap), and the U-key link/app-launch rules.
- `references/world-grid.md` — geo-registered scenes: flat plates and
  globes, extents windows, the grid scale rule, multi-grid scenes, and
  engine-verified placement examples. **Read it before building any
  map/geographic scene.**
- `references/troubleshooting.md` — the scene loaded, nothing errored, and it
  still looks wrong: a symptom index of the seventeen silent failure modes
  (children flung away by a topology change, textures ignored on the wrong
  geometry, inert palettes, labels that all vanish, edges that never draw, …)
  with the cause and fix for each. **Read it whenever a generated scene doesn't
  look right — and skim it before generating, since most entries are cheaper to
  avoid than to diagnose.**
- `references/OUTLINE.md` — what's planned but not yet written; do not invent
  content for those areas, derive from `glyphviz_core/` source when available.

## Worked examples

`examples/` holds six complete, verified scenes with READMEs that explain the
**design thinking**, not just the format. Read the closest one before designing
a scene of your own:

| If you're building… | Study |
|---|---|
| a hyperglyph — one repeating composite glyph carrying several variables | `Wind_Rose/`, `Decay_Chain/` |
| a geographic or multi-grid scene | `SD_Seismicity/`, `Wind_Rose/Monsoon_Year/` |
| time-series animation over many nodes | `Breathing_Century/`, `Decay_Chain/Secular_Equilibrium/` |
| a deep multi-branch hierarchy under one clock | `Duel_of_Dynasties/` |
| a live-data scene that regenerates and reloads | `RSS_News/` |
| a graph or network where the edges carry meaning | `Decay_Chain/` (110 links), `SD_Seismicity/` |
