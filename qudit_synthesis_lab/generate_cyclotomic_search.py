"""
The cyclotomic lattice search, drawn in GlyphViz: how a ququint (d = 5)
Clifford+T compiler finds a gate entry close to a target phase.

An illustration for Nguyen, Bregman & Nema's AMS talk "Synthesis of
Single-Qudit Circuits in Dimensions 3 and 5". See qudit_math.py for the
mathematics; in short:

  * Every entry of a gate the ququint Clifford+T menu can build is
    u / sqrt(5)^k with u = a0 + a1 zeta + a2 zeta^2 + a3 zeta^3 in Z[zeta5]:
    four integers, so the candidates form a 4-D lattice. k is the LEVEL.
  * u has two essentially different complex values: sigma1(u), the number
    the gate uses, and its Galois TWIN sigma2(u) (zeta -> zeta^2). The
    column must be a unit vector under both, so the twin must also fit in
    the unit disc. That is the hidden constraint that makes the search hard.
  * To be within eps of the phase exp(i theta), the entry must be near the
    target AND almost exactly unit length (the rest of the column carries the
    shortfall): a thin SLIVER of the disc, area (2/3) eps^3.
  * Each level makes the lattice 25x denser (5 per complex plane), so the
    level needed grows like log(1/eps): 2.15 levels per decade of precision.

Panels:
    back wall, left    every LEGAL entry (twin in its disc) at levels 0, 1, 2
                       -- 11, 111, 2251 -- filling the unit disc
    front, right       the zoom window around the target. Floor = the entry's
                       value; height = the twin's size r, compressed by the
                       HCS map r / (1 + r) (Jeff Sale's hyperdimensional
                       coordinate system, after Springer): the r = 1 ceiling
                       sits at half height and r = infinity at the top, so
                       the whole unbounded lattice fits in a finite column.
                       The gold slot is the sliver; a candidate is a point
                       inside the slot AND under the ceiling.
    back wall, middle  the twin plane for the candidates; the completed column
                       as squared lengths, summing to 1 in BOTH embeddings
    back wall, right   the ladder: level needed vs precision, 100 random
                       targets per eps (ensemble_cyclotomic_ladder.py)

Usage:
    python generate_cyclotomic_search.py [--out DIR]
"""
import argparse
import csv
import os
import sys
from pathlib import Path

import numpy as np

import qudit_math as qm
from scene_kit import (CUBE_HALF, GEO_CUBE, GEO_POINT, GEO_SPHERE, GEO_STAR,
                       LAYER_COLORS, Scene, caption, circle_pts, cloud, line, stage_track)

HERE = Path(__file__).resolve().parent

THETA = 1.0                   # target phase exp(i theta): one radian, 57.3 degrees
EPS = 0.1                     # column error allowed
LEVELS = (0, 1, 2)            # level 2 is the first with a candidate (2 of them)

# Timeline (30 fps).
F_LEVEL = (30, 150, 270)      # each level's points appear
F_HIT = 360                   # the candidates light up
F_COL = 450                   # the completed column appears
FRAMES = 630

BG = (10, 12, 22)
GOLD = (255, 200, 60)
TEAL = (70, 210, 200)
GUIDE = (110, 115, 145)
FAINT = (80, 84, 110)

# --------------------------------------------------------------------------
# Layout (turn frame: +X toward the viewer, +Y screen right, +Z up)
# --------------------------------------------------------------------------

WALL_X, WALL_Z = -6.0, 0.0    # the leaned backdrop wall
B0 = (2.0, 0.0, 0.0)          # zoom column: floor centre
W = 0.12                      # zoom window half-width (plane-1 units)
FS = 6.5                      # floor half-size (world)
S = FS / W                    # plane-1 units -> world on the floor
H = 8.0                       # column height: r = infinity
R_CAP = 6.0                   # twins drawn up to size 6 (height 6.9)

A0 = (-17.0, 9.0)             # wall: the full-disc panel centre (y, z)
RA = 6.0
T0 = (14.0, 16.5)             # wall: the twin-plane disc centre
RT = 2.4
BAR_Y, BAR_Z, BAR_L = 9.5, 9.6, 7.0     # wall: the completed-column bars
LAD0 = (15.5, -0.5)          # wall: the ladder's origin (y, z)
LAD_W, LAD_H = 11.0, 6.5
LAD_KMAX = 8.0
LEGEND_Z = 25.0


