# Glyph Composer

**Tools → Glyph Composer…** (**Ctrl+G**)

The Glyph Composer builds a *hyperglyph* — a small, deliberately designed
hierarchy of nodes — by describing it one **level** at a time, with a live
preview, and then drops it into your scene.

It is the hand-authoring counterpart to the
[Hyperglyph Generator](hyperglyph-generator.md), which rolls whole designs at
random. Both write the same template `.json`, so a generated design can be
opened here and edited level by level.

## The model: one spec per level

A recipe is a list of **levels**, not a list of nodes. Level 0 is the Root;
every level after it describes *the children of the level above*, and that one
description is applied to every parent at that depth.

So a recipe with `Root ×1 → Level 1 ×6 → Level 2 ×4` produces 1 + 6 + 24 = 31
nodes from three short descriptions. Node count grows as the running product of
the counts, which is worth watching: three levels of ×10 is 1,110 nodes.

This is also the feature's main limitation. Because a level carries one
specification, siblings at a given depth are identical apart from their position
and their place in the color gradient. Per-branch variation isn't expressible.

## Layout

- **Left** — the Branch Levels list, with **+ Add Level** and **− Remove**.
  Each row shows its count, geometry, and a `⌁` mark if the level has links.
- **Right** — the parameter form for the selected level.
- **Bottom** — a live preview viewport.
- **Footer** — template name, Save/Load, preview controls, and the two ways out
  (Insert into Scene, Use as Draw Brush).

## Per-level parameters

### Basic

| Field | What it does |
| --- | --- |
| **Count** | How many nodes at this level, *per parent*. |
| **Geometry** | The glyph shape ([Geometries](geometries.md)). |
| **Topology (child layout)** | The topology of **this** node — it decides how the *next* level's children are arranged around it ([Topologies](topologies.md)). |
| **Ratio** | Topology-specific size: a torus's tube thickness, and similar. |
| **Topo Scale** | The size of the coordinate system this node places its children in — see below. |

### Topo Scale and Auto

[Topology Scale](topologies.md) multiplies only the translate axes a topology
reads as a **distance**, never the angular ones — so no value can distort a
circular layout.

It matters here because the Composer describes child placement in one
vocabulary: an **Angular** level always hands its children `translate_x` = 0–360.
Under a Sphere, Torus or Cylinder parent that is a full revolution. Under a
Cube, Pin, Plane or None parent it is 360 *world units*, which throws the
children hundreds of parent-radii away, off screen and with no clue where they
went.

**Auto** (on by default) resolves this: it picks the ANTz convention (1/180)
exactly when a 0–360 sweep is about to be read as a distance, and 1:1 otherwise.
The note under the checkbox tells you which is in force.

Touching the value, the slider, or either preset takes the level off Auto — the
control you reached for *is* the decision, so you don't have to find the
checkbox first. Re-check Auto to re-fit.

!!! note "Older templates"
    A template saved before Topo Scale existed carries no value and loads onto
    Auto. That is what repairs the ones whose children were flying off — such a
    template regenerates as the corrected design rather than the smeared one.

### Placement

The Root and the deeper levels offer different distributions, because a root has
no parent to be arranged around.

**Root** placement modes:

| Mode | Parameters |
| --- | --- |
| Linear (along axis) | Step, Axis (X/Y/Z) |
| Circular (world ring) | Radius |
| Grid (world XY) | Columns, Spacing X, Spacing Y |
| Random | Bounds (±) |

**Child level** placement modes:

| Mode | Parameters |
| --- | --- |
| **Angular (ring around parent)** | **Tilt / Latitude Y** — the children's `translate_y`, read as latitude or tilt depending on the parent's topology. **Altitude Offset Z** — their `translate_z`, the altitude or radial offset off the parent's surface. |
| Linear (along axis) | Step, Axis |

Angular spaces the children evenly through the parent topology's angular
coordinate, which is what produces rings, shells and spirals.

### Transform

