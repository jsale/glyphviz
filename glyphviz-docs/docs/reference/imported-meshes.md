# Imported Meshes

GlyphViz can use an arbitrary triangle mesh as a glyph. Set a node's
**Geometry** to an imported mesh and it draws that model instead of a cube or
a sphere, scaled, coloured, textured, placed by topology, animated through
Channels and picked by the mouse exactly like every built-in shape.

Supported files: **OBJ, STL, PLY, glTF/GLB**.

---

## Getting a mesh into a scene

Three routes, all equivalent:

* **Meshes > Import Mesh File…** — loads one file and assigns it to the
  selection (or creates a node for it if nothing is selected).
* **Drag and drop** — drop an `.obj`/`.stl`/`.ply`/`.glb` onto the window.
* **A `meshes/` folder beside the node CSV** — loaded automatically when the
  scene opens. This is the one to use for a scene you intend to keep or share;
  see [Scene folders](#scene-folders-meshes-and-media) below.

Each imported mesh gets its own entry in the Geometry dropdowns —
`Mesh 1: hull`, `Mesh 2: greebles`, … — and picking one sets both `geometry`
(to 23, `GEO_MESH`) and `mesh_id`.

---

## What the importer does to your model

Three transformations, and it is worth knowing all three before you model
anything:

### 1. It is re-centred and normalized to radius 1

The model's own units do not survive; only its proportions do. Its origin
ends up at the centre of its **bounding box**, and it is scaled so its
furthest vertex sits at radius 1.

This is the same convention every built-in glyph follows, which is the point:
a mesh composes with `scale_x/y/z` identically to a cube. But it does mean a
building modelled with its feet at `z = 0` arrives with its feet *below* the
node position, and you have to put them back:

```
translate_z = (half the model's height in normalized units) x scale
```

`mesh_creation_lab/meshkit.py`'s `Mesh.placement()` computes this for you rather than
leaving you to estimate it.

### 2. Duplicate vertices are welded

Two vertices at the same position become one — unless they carry different
texture coordinates, which is exactly how a UV seam survives. Splitting
vertices in your exporter to force a hard edge therefore achieves nothing;
hard edges come from the crease angle instead.

### 3. Edges are classified by crease angle

Each face corner takes the average of only those neighbouring faces within
**40°** of its own (`mesh_loader.DEFAULT_CREASE_ANGLE`). So:

* a cube keeps six flat faces and square corners;
* a sphere or a lofted hull shades as one smooth surface;
* a cylinder gets a round barrel *and* hard cap rims, from the same rule, at
  the same shared vertices.

There is no smoothing-group data in an OBJ and none is needed.

A **texture seam is not a crease**. The two sides of a UV seam are separate
vertices — that is what a seam is — but creases are decided on position, so a
seam does not put a shading stripe down an otherwise smooth surface.

!!! note "This changed in 2026-09-17"
    Before that release the importer used per-vertex averaged normals, so
    **every** imported model came out uniformly smoothed — a cube shaded like
    a beach ball, and an STL of a machined part looked melted. If you imported
    hard-surface models before and were unhappy with them, re-import; nothing
    about the files needs to change.

---

## Colour, texture and materials

**A node paints its mesh in one flat colour.** A mesh file's own materials —
its `.mtl`, its embedded glTF textures, its per-vertex colours — are
deliberately ignored. In GlyphViz the appearance belongs to the *node*, so the
same model can be re-skinned per instance without touching the file.

### One colour per mesh means several meshes per model

A multi-coloured model is built as **one mesh per material**, assembled as
nodes. The jet in `mesh_creation_lab/Jet/` is six meshes — airframe,
radome, canopy, intakes, exhaust, stores — which is also what lets the canopy
be translucent (`color_a`) while the airframe beside it is opaque.

### Importing a model that already has materials

A model you download is usually one file carrying a dozen materials and their
textures. **Meshes › Import Model with Materials…** does that split for you:

* the model's `usemtl` groups become **one node per material**, each with its
  own mesh and its own `texture_id`;
* they hang off a **hidden rig node** carrying the model's position, rotation
  and size — move or scale the rig and the whole model follows;
* the parts are written into the scene's `meshes/` folder and each material's
  `map_Kd` image into `media/`, so the result reopens and ships like any
  other scene.

Ordinary **Import Mesh File…** is unchanged and still brings a model in as the
single shape it always did. The two answer different questions — *give me this
shape* versus *give me this model*.

Three things worth knowing:

* **Up axis.** Most tools export Y-up and GlyphViz is Z-up, so the rig is
  created with `rotate_x = 90`. If a model arrives lying on its side, that one
  field is what to change — no vertex is involved.
* **Each part is scaled, not resized.** A part's `scale_x/y/z` is its own
  extent within the whole model. Setting them all to 1 makes every part the
  same size — a cockpit as large as the hull around it.
* **Textures are found through the `.mtl`.** Parts whose material names no
  `map_Kd` arrive with a flat colour, and the status bar says how many.

!!! warning "When a model is drawn more than once"
    The same export habit that loses textures also tends to write the model
    out **several times over**. A Maya scene carrying both an object-level
    material and per-face-set materials exports *both* assignments, so the OBJ
    ships two or more fully overlapping copies of itself — each with its own
    vertex indices, so nothing in the file marks them as duplicates.

    On screen that is unmistakable once you know it: the surface **flickers
    between two textures in a dense rib pattern** (z-fighting), and the copy
    that covers the whole model hides the correctly-textured one under a
    single wrong image. Lift one part out of the way and a second, complete
    ship is sitting underneath.

    GlyphViz removes those on import — each distinct surface is kept once,
    from the material with the **fewest faces**, on the reasoning that a
    narrow assignment is the specific intent and the catch-all is the leftover.
    Anything a broad material covers *alone* it still keeps, so no geometry is
    lost. The count is always reported.

    The cargo ship this was found on shipped **87,128 triangles for 24,830 of
    actual surface** — 3.5 copies. Its catch-all material kept exactly the
    3,340 engine triangles no per-material assignment claimed. Pass
    `--keep-overlaps` to `tools/model_to_scene.py` to import a file as
    authored.

!!! warning "When an `.mtl` has lost its textures"
    V-Ray, Arnold and Redshift keep their shading in a node graph the `.mtl`
    format cannot express. Exporting to OBJ from such a scene routinely writes
    an `.mtl` with **no `map_Kd` at all and `Kd 0 0 0` on every material** —
    the model is fine, only the material file is lossy. GlyphViz treats an
    all-black `Kd` as "no colour given" and uses neutral grey, rather than
    importing a silhouette.

    To recover the real assignment you need a second source. The command-line
    `tools/model_to_scene.py` takes one:

    ```
    python tools/model_to_scene.py MODEL.obj --out SCENE_DIR \
        --textures "path/to/textures" --maya-scene MODEL_Scene.ma
    ```

    `--maya-scene` reads the Maya graph directly, which is authoritative;
    `--textures` alone falls back to matching material names against texture
    file names, which is a good guess and reported as one. Add `--dry-run` to
    see the match before anything is written.

### Textures

A mesh whose file carries **texture coordinates** can wear a `texture_id` from
the scene's `media/` folder, like any built-in geometry. Colour multiplies the
texture (`GL_MODULATE`), so:

!!! warning "Tint, do not colour"
    A textured node's `color_r/g/b` **multiplies** its texture. Give a
    textured mesh a near-white tint and let the image carry the hue. Setting
    the real material colour there multiplies brown by brown and renders the
    model nearly black.

A mesh with **no** texture coordinates stays untextured even if you set
`texture_id` — every vertex would otherwise sample the same single texel and
smear it over the whole model, which looks worse than the flat colour it
replaced. If your model should be textured and is not, the UVs are missing
from the file; re-export with them.

---

## Scene folders: `meshes/` and `media/`

When GlyphViz opens a node CSV it looks for two folders beside it:

```
My_Scene/
    my_scene_gv_node.csv
    my_scene_gv_tag.csv
    media/         <- texture_id = 1-based position, sorted by name
    meshes/        <- mesh_id    = 1-based position, sorted by name
```

Both ids are **positional**. `mesh_id = 3` means "the third mesh file in
`meshes/`, sorted alphanumerically" — which is what makes a mesh scene
reopenable and shippable, and also means:

Sorting is by file name and is **case-sensitive** (`Zebra.obj` before
`alpha.obj`), deliberately, so a folder yields the same ids on Windows, macOS
and Linux, and in GlyphViz Web. Note `media/` → `texture_id` predates this and
still sorts case-insensitively on Windows; the two differ only for folders that
mix cases.

!!! warning "Adding a file renames the ids after it"
    Drop `aardvark.obj` into a folder and everything that sorted after it
    shifts up by one. The scene still opens — wearing the wrong shapes. Name
    mesh files so their order is stable (a numeric prefix works well), or
    generate the scene and the folder together so they cannot disagree.

A file that fails to parse is skipped but **still consumes its id**, precisely
so one bad model does not shift every later one.

---

## Performance

An imported mesh compiles into a display list once and draws as a single call
per node, so triangle count costs you at import and at fill rate, not per
frame in Python. Practical guidance:

* A few thousand triangles per model is comfortable and instances freely.
* Tens of thousands is fine for a hero object. The starship example's greeble
  layer is ~19,000 and draws as one node.
* Import time is roughly linear and dominated by building the display list —
  100k triangles takes a moment, once.

**Back-face culling is disabled** while a mesh draws, because an imported file
cannot be trusted to wind its faces consistently. Both sides of every triangle
are therefore visible, which is usually what you want for an imported model
and does cost some fill rate on dense meshes.

---

## Authoring meshes from code

`mesh_creation_lab/meshkit.py` is a small procedural mesh library: boxes,
prisms, lofts, surfaces of revolution, swept tubes and parametric surfaces, all
writing OBJ with texture coordinates. `mesh_creation_lab/texkit.py` generates
matching tiling textures. Neither is part of the application — they are
authoring tools, and they encode the three importer facts above so you do not
have to rediscover them.

The `Model` / `Model.assembly()` pair handles the awkward part: because each
file is normalized on its **own** bounding box, parts of one model arrive in
different coordinate systems. `assembly()` returns the per-part offset and
scale that undo that, to be hung off one hidden "rig" node carrying the whole
model's position, rotation and size.

---

## The Mesh Creation Lab

Six scenes exercising all of the above live in `mesh_creation_lab/` — a lab in
the repository, deliberately **not** part of the shipped examples collection.
Its README also collects the authoring traps worth knowing before you generate
models from code.

| Scene | What it shows |
| --- | --- |
| `Tree/` | Two meshes per tree, instanced across a grove; texture vs. tint |
| `Building/` | UV-textured facades — every window is a texel; textured and untextured twins side by side |
| `City/` | 90 buildings and 60 vehicles from 16 files; world-scaled UVs; what non-uniform rig scale does to a texture |
| `Whale/` | Smooth organic lofting from a lines plan; the crease rule's other half |
| `Jet/` | Six materials on one model; hard and smooth surfaces together; building to an axis convention |
| `Starship/` | Procedural greebling; a dense mesh as a capacity check; fake emissive parts |

Each folder contains the generator script that produced it.

---

## See also

* [Geometries](geometries.md) — the built-in shapes, and `GEO_MESH`'s place among them
* [Drag and Drop](drag-and-drop.md) — what a dropped mesh file does
* [Point Cloud Import](point-cloud-import.md) — for scans rather than models
