"""
Parent-child spatial topology — converts a child's translate_x/y/z into a
world-space offset from its parent, according to the parent's topo id
(np_topo_id in the GaiaViz reference docs).

See gaiaviz-skill/references/structure/Topology-Guide.md for the full
per-topology coordinate conventions. New topologies are added by writing an
offset function and registering it in _TOPO_OFFSET_FUNCS.
"""
import math
from typing import NamedTuple

import numpy as np

from .geometry_data import ROD_HEIGHT_FACTOR, torus_radii
from .node import (
    Node, DEFAULT_TOPO_SCALE, GRID_GLOBE_RADIUS, NODE_TYPE_GRID,
    ROTATION_MODE_EULER_XYZ, ROTATION_MODE_HEADING_TILT_ROLL,
)

# topo id values — full reference list from Topology-Guide.md (np_topo_id there).
# Every id except TOPO_NONE has a dedicated offset function registered in
# _TOPO_OFFSET_FUNCS; TOPO_NONE falls back to a plain Cartesian offset (ANTz
# convention: an untyped parent's children translate rigidly with it).
TOPO_NONE      = 0
TOPO_CUBE      = 1
TOPO_SPHERE    = 2   # KML-style longitude/latitude/altitude on a globe surface
TOPO_TORUS     = 3   # orbital-angle/tube-angle/elevation on a donut surface
TOPO_CYLINDER  = 4
TOPO_PIN       = 5
TOPO_ROD       = 6
TOPO_POINT     = 7
TOPO_PLANE     = 8
TOPO_ZCUBE     = 9
TOPO_ZSPHERE   = 10
TOPO_ZTORUS    = 11
TOPO_ZCYLINDER = 12
TOPO_ZROD      = 13
TOPO_SPIRAL    = 14
TOPO_VIDEO     = 15
TOPO_PLOT      = 16  # 1D/2D/3D line plot, GPS, Oscilloscope (jsale/antz extension)
TOPO_SURFACE   = 17  # deformable grid, FFT, LIDAR, sound sphere (jsale/antz extension)
TOPO_POINTCLOUD = 18  # unstructured point cloud, batched GL_POINTS (jsale/antz extension)
TOPO_COUNT     = 19

TOPO_NAMES = {
    TOPO_NONE:      "None",
    TOPO_CUBE:      "Cube",
    TOPO_SPHERE:    "Sphere (KML)",
    TOPO_TORUS:     "Torus",
    TOPO_CYLINDER:  "Cylinder",
    TOPO_PIN:       "Pin",
    TOPO_ROD:       "Rod",
    TOPO_POINT:     "Point",
    TOPO_PLANE:     "Plane (Grid)",
    TOPO_ZCUBE:     "Zcube",
    TOPO_ZSPHERE:   "Zsphere",
    TOPO_ZTORUS:    "Ztorus",
    TOPO_ZCYLINDER: "Zcylinder",
    TOPO_ZROD:      "Zrod",
    TOPO_SPIRAL:    "Spiral",
    TOPO_VIDEO:     "Video",
    TOPO_PLOT:      "Plot",
    TOPO_SURFACE:   "Surface",
    TOPO_POINTCLOUD: "Point Cloud",
}


# ---------------------------------------------------------------------------
# Which of a child's translate_x/y/z each topology reads as a DISTANCE, and
# which it reads as an angle (or as a parameter already proportional to the
# parent's base radius, which is a distance that already tracks the parent's
# size and so needs no further scaling).
#
# The parent's Node.topo_scale multiplies exactly the True axes below, and
# nothing else. That is the whole implementation of the feature: every offset
# function further down stays untouched, because scaling an axis before the
# math is algebraically identical to scaling the distance term the math
# derives from it — `radial = base_radius + tz` becomes
# `base_radius + k*tz`, `dist * n + tx * u` becomes `dist * n + k*tx * u`,
# and so on. Keeping it to a pre-multiply is also what guarantees the
# property the field is for: an angular axis is never touched, so no value of
# topo_scale can disturb a circular layout.
#
# Per-topology reasoning for the False entries:
#   Sphere/Point/Zsphere — tx/ty are longitude/latitude degrees.
#   Torus/Ztorus         — tx/ty are orbital and tube angles.
#   Cylinder/Zcylinder   — tx is the angle around the axis.
#   Rod                  — ty is the angle around the axis; tx maps [0,180]
#                          onto the rod's full rendered LENGTH, so it is
#                          already expressed as a fraction of the parent's
#                          size (this is ANTz's own normalization, the very
#                          convention TOPO_SCALE_ANTZ generalizes).
#   Zrod                 — delegates to Zcylinder, so tx is the angle.
#   Spiral               — tx is the helix angle AND drives the helical rise
#                          as a fraction of base_radius; both size-relative.
# Anything absent (TOPO_NONE, Plane, Video, Plot, Surface, and any unknown
# id, which falls back to Cartesian placement) reads all three as distances.
# ---------------------------------------------------------------------------

_ALL_AXES_LINEAR = (True, True, True)

LINEAR_PLACEMENT_AXES: dict[int, tuple[bool, bool, bool]] = {
    TOPO_CUBE:      (True,  True,  True),    # face u, face v, height off face
    TOPO_SPHERE:    (False, False, True),    # lon, lat, altitude
    TOPO_TORUS:     (False, False, True),    # orbital angle, tube angle, tube offset
    TOPO_CYLINDER:  (False, True,  True),    # angle, height, radial
    TOPO_PIN:       (True,  True,  True),    # height, and two lateral offsets
    TOPO_ROD:       (False, False, True),    # length fraction, angle, radial
    TOPO_POINT:     (False, False, True),    # lon, lat, distance from center
    TOPO_PLANE:     (True,  True,  True),
    TOPO_ZCUBE:     (True,  True,  True),
    TOPO_ZSPHERE:   (False, False, True),
    TOPO_ZTORUS:    (False, False, True),
    TOPO_ZCYLINDER: (False, True,  True),
    TOPO_ZROD:      (False, True,  True),    # same math as Zcylinder
    TOPO_SPIRAL:    (False, True,  True),    # helix angle, rise offset, radial
    TOPO_VIDEO:     (True,  True,  True),
    TOPO_PLOT:      (True,  True,  True),
    TOPO_SURFACE:   (True,  True,  True),
    TOPO_POINTCLOUD: (True,  True,  True),
}

# Row `topo` -> boolean mask, for the batched engine. Out-of-range/unknown ids
# are handled by the callers (all-linear, matching the Cartesian fallback).
_LINEAR_AXES_ARR = np.array(
    [LINEAR_PLACEMENT_AXES.get(t, _ALL_AXES_LINEAR) for t in range(TOPO_COUNT)],
    dtype=bool,
)


def linear_placement_axes(parent: Node | None) -> tuple[bool, bool, bool]:
    """Which of a child's translate axes this parent reads as a distance —
    i.e. which ones its topo_scale multiplies.

    A World Grid parent returns all-False: grid children are exempt from
    topo_scale entirely, because the grid's rendered footprint is sized from
    the same extents window their coordinates are read in, and scaling one
    without the other would slide the frame out from under its children.
    """
    if parent is None or parent.type == NODE_TYPE_GRID:
        return (False, False, False)
    return LINEAR_PLACEMENT_AXES.get(parent.topo, _ALL_AXES_LINEAR)


