"""
The mathematics behind the two qudit-synthesis scenes, in plain numpy.

Part 1 -- the cyclotomic lattice search (scene Cyclotomic_Search)
-----------------------------------------------------------------
Every gate built from the ququint (d = 5) Clifford+T menu has matrix entries
of the form u / sqrt(5)^k with u in Z[zeta5], zeta5 = exp(2 pi i / 5): the
Hadamard brings the 1/sqrt(5), everything else is fifth roots of unity, and
sqrt(5) = -1 - 2 zeta^2 - 2 zeta^3 is itself in the ring. An element
u = a0 + a1 zeta + a2 zeta^2 + a3 zeta^3 is FOUR integers, so the candidates
form a 4-D lattice.

Each u has two essentially different complex values, its EMBEDDINGS:
sigma1 sends zeta -> exp(2 pi i / 5) (the number the gate actually uses) and
sigma2 sends zeta -> exp(4 pi i / 5) (its Galois "twin"). Unitarity must hold
under both. For one column of the gate, sum_j |u_j|^2 = 5^k, and applying
sigma2 gives sum_j |sigma2(u_j)|^2 = 5^k as well (sigma2(sqrt 5) = -sqrt 5,
squared away). So an entry is LEGAL only if its twin also fits:
|sigma2(u)| <= sqrt(5)^k.

To approximate a phase gate entry z = exp(i theta) to precision eps, the
whole column must be within eps of z e_j:
    |u/s - z|^2 + (1 - |u/s|^2) = 2 - 2 Re(u z* / s) <= eps^2,  s = sqrt(5)^k
-- the entry must be close to z AND almost exactly unit length, because the
rest of the column carries the shortfall 1 - |u/s|^2. That region is a thin
SLIVER of the unit disc (chord ~ 2 eps, depth eps^2 / 2, area ~ (2/3) eps^3).
The search: the smallest k with a lattice point whose sigma1 lies in the
sliver and whose sigma2 lies in the unit disc.

Once found, the rest of the column is a number-theory equation: the leftover
L = 5^k - u u* is a totally positive element of Z[phi] (phi the golden ratio),
and three real entries a, b, c in Z[phi] with a^2 + b^2 + c^2 = L complete
the column exactly (every totally positive integer of Q(sqrt 5) is a sum of
three squares -- Maass, 1941). complete_column() finds them.

Part 2 -- reachable state nets (scene Reachable_Net)
----------------------------------------------------
Every state reachable from |0> with at most k non-Clifford gates: Clifford+T
for a qubit, Clifford+R for a qutrit. Layer 0 is the Clifford orbit of |0>
(the stabilizer states); layer k+1 = Clifford . G . layer k, deduplicated up
to global phase. Exact layer sizes are what reachable_states() reports.
"""
import numpy as np

# --------------------------------------------------------------------------
# Z[zeta5]: exact integer arithmetic on coefficient vectors (a0, a1, a2, a3)
# --------------------------------------------------------------------------

Z1 = np.exp(2j * np.pi / 5)
Z2 = Z1 ** 2
B1 = np.array([Z1 ** j for j in range(4)])          # sigma1 of the basis
B2 = np.array([Z2 ** j for j in range(4)])          # sigma2 of the basis
M_EMBED = np.vstack([B1.real, B1.imag, B2.real, B2.imag])   # Z^4 -> R^4
M_INV = np.linalg.inv(M_EMBED)
COVOLUME = abs(np.linalg.det(M_EMBED))              # sqrt(125) / 4 = 2.795
SQRT5 = np.array([-1, 0, -2, -2])                   # sqrt 5 in Z[zeta5]
G = np.array([-1, 0, -1, -1])                       # zeta + zeta^4 = phi - 1 (real)
TOL = 1e-9


def sigma(u):
    """(sigma1(u), sigma2(u)) for coefficient rows u (..., 4)."""
    u = np.asarray(u, float)
    return u @ B1, u @ B2


