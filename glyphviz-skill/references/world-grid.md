# World Grid — geo-registered scenes (node type = 6)

Verified against `glyphviz_core/node.py` (grid accessors), `topology.py`
(the vectorized engine's type-6 handling), `scene.py` (`_grid_draw_scale`),
and `glyphviz_gl/main_window.py`/`viewport.py` (2026-07-18). Every worked
example's world values are output from the real transform engine (the same
path the app's Scene uses), not hand math.

## What a World Grid is

A **real node** with `type = 6` — movable, rotatable, scalable, texturable —
that renders as a flat longitude/latitude plate or a globe, and places its
children by geographic coordinates. It is a node *type*, not a topology:

- Children attach **explicitly** via `parent_id = the grid's id`. There is
  no default or implicit grid, and `parent_id = 0` means "ordinary root
  node," never "attached to a main grid" (GaiaViz's parent_id=0 main-grid
  convention is deliberately not used). A grid row's own `topo` field is
  irrelevant to how its children place.
- **Multiple grids per scene are fully supported** — side-by-side regional
  maps, stacked layers, a flat map and a globe in one scene. The G key
  cycles between them. A grid is also an ordinary hierarchy member: it can
  itself be the child of another node.

## CSV recipe

The grid row:

| Field | Value |
|---|---|
| `type` | 6 |
| `geometry` | **20/21 (Grid wire/solid) → flat plate; 2/3 (Sphere wire/solid) → globe.** Any other geometry also renders as the flat plate. Solid forms take a texture; wire forms draw only the lattice. |
| `translate_x/y/z` | the grid's own position (world Cartesian for a root grid) |
| `rotate_*`, `scale_*` | work normally on the grid itself; see the scale rule below |
| `trigger_lo_x` / `trigger_hi_x` | extents window: longitude min / max |
| `trigger_lo_y` / `trigger_hi_y` | extents window: latitude min / max |
| `segments_x/y` | rendered cell counts (1 = plain outline; on a globe, the graticule). The app's Add button uses 36×18 = 10° cells |
| `texture_id` | optional equirectangular image, mapped across the window (flat) or the sphere (globe) — a plate carrée world map lines up with child placement automatically |

A **degenerate extents axis** (`hi ≤ lo` — e.g. the all-zero defaults of
files that predate the feature) falls back to the whole-earth window
(−180..180, −90..90) for that axis. Fractional extents round-trip exactly
(the trigger fields are written int-or-float).

Child rows: `parent_id` = the grid's `id`; `translate_x` = longitude,
`translate_y` = latitude, `translate_z` = elevation; `branch_level` = the
grid's + 1. A child's own `topo` still arranges *its* children normally —
glyph hierarchies sit on the map intact.

## Placement semantics (engine-verified)

**Flat plate**: `offset = (lon − center_lon, lat − center_lat, elevation)`
in the grid's local frame — plain Cartesian recentered on the extents
window's midpoint — then carried through the grid's rotation and per-axis
scale to the grid's position. Children of a flat grid get no outward
rotation scaffold.

- The default whole-earth window centers at (0, 0), so a grid at the origin
  with scale 1 is an exact **1:1 frame**:
  `child (180, 90, 0) → world (180, 90, 0)`.
- Moving/scaling the grid carries the layout: grid at (500, 0, 100) with
  scale (2, 2, 1): `child (10, 20, 5) → world (520, 40, 105)`.
- A **region window** recenters on its midpoint — raw lon/lat data lands on
  it with no coordinate transforms. Window −125..−66, 24..49 (contiguous
  US), grid at origin, scale 1 (center is (−95.5, 36.5)):
  `child (-95.5, 36.5, 0) → world (0, 0, 0)` ·
  `child (-66, 49, 0) → world (29.5, 12.5, 0)`.
- The rendered rectangle spans exactly the extents window × the grid's
  **raw** scale (no Global Scale factor, no 0.2 floor — unique to grids),
  so the plate always sits under its children: the default window draws
  360×180 world units at scale 1.

