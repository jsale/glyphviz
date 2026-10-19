# blender_lab — Blender builds it, GlyphViz plays it

Claude drives Blender 3.4 (live, over the blender-mcp addon's socket) to build a mechanism,
bakes every moving part, and turns the bake into an ordinary GlyphViz scene: one mesh node per
rigid part, animated by a Channels pair.  Nothing in the scene depends on Blender at runtime.

The first subject is **`machine_design.py`**, a loopable clockwork marble machine
(12 s loop, 360 frames at 30 fps, 35 parts, 560 KB).

## Run it

All Python except the Blender-side scripts uses the `glyphviz` env (`$env:GLYPHVIZ_PYTHON`).
Blender must be open with *N-panel > MCP for Blender > Connect* (port 9876).

```
python bl.py run machine_design.py        # build + bake inside the live Blender  -> out/machine/
python bl.py run audit_collisions.py      # every-frame overlap audit, inside Blender
python blender_to_gv.py out/machine out/Clockwork_Marble_Machine clockwork --scale 10
python verify_scene.py out/machine out/Clockwork_Marble_Machine 0 90 180 270
python check_motion.py out/machine        # per-frame jumps, including the loop seam
python gv_frames.py out/Clockwork_Marble_Machine out/frames/f 0 1 2 ... --az -80 --el 7
```

`bl.py` speaks the addon's JSON socket directly (`{"type":"execute_code","params":{"code":...}}`),
which is all the MCP server wraps.  Use it when the `mcp__blender__*` tools are not loaded in the
Claude session (they load only if the session started after the server was registered).
`blender -b -P script.py` also works headless.

## The pipeline

| step | file | runs in | does |
|---|---|---|---|
| build | `machine_lib.py`, `machine_design.py` | Blender | closed-form motion keyed on every frame |
| bake | `export_for_glyphviz.py` | Blender | per-part OBJ in LOCAL space + per-frame world matrices + animated colour/hide props -> `bake.json` |
| convert | `blender_to_gv.py` | glyphviz env | SceneBuilder -> `*_gv_node.csv`, `*_gv_ch-map.csv`, `*_gv_ch-tracks.csv` |
| verify | `verify_scene.py` | glyphviz env | poses the scene with the app's own `ChannelEngine` + `node_world_matrix`, compares vertex SETS to Blender's |
| audit | `check_motion.py`, `audit_collisions.py` | env / Blender | continuity and collisions |
| look | `gv_frames.py`, `blender_preview.py` | env / Blender | headless renders with channels applied |

### How a Blender part becomes a GlyphViz node

GlyphViz normalizes every imported mesh on its OWN bounding box (centre -> origin, max radius -> 1),
so a node rotates about the mesh's bbox centre, not Blender's object origin.  For a rigid part that
is exact without any pivot rig:

```
node translate = world position of the part's bbox centre   (x S)
node rotate    = the part's world rotation as GlyphViz Euler
node scale     = mesh radius x S
```

Only attributes that actually vary over the loop become channel tracks; parts with identical motion
share a channel.  Object scale and mirroring must be baked into the mesh (the converter refuses a
non-rotation matrix).

## Traps (all hit once)

* **Euler order.** GlyphViz EULER_XYZ is `Rx @ Ry @ Rz`, the reverse of Blender's XYZ (`Rz @ Ry @ Rx`).
  Decompose numerically.  Every rotation has two solutions `(rx,ry,rz)` and `(rx+180, 180-ry, rz+180)`;
  pick the one nearest the previous frame or a plain spin drags two spurious tracks along.
* **Poles.** Near `ry = +-90` use `atan2`, not `asin` (asin lost 1e-6 there), orthonormalize
  Blender's float32 matrices first, and handle the singular case explicitly.
* **Viewing.** GlyphViz `az=-90, el=0` looks from -Y, which is Blender's front.  The machine lives in the
  XZ plane with shafts along Y.
* **Meshing gears.** Trapezoid teeth at exact pitch spacing interfered; centre distance + 0.015
  (`MESH_GAP`) gives zero overlap over a full loop.  Phase law: `theta_b = phi + pi - pi/Tb - (theta_a - phi) * Ta/Tb`.
* **Escapement.** A real anchor straddles a half-integer number of tooth pitches (2.5), the wheel steps
  half a tooth at each pendulum zero crossing, and the pallets must reach only to r~0.92 (tip 0.98).
  `scan_escapement.py` found the workable window (10 deg swing, wheel z 0.96, pallets +-0.74).  A scan that
  samples every second frame misses collisions on the odd ones, so sample twice per frame.
* **Tangent contact is an overlap.** A marble exactly resting on a plank is flagged by a BVH test.  Leave
  a few mm.
* **Loop closure.** Gear turns per loop must be integers; marbles are scripted on closed paths (a
  rigid-body bake would not loop).  Check the wrap with `check_motion.py` (it rolls frame N back to 1).
* **`-0` in the tracks file.** Format numbers so they never print `-0`.

## Results (2026-10-18)

* Gear pairs G1/G2, G2/G3 and escape wheel/anchor: **0 interfering triangles over all 360 frames**.
* Collision audit across the whole machine: **0 unexpected overlaps** (expected: pins seated in the wheel, the
  cam follower on the cam, the rod pinned in the piston, marbles passing through the prism).
* GlyphViz vs Blender, 9+ frames incl. exact-pole frames: worst vertex distance **0.00007 world units**
  (the CSV's 4-decimal rounding); negative control with a 5% scale error fails at 0.65-1.25.
* Rendered loop seam: frame 359 -> 0 pixel change is 0.98x the median frame-to-frame change.

## Not built / ideas

* Rigid-body marbles that really tumble (would need a bake that loops, or an accepted seam).
* Scale, shape keys, armatures, particles and modifiers-on-the-fly are NOT representable as channels;
  anything animated that way must be decomposed into rigid parts first.
* A Geneva drive (intermittent motion) and a planetary gear set would slot into the same pipeline.