def _reduce(c):
    """Coefficients of sum c_j zeta^j (any length) reduced mod
    1 + zeta + zeta^2 + zeta^3 + zeta^4, with zeta^5 = 1."""
    c = np.asarray(c, dtype=object)
    r = [0] * 5
    for j, v in enumerate(c):
        r[j % 5] += v
    return np.array([r[i] - r[4] for i in range(4)], dtype=object)


def mul(a, b):
    a = np.asarray(a, dtype=object)
    b = np.asarray(b, dtype=object)
    return _reduce(np.convolve(a, b))


def conj(a):
    """Complex conjugate: zeta^j -> zeta^(5 - j)."""
    a = np.asarray(a, dtype=object)
    return _reduce([a[0], 0, a[3], a[2], a[1]])


def power(a, n):
    out = np.array([1, 0, 0, 0], dtype=object)
    for _ in range(n):
        out = mul(out, a)
    return out


def five_to(k):
    return np.array([5 ** k, 0, 0, 0], dtype=object)


def real_part(x):
    """x in Z[phi] (x = x*) -> (m, n) with x = m + n g, g = zeta + zeta^4.
    In the basis 1, zeta, zeta^2, zeta^3 a real element is
    m + n (-1 - zeta^2 - zeta^3) = (m - n) - n zeta^2 - n zeta^3."""
    x = [int(v) for v in x]
    assert x[1] == 0 and x[2] == x[3], x
    n = -x[2]
    return x[0] + n, n


def from_real(m, n):
    return np.array([m - n, 0, -n, -n], dtype=object)


# Embeddings of g = zeta + zeta^4 under sigma1, sigma2.
G1 = 2 * np.cos(2 * np.pi / 5)       # 0.618 = 1/phi
G2 = 2 * np.cos(4 * np.pi / 5)       # -1.618 = -phi


# --------------------------------------------------------------------------
# Lattice enumeration
# --------------------------------------------------------------------------

def enumerate_box(k, center, rho, R):
    """All u with |sigma1(u)/s - center| <= rho and |sigma2(u)/s| <= R,
    s = sqrt(5)^k, by an integer box around the region. -> (u, y1, y2) with
    y1, y2 the embeddings of the ENTRY u / sqrt(5)^k: sigma1(u) / sqrt(5)^k
    and sigma2(u) / (-sqrt 5)^k -- the twin's sign flips on odd levels, and
    getting it right is what makes a level-k point and the same entry
    written at level k + 1 coincide. Fine for the drawn windows (k <= 3)."""
    s = 5 ** (k / 2)
    c = np.array([center.real, center.imag, 0.0, 0.0]) * s
    rng = []
    for i in range(4):
        w = M_INV[i]
        m = w @ c
        r = rho * s * np.hypot(w[0], w[1]) + R * s * np.hypot(w[2], w[3])
        rng.append(np.arange(int(np.floor(m - r)), int(np.ceil(m + r)) + 1))
    A = np.stack(np.meshgrid(*rng, indexing="ij"), -1).reshape(-1, 4)
    y1, y2 = sigma(A)
    y1, y2 = y1 / s, y2 / (-s if k % 2 else s)       # sigma2(sqrt 5) = -sqrt 5
    keep = (np.abs(y1 - center) <= rho + TOL) & (np.abs(y2) <= R + TOL)
    return A[keep], y1[keep], y2[keep]


def _fincke_pohst(Gm, center, bound):
    """Integer x with (x - center)^T Gm (x - center) <= bound (Gm SPD, 4x4)."""
    n = len(center)
    Rc = np.linalg.cholesky(Gm).T            # upper: Gm = Rc^T Rc
    out = []
    x = np.zeros(n, int)

    def rec(i, rem):
        # Sum over j > i is fixed; row i: (Rc[i,i](x_i - c_i) + sum_{j>i} Rc[i,j](x_j - c_j))^2
        off = sum(Rc[i, j] * (x[j] - center[j]) for j in range(i + 1, n))
        mid = center[i] - off / Rc[i, i]
        half = np.sqrt(max(rem, 0.0)) / Rc[i, i]
        for xi in range(int(np.ceil(mid - half - 1e-12)), int(np.floor(mid + half + 1e-12)) + 1):
            x[i] = xi
            t = Rc[i, i] * (xi - center[i]) + off
            r2 = rem - t * t
            if r2 < -1e-12:
                continue
            if i == 0:
                out.append(x.copy())
            else:
                rec(i - 1, r2)

    rec(n - 1, bound)
    return np.array(out, int).reshape(-1, n)


