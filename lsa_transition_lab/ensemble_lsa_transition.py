"""
Step and point-move counts of the two transition schedules over many random
cases from generate_lsa_transition.problem() -- the source of the scene's
"fewer steps in N of 40" caption, and of SEED (a median case).

    python ensemble_lsa_transition.py [--cases 40]
"""
import argparse

import numpy as np

import generate_lsa_transition as gen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=int, default=40)
    args = ap.parse_args()
    rows = []
    for seed in range(args.cases):
        X, S0, S1, k0, k1 = gen.problem(seed)
        a = gen.sequential(X, S0, S1, k0, k1)
        b = gen.combined(X, S0, S1, k0, k1)
        rows.append((seed, len(a) - 1, gen.point_moves(a), len(b) - 1, gen.point_moves(b)))
        print("seed %2d  sequential %3d steps %4d moves | combined %3d steps %4d moves  "
              "(step ratio %.2f)" % (*rows[-1], rows[-1][3] / rows[-1][1]))
    r = np.array(rows, float)
    ratio = r[:, 3] / r[:, 1]
    print(f"\n{args.cases} cases: combined used fewer steps in {(r[:, 3] < r[:, 1]).sum():.0f}, "
          f"the same in {(r[:, 3] == r[:, 1]).sum():.0f}, more in {(r[:, 3] > r[:, 1]).sum():.0f}")
    print(f"step ratio median {np.median(ratio):.2f} (range {ratio.min():.2f}-{ratio.max():.2f}); "
          f"point-move ratio median {np.median(r[:, 4] / r[:, 2]):.2f}, fewer moves in "
          f"{(r[:, 4] < r[:, 2]).sum():.0f}")
    med = np.argsort(np.abs(ratio - np.median(ratio)))[:5]
    print("closest to the median:", [(int(r[i, 0]), int(r[i, 1]), int(r[i, 3])) for i in med])


if __name__ == "__main__":
    main()
