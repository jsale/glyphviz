"""
Scene 6 -- The Cut: the stress tensor, and Mohr's circle.

Stress is where the word comes from. Latin tendere is "to stretch", and
Woldemar Voigt gave "tensor" its modern meaning in 1898, writing about the
physics of crystals. Imagine cutting a loaded solid with a plane whose
normal is n. The material on the far side pulls on the cut face with a
force per area, the traction t. It depends on the cut: t = sigma n, Scene 2's
machine once more. And t is generally NOT along n. It splits into a pull
straight out of the cut (sigma_n) and a shear along it (tau).

    Act 1  0-40 s     a square of material in plane stress. Face arrows
                      show sigma_xx, sigma_yy, tau_xy. A cut turns through
                      180 deg; its (sigma_n, tau) runs once around Mohr's
                      circle: turn the cut by theta, the point moves 2 theta.
                      Where tau = 0 the cut is a principal plane.
    Act 2  42-76 s    a cube in 3-D stress. The cut plane sweeps every
                      direction; (sigma_n, |tau|) never leaves the region
                      between three circles (Mohr's arbelos).
    Act 3  76-92 s    turn the cube onto the principal directions: the shear
                      arrows on its faces vanish, the grid goes diagonal.

Stresses are in MPa and illustrative.

    python generate_stress.py [--out DIR]
"""
import argparse
import math
import os

import numpy as np

import tensor_kit as kit

HERE = os.path.dirname(os.path.abspath(__file__))

SIG2 = np.array([[3.0, 1.0], [1.0, 1.0]])
P3 = np.array([3.0, 1.0, -1.5])
_qa = kit.rot_z(35.0) @ kit.rot_y(-30.0) @ kit.rot_x(20.0)
Q3 = _qa
SIG3 = Q3 @ np.diag(P3) @ Q3.T

FRAMES = 2760
ACT1 = (0, 1200)
CUT_ON = 210
KEYS = ((240, 0.0), (420, 22.5), (480, 22.5), (600, 67.5), (660, 67.5), (780, 112.5),
        (840, 112.5), (1080, 180.0))
ACT2 = (1260, 2280)
SWEEP3 = (1320, 2220)
ACT3 = (2280, FRAMES)
TURN3 = (2340, 2580)
LIFT = 9.0
STAGE_AT = (0.0, -10.0, 0.0)
BOARD_AT = (0.0, -19.0, 12.0)
BG = (14, 12, 16)

H2 = 2.6                                   # half-size of the 2-D square (world)
H3 = 2.2                                   # half-size of the 3-D cube
S = 1.0                                    # world units per MPa on the stage
MX0, MY0, MU = 23.5, -11.5, 2.0            # Mohr axes: sigma = 0 at MX0; tau = 0 at MY0
GX0, GY0, GW, GH, GUNIT = 36.0, -6.6, 2.4, 2.8, 0.6

PULL = (255, 110, 110)                     # sigma_n n
SHEAR = (90, 220, 230)                     # tau
TRACTION = (255, 170, 60)                  # t = sigma n
NCOL = (235, 235, 245)
MATERIAL = (170, 160, 150)
GEO_CUBE_WIRE, GEO_RING = 0, 33


def theta_at(k):
    """The 2-D cut's normal angle, degrees."""
    if k <= KEYS[0][0]:
        return KEYS[0][1]
    for (f0, a0), (f1, a1) in zip(KEYS, KEYS[1:]):
        if k <= f1:
            return a0 + (a1 - a0) * float(kit.ease((k - f0) / max(f1 - f0, 1)))
    return KEYS[-1][1]


