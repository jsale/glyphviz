# Troubleshooting — when a scene loads but looks wrong

Verified against `glyphviz_core/` and `glyphviz_gl/` (2026-08-13, extended
2026-08-15).

Every entry here is a case where **the CSV is valid, the file loads, nothing
errors** — and the scene still isn't what you intended. That's what makes them
expensive: there is no message to read. Find the symptom, then go to the
reference named at the end of the entry for the full rules.

## Symptom index

| What you see | Jump to |
|---|---|
| Children flung far away after changing a parent's `topo` | [1](#1-children-fly-away-when-the-parent-topology-changes) |
| A parent's children sit in a tiny knot at its center | [1](#1-children-fly-away-when-the-parent-topology-changes) |
| Small glyphs all look the same size | [2](#2-every-tiny-glyph-renders-at-the-same-size) |
| Point glyphs ignore `scale_*`, don't shrink with distance | [3](#3-point-glyphs-ignore-scale_) |
| A texture is set but the glyph renders flat-colored | [4](#4-a-texture_id-is-set-but-nothing-is-textured) |
| `geometry` 23 nodes all render as spheres | [5](#5-mesh-glyphs-render-as-spheres) |
| No labels at all, on any node | [6](#6-every-label-vanished) |
| One label reads `nan` | [7](#7-a-label-reads-nan) |
| Hand-posed rotations came out wrong | [8](#8-rotations-are-wrong-in-a-way-that-looks-like-a-different-axis) |
| Colors ignore `palette_id` / `color_index` on load | [9](#9-palette-colors-do-nothing-on-load) |
| The background changed when you recolored everything | [10](#10-a-bulk-edit-changed-the-background) |
| Level-based selection is off by one | [11](#11-select-by-level-is-off-by-one) |
| Some graph edges never appear | [12](#12-some-edges-never-appear) |
| A link went hairline or bloated after a geometry change | [13](#13-a-link-changed-thickness-when-you-changed-its-geometry) |
| Pin glyphs look offset upward from their coordinates | [14](#14-a-pin-sits-above-the-point-it-marks) |
| Spokes/needles/arrows are placed right but point wrong | [15](#15-glyphs-that-should-radiate-came-out-laid-flat-or-fanned-the-wrong-way) |
| A starburst renders as a flat stacked fan | [15](#15-glyphs-that-should-radiate-came-out-laid-flat-or-fanned-the-wrong-way) |

---

## 1. Children fly away when the parent topology changes

**Symptom.** A parent renders fine, then you switch its `topo` — Sphere to Cube,
say — and its children vanish off-screen. Or the reverse: a layout authored in
world units collapses into a knot when the parent becomes a Sphere.

**Cause.** A topology reads some translate axes as **angles** and others as
**distances**. Sphere's `translate_x` is a longitude (360 = all the way round);
a Cube facet's `translate_x` is a distance (360 = 360 world units). The same
authored numbers mean wildly different things under the two readings. From a
radius-9 parent, twelve children authored in degrees land 9.0 units away under
Sphere and **2997.5** under Cube.

**Fix.** Set the **parent's** `topo_scale`:

- Authoring in **world units** (Cartesian-style layouts) → leave it at `1.0`.
- Authoring in **degrees** and want the layout to survive a topology switch →
  `1/180 ≈ 0.005556`, the ANTz convention where a linear axis spans the
  parent's own extent.

Angular axes are never scaled, so this can't distort a circular layout. It's a
per-parent value, so mixed scenes are fine. Full axis-by-axis table:
`topologies.md`.

---

## 2. Every tiny glyph renders at the same size

**Symptom.** Nodes authored at `scale 0.05`, `0.1`, and `0.2` are all drawn
identically, so a size encoding reads as flat.

**Cause.** The viewer has an optional clamp — **View → Enforce Minimum Glyph
Size** — that lifts rendered scale to 0.2 per axis so near-zero glyphs stay
clickable. It is **off by default**, but a user can switch it on at any time,
and then every value below 0.2 collapses to the same floor.

**Fix.** Keep visible nodes at raw `scale_x/y/z` **≥ 0.2** and put the dynamic
range above that floor, so the scene reads identically with the setting either
way. Never encode size as a huge parent times a tiny child — scale multiplies
down the hierarchy, so the *cumulative* value is what gets clamped. World Grid
footprints are exempt from the clamp whatever the setting.

---

## 3. Point glyphs ignore `scale_*`

**Symptom.** `geometry` = 22 nodes are all the same size no matter what you
write in `scale_x/y/z`, and they don't get smaller as the camera pulls back.

**Cause.** Point is not a 3-D shape. It's a `GL_POINTS` sprite drawn at
`max(2, ratio × 20)` **pixels**, outside the display-list system that every
other geometry uses. Node scale is baked into the modelview matrix, which a
fixed-pixel sprite ignores by construction — and so is perspective, so a Point
a mile away is as big as one in front of the camera.

**Fix.** Size point clouds with **`ratio`**, per node. If size needs to read as
depth or magnitude, use the flat markers **Circle 24 / Cross 25 / Star 26**
instead — same cheap scatter-plot idea, but ordinary world-space plates that
scale and recede normally. Details: `node-csv-format.md`.

---

## 4. A `texture_id` is set but nothing is textured

**Symptom.** The media file loads (the status bar counts it), the `texture_id`
is right, and the glyph still renders flat-colored.

**Cause.** `texture_id` is never gated by `geometry` in the format — any node
may carry any id — but only some shapes render one. On a **wireframe**, on
**Point 22**, on **Mesh 23**, and on a plain **Line 27** link, the id is read
and silently dropped.

**Fix.** Move the texture to a solid geometry, a flat marker (24/25/26, textured
since 2026-08-06), or a Link **Prism 28**. Full textured/untextured table:
`textures-and-media.md`.

A second, sneakier version of this: `texture_id` is a **1-based index into the
sorted `media/` folder**, not a filename. Adding one image renumbers every file
after it. If a whole scene's textures shifted by one, count the folder.

---

## 5. Mesh glyphs render as spheres

**Symptom.** Nodes with `geometry` = 23 all draw as spheres.

**Cause.** `mesh_id` is **session state, not a file reference**. Unlike
`texture_id`, which resolves against a `media/` folder discovered next to the
CSV, mesh ids are handed out in the order the user imports mesh files
(Meshes → Import Mesh File…, or dropping mesh files onto the window). With no
mesh loaded for that id, the renderer falls back to a sphere.

**Fix.** Ship the mesh files with the scene and **tell the user the import
order** in your handoff notes — `mesh_id` 1 is the first mesh imported, 2 the
second. Dropping the scene folder works when it contains the meshes. If a scene
must stand alone with no user step, use a built-in geometry instead.

---

## 6. Every label vanished

**Symptom.** Not one label draws, including nodes you know have text.

**Causes, in the order worth checking:**

1. **Labels are off by default** — `T` toggles them. A node with `show_text` = 1
   is pinned on regardless; that's the reliable way to guarantee a label shows.
2. **An encoding problem killed the whole set.** Write CSVs with
   `encoding="utf-8"` and strip control characters from label text — one bad
   byte can take out every tag in the file, silently.
3. **Show-all mode draws at most 500 labels per frame** (file order). This is a
   frame-rate valve, not a limit on how many you may author, and it does not
   apply to selected-only mode.

Full rules, including the three tag-file title encodings: `tags-and-labels.md`.

---

## 7. A label reads `nan`

**Symptom.** One node's label is the literal text `nan`.

**Cause.** The tag file is read with pandas' default NA tokens, so a title of
`None` (also `NA`, `N/A`, `null`, …) parses as a missing value rather than as
the word.

**Fix.** In a generator, rename the value — `"None"` → `"none"`, or better,
something meaningful like `"no decay mode"`. This bites real data often: `None`
is a legitimate category name in plenty of source tables.

---

## 8. Rotations are wrong in a way that looks like a different axis

**Symptom.** You wrote `rotate_x/y/z` expecting each field to spin its own axis;
glyphs came out tilted or spun about something else.

**Cause.** Two conventions exist, and the **CSV default is asymmetric by
design**. A file with **no `rotation_mode` column** loads as ANTz's
Heading/Tilt/Roll (a Z-X-Z sequence: `rotate_y` = heading about Z, `rotate_x` =
tilt about X, `rotate_z` = roll about Z again). A `Node()` constructed in code
defaults to the opposite — Euler XYZ. The asymmetry keeps every pre-existing
ANTz/GaiaViz file rendering exactly as it always did.

**Fix.** If you hand-pose rotations, **write a `rotation_mode` column with 0**
(Euler XYZ). If every rotation is 0, omit the column. See `node-csv-format.md`.

---

## 9. Palette colors do nothing on load

**Symptom.** You set `color_index` and `palette_id` carefully and the scene
opens in the wrong colors entirely.

**Cause.** Palette fields are **inert on load**. Nothing resolves them into RGB
at open time; they take effect only when the user cycles colors with `=` / `−`
(color index) or `Alt+=` / `Alt+−` (palette).

**Fix.** Always write literal `color_r/g/b` for the on-load appearance, *and*
set `color_index` / `palette_id` as well so in-app recoloring is pre-wired.
They're complementary, not alternatives. See `color-palettes.md`.

---

## 10. A bulk edit changed the background

**Symptom.** You recolored "all nodes" in a generator and the scene background
changed too — or a node count is one higher than the glyphs you can see.

**Cause.** Scene settings live on a real CSV row: a **`type` = 0 World node**,
which is never drawn but carries the background color in its own
`color_r/g/b/a`, plus render mode, fog, and tag color. A `type` = 1 Camera row
is likewise non-visual. Loop over every row and you'll edit them along with the
glyphs.

**Fix.** In generators, skip non-visual types (0 and 1) in any bulk pass over
nodes, and treat the World row as scene configuration rather than as data.

---

## 11. Select-by-level is off by one

**Symptom.** Selecting "level 1" picks your root nodes; level-based navigation
is consistently one deeper than expected.

**Cause.** `branch_level` is **0 for roots** in GlyphViz. GaiaViz files use 1,
and that convention leaks easily into a generator — especially one that computes
a child's level as `parent_level + 1` from a root seeded at 1.

**Fix.** Roots (`parent_id` = 0) get `branch_level` = 0, their children 1, and
so on. The field doesn't affect attachment — `parent_id` alone defines the
hierarchy — so nothing moves, which is exactly why this goes unnoticed. It does
drive select-by-level and sibling navigation.

One exception worth knowing: a **Link** node's `parent_id` is its A-end, not a
hierarchy parent, so a link has no tree depth to match. Give it the level of the
structure it belongs to.

---

## 12. Some edges never appear

**Symptom.** A graph draws, but edges are missing — and the node count is higher
than the number of things you can see. No warning, no error.

**Cause.** A Link (`type` = 7) draws **only when both ends resolve**. If
`child_id` is 0, absent, or names an id that isn't in the file — and likewise
for `parent_id` — the renderer skips the row silently. Generators produce these
easily: an edge written before its target node existed, an edge to a node that
was later filtered out, or ids rebased without rewriting `child_id`.

**Fix.** Validate `child_id` exactly as you validate `parent_id`: every link's
**both** endpoints must be real ids in the same file. Drop edges whose target
was filtered out rather than leaving them dangling. Full rules:
`links-and-edges.md`.

---

## 13. A link changed thickness when you changed its geometry

**Symptom.** A Line link at `ratio` = 0.1 looked right; the same link as a
Cylinder is a near-invisible thread across a wide gap — or a `ratio` tuned for a
chunky line turns into a bloated sausage.

**Cause.** `ratio` means two different things in the two modes. On a **Line**
(27) it is a **screen** measurement: `max(ratio × 20, 1)` pixels, which never
changes with distance or with how far apart the endpoints are. On any **stretched
glyph** link it is a **world** measurement: the edge's radius in world units. So
`ratio` = 0.1 is a comfortable 2-pixel line and, at the same time, a 0.2-unit-thick
rod — which is hairline across a 30-unit span and chunky across a 1-unit one.

**Fix.** Re-tune `ratio` whenever you switch a link between line and glyph
modes, and scale it to the **typical edge length** in the scene, not to a fixed
number. `scale_x/y/z` cannot help — they are inert on a link.

---

## 14. A pin sits above the point it marks

**Symptom.** Pin glyphs (`geometry` 16/17) look offset upward from their
coordinates, where every other geometry sits centred on its position.

**Cause.** Pin is the one glyph **not centred on its own origin**. It stands
with its tip at the origin and its shaft along +Z — ANTz's convention, which is
what lets a pin *point at* something. (This changed 2026-08-14; before that the
pin hung below its origin, so pins in older files render about one glyph height
lower than they do now.)

**Fix.** Nothing, if a marker is what you wanted — the tip is on the data point,
which is the useful reading. If you want the pin's *head* on the point, offset
the node by the pin's height along its own +Z. For children of a Pin **parent**,
`translate_x` = 0 is the head's centre and −B is the tip, so the range −B…0
walks the shaft: `topologies.md`.

---

## 15. Glyphs that should radiate came out laid flat, or fanned the wrong way

**Symptom.** You built spokes, needles, arrows, rays or tree limbs. The glyphs
are in the **right places** — a validation pass over the positions confirms it,
which is what makes this one so expensive — but their **bodies point the wrong
way**: a starburst renders as a shallow stacked fan, rods lie flat instead of
radiating, cones aim at nothing in particular.

**Cause.** You hand-posed `rotate_x/y/z` to aim glyphs that the parent's
topology *already aims*. Under a Sphere, Point, Torus, Ztorus or Cube parent
the engine applies a base rotation putting the child's local **+Z** along the
outward direction at that child's own coordinates — and +Z is the long axis of
Cylinder/Cone/Pin and the facing normal of the flat markers. A child's own
rotations do **not** replace that base rotation, they **compose on top of it**,
so every degree you write is a deviation from an aim that was already correct.
Two ways this compounds:

- The frame you rotate in is not the world. After the base rotation your
  `rotate_z` spins about the child's *outward* axis, not the world Z, so the
  angle lands somewhere you didn't intend.
- Multi-axis Euler poses then interact: with `rotation_mode` = 0 each field
  turns about its own axis **in sequence**, so a `rotate_x` = 90 tilt changes
  what the following `rotate_z` does (entry 8 covers the related
  `rotation_mode` trap).

**Fix.** Delete the rotations and let placement do the aiming: set
`rotate_x/y/z` = 0, and express the direction as the child's **`translate_x`**
(longitude/bearing) under a Sphere or Point parent. That is the actual insight —
*the "rotation" you want is a translation.* Reach for `rotate_*` only to pose a
glyph relative to that frame.

Two traps in the same area: **Zsphere places children like a sphere but does
NOT aim them** (Ztorus does), and the axis family (Cylinder, Zcylinder, Spiral,
Zrod, Rod) only spins children about the parent's axis — there the child's **+X**
goes radial and +Z stays axial, so a Cylinder-geometry child of a Cylinder
parent does *not* point outward. Per-topology aim table, the geometry pointing
axes, and a worked spokes recipe: `topologies.md`.

**Catching it before the user does.** Position checks pass on this failure.
Verify **direction** separately: for every glyph whose meaning depends on where
it points, re-derive its aimed axis and compare it against the direction the
design calls for. And when handing off a scene you cannot see rendered, say so
and name what to eyeball.

---

## When the problem is that nothing loads at all

Those failures are loud, and the checks in `SKILL.md`'s workflow step 5 catch
almost all of them before delivery: required columns present, `id` unique,
every `parent_id` resolving to a real id (or 0), colors in 0–255, UTF-8 clean.
Run that validation pass on generated output every time — it is much cheaper
than reading a scene to find out what went wrong.
