# Quickstart

This page walks through the smallest possible end-to-end GlyphViz workflow: a node CSV in, a rendered 3D scene out. It assumes you've already completed [Installation](installation.md).

=== "GUI (Windows executable)"

    ## 1. Launch GlyphViz

    Open GlyphViz from the Start menu or the folder you extracted it to. You'll see the **Viewer** (the main 3D scene window), with the **Node Panel** and **Properties Panel** docked to the side.

    !!! warning "Placeholder — exact panel layout pending"
        The default window layout, panel names, and docking arrangement described here need to be confirmed against the actual GUI. See the [Reference](../reference/index.md) section once it's filled in from the real interface.

    ## 2. Load a scene

    Use the **File → Open** menu (or the equivalent toolbar button) to load a node CSV. If you don't have one yet, GlyphViz ships with a small demo scene — look for a **File → Open Demo Scene** option, or load one of the samples from the [Examples Gallery](../examples/index.md).

    ## 3. Navigate the Viewer

    Once a scene is loaded, you can orbit, pan, and zoom around it with the mouse.

    !!! warning "Placeholder — exact mouse bindings pending"
        The specific mouse/keyboard bindings for orbit, pan, and zoom need to be confirmed and documented in [Viewer Navigation](../reference/viewer-navigation.md).

    ## 4. Inspect and edit a node

    Click any node in the Viewer to select it. Its properties appear in the **Properties Panel**, where you can adjust things like color, scale, and geometry. The **Node Panel** shows the full hierarchy as a tree you can navigate directly.

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
