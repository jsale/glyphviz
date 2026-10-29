"""
Scene 7 -- A Field of Machines: a diffusion tensor at every point.

Diffusion is conductivity for molecules. Fick's law, J_i = -D_ij dc/dx_j,
is Scene 4's machine with a concentration gradient in place of the field
and the diffusion tensor D in place of sigma. In fibrous tissue water
moves easily along the fibres and poorly across them, so D is an
ellipsoid, and it changes from place to place: a tensor FIELD. Diffusion
MRI (DTI) measures one D per voxel, and this is the picture it gives.

The tissue is a SYNTHETIC phantom, not a scan: an arching bundle, a
vertical bundle that crosses its top, a bundle running through the slice,
a fluid pocket, and grey matter around them. Diffusivities are typical
brain values (in units of 1e-3 mm^2/s).

    Act 1  0-24 s     one point's machine: a drop of dye spreads into an
                      ellipsoid, the shape D predicts (2 sigma: about three
                      quarters of the dye inside)
    Act 2  24-42 s    the drop's ellipsoid takes its place in the slice,
                      and the whole field appears: one D per voxel, coloured
                      by the long axis's direction
    Act 3  42-58 s    rank 0 from rank 2: mean diffusivity (tr D / 3) and
                      fractional anisotropy, the two maps radiologists read
    Act 4  58-95 s    tractography: step along each ellipsoid's long axis
                      and the paths trace the bundles; at the crossing the
                      ellipsoid is a flattened disc and the vertical track
                      takes a wrong turn; through-slice and fluid seeds stop

    python generate_field.py [--out DIR]
"""
import argparse
import math
import os

import numpy as np

import tensor_kit as kit

HERE = os.path.dirname(os.path.abspath(__file__))

NX, NY = 18, 12
XS = np.arange(NX) - (NX - 1) / 2         # voxel centres, lab units (1 per voxel)
YS = np.arange(NY) - (NY - 1) / 2
ARCH_C, ARCH_R = np.array([0.0, -6.0]), (6.3, 8.7)
VERT_X = 1.0
THRU_C, THRU_R = np.array([6.0, 3.5]), 1.6
CSF_C, CSF_R = np.array([-4.5, 3.6]), (2.1, 1.3)
L_PAR, L_PERP, L_GREY, L_CSF = 1.7, 0.3, 0.8, 3.0
MIX = 0.6                                  # the crossing: 60% arch, 40% vertical
GLYPH = 0.32                               # semi-axis = GLYPH * sqrt(lambda)
DEMO_VOX = (3, 4)                          # (ix, iy) of the dye-drop voxel: x -5.5, y -1.5

S = 1.25                                   # world units per lab unit
FRAMES = 2850
DROP = (60, 600)
ACT2 = (720, 1260)
MOVE = (600, 720)
SCAN = (720, 840)
ACT3 = (1260, 1740)
ACT4 = (1740, FRAMES)
TRACK = (1800, 2640)
N_DYE = 90
DEMO_K = 3.4                               # the drop's 2-sigma semi-axes: DEMO_K sqrt(lambda_i)
LIFT = 9.0
STAGE_AT = (0.0, -10.0, 0.0)
BOARD_AT = (0.0, -19.0, 12.0)
BG = (8, 10, 14)

MAPX, MAPY, CELL = 22.0, -9.4, 0.42        # the FA and MD maps on the board
GREY = np.array([110, 110, 120])
TRACK_COL = (255, 225, 120)
DYE = (120, 220, 255)


def stick(d, lp=L_PAR, lq=L_PERP):
    d = np.asarray(d, float)
    d = d / np.linalg.norm(d)
    return lq * np.eye(3) + (lp - lq) * np.outer(d, d)


