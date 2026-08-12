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

| ID | Name (`TOPO_NAMES`) | Offset function | What it actually does |
|---|---|---|---|
| 0 | None | *(fallback)* `_cartesian_offset` | No offset function is registered for `TOPO_NONE`; `_TOPO_OFFSET_FUNCS.get()` falls through to plain Cartesian — children translate rigidly with the parent, `(dx,dy,dz) = (tx,ty,tz)`, no automatic layout (`topology.py:325-332`) |
| 1 | Cube | `_cube_offset` | Places the child on one of 6 named faces, chosen by the child's own **Facet**/`subspace` field (0–5 = +X,−X,+Y,−Y,+Z,−Z); `tx`/`ty` position the child within that face's plane, `tz` is distance outward from the face surface (`topology.py:403-411`) |
| 2 | Sphere (KML) | `_sphere_offset` | `tx`/`ty`/`tz` are read as longitude/latitude/altitude and converted to a point on/above the parent's rendered spherical surface, KML-style (`topology.py:335-336, 61-81`) |
| 3 | Torus | `_torus_offset` | `tx` = orbital angle, `ty` = tube angle around the donut cross-section, `tz` = radial offset from the tube surface; major/minor radius split comes from the parent's `ratio` field (`topology.py:339-350`) |
| 4 | Cylinder | `_cylinder_offset` | `tx` = angle (degrees) around the cylinder's local-Z axis, `ty` = literal height offset along that axis, `tz` = radial distance from the axis (0 = surface) (`topology.py:364-388`) |
| 5 | Pin | `_pin_offset` | Offset = `(ty, tz, base_radius + tx)` — `tx` drives height up the pin from its base, `ty`/`tz` are lateral X/Y offset (`topology.py:399-400`) |
| 6 | Rod | `_rod_offset` | `ty` = angle around the rod's axis, `tz` = radial distance from the axis; `tx` is remapped from a `[0,180]` range onto the rod's full physical length (`2 × base_radius × ROD_HEIGHT_FACTOR`) (`topology.py:353-361`) |
| 7 | Point | `_point_offset` | Same KML longitude/latitude/altitude math as Sphere, but with the surface radius forced to `0.0` — children sit out from the exact center point along a ray, not on a shell (`topology.py:391-396`) |
| 8 | Plane (Grid) | `_cartesian_offset` | Plain Cartesian: `tx`/`ty` position the child within the parent's local XY plane, `tz` is elevation above it |
| 9 | Zcube | `_zcube_offset` | Identical face-selection math to Cube, but the base-radius term is dropped — `dist = tz` only, so a child at `tz=0` sits at the parent's *center*, not on the cube face (`topology.py:431-441`) |
| 10 | Zsphere | `_zsphere_offset` | Same KML math as Point — radius forced to `0.0` (`topology.py:444-447`) |
| 11 | Ztorus | `_ztorus_offset` | Same orbital/tube-angle math as Torus, but with the tube (minor) radius zeroed out — `tz` offsets directly outward from the main ring instead of riding a donut surface (`topology.py:450-464`) |
| 12 | Zcylinder | `_zcylinder_offset` | Same angle math as Cylinder, but radius forced to `0` — children collapse onto the central axis, and `tz` offsets straight out from that axis (`topology.py:467-477`) |
| 13 | Zrod | `_zrod_offset` | Delegates to the *exact same* placement function as Zcylinder — the only documented Rod→Zrod difference is a separate rendering rule (scale not affecting child size), not a position difference (`topology.py:480-484`) |
| 14 | Spiral | `_spiral_offset` | `tx` is the helical angle (also drives height progression, scaled by `base_radius`), `ty` adds a further linear height offset, `tz` is radial offset from the spiral's radius (`topology.py:414-421`) |
| 15 | Video | `_cartesian_offset` | Plain Cartesian offset — treats the parent as a flat "screen," children placed at literal `tx/ty/tz` |
| 16 | Plot | `_plot_offset` | Plain Cartesian offset — 1D/2D/3D line plot, GPS, or oscilloscope data; GlyphViz/ANTz-extension topology, not in the original ANTz/GaiaViz set (`topology.py:35, 487-491`) |
| 17 | Surface | `_surface_offset` | Plain Cartesian offset — `tx`/`ty` form a grid position, `tz` is the height/value at that point (deformable grid, FFT, LIDAR, sound sphere); GlyphViz/ANTz-extension topology (`topology.py:36, 494-499`) |

`TOPO_COUNT = 18` (`topology.py:37`). Default topology for newly-created
nodes is **Point** (`main_window.py:536`).

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

Twelve children at `translate_x = 0, 30, … 330` under a parent of radius 9,
farthest child:

| Parent topology | at 1.0 | at 1/180 |
|---|---|---|
| Sphere | 9.0 | 9.0 |
| Torus | 9.0 | 9.0 |
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

A companion set of Channels-animated scenes, one small probe glyph per
topology, built specifically to make the table above *visible* rather than
read. Each scene parks a cone-shaped probe on a topology's surface and sweeps
it through the three placement axes one at a time (150 frames per axis, 450
frames total at 30 fps), with an optional "scribe" effect — a fading comet
trail plus a chalk-line overlay that draws the probe's actual world-space
path as it moves — so you can watch a topology's coordinate system become a
literal line in space instead of inferring it from numbers.

[:material-download: Download the topology animations (topology_animations.zip)](https://www.iluvdata.org/glyphviz/animations/topology_animations.zip){ .md-button .md-button--primary }

1. Download and extract **[topology_animations.zip](https://www.iluvdata.org/glyphviz/animations/topology_animations.zip)**, keeping each numbered folder intact — GlyphViz only auto-loads Channels when a node CSV's folder holds exactly one `ch-map` and one `ch-tracks` file.
2. Open a `*_gv_node.csv` in GlyphViz (**File → Open**); its Channels load automatically and the Channels panel appears.
3. **Space** plays/pauses, **Shift+Space** stops and resets to frame 0, **T** toggles labels, **C** cycles the scene's stored cameras.

**What's inside:**

| Folder | Teaches |
|---|---|
| `01_grid_probe` | The Cartesian baseline (None/Plane/Video/Plot/Surface all share this placement math) — no standoff, the origin is a real place. |
| `02_sphere_probe` | Longitude/latitude/altitude on the Sphere surface; watch the probe tip over as latitude changes so it always faces outward. |
| `03_grid_axis_triad` | Three probes reading one shared track column — several channels can read the same track. |
| `04_sphere_meridian_comb` | One channel driving twelve children, overwriting only latitude/altitude/color while each keeps its own CSV longitude. |
| `05_rosetta_grid_vs_sphere` | The same byte-identical numbers fed to a Cartesian parent and a Sphere parent side by side — ±10 units vs. ±10 degrees. |
| `06_sphere_probe_with_screen` | The base sphere scene plus a video plate — drop a lesson video into its `media/` folder. |
| `next_up/` | The rest of the set: Cube, Torus, Cylinder, Pin, Rod, and Point probes. |

The zip also ships the generator itself (`glyphviz_topology_anim.py` and a
Jupyter notebook), so the whole series — or a single topology, or slower
sweeps — can be regenerated rather than hand-edited.

!!! note "Thumbnails coming"
    Screenshots of each animation, placed alongside its topology's row in the table above, are planned for a future pass.

## Next step

See [Geometries](geometries.md) for what individual nodes look like, or
[Properties Panel](properties-panel.md#selected-node) for where Topology and
Facet are set in the GUI.
