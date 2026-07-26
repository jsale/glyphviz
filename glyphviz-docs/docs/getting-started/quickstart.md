# Quickstart

This page walks through the smallest possible end-to-end GlyphViz workflow: a node CSV in, a rendered 3D scene out. It assumes you've already completed [Installation](installation.md).

=== "GUI (Windows executable)"

    ## 1. Launch GlyphViz

    Run `GlyphViz.exe` from the folder you extracted. You'll see the 3D **Viewer** filling the window, with two docks alongside it: the **Node Table** (one row per node, sortable by any column) and the **Properties** panel (scene-wide display settings on top, the selected node's fields below).

    Full tours of both: [Node Panel](../reference/node-panel.md) and [Properties Panel](../reference/properties-panel.md).

    ## 2. Load a scene

    Use the **File → Open** menu to load a node CSV — the file ending in `_gv_node.csv`. Companion tag and channel files sitting next to it load automatically.

    If you don't have a scene yet, grab the example set: **[GlyphVizExamples20260729.zip](https://iluvdata.org/glyphviz/examples/GlyphVizExamples20260729.zip)** (see [Installation → Example scenes](installation.md#example-scenes)). Extract it, then open any example's node CSV. `Topology_Example` and `Palette_Example` are good first ones — small, fast, and they show the node model clearly.

    ## 3. Navigate the Viewer

    | Action | Binding |
    |---|---|
    | Orbit | Left-drag (or right-drag) |
    | Pan | Middle-drag |
    | Zoom | Scroll wheel |
    | Frame a node | Double-click it |
    | Reframe everything | **View → Reset Camera** |

    The full binding list — including selection, the Move/Rotate/Size gizmos, and the single-key shortcuts — is in [Viewer Navigation](../reference/viewer-navigation.md).

    ## 4. Inspect and edit a node

    Click any node in the Viewer to select it (Ctrl+click to add to the selection, Shift+drag for a rubber-band box). Its fields appear in the **Properties** panel's *Selected Node* group, where you can edit position, rotation, scale, color, geometry, and topology live — the Viewer repaints as you change them.

    The **Node Table** is the same selection, seen as data: a flat, sortable row per node with a `Parent` column carrying the hierarchy. Selecting in one highlights in the other; double-clicking a row frames that node in the Viewer.

    ## 5. What's next

    - [Reference](../reference/index.md) — full guide to the interface: menus, panels, geometries, and topologies
    - [Tutorial 01 — Your First Scene](../tutorials/01-first-scene.md) — a more detailed walkthrough
    - [Tutorial 04 — Mapping Real Data](../tutorials/04-mapping-real-data.md) — once you're ready to bring in your own dataset

=== "CLI (Python install)"

    ## 1. A minimal node CSV

    GlyphViz scenes are described by node CSV files following the ANTz node format. Here's a minimal three-node example — a parent with two children:

    ```csv
    id,parent_id,pos_x,pos_y,pos_z,topology,geometry,label
    1,0,0.0,0.0,0.0,sphere,pin,Root
    2,1,1.0,0.5,0.0,sphere,pin,Child A
    3,1,-1.0,0.5,0.0,sphere,pin,Child B
    ```

    !!! warning "Placeholder column set"
        The columns above are illustrative, not the verified GlyphViz/ANTz schema. Once the full [ANTz Node CSV Format Spec](../reference/antz-format-spec.md) is finalized, this example will be updated to match it exactly.

    Save this as `quickstart.csv`.

    ## 2. Render it

    ```bash
    glyphviz render quickstart.csv
    ```

    This opens the same interactive Viewer as the GUI workflow. You should see a root node with two children positioned around it. Try:

    - **Left-click + drag** to orbit the camera
    - **Scroll** to zoom
    - **Click a node** to select it and see its properties

    ## 3. Export a static image

    Rather than the interactive viewer, you can render directly to a PNG — useful for documentation, regression baselines, or quick sharing:

    ```bash
    glyphviz render quickstart.csv --export-frame output.png
    ```

    ## 4. What's next

    - [Reference](../reference/index.md) — full interface and format reference
    - [Tutorial 01 — Your First Scene](../tutorials/01-first-scene.md) — a more detailed walkthrough of the same workflow
    - [Tutorial 04 — Mapping Real Data](../tutorials/04-mapping-real-data.md) — once you're ready to bring in your own dataset
