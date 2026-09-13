---
name: glyphviz
description: Generate and validate CSV scene files for GlyphViz, a 3D hierarchical data visualization app. Creates gv_node.csv (and optional gv_tag.csv / Channels animation files) with correct columns, topologies, hierarchy, links, colors, and labels. Use when users want to visualize data in GlyphViz, build glyph hierarchies or hyperglyphs, graphs/networks or branching structures, bar charts or scatter plots, convert data to GlyphViz format, or debug why a GlyphViz CSV doesn't load or render as expected. Also use when a scene loads but looks wrong — parts buried inside each other, children flung far out or collapsed to the centre, bars that sink below the baseline, glyphs that distort or fly apart when scaled, or components hidden behind their siblings.
---

# GlyphViz CSV Generation Skill

GlyphViz renders hierarchical data as interactive 3D scenes: each CSV row is a
**node** (a 3D glyph); `parent_id` links rows into trees; a parent's **topology**
(`topo`) decides how its children are arranged around it (on a sphere surface,
around a torus ring, stacked on a pin, along a plot line, …).

GlyphViz descends from the ANTz/GaiaViz format family but has its own native
conventions. **Do not apply GaiaViz lore to GlyphViz** — several well-known
GaiaViz rules are wrong here (see "GaiaViz myths" below).

## The one required file: `gv_node.csv`

A header row plus one row per node. Only **20 columns are required**:

```
id,type,parent_id,branch_level,translate_x,translate_y,translate_z,
rotate_x,rotate_y,rotate_z,scale_x,scale_y,scale_z,
color_r,color_g,color_b,color_a,geometry,hide,topo
```

Everything else is optional with sensible defaults — see
`references/node-csv-format.md` for the full column-by-column spec. This
minimal dialect is also what GlyphViz itself saves; the canonical 94-column
ANTz-compatible layout is an opt-in interop format, not what you will get back
out of the app.
**No infrastructure rows are required**: no camera rows, no grid row. A single
optional `type=0` World row sets the background color via `color_r/g/b/a`.

Minimal working scene (a torus parent with three orbiting children):

```csv
id,type,parent_id,branch_level,translate_x,translate_y,translate_z,rotate_x,rotate_y,rotate_z,scale_x,scale_y,scale_z,color_r,color_g,color_b,color_a,geometry,hide,topo,ratio
1,5,0,0,0,0,0,0,0,0,1,1,1,242,121,61,255,7,0,3,0.15
2,5,1,1,0,0,0,0,0,0,0.4,0.4,0.4,230,230,230,255,3,0,0,0.1
3,5,1,1,120,0,0,0,0,0,0.4,0.4,0.4,230,230,230,255,3,0,0,0.1
4,5,1,1,240,0,0,0,0,0,0.4,0.4,0.4,230,230,230,255,3,0,0,0.1
```

## Hard rules (each verified against `glyphviz_core`)
1. `id` unique, ≥ 1. `parent_id = 0` means root. `branch_level`: roots are
   **0**, children 1, etc.

