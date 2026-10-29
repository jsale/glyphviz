"""
The bosonic string's numbers, computed rather than quoted.

  * states(N): how many states one side of the string has at level N, the
    coefficient of q^N in prod_n (1 - q^n)^-24 -- 24 directions, each with
    vibration modes n = 1, 2, 3, ... (partitions of N into 24 colours).
  * mass2(N) = N - 1 in units of 4/alpha' (the closed string's convention
    for one side): N = 0 is the tachyon, N = 1 massless.
  * The critical dimension: the zero-point shift is -(D - 2)/24 (from
    zeta(-1) = -1/12); level 1 holds only D - 2 states, too few for a massive
    particle in D dimensions, so it must be massless: D = 26.
  * Moonshine: (Leech theta) / Delta = j - 720, so 196,560 + 324 = 196,884,
    the first coefficient of j; j is computed independently as E4^3 / Delta.
"""
import numpy as np

import leech


def eta24_inverse(n):
    """Coefficients of prod_{k>=1} (1 - q^k)^-24 up to q^(n-1), as Python
    ints (exact; they pass 2^63 by level 14)."""
    c = [0] * n
    c[0] = 1
    for k in range(1, n):
        for _ in range(24):              # multiply by 1/(1 - q^k), 24 times
            for i in range(k, n):
                c[i] += c[i - k]
    return c


def states(n_levels):
    return eta24_inverse(n_levels)


def mass2(N):
    return np.asarray(N, dtype=float) - 1.0


def critical_dimension():
    """Solve (D - 2)/24 = 1: the level-1 states must be massless."""
    return 2 + 24


def j_coefficients(n):
    """Coefficients of q^-1 .. q^(n-2) of j = E4^3 / Delta, exact ints."""
    def sigma3(m):
        return sum(d ** 3 for d in range(1, m + 1) if m % d == 0)
    e4 = [1] + [240 * sigma3(m) for m in range(1, n)]
    sq = [sum(e4[i] * e4[k - i] for i in range(k + 1)) for k in range(n)]
    e4_3 = [sum(sq[i] * e4[k - i] for i in range(k + 1)) for k in range(n)]
    inv = eta24_inverse(n)               # 1 / prod (1 - q^k)^24; Delta = q prod(...)^24
    return [sum(e4_3[i] * inv[k - i] for i in range(k + 1)) for k in range(n)]


def leech_theta(n, vectors=None):
    """Coefficients of q^0 .. q^(n-1) of the Leech theta series, counting
    lattice vectors by norm/2 (unscaled norm 4 -> q^2). Only the shells this
    lab computes (0 and the minimal vectors) are filled; n <= 3."""
    assert n <= 3
    if vectors is None:
        vectors, _ = leech.minimal_vectors()
    c = [0] * n
    c[0] = 1
    if n > 2:
        c[2] = len(vectors)              # norm 32 scaled = norm 4: q^2
    return c                             # q^1 stays 0: the Leech lattice has no roots


def check():
    s = states(13)
    assert s[:7] == [1, 24, 324, 3200, 25650, 176256, 1073720], s[:7]
    assert critical_dimension() == 26
    assert 24 == critical_dimension() - 2
    # Level 2 is exactly one massive spin-2 particle in 26-D: the symmetric
    # traceless tensor of SO(25).
    assert s[2] == 25 * 26 // 2 - 1
    # Level 1 closed string: 24 x 24 = graviton + B-field + dilaton.
    assert 24 * 24 == (24 * 25 // 2 - 1) + 24 * 23 // 2 + 1 == 299 + 276 + 1
    j = j_coefficients(4)
    assert j[:3] == [1, 744, 196884], j
    th = leech_theta(3)
    # theta / Delta = q^-1 * theta * prod(1 - q^n)^-24
    lhs = [sum(th[i] * s[k - i] for i in range(k + 1)) for k in range(3)]
    assert lhs == [1, 24, 196884] and lhs[1] == j[1] - 720 and lhs[2] == j[2]
    assert 196884 == 324 + 196560 == 1 + 196883
    return s


if __name__ == "__main__":
    print("states per level:", check())
