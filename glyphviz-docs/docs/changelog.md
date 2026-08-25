# Changelog

GlyphViz doesn't cut numbered releases yet — development moves in daily commits rather than versions, so this changelog is organized by date, newest first, generated from the project's git history. Windows app builds are separately dated (`GlyphViz<YYYYMMDD>.zip`, see [Installation](getting-started/installation.md)); the dates below track everything that shipped into the codebase, which is more granular than the app builds themselves. Purely internal housekeeping (gitignore tweaks, dev-environment notes) is omitted.

## 2026-08-24

- **Objects can now be viewed from the inside.** Four new geometries — **Sphere (Interior)**, **Cube (Interior)** and **Cylinder (Interior)** capped or open — draw a shape's inner surface instead of its outer one, so you can fly the camera into it and watch a texture or a video wrap around you: a 360° video sphere, a cylindrical panorama, a video room. Pick one from the Geometry dropdown, cycle to it with **O**, set it in the `geometry` column, or animate it through Channels; it is an ordinary geometry in every respect, so a Link carrying one becomes a tube you can fly down. See [Interior geometries](reference/geometries.md#interior-geometries-seen-from-within).
- This is deliberately *not* the same as switching off back-face culling. Looking at the inside of an ordinary shape is a mirror view, so a video seen that way plays backwards — text and faces reversed. The interior geometries are built mirrored, so the image reads the right way round from within; they draw unlit, so the footage comes through at its own full brightness instead of at roughly half of it under scene lighting; and they stay single-sided, which keeps translucent objects blending correctly.
- The interior cylinder's **End caps** are a checkbox in the Properties panel: off for an open tube, on to close both ends and map the texture across them. It is stored as the geometry itself, so the choice saves and loads with the file rather than needing a column of its own.

## 2026-08-21

- **New tool: the [Timeline Tower Designer](reference/timeline-tower.md).** Drop your X (Twitter) archive onto a browser page and it becomes a **Timeline Tower** — a single hyperglyph of everything you have ever posted. Each post is a needle radiating from a vertical time axis: height is when it was posted, bearing is the time of day it was posted, colour is whether it was an original, a reply, a repost or a quote, and concentric rings riding each needle carry likes, reposts, hashtags, links, uppercase, punctuation and your own keyword hits. Because a ring always sits at the same distance from the axis, one ring followed up the tower is one variable followed across a whole life. Every needle links back to the real post, so **U** opens it on X. **Nothing is uploaded** — the page has no network code in it at all and works offline; your archive is read in the browser and stays there.
- Three layouts share that mapping. **Tower** is the classic form, read from the outside. **Immersive** turns it inside out — the needles hang inward off a cylindrical wall so you stand at the centre of your own history, which is what it was built for in VR. **Helix** winds time as a spiral, one turn per year, so seasons stack vertically and the record never doubles back; it reads like tree rings, and time of day survives as the needle's pitch.
- The design is not new — it was built for ANTz in 2018 — but the data behind it is better: the X archive is complete where the API capped a timeline at the last 3,200 posts, and it carries a per-post repost count the API never returned, which is why there is a reposts ring now that the original could not draw.
- The same scenes can be built from a terminal with `twitter_lab/tut.py`, which is the reference implementation the browser tool is checked against.

## 2026-08-18

- **Tag label text size is now adjustable** (Properties panel → Display → **Tag Text Size**): a slider from 6 to 36 points covering every label in the scene. Like Tag Color, it is scene data — it saves with the file, so a scene's labels are the size its author chose — and it is bindable as a Channels attribute on the World row.
- **Labels are two points bigger by default** (9 pt → 11 pt). Tag text was previously painted at a fixed size that read a little small at a normal working distance; every existing scene picks up the larger default on open, with no file change needed.
- Added the **[Trust Network](examples/trust-network.md)** example — the Bitcoin OTC web of trust, where every one of the 922 traders is a three-level *hyperglyph* rather than a coloured dot: two hubs at its poles for ratings received and given, and a spoke per band of the trust scale, sized by how many ratings fell in it. Reputation becomes a shape you can compare across the scene. Its 17,235 signed ratings are drawn as links that carry their rating in geometry, and the whole marketplace grows from 13 traders to 922 under Channels playback, with the layout re-solving as it goes.

