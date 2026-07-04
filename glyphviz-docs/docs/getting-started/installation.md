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

!!! warning "Placeholder — link and version pending"
    The exact download URL on [iluvdata.org](https://www.iluvdata.org) and the current release version are not yet finalized in this page. Update this section with the real link once the release process is set up.

1. Download `GlyphViz-Setup.exe` (or the current release archive) from the download page on iluvdata.org.
2. Run the installer, or if it's a portable `.zip`, extract it anywhere and run `GlyphViz.exe` directly.
3. Launch GlyphViz from the Start menu (or the extracted folder).

You'll land in the GlyphViz GUI — the Viewer, Node Panel, and Properties Panel are all available immediately. See the [Reference](../reference/index.md) section for a full guide to the interface.

!!! note "Windows Defender / antivirus warning"
    Windows-built executables from tools like PyInstaller are sometimes flagged by antivirus software as a false positive on first run. If GlyphViz is blocked or deleted after downloading, add an exclusion for the GlyphViz folder in Windows Security under **Virus & threat protection → Manage settings → Exclusions**, then try again.

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
