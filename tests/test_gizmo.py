"""
Transform gizmo unit tests (glyphviz_core/gizmo.py).

The gizmo's whole claim is that dragging a handle changes exactly the field
that handle is labelled with, by exactly the amount the cursor asked for.
That rests on three pieces of math, each pinned here against the engine
rather than against itself:

* `translate_gradient` — the world direction (and world-units-per-field-unit)
  each translate field pushes a node. Checked by actually moving the field
  and re-running the real transform engine.
* `rotation_axes` — the world axis each rotate field spins a node about,
  which under ANTz's Heading/Tilt/Roll convention is NOT the axis the field
  is named for. Checked against the composed rotation matrix.
* screen-space projection, hit testing, and the sweep/along-axis drag
  conversions.
"""
import math

import numpy as np
import pytest

from glyphviz_core import gizmo as gz
from glyphviz_core.node import (
    NODE_TYPE_GRID, ROTATION_MODE_EULER_XYZ, ROTATION_MODE_HEADING_TILT_ROLL,
    Node,
)
from glyphviz_core.scene import Scene
from glyphviz_core import topology as topo


BASE_SCALE = 1.0


def _node(node_id: int, **kw) -> Node:
    n = Node(
        id=node_id, type=5, parent_id=0, branch_level=0,
        translate_x=0.0, translate_y=0.0, translate_z=0.0,
        rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=255, color_g=255, color_b=255, color_a=255,
        geometry=7, hide=False, topo=0,
    )
    n.ratio = 0.1
    for k, v in kw.items():
        setattr(n, k, v)
    return n


def _frames(scene: Scene, node: Node):
    """(parent, parent_world_basis) as the viewport resolves them."""
    parent = scene.node_by_id(node.parent_id)
    if parent is None or parent is node:
        return None, None
    pb = scene.basis_matrices(parent.id)
    return parent, (pb[0] if pb is not None else None)


def _numeric_world_gradient(scene: Scene, node: Node, axis: int,
                            step: float = 1e-4) -> np.ndarray:
    """d(world position)/d(translate_axis), measured by running the real
    engine at translate ± step. This is the ground truth the gizmo's cheap
    per-node gradient has to reproduce."""
    attr = ('translate_x', 'translate_y', 'translate_z')[axis]
    original = getattr(node, attr)
    out = []
    for delta in (step, -step):
        setattr(node, attr, original + delta)
        scene.invalidate()
        out.append(np.array(scene.world_pos(node.id)))
    setattr(node, attr, original)
    scene.invalidate()
    return (out[0] - out[1]) / (2.0 * step)


# --- translate gradient ------------------------------------------------------

@pytest.mark.parametrize("parent_topo", [
    topo.TOPO_NONE, topo.TOPO_PLANE, topo.TOPO_SPHERE, topo.TOPO_TORUS,
    topo.TOPO_CYLINDER, topo.TOPO_PIN, topo.TOPO_ROD, topo.TOPO_SPIRAL,
    topo.TOPO_ZSPHERE, topo.TOPO_ZCYLINDER, topo.TOPO_CUBE, topo.TOPO_ZCUBE,
])
def test_translate_gradient_matches_engine(parent_topo):
    """Every parent topology: the gizmo's gradient is the direction AND the
    magnitude the engine actually moves the child in."""
    parent = _node(1, topo=parent_topo, rotate_z=25.0, scale_x=2.0, scale_y=1.5)
    child = _node(2, parent_id=1, translate_x=37.0, translate_y=18.0,
                  translate_z=4.0, subspace=2)
    scene = Scene([parent, child], base_scale=BASE_SCALE)
    _p, pwb = _frames(scene, child)

    grad = gz.translate_gradient(parent, child, BASE_SCALE, pwb)
    for axis in range(3):
        expected = _numeric_world_gradient(scene, child, axis)
        assert np.allclose(grad[:, axis], expected, atol=1e-6), (
            f"topo={parent_topo} axis={axis}")


