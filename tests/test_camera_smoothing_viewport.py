"""
Camera smoothing — viewport wiring.

The math lives in tests/test_camera_smoothing.py; this file pins the contract
the viewport has to hold up around it:

  * OFF IS OFF. With the default settings every gesture must leave the camera
    exactly where it left it before the feature existed. This is the test that
    protects 53 example scenes and every existing camera test.
  * Gestures write the GOAL, and the rendered _cam_* chases it — so the
    matrices, picking and distance-scaled drag speeds all keep reading one
    consistent camera.
  * Programmatic moves (presets, framing, focus, follow, flight, restore) SNAP.
    A jump is a jump; only drags glide.
  * The glide continues after the mouse stops, so a still-settling camera has
    to hold the repaint timer open, then release it.

Needs a QOpenGLWidget, so it runs offscreen (no GL context required — nothing
here paints).
"""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtWidgets import QApplication              # noqa: E402

from glyphviz_core import camera_smoothing as cs        # noqa: E402
from glyphviz_core.node import Node                     # noqa: E402
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


class _Wheel:
    """Stand-in for QWheelEvent — wheelEvent only reads angleDelta()."""

    def __init__(self, dy):
        self._dy = dy

    def angleDelta(self):
        class _D:
            def __init__(self, dy):
                self._dy = dy

            def y(self):
                return self._dy
        return _D(self._dy)


def _wheel(dy):
    return _Wheel(dy)


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
    v.set_nodes([_node(1, 0, 0, 0), _node(2, 100, 50, 20)])
    v._cam_azimuth, v._cam_elevation, v._cam_distance = 37.0, 22.0, 400.0
    v._cam_target = [10.0, -5.0, 3.0]
    v._snap_camera_goal()
    return v


def _rig(v):
    return (v._cam_azimuth, v._cam_elevation, v._cam_distance, list(v._cam_target))


def _goal(v):
    return (v._cam_goal_azimuth, v._cam_goal_elevation,
            v._cam_goal_distance, list(v._cam_goal_target))


# --- off is off --------------------------------------------------------------

def test_defaults_to_off(vp):
    assert vp.camera_smoothing_tau == cs.TAU_OFF
    assert vp.camera_smoothing_scope == cs.SCOPE_COMBO


def test_goal_starts_matching_the_camera(vp):
    assert _goal(vp) == _rig(vp)


@pytest.mark.parametrize('gesture', [
    lambda v: v._orbit_camera(12.0, -7.0),
    lambda v: v._orbit_zoom_camera(12.0, -7.0),
])
def test_gestures_are_instant_when_off(vp, gesture):
    """The whole safety argument for shipping this on by default being a
    non-event: with tau = 0 the rendered camera lands on the goal inside the
    gesture call, with no filter step involved."""
    gesture(vp)
    assert _rig(vp) == _goal(vp)


def test_orbit_when_off_matches_the_original_formula(vp):
    """Pin the pre-existing sensitivity exactly (0.4 deg/px, inverted azimuth,
    +-89 elevation clamp) so the goal/actual split cannot have changed feel."""
    az0, el0 = vp._cam_azimuth, vp._cam_elevation
    vp._orbit_camera(12.0, -7.0)
    assert vp._cam_azimuth == pytest.approx(az0 - 12.0 * 0.4)
    assert vp._cam_elevation == pytest.approx(el0 - 7.0 * 0.4)


def test_orbit_zoom_when_off_matches_the_original_formula(vp):
    az0, d0 = vp._cam_azimuth, vp._cam_distance
    vp._orbit_zoom_camera(10.0, 20.0)
    assert vp._cam_azimuth == pytest.approx(az0 - 10.0 * 0.4)
    assert vp._cam_distance == pytest.approx(d0 * (1.0 + 20.0 * 0.005))


def test_elevation_clamp_survives_on_the_goal(vp):
    """The pole clamp has to live on the goal, or smoothing would let the
    camera ease past +-89 and flip through the up-vector singularity."""
    vp._orbit_camera(0.0, 10000.0)
    assert vp._cam_goal_elevation == pytest.approx(89.0)
    vp._orbit_camera(0.0, -100000.0)
    assert vp._cam_goal_elevation == pytest.approx(-89.0)


def test_camera_settled_is_trivially_true_when_off(vp):
    vp._orbit_camera(50.0, 30.0)
    assert vp._camera_settled()


