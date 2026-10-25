"""
The r-Sweep Tower: where each Lorenz model turns chaotic, after Shen (2014)
Figs. 3, 5, 7 and 8.

One tower per model -- 3DLM, 3DLMP (q = 0.17) and 5DLM -- each a stack of
phase-portrait slices, one per heating level r = 20, 20.5, ..., 50. A slice is
the model's whole trajectory from the paper's start (Y = 1, all else 0) over
40 time units, drawn in the plane

    across  Y / Yc         (the critical-point normalization of section 2e)
    depth   Z / Zc - 1     (toward the viewer)
    up      r              (the slice's height in the tower)

dim early and bright late, with a bead riding it during playback. The tower is
leaned back a little, so the opening view is close to a bifurcation diagram (Y
across, r up): below the onset of chaos every slice ends in a bright dot at a
steady roll, Y/Yc = +/-1; above it, the slice is a band -- the butterfly seen
nearly edge-on. Orbit the camera to see each slice's butterfly.

Beside each tower, the paper's Fig. 7 turned on its side: one bar per slice,
the ensemble-averaged leading Lyapunov exponent from ensemble_shen.py (blue
left = stable, red right = chaotic). Two markers per tower:

    linear r_c      where the steady roll itself loses stability
    ensemble onset  where random starts first find chaos (mean LE > 0)

Between them (gold bracket) the two COEXIST: the steady roll is still stable,
yet almost every random start falls onto the chaotic attractor instead. That
window -- not in the paper -- is why its ensemble r_c (42.9 for the 5DLM) sits
below its linear r_c (45.94).

The 3DLMP is normalized by the 3DLM's critical point, as in the paper, so its
steady rolls sit at Y/Yc = +/-1.098 (Fig. 9a): the parameterization buys the
5DLM's stability at the price of a ~10% shift in the steady state.

    python generate_r_sweep_tower.py [--out DIR]
"""
import argparse
import functools
import json
import os

import numpy as np

import scene_kit as kit
import shen_model as sm

HERE = os.path.dirname(os.path.abspath(__file__))

MODELS = ("3DLM", "3DLMP", "5DLM")
R_SLICES = np.round(np.arange(20.0, 50.0 + 1e-9, 0.5), 2)
T_END = 40.0
DT = 0.002
SAMPLE = 0.04                    # tau between slice vertices
FRAME_DT = 0.025
FRAMES = int(round(T_END / FRAME_DT))
START = np.array([0.0, 1.0, 0.0, 0.0, 0.0])
CONVERGED = 2e-3                 # stop a slice once it stays this close to its end state

# ---- layout, board units: x right, y up, z toward the viewer ----
SX = 0.9                         # Y/Yc -> x
SZ = 0.8                         # Z/Zc - 1 -> z
RY = 0.34                        # one unit of r -> y
TILT = 22.0                      # the tower leans back so slices show some depth
TOWER_PITCH = 10.5
LE_X0, LE_SCALE = 4.3, 1.1       # zero line of the Lyapunov strip; LE -> x
LIFT = 30.0
BOARD_SCALE = 1.6
BOARD_CENTRE = (12.0, 4.0)

BG = (10, 12, 22)
COLOR = {"3DLM": (255, 145, 45), "3DLMP": (235, 110, 200), "5DLM": (70, 200, 255)}
TITLE = {"3DLM": "3DLM (Lorenz)", "3DLMP": "3DLMP (q = 0.17)", "5DLM": "5DLM (Shen)"}
GOLD = (250, 205, 80)


def y_of(r):
    return (r - R_SLICES[0]) * RY


@functools.lru_cache(maxsize=None)
def _run(model):
    """Every slice of one model at once: (steps + 1, n_r, 5) sampled every SAMPLE."""
    r = R_SLICES                     # matches X's shape (n_r,)
    s = np.tile(START, (len(R_SLICES), 1))
    every = int(round(SAMPLE / DT))
    n = int(round(T_END / DT))
    out = [s.copy()]
    for i in range(1, n + 1):
        k1 = sm.rhs(s, r, model)
        k2 = sm.rhs(s + DT / 2 * k1, r, model)
        k3 = sm.rhs(s + DT / 2 * k2, r, model)
        k4 = sm.rhs(s + DT * k3, r, model)
        s = s + DT / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        if i % every == 0:
            out.append(s.copy())
    return np.array(out)


