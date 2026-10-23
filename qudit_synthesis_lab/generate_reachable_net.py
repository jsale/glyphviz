"""
The reachable net, drawn in GlyphViz: every state a qubit (Clifford+T) or a
qutrit (Clifford+R) can reach from |0> with at most k non-Clifford gates,
layer by layer, filling its state space.

An illustration for Nguyen, Bregman & Nema's AMS talk "Synthesis of
Single-Qudit Circuits in Dimensions 3 and 5". Their headline claim is that
the number of R gates needed grows like log(1/eps). This scene shows why
such a law is natural: every extra non-Clifford gate multiplies the number of
reachable states by a fixed factor (x2 per T for a qubit, x9 per R for a
qutrit), so the gaps between them shrink by a fixed factor, and the gate
count needed to get within eps is proportional to log(1/eps). (This is state
preparation, a simpler cousin of gate synthesis: the gates live in SU(3),
8-dimensional; the states in a 4-dimensional space.)

    left    QUBIT on the Bloch sphere: exact, every state is a point on it
    right   QUTRIT on a solid torus. No sphere exists for a qutrit; its state
            space is 4-D. Drawn: ring angle = phase of |1> relative to |0>,
            tube angle = phase of |2> relative to |0>, depth = how much |0>
            (core = all |0>, surface = none). Not drawn: how the rest splits
            between |1> and |2>. With depth = 1 - p0, uniformly random qutrit
            states fill the tube's cross-section uniformly, so an even net
            looks even. The two phases make the same torus as the 2-D HCS
            torus of the Lorenz scene: phases are angles already.
    wall    distance from a random target to the nearest reachable state,
            median over 300 targets (ensemble_reachable_net.py), log scale:
            straight lines = a fixed factor per gate.

Usage:
    python generate_reachable_net.py [--out DIR]
"""
import argparse
import csv
import sys
from pathlib import Path

import numpy as np

import qudit_math as qm
from scene_kit import (GEO_POINT, GEO_SPHERE, GEO_STAR, LAYER_COLORS, Scene, caption,
                       circle_pts, cloud, line, stage_track)

HERE = Path(__file__).resolve().parent

K_QUBIT = 10                  # qubit layers drawn: 6 ... 6144 states
K_QUTRIT = 4                  # qutrit layers drawn: 12 ... 78732 states
STAGE = 60                    # frames per gate (30 fps)
INTRO = 30
FRAMES = INTRO + STAGE * (K_QUBIT + 1) + 90
SEED = 7

BG = (10, 12, 22)
GUIDE = (110, 115, 145)
FAINT = (80, 84, 110)
WHITE = (240, 240, 250)

# Layout (turn frame: +X toward the viewer, +Y screen right, +Z up).
QB, RB = (0.0, -22.0, 6.5), 5.5          # Bloch sphere
QT, R0, RT = (0.0, -4.0, 5.0), 5.2, 2.2   # torus: centre, ring radius, tube radius
WALL_X = -6.0
P0 = (10.5, 1.0)                          # wall: plot origin (y, z)
PW, PH = 18.0, 10.0
LOG_LO = -2.5                            # plot bottom: distance 10^-2.5
K_AXIS = 12


def f_stage(k):
    return INTRO + STAGE * k


def hide_from(frame):
    return 1.0 - stage_track(FRAMES, frame)


def bloch_pos(b):
    b = np.atleast_2d(b)
    return np.c_[QB[0] - RB * b[:, 1], QB[1] + RB * b[:, 0], QB[2] + RB * b[:, 2]]


def torus_coords(v):
    """Qutrit states (rows) -> (ring angle phi1, tube angle phi2, depth 1 - p0,
    weights p)."""
    v = np.atleast_2d(v)
    p = np.abs(v) ** 2
    phi1 = np.angle(v[:, 1] * np.conj(v[:, 0]))
    phi2 = np.angle(v[:, 2] * np.conj(v[:, 0]))
    return phi1, phi2, 1 - p[:, 0], p


def torus_xyz(phi1, phi2, depth):
    rho = RT * np.asarray(depth)
    a = (R0 + rho * np.cos(phi2)) * np.cos(phi1)
    b = (R0 + rho * np.cos(phi2)) * np.sin(phi1)
    h = rho * np.sin(phi2)
    return np.c_[QT[0] - b, QT[1] + a, QT[2] + h]


