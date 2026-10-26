"""
Scene 1 -- One Arrow, Many Shadows: what vector components are.

One fixed gold arrow v, and an orthonormal basis (red, green, blue) that
turns around it. The arrow never changes; its three components do, because a
component is a question asked OF the arrow BY a basis vector: "how far along
you does v reach?" (v_i = v . e_i).

    Act 1  0-11 s     the basis is the room's axes; v is rebuilt as
                      v1 e1 + v2 e2 + v3 e3, one leg at a time
    Act 2  11-36 s    the basis tours a closed loop of rotations: the legs,
                      drop lines and bars all change, the arrow does not,
                      and v1^2 + v2^2 + v3^2 never changes
    Act 3  38-63 s    the basis holds still and the ARROW turns the opposite
                      way: the component history repeats exactly. The
                      components only know the arrow RELATIVE to the basis.

The transformation law it shows: v'_i = sum_j R_ji v_j -- one rotation
matrix for the one index. That one R is what makes v a rank-1 tensor; Scene 2
is the step to two.

    python generate_vectors.py [--out DIR]
"""
import argparse
import os

import numpy as np

import tensor_kit as kit

HERE = os.path.dirname(os.path.abspath(__file__))

V0 = np.array([0.4, 1.5, 1.2])
S = 4.0                       # world units per math unit on the stage
FRAMES = 1980
ACT1 = (0, 330)
ACT2 = (330, 1080)
ACT3 = (1140, 1890)
GROW = ((60, 120), (120, 180), (180, 240))   # Act 1: the three legs, in turn
LIFT = 8.0
STAGE_AT = (0.0, -9.0, 0.0)
BOARD_AT = (0.0, -18.0, 11.0)
BG = (10, 12, 22)

BAR_UNIT = 1.6
BARS_X = (21.0, 22.4, 23.8)
BARS_Y = -8.3
STACK_X, STACK_UNIT = 26.4, 0.8
HIST_X0, HIST_W, HIST_Y, HIST_UNIT = 20.0, 16.0, -16.3, 1.0
NAMES = ("v1", "v2", "v3")


def timeline():
    """Per frame: basis R (F, 3, 3), arrow v (F, 3), leg growth g (F, 3)."""
    F = FRAMES
    Rs = np.repeat(np.eye(3)[None], F, axis=0)
    vs = np.repeat(V0[None], F, axis=0)
    g = np.ones((F, 3))
    f = np.arange(F)
    for i, (a, b) in enumerate(GROW):
        g[:, i] = kit.ease((f - a) / (b - a))
    for k in range(*ACT2):
        Rs[k] = kit.tour(kit.ease((k - ACT2[0]) / (ACT2[1] - ACT2[0])))
    for k in range(*ACT3):
        Rk = kit.tour(kit.ease((k - ACT3[0]) / (ACT3[1] - ACT3[0])))
        vs[k] = Rk.T @ V0
    comps = np.einsum("fji,fj->fi", Rs, vs)      # c_i = e_i . v = (R^T v)_i
    return Rs, vs, g, comps