def normalized(model, r):
    """(samples, 2): (Y/Yc, Z/Zc) of one slice's run."""
    i = int(np.nonzero(R_SLICES == r)[0][0])
    run = _run(model)[:, i]
    norm = sm.normalization(r, model)
    return np.stack([run[:, 1] / norm[1], run[:, 2] / norm[2]], axis=1)


def slice_cut(yz):
    """Index after which the slice never leaves CONVERGED of its end state."""
    far = np.nonzero(np.abs(yz - yz[-1]).max(axis=1) > CONVERGED)[0]
    return len(yz) if not len(far) or far[-1] + 2 >= len(yz) else far[-1] + 2


def slice_path(model, r):
    """A slice's vertices in its own frame (x = Y/Yc, z = Z/Zc - 1)."""
    yz = normalized(model, r)[:slice_cut(normalized(model, r))]
    return np.stack([SX * yz[:, 0], np.zeros(len(yz)), SZ * (yz[:, 1] - 1.0)], axis=1)


def load_ensemble():
    path = os.path.join(HERE, "ensemble_shen.json")
    if not os.path.exists(path):
        raise SystemExit("ensemble_shen.json missing: run ensemble_shen.py first")
    with open(path, encoding="utf-8") as fh:
        ens = json.load(fh)
    assert np.allclose(ens["r"], R_SLICES), "ensemble r grid differs from the tower's"
    return ens


def linear_rc(model):
    lo, hi = 20.0, 60.0
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if sm.linear_growth(mid, model) < 0 else (lo, mid)
    return lo


def tower(sc, bd, t, model, ens):
    m = ens["models"][model]
    le = np.array(m["mean_le"])
    onset = m["onset_r_mean_le_positive"]
    rc_lin = linear_rc(model)
    x0 = t * TOWER_PITCH
    col = np.array(COLOR[model])
    frame = sc.node(bd, pos=(x0, 0.0, 0.0), rot=(TILT, 0.0, 0.0), hide=1,
                    geometry=kit.GEO_POINT,
                    text=f"{TITLE[model]} tower (leaned back {TILT:g} deg)")
    top = y_of(R_SLICES[-1])
    sc.node(bd, pos=(x0 - 2.7, top * np.cos(np.radians(TILT)) + 1.6, 0.0), scale=0.1,
            geometry=kit.GEO_CIRCLE, color=(*COLOR[model], 255), show_text=1,
            text=f"{TITLE[model]}: chaos from r = {onset:g}")

    # Guides: the steady rolls' column and r ticks.
    fix = sm.normalization(25.0, model)
    steady_x = SX * abs(sm.critical_point(25.0, model)[1] / fix[1])
    for sgn in (-1, 1):
        kit.static_plot(sc, frame, [(sgn * steady_x, 0, 0), (sgn * steady_x, top, 0)],
                        (150, 155, 185, 70),
                        f"Y/Yc = {sgn * steady_x / SX:+.3f}: where the steady rolls sit",
                        ratio=0.02)
    for rt in range(20, 51, 5):
        sc.node(frame, pos=(-3.2, y_of(rt), 0.0), scale=0.04, geometry=kit.GEO_CIRCLE,
                color=(150, 155, 185, 255), show_text=1, text=f"r = {rt}")

    # Slices.
    idx = np.arange(FRAMES)
    for i, r in enumerate(R_SLICES):
        path = slice_path(model, r)
        n = len(path)
        bright = 0.22 + 0.78 * (np.arange(n) / max(n - 1, 1)) ** 1.5
        cols = [(*np.round(col * b).astype(int), 255) for b in bright]
        state = "chaotic" if le[i] > 0 else "steady"
        plot = kit.static_plot(
            sc, frame, path, None,
            f"slice {model} r = {r:g} (ensemble LE {le[i]:+.3f}: {state}) - the run "
            f"from Y = 1, dim early, bright late", ratio=0.035, colors=cols)
        sc.rows[plot - 1][5] = y_of(r)           # the slice sits at its r
        # Bead: the state now, interpolated onto animation frames.
        yz = normalized(model, r)
        tt = np.arange(len(yz)) * SAMPLE
        tf = idx * FRAME_DT
        bx = SX * np.interp(tf, tt, yz[:, 0])
        bz = SZ * (np.interp(tf, tt, yz[:, 1]) - 1.0)
        pts = np.stack([bx, np.full(FRAMES, y_of(r)), bz], axis=1)
        sc.node(frame, pos=tuple(pts[0]), scale=0.045, color=(255, 255, 255, 255),
                ch=kit.pos_channel(sc, pts), text=f"{model} state now, r = {r:g}")
        # Lyapunov strip (Fig. 7 on its side).
        a, b = sorted((LE_X0, LE_X0 + LE_SCALE * le[i]))
        lc = (255, 90, 70) if le[i] > 0 else (90, 150, 255)
        sc.node(frame, pos=(0.5 * (a + b), y_of(r), 0.0),
                scale=((b - a) / (2 * kit.CUBE_FACE), 0.11 / (2 * kit.CUBE_FACE),
                       0.05 / (2 * kit.CUBE_FACE)),
                color=(*lc, 255), geometry=kit.GEO_CUBE,
                text=f"ensemble Lyapunov exponent at r = {r:g}: {le[i]:+.3f} "
                     f"({ens['n']} random starts; > 0 = chaotic)")
    kit.static_plot(sc, frame, [(LE_X0, 0, 0), (LE_X0, top, 0)], (200, 200, 220, 150),
                    "Lyapunov exponent = 0", ratio=0.03)
    sc.node(frame, pos=(LE_X0 - 0.3, -0.5, 0.0), scale=0.04, geometry=kit.GEO_CIRCLE,
            color=(200, 200, 220, 255), show_text=1, text="Lyapunov exp.")

    # Markers: linear r_c, ensemble onset, and the coexistence window.
    for r_mark, name, c in ((rc_lin, f"linear r_c = {rc_lin:.2f}: the steady roll goes unstable",
                             (255, 255, 255)),
                            (onset, f"ensemble onset r = {onset:g}: random starts find chaos",
                             GOLD)):
        kit.static_plot(sc, frame, [(-2.9, y_of(r_mark), 0), (LE_X0 + 1.6, y_of(r_mark), 0)],
                        (*c, 200), name, ratio=0.04)
    # The window: from the ensemble onset up to the linear r_c, the near-critical
    # starts must all have stayed steady (else the roll is not really stable).
    near = np.array(m["near_critical_chaotic_fraction"])
    if onset < rc_lin:
        lo, hi = onset, rc_lin
        assert np.all(near[(R_SLICES >= lo) & (R_SLICES < rc_lin)] == 0)
        kit.bar(sc, frame, -2.75, y_of(lo), y_of(hi), 0.09, (*GOLD, 255),
                text=f"coexistence window r = {lo:g} to {hi:.2f}: the steady roll is still "
                     f"stable, yet random starts end up chaotic")
    return rc_lin, onset


