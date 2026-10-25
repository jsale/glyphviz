"""
The Lorenz models of Shen (2014), "Nonlinear Feedback in a Five-Dimensional
Lorenz Model", J. Atmos. Sci. 71, 1701-1723 (doi:10.1175/JAS-D-13-0223.1).

One state layout for all three models, s = (X, Y, Z, Y1, Z1):

    3DLM    Lorenz (1963), eqs. (15)-(17). Y1 and Z1 stay 0.
    3DLMP   the 3DLM with -XY1 "parameterized" as -q X^2, eqs. (15), (16), (18).
    4DLM    eqs. (10)-(13) with Z1 dropped (section 2d): M5 without M6. It has
            no real nontrivial critical point for r > d_o + 1 and does not
            conserve energy; from the paper's start it runs away to infinity.
    5DLM    eqs. (10)-(14).

and the physical fields they are a truncation of, eqs. (5)-(9), so a scene can
draw the convecting fluid itself rather than only the five amplitudes:

    psi   = C1 X M1                                  (the roll)
    theta = C2 (Y M2 - Z M3 + Y1 M5 - Z1 M6)         (temperature perturbation)

with M1 = sqrt2 sin(lx) sin(mz), M2 = sqrt2 cos(lx) sin(mz), M3 = sin(2mz),
M5 = sqrt2 cos(lx) sin(3mz), M6 = sin(4mz), l = pi a / H, m = pi / H.

Units used here: H = 1, so the fluid layer is 0 <= z <= 1 and the domain
0 <= x <= 2/a = 2 sqrt2 holds one horizontal wavelength, i.e. TWO
counter-rotating rolls. Temperatures are in units of the plate difference
Delta T, where C2 = Delta T Rc / (pi Ra) = Delta T / (pi r) (eq. 9). Times are
the paper's dimensionless tau. Velocities come from psi (u = -psi_z,
w = psi_x) divided by kappa (1 + a^2) (pi / H)^2, the tau scaling, which leaves
    dx/dtau = -sqrt2 X sin(lx) cos(mz) / (a pi)
    dz/dtau =  sqrt2 X cos(lx) sin(mz) / pi
(divergence-free; see velocity()).
"""
import numpy as np

SIGMA = 10.0
A = 1.0 / np.sqrt(2.0)                    # the paper's a: minimizes Rc
B = 4.0 / (1.0 + A * A)                   # 8/3
D_O = (9.0 + A * A) / (1.0 + A * A)       # 19/3
L_WAVE = np.pi * A                        # l with H = 1
M_WAVE = np.pi                            # m with H = 1
WIDTH = 2.0 / A                           # domain width 2H/a

MODELS = ("3DLM", "3DLMP", "5DLM")
Q_PAPER = 0.17                            # the paper's preferred 3DLMP q


def rhs(s, r, model="5DLM", q=Q_PAPER, sigma=SIGMA):
    """d s / d tau for states with last axis (X, Y, Z, Y1, Z1)."""
    X, Y, Z, Y1, Z1 = np.moveaxis(s, -1, 0)
    out = np.empty_like(s)
    out[..., 0] = -sigma * X + sigma * Y
    out[..., 1] = -X * Z + r * X - Y
    if model == "5DLM":
        out[..., 2] = X * Y - X * Y1 - B * Z
        out[..., 3] = X * Z - 2 * X * Z1 - D_O * Y1
        out[..., 4] = 2 * X * Y1 - 4 * B * Z1
    elif model == "4DLM":
        out[..., 2] = X * Y - X * Y1 - B * Z
        out[..., 3] = X * Z - D_O * Y1
        out[..., 4] = 0.0
    else:
        out[..., 2] = X * Y - (q * X * X if model == "3DLMP" else 0.0) - B * Z
        out[..., 3] = 0.0
        out[..., 4] = 0.0
    return out


def tangent(s, v, r, model="5DLM", q=Q_PAPER, sigma=SIGMA):
    """Jacobian of rhs at s applied to v (the variational equation, eq. 27)."""
    X, Y, Z, Y1, Z1 = np.moveaxis(s, -1, 0)
    dX, dY, dZ, dY1, dZ1 = np.moveaxis(v, -1, 0)
    out = np.empty_like(v)
    out[..., 0] = -sigma * dX + sigma * dY
    out[..., 1] = (r - Z) * dX - dY - X * dZ
    if model == "5DLM":
        out[..., 2] = (Y - Y1) * dX + X * dY - B * dZ - X * dY1
        out[..., 3] = (Z - 2 * Z1) * dX + X * dZ - D_O * dY1 - 2 * X * dZ1
        out[..., 4] = 2 * Y1 * dX + 2 * X * dY1 - 4 * B * dZ1
    elif model == "4DLM":
        out[..., 2] = (Y - Y1) * dX + X * dY - B * dZ - X * dY1
        out[..., 3] = Z * dX + X * dZ - D_O * dY1
        out[..., 4] = 0.0
    else:
        qq = q if model == "3DLMP" else 0.0
        out[..., 2] = (Y - 2 * qq * X) * dX + X * dY - B * dZ
        out[..., 3] = 0.0
        out[..., 4] = 0.0
    return out


def rk4_step(s, dt, r, model="5DLM", q=Q_PAPER):
    k1 = rhs(s, r, model, q)
    k2 = rhs(s + dt / 2 * k1, r, model, q)
    k3 = rhs(s + dt / 2 * k2, r, model, q)
    k4 = rhs(s + dt * k3, r, model, q)
    return s + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)


