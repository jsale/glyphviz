"""
How deep must the cyclotomic search go? For each precision eps (0.1 down to
0.001) and 100 random target angles theta, the smallest level k at which
Z[zeta5] has an entry u / sqrt(5)^k in the eps-sliver with its twin in the
unit disc. Writes cyclotomic_ladder.csv beside this script, which
generate_cyclotomic_search.py reads for its ladder plot.

    python ensemble_cyclotomic_ladder.py [--n 100]

The prediction it is compared against: the sliver has area (2/3) eps^3, the
twin's disc pi, and level-k points have density 25^k / covolume in R^4, so
the expected number of candidates is E_k = (2/3) eps^3 pi 25^k / 2.795, and
the level where E_k = 1 grows as 3 log_25(1/eps) -- 2.15 levels per decade of
precision. That straight line IS "gate count grows like log(1/eps)".
"""
import argparse
import csv
from pathlib import Path

import numpy as np

import qudit_math as qm

HERE = Path(__file__).resolve().parent
OUT = HERE / "cyclotomic_ladder.csv"
EPS = 10.0 ** -(1.0 + 0.25 * np.arange(9))          # 0.1 ... 0.001
SEED = 2026


def predicted_level(eps):
    """The k at which the expected number of sliver candidates reaches 1."""
    return np.log((3 * qm.COVOLUME) / (2 * np.pi * eps ** 3)) / np.log(25)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    args = ap.parse_args()
    rng = np.random.default_rng(SEED)
    rows = []
    for eps in EPS:
        thetas = rng.uniform(0, 2 * np.pi, args.n)
        ks = np.array([qm.first_level(t, eps)[0] for t in thetas])
        q1, med, q3 = np.percentile(ks, [25, 50, 75])
        rows.append((eps, ks.mean(), q1, med, q3, ks.min(), ks.max(), predicted_level(eps)))
        print(f"eps {eps:.4g}: mean level {ks.mean():.2f} (median {med:g}, "
              f"range {ks.min()}-{ks.max()}), predicted {predicted_level(eps):.2f}")
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["eps", "mean_level", "q1", "median", "q3", "min", "max", "predicted"])
        for r in rows:
            w.writerow([f"{v:.6g}" for v in r])
    x = np.log10(1 / EPS)
    slope = np.polyfit(x, [r[1] for r in rows], 1)[0]
    print(f"fitted slope {slope:.2f} levels per decade of precision "
          f"(prediction {3 / np.log10(25):.2f}) -> {OUT}")


if __name__ == "__main__":
    main()