# --- direct writes to the rig still work -------------------------------------
#
# Code outside the navigation path assigns _cam_* directly and expects the
# camera to be there — the Glyph Composer's preview does it, tests/test_camera_
# mode.py's fixture does it. If the goal did not adopt those writes, the next
# gesture would silently navigate from a stale viewpoint.

def test_a_direct_write_is_adopted_by_the_next_gesture(vp):
    vp._cam_distance = 400.0        # assigned directly, goal untouched
    vp.wheelEvent(_wheel(120))
    assert vp._cam_distance == pytest.approx(400.0 * 0.88)


def test_a_direct_write_is_adopted_by_an_orbit(vp):
    vp._cam_azimuth = 200.0
    vp._orbit_camera(10.0, 0.0)
    assert vp._cam_azimuth == pytest.approx(200.0 - 10.0 * 0.4)


def test_a_direct_write_survives_a_camera_state_snapshot(vp):
    """camera_state() reconciles the rig; with nothing gliding it must not
    overwrite a directly-assigned camera with a stale goal. This is the Glyph
    Composer preview's exact path."""
    vp._cam_azimuth, vp._cam_distance = 123.0, 7.5
    vp._cam_target = [1.0, 2.0, 3.0]
    state = vp.camera_state()
    assert state['azimuth'] == 123.0
    assert state['distance'] == 7.5
    assert state['target'] == [1.0, 2.0, 3.0]


def test_a_direct_write_survives_entering_camera_mode(vp):
    vp._cam_azimuth, vp._cam_distance = 123.0, 7.5
    vp.set_fly_mode(True)
    assert vp._cam_azimuth == 123.0
    assert vp._cam_distance == 7.5


def test_mid_glide_the_goal_wins_over_the_lagging_actual(vp):
    """The other half of the rule: a takeover mid-glide lands on where the
    user AIMED, not on where the camera had crawled to."""
    vp.set_camera_smoothing(cs.TAU_ANTZ, cs.SCOPE_ALL)
    vp._orbit_camera(60.0, 0.0)
    aimed = vp._cam_goal_azimuth
    vp._apply_camera_smoothing(1000.0 / 60.0)       # part-way there
    assert vp._cam_azimuth != pytest.approx(aimed)
    vp._reconcile_camera_goal()
    assert vp._cam_azimuth == pytest.approx(aimed)


# --- on: gestures write the goal, the camera lags ----------------------------

def test_combo_drag_glides_at_the_default_scope(vp):
    vp.set_camera_smoothing(cs.TAU_ANTZ)
    before = _rig(vp)
    vp._orbit_zoom_camera(30.0, 0.0)
    assert _goal(vp) != before, 'the gesture must move the goal'
    assert _rig(vp) == before, 'the rendered camera must not have jumped'


def test_single_button_orbit_is_instant_at_the_default_scope(vp):
    """SCOPE_COMBO is ANTz-faithful: only the Left+Right gesture glides."""
    vp.set_camera_smoothing(cs.TAU_ANTZ, cs.SCOPE_COMBO)
    vp._orbit_camera(30.0, 0.0)
    assert _rig(vp) == _goal(vp)


def test_single_button_orbit_glides_at_the_wide_scope(vp):
    """SCOPE_ALL is the tremor-buffering setting — it has to cover the plain
    orbit drag, which is what most navigation actually uses."""
    vp.set_camera_smoothing(cs.TAU_ANTZ, cs.SCOPE_ALL)
    before = _rig(vp)
    vp._orbit_camera(30.0, 0.0)
    assert _rig(vp) == before
    assert _goal(vp) != before


def test_wheel_zoom_is_instant_at_the_default_scope(vp):
    vp.set_camera_smoothing(cs.TAU_ANTZ, cs.SCOPE_COMBO)
    arm = vp._cam_distance
    vp.wheelEvent(_wheel(120))
    assert vp._cam_distance == pytest.approx(arm * 0.88)


def test_wheel_zoom_glides_at_the_wide_scope(vp):
    vp.set_camera_smoothing(cs.TAU_ANTZ, cs.SCOPE_ALL)
    arm = vp._cam_distance
    vp.wheelEvent(_wheel(120))
    assert vp._cam_distance == pytest.approx(arm), 'must not have jumped'
    assert vp._cam_goal_distance == pytest.approx(arm * 0.88)