def tissue(x, y, rng=None):
    """(D, kind) at a lab point."""
    p = np.array([x, y])
    r = np.linalg.norm(p - ARCH_C)
    in_arch = ARCH_R[0] <= r <= ARCH_R[1]
    in_vert = abs(x) <= VERT_X
    if np.hypot(*((p - CSF_C) / CSF_R)) <= 1:
        return L_CSF * np.eye(3), "fluid pocket"
    if np.linalg.norm(p - THRU_C) <= THRU_R:
        return stick((0, 0, 1)), "bundle through the slice"
    if in_arch:
        t = np.array([-(y - ARCH_C[1]), x - ARCH_C[0], 0.0]) / r
        if in_vert:
            return MIX * stick(t) + (1 - MIX) * stick((0, 1, 0)), "crossing (arch over vertical)"
        return stick(t), "arching bundle"
    if in_vert:
        return stick((0, 1, 0)), "vertical bundle"
    if rng is None:
        return L_GREY * np.eye(3), "grey matter"
    Q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    lam = L_GREY * (1 + 0.12 * rng.uniform(-1, 1, 3))
    return Q @ np.diag(lam) @ Q.T, "grey matter"


def field():
    """D (NX, NY, 3, 3) and kinds, seeded."""
    rng = np.random.default_rng(11)
    D = np.zeros((NX, NY, 3, 3))
    kinds = {}
    for i, x in enumerate(XS):
        for j, y in enumerate(YS):
            D[i, j], kinds[i, j] = tissue(x, y, rng)
    return D, kinds


def eig_sorted(D):
    lam, vec = np.linalg.eigh(D)
    lam, vec = lam[::-1], vec[:, ::-1]
    if np.linalg.det(vec) < 0:
        vec[:, 2] *= -1
    return lam, vec


def fa(lam):
    m = lam.mean()
    return math.sqrt(1.5) * np.linalg.norm(lam - m) / np.linalg.norm(lam)


def dti_color(lam, vec):
    f = fa(lam)
    c = f * np.abs(vec[:, 0]) * 255 + (1 - f) * GREY
    return tuple(int(round(v)) for v in np.clip(c * 1.15, 0, 255))


def interp(D, x, y):
    """Bilinear tensor interpolation at lab (x, y); None outside the grid."""
    fx, fy = x - XS[0], y - YS[0]
    i, j = int(math.floor(fx)), int(math.floor(fy))
    if not (0 <= i < NX - 1 and 0 <= j < NY - 1):
        return None
    u, v = fx - i, fy - j
    return ((1 - u) * (1 - v) * D[i, j] + u * (1 - v) * D[i + 1, j]
            + (1 - u) * v * D[i, j + 1] + u * v * D[i + 1, j + 1])


def streamline(D, seed, heading, step=0.08, n_max=400):
    """Follow the long axis from seed. Returns (points (n, 2), why it stopped)."""
    p = np.array(seed, float)
    d = np.array([*heading, 0.0])
    pts = [p.copy()]
    for _ in range(n_max):
        Dp = interp(D, *p)
        if Dp is None:
            return np.array(pts), "reached the edge"
        lam, vec = eig_sorted(Dp)
        if fa(lam) < 0.2:
            return np.array(pts), "stopped where D is too round"
        e = vec[:, 0] * (1 if vec[:, 0] @ d >= 0 else -1)
        if abs(e[2]) > 0.6:
            return np.array(pts), "stopped: fibres leave the slice"
        if e[:2] @ d[:2] < 0.5 * np.linalg.norm(e[:2]) * np.linalg.norm(d[:2]):
            return np.array(pts), "stopped: turned too sharply"
        d = e
        p = p + step * e[:2] / np.linalg.norm(e[:2])
        pts.append(p.copy())
    return np.array(pts), "ran out of steps"


SEEDS = (((-7.3, -2.2), (0.0, 1.0), "arch, outer"),
         ((-6.4, -2.6), (0.0, 1.0), "arch, inner"),
         ((0.5, -5.0), (0.0, 1.0), "vertical, from below"),
         ((-0.5, 5.2), (0.0, -1.0), "vertical, from above"),
         ((6.0, 3.5), (1.0, 0.0), "through-slice bundle"),
         ((-4.5, 3.6), (1.0, 0.0), "fluid pocket"))


def dye(D_demo):
    """Dye positions (frames, N_DYE, 3) in world units around the drop centre,
    and the 2-sigma spread scale per frame (sqrt(2 t) with t in 0..1)."""
    rng = np.random.default_rng(5)
    F = FRAMES
    lam, vec = eig_sorted(D_demo)
    root = vec @ np.diag(np.sqrt(2 * lam)) @ vec.T        # sqrt(2 D)
    steps = DROP[1] - DROP[0]
    dW = rng.normal(size=(steps, N_DYE, 3)) * math.sqrt(1.0 / steps)
    W = np.concatenate([np.zeros((1, N_DYE, 3)), np.cumsum(dW, axis=0)])
    X = np.einsum("ij,tnj->tni", root, W) * DEMO_K / (2 * math.sqrt(2))   # 2 sigma = DEMO_K sqrt(lam)
    out = np.zeros((F, N_DYE, 3))
    for k in range(F):
        t = min(max(k - DROP[0], 0), steps)
        out[k] = X[t]
    tnow = np.clip((np.arange(F) - DROP[0]) / steps, 0, 1)
    return out, tnow


