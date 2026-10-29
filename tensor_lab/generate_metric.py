"""
Scene 5 -- Slanted Rulers: upper and lower indices, and the metric tensor.

Scene 1 had two pictures of a component: walk along the axes (the legs) or
drop a perpendicular onto them (the shadows). In an orthonormal basis they
give the same numbers. Let the basis stretch and slant, as a real crystal's
lattice vectors do, and they come apart:

    v^i   (upper index) counts steps: v = v^1 e1 + v^2 e2. A longer ruler
          needs FEWER steps, so v^i scales against the basis: contravariant.
    v_i   (lower index) is a shadow: v_i = v . e_i. A longer ruler gives a
          BIGGER dot product, so v_i scales with the basis: covariant.

The metric tensor g_ij = e_i . e_j (every dot product between rulers) is
what connects them: v_i = g_ij v^j, and the length |v|^2 = v^i v_i.

    Act 1  0-15 s     a square lattice: legs and shadows agree, g = identity
    Act 2  15-35 s    stretch e1 to twice its length: v^1 halves, v_1 doubles
    Act 3  35-60 s    slant e2 toward e1: legs and shadows split apart
    Act 4  60-82 s    the basis wanders; g turns v^j into v_i, piece by
                      piece, and v^i v_i holds while (v^1)^2 + (v^2)^2 drifts
    Act 5  82-102 s   the dual basis e^i (e^i . e_j = 1 or 0): walking v_i
                      steps along it also reaches v. In a crystal it is the
                      reciprocal lattice, where X-ray diffraction spots sit.

    python generate_metric.py [--out DIR]
"""
import argparse
import math
import os

import numpy as np

import tensor_kit as kit

HERE = os.path.dirname(os.path.abspath(__file__))

V = np.array([1.5, 1.1])                  # the vector, fixed, in lab units
S = 3.0                                   # world units per lab unit
FRAMES = 3060
ACT1 = (0, 450)
ACT2 = (450, 1050)
STRETCH = (510, 750)
UNSTRETCH = (900, 1050)
ACT3 = (1050, 1800)
SLANT = (1110, 1410)
ACT4 = (1800, 2460)
ACT5 = (2460, FRAMES)
DUAL_ON = 2520
LIFT = 9.0
STAGE_AT = (0.0, -10.0, 0.0)
BOARD_AT = (0.0, -19.0, 12.0)
BG = (10, 14, 18)
LAT = range(-2, 4)                        # lattice steps along each ruler

BX0, BY0, BUNIT = 21.5, -9.4, 1.0         # index bars
GX0, GY0, GW, GH, GUNIT = 35.0, -6.8, 2.4, 3.4, 0.6    # g_ij
WX0, WY0 = 21.5, -16.8                    # v_i = g_ij v^j waterfalls
IX0, IY0, IUNIT = 35.0, -18.0, 0.8        # the two "lengths"

ATOM = (150, 170, 190)
GEO_CROSS = 25
DUAL = ((255, 120, 200), (120, 230, 230))   # e^1, e^2: magenta, cyan
DUAL_LIGHT = ((255, 175, 225), (175, 245, 245))