## 2026-08-17

- **GlyphViz can now lay out a network graph in three dimensions.** Two new modules — `glyphviz_core/graph.py` and `glyphviz_core/graph_layout.py` — take an edge list and produce world positions a node CSV uses directly: ForceAtlas2, Fruchterman–Reingold, PivotMDS for initialization, Louvain community detection, and Gephi's k-core and edge-weight filters. It runs on the generator side, so nothing changes in the app itself; see the new [3D Graph Layout](reference/graph-layout.md) reference. The one thing that had to change for three dimensions is worth knowing if you bring your own graph: ForceAtlas2's repulsion falls off as 1/d, which is the Coulomb law *of the plane*, and used unchanged in 3D it collapses a graph into the dense hairball that gives 3D graph drawing its bad name. `repulsion_falloff=2.0` restores the real inverse-square law and is the single most important setting in the module.
- Added the **[Collaboration Networks](examples/collaboration-networks.md)** example, two scenes built with it: 3,931 condensed-matter physicists and the 10,223 collaborations between them, and the 379-author network-science community with the ForceAtlas2 solver's own history bound to Channels — press play and the layout crystallises out of a random cloud. Community is encoded as colour *and* as geometry, so **Select By → Geometry** pulls out a whole sub-network, and each scene carries its key as real glyphs in the scene.
- **Fixed the camera locking up while Follow Selected was on.** With camera smoothing enabled and **F** active, orbiting and zooming did nothing at all — following a node was re-pointing the camera's goal at its own lagging position on every frame, which cancelled the glide before it could run. Following now tracks only what it should, the pivot, and navigation behaves exactly as it does with Follow off.
- **Fixed label columns being read as numbers.** A `text` or `link` column holding digits — a year, an ID, a measurement — was inferred as numeric on load, so `2016` came back as `2016.0` and was written that way on the next save. Label columns are now always read as text.

## 2026-08-15

- **GlyphViz Web now runs in VR**, and the docs now cover it: [Immersive VR](reference/immersive-vr.md) is a new reference page for the browser app's WebXR mode. Open the site in a headset's browser and press **Enter VR** to stand inside the scene — thumbstick flight, one-handed grab-drag and two-handed resize, controller-ray picking, in-scene labels, a wrist-mounted control panel with the Channels transport and the draw-limit lever, and Channels playback on-headset. No app to sideload and no PC-VR link; it's a URL someone can send you. Confirmed on hardware on a Meta Quest 3; any WebXR-capable headset browser, Apple Vision Pro included, should work the same way. The [Roadmap](roadmap.md) and [FAQ](faq.md) are updated to match — WebXR was listed there as the near-term target, and it has landed.
- **Filled in the two placeholder tool references.** [Glyph Composer](reference/glyph-composer.md) now documents the level model, every per-level parameter, the Topo Scale Auto fit, link levels, the preview behavior, and the template format. [Hyperglyph Generator](reference/hyperglyph-generator.md) covers the dialog, the seed/randomize workflow, Idle Motion, Capture live orientation, how designs are actually chosen (geometry families, palette schemes, the topology pool), and the `hyperglyph_lab/` batch CLI with its ratings-and-mutation loop. The Reference index gained a **Glyph authoring tools** group, and the Tools menu reference was missing its Hyperglyph Generator row.
- **New tool: the [Hyperglyph Tree Designer](reference/tree-designer.md).** A browser tool for designing branching, tree-like hyperglyphs — trees, ferns, corals, dendrites — and exporting them as Glyph Composer templates. It runs entirely in the page, with a live 3-D preview beside the template JSON, and it's a 3-D port of the branching engine from the 2-D [Fractal Forest](https://www.iluvdata.org/fractalforest/) drawing tool, keeping that tool's controls: Branch angle, Angle random, Length scale, Base width, Width scale, blossoms. Every branch continues its parent's direction, deviated by the branch angle, which is what makes the results read as trees rather than as clusters. Fork twist rotates each fork's plane in 3-D — set it to 0 for a flat, 2-D-style tree. Branching points are ordinary objects and the limbs between them are Link nodes, so a limb can be a cylinder, a cone, a pin or a cube. Fourteen presets included. Download the template, then **Tools → Glyph Composer → Load Template…**, or paint whole forests with it via **Use as Draw Brush**.
- **The Glyph Composer can now build Links.** Every level below the root has a **Link to Parent** option that gives each object at that level a connector back to its parent, drawn as any geometry stretched between the two. Links take their object's color by default, or a color of their own — brown limbs under a bright canopy. Combined with the level's altitude offset, this is what turns a composed glyph from a stack of touching shells into a jointed, branching structure. Templates saved before this load with links off and generate exactly as they did.
- **Links can now be any geometry.** A Link (the connector between two objects) used to draw as a thin line or a textured prism and nothing else; it now renders whatever geometry you give it, stretched between its two ends — a cylinder rod, a tapering cone, a wireframe cage, an imported mesh, or any other shape distorted along the connection axis. This is what ANTz always did, and it makes an edge able to carry shape as well as connection, which opens up far more lifelike hyperglyph structures. Press **O** / **Shift+O** with a link selected to cycle through the lot. `ratio` is the connector's thickness whatever geometry it carries, and the endpoint distance is its length. See [Geometries](reference/geometries.md#geometry-on-a-link-node).
- **PDB protein import now produces true ball-and-stick**: bonds render as real 3-D rods between the atoms rather than thin lines.
- **Fixed a long-standing picking bug**: clicking an object that had a link attached selected the *link* instead, and a rubber-band selection could miss the object entirely. Depending on the object's shape it could be impossible to select with the mouse from any angle, which is why it looked like it depended on the camera angle. The pick pass was drawing an invisible target at each link's own position — which is exactly where its first object sits.

