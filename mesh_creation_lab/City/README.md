# Mesh City

A city block grid — streets, towers, traffic and street trees — from **16 mesh
files**.

Open `mesh_city_gv_node.csv`.

| What | Count | Files |
|---|---|---|
| Buildings | 74 | 6 massings × 2 parts |
| Vehicles | 64 | 1 |
| Street trees | ~70 | 2 |
| Street network | 1 node | 1 |

## What it demonstrates

**Instancing.** A GlyphViz scene pays for mesh *shapes*, not mesh *instances*.
Every building is one of six massings placed by a rig node carrying its
position, yaw and size; every car is the same 320-triangle mesh wearing a
different flat colour.

**Two material regimes side by side.** Buildings are UV-textured — windows are
texels, and one facade image serves a 5-storey block and a 36-storey tower at
the same window size. Cars are the opposite case: an untextured mesh where the
node's `color_r/g/b` *is* the paint.

**One mesh for the whole street network.** The roads never move
independently, so they are one mesh and one node — one draw call for every
carriageway on the map, with UVs running along each street so the dashed
centre line repeats down its length.

**What non-uniform rig scale does to a texture.** On its own apron west of the
city stand two copies of the same massing: one at uniform scale, one scaled
2× in z only. The second one's facade UVs stretch with it and every storey is
twice as tall. They are set apart from the skyline deliberately — dropped
among the other buildings the stretched one just looks like a mistake.

## Rebuilding it

```
<glyphviz-env>\python.exe mesh_creation_lab/City/build_city.py
```
