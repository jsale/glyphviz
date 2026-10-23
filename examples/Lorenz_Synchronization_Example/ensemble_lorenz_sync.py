"""
How often does each controller lock? An ensemble check behind the captions.

One trajectory is an anecdote: in a chaotic system, moving the switch-on time
by a single 0.001 step flipped the z-coupling row from "never locks" to
"locks". So every caption the scene makes is backed by this instead: N
independent starts, each a pair of uncorrelated points on the attractor (what
two systems look like after the uncoupled divergence), controller on from
t = 0, judged after the same 18 time units the scene gives each row.

    python ensemble_lorenz_sync.py [--n 200]
"""
import argparse

import numpy as np

import generate_lorenz_sync as gen

HORIZON = gen.T_END - gen.T_ON       # 18 time units, as in the scene
LOCK_TOL = 0.1                       # |e| below this over the last 2 units


def rhs(S, kx, kz, g):
    x1, y1, z1, x2, y2, z2 = S.T
    return np.stack([
        gen.SIGMA * (y1 - x1) + kx * (x2 - x1),
        gen.RHO * x1 - y1 - x1 * z1 - g * y1,
        x1 * y1 - gen.BETA * z1 + kz * (z2 - z1),
        gen.SIGMA * (y2 - x2) + kx * (x1 - x2),
        gen.RHO * x2 - y2 - x2 * z2 - g * y2,
        x2 * y2 - gen.BETA * z2 + kz * (z1 - z2),
    ], axis=1)


def starts(n, seed=11):
    """n pairs of independent points on the attractor."""
    ref = gen.integrate(np.ones(6), 3000)[-1]
    path = gen.integrate(ref, 40000)[:, :3]          # 400 time units of system 1
    rng = np.random.default_rng(seed)
    a = path[rng.integers(0, len(path), n)]
    b = path[rng.integers(0, len(path), n)]
    return np.hstack([a, b])


def run(S, kx=0.0, kz=0.0, g=0.0, dt=0.002):
    steps = int(HORIZON / dt)
    tail = int(2.0 / dt)
    late = np.zeros(len(S))
    lobes = np.zeros(len(S))
    prev = np.sign(S[:, 0])
    for i in range(steps):
        k1 = rhs(S, kx, kz, g)
        k2 = rhs(S + dt / 2 * k1, kx, kz, g)
        k3 = rhs(S + dt / 2 * k2, kx, kz, g)
        k4 = rhs(S + dt * k3, kx, kz, g)
        S = S + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        if i >= steps - tail:
            late = np.maximum(late, np.linalg.norm(S[:, :3] - S[:, 3:], axis=1))
        if i >= steps // 2:
            sgn = np.sign(S[:, 0])
            lobes += sgn != prev
            prev = sgn
    locked = late < LOCK_TOL
    chaotic = lobes >= 2        # still switching lobes in the second half
    return locked, chaotic


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    n = ap.parse_args().n
    S = starts(n)
    cases = [("weak x  k=2", dict(kx=2.0)),
             ("x       k=10", dict(kx=10.0)),
             ("z       k=20", dict(kz=20.0)),
             ("z       k=2", dict(kz=2.0)),
             ("z       k=5", dict(kz=5.0)),
             ("z       k=50", dict(kz=50.0)),
             ("x2 + z20", dict(kx=2.0, kz=20.0)),
             ("x2 + y g=1", dict(kx=2.0, g=1.0))]
    print(f"{n} independent starts, {HORIZON:g} time units each, locked = |e| < {LOCK_TOL} "
          f"over the last 2 units")
    for name, kw in cases:
        locked, chaotic = run(S.copy(), **kw)
        print(f"  {name:14s} locked {locked.sum():4d}/{n} ({100 * locked.mean():5.1f}%)"
              f"   still lobe-switching {chaotic.sum():4d}/{n}"
              f"   locked AND chaotic {(locked & chaotic).sum():4d}/{n}")


if __name__ == "__main__":
    main()