def sliver_points(k, theta, eps):
    """Every u at level k whose scaled sigma1 lies in the eps-sliver at
    z = exp(i theta) and whose scaled twin lies in the unit disc.
    -> (u, y1, y2, err) with err = sqrt(2 - 2 Re(y1 z*)) the column error."""
    s = 5 ** (k / 2)
    z = np.exp(1j * theta)
    # Enclose the sliver in a disc of radius eps around z, the twin in the
    # unit disc: one ellipsoid (sum of the two normalised squares <= 2).
    D = np.diag([1 / eps ** 2, 1 / eps ** 2, 1.0, 1.0]) / s ** 2
    Gm = M_EMBED.T @ D @ M_EMBED
    ctr = M_INV @ (np.array([z.real, z.imag, 0.0, 0.0]) * s)
    A = _fincke_pohst(Gm, ctr, 2.0)
    if not len(A):
        return A, np.zeros(0, complex), np.zeros(0, complex), np.zeros(0)
    y1, y2 = sigma(A)
    y1, y2 = y1 / s, y2 / (-s if k % 2 else s)       # sigma2(sqrt 5) = -sqrt 5
    err = np.sqrt(np.maximum(2 - 2 * (y1 * np.conj(z)).real, 0))
    keep = (np.abs(y1) <= 1 + TOL) & (np.abs(y2) <= 1 + TOL) & (err <= eps)
    return A[keep], y1[keep], y2[keep], err[keep]


def first_level(theta, eps, kmax=12):
    """Smallest k with a sliver candidate -> (k, u, y1, y2, err) for the best
    (lowest-error) candidate at that level."""
    for k in range(kmax + 1):
        A, y1, y2, err = sliver_points(k, theta, eps)
        if len(A):
            i = int(np.argmin(err))
            return k, A[i], y1[i], y2[i], err[i]
    raise RuntimeError("no candidate up to kmax")


# --------------------------------------------------------------------------
# Completing the column: a^2 + b^2 + c^2 = 5^k - u u*
# --------------------------------------------------------------------------

def leftover(u, k):
    """L = 5^k - u u*, as (m, n) in Z[phi] (exact)."""
    return real_part(five_to(k) - mul(u, conj(u)))


def _real_elements(L1, L2):
    """All x = m + n g in Z[phi] with x1^2 <= L1 and x2^2 <= L2."""
    out = []
    r1, r2 = np.sqrt(max(L1, 0)), np.sqrt(max(L2, 0))
    # m + n G1 in [-r1, r1], m + n G2 in [-r2, r2]  ->  n (G1 - G2) in [-(r1+r2), r1+r2]
    nmax = int(np.ceil((r1 + r2) / (G1 - G2))) + 1
    for n in range(-nmax, nmax + 1):
        lo = max(-r1 - n * G1, -r2 - n * G2)
        hi = min(r1 - n * G1, r2 - n * G2)
        for m in range(int(np.ceil(lo - 1e-9)), int(np.floor(hi + 1e-9)) + 1):
            out.append((m, n))
    return out


def _sq(m, n):
    """(m + n g)^2 as (m', n'), using g^2 = 1 - g."""
    return m * m + n * n, 2 * m * n - n * n


