"""
Camera Mode (free flight, C key) unit tests.

The contract (see glyphviz_gl/viewport.py's "Camera Mode navigation" block):
the camera rig stays the same azimuth/elevation/distance/target orbit rig, and
flight only changes which end of the arm the mouse drives.

  * Orbit mode swings the EYE around a fixed target.
  * Flight swings the TARGET around a fixed eye (turning and looking around),
    and translates both together (flying and sliding) — the arm length never
    changes, so the target rides along in front of the camera instead of
    pinning it. That's the whole point: no object you're stuck circling.

Left-button flight is ANTz-style *rate* flight: the press point is a bearings
origin, and the cursor's held offset from it sets a continuous speed
(integrated per repaint tick in _apply_fly_drag), locked to the horizontal
plane the flight starts on.

These tests need a QOpenGLWidget, so they run offscreen; they're skipped
outright if Qt can't start (e.g. a headless box with no platform plugin).
"""
import math
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtCore import QPoint, Qt                   # noqa: E402
from PySide6.QtWidgets import QApplication              # noqa: E402

from glyphviz_core.node import Node                     # noqa: E402
from glyphviz_gl.viewport import (                      # noqa: E402
    _FLY_DEADZONE_PX, _FLY_RATE_PER_PX_S, _FLY_TURN_DEG_PER_PX_S,
    _LOOK_DEG_PER_PX, Viewport,
)


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication([])
        except Exception as exc:                        # pragma: no cover
            pytest.skip(f'Qt unavailable: {exc}')
    return app


def _node(node_id, x, y, z):
    return Node(
        id=node_id, type=5, parent_id=0, branch_level=0,
        translate_x=x, translate_y=y, translate_z=z,
        rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=255, color_g=0, color_b=0, color_a=255,
        geometry=3, hide=0, topo=1,
    )


@pytest.fixture
def vp(qapp):
    v = Viewport()
    v.set_nodes([_node(1, 0, 0, 0), _node(2, 100, 50, 20), _node(3, -80, 30, -40)])
    v._cam_azimuth, v._cam_elevation, v._cam_distance = 37.0, 22.0, 400.0
    v._cam_target = [10.0, -5.0, 3.0]
    return v


def _eye(vp):
    return vp._eye_position_with_offset(0.0)


def _unit(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v)


def _close(a, b, tol=1e-9):
    return max(abs(x - y) for x, y in zip(a, b)) < tol


def _heading(vp):
    """The horizontal-plane flight direction: the camera's forward vector
    with the elevation term dropped."""
    az = math.radians(vp._cam_azimuth)
    return (-math.cos(az), -math.sin(az), 0.0)


def _hold(vp, off_x, off_y):
    """Start a flight drag anchored at (100, 100) with the cursor held at the
    given offset from it — off_y < 0 means above the origin (fly forward)."""
    vp._fly_anchor = (100.0, 100.0)
    vp._fly_cursor = (100.0 + off_x, 100.0 + off_y)


class _Mouse:
    """Stand-in for QMouseEvent — the handlers only read pos(), button(),
    buttons(), and modifiers()."""

    def __init__(self, x, y, button, buttons,
                 modifiers=Qt.KeyboardModifier.NoModifier):
        self._pos = QPoint(x, y)
        self._button, self._buttons, self._mods = button, buttons, modifiers

    def pos(self):
        return self._pos

    def button(self):
        return self._button

    def buttons(self):
        return self._buttons

    def modifiers(self):
        return self._mods


# --- camera basis ----------------------------------------------------------

def test_basis_matches_the_glulookat_eye_and_target(vp):
    forward, _right, _up = vp._camera_basis()
    eye, target = _eye(vp), tuple(vp._cam_target)
    assert _close(forward, _unit(tuple(target[i] - eye[i] for i in range(3))))


def test_basis_is_orthonormal_and_right_handed(vp):
    forward, right, up = vp._camera_basis()
    for v in (forward, right, up):
        assert math.isclose(math.sqrt(sum(c * c for c in v)), 1.0, abs_tol=1e-12)
    for a, b in ((forward, right), (forward, up), (right, up)):
        assert abs(sum(x * y for x, y in zip(a, b))) < 1e-12
    assert abs(right[2]) < 1e-12, 'right must stay horizontal'
    cross = (right[1] * forward[2] - right[2] * forward[1],
             right[2] * forward[0] - right[0] * forward[2],
             right[0] * forward[1] - right[1] * forward[0])
    assert _close(cross, up)


