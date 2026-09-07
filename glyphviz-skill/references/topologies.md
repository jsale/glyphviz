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

### What B moves, and what it doesn't

B is a **viewer setting the CSV does not record** — Properties → Global
Scale, default 1.0. Author against 1.0. It multiplies every glyph's rendered
size (`scale_x/y/z × B`), and it moves exactly one class of position:

| Node | B = 1 | B = 3 | Moves? |
|---|---|---|---|
| Root, any topology | its literal `translate` | same | no |
| Sphere child, `translate_z = 0` (on the surface) | `(1, 0, 0)` | `(3, 0, 0)` | **yes** |
| Sphere child, `translate_z = 5` (off the surface) | `(6, 0, 0)` | `(8, 0, 0)` | **yes**, but not proportionally |
| Torus child on the ring | `(1, 0, 0)` | `(3, 0, 0)` | **yes** |
| Plane child `(4, 3, 0)` — Cartesian | `(4, 3, 0)` | same | no |
| None child `(4, 3, 2)` — free placement | `(4, 3, 2)` | same | no |
| World Grid child, lon 90 / lat 45 / elev 3 | `(90, 45, 3)` | same | no |

(Engine-measured through `compute_world_transforms`, unrotated scale-1
parents at the origin.)

The row that causes trouble is the third one. A surface-riding child sits at
`B × parent scale + translate_z`, so a distance expressed as **parent scale**
tracks B while the same distance expressed as **the child's own
`translate_z`** does not. Put a given distance in one of the two places, not
both, or the scene only lines up at the Global Scale you happened to author
it at. Symptom and fix: `troubleshooting.md` → "the scene's proportions
change with the Global Scale slider".

If you verify a scene through `glyphviz_core`, note that `Scene()`'s own
`base_scale` parameter still defaults to **3.0** while the app opens at
**1.0** — pass it explicitly, or you are checking a scene the viewer does not
draw.

Nothing auto-distributes: siblings land wherever their coordinates say. The
generator computes the angles/positions (e.g. `i * 360/n` around a torus).

## Topology Scale — angular axes vs. distance axes

Every topology reads some of a child's translate axes as **angles** and others
as **distances**. Sphere reads `translate_x` as longitude, so 0…360 wraps the
parent once whatever its size; Cube reads `translate_x` as a position across a
facet, so 0…360 is 360 **world units** — hundreds of times a typical glyph.
Values authored for one reading are wildly wrong under the other, which is why
switching a parent's topology from Sphere to Cube used to fling its children
out of sight.

The parent's **`topo_scale`** (default **1.0**) multiplies exactly the
distance-valued axes, and nothing else:

| Parent topo | scaled by `topo_scale` | never scaled |
|---|---|---|
| None, Plane, Video, Plot, Surface, Point Cloud | tx, ty, tz | — |
| Cube, Zcube | tx, ty (face u/v), tz (height off the face) | the base-radius face offset |
| Sphere, Point, Zsphere | tz (altitude) | tx, ty (lon/lat) |
| Torus, Ztorus | tz (tube offset) | tx, ty (orbital/tube angles) |
| Cylinder, Zcylinder | ty (height), tz (radial) | tx (angle) |
| Rod | tz (radial) | ty (angle), tx (already a fraction of rod length) |
| Zrod | ty (height), tz (radial) | tx (angle) |
| Pin | tx (height), ty, tz | the base-radius offset |
| Spiral | ty (rise offset), tz (radial) | tx (helix angle and its rise) |
| **World Grid children** | nothing — exempt | all (the grid's footprint is drawn from the same window its children's coordinates are read in) |
| **Root nodes** | nothing — exempt | all (`translate` IS the world position) |

Because angular axes are never touched, no value of `topo_scale` can distort a
circular layout: turn it down and a sphere's children stay exactly on the
sphere.

**Two landmarks:**

- **`1.0`** — one translate unit is one world unit. GlyphViz's behavior since
  its first commit, and what a file with no `topo_scale` column loads as, so
  every pre-existing scene renders unchanged.
