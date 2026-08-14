"""
Camera smoothing (optional ANTz-style navigation inertia) — filter math.

The contract, from glyphviz_core/camera_smoothing.py:

  * tau = 0 is EXACTLY off. The default has to be bit-identical to the
    behavior that shipped before the feature existed.
  * The filter is frame-rate independent — the same setting must feel the same
    at 30 fps and 144. (ANTz's `0.05 * 65/(fps+5)` fudge is not, which is why
    its smoothing was so much heavier in its early, slower years.)
  * Azimuth eases along the shortest arc, so a drag across the 0/360 seam is a
    small correction, not a full spin.
  * Distance eases geometrically, because zoom is multiplicative.
  * It is a LAG filter, not momentum: nothing overshoots or keeps going.
"""
import math

import pytest

from glyphviz_core import camera_smoothing as cs


# --- alpha_for: the off switch and frame-rate independence -------------------

@pytest.mark.parametrize('dt', [0.001, 1 / 144, 1 / 60, 1 / 30, 0.5])
def test_tau_zero_snaps_outright(dt):
    """tau = 0 must give alpha 1.0 at every dt: smoothing off costs nothing
    and introduces no drift."""
    assert cs.alpha_for(dt, cs.TAU_OFF) == 1.0


def test_negative_tau_also_snaps():
    assert cs.alpha_for(1 / 60, -0.5) == 1.0


def test_zero_dt_snaps_rather_than_stalling():
    """A zero-length step must not silently return alpha 0 and freeze."""
    assert cs.alpha_for(0.0, cs.TAU_ANTZ) == 1.0


def test_alpha_is_the_exponential_not_a_ratio():
    """One tau closes ~63.2% of the gap, by definition of the time constant."""
    assert cs.alpha_for(cs.TAU_ANTZ, cs.TAU_ANTZ) == pytest.approx(1 - 1 / math.e)


def _settle(steps, dt, tau, start=0.0, goal=100.0):
    v = start
    for _ in range(steps):
        v = cs.ease_scalar(v, goal, cs.alpha_for(dt, tau))
    return v


def test_frame_rate_independence():
    """Half a second of smoothing must land in the same place whether the app
    is painting at 30, 60 or 144 fps. This is the property ANTz lacked."""
    tau = cs.TAU_ANTZ
    at_30 = _settle(15, 1 / 30, tau)
    at_60 = _settle(30, 1 / 60, tau)
    at_144 = _settle(72, 1 / 144, tau)
    assert at_30 == pytest.approx(at_60, abs=1e-9)
    assert at_60 == pytest.approx(at_144, abs=1e-9)


def test_two_half_steps_equal_one_whole_step():
    """The exact-exponential property, stated directly."""
    tau = 0.25
    one = cs.ease_scalar(0.0, 1.0, cs.alpha_for(0.02, tau))
    half = cs.ease_scalar(0.0, 1.0, cs.alpha_for(0.01, tau))
    half = cs.ease_scalar(half, 1.0, cs.alpha_for(0.01, tau))
    assert one == pytest.approx(half, abs=1e-12)


def test_antz_tau_matches_antz_feel():
    """TAU_ANTZ is claimed to reproduce ANTz's f = 0.05 per frame at 60 fps
    (npengine.c's npLowPassFilter call). Check the claim rather than trusting
    the comment: one 1/60 s step should close ~5% of the gap."""
    assert cs.alpha_for(1 / 60, cs.TAU_ANTZ) == pytest.approx(0.05, abs=0.005)


# --- ease_scalar / ease_point: convergence, no overshoot ---------------------

def test_lag_filter_never_overshoots():
    """A lag filter approaches monotonically — it is not momentum. If this
    ever fails, the camera has started swinging past its goal."""
    v, goal = 0.0, 100.0
    prev = v
    for _ in range(300):
        v = cs.ease_scalar(v, goal, cs.alpha_for(1 / 60, cs.TAU_ANTZ))
        assert prev <= v <= goal
        prev = v


def test_converges_to_the_goal():
    assert _settle(600, 1 / 60, cs.TAU_ANTZ) == pytest.approx(100.0, abs=1e-6)


def test_ease_point_moves_all_three_axes():
    out = cs.ease_point([0.0, 0.0, 0.0], [10.0, -20.0, 5.0], 0.5)
    assert out == [5.0, -10.0, 2.5]


def test_ease_point_returns_a_new_list():
    """The viewport keeps _cam_target and _cam_goal_target as separate lists;
    aliasing them would make the goal follow the actual and kill the glide."""
    actual = [1.0, 2.0, 3.0]
    goal = [4.0, 5.0, 6.0]
    out = cs.ease_point(actual, goal, 0.5)
    assert out is not actual and out is not goal
    assert actual == [1.0, 2.0, 3.0]


def test_ease_point_snaps_at_alpha_one():
    goal = [4.0, 5.0, 6.0]
    out = cs.ease_point([1.0, 2.0, 3.0], goal, 1.0)
    assert out == goal and out is not goal


# --- ease_angle: the wrap seam ----------------------------------------------

def test_shortest_arc_across_the_seam():
    """350 -> 10 is +20 degrees, not -340. Without this a drag across the seam
    would spin the camera all the way round the scene."""
    out = cs.ease_angle(350.0, 10.0, 0.5)
    assert out == pytest.approx(360.0)


