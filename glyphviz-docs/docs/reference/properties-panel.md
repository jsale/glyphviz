# Properties Panel

The Properties Panel is a single `QDockWidget` titled **"Properties"**
(`_build_panel` — `glyphviz_gl/main_window.py:306-900`). It's not just a
per-node field editor — it's the GUI's home for every setting that isn't the
Viewer or the Node Table: scene-wide display toggles, global scale, stereo
3D, world/background settings, node creation defaults, selection tools, *and*
the per-node inspector. All groups below appear in this one scrollable dock,
top to bottom, in this order.

![Properties Panel, Selected Node group populated](../assets/screenshots/reference/properties-panel-selected-node-fields.png)

## What the Properties Panel does

Everything in the **Selected Node** group (below) reflects and edits
whichever node(s) are currently selected — in the Viewer, in the
[Node Table](node-panel.md), or via **Select By**. Edits apply live: changing
a spin box or combo box updates the node object immediately and repaints the
Viewer (`_on_insp_*` handlers, e.g. `_on_insp_pos_changed` at
`main_window.py:1464`, `_on_insp_rotation_changed` at `main_window.py:1491`).

## Display

| Field | Type | Default | Maps to |
|---|---|---|---|
| Show Axes | checkbox | checked | `Viewport.show_axes` |
| Show Grid | checkbox | checked | `Viewport.show_grid` |
| Grid Color | color button | dark gray (56, 56, 71) | The reference grid's line color. Unlike the checkboxes around it this is **scene data**, stored on the World node (`ref_grid_color_r/g/b`) and saved with the file. A World Grid node (type 6) draws its own lattice in its own node color and ignores this setting. |
| Show Hidden Nodes | checkbox | unchecked | `Viewport.show_hidden` |
| Show Tag Labels | checkbox | unchecked | `Viewport.show_tags` (also toggled by the **T** key) |
| Show Tag Labels of Selected | checkbox | unchecked | `Viewport.show_tags_selected_only` — when checked, only selected nodes' tags draw |
| *(texture status label + "…" button)* | — | "No textures loaded" | Opens **Textures → Set Texture Folder…** |
| Audio track dropdown | combo | "All Audio Tracks" | Solos one video's audio track when multiple textured videos are loaded; disabled unless 2+ tracks exist |

Source: `main_window.py:321-376`.

## Global Scale

A single slider, range 1–100 (displayed as 0.1–10.0), default value 10
(→ scale **1.0**). Sets `Viewport.base_scale`, the global geometry-to-world-units
conversion factor. Source: `main_window.py:379-389`.

## Stereo 3D (Cross-Eye)

| Field | Type | Range / Default |
|---|---|---|
| Enable Stereo View | checkbox | unchecked |
| Eye Separation | slider | 0.5%–15.0% of camera distance, default 3.0% |

Mirrors the **View → Stereo 3D (Cross-Eye)** menu toggle. Source:
`main_window.py:391-415`.

## Scene Settings