def test_the_filter_converges_on_the_goal(vp):
    vp.set_camera_smoothing(cs.TAU_ANTZ, cs.SCOPE_ALL)
    vp._orbit_camera(60.0, 10.0)
    goal = _goal(vp)
    for _ in range(400):
        vp._apply_camera_smoothing(1000.0 / 60.0)
    assert vp._cam_azimuth == pytest.approx(goal[0], abs=1e-6)
    assert vp._cam_elevation == pytest.approx(goal[1], abs=1e-6)
    assert vp._cam_distance == pytest.approx(goal[2], abs=1e-6)
    assert vp._cam_target == pytest.approx(goal[3], abs=1e-6)


def test_the_filter_lands_exactly_on_the_goal(vp):
    """Not just 'close': once settled the rig must be bit-equal to the goal,
    so a saved viewpoint round-trips and _camera_settled stays true."""
    vp.set_camera_smoothing(cs.TAU_ANTZ, cs.SCOPE_ALL)
    vp._orbit_camera(60.0, 10.0)
    goal = _goal(vp)
    for _ in range(400):
        vp._apply_camera_smoothing(1000.0 / 60.0)
    assert _rig(vp) == goal


def test_a_huge_dt_does_not_snap_the_glide_away(vp):
    """paintGL's dt is time since the last paint, which after an idle spell can
    be seconds. Unclamped, the first frame of a drag would blow alpha to 1 and
    there would be no glide at all."""
    vp.set_camera_smoothing(cs.TAU_ANTZ, cs.SCOPE_ALL)
    vp._orbit_camera(60.0, 0.0)
    vp._apply_camera_smoothing(5000.0)
    assert vp._cam_azimuth != pytest.approx(vp._cam_goal_azimuth)


def test_turning_smoothing_off_lands_the_camera(vp):
    """No stranding the camera mid-swing when the user drags the slider to 0."""
    vp.set_camera_smoothing(cs.TAU_ANTZ, cs.SCOPE_ALL)
    vp._orbit_camera(60.0, 10.0)
    goal = _goal(vp)
    vp.set_camera_smoothing(cs.TAU_OFF)
    assert _rig(vp) == goal


def test_scope_change_alone_keeps_the_amount(vp):
    vp.set_camera_smoothing(cs.TAU_ANTZ, cs.SCOPE_ALL)
    vp.set_camera_smoothing(cs.TAU_ANTZ, cs.SCOPE_COMBO)
    assert vp.camera_smoothing_tau == pytest.approx(cs.TAU_ANTZ)
    assert vp.camera_smoothing_scope == cs.SCOPE_COMBO


def test_tau_is_clamped_to_the_slider_range(vp):
    vp.set_camera_smoothing(99.0)
    assert vp.camera_smoothing_tau == cs.TAU_MAX
    vp.set_camera_smoothing(-5.0)
    assert vp.camera_smoothing_tau == cs.TAU_OFF


def test_bogus_scope_is_ignored_rather_than_stored(vp):
    vp.set_camera_smoothing(cs.TAU_ANTZ, 'nonsense')
    assert vp.camera_smoothing_scope in cs.SCOPES


# --- programmatic moves snap -------------------------------------------------

def test_camera_preset_snaps(vp):
    """Picking +X View is a jump. Gliding it would be a different feature, and
    a locked axis camera easing into place would look broken."""
    vp.set_camera_smoothing(cs.TAU_ANTZ, cs.SCOPE_ALL)
    vp.select_camera(1)
    assert _rig(vp) == _goal(vp)


def test_focus_on_snaps(vp):
    vp.set_camera_smoothing(cs.TAU_ANTZ, cs.SCOPE_ALL)
    vp.focus_on((50.0, 60.0, 70.0), radius=5.0)
    assert _rig(vp) == _goal(vp)
    assert vp._cam_target == [50.0, 60.0, 70.0]


def test_set_camera_snaps(vp):
    vp.set_camera_smoothing(cs.TAU_ANTZ, cs.SCOPE_ALL)
    vp.set_camera(azimuth=123.0, distance=250.0)
    assert _rig(vp) == _goal(vp)
    assert vp._cam_azimuth == 123.0


def test_scene_load_autoframing_snaps(vp):
    """set_nodes auto-frames; that must not glide in from the old viewpoint."""
    vp.set_camera_smoothing(cs.TAU_ANTZ, cs.SCOPE_ALL)
    vp.set_nodes([_node(1, 0, 0, 0), _node(2, 900, 900, 900)])
    assert _rig(vp) == _goal(vp)


