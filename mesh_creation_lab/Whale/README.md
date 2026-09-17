# Mesh Whale

A humpback pod, lofted from a lines plan.

Open `mesh_whale_gv_node.csv`.

## What it demonstrates

**Smooth shading — the other half of the crease rule.** The city example is
all hard edges; this one is the opposite case, and both come out of the same
importer with nothing switched. GlyphViz classifies each edge by its own
dihedral angle (40°, `mesh_loader.DEFAULT_CREASE_ANGLE`), so the body — a loft
whose neighbouring sections differ by a few degrees — shades as one continuous
surface, while a fluke's trailing edge stays a crisp line.

Before 2026-09-17 neither case worked properly: the importer averaged normals
across every welded vertex, so *every* model came out uniformly smoothed. This
whale would have looked roughly right by luck. The buildings would not have.

**Organic form from cross-sections.** The body is one loft over 34 stations,
each an ellipse whose width, height and centreline offset come from a table —
the way a boat's lines plan works. Flippers and flukes are lofted aerofoils
with real taper, sweep and twist, not deformed spheres or flat plates.

The proportions *are* the model: the first version of that table was twice as
wide as a real humpback and rendered a convincing balloon. Nothing about the
lofting was wrong.

**One mesh, many animals.** Five whales from one 4-part model, plus a calf at
40% rig scale beside its mother.

**Fog as water.** The underwater depth cue is the World row's fog fading
everything into the background colour. There is no other lighting trick in the
scene.

## Rebuilding it

```
<glyphviz-env>\python.exe mesh_creation_lab/Whale/build_whale.py
```

Edit the `LINES` table at the top to reshape the animal.