## 2026-08-14

- Added **Save Selection As…** (**Ctrl+Alt+S**): write the selected objects out to a node CSV of their own, keeping them exactly where they sit. Saving a subset naively would relocate it — an object whose parent stayed behind reloads as a root, and a root's position is read literally instead of through its parent's topology — so the export bakes each detached object's world placement into its own transform by default. Selected objects bring their descendants (and any links joining two of them) along, and matching tag and Channels files are written beside it.
- Rebuilt the **Pin** glyph to ANTz's actual shape: a true apex, a dome sitting flush on the cone's rim, no holes at either end, and 48% fewer triangles. Its tip now sits on the object's own origin, which is what lets Pin-topology children ride the shaft — note this moves existing pins up by about one glyph height.
- Gave the **Hyperglyph Generator** a **Save Recipe…** button: a generated design writes out as a Glyph Template `.json`, the same format **Tools → Glyph Composer → Load Template** opens — so a randomized hyperglyph you like can be reopened and reworked level by level instead of only being inserted as-is. The file is named for its seed, which is what makes the design reproducible.
- Added **Capture live orientation** (on by default) next to it: with Idle Motion running, the preview is spinning when you click Save, and this writes the pose it had reached rather than the orientation it was generated with. A recipe stores one rotation per *level* while Idle Motion gives every node its own axis and speed, so the trunk is captured exactly and each deeper level takes its first node's orientation; uncheck it to save the design as generated. A recipe carries no rate fields either way, so a saved one is always static.
- Warned before handing a very large hyperglyph to the Glyph Composer: designs over ~2,000 nodes render fine but rebuild their whole tree after every Composer edit, so the Generator now flags the count and suggests turning Auto Preview off.
- Gave newly created objects **ANTz's row-wrapping placement**: each new object steps along `translate_x`, and when the next step would reach a full lap (360) it restarts at 0 while `translate_y` steps to the next row. Repeated **N** / **Shift+N** now array into a grid instead of running off in a line — and, more usefully, the child that completes a lap around a Sphere, Torus or Cylinder parent starts a *new ring* instead of landing exactly on top of the first one.
- Added **Placement Step** and **Placement Z** to the Properties panel's New Object Defaults — the two numbers ANTz hardcoded. Placement Step sets how far apart consecutive objects sit (5 by default; type 15 for ANTz's own 24-per-ring lattice); Placement Z sets the `translate_z` each is born with, as two values, since the axis means height above the world plane for a root object but stand-off distance from the parent for a child. Both apply to N, Shift+N, the New Node / New Child buttons, paste, and mesh import.
- Added optional **camera smoothing** (Properties panel → Camera): navigation gets a weighted glide instead of snapping frame-to-frame. It's **off by default**, and it's ANTz's idea done coherently — ANTz eased the camera's position while applying the orbit angle instantly, so the object you were orbiting swung out of frame for a second or so; here the whole camera rig eases under one time constant, and the object you're orbiting stays put. Two presets (Off / ANTz) and a scope selector for which gestures it applies to. Beyond looking smoother in demos, it buffers hand tremor.

