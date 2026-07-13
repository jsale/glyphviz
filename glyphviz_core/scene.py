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
  (Scene._bake_draw_data batches the same formula across all nodes for the
  render loop — the old-vs-new verification and golden tests pin the batch
  to node_world_matrix's numbers.)

* The 4x4 matrix produced is (row-major NumPy, translation in last column):
      T_world  @  parent_basis  @  child_local  @  S_child  [@  T_cap_rod]
  where parent_basis (see topology.compute_world_transforms) is the parent's
  full recursive rotation+scale composition down the ancestor chain. For rod
  nodes a cap-offset T(0,0,drz) shifts the bottom to the node's world origin
  (ANTz kNPoffsetRod convention).

* Transforms are recomputed lazily on demand via Scene._ensure(), then cached
  until Scene.invalidate() is called.  The viewport calls invalidate() at the
  start of each paint to match ANTz's per-frame recomputation, and the pick
  pass reuses the freshly-computed cache without a second invalidation.
  Internally the cache is one batched numpy state (SceneTransforms) computed
  by the vectorized engine in topology.py — the per-node recursive dicts this
  replaced cost ~3.3 s per invalidation at 100k nodes.
"""

import math

import numpy as np

from .csv_reader import load_node_csv
from .geometry_data import ROD_RADIUS_FACTOR, ROD_HEIGHT_FACTOR
from .node import Node, NODE_TYPE_WORLD, NON_VISUAL_TYPES
from .topology import (
    TOPO_ROD,
    SceneTransforms,
    compute_world_transforms,
    update_world_transform_rows,
)

_MAT_IDENTITY_3 = ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.))

_ROD_SCALE_FACTORS = np.array([ROD_RADIUS_FACTOR, ROD_RADIUS_FACTOR,
                               ROD_HEIGHT_FACTOR])


class Scene:
    """Collection of nodes with lazily cached world-space transforms."""

    def __init__(self, nodes: list[Node], base_scale: float = 3.0):
        self.nodes = nodes
        self.base_scale = base_scale
        self._by_id: dict[int, Node] = {n.id: n for n in nodes}
        self._dirty = True
        # Monotonic change counter, bumped by invalidate()/register_node().
        # Lets a renderer detect "scene content changed since I last baked
        # it" (e.g. the viewport's retained scene display list) without
        # subscribing to every mutation path individually.
        self._revision = 0
        # Batched transform state (see topology.SceneTransforms): world/parent
        # bases and child-local rotations are RAW, dimensionless-scale
        # compositions — base_scale is applied once in the draw matrices, not
        # once per hierarchy level. world_basis also doubles as the matrix
        # that orients/stretches a node's children's topology offsets into
        # world space.
        self._transforms: SceneTransforms | None = None
        # Finished draw data (see node_draw_data), baked in one batch on
        # first access after a recompute: row-major 4x4 world matrices,
        # column-major float32 GL forms, and bounding-sphere radii.
        self._draw_M: np.ndarray | None = None
        self._draw_gl: np.ndarray | None = None
        self._draw_radius: np.ndarray | None = None

    def invalidate(self):
        """Mark cached transforms stale; they will be recomputed on next access."""
        self._dirty = True
        self._revision += 1

    def touch(self):
        """Bump the revision counter WITHOUT invalidating cached transforms.

        For edits that change what the renderer must draw but not where
        anything sits (e.g. hide flags): a renderer keyed on _revision rebakes
        its retained state, while the transform recompute (~0.4 s at 100k
        nodes) is skipped because node placement is untouched."""
        self._revision += 1

    def register_node(self, node: Node):
        """Called after a node is appended directly to self.nodes — keeps _by_id in sync."""
        self._by_id[node.id] = node
        self._dirty = True
        self._revision += 1

    def _ensure(self):
        if not self._dirty:
            return
        self._transforms = compute_world_transforms(self.nodes, self.base_scale)
        self._draw_M = self._draw_gl = self._draw_radius = None
        self._dirty = False

    def _row_of(self, node_id: int) -> int | None:
        self._ensure()
        return self._transforms.row_of_id.get(node_id)

    def rows_for_ids(self, ids) -> np.ndarray:
        """Row indices (sorted, int64) for the given node ids; unknown ids
        are silently dropped. For refresh_rows callers."""
        self._ensure()
        row_of_id = self._transforms.row_of_id
        return np.array(sorted(row_of_id[i] for i in ids if i in row_of_id),
                        dtype=np.int64)

    def refresh_rows(self, rows: np.ndarray) -> bool:
        """Partially refresh cached transforms + draw data for `rows` only,
        WITHOUT bumping _revision — the Channels-playback fast path: a
        renderer keyed on _revision keeps replaying its retained state for
        everything else while the animated subtrees get current matrices.

        `rows` must satisfy update_world_transform_rows' contract (closed
        under descendants; only translate/rotate/scale changed). Returns
        False when the cache was stale and a full recompute ran instead —
        either way, all draw data is current on return."""
        if self._dirty or self._transforms is None:
            self._ensure()
            return False
        update_world_transform_rows(self.nodes, self.base_scale,
                                    self._transforms, rows)
        if self._draw_M is not None:
            self._bake_draw_rows(rows)
        return True

    # --- public accessors (trigger lazy compute) ---

    def world_pos(self, node_id: int) -> tuple[float, float, float] | None:
        row = self._row_of(node_id)
        if row is None:
            return None
        x, y, z = self._transforms.world_pos[row]
        return (float(x), float(y), float(z))

    def world_scale(self, node_id: int) -> tuple[float, float, float] | None:
        """Approximate per-axis cumulative scale (column norms of the node's
        RAW world_basis) — a camera-framing/UI hint, not exact glyph-shape
        math (see node_world_matrix for that)."""
        row = self._row_of(node_id)
        if row is None:
            return None
        wb = self._transforms.world_basis[row]
        norms = np.sqrt((wb * wb).sum(axis=0))
        return (float(norms[0]), float(norms[1]), float(norms[2]))

    def _bake_draw_data(self):
        """Batch-compute node_world_matrix's formula for every node at once.

        Profiling showed per-node recomposition dominated both the static-
        scene render loop (fixed previously with a per-node cache) and the
        post-edit rebuild at 100k nodes (~1.3 s recomposed one node at a
        time; the batch is ~30 ms). Must stay numerically identical to
        node_world_matrix — the golden tests and the render/pick contract
        depend on it.
        """
        t = self._transforms
        n = len(self.nodes)
        bs = self.base_scale
        scale = np.array([(nd.scale_x, nd.scale_y, nd.scale_z)
                          for nd in self.nodes], dtype=np.float64)
        sc = np.maximum(scale * bs, 0.2)
        topo = np.array([nd.topo for nd in self.nodes], dtype=np.int64)
        rod = topo == TOPO_ROD
        if rod.any():
            sc[rod] *= _ROD_SCALE_FACTORS

        M3 = (t.parent_basis @ t.child_local) * sc[:, None, :]
        pos = t.world_pos.copy()
        if rod.any():
            # Cap offset: translate bottom of cylinder to world origin (ANTz
            # convention). M3[:, :, 2] is the rendered Z-axis vector.
            pos[rod] += M3[rod][:, :, 2]

        M = np.zeros((n, 4, 4))
        M[:, :3, :3] = M3
        M[:, :3, 3] = pos
        M[:, 3, 3] = 1.0
        self._draw_M = M
        self._draw_gl = np.ascontiguousarray(
            M.transpose(0, 2, 1).reshape(n, 16), dtype=np.float32)
        self._draw_radius = np.sqrt((M3 * M3).sum(axis=1)).max(axis=1)

    def _bake_draw_rows(self, rows: np.ndarray):
        """Row-subset version of _bake_draw_data, writing in place — must
        stay numerically identical to it (same formula, same dtypes)."""
        t = self._transforms
        k = len(rows)
        if k == 0:
            return
        bs = self.base_scale
        sub = [self.nodes[int(i)] for i in rows]
        scale = np.array([(nd.scale_x, nd.scale_y, nd.scale_z)
                          for nd in sub], dtype=np.float64)
        sc = np.maximum(scale * bs, 0.2)
        topo = np.array([nd.topo for nd in sub], dtype=np.int64)
        rod = topo == TOPO_ROD
        if rod.any():
            sc[rod] *= _ROD_SCALE_FACTORS

        M3 = (t.parent_basis[rows] @ t.child_local[rows]) * sc[:, None, :]
        pos = t.world_pos[rows]   # fancy index -> already a copy
        if rod.any():
            pos[rod] += M3[rod][:, :, 2]

        M = np.zeros((k, 4, 4))
        M[:, :3, :3] = M3
        M[:, :3, 3] = pos
        M[:, 3, 3] = 1.0
        self._draw_M[rows] = M
        self._draw_gl[rows] = M.transpose(0, 2, 1).reshape(k, 16)
        self._draw_radius[rows] = np.sqrt((M3 * M3).sum(axis=1)).max(axis=1)

    def node_draw_data(self, node: Node) -> tuple:
        """Per-node data the renderer needs every frame, batch-computed once
        and cached until invalidate():

            (M, gl_matrix, radius)

        M          -- node_world_matrix() result (float64 row-major 4x4)
        gl_matrix  -- the same matrix as a float32 column-major flat array,
                      ready for glMultMatrixf/glLoadMatrixf
        radius     -- max column norm of M's 3x3 linear part = the node's
                      world-space bounding-sphere radius for unit geometry
                      (callers add their own headroom for corner-touching
                      shapes / selection halos)
        """
        row = self._row_of(node.id)
        if row is None:
            # Node not in the scene list (legacy fallback): compose directly.
            M = node_world_matrix(node, self)
            gl_matrix = M.astype(np.float32).T.flatten()
            radius = float(np.linalg.norm(M[:3, :3], axis=0).max())
            return (M, gl_matrix, radius)
        if self._draw_M is None:
            self._bake_draw_data()
        return (self._draw_M[row], self._draw_gl[row],
                float(self._draw_radius[row]))

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
    composition (see compute_world_transforms — fusing each ancestor level's
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
    t = scene._transforms
    row = t.row_of_id.get(node.id) if t is not None else None
    if row is not None:
        wx, wy, wz = (float(v) for v in t.world_pos[row])
        pwb = t.parent_basis[row]
        lc = t.child_local[row]
    else:
        wx, wy, wz = node.translate_x, node.translate_y, node.translate_z
        pwb = np.array(_MAT_IDENTITY_3, dtype=np.float64)
        lc = np.array(_MAT_IDENTITY_3, dtype=np.float64)

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
