"""
Scene 4 -- Current Across the Grain: the conductivity tensor of a crystal.

Ohm's law for a wire is J = sigma E: the current density J runs along the
field E, sigma times as strong. A crystal is not a wire. Its atoms sit in
chains and layers, and charge moves easily along a chain, less easily
across one, and hardly at all between layers. Push with E and the current
leans toward the easy directions, so J is NOT parallel to E. Then the one
number sigma has to become a machine: J_i = sigma_ij E_j, a rank-2 tensor,
Scene 2's machine with a physical job.

    Act 1  0-28 s     a 2-D crystal (one sheet of chains). E along x gives a
                      J that leans toward the chains. Turn E all the way
                      round: J's tip draws an ellipse. 2 x 2 = 4 numbers.
    Act 2  28-63 s    the sheets stack into a 3-D crystal, with a third and
                      worst direction (between layers). E along x, then y,
                      then z: each experiment fills one COLUMN of the 3 x 3
                      grid. Then E along the crystal's own axes: J finally
                      follows E, 2.0, 0.6 and 0.25 times as strong.
    Act 3  64-92 s    a "hypercrystal": 3-D crystals stacked along a fourth
                      direction (drawn as its shadow). sigma becomes 4 x 4.
                      The rule J_i = sum_j sigma_ij E_j never changes; only
                      the count does: N^2 numbers, N(N+1)/2 independent.

The charges (small beads) drift along J, not along E, the whole way.
The conductivities are illustrative (a layered conductor such as graphite
has a far larger contrast, thousands to one).

    python generate_crystal.py [--out DIR]
"""
import argparse
import math
import os

import numpy as np

import tensor_kit as kit

HERE = os.path.dirname(os.path.abspath(__file__))

SIG = np.array([2.0, 0.6, 0.25])          # along chains, across chains, between layers
SIG4 = np.array([2.0, 0.6, 0.25, 1.1])    # the hypercrystal's four
Q1 = kit.rot_z(30.0)                      # Act 1: the sheet, chains 30 deg above x
Q3 = kit.rot_y(25.0) @ kit.rot_x(-20.0) @ kit.rot_z(30.0)   # Act 2: the crystal tilted
_rng4 = np.random.default_rng(4)
Q4, _ = np.linalg.qr(_rng4.normal(size=(4, 4)))
SIGMA4 = Q4 @ np.diag(SIG4) @ Q4.T

S = 3.0                                   # world units per unit of E or J
FRAMES = 2760
ACT1 = (0, 840)
SWEEP = (120, 720)                        # Act 1: E turns once
ACT2 = (840, 1890)
SWING = (840, 990)                        # the sheet lies down, the layers stack
EXPTS = ((990, 1110), (1140, 1260), (1290, 1410))       # E along x, y, z
PRINC = ((1440, 1560), (1590, 1710), (1740, 1860))      # E along the crystal's axes
ACT3 = (1920, 2700)
HYPER_ON = 1890
LIFT = 9.0
STAGE_AT = (0.0, -10.0, 0.0)
BOARD_AT = (0.0, -19.0, 12.0)
BG = (12, 10, 20)

A, B, C = 1.1, 1.5, 1.2                   # lattice spacings: along, across, between layers
NI, NJ, NK = 9, 7, 4
HALF = np.array([A * (NI - 1) / 2, B * (NJ - 1) / 2, C * (NK - 1) / 2])
N_Q = 40
HYP = 2.5                                 # the 4-D lattice spacing
DRIFT = 0.9                               # world units per second per unit of J

MX0, MY0, CW, CH, MUNIT = 24.0, -6.4, 2.6, 2.9, 0.95    # the sigma grid
JX = MX0 - 5.0                                          # J's waterfall column
EX_OFF = 1.8                                            # E's column, right of the grid
GAUGE_X, GAUGE_Y = JX, MY0 - 3 * CH - 1.4
LADDER_X0, LADDER_Y = 21.0, -21.0

