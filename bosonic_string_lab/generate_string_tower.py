"""
The String Tower: why bosonic string theory needs 26 dimensions, and its
infinite tower of states on one HCS circle.

A static scene (no Channels).

    circle    one HCS circle for mass^2 = N - 1 (units of 4/alpha', scale
              s = 1): massless at 0 deg, the tachyon at -90 deg, level 2 at
              90 deg, and every higher level crowding toward infinity at
              180 deg. The whole infinite tower fits on the circle.
    bars      one radial bar per level N = 1..12, length = log10 of how many
              states one side of the string has there (1, 24, 324, 3,200, ...
              10,914,317,934): the growth that never stops
    right     Moonshine: level 2's 324 vibration states plus the Leech
              lattice's 196,560 kissing vectors make 196,884, the first
              coefficient of the j-function (Leech_Kissing's lattice)
    top       why 26
    bottom    closed strings, gravity, and the tachyon

Every number is computed by string_math.py, not quoted.

    python generate_string_tower.py [--out DIR]    -> String_Tower/  (~1 s)
"""
import argparse
import math
from pathlib import Path

import numpy as np

import string_kit as kit
import string_math as sm
from string_kit import GEO_CUBE, GEO_POINT, GEO_SPHERE

HERE = Path(__file__).resolve().parent
STEM = "String_Tower"

LEVELS = 13                 # N = 0 .. 12
RC = 12.0                   # radius of the HCS circle (world units)
CIRCLE_AT = (-8.0, -3.0)    # wall (right, up) of the circle's centre
BAR_UNIT = 1.15             # bar length per decade of states
BAR_W = 0.45
WIDTH = 64.0
LIFT = 30.0
LINE = 1.8

BG = (8, 9, 20)
RING = (200, 205, 235, 170)
INF = (255, 90, 90)
TACHYON = (120, 200, 255)
ORANGE, BLUE, GOLD = (255, 120, 40), (60, 150, 255), (255, 200, 60)

STORY = (
    "Why 26? A string vibrates in modes n = 1, 2, 3, ... across each of its D - 2",
    "transverse directions, and each mode keeps a zero-point energy. The sum",
    "1 + 2 + 3 + ... is regularized to zeta(-1) = -1/12, so the lowest state sits at -(D - 2)/24.",
    "One quantum of vibration lifts it by 1 and gives just D - 2 states: too few for a",
    "massive particle in D dimensions, so they must be massless. (D - 2)/24 = 1, so D = 26.",
)
NOTES = (
    "One HCS circle, mass^2 = N - 1 in units of 4/alpha' (s = 1): massless at 0 deg, the tachyon",
    "at -90 deg, and the infinite tower crowding toward 180 deg, where +/- infinity meet.",
    "Bar length = log10 of the states one side of the string has at level N.",
    "Closed strings pair a left- and a right-moving side: level 1 gives 24 x 24 = 576 =",
    "299 graviton + 276 B-field + 1 dilaton states. Gravity comes free. The tachyon is why this",
    "isn't our universe; superstrings remove it (10d_superstring_lab/).",
)


def level_color(N):
    """Warm ramp from yellow (N = 1) to red (N = 12)."""
    t = (N - 1) / (LEVELS - 2)
    return (255, int(round(220 - 170 * t)), int(round(90 - 60 * t)))


def bar(sc, bd, theta, r0, length, color, label, show_text=0):
    """A radial bar from radius r0 outward along angle theta (deg) in the
    board plane; its tip pin carries the label when show_text."""
    t = math.radians(theta)
    mid = r0 + length / 2
    sc.node(bd, pos=(mid * math.cos(t), mid * math.sin(t), 0.0), rot=(0, 0, theta),
            scale=(length / (2 * kit.CUBE_FACE), BAR_W / (2 * kit.CUBE_FACE),
                   BAR_W / (2 * kit.CUBE_FACE)),
            color=(*color, 255), geometry=GEO_CUBE, text=label)
    tip = r0 + length
    return sc.node(bd, pos=(tip * math.cos(t), tip * math.sin(t), 0.0), scale=0.22,
                   color=(*color, 255), geometry=GEO_SPHERE, show_text=show_text,
                   text=label)


