# Geometries

The complete, exact list, read from `glyphviz_core/geometry_data.py` — the
single source shared by the GL renderer (`glyphviz_gl/geometry.py`) and the
Properties Panel's Geometry dropdown, which builds itself from `GEO_NAMES`.

## What geometry controls

Geometry is the shape assigned to an individual node — independent of
topology, which governs how a *parent* arranges its *children* in space. A
node's geometry answers "what does this one point in the hierarchy look
like," while [topology](topologies.md) answers "how are this node's children
laid out."

## The full list

IDs 0–22 are commented in source as matching ANTz's `kNPgeo*` enum
(`geometry_data.py:9`); IDs 23–26 are explicitly marked as GlyphViz-only
extensions with no ANTz/GaiaViz equivalent.

| ID | Name (`GEO_NAMES`) | Constant | Notes |
|---|---|---|---|
| 0 | Cube Wire | `GEO_CUBE_WIRE` | Wireframe; solid pair is `GEO_CUBE` |
| 1 | Cube | `GEO_CUBE` | |
| 2 | Sphere Wire | `GEO_SPHERE_WIRE` | Wireframe; solid pair is `GEO_SPHERE` |
| 3 | Sphere | `GEO_SPHERE` | |
| 4 | Cone Wire | `GEO_CONE_WIRE` | Wireframe; solid pair is `GEO_CONE` |
| 5 | Cone | `GEO_CONE` | |
| 6 | Torus Wire | `GEO_TORUS_WIRE` | Wireframe; solid pair is `GEO_TORUS` |
| 7 | Torus | `GEO_TORUS` | Shape driven by the node's `ratio` field (minor radius as a fraction of overall radius, default `TORUS_DEFAULT_RATIO = 0.14`) |
| 8 | Dodecahedron Wire | `GEO_DODECA_WIRE` | Wireframe; solid pair is `GEO_DODECA` |
| 9 | Dodecahedron | `GEO_DODECA` | |
| 10 | Octahedron Wire | `GEO_OCTA_WIRE` | Wireframe; solid pair is `GEO_OCTA` |
| 11 | Octahedron | `GEO_OCTA` | Default geometry for newly-created nodes (`main_window.py:531`) |
| 12 | Tetrahedron Wire | `GEO_TETRA_WIRE` | Wireframe; solid pair is `GEO_TETRA` |
| 13 | Tetrahedron | `GEO_TETRA` | |
| 14 | Icosahedron Wire | `GEO_ICOSA_WIRE` | Wireframe; solid pair is `GEO_ICOSA` |
| 15 | Icosahedron | `GEO_ICOSA` | |
| 16 | Pin | `GEO_PIN` | ANTz's "ice-cream cone": a 10:1 cone standing on its **apex at the node's own origin**, shaft rising along +Z, domed at the top. Unlike the other glyphs it is not centred on its origin — that placement is what lets Pin-topology children ride the shaft (see [Topologies](topologies.md)) |
| 17 | Pin Wire | `GEO_PIN_WIRE` | Wireframe pair — note the reversed solid/wire ID order vs. every other pair above |
| 18 | Cylinder Wire | `GEO_CYLINDER_WIRE` | Wireframe; solid pair is `GEO_CYLINDER` |
| 19 | Cylinder | `GEO_CYLINDER` | |
| 20 | Grid Wire | `GEO_GRID_WIRE` | Wireframe; solid pair is `GEO_GRID` |
| 21 | Grid | `GEO_GRID` | Flat square in the local XY plane, normal along +Z — matches ANTz's Grid node (topo=Plane, geometry=Square) |
| 22 | Point | `GEO_POINT` | Fixed-pixel-size `GL_POINTS` sprite; size driven by the node's `ratio` field |
| 23 | Mesh (Imported) | `GEO_MESH` | **GlyphViz extension** — arbitrary triangle mesh imported via `glyphviz_core/mesh_loader.py` (OBJ/STL/PLY/glTF), selected per-node by `Node.mesh_id` rather than a fixed shape. Each imported mesh gets its own entry in the geometry dropdowns ("Mesh 1: name", "Mesh 2: name", …); picking one sets both `geometry` and `mesh_id` |
| 24 | Circle | `GEO_CIRCLE` | **GlyphViz extension** — flat 2-D marker, world-space plate (like Grid), compiled to display lists for scatter-plot-scale performance |
| 25 | Cross | `GEO_CROSS` | **GlyphViz extension** — same idea as Circle |
| 26 | Star | `GEO_STAR` | **GlyphViz extension** — same idea as Circle |
| 27 | Line | `GEO_LINE` | **GlyphViz extension, Link nodes only** — the classic thin connector, and a Link's default. Width is `ratio × 20` px |
| 28 | Prism (Textured) | `GEO_LINE_PRISM` | **GlyphViz extension, Link nodes only** — a textured 4-sided tube between the two ends, scrollable via `rotate_rate_z` to show directed flow. `ratio` is its world-space half-width |
| 29 | Cube (Interior) | `GEO_CUBE_INTERIOR` | **GlyphViz extension** — see [Interior geometries](#interior-geometries-seen-from-within) below |
| 30 | Sphere (Interior) | `GEO_SPHERE_INTERIOR` | **GlyphViz extension** — a 360° / equirectangular image or video sphere |
| 31 | Cylinder (Interior) | `GEO_CYLINDER_INTERIOR` | **GlyphViz extension** — closed at both ends |
| 32 | Cylinder (Interior, Open) | `GEO_CYLINDER_INTERIOR_OPEN` | **GlyphViz extension** — an open tube; the same shape as 31 without its end caps |

`GEO_COUNT = 33` (`geometry_data.py`).

## Interior geometries (seen from within)

Ids 29–32 are the three shapes that enclose a volume, turned outside in: each
draws its **inside** surface, so you can fly the camera into it and see the
texture — a 360° video sphere, a cylindrical panorama, a video room. Set one
the way you set any other shape: the Geometry dropdown, the `O` key, the
`geometry` column of the CSV, or a Channels track.

An interior shape is **not** "back-face culling turned off", and the
difference is visible. Looking at the inside of an ordinary outward-mapped
surface is inherently a *mirror* view — a video would play backwards, text
and faces reversed. These shapes are built mirrored so that the image reads
**forwards** from within. They also stay single-sided: one fragment per
pixel, and alpha blending on a translucent node behaves exactly as it does
everywhere else.

Practical notes:

- **From outside** you see the *far* inner wall, like looking into a bowl —
  the near surface is culled away. The node stays visible in the scene and
  stays clickable; it just reads as a hollow shell until you go in.
- **They draw unlit**, so the image comes through at full brightness with no
  shading over it — exactly what the World Grid's globe does with a map, and
  what you want from a video. The node's own colour still tints an untextured
  interior shape; it simply isn't shaded.
- **End caps** are a property of the interior cylinder, and the two states are
  the two ids above. The Properties panel shows an **End caps** checkbox
  whenever a node is on one of them, and ticking it swaps the id — there is no
  separate field, so the choice travels with the CSV like any other geometry.
  Off gives an open tube (a panorama you look along, or a
  [link](#geometry-on-a-link-node) you fly through); on closes both ends and
  maps the texture over them too.
- **The interior cube's six faces** each carry the whole texture, upright and
  unmirrored for a viewer at the centre facing +Y. It is built face by face
  rather than by reflecting the ordinary cube, because a single reflection
  would leave the two faces perpendicular to the mirror axis reading
  backwards.
- **Scale** works as usual, so an interior sphere at `scale 57.3` with Global
  Scale 1.0 has a radius of 57.3 world units — fly inside and look around.
- These are ordinary geometries, so a **Link** carrying one renders it
  stretched between the two ends: an interior open cylinder on a link is a
  tube you can fly down.

## Geometry on a Link node

A **Link** (type=7) is an edge between two other nodes — its `parent_id` is
the A-end and its `child_id` the B-end — and its `geometry` picks how that
edge is drawn. **All of the following are selected by the `geometry` field
alone**, with no extra column, so a link's look travels with the CSV:

- **27 Line** and **28 Prism (Textured)** are the two line modes above.
- **22 Point** also draws as a plain line: a fixed-pixel sprite has no extent
  to stretch along an axis, so there is no glyph reading of it.
- **Every other ID renders that glyph stretched between the link's two ends.**
  This is ANTz's own link behavior, and it is what lets an edge become a
  cylinder rod, a tapering cone (whose apex points at the B-end — a natural
  arrowhead for directed graphs), a wireframe cage, an imported mesh, or an
  arbitrarily distorted version of any other shape.

Three rules govern a glyph link's transform:

| Property | How it is set |
|---|---|
| **Length** | The distance between the two endpoints. The glyph's own local Z extent is mapped onto the A→B segment, so it starts on A and ends on B exactly — including Pin, whose apex sits at its local origin rather than being centred |
| **Thickness** | `ratio`, applied to **both** cross-axes. One field controls thickness whatever geometry the link carries — the same field the Line and Prism modes already use for their width |
| **Orientation** | Derived entirely from the two endpoints. A link has no independent pose, so its own `translate`, `rotate`, and `scale` fields play no part. Roll is gravity-referenced, so a link does not spin about its own axis as it swings around |

Press **O** / **Shift+O** with a link selected to cycle it through every
geometry (Mesh and Point are skipped, as they are for ordinary nodes). A
selected glyph link draws the usual yellow selection box; a Line or Prism link
does not.

Two things worth knowing:

- On a **Torus** link, `ratio` does double duty — it is both the thickness and
  the torus's own minor-radius proportion. Values above 1.0 make a degenerate
  torus. The result at sane ratios is a hollow tube running along the edge.
- The **flat** geometries (Grid, Circle, Cross, Star) have no Z extent to
  stretch, so they render as a plate at the midpoint of the edge rather than
  spanning it.

Performance is left to you: a scene with thousands of solid glyph links draws
thousands of glyphs. Drop back to **Line** where the edge is not the point.

## Texture support

Setting a node's `texture_id` maps the image onto the solid geometries: Cube,
Sphere, Cone, Cylinder, Torus, Grid, Pin, the four Platonic solids, and the
flat markers Circle, Cross, and Star. Two geometries take no texture — the
11 **wireframe** variants (there is no surface to map onto), and **Point**,
whose fixed-pixel `GL_POINTS` sprite has no geometry to carry coordinates. In
both cases the node simply renders in its solid color; nothing errors.

The flat markers **crop** the image to their silhouette rather than stretching
it to fit, using the same image window the Grid uses across its square. A
Circle shows a circular crop of the picture, a Star a star-shaped one, and a
Cross the picture's central vertical and horizontal strips. Being flat, they
show their texture face-on and disappear to an edge when viewed side-on.

## Picking behavior

The 11 wireframe geometries render as outlines, but for click-picking
purposes each is mapped to its solid equivalent in a dedicated pick pass
(`WIRE_TO_SOLID`, `geometry_data.py:87-99`) — so clicking anywhere inside a
wireframe shape's silhouette registers a hit, not just clicks landing
precisely on a visible wire.

## Next step

See [Topologies](topologies.md) for how a parent node positions its children,
or [Properties Panel](properties-panel.md#selected-node) for where geometry
is set in the GUI.