def scale_linear_axes(parent: Node | None, tx: float, ty: float, tz: float
                      ) -> tuple[float, float, float]:
    """Apply the parent's topo_scale to whichever of tx/ty/tz that parent
    reads as a distance. Scalar counterpart of the pre-multiply
    _batched_topo_offsets does per row."""
    ax, ay, az = linear_placement_axes(parent)
    if not (ax or ay or az):
        return (tx, ty, tz)
    k = parent.topo_scale
    return (tx * k if ax else tx, ty * k if ay else ty, tz * k if az else tz)


def kml_offset(longitude: float, latitude: float, altitude: float, radius: float):
    """
    Convert KML-style longitude/latitude/altitude into a Cartesian offset
    from the parent's center, in the parent's own *unscaled* local frame.
    No scale is applied here: the result is transformed into world space by
    the parent's `world_basis` (see compute_world_bases), which is what
    carries the parent's (and every ancestor's) rotation and per-axis
    stretch through correctly, no matter how many hierarchy levels deep.
    `radius` is the topology's unscaled base radius — e.g. base_scale for
    Sphere (children sit on the rendered surface) or 0.0 for Point/Zsphere
    (children offset straight from the center, altitude only).
    """
    lon = math.radians(longitude)
    lat = math.radians(latitude)
    r = radius + altitude
    cos_lat = math.cos(lat)
    return (
        r * cos_lat * math.cos(lon),
        r * cos_lat * math.sin(lon),
        r * math.sin(lat),
    )


# Subspace 0-5 -> face name, confirmed against real ANTz ground truth
# (legacy 'facet' CSV column, 1-indexed: facet 1=+X .. 6=-Z -> subspace
# facet-1). Exposed for GUI consumption (e.g. a Facet picker) so the
# face-order source of truth lives in one place.
CUBE_FACE_NAMES = ("+X", "-X", "+Y", "-Y", "+Z", "-Z")

# Face data for cube topology: each entry is (normal, u, v) where
# normal = outward face direction, u/v = right/up within the face plane
# when viewed from outside the cube, in Z-up world coordinates.
_CUBE_FACES = [
    (( 1,  0,  0), ( 0,  1,  0), ( 0,  0,  1)),  # 0: +X face
    ((-1,  0,  0), ( 0, -1,  0), ( 0,  0,  1)),  # 1: -X face
    (( 0,  1,  0), (-1,  0,  0), ( 0,  0,  1)),  # 2: +Y face
    (( 0, -1,  0), ( 1,  0,  0), ( 0,  0,  1)),  # 3: -Y face
    (( 0,  0,  1), ( 1,  0,  0), ( 0,  1,  0)),  # 4: +Z face (top)
    (( 0,  0, -1), ( 1,  0,  0), ( 0, -1,  0)),  # 5: -Z face (bottom)
]


# ---------------------------------------------------------------------------
# 3x3 rotation matrices (row-major tuples-of-tuples — no numpy needed) used to
# cascade orientation and scale through the parent->child chain (see
# compute_world_bases) and to cascade translation (compute_world_positions).
# ---------------------------------------------------------------------------

_MAT_IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def _mat_mul(a, b):
    """3x3 matrix product a @ b (row-major)."""
    return tuple(
        tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3))
        for i in range(3)
    )


def _mat_vec_mul(m, v):
    """3x3 matrix times column vector v=(x,y,z)."""
    return tuple(sum(m[i][k] * v[k] for k in range(3)) for i in range(3))


def _mat_scale_cols(m, v):
    """3x3 matrix times a diagonal scale matrix: m @ diag(v)."""
    return tuple(
        tuple(m[i][j] * v[j] for j in range(3))
        for i in range(3)
    )


