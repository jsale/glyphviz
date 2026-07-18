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
| `scale_x/y/z` | float | Per-axis scale. **Renderer floors the rendered scale at 0.2 per axis** — author visible nodes with raw scale ≥ 0.2 and never encode size as huge-parent × tiny-child. |
| `color_r/g/b/a` | int | 0–255. Alpha blends per the World node's `render_mode`. |
| `geometry` | int | Shape id 0–28 (see Geometry ids). |
| `hide` | int | 1 = do not render this node. |
| `topo` | int | Topology id 0–17 controlling how **children** of this node are placed (see Topology ids). |

## Optional tracked columns (read into Node fields, with load defaults)

| Column | Default when column absent | Notes |
|---|---|---|
| `ratio` | 0.1 | Geometry/topology aspect parameter: a Torus parent's tube (minor) radius as a fraction of major radius — children of Torus/Ztorus parents sit on the tube defined by the **parent's** ratio; also drives Point-geometry marker size. |
| `subspace` / `facet` | 0 | Cube-topology face selector. `subspace` (GaiaViz spelling, 0-indexed) wins if present; else `facet` − 1 (legacy ANTz/GlyphViz spelling, 1-indexed: 1=+X, 2=−X, 3=+Y, 4=−Y, 5=+Z, 6=−Z), clipped at 0. `save_node_csv` always writes `facet`. |
| `texture_id` | 0 | 0 = untextured; otherwise a 1-based index into the alphanumerically sorted files of the scene's `media/` folder (images first, then videos) — see `textures-and-media.md`. |
| `mesh_id` | 0 | **GlyphViz-only.** Selects an imported mesh for `geometry` = 23 (Mesh). Written only when some node uses it. |
| `rotation_mode` | **1 (Heading/Tilt/Roll)** | **Asymmetric by design**: a missing column means the file predates the feature and loads as ANTz's Z-X-Z Heading/Tilt/Roll convention; a freshly constructed `Node()` in code defaults to 0 (Euler XYZ, each field rotates about its own axis). Written on save only when some node's value would be misread by the load fallback (i.e. any node with mode ≠ 1). **Generated files that hand-pose rotations should write `rotation_mode` = 0 explicitly.** |
| `color_index`, `palette_id` | 0, 0 | ANTz-style palette color selection. Inert on load/render — resolved into `color_r/g/b` only when the user cycles with =/− (color_index) or Alt+=/Alt+− (palette). 26 built-in palettes (0 = the 20-distinct-colors default). `palette_id` has no slot in the 94 columns; appended as an extension column only when nonzero. Full palette tables, gradient formulas, and authoring recipes: `color-palettes.md`. |
| `translate_rate_x/y/z`, `rotate_rate_x/y/z`, `scale_rate_x/y/z` | 0.0 | Per-cycle velocities added every animation tick (nominally 60/s, ANTz convention). Nonzero `freeze` (extras) suspends them. `rotate_rate_z` also scrolls a Link prism's texture (flow animation). |
| `text`, `link` | "" | **GlyphViz-only inline label columns.** `text` = label drawn in the viewport; `link` = URL/file opened by the U key. If *neither* column is present, the loader falls back to the companion tag file (see Tag companion file). Written on save only when some node has a value. |
| `render_mode` | 0 (Normal) | **World-node-only** scene blend mode: 0 Normal, 1 Additive, 2 Subtractive, 3 Dark/Multiply, 4 Off, 5 Screen, 6 Premultiplied. Extension column, written only when ≠ 0. |
| `fog_enabled`, `fog_start`, `fog_end` | 0, 0.0, 0.0 | **World-node-only** fog (fades to the World bg color). Extension columns, written only when nonzero. |

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
| 10 | `ch_input_id` | int | ⚙ | **Channels**: binds this node to a channel id in the ch-map/ch-tracks pair (GaiaViz alias `np_ch_in_id` also recognized) — see `channels-animation.md`. |
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
| 0 | **World** — one optional row holding scene-wide settings: background color in `color_r/g/b/a`, blend `render_mode`, fog. Never drawn or picked; **must be excluded from bulk selection/edits**. Without one, background falls back to (20, 20, 31). |
| 1 | **Camera** — stored view definitions (C key cycles). Never drawn or picked. |
| 5 | **Glyph** — the ordinary renderable node; use 5 for normal data (other unlisted values also draw as plain glyphs). |
| 6 | **World Grid** — a real, movable/scalable node rendering a flat lon/lat plate or (with Sphere/Sphere-Wire geometry) a globe. Children attach **explicitly** via `parent_id` = the grid's id and place by `translate_x` = longitude, `translate_y` = latitude, `translate_z` = elevation within the grid's extents window (`trigger_lo/hi_x/y`). No implicit/default grid exists. Grid scale re-spaces child positions, never child sizes. |
| 7 | **Link** — a graph edge from node `parent_id` (A-end) to node `child_id` (B-end). Geometry 27 (Line) = classic thin line; 28 (Prism) = textured 4-sided tube, texture scrollable via `rotate_rate_z` for directed flow. |

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
| 14/15 | Icosahedron wire/solid | | |

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
