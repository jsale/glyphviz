"""
Two Convection Cells: the fluid behind the Lorenz letters, after Shen (2014).

Lorenz's X, Y, Z (and Shen's Y1, Z1) are amplitudes of fixed spatial patterns
in a layer of fluid heated from below (Rayleigh-Benard convection). This scene
draws the fluid itself, rebuilt from those amplitudes, for Lorenz's 3-mode
model and Shen's 5-mode model side by side, at two heating levels:

    r = 25   3DLM chaotic, 5DLM steady       (the paper's Figs. 3a,b and 4)
    r = 35   3DLM chaotic, 5DLM steady       (the paper's Fig. 6d)

Every cell starts from rest with the paper's nudge, Y = 1 (section 2e).

Per row (one model at one r):

    cell        the temperature perturbation theta(x, z, t) as a heat map
                (red warm, blue cool) between a hot lower plate and a cool
                upper plate. The domain is one horizontal wavelength, so it
                holds two counter-rotating rolls. White beads ride the roll's
                streamlines, advected by the model's own velocity field: a
                roll reversal (a lobe switch of the butterfly) is the beads
                turning around.
    dZ/dtau     the paper's Fig. 6: the forcing XY (white) against the
                damping bZ (orange) and, in the 5DLM only, the new nonlinear
                sink XY1 (blue), with a cursor; then a live tug-of-war: XY
                pulls up, bZ + XY1 pull down. Balanced = steady.

Per heating level, a shared phase panel (the paper's Fig. 3): Y/Yc against
Z/Zc for both models, each normalized by its own critical point (eqs. 19 and
21), so both models' steady rolls sit at (+/-1, 1).

Below: a static mode atlas, the four temperature patterns the models add up.

Captions carry ensemble rates from ensemble_shen.json (run ensemble_shen.py
first): one run is an anecdote.

    python generate_convection_cells.py [--out DIR]
"""
import argparse
import json
import os

import numpy as np

import scene_kit as kit
import shen_model as sm

HERE = os.path.dirname(os.path.abspath(__file__))

R_VALUES = (25.0, 35.0)
MODELS = ("3DLM", "5DLM")
T_END = 40.0
DT = 0.001
FRAME_DT = 0.025
SUB = int(round(FRAME_DT / DT))
FRAMES = int(round(T_END / FRAME_DT))        # frame f is tau = f * FRAME_DT
START = np.array([0.0, 1.0, 0.0, 0.0, 0.0])  # the paper's start: Y = 1, all else 0

# ---- layout, board units (x right, y up, z toward the viewer) ----
CELL_S = 2.0                                 # fluid units -> board
CELL_W = sm.WIDTH * CELL_S
NX, NZ = 25, 17                              # heat-map lattice
ROW_PITCH = 2.9
GROUP_PITCH = 7.4
BUDGET_X, BUDGET_W = 9.0, 4.0               # labels are fixed pixels: the cell titles need ~8 units
BARS_X = 13.45
PHASE_CX, PHASE_SX = 18.3, 1.1               # Y/Yc -> board x
PHASE_W = 3.3                                # panel half-width
LIFT = 30.0
BOARD_SCALE = 1.9
BOARD_CENTRE = (10.8, -5.0)                  # board point placed at the wall origin
BOARD_ORIGIN = (0.0, -BOARD_SCALE * BOARD_CENTRE[0], -BOARD_SCALE * BOARD_CENTRE[1])

BG = (10, 12, 22)
COLOR = {"3DLM": (255, 145, 45), "5DLM": (70, 200, 255)}
NAME = {"3DLM": "3DLM, 3 modes", "5DLM": "5DLM, 5 modes"}
C_XY, C_BZ, C_XY1 = (235, 235, 240), (255, 160, 60), (80, 140, 255)
HOT, COLD = (255, 95, 50), (80, 150, 255)
FRAME_COLOR = (110, 120, 160, 140)
TEMP_SAT = 0.5                               # |T - mean| / Delta T at full colour
THETA_STOPS = [(-1.0, (80, 160, 255)), (-0.4, (45, 85, 170)), (0.0, (48, 50, 62)),
               (0.4, (175, 70, 40)), (1.0, (255, 140, 60))]
