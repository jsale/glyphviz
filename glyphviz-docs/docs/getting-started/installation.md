# Installation

GlyphViz can be installed two ways. Most users should start with the executable — no Python required.

<div class="grid cards" markdown>

- :material-microsoft-windows:{ .lg .middle } **Windows executable**

    ---

    Download and run. No installation, no command line, no Python.

    [:octicons-arrow-right-24: Jump to instructions](#windows-executable)

- :material-language-python:{ .lg .middle } **CLI / Python install**

    ---

    For scripting, automation, and macOS/Linux — where the executable isn't available yet.

    [:octicons-arrow-right-24: Jump to instructions](#cli-python-install)

</div>

---

## Windows executable

GlyphViz for Windows is a **portable build** — there's no installer and nothing is written to the registry. Download the archive, extract it, and run the executable.

[:material-download: Download GlyphViz for Windows (GlyphViz20260729.zip)](https://iluvdata.org/glyphviz/versions/GlyphViz20260729.zip){ .md-button .md-button--primary }

*Windows 10/11, 64-bit · ~116 MB download, ~300 MB extracted · build 2026-07-29*

### Install and run

1. Download **[GlyphViz20260729.zip](https://iluvdata.org/glyphviz/versions/GlyphViz20260729.zip)**.
2. Right-click the file → **Extract All…**, and extract it into **its own folder** — Windows suggests `GlyphViz20260729`, which is exactly right. The archive holds `GlyphViz.exe` plus an `_internal` folder at its top level, so "extract here" into your Downloads folder would scatter them.
3. Open the extracted folder and run **`GlyphViz.exe`**.

    !!! tip "Keep the folder together"
        `GlyphViz.exe` needs `_internal` and everything beside it. Move or copy the whole folder — don't pull the `.exe` out on its own. Right-click `GlyphViz.exe` → **Show more options → Send to → Desktop (create shortcut)** if you want a launcher.

4. To upgrade later, extract the newer dated archive into its own folder. Nothing carries over from the old one and nothing needs uninstalling — your scenes and CSVs live wherever you saved them, not inside the app folder.

You'll land in the GlyphViz GUI — the Viewer, the Node Table, and the Properties panel are all available immediately. See the [Reference](../reference/index.md) section for a full guide to the interface.

!!! note "Windows Defender / antivirus warning"
    Windows-built executables from tools like PyInstaller are sometimes flagged by antivirus software as a false positive on first run. You may also see a **Windows protected your PC** SmartScreen dialog — click **More info → Run anyway**. If GlyphViz is blocked or deleted after downloading, add an exclusion for the GlyphViz folder in Windows Security under **Virus & threat protection → Manage settings → Exclusions**, then try again.

### Example scenes

The example scenes are a separate download — 23 ready-to-open GlyphViz scenes covering World Grids and globes, Channels animation, tags, all 18 topologies, plots and surfaces, color palettes, audio and video textures, and real datasets (seismicity, EEG, sleep and biometrics, school testing, terrain, terrorism events, vehicle auctions, protein structures, RSS news). Most ship with the generator script that produced them.

[:material-download: Download the examples (GlyphVizExamples20260729.zip)](https://iluvdata.org/glyphviz/examples/GlyphVizExamples20260729.zip){ .md-button }

*~212 MB download, ~340 MB extracted*

1. Download **[GlyphVizExamples20260729.zip](https://iluvdata.org/glyphviz/examples/GlyphVizExamples20260729.zip)**.
2. Extract it into its own folder — the archive puts each example at its top level, each one self-contained. Keep each example's folder structure intact so its scene finds its own data and media.
3. In GlyphViz, use **File → Open** and pick an example's node CSV — the file ending in `_gv_node.csv`. Companion tag and channel files load automatically, so leave them next to the node CSV. A few of the larger examples hold several scenes, one per sub-folder.

Good first ones: `Topology_Example` (every topology side by side), `Palette_Example` (the built-in color palettes), and `SD_Seismicity_Example` (a real World Grid you can flip between flat map and globe). See [Quickstart](quickstart.md) for the walkthrough.

### macOS

!!! warning "No macOS executable yet"
    GlyphViz's rendering layer (`glyphviz_gl`) currently depends on the legacy fixed-function OpenGL pipeline, which macOS no longer accelerates natively. A packaged macOS executable isn't available until the render pipeline is modernized to use VBOs/VAOs and GLSL shaders. In the meantime, macOS users can run GlyphViz from source — see [CLI / Python install](#cli-python-install) below — though rendering performance and compatibility may be limited until that work lands.

### Next step

Jump to [Quickstart](quickstart.md) to open your first scene in the GUI.

---

## CLI / Python install

This path is for macOS and Linux users, contributors, and anyone scripting GlyphViz rather than using it interactively.

### Requirements

- Python 3.10 or later
- A working OpenGL environment (most desktop systems have this already; headless/server environments need an offscreen context — see [Headless & CI Environments](#headless-ci-environments) below)

### Install from PyPI

!!! note "Placeholder"
    GlyphViz is not yet published to PyPI. This section will be updated once a release is cut. For now, install from source (below).

```bash
pip install glyphviz
```

### Install from source

Clone the repository and install in editable mode:

```bash
git clone https://github.com/YOUR-ORG/glyphviz.git
cd glyphviz
pip install -e .
```

This installs `glyphviz_core` and `glyphviz_gl`. If you're working with XR/VR rendering, also install the XR extra:

```bash
pip install -e ".[xr]"
```

### Verifying your installation

Run the version check:

```bash
glyphviz --version
```

And render a quick test scene to confirm your OpenGL setup works:

```bash
glyphviz render --demo
```

If you see a 3D scene window open with a simple test hierarchy, you're set. If nothing renders or you get an OpenGL context error, see [Headless & CI Environments](#headless-ci-environments) below.

### Headless & CI Environments

!!! note "Placeholder"
    Detailed guidance on offscreen rendering (EGL headless, OSMesa, or Xvfb as a virtual display) for CI pipelines and the `--export-frame` screenshot pipeline will be added here once finalized.

### Next step

Head to [Quickstart](quickstart.md) — the CLI workflow is covered there alongside the GUI workflow.