def basis_at(k):
    """Columns e1, e2 (lab units) at frame k: a 2 x 2 matrix."""
    L1, L2, th1, th2 = 1.0, 1.0, 0.0, 90.0
    if k >= STRETCH[0]:
        L1 = 1.0 + float(kit.ease((k - STRETCH[0]) / (STRETCH[1] - STRETCH[0])))
    if k >= UNSTRETCH[0]:
        L1 = 2.0 - float(kit.ease((k - UNSTRETCH[0]) / (UNSTRETCH[1] - UNSTRETCH[0])))
    if k >= SLANT[0]:
        th2 = 90.0 - 40.0 * float(kit.ease((k - SLANT[0]) / (SLANT[1] - SLANT[0])))
    if k >= ACT4[0]:
        u = min((k - ACT4[0]) / (ACT4[1] - 60 - ACT4[0]), 1.0)
        w = math.sin(math.pi * u) ** 2                # 0 at both ends of the wander
        L1 = 1.0 + 0.45 * w * (1 + math.sin(2 * math.pi * u)) / 2 + 0.25 * w
        L2 = 1.0 + 0.35 * w * math.sin(4 * math.pi * u) ** 2
        th1 = 12.0 * w * math.sin(2 * math.pi * u)
        th2 = 50.0 + 25.0 * w * math.sin(3 * math.pi * u) ** 2 + th1
    if k >= ACT4[1] - 60:
        u = min(max((k - (ACT4[1] - 60)) / 60.0, 0.0), 1.0)
        L1 = 1.0 + 0.6 * float(kit.ease(u))
        L2, th1, th2 = 1.0, 0.0, 50.0
    a1, a2 = math.radians(th1), math.radians(th2)
    return np.array([[L1 * math.cos(a1), L2 * math.cos(a2)],
                     [L1 * math.sin(a1), L2 * math.sin(a2)]])


def timeline():
    """Per frame: basis Eb (F,2,2) with columns e_i; v^i, v_i, g_ij; and
    the dual basis Db (F,2,2) with columns e^i."""
    Eb = np.array([basis_at(k) for k in range(FRAMES)])
    up = np.linalg.solve(Eb, np.broadcast_to(V, (FRAMES, 2))[..., None])[..., 0]
    g = np.einsum("fki,fkj->fij", Eb, Eb)
    low = np.einsum("fki,k->fi", Eb, V)
    Db = np.linalg.inv(Eb).transpose(0, 2, 1)
    return Eb, up, low, g, Db


def lab3(xy):
    """Lab-plane points (..., 2) -> 3-D board-like coords, world units."""
    xy = np.asarray(xy, float) * S
    return np.concatenate([xy, np.zeros(xy.shape[:-1] + (1,))], axis=-1)