STREAM_LEVELS = (0.35, 0.8, 1.2)             # |M1| on the drawn streamlines (max sqrt 2)
BEADS_PER_LOOP = 3


def temperature(state, r, x, z):
    """Total temperature / Delta T relative to the layer's mean: the conduction
    profile (hot plate +1/2, cool plate -1/2) plus the perturbation theta."""
    return 0.5 - z + sm.theta(state, r, x, z)


def temp_color(t):
    return kit.lerp_color(THETA_STOPS, t / TEMP_SAT)


def row_base(g, k):
    """Board y of the bottom of row k (0 = 3DLM, 1 = 5DLM) in heating group g."""
    return -g * GROUP_PITCH - k * ROW_PITCH


def simulate(model, r):
    """Fine path (FRAMES * SUB + 1 rows) from the paper's start."""
    return sm.integrate(START, DT, FRAMES * SUB, r, model)


def load_ensemble():
    path = os.path.join(HERE, "ensemble_shen.json")
    if not os.path.exists(path):
        raise SystemExit("ensemble_shen.json missing: run ensemble_shen.py first")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def chaotic_share(ens, model, r):
    i = ens["r"].index(r)
    return ens["models"][model]["chaotic_fraction"][i], ens["n"]


# --------------------------------------------------------------------------
# Streamlines and tracer beads
# --------------------------------------------------------------------------

ROLL_CENTRES = ((sm.WIDTH / 4, 0.5), (3 * sm.WIDTH / 4, 0.5))


def streamline(centre, level, n=120):
    """Closed level set |M1| = level around a roll centre, by bisection along
    rays (|M1| is log-concave in the roll, so it falls monotonically along
    every ray from the centre)."""
    cx, cz = centre
    pts = []
    for phi in np.linspace(0, 2 * np.pi, n, endpoint=False):
        d = np.array([np.cos(phi), np.sin(phi)])
        # the ray leaves the roll's box at t_max
        with np.errstate(divide="ignore"):
            tx = (sm.WIDTH / 4) / abs(d[0]) if d[0] else np.inf
            tz = 0.5 / abs(d[1]) if d[1] else np.inf
        lo, hi = 0.0, min(tx, tz)
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            x, z = cx + mid * d[0], cz + mid * d[1]
            if abs(sm.stream_shape(x, z)) > level:
                lo = mid
            else:
                hi = mid
        pts.append((cx + lo * d[0], cz + lo * d[1]))
    return np.array(pts)


def bead_starts():
    """BEADS_PER_LOOP beads per streamline, evenly spaced by arc length."""
    out = []
    for centre in ROLL_CENTRES:
        for level in STREAM_LEVELS:
            loop = streamline(centre, level, 360)
            seg = np.linalg.norm(np.diff(np.vstack([loop, loop[:1]]), axis=0), axis=1)
            s = np.concatenate([[0], np.cumsum(seg)])
            for k in range(BEADS_PER_LOOP):
                out.append(loop[np.searchsorted(s, s[-1] * k / BEADS_PER_LOOP) % len(loop)])
    return np.array(out)


def advect(fine, p0):
    """Parcel positions at every frame, (FRAMES, n, 2) in fluid units: RK4 in
    the velocity field of psi = C1 X M1, X taken from the fine path (midpoint
    X for the half steps)."""
    X = fine[:, 0]
    p = p0.copy()
    out = np.empty((FRAMES, len(p0), 2))
    out[0] = p

    def v(Xv, q):
        return np.stack(sm.velocity(Xv, q[:, 0], q[:, 1]), axis=1)

    for f in range(1, FRAMES):
        for j in range((f - 1) * SUB, f * SUB):
            Xa, Xm, Xb = X[j], 0.5 * (X[j] + X[j + 1]), X[j + 1]
            k1 = v(Xa, p)
            k2 = v(Xm, p + DT / 2 * k1)
            k3 = v(Xm, p + DT / 2 * k2)
            k4 = v(Xb, p + DT * k3)
            p = p + DT / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        out[f] = p
    return out


# --------------------------------------------------------------------------
# Scene pieces
# --------------------------------------------------------------------------

