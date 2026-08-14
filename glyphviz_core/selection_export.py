"""Write part of a scene out as a standalone node CSV (File > Save Selection As…).

A selection is not a scene.  Handing save_node_csv a bare list of selected
Nodes produces a file that loads without complaint and is quietly wrong,
because a node whose parent_id names a row the file doesn't contain is
treated as a ROOT (topology._resolve_hierarchy), and a root's translate_x/y/z
IS its world position — no topology offset at all.  So a child of a Sphere
parent authored at (30, 45, 5) meaning "longitude 30, latitude 45, 5 units
out" reloads as literal world (30, 45, 5); a World Grid child's lon/lat
becomes raw world units and lands off the map.  Saving a selection naively
relocates and reorients everything in it.

build_selection() is the fix.  It decides membership, repairs every
cross-reference that would otherwise dangle, and detaches the nodes whose
parents didn't come along, under one of three policies:

    DETACH_BAKE       fold the missing ancestor chain into the node itself
    DETACH_ANCESTORS  bring the ancestor rows along instead
    DETACH_RAW        leave the fields exactly as authored

The bake is exact, and the reason is worth stating because the whole feature
rests on it.  compute_world_transforms builds

    world_basis = parent_basis @ child_local @ diag(scale)

and every descendant composes off its parent's world_basis (both for its own
basis and, through offset_basis, for its position), while the node's own draw
matrix is that same product times base_scale.  So a detached node that keeps
its world_basis and its world position keeps its ENTIRE SUBTREE pinned in
place, pixel for pixel.  Re-expressing that basis as a root's own
rotation+scale is the decomposition in decompose_basis() below: a root has
no topology base rotation, so world_basis = own_rotation @ diag(scale), and
Euler XYZ can express any rotation.

Two limits, both reported rather than hidden:

* A non-uniform ancestor scale combined with rotation produces SHEAR — the
  columns of world_basis stop being mutually perpendicular, and no
  rotate+scale pair can express that.  decompose_basis returns the closest
  non-sheared match and a shear magnitude; build_selection counts the nodes
  it had to approximate.
* translate_rate/rotate_rate on a detached node changes meaning: rates on a
  Sphere child orbit it in longitude/latitude, while the same numbers on a
  root drift it through world XYZ.  Counted as animated_detached.

A third property is worth knowing rather than reporting: the bake is exact
at the Global Scale (Scene.base_scale) in force when it runs.  A topology
offset is proportional to base_scale while a root's translate is a literal
world position, so a detached fragment reopened at a different Global Scale
sits where it was rather than where its old parent would now put it.  That
is inherent to the file format, not to this module.

Ids are preserved as-is (unlike scene_merge, which rebases them onto a fresh
block): extras['record_id'] — the tag file's join key — and any channel
binding stay coherent for free, and the fragment stays diffable against the
scene it came from.  Merge rebases on the way back in anyway.
"""

import copy
import math
from dataclasses import dataclass, field

import numpy as np

from .node import (
    NON_VISUAL_TYPES, NODE_TYPE_LINK, Node, ROTATION_MODE_EULER_XYZ,
)
from .scene_merge import recompute_branch_levels

# --- detach policies (ExportOptions.detach) ---
DETACH_BAKE = 'bake'
DETACH_ANCESTORS = 'ancestors'
DETACH_RAW = 'raw'

# How far world_basis' normalized columns may stray from mutually
# perpendicular before the bake counts as approximate.  Well above float
# noise in a deep composition (measured ~1e-15 on a 4-level chain) and well
# below anything visible: 1e-6 is a millionth of a unit axis.
SHEAR_TOLERANCE = 1e-6

# Column norm below which an axis counts as collapsed.  Such an axis is NOT
# an approximation — scale 0 annihilates whatever rotation column pairs with
# it, so R @ diag(s) still reproduces the basis exactly.
_DEGENERATE = 1e-12


