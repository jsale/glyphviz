# Links and edges — `type` = 7

Verified against `glyphviz_core/link_geometry.py`, `glyphviz_core/node.py`,
`glyphviz_gl/viewport.py`, `glyphviz_gl/main_window.py` (2026-08-15).

A **Link** is a node whose job is to connect two other nodes. It is the only
node type with no pose of its own: its position, rotation and scale are
ignored, and the two endpoints decide everything about how it draws. That makes
it the right tool for graph edges, molecular bonds, decay steps, callout
frusta, and tree limbs.

Since 2026-08-15 a link can carry **any geometry**, stretched between its two
ends — so an edge can be a rod, a cone arrowhead, a wire cage, or an imported
mesh, not just a line.

## The link row

Everything a link needs, as the app itself writes it:

| Field | Value |
|---|---|
| `type` | **7** |
| `parent_id` | the **A-end** node id (the edge starts here) |
| `child_id` | the **B-end** node id (extension column; the edge ends here) |
| `geometry` | how the edge draws — see the modes below. **27 (Line)** for a plain edge |
| `ratio` | thickness (default 0.1) — see "Thickness is `ratio`" |
| `color_r/g/b/a` | the edge's own color; nothing is inherited from either end |
| `translate_*`, `rotate_*` | **0** — a link has no pose |
| `scale_x/y/z` | **1** — unused, but keep them valid |
| `topo` | 0 — what the app writes; a link isn't used as a placement parent |
| `branch_level` | the A-end's level + 1 (what the app writes; it only drives select-by-level) |
| `hide` | honored — a hidden link doesn't draw |

Minimal example — two glyphs joined by a cylinder rod:

```csv
id,type,parent_id,branch_level,translate_x,translate_y,translate_z,rotate_x,rotate_y,rotate_z,scale_x,scale_y,scale_z,color_r,color_g,color_b,color_a,geometry,hide,topo,ratio,child_id
1,5,0,0,0,0,0,0,0,0,1,1,1,240,180,90,255,3,0,0,0.1,0
2,5,0,0,8,0,0,0,0,0,1,1,1,240,180,90,255,3,0,0,0.1,0
3,7,1,1,0,0,0,0,0,0,1,1,1,180,180,190,255,19,0,0,0.25,2
```

`child_id` is column 7 of the 94-column layout, so it is not an invented field
— it round-trips through GlyphViz, ANTz and GaiaViz alike.

**Both ends must resolve.** If `parent_id` or `child_id` is 0, missing, or
names an id that isn't in the file, the link draws **nothing** — silently. It
still occupies a row, so a node count that doesn't match what you see on screen
is usually a set of one-ended links.

## The three drawing modes

`geometry` alone chooses the mode; there is no extra column, so a link's look
travels with the CSV.

| `geometry` | Mode |
|---|---|
| **27 Line** | A thin GL line, `max(ratio × 20, 1)` **pixels** wide with round caps. Screen-space width — it never shrinks with distance. The cheapest edge by far. |
| **28 Prism** | A textured 4-sided tube. The one edge form that renders a `texture_id`, and `rotate_rate_z` scrolls that texture along the edge — directed-flow animation. |
| **22 Point** | Also draws as a plain line (a fixed-pixel sprite has no extent to stretch). Kept line-drawn so pre-existing point-link files render unchanged. |
| **any other id** | **The glyph, stretched between the two ends.** |

### Geometry links: exactly how the glyph is stretched

- **Length** — the glyph's local Z extent is mapped onto the A→B segment, so
  it starts on A and ends on B exactly, at any distance. Verified: with A =
  (1, 2, 3) and B = (4, −2, 9), a Cylinder link's local −Z end lands on A and
  its +Z end on B to floating-point exactness.
- **Thickness** — `ratio`, on **both** cross-axes. Every glyph is built at unit
  radius, so `ratio` **is** the edge's radius in world units (`ratio = 0.25`
  gives a rod 0.5 units across). It is *not* `scale_x/y/z`; those are inert.
- **Orientation** — entirely from the endpoints. The roll about the edge axis
  is gravity-referenced (the glyph's local X stays horizontal), so a textured
  or asymmetric glyph doesn't flip as the edge swings around.
- **+Z points at the B-end.** That's what makes a **Cone (5)** an arrowhead:
  its apex is its local +Z, so a cone link points at its B-end.
- **Pin (16/17)** stands on its apex, so a pin link puts its tip on A and its
  dome on B (its local span is 0…1.1, not −1…1, and the engine accounts for
  that).
- **Flat shapes have no Z extent** — Grid 20/21 and the markers 24/25/26 land
  as a plate at the **midpoint** of the edge rather than spanning it.
- **Torus (6/7)** is the one shape where `ratio` does double duty: it is also
  the torus's own minor-radius proportion, and above 1.0 that is degenerate.
- **Mesh (23)** works and still needs its own `mesh_id`.

## Recipes

**Plain graph.** `geometry` 27, one row per edge. Thousands of edges cost
almost nothing.

**Directed graph.** Two options: a **Cone (5)** link, whose apex lands on the
B-end, so the whole edge is the arrow; or a **Prism (28)** link with a
directional texture and `rotate_rate_z` set, so the flow animates. Cones read
as direction in a still image; prisms read as direction in motion.

**Weighted edges.** Put the weight in `ratio` — it is the thickness in both
modes (pixels for a line, world units for a glyph). Color the weight too if it
needs to survive at a distance.

**Molecular bonds / ball-and-stick.** Cylinder (19) links at a small `ratio`
between sphere glyphs. This is what GlyphViz's own PDB importer writes.

**Labelled edges.** Links take `text`, `link` and `show_text` like any other
node, and the label anchors to the **middle of the edge**. See
`tags-and-labels.md`.

**Limbs of a tree.** Joints are ordinary glyph nodes, limbs are links between
each joint and its parent — that split is what makes a branching structure read
as a tree instead of a chain of touching shells. Taper the limbs by writing a
smaller `ratio` per generation. The placement half of the recipe is
"Direction-relative branching" in `topologies.md`.

## Performance

A glyph link costs what a glyph costs — a scene of solid cylinder links draws
that many extra solid glyphs. On a graph with thousands of edges use 27 (Line)
unless the edge's shape is carrying meaning. This is deliberately left to the
author: capability first, and Line is always one field away.

## Gotchas

- **A link is stored as a child of its A-end** (`parent_id`), but it is not a
  hierarchy member in any meaningful sense — it has no depth, no placement, and
  is skipped by the child-slot arithmetic the app uses for new objects. Don't
  count links when reasoning about a parent's children.
- **`scale_x/y/z` do nothing.** Sizing a link means `ratio`.
- **A one-ended link is invisible, not an error.** Validate that every
  `child_id` resolves, exactly as you validate `parent_id`.
- **`texture_id` only renders on Prism 28 and on solid glyph links** — a
  textured Line link silently ignores it (`textures-and-media.md`).
- **A link between two nodes that move stays attached** — endpoints are read
  from world positions every frame, so rate animation and Channels playback
  both drag the edge along. That includes a link whose ends sit under different
  parents, or under different World Grids.

## Validation checklist

For every `type` = 7 row: `child_id` present and resolving to a real id;
`parent_id` resolving too; `ratio` > 0; `geometry` chosen deliberately (27 for
bulk graphs); `translate_*` and `rotate_*` zero; and `scale_*` = 1.