E_IN = (235, 235, 245)
J_OUT = (255, 160, 70)
ATOM = (150, 165, 190)
CHAIN = (215, 150, 95)
QBEAD = (255, 215, 150)
AX_COL = (kit.E_RGB[0], kit.E_RGB[1], kit.E_RGB[2], (190, 110, 255))
AX_NAME = ("x", "y", "z", "w")


def geodesic(a, b, u):
    """Unit vector a -> b along the great circle, u in 0..1."""
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    th = math.acos(float(np.clip(a @ b, -1, 1)))
    if th < 1e-9:
        return a.copy()
    return (math.sin((1 - u) * th) * a + math.sin(u * th) * b) / math.sin(th)


def face_rotation():
    """The lab frame facing the viewer (x right, y up, z out), in turn coords:
    the board's orientation (see tensor_kit.board)."""
    return kit.rot_y(-25.0) @ kit.rot_z(90.0) @ kit.rot_x(90.0)


def stage_rotation():
    return kit.rot_z(kit.STAGE_TURN)


def timeline():
    """Per frame: lab frame M (turn coords), crystal Qc (lab coords), the
    field E (lab, unit), and the 4-D field E4."""
    F = FRAMES
    M = np.repeat(stage_rotation()[None], F, axis=0)
    Qc = np.repeat(Q3[None], F, axis=0)
    E = np.zeros((F, 3))
    for k in range(F):
        if k < SWING[0]:
            M[k] = face_rotation()
            Qc[k] = Q1
        elif k < SWING[1]:
            u = float(kit.ease((k - SWING[0]) / (SWING[1] - SWING[0])))
            M[k] = kit.slerp(face_rotation(), stage_rotation(), u)
            Qc[k] = kit.slerp(Q1, Q3, u)
    # Act 1: E along x, one full turn in the sheet, back to x.
    for k in range(SWING[1]):
        u = float(kit.ease((k - SWEEP[0]) / (SWEEP[1] - SWEEP[0])))
        E[k] = (math.cos(2 * math.pi * u), math.sin(2 * math.pi * u), 0.0)
    # Act 2: x, y, z, then the crystal's own axes, with 1 s great-circle moves.
    stops = [np.eye(3)[0], np.eye(3)[1], np.eye(3)[2]]
    for i in range(3):
        a = Q3[:, i] * (1 if Q3[:, i] @ stops[-1] >= 0 else -1)
        stops.append(a)
    holds = EXPTS + PRINC
    for k in range(SWING[1], F):
        for s, (h0, h1) in enumerate(holds):
            if k < h0:
                u = float(kit.ease((k - holds[s - 1][1]) / (h0 - holds[s - 1][1])))
                E[k] = geodesic(stops[s - 1], stops[s], u)
                break
            if k < h1:
                E[k] = stops[s]
                break
        else:
            E[k] = stops[-1]
    E4 = np.zeros((F, 4))
    for k in range(F):
        u = min(max((k - ACT3[0]) / (ACT3[1] - ACT3[0]), 0.0), 1.0)
        a, c = 2 * math.pi * u, 4 * math.pi * u
        b = math.pi / 4 + 0.35 * math.sin(2 * math.pi * u)
        E4[k] = (math.cos(a) * math.cos(b), math.sin(a) * math.cos(b),
                 math.cos(c) * math.sin(b), math.sin(c) * math.sin(b))
    return M, Qc, E, E4


def sigma_lab(Qc):
    """sigma's components in the lab basis: Qc diag(SIG) Qc^T, per frame."""
    return np.einsum("fik,k,fjk->fij", Qc, SIG, Qc)