2. **Every geometry is centred on its own origin and fits inside radius 1** —
   which is *not* the same as spanning −1…+1 on each axis. A cube's eight
   corners sit on that sphere, so its faces are only **0.577** out; a Pin is a
   needle **0.1** wide; a flat square reaches **0.707**. So `scale_z = 4` is not
   a bar four units tall standing on its position — on a cube it is 4.6 tall
   with half of it *below*, and on a Pin it is 4.4 tall standing on its
   position. Measured from the app's own geometry builders:

   | geometry | x, y half-extent | z |
   |---|---|---|
   | Sphere, Cone, Cylinder, Octahedron (and their interiors) | 1 | −1…+1 |
   | Cube, Cube Interior | 0.577 | ±0.577 |
   | Icosahedron | 0.851 | ±0.851 |
   | Dodecahedron | 0.934 | ±0.934 |
   | Tetrahedron | 0.943 / 0.816 | −0.333…+1 |
   | **Pin (16/17)** — a needle standing *on* its origin | **0.1** | **0…1.1** |
   | Square / "Grid" (20/21) | 0.707 | flat |
   | Circle, Cross, Star (24–26) | 1 | flat |
   | Torus, Flat Ring | 1 | ±`ratio` |

   A node's **rendered half-extent** is that number × its own `scale` × every
   ancestor's scale × Global Scale, and its bottom edge is `translate_z −
   rendered half-extent`. Nothing in the CSV records rendered size, so compute
   it: `code/gv_extents.py` prints it per node and per level, and
   `gv_extents.local_box(geometry, ratio)` returns the table above. Most "the
   parts are buried in each other" bugs are this rule; most "my bar is the
   wrong height" bugs are the 0.577.

3. **Know where a child lands before you place it.** `translate` is read in the
   parent's topology (rule 10), and every topology puts its own surface at a
   different number. Under a parent of scale S, measured:

   | Parent `topo` | Child `translate` | Child **centre** lands at |
   |---|---|---|
   | None (0), Plane (8), Video, Plot, Surface, Point Cloud | `(1, 0, 0)` | `1·S` — Cartesian, so translate magnitude 1 is the surface |
   | Sphere (2) | `(lon, lat, 0)` | `1·S` — `translate_z` then adds altitude above it |
   | Point (7) | `(lon, lat, 1)` | `1·S` — `translate_z` is the **full reach**; 0 is the centre |
   | Torus (3) | `(0, 0, 0)` | `1·S` — the tube's outer equator |
   | Cylinder (4) | `(0, 0, 0)` | `1·S` — the wall |
   | Cube (1) | `(0, 0, 0)` | `1·S` — centred on the facet |
   | Pin (5) | `(h, 0, 0)` | `(1 + h)·S` — stacks up the axis from the parent's top |
   | Rod (6) | `(180, 0, 0)` | `10·S` — 0…180 spans the rod, which itself draws 0.25 wide and 5.0 long per unit of its own scale |
   | Zcube, Zsphere, Zcylinder, Zrod | `(0, 0, 0)` | `0` — pulled to the centre or axis |
   | Ztorus (11) | `(0, 0, 0)` | `(1 − ratio)·S` — the tube's centreline, **not** the centre |

   Every one of those numbers is `1 · S` because **placement uses radius 1
   whatever geometry the parent wears** — the topology seats children on the
   parent's circumscribed sphere, not on its drawn skin. The two only coincide
   when the geometry reaches radius 1 in that direction (rule 2). Measured: a
   scale-2 cube with `topo = Cube` seats a child at 2.000, while its drawn face
   is at 1.155 — so the child floats 0.845 above it, and that gap is a feature
   of the format, not a bug in your file. It scales with the parent, so a
   **Pin, Cube, Icosahedron or flat-square parent always looks like its children
   are hovering**; either accept it, or pull the child in with a negative
   `translate_z` (or a shorter Cartesian translate) sized from the table.

   A child placed *at* the surface is half buried, because the child has its own
   half-extent (rule 2). **To clear it, add the child's own rendered radius plus a
   gap, expressed in the parent's units.** Under a Cartesian parent that is
   `translate magnitude = 1 + (child_radius + gap) / parent_scale`.

4. **Resize a hyperglyph by scaling the ROOT and nothing else.** Every
   descendant's size *and* its seating distance ride the same chain, so proportions
   hold exactly: measured, taking a root from scale 1 to scale 3 moves a grandchild
   from 1.95 to 5.85 and grows its half-extent from 0.090 to 0.270 — the same
   factor. Two corollaries. **Author a constant per-level factor** and let
   inheritance compound it once: writing 0.6, 0.36, 0.216 down three levels
   *thinking those are final sizes* renders 0.6, 0.216 and 0.047, because the
   engine multiplies them together. And **a non-uniform ancestor shears any rotated
   descendant** — a cube at `rotate_x = 45` under a `(0.2, 0.2, 3)` rod comes out
   skewed, its basis axes 8° apart instead of 90°, while a spin about that rod's
   own long axis stays clean. Anything that must tumble freely belongs on a
   uniformly-scaled carrier (rule 13).

5. **A length that carries data belongs in position space, not scale space.**
   Write the value into `scale_z` and the glyph grows *both* ways from its position
   (rule 2), so the bar sinks below its baseline; and because Global Scale
   multiplies rendered size but not a root's coordinates (rule 7), the base moves
   again whenever the viewer changes it. For a bar of height H rooted at z = 0,
   measured at Global Scale 1 and 3:

   | Recipe | at B = 1 | at B = 3 |
   |---|---|---|
   | **D** — a **Link** from a hidden base node at 0 to a hidden tip node at H, `geometry` = Cylinder, `ratio` = thickness | 0…H | **0…H, fully invariant** |
   | **C** — a **Pin** at `scale_z = H/1.1` | 0…H | 0…3H — base holds, height scales |
   | **B** — a cube at `scale_z = H/1.155`, lifted to `translate_z = H/2` | 0…H | −H…2H — **the base sinks** |
   | **A** — plain `scale_z = H` on a cube | −0.58H…0.58H | −1.73H…1.73H |

   Note what A costs: not only is half the bar underground, the visible half is
   **0.58H, not H** — a cube reaches 0.577 of its scale (rule 2), so the naive
   recipe encodes the wrong number as well as drawing it in the wrong place.
   B and C divide that geometry factor back out; D never introduces it.

   Prefer **D**: the value is literally a coordinate you can read back, and nothing
   the viewer does moves either end. This generalises well past bar charts — it is
   the answer whenever a part's length, not its size, is the measurement. See
   `references/links-and-edges.md`, and `examples/Rooted_Bars/` for all four
   drawn side by side over the same data.

6. **The minimum-glyph-size clamp is OFF by default — do not design around it.**
   `Scene.scale_floor` is `0.0` unless the user ticks View → Enforce Minimum Glyph
   Size. When it *is* on, it lifts each node's **own** `scale × Global Scale` to
   0.2 per axis and **ignores every ancestor**, which has one consequence worth
   stating plainly: **it breaks counter-scaled children.** A bead authored
   `(5.0, 5.0, 0.073)` so that it renders round on a thin tall parent measures
   0.500 / 0.500 / 0.500 with the clamp off, and 0.500 / 0.500 / 1.378 — a 2.8 : 1
   ellipsoid — with it on. So keep the **rendered** size of a visible glyph at
   roughly 0.2 or more, both so the scene reads the same either way and because a
   smaller glyph is hard to click. But a small *authored* number under a large
   parent is **not** an error: that is exactly what counter-scaling is, and it is
   the right technique when a part must stay round under a deliberately stretched
   parent.

7. **Author against Global Scale = 1.0**, and put any given distance in only
   one place. The viewer applies a base scale **B** that the CSV does *not*
   record (Properties → Global Scale, default **1.0**). B multiplies two
   things: every glyph's rendered size (`scale_x/y/z × B`), and the placement
   radius of a child on a **surface-riding** topology — a Sphere/Torus/
   Cylinder/Cube parent seats its children at `B × parent scale`, plus the
   child's own `translate_z` on top. B does **not** move Cartesian children
   (None, Plane), root nodes, or World Grid children: those are literal
   coordinates. The trap is mixing the two idioms in one scene — a ring whose
   radius comes from its parent's `scale` tracks B, while a marker pushed out
   by its own `translate_z` does not, so the two line up at one setting and
   drift apart at another. Measured: a Sphere child at `translate_z = 5` sits
   6.0 units out at B = 1 and 8.0 at B = 3, while its sibling on the surface
   goes 1.0 → 3.0. See `references/topologies.md`.

8. Colors are ints 0–255 (all four of r/g/b/a).

9. Save with **`encoding="utf-8"`** and CRLF line endings
   (`lineterminator='\r\n'`); sanitize control characters out of any label
   text — one bad byte can silently kill all tags.

10. `translate_x/y/z` are coordinates **in the parent's topology system**, not
    world units: lon/lat/alt under a Sphere parent, orbital-angle/tube-angle/
    elevation under a Torus parent, Cartesian under None/Plane.

11. The parent's optional **`topo_scale`** (default **1.0**) says how far one
    unit of a child's `translate` reaches, on exactly the axes that parent's
    topology reads as a **distance** rather than an angle. Angular axes
    (longitude, latitude, orbital/tube angle) are never scaled, so no value of
    it can distort a circular layout. Leave it at 1.0 for Cartesian-authored
    scenes; set **1/180 ≈ 0.005556** (the ANTz convention: a linear axis spans
    the parent's own extent) when you author a layout **in degrees** and want it
    to survive a switch between an angular and a linear topology — without it,
    0…360 on a Cube face is 360 *world units* and children fly out of sight.
    See `references/topologies.md`.

12. **Aiming a glyph is the topology's job, not `rotate_*`'s.** Under a Sphere
    (2), Point (7), Torus (3), Ztorus (11) or Cube (1) parent the engine already
    orients every child from its own coordinates: it applies a base rotation
    that puts the child's local **+Z** along the outward direction there
    (surface normal, or face normal on a Cube). And **+Z is the pointing axis of
    every directional geometry** — Cylinder (18/19), Cone (4/5) and Pin (16/17)
    are elongated along it; the flat shapes (20/21 Grid, 24/25/26
    Circle/Cross/Star) face along it. Put those together: a Cylinder child of a
    Sphere parent with **all three rotate fields 0** is a spoke pointing
    straight out, and the direction you want is its `translate_x` (longitude),
    *not* a rotation. Use `rotate_x/y/z` only to pose a glyph **relative to**
    that frame (a twist, a deliberate lean) — never to aim one the topology
    already aims. Hand-posed rotations compose *on top of* the base rotation, so
    fighting it is what turns an intended starburst into a flat stacked fan.
    If you do hand-pose, add a `rotation_mode` column and write **0** (Euler
    XYZ — each field spins its own axis); a file *without* the column loads in
    ANTz Heading/Tilt/Roll mode (Z-X-Z). If all rotations are 0, omit the
    column. Per-topology aim table, geometry axes, and the spokes recipe:
    `references/topologies.md`. **Known-good scene, with every rod's measured
    +Z committed beside it: `examples/Radial_Spokes/`** — calibrate against it
    rather than probing with renders. `code/gv_extents.py` prints the same
    numbers for your own scene, under `AIM`.

13. **Carriers and shields.** For a structural node that positions things without
    drawing — a joint, a uniform frame, a pivot — use **`hide = 1` at uniform
    scale 1**. Both the render pass and the pick pass skip it, and its children are
    unaffected: a hidden parent still places its child at exactly the same world
    position. Three things that look like carriers and are not. **`color_a = 0`**
    still draws and still *picks*, so it silently steals clicks from whatever is
    behind it. **`scale = 0.001`** does not hide a node, it shrinks its entire
    subtree by a thousand. And a **tall anisotropic rod** shears whatever hangs on
    it (rule 4). Separately, a **wireframe hull is a click shield** — the pick pass
    maps every wire id to its solid counterpart, so a wire sphere blocks selection
    of everything inside it. To outline a container the user can reach through, draw
    it from Plot-topology (16) line children instead. **Plot and Surface vertices
    are the exception to all of this:** the line or mesh is drawn from them,
    including their alpha, so `hide = 1` removes a vertex from it and `color_a = 0`
    makes that part of it invisible. Author vertices at **scale 0** (solid
    geometry) — a zero-size glyph is skipped, the overlay still draws — and keep a
    textured Surface hub at `color_a = 255`.

14. Labels default to **selected-only**: a fresh scene draws the label of whatever
    the user selects and nothing else. `T` toggles labels off and on; unchecking
    "Show Tag Labels of Selected" labels every tagged node at once, capped at 500
    tags per frame. Prefer inline `text` (label) and `link` (URL/file for the U key)
    columns — GlyphViz-native and simpler than a tag file. Use a companion
    `gv_tag.csv` only for ANTz/GaiaViz compatibility (`table_id` must be 0 there).
    Set `show_text = 1` on the handful of nodes whose label should always be
    visible. **Label every node with what it is and what value it carries** — a
    scene the user can interrogate by clicking is worth far more than one they have
    to decode. Full rules: `references/tags-and-labels.md`.

15. Node types: 5 = ordinary glyph; 0 = World (scene settings, never drawn);
    1 = Camera; 6 = World Grid (children attach explicitly via
    `parent_id = grid.id`, place by lon/lat); 7 = Link (edge `parent_id` →
    `child_id`).

16. A **Link** has no pose — its `translate`/`rotate`/`scale` are ignored and
    both endpoints must resolve or it draws nothing. Its `geometry` picks how
    the edge looks: 27 (Line) for bulk graphs, 28 (Prism) for animated flow,
    or **any solid/wire glyph id, which renders that shape stretched from A to
    B** (a Cone points its apex at the B-end — an arrowhead). Thickness is
    `ratio`, never `scale_*`. See `references/links-and-edges.md`.

## GaiaViz myths that do NOT apply to GlyphViz

- ~~"Files must have exactly 94 columns"~~ — 20 required; the rest default.
- ~~"The first 6 infrastructure rows are mandatory"~~ — none are.
- ~~"line_width must be > 0 or nodes won't display"~~ — `line_width` and
  `point_size` are round-trip-only in GlyphViz (Point size comes from `ratio`).
- ~~"size must be 420"~~ — round-trip-only (the saver defaults it to 420).
- ~~"branch_level starts at 1 for roots"~~ — GlyphViz roots are level 0.
- ~~"np_ prefixes"~~ — never author `np_` files; that dialect is read-side
  interop for genuine GaiaViz data only.

## Placement myths — these are WRONG, and they are in circulation

Every one of these has been stated confidently in a real GlyphViz session, and
several have been written down as numbered rules inside skills built on top of
this one. If you are carrying any of them from another document, that document
is out of date. The bracketed number is the rule above with the correct answer.

- ~~"The renderer floors every glyph at 0.2, so authored scale must stay above
  it"~~ — the clamp is **off by default**, and when it is on it lifts a node's
  *own* scale only, so it *destroys* a counter-scaled child rather than
  protecting it. [rule 6]
- ~~"A sphere's native half-extent is 0.5"~~ — every geometry fits inside
  radius 1, so a sphere has radius 1 at scale 1. [rule 2]
- ~~"Every geometry spans −1…+1 per axis"~~ — they fit inside *radius* 1, which
  is not the same thing. A cube's faces are at 0.577, a Pin is 0.1 wide, a flat
  square 0.707. This one was in an earlier version of this file, and it makes
  every bar built on a cube 15% too tall and every Pin ten times too thin.
  [rule 2]
- ~~"A child seated on a cube parent touches the cube"~~ — placement uses the
  parent's circumscribed sphere whatever geometry it wears, so a child on a
  cube facet floats 0.42 × parent scale above the drawn face. [rule 3]
- ~~"A child's surface is at translate magnitude 1 under any parent"~~ — true
  only under **Cartesian** parents. Under Sphere the surface is
  `translate_z = 0`, under Point it is 1, under Torus/Cylinder/Cube it is 0.
  [rule 3]
- ~~"The root must stay at scale 1 or the subtree gets crushed"~~ — any root
  scale scales the subtree exactly proportionally. A `scale = 0.001` "invisible
  carrier" crushes its children because 0.001 is the scale it asked for.
  [rules 4, 13]
- ~~"The World row's `scale_x/y/z` is Global Scale"~~ — Global Scale is a viewer
  setting that the CSV never records. [rule 7]
- ~~"Rotations compose as Rz·Ry·Rx"~~ — a file with no `rotation_mode` column
  loads in ANTz Heading/Tilt/Roll (Z-X-Z); write `rotation_mode = 0` for Euler
  XYZ. Better: don't hand-build a rotation to aim something. [rule 12]
- ~~"An alpha-0 node is invisible scaffolding"~~ — it still draws and still
  picks. `hide = 1` is the carrier. [rule 13]
- ~~"A wireframe hull lets you click what's inside it"~~ — wire ids pick as
  their solid counterpart, so it is a click shield. [rule 13]

## Writing a skill on top of this one

Packaging a GlyphViz workflow as its own skill — a generator for one chart
family, a house style, a domain vocabulary — is a good pattern, and this skill
is meant to be the layer underneath it. Two rules keep that working.

**Don't restate placement facts.** Extents, seating, scale inheritance, the
minimum-size clamp, carriers and rotation belong to this skill, and they change
when the app changes. A companion skill that copies them freezes a snapshot, and
a stale copy is worse than no copy, because whichever document happens to be
read at design time is the one that wins. Cite the rule number instead.

**Do write down what is genuinely yours**: which columns of the user's data map
to which visual channel, the house palette, the named glyph designs and their
anatomy, the domain's conventions, and your own generator scripts. That is the
part this skill cannot know.

If you are a companion skill and you find yourself disagreeing with a rule
above, the rules above were measured against `glyphviz_core` directly.
Re-measure before overriding one, and say in your own text that you did.

## Choosing topologies (`topo` on the PARENT arranges its children)

| Data shape | Topology |
|---|---|
| Cyclical (months, hours, categories on a ring) | Torus (3) |
| Geographic / directional | Sphere (2) — children use lon/lat/alt |
| Sequential stack | Pin (5) or Rod (6) |
| Exactly ≤ 6 categories | Cube (1) — one face each via `facet` 1–6 |
| Matrix / small grid | Plane (8) |
| Helical / ranked spiral | Spiral (14) |
| Line plot, GPS track, time series path | Plot (16) |
| Heightfield, terrain, FFT | Surface (17) |
| Branching structure (tree, fern, dendrite) | Point (7) + Link limbs |
| **Graph / network** — nodes with no hierarchy, related by edges | **None (0)**, as flat ROOT rows whose `translate_x/y/z` are the world positions a 3-D force layout computed, plus Link rows. See "Laying out a graph" in `references/links-and-edges.md` |
| **Spokes from a hub** — clock face, starburst, wind rose, needles, rays | **Point (7)** (`translate_z` = full reach from the center) or **Sphere (2)** (`translate_z` = height above the surface). Both aim each child outward for you — see rule 12 |
| Free manual placement | None (0) |
| Geo-registered map/globe scene | World Grid node (type 6) as the parent |

Z-variants (9–13) are the same shapes with children pulled to the
center/axis. Full placement math, coordinate meanings per topology, and
worked examples: `references/topologies.md`.

Pick the topology to match the **shape of the data**, then set the parent's
`topo_scale` to match the **units you author children in** (rule 11): degrees
throughout → 1/180 on the linear-axis topologies, world units → leave 1.0.
Mixing the two within one scene is fine — `topo_scale` is per-parent.

## Workflow

1. **Understand the data**: hierarchy depth, what's cyclical vs sequential vs
   geographic, what should map to color/size/position. Ask before assuming.
2. **Design the tree on paper first**: one row per node, levels and topologies
   chosen per the table above.
3. **Generate with a script** (pandas or csv module), never by hand-editing
   CSV text. Start ids at 1; give parents their topology; place children in
   the parent's coordinate system.
4. **Color**: write literal `color_r/g/b` for the on-load look, and *also*
   set `color_index` (+ optional `palette_id`, 26 built-in palettes) to
   pre-wire in-app recoloring with the =/− and Alt+=/Alt+− keys. Palette
   fields never repaint on load — they resolve only on keypress. Palette
   tables, gradient formulas, and the category-coloring recipe:
   `references/color-palettes.md`.
5. **Validate before delivering — run the checker.**

   ```
   python code/gv_extents.py my_scene_gv_node.csv
   ```

   `code/` ships GlyphViz's own placement engine, so this reports the sizes and
   positions the app will actually draw. It names children swallowed by their
   parent, children flung far outside its layout, glyphs that will shear,
   `color_a = 0` nodes used as carriers, links with an unresolvable end, and
   anything that would distort if a user switched on the minimum-size clamp. It
   needs numpy and pandas and nothing else. See `code/README.md`.

   Do the file-level checks too — required columns, unique ids, every
   `parent_id` resolves, colors in range, UTF-8 clean — but know that they pass
   happily on a scene whose parts are buried inside each other. Rendered size
   and seating have to be *computed* (rules 2 and 3); you cannot read them off
   the `scale_*` column.
6. **Check the geometry you actually promised — not just the file's validity.**
   The checks above pass on scenes that render completely wrong, because they
   only test the *file*. Ask what the scene claims visually and re-derive
   exactly that:
   - *positions* — compute each child's **world** coordinate from the parent's
     topology formula (`references/topologies.md`) and confirm the pattern:
     "12 spokes 30° apart, all at z = 0, all the same distance out."
   - **directions** — if the scene's meaning depends on which way a glyph
     *points* (spokes, needles, arrows, cones, tree limbs, anything elongated),
     positions are not enough: a set of correctly-placed rods can still be
     aimed wrong, and no position check can see it. **Read the checker's `AIM`
     section** — it prints every directional glyph's world **+Z**, which is its
     pointing axis, so this is a number to compare rather than something to
     infer from a picture. Under a Sphere/Point/Torus/Ztorus/Cube parent with
     rotations 0, that +Z is the outward direction at the child's own
     `(translate_x, translate_y)`. Calibrate against
     `examples/Radial_Spokes/` — twelve rods on a Sphere hub, twelve on a
     Point hub, every rotate field 0, with the measured vectors committed in
     `aim_report.txt`. **Do not reverse-engineer this from test renders.**
   - *counts and extremes* — the far end of the longest branch, the child
     nearest the parent's center, the one at a wrap point (360°/0°).

   Then **say what you checked and what you couldn't**. You cannot see the
   render, so a scene that "validated" has had its numbers checked and its
   appearance assumed — state that plainly when handing it over, and name the
   specific things the user should eyeball (here: "12 should point up, 3
   right"). One good look at the scene diagnoses in seconds what no amount of
   file validation can catch — see "Closing the loop" below for how to get one
   in a single round trip instead of many.
7. **Hand off**: tell the user to open the node CSV in GlyphViz (File > Open,
   or drag the CSV / scene folder / zip onto the window); a name-paired tag
   file loads automatically. Suggest small first (dozens of nodes) before
   scaling to thousands.

### Closing the loop — getting a picture

You cannot see the render, and a scene that "validated" has had its numbers
checked and its appearance assumed. The slow way to fix that is to hand the
scene over and wait for the user to open the app, orbit to a useful angle and
grab the screen — once per question, for as many questions as it takes. The
fast way is to ask for the right artifact **once**, or to render it yourself.

**If you have a shell** and the user's checkout with GlyphViz's Python
environment, render it and look, before handing anything over:

```bash
python tools/export_frame.py --csv scene_gv_node.csv --out check.png \
    --angles three-quarter,front,top --report