def test_camera_state_round_trip_snaps(vp):
    vp.set_camera_smoothing(cs.TAU_ANTZ, cs.SCOPE_ALL)
    state = vp.camera_state()
    vp._orbit_camera(45.0, 12.0)
    vp.restore_camera_state(state)
    assert _rig(vp) == _goal(vp)


def test_camera_state_captures_the_goal_not_a_half_finished_glide(vp):
    """Snapshotting mid-glide must save where the user aimed, not where the
    camera happened to have crawled to."""
    vp.set_camera_smoothing(cs.TAU_ANTZ, cs.SCOPE_ALL)
    vp._orbit_camera(60.0, 0.0)
    aimed = vp._cam_goal_azimuth
    state = vp.camera_state()
    assert state['azimuth'] == pytest.approx(aimed)


def test_follow_selected_snaps_every_frame(vp):
    """Follow re-centers from the node's own animation, so smoothing it would
    leave the camera permanently trailing a moving node."""
    vp.set_camera_smoothing(cs.TAU_ANTZ, cs.SCOPE_ALL)
    vp.selected_node_ids = {2}
    vp.follow_selected = True
    vp._apply_follow_target()
    assert _rig(vp) == _goal(vp)


def test_entering_camera_mode_lands_any_glide(vp):
    """Flight re-derives the rig from the CURRENT eye, so a lagging camera
    would feed back into the flight path."""
    vp.set_camera_smoothing(cs.TAU_ANTZ, cs.SCOPE_ALL)
    vp._orbit_camera(60.0, 10.0)
    goal = _goal(vp)
    vp.set_fly_mode(True)
    assert _rig(vp) == goal


def test_flight_is_never_smoothed(vp):
    """Camera Mode is excluded under both scopes — rate flight is already
    integrated per tick, so there is no per-event jitter to filter."""
    vp.set_camera_smoothing(cs.TAU_ANTZ, cs.SCOPE_ALL)
    vp.set_fly_mode(True)
    assert not vp._camera_smoothing_active(combo=True)
    vp._reaim_about_eye(15.0)
    assert _rig(vp) == _goal(vp)
    vp._translate_rig((1.0, 0.0, 0.0), 25.0)
    assert _rig(vp) == _goal(vp)


# --- the repaint timer -------------------------------------------------------

def test_a_gliding_camera_holds_the_repaint_timer_open(vp):
    """The glide continues while the mouse sits still, so mouse events alone
    would freeze it mid-swing — same reason rate flight keeps the timer up."""
    assert not vp._render_timer.isActive()
    vp.set_camera_smoothing(cs.TAU_ANTZ, cs.SCOPE_ALL)
    vp._orbit_camera(60.0, 10.0)
    assert vp._render_timer.isActive()


def test_the_timer_is_released_once_the_camera_settles(vp):
    """...and it has to STOP, or a static scene idle-repaints forever."""
    vp.set_camera_smoothing(cs.TAU_ANTZ, cs.SCOPE_ALL)
    vp._orbit_camera(60.0, 10.0)
    for _ in range(400):
        vp._apply_camera_smoothing(1000.0 / 60.0)
    assert vp._camera_settled()
    assert not vp._render_timer.isActive()


def test_off_never_starts_the_timer(vp):
    vp._orbit_camera(60.0, 10.0)
    vp._orbit_zoom_camera(30.0, 20.0)
    assert not vp._render_timer.isActive()


# --- the pivot snap: where ANTz's lag actually lived -------------------------

def test_pivot_snap_glides_when_smoothing_is_on(vp):
    """_maybe_snap_orbit_target re-centers on the selected node at combo-press.
    This is exactly ANTz's npSetCamTarget/"targeting" moment, and easing the
    pivot TOGETHER with the aim is the version that doesn't throw the object
    out of frame on the way."""
    vp.set_camera_smoothing(cs.TAU_ANTZ)
    vp.selected_node_ids = {2}
    before = list(vp._cam_target)
    vp._maybe_snap_orbit_target()
    assert vp._cam_goal_target != before
    assert vp._cam_target == before


def test_pivot_snap_is_instant_when_smoothing_is_off(vp):
    vp.selected_node_ids = {2}
    vp._maybe_snap_orbit_target()
    assert vp._cam_target == vp._cam_goal_target
    assert vp._cam_target != [10.0, -5.0, 3.0]
