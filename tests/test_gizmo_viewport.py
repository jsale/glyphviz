"""
Transform gizmo interaction tests, through the real Viewport.

The math lives in tests/test_gizmo.py; what's pinned here is the wiring: that
a press on a handle grabs it instead of orbiting or re-picking, that dragging
one changes exactly the field it stands for (and, on a multi-selection, that
same field on every selected node), that a miss falls through to the drag
behavior the toolbar always had, and that the handles stay out of the way in
the modes that own the mouse.

A Viewport needs Qt, so these run offscreen and skip where Qt can't start —
but deliberately NOT a GL context: the camera matrices the hit test projects
with are seeded here with the same gluPerspective/gluLookAt pair paintGL
would have captured (_seed_camera, checked against a real capture in
test_seeded_camera_matches_a_real_paint). Requiring a live framebuffer would
make the whole file skip on any box without one, which is exactly where a
regression would go unnoticed.
"""
import math
import os

import numpy as np
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtCore import QPoint, Qt                   # noqa: E402
from PySide6.QtWidgets import QApplication              # noqa: E402

from glyphviz_core import gizmo as gz                   # noqa: E402
from glyphviz_core.node import Node, NODE_TYPE_LINK     # noqa: E402
from glyphviz_gl.viewport import Viewport               # noqa: E402


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication([])
        except Exception as exc:                        # pragma: no cover
            pytest.skip(f'Qt unavailable: {exc}')
    return app


def _seed_camera(vp):
    """Fill in the modelview/projection pair paintGL normally reads back out
    of GL, from the same orbit rig and the same 45-degree perspective — see
    Viewport.paintGL's non-stereo branch. Row-major, as _capture_camera_
    matrices returns them."""
    w, h = float(vp.width()), float(vp.height())
    az, el = math.radians(vp._cam_azimuth), math.radians(vp._cam_elevation)
    tgt = np.array(vp._cam_target, dtype=np.float64)
    eye = tgt + vp._cam_distance * np.array([
        math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])

    f = tgt - eye
    f /= np.linalg.norm(f)
    s = np.cross(f, np.array(vp._camera_up(), dtype=np.float64))
    s /= np.linalg.norm(s)
    u = np.cross(s, f)
    mv = np.eye(4)
    mv[0, :3], mv[1, :3], mv[2, :3] = s, u, -f
    mv[:3, 3] = -mv[:3, :3] @ eye

    near, far = 0.1, 100000.0
    cot = 1.0 / math.tan(math.radians(45.0) / 2.0)
    pr = np.zeros((4, 4))
    pr[0, 0] = cot / (w / h)
    pr[1, 1] = cot
    pr[2, 2] = (far + near) / (near - far)
    pr[2, 3] = 2.0 * far * near / (near - far)
    pr[3, 2] = -1.0

    vp._mv_matrix, vp._proj_matrix = mv, pr


def _node(node_id, x=0.0, y=0.0, z=0.0, **kw):
    n = Node(
        id=node_id, type=5, parent_id=0, branch_level=0,
        translate_x=x, translate_y=y, translate_z=z,
        rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=255, color_g=255, color_b=255, color_a=255,
        geometry=3, hide=0, topo=0,
    )
    for k, v in kw.items():
        setattr(n, k, v)
    return n


@pytest.fixture
def vp(qapp):
    v = Viewport()
    v.resize(800, 600)
    v.set_nodes([_node(1), _node(2, 120.0, 0.0, 0.0)])
    v._cam_azimuth, v._cam_elevation, v._cam_distance = 35.0, 20.0, 400.0
    v._cam_target = [0.0, 0.0, 0.0]
    v.selected_node_ids = {1}
    v.gizmo_mode = 'move'
    _seed_camera(v)
    return v


class _Mouse:
    """Stand-in for QMouseEvent — the handlers only read pos()/button()/
    buttons()/modifiers()."""

    def __init__(self, x, y, button=Qt.MouseButton.LeftButton, buttons=None,
                 modifiers=Qt.KeyboardModifier.NoModifier):
        self._pos = QPoint(int(x), int(y))
        self._button = button
        self._buttons = buttons if buttons is not None else button
        self._mods = modifiers

    def pos(self):
        return self._pos

    def button(self):
        return self._button

    def buttons(self):
        return self._buttons

    def modifiers(self):
        return self._mods


