# Changelog

GlyphViz doesn't cut numbered releases yet — development moves in daily commits rather than versions, so this changelog is organized by date, newest first, generated from the project's git history. Windows app builds are separately dated (`GlyphViz<YYYYMMDD>.zip`, see [Installation](getting-started/installation.md)); the dates below track everything that shipped into the codebase, which is more granular than the app builds themselves. Purely internal housekeeping (gitignore tweaks, dev-environment notes) is omitted.

## 2026-07-31

- Redesigned the home page: header carousel, a GlyphViz Web deployment call-to-action, and real (non-placeholder) content pages.
- Added the Guided Tour and rebuilt the Examples Gallery with real, generated screenshots for all 36 examples.

## 2026-07-30

- Added **Fetch Basemap**: World Grid panel button that auto-downloads map imagery (OSM streets, Esri satellite, or OpenTopoMap terrain — no API key) for a grid's lon/lat bounding box and applies it as the grid's texture.
- Added drag-and-drop loading: drop a node CSV, a scene folder, or a zip onto the window to load it (Shift+drop merges instead of replacing).
- Reworked Camera Mode flight to ANTz-style rate flight on left-drag: press point sets a bearings origin, cursor offset sets continuous forward/turn speed, flight stays locked to the horizontal plane it started on.

## 2026-07-29

- Added **Camera Mode** (free flight, **C** key), displacing the old plain-C camera cycling (moved to **Shift+C**).
- Expanded the Channels bindable-attribute set from 22 to 34 attributes.
- Added two new Channels examples and a Channels reference page to the docs site.

## 2026-07-28

- Added `tools/release.py`: one command to build, archive, publish, and re-stamp a Windows release, including rebuilding and publishing the docs site.
- Added **Scene Merge** (File > Merge Node CSV…, Ctrl+M): load a second node CSV *into* the current scene, rebasing ids so nothing collides.

## 2026-07-26