World-node-only settings — read from/written to the scene's `type=0` World
node (`glyphviz_core/node.py`'s `NODE_TYPE_WORLD`), mirroring ANTz's global
Background Color and Transparency Mode hotkeys.

| Field | Type | Notes |
|---|---|---|
| Background | color swatch + "B/W" button | "B/W" toggles black/white (also the **B** key) |
| Render Mode | combo, 7 options | Normal / Additive / Subtractive / Dark (Multiply) / Off / Screen / Premultiplied Alpha — scene-wide blend mode (also cycled by the **8** key). Values are `RENDER_MODE_*` in `node.py:29-50`. |
| Enable Fog | checkbox | unchecked by default |
| Fog Start / End | two spin boxes, 0–1,000,000 | Defaults 20.0 / 200.0; disabled until fog is enabled |

Source: `main_window.py:417-476`.

## Scene Info

Read-only labels: **File** (current filename), **Nodes** (total count),
**Visible** (count after hide/draw-limit filtering) — plus one checkbox,
**Also Save Tag File** (checked by default), which controls whether Save /
Save As also writes a companion tag CSV. The **K**-key quick-save always
writes both regardless of this checkbox. Source: `main_window.py:478-497`.

## Create

Two buttons — **New Node** (**N** key) and **New Child** (**Shift+N**, requires
exactly one node selected) — plus a **New Object Defaults** sub-form applied
to every node created either way:

| Field | Type | Default |
|---|---|---|
| Geometry | combo, all 27 `GEO_*` values | **Octahedron** (`GEO_OCTA`) |
| Topology | combo, all 18 `TOPO_*` values | **Point** (`TOPO_POINT`) |
| Scale (X, Y, Z) | 3 spin boxes, 0.001–10,000 | 1.0 / 1.0 / 1.0 |
| Lock X/Y/Z together | checkbox | checked |
| Color | color-picker button | RGBA (200, 200, 200, 255) |

Position and rotation for newly-created nodes are not part of these defaults
— they use the existing auto-placement logic (each **N** press increments X
by 10 units). Source: `main_window.py:499-572`.

## Delete

One button, **Delete Selected Objects** (also **Delete**/**Backspace**),
disabled until there's a selection. Deleting a node deletes its descendants
too — children are never reparented onto the deleted node's parent, since
there's no well-defined place to put them. Source: `main_window.py:574-587`.

## Select By

| Control | Notes |
|---|---|
| Select All / Deselect All buttons | Same as Ctrl+A's two states |
| Invert Selection | Selects every node that is *not* currently selected (Ctrl+I) |
| By: | combo — **Branch Level**, **Geometry**, or **Topology** |
| Value: | combo, repopulated from whichever distinct values exist in the loaded scene for the chosen criterion |
| Select All Matching | applies the filter |
| Add to current selection | checkbox, unchecked — when checked, **Select All Matching** and **Select Matching Tags** add to the selection instead of replacing it |
| Tag contains: | line edit — case-insensitive substring matched against each node's tag text (Enter runs the search) |
| Select Matching Tags | selects every node whose tag text contains that keyword |
| Show selection box | checkbox, checked — `Viewport.show_selection_box`, also **Ctrl+B** and **View → Show Selection Box**. Unchecking hides the yellow bounding box around selected nodes *without* deselecting them, so a screengrab can show a chosen state cleanly; Move/Rotate/Size and the selection keys keep working while it is off |

Source: `main_window.py:821-900, 1911-2006`.

## Selected Node

The per-node inspector — disabled (grayed out) until at least one node is
selected; its title becomes `"Selection (N nodes)"` for a multi-selection.
With 2+ nodes selected, Position and Rotation edits apply as a **delta** to
every selected node (so they move together), while Scale, Geometry,
Topology, Ratio, and Color apply the same absolute value to all of them
(`_refresh_inspector_multi` — `main_window.py:1378-1420`).

| Field (UI label) | Node attribute | Type / range | Notes |
|---|---|---|---|
| ID | `id` | read-only label | |
| Type | `type` | read-only label | |
| Parent | `parent_id` | read-only label | |
| Pos (X,Y,Z) | `translate_x/y/z` | 3 spin boxes, ±1,000,000, step 1.0 | |
| Translate Rate | `translate_rate_x/y/z` | 3 spin boxes, ±1,000,000, step 0.01, 4 decimals | Per-cycle position delta (nominally 60 cycles/sec) — nonzero keeps the node moving |
| Rotate (X,Y,Z) | `rotate_x/y/z` | 3 spin boxes, ±360, step 1.0, wraps | |
| Rotate Rate | `rotate_rate_x/y/z` | 3 spin boxes, ±3600, step 0.01, 4 decimals | Degrees added per cycle — spins the node continuously |
| Rotation Mode | `rotation_mode` | combo: "Euler XYZ" / "Heading/Tilt/Roll (ANTz)" | Two interpretations of rotate_x/y/z, dispatched in `topology.py`'s `local_rotation_matrix()` (see `topology.py:151-176`); a missing CSV `rotation_mode` column loads as Heading/Tilt/Roll (preserves legacy file rendering), while a fresh `Node()` constructed in code defaults to Euler XYZ |
| Scale (X,Y,Z) | `scale_x/y/z` | 3 spin boxes, 0.001–10,000, step 0.1 | |
| Scale Rate | `scale_rate_x/y/z` | 3 spin boxes, ±10,000, step 0.001, 4 decimals | Rarely useful nonzero — unbounded growth/shrink |
| *(Lock X/Y/Z together)* | — | checkbox | Ties the three Scale spin boxes together |
| Geometry | `geometry` | combo, all 27 values | See [Geometries](geometries.md) |
| Topology | `topo` | combo, all 18 values | See [Topologies](topologies.md) |
| Facet | `subspace` | combo, 6 named faces (`0: +X` … `5: -Z`) | Only meaningful when this node's **parent** uses Cube or Zcube topology |
| Ratio | `ratio` | spin box, 0.01–1.0, 3 decimals | Torus minor/major radius proportion; also doubles as Point sprite size and Link/Plot line width (both `ratio × 20` px) |
| Texture ID | `texture_id` | spin box, 0–9999, integer | 0 = none, 1 = first image in texture folder (alphanumeric), 2 = second, etc. |
| Color | `color_r/g/b/a` | color-picker button | |
| Tag Text | `text` | line edit | Label shown near the node in 3D (toggle with **T**) |
| Link | `link` | line edit | URL or local file path, opened with **U** |

Source: `main_window.py:621-832` (field construction), `1309-1420`
(populate/refresh logic).

## Channels

A playback transport (Frame label, scrub slider, ▶/■ buttons, FPS spin box,
Loop checkbox) that only becomes visible when the loaded scene has a
Channels animation (`ch-map`/`ch-tracks` CSV pair) attached. Hidden by
default (`self._ch_grp.setVisible(False)` — `main_window.py:834-882`).

## Next step

See [Node Panel](node-panel.md) for how nodes are selected and organized, or
[Geometries](geometries.md) and [Topologies](topologies.md) for what the
Geometry/Topology fields actually control.
