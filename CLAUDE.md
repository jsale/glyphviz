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

3. **Z-topology variants** — `TOPO_ZCUBE/ZSPHERE/ZTORUS/ZCYLINDER/ZROD` (ids 9–13) and `TOPO_VIDEO` (15) are defined in the enum but not yet implemented in `topology.py`.

4. **Workflow polish** — Save edits back to CSV, undo/redo, multi-select, table search/filter.

5. **VR/AR/XR** — Long-term goal: an immersive viewer. No codebase exists yet; desktop 3D is the current focus. Flag any architectural decisions that would make a future XR port harder.

## Topology Inventory

18 types defined in `glyphviz/topology.py`. Implemented: None (0), Cube (1), Sphere (2), Torus (3), Cylinder (4), Pin (5), Rod (6), Point (7), Plane (8), Spiral (14), Plot (16), Surface (17). Not yet implemented: ZCube (9), ZSphere (10), ZTorus (11), ZCylinder (12), ZRod (13), Video (15).

When topology behavior is ambiguous, consult `gaiaviz-skill/references/structure/Topology-Guide.md` first. If not covered there, derive from first principles and note the choice in the commit message.

## Collaboration Notes

- Address the developer as **Jeff**, not "the user."
- Jeff has strong domain vision but sometimes feels uncertain about feature prioritization. When the backlog is long, offer a ranked recommendation with brief rationale rather than presenting an open-ended menu of choices.
- Verification of math/picking/camera fixes uses the temp-CSV-through-real-app-objects pattern; see the auto-memory for details.

## Tech Stack

Python 3.12, PySide6 (Qt6), PyOpenGL, numpy, pandas.
Run: `conda run -n glyphviz python main.py` (Windows/Anaconda).

## GaiaViz Skill

`gaiaviz-skill/` is a Claude skill for generating GaiaViz-format CSV data — separate from the visualizer but sharing the same data contract. Treat `gaiaviz-skill/references/` as the authoritative spec for the 94-column node format.
