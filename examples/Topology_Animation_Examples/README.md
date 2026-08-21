# GlyphViz topology animations — instructional series

Each folder is one scene. Open the `*_gv_node.csv` in GlyphViz (File > Open);
the `ch-map` and `ch-tracks` files in the same folder load automatically and a
Channels panel appears.

**Keep the folders intact.** GlyphViz auto-loads Channels only when it finds
exactly one `ch-map` and one `ch-tracks` file in the node CSV's folder. Two
candidates in one directory disable Channels entirely, silently.

Playback: Space = play/pause, Shift+Space = stop (resets to frame 0 and
restores CSV values), T = toggle labels, C = cycle stored cameras. Default
30 fps, loop on. Every probe scene is 450 frames — 15 seconds; the concept
scenes run 210–450.

## Working surfaces

- `glyphviz_topology_animations.ipynb` — the notebook. Builds every scene,
  previews the probe path and the track curves inline before you open the app,
  and prints a folder audit at the end.
- `glyphviz_topology_anim.py` — the module the notebook drives. Structural
  changes go here; re-run the notebook's reload cell afterwards.

## Conventions

| | |
|---|---|
| parent geometry | **solid**, `color_a = 150`. Wireframe is reserved for the z-variants (ANTz convention). `TopoSpec.parent_geometry` picks wire automatically once a topo id is in `Z_TOPOS`, so the contrast can't drift as the series grows. |
| Grid parent | solid Grid plate (geometry 21). |
| probe | a small **cone** at scale `(0.28, 0.28, 0.48)` — roughly a quarter of the unit parent. A cone because half of what a topology does is *orientation*, and a sphere hides it. |
| seating | surface-riding topologies park the probe at `STANDOFF = 0.25` along the surface-normal axis, so it travels **over** the surface. Altitude `0` puts a child's *origin* on the surface — literally correct, visually wrong. |
| ruler | one dim wireframe at radius 10 (`color_a = 45`), ten times the parent's size, so it can't be misread as a z-variant tell. |
| sweep | three phases of 150 frames: axis 1 sweeps and returns home, then axis 2, then axis 3. Three tracks, three map rows, one `ch_input_id`. |
| scribe | on by default for every single-probe scene. |

The **0.2 render floor** is the constraint behind the probe sizing: GlyphViz
floors rendered scale at 0.2 per axis. To go smaller, scale the *parent up*
rather than the probe down, or the renderer quietly ignores you.

## The scribe effect

Two effects, both derived from the same three probe tracks, which is why both
work on every topology without extra math:

- **Comet** — eight icosahedra parented to the same node, reading the same
  three tracks delayed a few frames each and fading out behind the probe.
  They live in the *parent's topology coordinates*, so the tail bends through
  the topology exactly as the probe does: it arcs on a Sphere, wraps the tube
  on a Torus, stacks on a Pin.
- **Chalk line** — a transparent Plot-topology parent holding 150 beads at the
  probe's *Cartesian world* positions, computed with the topology's own offset
  function. Each bead's alpha is a step function that flips on as the probe
  arrives and stays on, so the curve draws itself. Plot draws its polyline
  through children in row order, which is why the beads are emitted in path
  order.

The chalk line is the one that earns its keep: the probe moves in the
topology's coordinates while the line accumulates in world space, so the
mapping between the two is on screen simultaneously rather than narrated.
`scribe=False` turns both off.

## Scenes

### Probe scenes — one per topology

Numbered by topology id, with one exception: the Cartesian probe is filed at
**08** rather than 00. It teaches five topologies at once — None (0), Plane
(8), Video (15), Plot (16) and Surface (17) all share `_cartesian_offset` —
and filing it at 8 lets the series read 01–08 as the first eight topologies.
All eight scribe, and all run 450 frames.

| folder | what it teaches |
|---|---|
| `topo01_cube_probe` | u/v across a face, then lift off it. The face is the child's own facet column (1–6), not a coordinate, so the probe never changes face; +Z is that face's normal. |
| `topo02_sphere_probe` | lon −180→180 (a full wrap), lat −90→90, altitude 0.25→10. Watch the cone tip over as latitude changes: the engine pre-rotates children by Rz(lon)·Ry(90−lat) so +Z stays on the outward normal. |
| `topo03_torus_probe` | orbital angle, tube angle, offset from the tube surface. Reads the **parent's** `ratio` for the tube radius. |
| `topo04_cylinder_probe` | angle, height, radial — measured from the *surface*, unlike Zcylinder which measures from the axis. |
| `topo05_pin_probe` | height up the pin, then the two sideways axes. Note the reshuffle: `translate_x` is the vertical axis here. |
| `topo06_rod_probe` | along the rod, angle about it, radial from it. The along-axis value is normalized: 0–180 spans the rod's full rendered length. The only topology with a normalized axis. |
| `topo07_point_probe` | lon, lat, distance from centre. Sphere without the base radius, so `tz` is the whole distance and `tz = 0` collapses the child into the parent. Spokes. |
| `topo08_grid_probe` | Cartesian baseline: ±10 on x, y, z. Identity orientation, no standoff — the origin is a real place here. |

