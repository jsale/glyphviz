# Core Concepts

GlyphViz is built around one idea, and almost everything else follows from it: **data structure is scene structure.** A parent/child relationship in your data isn't drawn as a line connecting two shapes on a chart — it *is* spatial nesting in 3D. A hierarchy isn't a diagram of the data; it's the data, rendered as the space itself. This page is the mental model behind that idea: nodes, hierarchy, the topology/geometry split, tags, and channels — enough to read any GlyphViz scene and understand why it looks the way it does.

## Nodes — the atomic unit

Every visible thing in a GlyphViz scene is a **node**: one row in a CSV, one object in space. A node carries, at minimum:

- an **id** and a **parent_id** — its identity and its place in the hierarchy
- a **transform** — `translate_x/y/z`, `rotate_x/y/z`, `scale_x/y/z`
- a **geometry** — what shape it renders as
- a **topology** — how *its own children* get arranged (more below)
- a **color** (`color_r/g/b/a`) and a few display flags like `hide`

That's the whole vocabulary. There's no separate "chart type" to pick — a scatter plot, a network graph, a terrain surface, and an EEG replay are all just nodes with different topologies and different data driving their transforms. The full column-by-column spec, with load-time defaults for everything not listed above, is in the [ANTz Node CSV Format Spec](../reference/antz-format-spec.md); you rarely need more than about 20 columns to describe a scene.

Two special node types round things out: a **World** node (optional, type 0) holds scene-wide settings — background color, fog, tag-label color — rather than representing anything itself, and a **Camera** node (type 1) stores a named view. Neither is drawn or selectable; everything else you see is an ordinary glyph.

## Hierarchy is spatial, not organizational

`parent_id` is the only thing that defines the tree — id 0 means "this is a root." That part is familiar from any hierarchical data format. What's specific to GlyphViz is what that hierarchy *does*: a child's `translate_x/y/z` is interpreted **in its parent's local space**, so moving, rotating, or scaling a parent carries every descendant with it automatically, the same way moving a folder in a filesystem carries everything inside it — except here "inside it" means "physically attached to it in 3D."

In the GUI, this hierarchy is visible two ways: spatially, in the Viewer itself, and as data, in the **Node Table** — a flat, sortable spreadsheet with one row per node and a `Parent` column carrying the tree (it's a table, not an expandable tree widget; see [Node Panel](../reference/node-panel.md)). Selecting a node in one highlights it in the other.

## Topology vs. geometry — the distinction that unlocks everything

This is the one pair of terms worth sitting with, because they answer two completely different questions:

- **Geometry** answers *"what does this one node look like?"* — cube, sphere, cone, an imported mesh, a flat point marker.
- **Topology** answers *"how does this node arrange its children?"* — the coordinate system its children's `translate_x/y/z` get interpreted in.

They're independent. A node with **Sphere** topology and **Cube** geometry children renders as a sphere built out of cubes — the topology places each child on the parent's spherical surface (reading `translate_x/y/z` as longitude/latitude/altitude, KML-style), while each child's own geometry is a perfectly ordinary cube. Swap the topology to **Torus** and the exact same children rearrange onto a donut, no data changes required. Swap the geometry to **Sphere** instead and you get a sphere of spheres. This orthogonality is what lets one node model cover a scatter plot, a globe, a ring of hockey seasons, and a terrain surface — the topology *is* the chart type, chosen per-parent, and it composes: a topology's children can themselves be parents with their own, different topology, nested arbitrarily deep.

There are 18 topologies (Cube, Sphere, Torus, Cylinder, Spiral, a deformable Surface, line/GPS Plot, and more — full list and exact placement math: [Topologies](../reference/topologies.md)) and 27 geometries ([Geometries](../reference/geometries.md)), plus two link-specific ones for graph edges. Pick topology for "how should this group of children be laid out," and geometry for "what should each individual thing look like."

## Tags — labels and links, layered on top

A **tag** is a text label attached to a node — the node's data identity (position, shape, color) and its human-readable label are deliberately separate concerns. Tags come from either inline `text`/`link` columns on the node itself, or a companion tag CSV (`gv_tag.csv`, joined by id) when a scene needs the same tag data ANTz/GaiaViz tooling can also read. A tag's `link` can point at a URL, a local file, or launch another application — **U** or Alt+click opens it. Display settings — show/hide, per-node pinning, label color — live in the [Properties Panel](../reference/properties-panel.md).

## Channels — animation is data, not tweening

**Channels** replay a time series into node attributes: a `ch-map` file binds a channel id to a node + attribute pair (position, color, scale, visibility, and more), and a `ch-tracks` file holds that channel's literal value at every frame. Pressing play doesn't interpolate or simulate anything — it steps through recorded or generated values frame by frame, which is why Channels can equally well drive an EEG replay, a GPS hike, or a flipbook texture animation. See [Channels Animation](../reference/channels-animation.md) for the complete bindable-attribute list.

## Where this comes from: the ANTz lineage

GlyphViz extends [ANTz](https://github.com/openantz/antz)'s node/tag model rather than inventing a new one, and that lineage explains a few things that might otherwise look like arbitrary choices:

- ANTz's on-disk format is a strict 94-column CSV. GlyphViz still *writes* that full layout (via `save_node_csv`) so files stay readable by ANTz/GaiaViz tooling, but it only *requires* about 20 columns to *read* a scene — everything else has a sensible default. You will rarely hand-author more than the minimal set.
- Rotation has two valid interpretations, and GlyphViz supports both: ANTz's original Heading/Tilt/Roll convention (a Z-X-Z Euler sequence, the only one ANTz ever used) and a more intuitive per-axis Euler XYZ convention that GlyphViz adds for hand-posing objects. Files without a `rotation_mode` column load as Heading/Tilt/Roll for backward compatibility; new nodes created in GlyphViz default to Euler XYZ.
- Two Plot and Surface topologies exist with no ANTz/GaiaViz equivalent at all — GlyphViz's own extensions for line plots/GPS traces and deformable grids/terrain, built to match ANTz's *behavior* everywhere it's defined, and designed from first principles everywhere it isn't.

That's the whole model. Once nodes, hierarchy, topology/geometry, tags, and channels click, every example scene in the [Examples Gallery](../examples/index.md) is legible — it's the same five ideas, recombined.
