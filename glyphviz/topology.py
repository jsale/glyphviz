"""
Parent-child spatial topology — converts a child's translate_x/y/z into a
world-space offset from its parent, according to the parent's np_topo_id.

See gaiaviz-skill/references/structure/Topology-Guide.md for the full
per-topology coordinate conventions. New topologies are added by writing an
offset function and registering it in _TOPO_OFFSET_FUNCS.
"""
import math

from .geometry import CYLINDER_RADIUS_RATIO, torus_radii
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
TOPO_COUNT     = 16

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
}


def kml_offset(longitude: float, latitude: float, altitude: float, radius: float, scale: float = 1.0):
    """
    Convert KML-style longitude/latitude/altitude into a Cartesian offset from
    the parent sphere's center. Z is treated as the polar axis (matching both
    the viewport's Z-up world and ANTz's own convention, where translate_z is
    the sphere's altitude/vertical axis): latitude=+90 sits at the north pole
    (+Z), and longitude=0 faces +X.

    `altitude` is a local-space measurement (like the parent's own translate/
    scale fields) carried into world space by `scale` — the parent's
    cumulative world scale — so that scaling a parent moves a child's surface
    perch proportionally, the same way its rendered radius grows. At
    scale=1.0 (the common, unscaled case) this is exactly `radius + altitude`,
    preserving the original surface-placement behavior.
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
    parent's center, mirroring the sphere/torus angle+angle+elevation
    convention:
      translate_x -> position along the rod's length, local-space
                     (its local Z-axis — matches _draw_cylinder's default
                     horizontal orientation, like Pin's height but sideways)
      translate_y -> angle around the rod's circumference
      translate_z -> elevation, offset outward from the rod's curved surface

    Matches _draw_cylinder's local-space orientation: the cylinder's axis
    runs along local Z, with its circular cross-section in the local XY plane.

    `axial_pos`/`elevation` are local-space, carried into world space by
    `scale` (the parent's cumulative world scale) — see kml_offset for why.
    """
    angle = math.radians(angle_deg)
    radial = CYLINDER_RADIUS_RATIO * radius + elevation * scale
    return (
        radial * math.cos(angle),
        radial * math.sin(angle),
        axial_pos * scale,
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
    """3x3 rotation matrix for a node's own rotate_x/y/z, composed in the same
    Rz * Ry * Rx order as _draw_node's glRotatef(z) -> glRotatef(y) ->
    glRotatef(x) calls (so undoing it in picking and cascading it to children
    both agree with what's actually rendered)."""
    return _mat_mul(_mat_mul(_rot_z(rz), _rot_y(ry)), _rot_x(rx))


def compute_world_rotations(nodes: list[Node]) -> dict[int, tuple]:
    """
    Resolve every node's cumulative (world) orientation as a 3x3 rotation
    matrix: a child's world orientation is its parent's world orientation
    composed with its own local rotate_x/y/z, and so on up the chain — so
    rotating a parent carries its whole subtree's orientation (and, via
    compute_world_positions, placement) with it, matching ANTz/GaiaViz
    scene-graph behavior. Mirrors compute_world_scales' cascading shape.
    """
    by_id = {n.id: n for n in nodes}
    resolved: dict[int, tuple] = {}

    def resolve(node: Node, visiting: frozenset[int]) -> tuple:
        cached = resolved.get(node.id)
        if cached is not None:
            return cached

        local = local_rotation_matrix(node.rotate_x, node.rotate_y, node.rotate_z)
        parent = by_id.get(node.parent_id)
        if parent is None or parent is node or node.id in visiting:
            rot = local
        else:
            prot = resolve(parent, visiting | {node.id})
            rot = _mat_mul(prot, local)

        resolved[node.id] = rot
        return rot

    for n in nodes:
        resolve(n, frozenset())

    return resolved


def _avg3(scale: tuple[float, float, float]) -> float:
    return (scale[0] + scale[1] + scale[2]) / 3.0


def _cartesian_offset(tx, ty, tz, _parent_radius, _parent_ratio, parent_scale):
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


def _sphere_offset(tx, ty, tz, parent_radius, _parent_ratio, parent_scale):
    return kml_offset(tx, ty, tz, parent_radius, _avg3(parent_scale))


def _torus_offset(tx, ty, tz, parent_radius, parent_ratio, parent_scale):
    return torus_offset(tx, ty, tz, parent_radius, parent_ratio, _avg3(parent_scale))


def _rod_offset(tx, ty, tz, parent_radius, _parent_ratio, parent_scale):
    return rod_offset(tx, ty, tz, parent_radius, _avg3(parent_scale))


def _point_offset(tx, ty, tz, _parent_radius, _parent_ratio, parent_scale):
    """Point topology: the same longitude/latitude/altitude system as Sphere,
    but altitude is measured from the parent's CENTER rather than its surface
    — so children collapse toward the center as altitude approaches zero."""
    return kml_offset(tx, ty, tz, 0.0, _avg3(parent_scale))


_TOPO_OFFSET_FUNCS = {
    TOPO_SPHERE: _sphere_offset,
    TOPO_TORUS: _torus_offset,
    TOPO_ROD: _rod_offset,
    TOPO_POINT: _point_offset,
    TOPO_PLANE: _cartesian_offset,
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
            )
            prot = world_rotation.get(parent.id, _MAT_IDENTITY)
            ox, oy, oz = _mat_vec_mul(prot, local_offset)
            pos = (px + ox, py + oy, pz + oz)

        resolved[node.id] = pos
        return pos

    for n in nodes:
        resolve(n, frozenset())

    return resolved


def compute_world_scales(nodes: list[Node]) -> dict[int, tuple[float, float, float]]:
    """
    Resolve every node's cumulative (world) per-axis scale factor (sx, sy, sz).

    This is plain scene-graph inheritance, independent of topology: a child's
    rendered size on each axis is its own scale_x/y/z multiplied by its
    parent's resolved scale on that same axis, and so on up the chain — so
    scaling a parent up or down carries its whole subtree with it
    proportionally, and X/Y/Z scaling stays independent across generations
    (matches ANTz/GaiaViz behavior).
    """
    by_id = {n.id: n for n in nodes}
    resolved: dict[int, tuple[float, float, float]] = {}

    def own_scale(node: Node) -> tuple[float, float, float]:
        return (node.scale_x, node.scale_y, node.scale_z)

    def resolve(node: Node, visiting: frozenset[int]) -> tuple[float, float, float]:
        cached = resolved.get(node.id)
        if cached is not None:
            return cached

        parent = by_id.get(node.parent_id)
        os = own_scale(node)
        if parent is None or parent is node or node.id in visiting:
            scale = os
        else:
            ps = resolve(parent, visiting | {node.id})
            scale = (os[0] * ps[0], os[1] * ps[1], os[2] * ps[2])

        resolved[node.id] = scale
        return scale

    for n in nodes:
        resolve(n, frozenset())

    return resolved