def test_translate_gradient_root_is_world_axes():
    """A root node's translate IS its world position, so the arrows are the
    plain world axes at unit scale."""
    node = _node(1, translate_x=5.0, translate_y=-2.0, rotate_z=40.0)
    grad = gz.translate_gradient(None, node, BASE_SCALE, None)
    assert np.allclose(grad, np.eye(3))


def test_translate_gradient_flat_grid_child():
    """A flat World Grid re-spaces child positions by its own scale, so one
    degree of longitude is worth that many more world units."""
    grid = _node(1, type=NODE_TYPE_GRID, topo=topo.TOPO_PLANE, geometry=20,
                 scale_x=2.0, scale_y=1.0, scale_z=1.0)
    child = _node(2, parent_id=1, translate_x=-117.0, translate_y=32.7)
    scene = Scene([grid, child], base_scale=BASE_SCALE)
    _p, pwb = _frames(scene, child)

    grad = gz.translate_gradient(grid, child, BASE_SCALE, pwb)
    for axis in range(3):
        assert np.allclose(grad[:, axis],
                           _numeric_world_gradient(scene, child, axis),
                           atol=1e-6)
    # Longitude runs along world X, doubled by the grid's scale_x.
    assert grad[0, 0] == pytest.approx(2.0)


def test_translate_gradient_globe_grid_child():
    """On a globe grid the lon/lat arrows are tangents to the sphere, not
    world axes — the case a fixed-frame gizmo would get plainly wrong."""
    grid = _node(1, type=NODE_TYPE_GRID, topo=topo.TOPO_PLANE, geometry=3)
    assert grid.grid_is_globe()
    child = _node(2, parent_id=1, translate_x=90.0, translate_y=0.0)
    scene = Scene([grid, child], base_scale=BASE_SCALE)
    _p, pwb = _frames(scene, child)

    grad = gz.translate_gradient(grid, child, BASE_SCALE, pwb)
    for axis in range(3):
        assert np.allclose(grad[:, axis],
                           _numeric_world_gradient(scene, child, axis),
                           atol=1e-6)
    # At lon=90 the outward (elevation) direction is +Y.
    assert np.allclose(gz.unit_columns(grad)[:, 2], (0.0, 1.0, 0.0), atol=1e-9)


# --- rotation axes -----------------------------------------------------------

@pytest.mark.parametrize("mode", [ROTATION_MODE_EULER_XYZ,
                                  ROTATION_MODE_HEADING_TILT_ROLL])
@pytest.mark.parametrize("field", [0, 1, 2])
def test_rotation_axis_is_the_axis_the_field_turns_about(mode, field):
    """Bumping rotate_<field> by one degree must rotate the node by one
    degree about the axis the matching ring is drawn around — in both
    rotation conventions, including HTR's inverted-sign Z-X-Z sequence."""
    node = _node(1, rotate_x=20.0, rotate_y=-35.0, rotate_z=50.0,
                 rotation_mode=mode)
    scene = Scene([node], base_scale=BASE_SCALE)
    _wb, pb, cl = scene.basis_matrices(node.id)
    axis = gz.rotation_axes(node, pb, cl)[:, field]

    before = np.asarray(topo.local_rotation_matrix(
        node.rotate_x, node.rotate_y, node.rotate_z, mode))
    fields = [node.rotate_x, node.rotate_y, node.rotate_z]
    fields[field] += 1.0
    after = np.asarray(topo.local_rotation_matrix(*fields, mode))

    delta = after @ before.T          # the world-space motion the field caused
    angle = math.degrees(math.acos(np.clip((np.trace(delta) - 1) / 2, -1, 1)))
    assert angle == pytest.approx(1.0, abs=1e-6)
    # Right-hand rule: the axial vector of the motion points along the ring's
    # axis (same sign), so dragging the ring one degree the way it turns adds
    # one degree to the field.
    axial = np.array([delta[2, 1] - delta[1, 2],
                      delta[0, 2] - delta[2, 0],
                      delta[1, 0] - delta[0, 1]])
    assert np.allclose(axial / np.linalg.norm(axial), axis, atol=1e-6)


