"""
Scene — node collection with lazily cached world transforms, plus the single
authoritative node_world_matrix() function used by the renderer, the picker,
and the golden-master tests.

Design contract
---------------
* node_world_matrix(node, scene) is the ONLY place world transforms are
  computed.  The renderer loads its result directly with glMultMatrixf;
  the color-ID FBO picker renders with the same call; tests compare it
  against the ANTz C oracle.  No other code path may compose node transforms.

* The 4x4 matrix produced is (row-major NumPy, translation in last column):
      T_world  @  R_world  [@  T_cap_rod]  @  S_rendered
  where S_rendered = world_scale * base_scale * [rod factors if TOPO_ROD].
  For rod nodes a cap-offset T(0,0,drz) shifts the bottom to the node's world
  origin (ANTz kNPoffsetRod convention).

* Transforms are recomputed lazily on demand via Scene._ensure(), then cached
  until Scene.invalidate() is called.  The viewport calls invalidate() at the
  start of each paint to match ANTz's per-frame recomputation, and the pick
  pass reuses the freshly-computed cache without a second invalidation.
"""

import numpy as np

from .csv_reader import load_node_csv
from .geometry_data import ROD_RADIUS_FACTOR, ROD_HEIGHT_FACTOR
from .node import Node, NON_VISUAL_TYPES
from .topology import (
    TOPO_ROD,
    compute_world_positions,
    compute_world_rotations,
    compute_world_scales,
)

_MAT_IDENTITY_3 = ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.))


class Scene:
    """Collection of nodes with lazily cached world-space transforms."""

    def __init__(self, nodes: list[Node], base_scale: float = 3.0):
        self.nodes = nodes
        self.base_scale = base_scale
        self._by_id: dict[int, Node] = {n.id: n for n in nodes}
        self._dirty = True
        self._world_pos: dict[int, tuple[float, float, float]] = {}
        self._world_rot: dict[int, tuple] = {}
        self._world_scale: dict[int, tuple[float, float, float]] = {}
        # Decomposed rotation/scale caches used by node_world_matrix to build
        # the ANTz-correct rendering matrix (see node_world_matrix docstring).
        self._parent_world_rot:   dict[int, tuple] = {}
        self._child_local_rot:    dict[int, tuple] = {}
        self._parent_world_scale: dict[int, tuple[float, float, float]] = {}

    def invalidate(self):
        """Mark cached transforms stale; they will be recomputed on next access."""
        self._dirty = True

    def register_node(self, node: Node):
        """Called after a node is appended directly to self.nodes — keeps _by_id in sync."""
        self._by_id[node.id] = node
        self._dirty = True

    def _ensure(self):
        if not self._dirty:
            return
        self._world_scale, self._parent_world_scale = compute_world_scales(self.nodes)
        self._world_rot, self._parent_world_rot, self._child_local_rot = (
            compute_world_rotations(self.nodes)
        )
        self._world_pos = compute_world_positions(
            self.nodes,
            self._placement_radius,
            self._world_scale,
            self._world_rot,
        )
        self._dirty = False

    def _placement_radius(self, node: Node) -> float:
        """Average rendered radius used for surface-topology child placement."""
        s = self._world_scale.get(node.id, (node.scale_x, node.scale_y, node.scale_z))
        avg = (s[0] + s[1] + s[2]) / 3.0
        return max(avg * self.base_scale, 0.2)

    # --- public accessors (trigger lazy compute) ---

    def world_pos(self, node_id: int) -> tuple[float, float, float] | None:
        self._ensure()
        return self._world_pos.get(node_id)

    def world_rot(self, node_id: int) -> tuple | None:
        self._ensure()
        return self._world_rot.get(node_id)

    def world_scale(self, node_id: int) -> tuple[float, float, float] | None:
        self._ensure()
        return self._world_scale.get(node_id)

    def glyph_nodes(self) -> list[Node]:
        """Nodes that represent visual glyphs (not camera/world/grid infrastructure)."""
        return [n for n in self.nodes if n.type not in NON_VISUAL_TYPES]

    def node_by_id(self, node_id: int) -> Node | None:
        return self._by_id.get(node_id)

    @classmethod
    def load(cls, path, base_scale: float = 3.0) -> 'Scene':
        """Load a GaiaViz/ANTz np_node.csv and return a Scene."""
        return cls(load_node_csv(str(path)), base_scale)


