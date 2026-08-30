# GlyphViz Node CSV Format

Verified against `glyphviz_core/csv_reader.py` and `glyphviz_core/node.py`
(2026-07-14). The loader is `load_node_csv()`; the writer is `save_node_csv()`.

## Two dialects

GlyphViz reads and writes the same conceptual format at two levels of
completeness:

1. **Minimal (authoring) dialect** — a header row plus only the columns you
   need. Just 20 columns are required (see below); every other column has a
   documented load-time default. This is the recommended dialect for
   generated/scripted data: the repo's own examples (e.g.
   `examples/Topology_Example/topology_example_gv_node.csv`) are 22-column
   files. **There are no mandatory "infrastructure rows"** — no camera rows, no
   grid row, no World row are required (a World row is optional, see Node
   types).

2. **Canonical 94-column dialect** — the full ANTz/GaiaViz-compatible layout.
   `save_node_csv()` always writes this (plus optional GlyphViz extension
   columns appended after the 94). Use it when a file must round-trip through
   ANTz/GaiaViz tooling.

Column *order does not matter to the GlyphViz loader* (pandas reads by header
name), but the canonical order below is what GlyphViz writes and what ANTz
expects.

## Required columns (loader fails if any is missing)

All 20: `id`, `type`, `parent_id`, `branch_level`, `translate_x/y/z`,
`rotate_x/y/z`, `scale_x/y/z`, `color_r/g/b/a`, `geometry`, `hide`, `topo`.

| Column | Type | Meaning |
|---|---|---|
| `id` | int | Unique node id. Use ids ≥ 1 (`parent_id = 0` is the root sentinel). |
| `type` | int | Node type: 0 World, 1 Camera, 5 ordinary glyph (convention), 6 World Grid, 7 Link. See Node types. |
| `parent_id` | int | 0 = root node; otherwise the parent's `id`. This alone defines the hierarchy. |
| `branch_level` | int | Tree depth: **roots are 0**, children 1, etc. (GaiaViz files use 1 for roots; GlyphViz uses this field for select-by-level and sibling navigation, not for attachment.) |
| `translate_x/y/z` | float | Position **in the parent's topology coordinate system** (Cartesian offsets for topo None/Plane; longitude/latitude/altitude for Sphere; orbital-angle/tube-angle/elevation for Torus; etc. — see `topologies.md`). |
| `rotate_x/y/z` | float | Orientation in degrees, interpreted per `rotation_mode` (see optional columns). |
| `scale_x/y/z` | float | Per-axis scale, rendered exactly as authored. **An optional viewer setting (View → Enforce Minimum Glyph Size, off by default) clamps rendered scale to 0.2 per axis** — so a scene whose sizes carry meaning reads correctly either way if you keep visible nodes at raw scale ≥ 0.2, and never encode size as huge-parent × tiny-child. Below ~0.2 a glyph also gets hard to click. |
| `color_r/g/b/a` | int | 0–255. Alpha blends per the World node's `render_mode`. |
| `geometry` | int | Shape id 0–28 (see Geometry ids). |
| `hide` | int | 1 = do not render this node. |
| `topo` | int | Topology id 0–17 controlling how **children** of this node are placed (see Topology ids). |

## Optional tracked columns (read into Node fields, with load defaults)