def build(out_dir):
    ens = load_ensemble()
    sc = kit.Scene(FRAMES)
    wall = kit.frames_of_reference(sc, BG, LIFT)
    bd = kit.board(sc, wall, (0.0, -BOARD_SCALE * BOARD_CENTRE[0],
                              -BOARD_SCALE * BOARD_CENTRE[1]), BOARD_SCALE)
    summary = {}
    for t, model in enumerate(MODELS):
        summary[model] = tower(sc, bd, t, model, ens)
    legend_y = -1.6
    for i, txt in enumerate((
            "Each slice: one run from rest (Y = 1) at that r, across = Y/Yc, depth = Z/Zc, "
            "dim early and bright late. Ends in a bright dot = settles to a steady roll.",
            "A band instead of a dot = chaos (the butterfly, seen nearly edge-on: orbit the "
            "camera to see it). White beads: the state now, during playback.",
            "Bars: ensemble Lyapunov exponent (blue < 0 stable, red > 0 chaotic). White line: "
            "linear r_c. Gold line: ensemble onset. Gold bracket: both states coexist.",
            "3DLMP is scaled by the 3DLM's critical point (as in the paper), so its steady "
            "rolls sit at +/-1.098, not +/-1.")):
        sc.node(bd, pos=(-3.2, legend_y - 0.45 * i, 0.05), scale=0.05,
                geometry=kit.GEO_CIRCLE, color=(200, 200, 220, 255), show_text=1, text=txt)
    stem = "R_Sweep_Tower"
    sc.write(out_dir, stem)
    for model, (rc_lin, onset) in summary.items():
        print(f"  {model}: linear r_c {rc_lin:.2f}, ensemble onset {onset:g}")
    print(f"{len(sc.rows)} nodes, {len(sc.tracks)} tracks, {FRAMES} frames -> {out_dir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", default=os.path.join(HERE, "R_Sweep_Tower"))
    build(ap.parse_args().out)
