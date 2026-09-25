"""Lesson: Camera Mode (free flight) — C, left-drag rate flight, turning,
right-drag look-around, the wheel, and C back to orbit.

Headings in this file: Camera Mode looks back along the azimuth, so forward
is (-cos az, -sin az). az=180 flies toward +X, az=90 toward -Y, and a right
turn DECREASES azimuth (viewport._apply_fly_drag).
"""
import math

from lessonkit import Key, Lesson, Shot, ease
from lessons._common import G_CUBE, glyph, world

SPACING = 6.0
EYE_Z = 2.5
FLY_DIST = 12.0   # rig arm length during flight; only positions the target


def _colour(h):
    # teal (short) -> indigo -> coral (tall)
    stops = [(38, 198, 181), (99, 140, 255), (255, 111, 97)]
    t = (h - 1.0) / 5.0
    i = min(int(t * 2), 1)
    f = t * 2 - i
    return tuple(int(stops[i][k] + (stops[i + 1][k] - stops[i][k]) * f) for k in range(3))


def build() -> Lesson:
    nodes = [world()]
    nid = 2
    for i in range(-3, 4):
        for j in range(-3, 4):
            # Deterministic, varied heights: a low rim, a tall middle.
            h = 1.2 + 4.3 * math.exp(-(i * i + j * j) / 7.0) \
                + 0.6 * math.sin(1.7 * i + 0.9 * j) ** 2
            nodes.append(glyph(nid, 0, 0, pos=(i * SPACING, j * SPACING, h),
                               scale=(1.0, 1.0, h), color=_colour(h),
                               geometry=G_CUBE))
            nid += 1

    def fly(u, *, eye, az, el=0.0):
        return Key(u, eye=(eye[0], eye[1], EYE_Z), az=az, el=el, dist=FLY_DIST)

    def drag(button, dx, dy, label):
        def g(u):
            k = ease(min(u / 0.35, 1.0)) * (1 - ease(max((u - 0.8) / 0.2, 0)))
            return dict(button=button, offset=(dx * k, dy * k), label=label)
        return g

    def look(u):
        # right-drag: sweep left, then up
        a = ease(min(u / 0.5, 1.0))
        b = ease(max((u - 0.5) / 0.4, 0.0))
        return dict(button="right", offset=(-70 * a + 30 * b, -60 * b),
                    label="right button: look around")

    shots = [
        Shot(title="Camera Mode", heading="Fly through a scene",
             say="Camera Mode lets you fly through a scene, "
                 "instead of orbiting it.",
             keys=[Key(0, az=215, el=38, dist=72, target=(0, 0, 3)),
                   Key(0.55, az=195, el=20, dist=40, target=(-6, 2, 3)),
                   fly(1, eye=(-30, 3), az=180)]),
        Shot(heading="Turn it on",
             say="Press C to turn it on. "
                 "You take off from right where you are.",
             keys=[fly(0, eye=(-30, 3), az=180), fly(1, eye=(-29, 3), az=180)],
             keycap="C", keycap_note="Camera Mode on"),
        Shot(heading="Fly forward",
             say="Hold the left button and move the mouse up. "
                 "The farther you move, the faster you fly.",
             keys=[fly(0, eye=(-29, 3), az=180), fly(1, eye=(4, 3), az=180)],
             gesture=drag("left", 0, -70, "left button: move up to fly")),
        Shot(heading="Turn while flying",
             say="Add some right, and you turn. "
                 "Your height never changes.",
             keys=[fly(0, eye=(4, 3), az=180),
                   fly(0.35, eye=(8.0, 2.4), az=150),
                   fly(0.55, eye=(9.0, 0.5), az=105),
                   fly(1, eye=(9.0, -9), az=90)],
             gesture=drag("left", 55, -50, "up and right: fly and turn")),
        Shot(heading="Look around",
             say="Right drag to look around, without moving.",
             keys=[fly(0, eye=(9, -9), az=90),
                   fly(0.5, eye=(9, -9), az=125),
                   fly(1, eye=(9, -9), az=105, el=-28)],
             gesture=look),
        Shot(heading="The wheel",
             say="The wheel moves you forward, or back.",
             keys=[fly(0, eye=(9, -9), az=105, el=-28),
                   fly(0.2, eye=(9, -9), az=90, el=-5),
                   fly(0.6, eye=(9, -17), az=90, el=-5),
                   fly(1, eye=(9, -12), az=90, el=-5)],
             gesture=drag("wheel", 0, 0, "wheel: forward / back")),
        Shot(heading="Back to orbit",
             say="Press C again to go back to orbiting.",
             keys=[fly(0, eye=(9, -12), az=90, el=-5),
                   Key(1, az=240, el=40, dist=78, target=(0, 0, 3))],
             keycap="C", keycap_note="Camera Mode off"),
        Shot(heading="Recap",
             say="That's Camera Mode.",
             keys=[Key(1, az=265)], min_dur=5,
             summary=["C: Camera Mode on / off",
                      "Left drag up: fly forward (farther = faster)",
                      "Left drag sideways: turn, height stays level",
                      "Right drag: look around   Wheel: forward / back"]),
    ]
    return Lesson(name="camera_mode", title="Camera Mode", nodes=nodes,
                  shots=shots, voice="af_heart")
