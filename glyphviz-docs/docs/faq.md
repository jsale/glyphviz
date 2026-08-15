# FAQ

Questions that have come up repeatedly while building GlyphViz and its documentation — not a formal support channel, just the things worth answering once and pointing people at.

## General

??? question "What is GlyphViz, in one sentence?"
    A 3D hierarchical visualization toolkit: it renders structured data — node hierarchies, time series, gene networks, EEG fields, strange attractors — as a navigable 3D scene where hierarchy *is* spatial nesting, not a diagram drawn on top of a chart. See [Core Concepts](getting-started/core-concepts.md) for the full idea.

??? question "Is GlyphViz a fork of ANTz or GaiaViz?"
    No. GlyphViz is written from scratch in Python, targeting the same CSV data contract and scene-graph behavior as ANTz and GaiaViz as a foundation, then extending past it with capabilities neither has (Plot/Surface topologies, World Grids, Channels animation, stereo 3D, and more). It shares no source code with either. See [Architecture](architecture/index.md) for the full split between what's inherited and what's original.

??? question "Is it a charting library, like Plotly or Matplotlib?"
    No, and it isn't trying to be — those tools already do 2D statistical charts better than GlyphViz ever will. GlyphViz's niche is narrower and stranger: treating a data hierarchy as a navigable 3D space in its own right. See the [Roadmap](roadmap.md)'s opening framing.

??? question "Who is GlyphViz for?"
    Anyone with hierarchical, relational, spatiotemporal, or higher-dimensional data who wants to explore it as a real 3D structure rather than a flat plot — the [Examples Gallery](examples/index.md) spans EEG signal fields, gene/organization networks, GPS tracks, crystallography, audio-driven "music synesthesia," and more, which is a reasonable cross-section of who's used it so far.

??? question "Is GlyphViz free?"
    Yes — download and use it. Formal licensing terms for redistribution or derivative work aren't finalized yet; ask if you have a specific use case in mind.

## Platforms & installation

??? question "Does GlyphViz run on Windows?"
    Yes — that's the primary supported platform today, distributed as a portable executable. See [Installation](getting-started/installation.md).

??? question "Does GlyphViz run on macOS?"
    Yes — a native `.app` build is available for both Apple Silicon and Intel Macs, built with the same PyInstaller pipeline as the Windows executable and rendering through macOS's built-in (if deprecated) OpenGL support. See [Installation → macOS](getting-started/installation.md#macos).

??? question "What about Linux?"
    A Linux/NVIDIA spike is done and works, including a browser-based GUI over noVNC for remote/headless boxes — audio playback doesn't work in that mode yet, which is the main reason it isn't a packaged release. Running from source works today on Linux with a working OpenGL environment.

??? question "Can I just try it without installing anything?"
    Yes — **[GlyphViz Web](https://www.iluvdata.org/glyphvizweb/)** is a full browser implementation (a from-scratch WebGL/Three.js rewrite, not a stripped port) that opens a scene from a URL with nothing to download. It reads the same native `gv_` CSV format as desktop and has closed most of the feature gap. See the [home page](index.md) for details.

??? question "Does GlyphViz work in VR?"
    Yes, and the easiest route needs no install at all: open **[GlyphViz Web](https://www.iluvdata.org/glyphvizweb/)** in a headset's browser and press **Enter VR**. Flight, two-handed grab-and-resize, controller-ray picking, in-scene labels, a wrist control panel and Channels playback all run on-headset. See [Immersive VR](reference/immersive-vr.md) for the full control reference.

    There is also an older internal OpenXR spike (`glyphviz_xr`) that drives the *desktop* app on a tethered PC-VR headset. It's where the interaction vocabulary was worked out, but it stays a spike — a headset can open a URL, which is a much lower barrier than a sideload.

??? question "Which headsets does the VR mode support?"
    Any headset whose browser supports [WebXR](https://www.w3.org/TR/webxr/). It has been **confirmed on hardware on a Meta Quest 3**. Apple Vision Pro (Safari on visionOS) provides WebXR and is expected to work, but hasn't been verified here. If the browser reports no WebXR support, the Enter VR button simply doesn't appear.

    Practical limit: expect comfortable framerates for scenes in the low thousands of nodes. Past that, the in-headset draw limit control is the lever.

## Data & compatibility

??? question "Will GlyphViz open my existing ANTz or GaiaViz CSV files?"
    Yes — GlyphViz reads genuine ANTz/GaiaViz-format files (`np_node.csv` and friends, including the full 94-column dialect) directly, no conversion step. See [ANTz & GaiaViz Format Notes](architecture/antz-gaiaviz-format-notes.md) for the handful of places the two upstream formats disagree with each other, and which convention GlyphViz applies where.

??? question "Do I need to use all 94 ANTz columns to build my own scene?"
    No — that's a compatibility *write* format, not GlyphViz's own data contract. A native `gv_` scene needs only about 20 required columns; everything else has a documented, sensible default. See `glyphviz-skill/references/node-csv-format.md` (or just use the [Claude Skill](getting-started/installation.md#claude-skill), which knows this already).

??? question "How big a dataset can GlyphViz handle?"
    Comfortably into six figures of nodes on the desktop renderer — the [Vehicle Sales example](examples/vehicle-market-galaxy.md) is built from a 559,000-row source CSV. Rendering performance work (vectorized transforms, display-list caching, frustum culling, a fast Channels-playback path) has specifically targeted large-scene responsiveness; see the [Roadmap](roadmap.md) for what's still ahead there.

## Claude / AI integration

??? question "What's the GlyphViz Skill?"
    A [Claude](https://claude.ai) Skill that teaches Claude how to generate and validate GlyphViz scene CSVs directly from a dataset and a description of what you want — required columns, topology choice, color/palette wiring, tags, Channels animation, all checked against the same rules the app itself expects. Several examples in the [Examples Gallery](examples/index.md) were built with it. Download and install steps: [Installation → Claude Skill](getting-started/installation.md#claude-skill).

??? question "Do I need to know the CSV format to use GlyphViz well?"
    Not to get started — the Claude Skill can produce a working first scene from a plain-language description of your data. Knowing the format (topologies especially) becomes valuable once you want to hand-tune a result or design a custom glyph; the [Guided Tour](getting-started/guided-tour.md) covers that hands-on.

## Project direction

??? question "Is there a public roadmap?"
    Yes — see [Roadmap](roadmap.md). Near-term: an AI-to-topology suggestion bridge, and deepening the [WebXR immersive mode](reference/immersive-vr.md) that shipped in 2026-08 (passthrough AR, hand tracking, authoring gestures). Longer-term and more speculative: data-to-sound mapping, collaborative multi-user scenes, and richer non-Euclidean topologies. None of it is a committed schedule.

??? question "Is there a public API?"
    Not yet, and it's deliberately low on the priority list — see the [Roadmap](roadmap.md#near-term) for why. Most people generating scenes today are better served by the Claude Skill or by editing CSVs directly than by a Python API GlyphViz isn't ready to make stability promises about.

??? question "I found a bug, or have a feature idea — where does that go?"
    There isn't a public issue tracker set up for this yet. For now, that feedback goes directly to the developer.
