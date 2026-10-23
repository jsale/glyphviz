"""
Time-symmetric, conformally flat initial data for a uniform ball of dust,
solved three ways. The physics behind Conformal_Star (generate_conformal_star.py).

Units G = c = 1, lengths in units of the star's COORDINATE radius R = 1.

The data: the spatial metric is g = phi^4 * (flat), the extrinsic curvature is
K = 0 (the star is momentarily at rest), so the momentum constraint is empty and
the Hamiltonian constraint, R(g) = 16 pi rho, becomes the Lichnerowicz equation

    Laplacian(phi) = -2 pi rho phi^5,     phi -> 1 far away,

with rho the PHYSICAL energy density. Pressure never appears: with K = 0 the
constraints see only energy density. Outside the ball phi = 1 + M/r, a
Schwarzschild slice of ADM mass m = 2M.

What you choose to hold fixed decides the power of phi in the matter term:

    A  DIRECT     rho = rho0                    -> -2 pi rho0 phi^5
    B  TEXTBOOK   rho = phi^-8 rho~, rho~ fixed -> -2 pi rho~  phi^-3
    C  DENSITIZED rho = phi^-6 rho*, rho* fixed -> -2 pi rho*  phi^-1

C holds the rest mass per COORDINATE volume fixed: sqrt(det g) = phi^6, so
rho * phi^6 = rho* is the matter in each coordinate cell -- a count the conformal
factor cannot change. It is a toy in the spirit of Isenberg & Maxwell's
conformally invariant matter variables (arXiv:2106.15027), for dust at rest; it
is not their perfect-fluid system, which also carries momentum and entropy.

A negative power keeps the maximum principle: B and C have exactly one solution
for every amount of matter. The +5 power of A does not. Its uniform ball has a
closed form (the interior is a cap of a round 3-sphere in stereographic
coordinates):

    phi_in  = (1 + s)^(3/2) / sqrt(1 + s r^2),   phi_out = 1 + s / r,
    kappa := 2 pi rho0 R^2 / 3 = s / (1 + s)^6.

s/(1+s)^6 rises from 0, peaks at s = 1/5 (kappa_max = 5^5 / 6^6 = 0.06698), and
falls back to 0: two solutions below kappa_max, one at it, none above. The large-s
branch is Wheeler's "bag of gold": past s = 1 the star sits behind a minimal
surface (a throat), most of a 3-sphere hanging off a Schwarzschild funnel.

The knob kappa is the same number in all three: 2 pi (rho0, rho~ or rho*) / 3.
"""
import numpy as np
from scipy.integrate import solve_ivp, cumulative_trapezoid
from scipy.optimize import brentq

KAPPA_MAX = 5 ** 5 / 6 ** 6          # 0.066980...
S_FOLD = 0.2

# Matter-term powers of phi.
POWER = {"A": 5, "B": -3, "C": -1}
# Physical density / the number you specified: phi^-DENSITY_POWER.
DENSITY_POWER = {"A": 0, "B": 8, "C": 6}


# --------------------------------------------------------------------------
# Case A: closed form
# --------------------------------------------------------------------------

def fold_roots(kappa):
    """The s values with s/(1+s)^6 = kappa: (small, large), or () above the fold."""
    f = lambda s: s / (1 + s) ** 6 - kappa
    if kappa > KAPPA_MAX:
        return ()
    if np.isclose(kappa, KAPPA_MAX, rtol=0, atol=1e-12):
        return (S_FOLD, S_FOLD)
    if kappa <= 0:
        return (0.0,)
    return brentq(f, 0.0, S_FOLD, xtol=1e-14), brentq(f, S_FOLD, 1e6, xtol=1e-12)


def direct_solution(s):
    """phi, phi' as callables of r for the closed-form uniform ball, and M."""
    a = (1 + s) ** 1.5

    def phi(r):
        r = np.asarray(r, float)
        return np.where(r <= 1, a / np.sqrt(1 + s * r * r), 1 + s / np.maximum(r, 1e-300))

    def dphi(r):
        r = np.asarray(r, float)
        return np.where(r <= 1, -a * s * r * (1 + s * r * r) ** -1.5,
                        -s / np.maximum(r, 1e-300) ** 2)
    return phi, dphi, s


# --------------------------------------------------------------------------
# Shooting: any power (used for B and C, and to check A's closed form)
# --------------------------------------------------------------------------