| Column | Default when column absent | Notes |
|---|---|---|
| `ratio` | 0.1 | Geometry/topology aspect parameter: a Torus parent's tube (minor) radius as a fraction of major radius — children of Torus/Ztorus parents sit on the tube defined by the **parent's** ratio. Also the **only** control over a Point glyph's size: `geometry` = 22 draws a `GL_POINTS` sprite `max(2, ratio × 20)` **pixels** wide, which ignores `scale_x/y/z` entirely and does not shrink with distance. Sizing a point cloud therefore means writing `ratio` per node, not `scale_*` — and if you want size to read as depth, use the flat markers (24/25/26) or a solid geometry instead. On a **Link** (type 7) it is the edge's thickness in every drawing mode: `max(ratio × 20, 1)` pixels for a Line, and the radius in world units for a stretched glyph (`scale_*` is inert there). See `links-and-edges.md`. |
| `topo_scale` | 1.0 | **GlyphViz-only.** How far one unit of a **child's** `translate` reaches, for the axes this node's topology reads as a **distance** rather than an angle (a Cube facet's two axes, Pin/Cylinder height, altitude above a Sphere, all three axes of the Cartesian family). Angular axes — longitude, latitude, orbital and tube angles — are never scaled, so no value of this can distort a circular layout. 1.0 = one translate unit is one world unit (GlyphViz's original behavior, hence the load default). **1/180 ≈ 0.005556 = the ANTz convention**, where a linear axis spans the parent's own extent: translate 180 reaches the edge of a cube facet exactly as 180° of longitude reaches the far side of a sphere. Set it on the **parent**, like `topo` and `ratio`. Extension column, written only when ≠ 1.0. See `topologies.md`. |
| `subspace` / `facet` | 0 | Cube-topology face selector. `subspace` (GaiaViz spelling, 0-indexed) wins if present; else `facet` − 1 (legacy ANTz/GlyphViz spelling, 1-indexed: 1=+X, 2=−X, 3=+Y, 4=−Y, 5=+Z, 6=−Z), clipped at 0. `save_node_csv` always writes `facet`. |
| `texture_id` | 0 | 0 = untextured; otherwise a 1-based index into the alphanumerically sorted files of the scene's `media/` folder (images first, then videos) — see `textures-and-media.md`. |
| `mesh_id` | 0 | **GlyphViz-only.** Selects an imported mesh for `geometry` = 23 (Mesh). Written only when some node uses it. |
| `rotation_mode` | **1 (Heading/Tilt/Roll)** | **Asymmetric by design**: a missing column means the file predates the feature and loads as ANTz's Z-X-Z Heading/Tilt/Roll convention; a freshly constructed `Node()` in code defaults to 0 (Euler XYZ, each field rotates about its own axis). Written on save only when some node's value would be misread by the load fallback (i.e. any node with mode ≠ 1). **Generated files that hand-pose rotations should write `rotation_mode` = 0 explicitly.** |
| `color_index`, `palette_id` | 0, 0 | ANTz-style palette color selection. Inert on load/render — resolved into `color_r/g/b` only when the user cycles with =/− (color_index) or Alt+=/Alt+− (palette). 26 built-in palettes (0 = the 20-distinct-colors default). `palette_id` has no slot in the 94 columns; appended as an extension column only when nonzero. Full palette tables, gradient formulas, and authoring recipes: `color-palettes.md`. |
| `translate_rate_x/y/z`, `rotate_rate_x/y/z`, `scale_rate_x/y/z` | 0.0 | Per-cycle velocities added every animation tick (nominally 60/s, ANTz convention). Nonzero `freeze` (extras) suspends them. `rotate_rate_z` also scrolls a Link prism's texture (flow animation). |
| `text`, `link` | "" | **GlyphViz-only inline label columns.** `text` = label drawn in the viewport; `link` = URL/file opened by the U key. If *neither* column is present, the loader falls back to the companion tag file (see Tag companion file). Written on save only when some node has a value. |
| `show_text` | 0 | **GlyphViz-only.** 1 = pin this node's tag text on: it draws whenever the node draws, regardless of the viewport's "Show Tag Labels" / "…of Selected" settings, and is exempt from the 500-tags-per-frame cap. The node's own `hide` and the `\` draw limit still apply. Use it for the handful of labels a scene should always show; don't set it on thousands of nodes. |
| `render_mode` | 0 (Normal) | **World-node-only** scene blend mode: 0 Normal, 1 Additive, 2 Subtractive, 3 Dark/Multiply, 4 Off, 5 Screen, 6 Premultiplied. Extension column, written only when ≠ 0. |
| `fog_enabled`, `fog_start`, `fog_end` | 0, 0.0, 0.0 | **World-node-only** fog (fades to the World bg color). Extension columns, written only when nonzero. |
| `tag_color_mode` | 0 (Uniform) | **World-node-only.** 0 = every tag label uses the single `tag_color_r/g/b` below; 1 = each label takes its own node's `color_r/g/b`, so a label reads as belonging to the glyph it names. The dark drop shadow behind tag text is fixed and not configurable. |
| `tag_color_r/g/b` | 255, 255, 200 | **World-node-only** tag label color (pastel yellow by default), used when `tag_color_mode` = 0. All three are written together or not at all. |
| `tag_font_size` | 11 | **World-node-only, GlyphViz-only.** Point size of every tag label in the scene, 6–36 (values outside that clamp on render). Labels were painted at a fixed 9 pt before this column existed, so a file without it loads at 11 pt — the default is deliberately a size change for old scenes. Written only when ≠ 11. |
| `ref_grid_color_r/g/b` | 56, 56, 71 | **World-node-only.** Color of the procedural reference grid the viewport draws under scenes that contain no World Grid node (dark gray by default). A type-6 World Grid paints its own lattice from its own `color_r/g/b` and ignores this. All three are written together or not at all. |

