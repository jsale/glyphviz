"""
Parent-child spatial topology — converts a child's translate_x/y/z into a
world-space offset from its parent, according to the parent's np_topo_id.

See gaiaviz-skill/references/structure/Topology-Guide.md for the full
per-topology coordinate conventions. New topologies are added by writing an
offset function and registering it in _TOPO_OFFSET_FUNCS.
"""
import math

from .geometry import CYLINDER_RADIUS_RATIO, ROD_HEIGHT_FACTOR, torus_radii
from .node import Node

# np_topo_id values — full reference list from Topology-Guide.md.
# Only a subset has dedicated offset functions below (see _TOPO_OFFSET_FUNCS);
# the rest fall back to a plain Cartesian offset until they're modeled.
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
TOPO_COUNT     = 18

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
}


def kml_offset(longitude: float, latitude: float, altitude: float, radius: float, scale: float = 1.0):
    """
    Convert KML-style longitude/latitude/altitude into a Cartesian offset from
    the parent sphere's center (uniform radius — used by Point topology and
    as the uniform-scale degenerate case).  For sphere parents with non-uniform
    scale use kml_ellipsoid_offset instead.
    """
    lon = math.radians(longitude)
    lat = math.radians(latitude)
    r = radius + altitude * scale
    cos_lat = math.cos(lat)
    return (
        r * cos_lat * math.cos(lon),
        r * cos_lat * math.sin(lon),
        r * math.sin(lat),
    )


def kml_ellipsoid_offset(longitude: float, latitude: float, altitude: float,
                          rx: float, ry: float, rz: float, alt_scale: float = 1.0):
    """
    Child offset for a sphere-topology parent whose rendered surface is an
    ellipsoid with per-axis semi-axes (rx, ry, rz).

    Uses the 'stretched-sphere' parametrisation that matches node_world_matrix:
        surface point = (rx·cos(lat)·cos(lon),
                         ry·cos(lat)·sin(lon),
                         rz·sin(lat))
    Altitude offsets further outward along the local sphere-normal direction
    (nx, ny, nz), scaled by alt_scale:
        final = ((rx + alt)·nx, (ry + alt)·ny, (rz + alt)·nz)

    When rx == ry == rz == radius this reduces exactly to kml_offset.
    The per-axis radii ensure that scaling the parent along X moves only
    children whose placement longitude faces X, not all children — matching
    ANTz's ellipsoidal parent-child placement.
    """
    lon = math.radians(longitude)
    lat = math.radians(latitude)
    alt = altitude * alt_scale
    cos_lat = math.cos(lat)
    nx = cos_lat * math.cos(lon)
    ny = cos_lat * math.sin(lon)
    nz = math.sin(lat)
    return (
        (rx + alt) * nx,
        (ry + alt) * ny,
        (rz + alt) * nz,
    )


def torus_offset(major_angle: float, minor_angle: float, elevation: float, radius: float,
                 ratio: float, scale: float = 1.0):
    """
    Convert torus-relative coordinates into a Cartesian offset from the
    parent's center, on (or above) the donut's surface — mirroring the
    sphere/KML convention:
      longitude-like translate_x -> angle around the major (orbital) circle
      latitude-like  translate_y -> angle around the minor (tube) circle
      altitude-like  translate_z -> elevation, offset outward from the tube surface

    Matches _draw_torus's local-space orientation: the major circle lies in
    the local XY plane and the tube cross-section extends along local Z.

    `ratio` is the parent's own torus `ratio` property — it determines the
    donut's major/minor radius proportions (see geometry.torus_radii), so a
    child rides on the actual rendered surface regardless of the parent's
    ratio.

    `elevation` is local-space, carried into world space by `scale` (the
    parent's cumulative world scale) — see kml_offset for why.
    """
    u = math.radians(major_angle)
    v = math.radians(minor_angle)
    major_r, minor_r = torus_radii(ratio, radius)
    tube_r = minor_r + elevation * scale
    cos_v = math.cos(v)
    radial = major_r + tube_r * cos_v
    return (
        radial * math.cos(u),
        radial * math.sin(u),
        tube_r * math.sin(v),
    )


