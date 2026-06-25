"""
Parent-child spatial topology — converts a child's translate_x/y/z into a
world-space offset from its parent, according to the parent's topo id
(np_topo_id in the GaiaViz reference docs).

See gaiaviz-skill/references/structure/Topology-Guide.md for the full
per-topology coordinate conventions. New topologies are added by writing an
offset function and registering it in _TOPO_OFFSET_FUNCS.
"""
import math

from .geometry_data import ROD_HEIGHT_FACTOR, torus_radii
from .node import Node, NON_VISUAL_TYPES, ROTATION_MODE_EULER_XYZ, ROTATION_MODE_HEADING_TILT_ROLL

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

# Plane and the Z-topology family position/space children via translate_x/y/z
# AND that spacing scales with the parent's own scale (Topology-Guide.md:
# "do NOT affect children size... DO affect children's translate_x/y/z
# position" -- e.g. scaling the World Grid up deliberately re-spaces every
# attached child, confirmed wanted for real use, like laying glyphs out
# across a map-textured floor). What this family does NOT do is stretch
# children's rendered SIZE the way Sphere/Cube/Torus/Rod's one-level-deep
# shape inheritance does (the ANTz-validated "diamond child" behavior) --
# a non-uniformly-scaled Grid must not also distort attached glyphs' own
# shape. See compute_world_bases' `parent_basis` exemption (shape only;
# compute_world_positions intentionally has no matching exemption -- it
# always uses `world_basis`, which carries the parent's own scale, for this
# family same as any other topology).
NO_SIZE_INHERIT_TOPOS = frozenset({
    TOPO_PLANE, TOPO_ZCUBE, TOPO_ZSPHERE, TOPO_ZTORUS, TOPO_ZCYLINDER, TOPO_ZROD,
})
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


def compute_world_bases(
    nodes: list[Node],
    grid: Node | None = None,
) -> tuple[dict[int, tuple], dict[int, tuple], dict[int, tuple]]:
    """
    Resolve every node's cumulative rotation+scale and return three dicts:

    world_basis[id]   = parent_basis[id] @ child_local[id] @ diag(own raw scale)
                        (the full recursive rotation+scale composition, the
                        same thing a real glPushMatrix/glPopMatrix chain
                        would produce — fusing each level's rotation AND
                        scale into one matrix before moving to the next
                        level)
    parent_basis[id]  = parent's world_basis (identity for roots with no
                        `grid`; the grid's own world_basis for roots when a
                        World Grid node is passed in — see `grid` below) —
                        EXCEPT when the parent's topo is in
                        NO_SIZE_INHERIT_TOPOS (Plane/Z-topology family), where
                        it's the parent's own parent_basis @ child_local
                        instead: everything above the parent, minus the
                        parent's own scale — so that family's scale can still
                        space children out via translate_x/y/z (see
                        compute_world_positions, which uses `world_basis`
                        rather than this dict) without also distorting their
                        rendered SHAPE, which is all `parent_basis` feeds
                        (node_world_matrix).
    child_local[id]   = topo_base_rotation(parent.topo, placement) @ own
                        rotation (this node's own orientation contribution,
                        no scale)

    `grid`, if given (see Scene.grid_node()), is the World Grid node that
    every ordinary root glyph (no real parent, not itself World/Camera/the
    grid) implicitly attaches to — composed exactly like any other child of
    a TOPO_PLANE parent. Pass None (the default) to get today's behavior:
    every parentless node is its own independent root at the origin.

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
    """
    by_id = {n.id: n for n in nodes}
    world_basis:  dict[int, tuple] = {}
    parent_basis: dict[int, tuple] = {}
    child_local:  dict[int, tuple] = {}

    def resolve(node: Node, visiting: frozenset[int]) -> tuple:
        cached = world_basis.get(node.id)
        if cached is not None:
            return cached

        own_rot = local_rotation_matrix(node.rotate_x, node.rotate_y, node.rotate_z,
                                         node.rotation_mode)
        own_scale = (node.scale_x, node.scale_y, node.scale_z)
        parent = by_id.get(node.parent_id)
        if (parent is None and grid is not None and node is not grid
                and node.type not in NON_VISUAL_TYPES):
            # Root glyph with no explicit parent: implicitly attach to the
            # World Grid, same as any other child of a TOPO_PLANE node.
            parent = grid
        if parent is None or parent is node or node.id in visiting:
            parent_basis[node.id] = _MAT_IDENTITY
            child_local[node.id]  = own_rot
            world_basis[node.id]  = _mat_scale_cols(own_rot, own_scale)
        else:
            pwb = resolve(parent, visiting | {node.id})
            topo_rot = _topology_base_rotation(
                parent.topo, node.translate_x, node.translate_y, node.translate_z,
                node.subspace,
            )
            lc = _mat_mul(topo_rot, own_rot)
            if parent.topo in NO_SIZE_INHERIT_TOPOS:
                # Shape sandwich only (see NO_SIZE_INHERIT_TOPOS): use the
                # parent's rotation-only basis -- its own parent_basis/
                # child_local, i.e. everything above it, minus its own scale
                # -- so this parent's scale spaces children out (world_basis,
                # used for position below) without resizing them.
                parent_basis[node.id] = _mat_mul(parent_basis[parent.id], child_local[parent.id])
            else:
                parent_basis[node.id] = pwb
            child_local[node.id]  = lc
            world_basis[node.id]  = _mat_mul(pwb, _mat_scale_cols(lc, own_scale))

        return world_basis[node.id]

    for n in nodes:
        resolve(n, frozenset())

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
}


