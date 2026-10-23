"""
One star, three ways to ask for it: perfect-fluid initial data in GR, drawn in
GlyphViz. An illustration for Paul T. Allen's AMS talk "Specifying initial
perfect fluid distributions in general relativity" (work with David Maxwell,
building on Isenberg & Maxwell's conformal method for Lagrangian matter).

A uniform ball of dust, momentarily at rest, on a conformally flat slice. The
constraint becomes the Lichnerowicz equation for the conformal factor phi, and
what you hold fixed decides whether it can be solved (star_physics.py):

    A  DIRECT      fix the physical density rho        -> phi^+5: two answers, then none
    B  TEXTBOOK    fix a seed rho~ = phi^8 rho         -> phi^-3: always one answer,
                                                          but not the density you asked for
    C  DENSITIZED  fix rho* = phi^6 rho, the matter    -> phi^-1: always one answer, and
                   in each coordinate cell                exactly the matter you asked for

C is a toy in the spirit of Isenberg & Maxwell's conformally invariant matter
variables, for dust at rest -- not their perfect-fluid system.

Each sheet is the slice's equatorial plane as an embedding diagram (a "rubber
sheet"): a surface of revolution whose lengths are the slice's real proper
lengths, rim pinned at coordinate radius 3. Gold = inside the star, brightness =
physical density / the number you specified. One knob, kappa = 2 pi (rho0, rho~
or rho*) R^2 / 3, sweeps up through all four sheets at once.

Usage:
    python generate_conformal_star.py [--out DIR]
Writes Conformal_Star_gv_node.csv + _gv_ch-map.csv + _gv_ch-tracks.csv into DIR
(default: ./Conformal_Star beside this script).
"""
import argparse
import csv
import os

import numpy as np

import star_physics as sp

# --------------------------------------------------------------------------
# Timeline
# --------------------------------------------------------------------------

KAPPA_START = 0.006           # answer 2 is a bag of gold with a throat here
KAPPA_END = 0.14              # about twice the fold
INTRO = 60                    # frames holding the start
SWEEP = 540                   # frames of linear kappa sweep (18 s at 30 fps)
OUTRO = 90
FRAMES = INTRO + SWEEP + OUTRO


def kappa_track():
    u = np.clip((np.arange(FRAMES) - INTRO) / (SWEEP - 1), 0.0, 1.0)
    return KAPPA_START + (KAPPA_END - KAPPA_START) * u


# --------------------------------------------------------------------------
# Sampling the sheets
# --------------------------------------------------------------------------

R_RIM = 3.0                   # sheets drawn out to coordinate radius 3 (star radius 1)
R_IN = np.linspace(0.0, 1.0, 26)
R_OUT = np.geomspace(1.0, R_RIM, 21)[1:]
R_MER = np.concatenate([R_IN, R_OUT])          # meridian vertices (conformal r)
N_IN = len(R_IN)
RING_R = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0)
N_MERIDIANS = 24
RING_VERTS = 49
FINE = np.concatenate([np.linspace(0.0, 1.0, 801), np.geomspace(1.0, R_RIM, 801)[1:]])


def sheet_frames(case, branch, kappas):
    """Per frame: rho_A and z (rim at z = 0) at the meridian and ring radii,
    density ratio at the interior vertices, throat radius, readouts. None in
    frames with no solution."""
    out, seen = [], {}
    for k in kappas:
        if k in seen:                 # the intro and outro hold one kappa
            out.append(seen[k])
            continue
        if case == "A":
            roots = sp.fold_roots(k)
            if not roots:
                out.append(None)
                seen[k] = None
                continue
            phi, dphi, M = sp.direct_solution(roots[branch])
        else:
            phi, dphi, M = sp.shot_solution(k, sp.POWER[case])
        rA, z = sp.embedding(phi, dphi, FINE)
        z = z - z[-1]
        at = lambda rr: (np.interp(rr, FINE, rA), np.interp(rr, FINE, z))
        d = sp.delivered(case, k, phi, M)
        th = sp.throat(phi, dphi, FINE)
        out.append(dict(mer=at(R_MER), ring=at(np.array(RING_R)),
                        dens=phi(R_IN) ** -sp.DENSITY_POWER[case],
                        throat=None if th is None else at(th), throat_r=th, **d))
        seen[k] = out[-1]
    return out