def _handle_screen(vp, axis):
    """Widget-pixel polyline of one handle, as the viewport sees it."""
    frame = vp._gizmo_frame()
    assert frame is not None
    return vp._gizmo_screen_handles(frame)[axis]


def _grab_point(vp, axis, t=0.75):
    """A point that unambiguously belongs to one handle.

    Shafts: partway along, clear of the origin the other two share. Rings:
    the sample point furthest from the other two rings, since three rings
    genuinely cross each other and a grab at a crossing is ambiguous for the
    test the same way it is for the user."""
    frame = vp._gizmo_frame()
    assert frame is not None
    screen = vp._gizmo_screen_handles(frame)
    pts = screen[axis]
    if len(pts) == 2:
        return tuple(pts[0] + (pts[1] - pts[0]) * t)
    others = [v for k, v in screen.items() if k != axis]
    clearance = [min(gz.polyline_distance(o, p) for o in others) for p in pts]
    return tuple(pts[int(np.argmax(clearance))])


# --- attachment --------------------------------------------------------------

def test_handles_attach_to_the_first_selected_visual_node(vp):
    vp.selected_node_ids = {1, 2}
    assert vp.gizmo_node().id == 1


def test_no_handles_without_a_selection(vp):
    vp.selected_node_ids = set()
    assert vp._gizmo_frame() is None


def test_no_handles_without_an_armed_mode(vp):
    vp.gizmo_mode = None
    assert vp._gizmo_frame() is None


def test_no_handles_on_a_link(vp):
    """A Link's own transform is inert (the edge follows its endpoints), so
    handles on one would promise an edit that does nothing."""
    link = _node(3, type=NODE_TYPE_LINK)
    vp.set_nodes([_node(1), link])
    vp.selected_node_ids = {3}
    assert vp.gizmo_node() is None
    assert vp._gizmo_frame() is None


def test_camera_mode_and_stereo_suppress_the_handles(vp):
    """Both modes own the mouse in ways the handles can't share: Camera Mode
    takes every drag button, stereo draws the scene twice."""
    vp.set_fly_mode(True)
    assert vp._gizmo_frame() is None
    vp.set_fly_mode(False)
    vp.selected_node_ids = {1}
    assert vp._gizmo_frame() is not None
    vp.stereo_mode = True
    assert vp._gizmo_frame() is None


def test_view_toggle_hides_the_handles_without_disarming_the_mode(vp):
    vp.show_gizmo_handles = False
    assert vp._gizmo_frame() is None
    assert vp.gizmo_mode == 'move'      # the armed mode is untouched


def test_handles_hold_a_constant_screen_size(vp):
    """Chrome, not geometry: twice as far away means twice as long in world
    units, so the same number of pixels on screen."""
    near = vp._gizmo_frame()['length']
    vp._cam_distance *= 3.0
    _seed_camera(vp)
    far = vp._gizmo_frame()['length']
    assert far == pytest.approx(near * 3.0, rel=0.02)


# --- picking -----------------------------------------------------------------

def test_a_press_on_a_handle_grabs_it(vp):
    x, y = _grab_point(vp, 'x')
    assert vp._gizmo_pick(x, y) == 'x'
    vp.mousePressEvent(_Mouse(x, y))
    assert vp._gizmo_drag is not None
    assert vp._gizmo_drag['axis'] == 'x'


def test_a_press_away_from_every_handle_falls_through(vp):
    """A miss is still the free-form drag the toolbar always had — the gizmo
    is additive, it doesn't take the old gesture away."""
    vp.mousePressEvent(_Mouse(5, 5))
    assert vp._gizmo_drag is None
    assert vp._drag_button == Qt.MouseButton.LeftButton
    before = vp._scene.node_by_id(1).translate_x
    vp.mouseMoveEvent(_Mouse(45, 5, buttons=Qt.MouseButton.LeftButton))
    assert vp._scene.node_by_id(1).translate_x != before


def test_shift_over_a_handle_still_grabs_rather_than_rubber_bands(vp):
    x, y = _grab_point(vp, 'y')
    vp.mousePressEvent(_Mouse(x, y, modifiers=Qt.KeyboardModifier.ShiftModifier))
    assert vp._gizmo_drag is not None
    assert not vp._rubber_mode


