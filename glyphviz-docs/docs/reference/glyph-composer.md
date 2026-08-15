# Glyph Composer Reference

!!! note "Coming later"
    Glyph Composer reference documentation will be built out once Glyph Composer itself is further along in development. This page is a placeholder to reserve its place in the site structure.

## What this will cover

*(placeholder)*

- What Glyph Composer is and how it relates to GlyphViz
- Interface reference (if it has its own GUI)
- Workflow for composing/authoring glyphs for use in GlyphViz scenes
- Templates: saving and loading recipe `.json` files, including ones exported by the [Hyperglyph Generator](hyperglyph-generator.md)

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

Levels in a template `.json` carry the link settings as `link_geo` (null =
no links), `link_ratio`, `link_color_start` (null = inherit the node color)
and `link_color_end`. Templates written before link levels existed load with
links off and generate exactly what they always did. Link edges ride along
everywhere a composed glyph goes: **Insert into Scene**, **Use as Draw
Brush** stamps, and saved node CSVs.

## Next step

Return to the [Reference overview](index.md).
