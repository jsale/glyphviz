# Mesh Creation Lab

Six GlyphViz scenes built from procedurally generated 3D models, and the small
toolkit that makes them. This is a **lab, not part of the official examples
collection** — nothing here is in the gallery, the per-example zips or
`GlyphViz_Examples.zip`. It exists to show what the mesh pipeline can do and to
exercise it.

| Scene | Triangles | What it is for |
|---|---|---|
| [`Tree/`](Tree/) | 6 files | Instancing — 16 trees, two meshes each |
| [`Building/`](Building/) | 216 | UV-textured facades: every window is a texel |
| [`City/`](City/) | 16 files | 74 buildings + 64 cars + 70 trees; textured and flat meshes together |
| [`Whale/`](Whale/) | ~2,200 | Smooth organic lofting from a lines plan |
| [`Jet/`](Jet/) | 2,716 | Six materials on one model; hard and smooth surfaces |
| [`Starship/`](Starship/) | ~21,500 | Procedural greebling; a dense mesh as a capacity check |

Open any scene's `*_gv_node.csv` in GlyphViz. The `meshes/` and `media/`
folders beside it load automatically.

Rebuild one with the glyphviz conda env's python:

```
<glyphviz-env>\python.exe mesh_creation_lab/Jet/build_jet.py
```

---

## The toolkit

Three modules, used only by the scenes here. They are authoring tools — none
of this ships with the application.

| Module | What it does |
|---|---|
| [`meshkit.py`](meshkit.py) | Procedural geometry: boxes, prisms, lofts, surfaces of revolution, swept tubes, parametric surfaces. Writes OBJ with texture coordinates. |
| [`texkit.py`](texkit.py) | Seamlessly tiling textures: facades, brick, asphalt, bark, hull plating, greebles, foliage, metal. |
| [`gvscene.py`](gvscene.py) | `SceneBuilder` — id allocation, the World row, and the `meshes/`/`media/` folder conventions, with a check that the folders match what the CSV claims. |

---

## Things that will bite you

Each of these cost real time while building these scenes. They are the reason
the toolkit exists rather than each generator improvising.

**Every mesh file is normalized on its own bounding box.** The importer
re-centres each file and scales it to radius 1, so the parts of one model
arrive in *different* coordinate systems and cannot simply be stacked at one
position. `Model.assembly()` returns the per-part offset and scale that undo
it, to be hung off one hidden "rig" node carrying the whole model's position,
rotation and size.

**A textured node's colour multiplies its texture.** Give a textured mesh a
near-white tint and let the image carry the hue. The first draft of the tree
scene used real bark and leaf colours and rendered a grove that was nearly
black.

**`type = 5` is an ordinary glyph.** `type = 0` is in `NON_VISUAL_TYPES`, so a
scene written with it loads, reports its node count, and renders *nothing*.
There is no named constant for 5 in `node.py`; `gvscene.NODE_TYPE_GLYPH` is it.

**A hidden node draws no label.** Text on a hidden rig node is silently
invisible, because the tag pass only labels nodes it draws.
`SceneBuilder.rig()` moves the label to the first visible child.

**Negating an angle is not a mirror.** Placing a left/right pair with
`rot_z(-90 * side)` *rotates* the left copy 180° about the vertical instead of
reflecting it, so anything fore-and-aft asymmetric points the wrong way — a
swept wing sweeps forward on one side, an aerofoil trails its round leading
edge. The jet and the whale both shipped with this before it was caught from a
top-down screenshot. Use `meshkit.mirror_pair()`, which places the +X side and
derives the other. It also reverses triangle winding, because a reflection
flips face normals.

**Scene extents are the opening shot.** `Viewport.set_nodes` auto-frames on
the bounding box, so an oversized ground or backdrop slab means the file opens
looking at a rectangle. The whale scene's slabs had to shrink from 150 to 62.

**Greeble size range matters more than greeble count.** At 5.5% of ship length
the boxes ate the starship's silhouette entirely; at 1.9% it reads as a
warship.

---

## Reference

[Imported Meshes](../glyphviz-docs/docs/reference/imported-meshes.md) documents
the pipeline itself: what the importer does to a model, how `mesh_id` resolves,
how textures and crease angles work, and the performance envelope.
