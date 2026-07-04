# GlyphViz

**A 3D hierarchical visualization toolkit for hyperdimensional data.**

GlyphViz renders structured data — node hierarchies, time series, gene networks, EEG signal fields, strange attractors — as navigable 3D scenes. It is built in the lineage of [ANTz](https://github.com/openantz/antz), extending its node/tag model into a modern Python toolkit while preserving exact rendering fidelity with the original.

GlyphViz is not a charting library. It treats *data structure as scene structure* — hierarchy becomes spatial nesting, relationships become topology, and dimensions beyond the third are recovered through projective geometry rather than discarded.

<div class="gv-hero">
  <span class="gv-sr-only">An interactive 3D scene showing GlyphViz's own node hierarchy: an indigo torus parent orbited by a teal sphere, an indigo cylinder, and a coral cone, with a smaller sphere orbiting the teal sphere as its own child node. Drag to rotate the view.</span>
  <div id="glyphviz-hero-canvas" class="gv-hero__canvas" role="img" aria-label="Live 3D render of a GlyphViz node hierarchy"></div>
  <p class="gv-hero__caption">Drag to orbit — this is a live render of GlyphViz's own node hierarchy: parent, children, and one grandchild.</p>
</div>

---

## Why GlyphViz

- **Hierarchical by design** — node and tag relationships map directly onto 3D spatial hierarchy, the way ANTz originally intended.
- **Validated, not just tested** — every release is checked against a golden-master oracle: the original ANTz C renderer, instrumented to dump its exact transformation matrices, compared frame-for-frame against GlyphViz's output.
- **Built for real scientific data** — spatiotemporal EEG, RNA-seq expression networks, longitudinal health records, and chaotic dynamical systems are first-class use cases, not afterthoughts.
- **Hyperdimensional-aware** — when your data has more than three dimensions, GlyphViz doesn't just drop the rest. Projective geometry and phase-space embedding techniques (Takens delay embedding, strange attractor reconstruction) bring higher-dimensional structure into a space you can actually navigate.
- **Desktop and XR** — a shared core (`glyphviz_core`) powers both the standard desktop renderer (`glyphviz_gl`) and immersive XR rendering (`glyphviz_xr`), so a scene you build once renders consistently everywhere.

---

## Where to start

<div class="grid cards" markdown>

- :material-rocket-launch:{ .lg .middle } **New to GlyphViz?**

    ---

    Get it installed and render your first scene in a few minutes.

    [:octicons-arrow-right-24: Quickstart](getting-started/quickstart.md)

- :material-book-open-page-variant:{ .lg .middle } **Want to understand the model first?**

    ---

    Nodes, tags, hierarchy, and how the ANTz lineage shapes everything.

    [:octicons-arrow-right-24: Core Concepts](getting-started/core-concepts.md)

- :material-image-multiple:{ .lg .middle } **Want to see what's possible?**

    ---

    Real visualizations — EEG fields, gene networks, strange attractors — with full source.

    [:octicons-arrow-right-24: Examples Gallery](examples/index.md)

- :material-map:{ .lg .middle } **Curious where this is headed?**

    ---

    WebXR deployment, an AI-to-topology bridge, and the long-range plan.

    [:octicons-arrow-right-24: Roadmap](roadmap.md)

</div>

---

*GlyphViz is under active development. This documentation site is a working scaffold — most sections are placeholders being filled in incrementally.*
