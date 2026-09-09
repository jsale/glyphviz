# `code/` — the app's own placement math, and a checker built on it

Two things live here. Use them; do not reimplement either.

| | |
|---|---|
| `gv_kernel/` | GlyphViz's placement engine, **byte-identical copies** of `glyphviz_core`. Positions, transforms, rendered sizes, the CSV loader and saver. |
| `gv_extents.py` | Reads a node CSV and tells you what it will actually render as, and what is wrong with it. |

Requires `numpy` and `pandas`, both present in the environment this skill
normally runs in. Nothing else, and no GlyphViz install.

## Check a scene before you hand it over

```
python code/gv_extents.py my_scene_gv_node.csv
```

It leads with problems, because that is usually why you are running it:

```
PROBLEMS
  ! 1 child is completely inside its parent and cannot be seen
      id 22 (Sphere) is 1.500 from parent 20, whose surface that way is at 3.000
      -- 50% of the way out; clear it at 3.501

  ! 1 child sits far outside its parent's layout
      id 11 is 275.5 from parent 10 (topo None, radius 1.00) -- 276x, largest translate 270

      ^ 1 of those hang off a Cartesian parent with a translate over 45.
        If those numbers were meant as degrees, this parent's topology reads them
        as distances.
```

then reports scene extents, rendered half-extent per hierarchy level, how
crowded the roots are, and what a Global Scale change would do.

What it catches: children swallowed by their parent, children whose centre is
inside their parent, children flung far outside their parent's layout (with a
hint when the numbers look like degrees written into a Cartesian slot), glyphs
that will shear because they are rotated under a stretched parent, `color_a = 0`
nodes being used as carriers when they still draw and still take clicks, links
with an end that does not resolve, spokes that were aimed by hand and all came
out parallel, and anything whose proportions would change if a user switched on
View > Enforce Minimum Glyph Size.

## Which way does this glyph point?

The `AIM` section answers the one question a position check cannot. A set of
perfectly placed rods can still be aimed into a flat fan, and no amount of
checking coordinates will show it -- so the checker prints the world **+Z**,
which is the pointing axis of every directional geometry, for each one:

```
AIM
  parent 2 (Sphere (KML)) aims its 12 directional children -- all at the aim placement gave them
      id 3      +Z (+1.000, +0.000, +0.000)  Cylinder
      id 4      +Z (+0.866, +0.500, +0.000)  Cylinder
      id 5      +Z (+0.500, +0.866, +0.000)  Cylinder
```

Twelve unit vectors 30 degrees apart in the XY plane: those spokes point
outward, and you know it without rendering anything. **Read this instead of
reverse-engineering the rotation convention from test renders.**
`examples/Radial_Spokes/` is the known-good scene to calibrate against, with
its own report committed beside it as `aim_report.txt`.

Exactly one aim fault is reported, because only one has a signature that cannot
also be a deliberate design: a set of glyphs **rotated by hand under a Cartesian
parent that all ended up pointing the same way**, while their positions fan out
around it. That is the classic mistake -- right positions, wrong bodies. A glyph
merely rotated *off* the aim its parent gave it is stated in the `AIM` section
and never called a fault, because that is also exactly how a deliberate lean is
authored: `Armillary_World` lays its pins along their rings at `rotate_x = -90`
on purpose, and an inclined orrery tilts its planes on purpose.

`--base-scale B` evaluates at a different Global Scale. `--all` lists every
offending row instead of the first few.

It is also importable, which is usually what you want mid-build:

```python
import sys; sys.path.insert(0, "code")
from gv_extents import analyse, report

r = analyse("my_scene_gv_node.csv", base_scale=1.0)
print(len(r["buried"]), "children inside their parent")
print(report(r))
```

## Compute placement yourself

```python
import sys; sys.path.insert(0, "code")
from gv_kernel import load_node_csv, compute_world_transforms, Scene, node_world_matrix

nodes = load_node_csv("my_scene_gv_node.csv")
t = compute_world_transforms(nodes, base_scale=1.0)
xyz = t.world_pos[t.row_of_id[42]]              # node 42, in world space

scene = Scene(nodes, 1.0)                        # rendered size needs the draw matrix
m = node_world_matrix(nodes[0], scene)           # 4x4; columns carry the full scale chain
```

## Why this is vendored rather than rewritten

Because every previous attempt to re-derive this math by hand has drifted from
the app and produced confident wrong answers: a sphere's half-extent guessed at
0.5 when a sphere has radius 1, a cube assumed to reach its full scale when its
faces stop at 0.577, a rotation order that did not match what
GlyphViz composes, degrees written into a slot the parent reads as distance, a
"verified engine" transcribed from documentation whose numbers disagreed with
the screen. Those cost real sessions to find.

These files are copied verbatim from the GlyphViz repository, and a test there
(`tests/test_skill_kernel.py`) fails if they drift. So a number you compute here
is the number the app will draw. **Do not hand-edit the vendored copies, and do
not write a second implementation of this math anywhere.**

## What this does not do

It cannot see the render. It checks geometry, not meaning: it will not tell you
that your colour ramp is unreadable, that a glyph is ugly, or that two
components sit along the same line of sight from the default camera. For a
picture, use `tools/export_frame.py` from the GlyphViz repo, or ask the user for
one — see "Closing the loop" in `SKILL.md`.

Sizes come from each geometry's bounding volume, matched to its silhouette: a
box for cubes, grids, flat markers and rings, a cylinder for cones, tori, pins
and cylinders, an ellipsoid for everything else. Burial is only judged under
topologies where a child is meant to sit *on* its parent — a Rod parent threads
its children along its own axis, and the Z-variants place them at the centre on
purpose, so neither counts as buried.