def n3_at(k):
    """The 3-D cut's normal: a spiral over the sphere, then parked on the
    largest principal direction."""
    if k >= SWEEP3[1]:
        return Q3[:, 0]
    u = min(max((k - SWEEP3[0]) / (SWEEP3[1] - SWEEP3[0]), 0.0), 1.0)
    phi = math.pi * (0.03 + 0.94 * u)
    psi = 2 * math.pi * 9 * u
    n = np.array([math.sin(phi) * math.cos(psi), math.sin(phi) * math.sin(psi), math.cos(phi)])
    if k >= SWEEP3[1] - 60:
        w = float(kit.ease((k - (SWEEP3[1] - 60)) / 60.0))
        n = (1 - w) * n + w * Q3[:, 0]
        n /= np.linalg.norm(n)
    return n


def timeline():
    F = FRAMES
    th = np.array([theta_at(k) for k in range(F)])
    n2 = np.column_stack([np.cos(np.radians(th)), np.sin(np.radians(th))])
    s2 = np.column_stack([-n2[:, 1], n2[:, 0]])
    t2 = n2 @ SIG2.T
    sn2 = np.einsum("fi,fi->f", t2, n2)
    tau2 = np.einsum("fi,fi->f", t2, s2)
    n3 = np.array([n3_at(k) for k in range(F)])
    t3 = n3 @ SIG3.T
    sn3 = np.einsum("fi,fi->f", t3, n3)
    sh3 = t3 - sn3[:, None] * n3
    Rc = np.repeat(np.eye(3)[None], F, axis=0)
    for k in range(TURN3[0], F):
        Rc[k] = kit.slerp(np.eye(3), Q3, float(kit.ease((k - TURN3[0]) / (TURN3[1] - TURN3[0]))))
    return th, n2, s2, t2, sn2, tau2, n3, t3, sn3, sh3, Rc


