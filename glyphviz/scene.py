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
from .geometry import ROD_RADIUS_FACTOR, ROD_HEIGHT_FACTOR
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

    def invalidate(self):
        """Mark cached transforms stale; they will be recomputed on next access."""
        self._dirty = True

    def _ensure(self):
        if not self._dirty:
            return
        self._world_scale = compute_world_scales(self.nodes)
        self._world_rot   = compute_world_rotations(self.nodes)
        self._world_pos   = compute_world_positions(
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

    Layout (row-major, translation in last column):
        T_world @ R_world @ [T_cap for TOPO_ROD] @ S_rendered

    S_rendered = diag(rx, ry, rz) where rx/ry/rz = world_scale * base_scale,
    with rod-factor adjustments for TOPO_ROD.  The rod cap offset T(0,0,drz)
    shifts the cylinder so its bottom sits at the node's world origin.

    This function is the single source of truth for node transforms.
    The renderer loads it with glMultMatrixf; the FBO picker renders with it;
    tests compare it against the ANTz C oracle.  It runs without a GL context.
    """
    scene._ensure()

    wx, wy, wz = scene._world_pos.get(
        node.id, (node.translate_x, node.translate_y, node.translate_z)
    )
    rot = scene._world_rot.get(node.id, _MAT_IDENTITY_3)
    (r00, r01, r02), (r10, r11, r12), (r20, r21, r22) = rot

    ws = scene._world_scale.get(node.id, (node.scale_x, node.scale_y, node.scale_z))
    bs = scene.base_scale
    rx = max(ws[0] * bs, 0.2)
    ry = max(ws[1] * bs, 0.2)
    rz = max(ws[2] * bs, 0.2)

    if node.topo == TOPO_ROD:
        drx = rx * ROD_RADIUS_FACTOR
        dry = ry * ROD_RADIUS_FACTOR
        drz = rz * ROD_HEIGHT_FACTOR
        # T_world @ R @ T(0,0,drz) @ S(drx,dry,drz)
        # Column 3 (translation): world_pos + R*(0,0,drz)
        return np.array([
            [r00*drx, r01*dry, r02*drz, wx + r02*drz],
            [r10*drx, r11*dry, r12*drz, wy + r12*drz],
            [r20*drx, r21*dry, r22*drz, wz + r22*drz],
            [0.,      0.,      0.,      1.           ],
        ], dtype=np.float64)

    # T_world @ R @ S(rx,ry,rz)
    return np.array([
        [r00*rx, r01*ry, r02*rz, wx],
        [r10*rx, r11*ry, r12*rz, wy],
        [r20*rx, r21*ry, r22*rz, wz],
        [0.,     0.,     0.,     1.],
    ], dtype=np.float64)
