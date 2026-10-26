"""
Scene 2 -- From Vector to Tensor: what a (rank-2) tensor is.

A rank-2 tensor T is a linear machine: feed it a direction n, it hands back
a vector T n. Drawn with no basis at all, it is the ellipsoid its outputs
make when n runs over every unit direction. Its components need TWO basis
vectors each: T_ij = e_i . (T e_j) -- feed in e_j, read the output along
e_i. That is the whole step up from a vector, and it is why the
transformation law grows a second rotation matrix:

    vector   v'_i  = R_ki v_k                 one R   (rank 1)
    tensor   T'_ij = R_ki R_lj T_kl           two R's (rank 2)

    Act 1  0-24 s     the machine: a probe n sweeps every direction; the
                      outputs T n paint the ellipsoid. No basis anywhere.
    Act 2  24-34 s    a basis appears: T e1, T e2, T e3 and the 3x3 grid.
                      Column j of the grid is T e_j, read along e1, e2, e3.
    Act 3  34-59 s    the basis tours (Scene 1's tour): the ellipsoid never
                      moves, all nine components change, tr T does not.
    Act 4  61-79 s    a steady turn about e3: rank 0 never waves, rank 1
                      waves ONCE per turn, rank 2 waves TWICE (an ellipsoid
                      is back to itself after half a turn).
    Act 5  81-105 s   the basis turns into the ellipsoid's own axes: the
                      off-diagonal components vanish, the diagonal ones
                      become the semi-axes. Diagonalizing is choosing a
                      basis, not changing the tensor.

    python generate_tensor.py [--out DIR]
"""
import argparse
import math
import os

import numpy as np

import tensor_kit as kit

HERE = os.path.dirname(os.path.abspath(__file__))

LAM = np.array([2.0, 1.2, 0.5])
_q1 = np.array([-0.3, 0.8, 0.5])
_q1 /= np.linalg.norm(_q1)
_q2 = np.cross(_q1, [0.85, 0.31, 0.42])       # ~ in the screen plane at the default camera
_q2 /= np.linalg.norm(_q2)
Q = np.column_stack([_q1, _q2, np.cross(_q1, _q2)])
T = Q @ np.diag(LAM) @ Q.T
V0 = np.array([0.4, 1.5, 1.2])                 # Scene 1's vector, for the rank ladder

S = 4.0
FRAMES = 3150
ACT1 = (0, 720)
ACT2 = (720, 1020)
ACT3 = (1020, 1770)
ACT4 = (1830, 2370)
ACT5 = (2430, 2970)
ELLIPSOID_ON = 560
LIFT = 9.0
STAGE_AT = (0.0, -10.0, 0.0)
BOARD_AT = (0.0, -19.0, 12.0)
BG = (10, 12, 22)

MX0, MY0, CW, CH, MUNIT = 23.0, -6.6, 2.6, 2.7, 0.85   # the 3x3 grid
LAD_Y = -16.6                                          # the rank ladder's baseline
SCOPE_X0, SCOPE_W, SCOPE_Y, SCOPE_UNIT = 22.0, 13.0, -23.0, 1.0
ELLIPSOID = (255, 160, 70)


def timeline():
    """Per frame: basis R, probe n (unit), and visibility windows."""
    F = FRAMES
    Rs = np.repeat(np.eye(3)[None], F, axis=0)
    for k in range(*ACT3):
        Rs[k] = kit.tour(kit.ease((k - ACT3[0]) / (ACT3[1] - ACT3[0])))
    for k in range(*ACT4):
        u = (k - ACT4[0]) / (ACT4[1] - ACT4[0] - 1)
        Rs[k] = kit.rot_z(360.0 * u)
    for k in range(ACT5[0], F):
        Rs[k] = kit.slerp(np.eye(3), Q, float(kit.ease((k - ACT5[0]) / (ACT5[1] - ACT5[0]))))
    n = np.zeros((F, 3))
    n[:, 2] = 1.0
    sweep = ACT1[1] - 120                      # the last 4 s of Act 1 hold the probe
    for k in range(F):
        u = min(k, sweep) / sweep
        phi = math.pi * (0.04 + 0.92 * u)
        psi = 2 * math.pi * 7 * u
        n[k] = (math.sin(phi) * math.cos(psi), math.sin(phi) * math.sin(psi), math.cos(phi))
    return Rs, n, sweep