def test_camera_up_is_always_plain_world_z(vp):
    """Flight never rolls the camera (banking was removed with the move to
    ANTz-style rate flight), so gluLookAt's up is always world-Z."""
    assert vp._camera_up() == (0.0, 0.0, 1.0)


# --- rate flight -----------------------------------------------------------

def test_holding_above_the_origin_flies_forward_along_the_heading(vp):
    """Flight is locked to the horizontal plane it starts on: translation
    follows the camera's heading (forward with the pitch dropped), so the
    eye's altitude never changes even though the camera is pitched."""
    vp.set_fly_mode(True)
    heading = _heading(vp)
    forward0 = vp._camera_basis()[0]
    eye0, target0, arm = _eye(vp), list(vp._cam_target), vp._cam_distance

    _hold(vp, 0, -(100 + _FLY_DEADZONE_PX))      # cursor 100px (net) above
    vp._apply_fly_drag(1000.0)

    moved = tuple(_eye(vp)[i] - eye0[i] for i in range(3))
    assert _close(_unit(moved), heading)
    assert abs(moved[2]) < 1e-12, 'altitude is locked'
    assert _close(tuple(vp._cam_target[i] - target0[i] for i in range(3)), moved)
    assert math.isclose(math.dist(_eye(vp), vp._cam_target), arm, abs_tol=1e-9)
    assert _close(vp._camera_basis()[0], forward0, tol=1e-12), 'aim must not change'


def test_holding_below_the_origin_flies_backward(vp):
    vp.set_fly_mode(True)
    heading = _heading(vp)
    eye0 = _eye(vp)

    _hold(vp, 0, 100 + _FLY_DEADZONE_PX)         # cursor below the origin
    vp._apply_fly_drag(1000.0)

    moved = tuple(_eye(vp)[i] - eye0[i] for i in range(3))
    assert _close(_unit(moved), tuple(-h for h in heading))


def test_flight_speed_scales_with_offset_arm_length_and_time(vp):
    vp.set_fly_mode(True)
    eye0 = _eye(vp)
    _hold(vp, 0, -(80 + _FLY_DEADZONE_PX))       # 80px of net offset
    vp._apply_fly_drag(500.0)                    # half a second
    step = math.dist(_eye(vp), eye0)
    assert math.isclose(step, 80 * vp._cam_distance * _FLY_RATE_PER_PX_S * 0.5,
                        abs_tol=1e-9)


def test_flight_continues_while_the_mouse_sits_still(vp):
    """The defining rate-flight behavior: a held offset keeps flying with no
    further mouse movement, at a constant speed."""
    vp.set_fly_mode(True)
    eye0 = _eye(vp)
    _hold(vp, 0, -(50 + _FLY_DEADZONE_PX))

    vp._apply_fly_drag(400.0)
    one_tick = math.dist(_eye(vp), eye0)
    vp._apply_fly_drag(400.0)                    # cursor untouched
    two_ticks = math.dist(_eye(vp), eye0)

    assert one_tick > 0.0
    assert math.isclose(two_ticks, 2 * one_tick, rel_tol=1e-9)


def test_no_motion_inside_the_dead_zone(vp):
    vp.set_fly_mode(True)
    eye0, aim0 = _eye(vp), vp._camera_basis()[0]

    _hold(vp, _FLY_DEADZONE_PX * 0.5, -_FLY_DEADZONE_PX * 0.5)
    vp._apply_fly_drag(1000.0)

    assert math.dist(_eye(vp), eye0) < 1e-12
    assert _close(vp._camera_basis()[0], aim0, tol=1e-12)


def test_returning_to_the_origin_stops_the_flight(vp):
    vp.set_fly_mode(True)
    _hold(vp, 0, -50)
    vp._apply_fly_drag(1000.0)
    eye_mid = _eye(vp)

    vp._fly_cursor = vp._fly_anchor              # back to the bearings origin
    vp._apply_fly_drag(1000.0)

    assert math.dist(_eye(vp), eye_mid) < 1e-12


def test_turning_pivots_in_place_instead_of_orbiting(vp):
    """The bug this guards: naively changing azimuth swings the eye around
    the target, which is exactly the anchored feel Camera Mode exists to
    escape."""
    vp.set_fly_mode(True)
    eye0 = _eye(vp)
    _hold(vp, 30 + _FLY_DEADZONE_PX, 0)
    vp._apply_fly_drag(1000.0)
    assert math.dist(_eye(vp), eye0) < 1e-9


