"""GlyphViz placement kernel — the app's own math, vendored for this skill.

These five modules are **byte-identical copies** of ``glyphviz_core`` in the
GlyphViz repository:

    node.py  geometry_data.py  topology.py  link_geometry.py  csv_reader.py
    scene.py

They are the real placement engine, not a reimplementation, so an answer you
compute here is the answer the app will render. A test in the GlyphViz repo
(``tests/test_skill_kernel.py``) fails if they ever drift apart.

**Never reimplement this math.** Every past attempt to hand-derive GlyphViz
placement in a notebook or a previewer has drifted from the app and produced
confident wrong answers — a sphere's half-extent guessed at 0.5, a rotation
order that did not match, degrees written into a Cartesian slot. Import this
instead.

Requires ``numpy`` and ``pandas``.

    import sys; sys.path.insert(0, "code")          # or wherever this sits
    from gv_kernel import load_node_csv, compute_world_transforms

    nodes = load_node_csv("scene_gv_node.csv")
    t = compute_world_transforms(nodes, base_scale=1.0)
    xyz = t.world_pos[t.row_of_id[42]]               # node 42 in world space

For rendered size, and for the checks that catch buried or flung children, use
``gv_extents.py`` next to this package rather than rolling your own.
"""

from .node import (
    Node, NODE_TYPE_WORLD, NODE_TYPE_CAMERA, NODE_TYPE_GRID, NODE_TYPE_LINK,
    NON_VISUAL_TYPES,
)
from .csv_reader import load_node_csv, save_node_csv
from .scene import (
    Scene, node_world_matrix, DEFAULT_SCALE_FLOOR, NO_SCALE_FLOOR,
)
from .topology import (
    compute_world_transforms,
    compute_world_positions,
    placement_offset,
    local_rotation_matrix,
    scale_linear_axes,
    LINEAR_PLACEMENT_AXES,
    TOPO_NAMES,
)
from .geometry_data import GEO_NAMES, torus_radii, ring_dims
from .link_geometry import local_z_span, DEFAULT_LOCAL_Z_SPAN

__all__ = [
    "Node", "load_node_csv", "save_node_csv",
    "NODE_TYPE_WORLD", "NODE_TYPE_CAMERA", "NODE_TYPE_GRID", "NODE_TYPE_LINK",
    "NON_VISUAL_TYPES",
    "Scene", "node_world_matrix", "DEFAULT_SCALE_FLOOR", "NO_SCALE_FLOOR",
    "compute_world_transforms", "compute_world_positions",
    "placement_offset", "local_rotation_matrix", "scale_linear_axes",
    "LINEAR_PLACEMENT_AXES", "TOPO_NAMES", "GEO_NAMES",
    "torus_radii", "ring_dims", "local_z_span", "DEFAULT_LOCAL_Z_SPAN",
]