def lattice():
    """Lattice coordinates from integer indices (identical values for every
    vertex of a row/column: a 7th-decimal mismatch is a hole in the mesh)."""
    xs = [round(i * sm.WIDTH / (NX - 1), 9) for i in range(NX)]
    zs = [round(k / (NZ - 1), 9) for k in range(NZ)]
    return xs, zs


def heat_map(sc, parent, x0, y0, states, r, label):
    """The fluid cell: a Surface lattice whose vertex colours follow the total
    temperature. theta is mirror-symmetric about the cell's centre (cos(l x)
    is), so columns i and NX-1-i share one channel. The plate rows (z = 0, 1)
    never change (theta = 0 there) and are not animated."""
    cell = sc.node(parent, pos=(x0, y0, 0.0), geometry=kit.GEO_POINT, topo=kit.TOPO_SURFACE,
                   ratio=0.05, color=(255, 255, 255, 255), text=label)
    xs, zs = lattice()
    shared = {}
    for k, z in enumerate(zs):
        for i, x in enumerate(xs):
            ch = 0
            t0 = temperature(states[0], r, x, z)
            if 0 < k < NZ - 1:
                key = (min(i, NX - 1 - i), k)
                if key not in shared:
                    t_t = temperature(states.T, r, xs[key[0]], z)
                    rgb = np.array([temp_color(t) for t in t_t])
                    shared[key] = sc.channel([(sc.track(rgb[:, c]), a) for c, a in
                                              enumerate(("color_r", "color_g", "color_b"))])
                ch = shared[key]
            sc.node(cell, pos=(x * CELL_S, z * CELL_S, 0.0), scale=0.0, geometry=kit.GEO_CUBE,
                    color=(*temp_color(t0), 255), ch=ch,
                    text=f"fluid at x = {x:.2f} H, z = {z:.2f} H  [{label}]")
    return cell


def fluid_cell(sc, bd, g, k, model, r, fine, ens):
    y0 = row_base(g, k)
    states = fine[::SUB][:FRAMES]
    share, n = chaotic_share(ens, model, r)
    verdict = (f"chaotic in {share:.0%} of {n} starts" if share > 0
               else f"steady in all {n} starts")
    sc.node(bd, pos=(0.0, y0 + 2.3, 0.05), scale=0.08, geometry=kit.GEO_CIRCLE,
            color=(*COLOR[model], 255), show_text=1, text=f"{NAME[model]}: {verdict}")
    label = f"{model}, r = {r:g}"
    heat_map(sc, bd, 0.0, y0, states, r, f"fluid temperature, {label}")
    kit.bar(sc, bd, CELL_W / 2, y0 - 0.1, y0 - 0.02, CELL_W, (*HOT, 255), depth=0.1,
            text=f"hot lower plate  [{label}]")
    kit.bar(sc, bd, CELL_W / 2, y0 + CELL_S + 0.02, y0 + CELL_S + 0.1, CELL_W, (*COLD, 255),
            depth=0.1, text=f"cool upper plate  [{label}]")

    # Streamlines: the roll's fixed shape (only its speed and sign change).
    for ci, centre in enumerate(ROLL_CENTRES):
        side = "left" if ci == 0 else "right"
        for level in STREAM_LEVELS:
            loop = streamline(centre, level)
            kit.static_plot(sc, bd, [(x0 * CELL_S, y0 + z0 * CELL_S, 0.02) for x0, z0 in loop],
                            (220, 225, 240, 90),
                            f"{side} roll streamline, |M1| = {level}  [{label}]",
                            ratio=0.04, closed=True)
    beads = advect(fine, bead_starts())
    for b in range(beads.shape[1]):
        xyz = np.stack([beads[:, b, 0] * CELL_S, y0 + beads[:, b, 1] * CELL_S,
                        np.full(FRAMES, 0.05)], axis=1)
        sc.node(bd, pos=tuple(xyz[0]), scale=0.055, color=(240, 240, 250, 255),
                ch=kit.pos_channel(sc, xyz),
                text=f"fluid parcel {b + 1}, carried by the roll  [{label}]")


