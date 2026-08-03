# GlyphViz — Project Context for Claude

## Vision and Goals

GlyphViz is **not** a straight reimplementation of ANTz or GaiaViz. The goal is to match both tools as a foundation, then go beyond them with new capabilities. Examples already shipped: `TOPO_PLOT` (line plots, GPS, oscilloscope data) and `TOPO_SURFACE` (deformable grids, FFT, LIDAR, sound spheres). The Spiral topology was independently derived — no GaiaViz source code is available, only the reference documentation bundled in this repo.

## Feature Target: ANTz vs GaiaViz

Two different questions, with two different answers — don't collapse them:

- **Data contract** (what to generate/validate): `glyphviz-skill/references/` is authoritative for GlyphViz's own native `gv_` format. Consult it first for anything producing data. See "GaiaViz Skill vs. GlyphViz Skill" below.
- **Behavior** (how a topology, placement, or interaction should act): `gaiaviz-skill/references/` is the source, since GlyphViz aims to match ANTz/GaiaViz semantics. For features absent from both (Spiral, Plot, Surface), derive from first principles.

**The ANTz 94-column layout is not GlyphViz's data contract.** `save_node_csv` still *writes* those 94 columns (plus GlyphViz extension columns appended after them) so saved files stay readable by ANTz/GaiaViz tooling, and `load_node_csv` reads them — but that is a compatibility write format, not an authoring requirement. Native `gv_` data needs only the ~20 required columns `glyphviz-skill/references/node-csv-format.md` documents; everything else has a documented load default.

**Key constraint:** We do not have access to the GaiaViz GitHub source. Never assume undocumented GaiaViz behavior — only what the reference docs describe.

## File Naming Convention

GaiaViz's `np_` file/column prefix stands for "neural physics," Shane Saxon's architectural concept underpinning ANTz/GaiaViz — GlyphViz has no equivalent architecture and shouldn't claim the name. GlyphViz's own example/generated data uses a `gv_` prefix instead (`gv_node.csv`, `gv_tag.csv`, `gv_ch-map.csv`, `gv_ch-tracks.csv`). The `np_` prefix is still recognized when *reading* genuine third-party GaiaViz files — both as a filename pattern and as the handful of GaiaViz-specific column names (`np_node_id`, `np_geometry_id`, `np_topo_id`, `np_texture_id`, `np_ch_in_id`) aliased in `glyphviz_core/csv_reader.py` and `channel_engine.py`. Do not rename those aliases — they exist for interop, not branding. `gaiaviz-skill/examples/` also keeps `np_` since it demonstrates the actual GaiaViz spec.

**Node↔tag pairing convention**: a tag CSV's name is its node CSV's name with the `node`/`np_node` stem swapped for `tag`/`np_tag` — e.g. `gv_node.csv` ↔ `gv_tag.csv`, `np_node.csv` ↔ `np_tag.csv`, and timestamped saves carry the same stamp on both (`gv_node20260625182432.csv` ↔ `gv_tag20260625182432.csv`). `glyphviz_core/csv_reader.py`'s `stamp_node_and_tag_paths()` derives the tag path this way and only when the unstamped node-file stem ends in `node`; `load_node_csv` looks for the matching tag file automatically on open. Tag rows: `table_id` is always `0`, `record_id` matches the node CSV's `id` column (full row format and the three `title` encodings: `glyphviz-skill/references/tags-and-labels.md`).

## Feature Status

**Shipped** — these were listed here as pending long after they landed; verified against the code 2026-07-24. Don't re-propose them as new work:

- **Tags** — text labels attached to nodes, loaded either from inline `text`/`link` columns or a companion tag CSV (`gv_tag.csv` native, `np_tag.csv` for GaiaViz-format files), with URL, local-file, and app-launch link encoding (U key / Alt+click). Per-node `show_text` pins a label on regardless of the scene-wide tag settings; the World node's `tag_color_mode` / `tag_color_r/g/b` style every label. Native spec: `glyphviz-skill/references/tags-and-labels.md`. `gaiaviz-skill/references/format/Tag-Format.md` covers only the legacy `np_` companion-file dialect — reach for it when reading genuine GaiaViz files, not when generating.
- **Channels (animation)** — time-series animation of node attributes via the `ch-map`/`ch-tracks` CSV pair (`gv_` native, `np_` for GaiaViz-format files), with a playback transport, FPS control, and a dense-scene fast path. Powers the EEG, GPS, IoT, and biometric examples. Native spec: `glyphviz-skill/references/channels-animation.md`. The bindable-attribute set lives in one table, `channel_engine.py`'s `_ATTR_TO_FIELD`, and covers transform + rates + color + palette (`palette_id`/`color_index`, resolved to RGB per frame) + shape (`ratio`/`topo`/`geometry`/`mesh_id`) + visibility (`hide`/`show_text`) + the World row's scene settings (`render_mode`, `fog_*`, and background via its own `color_r/g/b`). Adding one is a `_ATTR_TO_FIELD` entry plus, if it re-places children, an `_TRANSFORM_FIELDS` entry.
- **Save edits back to CSV** (timestamped node+tag save, K key) and **multi-select**.
- **Transform gizmo (red/green/blue X/Y/Z handles)** — arming Move/Rotate/Size draws arrows/rings/bars on the first selected visual node; dragging one constrains the edit to that axis and tracks the cursor, and the whole selection takes the same field change (GlyphViz Web's multi-select rule). Purely **additive**: a press that misses every handle still gets the pre-existing free-form axis-checkbox drag, so nothing was replaced. View > Show Transform Handles hides them without disarming the mode. The Properties panel's "Lock X/Y/Z together" checkbox also governs Size mode (`Viewport.uniform_scale`): any Size drag then applies one FACTOR to all three axes — deliberately not the panel spin boxes' equalize-the-values rule, which would flatten a 3:1:1 glyph to a cube on the first pixel. Rotate rings are built perpendicular to their OWN axis (`gizmo.perpendicular_basis`), never spanned by the other two — the gizmo's three rotation axes are non-orthogonal in general, and spanning ring A with axes B and C squashed it to a sliver near gimbal lock (Jeff's 2026-08-03 report); coincident rings now correctly *mean* gimbal lock. Suppressed on Links, in Camera Mode, and in stereo. The per-mode handle frames are the whole point and are NOT the node's local axes: Move follows the numerical gradient of `topology.placement_offset` (so a Sphere parent's red arrow is the longitude tangent), Rotate differentiates the rotation matrix (so HTR's `rotate_y`→Z-rotation is handled), Size uses the world_basis columns. Qt-free math in `glyphviz_core/gizmo.py`; tests `tests/test_gizmo.py` (math, pinned against the real engine) + `tests/test_gizmo_viewport.py` (interaction, no GL context needed — camera matrices are seeded and checked against a real paint). Docs: `glyphviz-docs/docs/reference/viewer-navigation.md#transform-handles`.
- **Camera Mode (free flight)** — **C** toggles it (this *displaced* the old plain-C camera cycling, which moved to **Shift+C**; reverse-cycling is gone, the Camera toolbar covers direct jumps). Left-drag is ANTz-style **rate flight** on ANTz's opposite button (reworked 2026-07-30 at the test group's request, replacing the original per-move drag with transient banking — banking is gone entirely): the press point becomes a bearings origin, the held cursor offset from it sets a continuous forward/back speed and turn rate (integrated per repaint tick in `_apply_fly_drag`, so motion continues while the mouse sits still; 3px dead zone), and flight is locked to the horizontal plane it starts on (translation follows the heading with pitch dropped). Right-drag looks around from where the camera stands (ANTz's left-button gesture), both buttons slide, wheel flies. Same orbit rig underneath: flight holds `_cam_distance` fixed and moves the *target* end of the arm (`_reaim_about_eye`, `_translate_rig` in `viewport.py`), so the target rides in front of the camera instead of pinning it. Locked axis cameras can't fly; Follow Selected is cleared on entry. Tests: `tests/test_camera_mode.py`.
- **Drag and drop** — dropping a node CSV, a scene folder, or a **zip** onto the window loads it; Shift+drop merges instead of replacing. Also takes `.pdb`, mesh files, and image/video folders. All routing decisions live in the Qt-free `glyphviz_core/drop_router.py` (`resolve_drop()` returns an ordered `DropPlan`; `MainWindow.apply_drop()` executes it), so they're testable headlessly — `tests/test_drop_router.py`. A folder/zip drop only ever *actions* the node CSV: the tag file, ch-map/ch-tracks pair, audio manifest, and `media/` textures are all discovered from that path by the existing loaders. Node CSVs are identified by **columns, not filename**, so arbitrarily-named files load and companions never masquerade as scenes. Zips extract beside themselves (never overwriting an existing folder), falling back to temp when that's unwritable; entries with absolute or `..` paths are refused. Docs: `glyphviz-docs/docs/reference/drag-and-drop.md`.
- **Fetch Basemap** — World Grid panel button (flat grids only): measures the grid children's lon/lat bounding box, downloads map imagery for that window from a free tile service (OSM streets / Esri satellite / OpenTopoMap terrain — no API key), reprojects Web Mercator → plate carrée so the map lines up with child placement, stamps the required attribution into the corner, writes `media/zz_basemap_grid<id>.png` beside the CSV, and sets the grid's extents + `texture_id` (other nodes' `texture_id`s auto-shift when the insertion changes media numbering; refetch overwrites in place, no shift). Qt-free logic in `glyphviz_core/basemap.py` (tile cache in `%LOCALAPPDATA%\GlyphViz\tile_cache`, 60-tile cap per fetch); dialog+worker in `glyphviz_gl/basemap_dialog.py`; tests `tests/test_basemap.py` run offline with an injected fetcher. Antimeridian-crossing windows unsupported. Docs: `glyphviz-docs/docs/reference/basemaps.md`.
- **Scene merge** — File > Merge Node CSV… (Ctrl+M) loads a second node file (and its companion tag file) *into* the loaded scene instead of replacing it, rebasing ids and every id-bearing `extras` field (`parent_id`, a link's `child_id`, the tag join key `record_id`). `glyphviz_core/scene_merge.py`. Channel animation from the merged file is deliberately not imported — that's the known gap if it ever comes up.

**Pending:**

1. **Workflow polish** — undo/redo, table search/filter, select-descendants.

2. **VR/AR/XR** — Long-term goal: an immersive viewer. No codebase exists yet; desktop 3D is the current focus. Flag any architectural decisions that would make a future XR port harder.

## Topology Inventory

All 18 types defined in `glyphviz_core/topology.py` are now implemented: None (0), Cube (1), Sphere (2), Torus (3), Cylinder (4), Pin (5), Rod (6), Point (7), Plane (8), Zcube (9), Zsphere (10), Ztorus (11), Zcylinder (12), Zrod (13), Spiral (14), Video (15), Plot (16), Surface (17).

The legacy ANTz/GlyphViz-native node CSV column for Cube's face selector is spelled `facet` (1-indexed: 1=+X, 2=-X, 3=+Y, 4=-Y, 5=+Z, 6=-Z — confirmed against a real ANTz session, see commit history); GaiaViz's `np_` dialect spells the same concept `subspace` (0-indexed). `glyphviz_core/csv_reader.py`'s `load_node_csv` checks for `subspace` first and falls back to `facet - 1`; `save_node_csv` always writes `facet` (the canonical ANTz column name) from `Node.subspace + 1`.

Z-topology variants (9–13) are each "akin to" their non-Z counterpart with the surface/radius offset term zeroed out (children sit through the center/axis rather than on the rendered surface) — see `Topology-Guide.md`'s "Important Scale and Position Notes" section. Zrod's placement math is intentionally identical to Zcylinder's.

When topology behavior is ambiguous, consult `gaiaviz-skill/references/structure/Topology-Guide.md` first. If not covered there, derive from first principles and note the choice in the commit message.

## World Grid (type=6)

Implemented 2026-07-13 (second attempt; the reverted V1's implicit root-glyph attachment is gone). A World Grid is a real, movable/rotatable/scalable node whose children attach **explicitly** via `parent_id = grid.id` — never implicitly, and scenes have no default grid (legacy type-6 rows in loaded files do render; GaiaViz's parent_id=0 main-grid convention is deliberately not used). Children place by `translate_x`=longitude, `translate_y`=latitude, `translate_z`=elevation within the grid's **extents window** (`Node.grid_extents()`), stored in the 94-column `trigger_lo_x/hi_x` (lon min/max) and `trigger_lo_y/hi_y` (lat min/max) fields; `segments_x/y` are the rendered cell counts. Degenerate (hi ≤ lo, i.e. legacy all-zero) axes fall back to the whole-earth window (-180..180, -90..90), which centers at (0, 0) so a grid at the origin with scale 1 is an exact 1:1 frame — a child at (180, 90) coincides with a non-child node at world (180, 90). Region windows recenter children on the window midpoint. The grid's draw matrix is extents half-spans × RAW scale (no base_scale, no 0.2 floor — see `scene._grid_draw_scale`) so the rendered rectangle stays under its children.

Key rules: grid scale re-spaces child POSITIONS per axis but never child rendered size or subtree internal spacing (keyed on parent TYPE=6 in `compute_world_transforms` / `update_world_transform_rows` — plain topo=Plane parents keep legacy scale inheritance); grids are never click/rubber-band-pickable (G key selects/cycles them, matching ANTz; the node table and World Grid panel also select) and are excluded from bulk Select All; Move-drag sensitivity for children of scaled Cartesian parents divides by the parent's cumulative scale (`viewport._move_axis_divisors` — this was V1's "hypersensitive mouse" failure). Solid grid geometry (`GEO_GRID`) takes an equirectangular texture across the window; wire geometry draws the lattice only.

**Globe form**: a grid whose `geometry` is Sphere/Sphere Wire (`Node.grid_is_globe()`) renders as a globe and places the SAME children by KML lon/lat on the sphere surface (radius `GRID_GLOBE_RADIUS` = 180/π at scale 1, so the equator is exactly 360 world units — the flat 1:1 map rolled up; `translate_z` = radial elevation, children get TOPO_SPHERE's outward base rotation). Toggle via the World Grid panel's Shape combo or the Geometry dropdown (wire/solid preserved; flat↔globe is just a geometry change + invalidate, fully CSV-native). Extents recentering does not apply on a globe (absolute lon/lat; the panel disables those fields); `segments_x/y` set the graticule. The sphere is drawn bespoke in `viewport._globe_surface` with exact equirect UVs — do NOT swap in `gluSphere`, whose texture mapping is offset and mirrored in longitude vs KML. Solid grid surfaces (plate or globe) render into the pick FBO as color-ID-0 occluders: still unpickable, but clicks can't select glyphs hidden behind them; wire forms get no occluder.

## Rotation Convention

`rotate_x/y/z` support two interpretations, selected per-node via `Node.rotation_mode` (`glyphviz_core/node.py`):

- **`ROTATION_MODE_HEADING_TILT_ROLL`** (1) — ANTz's only-ever convention: a Z-X-Z "proper Euler" sequence borrowed from KML's Heading/Tilt/Roll camera-and-model convention (`rotate_y`=Heading about z, `rotate_x`=Tilt about x, `rotate_z`=Roll about z again — see `gaiaviz-skill/references/structure/Node-Field-Descriptions.md`'s Rotate section). Heading-then-Tilt is the standard spherical-coordinate parameterization, matching the longitude/latitude convention `translate_x/y` already use on Sphere/Torus topologies.
- **`ROTATION_MODE_EULER_XYZ`** (0) — GlyphViz-only, and the default for new nodes: `rotate_x/y/z` each rotate about their own named axis, intuitive for hand-posing glyphs. Jeff finds the ANTz convention unintuitive for that workflow and no longer needs rotation-specific ANTz file compatibility.

Implemented in `glyphviz_core/topology.py`'s `local_rotation_matrix()` dispatcher. **CSV default-handling is asymmetric by design**: a missing `rotation_mode` column (every pre-existing ANTz/GaiaViz/`gv_` file) loads as `HEADING_TILT_ROLL` in `csv_reader.py`'s `load_node_csv`, preserving old files' rendering exactly; a freshly-constructed `Node()` in code defaults to `EULER_XYZ`. `save_node_csv` only writes the column when a node's value would be *misread* by that load-side fallback (i.e. `rotation_mode != HEADING_TILT_ROLL`) — not simply "non-default" — so untouched legacy files stay byte-for-byte stable and new EULER_XYZ nodes still round-trip correctly. See `examples/Rotation_Convention_Example/` for a verified (numerically checked against `local_rotation_matrix()`) side-by-side demonstration: identical `(rotate_x=30, rotate_y=0..360)` input traces a level circle under Heading/Tilt/Roll but wobbles in elevation under Euler XYZ.

## Collaboration Notes

- Address the developer as **Jeff**, not "the user."
- Jeff has strong domain vision but sometimes feels uncertain about feature prioritization. When the backlog is long, offer a ranked recommendation with brief rationale rather than presenting an open-ended menu of choices.
- Verification of math/picking/camera fixes uses the temp-CSV-through-real-app-objects pattern; see the auto-memory for details.

## Tech Stack

Python 3.12, PySide6 (Qt6), PyOpenGL, numpy, pandas.
Run: call the `glyphviz` conda env's `python.exe` directly for *every* invocation
(running the app, one-off scripts, headless verification scripts, tests) —
e.g. `& $env:GLYPHVIZ_PYTHON main.py`.

**`$env:GLYPHVIZ_PYTHON` is the answer when it's set.** Each machine defines it (plus
the other machine-local paths) in the gitignored `.claude/settings.local.json` `env`
block, so this file never has to carry a path that's wrong on the other machine. Use it
without re-deriving it. Only if the variable is empty — a fresh clone on a machine that
hasn't been set up yet — resolve the path (`conda env list`, take the `glyphviz` row, or
read `%USERPROFILE%\.conda\environments.txt`), then write it into
`.claude/settings.local.json` so the next session doesn't repeat the search. The path is
**not fixed** across Jeff's machines: seen so far `anaconda3\envs\glyphviz\python.exe`
and `.conda\envs\glyphviz\python.exe`, both under `%USERPROFILE%`.

Never use `conda run -n glyphviz ...`: it hangs silently on Jeff's Windows setup (broken
stdout/stderr inheritance in some terminal environments) and needs Ctrl+C to escape.

## GaiaViz Skill vs. GlyphViz Skill

Two separate Claude skills exist, for two separate formats — neither stands in for the other:

- **`glyphviz-skill/`** — the actively-maintained skill for GlyphViz's own **native** format (`gv_` prefix, only 20 required columns, no mandatory infrastructure rows). This is the skill Jeff shares externally, and `glyphviz-skill/references/` is the authoritative spec for GlyphViz's own CSV data contract — consult it first for anything generating or validating `gv_` data.
- **`gaiaviz-skill/`** — reference material for the actual legacy GaiaViz/ANTz format (`np_` prefix, 94 columns, mandatory infrastructure rows). Its role is interop and behavioral fidelity only: reading genuine third-party GaiaViz files, and grounding topology/behavior decisions in GaiaViz's documented conventions (see "Feature Target: ANTz vs GaiaViz" above). It is not the contract for anything GlyphViz generates natively — `glyphviz-skill/` is.