def node_world_matrix(node: Node, scene: Scene) -> np.ndarray:
    """
    4x4 float64 transform placing this node's unit geometry in world space.

    The rendering 3x3 is built as the ANTz-correct hierarchical product:

        M3 = R_parent_world @ S_parent @ R_child_local @ S_child

    where R_child_local = R_topo_base @ R_own.  This means the parent's
    non-uniform scale is sandwiched between the parent's rotation and the
    child's local frame, so a child that is oriented 90° relative to its
    parent sees a different axis stretched — matching ANTz's behavior where
    a sphere stretched along X produces a diamond-shaped child at 45° and
    a Y-elongated child at 90° (rather than always elongating along world X).

    In NumPy broadcasting:
        M3 = (R_pw * sp) @ R_lc * sc
    where sp / sc are (3,) vectors and the * broadcasts column-wise,
    i.e. (R_pw * sp)[i,k] = R_pw[i,k]*sp[k] (= R_pw @ diag(sp)) and
         (... * sc)[i,j]   = ...[i,j]*sc[j]  (= ... @ diag(sc)).

    For rod nodes the child-scale vector uses ROD_RADIUS/HEIGHT factors and
    the translation gains the cap offset (bottom of cylinder at world origin).

    This function is the single source of truth for node transforms.
    The renderer loads it with glMultMatrixf; the FBO picker renders with it;
    tests compare it against the ANTz C oracle.  It runs without a GL context.
    """
    scene._ensure()

    wx, wy, wz = scene._world_pos.get(
        node.id, (node.translate_x, node.translate_y, node.translate_z)
    )

    R_pw = np.array(
        scene._parent_world_rot.get(node.id, _MAT_IDENTITY_3), dtype=np.float64
    )
    sp = np.array(
        scene._parent_world_scale.get(node.id, (1.0, 1.0, 1.0)), dtype=np.float64
    )
    R_lc = np.array(
        scene._child_local_rot.get(node.id, _MAT_IDENTITY_3), dtype=np.float64
    )

    bs = scene.base_scale
    sc = np.array([
        max(node.scale_x * bs, 0.2),
        max(node.scale_y * bs, 0.2),
        max(node.scale_z * bs, 0.2),
    ], dtype=np.float64)

    if node.topo == TOPO_ROD:
        sc_rod = sc * np.array([ROD_RADIUS_FACTOR, ROD_RADIUS_FACTOR, ROD_HEIGHT_FACTOR])
        M3 = (R_pw * sp) @ R_lc * sc_rod
        # Cap offset: translate bottom of cylinder to world origin (ANTz convention).
        # M3[:, 2] is the rendered Z-axis vector (direction + magnitude), so adding
        # it once shifts the origin from the cylinder centre to its bottom cap.
        return np.array([
            [M3[0, 0], M3[0, 1], M3[0, 2], wx + M3[0, 2]],
            [M3[1, 0], M3[1, 1], M3[1, 2], wy + M3[1, 2]],
            [M3[2, 0], M3[2, 1], M3[2, 2], wz + M3[2, 2]],
            [0.,       0.,       0.,        1.             ],
        ], dtype=np.float64)

    # T_world @ (R_parent @ S_parent @ R_child_local @ S_child)
    M3 = (R_pw * sp) @ R_lc * sc
    return np.array([
        [M3[0, 0], M3[0, 1], M3[0, 2], wx],
        [M3[1, 0], M3[1, 1], M3[1, 2], wy],
        [M3[2, 0], M3[2, 1], M3[2, 2], wz],
        [0.,       0.,       0.,        1.],
    ], dtype=np.float64)