# --------------------------------------------------------------------------
# Scene plumbing (the lsa_transition_lab pattern)
# --------------------------------------------------------------------------

NODE_COLS = ["id", "type", "parent_id", "branch_level",
             "translate_x", "translate_y", "translate_z",
             "rotate_x", "rotate_y", "rotate_z",
             "scale_x", "scale_y", "scale_z",
             "color_r", "color_g", "color_b", "color_a",
             "geometry", "hide", "topo", "ratio",
             "ch_input_id", "show_text", "rotation_mode", "text"]

GEO_CUBE, GEO_SPHERE, GEO_POINT, GEO_CIRCLE = 1, 3, 22, 24
TOPO_NONE, TOPO_PLOT = 0, 16
CUBE_HALF = 0.57735           # a cube's face is 1/sqrt(3) out at scale 1


def num(v):
    """Compact float: 4 dp, trailing zeros trimmed, never '-0'."""
    s = f"{float(v):.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


class Scene:
    def __init__(self, frames):
        self.frames = frames
        self.rows = []
        self.level = {0: -1}
        self.tracks = []
        self.track_ids = {}
        self.chmap = []
        self.next_ch = 1

    def node(self, parent=0, *, type=5, pos=(0, 0, 0), rot=(0, 0, 0), scale=1.0,
             color=(255, 255, 255, 255), geometry=GEO_SPHERE, hide=0, topo=TOPO_NONE,
             ratio=0.1, ch=0, show_text=0, text=""):
        nid = len(self.rows) + 1
        self.level[nid] = self.level[parent] + 1
        sc = scale if isinstance(scale, (tuple, list)) else (scale,) * 3
        c = tuple(color) + (255,) * (4 - len(color))
        self.rows.append([nid, type, parent, self.level[nid], *pos, *rot, *sc, *c,
                          geometry, hide, topo, ratio, ch, show_text, 0, text])
        return nid

    def track(self, values):
        col = tuple(num(v) for v in values)
        assert len(col) == self.frames
        if col not in self.track_ids:
            self.tracks.append(col)
            self.track_ids[col] = len(self.tracks)
        return self.track_ids[col]

    def channel(self, bindings):
        """bindings: [(values, attribute), ...] -> new channel id."""
        ch = self.next_ch
        self.next_ch += 1
        for values, attr in bindings:
            self.chmap.append((ch, self.track(values), attr))
        return ch

    def write(self, out_dir, stem):
        os.makedirs(out_dir, exist_ok=True)
        # Companions first, node CSV last (Watch-and-Reload safe).
        with open(os.path.join(out_dir, f"{stem}_gv_ch-map.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\r\n")
            w.writerow(["channel_id", "track_id", "attribute"])
            w.writerows(self.chmap)
        with open(os.path.join(out_dir, f"{stem}_gv_ch-tracks.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            fh.write(",".join(["cyclecount"] + [f"ch{i + 1}" for i in range(len(self.tracks))])
                     + "\r\n")
            for f in range(self.frames):
                fh.write(str(f) + "," + ",".join(c[f] for c in self.tracks) + "\r\n")
        with open(os.path.join(out_dir, f"{stem}_gv_node.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\r\n")
            w.writerow(NODE_COLS)
            for row in self.rows:
                w.writerow([num(v) if isinstance(v, float) else v for v in row])


def line(sc, parent, pts, color, label, ratio=0.06, ch_alpha=None):
    """A fixed polyline; zero-scale vertices, label on the parent only."""
    plot = sc.node(parent, geometry=GEO_POINT, topo=TOPO_PLOT, ratio=ratio,
                   color=(255, 255, 255, 0), text=label)
    for p in pts:
        sc.node(plot, pos=tuple(float(v) for v in p), scale=0.0, color=color,
                ch=ch_alpha or 0)
    return plot


def caption(sc, parent, pos, text, show=1, ch=0):
    return sc.node(parent, pos=pos, scale=0.06, geometry=GEO_CIRCLE,
                   color=(200, 200, 220), show_text=show, text=text, ch=ch)


# --------------------------------------------------------------------------
# Layout (turned frame: +X toward the viewer, +Y screen right, +Z up)
# --------------------------------------------------------------------------

RIM_Z = 16.0                  # every rim at this height; answer 2's bag hangs below it
SHEET_Y = (-24.0, -8.0, 8.0, 24.0)

BG = (10, 12, 20)
CASE_COL = {"A": (255, 130, 80), "B": (95, 160, 255), "C": (110, 215, 120)}
GOLD_LO, GOLD_HI = np.array([70, 40, 20], float), np.array([255, 215, 90], float)
SURFACE_COL = (255, 235, 170)
THROAT_COL = (235, 90, 255)


def gold(ratio):
    t = np.clip(ratio, 0.0, 1.0)[..., None]
    return GOLD_LO + (GOLD_HI - GOLD_LO) * t


SHEETS = (
    ("A", 0, "A: fix rho, answer 1",
     "rho = rho0, as typed",
     "the density you typed in, used as is. Matter term phi^+5 in the Lichnerowicz equation"),
    ("A", 1, "A: same rho, answer 2",
     "the 'bag of gold'",
     "the SAME density has a second solution: most of a closed 3-sphere hanging off a "
     "Schwarzschild funnel. Exists only because phi^+5 defeats the maximum principle"),
    ("B", 0, "B: textbook seed rho~",
     "rho = rho~ / phi^8",
     "the standard conformal scaling. Matter term phi^-3: always exactly one solution, but "
     "the physical density is only known after you solve"),
    ("C", 0, "C: densitized rho*",
     "rho = rho* / phi^6",
     "rho* = rho * sqrt(det g): the matter in each coordinate cell, which the conformal factor "
     "cannot change. Matter term phi^-1: always one solution. A toy in the spirit of "
     "Isenberg-Maxwell, not their fluid equations"),
)


def sheet(sc, turn, si, kappas):
    case, branch, title, subtitle, about = SHEETS[si]
    col = CASE_COL[case]
    fr = sheet_frames(case, branch, kappas)
    alive = np.array([f is not None for f in fr])
    first = next(f for f in fr if f is not None)
    hold = lambda f: f if f is not None else first     # positions are moot while invisible
    mer_rA = np.array([hold(f)["mer"][0] for f in fr])  # (F, V)
    mer_z = np.array([hold(f)["mer"][1] for f in fr])
    ring_rA = np.array([hold(f)["ring"][0] for f in fr])
    ring_z = np.array([hold(f)["ring"][1] for f in fr])
    dens = np.array([hold(f)["dens"] for f in fr])      # (F, N_IN)
    alpha = np.where(alive, 255.0, 0.0)
    y0 = SHEET_Y[si]

    root = sc.node(turn, pos=(0, y0, RIM_Z), hide=1, geometry=GEO_POINT,
                   text=f"{title}: {about}")
    # Text draws to the right of its anchor; the anchor sits at the sheet's left.
    caption(sc, turn, (0, y0 - 5.0, RIM_Z + TITLE_DZ), title)
    caption(sc, turn, (0, y0 - 5.0, RIM_Z + TITLE_DZ - LINE_DZ), subtitle)

    a_ch = sc.channel([(alpha, "color_a")]) if not alive.all() else 0

    # Meridians: one shared vertex track set, rotated about the axis.
    vcols = []
    for v in range(len(R_MER)):
        if v < N_IN:
            g = gold(dens[:, v])
            const = np.allclose(g, g[0])
            vcols.append((g, const))
        else:
            vcols.append((None, True))
    for m in range(N_MERIDIANS):
        plot = sc.node(root, rot=(0, 0, 360.0 * m / N_MERIDIANS), geometry=GEO_POINT,
                       topo=TOPO_PLOT, ratio=0.055, color=(255, 255, 255, 0),
                       text=f"{title}: a meridian of the embedding diagram. Distance along it "
                            "is real proper distance in the slice; gold = inside the star")
        for v, r in enumerate(R_MER):
            g, const = vcols[v]
            binds = [(mer_rA[:, v], "translate_x"), (mer_z[:, v], "translate_z")]
            if g is not None and not const:
                binds += [(g[:, 0], "color_r"), (g[:, 1], "color_g"), (g[:, 2], "color_b")]
            if a_ch:
                binds.append((alpha, "color_a"))
            c0 = tuple(int(round(x)) for x in g[0]) if g is not None else col
            sc.node(plot, pos=(float(mer_rA[0, v]), 0.0, float(mer_z[0, v])), scale=0.0,
                    color=(*c0, 255 if alive[0] else 0), geometry=GEO_CUBE,
                    ch=sc.channel(binds))

    # Rings at fixed coordinate radii: a unit circle scaled to the areal radius.
    th = np.linspace(0, 2 * np.pi, RING_VERTS)
    circle = np.c_[np.cos(th), np.sin(th), np.zeros_like(th)]
    for j, rr in enumerate(RING_R):
        surface = rr == 1.0
        rc = SURFACE_COL if surface else (col if rr > 1 else tuple(int(x) for x in GOLD_HI))
        binds = [(ring_rA[:, j], "scale_x"), (ring_rA[:, j], "scale_y"),
                 (ring_z[:, j], "translate_z")]
        plot = sc.node(root, pos=(0, 0, float(ring_z[0, j])),
                       scale=(float(ring_rA[0, j]), float(ring_rA[0, j]), 1.0),
                       geometry=GEO_POINT, topo=TOPO_PLOT, ratio=0.11 if surface else 0.05,
                       color=(255, 255, 255, 0), ch=sc.channel(binds),
                       text=(f"{title}: the star's surface, coordinate radius r = 1. Its "
                             "circumference / 2 pi is the areal radius" if surface else
                             f"{title}: the circle at coordinate radius r = {rr:g}"))
        for p in circle:
            sc.node(plot, pos=tuple(p), scale=0.0, geometry=GEO_CUBE,
                    color=(*rc, 255 if alive[0] else 0), ch=a_ch)

    info = dict(alive=alive, frames=fr)

    # The throat (a minimal surface = an apparent horizon), where one exists.
    th_alive = np.array([f is not None and f["throat"] is not None for f in fr])
    if th_alive.any():
        trA = np.array([f["throat"][0] if t else 1.0 for f, t in zip(fr, th_alive)])
        tz = np.array([f["throat"][1] if t else 0.0 for f, t in zip(fr, th_alive)])
        ta = np.where(th_alive, 255.0, 0.0)
        ta_ch = sc.channel([(ta, "color_a")])
        plot = sc.node(root, pos=(0, 0, float(tz[0])), scale=(float(trA[0]), float(trA[0]), 1),
                       geometry=GEO_POINT, topo=TOPO_PLOT, ratio=0.16,
                       color=(255, 255, 255, 0),
                       ch=sc.channel([(trA, "scale_x"), (trA, "scale_y"), (tz, "translate_z")]),
                       text="the throat: a minimal surface. In time-symmetric data that is an "
                            "apparent horizon, so this star is already inside a black hole")
        for p in circle:
            sc.node(plot, pos=tuple(p), scale=0.0, geometry=GEO_CUBE,
                    color=(*THROAT_COL, 255 if th_alive[0] else 0), ch=ta_ch)
        caption(sc, root, (0, float(trA[0]) + 0.3, float(tz[0])), "throat = horizon",
                ch=sc.channel([(th_alive.astype(float), "show_text"),
                               (trA + 0.3, "translate_y"), (tz, "translate_z")]))
        info["throat_frames"] = int(th_alive.sum())

    if case == "A" and branch == 0:
        caption(sc, root, (0, -5.0, -1.2), "A: NO SOLUTION. This density is too much",
                show=0, ch=sc.channel([((~alive).astype(float), "show_text")]))

    for key in ("density_ratio", "rest_ratio", "adm"):
        info[key] = np.array([f[key] if f is not None else np.nan for f in fr])
    return info


# --------------------------------------------------------------------------
# The backdrop: three small plots against the knob, one per question
# --------------------------------------------------------------------------

WALL_X = -16.0                # backdrop distance behind the sheets
WALL_Z = RIM_Z + 7.0
PLOT_W = 16.0                 # kappa 0 .. KAPPA_END across each plot
PLOT_H = 10.0
PLOT_Y = (-21.0, 0.0, 21.0)
TITLE_DZ = 5.0                # sheet title height above the rim
LINE_DZ = 1.5                 # line spacing for stacked captions
AXIS = (120, 125, 150, 220)
LOGM_LO, LOGM_HI = -2.0, 0.5
DENSITY_HI = 1.25             # top of the density plot
MATTER_HI = 4.0               # top of the matter plot (answer 1 reaches 3.5)


def kappa_y(k):
    return PLOT_W * (np.asarray(k, float) / KAPPA_END - 0.5)


def plot_frame(sc, wall, y0, title, yticks, about):
    """An empty plot: axes, ticks, title. Returns its holder (local y = kappa_y)."""
    p = sc.node(wall, pos=(0.0, y0, 0.0), hide=1, geometry=GEO_POINT, text=f"plot: {about}")
    x0, x1 = -PLOT_W / 2, PLOT_W / 2
    line(sc, p, [(0, x0, PLOT_H), (0, x0, 0), (0, x1, 0)], AXIS, f"{title}: axes", ratio=0.05)
    caption(sc, p, (0, x0 - 0.3, PLOT_H + 1.2), title)
    for z, lab in yticks:
        line(sc, p, [(0, x0 - 0.3, z), (0, x0 + 0.3, z)], AXIS, f"{title}: {lab}", ratio=0.05)
        caption(sc, p, (0, x0 - 0.6 - 0.45 * len(lab), z), lab)
    for k in (0.05, 0.1):
        y = float(kappa_y(k))
        line(sc, p, [(0, y, -0.3), (0, y, 0.3)], AXIS, f"kappa = {k:g}", ratio=0.05)
        caption(sc, p, (0, y - 0.9, -1.3), f"{k:g}")
    fy = float(kappa_y(sp.KAPPA_MAX))
    line(sc, p, [(0.02, fy, 0), (0.02, fy, PLOT_H)], (*CASE_COL["A"], 90),
         f"the fold, kappa_max = 5^5 / 6^6 = {sp.KAPPA_MAX:.4f}: A has no solution to the right",
         ratio=0.04)
    return p


def curve(sc, p, k, v, case, about, ratio=0.1):
    ok = np.flatnonzero(np.isfinite(v))
    ok = np.unique(np.r_[ok[::max(1, len(ok) // 120)], ok[-1]])   # ~120 vertices, ends kept
    line(sc, p, np.c_[np.zeros(len(ok)), kappa_y(k[ok]), v[ok]], (*CASE_COL[case], 255),
         about, ratio=ratio)


def backdrop(sc, wall, kappas, infos):
    sweep = slice(INTRO, INTRO + SWEEP)
    ks = kappas[sweep]
    to_logm = lambda m: PLOT_H * (np.log10(np.maximum(m, 1e-9)) - LOGM_LO) / (LOGM_HI - LOGM_LO)
    to_dens = lambda v: PLOT_H * np.asarray(v) / DENSITY_HI
    to_matter = lambda v: PLOT_H * np.asarray(v) / MATTER_HI
    plots = []

    # 1. Which solutions exist: ADM mass (log).
    p = plot_frame(sc, wall, PLOT_Y[0], "solutions: ADM mass m / R",
                   [(float(to_logm(m)), f"{m:g}") for m in (0.01, 0.1, 1.0)],
                   "the ADM mass (what a distant orbit weighs) of every solution, log scale")
    s_hi = sp.fold_roots(KAPPA_START)[1]
    s = np.geomspace(1e-3, s_hi, 400)
    kA = s / (1 + s) ** 6
    keep = to_logm(2 * s) >= 0
    curve(sc, p, kA[keep], to_logm(2 * s[keep]), "A",
          "A: m = 2 s against kappa = s / (1 + s)^6. A fold: left of it two solutions for "
          "one density, right of it none")
    for si in (2, 3):
        curve(sc, p, ks, to_logm(infos[si]["adm"][sweep]), SHEETS[si][0],
              f"{SHEETS[si][0]}: exactly one solution for every kappa")
    caption(sc, p, (0, float(kappa_y(sp.KAPPA_MAX)) + 0.3, float(to_logm(0.4)) + 0.6), "fold")
    plots.append((p, "adm", to_logm))

    # 2. Did you get the density you asked for?
    p = plot_frame(sc, wall, PLOT_Y[1], "central density: got / asked",
                   [(float(to_dens(v)), f"{v:g}") for v in (0.0, 0.5, 1.0)],
                   "physical central density divided by the number you typed in")
    for si in (0, 2, 3):
        curve(sc, p, ks, to_dens(infos[si]["density_ratio"][sweep]), SHEETS[si][0],
              f"{SHEETS[si][0]}: central density got / asked")
    plots.append((p, "density_ratio", to_dens))

    # 3. Did you get the amount of matter you asked for?
    p = plot_frame(sc, wall, PLOT_Y[2], "matter in the star: got / asked",
                   [(float(to_matter(v)), f"{v:g}") for v in (0.0, 1.0, 2.0, 3.0)],
                   "rest mass in the star divided by (the number you typed in) x (coordinate "
                   "volume 4 pi R^3 / 3)")
    for si in (0, 2, 3):
        curve(sc, p, ks, to_matter(infos[si]["rest_ratio"][sweep]), SHEETS[si][0],
              f"{SHEETS[si][0]}: matter got / asked")
    a2 = infos[1]["rest_ratio"]
    caption(sc, p, (0, -PLOT_W / 2 - 1.0, -2.8),
            f"A answer 2: x{np.nanmin(a2):.0f} to x{np.nanmax(a2):.0f}, off the top")
    caption(sc, p, (0, -PLOT_W / 2 - 1.0, -2.8 - LINE_DZ), "C: exactly 1, always")
    plots.append((p, "rest_ratio", to_matter))

    # "Exactly what you asked for" lines, the cursor, and the moving dots.
    yk = kappa_y(kappas)
    for pi, (p, key, f) in enumerate(plots):
        if key != "adm":
            line(sc, p, [(0.01, -PLOT_W / 2, float(f(1.0))), (0.01, PLOT_W / 2, float(f(1.0)))],
                 (255, 255, 255, 110), "exactly what you asked for", ratio=0.05)
        cur = sc.node(p, geometry=GEO_POINT, topo=TOPO_PLOT, ratio=0.05,
                      color=(255, 255, 255, 0), text="the knob's current value")
        for z in (0.0, PLOT_H):
            sc.node(cur, pos=(0.04, float(yk[0]), z), scale=0.0, geometry=GEO_CUBE,
                    color=(230, 230, 240, 150), ch=sc.channel([(yk, "translate_y")]))
        for si, info in enumerate(infos):
            if key != "adm" and si == 1 and key == "density_ratio":
                continue                  # identical to answer 1's dot
            v = info[key]
            alive = np.isfinite(v)
            z = np.clip(f(np.where(alive, v, 1.0)), 0.0, PLOT_H)
            binds = [(yk, "translate_y"), (z, "translate_z")]
            if not alive.all():
                r = np.where(alive, DOT_R, 0.0)
                binds += [(r, "scale_x"), (r, "scale_y"), (r, "scale_z")]
            sc.node(p, pos=(0.1, float(yk[0]), float(z[0])),
                    scale=DOT_R if alive[0] else 0.0, geometry=GEO_SPHERE,
                    color=(*CASE_COL[SHEETS[si][0]], 255), ch=sc.channel(binds),
                    text=f"{SHEETS[si][2]}: right now")
    caption(sc, wall, (0, PLOT_Y[0] - PLOT_W / 2 - 1.0, -2.8),
            "across: kappa = 2 pi rho R^2 / 3, typed into A, B, C")


DOT_R = 0.32

LEGEND = (
    "ONE STAR, THREE WAYS TO ASK FOR IT: a ball of dust, momentarily at rest, in general relativity",
    "Each sheet is the space around the star as a rubber sheet, with true proper lengths. "
    "Gold = star; brighter = denser.",
    "A fixes the physical density (matter term phi^+5): two answers for one star; they merge "
    "at the fold, then none.",
    "B, the textbook rescaling (phi^-3), and C, densitized (phi^-1): one answer for any amount "
    "of matter.",
    "But only A delivers the density you typed in, and only C the matter. B delivers neither.",
    "C is a toy in the spirit of Isenberg-Maxwell's conformally invariant matter, not their "
    "perfect-fluid equations.",
)


def build(out_dir):
    kappas = kappa_track()
    sc = Scene(FRAMES)
    sc.node(0, type=0, color=(*BG, 255), geometry=GEO_POINT, hide=1, text="World - background")
    turn = sc.node(0, rot=(0, 0, 45), hide=1, geometry=GEO_POINT,
                   text="frame turned to the default camera's azimuth (45)")
    infos = [sheet(sc, turn, si, kappas) for si in range(len(SHEETS))]
    wall = sc.node(turn, pos=(WALL_X, 0.0, WALL_Z), rot=(0, -25, 0), hide=1,
                   geometry=GEO_POINT,
                   text="backdrop wall - leaned back to the default camera's elevation (25)")
    backdrop(sc, wall, kappas, infos)
    top = PLOT_H + 3.4 + LINE_DZ * (len(LEGEND) - 1)
    for i, txt in enumerate(LEGEND):
        caption(sc, wall, (0, PLOT_Y[0] - PLOT_W / 2 - 1.0, top - LINE_DZ * i), txt)

    stem = "Conformal_Star"
    sc.write(out_dir, stem)
    fold_frame = INTRO + int(np.ceil((sp.KAPPA_MAX - KAPPA_START) / (KAPPA_END - KAPPA_START)
                                     * (SWEEP - 1)))
    print(f"kappa {KAPPA_START} -> {KAPPA_END}; fold kappa_max = {sp.KAPPA_MAX:.5f} "
          f"at frame ~{fold_frame}")
    for si, info in enumerate(infos):
        t = SHEETS[si][2]
        extra = f", throat in {info['throat_frames']} frames" if "throat_frames" in info else ""
        a = info["alive"]
        print(f"  {t:24s} solution in {a.sum():3d}/{FRAMES} frames{extra}; "
              f"density ratio {np.nanmin(info['density_ratio']):.3f}.."
              f"{np.nanmax(info['density_ratio']):.3f}, matter ratio "
              f"{np.nanmin(info['rest_ratio']):.3f}..{np.nanmax(info['rest_ratio']):.3f}")
    print(f"{len(sc.rows)} nodes, {len(sc.tracks)} tracks, {sc.next_ch - 1} channels, "
          f"{FRAMES} frames -> {out_dir}")
    return infos


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                   "Conformal_Star"))
    args = ap.parse_args()
    build(args.out)