def charges(Qc, J):
    """Bead positions in CRYSTAL coords: each drifts with J (seen from the
    crystal) and wraps around the crystal's box. In Act 1 they sit just in
    front of the sheet; the swing spreads them through the layers."""
    F = FRAMES
    rng = np.random.default_rng(7)
    p = np.column_stack([rng.uniform(-HALF[0], HALF[0], N_Q),
                         rng.uniform(-HALF[1], HALF[1], N_Q),
                         np.zeros(N_Q)])
    z_target = rng.uniform(-HALF[2] - 0.4, HALF[2] + 0.4, N_Q)
    out = np.zeros((F, N_Q, 3))
    box = 2 * HALF + np.array([A, B, 0.8])
    for k in range(F):
        v = Qc[k].T @ J[k] * DRIFT / 30.0
        p = p + v
        p[:, :2] = (p[:, :2] + box[:2] / 2) % box[:2] - box[:2] / 2
        p[:, 2] = (p[:, 2] + box[2] / 2) % box[2] - box[2] / 2 if k >= SWING[0] else 0.0
        w = float(kit.ease((k - SWING[0]) / (SWING[1] - SWING[0])))
        out[k] = p
        z = (z_target + p[:, 2] + box[2] / 2) % box[2] - box[2] / 2
        out[k, :, 2] = (1 - w) * 0.35 + w * z
    return out


def hyper_projection(k):
    """The 4-D lattice's rotation at frame k; the shadow is its first 3 rows."""
    def plane(i, j, deg):
        R = np.eye(4)
        a = math.radians(deg)
        R[i, i] = R[j, j] = math.cos(a)
        R[i, j], R[j, i] = -math.sin(a), math.sin(a)
        return R
    u = min(max((k - ACT3[0]) / (ACT3[1] - ACT3[0]), 0.0), 1.0)
    P0 = plane(0, 3, 28.0) @ plane(2, 3, 22.0) @ plane(1, 3, 12.0)
    return plane(0, 3, 360.0 * u) @ plane(1, 2, 120.0 * u) @ plane(1, 3, 180.0 * u) @ P0


