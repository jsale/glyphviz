"""
Transform gizmo — the on-screen red/green/blue handles for Move / Rotate /
Size, and everything about them that doesn't need a GL context.

What lives here
---------------
* **Frames.** Which world direction each editable field actually acts along.
  The three modes each need a different answer and none of them is simply
  "the node's local axes":

    - Move   — translate_x/y/z are placement coordinates in the PARENT's
               topology, so the arrows follow `translate_gradient()`: the
               numerical derivative of `topology.placement_offset` carried
               into world space by the parent's basis. Exact for Cartesian
               parents (where it reduces to the parent's basis columns) and
               equally exact for the angular topologies, whose lon/lat/
               orbital-angle fields don't line up with any fixed axis.
    - Rotate — rotate_x/y/z are not one-axis-each in general: under ANTz's
               Heading/Tilt/Roll convention rotate_y and rotate_z BOTH drive
               Z rotations and every field's sign is inverted, so a ring
               drawn about the node's local Y would spin it about something
               else entirely. `rotation_axes()` differentiates the actual
               rotation matrix instead, which gets both conventions right by
               construction.
    - Size   — scale_x/y/z do stretch the node's own local axes, so the bars
               are the world_basis columns.

* **Geometry.** `handle_points()` returns the polyline each handle is drawn
  as — and the SAME points are what hit-testing measures against, so the
  grabbable region can never drift from the drawn one.

* **Hit testing and drag math**, in screen space: `pick()` finds the handle
  under the cursor; `axis_drag_pixels` + `axis_world_per_pixel` turn cursor
  motion along a shaft into world distance, and `sweep_degrees` turns motion
  around a ring into degrees. Screen space (rather than a 3D ray/plane
  intersection) is what makes a handle grabbable everywhere it looks
  grabbable, including the near-edge-on case where a drag plane degenerates.

All Qt-free and GL-free: the caller supplies camera matrices and a viewport
size, and gets numbers back. See tests/test_gizmo.py.
"""

import numpy as np

from .node import Node
from .topology import local_rotation_matrix, placement_offset

MODE_MOVE = 'move'
MODE_ROTATE = 'rotate'
MODE_SIZE = 'size'
MODES = (MODE_MOVE, MODE_ROTATE, MODE_SIZE)

AXES = ('x', 'y', 'z')
AXIS_INDEX = {'x': 0, 'y': 1, 'z': 2}

# Matching the world-axis decoration (_draw_axes) and GlyphViz Web's handles:
# X red, Y green, Z blue.
AXIS_COLORS = {
    'x': (1.0, 0.25, 0.25),
    'y': (0.25, 1.0, 0.35),
    'z': (0.35, 0.55, 1.0),
}

HANDLE_PX = 95.0     # on-screen length (arrows/bars) or radius (rings)
PICK_PX = 11.0       # cursor-to-handle screen distance that counts as a grab
SHAFT_START = 0.18   # handles start this far out, leaving the glyph centre clear
ARROW_HEAD = 0.26    # arrowhead length, as a fraction of the handle length
RING_SEGMENTS = 72

_EPS = 1e-9


# --- frames -----------------------------------------------------------------

def unit_columns(basis: np.ndarray) -> np.ndarray:
    """Normalize a 3x3's columns to unit length, substituting the matching
    world axis for any column that has collapsed (a zeroed scale field, a
    degenerate parent). Returns columns, i.e. result[:, i] is axis i."""
    out = np.asarray(basis, dtype=np.float64).copy()
    for i in range(3):
        n = float(np.linalg.norm(out[:, i]))
        if n < _EPS:
            out[:, i] = 0.0
            out[i, i] = 1.0
        else:
            out[:, i] /= n
    return out