def hcs(r):
    """Jeff Sale's HCS compactification of a size r >= 0 to a height:
    theta = 180 r / (1 + r) degrees, read here as a fraction of H."""
    return H * r / (1.0 + r)


def zoom_d(w):
    """Plane-1 value(s) -> offset from the target in the target's own frame:
    real part = outward (radial), imaginary part = along the circle."""
    return (np.asarray(w) - np.exp(1j * THETA)) * np.exp(-1j * THETA)


def floor_pos(w, h=0.0):
    d = zoom_d(w)
    return np.stack(np.broadcast_arrays(-S * d.imag, S * d.real, h), -1)


def wall_pos(center, radius, w, x=0.0):
    w = np.asarray(w)
    return np.stack(np.broadcast_arrays(x, center[0] + radius * w.real,
                                        center[1] + radius * w.imag), -1)


SUP = str.maketrans("23", "²³")


def fmt_u(u):
    """Coefficients (a0..a3) -> '2 + 2ζ + 2ζ² - 2ζ³'."""
    terms = []
    for j, a in enumerate(int(v) for v in u):
        if a == 0:
            continue
        mag = "" if (abs(a) == 1 and j) else str(abs(a))
        z = "" if j == 0 else ("ζ" + ("" if j == 1 else str(j).translate(SUP)))
        terms.append(("-" if a < 0 else "+", mag + z))
    if not terms:
        return "0"
    s = ("-" if terms[0][0] == "-" else "") + terms[0][1]
    for sign, t in terms[1:]:
        s += f" {sign} {t}"
    return s


def fmt_real(mn):
    """(m, n) -> 'm + ng' for an element of Z[phi], g = zeta + zeta^4."""
    m, n = mn
    if n == 0:
        return str(m)
    g = "g" if abs(n) == 1 else f"{abs(n)}g"
    return (f"{m} {'+' if n > 0 else '-'} {g}" if m else ("-" if n < 0 else "") + g)


def fmt_c(w):
    return f"{w.real:.4f} {'+' if w.imag >= 0 else '-'} {abs(w.imag):.4f}i"


def level_name(k):
    return "u" if k == 0 else ("u/√5" if k == 1 else f"u/√5^{k}" if k % 2
                               else f"u/{5 ** (k // 2)}")


def dim(c, f=0.42):
    return tuple(int(v * f) for v in c)


def hide_from(frame):
    """hide track: 1 before `frame`, 0 from it on."""
    return 1.0 - stage_track(FRAMES, frame)


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

def _keys(y1, y2):
    return {(round(a.real, 7), round(a.imag, 7), round(b.real, 7), round(b.imag, 7))
            for a, b in zip(y1, y2)}


def new_points(k, center, rho, R, seen):
    """Level-k lattice points in the region not already present at a lower
    level (every level contains the previous one: sqrt 5 is in the ring)."""
    A, y1, y2 = qm.enumerate_box(k, center, rho, R)
    keep = np.array([(round(a.real, 7), round(a.imag, 7), round(b.real, 7), round(b.imag, 7))
                     not in seen for a, b in zip(y1, y2)], bool)
    seen |= _keys(y1, y2)
    return A[keep], y1[keep], y2[keep]


def read_ladder():
    path = HERE / "cyclotomic_ladder.csv"
    if not path.exists():
        raise SystemExit(f"{path.name} missing: run ensemble_cyclotomic_ladder.py first")
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return {k: np.array([float(r[k]) for r in rows]) for k in rows[0]}


# --------------------------------------------------------------------------
# Panels
# --------------------------------------------------------------------------

