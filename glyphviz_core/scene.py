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
      T_world  @  parent_basis  @  child_local  @  S_child  [@  T_cap_rod]
  where parent_basis (see topology.compute_world_bases) is the parent's full
  recursive rotation+scale composition down the ancestor chain. For rod
  nodes a cap-offset T(0,0,drz) shifts the bottom to the node's world origin
  (ANTz kNPoffsetRod convention).

* Transforms are recomputed lazily on demand via Scene._ensure(), then cached
  until Scene.invalidate() is called.  The viewport calls invalidate() at the
  start of each paint to match ANTz's per-frame recomputation, and the pick
  pass reuses the freshly-computed cache without a second invalidation.
"""

import math

import numpy as np

from .csv_reader import load_node_csv
from .geometry_data import ROD_RADIUS_FACTOR, ROD_HEIGHT_FACTOR
from .node import Node, NODE_TYPE_WORLD, NON_VISUAL_TYPES
from .topology import (
    TOPO_ROD,
    compute_world_bases,
    compute_world_positions,
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
        # Recursive rotation+scale caches from compute_world_bases (RAW,
        # dimensionless scale — base_scale is applied once, below, not once
        # per hierarchy level). world_basis also doubles as the matrix that
        # orients/stretches a node's children's topology offsets into world
        # space (see compute_world_positions).
        self._world_basis:  dict[int, tuple] = {}
        self._parent_basis: dict[int, tuple] = {}
        self._child_local:  dict[int, tuple] = {}

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
        self._world_basis, self._parent_basis, self._child_local = (
            compute_world_bases(self.nodes)
        )
        self._world_pos = compute_world_positions(
            self.nodes, self.base_scale, self._world_basis,
        )
        self._dirty = False

    # --- public accessors (trigger lazy compute) ---

    def world_pos(self, node_id: int) -> tuple[float, float, float] | None:
        self._ensure()
        return self._world_pos.get(node_id)

    def world_scale(self, node_id: int) -> tuple[float, float, float] | None:
        """Approximate per-axis cumulative scale (column norms of the node's
        RAW world_basis) — a camera-framing/UI hint, not exact glyph-shape
        math (see node_world_matrix for that)."""
        self._ensure()
        wb = self._world_basis.get(node_id)
        if wb is None:
            return None
        return tuple(
            math.sqrt(wb[0][j] ** 2 + wb[1][j] ** 2 + wb[2][j] ** 2)
            for j in range(3)
        )

    def glyph_nodes(self) -> list[Node]:
        """Nodes that represent visual glyphs (not camera/world/grid infrastructure)."""
        return [n for n in self.nodes if n.type not in NON_VISUAL_TYPES]

    def node_by_id(self, node_id: int) -> Node | None:
        return self._by_id.get(node_id)

    def world_node(self) -> Node | None:
        """The World node (type=0), holding scene-wide background/render-mode/
        fog settings — see node.py. Returns the lowest-id match, or None if
        the file has no World row (old files render with hardcoded defaults)."""
        world_nodes = [n for n in self.nodes if n.type == NODE_TYPE_WORLD]
        return min(world_nodes, key=lambda n: n.id) if world_nodes else None

    @classmethod
    def load(cls, path, base_scale: float = 3.0) -> 'Scene':
        """Load a node CSV (GlyphViz gv_node.csv or GaiaViz/ANTz np_node.csv) and return a Scene."""
        return cls(load_node_csv(str(path)), base_scale)


def node_world_matrix(node: Node, scene: Scene) -> np.ndarray:
    """
    4x4 float64 transform placing this node's unit geometry in world space.

    The rendering 3x3 is built as the ANTz-correct hierarchical product:

        M3 = parent_basis @ child_local @ S_child

    where parent_basis is the parent's full recursive rotation+scale
    composition (see compute_world_bases — fusing each ancestor level's
    rotation AND scale into one matrix before moving to the next level,
    rather than a flat cumulative-scale vector that doesn't commute with
    intervening rotation), child_local is this node's own topo_base+rotation
    contribution, and S_child = diag(this node's own scale * base_scale,
    floored at 0.2). base_scale is applied here, exactly once, rather than
    inside the recursive composition — applying it once per hierarchy level
    would compound it as base_scale**depth.

    This means a non-uniform ancestor scale distorts a descendant's rendered
    shape relative to its *actual* accumulated orientation at every level —
    e.g. a sphere stretched along X produces a diamond-shaped child at 45° —
    correctly at any nesting depth, since rotation and non-uniform scale
    don't commute.

    For rod nodes the child-scale vector is further adjusted by the fixed
    ROD_RADIUS/HEIGHT factors relating the rod glyph's modeled proportions
    to its scale fields, and the translation gains a cap offset (bottom of
    the cylinder at the node's world origin, ANTz's kNPoffsetRod convention).

    This function is the single source of truth for node transforms.
    The renderer loads it with glMultMatrixf; the FBO picker renders with it;
    tests compare it against the ANTz C oracle.  It runs without a GL context.
    """
    scene._ensure()

    wx, wy, wz = scene._world_pos.get(
        node.id, (node.translate_x, node.translate_y, node.translate_z)
    )

    pwb = np.array(scene._parent_basis.get(node.id, _MAT_IDENTITY_3), dtype=np.float64)
    lc  = np.array(scene._child_local.get(node.id, _MAT_IDENTITY_3), dtype=np.float64)

    bs = scene.base_scale
    sc = np.array([
        max(node.scale_x * bs, 0.2),
        max(node.scale_y * bs, 0.2),
        max(node.scale_z * bs, 0.2),
    ], dtype=np.float64)

    if node.topo == TOPO_ROD:
        sc_rod = sc * np.array([ROD_RADIUS_FACTOR, ROD_RADIUS_FACTOR, ROD_HEIGHT_FACTOR])
        M3 = (pwb @ lc) * sc_rod
        # Cap offset: translate bottom of cylinder to world origin (ANTz convention).
        # M3[:, 2] is the rendered Z-axis vector (direction + magnitude), so adding
        # it once shifts the origin from the cylinder centre to its bottom cap.
        return np.array([
            [M3[0, 0], M3[0, 1], M3[0, 2], wx + M3[0, 2]],
            [M3[1, 0], M3[1, 1], M3[1, 2], wy + M3[1, 2]],
            [M3[2, 0], M3[2, 1], M3[2, 2], wz + M3[2, 2]],
            [0.,       0.,       0.,        1.             ],
        ], dtype=np.float64)

    M3 = (pwb @ lc) * sc
    return np.array([
        [M3[0, 0], M3[0, 1], M3[0, 2], wx],
        [M3[1, 0], M3[1, 1], M3[1, 2], wy],
        [M3[2, 0], M3[2, 1], M3[2, 2], wz],
        [0.,       0.,       0.,        1.],
    ], dtype=np.float64)