```

**If you don't** — the usual case, since this skill normally runs with no
GlyphViz install — ask the user to run exactly that one command and paste back
both the image and the report text. One command, one image, one paste.

- **`--angles` writes one labelled contact sheet.** A glyph that reads
  correctly from one viewpoint is routinely wrong from another (a starburst
  and a flat fan look identical head-on), so three views in one file is what
  makes a single paste conclusive. Choices: `three-quarter`, `front`, `back`,
  `side`, `top`, `bottom`.
- **`--report` is plain text**, so it costs nothing to paste and often answers
  the question outright — scene extents, **rendered** glyph size per hierarchy
  level (authored `scale` is not what you see; it is multiplied by every
  ancestor's scale and by Global Scale), how far each parent's children sit in
  multiples of the parent's own radius, whether the textures actually loaded,
  and how many labels are pinned versus hidden. **Ask for the report first**:
  most "I thought this was right and it isn't" gaps are visible in it, and it
  is cheaper for both of you than an image.
- Its defaults match how the app opens a file — Global Scale 1.0, labels off
  except `show_text = 1` nodes. Pass `--base-scale` or `--tags` when you need
  to see it another way, and say which you asked for.

**If the user has only the packaged app**, there is no CLI — `GlyphViz.exe`
takes no arguments. Ask for a screenshot, but ask well: name the viewpoint you
want (the Camera toolbar has Top / Front / Side), state what you expect to see
there, and batch your questions into one shot instead of one shot per
iteration. **GlyphViz Web** (`iluvdata.org/glyphvizweb/`) opens the same CSV in
a browser with nothing to install, which is often the quickest way for them to
look at all.

**Never reimplement the placement math.** `code/gv_kernel/` is GlyphViz's own
engine, copied verbatim, so `code/gv_extents.py` and anything you build on it
report what the app will actually draw. Hand-rolling that math in a matplotlib
or three.js previewer has a long history of producing confident wrong answers —
a sphere's half-extent guessed at 0.5, a rotation order that did not match, a
previewer that sized each node by the *mean* of its basis columns and therefore
drew every thin tall rod as a fat disc, generating bug reports about geometry
that was already correct. If a scene looks wrong, the placement math is exactly
what is under suspicion, so a home-made previewer disagreeing with the app
proves nothing.

What you can safely build on the kernel is a *numbers* check, and
`gv_extents.py` already is one. For a picture, use the app's renderer or ask the
user — see below.

### When the app can build it faster than a script

Generating CSV is the right tool for *data*. For a **repeating composite
glyph** with no data behind it — the shape itself is the deliverable — the app
has interactive builders that write the same format, and pointing the user at
one beats scripting it blind:

- **Tools > Glyph Composer** (Ctrl+G) — describe a glyph one level at a time
  (count, geometry, topology, distribution, color ramp, Topology Scale with an
  Auto fit), preview it live, then insert it into the scene, save it as a JSON
  template, or use it as a Draw Mode brush. A level can also emit a **Link back
  to each object's parent**, which is what turns a stack of nested shells into a
  jointed, branching structure.
- **Hyperglyph Tree Designer** — a browser tool (no install) that designs
  branching, tree-like hyperglyphs with a live 3-D preview and exports them as
  Glyph Composer templates. Reach for it for trees, ferns, and dendrites.
- **Hyperglyph Lab** — batch/random generation of composite glyph designs.
- **Epitrochoid Generator** (Ctrl+E) — design an epicycle chain (a stack of
  rotating arms, each turning on the tip of the last) and let the pen at the end
  draw its path. Reach for it for spirograph-family curves and for anything
  built from a Fourier series of circles.
- **Timeline Tower Designer** — a browser tool
  (`iluvdata.org/glyphviz/twitter_lab/tut_designer.html`) that turns an **X
  (Twitter) archive** into a finished scene: every post a needle radiating from
  a vertical time axis, height = when, bearing = time of day, rings on each
  needle carrying likes, reposts, hashtags and keyword hits. If a user asks for
  their X archive visualized, send them here rather than writing a generator —
  it reads the archive in the browser and uploads nothing.

These are GUI tools, not something this skill drives. Use them as a
recommendation; generate CSV yourself whenever real data is involved. The
placement math they rest on is documented either way — see "Direction-relative
branching" in `references/topologies.md` if you'd rather generate a tree
directly.

## Animation options (quick pointers)

- **Rate fields**: `translate_rate_*` / `rotate_rate_*` / `scale_rate_*` are
  per-cycle velocities (~60 cycles/s) applied continuously — the cheapest way
  to add motion (spinning tori, drifting clouds). `freeze` ≠ 0 suspends a node.
- **Channels**: full time-series playback of node attributes via
  `gv_ch-map.csv` / `gv_ch-tracks.csv`, bound per-node with `ch_input_id`
  — positions, rotations, scale, rates, colors, even `texture_id`
  flip-books, optionally synced to an audio file. See
  `references/channels-animation.md`.
- **Link flow**: Link nodes (type 7) with geometry 28 (Prism) scroll their
  texture via `rotate_rate_z` — directed-graph flow animation. Edges follow
  their endpoints every frame, so any animation that moves a node drags its
  edges with it.
- **Textures / video / audio**: `texture_id` is a 1-based index into the
  scene's `media/` folder (sorted: images, then videos; animated GIFs and
  videos animate automatically; video audio can be soloed to the selection).
  It applies to every **solid** geometry including the flat markers
  Circle/Cross/Star (24/25/26) — but is silently ignored by the wireframes,
  Point (22), Mesh (23), and plain Line links (27). See
  `references/textures-and-media.md` before authoring any textured scene.

## Live-updating scenes

A generator may loop (fetch → rebuild → rewrite, e.g. a `--watch N`
flag) and pair with the app's **File > Watch and Reload** (Ctrl+R),
which polls the open node CSV's mtime and hot-reloads on change,
preserving the user's camera, selection, and Channels playback. Rules
for the generator side: write every file **atomically** (temp file +
`os.replace`), and write companion tag/channel files *first* and the
node CSV *last*, so a triggered reload never sees a torn or mismatched
scene. Worked exemplar: `examples/RSS_News/`.

## References

- `code/` — **GlyphViz's own placement engine plus a checker built on it.**
  `code/gv_extents.py` reports rendered sizes, seating, and the specific faults
  that make a valid CSV render wrong; `code/gv_kernel/` is the engine itself,
  byte-identical to the app's, for computing positions and sizes yourself.
  Requires only numpy and pandas. **Run the checker on anything nontrivial
  before you hand it over** — see `code/README.md`.
- `references/hyperglyph-design.md` — how to design a composite glyph a person
  can actually read: anatomy, the design envelope that stops real data breaking
  a layout that worked on samples, readability and occlusion rules, and the
  patterns that keep parts connected and legible. **Read it before designing a
  glyph that carries more than one variable.**
- `references/node-csv-format.md` — the complete, verified column spec
  (required/optional/94-column tables, node types, geometry & topology id
  tables, tag file format). **Read it before generating anything nontrivial.**
  Two shape families there are easy to miss because they answer a request
  phrased as a *look* rather than as data: the **interior** geometries (29–32)
  for anything meant to be seen from within — a 360° video sphere, a panorama,
  a room — and the **Flat Ring** (33) for a ring that has to carry legible
  text or graduations, which a torus cannot.
- `references/topologies.md` — per-topology placement math: coordinate
  meanings, formulas, outward-orientation rules, Plot/Surface overlay
  requirements, and engine-verified worked examples. **Read it before
  positioning children under any non-Cartesian topology.**
- `references/color-palettes.md` — the 26 palettes (full 20-color table,
  gradient formulas), `color_index`/`palette_id` resolution semantics, and
  coloring recipes for generated data.
- `references/textures-and-media.md` — how `texture_id` maps to `media/`
  files, animated GIF/video textures, and video audio (incl. Solo Audio to
  Selection).
- `references/channels-animation.md` — the ch-map/ch-tracks formats, the
  complete bindable-attribute list, playback/audio-sync behavior, and
  animation recipes. **Read it before generating any Channels files.**
- `references/links-and-edges.md` — Link (type 7) rows: the drawing modes
  (line / flow prism / any glyph stretched between the ends), `ratio` as
  thickness, recipes for directed graphs, weighted edges, bonds, and tree
  limbs, **and how to lay a graph out in 3D** — flat root rows carrying world
  positions, and the inverse-square repulsion law a 2D force layout gets wrong.
  **Read it before generating a graph, network, or branching scene.**
- `references/tags-and-labels.md` — inline `text`/`link` vs the companion
  tag file, title encodings, display behavior (incl. the 500-per-frame
  cap), and the U-key link/app-launch rules.
- `references/world-grid.md` — geo-registered scenes: flat plates and
  globes, extents windows, the grid scale rule, multi-grid scenes, and
  engine-verified placement examples. **Read it before building any
  map/geographic scene.**
- `references/troubleshooting.md` — the scene loaded, nothing errored, and it
  still looks wrong: a symptom index of the seventeen silent failure modes
  (children flung away by a topology change, textures ignored on the wrong
  geometry, inert palettes, labels that all vanish, edges that never draw, …)
  with the cause and fix for each. **Read it whenever a generated scene doesn't
  look right — and skim it before generating, since most entries are cheaper to
  avoid than to diagnose.**
- `references/OUTLINE.md` — what's planned but not yet written; do not invent
  content for those areas, derive from `glyphviz_core/` source when available.

## Worked examples

`examples/` holds eight complete, verified scenes with READMEs that explain the
**design thinking**, not just the format. Read the closest one before designing
a scene of your own:

| If you're building… | Study |
|---|---|
| **spokes, rods, needles, rays — anything that has to point somewhere** | `Radial_Spokes/` — Sphere, Point and Cube hubs, every rotate field 0, with the measured +Z of every rod committed |
| **a bar chart, or anything whose length is the measurement** | `Rooted_Bars/` — four recipes over one dataset, measured at two Global Scale settings |
| **a glyph that has to survive the whole dataset, not the sample** | `Glyph_Envelope/` — one glyph at the min, median and max of every variable, with its budget and its extent report |
| a hyperglyph — one repeating composite glyph carrying several variables | `Wind_Rose/`, `Decay_Chain/` |
| a geographic or multi-grid scene | `SD_Seismicity/`, `Wind_Rose/Monsoon_Year/` |
| time-series animation over many nodes | `Breathing_Century/`, `Decay_Chain/Secular_Equilibrium/` |
| a deep multi-branch hierarchy under one clock | `Duel_of_Dynasties/` |
| a live-data scene that regenerates and reloads | `RSS_News/` |
| a graph or network where the edges carry meaning | `Decay_Chain/` (110 links), `SD_Seismicity/` |