def zoom_column(sc, turn, cands):
    z = np.exp(1j * THETA)
    col = sc.node(turn, pos=B0, hide=1, geometry=GEO_POINT,
                  text="zoom column: floor = the entry's value near the target, "
                       "height = its twin's size (HCS-compressed)")

    # Box edges, floor square, ceiling square.
    for zc, lab, c in ((0.0, "floor", GUIDE), (hcs(1.0), "ceiling: twin size 1", GOLD),
                       (H, "top: twin size infinity", FAINT)):
        line(sc, col, [(FS, -FS, zc), (FS, FS, zc), (-FS, FS, zc), (-FS, -FS, zc), (FS, -FS, zc)],
             (*c, 200 if zc else 160), f"zoom column {lab}", ratio=0.05 if zc != H else 0.03)
    for xs, ys in ((FS, -FS), (FS, FS), (-FS, FS), (-FS, -FS)):
        line(sc, col, [(xs, ys, 0.0), (xs, ys, H)], (*FAINT, 150),
             "zoom column edge", ratio=0.03)
    for t in np.linspace(-FS, FS, 5)[1:-1]:
        line(sc, col, [(t, -FS, hcs(1.0)), (t, FS, hcs(1.0))], (*GOLD, 70),
             "ceiling (twin size 1): entries above it cannot be in a unitary", ratio=0.03)
        line(sc, col, [(-FS, t, hcs(1.0)), (FS, t, hcs(1.0))], (*GOLD, 70),
             "ceiling (twin size 1): entries above it cannot be in a unitary", ratio=0.03)

    # HCS height axis at the near-left corner.
    ax = (FS + 0.6, -FS - 0.6)
    line(sc, col, [(*ax, 0.0), (*ax, H)], (230, 230, 240, 230),
         "height axis: twin size r drawn at H r / (1 + r) -- the HCS compression", ratio=0.05)
    for r in (0.0, 0.5, 1.0, 2.0, 4.0):
        h = hcs(r)
        line(sc, col, [(ax[0], ax[1] - 0.35, h), (ax[0], ax[1] + 0.35, h)],
             (230, 230, 240, 230), f"height tick: twin size {r:g}", ratio=0.05)
        caption(sc, col, (ax[0], ax[1] - 1.5, h), f"{r:g}", show=1)
    caption(sc, col, (ax[0], ax[1] - 1.5, H), "∞")
    caption(sc, col, (ax[0], ax[1] - 1.5, H + 1.6), "twin size, HCS r/(1+r)")

    # Unit-circle arc, eps-circle, sliver (floor and ceiling), target.
    a_lim = 1.05 * W
    arc = np.exp(1j * (THETA + np.linspace(-a_lim, a_lim, 41)))
    line(sc, col, floor_pos(arc), (230, 230, 240, 220),
         "the unit circle |entry| = 1 (an entry cannot be longer)", ratio=0.06)
    ring = z + EPS * np.exp(1j * np.linspace(0, 2 * np.pi, 73))
    line(sc, col, floor_pos(ring), (*FAINT, 220),
         f"entries within {EPS} of the target -- close, but most are too short to "
         "finish a unit column", ratio=0.04)
    a0 = np.arccos(1 - EPS ** 2 / 2)
    sliv = np.exp(1j * (THETA + np.linspace(-a0, a0, 33)))
    sliv = np.r_[sliv, sliv[0]]
    for h, lab in ((0.0, "floor"), (hcs(1.0), "ceiling")):
        line(sc, col, floor_pos(sliv, h), (*GOLD, 255),
             f"the sliver ({lab}): column error sqrt(2 - 2 Re(entry conj(target))) <= {EPS}",
             ratio=0.09)
    for w in (sliv[0], sliv[16], sliv[32]):
        line(sc, col, [floor_pos(w), floor_pos(w, hcs(1.0))], (*GOLD, 200),
             "the slot: sliver below the ceiling = every acceptable entry", ratio=0.06)
    sc.node(col, pos=(0.0, 0.0, 0.0), scale=0.32, geometry=GEO_STAR, color=(255, 255, 255),
            text=f"the target entry exp(i {THETA:g}) = {fmt_c(z)}")
    caption(sc, col, (0.0, 0.5, -0.6), "target e^i")
    caption(sc, col, (-FS, 0.4, hcs(1.0) + 0.4), f"gold slot: error ≤ {EPS}")
    caption(sc, col, (FS, FS + 0.4, -0.3), "↕ along the circle")
    caption(sc, col, (FS, FS - 2.6, -0.9), "outward →")

    # Points: per level, under / over the ceiling.
    seen = set()
    counts = []
    for k in LEVELS:
        A, y1, y2 = new_points(k, z, W * np.sqrt(2), R_CAP, seen)
        d = zoom_d(y1)
        inwin = (np.abs(d.real) <= W) & (np.abs(d.imag) <= W)
        A, y1, y2 = A[inwin], y1[inwin], y2[inwin]
        r = np.abs(y2)
        legal = (r <= 1 + qm.TOL) & (np.abs(y1) <= 1 + qm.TOL)
        pos = floor_pos(y1, hcs(r))
        for mask, tag, c, size in ((legal, "under the ceiling", LAYER_COLORS[k], 0.42 - 0.1 * k),
                                   (~legal, "over the ceiling", dim(LAYER_COLORS[k]),
                                    0.3 - 0.07 * k)):
            if not mask.any():
                continue
            labels = [f"level {k} entry {level_name(k)}, u = {fmt_u(a)}: value {fmt_c(v)}, "
                      f"twin size {abs(t):.3f} ({'legal' if m else 'too big: illegal'})"
                      for a, v, t, m in zip(A[mask], y1[mask], y2[mask], legal[mask])]
            cloud(sc, col, pos[mask], [(*c, 255)] * int(mask.sum()), labels, size,
                  f"level {k} entries in the zoom window, {tag}: {int(mask.sum())} points",
                  ch=sc.channel([(hide_from(F_LEVEL[k]), "hide")]))
        counts.append((len(A), int(legal.sum())))

    # The candidates: glyphs that light up at F_HIT.
    f = np.arange(FRAMES)
    pulse = np.where(f >= F_HIT, 0.34 * (1 + 0.8 * np.exp(-(f - F_HIT) / 12.0)), 0.0)
    for i, (u, y1, y2, err) in enumerate(cands):
        sc.node(col, pos=tuple(floor_pos(y1, hcs(abs(y2)))), scale=0.0, geometry=GEO_SPHERE,
                color=(*GOLD, 255),
                ch=sc.channel([(pulse, "scale_x"), (pulse, "scale_y"), (pulse, "scale_z"),
                               (stage_track(FRAMES, F_HIT) if i == 0 else np.zeros(FRAMES),
                                "show_text")]),
                text=(f"CANDIDATE: error {err:.3f}" if i == 0 else
                      f"candidate {i + 1}: u = {fmt_u(u)}, entry u/5 = {fmt_c(y1)}, "
                      f"error {err:.3f}, twin size {abs(y2):.2f}"))
    return counts


