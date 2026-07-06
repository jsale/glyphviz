# Geometries

The complete, exact list, read from `glyphviz_core/geometry_data.py:10-76` —
the single source shared by the GL renderer (`glyphviz_gl/geometry.py`) and
the Properties Panel's Geometry dropdown (`GEO_NAMES`, populated at
`main_window.py:528-531, 767-770`).

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
| 16 | Pin | `GEO_PIN` | |
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

`GEO_COUNT = 27` (`geometry_data.py:46`).

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
