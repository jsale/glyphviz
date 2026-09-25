"""Lesson: Torus topology — translate_x = angle around the ring, translate_y =
angle around the tube (0 outer edge, 90 top, 180 inner edge), translate_z =
distance out from the tube surface (topology._torus_offset). Children are
pre-rotated so their +Z points out of the surface, which the cone probe shows.
"""
import math

from lessonkit import Callout, Key, Lesson, Shot, ease, lerp, CORAL, TEAL, VIOLET
from lessons._common import G_CONE, G_SPHERE, G_TORUS, T_TORUS, glyph, world

TORUS, PROBE = 2, 3
RATIO = 0.25                  # tube radius 0.25, ring radius 0.75 (scale 1)
STANDOFF = 0.2                # half the probe's length: it rides the surface
CRUMB = 0.028
X_CRUMBS = list(range(10, 10 + 36))          # ids 10..45: every 10 deg of x
Y_CRUMBS = list(range(50, 50 + 36))          # ids 50..85: every 10 deg of y
Z_CRUMBS = list(range(90, 90 + 8))           # ids 90..97: radial steps
LATTICE0 = 200                                # 24 x 7 cells from here
Z_MAX = 0.75
# Ring angle the Y and Z sweeps run at. (Close-ups of GEO_TORUS show a small
# bright shading spike on the tube top that is the mesh's own, independent of
# any child -- verified with every child hidden. Reported, not fixed here.)
SIDE = 90


def _activity(hour, day):
    """A made-up weekly rhythm: weekday office hours, lazier weekends."""
    weekday = day < 5
    peak = 13.0 if weekday else 15.0
    width = 3.2 if weekday else 4.5
    base = 0.9 if weekday else 0.55
    return base * math.exp(-((hour - peak) / width) ** 2) + 0.06


def _heat(v):
    stops = [(38, 198, 181), (255, 193, 7), (255, 111, 97)]
    t = min(max(v, 0.0), 1.0) * 2
    i = min(int(t), 1)
    f = t - i
    return tuple(int(stops[i][k] + (stops[i + 1][k] - stops[i][k]) * f) for k in range(3))