def full_disc(sc, wall, cands):
    """Every legal entry, level by level, on the whole unit disc."""
    z = np.exp(1j * THETA)
    caption(sc, wall, (0, A0[0] - RA, A0[1] + RA + 1.6),
            "EVERY LEGAL ENTRY (twin inside its disc too)")
    line(sc, wall, wall_pos(A0, RA, np.exp(1j * np.linspace(0, 2 * np.pi, 121)), -0.02),
         (230, 230, 240, 220), "the unit circle of the entry's plane", ratio=0.06)
    for a, b, lab in ((-1.1, 1.1, "real axis"), (-1.1j, 1.1j, "imaginary axis")):
        line(sc, wall, wall_pos(A0, RA, np.array([a, b]), -0.02), (*FAINT, 200),
             f"entry plane: {lab}", ratio=0.03)
    caption(sc, wall, tuple(wall_pos(A0, RA, 1.12 + 0.05j)), "Re")
    caption(sc, wall, tuple(wall_pos(A0, RA, 0.05 + 1.14j)), "Im")
    seen = set()
    totals = []
    for k in LEVELS:
        A, y1, y2 = new_points(k, 0j, 1.0, 1.0, seen)
        legal = np.abs(y1) <= 1 + qm.TOL
        A, y1, y2 = A[legal], y1[legal], y2[legal]
        labels = [f"level {k} legal entry {level_name(k)}, u = {fmt_u(a)}: value {fmt_c(v)}, "
                  f"twin size {abs(t):.3f}" for a, v, t in zip(A, y1, y2)]
        cloud(sc, wall, wall_pos(A0, RA, y1), [(*LAYER_COLORS[k], 255)] * len(A), labels,
              (0.4, 0.25, 0.14)[k], f"level {k}: {len(A)} new legal entries",
              ch=sc.channel([(hide_from(F_LEVEL[k]), "hide")]))
        totals.append(len(A) + (totals[-1] if totals else 0))
    # The zoom window and the target.
    corners = z + np.array([W + W * 1j, -W + W * 1j, -W - W * 1j, W - W * 1j, W + W * 1j]) * z
    line(sc, wall, wall_pos(A0, RA, corners, 0.03), (255, 255, 255, 230),
         "the zoom window drawn in front (right)", ratio=0.05)
    sc.node(wall, pos=tuple(wall_pos(A0, RA, z, 0.06)), scale=0.18, geometry=GEO_STAR,
            color=(255, 255, 255), text=f"the target exp(i {THETA:g})")
    caption(sc, wall, tuple(wall_pos(A0, RA, z * 1.22)), "zoom")
    for i, (u, y1, y2, err) in enumerate(cands):
        sc.node(wall, pos=tuple(wall_pos(A0, RA, y1, 0.1)), scale=0.0, geometry=GEO_SPHERE,
                color=(*GOLD, 255),
                ch=sc.channel([(np.where(np.arange(FRAMES) >= F_HIT, 0.16, 0.0), a)
                               for a in ("scale_x", "scale_y", "scale_z")]),
                text=f"candidate {i + 1}: u = {fmt_u(u)}, error {err:.3f}")
    return totals