def test_rotation_axes_htr_y_is_not_local_y():
    """The reason rotation_axes exists: under Heading/Tilt/Roll, rotate_y is
    a Z rotation. A gizmo that drew the green ring about local Y would spin
    the node about something else."""
    node = _node(1, rotation_mode=ROTATION_MODE_HEADING_TILT_ROLL)
    scene = Scene([node], base_scale=BASE_SCALE)
    _wb, pb, cl = scene.basis_matrices(node.id)
    axes = gz.rotation_axes(node, pb, cl)
    assert np.allclose(axes[:, 1], (0.0, 0.0, -1.0), atol=1e-9)   # heading
    assert np.allclose(axes[:, 0], (-1.0, 0.0, 0.0), atol=1e-9)   # tilt


def test_rotation_axes_euler_are_local_axes_at_rest():
    node = _node(1, rotation_mode=ROTATION_MODE_EULER_XYZ)
    scene = Scene([node], base_scale=BASE_SCALE)
    _wb, pb, cl = scene.basis_matrices(node.id)
    assert np.allclose(gz.rotation_axes(node, pb, cl), np.eye(3), atol=1e-9)


def test_rotation_axes_inherit_parent_orientation():
    """A child of a rotated parent gets rings in the parent's frame, so the
    handles stay glued to the glyph as drawn."""
    parent = _node(1, rotate_z=90.0, rotation_mode=ROTATION_MODE_EULER_XYZ)
    child = _node(2, parent_id=1, rotation_mode=ROTATION_MODE_EULER_XYZ)
    scene = Scene([parent, child], base_scale=BASE_SCALE)
    _wb, pb, cl = scene.basis_matrices(child.id)
    axes = gz.rotation_axes(child, pb, cl)
    assert np.allclose(axes[:, 0], (0.0, 1.0, 0.0), atol=1e-9)   # local X -> world Y


# --- handle geometry ---------------------------------------------------------

def test_move_handles_are_shaft_segments():
    pts = gz.handle_points(gz.MODE_MOVE, (1.0, 2.0, 3.0), np.eye(3), 10.0)
    assert set(pts) == {'x', 'y', 'z'}
    assert np.allclose(pts['x'][0], (1.0 + 10.0 * gz.SHAFT_START, 2.0, 3.0))
    assert np.allclose(pts['x'][1], (11.0, 2.0, 3.0))


def test_rotate_handles_are_closed_rings_in_the_right_plane():
    pts = gz.handle_points(gz.MODE_ROTATE, (0.0, 0.0, 0.0), np.eye(3), 5.0)
    ring = pts['x']
    assert np.allclose(ring[0], ring[-1])                 # closed
    assert np.allclose(ring[:, 0], 0.0)                   # lies in the YZ plane
    assert np.allclose(np.linalg.norm(ring, axis=1), 5.0)


def test_handle_points_normalize_a_scaled_frame():
    """A node scaled 5x on X must not get a 5x-longer red arrow — the handles
    are screen-sized chrome, not part of the glyph."""
    axes = np.diag([5.0, 1.0, 1.0])
    pts = gz.handle_points(gz.MODE_MOVE, (0.0, 0.0, 0.0), axes, 4.0)
    assert np.linalg.norm(pts['x'][1]) == pytest.approx(4.0)


def test_unit_columns_survives_a_collapsed_axis():
    axes = np.diag([1.0, 0.0, 1.0])
    out = gz.unit_columns(axes)
    assert np.allclose(out[:, 1], (0.0, 1.0, 0.0))


# --- projection and hit testing ----------------------------------------------

def _ortho_mvp():
    """Trivial camera: world XY maps straight to NDC, everything in front."""
    m = np.eye(4)
    m[0, 0] = m[1, 1] = 0.01
    m[2, 2] = 0.0
    m[3, 3] = 1.0
    return m