Every other column in the file is preserved verbatim in `Node.extras` and
round-tripped by `save_node_csv` — unknown columns are never lost or reordered
within a session.

## Canonical 94-column order

Formats: **int** unless listed; **float** = written with 6 decimal places;
**int|float** = written as int when integral, else 6-dp float.

Use column key: ✅ read into a Node field · ⚙ interpreted from extras in a
specific context · ↻ round-trip only (preserved, never interpreted by
GlyphViz).

| # | Column | Format | Use | Notes |
|---|---|---|---|---|
| 1 | `id` | int | ✅ | |
| 2 | `type` | int | ✅ | |
| 3 | `data` | int | ↻ | Written as a copy of `id` by convention. |
| 4 | `selected` | int | ↻ | |
| 5 | `parent_id` | int | ✅ | |
| 6 | `branch_level` | int | ✅ | |
| 7 | `child_id` | int | ⚙ | **Link nodes (type 7): the B-end node id** (edge runs `parent_id` → `child_id`). Otherwise round-trip. |
| 8 | `child_index` | int | ↻ | |
| 9 | `child_count` | int | ↻ | |
| 10 | `ch_input_id` | int | ⚙ | **Channels**: binds this node to a channel id in the ch-map/ch-tracks pair (GaiaViz alias `np_ch_in_id` also recognized) — see `channels-animation.md`. Also settable in the app (Properties > Selected Node > **Channel In**), which rebinds a playing animation on the spot; it writes back through whichever of the two spellings the file already used. |
| 11 | `ch_output_id` | int | ↻ | |
| 12 | `ch_last_updated` | int | ↻ | |
| 13 | `average` | int | ↻ | |
| 14 | `samples` | int | ↻ | Default 1. |
| 15–17 | `aux_a_x/y/z` | float | ↻ | |
| 18–20 | `aux_b_x/y/z` | float | ↻ | |
| 21 | `color_shift` | float | ↻ | |
| 22–25 | `rotate_vec_x/y/z/s` | float | ↻ | Quaternion; preserved only. |
| 26–28 | `scale_x/y/z` | float | ✅ | |
| 29–31 | `translate_x/y/z` | float | ✅ | |
| 32–34 | `tag_offset_x/y/z` | float | ↻ | |
| 35–37 | `rotate_rate_x/y/z` | float | ✅ | |
| 38–40 | `rotate_x/y/z` | float | ✅ | |
| 41–43 | `scale_rate_x/y/z` | float | ✅ | |
| 44–46 | `translate_rate_x/y/z` | float | ✅ | |
| 47–49 | `translate_vec_x/y/z` | float | ↻ | |
| 50 | `shader` | int | ↻ | |
| 51 | `geometry` | int | ✅ | |
| 52 | `line_width` | float | ↻ | Default 1.0. **Not rendered by GlyphViz** (unlike GaiaViz, where 0 hides nodes). |
| 53 | `point_size` | float | ↻ | Not rendered by GlyphViz; Point size comes from `ratio`. |
| 54 | `ratio` | float | ✅ | |
| 55 | `color_index` | int | ✅ | |
| 56–59 | `color_r/g/b/a` | int | ✅ | |
| 60 | `color_fade` | int | ↻ | |
| 61 | `texture_id` | int | ✅ | |
| 62 | `hide` | int | ✅ | |
| 63 | `freeze` | int | ⚙ | Nonzero suspends this node's rate animation. |
| 64 | `topo` | int | ✅ | |
| 65 | `facet` | int | ✅ | 1-indexed on disk; loads into `Node.subspace` = facet − 1 (unless a `subspace` column overrides). |
| 66–68 | `auto_zoom_x/y/z` | int | ↻ | |
| 69–71 | `trigger_hi_x/y/z` | int\|float | ⚙ | **World Grid (type 6): `trigger_hi_x` = extents lon max, `trigger_hi_y` = lat max.** |
| 72–74 | `trigger_lo_x/y/z` | int\|float | ⚙ | **World Grid: `trigger_lo_x` = lon min, `trigger_lo_y` = lat min.** Degenerate axis (hi ≤ lo, e.g. legacy all-zero) falls back to whole-earth (−180..180, −90..90). |
| 75–77 | `set_hi_x/y/z` | float | ↻ | |
| 78–80 | `set_lo_x/y/z` | float | ↻ | |
| 81–83 | `proximity_x/y/z` | float | ↻ | |
| 84–86 | `proximity_mode_x/y/z` | int | ↻ | |
| 87–89 | `segments_x/y/z` | int | ⚙ | Defaults 16, 16, 0. **World Grid: `segments_x/y` = rendered cell counts** (1 = plain rectangle outline; on a globe they set the graticule). |
| 90 | `tag_mode` | int | ↻ | |
| 91 | `format_id` | int | ↻ | |
| 92 | `table_id` | int | ↻ | |
| 93 | `record_id` | int | ⚙ | Tag matching: companion-tag-file rows attach to nodes by `record_id` (falling back to `id`). Save defaults it to the node's own `id`. |
| 94 | `size` | int | ↻ | Default 420 (ANTz convention). |

