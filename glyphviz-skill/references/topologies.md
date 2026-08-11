# Topologies — child placement reference

Verified against `glyphviz_core/topology.py`'s offset functions and
`glyphviz_gl/viewport.py`'s overlay rendering (2026-07-14). Every worked
example below is numerically checked against the real engine
(`compute_world_positions`) — the world values are engine output, not hand
math.

## The placement model

A node's `topo` field controls how its **children** are placed. For each
child:

1. The child's `translate_x/y/z` are interpreted in the **parent's topology
   coordinate system** (angles, lon/lat, grid coordinates — per the tables
   below) and converted to a Cartesian offset in the parent's own unscaled
   local frame.
2. That offset is transformed by the parent's cumulative world basis — every
   ancestor's rotation and per-axis scale — and added to the parent's world
   position. So rotating or scaling a parent carries its whole subtree
   correctly, however deep.
3. **Root nodes** (`parent_id` = 0) skip all of this: their `translate_x/y/z`
   are plain world Cartesian coordinates.

**B = the app's Global Scale** (default **1.0**) appears in the formulas as
the parent glyph's unscaled base size. Surface-riding topologies place
children at radius B so they sit exactly on the parent's rendered surface;
the parent's own `scale_x/y/z` then stretches surface and child positions
together. All examples below assume an unrotated, scale-1 parent at the
origin and B = 1.

Nothing auto-distributes: siblings land wherever their coordinates say. The
generator computes the angles/positions (e.g. `i * 360/n` around a torus).

## Outward orientation (applied before the child's own rotate_x/y/z)

Children of circular/surface topologies get a base rotation so a child posed
to face outward *keeps* facing outward as its placement angle changes:

| Parent topo | Base rotation | Effect |
|---|---|---|
| Sphere, Point, Torus, Ztorus | Rz(tx)·Ry(90−ty) | child +Z aligns with the outward surface normal at (lon=tx, lat=ty) |
| Cylinder, Zcylinder, Spiral, Zrod | Rz(tx) | child carried around the axis by its angle |
| Rod | Rz(ty) | same, but Rod's angle lives in translate_y |
| Cube, Zcube | fixed per face | child +Z aligns with the face normal (`facet`/`subspace`) |
| all others | identity | no circular placement to track |

The child's own `rotate_x/y/z` (per its `rotation_mode`) applies on top of
this scaffold.

## Cartesian family — None (0), Plane (8), Video (15), Plot (16), Surface (17)

`offset = (tx, ty, tz)` — plain local-frame Cartesian. Identity orientation.

- **None (0)** — the default; children translate rigidly with the parent.
- **Plane (8)** — same math; the conventional choice when the parent is a
  flat plate (`geometry` 20/21) framing a 2D layout. `translate_z` =
  elevation above the plate.
- **Video (15)** — same math; marks the parent as a flat video screen.
- **Plot (16)** — same math **plus a polyline overlay**: GlyphViz draws a
  GL_LINE_STRIP through the children **in file (row) order** — order your
  rows along the intended path. Needs ≥ 2 visible children. Line width =
  parent's `ratio` × 20 px (min 1; ratio 0.15 → 3 px). Each vertex takes its
  child's color, so color-ramping children paints a gradient along the line.
  Use for line plots, GPS tracks, oscilloscope traces.
- **Surface (17)** — same math **plus a lit quad-mesh overlay** built from
  the children as a lattice: children are bucketed by their **exact**
  `(translate_x, translate_y)` values (rounded to 6 decimal places), the
  unique x's and y's are sorted, and a quad is drawn for every cell whose
  four corners all exist. `translate_z` is the height at that lattice point.
  **Generate lattice coordinates from identical values, never accumulated
  floats** — a corner that differs in the 7th decimal is a hole in the mesh.
  Needs ≥ 4 children and ≥ 2 distinct values on each axis; per-vertex child
  colors shade the surface. Use for terrain, FFT waterfalls, heatmap relief.

Example (all five): `child (1.5, -2, 0.5) → world (1.5, -2, 0.5)`.

## Sphere (2) — KML longitude/latitude/altitude