## 2026-08-13

- Taught the **Glyph Composer** per-level Topology Scale, with an **Auto** setting that fits it for you. The Composer describes child placement in one vocabulary — a 0–360 sweep — but the parent's topology decides whether that's degrees or world units, so choosing Cube, Pin, Plane or None used to fling a level's children roughly 300× the parent's radius away. Auto (on by default) applies the ANTz scale exactly when a sweep is about to be read as a distance. Templates saved before this load onto Auto, so a design that came out broken now regenerates correctly.
- Applied the same fit to the **Hyperglyph Generator**, which had the same problem under Pin parents: across a 200-design sample it re-fitted 67 levels and pulled 62 designs (31%) back in by 7.5×–117×. Saved recipes regenerate as the corrected design.
- Stopped the Glyph Composer's preview camera resetting on every edit — zoom in on a detail and it stays there. Re-framing is now explicit: a **Reset View** button, a freshly loaded template, or the first preview.

## 2026-08-12

- Added **Topology Scale** (Properties panel, under Topology): a per-node control over how far one unit of a *child's* `translate` reaches, for the axes a topology reads as a distance rather than an angle. It fixes the long-standing surprise where changing a parent's topology — by hand, or from a Channels track — flung its children off into empty space: values authored as degrees (0–360) are enormous when the new topology reads them as world units. Angular axes (longitude, latitude, orbital and tube angles) are never scaled, so turning it down can't distort a circular layout. The **ANTz** preset (1/180) reproduces ANTz's convention, where a linear axis spans the parent's own extent — a cube facet is 360 units across — and is the setting at which a layout survives switching between an angular and a linear topology. **Existing scenes are unaffected:** the default, and what any file without the new column loads as, is the behavior GlyphViz has always had. Also bindable as a Channels attribute, and a status-bar hint now names the control when a topology change does scatter a subtree.
- Added a Draw Mode walkthrough to the [Guided Tour](getting-started/guided-tour.md), including painting Glyph Composer hyperglyphs as brushes.

## 2026-08-11

- Added **Draw Mode** (**D** key, or the Properties panel's Draw Mode button): paint objects into the scene with the mouse. A click stamps one object — built from the New Object Defaults — onto the World Grid where the cursor lands; a drag stamps a trail of them at a configurable pixel spacing, and **Draw Z** sets each object's elevation. Stamped objects are real grid children, so a drawn scene saves and reloads like any other.
- Made Draw Mode stamp whole **hyperglyphs**: the new **Stamp** combo takes any Glyph Composer template (via its **Load…** button, or the Glyph Composer's new **Use as Draw Brush** button, which sets the brush and turns Draw Mode on in one press), planting the full hierarchy per click. New **Heading Jitter** and **Scale Jitter** controls randomize each stamp's spin and size — one draw per stamp, so hyperglyphs stay coherent — for organic, hand-scattered strokes like drawing a forest of glyph trees.
- Removed the long-standing 0.2-per-axis minimum on rendered glyph size as a default: glyphs now render at exactly the size their `scale_x/y/z` fields ask for, however small. The old clamp is still available as **View → Enforce Minimum Glyph Size (0.2)** (also in the Properties panel's Global Scale group), for when tiny nodes need to stay visible and clickable. World Grid footprints were never clamped and still aren't.

## 2026-08-05

- Added per-example downloads: every Examples Gallery page now offers a zip of just that example, and the examples that hold several scenes offer one zip per scene. The full examples set is unchanged.
- Made a dropped zip whose only payload is a `.pdb` import that structure, instead of being refused for having no node CSV.

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