def test_releasing_a_handle_press_does_not_clear_the_selection(vp):
    """The release must not fall through to the click-picker, which reads a
    handle as empty space and would drop the selection the handles need."""
    seen = []
    vp.nodesSelected.connect(seen.append)
    x, y = _grab_point(vp, 'x')
    vp.mousePressEvent(_Mouse(x, y))
    vp.mouseReleaseEvent(_Mouse(x, y))
    assert seen == []
    assert vp._gizmo_drag is None
    assert vp.selected_node_ids == {1}


def test_hover_highlights_and_clears(vp):
    x, y = _grab_point(vp, 'z')
    vp.mouseMoveEvent(_Mouse(x, y, buttons=Qt.MouseButton.NoButton))
    assert vp._gizmo_hover == 'z'
    vp.mouseMoveEvent(_Mouse(3, 3, buttons=Qt.MouseButton.NoButton))
    assert vp._gizmo_hover is None


# --- dragging ----------------------------------------------------------------

def _drag_handle(vp, axis, dx, dy):
    """Grab a handle and drag the cursor by (dx, dy) widget pixels."""
    x, y = _grab_point(vp, axis)
    vp.mousePressEvent(_Mouse(x, y))
    assert vp._gizmo_drag is not None
    vp.mouseMoveEvent(_Mouse(x + dx, y + dy, buttons=Qt.MouseButton.LeftButton))
    vp.mouseReleaseEvent(_Mouse(x + dx, y + dy))


def test_move_drag_changes_only_its_own_translate_field(vp):
    node = vp._scene.node_by_id(1)
    shaft = _handle_screen(vp, 'x')
    along = shaft[-1] - shaft[0]
    along = along / np.hypot(*along)
    _drag_handle(vp, 'x', along[0] * 60.0, along[1] * 60.0)
    assert node.translate_x > 0.1
    assert node.translate_y == 0.0
    assert node.translate_z == 0.0


def test_move_drag_tracks_the_cursor(vp):
    """Drag the red arrow 60px along its own screen direction and the node's
    world position must move that far along the arrow, not some fraction of
    it — the point of a handle over a free-form drag."""
    node = vp._scene.node_by_id(1)
    frame = vp._gizmo_frame()
    shaft = _handle_screen(vp, 'x')
    world_per_px = gz.axis_world_per_pixel(shaft, frame['length'])
    along = shaft[-1] - shaft[0]
    along = along / np.hypot(*along)
    _drag_handle(vp, 'x', along[0] * 60.0, along[1] * 60.0)
    moved = np.linalg.norm(np.array(vp._scene.world_pos(1)))
    assert moved == pytest.approx(60.0 * world_per_px, rel=0.02)


def test_move_drag_across_the_arrow_does_nothing(vp):
    """Motion perpendicular to the arrow is rejected — a handle constrains
    the drag rather than just seeding it. (Not exactly zero: the cursor lands
    on whole pixels, so a perpendicular drag carries under a pixel of
    along-axis motion with it.)"""
    shaft = _handle_screen(vp, 'x')
    along = shaft[-1] - shaft[0]
    along = along / np.hypot(*along)
    across = np.array([-along[1], along[0]])
    per_px = gz.axis_world_per_pixel(shaft, vp._gizmo_frame()['length'])

    _drag_handle(vp, 'x', across[0] * 60.0, across[1] * 60.0)
    sideways = abs(vp._scene.node_by_id(1).translate_x)
    assert sideways < per_px            # under one pixel's worth

    vp._scene.node_by_id(1).translate_x = 0.0
    vp._scene.invalidate()
    _seed_camera(vp)
    _drag_handle(vp, 'x', along[0] * 60.0, along[1] * 60.0)
    assert abs(vp._scene.node_by_id(1).translate_x) > 20.0 * sideways


def test_rotate_drag_changes_only_its_own_rotate_field(vp):
    vp.gizmo_mode = 'rotate'
    _seed_camera(vp)
    node = vp._scene.node_by_id(1)
    _drag_handle(vp, 'z', 25.0, 25.0)
    assert node.rotate_z != 0.0
    assert node.rotate_x == 0.0
    assert node.rotate_y == 0.0