def _rot_x(deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return ((1.0, 0.0, 0.0), (0.0, c, -s), (0.0, s, c))


def _rot_y(deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return ((c, 0.0, s), (0.0, 1.0, 0.0), (-s, 0.0, c))


def _rot_z(deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))


def _local_rotation_matrix_heading_tilt_roll(rx: float, ry: float, rz: float):
    """3x3 rotation matrix matching ANTz's DrawPinChild/DrawPin convention:
      glRotatef(rotate_y,  0, 0, -1)  → Rz(-ry)   "heading"
      glRotatef(rotate_x, -1, 0,  0)  → Rx(-rx)   "roll"
      glRotatef(rotate_z,  0, 0, -1)  → Rz(-rz)   "tilt"
    OpenGL right-multiplies, so the combined matrix is Rz(-ry) @ Rx(-rx) @ Rz(-rz).
    rotate_y and rotate_z both drive Z-axis rotations (no Y-axis rotation in ANTz)."""
    return _mat_mul(_mat_mul(_rot_z(-ry), _rot_x(-rx)), _rot_z(-rz))


def _local_rotation_matrix_euler_xyz(rx: float, ry: float, rz: float):
    """GlyphViz-only alternative: rotate_x about its own axis, then rotate_y
    about the resulting axis, then rotate_z about the final axis. No ANTz
    sign inversions — each field maps to a standard right-hand-rule rotation
    about the axis it's named for."""
    return _mat_mul(_mat_mul(_rot_x(rx), _rot_y(ry)), _rot_z(rz))


def local_rotation_matrix(rx: float, ry: float, rz: float,
                           rotation_mode: int = ROTATION_MODE_HEADING_TILT_ROLL):
    """Dispatches to the node's chosen rotate_x/y/z interpretation (see
    ROTATION_MODE_* in node.py)."""
    if rotation_mode == ROTATION_MODE_EULER_XYZ:
        return _local_rotation_matrix_euler_xyz(rx, ry, rz)
    return _local_rotation_matrix_heading_tilt_roll(rx, ry, rz)


# Precomputed per-face base rotations for Cube topology: aligns the child's
# +Z axis with each face's outward normal (order mirrors _CUBE_FACES in this file).
# face 0 (+X): Ry(90)   face 1 (-X): Ry(-90)  face 2 (+Y): Rx(-90)
# face 3 (-Y): Rx(90)   face 4 (+Z): identity  face 5 (-Z): Rx(180)
_CUBE_FACE_BASE_ROTS = (
    _rot_y(90),    # 0: +X normal
    _rot_y(-90),   # 1: -X normal
    _rot_x(-90),   # 2: +Y normal
    _rot_x(90),    # 3: -Y normal
    _MAT_IDENTITY, # 4: +Z normal (top)
    _rot_x(180),   # 5: -Z normal (bottom)
)


def _topology_base_rotation(parent_topo: int, tx: float, ty: float, tz: float,
                              child_subspace: int = 0) -> tuple:
    """Orientation scaffold inserted between the parent's world rotation and the
    child's own rotate_x/y/z: makes the child 'face outward' from the parent
    surface at its placement (tx, ty, tz) so the outward-facing side tracks the
    surface as the child's placement coordinates change.

    Rod / Zrod — Rz(ty) / Rz(tx): rotates the child around the cylinder axis
             by its angular placement, so a child with Ry=90 (its own
             rotate_x/y/z tilting it to point radially outward like a spoke)
             keeps facing outward — orthogonal to the orbit — as it travels
             along the circular path, instead of holding a fixed world
             orientation while the position sweeps underneath it. Rod's angle
             param is ty (tx is the linear position along the rod's length);
             Zrod delegates its placement math to _zcylinder_offset, so its
             angle param is tx like Cylinder, not ty.
    Sphere/Point/Torus/Ztorus (KML-style) — Rz(tx)*Ry(90-ty): aligns the
             child's +Z with the surface normal at (longitude=tx,
             latitude=ty). Torus's surface normal at (orbital angle=tx,
             tube angle=ty) has exactly this same KML form (the tube
             cross-section is a small "sphere" wrapped around the main
             ring), so the formula carries over unchanged from Sphere/Point.
    Cylinder/Zcylinder/Spiral — Rz(tx): these have a single circular angle
             param (tx), with no second axis to wrap around (Cylinder/
             Zcylinder's ty is linear height along the axis; Spiral's ty is
             a linear offset added to its helical height) — same "carry the
             child's own static orientation around" idea as Rod, just one
             axis instead of two.
    Cube   — precomputed rotation per face (subspace), aligning +Z with face normal.
    Pin and all others — identity (no circular placement, so no orientation
             to carry around).
    """
    if parent_topo in (TOPO_ROD,):
        return _rot_z(ty)
    if parent_topo in (TOPO_ZROD, TOPO_CYLINDER, TOPO_ZCYLINDER, TOPO_SPIRAL):
        return _rot_z(tx)
    if parent_topo in (TOPO_SPHERE, TOPO_POINT, TOPO_TORUS, TOPO_ZTORUS):
        return _mat_mul(_rot_z(tx), _rot_y(90.0 - ty))
    if parent_topo == TOPO_CUBE:
        return _CUBE_FACE_BASE_ROTS[max(0, min(5, child_subspace))]
    return _MAT_IDENTITY


# ---------------------------------------------------------------------------
# Vectorized transform engine.
#
# The per-node recursive resolution (tuple math, one Python call chain per
# node) cost ~3.3 s per Scene invalidation at 100k nodes. The engine below
# produces identical numbers by resolving the hierarchy structure once in
# plain Python (iterative — no recursion limit), then doing all math as
# level-ordered numpy batches: every node's local rotation, topology base
# rotation, and topology offset are computed in grouped array operations, and
# each hierarchy level composes onto its parents with one batched matmul.
#
# The scalar _*_offset functions and _topology_base_rotation below remain the
# readable per-topology specification — the batched implementations MUST stay
# in sync with them (verified by old-vs-new comparison when this was built).
# ---------------------------------------------------------------------------

class SceneTransforms(NamedTuple):
    """Batched transform state for one node list (see compute_world_transforms).

    row_of_id maps node id -> row index in the arrays (first occurrence wins,
    matching the old dict caches where the first resolution of an id stuck).
    eff_parent[i] is the row of node i's effective parent, -1 for roots
    (missing parent, self-parent, or a cycle entry — see _resolve_hierarchy).
    depth[i] is node i's hierarchy depth (0 for roots), kept so
    update_world_transform_rows can re-walk a row subset in level order.
    """
    row_of_id: dict[int, int]
    eff_parent: np.ndarray    # (n,)   int64
    world_basis: np.ndarray   # (n,3,3) float64 — RAW rotation+scale composition
    parent_basis: np.ndarray  # (n,3,3) float64
    child_local: np.ndarray   # (n,3,3) float64
    world_pos: np.ndarray     # (n,3)   float64
    depth: np.ndarray         # (n,)   int64


def _resolve_hierarchy(nodes: list[Node]) -> tuple[np.ndarray, np.ndarray]:
    """Resolve each node's effective parent row and hierarchy depth.

    Matches the recursive resolvers' structure: parent looked up by id (last
    node wins on duplicate ids, like the old by_id dicts); a node is a root
    when its parent is missing or itself. A parent-chain cycle is broken at
    its entry node (the first cycle member reached walking up from outside),
    which becomes a root. NOTE: the old recursive code then *overwrote* the
    entry node's basis with an extra composition onto its in-cycle parent,
    giving it a value inconsistent with what its own descendants had already
    used; this engine keeps the entry node a plain root instead — stable and
    order-independent. Only files with corrupt (cyclic) parent chains can
    render differently.
    """
    n = len(nodes)
    index_of_id: dict[int, int] = {}
    for i, nd in enumerate(nodes):
        index_of_id[nd.id] = i
    eff_parent = np.empty(n, dtype=np.int64)
    for i, nd in enumerate(nodes):
        p = index_of_id.get(nd.parent_id, -1)
        eff_parent[i] = -1 if p == i else p

    # Vectorized depth propagation handles the (overwhelmingly common)
    # acyclic case: each pass resolves every node whose parent's depth is
    # known, so pass count = max hierarchy depth. The scalar chain walk
    # below only mops up nodes trapped in / under parent cycles.
    depth = np.where(eff_parent < 0, 0, -1)
    pending = np.flatnonzero(depth < 0)
    while len(pending):
        parent_depth = depth[eff_parent[pending]]
        ready = parent_depth >= 0
        if not ready.any():
            break   # every remaining node hangs from a cycle
        depth[pending[ready]] = parent_depth[ready] + 1
        pending = pending[~ready]

    for i in pending:
        i = int(i)
        if depth[i] >= 0:
            continue
        # Walk up the parent chain until hitting a resolved node, a root,
        # or a node already on this chain (cycle).
        chain: list[int] = []
        on_chain: set[int] = set()
        j = i
        while depth[j] < 0 and j not in on_chain:
            chain.append(j)
            on_chain.add(j)
            p = int(eff_parent[j])
            if p < 0:
                break
            j = p
        else:
            if depth[j] < 0:      # j is on this chain twice -> cycle entry
                eff_parent[j] = -1
                depth[j] = 0
        for k in reversed(chain):
            if depth[k] >= 0:
                continue
            p = int(eff_parent[k])
            depth[k] = 0 if p < 0 else depth[p] + 1
    return eff_parent, depth


def _batched_rot_x(deg: np.ndarray) -> np.ndarray:
    a = np.radians(deg)
    c, s = np.cos(a), np.sin(a)
    m = np.zeros((len(a), 3, 3))
    m[:, 0, 0] = 1.0
    m[:, 1, 1] = c
    m[:, 1, 2] = -s
    m[:, 2, 1] = s
    m[:, 2, 2] = c
    return m


def _batched_rot_y(deg: np.ndarray) -> np.ndarray:
    a = np.radians(deg)
    c, s = np.cos(a), np.sin(a)
    m = np.zeros((len(a), 3, 3))
    m[:, 0, 0] = c
    m[:, 0, 2] = s
    m[:, 1, 1] = 1.0
    m[:, 2, 0] = -s
    m[:, 2, 2] = c
    return m


def _batched_rot_z(deg: np.ndarray) -> np.ndarray:
    a = np.radians(deg)
    c, s = np.cos(a), np.sin(a)
    m = np.zeros((len(a), 3, 3))
    m[:, 0, 0] = c
    m[:, 0, 1] = -s
    m[:, 1, 0] = s
    m[:, 1, 1] = c
    m[:, 2, 2] = 1.0
    return m


def _batched_local_rotations(rx: np.ndarray, ry: np.ndarray, rz: np.ndarray,
                              mode: np.ndarray) -> np.ndarray:
    """Vectorized local_rotation_matrix(): both conventions computed batched,
    selected per node by rotation_mode."""
    htr = _batched_rot_z(-ry) @ _batched_rot_x(-rx) @ _batched_rot_z(-rz)
    exyz = _batched_rot_x(rx) @ _batched_rot_y(ry) @ _batched_rot_z(rz)
    return np.where((mode == ROTATION_MODE_EULER_XYZ)[:, None, None], exyz, htr)


_CUBE_FACE_ROTS_ARR = None   # filled lazily below (after _CUBE_FACE_BASE_ROTS exists)


def _batched_topo_rotations(ptopo: np.ndarray, tx: np.ndarray, ty: np.ndarray,
                             subspace: np.ndarray) -> np.ndarray:
    """Vectorized _topology_base_rotation(). ptopo is the PARENT's topo per
    node (-1 for roots, which take the identity — a root's child_local is its
    own rotation only)."""
    global _CUBE_FACE_ROTS_ARR
    n = len(ptopo)
    T = np.tile(np.eye(3), (n, 1, 1))
    m = ptopo == TOPO_ROD
    if m.any():
        T[m] = _batched_rot_z(ty[m])
    m = np.isin(ptopo, (TOPO_ZROD, TOPO_CYLINDER, TOPO_ZCYLINDER, TOPO_SPIRAL))
    if m.any():
        T[m] = _batched_rot_z(tx[m])
    m = np.isin(ptopo, (TOPO_SPHERE, TOPO_POINT, TOPO_TORUS, TOPO_ZTORUS))
    if m.any():
        T[m] = _batched_rot_z(tx[m]) @ _batched_rot_y(90.0 - ty[m])
    m = ptopo == TOPO_CUBE
    if m.any():
        if _CUBE_FACE_ROTS_ARR is None:
            _CUBE_FACE_ROTS_ARR = np.array(_CUBE_FACE_BASE_ROTS)
        T[m] = _CUBE_FACE_ROTS_ARR[np.clip(subspace[m], 0, 5)]
    return T


def _batched_kml(lon_deg, lat_deg, alt, radius):
    lon = np.radians(lon_deg)
    lat = np.radians(lat_deg)
    r = radius + alt
    cos_lat = np.cos(lat)
    return np.stack([
        r * cos_lat * np.cos(lon),
        r * cos_lat * np.sin(lon),
        r * np.sin(lat),
    ], axis=1)


def _batched_topo_offsets(ptopo: np.ndarray, tx: np.ndarray, ty: np.ndarray,
                           tz: np.ndarray, base_scale: float,
                           pratio: np.ndarray, subspace: np.ndarray,
                           ptopo_scale: np.ndarray | None = None) -> np.ndarray:
    """Vectorized _TOPO_OFFSET_FUNCS dispatch: each node's local-frame offset
    from its parent, per the PARENT's topo. Cartesian is both TOPO_NONE's
    behavior and the fallback for unknown topo ids, so it is the default fill
    (this also covers Plane/Video/Plot/Surface, whose offset IS Cartesian).

    ptopo_scale is the PARENT's Node.topo_scale per row (None = all 1.0,
    i.e. the pre-topo_scale behavior). It multiplies only the axes the
    parent's topology reads as distances — see LINEAR_PLACEMENT_AXES, which
    is also why this pre-multiply is the only place the whole feature
    touches the placement math."""
    if ptopo_scale is not None and not np.all(ptopo_scale == DEFAULT_TOPO_SCALE):
        linear = np.ones((len(ptopo), 3), dtype=bool)
        known = (ptopo >= 0) & (ptopo < TOPO_COUNT)
        linear[known] = _LINEAR_AXES_ARR[ptopo[known]]
        factor = np.where(linear, ptopo_scale[:, None], 1.0)
        tx = tx * factor[:, 0]
        ty = ty * factor[:, 1]
        tz = tz * factor[:, 2]

    off = np.stack([tx, ty, tz], axis=1)   # cartesian default

    m = ptopo == TOPO_SPHERE
    if m.any():
        off[m] = _batched_kml(tx[m], ty[m], tz[m], base_scale)
    m = np.isin(ptopo, (TOPO_POINT, TOPO_ZSPHERE))
    if m.any():
        off[m] = _batched_kml(tx[m], ty[m], tz[m], 0.0)

    for topo_id, has_minor in ((TOPO_TORUS, True), (TOPO_ZTORUS, False)):
        m = ptopo == topo_id
        if m.any():
            u = np.radians(tx[m])
            v = np.radians(ty[m])
            minor_r = pratio[m] * base_scale          # torus_radii()
            major_r = base_scale - minor_r
            tube_r = (minor_r + tz[m]) if has_minor else tz[m]
            radial = major_r + tube_r * np.cos(v)
            off[m] = np.stack([radial * np.cos(u), radial * np.sin(u),
                               tube_r * np.sin(v)], axis=1)

    m = ptopo == TOPO_ROD
    if m.any():
        angle = np.radians(ty[m])
        off[m] = np.stack([
            tz[m] * np.cos(angle),
            tz[m] * np.sin(angle),
            (tx[m] / 180.0) * 2.0 * base_scale * ROD_HEIGHT_FACTOR,
        ], axis=1)

    m = ptopo == TOPO_CYLINDER
    if m.any():
        angle = np.radians(tx[m])
        radial = base_scale + tz[m]
        off[m] = np.stack([radial * np.cos(angle), radial * np.sin(angle),
                           ty[m]], axis=1)

    m = np.isin(ptopo, (TOPO_ZCYLINDER, TOPO_ZROD))
    if m.any():
        angle = np.radians(tx[m])
        off[m] = np.stack([tz[m] * np.cos(angle), tz[m] * np.sin(angle),
                           ty[m]], axis=1)

    m = ptopo == TOPO_PIN
    if m.any():
        off[m] = np.stack([ty[m], tz[m], base_scale + tx[m]], axis=1)

    for topo_id, on_surface in ((TOPO_CUBE, True), (TOPO_ZCUBE, False)):
        m = ptopo == topo_id
        if m.any():
            faces = np.array(_CUBE_FACES, dtype=np.float64)   # (6, 3, 3): n, u, v
            f = faces[np.clip(subspace[m], 0, 5)]
            dist = (base_scale + tz[m]) if on_surface else tz[m]
            off[m] = (dist[:, None] * f[:, 0]
                      + tx[m][:, None] * f[:, 1]
                      + ty[m][:, None] * f[:, 2])

    m = ptopo == TOPO_SPIRAL
    if m.any():
        theta = np.radians(tx[m])
        radial = base_scale + tz[m]
        off[m] = np.stack([radial * np.cos(theta), radial * np.sin(theta),
                           (tx[m] / 360.0) * base_scale + ty[m]], axis=1)
    return off


def compute_world_transforms(nodes: list[Node], base_scale: float,
                              world_basis_override: np.ndarray | None = None,
                              ) -> SceneTransforms:
    """Resolve every node's transform state in level-ordered numpy batches.

    Numerically equivalent to the old recursive compute_world_bases +
    compute_world_positions pair (see their docstrings for the math contract),
    ~20x faster at 100k nodes. world_basis_override substitutes a caller-
    supplied (n,3,3) basis array for the offset transforms in the position
    pass (compute_world_positions's optional world_basis dict argument).
    """
    n = len(nodes)
    if n == 0:
        e3 = np.empty((0, 3, 3))
        return SceneTransforms({}, np.empty(0, dtype=np.int64),
                               e3, e3.copy(), e3.copy(), np.empty((0, 3)),
                               np.empty(0, dtype=np.int64))

    eff_parent, depth = _resolve_hierarchy(nodes)

    # One pass over the node list (a comprehension per field costs ~2x the
    # attribute lookups' own time at 100k nodes).
    fields = np.array([
        (nd.translate_x, nd.translate_y, nd.translate_z,
         nd.rotate_x, nd.rotate_y, nd.rotate_z,
         nd.scale_x, nd.scale_y, nd.scale_z,
         nd.rotation_mode, nd.topo, nd.ratio, nd.subspace, nd.type,
         nd.topo_scale)
        for nd in nodes
    ], dtype=np.float64)
    tx, ty, tz = fields[:, 0], fields[:, 1], fields[:, 2]
    rx, ry, rz = fields[:, 3], fields[:, 4], fields[:, 5]
    scale = fields[:, 6:9]
    mode = fields[:, 9].astype(np.int64)
    topo = fields[:, 10].astype(np.int64)
    ratio = fields[:, 11]
    subspace = fields[:, 12].astype(np.int64)
    ntype = fields[:, 13].astype(np.int64)
    topo_scale = fields[:, 14]

    is_root = eff_parent < 0
    safe_parent = np.where(is_root, 0, eff_parent)
    ptopo = np.where(is_root, -1, topo[safe_parent])
    pratio = np.where(is_root, 0.0, ratio[safe_parent])
    # A root's translate IS its world position, never a topology offset, so
    # its (unused) offset row is computed at the neutral scale.
    ptopo_scale = np.where(is_root, DEFAULT_TOPO_SCALE, topo_scale[safe_parent])

    # World Grid (type=6) parents — see the "World Grid semantics" comment
    # block above _cartesian_offset. Flat grids place children Cartesian at
    # their coordinates relative to the extents-window center; globe grids
    # (sphere geometry — Node.grid_is_globe) place them by KML lon/lat/
    # elevation on the sphere surface. Both regardless of the grid row's
    # topo field.
    grid_center = np.zeros((n, 2))
    grid_globe = np.zeros(n, dtype=bool)
    for i in np.flatnonzero(ntype == NODE_TYPE_GRID):
        nd = nodes[int(i)]
        grid_center[i] = nd.grid_center()
        grid_globe[i] = nd.grid_is_globe()
    grid_child = ~is_root & (ntype[safe_parent] == NODE_TYPE_GRID)
    globe_child = grid_child & grid_globe[safe_parent]
    flat_child = grid_child & ~globe_child

    own_rot = _batched_local_rotations(rx, ry, rz, mode)
    topo_rot = _batched_topo_rotations(ptopo, tx, ty, subspace)
    if flat_child.any():
        # Flat-grid children take no topology base rotation (their
        # placement is plain Cartesian).
        topo_rot[flat_child] = np.eye(3)
    if globe_child.any():
        # Globe children orient outward from the sphere surface at their
        # lon/lat, same scaffold as TOPO_SPHERE children.
        topo_rot[globe_child] = (_batched_rot_z(tx[globe_child])
                                 @ _batched_rot_y(90.0 - ty[globe_child]))
    child_local = topo_rot @ own_rot          # identity topo_rot for roots
    local_scaled = child_local * scale[:, None, :]   # m @ diag(scale)
    offsets = _batched_topo_offsets(ptopo, tx, ty, tz, base_scale,
                                     pratio, subspace, ptopo_scale)
    if flat_child.any():
        pc = grid_center[safe_parent]
        offsets[flat_child] = np.stack([
            tx[flat_child] - pc[flat_child, 0],
            ty[flat_child] - pc[flat_child, 1],
            tz[flat_child],
        ], axis=1)
    if globe_child.any():
        offsets[globe_child] = _batched_kml(
            tx[globe_child], ty[globe_child], tz[globe_child],
            GRID_GLOBE_RADIUS)

    world_basis = np.empty((n, 3, 3))
    parent_basis = np.tile(np.eye(3), (n, 1, 1))
    world_pos = np.empty((n, 3))
    roots = np.flatnonzero(is_root)
    world_basis[roots] = local_scaled[roots]
    world_pos[roots] = np.stack([tx, ty, tz], axis=1)[roots]

    offset_basis = world_basis if world_basis_override is None else world_basis_override

    # Level-ordered composition: each level's parents are fully resolved
    # before the level is processed, so one batched matmul per level.
    order = np.argsort(depth, kind='stable')
    sorted_depth = depth[order]
    max_depth = int(sorted_depth[-1])
    bounds = np.searchsorted(sorted_depth, np.arange(max_depth + 2))
    for level in range(1, max_depth + 1):
        c = order[bounds[level]:bounds[level + 1]]
        p = eff_parent[c]
        pb = world_basis[p]   # fancy index -> already a copy, safe to patch
        gsel = ntype[p] == NODE_TYPE_GRID
        if gsel.any():
            # Children of a World Grid compose onto the grid's rotation-only
            # basis (everything above the grid, plus the grid's own rotation,
            # minus its scale): the grid's scale re-spaces child POSITIONS
            # (world_pos below uses the grid's full world_basis) but must not
            # stretch child shapes or their own subtrees' spacing — the
            # ANTz-documented Grid rule ("does NOT affect their size").
            pg = p[gsel]
            pb[gsel] = parent_basis[pg] @ child_local[pg]
        parent_basis[c] = pb
        world_basis[c] = pb @ local_scaled[c]
        world_pos[c] = world_pos[p] + np.einsum(
            'nij,nj->ni', offset_basis[p], offsets[c])

    row_of_id: dict[int, int] = {}
    for i, nd in enumerate(nodes):
        row_of_id.setdefault(nd.id, i)

    return SceneTransforms(row_of_id, eff_parent, world_basis, parent_basis,
                           child_local, world_pos, depth)


def update_world_transform_rows(nodes: list[Node], base_scale: float,
                                t: SceneTransforms, rows: np.ndarray) -> None:
    """Recompute a subset of an existing SceneTransforms in place.

    The per-frame engine behind Channels playback: when an animation mutates
    translate/rotate/scale on a known set of nodes, this refreshes
    child_local, parent_basis, world_basis and world_pos for exactly `rows`
    (reading parent state straight from the arrays) at O(len(rows)) cost
    instead of a full-scene compute_world_transforms.

    Contract:
    * `rows` must be closed under descendants: if a node's transform inputs
      changed, every descendant's row must also be present (their world
      state depends on it). Depth ordering below then guarantees any dirty
      parent is recomputed before its children; a parent NOT in `rows` has,
      by the closure rule, no changed ancestor, so its cached state is valid.
    * The HIERARCHY (parent_id, and the node list itself) must be unchanged
      since the last full compute_world_transforms: t.eff_parent, t.depth
      and t.row_of_id are reused as-is rather than rederived. Every other
      per-node input IS re-read fresh below — translate/rotate/scale plus
      rotation_mode, subspace, and the parent's topo/ratio/topo_scale/grid
      form — so a
      Channels animation binding shape fields (ratio, topo, geometry; see
      channel_engine._TRANSFORM_FIELDS) is handled correctly here, provided
      the closure rule above puts the changed node's descendants in `rows`.

    The math here must stay numerically identical to
    compute_world_transforms — same helpers, same composition order — since
    refreshed rows feed the same render/pick contract.
    """
    k = len(rows)
    if k == 0:
        return
    sub = [nodes[int(i)] for i in rows]
    fields = np.array([
        (nd.translate_x, nd.translate_y, nd.translate_z,
         nd.rotate_x, nd.rotate_y, nd.rotate_z,
         nd.scale_x, nd.scale_y, nd.scale_z,
         nd.rotation_mode, nd.subspace)
        for nd in sub
    ], dtype=np.float64)
    tx, ty, tz = fields[:, 0], fields[:, 1], fields[:, 2]
    rx, ry, rz = fields[:, 3], fields[:, 4], fields[:, 5]
    scale = fields[:, 6:9]
    mode = fields[:, 9].astype(np.int64)
    subspace = fields[:, 10].astype(np.int64)

    eff_parent = t.eff_parent[rows]
    is_root = eff_parent < 0
    ptopo = np.full(k, -1, dtype=np.int64)
    pratio = np.zeros(k)
    ptopo_scale = np.full(k, DEFAULT_TOPO_SCALE)
    pgrid = np.zeros(k, dtype=bool)   # parent is a World Grid (type=6)
    pglobe = np.zeros(k, dtype=bool)  # ... in globe (sphere-geometry) form
    pcenter = np.zeros((k, 2))        # grid parents' extents-window center
    nr = np.flatnonzero(~is_root)
    if nr.size:
        ptopo[nr] = [nodes[int(p)].topo for p in eff_parent[nr]]
        pratio[nr] = [nodes[int(p)].ratio for p in eff_parent[nr]]
        ptopo_scale[nr] = [nodes[int(p)].topo_scale for p in eff_parent[nr]]
        for j in nr:
            parent = nodes[int(eff_parent[j])]
            if parent.type == NODE_TYPE_GRID:
                pgrid[j] = True
                pglobe[j] = parent.grid_is_globe()
                pcenter[j] = parent.grid_center()
    pflat = pgrid & ~pglobe

    own_rot = _batched_local_rotations(rx, ry, rz, mode)
    topo_rot = _batched_topo_rotations(ptopo, tx, ty, subspace)
    if pflat.any():
        topo_rot[pflat] = np.eye(3)   # flat-grid children: plain Cartesian
    if pglobe.any():
        topo_rot[pglobe] = (_batched_rot_z(tx[pglobe])
                            @ _batched_rot_y(90.0 - ty[pglobe]))
    child_local = topo_rot @ own_rot          # identity topo_rot for roots
    local_scaled = child_local * scale[:, None, :]
    offsets = _batched_topo_offsets(ptopo, tx, ty, tz, base_scale,
                                     pratio, subspace, ptopo_scale)
    if pflat.any():
        offsets[pflat] = np.stack([
            tx[pflat] - pcenter[pflat, 0],
            ty[pflat] - pcenter[pflat, 1],
            tz[pflat],
        ], axis=1)
    if pglobe.any():
        offsets[pglobe] = _batched_kml(tx[pglobe], ty[pglobe], tz[pglobe],
                                       GRID_GLOBE_RADIUS)
    t.child_local[rows] = child_local

    # Level-ordered in-place update, mirroring compute_world_transforms'
    # per-level composition but over the subset only.
    order = np.argsort(t.depth[rows], kind='stable')
    sorted_depth = t.depth[rows][order]
    bounds = np.flatnonzero(np.diff(sorted_depth) > 0) + 1
    for gsel in np.split(order, bounds):
        grows = rows[gsel]
        p = t.eff_parent[grows]
        rootm = p < 0
        if rootm.any():
            rsel = gsel[rootm]
            t.world_basis[rows[rsel]] = local_scaled[rsel]
            t.world_pos[rows[rsel]] = np.stack(
                [tx[rsel], ty[rsel], tz[rsel]], axis=1)
        if (~rootm).any():
            csel = gsel[~rootm]
            crows = rows[csel]
            pp = p[~rootm]
            pb = t.world_basis[pp]   # fancy index -> already a copy
            # Positions first, from the parent's FULL basis (scale included —
            # a World Grid's scale deliberately re-spaces its children) ...
            t.world_pos[crows] = t.world_pos[pp] + np.einsum(
                'nij,nj->ni', pb, offsets[csel])
            gm = pgrid[csel]
            if gm.any():
                # ... then patch World Grid parents' SHAPE basis to exclude
                # the grid's scale (mirrors compute_world_transforms' per-
                # level override) before composing child bases from it.
                pg = pp[gm]
                pb[gm] = t.parent_basis[pg] @ t.child_local[pg]
            t.parent_basis[crows] = pb
            t.world_basis[crows] = pb @ local_scaled[csel]


def compute_world_bases(
    nodes: list[Node],
) -> tuple[dict[int, tuple], dict[int, tuple], dict[int, tuple]]:
    """
    Resolve every node's cumulative rotation+scale and return three dicts:

    world_basis[id]   = parent_basis[id] @ child_local[id] @ diag(own raw scale)
                        (the full recursive rotation+scale composition, the
                        same thing a real glPushMatrix/glPopMatrix chain
                        would produce — fusing each level's rotation AND
                        scale into one matrix before moving to the next
                        level)
    parent_basis[id]  = parent's world_basis (identity for roots)
    child_local[id]   = topo_base_rotation(parent.topo, placement) @ own
                        rotation (this node's own orientation contribution,
                        no scale)

    Scale here is deliberately kept in RAW (dimensionless) units — no
    base_scale baked in. base_scale (the global geometry-to-world-units
    conversion) is applied exactly once by node_world_matrix and
    compute_world_positions, not once per hierarchy level, which would
    otherwise compound it as base_scale**depth.

    Fusing rotation and scale recursively (rather than tracking cumulative
    rotation and a flat cumulative-scale vector in separate dicts and
    sandwiching them together post-hoc, which was tried previously) is
    required for correctness beyond one level of nesting: rotation and
    non-uniform scale don't commute, so flattening cumulative scale into a
    flat per-axis vector silently misapplies an ancestor's stretch to the
    wrong world axis as soon as an intermediate level has its own rotation —
    e.g. rotating an unrelated intermediate parent changes a grandchild's
    rendered *shape*, not just its position/orientation, which is the bug
    this replaces.

    For a node whose parent is a root, the rendering matrix built from these
    three dicts (see node_world_matrix) is algebraically identical to the
    ANTz-validated one-level-deep formula `R_parent @ S_parent @
    R_child_local @ S_child` (a root's own scale/rotation equal its
    cumulative scale/world rotation, since it has no ancestors), so this
    cannot regress that already-confirmed case (e.g. a sphere stretched
    along X producing a diamond-shaped child at 45°) while correctly
    generalizing to arbitrary depth.

    Compatibility wrapper over compute_world_transforms (the vectorized
    engine); base_scale plays no role in the bases, so any value works for
    the positions the engine computes alongside.
    """
    t = compute_world_transforms(nodes, base_scale=1.0)
    world_basis:  dict[int, tuple] = {}
    parent_basis: dict[int, tuple] = {}
    child_local:  dict[int, tuple] = {}
    for node_id, row in t.row_of_id.items():
        world_basis[node_id] = tuple(map(tuple, t.world_basis[row].tolist()))
        parent_basis[node_id] = tuple(map(tuple, t.parent_basis[row].tolist()))
        child_local[node_id] = tuple(map(tuple, t.child_local[row].tolist()))
    return world_basis, parent_basis, child_local


# All _*_offset wrappers share the signature:
#   (tx, ty, tz, base_radius, parent_ratio, child_subspace=0)
# where base_radius is the topology's fixed, UNSCALED base size (base_scale,
# or 0.0 for the Z-variants/Point that place children through the center).
# No scale appears here at all — compute_world_positions transforms the
# returned local-frame offset by the parent's world_basis (see
# compute_world_bases), which applies every ancestor's rotation and per-axis
# stretch in the mathematically correct order, however many levels deep.
# child_subspace is only used by _cube_offset/_zcube_offset.
#
# The parent's topo_scale does not appear here either: callers pre-multiply
# the distance-valued axes before dispatching (scale_linear_axes /
# _batched_topo_offsets), which is exactly equivalent and keeps every
# function below the readable, unqualified statement of its topology's
# coordinate system. See LINEAR_PLACEMENT_AXES near the top of this file.

# ---------------------------------------------------------------------------
# World Grid semantics (parent TYPE = 6, not a topo id — see NODE_TYPE_GRID).
#
# A World Grid maps its children's translate_x/y as coordinates within the
# grid's extents window (Node.grid_extents(), default the whole earth in
# equirectangular degrees) and translate_z as elevation:
#
#     offset = (tx - center_lon, ty - center_lat, tz)
#
# i.e. plain Cartesian recentered on the window midpoint, regardless of the
# grid row's topo field, then transformed by the grid's world_basis like any
# child offset — so the grid's scale_x/y/z re-space children per axis and
# its rotation carries them around. The default window centers at (0, 0),
# making a grid at the origin with scale 1 an exact 1:1 frame: a child at
# translate (180, 90) lands at world (180, 90).
#
# A grid whose geometry is Sphere/Sphere Wire is a GLOBE (Node.grid_is_globe):
# children place by KML lon/lat on the sphere surface at radius
# GRID_GLOBE_RADIUS (180/pi, so the equator is exactly 360 units — the flat
# 1:1 map rolled up), translate_z is a radial elevation, and each child gets
# the TOPO_SPHERE outward-facing base rotation. Extents recentering does not
# apply on a globe — lon/lat are absolute positions on the sphere.
#
# Unlike every topo-driven parent, a grid's scale must NOT stretch its
# children's rendered shape or their subtrees' internal spacing (the
# ANTz-documented Grid rule: scaling "compacts the spacing of attached
# nodes but does NOT affect their size, and is axis specific") — see the
# per-level shape-basis override in compute_world_transforms /
# update_world_transform_rows, keyed on the parent's type. This holds for
# both flat and globe forms.
#
# This special-casing lives in the vectorized engine only; the scalar
# offset functions below dispatch purely on parent topo and stay the
# readable per-TOPOLOGY spec.
# ---------------------------------------------------------------------------

def _cartesian_offset(tx, ty, tz, _base_radius, _parent_ratio, _child_subspace=0):
    """Plain Cartesian (dx, dy, dz) offset from the parent's center, in the
    parent's own local frame. This is the Plane/Grid topology's coordinate
    system (translate_x/y position a child within the parent's local plane,
    translate_z is elevation above it) and the fallback for topologies not
    yet modeled.
    """
    return (tx, ty, tz)


def _sphere_offset(tx, ty, tz, base_radius, _parent_ratio, _child_subspace=0):
    return kml_offset(tx, ty, tz, base_radius)


def _torus_offset(tx, ty, tz, base_radius, parent_ratio, _child_subspace=0):
    u = math.radians(tx)
    v = math.radians(ty)
    major_r, minor_r = torus_radii(parent_ratio, base_radius)
    tube_r = minor_r + tz
    cos_v = math.cos(v)
    radial = major_r + tube_r * cos_v
    return (
        radial * math.cos(u),
        radial * math.sin(u),
        tube_r * math.sin(v),
    )


def _rod_offset(tx, ty, tz, base_radius, _parent_ratio, _child_subspace=0):
    angle = math.radians(ty)
    radial = tz
    world_z = (tx / 180.0) * 2.0 * base_radius * ROD_HEIGHT_FACTOR
    return (
        radial * math.cos(angle),
        radial * math.sin(angle),
        world_z,
    )


def _cylinder_offset(tx, ty, tz, base_radius, _parent_ratio, _child_subspace=0):
    """Cylinder topology (per Topology-Guide.md: 'Children on cylindrical
    surface'):
      translate_x -> angle (degrees) around the cylinder's axis (local Z,
                     matching GEO_CYLINDER's own local-Z orientation)
      translate_y -> height along the axis, literal local-Z offset from the
                     parent's center (not normalized to the rendered length —
                     unlike Rod, which deliberately maps [0,180] to the full
                     physical cylinder length; Cylinder has no such
                     documented convention, so this follows Pin's plainer
                     'literal height value' precedent instead)
      translate_z -> radial distance from the axis, riding on the actual
                     rendered surface (translate_z=0 = the surface) — the
                     Zcylinder variant (radius=0) is explicitly described as
                     'akin to cylindrical coords but with radius=0.0',
                     confirming base Cylinder's translate_z=0 means the
                     surface, not the axis.
    """
    angle = math.radians(tx)
    radial = base_radius + tz
    return (
        radial * math.cos(angle),
        radial * math.sin(angle),
        ty,
    )


def _point_offset(tx, ty, tz, _base_radius, _parent_ratio, _child_subspace=0):
    """Point topology: longitude/latitude/altitude from the parent center —
    a child at lon=0, alt=5 sits 5 units out along the parent's local +X;
    world_basis then carries that through the parent's (and every
    ancestor's) per-axis scale and rotation."""
    return kml_offset(tx, ty, tz, 0.0)


def _pin_offset(tx, ty, tz, base_radius, _parent_ratio, _child_subspace=0):
    return (ty, tz, base_radius + tx)


def _cube_offset(tx, ty, tz, base_radius, _parent_ratio, child_subspace=0):
    face_idx = max(0, min(5, child_subspace))
    n, u, v = _CUBE_FACES[face_idx]
    dist = base_radius + tz
    return (
        dist * n[0] + tx * u[0] + ty * v[0],
        dist * n[1] + tx * u[1] + ty * v[1],
        dist * n[2] + tx * u[2] + ty * v[2],
    )


def _spiral_offset(tx, ty, tz, base_radius, _parent_ratio, _child_subspace=0):
    theta = math.radians(tx)
    height = (tx / 360.0) * base_radius
    return (
        (base_radius + tz) * math.cos(theta),
        (base_radius + tz) * math.sin(theta),
        height + ty,
    )


# ---------------------------------------------------------------------------
# Z-topology variants (9-13): each is "akin to" an already-implemented
# topology with its surface/radius term zeroed out, so children sit at/through
# the parent's center instead of on its rendered surface (Topology-Guide.md's
# "Important Scale and Position Notes").
# ---------------------------------------------------------------------------

def _zcube_offset(tx, ty, tz, _base_radius, _parent_ratio, child_subspace=0):
    """Akin to Cube, but dist = tz only (no base_radius term) — a child at
    tz=0 sits at the parent's center rather than on the cube face."""
    face_idx = max(0, min(5, child_subspace))
    n, u, v = _CUBE_FACES[face_idx]
    dist = tz
    return (
        dist * n[0] + tx * u[0] + ty * v[0],
        dist * n[1] + tx * u[1] + ty * v[1],
        dist * n[2] + tx * u[2] + ty * v[2],
    )


def _zsphere_offset(tx, ty, tz, _base_radius, _parent_ratio, _child_subspace=0):
    """Akin to KML/Sphere coords, but translate_z=0 is the center point (the
    radius is forced to 0) rather than the sphere's surface."""
    return kml_offset(tx, ty, tz, 0.0)


def _ztorus_offset(tx, ty, tz, base_radius, parent_ratio, _child_subspace=0):
    """Akin to Torus, but with zero tube thickness: the minor (tube) radius
    is dropped, so translate_z directly offsets outward from the major
    (orbital) ring instead of riding on a donut surface."""
    u = math.radians(tx)
    v = math.radians(ty)
    major_r, _minor_r = torus_radii(parent_ratio, base_radius)
    tube_r = tz  # zero thickness: no minor-radius contribution
    cos_v = math.cos(v)
    radial = major_r + tube_r * cos_v
    return (
        radial * math.cos(u),
        radial * math.sin(u),
        tube_r * math.sin(v),
    )


def _zcylinder_offset(tx, ty, tz, _base_radius, _parent_ratio, _child_subspace=0):
    """Akin to Cylinder, but with radius=0: children collapse onto the
    central axis (translate_z directly offsets outward from the axis instead
    of riding on the cylinder's surface)."""
    angle = math.radians(tx)
    radial = tz
    return (
        radial * math.cos(angle),
        radial * math.sin(angle),
        ty,
    )


def _zrod_offset(tx, ty, tz, base_radius, parent_ratio, child_subspace=0):
    """Akin to Zcylinder — identical placement math; the only documented
    difference (scale not affecting child size) is a separate rendering rule,
    not a position difference here."""
    return _zcylinder_offset(tx, ty, tz, base_radius, parent_ratio, child_subspace)


def _plot_offset(tx, ty, tz, _base_radius, _parent_ratio, _child_subspace=0):
    """Plot topology (1D/2D/3D line plot, GPS, Oscilloscope): children placed
    at their Cartesian translate_x/y/z coordinates — same spatial layout as
    Plane, distinct semantic meaning."""
    return (tx, ty, tz)


def _pointcloud_offset(tx, ty, tz, _base_radius, _parent_ratio, _child_subspace=0):
    """Point Cloud topology (unstructured scan data, LIDAR): children placed
    at their Cartesian translate_x/y/z coordinates.

    ANTz's own rule — npgldraw.c:641 comments it "children use direct
    Cartesian coordinates: translate.xyz is world position". Cartesian is
    also `_batched_topo_offsets`' default fill and the fallback for unknown
    topo ids, so the batched engine needs no case for this topology, and an
    older build reading a topo=18 file still places every point correctly
    (it just draws them as individual glyphs instead of one GL_POINTS batch).

    The topology is a RENDERING contract, not a placement one: the viewport
    draws a cloud parent's children as a single batched point array in place
    of their per-child glyphs — see Viewport._draw_point_clouds.
    """
    return (tx, ty, tz)


def _surface_offset(tx, ty, tz, _base_radius, _parent_ratio, _child_subspace=0):
    """Surface topology (deformable grid, FFT, LIDAR, sound sphere): children
    placed at their Cartesian translate_x/y/z coordinates — translate_x/y
    form the grid position, translate_z is the height value at that grid
    point."""
    return (tx, ty, tz)


_TOPO_OFFSET_FUNCS = {
    TOPO_CUBE:      _cube_offset,
    TOPO_SPHERE:    _sphere_offset,
    TOPO_TORUS:     _torus_offset,
    TOPO_CYLINDER:  _cylinder_offset,
    TOPO_PIN:       _pin_offset,
    TOPO_ROD:       _rod_offset,
    TOPO_POINT:     _point_offset,
    TOPO_PLANE:     _cartesian_offset,
    TOPO_ZCUBE:     _zcube_offset,
    TOPO_ZSPHERE:   _zsphere_offset,
    TOPO_ZTORUS:    _ztorus_offset,
    TOPO_ZCYLINDER: _zcylinder_offset,
    TOPO_ZROD:      _zrod_offset,
    TOPO_VIDEO:     _cartesian_offset,   # flat screen: children at Cartesian coords
    TOPO_SPIRAL:    _spiral_offset,
    TOPO_PLOT:      _plot_offset,
    TOPO_SURFACE:   _surface_offset,
    TOPO_POINTCLOUD: _pointcloud_offset,
}


def placement_offset(parent: Node | None, tx: float, ty: float, tz: float,
                      base_scale: float, subspace: int = 0
                      ) -> tuple[float, float, float]:
    """One child's local-frame offset from its parent, for arbitrary
    translate values rather than the child's current ones.

    Single-node counterpart of the offset half of compute_world_transforms:
    same three cases in the same order (root, World Grid parent, parent
    topology), so the two must be kept numerically identical. World space is
    then `parent.world_pos + parent.world_basis @ this` — for a root, where
    there is no parent basis, translate IS the world position, which is why
    the None case returns the coordinates unchanged.

    The transform gizmo differentiates this numerically to find the world
    direction each translate field actually pushes a node (glyphviz_core/
    gizmo.py's translate_gradient) — exact for every topology, including the
    angular ones whose mapping is nonlinear.
    """
    if parent is None:
        return (tx, ty, tz)
    if parent.type == NODE_TYPE_GRID:
        if parent.grid_is_globe():
            return kml_offset(tx, ty, tz, GRID_GLOBE_RADIUS)
        cx, cy = parent.grid_center()
        return (tx - cx, ty - cy, tz)
    tx, ty, tz = scale_linear_axes(parent, tx, ty, tz)
    fn = _TOPO_OFFSET_FUNCS.get(parent.topo, _cartesian_offset)
    return fn(tx, ty, tz, base_scale, parent.ratio, subspace)


def compute_world_positions(
    nodes: list[Node],
    base_scale: float,
    world_basis: dict[int, tuple] | None = None,
) -> dict[int, tuple[float, float, float]]:
    """
    Resolve every node's world-space position by walking its parent chain.

    Root nodes (parent_id missing/unresolvable) use translate_x/y/z directly
    as Cartesian world coordinates. Each child's world position is its
    parent's world position plus an offset derived from the parent's
    topology — so moving a parent carries its whole subtree with it.

    The topology offset (e.g. a longitude/latitude point on the parent's
    surface) is computed in the parent's own *unscaled* local frame, with
    `base_scale` standing in for the parent's rendered base size — see the
    `_*_offset` functions above — then transformed into world space by the
    parent's `world_basis` (from compute_world_bases), the parent's full
    recursive rotation+scale composition: this is what threads every
    ancestor's per-axis stretch and rotation through correctly, however many
    non-uniformly-scaled, rotated levels sit above it.

    Compatibility wrapper over compute_world_transforms (the vectorized
    engine). The world_basis dict (id -> 3x3, defaulting to identity for
    missing ids — including for ALL nodes when the argument is omitted,
    matching the old `world_basis or {}` behavior) is converted to a per-row
    array and substituted into the engine's offset transforms.
    """
    world_basis = world_basis or {}
    override = np.array(
        [world_basis.get(nd.id, _MAT_IDENTITY) for nd in nodes],
        dtype=np.float64,
    ) if nodes else None
    t = compute_world_transforms(nodes, base_scale, world_basis_override=override)
    resolved: dict[int, tuple[float, float, float]] = {}
    for node_id, row in t.row_of_id.items():
        x, y, z = t.world_pos[row]
        resolved[node_id] = (float(x), float(y), float(z))
    return resolved