def torus_pos(v):
    phi1, phi2, depth, _ = torus_coords(v)
    return torus_xyz(phi1, phi2, depth)


def read_ensemble():
    path = HERE / "reachable_net.csv"
    if not path.exists():
        raise SystemExit(f"{path.name} missing: run ensemble_reachable_net.py first")
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = {}
    for name in ("qubit", "qutrit"):
        rs = [r for r in rows if r["system"] == name]
        out[name] = {k: np.array([float(r[k]) for r in rs])
                     for k in ("k", "new_states", "total_states", "median", "q1", "q3")}
    return out


def pick_target(d, layers, rng):
    """A random target whose nearest-distance profile is the most typical of
    200 random ones (closest to the median in log distance, layer by layer),
    so the scene's one example does not oversell or undersell."""
    v = rng.normal(size=(200, d)) + 1j * rng.normal(size=(200, d))
    T = v / np.linalg.norm(v, axis=1, keepdims=True)
    best = np.ones(len(T))
    prof = []
    for layer in layers:
        best = np.minimum(best, qm.state_distance(T, layer).min(1))
        prof.append(np.log(best.copy()))
    prof = np.array(prof)                      # (layers, targets)
    dev = np.abs(prof - np.median(prof, 1, keepdims=True)).sum(0)
    t = T[int(np.argmin(dev))]
    t = t * np.exp(-1j * np.angle(t[0]))
    return t


def nearest_track(target, layers, kmax_drawn, pos_fn):
    """Per stage k (0..K_QUBIT): the nearest reachable state among layers
    <= min(k, kmax_drawn), its position and distance."""
    best_d, best_v = 2.0, None
    per_k = []
    for k in range(K_QUBIT + 1):
        if k <= kmax_drawn:
            L = layers[k]
            dist = qm.state_distance(target[None, :], L)[0]
            i = int(np.argmin(dist))
            if dist[i] < best_d:
                best_d, best_v = float(dist[i]), L[i]
        per_k.append((best_d, pos_fn(best_v)[0]))
    return per_k


