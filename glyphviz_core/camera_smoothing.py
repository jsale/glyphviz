"""Camera smoothing — the optional ANTz-style "inertia" on camera navigation.

Qt-free so it can be unit-tested headlessly (same split as `gizmo.py`,
`drop_router.py` and `basemap.py`); the viewport owns the state and calls in
here once per repaint tick.


What ANTz did, and what it got wrong
------------------------------------

ANTz smoothed its camera in two independent places, and only one of them is
the effect users remember fondly:

1. A 10-cycle boxcar average of the raw mouse deltas (`npUpdateMouse`,
   npmouse.c). Every camera mode got it. This is the part that buffered a
   user's hand tremor — the accessibility win Dr. Warner reported.

2. A first-order low-pass on the camera's *world position* while "targeting"
   (`npCameraTranslate`, npengine.c), engaged by the Left+Right combo drag:

       cam->translate = f*ideal + (1-f)*cam->translate,  f = 0.05 * 65/(fps+5)

   but the orbit *angle* and the *zoom distance* were applied instantly, the
   same frame. So the eye crawled toward a solution the aim had already left,
   and the object being orbited genuinely swung out of frame for a second or
   two before easing back. That artifact — not the smoothing itself — is what
   made the feature divisive, and ANTz never offered a way to turn it off.

GlyphViz keeps the glide and drops the artifact by easing the camera rig
*coherently*: azimuth, elevation, distance and target all run through the same
filter with the same time constant, so the aim and the eye never disagree and
the framing stays put. The gesture writes a GOAL; the rendered camera is the
ACTUAL, chasing it. With tau = 0 the actual is assigned the goal outright, so
smoothing off is bit-identical to no smoothing at all.

The filter is also frame-rate correct — `alpha_for` solves the exponential
properly instead of ANTz's `65/(fps+5)` fudge, so the same setting feels the
same at 30 fps and at 144. (ANTz's smoothing being much heavier in its early,
slower years is exactly that fudge failing.)

Note this is a *lag* filter, not momentum: releasing the mouse stops the goal,
and the actual coasts to rest against it. Nothing ever overshoots or keeps
spinning.
"""

from __future__ import annotations

import math

__all__ = [
    'TAU_OFF', 'TAU_ANTZ', 'TAU_MAX',
    'SCOPE_COMBO', 'SCOPE_ALL', 'SCOPES',
    'alpha_for', 'ease_scalar', 'ease_angle', 'ease_log', 'ease_point',
    'is_settled',
]


# --- Smoothing amount ---------------------------------------------------------
#
# The setting is a time constant in seconds: the time to close ~63% of the
# remaining gap. Exposed to the user as a slider from TAU_OFF to TAU_MAX.

TAU_OFF = 0.0     # no smoothing: the rendered camera IS the gesture (default)
TAU_ANTZ = 0.33   # ANTz's own feel: its f = 0.05/frame at 60 fps is tau ~= 0.33 s
TAU_MAX = 0.60    # slider ceiling — beyond this the camera feels disconnected

# --- Which gestures the filter applies to -------------------------------------
#
# ANTz's positional lag engaged only on the Left+Right combo drag, so that is
# the faithful default. SCOPE_ALL widens it to every orbit-rig gesture
# (single-button orbit, wheel zoom, pan), which is what a user relying on the
# tremor-buffering actually needs — they are not only using the combo gesture.
# Camera Mode (free flight) is excluded under both: it is already integrated
# per tick from a held cursor offset, so it has no per-event jitter to filter.

SCOPE_COMBO = 'combo'
SCOPE_ALL = 'all'
SCOPES = (SCOPE_COMBO, SCOPE_ALL)


def alpha_for(dt: float, tau: float) -> float:
    """Blend fraction for one step of `dt` seconds at time constant `tau`.

    `1 - exp(-dt/tau)` is the exact solution of the exponential decay, which is
    what makes the result frame-rate independent: two 8ms steps close exactly
    as much of the gap as one 16ms step. A per-frame constant (ANTz's `f`)
    does not have that property, and drifts with frame rate.

    Returns 1.0 (snap outright) for tau <= 0, so smoothing-off costs nothing
    and introduces no floating-point drift.
    """
    if tau <= 0.0 or dt <= 0.0:
        return 1.0
    return 1.0 - math.exp(-dt / tau)


def ease_scalar(actual: float, goal: float, alpha: float) -> float:
    """One filter step on a plain scalar."""
    if alpha >= 1.0:
        return goal
    return actual + (goal - actual) * alpha


def ease_angle(actual: float, goal: float, alpha: float) -> float:
    """One filter step on an angle in degrees, along the SHORTEST arc.

    Azimuth is unbounded and wraps, so a naive lerp from 350 to 10 would take
    the camera the long way round — a full 340-degree spin for a 20-degree
    drag. The residual is folded into (-180, 180] first. The result is not
    re-wrapped: the viewport's own azimuth is free-running, and clamping it
    here would fight `_cam_elevation`'s pole clamp.
    """
    if alpha >= 1.0:
        return goal
    delta = (goal - actual + 180.0) % 360.0 - 180.0
    return actual + delta * alpha


def ease_log(actual: float, goal: float, alpha: float) -> float:
    """One filter step on a distance, eased GEOMETRICALLY.

    Zoom is multiplicative — the gesture scales the arm length by a factor per
    pixel — so a linear ease reads as a rush at the far end and a crawl at the
    near end. Filtering in log space makes the glide perceptually even, and
    keeps the value strictly positive so the arm can never cross zero.

    Non-positive inputs fall back to the linear ease rather than raising: the
    viewport clamps distance to >= 1.0, but a caller with a degenerate rig
    should get a sane camera rather than an exception mid-paint.
    """
    if alpha >= 1.0:
        return goal
    if actual <= 0.0 or goal <= 0.0:
        return ease_scalar(actual, goal, alpha)
    return math.exp(ease_scalar(math.log(actual), math.log(goal), alpha))


def ease_point(actual, goal, alpha: float) -> list[float]:
    """One filter step on an XYZ point (the orbit pivot). Returns a new list."""
    if alpha >= 1.0:
        return list(goal)
    return [a + (g - a) * alpha for a, g in zip(actual, goal)]


def is_settled(actual_az: float, goal_az: float,
               actual_el: float, goal_el: float,
               actual_dist: float, goal_dist: float,
               actual_target, goal_target,
               *, angle_tol: float = 0.05, dist_frac: float = 1e-3) -> bool:
    """True when every rig quantity is close enough to its goal to stop ticking.

    An exponential never *reaches* its goal, so without a tolerance the
    repaint timer would run forever after a single drag — and because the tail
    is long, a tolerance that is merely small still costs seconds of idle
    repainting. Both defaults are therefore set at roughly one screen pixel,
    which is where further easing stops being visible at all:

      * A ~1000px viewport at a ~60-degree field of view is ~0.06 deg/px, so
        0.05 degrees of residual rotation is under a pixel of movement.
      * The distance and target tolerances are relative to the arm length
        (0.1% of it), because an 0.05-unit residual is invisible on a
        500-unit rig and glaring on a 2-unit one.
    """
    if abs((goal_az - actual_az + 180.0) % 360.0 - 180.0) > angle_tol:
        return False
    if abs(goal_el - actual_el) > angle_tol:
        return False
    scale = max(abs(actual_dist), abs(goal_dist), 1.0)
    if abs(goal_dist - actual_dist) > scale * dist_frac:
        return False
    tol = scale * dist_frac
    return all(abs(g - a) <= tol for a, g in zip(actual_target, goal_target))