Scale X/Y/Z and Rotate X/Y/Z, applied to every node at the level, plus a **Lock
X/Y/Z** checkbox that keeps the three scales equal. The lock persists as you
switch levels.

Scale here is a **local** multiplier relative to the parent level. GlyphViz's
renderer composes each level's scale with its parent's already-cascaded scale,
so depth compounds once, at draw time — you do not need to pre-shrink each level
yourself.

### Color

A **Color** for the level, and an optional **gradient** to a second color spread
across the siblings at that level.

## Link to Parent (link levels)

Every level after the Root has a checkable **Link to Parent** group. Turning it
on gives each node at that level a companion **Link** (type = 7) edge back to
its parent, rendered as the chosen geometry stretched between the two — the
same any-geometry links the viewer draws (see
[Geometry on a Link node](geometries.md#geometry-on-a-link-node)).

- **Geometry** — any glyph shape (Cylinder is the default), or the two classic
  line modes (Line, Prism). Mesh and Point are not offered.
- **Thickness** — the link's `ratio`: its width on both cross-axes, in world
  units.
- **Use node color** (default) — each link takes its child node's own
  gradient-resolved color. Uncheck it to give the level's links an independent
  color (with an optional sibling gradient) — e.g. wood-brown limbs under
  brightly colored canopy spheres.

For the links to be visible, the level needs a gap to span: give it some
**Altitude Offset Z** in its Angular placement so children lift off their
parent's surface. Parent and child then read as joints, and the links as the
limbs between them — which is what turns a composed glyph into a jointed,
branching structure (strings of pearls, trees with true branches,
ball-and-stick molecules).

A level with links contributes **two** nodes per child, so it doubles that
level's share of the node count.

## The preview

**Auto-preview** rebuilds the glyph 350 ms after every edit. **Preview Now**
forces a rebuild — pair it with Auto-preview off when a design gets large enough
that the rebuild is noticeable.

The preview camera **stays where you put it**. Composing is an edit-and-look
loop, and being yanked back to a distant overview every keystroke makes close-up
work impossible, so re-framing is explicit:

- **Reset View** (on the Preview header) re-frames on the whole glyph.
- Loading a template re-frames, since it is a different glyph entirely.
- The very first preview frames itself.

## Getting the glyph out

| Button | Result |
| --- | --- |
| **Insert into Scene** | Adds the generated nodes to the live scene. With a node selected, the glyph is inserted **as its child**; with nothing selected, at the scene root. |
| **Use as Draw Brush** | Registers a **snapshot** of the template as the Draw Mode stamp and switches Draw Mode on — click or drag in the viewer to paint copies. Because it is a snapshot, further edits here don't change what an in-progress drawing stamps; press the button again to register the edited version. |
| **Save Template…** | Writes the recipe as a `.json`. |
| **Load Template…** | Opens one. |

Saving *scene* data is unchanged: once a glyph is inserted, File → Save writes
node CSVs like any other content.

## Templates

A template is a small `.json` holding the level list — a few hundred bytes
whatever the tree expands to. Templates come from three places:

- **Save Template…** here.
- **Save Recipe…** in the [Hyperglyph Generator](hyperglyph-generator.md).
- **Download .json** from the [Hyperglyph Tree Designer](tree-designer.md).

Levels carry their link settings as `link_geo` (null = no links), `link_ratio`,
`link_color_start` (null = inherit the node color) and `link_color_end`, and
their scale fit as `topo_scale` / `topo_scale_auto`. Templates written before
either feature existed load with links off and Topo Scale on Auto.

!!! warning "Large designs are awkward to edit here"
    Above roughly **2,000 nodes** the Composer starts to feel sluggish, because
    Auto-preview regenerates and re-bakes the entire tree after every edit. The
    file is small and the glyph renders fine in a scene — it is editing that
    gets heavy. Turn off Auto-preview and use Preview Now, or lower the
    per-level counts.

## Next step

Return to the [Reference overview](index.md), or see the
[Hyperglyph Generator](hyperglyph-generator.md) for the procedural way to arrive
at a design worth editing here.
