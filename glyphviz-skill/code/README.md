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
with an end that does not resolve, and anything whose proportions would change
if a user switched on View > Enforce Minimum Glyph Size.

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