def complete_column(u, k):
    """Real a, b, c in Z[phi] with a^2 + b^2 + c^2 = 5^k - u u*, exactly.
    -> list of three (m, n) pairs, or None."""
    Lm, Ln = leftover(u, k)
    L1, L2 = Lm + Ln * G1, Lm + Ln * G2
    assert L1 >= -TOL and L2 >= -TOL, "leftover not totally positive"
    elems = _real_elements(L1, L2)
    squares = {}
    for e in elems:
        squares.setdefault(_sq(*e), e)
    for i, a in enumerate(elems):
        a2 = _sq(*a)
        for b in elems[i:]:
            b2 = _sq(*b)
            rest = (Lm - a2[0] - b2[0], Ln - a2[1] - b2[1])
            c = squares.get(rest)
            if c is not None:
                return [a, b, c]
    return None


def real_value(mn, which=1):
    m, n = mn
    return m + n * (G1 if which == 1 else G2)


# --------------------------------------------------------------------------
# Clifford groups and reachable states
# --------------------------------------------------------------------------

def _key(v, digits=8):
    """Canonical key of a vector up to global phase."""
    i = int(np.argmax(np.abs(v) > 1e-6))
    w = v * np.exp(-1j * np.angle(v[i]))
    return tuple(np.round(np.concatenate([w.real, w.imag]), digits) + 0.0)


def clifford_group(d):
    """Every d-dim Clifford unitary up to global phase (24 for d = 2, 216 for
    d = 3), generated by the Fourier Hadamard and the phase gate."""
    w = np.exp(2j * np.pi / d)
    H = np.array([[w ** (j * k) for k in range(d)] for j in range(d)]) / np.sqrt(d)
    if d == 2:
        S = np.diag([1, 1j])
    else:
        S = np.diag([w ** (j * (j - 1) // 2) for j in range(d)])
    group = {_key(np.eye(d).ravel()): np.eye(d, dtype=complex)}
    frontier = list(group.values())
    while frontier:
        nxt = []
        for U in frontier:
            for g in (H, S):
                V = g @ U
                kk = _key(V.ravel())
                if kk not in group:
                    group[kk] = V
                    nxt.append(V)
        frontier = nxt
    return np.array(list(group.values()))


def t_gate(d):
    if d == 2:
        return np.diag([1, np.exp(1j * np.pi / 4)])
    raise ValueError(d)


def r_gate():
    return np.diag([1, 1, -1]).astype(complex)


def _canonical(V, digits=8):
    """Rows up to global phase: the first non-negligible component made real
    and positive. -> (phase-fixed rows, rounded real keys)."""
    i = np.argmax(np.abs(V) > 1e-6, axis=1)
    ph = V[np.arange(len(V)), i]
    W = V * np.exp(-1j * np.angle(ph))[:, None]
    K = np.round(np.concatenate([W.real, W.imag], 1), digits) + 0.0
    return W, K


def reachable_states(d, gate, kmax):
    """Layers of states reachable from |0> with exactly k non-Clifford gates
    (and no fewer), k = 0..kmax. -> list of (N_k, d) arrays, each state with
    its first nonzero amplitude real and positive."""
    C = clifford_group(d)
    e0 = np.zeros(d, complex)
    e0[0] = 1
    seen = set()
    layers = []
    cand = C @ e0
    for k in range(kmax + 1):
        if k:
            base = layers[-1] @ gate.T            # the gate on every state of the last layer
            cand = np.einsum("cij,nj->cni", C, base).reshape(-1, d)
        W, K = _canonical(cand)
        _, first = np.unique(K, axis=0, return_index=True)
        first.sort()
        keep = []
        for j in first:
            kb = K[j].tobytes()
            if kb not in seen:
                seen.add(kb)
                keep.append(j)
        layers.append(W[keep])
    return layers


def state_distance(a, b):
    """Trace distance between pure states (rows): sqrt(1 - |<a|b>|^2)."""
    ov = np.abs(np.conj(a) @ b.T) ** 2
    return np.sqrt(np.clip(1 - ov, 0, 1))


def bloch(v):
    """Qubit state rows -> Bloch vectors."""
    a, b = v[:, 0], v[:, 1]
    x = 2 * (np.conj(a) * b).real
    y = 2 * (np.conj(a) * b).imag
    z = np.abs(a) ** 2 - np.abs(b) ** 2
    return np.stack([x, y, z], -1)