def rod_offset(axial_pos: float, angle_deg: float, elevation: float, radius: float, scale: float = 1.0):
    """
    Convert rod-relative coordinates into a Cartesian offset from the
    parent's CENTER, matching the GlyphViz rod-topology convention:
      translate_x -> position along the rod's length (local Z axis);
                     0 = bottom end of cylinder, 180 = top end.
                     (ANTz uses 0 = top, -180 = bottom; GlyphViz inverts sign.)
      translate_y -> angle (degrees) around the rod's circumference
      translate_z -> radial distance from the cylinder's center axis
                     (0 = on the axis; positive = outward)

    `radius` is the parent's effective rendered radius (including base_scale).
    The full [0, 180] axial range maps to the cylinder's actual rendered length
    so 13 children spaced 15 units apart fill the cylinder evenly.
    """
    angle = math.radians(angle_deg)
    radial = elevation * scale
    # Map [0, 180] to [0, 2*half_length]: bottom cap of the parent cylinder
    # sits at the parent's world origin, so tx=0 lands a child there and
    # tx=180 lands it at the top cap — matching ANTz's one-end-at-origin convention.
    world_z = (axial_pos / 180.0) * 2.0 * radius * ROD_HEIGHT_FACTOR
    return (
        radial * math.cos(angle),
        radial * math.sin(angle),
        world_z,
    )


def pin_offset(tx: float, ty: float, tz: float, parent_radius: float, scale: float = 1.0):
    """
    Stack children vertically above the parent's top (along the Z axis):
      translate_x -> height above the parent's topmost point
      translate_y -> X offset from the stack axis
      translate_z -> Y offset from the stack axis

    Designed for pin-like arrangements where items hang or stack in a column
    above a parent node.
    """
    s = scale
    return (
        ty * s,
        tz * s,
        parent_radius + tx * s,
    )


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


def cube_offset(tx: float, ty: float, tz: float, parent_radius: float,
                scale: float = 1.0, subspace: int = 0):
    """
    Place a child on one of the six faces of the parent cube:
      child.subspace (0–5) selects the face (see _CUBE_FACES)
      translate_x    -> "right" (u-axis) within the face plane
      translate_y    -> "up" (v-axis) within the face plane
      translate_z    -> elevation above the face surface (along face normal)

    The face center is at parent_radius * face_normal from the parent center.
    For a cube glyph scaled by glScalef(rx, ry, rz), each face's center is
    exactly at radius distance along its normal, so children land on the
    actual rendered cube face when translate_z == 0.
    """
    face_idx = max(0, min(5, subspace))
    n, u, v = _CUBE_FACES[face_idx]
    s = scale
    dist = parent_radius + tz * s
    return (
        dist * n[0] + tx * s * u[0] + ty * s * v[0],
        dist * n[1] + tx * s * u[1] + ty * s * v[1],
        dist * n[2] + tx * s * u[2] + ty * s * v[2],
    )


def spiral_offset(tx: float, ty: float, tz: float, parent_radius: float, scale: float = 1.0):
    """
    Custom conical helix (spiral) topology — a GlyphViz-specific
    implementation inspired by GaiaViz's description of a "conical spiral
    with inner radius, outer radius and height":
      translate_x -> continuous angle in degrees around the helix axis
                     (0–360 = first turn, 360–720 = second turn, etc.)
      translate_y -> additional height offset above the computed helix height
      translate_z -> radial offset from the nominal helix radius

    The helix rises at a pitch of one full parent_radius per complete turn
    (360°), giving a natural stacking density. Radius stays at parent_radius
    from the axis unless offset by translate_z.
    """
    s = scale
    theta = math.radians(tx)
    height = (tx / 360.0) * parent_radius * s
    r = parent_radius + tz * s
    return (
        r * math.cos(theta),
        r * math.sin(theta),
        height + ty * s,
    )


# ---------------------------------------------------------------------------
# 3x3 rotation matrices (row-major tuples-of-tuples — no numpy needed) used to
# cascade orientation through the parent->child chain, mirroring how
# compute_world_scales cascades per-axis scale and compute_world_positions
# cascades translation.
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


