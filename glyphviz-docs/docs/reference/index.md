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

- **Immersive VR**

    ---

    Walking into a scene with a headset, in the browser — controls, the wrist panel, and what stands aside during a session.

    [:octicons-arrow-right-24: Reference](immersive-vr.md)

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

- **3D Graph Layout**

    ---

    Turning an edge list into a scene: force-directed layout in three dimensions, communities, and filters.

    [:octicons-arrow-right-24: Reference](graph-layout.md)

- **CLI Reference**

    ---

    For scripting, automation, and headless/CI use. Most interactive users won't need this.

    [:octicons-arrow-right-24: Reference](cli.md)

- **Claude Skill**

    ---

    Teach Claude to generate and validate GlyphViz scene CSVs from your data.

    [:octicons-arrow-right-24: Download](../getting-started/installation.md#claude-skill)

</div>

## Glyph authoring tools

Three tools for building *hyperglyphs* — designed node hierarchies read as a
single visual object. They all speak the same template `.json`, so a design can
move between them.

<div class="grid cards" markdown>

- **Glyph Composer**

    ---

    Build a glyph by hand, one level at a time, with a live preview. **Ctrl+G**

    [:octicons-arrow-right-24: Reference](glyph-composer.md)

- **Hyperglyph Generator**

    ---

    Roll whole designs procedurally, then insert or save them for editing. **Ctrl+H**

    [:octicons-arrow-right-24: Reference](hyperglyph-generator.md)

- **Hyperglyph Tree Designer**

    ---

    A browser tool for designing branching, tree-like hyperglyphs and exporting them as Glyph Composer templates.

    [:octicons-arrow-right-24: Reference](tree-designer.md)

</div>

## Your own data

Tools that turn a personal data export into a finished scene. Unlike the glyph
authoring tools above, these write a scene CSV rather than a glyph template.

<div class="grid cards" markdown>

- **Timeline Tower Designer**

    ---

    A browser tool that turns your X (Twitter) archive into a tower of everything you have ever posted. Nothing is uploaded.

    [:octicons-arrow-right-24: Reference](timeline-tower.md)

</div>

---

!!! warning "This section is being built out"
    Some Interface and Visual model pages are still placeholders pending a verification pass with Claude Code against the actual GlyphViz source and GUI — including annotated screenshots generated through the `--export-frame`-style pipeline. Content there should not yet be treated as final.