def twin_plane(sc, wall, cands):
    caption(sc, wall, (0, T0[0] - RT, T0[1] + RT + 1.0), "TWIN PLANE (ζ → ζ²)")
    line(sc, wall, wall_pos(T0, RT, np.exp(1j * np.linspace(0, 2 * np.pi, 97)), -0.02),
         (*GOLD, 220), "the twin's unit disc: a legal entry's twin must land inside", ratio=0.06)
    for a, b, lab in ((-1.15, 1.15, "real axis"), (-1.15j, 1.15j, "imaginary axis")):
        line(sc, wall, wall_pos(T0, RT, np.array([a, b]), -0.02), (*FAINT, 200),
             f"twin plane: {lab}", ratio=0.03)
    for i, (u, y1, y2, err) in enumerate(cands):
        sc.node(wall, pos=tuple(wall_pos(T0, RT, y2, 0.1)), scale=0.0, geometry=GEO_SPHERE,
                color=(*GOLD, 255),
                ch=sc.channel([(np.where(np.arange(FRAMES) >= F_HIT, 0.16, 0.0), a)
                               for a in ("scale_x", "scale_y", "scale_z")]),
                text=f"candidate {i + 1}'s twin: {fmt_c(y2)}, size {abs(y2):.3f} -- inside")


def column_bars(sc, wall, best, k):
    """The completed column, as squared lengths, in both embeddings."""
    u, y1, y2, err = best
    parts = qm.complete_column(u, k)
    assert parts is not None
    others = [p for p in parts if p != (0, 0)]
    s2 = 5.0 ** k
    real = [abs(y1) ** 2] + [qm.real_value(p, 1) ** 2 / s2 for p in others]
    twin = [abs(y2) ** 2] + [qm.real_value(p, 2) ** 2 / s2 for p in others]
    assert abs(sum(real) - 1) < 1e-9 and abs(sum(twin) - 1) < 1e-9
    on = stage_track(FRAMES, F_COL)
    names = ["the entry u/5"] + [f"filler {j + 1} = ({fmt_real(p)})/5, g = ζ + ζ⁴"
                                  for j, p in enumerate(others)]
    caption(sc, wall, (0, BAR_Y, BAR_Z + 2.6),
            "THE COLUMN, COMPLETED EXACTLY (squared lengths)", show=0,
            ch=sc.channel([(on, "show_text")]))
    for row, (vals, tag) in enumerate(((real, "real"), (twin, "twin"))):
        z = BAR_Z + 1.5 - 1.5 * row
        y = BAR_Y
        for j, v in enumerate(vals):
            L = BAR_L * v
            c = GOLD if j == 0 else TEAL
            sc.node(wall, pos=(0.0, y + L / 2, z), scale=0.0, geometry=GEO_CUBE,
                    color=(*c, 255),
                    ch=sc.channel([(on * 0.1, "scale_x"), (on * L / (2 * CUBE_HALF), "scale_y"),
                                   (on * 0.5 / (2 * CUBE_HALF), "scale_z")]),
                    text=f"{tag} world: {names[j]} contributes {v:.4f}")
            y += L
        caption(sc, wall, (0, BAR_Y + BAR_L + 0.3, z),
                f"{tag}: " + " + ".join(f"{v:.4f}" for v in vals) + " = 1", show=0,
                ch=sc.channel([(on, "show_text")]))
    return (f"u = {fmt_u(u)}; 25 - |u|² = "
            + " + ".join(f"({fmt_real(p)})²" for p in others) + ", g = ζ + ζ⁴")