def test_holding_right_of_the_origin_turns_right(vp):
    """A right turn rotates the aim toward the camera's own right vector.
    Checked at zero pitch, where a heading change about world Z and a
    rotation in the camera's frame coincide exactly."""
    vp.set_fly_mode(True)
    vp._cam_azimuth, vp._cam_elevation = 15.0, 0.0
    vp._cam_target = [0.0, 0.0, 0.0]
    forward0, right0, _u = vp._camera_basis()

    _hold(vp, 40 + _FLY_DEADZONE_PX, 0)
    vp._apply_fly_drag(1000.0)

    theta = math.radians(40 * _FLY_TURN_DEG_PER_PX_S)
    expected = tuple(forward0[i] * math.cos(theta) + right0[i] * math.sin(theta)
                     for i in range(3))
    assert _close(vp._camera_basis()[0], expected)


def test_no_flight_outside_camera_mode_or_without_an_anchor(vp):
    eye0 = _eye(vp)
    _hold(vp, 0, -200)                           # fly_mode is still off
    vp._apply_fly_drag(1000.0)
    assert math.dist(_eye(vp), eye0) < 1e-12

    vp.set_fly_mode(True)                        # on, but no drag in progress
    vp._fly_anchor = vp._fly_cursor = None
    vp._apply_fly_drag(1000.0)
    assert math.dist(_eye(vp), eye0) < 1e-12


# --- press / release state machine -----------------------------------------

def test_left_press_drops_the_origin_and_starts_the_repaint_timer(vp):
    vp.set_fly_mode(True)
    assert not vp._render_timer.isActive()

    vp.mousePressEvent(_Mouse(120, 80, Qt.MouseButton.LeftButton,
                              Qt.MouseButton.LeftButton))

    assert vp._fly_anchor == (120.0, 80.0)
    assert vp._fly_cursor == (120.0, 80.0)
    assert vp._render_timer.isActive(), 'held-offset flight needs ticks'


def test_release_ends_the_drag_and_stops_the_timer(vp):
    vp.set_fly_mode(True)
    vp.mousePressEvent(_Mouse(120, 80, Qt.MouseButton.LeftButton,
                              Qt.MouseButton.LeftButton))
    vp._drag_moved = True                        # skip the click-pick path

    vp.mouseReleaseEvent(_Mouse(150, 90, Qt.MouseButton.LeftButton,
                                Qt.MouseButton.NoButton))

    assert vp._fly_anchor is None and vp._fly_cursor is None
    assert not vp._render_timer.isActive()


def test_pressing_the_second_button_of_a_combo_suspends_rate_flight(vp):
    """Left+Right together strafes; the rate-flight origin is dropped so the
    strafe isn't fighting a leftover held-offset flight."""
    vp.set_fly_mode(True)
    vp.mousePressEvent(_Mouse(120, 80, Qt.MouseButton.LeftButton,
                              Qt.MouseButton.LeftButton))
    both = Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton
    vp.mousePressEvent(_Mouse(120, 80, Qt.MouseButton.RightButton, both))
    assert vp._fly_anchor is None


def test_ending_a_combo_with_left_still_down_reanchors_at_the_cursor(vp):
    """Releasing Right out of a Left+Right strafe resumes rate flight from a
    *fresh* origin under the cursor — the pre-combo origin is stale and would
    lurch the camera the moment Right lifted."""
    vp.set_fly_mode(True)
    vp.mousePressEvent(_Mouse(120, 80, Qt.MouseButton.LeftButton,
                              Qt.MouseButton.LeftButton))
    both = Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton
    vp.mousePressEvent(_Mouse(120, 80, Qt.MouseButton.RightButton, both))
    vp._drag_moved = True

    vp.mouseReleaseEvent(_Mouse(200, 150, Qt.MouseButton.RightButton,
                                Qt.MouseButton.LeftButton))

    assert vp._fly_anchor == (200.0, 150.0)
    assert vp._render_timer.isActive()


# --- look around -----------------------------------------------------------

def test_look_around_keeps_the_eye_planted(vp):
    vp.set_fly_mode(True)
    eye0, arm = _eye(vp), vp._cam_distance
    aim0 = vp._camera_basis()[0]

    vp._look_around_camera(60, 25)

    assert math.dist(_eye(vp), eye0) < 1e-9
    assert math.isclose(math.dist(_eye(vp), vp._cam_target), arm, abs_tol=1e-9)
    assert not _close(vp._camera_basis()[0], aim0, tol=1e-3)