def local_rotation_matrix(rx: float, ry: float, rz: float):
    """3x3 rotation matrix matching ANTz's DrawPinChild/DrawPin convention:
      glRotatef(rotate_y,  0, 0, -1)  → Rz(-ry)   "heading"
      glRotatef(rotate_x, -1, 0,  0)  → Rx(-rx)   "roll"
      glRotatef(rotate_z,  0, 0, -1)  → Rz(-rz)   "tilt"
    OpenGL right-multiplies, so the combined matrix is Rz(-ry) @ Rx(-rx) @ Rz(-rz).
    rotate_y and rotate_z both drive Z-axis rotations (no Y-axis rotation in ANTz)."""
    return _mat_mul(_mat_mul(_rot_z(-ry), _rot_x(-rx)), _rot_z(-rz))


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

    Rod    — Rz(ty): rotates the child around the cylinder axis by the angular
             placement angle.  A child with Ry=90 (cylinder tilted horizontal)
             will point radially outward like a spoke at azimuth ty.
    Sphere/Point (KML) — Rz(tx)*Ry(90-ty): aligns the child's +Z with the
             sphere-surface normal at (longitude=tx, latitude=ty).
    Cube   — precomputed rotation per face (subspace), aligning +Z with face normal.
    Pin / Cylinder and all others — identity (no placement-based rotation).
    Torus  — deferred; its two-axis rotation will be addressed separately.
    """
    if parent_topo == TOPO_ROD:
        return _rot_z(ty)
    if parent_topo in (TOPO_SPHERE, TOPO_POINT):
        return _mat_mul(_rot_z(tx), _rot_y(90.0 - ty))
    if parent_topo == TOPO_CUBE:
        return _CUBE_FACE_BASE_ROTS[max(0, min(5, child_subspace))]
    return _MAT_IDENTITY


def compute_world_rotations(
    nodes: list[Node],
) -> tuple[dict[int, tuple], dict[int, tuple], dict[int, tuple]]:
    """
    Resolve every node's cumulative orientation and return three dicts:

    combined[id]      = R_parent_world @ R_topo_base @ R_child_local
                        (full world rotation — used by compute_world_positions
                        and the world_rot() accessor)
    parent_world[id]  = parent's combined world rotation (identity for roots)
    child_local[id]   = R_topo_base @ R_child_local
                        (the child's own contribution, without parent)

    The split is needed by node_world_matrix to build the ANTz-correct
    rendering matrix: R_parent @ S_parent @ R_child_local @ S_child, where
    the parent's non-uniform scale is sandwiched between the two rotation
    halves so it distorts the child's shape relative to its orientation.
    """
    by_id = {n.id: n for n in nodes}
    combined:      dict[int, tuple] = {}
    parent_world:  dict[int, tuple] = {}
    child_local:   dict[int, tuple] = {}

    def resolve(node: Node, visiting: frozenset[int]) -> tuple:
        cached = combined.get(node.id)
        if cached is not None:
            return cached

        local = local_rotation_matrix(node.rotate_x, node.rotate_y, node.rotate_z)
        parent = by_id.get(node.parent_id)
        if parent is None or parent is node or node.id in visiting:
            combined[node.id]     = local
            parent_world[node.id] = _MAT_IDENTITY
            child_local[node.id]  = local
        else:
            prot = resolve(parent, visiting | {node.id})
            topo_rot = _topology_base_rotation(
                parent.topo, node.translate_x, node.translate_y, node.translate_z,
                node.subspace,
            )
            lc = _mat_mul(topo_rot, local)
            combined[node.id]     = _mat_mul(prot, lc)
            parent_world[node.id] = prot
            child_local[node.id]  = lc

        return combined[node.id]

    for n in nodes:
        resolve(n, frozenset())

    return combined, parent_world, child_local


def _avg3(scale: tuple[float, float, float]) -> float:
    return (scale[0] + scale[1] + scale[2]) / 3.0


# All _*_offset wrappers share the signature:
#   (tx, ty, tz, parent_radius, parent_ratio, parent_scale, child_subspace=0)
# child_subspace is only used by _cube_offset; the others ignore it.

def _cartesian_offset(tx, ty, tz, _parent_radius, _parent_ratio, parent_scale, _child_subspace=0):
    """Plain Cartesian (dx, dy, dz) offset from the parent's center, expressed
    in the parent's local space and carried along — per axis — by its
    cumulative world scale: standard scene-graph composition
    (world_offset = parent_scale * local_offset), matching how
    compute_world_scales cascades sizing, and respecting independently
    scaled X/Y/Z. This is the Plane/Grid topology's coordinate system
    (translate_x/y position a child within the parent's local plane,
    translate_z is elevation above it) and the fallback for topologies not
    yet modeled.
    """
    sx, sy, sz = parent_scale
    return (tx * sx, ty * sy, tz * sz)


def _sphere_offset(tx, ty, tz, parent_radius, _parent_ratio, parent_scale, _child_subspace=0):
    # parent_radius = avg(sx,sy,sz) * base_scale, so recover per-axis radii:
    #   per_axis_radius = per_axis_scale * base_scale
    #                   = per_axis_scale * parent_radius / avg(parent_scale)
    # This ensures a child at longitude=90 moves only when scale_y changes,
    # not when scale_x or scale_z changes (ANTz ellipsoidal placement).
    avg_s = _avg3(parent_scale)
    if avg_s < 1e-9:
        return (0.0, 0.0, 0.0)
    f = parent_radius / avg_s          # = base_scale
    rx = parent_scale[0] * f
    ry = parent_scale[1] * f
    rz = parent_scale[2] * f
    return kml_ellipsoid_offset(tx, ty, tz, rx, ry, rz, avg_s)


def _torus_offset(tx, ty, tz, parent_radius, parent_ratio, parent_scale, _child_subspace=0):
    return torus_offset(tx, ty, tz, parent_radius, parent_ratio, _avg3(parent_scale))


def _rod_offset(tx, ty, tz, parent_radius, _parent_ratio, parent_scale, _child_subspace=0):
    # parent_radius = avg(sx,sy,sz) * base_scale.  The rod's axial length scales
    # with sz only, so recover rz = parent_radius * (sz / avg_s) to avoid
    # cross-axis coupling: changing the parent's X or Y scale must not move
    # children along the cylinder axis (Z), and changing Z must fill the cylinder.
    avg_s = _avg3(parent_scale)
    sz = parent_scale[2]
    z_radius = parent_radius * sz / avg_s if avg_s > 1e-9 else parent_radius
    return rod_offset(tx, ty, tz, z_radius, _avg3(parent_scale))


def _point_offset(tx, ty, tz, _parent_radius, _parent_ratio, parent_scale, _child_subspace=0):
    """Point topology: longitude/latitude/altitude from the parent center with
    per-axis scale — a child at lon=0, alt=5 on a parent scaled 2x along X
    lands at world X=10, not X=6.67 (which avg-scale would give).
    Equivalent to kml_ellipsoid_offset with rx=ry=rz=0 and per-axis alt_scale."""
    lon = math.radians(tx)
    lat = math.radians(ty)
    cos_lat = math.cos(lat)
    nx = cos_lat * math.cos(lon)
    ny = cos_lat * math.sin(lon)
    nz = math.sin(lat)
    sx, sy, sz = parent_scale
    return (tz * nx * sx, tz * ny * sy, tz * nz * sz)


def _pin_offset(tx, ty, tz, parent_radius, _parent_ratio, parent_scale, _child_subspace=0):
    return pin_offset(tx, ty, tz, parent_radius, _avg3(parent_scale))


def _cube_offset(tx, ty, tz, parent_radius, _parent_ratio, parent_scale, child_subspace=0):
    return cube_offset(tx, ty, tz, parent_radius, _avg3(parent_scale), child_subspace)


def _spiral_offset(tx, ty, tz, parent_radius, _parent_ratio, parent_scale, _child_subspace=0):
    return spiral_offset(tx, ty, tz, parent_radius, _avg3(parent_scale))


def _plot_offset(tx, ty, tz, _parent_radius, _parent_ratio, parent_scale, _child_subspace=0):
    """Plot topology (1D/2D/3D line plot, GPS, Oscilloscope): children placed
    at their Cartesian translate_x/y/z coordinates, scaled by the parent's
    world scale — same spatial layout as Plane, distinct semantic meaning."""
    sx, sy, sz = parent_scale
    return (tx * sx, ty * sy, tz * sz)


def _surface_offset(tx, ty, tz, _parent_radius, _parent_ratio, parent_scale, _child_subspace=0):
    """Surface topology (deformable grid, FFT, LIDAR, sound sphere): children
    placed at their Cartesian translate_x/y/z coordinates, scaled by the parent's
    world scale — translate_x/y form the grid position, translate_z is the
    height value at that grid point."""
    sx, sy, sz = parent_scale
    return (tx * sx, ty * sy, tz * sz)


_TOPO_OFFSET_FUNCS = {
    TOPO_CUBE:    _cube_offset,
    TOPO_SPHERE:  _sphere_offset,
    TOPO_TORUS:   _torus_offset,
    TOPO_PIN:     _pin_offset,
    TOPO_ROD:     _rod_offset,
    TOPO_POINT:   _point_offset,
    TOPO_PLANE:   _cartesian_offset,
    TOPO_SPIRAL:  _spiral_offset,
    TOPO_PLOT:    _plot_offset,
    TOPO_SURFACE: _surface_offset,
}


def compute_world_positions(
    nodes: list[Node],
    radius_of,
    world_scale: dict[int, tuple[float, float, float]],
    world_rotation: dict[int, tuple] | None = None,
) -> dict[int, tuple[float, float, float]]:
    """
    Resolve every node's world-space position by walking its parent chain.

    Root nodes (parent_id missing/unresolvable) use translate_x/y/z directly
    as Cartesian world coordinates. Each child's world position is its
    parent's world position plus an offset derived from the parent's
    topology — so moving a parent carries its whole subtree with it.

    `radius_of(node)` returns a node's rendered surface radius, needed by
    surface-based topologies (e.g. sphere) to place children on its surface.
    `world_scale` is the cumulative scale map from compute_world_scales,
    needed by Cartesian-style topologies (e.g. Plane, None) to carry a
    child's local offset along proportionally when the parent is resized —
    the standard scene-graph composition (world_offset = parent_scale *
    local_offset) that keeps position and size scaling consistent.

    `world_rotation` is the cumulative orientation map from
    compute_world_rotations: the topology offset is computed in the parent's
    *local* space, so it's rotated by the parent's cumulative world
    orientation before being added to the parent's world position — the same
    standard scene-graph composition (world_offset = parent_rotation *
    local_offset) that keeps a rotated parent's whole subtree riding along
    with it, the way ANTz/GaiaViz behaves.
    """
    by_id = {n.id: n for n in nodes}
    resolved: dict[int, tuple[float, float, float]] = {}
    world_rotation = world_rotation or {}

    def resolve(node: Node, visiting: frozenset[int]) -> tuple[float, float, float]:
        cached = resolved.get(node.id)
        if cached is not None:
            return cached

        parent = by_id.get(node.parent_id)
        if parent is None or parent is node or node.id in visiting:
            pos = (node.translate_x, node.translate_y, node.translate_z)
        else:
            px, py, pz = resolve(parent, visiting | {node.id})
            offset_fn = _TOPO_OFFSET_FUNCS.get(parent.topo, _cartesian_offset)
            local_offset = offset_fn(
                node.translate_x, node.translate_y, node.translate_z,
                radius_of(parent), parent.ratio,
                world_scale.get(parent.id, (1.0, 1.0, 1.0)),
                node.subspace,
            )
            prot = world_rotation.get(parent.id, _MAT_IDENTITY)
            ox, oy, oz = _mat_vec_mul(prot, local_offset)
            pos = (px + ox, py + oy, pz + oz)

        resolved[node.id] = pos
        return pos

    for n in nodes:
        resolve(n, frozenset())

    return resolved


def compute_world_scales(
    nodes: list[Node],
) -> tuple[dict[int, tuple[float, float, float]], dict[int, tuple[float, float, float]]]:
    """
    Resolve every node's cumulative per-axis scale and return two dicts:

    world[id]        = (parent_world_sx * own_sx, …)  — full cumulative scale
                       (used by _placement_radius, world_scale() accessor, and
                       as the `world_scale` argument to compute_world_positions)
    parent_world[id] = parent's cumulative scale ((1,1,1) for roots)

    The split is needed by node_world_matrix: `sp = parent_world[id]` is
    inserted between R_parent and R_child_local so a non-uniform parent scale
    distorts the child's rendered shape relative to the child's orientation,
    matching ANTz behavior (see compute_world_rotations docstring).
    """
    by_id = {n.id: n for n in nodes}
    world:        dict[int, tuple[float, float, float]] = {}
    parent_world: dict[int, tuple[float, float, float]] = {}

    def resolve(node: Node, visiting: frozenset[int]) -> tuple[float, float, float]:
        cached = world.get(node.id)
        if cached is not None:
            return cached

        parent = by_id.get(node.parent_id)
        os = (node.scale_x, node.scale_y, node.scale_z)
        if parent is None or parent is node or node.id in visiting:
            world[node.id]        = os
            parent_world[node.id] = (1.0, 1.0, 1.0)
        else:
            ps = resolve(parent, visiting | {node.id})
            world[node.id]        = (os[0] * ps[0], os[1] * ps[1], os[2] * ps[2])
            parent_world[node.id] = ps

        return world[node.id]

    for n in nodes:
        resolve(n, frozenset())

    return world, parent_world