- **`1/180` ≈ `0.005556`** — the **ANTz convention**: a linear axis spans the
  parent's own extent, so a facet is 360 units across and translate 180 lands
  on its edge, exactly as 180° of longitude reaches the far side of a sphere.
  This is the setting at which a layout authored in degrees survives a switch
  between an angular and a linear topology intact.

In the app it is the **Topo Scale** row of the Properties panel, directly under
Topology, with `1:1` and `ANTz` preset buttons; edits apply to the whole
selection, so *Edit → Select By → Topology → Cube* then one slider drag retunes
every cube parent in a scene. It is also bindable as a Channels attribute, so a
scene animating `topo` can animate `topo_scale` alongside it. The Glyph
Composer carries the same row per level, with an **Auto** checkbox that fits
the value to the child layout the level asks for.

Worked example — 12 children at `translate_x = 0, 30, … 330`, `translate_y = 45`,
`translate_z = 0` under a scale-9 parent at the default `ratio` (engine output:
distance from the parent to its farthest child):

| Parent topo | at `topo_scale` 1.0 | at 1/180 |
|---|---|---|
| Sphere | 9.0 | 9.0 |
| Torus | 8.8 | 8.8 |
| Cylinder | 405.1 | 9.3 |
| Spiral | 413.3 | 13.8 |
| Cube | **2997.5** | 18.9 |

Read the top two rows as the control: Sphere and Torus take **both** of those
translate values as angles, so their children stay pinned to the parent's own
surface and `topo_scale` moves nothing at all. (Torus lands at 8.8 rather than
9.0 because a tube angle of 45° carries the child slightly inside the ring's
major radius — geometry, not scaling.) The bottom three read `translate_y` as a
height or an offset, and at 1.0 that single value throws children hundreds of
units out; Cube reads `translate_x` that way too, which is why it goes furthest.

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

**Note the two traps in that table.** `Zsphere` is *not* in row one — it is the
one Z-variant that drops the outward aim (Ztorus keeps it), so a child of a
Zsphere parent is placed on a sphere but left unrotated. And the axis family
(Cylinder, Zcylinder, Spiral, Zrod, Rod) only *spins* the child about the
parent's axis: its local **+X** ends up radial while **+Z** stays parallel to
the axis. Measured, unrotated child, engine output:

| Parent topo | child's local +X | child's local +Z |
|---|---|---|
| Sphere / Point / Torus / Ztorus | tangent | **outward (radial)** |
| Cube (any `facet`) | in-face | **outward (face normal)** |
| Cylinder / Zcylinder / Spiral / Zrod / Rod | **radial (horizontal)** — swept by `translate_x`, but by `translate_y` on Rod | axial (parent's +Z) |
| Zsphere, Pin, None, Plane, Video, Plot, Surface, Point Cloud | +X | +Z (unrotated) |

## Pointing a glyph: use placement, not rotation

**+Z is the pointing axis of every directional geometry**, which is what makes
the table above actionable:

| Geometry | What +Z means for it |
|---|---|
| Cylinder 18/19, Cone 4/5 | the long axis (a rod/spike lying along ±Z, length 2 at scale 1; the cone's apex is at +Z) |
| Pin 16/17 | the shaft — tip at the origin, shaft rising along +Z |
| Grid 20/21, Circle 24, Cross 25, Star 26 | the facing normal (the plate lies in the XY plane) |
| Torus 6/7 | the ring's axis (the ring itself lies in the XY plane) |
| Cube, Sphere, and the polyhedra | nothing — isotropic, no aim to get wrong |

So **a directional glyph placed by an aiming topology needs no rotation at
all**: put `rotate_x/y/z = 0` and let placement do the work. The angle you want
is a `translate_x`, not a `rotate_z`.

This is the single most common authoring mistake in GlyphViz, and it fails
*silently*: hand-posed rotations do not replace the base rotation, they compose
on top of it, so the child ends up placed correctly and aimed wrong. The
symptom is an intended starburst that renders as a flat stacked fan — positions
right, bodies pointing the wrong way. See `troubleshooting.md` entry 15.

### Recipe: radial spokes (clock face, starburst, wind rose, rays)

n rods radiating from a hub, in the horizontal plane:

```text
hub    topo = 2 (Sphere), scale 1                 # or topo = 7 (Point)
rod i  parent_id = hub
       translate_x = i * 360/n     # the bearing -- THIS is the "rotation"
       translate_y = 0             # latitude 0 keeps every rod in the XY plane
       translate_z = <reach>       # Sphere: height above the surface
                                   # Point:  full distance from the center
       rotate_x/y/z = 0            # <-- the topology aims it; do not touch
       geometry = 19 (Cylinder)
       scale = (thickness, thickness, half_length)
```

Under a **Sphere** hub the rod's center lands at radius `B + translate_z`
(B = Global Scale, default 1), so `translate_z = half_length` puts the rod's
inner end exactly on the hub's surface. Under a **Point** hub there is no base
radius: `translate_z` *is* the center distance.

Verified through the real engine (Sphere hub, `scale_z` 2, `translate_z` 2,
twelve rods): every rod center at z = 0 and radius 3.0, bearings exactly 30°
apart, each rod's inner end at radius 1.000 (flush with the hub) and its axis
matching its own outward radial to 1.7e-16.

**Which way is clockwise.** Longitude runs **counter-clockwise seen from +Z**
(0 → +X, 90 → +Y), so a clock face — clockwise — needs *decreasing* longitude:

```text
translate_x = (lon12 - 30 * hour) mod 360
```

where `lon12` is the longitude you want 12 o'clock to face. Pick it from how
the scene will be viewed, because "up" is a camera property, not a world one.
For GlyphViz's overhead **+Z View** (azimuth 0, elevation 89) screen-up is
**−X** and screen-right is **+Y**, so `lon12 = 180` puts 12 at the top, 3 at
the right, 6 at the bottom, 9 at the left — measured off a real render, not
assumed.

## Cartesian family — None (0), Plane (8), Video (15), Plot (16), Surface (17), Point Cloud (18)

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
- **Point Cloud (18)** — same math, but the children **replace** their glyphs
  with one batched `GL_POINTS` array. Plot and Surface *add* an overlay on top
  of the glyphs; a Point Cloud parent's children draw no glyphs at all. Use
  for unstructured scan data — LIDAR, photogrammetry, particle sets. See the
  dedicated section below.

Example (all six): `child (1.5, -2, 0.5) → world (1.5, -2, 0.5)`.

## Point Cloud (18) — authoring a cloud

The topology to reach for when you have tens of thousands of positions and
no structure to impose on them. One `glDrawArrays` for the whole cloud:
measured, 100k colored points cost 0.10 ms/frame and 1M cost 0.63 ms.

| Field | Meaning |
|---|---|
| parent `topo` | `18` |
| parent `ratio` | rendered point size in pixels = `ratio × 20`, clamped to 1–64. Default `0.1` → 2 px |
| child `translate_x/y/z` | the point's position relative to the parent — plain Cartesian |
| child `color_r/g/b/a` | that point's colour; `color_a` blends |
| child `geometry`, `scale_*`, `rotate_*` | **ignored** — a point is a vertex, not a glyph |

Rules that follow from "one batch, still real nodes":

- **Every point remains a node.** It is individually clickable, selectable,
  taggable, Channels-bindable, and it saves and merges like anything else.
- **Point size is per-cloud, not per-point.** Fixed-function OpenGL has no
  per-vertex point size. Vary colour, not size, to encode a second variable —
  or split the scan across several cloud parents at different `ratio`s.
- **Order does not matter.** Unlike Plot (which connects children in row
  order) and Surface (which needs an exact lattice), a cloud reads its
  children as an unordered set. Nothing to sort, no holes to avoid.
- **`topo_scale` scales all three axes** — none is angular. This is the one
  field that rescales a whole imported scan.
- **Labels**: in the all-tags mode a cloud's points are deliberately not
  labelled. A point labels when selected, or when it sets `show_text = 1`.
  Pin a handful of landmarks; do not label every point.
- **The `\` draw limit treats a cloud as one unit** and never decimates it.

**Size budget.** The renderer is not the constraint; the node model is, and
mostly its size on disk — about **90 bytes per point** in the minimal dialect
GlyphViz saves. Measured: 100,000 points is a 9.1 MB scene that saves in 1.0 s
and reopens in 1.4 s; 442,767 points is 40.7 MB, 4.2 s and 6.3 s (and renders
at ~400 fps). (Before the 2026-09-07 compact-save change a row was the full
94-column layout at ~550 bytes, which made that same scan a 243 MB file — if
you meet one of those, re-saving it shrinks it.) Keep a cloud at or under
**100,000 points** unless the scene really needs more. Decimate to fit — a
100k-point sample of a 5M scan reads the same at any camera distance a person
actually uses.

**Back-compat.** An unrecognised `topo` falls back to plain Cartesian
placement, which is exactly what topology 18 does — so a cloud file opened by
an older GlyphViz build places every point correctly and simply draws them as
individual glyphs. No new column: the cloud travels in the node CSV.

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
| `translate_x` | height along the pin: child sits at local Z = B + tx |
| `translate_y` | sideways offset, local X |
| `translate_z` | sideways offset, local Y |

`offset = (ty, tz, B + tx)`. Identity orientation. Stack sequential items by
increasing `translate_x`.

The Pin *glyph* is the one shape not centred on its own origin: it stands with
its tip at local Z = 0 and its head centred at Z = B (the shaft is 10× as long
as it is wide, and the head adds a further 10% above that). So `tx = 0` places
a child at the centre of the head, and `tx = -B` places it at the tip — the
range `-B ≤ tx ≤ 0` walks the child down the shaft. Positive `tx` rises off the
end of the pin, which is fine when the pin is a stalk for a stack rather than a
marker.

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

### Direction-relative branching — trees, ferns, dendrites

Point is also the topology for **branching structures**, because of one
property: a child is aimed **down its own offset direction** (the outward
orientation), so its own children are then placed relative to *its* heading.
That makes the recursion turtle-style — each branch continues the direction its
parent was heading, deviated by a fixed angle — which is the mechanism that
makes an output read as a tree rather than as a starburst.

The convention that falls out of it:

| Field on the child | Meaning in a tree |
|---|---|
| `translate_y` = **90 − A** | the branch turns **A degrees** off the parent's heading |
| `translate_x` | azimuth around the parent's heading — the **fork twist**. Siblings at `t`, `t + 180` fork flat; add a per-level offset to spiral the forks |
| `translate_z` | the **branch length** (the reach from parent joint to child joint) |

`translate_y = 90` therefore means "straight on", and the trunk of a tree is
just a child at `(0, 90, trunk_length)` under the root.

Engine-verified (branch angle A = 35°, fork twist 60°, lengths 4 / 3 / 2, all
joints at scale 1):

| Node | Authored `(tx, ty, tz)` | World position | Angle off parent's heading |
|---|---|---|---|
| trunk | `(0, 90, 4)` | `(0, 0, 4)` | 0.0000° |
| fork A | `(60, 55, 3)` | `(0.8604, 1.4902, 6.4575)` | 35.0000° |
| fork B | `(240, 55, 3)` | `(−0.8604, −1.4902, 6.4575)` | 35.0000° |
| next gen | `(60, 55, 2)` | `(0.7048, 3.2076, 7.4705)` | 35.0000° |

Each child's own heading points exactly down its own branch (measured
deviation: 0), which is what lets the same three numbers be reused at every
depth.

Two rules that bite:

- **A joint's scale multiplies its children's reach**, because a node's
  rendered size and the frame its children are placed in are the same quantity
  in GlyphViz. Measured on the case above: a joint at scale 0.5 pulls its
  child's reach from 2.0 to 1.0, and scale 2.0 pushes it to 4.0. So either keep
  joints at scale 1 and taper the branches with `translate_z`, or divide the
  compensating factor back out of each child's `translate_z` (this is what the
  Hyperglyph Tree Designer's "telescoping" does, which is why resizing joints
  there doesn't reshape the tree).
- **Scale joints uniformly.** Uniform scale preserves the branch angle exactly
  (35.000° at scale 0.5, 1.0 and 2.0 above); a non-uniform scale shears the
  frame and bends it — `scale_z = 0.5` on the joint above turned a 35° branch
  into 54.47°.

Draw the limbs as **Link nodes** between each joint and its parent
(`links-and-edges.md`); the joints alone read as a cloud of beads.

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