- Published the Windows app and example-scenes downloads on the Installation page.
- Made the 3D viewer's reference grid color settable per scene.
- Made tag text color settable, and added the ability to pin an individual node's tag label on regardless of scene-wide tag display settings.
- Extended tag-text drawing to Link nodes, under the same settings as any other node.
- Added a toggle to show/hide the selection bounding box without deselecting (**Ctrl+B**).
- Fixed the `\` draw-limit performance feature to actually cache per-frame scene scans, so it pays off as intended.

## 2026-07-22

- Inverted camera orbit-drag direction so dragging feels like grabbing the object, not flying around it.
- Added a status-bar tag-text display and a **Select by Tag Text** keyword search.
- Added the **CalStateTesting** example's Achievement Gap and Full Decade Cube scenes.
- Added the **YBCO Superconductor** example — the first crystallography/space-group visualization.

## 2026-07-21

- Added **Watch and Reload** (Ctrl+R): hot-reload the open node CSV whenever it changes on disk, preserving camera, selection, and Channels playback.
- Added Alt+click to open a node's link (URL, local file, or app launch).
- Added the **RSS News** example: a live multi-feed globe with article children ringing each concept cube.

## 2026-07-19

- Added the **San Diego Seismicity** example: real World Grids plus Channels time-replay of seismic events.
- Curated three Claude-Skill-generated NHL history exemplars, two of which were folded into the GlyphViz Skill itself as reference examples.

## 2026-07-18

- Added the GlyphViz Skill's `world-grid.md`, `tags-and-labels.md`, and `channels-animation.md` reference documents — the core data-format specs the Claude Skill relies on.

## 2026-07-17

- Added combined orbit+zoom camera drag and multi-camera cycling.
- Added the GlyphViz Skill's color-palette and textures/media reference documents.
- Hyperglyph Generator: assign `color_index` from a node's branch level.

## 2026-07-15

- Added video-texture audio **Solo Audio to Selection**.
- Added the **Bird Song Spectrogram Surface** example: an animated spectrogram waterfall.

## 2026-07-14

- Added ANTz-style **O/J** key cycling: step the selected node through every geometry (**O**) or topology (**J**), Shift to reverse.
- Added color palettes and `color_index`: ANTz-style **=**/**−** and **Alt+=**/**Alt+−** cycling through a node's palette.
- Added textured Link (Prism) geometry with flow animation, plus interactive Link creation.
- Adopted a real World Grid (type=6) in the GTDB Event Cloud and Time Replay examples.
- Added the GlyphViz Skill's `topologies.md` reference and the initial skill scaffold + verified node-CSV-format reference.

## 2026-07-13

- Shipped **World Grid V2** (type=6): a real, movable/rotatable/scalable geospatial reference plane with an explicit `parent_id` child-attachment model.
- Added **Globe Grid**: a World Grid's geometry can toggle between a flat plate and a sphere ("globe") form, placing the same children by lon/lat either way.
- Added a Channels playback fast path, FPS slider, and transport/panel keyboard shortcuts (measured 14x speedup on dense, mostly-static scenes).

## 2026-07-12

- Added the **Cat Scan Synesthesia** example: the first true audio-driven "music synesthesia" scene.
- Added Global Terrorism Database (GTDB) Channels scenes: Time Replay and Campaign Pulse.
- `ChannelEngine`: added animation of rate attributes (`translate_rate` / `rotate_rate` / `scale_rate` per x/y/z).
- Reorganized the audio-animation examples into per-example folders and added three more songs.

## 2026-07-07

- Global Terrorism Database example: added a rosette layout (12 evenly-spaced ring objects), a tagged octahedron root with a Tab-friendly hierarchy, and a Blue-Marble world-map ground plane aligned exactly to lat/lon.

## 2026-07-06

- Added the **Global Terrorism Database** example: organization rosettes, an event cloud, and a linked org–event network.
- Excluded World/Camera/Grid configuration nodes from bulk selection commands (Select All, etc.), so scene infrastructure can't get swept up by accident.
- Added a per-mesh geometry dropdown entry for imported meshes, and fixed mesh assignment via the dropdown.
- Auto-load a `media/` folder next to the app as the startup texture folder.

## 2026-07-05

- Vectorized scene transform math: post-edit recompute dropped from 4.5s to 0.38s at 100,000 nodes.
- Vectorized CSV loading: 8.5x faster on 100,000-node scenes (6.6s → 0.8s).
- Made node-table selection and refresh scale cleanly to 100,000+ rows.
- Removed the 500-tag cap for selected nodes and sped up tag painting roughly 4x.
- Added the **Vehicle Sales** example: three scenes built from a 559,000-row used-car auction dataset.

## 2026-07-04

- Merged **PDB protein import** (BioPython + KD-tree bond inference) — load a protein structure file directly as a glyph hierarchy.
- Added camera focus-fit framing and **Follow Selected Node** mode (**F**).
- Added the **Flocking** example: a boids simulation baked into Channels animation files.
- Moved the MkDocs documentation site source into the main repository (`glyphviz-docs/`).

## 2026-07-03

- Added the **Hyperglyph Generator** GUI tool; fixed a Z-topology clustering and scale-compounding bug found while building it.
- Added retained per-node draw-data caching in `Scene` (a "display list" for the whole scene), improving frame times on large loaded scenes.

## 2026-07-02

- Rebalanced example scene scales and geometry for the Global Scale default change (see 2026-06-29).

## 2026-07-01

- Added **Hyperglyph Lab**: a procedural music-synesthesia glyph generator (batch CLI, notebook, and GUI).

## 2026-06-30

- Added **stereoscopic cross-eye 3D** view to the Viewer panel, and fixed stereo eye rotational misalignment near top-down camera angles.
- Added the **Glyph Composer**: a hierarchical glyph template builder with live preview (Tools > Glyph Composer, Ctrl+G).
- Improved rendering performance further: display-list caching, frustum culling, and a tag-count cap.

## 2026-06-29

- Changed the Global Scale default from 3.0 to 1.0 (with a rebalance pass across affected examples over the following days).

## 2026-06-28

- Added ratio-driven Point glyph sizing and Circle/Cross/Star marker shapes; antialiased points and lines, and rounded Link/Plot line caps and joins.
- Added the **CalStateTesting**, **SES Achievement Gap Terrain**, **District Heatmap**, and **Hacking Creativity Glyph** examples.

## 2026-06-27

- Fixed Torus/Cylinder (and their Z-variants, and Spiral) child orientation so children orient with the circular path they sit on, rather than a fixed world orientation.

## 2026-06-26

- Added **GEO_MESH**: import OBJ/STL/PLY/glTF files as a glyph's rendered shape.
- Added the **Multi-Hike Race** example: a 20-hike GPS race demo over real Cowles Mountain terrain.
- Linux port spike: added an interactive browser GUI over noVNC, plus a headless NVIDIA/Linux GPU smoke-test container.

## 2026-06-25

- Fixed a multi-level non-uniform-scale distortion bug via true recursive matrix-stack composition — the fix that unblocked World Grid development.
- Added timestamped Save / Save As and the **K**-key autosave, with an optional companion tag-file save.
- Added **Copy/Paste** for nodes (**Ctrl+C**/**Ctrl+V**): duplicates a node together with its full descendant subtree.
- Added Scene World Settings: background color, 7 render modes, and fog.
- (World Grid V1 was added and then reverted the same day — its implicit root-glyph attachment design was replaced by the explicit-parenting World Grid V2 shipped 2026-07-13.)

## 2026-06-24

- Added per-node `translate_rate` / `rotate_rate` / `scale_rate`: continuous per-cycle animation without needing full Channels playback.
- Added per-node `rotation_mode`: GlyphViz's own Euler XYZ convention alongside ANTz's Heading/Tilt/Roll, defaulting new nodes to Euler XYZ while legacy files keep rendering unchanged.
- Added the **Surface Example** (Cowles Mountain DEM rendered via `TOPO_SURFACE`) and a New Object Defaults panel.

## 2026-06-23

- Implemented the Cylinder topology and all Z-topology variants; fixed a Cube `facet` CSV bug.
- Added a Facet picker to the Properties panel for Cube/Zcube children.
- Added the **Topology Example**: a child-distribution tutorial scene covering all 18 topologies.
- Added **Save Scene as PNG** (File menu, **F12**).

## 2026-06-22

- Added audio-driven Channels playback ("music synesthesia") with real audio sync — the seed of the audio/music examples line.
- Renamed GlyphViz's own native CSV prefix from `np_` to `gv_`, establishing the naming convention used ever since.
- Replaced the old `usr/images/` texture folder convention with a single `media/` folder; added animated GIF playback.
- Added audio for video textures (mix-all by default, with a solo dropdown).

## 2026-06-21

- Added texture animation to Channels, and wired Channels/texture playback into the VR spike.
- Added camera-facing tag-label billboards in VR.
- Added the **AutoSleep 2025** example (sleep/deep-sleep visualization from an AutoSleep CSV export).
- Carried a parent's per-axis world scale correctly into torus/rod/pin/cube/spiral child placement.

## 2026-06-18

- Split the codebase into `glyphviz_core` (the Qt/OpenGL-free kernel) and `glyphviz_gl` (the PySide6/PyOpenGL renderer) — the package boundary the project still uses today. See [Architecture](architecture/package-boundary.md).
- Extracted `glyphviz_xr` from the original OpenXR stereo spike script into its own package built on `glyphviz_core`.
- Added controller-ray picking with a wireframe-box selection highlight, and Touch controller navigation, to the VR spike.
- Added auto-scale so any file loaded via `--csv` gets a sensible default size.
- Loading genuine GaiaViz `np_node.csv` files directly, without a header-rewriting step.

## 2026-06-17

- Added interactive mouse manipulation (move/rotate/scale dragging); fixed a picking bug and a QPainter GL-state leak.

## 2026-06-16

- Added the channel-animation system and the **SineWave** example — Channels' first working version.
- Added video-as-texture support via Qt Multimedia.

## 2026-06-15

- Added tag text and the node-link system (labels with clickable URL/file/app links).
- Added Link lines, Plot polylines, and Surface quad-mesh rendering.

## 2026-06-14

- Added Save / Save As, writing the full GaiaViz-compatible 94-column CSV format.
- Added draw-limit culling and an FPS counter; fixed a per-frame transform bottleneck.
- Fixed non-uniform scale transforms and child placement to match ANTz's actual behavior.

## 2026-06-13

- Added ANTz-style node creation (**N** / **Shift+N**) and Create panel buttons.

## 2026-06-12

- Added multi-object selection, Select By / Select All, panel visibility toggles, and keyboard hierarchy navigation.

## 2026-06-11

- Added the ANTz-compatible 94-column golden-master test scenes that the [Golden-Master Validation](architecture/golden-master-validation.md) harness still uses today.
- Fixed wireframe picking and adopted GaiaViz's `branch_level` convention in test scenes.

## 2026-06-10

- Added the golden-master test harness itself, alongside a Scene/viewport rewrite.
- Fixed Rod placement/scaling and added topology-aware child orientation.

## 2026-06-08

- Implemented the Cube, Pin, Spiral, Plot, and Surface topologies; fixed the Rod topology.
- Switched the world to Z-up (matching ANTz's convention), added rotation editing/cascading, and expanded the glyph library.

## 2026-06-07

- **Initial commit**: GlyphViz 3D node-graph visualizer.
- Made X/Y/Z scale independently editable; fixed selection and added camera-focus UX.