### GlyphViz extension columns (appended after the 94)

Each is written **only when omitting it would misread on reload**:

| Column | Written when |
|---|---|
| `text` | any node has a label |
| `link` | any node has a link |
| `rotation_mode` | any node's mode ≠ Heading/Tilt/Roll (1) |
| `mesh_id` | any node references an imported mesh |
| `palette_id` | any node has a non-default palette |
| `render_mode` | World render mode ≠ Normal |
| `fog_enabled` / `fog_start` / `fog_end` | fog configured |
| `show_text` | any node pins its tag text on |
| `tag_color_mode` | World tag color mode ≠ Uniform (0) |
| `tag_color_r` / `tag_color_g` / `tag_color_b` | World tag color ≠ the pastel-yellow default |
| `tag_font_size` | World tag font size ≠ 11 pt |
| `ref_grid_color_r` / `_g` / `_b` | World reference-grid color ≠ the default gray |

This rule keeps untouched legacy ANTz/GaiaViz files byte-for-byte stable
across a load/save round-trip.

## File formatting rules

- **Encoding: UTF-8, explicitly.** One stray byte (e.g. an unsanitized control
  character in a title) can silently break parsing downstream — always pass
  `encoding="utf-8"` when generating, and sanitize control characters out of
  label text.
- **Line endings**: GlyphViz writes CRLF (`\r\n`) and reads either; write CRLF
  for ANTz/GaiaViz compatibility.
- **Number formatting on save**: floats with 6 decimal places; ints bare;
  `trigger_*` written as int when integral (legacy byte-stability) and 6-dp
  float otherwise (fractional World Grid extents like −117.5 are preserved).
- The loader reads columns **by header name**, order-independent, via pandas.

## GaiaViz `np_` dialect (read-side interop)

A file whose *first* header column is `np_node_id` is detected as GaiaViz
dialect and these columns are remapped: `np_node_id`→`id`,
`np_geometry_id`→`geometry`, `np_topo_id`→`topo`, `np_texture_id`→`texture_id`.
All other GaiaViz column names already match. GlyphViz **writes** only the
canonical (ANTz-name) layout. Never author new data in `np_` dialect — that
prefix is for genuine GaiaViz files.

## Node types

| type | Meaning |
|---|---|
| 0 | **World** — one optional row holding scene-wide settings: background color in `color_r/g/b/a`, blend `render_mode`, fog, tag-label color and size (`tag_color_mode`, `tag_color_r/g/b`, `tag_font_size`), reference-grid color (`ref_grid_color_r/g/b`). Never drawn or picked; **must be excluded from bulk selection/edits**. Without one, background falls back to (20, 20, 31), tag text to pastel yellow at 11 pt, and the reference grid to (56, 56, 71). |
| 1 | **Camera** — stored view definitions (C key cycles). Never drawn or picked. |
| 5 | **Glyph** — the ordinary renderable node; use 5 for normal data (other unlisted values also draw as plain glyphs). |
| 6 | **World Grid** — a real, movable/scalable node rendering a flat lon/lat plate or (with Sphere/Sphere-Wire geometry) a globe. Children attach **explicitly** via `parent_id` = the grid's id and place by `translate_x` = longitude, `translate_y` = latitude, `translate_z` = elevation within the grid's extents window (`trigger_lo/hi_x/y`). No implicit/default grid exists. Grid scale re-spaces child positions, never child sizes. Full rules: `world-grid.md`. |
| 7 | **Link** — a graph edge from node `parent_id` (A-end) to node `child_id` (B-end). `geometry` chooses how the edge draws: 27 (Line) = classic thin line, and the default; 28 (Prism) = textured 4-sided tube, texture scrollable via `rotate_rate_z` for directed flow; 22 (Point) also draws as a plain line. **Any other geometry id renders that glyph stretched between the two ends** — see "Geometry on a Link" below. Links take `text`/`link` and `show_text` like any other node — an edge label draws at the middle of the edge (`tags-and-labels.md`). Full row shape, drawing modes, and edge recipes: `links-and-edges.md`. |