def ladder(sc, wall):
    lad = read_ladder()
    x = lambda e: LAD0[0] + LAD_W * (np.log10(1 / np.asarray(e)) - 1) / 2
    y = lambda k: LAD0[1] + LAD_H * np.asarray(k) / LAD_KMAX
    caption(sc, wall, (0, LAD0[0], LAD0[1] + LAD_H + 1.4),
            "HOW DEEP MUST THE SEARCH GO? (100 random targets per ε)")
    line(sc, wall, [(0, x(0.1), y(0)), (0, x(0.001), y(0))], (*GUIDE, 220),
         "ladder x axis: precision eps, log scale", ratio=0.04)
    line(sc, wall, [(0, x(0.1), y(0)), (0, x(0.1), y(LAD_KMAX))], (*GUIDE, 220),
         "ladder y axis: level k needed", ratio=0.04)
    for e in (0.1, 0.01, 0.001):
        line(sc, wall, [(0, x(e), y(0) - 0.25), (0, x(e), y(0) + 0.25)], (*GUIDE, 220),
             f"ladder tick eps = {e:g}", ratio=0.04)
        caption(sc, wall, (0, x(e) - 0.4, y(0) - 0.8), f"ε={e:g}")
    for k in (0, 2, 4, 6, 8):
        line(sc, wall, [(0, x(0.1) - 0.25, y(k)), (0, x(0.1) + 0.25, y(k))], (*GUIDE, 220),
             f"ladder tick level {k}", ratio=0.04)
        caption(sc, wall, (0, x(0.1) - 1.0, y(k)), f"{k}")
    caption(sc, wall, (0, x(0.1) - 2.4, y(LAD_KMAX) + 0.9), "level k")
    line(sc, wall, [(0.02, x(e), y(p)) for e, p in zip(lad["eps"], lad["predicted"])],
         (*TEAL, 230), "predicted: the level where the expected number of candidates "
                       "(2/3) eps^3 pi 25^k / 2.795 reaches 1 -- 2.15 levels per decade",
         ratio=0.06)
    for e, m, q1, q3 in zip(lad["eps"], lad["mean_level"], lad["q1"], lad["q3"]):
        if q3 > q1:
            line(sc, wall, [(0.03, x(e), y(q1)), (0.03, x(e), y(q3))], (255, 255, 255, 140),
                 f"eps {e:.3g}: middle half of the 100 targets, levels {q1:g} to {q3:g}",
                 ratio=0.05)
        sc.node(wall, pos=(0.05, float(x(e)), float(y(m))), scale=0.17, geometry=GEO_SPHERE,
                color=(255, 255, 255), text=f"eps {e:.3g}: mean level needed {m:.2f}")
    sc.node(wall, pos=(0.08, float(x(EPS)), float(y(LEVELS[-1]))), scale=0.26,
            geometry=GEO_STAR, color=(*GOLD, 255),
            text=f"this scene: eps {EPS}, target exp(i {THETA:g}), found at level {LEVELS[-1]}")
    # Fit where the lattice statistics apply: at coarse eps the ten roots of
    # unity (level 0) are often close enough by luck, which drags the means
    # at the left end down.
    fine = lad["eps"] <= 0.032
    slope = np.polyfit(np.log10(1 / lad["eps"][fine]), lad["mean_level"][fine], 1)[0]
    caption(sc, wall, (0, x(0.1), y(0) - 1.9),
            f"measured {slope:.2f} levels per decade (ε ≤ 0.03); predicted 2.15 (teal)")
    caption(sc, wall, (0, x(0.1), y(0) - 2.7),
            "a straight line on a log axis = cost grows like log(1/ε)")
    caption(sc, wall, (0, x(0.1), y(0) - 3.5),
            "left end: a root of unity (level 0) is often already close enough")
    return slope