@dataclass(frozen=True)
class ExportOptions:
    """What File > Save Selection As…'s dialog collects."""

    # Selected nodes bring their full descendant subtree (the rule
    # _delete_selected and _copy_selected already enforce).  Free for a leaf
    # selection — a leaf's closure is itself.
    include_descendants: bool = True
    # How to handle a node whose parent isn't in the export (see module docstring).
    detach: str = DETACH_BAKE
    # Carry the type-0 World row: background color, fog, render mode, tag and
    # reference-grid styling.  It is never selectable in bulk (see
    # MainWindow._selectable_nodes), so without this the fragment reopens on
    # the wrong background.
    include_world_row: bool = True


@dataclass
class SelectionPlan:
    """Which rows an export will contain, resolved without copying or
    modifying anything.

    Split out from the export itself so a dialog can preview the outcome on
    every checkbox toggle: the membership rules are a few set walks over the
    node list, while materializing deep-copies every node (seconds, on a
    100k-node scene).
    """

    # ids to write, in scene order, links already vetted. Excludes the World
    # row, which is prepended separately (world_id).
    ids: list[int] = field(default_factory=list)
    # ids that will be re-rooted because their parent isn't in the export
    detached_ids: list[int] = field(default_factory=list)
    descendants_added: int = 0
    ancestors_added: int = 0
    links_added: int = 0      # links pulled in because both ends are present
    dropped_links: int = 0    # links whose other end is outside the export
    world_id: int | None = None

    @property
    def count(self) -> int:
        """Total rows the file will hold, World row included."""
        return len(self.ids) + (0 if self.world_id is None else 1)

    @property
    def world_row(self) -> bool:
        return self.world_id is not None


@dataclass
class SelectionExport:
    """What build_selection() produced, for the caller's status reporting."""

    nodes: list[Node] = field(default_factory=list)
    plan: SelectionPlan = field(default_factory=SelectionPlan)
    # detached nodes whose bake couldn't be exact (sheared ancestor scale)
    approximated_ids: list[int] = field(default_factory=list)
    # ...and those carrying translate/rotate rates, whose animation now runs
    # in world space instead of their old parent's coordinate system
    animated_detached: list[int] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.nodes)

    # The plan's counts read naturally off the result too.
    @property
    def detached_ids(self) -> list[int]:
        return self.plan.detached_ids

    @property
    def descendants_added(self) -> int:
        return self.plan.descendants_added

    @property
    def ancestors_added(self) -> int:
        return self.plan.ancestors_added

    @property
    def links_added(self) -> int:
        return self.plan.links_added

    @property
    def dropped_links(self) -> int:
        return self.plan.dropped_links

    @property
    def world_row(self) -> bool:
        return self.plan.world_row


def _nearest_rotation(Q: np.ndarray) -> np.ndarray:
    """Closest rotation matrix to Q (orthogonal Procrustes, det +1).

    Exact identity when Q is already a rotation; when Q is sheared this is
    the least-squares best fit.  Rank-deficient Q (a collapsed axis) is fine:
    the SVD still yields orthonormal factors, and the arbitrary direction it
    picks for the dead axis is multiplied by a zero scale anyway.
    """
    U, _s, Vt = np.linalg.svd(Q)
    if np.linalg.det(U @ Vt) < 0:
        U = U.copy()
        U[:, -1] *= -1.0
    return U @ Vt


