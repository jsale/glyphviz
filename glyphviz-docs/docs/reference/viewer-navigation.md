# Viewer Navigation

Everything on this page is read directly from the event handlers in
`glyphviz_gl/viewport.py` (the `Viewport` `QOpenGLWidget` subclass) and the
shortcuts wired up in `glyphviz_gl/main_window.py`. Citations point at the
function/line where each binding is implemented.

## Camera controls

The camera is orbit/target/distance based (`_cam_azimuth`, `_cam_elevation`,
`_cam_target`, `_cam_distance` — `viewport.py:126-129`). Which mouse button
does what depends on whether a Move/Rotate/Size **gizmo mode** is active (see
[Node manipulation](#node-manipulation) below) — the bindings below describe
plain camera-only interaction, i.e. no gizmo mode selected. They also assume
Camera Mode is off; **C** swaps them all for free flight (see
[Camera Mode](#camera-mode-free-flight)).

| Action | Binding | Source |
|---|---|---|
| Orbit | Left-click + drag (or Right-click + drag) | `mouseMoveEvent`, `_orbit_camera` — `viewport.py:1502-1515, 1533-1535` |
| Pan | Middle-click + drag | `mouseMoveEvent` — `viewport.py:1517-1528` |
| Zoom | Scroll wheel (×0.88 per notch in, ×1.14 per notch out) | `wheelEvent` — `viewport.py:1569-1573` |
| Reset / reframe view | **View → Reset Camera** menu item | `_reset_camera` — `main_window.py:1802-1803` |

Orbit sensitivity is `0.4°` of azimuth/elevation per pixel of drag; elevation
is clamped to ±89° (`_orbit_camera`, `viewport.py:1533-1535`). Pan speed scales
with the current camera distance (`viewport.py:1525-1528`).

**Reset Camera** re-fits the camera's *target* and *distance* to the bounding
box of all loaded nodes (the same auto-framing `Viewport.set_nodes()` does on
load) — it does **not** reset azimuth/elevation back to any default angle,
since it just calls `set_nodes()` again (`main_window.py:1802-1803`,
`viewport.py:223-244`).

### Camera Mode (free flight)

Press **C**, click **Fly** on the Camera toolbar, or use **View → Camera Mode
(Free Flight)** to swap the orbit gestures for flight. The orbit camera is
always anchored to a target — to get a fresh angle you pan away, re-orient,
pan again. Camera Mode drops the anchor so you can simply fly to the shot,
which is what it exists for: composing screen-capture angles.

| Action | Binding | Source |
|---|---|---|
| Fly forward / back (hold above / below the press point) | Left-click + hold, cursor above/below the click | `_apply_fly_drag` |
| Turn left / right (hold beside the press point) | Left-click + hold, cursor left/right of the click | `_apply_fly_drag` |
| Look around from where the camera stands | Right-click + drag | `_look_around_camera` |
| Slide sideways / up / down without turning | Left + Right together + drag | `_fly_strafe_camera` |
| Fly forward / back | Scroll wheel | `wheelEvent` |
| Pan | Middle-click + drag (unchanged) | `mouseMoveEvent` |

Left-button flight is **rate-based**, matching ANTz (but on ANTz's opposite
button — in ANTz the right button flies and the left looks around; here
it's reversed). The point where you press becomes the bearings origin, and
nothing moves until the cursor leaves a small dead zone around it. Holding
the cursor above the origin flies forward at a speed proportional to the
held offset — a slight offset gives a slight but *constant* speed for as
long as the button is down, even with the mouse stationary — and bringing
the cursor back to the origin stops the flight; holding below it flies
backward, and holding left/right of it turns at a rate proportional to the
sideways offset. Flight is locked to the horizontal plane it starts on:
the camera translates along its heading with the pitch component dropped,
so altitude never changes no matter where the aim points (use right-drag
look-around, the wheel, or a Left+Right slide to change altitude).

Speeds scale with the camera's arm length (`_FLY_RATE_PER_PX_S`), so
holding the same offset covers about the same fraction of the view whether
you're circling a whole scene or nosing around one glyph. Pitch is clamped
to ±89°, as with the orbit camera.

While Camera Mode is on:

- Clicking still selects, and Shift+drag still rubber-band selects — but
  Move/Rotate/Size gizmo drags are suspended until it's switched back off.
- **Follow Selected Node** is switched off (it re-pins the camera target
  every frame, which would undo flight immediately).
- The fixed **+X/+Y/+Z** reference views can't fly. Turning Camera Mode on
  switches to the **Main** camera; picking a reference view turns it off.

Double-clicking a node also moves the camera: it selects the node and zooms
in to frame it with headroom (`mouseDoubleClickEvent` →
`focus_on_node` — `viewport.py:1474-1479, 306-310`). The Node Table's
double-click does the same thing (`_on_table_double_click` —
`main_window.py:1796-1800`).

## Selection

| Action | Binding | Source |
|---|---|---|
| Select a node | Left-click on it (replaces selection) | `mouseReleaseEvent` — `viewport.py:1453-1469` |
| Add/remove one node | Ctrl + Left-click on it | `mouseReleaseEvent` → `nodeClickedAdditive` — `viewport.py:1461-1466` |
| Rubber-band select | Shift + Left-click-drag a rectangle | `mousePressEvent`/`mouseReleaseEvent` — `viewport.py:1412-1425, 1434-1451` |
| Deselect all | Left-click empty space (no Ctrl held) | `mouseReleaseEvent` — `viewport.py:1467-1469` |
| Select/deselect all | **Ctrl+A** (toggles: selects all unless everything is already selected, then deselects) | `QShortcut("Ctrl+A")` → `_on_select_all_toggle` — `main_window.py:109-111, 1258-1263` |

Rubber-band region select is disabled while Stereo 3D (Cross-Eye) view is
active — a single screen-space rectangle can't be mapped back to one node set
when the two eyes show different projections of the same scene. Single-node
click/double-click picking still works in stereo (`mousePressEvent` comment —
`viewport.py:1413-1418`).

Node Table row selection and Viewer selection are the same selection state —
picking in one updates the other (`_on_table_selection`,
`_on_viewport_pick*` — `main_window.py:1267-1284`). See
[Node Panel](node-panel.md).

## Keyboard shortcuts

Shortcuts handled directly in the Viewer (`Viewport.keyPressEvent`/`event`,
`viewport.py:1341-1390`) — active whenever the 3D view has keyboard focus:

| Key | Action | Source |
|---|---|---|
| ↑ (Up) | Select the current node's parent | `navParent` → `_nav_parent` — `viewport.py:1356-1358`, `main_window.py:1844-1852` |
| ↓ (Down) | Select the current node's first child | `navChild` → `_nav_child` — `viewport.py:1359-1361`, `main_window.py:1854-1865` |
| Tab | Select next sibling (wraps; at branch level 0 this cycles all root nodes) | `navNextSibling` → `_nav_next_sibling` — `viewport.py:1345-1348`, `main_window.py:1867-1891` |
| Shift+Tab | Select previous sibling (wraps) | `navPrevSibling` → `_nav_prev_sibling` — `viewport.py:1349-1352`, `main_window.py:1893-1906` |
| N | New node (child of selection if a non-root node is selected, else a new root) | `createNode` → `_on_create_node` — `viewport.py:1362-1366`, `main_window.py:1910-1913` |
| Shift+N | New child node under the current (single) selection | `createChildNode` → `_create_child_node` — `viewport.py:1363-1364` |
| \ (backslash) | Halve the draw limit (progressively hides nodes — perf aid for huge scenes) | `_adjust_draw_limit(0.5)` — `viewport.py:1368-1374, 1392-1408` |
| Shift+\ or \| | Double the draw limit (restores toward showing everything) | `_adjust_draw_limit(2.0)` — `viewport.py:1368-1374` |
| T | Toggle tag-label display | `viewport.py:1375-1379` |
| B | Toggle background black/white | `bgToggleRequested` — `viewport.py:1380-1382` |
| 8 | Cycle the scene-wide render/blend mode | `renderModeCycleRequested` — `viewport.py:1383-1385` |
| K | Quick-save — writes fresh, timestamped node + tag CSVs immediately (no dialog), next to the running executable | `quickSaveRequested` → `_quick_save` — `viewport.py:1386-1388`, `main_window.py:1093-1106` |
| C | Toggle **Camera Mode** (free flight) on/off — see [above](#camera-mode-free-flight) | `toggle_fly_mode` |
| Shift+C | Step to the next camera (Main → +X → +Y → +Z → Main) | `cycle_camera` |
| O / Shift+O | Cycle each selected node's **geometry** forward/back one entry (ANTz-style; the step is per node, so a mixed-geometry selection stays mixed) | `geoCycleRequested` → `_cycle_selected_geometry` |
| J / Shift+J | Cycle each selected node's **topology** forward/back one entry (same per-node rule) | `topoCycleRequested` → `_cycle_selected_topology` |

Shortcuts registered at the main-window level (`QShortcut`, still fire while
the Viewer has focus, since Qt shortcuts aren't widget-scoped here):

| Key | Action | Source |
|---|---|---|
| Ctrl+A | Select all / deselect all (see above) | `main_window.py:109-111` |
| U | Open the selected node's **Link** field (URL or local file) in the OS default handler | `_on_open_link` — `main_window.py:112, 1166-1181` |
| Delete / Backspace | Delete the selected node(s) and their descendants | `_delete_selected` — `main_window.py:113-114` |
| Ctrl+B | Show/hide the yellow selection bounding box **without** changing the selection — for clean screengrabs of a selected state. (ANTz uses the spacebar for this; in GlyphViz the spacebar drives Channels playback.) | *View → Show Selection Box* → `_set_selection_box` |

File/Edit/View menu actions carry their own accelerators (Ctrl+O, Ctrl+S,
Ctrl+Shift+S, F12, Ctrl+C, Ctrl+V, Ctrl+G, Ctrl+B) — see [Menus](menus.md).

## Node manipulation

The **Manipulate** toolbar (built in `_build_manipulate_toolbar`,
`main_window.py:241-279`) sits above the Viewer and is always visible. It has
three mutually-exclusive mode buttons — **Move**, **Rotate**, **Size** — plus
**X**/**Y**/**Z** axis-confinement checkboxes (all checked by default). The
buttons are disabled until at least one node is selected.

Clicking a mode button a second time returns to camera-only dragging
(`_on_mode_button_clicked` — `main_window.py:281-283`). While a mode is
active:

- **Left-click + drag** moves/rotates/scales the selection along the first
  enabled axis (and the second, if two or more axes are checked).
- **Right-click + drag** manipulates the third enabled axis, but only when
  all three X/Y/Z boxes are checked — otherwise Right-click still just orbits
  the camera.

(`mouseMoveEvent`, `_apply_axis_deltas` — `viewport.py:1499-1567`.) Move drag
speed matches camera-pan speed; Rotate drag speed matches orbit sensitivity
(0.4° per pixel); Size drag applies a `1.0 + raw*0.004` per-pixel multiplier,
floored at `0.001` (`viewport.py:1552-1562`).

## Next step

See [Menus](menus.md) for the menu-driven equivalents of these actions, or
[Properties Panel](properties-panel.md) to see what happens after you select
a node.