LEGEND = (
    "THE CYCLOTOMIC SEARCH: a ququint (d = 5) Clifford+T compiler hunting for one gate entry",
    "Buildable entries: u/√5^k, u = a + bζ + cζ² + dζ³, "
    "ζ = e^(2πi/5). Four integers: a 4-D lattice. k = the LEVEL.",
    "Each u has a Galois TWIN (ζ → ζ²). The column must be a unit vector "
    "for both, so the twin must fit in its disc too.",
    "Target: the phase e^i, column error ≤ 0.1. That needs the entry near e^i AND almost "
    "unit length: the gold sliver.",
    "Column height = the twin's size r through the HCS map r/(1+r): ceiling r = 1 at half "
    "height, r = ∞ at the top.",
)


def build(out_dir):
    sc = Scene(FRAMES)
    sc.node(0, type=0, color=(*BG, 255), geometry=GEO_POINT, hide=1, text="World - background")
    turn = sc.node(0, rot=(0, 0, 45), hide=1, geometry=GEO_POINT,
                   text="frame turned to the default camera's azimuth (45)")
    wall = sc.node(turn, pos=(WALL_X, 0.0, WALL_Z), rot=(0, -25, 0), hide=1, geometry=GEO_POINT,
                   text="backdrop wall - leaned back to the default camera's elevation (25)")

    k_hit = None
    for k in range(6):
        A, y1, y2, err = qm.sliver_points(k, THETA, EPS)
        if len(A):
            k_hit = k
            break
    assert k_hit == LEVELS[-1], k_hit
    order = np.argsort(err)
    cands = [(A[i], y1[i], y2[i], err[i]) for i in order]

    counts = zoom_column(sc, turn, cands)
    totals = full_disc(sc, wall, cands)
    twin_plane(sc, wall, cands)
    col_note = column_bars(sc, wall, cands[0], k_hit)
    slope = ladder(sc, wall)

    # Stage captions above the zoom column.
    col_cap = (B0[0] + FS, B0[1] - FS, -1.8)
    stage_text = []
    cum = cum_legal = 0
    for k, (n, legal) in zip(LEVELS, counts):
        cum += n
        cum_legal += legal
        stage_text.append(
            f"LEVEL {k} ({level_name(k)}): {totals[k]} legal on the disc; window {cum} points, "
            f"{cum_legal} under the ceiling, "
            + ("none in the slot" if k < k_hit else f"{len(cands)} IN THE SLOT"))
    for k, txt in enumerate(stage_text):
        end = F_LEVEL[k + 1] if k + 1 < len(LEVELS) else None
        caption(sc, turn, col_cap, txt, show=0,
                ch=sc.channel([(stage_track(FRAMES, F_LEVEL[k], end), "show_text")]))
    caption(sc, turn, (col_cap[0], col_cap[1], col_cap[2] - 0.8),
            f"found at level {k_hit}: {col_note}", show=0,
            ch=sc.channel([(stage_track(FRAMES, F_HIT), "show_text")]))
    for i, txt in enumerate(LEGEND):
        caption(sc, wall, (0, A0[0] - RA, LEGEND_Z - 0.8 * i), txt)

    stem = "Cyclotomic_Search"
    sc.write(out_dir, stem)
    print(f"target exp(i {THETA}), eps {EPS}: first candidates at level {k_hit}: "
          + ", ".join(f"u = {fmt_u(c[0])} err {c[3]:.4f} twin {abs(c[2]):.3f}" for c in cands))
    print(f"zoom window points per level (new, legal): {counts}")
    print(f"ladder slope {slope:.2f} levels/decade")
    print(f"{len(sc.rows)} nodes, {len(sc.tracks)} tracks, {sc.next_ch - 1} channels, "
          f"{FRAMES} frames -> {out_dir}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")      # the Windows console would choke on zeta
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", default=str(HERE / "Cyclotomic_Search"))
    args = ap.parse_args()
    build(args.out)
