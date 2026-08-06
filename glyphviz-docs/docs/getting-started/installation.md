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

- :material-robot-outline:{ .lg .middle } **Claude Skill**

    ---

    Teach Claude to generate and validate GlyphViz scene CSVs directly from your data.

    [:octicons-arrow-right-24: Jump to instructions](#claude-skill)

</div>

---

## Windows executable

GlyphViz for Windows is a **portable build** — there's no installer and nothing is written to the registry. Download the archive, extract it, and run the executable.

[:material-download: Download GlyphViz for Windows (GlyphViz20260806.zip)](https://iluvdata.org/glyphviz/versions/GlyphViz20260806.zip){ .md-button .md-button--primary }

*Windows 10/11, 64-bit · ~165 MB download, ~408 MB extracted · build 2026-08-06*

### Install and run

1. Download **[GlyphViz20260806.zip](https://iluvdata.org/glyphviz/versions/GlyphViz20260806.zip)**.
2. Right-click the file → **Extract All…**, and extract it into **its own folder** — Windows suggests `GlyphViz20260806`, which is exactly right. The archive holds `GlyphViz.exe` plus an `_internal` folder at its top level, so "extract here" into your Downloads folder would scatter them.
3. Open the extracted folder and run **`GlyphViz.exe`**.

    !!! tip "Keep the folder together"
        `GlyphViz.exe` needs `_internal` and everything beside it. Move or copy the whole folder — don't pull the `.exe` out on its own. Right-click `GlyphViz.exe` → **Show more options → Send to → Desktop (create shortcut)** if you want a launcher.

4. To upgrade later, extract the newer dated archive into its own folder. Nothing carries over from the old one and nothing needs uninstalling — your scenes and CSVs live wherever you saved them, not inside the app folder.

You'll land in the GlyphViz GUI — the Viewer, the Node Table, and the Properties panel are all available immediately. See the [Reference](../reference/index.md) section for a full guide to the interface.

!!! note "Windows Defender / antivirus warning"
    Windows-built executables from tools like PyInstaller are sometimes flagged by antivirus software as a false positive on first run. You may also see a **Windows protected your PC** SmartScreen dialog — click **More info → Run anyway**. If GlyphViz is blocked or deleted after downloading, add an exclusion for the GlyphViz folder in Windows Security under **Virus & threat protection → Manage settings → Exclusions**, then try again.

### Example scenes

The example scenes are a separate download — 53 ready-to-open GlyphViz scenes covering World Grids and globes, Channels animation, tags, all 18 topologies, plots and surfaces, color palettes, audio and video textures, and real datasets (seismicity, sleep data, school testing, terrain, terrorism events, vehicle auctions, protein structures, RSS news, hockey history, tropical cyclones, the geomagnetic field, wind climatology, radioactive decay chains, the periodic table, 43,000 galaxies, and 57 years of internet standards). Most ship with the generator script that produced them. Browse them all, with screenshots, in the [Examples Gallery](../examples/index.md).

[:material-download: Download the examples (GlyphViz_Examples.zip)](https://iluvdata.org/glyphviz/examples/GlyphViz_Examples.zip){ .md-button }

*~218 MB download, ~388 MB extracted*

1. Download **[GlyphViz_Examples.zip](https://iluvdata.org/glyphviz/examples/GlyphViz_Examples.zip)**.
2. Extract it into its own folder — the archive puts each example at its top level, each one self-contained. Keep each example's folder structure intact so its scene finds its own data and media.
3. In GlyphViz, use **File → Open** and pick an example's node CSV — the file ending in `_gv_node.csv`. Companion tag and channel files load automatically, so leave them next to the node CSV. A few of the larger examples hold several scenes, one per sub-folder.

Good first ones: `Topology_Example` (every topology side by side), `Palette_Example` (the built-in color palettes), and `SD_Seismicity_Example` (a real World Grid you can flip between flat map and globe). See [Quickstart](quickstart.md) for the walkthrough.

#### One example at a time

You don't have to take all 218 MB. Every page in the [Examples Gallery](../examples/index.md) carries its own download button, and the larger examples offer one zip per scene — so the wind rose is a 2 MB download rather than the whole set.

A single-example zip holds that one scene's files at its top level, so extracting it gives you one folder, ready to open. You can also drag the zip straight onto the GlyphViz window: it extracts beside itself and loads. Because the scene's folder is the whole archive, the file path is shorter than the one each gallery page quotes — that path is where the file sits in the full examples set.

### macOS

!!! warning "No macOS executable yet"
    GlyphViz's rendering layer (`glyphviz_gl`) currently depends on the legacy fixed-function OpenGL pipeline, which macOS no longer accelerates natively. A packaged macOS executable isn't available until the render pipeline is modernized to use VBOs/VAOs and GLSL shaders. In the meantime, macOS users can run GlyphViz from source — see [CLI / Python install](#cli-python-install) below — though rendering performance and compatibility may be limited until that work lands.

### Next step

Jump to [Quickstart](quickstart.md) to open your first scene in the GUI.

---

## Claude Skill

The **GlyphViz Skill** teaches [Claude](https://claude.ai) — Claude Code, Claude Desktop, or claude.ai with Skills enabled — how to turn your data into a valid GlyphViz scene: the required `gv_node.csv` columns, choosing a topology that fits your data's shape, color and palette wiring, tags, and Channels animation. It's the same skill the GTDB, RSS News, and NHL history examples in the [Examples Gallery](../examples/index.md) were built with — describe your dataset, and Claude generates (and validates) the CSV directly, rather than you learning the format by hand.

[:material-download: Download the GlyphViz Skill (glyphviz-skill.zip)](https://www.iluvdata.org/glyphviz/skills/glyphviz-skill.zip){ .md-button .md-button--primary }

Download **[glyphviz-skill.zip](https://www.iluvdata.org/glyphviz/skills/glyphviz-skill.zip)**, then install it one of two ways depending on which Claude you use — the zip itself is the same either way.

=== "claude.ai or Claude Desktop"

    No unzipping needed — upload the zip file itself.

    1. Open **Settings → Capabilities → Skills** (the "Customize" area of your Claude settings).
    2. Upload `glyphviz-skill.zip` directly, as downloaded.
    3. Claude unpacks and registers it for you.

    (This menu is Anthropic's, not GlyphViz's, so the exact wording may shift as Skills matures — "Customize" is the reliable landmark to look for if "Capabilities" moves.)

=== "Claude Code (CLI / IDE extension)"

    Here you extract the zip yourself into a skills folder Claude Code already looks in.

    1. Extract `glyphviz-skill.zip` — you'll get a `SKILL.md` plus a `references/` folder of format specs and an `examples/` folder of worked scenes.
    2. Place the extracted `glyphviz-skill/` folder under `.claude/skills/` — either your current project's (so it's available there only) or `~/.claude/skills/` (so it's available everywhere).

Once installed, just ask: *"Use the GlyphViz skill to visualize this CSV as a sphere of clustered categories"* — Claude reads the spec, writes the node (and tag/Channels) CSVs, and validates them before handing the file back.

The skill is native to GlyphViz's own `gv_` CSV format (not the legacy 94-column ANTz/GaiaViz dialect), so it produces scenes that open cleanly in either the desktop app or [GlyphViz Web](https://www.iluvdata.org/glyphvizweb/).

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
