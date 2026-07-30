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

These tests need a QOpenGLWidget, so they run offscreen; they're skipped
outright if Qt can't start (e.g. a headless box with no platform plugin).
"""
import math
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtWidgets import QApplication              # noqa: E402

from glyphviz_core.node import Node                     # noqa: E402
from glyphviz_gl.viewport import (                      # noqa: E402
    _BANK_MAX_DEG, _BANK_TAU_S, _FLY_SPEED_PER_PX, _FLY_TURN_DEG_PER_PX,
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
    v._cam_bank = 0.0
    return v


def _eye(vp):
    return vp._eye_position_with_offset(0.0)


def _unit(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v)


def _close(a, b, tol=1e-9):
    return max(abs(x - y) for x, y in zip(a, b)) < tol


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


def test_unbanked_camera_passes_plain_world_z_to_glulookat(vp):
    assert vp._camera_up() == (0.0, 0.0, 1.0)


def test_banking_rolls_up_toward_right(vp):
    """Positive bank tips screen-up to the right, which reads on screen as
    banking into a right turn (verified against rendered frames)."""
    vp._cam_bank = 90.0
    _f, right, up = vp._camera_basis()
    assert _close(up, right)


def test_banked_up_stays_a_valid_look_at_vector(vp):
    vp._cam_bank = 20.0
    forward, _r, up = vp._camera_basis()
    assert math.isclose(math.sqrt(sum(c * c for c in up)), 1.0, abs_tol=1e-12)
    assert abs(sum(a * b for a, b in zip(up, forward))) < 1e-12


# --- flight ----------------------------------------------------------------

def test_flying_translates_eye_and_target_together_along_the_view_axis(vp):
    vp.set_fly_mode(True)
    forward = vp._camera_basis()[0]
    eye0, target0, arm = _eye(vp), list(vp._cam_target), vp._cam_distance

    vp._fly_camera(0, -100)          # drag up = fly forward

    moved = tuple(_eye(vp)[i] - eye0[i] for i in range(3))
    assert _close(_unit(moved), forward)
    assert _close(tuple(vp._cam_target[i] - target0[i] for i in range(3)), moved)
    assert math.isclose(math.dist(_eye(vp), vp._cam_target), arm, abs_tol=1e-9)
    assert _close(vp._camera_basis()[0], forward, tol=1e-12), 'aim must not change'


def test_flight_speed_scales_with_the_arm_length(vp):
    vp.set_fly_mode(True)
    eye0 = _eye(vp)
    vp._fly_camera(0, -100)
    step = math.dist(_eye(vp), eye0)
    assert math.isclose(step, 100 * vp._cam_distance * _FLY_SPEED_PER_PX, abs_tol=1e-9)


def test_turning_pivots_in_place_instead_of_orbiting(vp):
    """The bug this guards: naively changing azimuth swings the eye around
    the target, which is exactly the anchored feel Camera Mode exists to
    escape."""
    vp.set_fly_mode(True)
    eye0 = _eye(vp)
    vp._fly_camera(30, 0)
    assert math.dist(_eye(vp), eye0) < 1e-9


def test_a_rightward_drag_turns_right(vp):
    """A right turn rotates the aim toward the camera's own right vector.
    Checked at zero pitch, where a heading change about world Z and a
    rotation in the camera's frame coincide exactly."""
    vp.set_fly_mode(True)
    vp._cam_azimuth, vp._cam_elevation = 15.0, 0.0
    vp._cam_target = [0.0, 0.0, 0.0]
    forward0, right0, _u = vp._camera_basis()

    vp._fly_camera(40, 0)
    vp._cam_bank = 0.0               # bank would rotate up, not forward

    theta = math.radians(40 * _FLY_TURN_DEG_PER_PX)
    expected = tuple(forward0[i] * math.cos(theta) + right0[i] * math.sin(theta)
                     for i in range(3))
    assert _close(vp._camera_basis()[0], expected)


def test_sideways_drag_banks_into_the_turn_and_saturates(vp):
    vp.set_fly_mode(True)
    vp._fly_camera(30, 0)
    assert vp._cam_bank > 0.0, 'a right turn banks right'
    vp._cam_bank = 0.0
    vp._fly_camera(-30, 0)
    assert vp._cam_bank < 0.0, 'a left turn banks left'
    vp._cam_bank = 0.0
    for _ in range(20):
        vp._fly_camera(40, 0)
    assert math.isclose(vp._cam_bank, _BANK_MAX_DEG, abs_tol=1e-9)


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


# --- bank decay ------------------------------------------------------------

def test_bank_decays_toward_level_on_its_own_clock(vp):
    vp._cam_bank = 25.0
    vp._decay_bank(_BANK_TAU_S * 1000.0)          # exactly one time constant
    assert math.isclose(vp._cam_bank, 25.0 / math.e, rel_tol=1e-9)


def test_bank_decay_is_frame_rate_independent(vp):
    vp._cam_bank = 25.0
    vp._decay_bank(300.0)
    one_step = vp._cam_bank
    vp._cam_bank = 25.0
    for _ in range(30):
        vp._decay_bank(10.0)
    assert math.isclose(vp._cam_bank, one_step, rel_tol=1e-9)


def test_bank_snaps_to_exactly_level_and_restores_world_up(vp):
    vp._cam_bank = 25.0
    for _ in range(60):
        vp._decay_bank(100.0)
    assert vp._cam_bank == 0.0
    assert vp._camera_up() == (0.0, 0.0, 1.0)


def test_a_turn_starts_the_repaint_timer_so_the_bank_can_level(vp):
    vp.set_fly_mode(True)
    vp._update_render_timer_state()
    assert not vp._render_timer.isActive()

    vp._fly_camera(30, 0)
    assert vp._render_timer.isActive()

    for _ in range(60):
        vp._decay_bank(100.0)
    assert vp._cam_bank == 0.0 and not vp._render_timer.isActive()


# --- wheel -----------------------------------------------------------------

class _Wheel:
    """Stand-in for QWheelEvent — wheelEvent only reads angleDelta().y()."""

    def __init__(self, dy):
        self._dy = dy

    def angleDelta(self):
        from PySide6.QtCore import QPoint
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


def test_leaving_camera_mode_levels_the_horizon(vp):
    vp.set_fly_mode(True)
    vp._cam_bank = 20.0
    vp.set_fly_mode(False)
    assert vp._cam_bank == 0.0


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
