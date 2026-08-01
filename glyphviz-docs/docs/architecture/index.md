# Architecture

"Architecture" means two different things for GlyphViz, and they have two different answers.

**Behavior and data model** — what a topology does, how a scene graph cascades transforms from parent to child, what a node CSV row means — is inherited. GlyphViz targets the ANTz/GaiaViz lineage as a foundation and is explicit about it: the [Golden-Master Validation](golden-master-validation.md) harness exists specifically to keep GlyphViz's rendering math conformant with that lineage, and the [ANTz & GaiaViz Format Notes](antz-gaiaviz-format-notes.md) page tracks the specific places the two upstream formats diverge from each other so GlyphViz can target the right one in the right context.

**Code and technology** — the actual implementation — is not inherited, because it couldn't be. GlyphViz is written from scratch in Python, and [GlyphViz Web](https://www.iluvdata.org/glyphvizweb/) is a from-scratch TypeScript/Three.js rewrite for the browser. Neither shares a line of source with ANTz or GaiaViz. The [Package Boundary](package-boundary.md) page covers how GlyphViz's own Python codebase is split — `glyphviz_core`, `glyphviz_gl`, `glyphviz_xr` — which is a GlyphViz-specific decision, not one inherited from anywhere.

Both things are true at once: GlyphViz owes ANTz and GaiaViz its data contract and its design philosophy, and owes them nothing in the codebase itself.

## What GlyphViz inherited

**ANTz**, created by Dr. Dave Warner and Shane Saxon, established the ideas GlyphViz treats as bedrock: a portable CSV node format where a spreadsheet row *is* a 3D object, a parent→child scene graph where transforms cascade down the tree, and — the idea that makes this a *hierarchical* visualizer rather than a 3D scatter plot tool — topologies, where a parent's shape decides what a child's `translate_x/y/z` even mean (longitude/latitude on a sphere, ring position on a torus, plain Cartesian offsets elsewhere). That reinterpretation-by-context is the single idea GlyphViz's entire visual model is built around, and it isn't GlyphViz's invention.

**GaiaViz**, developed by Shane Saxon and Lucas Erickson as ANTz's commercial successor, extended that format with new topologies, animation channels, and its own `np_` ("neural physics") naming convention reflecting GaiaViz's own underlying architecture — an architecture GlyphViz doesn't share and doesn't claim to. Where GaiaViz's documented conventions go further than or diverge from ANTz's, GlyphViz treats GaiaViz's reference documentation as the best available account of *behavior* it can consult (GlyphViz has no access to GaiaViz's actual source, so nothing undocumented is ever assumed), while still authoring its own data under a `gv_` prefix rather than borrowing the `np_` name for something with no shared architecture. See [ANTz & GaiaViz Format Notes](antz-gaiaviz-format-notes.md) for exactly where that line gets drawn.

Both ANTz and GaiaViz are console-native, single-scene desktop tools built around their own rendering pipelines predating GlyphViz by years — everything about *how* GlyphViz gets pixels on screen (Python, Qt, PyOpenGL's legacy fixed-function pipeline today, WebGL/Three.js in the browser, OpenXR on a headset) is a GlyphViz-era decision made independently, not a port of anything from that lineage.

## What's original to GlyphViz

Past matching the foundation, GlyphViz has gone in directions neither ANTz nor GaiaViz documents: `TOPO_PLOT` and `TOPO_SURFACE` for line/GPS/oscilloscope data and deformable heightfields, the Spiral topology (independently derived — no GaiaViz source was available to crib from), World Grid (type=6) geo-registered scenes with a flat-plate/globe toggle, the full Channels bindable-attribute set, drag-and-drop scene loading, Fetch Basemap map-imagery download, and a from-scratch OpenXR VR spike reusing the exact same `glyphviz_core` kernel the desktop app runs on. None of that is ANTz's or GaiaViz's to credit — it's covered under "Shipped" in the project's own feature-status tracking, not here.

## Pages in this section

- **[Package Boundary](package-boundary.md)** — why GlyphViz's own Python code splits into `glyphviz_core` / `glyphviz_gl` / `glyphviz_xr`, and what that boundary buys.
- **[Golden-Master Validation](golden-master-validation.md)** — how GlyphViz's rendering math is checked for conformance with the ANTz/GaiaViz scene-graph model.
- **[ANTz & GaiaViz Format Notes](antz-gaiaviz-format-notes.md)** — the specific, documented places GaiaViz's conventions moved on from ANTz's, and which one GlyphViz targets where.