def build(out_dir):
    sc = kit.Scene(FRAMES, dedupe=True)
    F = FRAMES
    D, kinds = field()
    turn, wall = kit.frames_of_reference(sc, BG, LIFT)
    bd = kit.board(sc, wall, BOARD_AT)
    lab = kit.board(sc, wall, (0.0, STAGE_AT[1], 0.0), label="slice plane")
    act1 = kit.window(F, 0, MOVE[0])
    act234 = kit.window(F, SCAN[0], F)
    act34 = kit.window(F, ACT3[0], F)
    act4 = kit.window(F, ACT4[0], F)

    # ---- Act 1: the drop of dye ----
    iD, jD = DEMO_VOX
    Dd = D[iD, jD]
    lam_d, vec_d = eig_sorted(Dd)
    X, tnow = dye(Dd)
    hide_dye = sc.track(1 - kit.window(F, DROP[0], MOVE[0] + 30))
    for q in range(N_DYE):
        sc.node(lab, pos=np.round(X[0, q], 2) + [0, 0, 1.0], scale=0.09, color=(*DYE, 255),
                geometry=kit.GEO_SPHERE, hide=1,
                ch=kit.pos_channel(sc, X[:, q] + [0, 0, 1.0], dp=2, extra=[(hide_dye, "hide")]),
                text=f"dye molecule {q + 1}: a random walk, steered by D")
    # the predicted 2-sigma ellipsoid: grows as sqrt(t), then flies to its voxel
    grow = np.sqrt(np.maximum(tnow, 1e-6))
    home = np.array([XS[iD] * S, YS[jD] * S, 0.0])
    w_mv = np.array([float(kit.ease((k - MOVE[0]) / (MOVE[1] - MOVE[0]))) for k in range(F)])
    big = DEMO_K * np.sqrt(lam_d)
    small = GLYPH * S * np.sqrt(lam_d)
    sz = np.where(w_mv[:, None] > 0, (1 - w_mv[:, None]) * big + w_mv[:, None] * small,
                  grow[:, None] * big)
    ctr = np.outer(w_mv, home) + np.outer(1 - w_mv, [0, 0, 1.0])
    on_ell = kit.window(F, DROP[0], SCAN[0])
    sc.node(lab, pos=ctr[0], rot=kit.euler_xyz(vec_d), scale=np.maximum(sz[0], 1e-3),
            color=(*DYE, 200), geometry=kit.GEO_SPHERE_WIRE, hide=1,
            ch=sc.channel([(sc.track(ctr[:, i], 3), a) for i, a in
                           enumerate(("translate_x", "translate_y", "translate_z"))]
                          + [(sc.track(sz[:, i], 4), a) for i, a in
                             enumerate(("scale_x", "scale_y", "scale_z"))]
                          + [(sc.track(1 - on_ell), "hide")]),
            text="the shape D predicts: two standard deviations along each axis, about 3/4 of the dye inside")
    kit.marker(sc, lab, (0, 0, 1.0), (255, 255, 255, 255), "where the drop of dye started",
               scale=0.12, ch=kit.hide_channel(sc, kit.window(F, 0, MOVE[0])))

    # ---- the field: one ellipsoid per voxel ----
    lams = np.zeros((NX, NY, 3))
    vis_demo = kit.window(F, SCAN[0], F)
    for i, x in enumerate(XS):
        vis = kit.window(F, SCAN[0] + int((SCAN[1] - SCAN[0]) * i / NX), F)
        chc = kit.hide_channel(sc, vis)
        for j, y in enumerate(YS):
            lam, vec = eig_sorted(D[i, j])
            lams[i, j] = lam
            ch = kit.hide_channel(sc, vis_demo) if (i, j) == DEMO_VOX else chc
            sc.node(lab, pos=(x * S, y * S, 0.0), rot=kit.euler_xyz(vec),
                    scale=GLYPH * S * np.sqrt(lam), color=(*dti_color(lam, vec), 255),
                    geometry=kit.GEO_SPHERE, ch=ch, hide=1,
                    text=f"voxel ({i + 1}, {j + 1}), {kinds[i, j]}: D eigenvalues "
                         f"{lam[0]:.2f}, {lam[1]:.2f}, {lam[2]:.2f}; FA {fa(lam):.2f}")
    frame_pts = [(-NX / 2, -NY / 2, 0), (NX / 2, -NY / 2, 0), (NX / 2, NY / 2, 0),
                 (-NX / 2, NY / 2, 0), (-NX / 2, -NY / 2, 0)]
    kit.polyline(sc, lab, [tuple(np.array(p) * S) for p in frame_pts], (90, 95, 115, 200),
                 "the edge of the slice", ratio=0.03)

    # ---- Act 4: tractography ----
    Dt = D                                       # the tracks read exactly what is drawn
    tracks = []
    t0, t1 = TRACK
    for k, (seed, head, name) in enumerate(SEEDS):
        pts, why = streamline(Dt, seed, head)
        if len(pts) > 2:
            dirs = np.diff(pts, axis=0)
            if np.degrees(np.arccos(np.clip(dirs[-1] @ dirs[0] / np.linalg.norm(dirs[-1])
                                            / np.linalg.norm(dirs[0]), -1, 1))) > 60 and "arch" not in name:
                why = "turned at the crossing (wrong turn), then " + why.replace("stopped", "stopped")
        tracks.append((name, pts, why))
        start = t0 + 60 * k
        dur = max(int(len(pts) * 1.2), 30)
        f_on = np.minimum(start + (np.arange(len(pts)) * dur / max(len(pts) - 1, 1)).astype(int),
                          F - 1)
        P3 = np.column_stack([pts * S, np.full(len(pts), 0.75)])
        kit.marker(sc, lab, P3[0], (255, 255, 255, 255), f"track seed: {name}", scale=0.13,
                   ch=kit.hide_channel(sc, kit.window(F, start, F)), hide=1)
        if len(pts) > 2:
            kit.reveal(sc, lab, P3, (*TRACK_COL, 240), f"track from the {name} seed",
                       f_on, F, ratio=0.09, seg=6)
        head_pos = P3[np.clip(np.searchsorted(f_on, np.arange(F), side="right") - 1, 0, len(pts) - 1)]
        sc.node(lab, pos=np.round(head_pos[0], 3), scale=0.16, color=(*TRACK_COL, 255),
                ch=kit.pos_channel(sc, head_pos, dp=3,
                                   extra=[(sc.track(1 - kit.window(F, start, int(f_on[-1]) + 1)),
                                           "hide")]), hide=1,
                text=f"tracker on the {name} track: it steps along the local long axis")
        end_vis = kit.window(F, int(f_on[-1]), F)
        kit.marker(sc, lab, P3[-1] + [0, 0, 0.05], (255, 120, 120, 255),
                   f"end of the {name} track: {why}", scale=0.15, geometry=25,
                   ch=kit.hide_channel(sc, end_vis), hide=1)

    # ---- board: captions ----
    kit.caption(sc, bd, (0, 0), "A FIELD OF MACHINES: a diffusion tensor at every point",
                color=(255, 225, 120), size=0.09)
    acts = (
        (0, MOVE[0], ("Act 1. Diffusion is conductivity for molecules: Fick's law J_i = -D_ij dc/dx_j is Scene 4's machine.",
                      "Along fibres water moves easily, across them poorly. A drop of dye spreads into D's ellipsoid.")),
        (MOVE[0], ACT3[0], ("Act 2. Tissue has a D at every point: a tensor FIELD. Diffusion MRI measures one per voxel (DTI).",
                            "Colour = the long axis's direction (red left-right, green up-down, blue through the slice).")),
        (ACT3[0], ACT4[0], ("Act 3. Two numbers no basis can change (rank 0, like tr T in Scene 2): mean diffusivity tr D / 3,",
                            "how fast overall, and fractional anisotropy FA, how lopsided (0 = sphere, 1 = needle).")),
        (ACT4[0], F, ("Act 4. Tractography: keep stepping along the local long axis, and the paths trace the bundles.",
                      "At the crossing the ellipsoid is a flat disc, and the vertical track takes a wrong turn.")),
    )
    for f0, f1, lines in acts:
        vis = kit.window(F, f0, f1)
        for j, line in enumerate(lines):
            kit.caption(sc, bd, (0.4, -1.0 - 0.85 * j), line, visible=vis)
    kit.caption(sc, bd, (0.4, -3.0),
                "A SYNTHETIC phantom, not a scan: one tensor per voxel can't hold two crossing fibre "
                "directions; newer methods fit several.", color=(170, 175, 200))

    # ---- board: colour legend ----
    for k, (name, col) in enumerate((("left-right", kit.E_RGB[0]), ("up-down", kit.E_RGB[1]),
                                     ("through the slice", kit.E_RGB[2]),
                                     ("round (FA near 0)", tuple(GREY)))):
        sc.node(bd, pos=(MAPX + 0.1, -4.8 - 0.95 * k, 0.0), scale=0.22, color=(*col, 255),
                geometry=kit.GEO_SPHERE, ch=kit.hide_channel(sc, act234), hide=1,
                text=f"colour key: {name}")
        kit.caption(sc, bd, (MAPX + 0.5, -4.8 - 0.95 * k), name, color=(190, 190, 210),
                    size=0.025, visible=act234)

    # ---- board: the two scalar maps (Act 3 on) ----
    md = lams.mean(axis=2)
    fam = np.array([[fa(lams[i, j]) for j in range(NY)] for i in range(NX)])
    chm = kit.hide_channel(sc, act34)
    for m, (name, vals, lo, hi) in enumerate((("FA: how lopsided, 0 to 1", fam, 0.0, 1.0),
                                               ("MD: blind to fibres", md, 0.0, L_CSF))):
        x0 = MAPX + m * (NX * CELL + 2.4)
        y0 = MAPY - 1.0
        kit.caption(sc, bd, (x0 - 0.2, y0 + 0.9), name, color=(190, 190, 210), size=0.03,
                    visible=act34)
        for i in range(NX):
            for j in range(NY):
                u = (vals[i, j] - lo) / (hi - lo)
                col = ((40 + 215 * u,) * 3 if m == 0 else
                       (30 + 225 * u ** 0.8, 60 + 195 * u, 120 + 135 * u))
                sc.node(bd, pos=(x0 + i * CELL, y0 - (NY - 1 - j) * CELL, 0.0),
                        scale=0.48 * CELL / kit.CUBE_FACE * np.array([1, 1, 0.2]),
                        color=(*col, 255), geometry=kit.GEO_CUBE, ch=chm, hide=1,
                        text=f"{name.split(':')[0]} map, voxel ({i + 1}, {j + 1}): "
                             f"{vals[i, j]:.2f}")

    # ---- board: the tracks' fates ----
    kit.caption(sc, bd, (MAPX - 0.2, MAPY - NY * CELL - 1.6), "the tracks:",
                color=(190, 190, 210), size=0.03, visible=act4)
    for k, (name, pts, why) in enumerate(tracks):
        vis = kit.window(F, TRACK[0] + 60 * k, F)
        short = ("wrong turn at the crossing" if "wrong turn" in why else
                 "followed the bundle to the edge" if "edge" in why else
                 "stops: fibres leave the slice" if "leave" in why else "stops: D too round to follow")
        kit.caption(sc, bd, (MAPX - 0.2, MAPY - NY * CELL - 2.5 - 0.95 * k),
                    f"{name}: {short}",
                    color=TRACK_COL, size=0.025, visible=vis)

    stem = "A_Field_of_Machines"
    sc.write(out_dir, stem)
    for name, pts, why in tracks:
        print(f"track {name:<30} {len(pts):4d} steps, {why}")
    print(f"FA range {fam.min():.2f} .. {fam.max():.2f}; crossing FA "
          f"{fam[int(np.argmin(np.abs(XS - 0.5))), int(np.argmin(np.abs(YS - 1.5)))]:.2f}")
    print(f"{len(sc.rows)} nodes, {len(sc.tracks)} tracks, {F} frames -> {out_dir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", default=os.path.join(HERE, "A_Field_of_Machines"))
    build(ap.parse_args().out)
