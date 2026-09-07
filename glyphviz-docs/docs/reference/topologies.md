# Topologies

The complete, exact list — IDs and names from `TOPO_NAMES`
(`glyphviz_core/topology.py:19-58`), positioning behavior read directly from
each topology's `_*_offset` function in the same file (registered in
`_TOPO_OFFSET_FUNCS`, `topology.py:502-520`), not inferred from naming
convention.

## What topology controls

A node's topology governs how *its children* are arranged in 3D space —
translating each child's raw `translate_x/y/z` CSV values into a
topology-specific spatial meaning (angle, height, radius, etc.) before that
offset is transformed into world space by the parent's full rotation+scale
chain (`compute_world_positions`, `topology.py:523-574`).

## The full list

The **Animation** column names the folder in the [downloadable animation
series](#topology-animations-a-downloadable-instructional-series) that shows
that topology's placement axes sweeping, one at a time.

| ID | Name (`TOPO_NAMES`) | Offset function | What it actually does | Animation |
|---|---|---|---|---|
| 0 | None | *(fallback)* `_cartesian_offset` | No offset function is registered for `TOPO_NONE`; `_TOPO_OFFSET_FUNCS.get()` falls through to plain Cartesian — children translate rigidly with the parent, `(dx,dy,dz) = (tx,ty,tz)`, no automatic layout (`topology.py:325-332`) | `topo08_grid_probe` |
| 1 | Cube | `_cube_offset` | Places the child on one of 6 named faces, chosen by the child's own **Facet**/`subspace` field (0–5 = +X,−X,+Y,−Y,+Z,−Z); `tx`/`ty` position the child within that face's plane, `tz` is distance outward from the face surface (`topology.py:403-411`) | `topo01_cube_probe` |
| 2 | Sphere (KML) | `_sphere_offset` | `tx`/`ty`/`tz` are read as longitude/latitude/altitude and converted to a point on/above the parent's rendered spherical surface, KML-style (`topology.py:335-336, 61-81`) | `topo02_sphere_probe` |
| 3 | Torus | `_torus_offset` | `tx` = orbital angle, `ty` = tube angle around the donut cross-section, `tz` = radial offset from the tube surface; major/minor radius split comes from the parent's `ratio` field (`topology.py:339-350`) | `topo03_torus_probe` |
| 4 | Cylinder | `_cylinder_offset` | `tx` = angle (degrees) around the cylinder's local-Z axis, `ty` = literal height offset along that axis, `tz` = radial distance from the axis (0 = surface) (`topology.py:364-388`) | `topo04_cylinder_probe` |
| 5 | Pin | `_pin_offset` | Offset = `(ty, tz, base_radius + tx)` — `tx` drives height up the pin from its base, `ty`/`tz` are lateral X/Y offset (`topology.py:399-400`). The Pin *glyph* stands with its tip on the node's origin and its shaft along +Z to suit this: at `tx = 0` a child sits at the centre of the pin's head, and sliding `tx` down to `-base_radius` walks it to the tip | `topo05_pin_probe` |
| 6 | Rod | `_rod_offset` | `ty` = angle around the rod's axis, `tz` = radial distance from the axis; `tx` is remapped from a `[0,180]` range onto the rod's full physical length (`2 × base_radius × ROD_HEIGHT_FACTOR`) (`topology.py:353-361`) | `topo06_rod_probe` |
| 7 | Point | `_point_offset` | Same KML longitude/latitude/altitude math as Sphere, but with the surface radius forced to `0.0` — children sit out from the exact center point along a ray, not on a shell (`topology.py:391-396`) | `topo07_point_probe` |
| 8 | Plane (Grid) | `_cartesian_offset` | Plain Cartesian: `tx`/`ty` position the child within the parent's local XY plane, `tz` is elevation above it | `topo08_grid_probe` |
| 9 | Zcube | `_zcube_offset` | Identical face-selection math to Cube, but the base-radius term is dropped — `dist = tz` only, so a child at `tz=0` sits at the parent's *center*, not on the cube face (`topology.py:431-441`) | *planned* |
| 10 | Zsphere | `_zsphere_offset` | Same KML math as Point — radius forced to `0.0` (`topology.py:444-447`) | *planned* |
| 11 | Ztorus | `_ztorus_offset` | Same orbital/tube-angle math as Torus, but with the tube (minor) radius zeroed out — `tz` offsets directly outward from the main ring instead of riding a donut surface (`topology.py:450-464`) | *planned* |
| 12 | Zcylinder | `_zcylinder_offset` | Same angle math as Cylinder, but radius forced to `0` — children collapse onto the central axis, and `tz` offsets straight out from that axis (`topology.py:467-477`) | *planned* |
| 13 | Zrod | `_zrod_offset` | Delegates to the *exact same* placement function as Zcylinder — the only documented Rod→Zrod difference is a separate rendering rule (scale not affecting child size), not a position difference (`topology.py:480-484`) | *planned* |
| 14 | Spiral | `_spiral_offset` | `tx` is the helical angle (also drives height progression, scaled by `base_radius`), `ty` adds a further linear height offset, `tz` is radial offset from the spiral's radius (`topology.py:414-421`) | *planned* |
| 15 | Video | `_cartesian_offset` | Plain Cartesian offset — treats the parent as a flat "screen," children placed at literal `tx/ty/tz` | `topo08_grid_probe` |
| 16 | Plot | `_plot_offset` | Plain Cartesian offset — 1D/2D/3D line plot, GPS, or oscilloscope data; GlyphViz/ANTz-extension topology, not in the original ANTz/GaiaViz set (`topology.py:35, 487-491`) | `topo08_grid_probe` |
| 17 | Surface | `_surface_offset` | Plain Cartesian offset — `tx`/`ty` form a grid position, `tz` is the height/value at that point (deformable grid, FFT, LIDAR, sound sphere); GlyphViz/ANTz-extension topology (`topology.py:36, 494-499`) | `topo08_grid_probe` |
| 18 | Point Cloud | `_pointcloud_offset` | Plain Cartesian offset — **but the children render as one batched `GL_POINTS` array instead of one glyph apiece**, which is what makes six-figure point counts practical. For unstructured scan data: LIDAR, photogrammetry, particle sets. GlyphViz/ANTz-extension topology. See [Point clouds](#point-clouds-topology-18) below | `topo08_grid_probe` |

`TOPO_COUNT = 19` (`topology.py`). Default topology for newly-created
nodes is **Point** (`main_window.py:536`).

Six topologies share one animation because they share one offset function:
None (0), Plane (8), Video (15), Plot (16), Surface (17) and Point Cloud (18)
are all plain Cartesian, so `topo08_grid_probe` is the animation for all of
them. (A Video plate is separately shown *in use* in
`06_sphere_probe_with_screen`.)

## Point clouds (topology 18)

Point Cloud is the one topology that **replaces** how its children draw
rather than decorating it. Plot and Surface add a polyline or a quad mesh
*on top of* the children's glyphs; a Point Cloud parent's children draw no
glyphs at all. They are gathered into a single position + color array and
issued as one `glDrawArrays(GL_POINTS)`.

That is the whole reason the topology exists. Measured on an RTX 3080 Ti:

| Points | Drawn as a cloud | Drawn as glyphs |
|---|---|---|
| 100,000 | 0.10 ms/frame | the scene GlyphViz is already slow at |
| 1,000,000 | 0.63 ms/frame | — |

**Every point is still a real node.** It has an id, a color, a label, a
channel binding; it is individually clickable (the pick pass renders the same
batch in per-point colour-IDs); it selects, saves and merges like any other
node. Only the drawing is pooled.

### Using it

1. Give a parent node `topo = 18`.
2. Give each point a child row whose `translate_x/y/z` is its position
   relative to that parent. Plain Cartesian — no angles, no surface.
3. Colour each point with its own `color_r/g/b/a`.

The parent's **`ratio`** sets the rendered point size in pixels
(`ratio × 20`, minimum 1, maximum 64) — the same conversion Link lines and
Plot polylines use for their widths. The default `ratio` of 0.1 gives 2 px
points. Size is per-cloud, not per-point: fixed-function OpenGL has no
per-vertex point size.

The parent itself still draws as an ordinary glyph, so it stays visible and
clickable as the handle for the whole cloud — move, rotate or scale it and
every point follows.

### How big a cloud can be

The renderer is not the limit; the node model is — and mostly its footprint
on disk. Each `Node` costs about 2 KB resident and about **90 bytes saved**,
since GlyphViz writes only the columns a point actually uses. Measured end to
end:

| Points | Import from LAZ | Saved scene | Save | Reopen | Resident |
|---|---|---|---|---|---|
| 100,000 | 1.4 s | 9.1 MB | 1.0 s | 1.4 s | ~200 MB |
| 442,767 | 4.0 s | 40.7 MB | 4.2 s | 6.3 s | ~900 MB |

**Importing is far cheaper than saving.** A 442,767-point cloud comes out of a
compressed LAZ in about four seconds and renders at ~400 fps; it is keeping it
as a scene file that gets expensive. 100,000 is the comfortable default —
decimate on import for anything much larger, see
[Importing point clouds](point-cloud-import.md).

### Interaction rules

- **The `\` draw limit counts a cloud as one unit** — its parent glyph. The
  limit thins the glyphs around a cloud and never decimates the cloud
  itself, the same way it leaves links and plot lines alone.
- **Labels**: in the all-tags display mode a cloud's points are *not*
  labelled, because a six-figure scan would bury the scene in text. A point
  is labelled when it is **selected**, or when it pins itself with
  `show_text`. The default tag mode (selected only) already behaves this way
  for every node, so nothing changes there.
- **`topo_scale`** applies to all three axes, since none of them is angular —
  it is the single field that rescales an imported scan.

### Compatibility

A `topo` value the loader does not recognise falls back to plain Cartesian
placement, and `_pointcloud_offset` *is* that fallback. So a `topo=18` file
opened by a GlyphViz build predating this topology puts every point in
exactly the right place — it just draws them as individual glyphs, slowly.
Nothing is lost and no column was added: the cloud travels in the CSV.

## Topology Scale — when children fly off after a topology change

Read the table above and one distinction stands out: some topologies read a
child's `translate` axis as an **angle** (Sphere's longitude, Torus's orbital
angle) and others read it as a **distance** (Cube's position across a facet,
Pin's height, all three axes of the Cartesian family). An angle of 330° is a
perfectly ordinary value; 330 *world units* is enormous — far larger than any
glyph. So a parent switched from Sphere to Cube reads its children's
coordinates in units 180× bigger than they were authored for, and they
disappear into the distance.

Each node carries a **Topology Scale** (`topo_scale`, the Properties panel row
under Topology) that multiplies exactly the distance-valued axes of its own
topology, and nothing else. Longitude, latitude and every orbital or tube angle
are left alone, so turning it down can never distort a circular layout — a
sphere's children stay exactly on the sphere.

| Value | Meaning |
|---|---|
| **1.0** (default) | One translate unit is one world unit. GlyphViz's original behavior, and what any file without a `topo_scale` column loads as — no existing scene changes. |
| **1/180 ≈ 0.005556** (**ANTz** preset) | A linear axis spans the parent's own extent: a cube facet is 360 units across, so translate 180 lands on its edge exactly as 180° of longitude reaches the far side of a sphere. At this setting a layout authored in degrees survives a switch between an angular and a linear topology. |

Twelve children at `translate_x = 0, 30, … 330` and `translate_y = 45` under a
scale-9 parent, farthest child:

| Parent topology | at 1.0 | at 1/180 |
|---|---|---|
| Sphere | 9.0 | 9.0 |
| Torus | 8.8 | 8.8 |
| Cylinder | 405.1 | 9.3 |
| Spiral | 413.3 | 13.8 |
| Cube | **2997.5** | 18.9 |

Notes:

- Set it on the **parent** — it describes that node's coordinate system, the
  same way Topology and Ratio do.
- Edits apply to the whole selection, so *Edit → Select By → Topology → Cube*
  followed by one slider drag retunes every cube parent in a scene at once.
- **World Grid children and root nodes are exempt.** A grid's footprint is
  drawn from the same extents window its children's coordinates are read in,
  and a root's `translate` *is* its world position, not an offset.
- It is bindable as a Channels attribute, so a scene that animates `topo` can
  animate `topo_scale` alongside it — see
  [Channels](channels-animation.md) and the Channel Parameters example.
- If a topology change does scatter a subtree, the status bar says so and
  names this field.
- The **Glyph Composer** sets it for you. Its per-level *Topo Scale* row has
  the same spin box, log slider and 1:1 / ANTz presets, plus an **Auto**
  checkbox (on by default). While Auto is on, a level whose children ask for
  the *Angular (ring around parent)* distribution — which hands them
  `translate_x = 0…360` — gets ANTz whenever its topology would read that
  sweep as a distance, and 1.0 otherwise. Touching the value or a preset
  turns Auto off and the number is yours; re-check it to go back to fitting.

## Orientation ("facing outward")

Independent of position, most topologies also insert a base rotation between
the parent's world orientation and the child's own `rotate_x/y/z`, so a child
with a fixed local pose keeps "facing outward" as its placement coordinates
change (`_topology_base_rotation`, `topology.py:192-232`):

- **Rod/Zrod**, **Cylinder/Zcylinder/Spiral**: rotate around the single
  circular angle parameter, so a radially-posed child sweeps around the axis
  without flipping orientation.
- **Sphere/Point/Torus/Ztorus**: align the child's +Z with the KML surface
  normal at its longitude/latitude — Torus reuses the identical formula
  because a torus's tube cross-section is a small "sphere" wrapped around the
  main ring.
- **Cube**: a precomputed rotation per face, aligning +Z with that face's
  outward normal.
- **Pin and everything else**: identity — no circular placement, so nothing
  to orient around.

## Z-topology variants, as a group

Topologies 9–13 (Zcube, Zsphere, Ztorus, Zcylinder, Zrod) are each "akin to"
an already-implemented topology with its surface/radius offset term zeroed
out, so children pass through the parent's center/axis instead of riding on
its rendered surface — confirmed directly in each function's docstring
(`topology.py:424-484`).

## Cube face names

The **Facet** field (`Node.subspace`, 0-indexed) names faces `+X, -X, +Y, -Y,
+Z, -Z` for values 0–5 (`CUBE_FACE_NAMES`, `topology.py:88`) — confirmed
against real ANTz ground truth via the legacy `facet` CSV column (1-indexed,
`facet = subspace + 1`).

## Topology animations — a downloadable instructional series

A companion set of Channels-animated scenes built specifically to make the
table above *visible* rather than read. Each **probe scene** parks a small
cone-shaped glyph on one topology's surface and sweeps it through that
topology's three placement axes one at a time — axis 1 out and home, then
axis 2, then axis 3 (150 frames per axis, 450 frames total at 30 fps). The
probe is a cone rather than a sphere because half of what a topology does is
*orientation*: under Sphere, Point, Torus, Cylinder, Rod and Cube the engine
pre-rotates children so the child's +Z tracks the outward surface normal, and
a cone makes that rotation legible. Under the Cartesian topologies it never
tips at all.

Every scene also carries a "scribe" pair, both derived from the probe's own
three tracks:

- a **comet** — eight small glyphs reading the same tracks a few frames
  delayed, fading out behind the probe. They live in the *parent's topology
  coordinates*, so the tail bends the way the topology bends: it arcs on a
  Sphere, wraps the tube on a Torus, stacks on a Pin.
- a **chalk line** — 150 beads at the probe's actual *world-space* positions,
  each switching on as the probe reaches it, so the path draws itself and
  stays drawn.

That pairing is what the series is for: the probe moves in the topology's
coordinates while the line accumulates in world space, so the mapping between
the two is on screen at the same time instead of being narrated.

Every scene shares one ruler — a dim wireframe sphere at radius 10 — and every
linear axis reaches exactly that far, so scenes are directly comparable to one
another.

[:material-download: Download the topology animations (546 KB)](https://iluvdata.org/glyphviz/zips/Topology_Animation_Examples.zip){ .md-button .md-button--primary }

The set also ships inside the full examples archive, as
`examples/Topology_Animation_Examples/` — see the
[Examples Gallery](../examples/index.md).

1. Extract the zip, **keeping each scene folder intact** — GlyphViz only auto-loads Channels when a node CSV's folder holds exactly one `ch-map` and one `ch-tracks` file, so flattening the folders silently disables playback everywhere.
2. Open a `*_gv_node.csv` in GlyphViz (**File → Open**), or drag the zip straight onto the window; the Channels load automatically and the Channels panel appears.
3. **Space** plays/pauses, **Shift+Space** stops and resets to frame 0, **T** toggles labels, **C** cycles the scene's stored cameras.

### The probe scenes — one per topology

One folder per topology, numbered by topology ID. These are the folders the
**Animation** column of the table above points at.

| Folder | Topology | The three axes it sweeps |
|---|---|---|
| `topo01_cube_probe` | Cube (1) | `translate_x`/`translate_y` across the chosen face, `translate_z` lifting off it. The face itself comes from the child's own **Facet** column, not from a coordinate — so the probe never changes face. |
| `topo02_sphere_probe` | Sphere (2) | longitude −180→180 (a full wrap), latitude −90→90, altitude. Watch the cone tip over as latitude changes. |
| `topo03_torus_probe` | Torus (3) | orbital angle 0→360, tube angle 0→360, offset from the tube surface. The tube radius is the *parent's* `ratio`. |
| `topo04_cylinder_probe` | Cylinder (4) | angle 0→360, height along the axis, radial distance measured **from the surface**. |
| `topo05_pin_probe` | Pin (5) | height up the pin, then the two sideways axes. Note the reshuffle: `translate_x` is the vertical axis here. |
| `topo06_rod_probe` | Rod (6) | position along the rod, angle about it, radial distance from it. The along-axis value is *normalized* — 0–180 spans the rod's full rendered length, the only topology with a normalized axis. |
| `topo07_point_probe` | Point (7) | longitude, latitude, distance from the centre. Sphere without the base radius: `translate_z` is the whole distance, so 0 collapses the child into the parent. Spokes. |
| `topo08_grid_probe` | None (0), Plane (8), Video (15), Plot (16), Surface (17) | plain ±10 on x, y and z. Identity orientation and no surface to ride, so the probe starts at a true (0, 0, 0) — the origin is a real place here. One animation for all five Cartesian topologies. |

### The concept scenes — what else Channels can do

Four further scenes in the same visual language, teaching the *channel*
mechanics rather than a topology. Their numbering is a separate series from
the `topo*` folders.

| Folder | Frames | What it teaches |
|---|---|---|
| `03_grid_axis_triad` | 210 | **Several channels can read one track.** Three probes on a Cartesian parent, three channels, and a single track column — channel 1 binds it to `translate_x`, channel 2 to `translate_y`, channel 3 to `translate_z`. One curve, three axes, no duplicated data. |
| `04_sphere_meridian_comb` | 260 | **One channel can drive many nodes.** Twelve children share a single channel that writes only latitude, altitude and colour — each keeps its own longitude from the CSV, so the shared sweep combs a whole meridian at once. The compression pattern for large animated scenes. |
| `05_rosetta_grid_vs_sphere` | 450 | **The same numbers mean different things.** A Cartesian parent and a Sphere parent, side by side, fed byte-identical values from one channel: ±10 *units* on the left, ±10 *degrees* on the right. Deliberately no standoff on the sphere probe — the point is that both receive exactly the same track. |
| `06_sphere_probe_with_screen` | 450 | The sphere probe scene plus an upright video plate (a Video-topology node on `texture_id` 1) standing beside it. Drop a lesson video into the folder's `media/` and it plays in-scene, alongside the topology it explains. |

The zip also ships the generator itself — `glyphviz_topology_anim.py` and the
`glyphviz_topology_animations.ipynb` notebook that drives it — so the whole
series, or one topology, or slower sweeps, can be regenerated rather than
hand-edited:

```text
python glyphviz_topology_anim.py --out topology_animations
python glyphviz_topology_anim.py --probe-topo 3        # torus only
python glyphviz_topology_anim.py --no-scribe           # bare probe scenes
python glyphviz_topology_anim.py --frames-per-axis 210 # slower sweeps
```

!!! note "Still to come"
    Probe scenes for the Z-variants (Zcube, Zsphere, Ztorus, Zcylinder, Zrod)
    and Spiral, which will fill in the *planned* rows of the table above.
    Following the ANTz convention, the Z-variants' parents will be drawn in
    **wireframe** where the base topologies are solid — the visual tell that a
    child rides the parent's centre rather than its surface. Per-animation
    thumbnails alongside each topology row are planned as well.

## Next step

See [Geometries](geometries.md) for what individual nodes look like, or
[Properties Panel](properties-panel.md#selected-node) for where Topology and
Facet are set in the GUI.
