"""
How fast does the reachable net close in? For 300 uniformly random target
states, the distance to the nearest state reachable from |0> with at most k
non-Clifford gates: Clifford+T for a qubit (k <= 12), Clifford+R for a
qutrit (k <= 5). Writes reachable_net.csv beside this script, which
generate_reachable_net.py reads for its plot.

    python ensemble_reachable_net.py

Distance = trace distance between pure states, sqrt(1 - |<a|b>|^2).
Measured (seed 2026): the qubit's median shrinks by ~1/sqrt(2) per T, the
qutrit's by ~1/sqrt(3) per R, matching layer growth x2 on the 2-D Bloch
sphere and x9 in the qutrit's 4-D state space.
"""
import csv
from pathlib import Path

import numpy as np

import qudit_math as qm

HERE = Path(__file__).resolve().parent
OUT = HERE / "reachable_net.csv"
SEED = 2026
N_TARGETS = 300
K_QUBIT, K_QUTRIT = 12, 5


def haar(rng, d, n):
    v = rng.normal(size=(n, d)) + 1j * rng.normal(size=(n, d))
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def best_by_layer(layers, targets, chunk=20000):
    best = np.ones(len(targets))
    out = []
    for layer in layers:
        for i in range(0, len(layer), chunk):
            best = np.minimum(best, qm.state_distance(targets, layer[i:i + chunk]).min(1))
        out.append(best.copy())
    return out


def main():
    rng = np.random.default_rng(SEED)
    rows = []
    for name, d, gate, kmax in (("qubit", 2, qm.t_gate(2), K_QUBIT),
                                ("qutrit", 3, qm.r_gate(), K_QUTRIT)):
        layers = qm.reachable_states(d, gate, kmax)
        targets = haar(rng, d, N_TARGETS)
        total = 0
        for k, (layer, best) in enumerate(zip(layers, best_by_layer(layers, targets))):
            total += len(layer)
            q1, med, q3 = np.percentile(best, [25, 50, 75])
            rows.append((name, k, len(layer), total, med, q1, q3, best.max()))
            print(f"{name} k={k}: {len(layer)} new states ({total} total), median distance "
                  f"{med:.4f} (middle half {q1:.4f}-{q3:.4f}, worst {best.max():.4f})")
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["system", "k", "new_states", "total_states", "median", "q1", "q3", "worst"])
        for r in rows:
            w.writerow([r[0], r[1], r[2], r[3]] + [f"{v:.6g}" for v in r[4:]])
    for name in ("qubit", "qutrit"):
        rs = [r for r in rows if r[0] == name and r[1] >= 1]
        slope = np.polyfit([r[1] for r in rs], np.log([r[4] for r in rs]), 1)[0]
        print(f"{name}: median shrinks x{np.exp(slope):.3f} per gate -> {OUT.name}")


if __name__ == "__main__":
    main()
