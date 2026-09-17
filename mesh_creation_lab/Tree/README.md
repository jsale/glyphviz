# Mesh Tree

A procedurally grown grove, built from **six OBJ files**.

Open `mesh_tree_gv_node.csv`. The `meshes/` and `media/` folders beside it load
automatically.

| What | Where |
|---|---|
| 16 trees | 3 species × (trunk mesh + canopy mesh) |
| Textures | Bark, two leaf sets, ground — all generated, all tiling |
| Ground | A built-in Cube glyph, not a mesh |

## What it demonstrates

**A node paints its mesh in one flat colour**, so a two-coloured tree is two
meshes and two nodes. That is the seam the whole mesh series is built around.

**A mesh is a shape, not an object.** Every tree in the grove is the same pair
of files at a different rig scale, rotation and tint. The specimen oak is the
grove's oak at twice the size; the winter willow is the willow's trunk mesh
with its canopy node simply left off.

**Texture carries the hue, the node colour only shades it.** A textured node's
`color_r/g/b` multiplies its texture, so the tints here are near-white. The
first draft of this scene used real bark and leaf colours and rendered a
grove that was almost black.

## Rebuilding it

```
<glyphviz-env>\python.exe mesh_creation_lab/Tree/build_tree.py
```

The growth is a recursive branching walk; branches are swept tubes along their
own curved paths (`meshkit.py`), and the canopy is a set of lobed blobs
at the branch tips rather than individual leaves. Change the seeds or the
`SPECIES` table at the bottom of the script to get a different wood.