def frame_with_z(n):
    """A rotation whose third column is n (for the cut ring)."""
    a = np.array([0.0, 0.0, 1.0]) if abs(n[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    x = np.cross(a, n)
    x /= np.linalg.norm(x)
    return np.column_stack([x, np.cross(n, x), n])


def face_arrows(sc, parent, centers, normals, sigma, label, visible, shear_off=0.35):
    """Normal and shear traction arrows on a face, animated.
    centers, normals: (F, d); sigma: (d, d)."""
    t = normals @ sigma.T
    tn = np.einsum("fi,fi->f", t, normals)
    sh = t - tn[:, None] * normals
    z = np.zeros((len(t), 3 - normals.shape[1]))
    c3 = np.hstack([centers, z])
    n3 = np.hstack([normals, z])
    s3 = np.hstack([sh, z])
    kit.arrow(sc, parent, c3, c3 + S * tn[:, None] * n3, (*PULL, 255),
              f"{label}: pull (normal stress) on this face", radius=0.07, head=0.4,
              ch_visible=visible)
    base = c3 + shear_off * n3
    kit.arrow(sc, parent, base - 0.5 * S * s3, base + 0.5 * S * s3, (*SHEAR, 255),
              f"{label}: shear along this face", radius=0.06, head=0.35,
              ch_visible=visible * (np.linalg.norm(sh, axis=1) > 0.02))
    return tn, sh


def build(out_dir):
    sc = kit.Scene(FRAMES, dedupe=True)
    F = FRAMES
    th, n2, s2, t2, sn2, tau2, n3, t3, sn3, sh3, Rc = timeline()
    act1 = kit.window(F, *ACT1)
    cut1 = kit.window(F, CUT_ON, ACT1[1])
    act23 = kit.window(F, ACT2[0], F)
    sweep = kit.window(F, ACT2[0], ACT3[0])

    turn, wall = kit.frames_of_reference(sc, BG, LIFT)
    bd = kit.board(sc, wall, BOARD_AT)
    lab = kit.board(sc, wall, (0.0, STAGE_AT[1], 0.0), label="lab plane")
    st = kit.stage(sc, turn, STAGE_AT)

    # ================= Act 1: plane stress =================
    ch1 = kit.hide_channel(sc, act1)
    sq = [(-H2, -H2, 0), (H2, -H2, 0), (H2, H2, 0), (-H2, H2, 0), (-H2, -H2, 0)]
    kit.polyline(sc, lab, sq, (*MATERIAL, 255), "the square of material (its edge)",
                 ratio=0.06, ch=ch1)
    for gx in np.linspace(-H2, H2, 7)[1:-1]:
        kit.polyline(sc, lab, [(gx, -H2, -0.05), (gx, H2, -0.05)], (*MATERIAL, 50),
                     "material texture line", ratio=0.015, ch=ch1)
    for k, m in enumerate(((1, 0), (0, 1), (-1, 0), (0, -1))):
        m = np.broadcast_to(np.array(m, float), (F, 2))
        face_arrows(sc, lab, H2 * m, m, SIG2, f"face {'+x +y -x -y'.split()[k]}", act1)
    # the cut
    half = H2 / np.maximum(np.abs(s2).max(axis=1), 1e-9)
    for sgn, nm in ((1, "end A"), (-1, "end B")):
        p = np.hstack([sgn * half[:, None] * s2, np.full((F, 1), 0.1)])
        if sgn == 1:
            a_id = sc.node(lab, pos=p[0], hide=1, geometry=kit.GEO_POINT,
                           ch=kit.pos_channel(sc, p), text=f"the cut line, {nm}")
        else:
            b_id = sc.node(lab, pos=p[0], hide=1, geometry=kit.GEO_POINT,
                           ch=kit.pos_channel(sc, p), text=f"the cut line, {nm}")
    kit.rod(sc, a_id, b_id, (240, 240, 250), "the cut: a line through the material, normal n",
            radius=0.06, ch=kit.hide_channel(sc, cut1), hide=1)
    z2 = np.full((F, 1), 0.2)
    o = np.zeros(3) + [0, 0, 0.2]
    kit.arrow(sc, lab, o, np.hstack([2.2 * n2, z2]), (*NCOL, 255), "n (the cut's normal)",
              radius=0.06, head=0.4, ch_visible=cut1, show_text=1)
    kit.arrow(sc, lab, o, np.hstack([S * t2, z2]), (*TRACTION, 255), "t = sigma n (traction)",
              radius=0.09, head=0.55, ch_visible=cut1, show_text=1)
    kit.arrow(sc, lab, o, np.hstack([S * sn2[:, None] * n2, z2 + 0.05]), (*PULL, 255),
              "sigma_n: the pull", radius=0.06, head=0.4, ch_visible=cut1, show_text=1)
    kit.arrow(sc, lab, o, np.hstack([S * tau2[:, None] * s2, z2 + 0.05]), (*SHEAR, 255),
              "tau: the shear", radius=0.06, head=0.4,
              ch_visible=cut1 * (np.abs(tau2) > 0.03), show_text=1)

    # ================= Acts 2-3: a cube in 3-D stress =================
    ch23 = kit.hide_channel(sc, act23)
    cube = sc.node(st, rot=(0, 0, 0), scale=H3 / kit.CUBE_FACE, color=(*MATERIAL, 255),
                   geometry=GEO_CUBE_WIRE,
                   ch=sc.channel([(tid, a) for tid, a in
                                  zip([sc.track(e, 3) for e in kit.euler_xyz(Rc).T],
                                      ("rotate_x", "rotate_y", "rotate_z"))]
                                 + [(sc.track(1 - act23), "hide")]), hide=1,
                   text="the cube of material: three of its faces show their tractions")
    for k in range(3):
        m = Rc[:, :, k]
        face_arrows(sc, st, H3 * m, m, SIG3, f"cube face +{'xyz'[k]}", act23, shear_off=0.3)
    # the cut plane, as a ring, and its arrows
    Rring = np.array([frame_with_z(n) for n in n3])
    sc.node(st, rot=kit.euler_xyz(Rring[0]), scale=(1.6 * H3, 1.6 * H3, 0.04), ratio=0.03,
            color=(240, 240, 250, 255), geometry=GEO_RING,
            ch=sc.channel([(sc.track(e, 3), a) for e, a in
                           zip(kit.euler_xyz(Rring).T, ("rotate_x", "rotate_y", "rotate_z"))]
                          + [(sc.track(1 - act23), "hide")]), hide=1,
            text="the cut plane (its rim), normal n")
    o3 = np.zeros(3)
    kit.arrow(sc, st, o3, 2.0 * n3, (*NCOL, 255), "n", radius=0.06, head=0.4,
              ch_visible=act23, show_text=1)
    kit.arrow(sc, st, o3, S * t3, (*TRACTION, 255), "t = sigma n", radius=0.09, head=0.55,
              ch_visible=act23, show_text=1)
    kit.arrow(sc, st, o3, S * sn3[:, None] * n3, (*PULL, 255), "pull", radius=0.06, head=0.4,
              ch_visible=act23)
    kit.arrow(sc, st, o3, S * sh3, (*SHEAR, 255), "shear", radius=0.06, head=0.4,
              ch_visible=act23 * (np.linalg.norm(sh3, axis=1) > 0.03))
    for i in range(3):
        a = Q3[:, i] * 2.6 * H3
        kit.polyline(sc, st, [-a, a], (255, 225, 120, 130),
                     f"principal direction {i + 1}: a cut across it feels pure "
                     f"{'pull' if P3[i] > 0 else 'push'} {P3[i]:g} MPa, no shear",
                     ratio=0.025, ch=kit.hide_channel(sc, kit.window(F, ACT3[0], F)), hide=1)

    # ================= board =================
    kit.caption(sc, bd, (0, 0), "THE CUT: the stress tensor, and Mohr's circle",
                color=(255, 225, 120), size=0.09)
    acts = (
        (0, CUT_ON, ("Act 1. A square of loaded material. Each face is pulled by its neighbour: a pull straight out",
                     "(red) and a shear along the face (cyan). sigma_xx = 3, sigma_yy = 1, tau_xy = 1 MPa.")),
        (CUT_ON, 840, ("Cut it with a line of normal n. The far side pulls on the cut with t = sigma n (orange): Scene 2's",
                       "machine. t is not along n; it splits into a pull sigma_n = t . n and a shear tau along the cut.")),
        (840, ACT1[1], ("Turn the cut by theta and the point (sigma_n, tau) goes 2 theta round Mohr's circle: rank 2's two",
                        "waves per turn. Where tau = 0 the cut is a principal plane: pure pull, 3.41 or 0.59 MPa.")),
        (ACT2[0], ACT3[0], ("Act 2. A cube in 3-D stress. The cut plane sweeps every direction. Each cut is a point",
                            "(sigma_n, |tau|), and every one lands between three circles: Mohr's arbelos.")),
        (ACT3[0], F, ("Act 3. Turn the cube onto the principal directions: the shear on its faces vanishes. Metals slip",
                      "where shear peaks (45 deg between them); chalk snaps where pull peaks. Twist chalk: a 45 deg break.")),
    )
    for f0, f1, lines in acts:
        vis = kit.window(F, f0, f1)
        for j, line in enumerate(lines):
            kit.caption(sc, bd, (0.4, -1.0 - 0.85 * j), line, visible=vis)
    kit.caption(sc, bd, (0.4, -3.0),
                "t_i = sigma_ij n_j: a cut's normal in, a force per area out. Latin tendere, to stretch: "
                "stress is the original tensor.", color=(170, 175, 200))

    # ---- Mohr axes (both acts) ----
    def mx(sv):
        return MX0 + MU * sv

    def my(tv):
        return MY0 + MU * tv
    kit.polyline(sc, bd, [(mx(-2.2), my(0), 0), (mx(4.0), my(0), 0)], (170, 170, 190, 220),
                 "Mohr axis: sigma_n, the pull on the cut (MPa)", ratio=0.02)
    kit.polyline(sc, bd, [(mx(0), my(-2.4), 0), (mx(0), my(2.6), 0)], (170, 170, 190, 220),
                 "Mohr axis: tau, the shear on the cut (MPa)", ratio=0.02)
    kit.caption(sc, bd, (mx(4.1), my(0)), "sigma_n", color=(190, 190, 210), size=0.03)
    kit.caption(sc, bd, (mx(0) + 0.2, my(2.7)), "tau", color=(190, 190, 210), size=0.03)
    for v in (-1, 1, 2, 3):
        kit.polyline(sc, bd, [(mx(v), my(0) - 0.15, 0), (mx(v), my(0) + 0.15, 0)],
                     (170, 170, 190, 220), f"tick: sigma_n = {v} MPa", ratio=0.015)
        kit.caption(sc, bd, (mx(v) - 0.15, my(0) - 0.6), f"{v}", color=(150, 150, 170), size=0.02)

    # ---- Act 1 Mohr: circle painted by the turning cut ----
    c2 = 0.5 * np.trace(SIG2)
    r2 = math.hypot(0.5 * (SIG2[0, 0] - SIG2[1, 1]), SIG2[0, 1])
    f_on = np.arange(KEYS[0][0], KEYS[-1][0] + 1, 4)
    kit.reveal(sc, bd, np.column_stack([mx(sn2[f_on]), my(tau2[f_on]), np.zeros(len(f_on))]),
               (*TRACTION, 220), "Mohr's circle, painted by the turning cut", f_on, ACT1[1],
               ratio=0.06, seg=6)
    cen = sc.node(bd, pos=(mx(c2), my(0), 0.02), scale=0.12, color=(255, 225, 120, 255),
                  ch=ch1, text=f"the circle's centre: (sigma_xx + sigma_yy)/2 = {c2:g} MPa")
    pt = sc.node(bd, pos=(mx(sn2[0]), my(tau2[0]), 0.05), scale=0.2, color=(*TRACTION, 255),
                 ch=kit.pos_channel(sc, np.column_stack([mx(sn2), my(tau2), np.full(F, 0.05)]),
                                    extra=[(sc.track(1 - cut1), "hide")]), hide=1,
                 text="this cut, right now: (sigma_n, tau)")
    kit.rod(sc, cen, pt, (255, 225, 120, 200), "radius to this cut: it turns 2 theta when the cut turns theta",
            radius=0.03, ch=kit.hide_channel(sc, cut1), hide=1)
    for v, lab_ in ((c2 + r2, "sigma_1"), (c2 - r2, "sigma_2")):
        kit.marker(sc, bd, (mx(v), my(0), 0.03), (255, 225, 120, 255),
                   f"{lab_} = {v:.2f} MPa: a principal plane (no shear)", scale=0.14, ch=ch1)
        kit.caption(sc, bd, (mx(v) - 0.4, my(0) + (0.7 if lab_ == "sigma_1" else -1.3)),
                    f"{lab_} = {v:.2f}", color=(255, 225, 120),
                    size=0.025, visible=act1)
    for sgn in (1, -1):
        kit.marker(sc, bd, (mx(c2), my(sgn * r2), 0.03), (*SHEAR, 255),
                   f"largest shear, {sgn * r2:+.2f} MPa: the cut 45 deg from a principal plane",
                   scale=0.11, ch=ch1)

    # ---- Act 2 Mohr: three circles and the arbelos ----
    ps = np.sort(P3)[::-1]
    t_c = np.linspace(0, math.pi, 61)
    for (a, b), nm in (((0, 2), "outer"), ((0, 1), "inner"), ((1, 2), "inner")):
        cc, rr = 0.5 * (ps[a] + ps[b]), 0.5 * abs(ps[a] - ps[b])
        pts = np.column_stack([mx(cc + rr * np.cos(t_c)), my(rr * np.sin(t_c)), np.zeros(61)])
        kit.polyline(sc, bd, pts, (255, 225, 120, 200),
                     f"Mohr circle through sigma_{a + 1} = {ps[a]:g} and sigma_{b + 1} = {ps[b]:g} "
                     f"({nm}: every cut lands {'inside' if nm == 'outer' else 'outside'} it)",
                     ratio=0.04, ch=ch23, hide=1)
    for i, v in enumerate(ps):
        kit.caption(sc, bd, (mx(v) - 0.3, my(0) - 1.2 - 0.8 * (i == 1)), f"sigma_{i + 1} = {v:g}",
                    color=(255, 225, 120), size=0.025, visible=act23)
    tau3 = np.linalg.norm(sh3, axis=1)
    f_on = np.arange(SWEEP3[0], SWEEP3[1] + 1, 3)
    kit.reveal(sc, bd, np.column_stack([mx(sn3[f_on]), my(tau3[f_on]), np.full(len(f_on), 0.03)]),
               (*TRACTION, 210), "where the sweeping cut has landed: (sigma_n, |tau|)", f_on, F,
               ratio=0.04, seg=6)
    sc.node(bd, pos=(mx(sn3[0]), my(tau3[0]), 0.06), scale=0.2, color=(*TRACTION, 255),
            ch=kit.pos_channel(sc, np.column_stack([mx(sn3), my(tau3), np.full(F, 0.06)]),
                               extra=[(sc.track(1 - act23), "hide")]), hide=1,
            text="this 3-D cut, right now: (sigma_n, |tau|)")

    # ---- the component grids ----
    blocks = ((2, np.broadcast_to(SIG2, (F, 2, 2)), act1, "the square's"),
              (3, np.einsum("fki,kl,flj->fij", Rc, SIG3, Rc), act23, "the cube's"))
    for N, sig, vis, who in blocks:
        chv = kit.hide_channel(sc, vis)
        kit.caption(sc, bd, (GX0 - 0.8, GY0 + 2.0), f"sigma_ij in {who} own axes (MPa)",
                    color=TRACTION, size=0.035, visible=vis)
        for i in range(N):
            y = GY0 - i * GH
            kit.polyline(sc, bd, [(GX0 - 0.7, y, 0), (GX0 + (N - 1) * GW + 0.7, y, 0)],
                         (110, 110, 130, 200), f"zero line, row {i + 1} ({who})", ratio=0.012,
                         ch=chv, hide=int(not vis[0]))
            for j in range(N):
                v = sig[:, i, j]
                lbl = (f"sigma_{'xyz'[i]}{'xyz'[j]} ({who} axes)"
                       + ("  (diagonal: pull or push)" if i == j else "  (off-diagonal: shear)"))
                if np.ptp(v) == 0:
                    kit.vspan(sc, bd, GX0 + j * GW, y, y + GUNIT * v[0],
                              kit.WARM if v[0] >= 0 else kit.COOL, lbl,
                              width=0.7 if i == j else 0.5, visible=vis)
                else:
                    kit.signed_bar(sc, bd, GX0 + j * GW, y, v, kit.WARM, lbl, unit=GUNIT,
                                   width=0.7 if i == j else 0.5, colors=kit.sign_colors(v),
                                   visible=vis)
                kit.caption(sc, bd, (GX0 + j * GW - 0.3, y - 0.6), f"{'xyz'[i]}{'xyz'[j]}",
                            color=(170, 170, 190), size=0.022, visible=vis)

    stem = "The_Cut"
    sc.write(out_dir, stem)
    inside = (sn3 - 0.5 * (ps[0] + ps[2])) ** 2 + tau3 ** 2 <= (0.5 * (ps[0] - ps[2])) ** 2 + 1e-9
    print(f"Act 1: Mohr circle centre {c2}, radius {r2:.4f}; principal plane at "
          f"{0.5 * math.degrees(math.atan2(2 * SIG2[0, 1], SIG2[0, 0] - SIG2[1, 1])):.1f} deg")
    print(f"Act 2: every cut inside the outer circle: {bool(inside.all())}")
    print(f"{len(sc.rows)} nodes, {len(sc.tracks)} tracks, {F} frames -> {out_dir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", default=os.path.join(HERE, "The_Cut"))
    build(ap.parse_args().out)