def decompose_basis(A: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """Split a raw world_basis into (rotation, per-axis scale, shear).

    Returns R (3x3, det +1), s (3,), and the shear magnitude — the largest
    deviation of the normalized columns' Gram matrix from the identity,
    i.e. 0 when the columns are mutually perpendicular.  R @ diag(s)
    reproduces A exactly whenever shear is 0.

    A reflection (an odd number of negative scale fields upstream) is folded
    into a negative Z scale rather than into R, keeping R a true rotation and
    the product exact.
    """
    A = np.asarray(A, dtype=np.float64)
    norms = np.linalg.norm(A, axis=0)
    live = norms > _DEGENERATE
    s = np.where(live, norms, 0.0)
    Q = np.zeros((3, 3))
    Q[:, live] = A[:, live] / norms[live]

    # Handedness: flipping a column of Q and the matching entry of s leaves
    # Q @ diag(s) untouched, so this costs nothing in fidelity.
    if live.all() and np.linalg.det(Q) < 0:
        Q[:, 2] *= -1.0
        s[2] = -s[2]

    if live.sum() > 1:
        G = Q[:, live].T @ Q[:, live]
        shear = float(np.abs(G - np.eye(int(live.sum()))).max())
    else:
        shear = 0.0   # one axis or fewer can't be non-perpendicular to anything
    return _nearest_rotation(Q), s, shear


def euler_xyz_from_matrix(R: np.ndarray) -> tuple[float, float, float]:
    """(rotate_x, rotate_y, rotate_z) in degrees reproducing R under
    ROTATION_MODE_EULER_XYZ — the exact inverse of
    topology._local_rotation_matrix_euler_xyz, whose product is

        Rx(rx) @ Ry(ry) @ Rz(rz)
      = [[ cy*cz,            -cy*sz,             sy    ],
         [ cx*sz + sx*sy*cz,  cx*cz - sx*sy*sz, -sx*cy ],
         [ sx*sz - cx*sy*cz,  sx*cz + cx*sy*sz,  cx*cy ]]

    At gimbal lock (ry = ±90°, where the X and Z rotations act on the same
    axis) the split between rx and rz is arbitrary; rz is set to 0 and the
    whole rotation goes to rx, which is the conventional choice and still
    reproduces R exactly.
    """
    R = np.asarray(R, dtype=np.float64)
    sy = min(1.0, max(-1.0, float(R[0, 2])))
    ry = math.asin(sy)
    if abs(sy) < 1.0 - 1e-9:
        rx = math.atan2(-R[1, 2], R[2, 2])
        rz = math.atan2(-R[0, 1], R[0, 0])
    else:
        rx = math.atan2(R[2, 1], R[1, 1])
        rz = 0.0
    return (math.degrees(rx), math.degrees(ry), math.degrees(rz))


def bake_world_placement(node: Node, scene) -> float:
    """Rewrite `node`'s transform fields so that, as a ROOT, it keeps the
    world placement it had as a child.  Returns the shear magnitude (0 when
    the rewrite is exact).

    The node's own topo/ratio/topo_scale/subspace are deliberately untouched:
    those describe the coordinate system it offers its CHILDREN, which this
    must not disturb.  Only the fields describing where the node itself sits
    are restated, plus rotation_mode — Euler XYZ is the mode that can express
    an arbitrary rotation matrix.
    """
    bases = scene.basis_matrices(node.id)
    pos = scene.world_pos(node.id)
    if bases is None or pos is None:
        return 0.0   # not part of this scene's transform state; leave as authored
    R, s, shear = decompose_basis(bases[0])   # bases[0] is world_basis
    rx, ry, rz = euler_xyz_from_matrix(R)
    node.translate_x, node.translate_y, node.translate_z = pos
    node.rotate_x, node.rotate_y, node.rotate_z = rx, ry, rz
    node.scale_x, node.scale_y, node.scale_z = (float(s[0]), float(s[1]), float(s[2]))
    node.rotation_mode = ROTATION_MODE_EULER_XYZ
    return shear


def _link_b_end(node: Node) -> int:
    """A link's B-end id (extras['child_id']), or 0 when absent/unparseable."""
    try:
        return int(float(node.extras.get('child_id', 0)))
    except (TypeError, ValueError):
        return 0


def _has_motion(node: Node) -> bool:
    """True when the node carries per-cycle translate/rotate rates, whose
    frame of reference a detach changes (see the module docstring)."""
    return any((
        node.translate_rate_x, node.translate_rate_y, node.translate_rate_z,
        node.rotate_rate_x, node.rotate_rate_y, node.rotate_rate_z,
    ))


def plan_selection(scene, selected_ids, options: ExportOptions | None = None
                   ) -> SelectionPlan:
    """Work out which rows a Save Selection As… write would contain.

    Reads the scene without copying or modifying it, so a dialog can call
    this on every option change.  build_selection() below runs exactly this
    and then materializes the result.

    Membership:
      - the selected ids, minus World/Camera rows (they are scene-wide
        settings, not members; the World row comes back below on its own
        terms),
      - plus every descendant, when include_descendants is set,
      - plus, in DETACH_ANCESTORS mode, the ancestor chain of everything
        above,
      - plus any link (type 7) whose A-end and B-end are BOTH present, even
        when the link node itself wasn't selected — otherwise saving two
        connected nodes silently loses the edge between them,
      - plus the World row, when include_world_row is set.

    A link with only one end present is dropped rather than left dangling
    (the same rule Copy/Paste and scene merge already use).
    """
    opts = options or ExportOptions()
    result = SelectionPlan()

    by_id: dict[int, Node] = {n.id: n for n in scene.nodes}
    ids = {
        i for i in selected_ids
        if i in by_id and by_id[i].type not in NON_VISUAL_TYPES
    }
    if not ids:
        return result

    if opts.include_descendants:
        children_of: dict[int, list[int]] = {}
        for n in scene.nodes:
            children_of.setdefault(n.parent_id, []).append(n.id)
        before = len(ids)
        frontier = set(ids)
        while frontier:
            frontier = {
                c for p in frontier for c in children_of.get(p, ())
                if c not in ids
            }
            ids |= frontier
        result.descendants_added = len(ids) - before

    if opts.detach == DETACH_ANCESTORS:
        before = len(ids)
        for start in list(ids):
            p = by_id[start].parent_id
            # Bounded by the node count: a parent cycle can't outrun it.
            for _ in range(len(by_id)):
                parent = by_id.get(p)
                if parent is None or p in ids or parent.type in NON_VISUAL_TYPES:
                    break
                ids.add(p)
                p = parent.parent_id
        result.ancestors_added = len(ids) - before

    # Links joining two members, whether or not the link row was selected.
    extra_links = {
        n.id for n in scene.nodes
        if n.type == NODE_TYPE_LINK and n.id not in ids
        and n.parent_id in ids and _link_b_end(n) in ids
    }
    ids |= extra_links
    result.links_added = len(extra_links)

    # Scene order is kept: it puts parents before children in every file the
    # app writes, and keeps the export diffable against its source.
    kept: list[int] = []
    for n in scene.nodes:
        if n.id not in ids:
            continue
        if n.type == NODE_TYPE_LINK and _link_b_end(n) not in ids:
            result.dropped_links += 1
            continue
        kept.append(n.id)

    kept_ids = set(kept)
    result.ids = kept
    result.detached_ids = [
        i for i in kept
        if by_id[i].parent_id != 0 and by_id[i].parent_id not in kept_ids
    ]

    world = scene.world_node() if opts.include_world_row else None
    if world is not None and world.id not in kept_ids:
        result.world_id = world.id
    return result


def build_selection(scene, selected_ids, options: ExportOptions | None = None
                    ) -> SelectionExport:
    """Materialize a Save Selection As… write: plan_selection() plus the
    repairs that need actual nodes to work on.

    Returns fresh deep copies — `scene` is never mutated, so the same
    selection can be exported repeatedly under different options.  Every node
    whose parent didn't make it is re-rooted and detached per the chosen
    policy, and branch_level is restated from the resulting hierarchy.
    """
    opts = options or ExportOptions()
    plan = plan_selection(scene, selected_ids, opts)
    result = SelectionExport(plan=plan)
    if not plan.ids:
        return result

    by_id: dict[int, Node] = {n.id: n for n in scene.nodes}
    out = [copy.deepcopy(by_id[i]) for i in plan.ids]

    detached = set(plan.detached_ids)
    for node in out:
        if node.id not in detached:
            continue
        if opts.detach != DETACH_RAW:
            # Applies in DETACH_ANCESTORS too: a top node still missing its
            # parent there means the chain was broken by something the walk
            # refused to include, and baking is the faithful answer.
            if bake_world_placement(node, scene) > SHEAR_TOLERANCE:
                result.approximated_ids.append(node.id)
        if _has_motion(node):
            result.animated_detached.append(node.id)
        node.parent_id = 0

    if plan.world_id is not None:
        # World row leads the file, as in a saved scene.
        out.insert(0, copy.deepcopy(by_id[plan.world_id]))

    recompute_branch_levels(out, {n.id for n in out})
    result.nodes = out
    return result