def translate_gradient(parent: Node | None, child: Node, base_scale: float,
                        parent_world_basis: np.ndarray | None) -> np.ndarray:
    """3x3 whose column A is d(world position) / d(translate_A) for `child`.

    Central-differenced through topology.placement_offset, so it is correct
    for every parent topology — including World Grid parents (flat and globe)
    and the angular topologies, where a translate field is degrees and the
    mapping to world space is nonlinear. For a Cartesian parent the columns
    come back as exactly the parent's world_basis columns, which is the
    identity this reduces to.

    Both the arrow directions and the drag scale come from this: the column's
    direction is where the arrow points, its LENGTH is how many world units
    one unit of that field buys.
    """
    step = 1e-3
    tx, ty, tz = child.translate_x, child.translate_y, child.translate_z
    grad = np.zeros((3, 3))
    for i, (dx, dy, dz) in enumerate(((step, 0.0, 0.0), (0.0, step, 0.0),
                                      (0.0, 0.0, step))):
        plus = placement_offset(parent, tx + dx, ty + dy, tz + dz,
                                base_scale, child.subspace)
        minus = placement_offset(parent, tx - dx, ty - dy, tz - dz,
                                 base_scale, child.subspace)
        grad[:, i] = (np.asarray(plus) - np.asarray(minus)) / (2.0 * step)
    if parent_world_basis is not None:
        grad = np.asarray(parent_world_basis, dtype=np.float64) @ grad
    return grad


def rotation_axes(node: Node, parent_basis: np.ndarray,
                   child_local: np.ndarray) -> np.ndarray:
    """3x3 whose column A is the world axis that rotate_A spins `node` about.

    Differentiating R(fields) instead of assuming rotate_A ↔ local axis A is
    what makes this hold under both rotation conventions: dR/dA · Rᵀ is the
    skew-symmetric generator of the motion the field produces, and its axial
    vector is the instantaneous rotation axis. Under Euler XYZ that recovers
    X, Rx·Y, Rx·Ry·Z; under ANTz's Heading/Tilt/Roll it recovers the Z-X-Z
    sequence's axes complete with the convention's sign inversions — so
    dragging a ring one degree changes its field by exactly one degree, in
    the direction the ring turned.

    The generator's magnitude is π/180 for every field (one radian of motion
    per 180/π degrees), which is why the columns can be normalized without
    losing the degrees-in/degrees-out correspondence.

    `parent_basis` and `child_local` are the node's SceneTransforms rows;
    the node's own rotation is divided back out of child_local to recover
    the topology scaffold the fields act inside.
    """
    own = np.asarray(local_rotation_matrix(node.rotate_x, node.rotate_y,
                                           node.rotate_z, node.rotation_mode),
                     dtype=np.float64)
    # child_local = topo_rot @ own_rot, and own_rot is a pure rotation.
    frame = (np.asarray(parent_basis, dtype=np.float64)
             @ np.asarray(child_local, dtype=np.float64) @ own.T)

    step = 1e-4
    axes = np.zeros((3, 3))
    fields = (node.rotate_x, node.rotate_y, node.rotate_z)
    for i in range(3):
        bumped = list(fields)
        bumped[i] += step
        plus = np.asarray(local_rotation_matrix(*bumped, node.rotation_mode),
                          dtype=np.float64)
        bumped[i] = fields[i] - step
        minus = np.asarray(local_rotation_matrix(*bumped, node.rotation_mode),
                           dtype=np.float64)
        skew = (plus - minus) / (2.0 * step) @ own.T
        axes[:, i] = (skew[2, 1] - skew[1, 2],
                      skew[0, 2] - skew[2, 0],
                      skew[1, 0] - skew[0, 1])
    return unit_columns(frame @ axes)


# --- handle geometry --------------------------------------------------------

def perpendicular_basis(axis) -> tuple[np.ndarray, np.ndarray]:
    """Two orthonormal vectors spanning the plane perpendicular to `axis`.

    Which pair is arbitrary — they only parameterize a full circle, so where
    it starts doesn't show. What matters is that they come from the axis
    ITSELF rather than from the gizmo's other two axes: a rotation gizmo's
    three axes are not orthogonal in general (see rotation_axes), so spanning
    ring A with axes B and C tilts it off the plane it is supposed to sweep,
    and collapses it to a sliver whenever B and C happen to line up. Seeding
    off whichever world axis the ring axis leans on least keeps the cross
    product well away from zero.
    """
    a = np.asarray(axis, dtype=np.float64)
    n = np.linalg.norm(a)
    a = a / n if n > _EPS else np.array([0.0, 0.0, 1.0])
    seed = np.zeros(3)
    seed[int(np.argmin(np.abs(a)))] = 1.0
    u = np.cross(a, seed)
    u /= np.linalg.norm(u)
    return u, np.cross(a, u)


