# Reference

GlyphViz is primarily a visual, interactive tool — most users will spend their time in the GUI, not the command line. This section is organized that way: interface reference first, file format and CLI reference for scripting/automation users further down.

## Interface

<div class="grid cards" markdown>

- **Viewer Navigation**

    ---

    Mouse and keyboard controls for orbiting, panning, zooming, and selecting nodes in the 3D Viewer.

    [:octicons-arrow-right-24: Reference](viewer-navigation.md)

- **Menus**

    ---

    Every menu and menu item in the GlyphViz GUI.

    [:octicons-arrow-right-24: Reference](menus.md)

- **Properties Panel**

    ---

    Every field in the Properties Panel — what it controls and how it maps to the underlying node data.

    [:octicons-arrow-right-24: Reference](properties-panel.md)

- **Node Panel**

    ---

    The hierarchy tree view: navigating, selecting, and restructuring nodes.

    [:octicons-arrow-right-24: Reference](node-panel.md)

</div>

## Visual model

<div class="grid cards" markdown>

- **Geometries**

    ---

    Every shape a node can take, and when to use each one.

    [:octicons-arrow-right-24: Reference](geometries.md)

- **Topologies**

    ---

    How a parent node arranges its children in space.

    [:octicons-arrow-right-24: Reference](topologies.md)

- **Channels Animation**

    ---

    Playing a time series into node attributes — the complete list of what
    Channels can drive, and what cascades to children.

    [:octicons-arrow-right-24: Reference](channels-animation.md)

</div>

## Formats & scripting

<div class="grid cards" markdown>

- **ANTz Node CSV Format Spec**

    ---

    The canonical column specification behind every GlyphViz scene.

    [:octicons-arrow-right-24: Reference](antz-format-spec.md)

- **CLI Reference**

    ---

    For scripting, automation, and headless/CI use. Most interactive users won't need this.

    [:octicons-arrow-right-24: Reference](cli.md)

- **API Reference**

    ---

    `glyphviz_core`, `glyphviz_gl`, and `glyphviz_xr`, auto-generated from source.

    [:octicons-arrow-right-24: Reference](api/index.md)

- **Glyph Composer Reference**

    ---

    Reference for the Glyph Composer tool. Coming once Glyph Composer development is further along.

    [:octicons-arrow-right-24: Reference](glyph-composer.md)

</div>

---

!!! warning "This section is being built out"
    Most Interface and Visual model pages are placeholders pending a verification pass with Claude Code against the actual GlyphViz source and GUI — including annotated screenshots generated through the `--export-frame`-style pipeline. Content here should not yet be treated as final.