def budget(sc, bd, g, k, model, r, fine, vmax):
    """Fig. 6: the terms of dZ/dtau, plus a live tug-of-war."""
    y0 = row_base(g, k)
    label = f"{model}, r = {r:g}"
    states = fine[::SUB][:FRAMES]
    xy, bz, third = sm.z_budget(states, model)
    terms = [("XY (forcing)", xy, C_XY), ("bZ (damping)", bz, C_BZ)]
    if model == "5DLM":
        terms.append(("XY1 (the new nonlinear sink)", third, C_XY1))
    eq = "dZ/dtau = XY - bZ - XY1" if model == "5DLM" else "dZ/dtau = XY - bZ"
    sc.node(bd, pos=(BUDGET_X + 1.2, y0 + 2.3, 0.05), scale=0.06, geometry=kit.GEO_CIRCLE,
            color=(200, 200, 220, 255), show_text=1, text=eq)
    x1 = BUDGET_X + BUDGET_W
    kit.static_plot(sc, bd, [(BUDGET_X, y0, 0), (x1, y0, 0), (x1, y0 + 2, 0),
                             (BUDGET_X, y0 + 2, 0)], FRAME_COLOR,
                    f"dZ/dtau budget frame: tau 0..{T_END:g} across, 0..{vmax:g} up "
                    f"(early spikes clipped)  [{label}]", ratio=0.03, closed=True)

    def to_y(v):
        return y0 + 2.0 * np.clip(v / vmax, 0.0, 1.0)

    tx = BUDGET_X + BUDGET_W * np.arange(FRAMES) * FRAME_DT / T_END
    idx = np.arange(0, FRAMES, 2)
    for name, v, col in terms:
        kit.static_plot(sc, bd, [(tx[i], to_y(v[i]), 0.01) for i in idx], (*col, 230),
                        f"{name} over time  [{label}]", ratio=0.08)
        pts = np.stack([tx, to_y(v), np.full(FRAMES, 0.03)], axis=1)
        sc.node(bd, pos=tuple(pts[0]), scale=0.05, color=(*col, 255),
                ch=kit.pos_channel(sc, pts), text=f"{name} now  [{label}]")
    cur = sc.channel([(sc.track(tx), "translate_x")])
    kit.bar(sc, bd, tx[0], y0, y0 + 2.0, 0.015, (200, 200, 220, 120), ch=cur,
            text=f"now  [{label}]")

    # Tug-of-war: XY up from the mid line; bZ, then XY1, down from it.
    mid = y0 + 1.0
    kit.static_plot(sc, bd, [(BARS_X - 0.2, mid, 0), (BARS_X + 0.2, mid, 0)],
                    (200, 200, 220, 200), f"tug-of-war balance line  [{label}]", ratio=0.05)
    up = mid + np.clip(xy / vmax, 0, 1.0)
    d1 = mid - np.clip(bz / vmax, 0, 1.0)
    d2 = np.maximum(d1 - np.clip(third / vmax, 0, 1.0), y0) if model == "5DLM" else d1
    line = np.full(FRAMES, mid)
    pulls = [("XY pulls Z up", line, up, C_XY), ("bZ pulls Z down", d1, line, C_BZ)]
    if model == "5DLM":
        pulls.append(("XY1 pulls Z down too", d2, d1, C_XY1))
    for name, a, b, col in pulls:
        kit.bar(sc, bd, BARS_X, a[0], b[0], 0.16, (*col, 255),
                ch=kit.bar_channel(sc, a, b, 0.16),
                text=f"{name} (bar length = term size; balanced = steady)  [{label}]")