def compute_world_positions(
    nodes: list[Node],
    base_scale: float,
    world_basis: dict[int, tuple] | None = None,
    grid: Node | None = None,
) -> dict[int, tuple[float, float, float]]:
    """
    Resolve every node's world-space position by walking its parent chain.

    Root nodes (parent_id missing/unresolvable) use translate_x/y/z directly
    as Cartesian world coordinates, UNLESS a World Grid node is passed in via
    `grid` (see Scene.grid_node()) — then ordinary root glyphs (not
    World/Camera, not the grid itself) implicitly attach to it instead,
    exactly like any other child of a TOPO_PLANE parent. Pass the same `grid`
    value used to build `world_basis` via compute_world_bases — the two
    consumers must agree on the implicit-parent redirect or glyph position
    and glyph shape/orientation will disagree (see compute_world_bases).
    Each child's world position is its parent's world position plus an
    offset derived from the parent's topology — so moving a parent carries
    its whole subtree with it. This applies uniformly to every topology,
    including Plane/Z-topology parents (NO_SIZE_INHERIT_TOPOS, e.g. the World
    Grid): scaling the grid deliberately re-spaces every attached child
    (Jeff confirmed this is wanted — only the *shape* exemption in
    compute_world_bases' `parent_basis` is special-cased, not position).

    The topology offset (e.g. a longitude/latitude point on the parent's
    surface) is computed in the parent's own *unscaled* local frame, with
    `base_scale` standing in for the parent's rendered base size — see the
    `_*_offset` functions above — then transformed into world space by the
    parent's `world_basis` (from compute_world_bases), the parent's full
    recursive rotation+scale composition: this is what threads every
    ancestor's per-axis stretch and rotation through correctly, however many
    non-uniformly-scaled, rotated levels sit above it.
    """
    by_id = {n.id: n for n in nodes}
    resolved: dict[int, tuple[float, float, float]] = {}
    world_basis = world_basis or {}

    def resolve(node: Node, visiting: frozenset[int]) -> tuple[float, float, float]:
        cached = resolved.get(node.id)
        if cached is not None:
            return cached

        parent = by_id.get(node.parent_id)
        if (parent is None and grid is not None and node is not grid
                and node.type not in NON_VISUAL_TYPES):
            parent = grid
        if parent is None or parent is node or node.id in visiting:
            pos = (node.translate_x, node.translate_y, node.translate_z)
        else:
            px, py, pz = resolve(parent, visiting | {node.id})
            offset_fn = _TOPO_OFFSET_FUNCS.get(parent.topo, _cartesian_offset)
            local_offset = offset_fn(
                node.translate_x, node.translate_y, node.translate_z,
                base_scale, parent.ratio, node.subspace,
            )
            wb_parent = world_basis.get(parent.id, _MAT_IDENTITY)
            ox, oy, oz = _mat_vec_mul(wb_parent, local_offset)
            pos = (px + ox, py + oy, pz + oz)

        resolved[node.id] = pos
        return pos

    for n in nodes:
        resolve(n, frozenset())

    return resolved
