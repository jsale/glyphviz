"""
The Leech lattice from scratch: the extended binary Golay code, the 196,560
minimal vectors, and the checks that they really are the Leech lattice's
first shell.

Coordinates are Conway's: the lattice scaled by sqrt(8), so every minimal
vector has integer entries and squared length 32 (length 1 after dividing by
sqrt(32)). Conway's membership test (Sphere Packings, Lattices and Groups,
ch. 4, sec. 11): x is in the scaled lattice iff, for some m in {0, 1},
  * every x_i = m (mod 2),
  * sum x_i = 4m (mod 8),
  * for each k, the set {i : x_i = k (mod 4)} is the support of a Golay word.

The minimal vectors come in three shapes:
  (+/-2^8, 0^16)     2 on an octad, an even number of minus signs   759 x 128 =  97,152
  (-3, 1^23) flipped on a Golay word, the -3 anywhere              24 x 4096 =  98,304
  (+/-4, +/-4, 0^22) any two places, any signs                     276 x 4  =   1,104
                                                                              -------
                                                                              196,560
"""
import itertools

import numpy as np

# The cyclic Golay code [23, 12] has generator polynomial
# g(x) = 1 + x^2 + x^4 + x^5 + x^6 + x^10 + x^11; adding an overall parity
# bit extends it to the [24, 12, 8] extended Golay code.
G_POLY = (1, 0, 1, 0, 1, 1, 1, 0, 0, 0, 1, 1)


def golay_code():
    """All 4,096 words of the extended Golay code, as a (4096, 24) 0/1 array."""
    gens = np.zeros((12, 24), dtype=np.int64)
    for r in range(12):
        gens[r, r:r + 12] = G_POLY
    gens[:, 23] = gens[:, :23].sum(axis=1) % 2
    bits = np.array(list(itertools.product((0, 1), repeat=12)), dtype=np.int64)
    words = bits @ gens % 2
    return words


def octads(words=None):
    """The 759 weight-8 words (octads), sorted, as a (759, 24) 0/1 array."""
    words = golay_code() if words is None else words
    o = words[words.sum(axis=1) == 8]
    return o[np.lexsort(o.T[::-1])][::-1]


def minimal_vectors(words=None):
    """All 196,560 minimal vectors, (196560, 24) int8, in shape order
    (2^8), (-3, 1^23), (4^2). Also returns the shape label of each row."""
    words = golay_code() if words is None else words
    out, shape = [], []

    # (+/-2^8, 0^16): 2 on an octad, an even number of minus signs.
    even_signs = np.array([s for s in itertools.product((1, -1), repeat=8)
                           if s.count(-1) % 2 == 0], dtype=np.int64)
    for o in octads(words):
        idx = np.flatnonzero(o)
        v = np.zeros((len(even_signs), 24), dtype=np.int64)
        v[:, idx] = 2 * even_signs
        out.append(v)
    shape += [0] * (759 * 128)

    # (-3, 1^23) with signs flipped on a Golay word.
    flip = 1 - 2 * words                      # +1 off the word, -1 on it
    for k in range(24):
        base = np.ones(24, dtype=np.int64)
        base[k] = -3
        out.append(flip * base)
    shape += [1] * (24 * 4096)

    # (+/-4, +/-4, 0^22).
    for i, j in itertools.combinations(range(24), 2):
        for si, sj in itertools.product((4, -4), repeat=2):
            v = np.zeros(24, dtype=np.int64)
            v[i], v[j] = si, sj
            out.append(v[None])
    shape += [2] * (276 * 4)

    return np.vstack(out).astype(np.int8), np.array(shape, dtype=np.int8)


def in_leech(x, words):
    """Conway's membership test for rows of x (scaled coordinates)."""
    x = np.asarray(x, dtype=np.int64)
    code = {tuple(w) for w in words}
    ok = np.zeros(len(x), dtype=bool)
    for r, v in enumerate(x):
        m = v[0] % 2
        if np.any(v % 2 != m) or v.sum() % 8 != (4 * m) % 8:
            continue
        # The empty set and all 24 places are Golay words too, so testing
        # every residue class covers both parities.
        ok[r] = all(tuple(((v % 4) == k).astype(np.int64)) in code for k in range(4))
    return ok


def check(full=False):
    """Every claim this module makes, asserted. full=True also checks that no
    two distinct minimal vectors are closer than the minimum (all 196,560^2
    inner products, about a minute); otherwise a 3,000-row sample against all."""
    words = golay_code()
    weights = np.bincount(words.sum(axis=1), minlength=25)
    assert weights[0] == 1 and weights[8] == 759 and weights[12] == 2576
    assert weights[16] == 759 and weights[24] == 1 and weights.sum() == 4096
    assert len({tuple(w) for w in words}) == 4096

    v, shape = minimal_vectors(words)
    assert len(v) == 196560
    assert np.bincount(shape).tolist() == [97152, 98304, 1104]
    assert len({r.tobytes() for r in v}) == 196560, "duplicate vectors"
    assert np.all((v.astype(np.int64) ** 2).sum(axis=1) == 32)
    assert in_leech(v, words).all(), "a vector fails Conway's test"

    # Minimal: no two distinct vectors closer than the vectors' own length,
    # i.e. every inner product of distinct vectors is at most 16 (60 deg).
    vf = v.astype(np.float32)
    rows = np.arange(len(v)) if full else \
        np.random.default_rng(0).choice(len(v), 3000, replace=False)
    seen = set()
    for k in range(0, len(rows), 512):
        r = rows[k:k + 512]
        d = vf[r] @ vf.T
        d[np.arange(len(r)), r] = -99
        assert d.max() <= 16.0 + 1e-3
        seen |= set(np.unique(d).astype(int).tolist())
    assert seen - {-99} <= {-32, -16, -12, -8, -4, 0, 4, 8, 12, 16}

    # The 759 octad vectors: around any one, 280 touch (|cap| = 4, 60 deg),
    # 448 sit at 75.5 deg (|cap| = 2), 30 at 90 deg (disjoint).
    o = octads(words)
    caps = o @ o.T
    for row in caps:
        assert np.bincount(row, minlength=9)[[0, 2, 4, 8]].tolist() == [30, 448, 280, 1]
    return v, shape


if __name__ == "__main__":
    import sys
    import time
    t = time.perf_counter()
    check(full="--full" in sys.argv)
    print(f"Leech lattice checks pass ({time.perf_counter() - t:.1f} s)")