def handle_points(mode: str, origin, axes: np.ndarray, length: float
                   ) -> dict[str, np.ndarray]:
    """World-space polyline for each axis handle: {'x': (N,3), 'y': ..., 'z': ...}.

    Drawing and hit-testing both read this, so a handle is grabbable exactly
    where it is visible. Move/Size are a two-point shaft (the arrowhead/box
    at the far end is decoration drawn around the last point); Rotate is a
    closed ring, sampled finely enough that the polyline is within a pixel
    of the curve at normal handle sizes.

    A rotate ring is always a true circle in the plane perpendicular to its
    own axis — the path a point on the glyph would actually travel. So when
    two rings coincide, that is Euler gimbal lock being reported honestly
    (near rotate_y = +/-90 degrees, rotate_x and rotate_z really do spin the
    node about the same axis), not the handles losing their shape.
    """
    o = np.asarray(origin, dtype=np.float64)
    unit = unit_columns(axes)
    out: dict[str, np.ndarray] = {}
    if mode == MODE_ROTATE:
        theta = np.linspace(0.0, 2.0 * np.pi, RING_SEGMENTS + 1)
        for name, i in AXIS_INDEX.items():
            u, v = perpendicular_basis(unit[:, i])
            out[name] = (o
                         + length * np.cos(theta)[:, None] * u
                         + length * np.sin(theta)[:, None] * v)
    else:
        for name, i in AXIS_INDEX.items():
            d = unit[:, i]
            out[name] = np.array([o + d * length * SHAFT_START, o + d * length])
    return out


# --- projection and hit testing ---------------------------------------------

def project(mvp: np.ndarray, points: np.ndarray, width: float, height: float):
    """World → widget-pixel projection (Qt convention: origin top-left, y down).

    Returns (screen (N,2) float64, in_front (N,) bool). Points at or behind
    the eye plane get NaN screen coordinates and a False flag — callers must
    drop them rather than trust the (mirrored) numbers a negative w produces.
    """
    pts = np.atleast_2d(np.asarray(points, dtype=np.float64))
    homo = np.ones((len(pts), 4))
    homo[:, :3] = pts
    clip = homo @ np.asarray(mvp, dtype=np.float64).T
    w = clip[:, 3]
    in_front = w > _EPS
    with np.errstate(divide='ignore', invalid='ignore'):
        ndc = clip[:, :2] / w[:, None]
    screen = np.empty((len(pts), 2))
    screen[:, 0] = (ndc[:, 0] + 1.0) / 2.0 * width
    screen[:, 1] = (1.0 - (ndc[:, 1] + 1.0) / 2.0) * height
    screen[~in_front] = np.nan
    return screen, in_front


def polyline_distance(screen: np.ndarray, cursor) -> float:
    """Shortest distance in pixels from `cursor` to a projected polyline.

    Segments with an endpoint behind the camera (NaN) are skipped; a polyline
    with nothing left is infinitely far away, which is what keeps a handle
    pointing straight back past the eye from staying grabbable.
    """
    pts = np.asarray(screen, dtype=np.float64)
    if len(pts) < 2:
        return float('inf')
    a, b = pts[:-1], pts[1:]
    ok = np.isfinite(a).all(axis=1) & np.isfinite(b).all(axis=1)
    if not ok.any():
        return float('inf')
    a, b = a[ok], b[ok]
    c = np.asarray(cursor, dtype=np.float64)
    ab = b - a
    denom = (ab * ab).sum(axis=1)
    with np.errstate(divide='ignore', invalid='ignore'):
        t = np.clip(((c - a) * ab).sum(axis=1) / denom, 0.0, 1.0)
    t = np.where(denom > _EPS, t, 0.0)
    closest = a + t[:, None] * ab
    return float(np.hypot(*(closest - c).T).min())