def phase_panel(sc, bd, g, r, fines, comets):
    """Fig. 3: Y/Yc vs Z/Zc for both models, each normalized by its own
    critical point."""
    top, bottom = row_base(g, 0) + 2.0, row_base(g, 1)
    sy = (top - bottom) / 2.0                  # Z/Zc 0..2 fills the panel
    sc.node(bd, pos=(PHASE_CX - PHASE_W, top + 0.3, 0.05), scale=0.06,
            geometry=kit.GEO_CIRCLE, color=(200, 200, 220, 255), show_text=1,
            text="Y/Yc across, Z/Zc up: both models")
    l, rgt = PHASE_CX - PHASE_W, PHASE_CX + PHASE_W
    kit.static_plot(sc, bd, [(l, bottom, 0), (rgt, bottom, 0), (rgt, top, 0), (l, top, 0)],
                    FRAME_COLOR, f"phase panel frame: Y/Yc -3..3, Z/Zc 0..2, r = {r:g}",
                    ratio=0.03, closed=True)
    for yv in (-1.0, 0.0, 1.0):
        kit.static_plot(sc, bd, [(PHASE_CX + PHASE_SX * yv, bottom, 0),
                                 (PHASE_CX + PHASE_SX * yv, top, 0)], (110, 120, 160, 60),
                        f"Y/Yc = {yv:g}", ratio=0.02)
    kit.static_plot(sc, bd, [(l, bottom + sy, 0), (rgt, bottom + sy, 0)], (110, 120, 160, 60),
                    "Z/Zc = 1", ratio=0.02)
    for sgn, turn in ((1, "clockwise"), (-1, "counterclockwise")):
        sc.node(bd, pos=(PHASE_CX + PHASE_SX * sgn, bottom + sy, 0.02), scale=0.12,
                geometry=kit.GEO_CIRCLE, color=(255, 255, 255, 200),
                text=f"critical point (Y/Yc, Z/Zc) = ({sgn:+d}, 1): a steady roll, "
                     f"left roll turning {turn}")
    for model, fine in fines.items():
        norm = sm.normalization(r, model)
        path = np.stack([PHASE_CX + PHASE_SX * fine[:, 1] / norm[1],
                         bottom + sy * fine[:, 2] / norm[2],
                         np.full(len(fine), 0.03 if model == "5DLM" else 0.02)], axis=1)
        comets.trail(bd, path, SUB, COLOR[model],
                     f"{model} trajectory, r = {r:g} (last 4 tau)", max_step=0.1)
        pts = path[::SUB][:FRAMES]
        sc.node(bd, pos=tuple(pts[0]), scale=0.08, color=(*COLOR[model], 255),
                ch=kit.pos_channel(sc, pts), text=f"{model} state now, r = {r:g}")


def mode_atlas(sc, bd, y0):
    """The four temperature patterns, each shown as it enters theta for a
    positive amplitude (static)."""
    sc.node(bd, pos=(0.0, y0 + 0.35, 0.05), scale=0.06, geometry=kit.GEO_CIRCLE,
            color=(200, 200, 220, 255), show_text=1,
            text="The patterns the models add to plain conduction "
                 "(temperature = conduction + Y M2 - Z M3 + Y1 M5 - Z1 M6), for positive amplitudes:")
    tiles = [("Y M2: warm / cool sides", lambda m: m[1]),
             ("-Z M3: flattened profile", lambda m: -m[2]),
             ("Y1 M5: 5DLM only", lambda m: m[3]),
             ("-Z1 M6: 5DLM only", lambda m: -m[4])]
    s = 1.0
    w = sm.WIDTH * s
    xs = [round(i * sm.WIDTH / 24, 9) for i in range(25)]
    zs = [round(k / 16, 9) for k in range(17)]
    for t, (name, pick) in enumerate(tiles):
        x0 = t * (w + 2.4)
        tile = sc.node(bd, pos=(x0, y0 - s - 0.1, 0.0), geometry=kit.GEO_POINT,
                       topo=kit.TOPO_SURFACE, ratio=0.05, text=f"pattern {name}")
        for z in zs:
            for x in xs:
                v = pick(sm.modes(x, z)) / 1.4142
                sc.node(tile, pos=(x * s, z * s, 0.12 * v), scale=0.0,
                        geometry=kit.GEO_CUBE, color=(*kit.lerp_color(THETA_STOPS, v), 255),
                        text=f"pattern {name} at x = {x:.2f} H, z = {z:.2f} H")
        sc.node(bd, pos=(x0, y0 - s - 0.45, 0.05), scale=0.05, geometry=kit.GEO_CIRCLE,
                color=(200, 200, 220, 255), show_text=1, text=name)


