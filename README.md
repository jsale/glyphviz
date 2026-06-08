# GlyphViz

GlyphViz is a 3D node-graph visualizer for [ANTz](https://github.com/Vidovicarius/ANTz)/GaiaViz CSV
data, built with PySide6 and PyOpenGL. It loads a node CSV export, lays the
nodes out in a Z-up scene matching ANTz's own coordinate convention, and lets
you inspect, select, and edit node properties interactively.

## Features

- **CSV loading** — opens ANTz/GaiaViz-style node CSV files (`File > Open Node
  CSV…`) and renders every node as a 3D glyph.
- **Hierarchical scene graph** — translation, rotation, and scale cascade
  through the parent → child chain, and surface-based topologies (Sphere,
  Torus, Rod, Point) place children directly on their parent's rendered
  surface, matching ANTz/GaiaViz scene-graph behavior.
- **Interactive 3D viewport** — orbit/pan/zoom camera, optional axes/grid
  overlays, click-to-select with a highlighted bounding glyph, and
  double-click / shift-click to focus the camera on a node.
- **Node table** — a sortable, filterable table view of every loaded node and
  its properties, synced with the 3D selection.
- **Property inspector** — edit a selected node's position, rotation, scale
  (with an X/Y/Z lock for uniform scaling), geometry, topology, torus `ratio`,
  and color, with changes reflected live in the viewport and table.
- **Geometry library** — a built-in set of glyphs (cube, sphere, cone, torus,
  dodecahedron, octahedron, tetrahedron, icosahedron, pin, cylinder, grid,
  point — each with wireframe and solid variants where applicable) rendered
  via OpenGL display lists, matching ANTz's `kNPgeo*` geometry IDs.

## Requirements

- Python 3.12
- [PySide6](https://pypi.org/project/PySide6/), [PyOpenGL](https://pypi.org/project/PyOpenGL/),
  [numpy](https://pypi.org/project/numpy/), [pandas](https://pypi.org/project/pandas/)
  (see `requirements.txt`)

> **Windows/Anaconda note:** use a dedicated conda environment to avoid
> Qt5/Qt6 DLL conflicts with Anaconda's base environment (which ships
> PyQt5/Qt5):
> ```
> conda create -n glyphviz python=3.12 pip -y
> conda run -n glyphviz pip install -r requirements.txt
> ```

## Running

```
python main.py
```

(On Windows with the conda environment above:
`C:\Users\<you>\anaconda3\envs\glyphviz\python.exe main.py`)

Then use **File > Open Node CSV…** to load an ANTz/GaiaViz node export.

## Project layout

- [`main.py`](main.py) — application entry point
- [`glyphviz/main_window.py`](glyphviz/main_window.py) — main window, menus,
  property inspector, and node table wiring
- [`glyphviz/viewport.py`](glyphviz/viewport.py) — OpenGL viewport: camera,
  rendering, picking, and overlays
- [`glyphviz/node.py`](glyphviz/node.py) — the `Node` data model
- [`glyphviz/csv_reader.py`](glyphviz/csv_reader.py) — CSV loading
- [`glyphviz/topology.py`](glyphviz/topology.py) — parent → child placement,
  rotation, and scale cascading per topology type
- [`glyphviz/geometry.py`](glyphviz/geometry.py) — glyph geometry definitions
  and the OpenGL renderer
- [`glyphviz/node_table.py`](glyphviz/node_table.py) — node table model/view