def test_shortest_arc_the_other_way():
    out = cs.ease_angle(10.0, 350.0, 0.5)
    assert out == pytest.approx(0.0)


def test_exact_opposite_is_finite_and_bounded():
    """A 180-degree residual is the ambiguous case; it must still resolve to a
    single half-step rather than blowing up."""
    out = cs.ease_angle(0.0, 180.0, 0.5)
    assert abs(out) == pytest.approx(90.0)


def test_angle_does_not_rewrap_the_result():
    """The viewport's azimuth is free-running (it can sit at 725 degrees after
    a few spins); clamping here would jump the camera."""
    assert cs.ease_angle(720.0, 720.0, 0.5) == pytest.approx(720.0)


def test_angle_snaps_at_alpha_one():
    assert cs.ease_angle(350.0, 10.0, 1.0) == 10.0


def test_angle_converges_across_the_seam():
    v = 359.0
    for _ in range(400):
        v = cs.ease_angle(v, 1.0, cs.alpha_for(1 / 60, cs.TAU_ANTZ))
    # Lands on the goal, having travelled +2 degrees rather than -358.
    assert ((v - 1.0 + 180.0) % 360.0) - 180.0 == pytest.approx(0.0, abs=1e-6)
    assert 359.0 <= v <= 361.0


# --- ease_log: zoom -----------------------------------------------------

def test_distance_eases_geometrically():
    """Halfway from 100 to 400 in log space is 200 (the geometric mean), not
    250. Zoom is multiplicative, so this is what reads as an even glide."""
    assert cs.ease_log(100.0, 400.0, 0.5) == pytest.approx(200.0)


def test_distance_stays_positive():
    """The arm length can never cross zero, however aggressive the zoom."""
    v = 500.0
    for _ in range(200):
        v = cs.ease_log(v, 1.0, cs.alpha_for(1 / 60, cs.TAU_ANTZ))
        assert v > 0.0


def test_distance_snaps_at_alpha_one():
    assert cs.ease_log(100.0, 400.0, 1.0) == 400.0


def test_distance_degenerate_input_falls_back_instead_of_raising():
    """log(0) would raise mid-paint; a degenerate rig should still render."""
    assert cs.ease_log(0.0, 400.0, 0.5) == pytest.approx(200.0)
    assert cs.ease_log(100.0, 0.0, 0.5) == pytest.approx(50.0)


# --- is_settled: what stops the repaint timer --------------------------------

def _settled(**kw):
    base = dict(actual_az=10.0, goal_az=10.0, actual_el=5.0, goal_el=5.0,
                actual_dist=100.0, goal_dist=100.0,
                actual_target=[0.0, 0.0, 0.0], goal_target=[0.0, 0.0, 0.0])
    base.update(kw)
    return cs.is_settled(base['actual_az'], base['goal_az'],
                         base['actual_el'], base['goal_el'],
                         base['actual_dist'], base['goal_dist'],
                         base['actual_target'], base['goal_target'])


def test_identical_rig_is_settled():
    assert _settled()


@pytest.mark.parametrize('kw', [
    {'goal_az': 20.0},
    {'goal_el': 15.0},
    {'goal_dist': 150.0},
    {'goal_target': [50.0, 0.0, 0.0]},
])
def test_any_axis_off_goal_is_unsettled(kw):
    assert not _settled(**kw)


def test_settled_across_the_seam():
    """359.999 vs 0.0 is a hair apart, not 360 degrees apart."""
    assert _settled(actual_az=359.999, goal_az=0.0)


def test_position_tolerance_scales_with_arm_length():
    """A 0.4-unit residual is invisible on a 500-unit rig and glaring on a
    2-unit one, so the tolerance is relative."""
    assert _settled(actual_dist=500.0, goal_dist=500.0,
                    actual_target=[0.4, 0.0, 0.0])
    assert not _settled(actual_dist=2.0, goal_dist=2.0,
                        actual_target=[0.4, 0.0, 0.0])


def test_glide_is_visually_complete_within_three_tau():
    """What the user perceives: 95% of a 90-degree orbit is done by 3 tau
    (~1 s at the ANTz setting). The rest is the exponential's invisible tail."""
    az, goal = 0.0, 90.0
    frames = int(3 * cs.TAU_ANTZ * 60)      # whole frames, so a hair under 3 tau
    for _ in range(frames):
        az = cs.ease_angle(az, goal, cs.alpha_for(1 / 60, cs.TAU_ANTZ))
    # 1 - e^-3 = 95.02% of the way; the whole-frame truncation costs a little.
    assert az == pytest.approx(goal * (1 - math.exp(-3)), rel=0.01)
    assert az > goal * 0.94


def test_a_real_glide_stops_holding_the_repaint_timer():
    """The tail still has to END, or the ~30fps repaint timer would idle-spin
    on a static scene forever after a drag. At sub-pixel tolerance a 90-degree
    orbit at the ANTz setting releases the timer inside three seconds."""
    az, goal = 0.0, 90.0
    for frame in range(240):        # 4 s at 60 fps
        az = cs.ease_angle(az, goal, cs.alpha_for(1 / 60, cs.TAU_ANTZ))
        if _settled(actual_az=az, goal_az=goal):
            break
    else:
        pytest.fail('90-degree glide never settled')
    assert frame / 60.0 < 3.0