def integrate(s0, dt, steps, r, model="5DLM", q=Q_PAPER):
    """States at every step including the start, shape (steps + 1, 5)."""
    out = np.empty((steps + 1, 5))
    s = np.asarray(s0, dtype=float)
    out[0] = s
    for i in range(steps):
        s = rk4_step(s, dt, r, model, q)
        out[i + 1] = s
    return out


def critical_point(r, model="5DLM", q=Q_PAPER, sign=1.0):
    """The nontrivial critical point (X, Y, Z, Y1, Z1): eqs. (19), (21), (22).
    sign picks the +/- branch of X = Y."""
    if model == "4DLM":
        raise ValueError("the 4DLM has no real nontrivial critical point for r > d_o + 1")
    Zc = r - 1.0
    if model == "5DLM":
        Z1c = (-D_O + np.sqrt(D_O ** 2 + 4 * Zc ** 2)) / 4.0
        Xc = sign * np.sqrt(B * (Zc + 2 * Z1c))
        return np.array([Xc, Xc, Zc, Xc / D_O * (Zc - 2 * Z1c), Z1c])
    qq = q if model == "3DLMP" else 0.0
    Xc = sign * np.sqrt(B * Zc / (1.0 - qq))
    return np.array([Xc, Xc, Zc, 0.0, 0.0])


def normalization(r, model="5DLM"):
    """The paper's normalization scales (Xc, Yc, Zc, Y1c, Z1c), always the
    positive branch. Per section 2e the 3DLMP is scaled by the 3DLM's critical
    point (eq. 21), not its own -- which is why Fig. 9a settles at -1.098."""
    c = critical_point(r, "3DLM" if model == "3DLMP" else model)
    c[3:] = np.where(c[3:] == 0.0, 1.0, c[3:])
    return c


def jacobian(s, r, model="5DLM", q=Q_PAPER, sigma=SIGMA):
    """Full Jacobian matrix at s (appendix C's A matrices at a critical point)."""
    n = {"5DLM": 5, "4DLM": 4}.get(model, 3)
    J = np.empty((n, n))
    for j in range(n):
        e = np.zeros(5)
        e[j] = 1.0
        J[:, j] = tangent(s, e, r, model, q, sigma)[:n]
    return J


def linear_growth(r, model="5DLM", q=Q_PAPER, sigma=SIGMA):
    """Largest Re(lambda) at the nontrivial critical point (section 3e)."""
    J = jacobian(critical_point(r, model, q), r, model, q, sigma)
    return float(np.max(np.linalg.eigvals(J).real))


# --------------------------------------------------------------------------
# The fields
# --------------------------------------------------------------------------

SQ2 = np.sqrt(2.0)


def modes(x, z):
    """(M1, M2, M3, M5, M6) on matching arrays x, z (H = 1)."""
    sx, cx = np.sin(L_WAVE * x), np.cos(L_WAVE * x)
    return (SQ2 * sx * np.sin(M_WAVE * z), SQ2 * cx * np.sin(M_WAVE * z),
            np.sin(2 * M_WAVE * z), SQ2 * cx * np.sin(3 * M_WAVE * z),
            np.sin(4 * M_WAVE * z))


def theta(state, r, x, z):
    """Temperature perturbation / Delta T at (x, z) for one state (eq. 8, with
    C2 = Delta T / (pi r))."""
    X, Y, Z, Y1, Z1 = state
    _m1, m2, m3, m5, m6 = modes(x, z)
    return (Y * m2 - Z * m3 + Y1 * m5 - Z1 * m6) / (np.pi * r)


def theta_parts(state, r, x, z):
    """theta split into its mode contributions: dict name -> field."""
    X, Y, Z, Y1, Z1 = state
    _m1, m2, m3, m5, m6 = modes(x, z)
    k = 1.0 / (np.pi * r)
    return {"Y M2": k * Y * m2, "-Z M3": -k * Z * m3,
            "Y1 M5": k * Y1 * m5, "-Z1 M6": -k * Z1 * m6}


def stream_shape(x, z):
    """psi / (C1 X): the roll's fixed shape, M1. Every streamline is a level
    set of this, and the flow only changes speed and direction (with X)."""
    return SQ2 * np.sin(L_WAVE * x) * np.sin(M_WAVE * z)


def velocity(X, x, z):
    """(dx/dtau, dz/dtau) of a fluid parcel."""
    return (-SQ2 * X * np.sin(L_WAVE * x) * np.cos(M_WAVE * z) / (A * np.pi),
            SQ2 * X * np.cos(L_WAVE * x) * np.sin(M_WAVE * z) / np.pi)


def z_budget(s, model="5DLM", q=Q_PAPER):
    """The terms of dZ/dtau as plotted in Fig. 6: (XY, bZ, XY1 or qX^2).
    dZ/dtau = XY - bZ - third."""
    X, Y, Z, Y1, _Z1 = np.moveaxis(np.asarray(s), -1, 0)
    third = (X * Y1 if model in ("5DLM", "4DLM")
             else (q * X * X if model == "3DLMP" else 0.0 * X))
    return X * Y, B * Z, third


def linear_rc(model="5DLM", q=Q_PAPER, sigma=SIGMA, lo=1.5, hi=200.0):
    """r at which the nontrivial critical point loses stability (Re lambda = 0),
    by bisection; None if it is still stable at hi."""
    if linear_growth(hi, model, q, sigma) < 0:
        return None
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if linear_growth(mid, model, q, sigma) < 0 else (lo, mid)
    return 0.5 * (lo + hi)
