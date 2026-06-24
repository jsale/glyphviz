# GlyphViz — Project Context for Claude

## Vision and Goals

GlyphViz is **not** a straight reimplementation of ANTz or GaiaViz. The goal is to match both tools as a foundation, then go beyond them with new capabilities. Examples already shipped: `TOPO_PLOT` (line plots, GPS, oscilloscope data) and `TOPO_SURFACE` (deformable grids, FFT, LIDAR, sound spheres). The Spiral topology was independently derived — no GaiaViz source code is available, only the reference documentation bundled in this repo.

## Feature Target: ANTz vs GaiaViz

This is an open architectural question. When implementing topologies or behaviors, use `gaiaviz-skill/references/` as the primary spec. For features absent from both (Spiral, Plot, Surface), derive from first principles while keeping the ANTz 94-column CSV format as the data contract.

**Key constraint:** We do not have access to the GaiaViz GitHub source. Never assume undocumented GaiaViz behavior — only what the reference docs describe.

## File Naming Convention

GaiaViz's `np_` file/column prefix stands for "neural physics," Shane Saxon's architectural concept underpinning ANTz/GaiaViz — GlyphViz has no equivalent architecture and shouldn't claim the name. GlyphViz's own example/generated data uses a `gv_` prefix instead (`gv_node.csv`, `gv_tag.csv`, `gv_ch-map.csv`, `gv_ch-tracks.csv`). The `np_` prefix is still recognized when *reading* genuine third-party GaiaViz files — both as a filename pattern and as the handful of GaiaViz-specific column names (`np_node_id`, `np_geometry_id`, `np_topo_id`, `np_texture_id`, `np_ch_in_id`) aliased in `glyphviz_core/csv_reader.py` and `channel_engine.py`. Do not rename those aliases — they exist for interop, not branding. `gaiaviz-skill/examples/` also keeps `np_` since it demonstrates the actual GaiaViz spec.

## Pending High-Priority Features

1. **Tags** — Text labels attached to nodes. Load/render the tag CSV (`gv_tag.csv` for GlyphViz-native data, `np_tag.csv` for GaiaViz-format data); support URL, local file, and app-launch encoding. `table_id` must be 0; `record_id` matches the node CSV's id column. Spec: `gaiaviz-skill/references/format/Tag-Format.md` and `Text-Tags-Usage.md`.

2. **Channels (animation)** — Time-series animation of node attributes via the `ch-map`/`ch-tracks` CSV pair (`gv_ch-map.csv`/`gv_ch-tracks.csv` for GlyphViz-native data, `np_ch-map.csv`/`np_ch-tracks.csv` for GaiaViz-format data). Enables EEG, GPS, IoT, and biometric visualizations. See `gaiaviz-skill/examples/Channels_Example/` and `RHR_Channel_Anim1/`.

3. **Workflow polish** — Save edits back to CSV, undo/redo, multi-select, table search/filter.

4. **VR/AR/XR** — Long-term goal: an immersive viewer. No codebase exists yet; desktop 3D is the current focus. Flag any architectural decisions that would make a future XR port harder.

## Topology Inventory

All 18 types defined in `glyphviz_core/topology.py` are now implemented: None (0), Cube (1), Sphere (2), Torus (3), Cylinder (4), Pin (5), Rod (6), Point (7), Plane (8), Zcube (9), Zsphere (10), Ztorus (11), Zcylinder (12), Zrod (13), Spiral (14), Video (15), Plot (16), Surface (17).

The legacy ANTz/GlyphViz-native node CSV column for Cube's face selector is spelled `facet` (1-indexed: 1=+X, 2=-X, 3=+Y, 4=-Y, 5=+Z, 6=-Z — confirmed against a real ANTz session, see commit history); GaiaViz's `np_` dialect spells the same concept `subspace` (0-indexed). `glyphviz_core/csv_reader.py`'s `load_node_csv` checks for `subspace` first and falls back to `facet - 1`; `save_node_csv` always writes `facet` (the canonical ANTz column name) from `Node.subspace + 1`.

Z-topology variants (9–13) are each "akin to" their non-Z counterpart with the surface/radius offset term zeroed out (children sit through the center/axis rather than on the rendered surface) — see `Topology-Guide.md`'s "Important Scale and Position Notes" section. Zrod's placement math is intentionally identical to Zcylinder's.

When topology behavior is ambiguous, consult `gaiaviz-skill/references/structure/Topology-Guide.md` first. If not covered there, derive from first principles and note the choice in the commit message.

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
Run: `conda run -n glyphviz python main.py` (Windows/Anaconda).

## GaiaViz Skill

`gaiaviz-skill/` is a Claude skill for generating GaiaViz-format CSV data — separate from the visualizer but sharing the same data contract. Treat `gaiaviz-skill/references/` as the authoritative spec for the 94-column node format.
