"""
The Hyperdimensional Coordinate System (HCS): Jeff Sale's coordinate system in
which every dimension is the real line folded onto a circle (Dr. Art
Springer's subsegment-ratio construction, theta = 180 u / (1 + |u|), so
+/- infinity is a reachable point at 180 deg), and dimensions nest as circles
on circles. Ported from lorenz_sync_lab/generate_lorenz_sync.py, itself a port
of Jeff's hyperdims plotter (src/hcs/mapping.ts, geometry.ts).

Here each variable is scaled by the magnitude of its critical-point value, the
paper's own normalization (section 2e). Then u = +/-1, a steady roll, lands at
exactly +/-90 deg on every circle: a steady state is every circle parked at a
quarter turn.
"""
import numpy as np


def angle(v, s):
    """HCS angle in degrees of value v at scale s (hyperdims' valueToAngle)."""
    u = np.asarray(v, dtype=float) / s
    return 180.0 * u / (1.0 + np.abs(u))


def chain(angles, r1, ratio):
    """Leaf of the nested-circle HCS for rows of angles (deg), shape (N, D) ->
    (N, 3) in the glyph frame. Circle 1 lies in the frame's XY plane, radius
    r1; circle k+1 is centred on circle k's chosen point, in the plane of
    circle k's outward radial N and its normal w, radius scaled by ratio
    (hyperdims' childFrame). Vectorized."""
    angles = np.atleast_2d(angles)
    n = len(angles)
    c = np.zeros((n, 3))
    u = np.tile([1.0, 0.0, 0.0], (n, 1))
    v = np.tile([0.0, 1.0, 0.0], (n, 1))
    w = np.tile([0.0, 0.0, 1.0], (n, 1))
    radius = r1
    for d in range(angles.shape[1]):
        t = np.radians(angles[:, d])[:, None]
        radial = np.cos(t) * u + np.sin(t) * v
        point = c + radius * radial
        if d == angles.shape[1] - 1:
            return point
        c, u, v, w = point, radial, w, np.cross(radial, w)
        radius *= ratio


def ts_leaf(angles_deg, r1, ratio):
    """Literal one-row port of hyperdims/src/hcs/geometry.ts (baseFrame /
    childFrame / circlePoint) -- deliberately NOT chain(), so the two can
    check each other."""
    c, u, v, w = (np.zeros(3), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]),
                  np.array([0, 0, 1.0]))
    radius = r1

    def circle_point(theta):
        t = np.radians(theta)
        return c + np.cos(t) * radius * u + np.sin(t) * radius * v

    for theta in angles_deg[:-1]:
        t = np.radians(theta)
        n = np.cos(t) * u + np.sin(t) * v
        c = circle_point(theta)
        u, v, w = n, w, np.cross(n, w)
        radius *= ratio
    return circle_point(angles_deg[-1])