def build(out_dir):
    sc = kit.Scene(FRAMES)
    Rs, vs, g, comps = timeline()
    F = FRAMES
    turn, wall = kit.frames_of_reference(sc, BG, LIFT)
    st = kit.stage(sc, turn, STAGE_AT)
    bd = kit.board(sc, wall, BOARD_AT)

    # ---- the room: faint fixed axes ----
    for i, name in enumerate("xyz"):
        a = np.zeros(3)
        a[i] = 2.4 * S
        kit.polyline(sc, st, [-a * 0.35, a], (*kit.GREY, 110),
                     f"room {name} axis (fixed): the reference the basis turns against",
                     ratio=0.02)

    # ---- the basis: one frame node turned by R(t); everything in it rides along ----
    basis = sc.node(st, hide=1, geometry=kit.GEO_POINT, ch=kit.rot_channel(sc, Rs),
                    text="the basis frame: turned by R(t), so its local axes ARE e1', e2', e3'")
    origin = sc.node(basis, hide=1, geometry=kit.GEO_POINT, text="origin (the common tail)")
    for i in range(3):
        e = np.zeros(3)
        e[i] = 1.0
        kit.polyline(sc, basis, [-2.1 * S * e, 2.1 * S * e], (*kit.E_RGB[i], 90),
                     f"e{i + 1}' axis line: where the v{i + 1} shadow falls", ratio=0.025)
        kit.arrow(sc, basis, np.zeros(3), S * e, (*kit.E_RGB[i], 255),
                  f"e{i + 1}'", radius=0.07, head=0.55,
                  tail_node=origin, show_text=1)

    # ---- the vector itself: gold, in the stage frame ----
    kit.arrow(sc, st, np.zeros(3), vs * S, (*kit.GOLD, 255),
              "v", radius=0.1, head=0.8,
              show_text=1)

    # ---- the legs v1 e1 + v2 e2 + v3 e3, in basis coordinates ----
    c = comps * g                                  # Act 1 grows each leg in turn
    P = np.zeros((F, 4, 3))
    P[:, 1, 0] = c[:, 0]
    P[:, 2, :2] = c[:, :2]
    P[:, 3] = c
    P *= S
    for i in range(3):
        visible = (g[:, i] > 1e-6).astype(float)
        kit.arrow(sc, basis, P[:, i], P[:, i + 1], (*kit.E_LIGHT[i], 235),
                  f"leg {i + 1}: v{i + 1} e{i + 1}'  (walk v{i + 1} along e{i + 1}')",
                  radius=0.055, head=0.4, ch_visible=visible)

    # ---- the shadows: drop lines from v's tip to each axis, and the feet ----
    tip = sc.node(basis, pos=comps[0] * S, hide=1, geometry=kit.GEO_POINT,
                  ch=kit.pos_channel(sc, comps * S), text="v's tip, in basis coordinates")
    shadows = kit.window(F, GROW[2][1], F)
    for i in range(3):
        foot = np.zeros((F, 3))
        foot[:, i] = comps[:, i] * S
        fid = kit.marker(sc, basis, foot[0], (*kit.E_RGB[i], 255),
                         f"shadow of v on e{i + 1}': v{i + 1} = v . e{i + 1}'", scale=0.14,
                         ch=kit.pos_channel(sc, foot, extra=[(sc.track(1 - shadows), "hide")]),
                         hide=1)
        kit.rod(sc, tip, fid, (200, 200, 215, 150),
                f"drop line from v's tip to e{i + 1}': meets it at a right angle",
                radius=0.04, geometry=27, ch=kit.hide_channel(sc, shadows), hide=1)

    # ---- board: captions ----
    kit.caption(sc, bd, (0, 0), "ONE ARROW, MANY SHADOWS: what vector components are",
                color=(255, 225, 120), size=0.09)
    acts = (
        (ACT1[0], ACT1[1], ("Act 1. A basis is three perpendicular unit arrows. v = v1 e1 + v2 e2 + v3 e3:",
                            "walk v1 along e1, then v2 along e2, then v3 along e3, and you arrive at v's tip.")),
        (ACT2[0], ACT2[1] + 60, ("Act 2. Turn the basis. The gold arrow never moves, but every component changes:",
                                 "v_i = v . e_i is a shadow, and the shadow depends on where you shine from.")),
        (ACT3[0], F, ("Act 3. Now hold the basis and turn the ARROW the opposite way.",
                      "The bars and the history replay Act 2 exactly: components only know v RELATIVE to the basis.")),
    )
    for f0, f1, lines in acts:
        vis = kit.window(F, f0, f1)
        for j, line in enumerate(lines):
            kit.caption(sc, bd, (0.4, -1.0 - 0.85 * j), line, visible=vis)
    kit.caption(sc, bd, (0.4, -3.0),
                "Transformation law: v'_i = R_ji v_j, summed over j. One rotation matrix for one index: "
                "that is what makes v rank 1.", color=(170, 175, 200))

    # ---- board: component bars ----
    kit.hline(sc, bd, BARS_X[0] - 0.8, BARS_X[2] + 0.8, BARS_Y, (200, 200, 220),
              "zero line for the component bars")
    vlen = float(np.linalg.norm(V0))
    for sgn in (1, -1):
        kit.hline(sc, bd, BARS_X[0] - 0.8, BARS_X[2] + 0.8, BARS_Y + sgn * BAR_UNIT * vlen,
                  (120, 120, 140), f"{'+' if sgn > 0 else '-'}|v| = {sgn * vlen:+.2f}: "
                  "no component can pass this", ratio=0.012)
    for i in range(3):
        kit.signed_bar(sc, bd, BARS_X[i], BARS_Y, comps[:, i], kit.E_RGB[i],
                       f"{NAMES[i]} = v . e{i + 1}'  (component {i + 1}, right now)",
                       unit=BAR_UNIT, width=0.7)
        kit.caption(sc, bd, (BARS_X[i] - 0.25, BARS_Y - BAR_UNIT * vlen - 0.55),
                    NAMES[i], color=kit.E_RGB[i], size=0.04)
    kit.caption(sc, bd, (BARS_X[0] - 0.8, BARS_Y + BAR_UNIT * vlen + 0.6),
                "components v_i = v . e_i", color=(190, 190, 210), size=0.04)

    # ---- board: |v|^2 as a stack that never changes height ----
    sq = comps ** 2
    base = np.zeros(F)
    for i in range(3):
        y0 = BARS_Y + STACK_UNIT * base
        y1 = y0 + STACK_UNIT * sq[:, i]
        h = y1 - y0
        on = h > 1e-9
        s = 0.8 / (2 * kit.CUBE_FACE)
        ch = sc.channel([(sc.track(0.5 * (y0 + y1)), "translate_y"),
                         (sc.track(h / (2 * kit.CUBE_FACE)), "scale_y"),
                         (sc.track(np.where(on, s, 0.0)), "scale_x"),
                         (sc.track(np.where(on, 0.25, 0.0)), "scale_z")])
        sc.node(bd, pos=(STACK_X, 0.5 * (y0[0] + y1[0]), 0.0),
                scale=(s, h[0] / (2 * kit.CUBE_FACE), 0.25) if on[0] else 0.0,
                color=(*kit.E_RGB[i], 255), geometry=kit.GEO_CUBE, ch=ch,
                text=f"{NAMES[i]}^2: its share of |v|^2 (the shares trade; the total cannot)")
        base = base + sq[:, i]
    top = BARS_Y + STACK_UNIT * vlen ** 2
    kit.hline(sc, bd, STACK_X - 0.7, STACK_X + 0.7, top, (255, 225, 120),
              f"|v|^2 = {vlen ** 2:.2f}: the same in every basis", ratio=0.03)
    kit.caption(sc, bd, (STACK_X + 0.9, top),
                f"sum of squares = |v|^2 = {vlen ** 2:.2f}, always",
                color=(255, 225, 120), size=0.04)

    # ---- board: component history, with a time cursor ----
    t = np.arange(F)
    xs = HIST_X0 + HIST_W * t / (F - 1)
    step = 6
    for i in range(3):
        pts = [(xs[k], HIST_Y + HIST_UNIT * comps[k, i], 0.0) for k in range(0, F, step)]
        kit.polyline(sc, bd, pts, (*kit.E_RGB[i], 230),
                     f"history of {NAMES[i]} over the whole run (left to right = time)", ratio=0.035)
    kit.hline(sc, bd, HIST_X0, HIST_X0 + HIST_W, HIST_Y, (110, 110, 130),
              "history zero line", ratio=0.012)
    for f0, f1, name in ((ACT1[0], ACT1[1], "Act 1"), (ACT2[0], ACT2[1], "Act 2: basis turns"),
                         (ACT3[0], ACT3[1], "Act 3: arrow turns")):
        x0 = HIST_X0 + HIST_W * f0 / (F - 1)
        kit.polyline(sc, bd, [(x0, HIST_Y - 2.3, 0), (x0, HIST_Y + 2.3, 0)], (90, 90, 110, 160),
                     f"{name} begins", ratio=0.012)
        kit.caption(sc, bd, (x0 + 0.1, HIST_Y + 2.6), name, color=(160, 160, 185), size=0.03)
    cursor_x = xs
    ch = sc.channel([(sc.track(cursor_x), "translate_x")])
    sc.node(bd, pos=(cursor_x[0], HIST_Y, 0.02), scale=(0.03, 4.4 / (2 * kit.CUBE_FACE), 0.03),
            color=(255, 255, 255, 200), geometry=kit.GEO_CUBE, ch=ch,
            text="now: the time cursor on the component history")
    kit.caption(sc, bd, (HIST_X0, HIST_Y - 2.9),
                "component history: Acts 2 and 3 trace the same curves", color=(190, 190, 210),
                size=0.04)

    stem = "Vectors_and_Bases"
    sc.write(out_dir, stem)
    n2 = (comps ** 2).sum(1)
    print(f"|v|^2 over the run: {n2.min():.12f} .. {n2.max():.12f}")
    a2 = comps[ACT2[0]:ACT2[1]]
    a3 = comps[ACT3[0]:ACT3[1]]
    print(f"Act 3 replays Act 2: worst component difference {np.abs(a2 - a3).max():.1e}")
    print(f"{len(sc.rows)} nodes, {len(sc.tracks)} tracks, {F} frames -> {out_dir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", default=os.path.join(HERE, "Vectors_and_Bases"))
    build(ap.parse_args().out)
