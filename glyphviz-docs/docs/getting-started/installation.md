# Installation

GlyphViz can be installed several ways. Most users should start with the native app for their platform — no Python required.

<div class="grid cards" markdown>

- :material-microsoft-windows:{ .lg .middle } **Windows executable**

    ---

    Download and run. No installation, no command line, no Python.

    [:octicons-arrow-right-24: Jump to instructions](#windows-executable)

- :material-apple:{ .lg .middle } **macOS app**

    ---

    A native `.app` for Apple Silicon or Intel. Download, clear quarantine once, run.

    [:octicons-arrow-right-24: Jump to instructions](#macos)

- :material-linux:{ .lg .middle } **Linux**

    ---

    A `.AppImage` (no install) or `.tar.gz`, built with the same PyInstaller pipeline as Windows and macOS.

    [:octicons-arrow-right-24: Jump to instructions](#linux)

- :material-language-python:{ .lg .middle } **CLI / Python install**

    ---

    For scripting, automation, and contributors — or any platform if you prefer running from source over the packaged builds.

    [:octicons-arrow-right-24: Jump to instructions](#cli-python-install)

- :material-robot-outline:{ .lg .middle } **Claude Skill**

    ---

    Teach Claude to generate and validate GlyphViz scene CSVs directly from your data.

    [:octicons-arrow-right-24: Jump to instructions](#claude-skill)

</div>

---

## Windows executable

GlyphViz for Windows is a **portable build** — there's no installer and nothing is written to the registry. Download the archive, extract it, and run the executable.

[:material-download: Download GlyphViz for Windows (GlyphViz20260814.zip)](https://iluvdata.org/glyphviz/versions/GlyphViz20260814.zip){ .md-button .md-button--primary }

*Windows 10/11, 64-bit · ~169 MB download, ~409 MB extracted · build 2026-08-14*

### Install and run

1. Download **[GlyphViz20260814.zip](https://iluvdata.org/glyphviz/versions/GlyphViz20260814.zip)**.
2. Right-click the file → **Extract All…**, and extract it into **its own folder** — Windows suggests `GlyphViz20260814`, which is exactly right. The archive holds `GlyphViz.exe` plus an `_internal` folder at its top level, so "extract here" into your Downloads folder would scatter them.
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

GlyphViz for macOS is a standard `.app` bundle, built with the same PyInstaller pipeline as the Windows build. Two builds are available — pick the one matching your Mac's chip.

**Requirements: macOS 11 Big Sur or later on Intel Macs; macOS 12 Monterey or later on Apple Silicon** (every Apple Silicon Mac can run 12). The Intel floor comes from Qt itself — no PySide6 (Qt 6) build for older macOS exists — so it can't be lowered by building from source, either.

[:material-download: Download for Apple Silicon (GlyphViz-2026.8.6-macOS-arm64.zip)](https://www.iluvdata.org/glyphviz/versions/GlyphViz-2026.8.6-macOS-arm64.zip){ .md-button .md-button--primary }
[:material-download: Download for Intel (GlyphViz-2026.8.6-macOS-x86_64.zip)](https://www.iluvdata.org/glyphviz/versions/GlyphViz-2026.8.6-macOS-x86_64.zip){ .md-button }

*Apple Silicon (arm64): ~98 MB download, ~268 MB extracted · Intel (x86_64): ~117 MB download, ~382 MB extracted · build 2026-08-06*

1. Download **[GlyphViz-2026.8.6-macOS-arm64.zip](https://www.iluvdata.org/glyphviz/versions/GlyphViz-2026.8.6-macOS-arm64.zip)** for Apple Silicon (M1 and later) or **[GlyphViz-2026.8.6-macOS-x86_64.zip](https://www.iluvdata.org/glyphviz/versions/GlyphViz-2026.8.6-macOS-x86_64.zip)** for Intel, and double-click it to extract `GlyphViz.app`.
2. The app is not notarized with Apple (that requires a paid developer account), so macOS will quarantine it on first launch. Clear the flag once in Terminal:

    ```bash
    xattr -dr com.apple.quarantine ~/Downloads/GlyphViz.app
    ```

    then double-click `GlyphViz.app` normally. (Right-click → **Open** → **Open** also works on Intel Macs, but Apple Silicon requires the `xattr` route for ad-hoc-signed apps.)

3. Drag it to **Applications** if you want it to stick around.

Node CSVs can be opened with **File → Open**, dragged onto the window, or dropped onto the Dock icon.

!!! note "OpenGL on macOS"
    Apple deprecated OpenGL in macOS 10.14, but still ships it on every macOS to date, including Apple Silicon — GlyphViz renders through that built-in support. If you want to verify a particular Mac before committing to a download, the [CLI install](#cli-python-install) below has a one-line `glyphviz --check` that reports exactly what the machine's driver offers.

??? info "Building the .app yourself"
    `build_mac.sh` in the repo builds `dist/GlyphViz.app` on any Mac running macOS 11+ with Python 3.10+ installed — it creates its own throwaway venv, so it won't disturb your Python setup. The repo's `build-macos.yml` GitHub Actions workflow runs the same build on GitHub's macOS runners. One deliberate choice to know about: the build pins PySide6 to 6.7.x (the last series whose wheels support macOS 11) and numpy/scipy to their last single-wheel-per-arch series — newer releases ship an extra macOS-14-only wheel variant that pip silently prefers on new Macs, which would raise the app's minimum to macOS 14. Building with `--latest` drops all the pins for a newest-everything build (macOS 13+/14+ only).

### Next step

Jump to [Quickstart](quickstart.md) to open your first scene in the GUI.

---

## Linux

GlyphViz for Linux is a single zip holding two independent, ready-to-run builds from the same PyInstaller pipeline as Windows and macOS — pick whichever fits how you like to run downloaded software. Only x86_64 is available for now.

[:material-download: Download GlyphViz for Linux (GlyphViz-2026.8.6-Linux-x86_64.zip)](https://www.iluvdata.org/glyphviz/versions/GlyphViz-2026.8.6-Linux-x86_64.zip){ .md-button .md-button--primary }

*x86_64, ~310 MB download (AppImage ~160 MB + tar.gz ~159 MB, both included) · build 2026-08-06*

1. Download **[GlyphViz-2026.8.6-Linux-x86_64.zip](https://www.iluvdata.org/glyphviz/versions/GlyphViz-2026.8.6-Linux-x86_64.zip)** and extract it. You'll get two files — `GlyphViz-2026.8.6-Linux-x86_64.AppImage` and `GlyphViz-2026.8.6-Linux-x86_64.tar.gz`. You only need one; pick a route below.
2. **AppImage (recommended)** — no install, no further extraction:

    ```bash
    chmod +x GlyphViz-2026.8.6-Linux-x86_64.AppImage
    ./GlyphViz-2026.8.6-Linux-x86_64.AppImage
    ```

    **tar.gz** — if your system can't run AppImages (no FUSE, some containers/sandboxes):

    ```bash
    tar xzf GlyphViz-2026.8.6-Linux-x86_64.tar.gz
    ./GlyphViz/GlyphViz
    ```

    !!! tip "Keep the tar.gz folder together"
        Like the Windows build, `GlyphViz` needs the `_internal` folder extracted beside it. Move or copy the whole `GlyphViz/` folder, don't pull the executable out on its own.

You'll land in the GlyphViz GUI — the Viewer, the Node Table, and the Properties panel are all available immediately. See the [Reference](../reference/index.md) section for a full guide to the interface. Node CSVs can be opened with **File → Open** or dragged onto the window.

!!! note "OpenGL on Linux"
    Like the Windows and macOS builds, GlyphViz renders through whatever `libGL.so.1` / vendor driver your system already has — nothing GL-related is bundled. Any desktop Linux with a working X11 or Wayland session and a GPU driver should have this already; it also runs inside a properly configured Docker container with GPU/display passthrough. Verify a specific machine with `glyphviz --check` (see [Verifying your installation](#verifying-your-installation) below).

??? info "Building it yourself"
    `build_linux.sh` in the repo builds both artifacts locally — it creates its own throwaway venv, so it won't disturb your Python setup. The repo's `build-linux.yml` GitHub Actions workflow runs the same build on GitHub's `ubuntu-22.04` runners (an older LTS image, not `-latest`, to keep the produced build's glibc floor lower — see `GlyphViz-Linux.spec`'s header comment). Trigger it from the Actions tab, or push a `v*` tag to attach both artifacts to that release. An `aarch64` (ARM64) build is available as an opt-in workflow input, off by default because GitHub's ARM Linux runner pricing for a private repo wasn't confirmed free-tier at the time this was written.

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

This path is for Linux users, contributors, and anyone scripting GlyphViz rather than using it interactively. It also works on macOS (11+) and Windows if you prefer running from source over the packaged builds.

### Requirements

- Python 3.10 or later
- A working OpenGL environment (most desktop systems have this already)

### Install from PyPI

!!! note "Placeholder"
    GlyphViz is not yet published to PyPI. This section will be updated once a release is cut. For now, install from source (below).

### Install from source

Clone the repository and install in editable mode:

```bash
git clone https://github.com/jsale/glyphviz.git
cd glyphviz
pip install -e .
```

This installs the `glyphviz_core` and `glyphviz_gl` packages plus a `glyphviz` command. If you're working with XR/VR rendering, also install the XR extra:

```bash
pip install -e ".[xr]"
```

!!! tip "macOS 11 Big Sur: pin PySide6 first"
    Current PySide6 wheels require macOS 13+ (and 6.8/6.9 requires 12+), so on Big Sur a plain install pulls a Qt that won't import. Install the 6.7 series first and the GlyphViz install will keep it:

    ```bash
    pip install "PySide6>=6.7,<6.8"
    pip install -e .
    ```

### Verifying your installation

Run the version check, then the environment report:

```bash
glyphviz --version
glyphviz --check
```

`--check` opens no window — it prints your Python/Qt/OpenGL versions and confirms an OpenGL context with the fixed-function pipeline GlyphViz renders through is available. Then open a real window with a small built-in test scene:

```bash
glyphviz --demo
```

If a 3D window opens showing a sphere studded with smaller glyphs around its equator and poles, you're set. From here, `glyphviz path/to/your_gv_node.csv` opens a scene directly.

### Next step

Head to [Quickstart](quickstart.md) — the CLI workflow is covered there alongside the GUI workflow.