**Globe** (geometry Sphere/Sphere Wire): the same children place by KML
lon/lat on a sphere of radius **180/π (≈ 57.2958) × scale** — the flat 1:1
map rolled up, so the equator is exactly 360 world units and toggling
flat↔globe keeps the layout the same overall size. `translate_z` is radial
elevation; children get the same outward-facing orientation as
`TOPO_SPHERE` children. **Extents recentering does not apply on a globe** —
lon/lat are absolute positions on the sphere (the panel disables the window
fields); `segments_x/y` set the graticule.

Globe at origin, scale 1: `child (0, 0, 0) → world (57.2958, 0, 0)` ·
`child (90, 0, 0) → world (0, 57.2958, 0)` ·
`child (0, 90, 10) → world (0, 0, 67.2958)`.

## The scale rule (the one everyone gets wrong)

**A grid's scale re-spaces its children's POSITIONS per axis but never
their rendered size or their own subtrees' internal spacing** (the
ANTz-documented Grid rule; children compose onto the grid's rotation-only
basis). `scale_x = 2` doubles the longitude spread; every glyph stays the
same size, and each glyph's own children keep their spacing — engine
check: on a scale-2 grid, a child's own child at `(0, 0, 7)` sits 7 units
above it, not 14. Use grid scale freely for zoom and aspect ratio
(`scale_y` ≈ cos(mean latitude) × `scale_x` approximates a locally
conformal map). This exemption is the grid's own scale only — a plain
`topo` = Plane parent still scales its children fully.

`scale_z` re-spaces elevations the same way — a cheap vertical
exaggeration control for elevation-as-data scenes.

## Selection and picking (app behavior)

- Grids are **never click- or rubber-band-pickable**, so they can't swallow
  clicks meant for glyphs sitting on them. The **G key selects and cycles
  through grids**; the node table and the World Grid panel also select.
  Grids are excluded from Select All.
- **Solid** grid surfaces (plate or globe) still *occlude* picking — a
  click can't select a glyph hidden behind the surface. Wire forms don't
  occlude.
- With exactly one grid selected, the **World Grid panel** edits Shape
  (flat↔globe, preserving wire/solid — it's just a geometry change, fully
  CSV-native), the lon/lat window, and cell counts.

## Scene recipes

- **Whole-earth 1:1**: default window (write zeros or −180..180/−90..90),
  solid geometry + an equirect world-map `texture_id`, raw lon/lat data as
  children. Works identically as a globe — same rows, geometry 3.
- **Regional map**: set the window to the region; feed raw coordinates.
  Grid scale zooms; segments to taste. You don't have to ship a map image:
  the app's World Grid panel has a **Fetch Basemap…** button that measures
  the children's lon/lat bounding box, downloads free map imagery
  (OpenStreetMap / satellite / terrain, no API key) for exactly that
  window, reprojects it to plate carrée, saves it into `media/`, and sets
  the grid's extents + `texture_id` to match. A generator only needs to
  put the data on the grid.
- **Map + globe twins**: two grids, two copies of the child rows (a node
  has one parent) — or one grid the user toggles live via the panel.
- **Stacked layers**: several region grids at different `translate_z` (or
  positions), e.g. one per year — a small-multiples map stack.
- **GPS playback**: children on a grid + Channels tracks driving
  `translate_x/y` (lon/lat over time) — see `channels-animation.md`.
- **Elevation as data**: `translate_z` in real units, grid `scale_z` as
  the exaggeration knob.

## Gotchas

- Attach children explicitly — a type-6 row in a legacy file renders, but
  nothing attaches to it unless `parent_id` says so.
- Keep child scales ≥ 0.2 as usual (the no-floor exemption is for the
  grid's own rendered plate, not for glyphs).
- Rotating a grid rotates the whole layout (children ride along); rotating
  it 90° about X turns a floor map into a wall map.
- Don't use `gluSphere`-style UV assumptions for globe textures — GlyphViz
  maps the globe with exact equirect UVs matched to KML placement; just
  supply a standard plate carrée image.
