# Package Boundary

GlyphViz's own Python code — no ANTz or GaiaViz lineage here, this split is entirely GlyphViz's own — is organized into three packages with a strict, one-directional dependency:

```text
glyphviz_core   ← glyphviz_gl   (desktop app: PySide6 + PyOpenGL)
glyphviz_core   ← glyphviz_xr   (VR spike: OpenXR)
```

`glyphviz_core` depends on neither. That's not a loose convention — it holds in practice: nothing in `glyphviz_core` imports from `glyphviz_gl` or `glyphviz_xr`, checked directly against the source rather than assumed.

## `glyphviz_core` — the kernel

Everything that defines what a GlyphViz scene *is*, independent of how it gets drawn: CSV reading and writing (`csv_reader.py`), the node/scene data model (`node.py`, `scene.py`), topology placement math (`topology.py`), the Channels animation engine (`channel_engine.py`, `channel_loader.py`), color palettes, audio analysis, mesh/PDB/basemap loaders, drag-and-drop routing, and scene-merge logic. It depends on `numpy`, `pandas`, and the standard library — nothing that draws a pixel. That's deliberate: every one of those modules is unit-testable headlessly (see `tests/`), and it's what makes the [Golden-Master Validation](golden-master-validation.md) harness possible at all — `node_world_matrix()` can be computed and checked in isolation, with no window, no OpenGL context, no Qt event loop.

## `glyphviz_gl` — the desktop renderer

The PySide6/PyOpenGL presentation layer: the main window, the 3D viewport (camera, picking, drag manipulation, drawing), the node table, texture/video/audio playback, and the tool dialogs (Glyph Composer, Hyperglyph Generator, Fetch Basemap). It consumes `glyphviz_core` as a library — a `Scene` loaded by `csv_reader.py` is what the viewport draws, a `Node`'s fields are what the Properties panel edits — but never the reverse. This is the only package that currently ships a packaged executable (see [Installation](../getting-started/installation.md)); everything platform-specific about "having a window" lives here.

## `glyphviz_xr` — the VR spike

An OpenXR renderer targeting a Meta Quest 3 over a PC-VR link: stereo rendering, thumbstick flight and grab-drag navigation, controller-ray picking, and camera-facing tag billboards. It's built on the same `glyphviz_core` kernel as the desktop app — the same CSV pipeline, the same topology math, the same channel engine — and additionally reuses `glyphviz_gl.geometry`'s OpenGL display-list shapes rather than re-authoring geometry for a third time. That single reuse is the one place the otherwise-clean core/gl/xr split bends, and it's a pragmatic one: `glyphviz_gl.geometry` has no Qt dependency itself, so importing it doesn't pull a windowing toolkit into a VR runtime that doesn't want one.

## Why this boundary, not a fork

The alternative to this package split was the one VR/XR projects reach for by default: fork the renderer, or start a separate codebase against a game engine (Unity, Unreal) built for that purpose. GlyphViz deliberately didn't, because the expensive, correctness-critical part of GlyphViz was never "how do I draw a sphere" — it's the topology placement math, the CSV format's many edge cases, and the channel-animation engine, all validated against the ANTz/GaiaViz behavioral contract. Forking would mean maintaining two implementations of that math that could silently drift apart. Because `glyphviz_xr` imports `glyphviz_core` instead of reimplementing it, a topology fix or a new Channels-bindable attribute lands in VR the moment it lands on desktop, with no second implementation to keep in sync — which is also exactly why the VR spike could prove out a working headset renderer as an internal spike rather than a multi-month rewrite.

## Where GlyphViz Web fits — and doesn't

[GlyphViz Web](https://www.iluvdata.org/glyphvizweb/) is **not** part of this dependency graph. It's a separate repository, written from scratch in TypeScript against Three.js, sharing zero source with `glyphviz_core`. That's not an oversight — a browser can't execute Python, so there was never a version of "share the kernel" available to it the way `glyphviz_xr` shares it. What GlyphViz Web shares with the Python side is the **contract**, not the code: it reads and writes the same native `gv_` CSV scene format described in `glyphviz-skill/references/`, so a scene built in one opens correctly in the other. Two independent implementations of the same file format is a real ongoing maintenance cost — a topology or Channels behavior change on the Python side has to be ported by hand to keep GlyphViz Web in sync — but it's the only option for "the same scene, no install, in a browser tab."