def test_size_drag_changes_only_its_own_scale_field(vp):
    vp.gizmo_mode = 'size'
    _seed_camera(vp)
    node = vp._scene.node_by_id(1)
    shaft = _handle_screen(vp, 'y')
    along = shaft[-1] - shaft[0]
    along = along / np.hypot(*along)
    _drag_handle(vp, 'y', along[0] * 50.0, along[1] * 50.0)
    assert node.scale_y > 1.0
    assert node.scale_x == 1.0
    assert node.scale_z == 1.0


def test_a_handle_drag_carries_the_whole_selection(vp):
    vp.selected_node_ids = {1, 2}
    _seed_camera(vp)
    shaft = _handle_screen(vp, 'x')
    along = shaft[-1] - shaft[0]
    along = along / np.hypot(*along)
    _drag_handle(vp, 'x', along[0] * 60.0, along[1] * 60.0)
    a = vp._scene.node_by_id(1).translate_x
    b = vp._scene.node_by_id(2).translate_x
    assert a > 0.1
    assert b - 120.0 == pytest.approx(a)     # same field change on both


def test_a_handle_drag_emits_nodesManipulated(vp):
    seen = []
    vp.nodesManipulated.connect(seen.append)
    shaft = _handle_screen(vp, 'x')
    along = shaft[-1] - shaft[0]
    along = along / np.hypot(*along)
    _drag_handle(vp, 'x', along[0] * 60.0, along[1] * 60.0)
    assert seen and seen[-1] == {1}


def test_a_handle_drag_never_moves_the_camera(vp):
    before = (vp._cam_azimuth, vp._cam_elevation, vp._cam_distance,
              list(vp._cam_target))
    _drag_handle(vp, 'x', 40.0, 40.0)
    assert (vp._cam_azimuth, vp._cam_elevation, vp._cam_distance,
            list(vp._cam_target)) == before


# --- the seeding shortcut itself ---------------------------------------------

def test_seeded_camera_matches_a_real_paint(vp):
    """Guard on _seed_camera: the matrices these tests project with have to be
    the ones paintGL would have captured, or every hit test above is measuring
    a camera the app never had. Skipped where no framebuffer is available —
    the rest of the file deliberately does not depend on one."""
    seeded_mv, seeded_pr = vp._mv_matrix, vp._proj_matrix
    vp._mv_matrix = vp._proj_matrix = None
    try:
        vp.grabFramebuffer()
    except Exception as exc:                            # pragma: no cover
        pytest.skip(f'no usable GL context: {exc}')
    if vp._mv_matrix is None:                           # pragma: no cover
        pytest.skip('paintGL did not run on this platform')
    assert np.allclose(vp._mv_matrix, seeded_mv, atol=1e-9)
    assert np.allclose(vp._proj_matrix, seeded_pr, rtol=1e-6, atol=1e-9)


# --- the cases a fixed-frame gizmo would get wrong ----------------------------

def test_move_drag_tracks_the_cursor_on_a_sphere_parent(vp):
    """The hard case: the child's translate_x is a LONGITUDE, so the red
    arrow is a tangent to the parent's surface and one 'unit' of the field is
    worth many world units. Dragging it must still move the node the distance
    the cursor asked for."""
    parent = _node(1, topo=2, scale_x=6.0, scale_y=6.0, scale_z=6.0)
    child = _node(2, 25.0, 40.0, 3.0, parent_id=1)
    vp.set_nodes([parent, child])
    vp.selected_node_ids = {2}
    vp._cam_target = list(vp._scene.world_pos(2))
    _seed_camera(vp)

    before = np.array(vp._scene.world_pos(2))
    frame = vp._gizmo_frame()
    shaft = _handle_screen(vp, 'x')
    world_per_px = gz.axis_world_per_pixel(shaft, frame['length'])
    along = shaft[-1] - shaft[0]
    along = along / np.hypot(*along)

    _drag_handle(vp, 'x', along[0] * 40.0, along[1] * 40.0)
    assert child.translate_y == 40.0 and child.translate_z == 3.0
    moved = np.linalg.norm(np.array(vp._scene.world_pos(2)) - before)
    # A tangent drag curves away from the straight arrow, so allow a little
    # slack — the point is that it tracks at all rather than by some fixed
    # per-pixel guess.
    assert moved == pytest.approx(40.0 * world_per_px, rel=0.08)