def build() -> Lesson:
    nodes = [world(),
             glyph(TORUS, 0, 0, color=(63, 81, 181, 120), geometry=G_TORUS,
                   topo=T_TORUS, ratio=RATIO, text="Torus"),
             glyph(PROBE, TORUS, 1, pos=(0, 0, STANDOFF), scale=(0.1, 0.1, 0.2),
                   color=CORAL, geometry=G_CONE, text="child")]
    for k, nid in enumerate(X_CRUMBS):
        nodes.append(glyph(nid, TORUS, 1, pos=(k * 10, 0, 0.02), scale=CRUMB,
                           color=CORAL, hide=1))
    for k, nid in enumerate(Y_CRUMBS):
        nodes.append(glyph(nid, TORUS, 1, pos=(SIDE, k * 10, 0.02), scale=CRUMB,
                           color=TEAL, hide=1))
    for k, nid in enumerate(Z_CRUMBS):
        nodes.append(glyph(nid, TORUS, 1, pos=(SIDE, 90, (k + 1) * Z_MAX / 8),
                           scale=CRUMB, color=VIOLET, hide=1))
    for day in range(7):
        for hour in range(24):
            v = _activity(hour, day)
            nodes.append(glyph(LATTICE0 + day * 24 + hour, TORUS, 1,
                               pos=(hour * 15, day * 360 / 7, 0.02),
                               scale=0.035 + 0.05 * v, color=_heat(v),
                               geometry=G_SPHERE, hide=1))
    lattice = range(LATTICE0, LATTICE0 + 168)

    def probe(lesson, x=None, y=None, z=None):
        p = lesson.node(PROBE)
        if x is not None:
            p.translate_x = x
        if y is not None:
            p.translate_y = y
        if z is not None:
            p.translate_z = z

    def reveal(lesson, ids, upto):
        for nid in ids:
            n = lesson.node(nid)
            n.hide = 0 if nid < upto else 1

    def sweep(u, a=0.08, b=0.85):
        return ease((u - a) / (b - a))

    def anim_x(lesson, u):
        x = 360 * sweep(u)
        probe(lesson, x=x, y=0, z=STANDOFF)
        reveal(lesson, X_CRUMBS, X_CRUMBS[0] + int(x // 10) + (1 if u > 0.08 else 0))

    def anim_y(lesson, u):
        y = 360 * sweep(u)
        probe(lesson, x=SIDE, y=y, z=STANDOFF)
        reveal(lesson, Y_CRUMBS, Y_CRUMBS[0] + int(y // 10) + (1 if u > 0.08 else 0))

    def anim_z(lesson, u):
        up = sweep(u, 0.1, 0.55)
        down = sweep(u, 0.65, 0.95)
        z = STANDOFF + (Z_MAX - STANDOFF) * (up - down)
        probe(lesson, x=SIDE, y=90, z=z)
        # Crumbs mark how far it went, so they stay once laid.
        reveal(lesson, Z_CRUMBS, Z_CRUMBS[0] + int(round(8 * up)))

    def anim_lattice(lesson, u):
        lesson.node(PROBE).hide = 1
        reveal(lesson, X_CRUMBS + Y_CRUMBS + Z_CRUMBS, 0)
        shown = int(168 * sweep(u, 0.05, 0.6))
        reveal(lesson, lattice, LATTICE0 + shown)

    def readout(lesson, u):
        p = lesson.node(PROBE)
        return (f"translate_x  {p.translate_x % 360:5.0f}°\n"
                f"translate_y  {p.translate_y % 360:5.0f}°\n"
                f"translate_z  {p.translate_z:6.2f}")

    shots = [
        Shot(title="Torus Topology", heading="Children on a ring",
             say="Under Torus topology, a node's children ride the surface "
                 "of a ring.",
             keys=[Key(0, az=20, el=38, dist=4.2, target=(0, 0, 0)),
                   Key(1, az=75, el=30)],
             callouts=[Callout(PROBE, "child", 0.55, 0.95, offset=(80, -70),
                               color=CORAL)]),
        Shot(heading="translate_x: around the ring",
             say="Translate X is the angle around the ring. Zero to three "
                 "sixty goes all the way round.",
             keys=[Key(0, az=75, el=58, dist=3.4), Key(1, az=105)],
             animate=anim_x, readout=readout),
        Shot(heading="translate_y: around the tube",
             say="Translate Y is the angle around the tube: zero outside, "
                 "ninety on top, one eighty inside. The child always points "
                 "outward.",
             keys=[Key(0, az=125, el=18, dist=2.1, target=(0, 0.6, 0)),
                   Key(1, az=145, el=22)],
             animate=anim_y, readout=readout),
        Shot(heading="translate_z: out from the surface",
             say="Translate Z lifts the child straight out from the tube.",
             keys=[Key(0, az=145, el=22, dist=2.2, target=(0, 0.6, 0.3)),
                   Key(1, az=110, el=12)],
             animate=anim_z, readout=readout),
        Shot(heading="Data that wraps twice",
             say="Fill it, and you get a grid that wraps both ways: here, hour "
                 "of the day around the ring, and weekday around the tube.",
             keys=[Key(0, az=20, el=42, dist=4.0, target=(0, 0, 0)),
                   Key(1, az=130, el=48, dist=3.6)],
             animate=anim_lattice),
        Shot(heading="Recap",
             say="That's the Torus.",
             keys=[Key(1, az=175)], min_dur=5,
             summary=["translate_x: angle around the ring (0-360)",
                      "translate_y: angle around the tube",
                      "   0 outer edge, 90 top, 180 inner edge",
                      "translate_z: distance out from the surface"]),
    ]
    return Lesson(name="torus", title="Torus Topology", nodes=nodes,
                  shots=shots, show_grid=False, voice="af_heart")