## Topology ids (`topo` — how children of this node are placed)

0 None (Cartesian) · 1 Cube (children on faces via `facet`/`subspace`) ·
2 Sphere (lon/lat/alt, KML-style) · 3 Torus (orbital angle/tube angle/elevation) ·
4 Cylinder · 5 Pin · 6 Rod · 7 Point · 8 Plane · 9 Zcube · 10 Zsphere ·
11 Ztorus · 12 Zcylinder · 13 Zrod · 14 Spiral · 15 Video ·
16 Plot (line plots/GPS/oscilloscope; GlyphViz extension) ·
17 Surface (deformable grid/FFT/LIDAR; GlyphViz extension).

Z-variants (9–13) zero the surface/radius offset so children sit through the
center/axis instead of on the rendered surface. Full placement math:
`topologies.md`.

## Geometry ids (`geometry` — this node's own shape)

| id | Shape | id | Shape |
|---|---|---|---|
| 0/1 | Cube wire/solid | 16/17 | Pin solid/wire (**note: solid=16 comes first**) |
| 2/3 | Sphere wire/solid | 18/19 | Cylinder wire/solid |
| 4/5 | Cone wire/solid | 20/21 | Grid wire/solid |
| 6/7 | Torus wire/solid | 22 | Point |
| 8/9 | Dodecahedron wire/solid | 23 | Mesh (imported; GlyphViz-only, needs `mesh_id`) |
| 10/11 | Octahedron wire/solid | 24/25/26 | Circle / Cross / Star flat markers (GlyphViz-only) |
| 12/13 | Tetrahedron wire/solid | 27/28 | Line / Textured Prism (Link nodes only) |
| 14/15 | Icosahedron wire/solid | 29/30 | Cube / Sphere **(Interior)** (GlyphViz-only) |
| | | 31/32 | Cylinder (Interior) capped / open (GlyphViz-only) |
| | | 33/34 | **Flat Ring** solid/wire (GlyphViz-only) |

**Interior geometries (29–32)** draw the shape's *inside* surface, so a
texture or video can be viewed from within — a 360° sphere, a cylindrical
panorama, a video room. They are built mirrored, so the image reads
**forwards** from inside rather than reversed the way an ordinary shape's
interior would; they draw **unlit**, so the image reads at full brightness
with no shading over it; they stay single-sided (culling on, alpha
unaffected); and from outside you see the far inner wall, like looking into a
bowl. Ids 31 and
32 are one cylinder with and without its end caps — capless is the one for a
panorama, or for a link you fly down. Scale as usual: an interior sphere at
`scale 57.3` (Global Scale 1.0) has a 57.3-unit radius.

**Flat Ring (33/34)** is a torus with a **rectangular** cross-section — a
machined instrument band rather than soft tubing. Reach for it when a ring has
to carry a texture that must stay legible (degree markings, a scale, a name
wrapped around a hoop): a torus curves the image away round its tube, a flat
ring holds it on a face. It adds **no new column** — both proportions come from
fields a torus already uses:

| Field | On a Flat Ring |
|---|---|
| `ratio` | the band's **radial width**, exactly its torus meaning (the tube spans radius `1 − 2 × ratio` to `1`). Default 0.14 |
| `scale_z` | the band's **height** — it stretches a rectangle now instead of an ellipse |

A torus's cross-section is already square, so `scale_z = scale_x` gives a square
section and **Torus ↔ Flat Ring is a pure change of look**: same silhouette,
same extents, and a `topo = 3` (Torus) parent places its children identically
whichever it wears. The two useful departures from square are a wide thin
washer (large `ratio`, small `scale_z` — a dial read face-on) and a tall thin
hoop (small `ratio`, large `scale_z` — a meridian band read on its outer wall).