def build(out_dir):
    sc = kit.Scene(FRAMES, dedupe=True)
    F = FRAMES
    Eb, up, low, g, Db = timeline()
    turn, wall = kit.frames_of_reference(sc, BG, LIFT)
    bd = kit.board(sc, wall, BOARD_AT)
    lab = kit.board(sc, wall, (0.0, STAGE_AT[1], 0.0), label="lab plane")
    act45 = kit.window(F, ACT4[0], F)
    act5 = kit.window(F, DUAL_ON, F)

    # ---- the lattice: atoms at m e1 + n e2, joined along both rulers ----
    ids = {}
    for m in LAT:
        for n in LAT:
            P = lab3(Eb[:, :, 0] * m + Eb[:, :, 1] * n)
            ids[m, n] = sc.node(lab, pos=np.round(P[0], 2), scale=0.12, color=(*ATOM, 255),
                                geometry=kit.GEO_SPHERE, ch=kit.pos_channel(sc, P, dp=2),
                                text=f"lattice point {m} e1 + {n} e2")
    lo, hi = LAT[0], LAT[-1]
    for m in LAT:
        kit.rod(sc, ids[m, lo], ids[m, hi], (*kit.E_RGB[1], 70 if m else 150),
                f"lattice line along e2 at {m} steps of e1" + (": the e2 axis" if m == 0 else ""),
                radius=0.02 if m else 0.035, geometry=27)
    for n in LAT:
        kit.rod(sc, ids[lo, n], ids[hi, n], (*kit.E_RGB[0], 70 if n else 150),
                f"lattice line along e1 at {n} steps of e2" + (": the e1 axis" if n == 0 else ""),
                radius=0.02 if n else 0.035, geometry=27)

    # ---- the rulers e1, e2 and the vector v ----
    for i in range(2):
        kit.arrow(sc, lab, np.zeros(3), lab3(Eb[:, :, i]) + [0, 0, 0.05],
                  (*kit.E_RGB[i], 255), f"e{i + 1}", radius=0.08, head=0.5, show_text=1)
    kit.arrow(sc, lab, np.zeros(3), lab3(V) + [0, 0, 0.1], (*kit.GOLD, 255), "v",
              radius=0.1, head=0.6, show_text=1)

    # ---- legs: walk v^1 along e1, then v^2 along e2 ----
    c1 = lab3(up[:, :1] * Eb[:, :, 0]) + [0, 0, 0.15]
    kit.arrow(sc, lab, np.zeros(3) + [0, 0, 0.15], c1, (*kit.E_LIGHT[0], 235),
              "leg 1: v^1 e1 (v^1 steps of e1)", radius=0.06, head=0.35)
    kit.arrow(sc, lab, c1, lab3(V) + [0, 0, 0.15], (*kit.E_LIGHT[1], 235),
              "leg 2: v^2 e2 (v^2 steps of e2)", radius=0.06, head=0.35)

    # ---- shadows: perpendicular drops onto each ruler's line ----
    tip = sc.node(lab, pos=lab3(V) + [0, 0, 0.2], hide=1, geometry=kit.GEO_POINT,
                  text="v's tip")
    for i in range(2):
        e = Eb[:, :, i]
        eh = e / np.linalg.norm(e, axis=1)[:, None]
        foot = lab3((eh @ V)[:, None] * eh) + [0, 0, 0.2]
        fid = kit.marker(sc, lab, foot[0], (*kit.E_RGB[i], 255),
                         f"foot of v's shadow on the e{i + 1} line: v_{i + 1} = v . e{i + 1} = "
                         f"(this length) x |e{i + 1}|", scale=0.13,
                         ch=kit.pos_channel(sc, foot))
        kit.rod(sc, tip, fid, (220, 220, 235, 170),
                f"drop line from v onto the e{i + 1} line (meets it at a right angle)",
                radius=0.035, geometry=27)

    # ---- Act 5: the dual basis, its legs, the reciprocal lattice ----
    ch5 = kit.hide_channel(sc, act5)
    for i in range(2):
        kit.arrow(sc, lab, np.zeros(3), lab3(Db[:, :, i]) + [0, 0, 0.25], (*DUAL[i], 255),
                  f"e^{i + 1} (dual)", radius=0.07, head=0.45, ch_visible=act5, show_text=1)
    d1 = lab3(low[:, :1] * Db[:, :, 0]) + [0, 0, 0.3]
    kit.arrow(sc, lab, np.zeros(3) + [0, 0, 0.3], d1, (*DUAL_LIGHT[0], 235),
              "dual leg 1: v_1 e^1 (v_1 steps of e^1)", radius=0.05, head=0.3, ch_visible=act5)
    kit.arrow(sc, lab, d1, lab3(V) + [0, 0, 0.3], (*DUAL_LIGHT[1], 235),
              "dual leg 2: v_2 e^2 (v_2 steps of e^2)", radius=0.05, head=0.3, ch_visible=act5)
    Dh = Db[DUAL_ON]
    for m in LAT:
        for n in LAT:
            if m == n == 0:
                continue
            p = lab3(Dh[:, 0] * m + Dh[:, 1] * n)
            if np.abs(p[:2]).max() > 3.6 * S:
                continue
            sc.node(lab, pos=p + [0, 0, -0.1], scale=0.09, color=(*DUAL_LIGHT[0], 230),
                    geometry=GEO_CROSS, ch=ch5, hide=1,
                    text=f"reciprocal-lattice point {m} e^1 + {n} e^2 (where a diffraction spot falls)")

    # ---- board: captions ----
    kit.caption(sc, bd, (0, 0), "SLANTED RULERS: upper and lower indices, and the metric",
                color=(255, 225, 120), size=0.09)
    acts = (
        (ACT1[0], ACT1[1], ("Act 1. A square lattice, rulers of length 1. Two ways to get components: walk the legs",
                            "(v = v^1 e1 + v^2 e2) or drop shadows (v_i = v . e_i). Here they agree, as in Scene 1.")),
        (ACT2[0], ACT2[1], ("Act 2. Stretch e1 to twice its length. You need HALF as many e1 steps: v^1 halves (contravariant).",
                            "But v . e1 DOUBLES: v_1 doubles (covariant). Same arrow; the two kinds of component part ways.")),
        (ACT3[0], ACT3[1], ("Act 3. Slant e2 toward e1 (both rulers length 1 again). The legs walk the slanted grid; the",
                            "shadows still drop at right angles. Now v^i and v_i differ even with unit rulers.")),
        (ACT4[0], ACT4[1], ("Act 4. The metric g_ij = e_i . e_j (every dot product between rulers) converts one to the other:",
                            "v_i = g_i1 v^1 + g_i2 v^2. And length needs one of each: |v|^2 = v^1 v_1 + v^2 v_2, in every basis.")),
        (ACT5[0], F, ("Act 5. The dual basis e^i: e^1 is at right angles to e2, with e^1 . e1 = 1. Walk v_1 steps of e^1",
                      "and v_2 of e^2: you reach v again. In a crystal the dual lattice is the reciprocal lattice of X-ray diffraction.")),
    )
    for f0, f1, lines in acts:
        vis = kit.window(F, f0, f1)
        for j, line in enumerate(lines):
            kit.caption(sc, bd, (0.4, -1.0 - 0.85 * j), line, visible=vis)
    kit.caption(sc, bd, (0.4, -3.0),
                "Upper index: counts steps, scales against the ruler. Lower index: a dot product, "
                "scales with it.", color=(170, 175, 200))

    # ---- board: v^i and v_i side by side ----
    kit.caption(sc, bd, (BX0 - 0.6, BY0 + 4.6), "the two kinds of component",
                color=(190, 190, 210), size=0.04)
    for i in range(2):
        x = BX0 + 4.4 * i
        kit.signed_bar(sc, bd, x, BY0, up[:, i], kit.E_RGB[i],
                       f"v^{i + 1} (upper): how many steps of e{i + 1}", unit=BUNIT, width=0.75)
        kit.signed_bar(sc, bd, x + 1.6, BY0, low[:, i], kit.E_LIGHT[i],
                       f"v_{i + 1} (lower): v . e{i + 1}", unit=BUNIT, width=0.75)
        kit.hline(sc, bd, x - 0.6, x + 2.2, BY0, (110, 110, 130),
                  f"zero line, component {i + 1}", ratio=0.012)
        kit.caption(sc, bd, (x - 0.35, BY0 - 0.7), f"v^{i + 1}", color=kit.E_RGB[i], size=0.035)
        kit.caption(sc, bd, (x + 1.3, BY0 - 0.7), f"v_{i + 1}", color=kit.E_LIGHT[i], size=0.035)

    # ---- board: the metric g_ij ----
    kit.caption(sc, bd, (GX0 - 0.8, GY0 + 2.3), "metric g_ij = e_i . e_j", color=kit.GOLD,
                size=0.04)
    for i in range(2):
        y = GY0 - i * GH
        kit.hline(sc, bd, GX0 - 0.7, GX0 + GW + 0.7, y, (110, 110, 130),
                  f"zero line, g row {i + 1}", ratio=0.012)
        for j in range(2):
            kit.signed_bar(sc, bd, GX0 + j * GW, y, g[:, i, j], kit.GOLD,
                           f"g_{i + 1}{j + 1} = e{i + 1} . e{j + 1}"
                           + ("  (a ruler's length squared)" if i == j else "  (how slanted the pair is)"),
                           unit=GUNIT, width=0.7 if i == j else 0.5)
            kit.caption(sc, bd, (GX0 + j * GW - 0.3, y - 0.65), f"g{i + 1}{j + 1}",
                        color=(200, 190, 140), size=0.03)

    kit.caption(sc, bd, (GX0 - 0.8, GY0 - GH - 1.9),
                "relativity: one g_ij per point of spacetime",
                color=(170, 175, 200), size=0.03)

    # ---- board: v_i = g_i1 v^1 + g_i2 v^2, piece by piece (Acts 4-5) ----
    kit.caption(sc, bd, (WX0 - 0.6, WY0 + 3.6), "v_i = g_i1 v^1 + g_i2 v^2",
                color=(190, 190, 210), size=0.035, visible=act45)
    for i in range(2):
        x = WX0 + 4.4 * i
        kit.waterfall(sc, bd, x, WY0, g[:, i, :] * up, (kit.E_RGB[0], kit.E_RGB[1]),
                      [f"v_{i + 1} piece: g_{i + 1}{j + 1} v^{j + 1}" for j in range(2)],
                      f"v_{i + 1} rebuilt from the upper components by g",
                      unit=BUNIT, visible=act45)
        kit.signed_bar(sc, bd, x + 1.4, WY0, low[:, i], kit.E_LIGHT[i],
                       f"v_{i + 1} = v . e{i + 1}, for comparison", unit=BUNIT, width=0.5,
                       visible=act45)
        kit.polyline(sc, bd, [(x - 0.4, WY0, 0), (x + 1.8, WY0, 0)], (110, 110, 130, 200),
                     f"zero line, rebuilt v_{i + 1}", ratio=0.012,
                     ch=kit.hide_channel(sc, act45), hide=1)

    # ---- board: two candidate lengths (Acts 4-5) ----
    kit.caption(sc, bd, (IX0 - 0.8, IY0 + 4.6), "|v|^2: which formula holds still?",
                color=(190, 190, 210), size=0.035, visible=act45)
    kit.waterfall(sc, bd, IX0, IY0, up * low, (kit.E_RGB[0], kit.E_RGB[1]),
                  ["v^1 v_1: its share of |v|^2", "v^2 v_2: its share of |v|^2"],
                  "v^1 v_1 + v^2 v_2 = |v|^2: never moves", unit=IUNIT, dx=0.5, width=0.5,
                  visible=act45)
    kit.waterfall(sc, bd, IX0 + 3.4, IY0, up ** 2, ((150, 150, 165), (110, 110, 125)),
                  ["(v^1)^2", "(v^2)^2"], "(v^1)^2 + (v^2)^2: drifts (wrong in a slanted basis)",
                  unit=IUNIT, dx=0.5, width=0.5, visible=act45, total_color=(170, 170, 185))
    n2 = float(V @ V)
    kit.polyline(sc, bd, [(IX0 - 0.5, IY0 + IUNIT * n2, 0), (IX0 + 4.4, IY0 + IUNIT * n2, 0)],
                 (255, 225, 120, 150), f"|v|^2 = {n2:.2f}", ratio=0.015,
                 ch=kit.hide_channel(sc, act45), hide=1)
    kit.caption(sc, bd, (IX0 - 0.3, IY0 - 0.7), "v^i v_i", color=kit.GOLD, size=0.03,
                visible=act45)
    kit.caption(sc, bd, (IX0 + 3.2, IY0 - 0.7), "v^i v^i", color=(170, 170, 185), size=0.03,
                visible=act45)

    stem = "Slanted_Rulers"
    sc.write(out_dir, stem)
    inv = (up * low).sum(1)
    print(f"v^i v_i over the run: {inv.min():.12f} .. {inv.max():.12f} (|v|^2 = {n2})")
    print(f"(v^1)^2 + (v^2)^2 over Act 4: {(up[slice(*ACT4)] ** 2).sum(1).min():.3f} .. "
          f"{(up[slice(*ACT4)] ** 2).sum(1).max():.3f}; v^i > 0 always: {bool((up > 0).all())}")
    print(f"{len(sc.rows)} nodes, {len(sc.tracks)} tracks, {F} frames -> {out_dir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", default=os.path.join(HERE, "Slanted_Rulers"))
    build(ap.parse_args().out)