def build(out_dir):
    sc = kit.Scene(FRAMES, dedupe=True)
    F = FRAMES
    M, Qc, E, E4 = timeline()
    Sg = sigma_lab(Qc)
    J = np.einsum("fij,fj->fi", Sg, E)
    J4 = E4 @ SIGMA4.T
    act1 = kit.window(F, *ACT1)
    act12 = kit.window(F, 0, HYPER_ON)
    act2 = kit.window(F, ACT2[0], HYPER_ON)
    act3 = kit.window(F, HYPER_ON, F)

    turn, wall = kit.frames_of_reference(sc, BG, LIFT)
    bd = kit.board(sc, wall, BOARD_AT)
    lab = sc.node(turn, pos=STAGE_AT, rot=kit.euler_xyz(M[0]), hide=1, geometry=kit.GEO_POINT,
                  ch=kit.rot_channel(sc, M),
                  text="lab frame: faces you in Act 1 (x right, y up), then lies down "
                       "(x toward you, y right, z up)")

    # ---- the lab's axes: where E and J are measured ----
    for i in range(3):
        a = np.zeros(3)
        a[i] = 2.3 * S
        kit.polyline(sc, lab, [-a * 0.25, a], (*kit.E_RGB[i], 120),
                     f"lab {AX_NAME[i]} axis: E and J are measured along it", ratio=0.022,
                     ch=kit.hide_channel(sc, act2 if i == 2 else act12), hide=int(i == 2))

    # ---- the crystal: layers of atoms, chains along its own x ----
    cry = sc.node(lab, rot=kit.euler_xyz(Qc[0]), hide=1, geometry=kit.GEO_POINT,
                  ch=kit.rot_channel(sc, Qc),
                  text="crystal frame: x = along the chains, y = across, z = between layers")
    layers = []
    for k in range(NK):
        z_end = (k - (NK - 1) / 2) * C
        rise = np.array([z_end * float(kit.ease((f - SWING[0]) / (SWING[1] - SWING[0])))
                         for f in range(F)])
        vis = act1 * (k == 0) + act2
        lay = sc.node(cry, hide=1, geometry=kit.GEO_POINT,
                      ch=sc.channel([(sc.track(rise), "translate_z")]),
                      text=f"layer {k + 1} of the crystal" + (" (the 2-D sheet of Act 1)" if k == 0 else ""))
        ch_l = kit.hide_channel(sc, vis)
        hide0 = int(not vis[0])
        ids = {}
        for i in range(NI):
            for j in range(NJ):
                x, y = (i - (NI - 1) / 2) * A, (j - (NJ - 1) / 2) * B
                ids[i, j] = sc.node(lay, pos=(x, y, 0.0), scale=0.14, color=(*ATOM, 255),
                                    geometry=kit.GEO_SPHERE, ch=ch_l, hide=hide0,
                                    text=f"atom ({i + 1}, {j + 1}) of layer {k + 1}")
        for j in range(NJ):
            y = (j - (NJ - 1) / 2) * B
            kit.polyline(sc, lay, [(-HALF[0], y, 0), (HALF[0], y, 0)], (*CHAIN, 230),
                         f"chain {j + 1} of layer {k + 1}: the easy direction (sigma = {SIG[0]:g})",
                         ratio=0.06, ch=ch_l, hide=hide0)
        for i in range(NI):
            x = (i - (NI - 1) / 2) * A
            kit.polyline(sc, lay, [(x, -HALF[1], 0), (x, HALF[1], 0)], (*ATOM, 90),
                         f"cross bond line {i + 1} of layer {k + 1} (sigma = {SIG[1]:g} across chains)",
                         ratio=0.018, ch=ch_l, hide=hide0)
        layers.append((lay, ids))
    ch_up = kit.hide_channel(sc, act2)
    for k in range(NK - 1):
        for i in range(0, NI, 2):
            for j in range(0, NJ, 2):
                kit.rod(sc, layers[k][1][i, j], layers[k + 1][1][i, j], (*ATOM, 70),
                        f"weak bond between layers {k + 1} and {k + 2} (sigma = {SIG[2]:g})",
                        radius=0.015, ch=ch_up, hide=1, geometry=27)

    # ---- the crystal's own axes, shown once E visits them ----
    vis_ax = kit.window(F, PRINC[0][0] - 30, HYPER_ON)
    ch_ax = kit.hide_channel(sc, vis_ax)
    for i, name in enumerate(("along the chains", "across the chains", "between layers")):
        a = np.zeros(3)
        a[i] = 2.3 * S
        kit.polyline(sc, cry, [-a, a], (*J_OUT, 150),
                     f"crystal axis {i + 1} ({name}): J = {SIG[i]:g} E here, parallel",
                     ratio=0.03, ch=ch_ax, hide=1)

    # ---- the charges: drifting along J ----
    P = charges(Qc, J)
    hide_q = sc.track(1 - act12)
    for q in range(N_Q):
        sc.node(cry, pos=np.round(P[0, q], 2), scale=0.13, color=(*QBEAD, 255), geometry=kit.GEO_SPHERE,
                ch=kit.pos_channel(sc, P[:, q], dp=2, extra=[(hide_q, "hide")]),
                text=f"charge carrier {q + 1}: drifts along J, not E")

    # ---- E and J ----
    kit.arrow(sc, lab, np.zeros(3), E * S, (*E_IN, 255), "E (field)", radius=0.1,
              head=0.6, ch_visible=act12, show_text=1)
    kit.arrow(sc, lab, np.zeros(3), J * S, (*J_OUT, 255), "J (current)",
              radius=0.13, head=0.8, ch_visible=act12, show_text=1)
    f_on = np.arange(SWEEP[0], SWEEP[1] + 1, 3)
    kit.reveal(sc, lab, J[f_on] * S + [0, 0, 0.05], (*J_OUT, 200),
               "where J's tip has been as E turned: an ellipse", f_on, SWING[0],
               ratio=0.05, seg=8)
    kit.reveal(sc, lab, E[f_on] * S, (*E_IN, 110), "where E's tip has been: a circle",
               f_on, SWING[0], ratio=0.03, seg=8)

    # ---- the 4-D hypercrystal's shadow ----
    hyper = sc.node(lab, hide=1, geometry=kit.GEO_POINT,
                    text="the hypercrystal's 3-D shadow: its 4-D points with the 4th coordinate dropped")
    grid4 = np.array([(a, b, c, d) for a in (-1, 0, 1) for b in (-1, 0, 1)
                      for c in (-1, 0, 1) for d in (-1, 0, 1)], float) * HYP
    Ps = np.array([hyper_projection(k) for k in range(F)])
    pos4 = np.einsum("fij,nj->fni", Ps[:, :3, :], grid4)
    hide4 = sc.track(1 - act3)
    w_col = {-1: (110, 160, 255), 0: (215, 215, 230), 1: (255, 130, 200)}
    ids4 = {}
    for n, x in enumerate(grid4):
        key = tuple(int(round(v / HYP)) for v in x)
        ids4[key] = sc.node(hyper, pos=np.round(pos4[0, n], 2), scale=0.17, color=(*w_col[key[3]], 255),
                            geometry=kit.GEO_SPHERE, hide=1,
                            ch=kit.pos_channel(sc, pos4[:, n], dp=2, extra=[(hide4, "hide")]),
                            text=f"4-D atom (x, y, z, w) = {key}: w = {key[3]} sets its colour")
    ch_e4 = kit.hide_channel(sc, act3)
    for key, nid in ids4.items():
        for ax in range(4):
            if key[ax] < 1:
                nb = list(key)
                nb[ax] += 1
                col = (*AX_COL[3], 170) if ax == 3 else (150, 155, 180, 110)
                kit.rod(sc, nid, ids4[tuple(nb)], col,
                        f"4-D bond along {AX_NAME[ax]}" + (" (the 4th direction)" if ax == 3 else ""),
                        radius=0.02, ch=ch_e4, hide=1, geometry=27)

    # ---- board: captions ----
    kit.caption(sc, bd, (0, 0), "CURRENT ACROSS THE GRAIN: the conductivity tensor of a crystal",
                color=(255, 225, 120), size=0.09)
    acts = (
        (0, SWEEP[0] + 180, ("Act 1. A 2-D crystal: atoms in chains. Charge moves easily along a chain, poorly across one.",
                             "Push with a field E along x, and the current J leans toward the chains. J is not parallel to E.")),
        (SWEEP[0] + 180, SWING[0], ("Turn E all the way round. J's tip draws an ellipse, and J lines up with E only along the chains",
                                    "or straight across them. J_x needs E_y too: J = sigma E takes 2 x 2 = 4 numbers.")),
        (SWING[0], PRINC[0][0] - 30, ("Act 2. Stack the sheets into a 3-D crystal, with a third, worst direction: between layers.",
                                      "Measure sigma: E along x, then y, then z. Each time, J's x, y, z parts fill one COLUMN of the grid.")),
        (PRINC[0][0] - 30, HYPER_ON, ("Now point E along the crystal's own axes, and J finally follows E: 2.0, 0.6, 0.25 times as strong.",
                                      "3 conductivities + 3 angles for the tilt = 6 numbers. The grid's 9 repeat 3 of them: sigma_ij = sigma_ji.")),
        (HYPER_ON, F, ("Act 3. A 'hypercrystal': 3-D crystals stacked along a 4th direction (you see its shadow). sigma is 4 x 4.",
                       "Arrows can't be drawn in 4-D, but the rule still works: J_i = sigma_i1 E_1 + ... + sigma_i4 E_4.")),
    )
    for f0, f1, lines in acts:
        vis = kit.window(F, f0, f1)
        for j, line in enumerate(lines):
            kit.caption(sc, bd, (0.4, -1.0 - 0.85 * j), line, visible=vis)
    kit.caption(sc, bd, (0.4, -3.0),
                "Ohm's law, grown up: J_i = sigma_ij E_j, summed over j. Two indices, one for the push "
                "and one for the flow: sigma is a rank-2 tensor.", color=(170, 175, 200))

    # ---- board: J = sigma E as a matrix equation, one block per dimension ----
    blocks = ((2, Sg[:, :2, :2], E[:, :2], act1, "2-D: 4 numbers"),
              (3, Sg, E, act2, "3-D: 9 numbers"),
              (4, np.broadcast_to(SIGMA4, (F, 4, 4)), E4, act3, "4-D: 16 numbers"))
    for N, sig, e, vis, tag in blocks:
        ch_v = kit.hide_channel(sc, vis)
        hide0 = int(not vis[0])
        jv = np.einsum("fij,fj->fi", sig, e)
        kit.caption(sc, bd, (MX0 - 0.8, MY0 + 2.5), f"sigma_ij, {tag}", color=J_OUT, size=0.04,
                    visible=vis)
        kit.caption(sc, bd, (JX - 0.8, MY0 + 2.5), "J_i", color=J_OUT, size=0.04, visible=vis)
        kit.caption(sc, bd, (MX0 + N * CW + EX_OFF - 0.4, MY0 + 1.6), "E_j", color=E_IN,
                    size=0.04, visible=vis)
        kit.caption(sc, bd, (JX + 1.9, MY0 - 0.5 * (N - 1) * CH), "=", color=CAPTION_HI,
                    size=0.05, visible=vis)
        for j in range(N):
            kit.caption(sc, bd, (MX0 + j * CW - 0.35, MY0 + 1.6), f"E_{AX_NAME[j]}",
                        color=AX_COL[j], size=0.035, visible=vis)
        for i in range(N):
            y = MY0 - i * CH
            kit.polyline(sc, bd, [(MX0 - 0.8, y, 0), (MX0 + (N - 1) * CW + 0.8, y, 0)],
                         (110, 110, 130, 200), f"zero line, sigma row {i + 1} ({tag})",
                         ratio=0.012, ch=ch_v, hide=hide0)
            kit.polyline(sc, bd, [(JX - 0.4, y, 0), (JX + 0.6 + (N - 1) * 0.45, y, 0)],
                         (110, 110, 130, 200), f"zero line, J_{AX_NAME[i]} ({tag})",
                         ratio=0.012, ch=ch_v, hide=hide0)
            kit.caption(sc, bd, (JX - 1.6, y), f"J_{AX_NAME[i]}", color=AX_COL[i], size=0.035,
                        visible=vis)
            for j in range(N):
                vals = sig[:, i, j]
                label = (f"sigma_{AX_NAME[i]}{AX_NAME[j]} ({tag}): how much E_{AX_NAME[j]} "
                         f"drives J_{AX_NAME[i]}" + ("  (diagonal)" if i == j else ""))
                if np.ptp(vals) == 0:
                    kit.vspan(sc, bd, MX0 + j * CW, y, y + MUNIT * vals[0],
                              kit.WARM if vals[0] >= 0 else kit.COOL, label,
                              width=0.7 if i == j else 0.5, visible=vis)
                    continue
                kit.signed_bar(sc, bd, MX0 + j * CW, y, vals, J_OUT,
                               f"sigma_{AX_NAME[i]}{AX_NAME[j]} ({tag}): how much E_{AX_NAME[j]} "
                               f"drives J_{AX_NAME[i]}" + ("  (diagonal)" if i == j else ""),
                               unit=MUNIT, width=0.7 if i == j else 0.5,
                               colors=kit.sign_colors(vals), visible=vis)
            kit.waterfall(sc, bd, JX, y, sig[:, i, :] * e,
                          [AX_COL[j] for j in range(N)],
                          [f"J_{AX_NAME[i]} piece: sigma_{AX_NAME[i]}{AX_NAME[j]} E_{AX_NAME[j]} ({tag})"
                           for j in range(N)],
                          f"J_{AX_NAME[i]} = the sum of its row's pieces ({tag})",
                          unit=MUNIT, visible=vis, total_color=J_OUT)
            ex = MX0 + N * CW + EX_OFF
            kit.signed_bar(sc, bd, ex, y, e[:, i], AX_COL[i],
                           f"E_{AX_NAME[i]} ({tag}): the field's {AX_NAME[i]} part", unit=MUNIT,
                           width=0.55, visible=vis)
            kit.polyline(sc, bd, [(ex - 0.5, y, 0), (ex + 0.5, y, 0)], (110, 110, 130, 200),
                         f"zero line, E_{AX_NAME[i]} ({tag})", ratio=0.012, ch=ch_v, hide=hide0)
        assert np.allclose(jv[vis > 0], (sig[:, :, :] @ e[:, :, None])[vis > 0, :, 0])

    # ---- board: which column an experiment fills ----
    for j, (h0, h1) in enumerate(EXPTS):
        vis = kit.window(F, h0, h1)
        sc.node(bd, pos=(MX0 + j * CW, MY0 - CH, 0.0),
                scale=(1.1 / kit.CUBE_FACE, (1.5 * CH + 0.4) / kit.CUBE_FACE, 0.1),
                color=(*AX_COL[j], 200), geometry=0, ch=kit.hide_channel(sc, vis), hide=1,
                text=f"experiment {j + 1}: E along {AX_NAME[j]} fills column {j + 1} of sigma")

    # ---- board: the angle between E and J ----
    ang = np.degrees(np.arccos(np.clip(np.einsum("fi,fi->f", E, J)
                                       / np.linalg.norm(J, axis=1), -1, 1)))
    GU = 2.6 / 90.0
    kit.vspan(sc, bd, GAUGE_X, GAUGE_Y, GAUGE_Y + GU * ang, J_OUT,
              "angle between E and J, in degrees", width=0.6, visible=act12)
    kit.polyline(sc, bd, [(GAUGE_X - 0.6, GAUGE_Y + 2.6, 0), (GAUGE_X + 0.6, GAUGE_Y + 2.6, 0)],
                 (235, 90, 90, 220), "90 degrees: J can never get here (current never runs against the push)",
                 ratio=0.025, ch=kit.hide_channel(sc, act12))
    kit.polyline(sc, bd, [(GAUGE_X - 0.6, GAUGE_Y, 0), (GAUGE_X + 0.6, GAUGE_Y, 0)],
                 (110, 110, 130, 200), "0 degrees: J along E", ratio=0.012,
                 ch=kit.hide_channel(sc, act12))
    kit.caption(sc, bd, (GAUGE_X - 1.2, GAUGE_Y - 0.8), "angle from E to J", color=J_OUT,
                size=0.035, visible=act12)
    kit.caption(sc, bd, (GAUGE_X + 0.8, GAUGE_Y + 2.6), "90: never", color=(235, 120, 120),
                size=0.03, visible=act12)

    # ---- board: the count ladder (Act 3) ----
    kit.caption(sc, bd, (LADDER_X0 - 0.6, LADDER_Y + 1.6),
                "N dimensions: N^2 numbers; the gold diagonal + one triangle are independent",
                color=(190, 190, 210), size=0.035, visible=act3)
    ch_l = kit.hide_channel(sc, act3)
    for N in range(1, 6):
        cell = 0.42
        x0 = LADDER_X0 + 4.6 * (N - 1)
        kit.caption(sc, bd, (x0 - 0.1, LADDER_Y + 0.7), f"N={N}", color=(200, 200, 215),
                    size=0.028, visible=act3)
        for i in range(N):
            for j in range(N):
                col = kit.GOLD if i == j else (J_OUT if i < j else (90, 90, 110))
                kind = ("a principal-value slot (diagonal)" if i == j else
                        "independent off-diagonal" if i < j else "a repeat (sigma_ij = sigma_ji)")
                sc.node(bd, pos=(x0 + j * cell, LADDER_Y - i * cell, 0.0),
                        scale=0.33 * cell / kit.CUBE_FACE, color=(*col, 255),
                        geometry=kit.GEO_CUBE, ch=ch_l, hide=1,
                        text=f"N = {N}: sigma_{i + 1}{j + 1}, {kind}")
        kit.caption(sc, bd, (x0 - 0.1, LADDER_Y - N * cell - 0.6),
                    f"{N * N}, {N * (N + 1) // 2} free", color=(200, 200, 215),
                    size=0.028, visible=act3)

    stem = "Current_Across_the_Grain"
    sc.write(out_dir, stem)
    print(f"Act 1, E along x: J = {np.round(J[0, :2], 4)}, angle {ang[0]:.1f} deg; "
          f"widest angle over the run {ang[act12 > 0].max():.1f} deg")
    print(f"{len(sc.rows)} nodes, {len(sc.tracks)} tracks, {F} frames -> {out_dir}")


CAPTION_HI = (230, 230, 240)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", default=os.path.join(HERE, "Current_Across_the_Grain"))
    build(ap.parse_args().out)