def stepwise(values_per_k):
    """Per-frame track holding values_per_k[k] from stage k on."""
    out = np.empty(FRAMES)
    for f in range(FRAMES):
        k = int(np.clip((f - INTRO) // STAGE, 0, K_QUBIT))
        out[f] = values_per_k[k]
    return out


def target_link(sc, turn, tpos, per_k, label):
    """The target star and a line to its nearest reachable state, which
    jumps as each layer arrives."""
    sc.node(turn, pos=tuple(tpos), scale=0.38, geometry=GEO_STAR, color=WHITE,
            text=f"{label}: the target state")
    plot = sc.node(turn, geometry=GEO_POINT, topo=16, ratio=0.07, color=(255, 255, 255, 0),
                   text=f"{label}: line from the target to the nearest reachable state")
    sc.node(plot, pos=tuple(tpos), scale=0.0, color=(*WHITE, 255),
            text=f"{label}: link end at the target")
    xyz = np.array([p for _, p in per_k])
    tracks = [stepwise(xyz[:, i]) for i in range(3)]
    sc.node(plot, pos=tuple(xyz[0]), scale=0.0, color=(*WHITE, 255),
            ch=sc.channel([(tracks[0], "translate_x"), (tracks[1], "translate_y"),
                           (tracks[2], "translate_z")]),
            text=f"{label}: link end at the nearest reachable state")
    ring = stepwise([0.3] * len(per_k))
    sc.node(turn, pos=tuple(xyz[0]), scale=0.3, geometry=GEO_SPHERE, color=(255, 255, 255, 120),
            ch=sc.channel([(tracks[0], "translate_x"), (tracks[1], "translate_y"),
                           (tracks[2], "translate_z"), (ring, "scale_x")]),
            text=f"{label}: the nearest reachable state so far")


def qubit_panel(sc, turn, layers, target):
    c = np.array(QB)
    # Guides: equator and two meridians, the z axis.
    for axes, lab in (((1, 0), "equator: equal |0> and |1>, phase going round"),
                      ((1, 2), "meridian through |0>, |+>, |1>"),
                      ((0, 2), "meridian through |0>, |+i>, |1>")):
        line(sc, turn, circle_pts(tuple(c), RB, 97, axes=axes), (*GUIDE, 170),
             f"Bloch sphere {lab}", ratio=0.04)
    line(sc, turn, [tuple(c + (0, 0, -1.18 * RB)), tuple(c + (0, 0, 1.18 * RB))],
         (*FAINT, 200), "Bloch z axis: |0> at the top, |1> at the bottom", ratio=0.04)
    for b, txt in (((0, 0, 1.25), "|0>"), ((0, 0, -1.3), "|1>"), ((1.15, 0, 0), "|+>"),
                   ((0, 1.12, 0.05), "|+i>")):
        caption(sc, turn, tuple(bloch_pos(np.array(b))[0]), txt)
    caption(sc, turn, (QB[0], QB[1] - RB, QB[2] + RB + 2.6),
            "QUBIT, Clifford+T: every state on the Bloch sphere")
    for k in range(K_QUBIT + 1):
        L = layers[k]
        B = qm.bloch(L)
        labels = [f"qubit, {k} T gate{'s' * (k != 1)}: Bloch ({x:+.3f}, {y:+.3f}, {z:+.3f})"
                  for x, y, z in B]
        cloud(sc, turn, bloch_pos(B), [(*LAYER_COLORS[k], 255)] * len(L), labels,
              max(0.1, 0.45 - 0.04 * k),
              f"qubit layer {k}: {len(L)} states first reachable with {k} T gates",
              ch=sc.channel([(hide_from(f_stage(k)), "hide")]))
    per_k = nearest_track(target, layers, K_QUBIT, lambda v: bloch_pos(qm.bloch(v[None, :])))
    target_link(sc, turn, bloch_pos(qm.bloch(target[None, :]))[0], per_k, "qubit")
    return per_k


def qutrit_panel(sc, turn, layers, target):
    # Guides: core circle, four tube circles round the ring, four lines of
    # latitude along it.
    ring = np.linspace(-np.pi, np.pi, 121)
    line(sc, turn, torus_xyz(ring, 0 * ring, 0 * ring), (*FAINT, 200),
         "torus core: states that are all |0> (depth 0)", ratio=0.04)
    for phi2, lab in ((0, "outer equator: tube angle 0"), (np.pi, "inner equator: tube "
                      "angle 180"), (np.pi / 2, "top: tube angle +90"),
                      (-np.pi / 2, "bottom: tube angle -90")):
        line(sc, turn, torus_xyz(ring, phi2 + 0 * ring, 1 + 0 * ring), (*GUIDE, 150),
             f"torus surface (no |0> at all), {lab}", ratio=0.035)
    tube = np.linspace(-np.pi, np.pi, 49)
    for phi1 in (0, np.pi / 2, np.pi, -np.pi / 2):
        line(sc, turn, torus_xyz(phi1 + 0 * tube, tube, 1 + 0 * tube), (*GUIDE, 150),
             f"tube circle at ring angle {np.degrees(phi1):.0f}: the phase of |2> going round",
             ratio=0.035)
    caption(sc, turn, (QT[0], QT[1] - R0 - RT, QT[2] + RT + 3.0),
            "QUTRIT, Clifford+R: drawn on a torus")
    for i, txt in enumerate(("ring angle = phase of |1>, tube angle = phase of |2>",
                             "depth = how much |0>: core all, surface none",
                             "not drawn: how the rest splits between |1> and |2>")):
        caption(sc, turn, (QT[0] + R0, QT[1] - R0 - RT, QT[2] - RT - 4.2 - 1.1 * i), txt)
    for k in range(K_QUTRIT + 1):
        L = layers[k]
        phi1, phi2, depth, p = torus_coords(L)
        labels = [f"qutrit, {k} R gate{'s' * (k != 1)}: weights {a:.3f}/{b:.3f}/{c:.3f}, "
                  f"phases vs |0> {np.degrees(f1):+.0f}/{np.degrees(f2):+.0f} deg"
                  for (a, b, c), f1, f2 in zip(p, phi1, phi2)]
        cloud(sc, turn, torus_xyz(phi1, phi2, depth), [(*LAYER_COLORS[k], 255)] * len(L),
              labels, [0.45, 0.3, 0.18, 0.1, 0.06][k],
              f"qutrit layer {k}: {len(L)} states first reachable with {k} R gates",
              ch=sc.channel([(hide_from(f_stage(k)), "hide")]))
    per_k = nearest_track(target, layers, K_QUTRIT, torus_pos)
    target_link(sc, turn, torus_pos(target)[0], per_k, "qutrit")
    return per_k


def plot_wall(sc, wall, ens, per_q, per_t):
    x = lambda k: P0[0] + PW * np.asarray(k, float) / K_AXIS
    y = lambda d: P0[1] + PH * (np.log10(np.asarray(d, float)) - LOG_LO) / -LOG_LO
    caption(sc, wall, (0, P0[0], P0[1] + PH + 1.3),
            "NEAREST-STATE DISTANCE (median, 300 random targets)")
    line(sc, wall, [(0, x(0), y(10 ** LOG_LO)), (0, x(K_AXIS), y(10 ** LOG_LO))],
         (*GUIDE, 220), "plot x axis: non-Clifford gates k", ratio=0.04)
    line(sc, wall, [(0, x(0), y(10 ** LOG_LO)), (0, x(0), y(1))], (*GUIDE, 220),
         "plot y axis: distance, log scale", ratio=0.04)
    for k in range(0, K_AXIS + 1, 2):
        line(sc, wall, [(0, x(k), y(10 ** LOG_LO) - 0.2), (0, x(k), y(10 ** LOG_LO) + 0.2)],
             (*GUIDE, 220), f"plot tick: {k} gates", ratio=0.04)
        caption(sc, wall, (0, x(k) - 0.15, y(10 ** LOG_LO) - 0.7), f"{k}")
    caption(sc, wall, (0, x(K_AXIS) - 6.0, y(10 ** LOG_LO) - 1.8),
            "non-Clifford gates (T or R)")
    for d in (1.0, 0.1, 0.01):
        line(sc, wall, [(0, x(0) - 0.2, y(d)), (0, x(0) + 0.2, y(d))], (*GUIDE, 220),
             f"plot tick: distance {d:g}", ratio=0.04)
        caption(sc, wall, (0, x(0) - 1.5, y(d)), f"{d:g}")
    out = {}
    for name, col, gate, rate in (("qubit", (120, 200, 255), "T", np.sqrt(2)),
                                  ("qutrit", (255, 175, 90), "R", np.sqrt(3))):
        e = ens[name]
        ks, med = e["k"], e["median"]
        line(sc, wall, [(0.02, x(k), y(m)) for k, m in zip(ks, med)], (*col, 255),
             f"{name}: median distance to the nearest state reachable with k {gate} gates",
             ratio=0.08)
        for k, m, n in zip(ks, med, e["total_states"]):
            sc.node(wall, pos=(0.04, float(x(k)), float(y(m))), scale=0.15, geometry=GEO_SPHERE,
                    color=(*col, 255),
                    text=f"{name}, {int(k)} {gate} gates: {int(n)} states, median distance "
                         f"{m:.4f}")
        guide = med[1] * rate ** -(ks[ks >= 1] - 1)
        line(sc, wall, [(0.01, x(k), y(g)) for k, g in zip(ks[ks >= 1], guide)],
             (*col, 90), f"{name}: a factor 1/sqrt({int(round(rate ** 2))}) per {gate} gate",
             ratio=0.04)
        fit = np.exp(np.polyfit(ks[ks >= 1], np.log(med[ks >= 1]), 1)[0])
        out[name] = fit
    for i, txt in enumerate((f"qubit (blue): x{out['qubit']:.3f} per T  (1/√2 = 0.707)",
                             f"qutrit (orange): x{out['qutrit']:.3f} per R  (1/√3 = 0.577)",
                             "straight on a log axis = gates grow like log(1/ε)")):
        caption(sc, wall, (0, x(0), y(10 ** LOG_LO) - 3.1 - 1.1 * i), txt)
    # Cursor and this scene's two targets.
    kt = stepwise(np.arange(K_QUBIT + 1, dtype=float))
    cur = sc.node(wall, geometry=GEO_POINT, topo=16, ratio=0.05, color=(255, 255, 255, 0),
                  text="plot cursor: the gate count now on screen")
    for d in (10 ** LOG_LO, 1.0):
        sc.node(cur, pos=(0.03, float(x(0)), float(y(d))), scale=0.0, color=(230, 230, 240, 150),
                ch=sc.channel([(x(kt), "translate_y")]),
                text="plot cursor end")
    for name, per_k, col in (("qubit", per_q, (120, 200, 255)), ("qutrit", per_t, (255, 175, 90))):
        dk = np.array([max(dd, 10 ** LOG_LO) for dd, _ in per_k])
        sc.node(wall, pos=(0.06, float(x(0)), float(y(dk[0]))), scale=0.24, geometry=GEO_STAR,
                color=(*col, 255),
                ch=sc.channel([(x(kt), "translate_y"), (stepwise(y(dk)), "translate_z")]),
                text=f"{name}: this scene's target, distance to its nearest reachable state")
    return out


def build(out_dir):
    q_layers = qm.reachable_states(2, qm.t_gate(2), K_QUBIT)
    t_layers = qm.reachable_states(3, qm.r_gate(), K_QUTRIT)
    ens = read_ensemble()
    rng = np.random.default_rng(SEED)
    q_target = pick_target(2, q_layers, rng)
    t_target = pick_target(3, t_layers, rng)

    sc = Scene(FRAMES)
    sc.node(0, type=0, color=(*BG, 255), geometry=GEO_POINT, hide=1, text="World - background")
    turn = sc.node(0, rot=(0, 0, 45), hide=1, geometry=GEO_POINT,
                   text="frame turned to the default camera's azimuth (45)")
    wall = sc.node(turn, pos=(WALL_X, 0.0, 0.0), rot=(0, -25, 0), hide=1, geometry=GEO_POINT,
                   text="backdrop wall - leaned back to the default camera's elevation (25)")
    per_q = qubit_panel(sc, turn, q_layers, q_target)
    per_t = qutrit_panel(sc, turn, t_layers, t_target)
    rates = plot_wall(sc, wall, ens, per_q, per_t)

    # Stage captions under each object.
    nq = np.cumsum([len(L) for L in q_layers])
    nt = np.cumsum([len(L) for L in t_layers])
    next_t = int(ens["qutrit"]["new_states"][K_QUTRIT + 1]) if len(
        ens["qutrit"]["k"]) > K_QUTRIT + 1 else None
    for k in range(K_QUBIT + 1):
        end = f_stage(k + 1) if k < K_QUBIT else None
        on = stage_track(FRAMES, f_stage(k), end)
        caption(sc, turn, (QB[0] + RB, QB[1] - RB, QB[2] - RB - 1.0),
                f"{k} T gate{'s' * (k != 1)}: {nq[k]} states, target {per_q[k][0]:.3f} away",
                show=0, ch=sc.channel([(on, "show_text")]))
        if k <= K_QUTRIT:
            txt = f"{k} R gate{'s' * (k != 1)}: {nt[k]} states, target {per_t[k][0]:.3f} away"
        else:
            txt = (f"{K_QUTRIT} R gates: {nt[K_QUTRIT]} states drawn"
                   + (f"; R gate {K_QUTRIT + 1} would add {next_t:,}" if next_t else ""))
        caption(sc, turn, (QT[0] + R0, QT[1] - R0 - RT, QT[2] - RT - 1.6), txt,
                show=0, ch=sc.channel([(on, "show_text")]))
    legend = (
        "THE REACHABLE NET: every state reachable from |0> with k non-Clifford gates "
        "(colour = k)",
        "Each T gate doubles the qubit's states; each R gate multiplies the qutrit's by 9.",
        "A fixed factor more states per gate shrinks the gaps by a fixed factor (the straight "
        "lines),",
        "so the gates needed to come within ε grow like log(1/ε): the talk's "
        "\"optimal scaling\".",
        "Shown for states. The talk compiles gates, which live in 8-D SU(3), not a 4-D "
        "state space.",
    )
    for i, txt in enumerate(legend):
        caption(sc, wall, (0, QB[1] - RB, 20.5 - 1.15 * i), txt)

    stem = "Reachable_Net"
    sc.write(out_dir, stem)
    seam = int((np.abs(np.concatenate(t_layers)[:, 0]) < 1e-9).sum())
    print(f"qubit layers {[len(L) for L in q_layers]}; target distances "
          f"{[round(d, 4) for d, _ in per_q]}")
    print(f"qutrit layers {[len(L) for L in t_layers]}; target distances "
          f"{[round(d, 4) for d, _ in per_t[:K_QUTRIT + 1]]}; {seam} drawn states have no |0> part")
    print(f"median shrink per gate: qubit x{rates['qubit']:.3f}, qutrit x{rates['qutrit']:.3f}")
    print(f"{len(sc.rows)} nodes, {len(sc.tracks)} tracks, {sc.next_ch - 1} channels, "
          f"{FRAMES} frames -> {out_dir}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", default=str(HERE / "Reachable_Net"))
    args = ap.parse_args()
    build(args.out)