def test_project_maps_origin_to_screen_centre_with_y_flip():
    screen, ok = gz.project(_ortho_mvp(), np.array([[0.0, 0.0, 0.0],
                                                    [0.0, 100.0, 0.0]]),
                            800.0, 600.0)
    assert ok.all()
    assert np.allclose(screen[0], (400.0, 300.0))
    assert screen[1][1] < screen[0][1]     # +Y world is UP the screen


def test_project_flags_points_behind_the_eye():
    mvp = np.eye(4)
    mvp[3, 3] = 0.0
    mvp[3, 2] = 1.0        # w = z
    screen, ok = gz.project(mvp, np.array([[0.0, 0.0, -5.0]]), 800.0, 600.0)
    assert not ok[0]
    assert np.isnan(screen[0]).all()


def test_pick_finds_the_nearest_handle_and_misses_cleanly():
    handles = {
        'x': np.array([[100.0, 300.0], [300.0, 300.0]]),
        'y': np.array([[100.0, 300.0], [100.0, 100.0]]),
        'z': np.array([[100.0, 300.0], [100.0, 500.0]]),
    }
    assert gz.pick(handles, (200.0, 303.0)) == 'x'
    assert gz.pick(handles, (97.0, 200.0)) == 'y'
    assert gz.pick(handles, (600.0, 600.0)) is None


def test_pick_ignores_handles_that_project_behind_the_camera():
    handles = {'x': np.array([[np.nan, np.nan], [np.nan, np.nan]]),
               'y': np.array([[0.0, 0.0], [0.0, 100.0]])}
    assert gz.pick(handles, (0.0, 50.0)) == 'y'


def test_polyline_distance_measures_to_the_segment_not_the_endpoints():
    poly = np.array([[0.0, 0.0], [100.0, 0.0]])
    assert gz.polyline_distance(poly, (50.0, 8.0)) == pytest.approx(8.0)
    assert gz.polyline_distance(poly, (130.0, 0.0)) == pytest.approx(30.0)


# --- drag conversions --------------------------------------------------------

def test_axis_drag_projects_motion_onto_the_shaft():
    shaft = np.array([[100.0, 300.0], [200.0, 300.0]])   # points right
    assert gz.axis_drag_pixels(shaft, 10.0, 0.0) == pytest.approx(10.0)
    assert gz.axis_drag_pixels(shaft, -10.0, 0.0) == pytest.approx(-10.0)
    assert gz.axis_drag_pixels(shaft, 0.0, 25.0) == pytest.approx(0.0)


def test_axis_drag_is_zero_for_an_edge_on_handle():
    shaft = np.array([[100.0, 300.0], [100.2, 300.0]])
    assert gz.axis_drag_pixels(shaft, 40.0, 0.0) == 0.0
    assert gz.axis_world_per_pixel(shaft, 10.0) == 0.0


def test_world_per_pixel_uses_the_drawn_shaft_span():
    """The shaft is the length minus its inner gap, so a 100px shaft standing
    for that span converts pixels back to world units at that ratio."""
    shaft = np.array([[0.0, 0.0], [100.0, 0.0]])
    span = 10.0 * (1.0 - gz.SHAFT_START)
    assert gz.axis_world_per_pixel(shaft, 10.0) == pytest.approx(span / 100.0)


def test_sweep_degrees_signs_with_the_ring_facing():
    centre = (400.0, 300.0)
    # Cursor moving from due-east to just north of east: counter-clockwise on
    # screen, which is positive for a ring whose axis points at the viewer.
    east = (500.0, 300.0)
    north_of_east = (500.0, 290.0)
    facing = gz.sweep_degrees(centre, east, north_of_east, toward_viewer=True)
    assert facing > 0
    away = gz.sweep_degrees(centre, east, north_of_east, toward_viewer=False)
    assert away == pytest.approx(-facing)


