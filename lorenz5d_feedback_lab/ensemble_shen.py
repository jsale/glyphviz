"""
Ensemble Lyapunov exponents for the 3DLM, 3DLMP and 5DLM over r -- the
numbers behind the scenes' captions and the r-Sweep Tower's colours.

The paper (section 2e) averages the leading LE over 10,000 starts, tau = 1000,
dtau = 1e-4: about 20 wall-clock hours per r. This is a cheaper version of the
same measurement, vectorized over every (r, start) pair at once:

  * starts: Gaussian white noise about the trivial critical point (the paper's
    choice; its spread is not given, so std 1 here is an ASSUMPTION);
  * leading LE from the variational equation (eq. 27) integrated alongside
    the model with RK4 at dtau = 0.01, the tangent renormalized every step;
  * the first TRANSIENT time units are discarded, then the LE is averaged over
    AVERAGE units. A start counts as chaotic if its LE > CHAOS_LE.

It also runs a second probe the paper does not: starts placed a hair (1e-3)
off the stable critical point. Where the random starts go chaotic but these
stay put, a stable steady state and the chaotic attractor COEXIST -- the
classic Lorenz picture between 24.06 and 24.74, and a candidate explanation
for the gap between the paper's ensemble r_c (42.9) and its linear r_c
(45.94).

    python ensemble_shen.py [--n 64] [--out ensemble_shen.json]
"""
import argparse
import json
import os
import time

import numpy as np

import shen_model as sm

HERE = os.path.dirname(os.path.abspath(__file__))
R_GRID = np.round(np.arange(20.0, 50.0 + 1e-9, 0.5), 2)
DT = 0.01
TRANSIENT = 50.0
AVERAGE = 200.0
CHAOS_LE = 0.02


def leading_le(s, r, model, dt=DT, transient=TRANSIENT, average=AVERAGE):
    """Leading LE of every start. s: (n_r, n, 5); r: (n_r, 1).
    -> (LEs (n_r, n), final states (n_r, n, 5))."""
    v = np.zeros_like(s)
    v[..., :2] = 1.0
    v /= np.linalg.norm(v, axis=-1, keepdims=True)
    acc = np.zeros(s.shape[:-1])
    n_tr, n_av = int(round(transient / dt)), int(round(average / dt))

    def f(state, tv):
        return sm.rhs(state, r, model), sm.tangent(state, tv, r, model)

    for i in range(n_tr + n_av):
        k1s, k1v = f(s, v)
        k2s, k2v = f(s + dt / 2 * k1s, v + dt / 2 * k1v)
        k3s, k3v = f(s + dt / 2 * k2s, v + dt / 2 * k2v)
        k4s, k4v = f(s + dt * k3s, v + dt * k3v)
        s = s + dt / 6 * (k1s + 2 * k2s + 2 * k3s + k4s)
        v = v + dt / 6 * (k1v + 2 * k2v + 2 * k3v + k4v)
        norm = np.linalg.norm(v, axis=-1)
        v /= norm[..., None]
        if i >= n_tr:
            acc += np.log(norm)
    return acc / average, s


def onset(rs, frac, level=0.5):
    """First r at which the chaotic fraction reaches `level` (None if never)."""
    hit = np.nonzero(np.asarray(frac) >= level)[0]
    return float(rs[hit[0]]) if len(hit) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=64, help="random starts per r")
    ap.add_argument("--seed", type=int, default=2014)
    ap.add_argument("--out", default=os.path.join(HERE, "ensemble_shen.json"))
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    r = R_GRID[:, None]
    result = {"r": R_GRID.tolist(), "n": args.n, "dt": DT, "transient": TRANSIENT,
              "average": AVERAGE, "chaos_le": CHAOS_LE, "models": {}}
    for model in sm.MODELS:
        t0 = time.perf_counter()
        noise = rng.standard_normal((len(R_GRID), args.n, 5))
        if model != "5DLM":
            noise[..., 3:] = 0.0
        le, _ = leading_le(noise, r, model)

        # Probe: a hair off the critical point, both branches.
        crit = np.stack([[sm.critical_point(rv, model, sign=sg) for sg in (1.0, -1.0)]
                         for rv in R_GRID])                         # (n_r, 2, 5)
        kick = 1e-3 * rng.standard_normal(crit.shape)
        if model != "5DLM":
            kick[..., 3:] = 0.0
        le_near, _ = leading_le(crit + kick, r, model)
        lin = [sm.linear_growth(rv, model) for rv in R_GRID]

        frac = (le > CHAOS_LE).mean(axis=1)
        near_chaos = (le_near > CHAOS_LE).mean(axis=1)
        result["models"][model] = {
            "mean_le": le.mean(axis=1).round(4).tolist(),
            "chaotic_fraction": frac.round(4).tolist(),
            "near_critical_chaotic_fraction": near_chaos.round(4).tolist(),
            "linear_growth": np.round(lin, 4).tolist(),
            "onset_r_half_chaotic": onset(R_GRID, frac),
            "onset_r_mean_le_positive": onset(R_GRID, le.mean(axis=1) > 0, 1.0),
        }
        m = result["models"][model]
        print(f"{model}: {time.perf_counter() - t0:.0f} s   ensemble onset (mean LE > 0) "
              f"r = {m['onset_r_mean_le_positive']}   half the starts chaotic from "
              f"r = {m['onset_r_half_chaotic']}")
        for i, rv in enumerate(R_GRID):
            print(f"   r {rv:5.1f}  mean LE {le[i].mean():+.3f}  chaotic {frac[i]:5.0%}"
                  f"  near-critical chaotic {near_chaos[i]:4.0%}  linear Re(lambda) "
                  f"{lin[i]:+.3f}")
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1)
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