### Concept scenes — what Channels can do

A separate 03–06 numbering, left alone deliberately: these numbers predate the
`topo*` series (01 and 02 were the grid and sphere probes, now `topo08` and
`topo02`), and renumbering would break links to them.

| folder | frames | scribe | what it teaches |
|---|---|---|---|
| `03_grid_axis_triad` | 210 | no | Three probes, three channels, **one track column**. Several channels may read the same track. |
| `04_sphere_meridian_comb` | 260 | no | Twelve children, **one channel** — it overwrites only latitude, altitude and colour, so each child keeps its own longitude from the CSV. The compression pattern. |
| `05_rosetta_grid_vs_sphere` | 450 | no | Two parents, **byte-identical numbers**, one channel. ±10 units vs ±10 degrees. Deliberately no standoff on the sphere probe — the point is that both receive the same values. |
| `06_sphere_probe_with_screen` | 450 | yes | The base sphere scene plus an upright video plate (geometry 21, topo 15, `rotate_x = 90`) on `texture_id` 1. Drop the lesson video into its `media/` folder. |

Multi-child scenes stay clean on purpose: with three or twelve probes already
in flight, a comet and a chalk line each would read as clutter rather than
clarity.

### Still to come

Probe scenes for Zcube (9), Zsphere (10), Ztorus (11), Zcylinder (12), Zrod
(13) and Spiral (14). `TopoSpec.parent_geometry` already picks wireframe
automatically for anything in `Z_TOPOS`, so the solid/wireframe contrast that
distinguishes a z-variant from its base topology cannot drift as the series
grows — which is why nothing else in these scenes is allowed to spend it.

## `rotation_mode`, and why most files don't have it

A node CSV *without* a `rotation_mode` column loads in ANTz Heading/Tilt/Roll
(Z-X-Z) mode. The writer therefore omits the column while every rotation is
zero — the two conventions agree there and the file stays minimal — and emits
an explicit `rotation_mode = 0` (Euler XYZ, each field spinning its own axis)
the moment any node is hand-posed. Right now the video-screen scene is the
only file with the column, because its plate is the only rotated node.

## Regenerating

```text
python glyphviz_topology_anim.py --out topology_animations
python glyphviz_topology_anim.py --probe-topo 3        # torus only
python glyphviz_topology_anim.py --no-probes           # concept scenes only
python glyphviz_topology_anim.py --no-scribe           # bare probe scenes
python glyphviz_topology_anim.py --ghosts 16 --chalk-points 200
python glyphviz_topology_anim.py --frames-per-axis 210 # slower sweeps
```

A plain run reproduces all twelve published folders byte-for-byte — verified
2026-08-21 — so regenerating is safe to do and easy to diff.

For audio-locked playback, put a one-line `<anything>_gv_audio.txt` next to the
node CSV containing a relative path to an audio file — frame advance then
follows real audio position instead of the FPS timer, so render slowdowns cost
smoothness rather than sync.

## Worth a skeptical first look

- **Plot overlay with a transparent parent.** The scribe's Plot parent is
  `color_a = 0` rather than `hide = 1`, on the assumption that hiding a parent
  may suppress its overlay. If `hide = 1` works, prefer it.
- **Alpha-0 vertices.** The chalk line's unrevealed beads may leave a faint
  ghost of the whole path depending on blend mode. If so, set the World row's
  `render_mode` to 1 (Additive).
- **Screen placement.** The plate sits at y = 19, lifted to z ≈ 4.6, facing
  back down −Y. Whether that framing works depends on your camera; it's two
  numbers in `add_screen()`.
- **Standoff vs. truth.** `STANDOFF` makes the probe look right at the cost of
  the axis home no longer being a round zero. If a lesson needs the honest
  number on screen, set `gta.STANDOFF = 0.0`, reload, and regenerate.