def build(out_dir):
    counts = sm.check()[:LEVELS]
    sc = kit.Scene()
    turn, wall = kit.frames_of_reference(sc, BG, LIFT)
    for side in (-1, 1):
        sc.node(wall, pos=(0.0, side * WIDTH / 2, 0.0), hide=1, geometry=GEO_POINT,
                text=f"framing anchor ({'left' if side < 0 else 'right'} edge of the opening view)")

    # ---- the HCS circle ----
    cb = kit.board(sc, wall, (0.0, *CIRCLE_AT), label="HCS circle board")
    kit.polyline(sc, cb, RC * kit.unit_circle(181), RING,
                 "the HCS circle for mass^2: s = 1 lands at 90 deg, +/- infinity at 180 deg",
                 ratio=0.08)
    ticks = ((0.0, "M^2 = 0: massless", (235, 235, 245)),
             (90.0, "M^2 = +1", (235, 235, 245)),
             (-90.0, "M^2 = -1", (235, 235, 245)))
    for th, lbl, c in ticks:
        t = math.radians(th)
        sc.node(cb, pos=(RC * math.cos(t), RC * math.sin(t), 0.0), scale=0.3, color=(*c, 255),
                text=f"HCS tick at {th:.0f} deg: {lbl}")
    sc.node(cb, pos=(-RC, 0.0, 0.0), scale=0.5, color=(*INF, 255), show_text=1,
            text="M^2 = infinity (180 deg)")

    # Level 0: the tachyon, one state, no bar (log10 1 = 0).
    th0 = float(kit.hcs_angle(sm.mass2(0), 1.0))
    sc.node(cb, pos=(RC * math.cos(math.radians(th0)), RC * math.sin(math.radians(th0)), 0.0),
            scale=0.55, color=(*TACHYON, 255), show_text=1,
            text="level 0: the tachyon, M^2 = -1 -- 1 state, an unstable vacuum")
    pinned = {1: "level 1: massless, 24 states",
              2: "level 2: M^2 = 1, 324 states = 25 x 26 / 2 - 1, one massive spin-2 in 26-D",
              6: "level 6: 1,073,720 states",
              12: f"level 12: {counts[12]:,} states"}
    for N in range(1, LEVELS):
        th = float(kit.hcs_angle(sm.mass2(N), 1.0))
        L = BAR_UNIT * math.log10(counts[N])
        label = pinned.get(N, f"level {N}: M^2 = {N - 1}, {counts[N]:,} states")
        bar(sc, cb, th, RC, L, level_color(N), label, show_text=int(N in pinned))

    # ---- right: Moonshine ----
    rb = kit.board(sc, wall, (0.0, 0.5 * WIDTH - 13.0, 6.0), label="Moonshine board")
    unit = 9.0 / 196884                      # bar height per state
    kit.caption(sc, rb, (0.0, 2.2), "Level 2 of a string curled up on the Leech lattice",
                color=kit.TITLE, size=0.3)
    h1, h2 = 324 * unit, 196560 * unit
    for y0, h, c, lbl in ((0.0, h1, ORANGE, "324 vibration states (the bar is that thin)"),
                          (h1, h2, BLUE, "196,560 Leech kissing vectors (Leech_Kissing)")):
        sc.node(rb, pos=(0.0, -12.0 + y0 + h / 2, 0.0),
                scale=(1.2 / (2 * kit.CUBE_FACE), max(h, 1e-3) / (2 * kit.CUBE_FACE),
                       0.4 / (2 * kit.CUBE_FACE)),
                color=(*c, 255), geometry=GEO_CUBE, text=lbl)
    sc.node(rb, pos=(0.0, -12.0 + h1 + h2, 0.0),
            scale=(1.8 / (2 * kit.CUBE_FACE), 0.12 / (2 * kit.CUBE_FACE), 0.5 / (2 * kit.CUBE_FACE)),
            color=(*GOLD, 255), geometry=GEO_CUBE, text="total: 196,884 states at level 2")
    rows = (("324 + 196,560 = 196,884", kit.TITLE),
            ("= 1 + 196,883, the Monster group's", None),
            ("smallest representation:", None),
            ("j(q) = 1/q + 744 + 196,884 q + ...", None),
            ("This coincidence started Monstrous Moonshine;", None),
            ("Borcherds proved it (1992) with this 26-D string.", None),
            ("orange: 324 vibration states", ORANGE),
            ("blue: 196,560 lattice vectors", BLUE))
    for i, (t, c) in enumerate(rows):
        kit.caption(sc, rb, (2.2, -1.0 - LINE * i), t, color=c or kit.CAPTION, size=0.25)

    # ---- top: why 26 ----
    tb = kit.board(sc, wall, (0.0, -0.5 * WIDTH, 30.0), label="story board")
    kit.caption(sc, tb, (0.0, 0.0), "The String Tower: why 26 dimensions, and infinitely many states",
                color=kit.TITLE, size=0.3)
    for i, t in enumerate(STORY):
        kit.caption(sc, tb, (0.0, -LINE * (i + 1.5)), t, size=0.2)

    # ---- bottom: reading the circle ----
    bb = kit.board(sc, wall, (0.0, -0.5 * WIDTH, -19.0), label="notes board")
    for i, t in enumerate(NOTES):
        kit.caption(sc, bb, (0.0, -LINE * (i + (1 if i >= 3 else 0))), t, size=0.2)

    sc.write(out_dir, STEM)
    return sc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / STEM))
    args = ap.parse_args()
    sc = build(args.out)
    print(f"{STEM}: {len(sc.rows)} nodes -> {args.out}")


if __name__ == "__main__":
    main()