def test_rotate_ring_turns_the_way_the_cursor_does(vp):
    """Counter-clockwise on a ring facing the viewer is a positive rotation.
    Getting this backwards is the classic gizmo bug, and the sign depends on
    both Qt's y-down screen and which side of the ring you're looking at."""
    vp.gizmo_mode = 'rotate'
    node = vp._scene.node_by_id(1)
    frame = vp._gizmo_frame()
    centre, _ = gz.project(vp._proj_matrix @ vp._mv_matrix,
                           frame['origin'][None, :],
                           float(vp.width()), float(vp.height()))
    cx, cy = centre[0]
    # Blue ring, camera above the scene: +Z points at the viewer.
    start = (cx + 90.0, cy)
    vp.mousePressEvent(_Mouse(*start))
    assert vp._gizmo_drag['axis'] == 'z'
    assert vp._gizmo_drag['toward_viewer']
    vp.mouseMoveEvent(_Mouse(cx + 90.0, cy - 20.0,      # up the screen = CCW
                             buttons=Qt.MouseButton.LeftButton))
    vp.mouseReleaseEvent(_Mouse(cx + 90.0, cy - 20.0))
    assert node.rotate_z > 0.0
    assert node.rotate_x == 0.0 and node.rotate_y == 0.0


# --- uniform scale lock -------------------------------------------------------

def test_size_lock_scales_every_axis_from_one_handle(vp):
    """The Properties panel's 'Lock X/Y/Z together' also governs Size drags:
    grab the green bar and all three axes take the same factor."""
    vp.gizmo_mode = 'size'
    vp.uniform_scale = True
    node = vp._scene.node_by_id(1)
    node.scale_x, node.scale_y, node.scale_z = 2.0, 1.0, 0.5
    shaft = _handle_screen(vp, 'y')
    along = shaft[-1] - shaft[0]
    along = along / np.hypot(*along)
    _drag_handle(vp, 'y', along[0] * 50.0, along[1] * 50.0)
    assert node.scale_x > 2.0 and node.scale_y > 1.0 and node.scale_z > 0.5
    # Shared FACTOR, not forced equality — the 4:2:1 shape is preserved.
    assert node.scale_x / node.scale_y == pytest.approx(2.0)
    assert node.scale_y / node.scale_z == pytest.approx(2.0)


def test_size_lock_also_governs_the_free_form_drag(vp):
    """Not just the handles: the axis-checkbox Size drag honours it too, so
    the checkbox means one thing wherever you scale from."""
    vp.gizmo_mode = 'size'
    vp.uniform_scale = True
    node = vp._scene.node_by_id(1)
    vp.mousePressEvent(_Mouse(5, 5))
    assert vp._gizmo_drag is None            # a miss: the free-form path
    vp.mouseMoveEvent(_Mouse(55, 5, buttons=Qt.MouseButton.LeftButton))
    assert node.scale_x > 1.0
    assert node.scale_y == pytest.approx(node.scale_x)
    assert node.scale_z == pytest.approx(node.scale_x)


def test_size_lock_off_leaves_the_other_axes_alone(vp):
    vp.gizmo_mode = 'size'
    vp.uniform_scale = False
    node = vp._scene.node_by_id(1)
    shaft = _handle_screen(vp, 'y')
    along = shaft[-1] - shaft[0]
    along = along / np.hypot(*along)
    _drag_handle(vp, 'y', along[0] * 50.0, along[1] * 50.0)
    assert node.scale_y > 1.0
    assert node.scale_x == 1.0 and node.scale_z == 1.0


def test_size_lock_does_not_leak_into_move_or_rotate(vp):
    """It is a scale lock, not a general axis lock — Move and Rotate handles
    must still touch exactly one field with it on."""
    vp.uniform_scale = True
    node = vp._scene.node_by_id(1)
    shaft = _handle_screen(vp, 'x')
    along = shaft[-1] - shaft[0]
    along = along / np.hypot(*along)
    _drag_handle(vp, 'x', along[0] * 60.0, along[1] * 60.0)
    assert node.translate_x != 0.0
    assert node.translate_y == 0.0 and node.translate_z == 0.0