def build(out_dir):
    ens = load_ensemble()
    sc = kit.Scene(FRAMES)
    wall = kit.frames_of_reference(sc, BG, LIFT)
    bd = kit.board(sc, wall, BOARD_ORIGIN, BOARD_SCALE)
    comets = kit.Comets(sc, FRAMES)

    runs = {(m, r): simulate(m, r) for r in R_VALUES for m in MODELS}

    # Shared clock along the top.
    top = row_base(0, 0) + 3.6
    t_frac = np.arange(FRAMES) * FRAME_DT / T_END
    span = PHASE_CX + PHASE_W
    kit.static_plot(sc, bd, [(0, top, 0), (span, top, 0)], (150, 155, 185, 160),
                    f"time axis: tau = 0 to {T_END:g} (the paper's dimensionless time)",
                    ratio=0.05)
    for tk in range(0, int(T_END) + 1, 10):
        sc.node(bd, pos=(span * tk / T_END, top, 0.02), scale=0.05,
                geometry=kit.GEO_CIRCLE, color=(150, 155, 185, 255),
                show_text=1, text=f"tau = {tk}")
    clock = np.stack([span * t_frac, np.full(FRAMES, top), np.full(FRAMES, 0.04)], axis=1)
    sc.node(bd, pos=tuple(clock[0]), scale=0.1, color=(255, 255, 255, 255),
            ch=kit.pos_channel(sc, clock), text="now (tau)")

    for g, r in enumerate(R_VALUES):
        sc.node(bd, pos=(0.0, row_base(g, 0) + 2.9, 0.05), scale=0.1,
                geometry=kit.GEO_CIRCLE, color=(255, 230, 140, 255), show_text=1,
                text=f"r = {r:g}: heated to {r:g} x the Rayleigh number where convection begins")
        later = np.concatenate([sm.z_budget(runs[(m, r)][::SUB][int(5 / FRAME_DT):], m)[0]
                                for m in MODELS])
        vmax = float(np.ceil(np.percentile(later, 99.5) * 1.05 / 50.0) * 50.0)
        for k, m in enumerate(MODELS):
            fluid_cell(sc, bd, g, k, m, r, runs[(m, r)], ens)
            budget(sc, bd, g, k, m, r, runs[(m, r)], vmax)
        phase_panel(sc, bd, g, r, {m: runs[(m, r)] for m in MODELS}, comets)

    atlas_y = row_base(len(R_VALUES) - 1, 1) - 0.9
    mode_atlas(sc, bd, atlas_y)
    legend = atlas_y - 2.1
    for i, txt in enumerate((
            "Fluid cells: temperature (red hot, blue cool) between the hot lower and cool upper "
            "plates. White beads: fluid parcels carried by the two rolls.",
            "Lorenz's X is the roll speed (its sign is the turning direction); every lobe switch "
            "of the butterfly is the rolls reversing.",
            "Shen's 5DLM adds Y1, Z1: finer layering near the plates. Its new term -XY1 "
            "drains Z, and that extra sink is what calms the flow.",
            "Every run starts from rest with the paper's nudge Y = 1. Rates in the titles: "
            "ensemble_shen.py, random starts per r.")):
        sc.node(bd, pos=(0.0, legend - 0.42 * i, 0.05), scale=0.05, geometry=kit.GEO_CIRCLE,
                color=(200, 200, 220, 255), show_text=1, text=txt)

    stem = "Convection_Cells"
    sc.write(out_dir, stem)
    for (m, r), fine in runs.items():
        st = fine[::SUB][:FRAMES]
        flips = int(np.sum(np.diff(np.sign(st[:, 0])) != 0))
        th = max(abs(sm.theta(s, r, x, z)) for s in st[::40]
                 for x in (0.0, sm.WIDTH / 2) for z in np.linspace(0, 1, 9))
        print(f"  {m} r={r:g}: roll reversals {flips:3d}   max |theta| {th:.2f}   "
              f"final Y/Yc {st[-1, 1] / sm.normalization(r, m)[1]:+.3f}")
    print(f"{len(sc.rows)} nodes, {len(sc.tracks)} tracks, {sc.next_ch - 1} channels, "
          f"{FRAMES} frames -> {out_dir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", default=os.path.join(HERE, "Convection_Cells"))
    build(ap.parse_args().out)