def pick(screen_handles: dict[str, np.ndarray], cursor,
         threshold: float = PICK_PX) -> str | None:
    """Axis letter of the handle under the cursor, nearest first, or None.

    Ties are broken x → y → z only when the distances are genuinely equal;
    otherwise the closest handle wins, which is what makes the ring crossings
    in Rotate mode behave.
    """
    best, best_d = None, threshold
    for name in AXES:
        pts = screen_handles.get(name)
        if pts is None:
            continue
        d = polyline_distance(pts, cursor)
        if d < best_d:
            best, best_d = name, d
    return best


# --- drag math --------------------------------------------------------------

def axis_screen_vector(screen_handle: np.ndarray) -> np.ndarray | None:
    """The drawn shaft as a screen-space vector (Qt pixels), or None when it
    is degenerate — a Move/Size handle pointing straight at (or away from)
    the camera, which has no unambiguous drag direction on screen."""
    pts = np.asarray(screen_handle, dtype=np.float64)
    if len(pts) < 2 or not np.isfinite(pts[[0, -1]]).all():
        return None
    v = pts[-1] - pts[0]
    return None if np.hypot(*v) < 1.0 else v


def axis_drag_pixels(screen_handle: np.ndarray, dx: float, dy: float
                      ) -> float:
    """Signed pixels of cursor motion ALONG a Move/Size handle.

    A plain projection of the motion onto the shaft direction: drag with the
    arrow and it grows, drag against it and it shrinks, drag across it and
    nothing happens. The y-down screen convention cancels out of the dot
    product (both vectors are in it), so no flip is needed here — unlike the
    rotation sweep below, where the sign of a cross product does depend on it.
    """
    v = axis_screen_vector(screen_handle)
    if v is None:
        return 0.0
    n = np.hypot(*v)
    return float((dx * v[0] + dy * v[1]) / n)


def axis_world_per_pixel(screen_handle: np.ndarray, world_length: float
                          ) -> float:
    """World units per pixel measured along a Move handle: the shaft is
    `world_length` units long and however many pixels the projection makes
    it, so the ratio converts cursor travel into world travel at exactly the
    handle's depth. Returns 0.0 for a degenerate (near-edge-on) shaft, which
    the caller reads as "this axis can't be dragged from here"."""
    v = axis_screen_vector(screen_handle)
    if v is None:
        return 0.0
    span = world_length * (1.0 - SHAFT_START)   # the shaft, not the full axis
    return float(span / np.hypot(*v))


def sweep_degrees(center, previous, current, toward_viewer: bool) -> float:
    """Signed degrees swept around a ring, from one cursor position to the next.

    Measured as the change in screen-space bearing about the ring's projected
    centre, so the handle turns with the cursor wherever on the ring it was
    grabbed. Qt's y-down screen flips the handedness of the cross product, so
    y is negated first; `toward_viewer` then accounts for a ring seen from
    its back, where a right-handed rotation reads clockwise.

    Returns 0.0 when either cursor position sits on the centre, where the
    bearing is undefined.
    """
    c = np.asarray(center, dtype=np.float64)
    p0 = np.asarray(previous, dtype=np.float64) - c
    p1 = np.asarray(current, dtype=np.float64) - c
    if np.hypot(*p0) < 1.0 or np.hypot(*p1) < 1.0:
        return 0.0
    a0 = np.arctan2(-p0[1], p0[0])
    a1 = np.arctan2(-p1[1], p1[0])
    delta = (a1 - a0 + np.pi) % (2.0 * np.pi) - np.pi   # shortest way round
    return float(np.degrees(delta) * (1.0 if toward_viewer else -1.0))


def handle_world_length(eye, origin, pixels: float, fov_deg: float,
                        viewport_height: float) -> float:
    """World length that subtends `pixels` on screen at the gizmo's depth, so
    the handles stay the same size however far away the node is. Uses the
    eye→origin distance rather than the depth along the view direction: the
    small error off-axis is invisible, and it can never go to zero or
    negative for a node beside or behind the camera."""
    if viewport_height <= 0:
        return 1.0
    dist = float(np.linalg.norm(np.asarray(origin, dtype=np.float64)
                                - np.asarray(eye, dtype=np.float64)))
    world_per_px = (2.0 * max(dist, _EPS)
                    * np.tan(np.radians(fov_deg) / 2.0) / viewport_height)
    return max(pixels * world_per_px, _EPS)