def test_sweep_degrees_takes_the_short_way_round():
    centre = (0.0, 0.0)
    delta = gz.sweep_degrees(centre, (-100.0, -1.0), (-100.0, 1.0),
                             toward_viewer=True)
    assert abs(delta) < 2.0       # not ~358 degrees the other way


def test_sweep_degrees_ignores_a_cursor_on_the_centre():
    assert gz.sweep_degrees((10.0, 10.0), (10.0, 10.0), (50.0, 50.0),
                            toward_viewer=True) == 0.0


def test_handle_world_length_scales_with_distance():
    near = gz.handle_world_length((0.0, 0.0, 0.0), (0.0, 0.0, 100.0),
                                  gz.HANDLE_PX, 45.0, 600.0)
    far = gz.handle_world_length((0.0, 0.0, 0.0), (0.0, 0.0, 400.0),
                                 gz.HANDLE_PX, 45.0, 600.0)
    assert far == pytest.approx(near * 4.0)
    assert near > 0.0


# --- rings sit in the plane they sweep ---------------------------------------

def test_perpendicular_basis_is_orthonormal_and_perpendicular():
    for axis in ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.3, -0.7, 0.2),
                 (1.0, 1.0, 1.0)):
        u, v = gz.perpendicular_basis(axis)
        a = np.asarray(axis) / np.linalg.norm(axis)
        assert np.dot(u, a) == pytest.approx(0.0, abs=1e-12)
        assert np.dot(v, a) == pytest.approx(0.0, abs=1e-12)
        assert np.dot(u, v) == pytest.approx(0.0, abs=1e-12)
        assert np.linalg.norm(u) == pytest.approx(1.0)
        assert np.linalg.norm(v) == pytest.approx(1.0)


def test_rings_are_perpendicular_to_their_own_axis_when_axes_are_skew():
    """The rotate gizmo's three axes are NOT orthogonal in general (Euler
    axes never are away from rest), so a ring spanned by the OTHER two axes
    tilts off the plane it is supposed to sweep. Each ring must come from its
    own axis."""
    skew = np.array([[1.0, 0.0, -0.94],       # X and Z nearly parallel:
                     [0.0, 0.73, 0.17],       # what near-gimbal-lock looks like
                     [0.0, 0.68, -0.18]]).T
    pts = gz.handle_points(gz.MODE_ROTATE, (0.0, 0.0, 0.0), skew, 10.0)
    unit = gz.unit_columns(skew)
    for name, i in gz.AXIS_INDEX.items():
        ring = pts[name] - np.array([0.0, 0.0, 0.0])
        assert np.allclose(ring @ unit[:, i], 0.0, atol=1e-9), name
        assert np.allclose(np.linalg.norm(ring, axis=1), 10.0)


def test_gimbal_lock_coincides_rings_rather_than_collapsing_one():
    """At rotate_y near 90 degrees, rotate_x and rotate_z really do spin the
    node about the same axis. The rings should report that by landing on top
    of each other — all three still full-size circles, none squashed to a
    line, which is what the old other-two-axes spanning produced."""
    node = _node(1, rotate_x=43.3, rotate_y=-104.5, rotate_z=15.3,
                 rotation_mode=ROTATION_MODE_EULER_XYZ)
    scene = Scene([node], base_scale=BASE_SCALE)
    _wb, pb, cl = scene.basis_matrices(node.id)
    axes = gz.rotation_axes(node, pb, cl)
    assert abs(np.dot(axes[:, 0], axes[:, 2])) > 0.9    # X and Z nearly aligned

    pts = gz.handle_points(gz.MODE_ROTATE, (0.0, 0.0, 0.0), axes, 10.0)
    for name in gz.AXES:
        ring = pts[name]
        assert np.allclose(np.linalg.norm(ring, axis=1), 10.0)
        # A genuine circle spans its full diameter in every direction of its
        # own plane — a collapsed one would be thin along one of them.
        spread = ring.max(axis=0) - ring.min(axis=0)
        assert np.linalg.norm(spread) > 20.0, name