def test_look_around_turns_the_same_way_flight_does(vp):
    vp.set_fly_mode(True)
    vp._cam_azimuth, vp._cam_elevation = 15.0, 0.0
    vp._cam_target = [0.0, 0.0, 0.0]
    forward0, right0, _u = vp._camera_basis()

    vp._look_around_camera(40, 0)

    theta = math.radians(40 * _LOOK_DEG_PER_PX)
    expected = tuple(forward0[i] * math.cos(theta) + right0[i] * math.sin(theta)
                     for i in range(3))
    assert _close(vp._camera_basis()[0], expected)


@pytest.mark.parametrize('dy, expected', [(10_000, 89.0), (-10_000, -89.0)])
def test_pitch_clamps_short_of_the_up_vector_singularity(vp, dy, expected):
    vp.set_fly_mode(True)
    vp._look_around_camera(0, dy)
    assert vp._cam_elevation == expected


# --- strafe / pedestal -----------------------------------------------------

def test_strafe_slides_the_camera_without_changing_the_aim(vp):
    vp.set_fly_mode(True)
    vp._cam_azimuth, vp._cam_elevation = 0.0, 0.0
    vp._cam_target = [0.0, 0.0, 0.0]
    forward0, right0, _u = vp._camera_basis()
    eye0 = _eye(vp)

    vp._fly_strafe_camera(50, 0)

    assert _close(_unit(tuple(_eye(vp)[i] - eye0[i] for i in range(3))), right0)
    assert _close(vp._camera_basis()[0], forward0, tol=1e-12)

    eye1 = _eye(vp)
    vp._fly_strafe_camera(0, 50)     # drag down
    assert _eye(vp)[2] < eye1[2]


# --- wheel -----------------------------------------------------------------

class _Wheel:
    """Stand-in for QWheelEvent — wheelEvent only reads angleDelta().y()."""

    def __init__(self, dy):
        self._dy = dy

    def angleDelta(self):
        return QPoint(0, self._dy)


def test_wheel_flies_instead_of_zooming_in_camera_mode(vp):
    vp.set_fly_mode(True)
    forward, arm = vp._camera_basis()[0], vp._cam_distance
    eye0 = _eye(vp)

    vp.wheelEvent(_Wheel(120))

    assert math.isclose(vp._cam_distance, arm, abs_tol=1e-12), 'arm length is the speed scale'
    assert _close(_unit(tuple(_eye(vp)[i] - eye0[i] for i in range(3))), forward)


def test_wheel_still_zooms_outside_camera_mode(vp):
    arm = vp._cam_distance
    vp.wheelEvent(_Wheel(120))
    assert math.isclose(vp._cam_distance, arm * 0.88, abs_tol=1e-9)


# --- mode interlocks -------------------------------------------------------

def test_engaging_camera_mode_clears_follow_selected(vp):
    vp.follow_selected = True
    vp.set_fly_mode(True)
    assert vp.follow_selected is False


def test_fixed_reference_views_do_not_fly(vp):
    vp.select_camera(1)                      # +X View, locked
    assert vp.active_camera_locked()

    vp.set_fly_mode(True)
    assert vp.fly_mode is True
    assert vp.active_camera_index == 0, 'switches to Main rather than flying a locked view'

    vp.select_camera(1)
    assert vp.fly_mode is False, 'picking a reference view leaves Camera Mode'


def test_starting_a_both_button_drag_does_not_teleport_the_camera(vp):
    """Outside Camera Mode, pressing both buttons snaps the orbit pivot onto
    the selected node. In Camera Mode the eye is derived from that pivot, so
    the same snap would teleport the camera onto the node mid-flight."""
    vp.selected_node_ids = {2}
    vp.set_fly_mode(True)
    eye0 = _eye(vp)

    vp._maybe_snap_orbit_target()

    assert math.dist(_eye(vp), eye0) < 1e-9


def test_leaving_camera_mode_ends_any_flight_drag(vp):
    vp.set_fly_mode(True)
    _hold(vp, 0, -50)
    vp.set_fly_mode(False)
    assert vp._fly_anchor is None and vp._fly_cursor is None


def test_camera_state_round_trips_camera_mode(vp):
    vp.set_fly_mode(True)
    state = vp.camera_state()
    vp.set_fly_mode(False)

    vp.restore_camera_state(state)
    assert vp.fly_mode is True


def test_a_snapshot_predating_camera_mode_restores_cleanly(vp):
    """Older camera_state() dicts have no 'fly' key — they must load as
    orbit mode, not blow up."""
    vp.set_fly_mode(True)
    state = vp.camera_state()
    del state['fly']

    vp.restore_camera_state(state)
    assert vp.fly_mode is False