The local half-height *is* `ratio`, so a thin band needs a large `scale_z` to be
tall: a hoop 0.5 units tall at `ratio = 0.02` wants `scale_z = 25`. Working from
an instrument maker's numbers, for radius `R`, radial width `w`, thickness `t`:
**`ratio = w / (2R)`** and **`scale_z = t × R / w`**. A `ratio` at or past 0.5
closes the hole and the ring becomes a solid wheel rather than inverting.

Two authoring rules go with it, both design constraints rather than settings:

1. **A ring that carries children must be scaled uniformly.** Children inherit
   per-axis scale, so a child of an `(S, S, Z)` ring comes out stretched. Split
   the job: thin *rails* at uniform scale carry the children; wide, thin,
   textured *bands* carry the markings and stay childless.
2. **A ring carrying readable text has to be a wide band**, on the order of
   10–20% of its own radius, because its texture canvas is `2πR / face width`
   — 31:1 at 20% of the radius, 63:1 at 10%, 157:1 for a thin 4% hoop. See
   `textures-and-media.md` — this is the trap, and it is not recoverable by
   repeating the content more times.

### Geometry on a Link (type 7)

Every id above is valid on a Link. 27, 28, and 22 draw the edge as a line or
tube (see the Node types table); **every other id renders that glyph stretched
between the link's two ends**:

- **Length** = the endpoint distance. The glyph's local Z extent maps onto the
  A→B segment, so it starts on A and ends on B exactly.
- **Thickness** = `ratio`, on **both** cross-axes — the same field the Line and
  Prism modes use for their width. Not `scale_x`/`scale_y`.
- **Orientation** comes entirely from the two endpoints; a link's own
  `translate`, `rotate`, and `scale` are ignored, as they always were.

So an edge can be a cylinder rod, a cone (apex at the B-end — an arrowhead for
directed graphs), a wire cage, or an imported mesh. Three quirks: on a **Torus**
link `ratio` also sets the torus's own minor-radius proportion (above 1.0 is
degenerate); the flat shapes (20/21, 24/25/26) have no Z extent to stretch so
they land as a plate at the edge's midpoint; and **Pin** (16/17) stands on its
apex, so a pin link puts its tip on A and its dome on B.

Authoring guidance: a solid glyph link costs what a glyph costs. On a graph
with thousands of edges, use 27 (Line) unless the edge itself carries meaning.
Recipes (arrowheads, weighted edges, bonds, tree limbs) and the full validation
rules: `links-and-edges.md`.

Geometry never gates `texture_id` in the format, but only the solid primitives,
the three flat markers (24/25/26 — textured since 2026-08-06), and the Link
Prism (28) actually *render* a texture; on wireframes, Point (22), Mesh (23),
and Line (27) it is read and silently ignored. Full table: `textures-and-media.md`.

Pin (16/17) is the one geometry that is **not centred on its own origin**: it
stands with its tip at the origin and its shaft along +Z, so a pin marks the
point it sits on rather than straddling it. (Rebuilt to ANTz's shape
2026-08-14; before that it hung below the origin, so pins in pre-2026-08-14
files sit about one glyph height lower than they do now.) Placement of a Pin
parent's own children follows from the same convention — see `topologies.md`.

Point (22) is the one geometry whose on-screen size does **not** come from
`scale_x/y/z`: it is a fixed-pixel sprite sized `max(2, ratio × 20)` px that
never shrinks with distance. Markers 24/25/26 are ordinary world-space plates
and do scale normally — reach for them when a point cloud needs depth cues.

## Tag companion file (`gv_tag.csv`)

Used only when the node CSV has **no inline `text`/`link` columns**. Naming: the
node file's stem with its trailing `node` swapped for `tag`
(`gv_node.csv` ↔ `gv_tag.csv`, `foo_gv_node20260625182432.csv` ↔
`foo_gv_tag20260625182432.csv`); auto-loaded on open.

Columns: `id, table_id, record_id, title`.
- `table_id` **must be 0** or the row is ignored.
- `record_id` matches the node CSV's `record_id` (fallback: node `id`).
- `title`: an HTML `<a href="url">label</a>` anchor (sets both link and text),
  a bare URL (`http(s)://`, `www.`, `ftp://`), or plain text.
- Written with CRLF; for generated data prefer the inline `text`/`link`
  columns unless ANTz/GaiaViz tag compatibility is needed.
- Display behavior, link/app-launch rules, and gotchas: `tags-and-labels.md`.
