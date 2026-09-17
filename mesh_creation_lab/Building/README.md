# Mesh Building

One tower, modelled and textured from scratch — and the same tower with its
textures switched off, standing next to it.

Open `mesh_building_gv_node.csv`.

## What it demonstrates

**Texture coordinates on an imported mesh.** Every window in this scene is a
*texel*, not a triangle. The facade is a single 512×512 PNG mapped so one
texture tile is one storey by three window bays, and the whole 202 m tower —
podium, three setback blocks and crown — is 216 triangles.

Modelling those ~1,100 windows as geometry would have cost tens of thousands
of triangles to say something a 46 KB image says better. That is the argument
for textures on meshes in one sentence.

**World-scaled UVs.** `meshkit.prism(uv_world=True)` runs texture coordinates
past 1.0 in proportion to real size instead of normalising 0..1 across each
face. So the 4-storey podium and the 44-storey shaft share one image at the
same apparent window size, and a narrower setback gets *fewer bays*, not
squashed ones. It needs a seamlessly tiling texture, which `texkit.py`
generates by construction.

**Five meshes, because a node paints one colour.** Curtain wall, podium,
concrete core, entrance canopy and rooftop plant.

## Rebuilding it

```
<glyphviz-env>\python.exe mesh_creation_lab/Building/build_building.py
```