def _interior(c, kappa, p, r_eval=None):
    """Integrate phi'' + 2 phi'/r = -3 kappa phi^p from the centre with
    phi(0) = c, phi'(0) = 0 (series start), out to r = 1."""
    k = 3.0 * kappa
    r0 = 1e-4
    # phi = c - k c^p r^2 / 6 + ...
    y0 = [c - k * c ** p * r0 ** 2 / 6, -k * c ** p * r0 / 3]

    def rhs(r, y):
        ph = max(y[0], 1e-12)
        return [y[1], -k * ph ** p - 2 * y[1] / r]
    sol = solve_ivp(rhs, (r0, 1.0), y0, rtol=1e-11, atol=1e-13, dense_output=True,
                    t_eval=r_eval)
    return sol


def _mismatch(c, kappa, p):
    """phi(1) + phi'(1) - 1: zero exactly when the interior joins 1 + M/r."""
    y = _interior(c, kappa, p).y[:, -1]
    return y[0] + y[1] - 1.0


def shoot_roots(kappa, p, c_hi=400.0, n=600):
    """Every central value c that solves the problem, by scanning then
    bracketing the mismatch on a log grid of c."""
    cs = np.geomspace(1.0, c_hi, n)
    g = np.array([_mismatch(c, kappa, p) for c in cs])
    roots = []
    for i in np.where(np.sign(g[:-1]) != np.sign(g[1:]))[0]:
        roots.append(brentq(_mismatch, cs[i], cs[i + 1], args=(kappa, p), xtol=1e-13))
    return roots


def shot_solution(kappa, p):
    """The unique solution for B/C (a negative power): phi, phi', M."""
    if kappa <= 0:
        return (lambda r: np.ones_like(np.asarray(r, float)),
                lambda r: np.zeros_like(np.asarray(r, float)), 0.0)
    # g(1) = phi(1) + phi'(1) - 1 < 0 always (the ball pulls phi' negative);
    # g grows with c, so bracket upward.
    hi = 2.0
    while _mismatch(hi, kappa, p) < 0:
        hi *= 2
    c = brentq(_mismatch, 1.0, hi, args=(kappa, p), xtol=1e-13)
    sol = _interior(c, kappa, p)
    M = -sol.y[1, -1]

    def phi(r):
        r = np.asarray(r, float)
        inner = np.where(r < 1e-4, c, sol.sol(np.clip(r, 1e-4, 1.0))[0])
        return np.where(r <= 1, inner, 1 + M / np.maximum(r, 1e-300))

    def dphi(r):
        r = np.asarray(r, float)
        inner = np.where(r < 1e-4, 0.0, sol.sol(np.clip(r, 1e-4, 1.0))[1])
        return np.where(r <= 1, inner, -M / np.maximum(r, 1e-300) ** 2)
    return phi, dphi, M


# --------------------------------------------------------------------------
# What a solution looks like, and what it delivered
# --------------------------------------------------------------------------

def embedding(phi, dphi, r):
    """The spatial slice's equatorial plane drawn as a surface of revolution in
    flat 3-space: areal radius rho_A = r phi^2 against height z. Proper radial
    distance dl = phi^2 dr; dz = sqrt(dl^2 - d rho_A^2) = sqrt(2 m(r) / rho_A) dl
    is real for any rho >= 0. rho_A need not be monotone -- past a throat it
    shrinks again -- which is why this is drawn as meridians, not a height field.
    Returns (rho_A, z) with z = 0 at the centre."""
    ph, dp = phi(r), dphi(r)
    dl = ph ** 2
    drho = ph * (ph + 2 * r * dp)
    dz = np.sqrt(np.maximum(dl ** 2 - drho ** 2, 0.0))
    return r * ph ** 2, cumulative_trapezoid(dz, r, initial=0.0)


def delivered(case, kappa, phi, M, n=4001):
    """What the solution delivered, against the number you typed in.
    density_ratio: physical central density / the specified value.
    rest_ratio:    rest mass  int rho phi^6 d^3x  over the ball, divided by the
                   specified value times the coordinate volume 4 pi / 3.
    adm:           ADM mass m = 2 M (what a distant planet's orbit measures)."""
    r = np.linspace(0, 1, n)
    q = DENSITY_POWER[case]
    ph = phi(r)
    dens = ph ** -q
    rest = 3 * np.trapezoid(dens * ph ** 6 * r * r, r)
    return dict(density_ratio=float(ph[0] ** -q), rest_ratio=float(rest), adm=2.0 * M,
                phi0=float(ph[0]))


def throat(phi, dphi, r):
    """Coordinate radius of a minimal surface -- where the areal radius stops
    shrinking and grows again (d rho_A / dr goes - to +) -- or None. The
    bag's equator, a MAXIMUM of rho_A, is the + to - crossing and is skipped.
    In time-symmetric data a minimal surface is an apparent horizon."""
    ph, dp = phi(r), dphi(r)
    g = ph + 2 * r * dp
    idx = np.where((g[:-1] < 0) & (g[1:] >= 0))[0]
    return float(r[idx[0]]) if len(idx) else None