| Field | Meaning |
|---|---|
| `translate_x` | longitude, degrees (0 → parent's local +X, 90 → +Y) |
| `translate_y` | latitude, degrees (90 → +Z pole) |
| `translate_z` | altitude above the sphere surface (0 = on the surface) |

`r = B + tz`; `offset = (r·cos lat·cos lon, r·cos lat·sin lon, r·sin lat)`.

Examples: `child (90, 0, 0) → world (0, 1, 0)` ·
`child (45, 45, 0) → world (0.5, 0.5, 0.707107)` ·
`child (0, 90, 0.5) → world (0, 0, 1.5)`.

## Torus (3) — orbital angle / tube angle / tube offset

| Field | Meaning |
|---|---|
| `translate_x` | orbital angle around the main ring, degrees |
| `translate_y` | tube angle around the ring's cross-section, degrees (0 = outer equator, 90 = top of the tube) |
| `translate_z` | offset outward from the tube surface (0 = on the surface) |

Uses the **parent's** `ratio` (default 0.1): `major = B·(1−ratio)`,
`minor = B·ratio`, `tube_r = minor + tz`;
`offset = ((major + tube_r·cos ty)·cos tx, (major + tube_r·cos ty)·sin tx,
tube_r·sin ty)`.

The classic "ring of categories" topology: place n children at
`tx = i·360/n, ty = 0, tz = 0`.

Examples (ratio 0.1): `child (90, 0, 0) → world (0, 1, 0)` ·
`child (0, 90, 0) → world (0.9, 0, 0.1)`.

## Cylinder (4) — angle / height / radial

| Field | Meaning |
|---|---|
| `translate_x` | angle around the axis (local Z), degrees |
| `translate_y` | height along the axis — a literal offset from the parent's center |
| `translate_z` | radial offset from the surface (0 = on the surface, radius B) |

`offset = ((B+tz)·cos tx, (B+tz)·sin tx, ty)`.

Example: `child (90, 0.5, 0) → world (0, 1, 0.5)`.

## Pin (5) — vertical stack

| Field | Meaning |
|---|---|
| `translate_x` | height above the pin top: child sits at local Z = B + tx |
| `translate_y` | sideways offset, local X |
| `translate_z` | sideways offset, local Y |

`offset = (ty, tz, B + tx)`. Identity orientation. Stack sequential items by
increasing `translate_x`.

Example: `child (0.5, 0, 0) → world (0, 0, 1.5)`.

## Rod (6) — normalized length / angle / radial

| Field | Meaning |
|---|---|
| `translate_x` | position along the rod, **normalized: 0–180 spans the rod's full rendered length** (10·B at scale 1) |
| `translate_y` | angle around the rod's axis, degrees |
| `translate_z` | radial distance from the axis (0 = **on the axis**, unlike Cylinder) |

`offset = (tz·cos ty, tz·sin ty, (tx/180)·10·B)`.

Examples: `child (90, 0, 0) → world (0, 0, 5)` (halfway up) ·
`child (0, 45, 0.2) → world (0.141421, 0.141421, 0)`.

## Point (7) — pure direction

KML lon/lat like Sphere but with **no base radius**: `translate_z` is the
full distance from the parent's center (`tz = 0` → at the center).
`offset = kml(tx, ty, tz, radius 0)`. Same outward orientation as Sphere —
useful for "spokes" radiating from a hub.

Example: `child (0, 0, 2) → world (2, 0, 0)`.

## Cube (1) — six faces

Children attach to one of six faces chosen by the node CSV's `facet` column
(1-indexed; or GaiaViz `subspace`, 0-indexed — see the format reference):

| facet | Face | Child +Z points | tx moves along | ty moves along |
|---|---|---|---|---|
| 1 | +X | +X | +Y | +Z |
| 2 | −X | −X | −Y | +Z |
| 3 | +Y | +Y | −X | +Z |
| 4 | −Y | −Y | +X | +Z |
| 5 | +Z (top) | +Z | +X | +Y |
| 6 | −Z (bottom) | −Z | +X | −Y |

`offset = (B + tz)·normal + tx·u + ty·v` — `translate_z` lifts off the face,
`translate_x/y` slide within it (u/v per the table, as seen from outside).

Example (facet 1): `child (0.2, 0.3, 0) → world (1, 0.2, 0.3)`.

## Spiral (14) — helix

| Field | Meaning |
|---|---|
| `translate_x` | helix angle, degrees — **keeps counting past 360**: each full turn rises B |
| `translate_y` | extra height added to the helical height |
| `translate_z` | radial offset from the helix radius B |

`offset = ((B+tz)·cos tx, (B+tz)·sin tx, (tx/360)·B + ty)`.

Rank/time-ordered data reads naturally as one continuous winding: item i at
`tx = i·step`, nothing else needed.

Example: `child (720, 0, 0) → world (1, 0, 2)` (two turns up).

## Z-variants (9–13) — same shapes, collapsed to center/axis

Each drops the base-radius term so `translate_z` measures from the parent's
**center or axis** instead of its surface. Same coordinate meanings and
outward orientation as the base topology otherwise.

| Topo | Like | Difference | Example |
|---|---|---|---|
| Zcube (9) | Cube | distance along the face normal is `tz` alone (tz=0 → parent center) | facet 5: `child (0.2, 0.3, 0.5) → world (0.2, 0.3, 0.5)` |
| Zsphere (10) | Sphere | radius is `tz` alone — identical math to Point | `child (90, 0, 1.5) → world (0, 1.5, 0)` |
| Ztorus (11) | Torus | no tube: `tz` offsets from the major ring itself | ratio 0.1: `child (0, 90, 0.2) → world (0.9, 0, 0.2)` |
| Zcylinder (12) | Cylinder | radius is `tz` alone (tz=0 → on the axis) | `child (180, 1, 0.5) → world (-0.5, 0, 1)` |
| Zrod (13) | Zcylinder | identical placement math (deliberately); differs only in rendering rules | same as Zcylinder |

Note Zrod places like **Zcylinder** (`translate_y` = literal height), not
like Rod (no 0–180 normalization).

## World Grid (parent type = 6 — a node type, not a topo id)

Children of a World Grid node place by `translate_x` = longitude,
`translate_y` = latitude within the grid's extents window (`translate_z` =
elevation), regardless of the grid row's own `topo` value — flat plate or
globe depending on the grid's geometry. Grid scale re-spaces child positions
but never child sizes. Full rules and engine-verified examples:
`world-grid.md`; field layout: `node-csv-format.md`.

## Generation tips

- Angles are degrees everywhere; they may exceed 360 (Spiral relies on it).
- Torus placement reads the **parent's** `ratio` — set it on the parent, not
  the children.
- Children of one parent may mix `translate_z` values to hover above/below
  the surface (e.g. bar heights above a sphere: vary `tz` on a Sphere
  parent).
- A parent's topology affects only its **direct children**; grandchildren
  use *their* parent's topo — mix topologies per level (torus of pins,
  sphere of plots, …).
- Deep hierarchies inherit cumulative scale: a 0.5-scale parent halves its
  children's spacing *and* rendered size (except World Grid parents). Keep
  every visible node's raw scale ≥ 0.2 so the viewer's optional
  minimum-glyph-size clamp (off by default) can't alter your proportions,
  and so glyphs stay easy to click.