def components(Rs):
    """T'_ij = e_i' . T e_j' = (R^T T R)_ij, per frame."""
    return np.einsum("fki,kl,flj->fij", Rs, T, Rs)


def build(out_dir):
    sc = kit.Scene(FRAMES)
    F = FRAMES
    Rs, n, sweep = timeline()
    Tp = components(Rs)
    vp = np.einsum("fki,k->fi", Rs, V0)
    on_probe = kit.window(F, 0, ACT2[0])
    on_basis = kit.window(F, ACT2[0], F)
    on_v = kit.window(F, ACT3[0], F)

    turn, wall = kit.frames_of_reference(sc, BG, LIFT)
    st = kit.stage(sc, turn, STAGE_AT)
    bd = kit.board(sc, wall, BOARD_AT)

    # ---- room axes ----
    for i, name in enumerate("xyz"):
        a = np.zeros(3)
        a[i] = 2.2 * S
        kit.polyline(sc, st, [-a * 0.3, a], (*kit.GREY, 90),
                     f"room {name} axis (fixed)", ratio=0.02)

    # ---- the tensor itself: the ellipsoid of outputs, and its own axes ----
    e_rot = kit.euler_xyz(Q)
    vis_ell = kit.window(F, ELLIPSOID_ON, F)
    # Wire only: a translucent solid writes depth, and the arrows inside it
    # (Links, drawn after the glyphs) would fail the depth test.
    sc.node(st, rot=e_rot, scale=LAM * S, color=(*ELLIPSOID, 120), geometry=kit.GEO_SPHERE_WIRE,
            ch=kit.hide_channel(sc, vis_ell), hide=1,
            text=f"the tensor T, drawn with no basis: every output T n for a unit n "
                 f"(semi-axes {LAM[0]:g}, {LAM[1]:g}, {LAM[2]:g})")
    pax = sc.node(st, rot=e_rot, hide=1, geometry=kit.GEO_POINT,
                  text="the ellipsoid's own axes frame (principal axes)")
    for i in range(3):
        e = np.zeros(3)
        e[i] = LAM[i] * S
        kit.polyline(sc, pax, [-e, e], (*ELLIPSOID, 150),
                     f"principal axis {i + 1}: T n = {LAM[i]:g} n here (n and T n line up)",
                     ratio=0.025, ch=kit.hide_channel(sc, vis_ell), hide=1)

    # ---- Act 1: the probe ----
    sc.node(st, scale=S, color=(255, 255, 255, 40), geometry=kit.GEO_SPHERE_WIRE,
            ch=kit.hide_channel(sc, on_probe), text="every unit input direction n (radius 1)")
    kit.arrow(sc, st, np.zeros(3), n * S, (*kit.WHITE, 255), "n (input)", radius=0.07,
              head=0.55, ch_visible=on_probe, show_text=1)
    Tn = n @ T.T
    kit.arrow(sc, st, np.zeros(3), Tn * S, (*ELLIPSOID, 255), "T n (output)", radius=0.09,
              head=0.7, ch_visible=on_probe, show_text=1)
    f_on = np.arange(0, sweep + 1, 2)
    kit.reveal(sc, st, Tn[f_on] * S, (*ELLIPSOID, 210),
               "where the outputs T n have been: they paint the ellipsoid", f_on,
               ACT2[1], ratio=0.04, seg=6)

    # ---- the basis, and what T does to each basis vector ----
    basis = sc.node(st, hide=1, geometry=kit.GEO_POINT, ch=kit.rot_channel(sc, Rs),
                    text="the basis frame: turned by R(t), so its local axes ARE e1', e2', e3'")
    origin = sc.node(basis, hide=1, geometry=kit.GEO_POINT, text="origin (the common tail)")
    for i in range(3):
        e = np.zeros(3)
        e[i] = 1.0
        kit.polyline(sc, basis, [-2.1 * S * e, 2.1 * S * e], (*kit.E_RGB[i], 80),
                     f"e{i + 1}' axis line", ratio=0.022,
                     ch=kit.hide_channel(sc, on_basis), hide=1)
        kit.arrow(sc, basis, np.zeros(3), S * e, (*kit.E_RGB[i], 255), f"e{i + 1}'",
                  radius=0.07, head=0.55, tail_node=origin, ch_visible=on_basis, show_text=1)
    for j in range(3):
        # T e_j' in basis coordinates is column j of T'.
        kit.arrow(sc, basis, np.zeros(3), Tp[:, :, j] * S, (*kit.E_LIGHT[j], 255),
                  f"T e{j + 1}'", radius=0.06, head=0.55, ch_visible=on_basis, show_text=1)
    tip1 = sc.node(basis, pos=Tp[0, :, 0] * S, hide=1, geometry=kit.GEO_POINT,
                   ch=kit.pos_channel(sc, Tp[:, :, 0] * S),
                   text="tip of T e1', in basis coordinates")
    for i in range(3):
        foot = np.zeros((F, 3))
        foot[:, i] = Tp[:, i, 0] * S
        fid = kit.marker(sc, basis, foot[0], (*kit.E_RGB[i], 255),
                         f"T_{i + 1}1 = e{i + 1}' . T e1': the shadow of T e1' on e{i + 1}'",
                         scale=0.13, ch=kit.pos_channel(sc, foot, extra=[
                             (sc.track(1 - on_basis), "hide")]), hide=1)
        kit.rod(sc, tip1, fid, (200, 200, 215, 150),
                f"drop line from T e1' to e{i + 1}': gives component T_{i + 1}1",
                radius=0.04, geometry=27, ch=kit.hide_channel(sc, on_basis), hide=1)

    # ---- the rank-1 comparison: Scene 1's vector ----
    kit.arrow(sc, st, np.zeros(3), V0 * S, (*kit.GOLD, 255), "v", radius=0.08, head=0.6,
              ch_visible=on_v, show_text=1)

    # ---- board: captions ----
    kit.caption(sc, bd, (0, 0), "FROM VECTOR TO TENSOR: a machine with two slots",
                color=(255, 225, 120), size=0.09)
    acts = (
        (ACT1[0], ACT1[1], ("Act 1. A tensor is a linear machine: feed in a direction n, get back a vector T n.",
                            "Sweep n over every direction and the outputs paint an ellipsoid. No basis needed: that IS T.")),
        (ACT2[0], ACT2[1], ("Act 2. To write T down, pick a basis and feed it each e_j. Column j of the grid is T e_j,",
                            "read along e1, e2, e3: T_ij = e_i . (T e_j). Every component uses TWO basis vectors.")),
        (ACT3[0], ACT4[0], ("Act 3. Turn the basis (Scene 1's tour). The ellipsoid never moves; all nine numbers change.",
                            "tr T = T11 + T22 + T33 never changes, the way |v|^2 never did.")),
        (ACT4[0], ACT5[0], ("Act 4. One steady turn about e3. Watch the scope: a scalar never waves, a vector component",
                            "waves once per turn, a tensor component TWICE. An ellipsoid looks the same after half a turn.")),
        (ACT5[0], F, ("Act 5. Turn the basis onto the ellipsoid's own axes: the off-diagonal numbers vanish, and the",
                      "diagonal ones become the semi-axes 2.0, 1.2, 0.5. Diagonalizing chooses a basis; T never changed.")),
    )
    for f0, f1, lines in acts:
        vis = kit.window(F, f0, f1)
        for j, line in enumerate(lines):
            kit.caption(sc, bd, (0.4, -1.0 - 0.85 * j), line, visible=vis)
    kit.caption(sc, bd, (0.4, -3.0),
                "vector: v'_i = R_ki v_k (one R).   tensor: T'_ij = R_ki R_lj T_kl (two R's, one per "
                "index). Count the R's: that is the rank.", color=(170, 175, 200))

    # ---- board: the 3x3 grid ----
    kit.caption(sc, bd, (MX0 - 0.8, MY0 + 2.4),
                "rank 2: T_ij = e_i' . T e_j', 9 numbers, two R's", color=ELLIPSOID, size=0.04)
    for j in range(3):
        kit.caption(sc, bd, (MX0 + j * CW - 0.5, MY0 + 1.5), f"T e{j + 1}'",
                    color=kit.E_LIGHT[j], size=0.035)
    for i in range(3):
        y = MY0 - i * CH
        kit.caption(sc, bd, (MX0 + 2 * CW + 1.1, y), f"along e{i + 1}'",
                    color=kit.E_RGB[i], size=0.035)
        kit.hline(sc, bd, MX0 - 0.8, MX0 + 2 * CW + 0.8, y, (110, 110, 130),
                  f"zero line, row {i + 1}", ratio=0.012)
        for j in range(3):
            vals = Tp[:, i, j]
            kit.signed_bar(sc, bd, MX0 + j * CW, y, vals, kit.WARM,
                           f"T_{i + 1}{j + 1} = e{i + 1}' . T e{j + 1}'"
                           + ("  (diagonal)" if i == j else "  (off-diagonal)"),
                           unit=MUNIT, width=0.75 if i == j else 0.55,
                           colors=kit.sign_colors(vals), visible=on_basis)

    # ---- board: the rank ladder (rank 0 and rank 1 beside the grid) ----
    tr = np.trace(Tp, axis1=1, axis2=2)
    base = np.zeros(F)
    ly = LAD_Y
    lad_x = MX0
    for i in range(3):
        y0 = ly + 0.5 * base
        h = 0.5 * Tp[:, i, i]
        s = 0.7 / (2 * kit.CUBE_FACE)
        ch = sc.channel([(sc.track(y0 + h / 2), "translate_y"),
                         (sc.track(h / (2 * kit.CUBE_FACE)), "scale_y"),
                         (sc.track(np.full(F, s)), "scale_x"), (sc.track(np.full(F, 0.2)), "scale_z"),
                         (sc.track(1 - on_basis), "hide")])
        sc.node(bd, pos=(lad_x, y0[0] + h[0] / 2, 0.0), scale=(s, h[0] / (2 * kit.CUBE_FACE), 0.2),
                color=(*kit.E_RGB[i], 255), geometry=kit.GEO_CUBE, ch=ch, hide=1,
                text=f"T{i + 1}{i + 1}: its share of tr T")
        base = base + Tp[:, i, i]
    top = ly + 0.5 * tr[0]
    kit.hline(sc, bd, lad_x - 0.6, lad_x + 0.6, top, (255, 225, 120),
              f"tr T = {tr[0]:.2f} in every basis", ratio=0.03)
    kit.caption(sc, bd, (lad_x - 0.8, ly - 0.8), "rank 0: tr T", color=(255, 225, 120),
                size=0.035)
    kit.caption(sc, bd, (lad_x - 0.8, ly - 1.55), "never moves",
                color=(170, 175, 200), size=0.03)
    vx, vy = MX0 + 4.6, ly + 1.7
    for i in range(3):
        kit.signed_bar(sc, bd, vx + 0.7 * i, vy, vp[:, i], kit.E_RGB[i],
                       f"v{i + 1}' = e{i + 1}' . v (rank 1, for comparison)", unit=MUNIT,
                       width=0.5, visible=on_v)
    kit.hline(sc, bd, vx - 0.5, vx + 1.9, vy, (110, 110, 130), "zero line, v's components",
              ratio=0.012)
    kit.caption(sc, bd, (vx - 0.5, ly - 0.8), "rank 1: v", color=kit.GOLD, size=0.035)
    kit.caption(sc, bd, (vx - 0.5, ly - 1.55), "3 numbers, one R", color=(170, 175, 200),
                size=0.03)

    # ---- board: the scope (Act 4) ----
    a0, a1 = ACT4
    ks = np.arange(a0, a1)
    ang = 360.0 * (ks - a0) / (a1 - a0 - 1)
    xs = SCOPE_X0 + SCOPE_W * ang / 360.0
    kit.hline(sc, bd, SCOPE_X0, SCOPE_X0 + SCOPE_W, SCOPE_Y, (110, 110, 130),
              "scope zero line", ratio=0.012)
    for deg in (0, 90, 180, 270, 360):
        x = SCOPE_X0 + SCOPE_W * deg / 360
        kit.polyline(sc, bd, [(x, SCOPE_Y - 2.2, 0), (x, SCOPE_Y + 2.2, 0)], (80, 80, 100, 140),
                     f"scope gridline: basis turned {deg} deg", ratio=0.01)
        kit.caption(sc, bd, (x - 0.3, SCOPE_Y - 2.7), f"{deg}", color=(150, 150, 170), size=0.02)
    traces = (("tr T / 3: rank 0, never waves", tr[ks] / 3, (255, 225, 120)),
              ("v1': rank 1, one wave per turn", vp[ks, 0], kit.GOLD),
              ("T11': rank 2, two waves per turn", Tp[ks, 0, 0], (255, 110, 70)),
              ("T12': rank 2, two waves per turn", Tp[ks, 0, 1], (225, 110, 235)))
    for j, (name, vals, col) in enumerate(traces):
        step = 3
        pts = [(xs[k], SCOPE_Y + SCOPE_UNIT * vals[k], 0.0) for k in range(0, len(ks), step)]
        kit.polyline(sc, bd, pts, (*col, 235), f"scope trace: {name}", ratio=0.04)
        kit.caption(sc, bd, (SCOPE_X0 + SCOPE_W + 0.4, SCOPE_Y + 1.6 - 0.75 * j), name,
                    color=col, size=0.03)
    cur = np.clip((np.arange(F) - a0) / (a1 - a0 - 1), 0, 1)
    sc.node(bd, pos=(SCOPE_X0, SCOPE_Y, 0.02), scale=(0.03, 4.4 / (2 * kit.CUBE_FACE), 0.03),
            color=(255, 255, 255, 200), geometry=kit.GEO_CUBE,
            ch=sc.channel([(sc.track(SCOPE_X0 + SCOPE_W * cur), "translate_x"),
                           (sc.track(1 - kit.window(F, a0, a1)), "hide")]), hide=1,
            text="now: how far the basis has turned in Act 4")
    kit.caption(sc, bd, (SCOPE_X0, SCOPE_Y + 2.7),
                "Act 4 scope: components against the angle the basis has turned about e3",
                color=(190, 190, 210), size=0.04)

    stem = "Vector_to_Tensor"
    sc.write(out_dir, stem)
    end = Tp[-1]
    off = np.abs(end - np.diag(np.diag(end))).max()
    print(f"tr T over the run: {tr.min():.12f} .. {tr.max():.12f}")
    print(f"end of Act 5: diagonal {np.round(np.diag(end), 6)}, worst off-diagonal {off:.1e}")
    print(f"{len(sc.rows)} nodes, {len(sc.tracks)} tracks, {F} frames -> {out_dir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", default=os.path.join(HERE, "Vector_to_Tensor"))
    build(ap.parse_args().out)
