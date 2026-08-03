#!/usr/bin/env python3
"""
geomag.py — Earth's main magnetic field from published Gauss coefficients.

Self-contained: no runtime dependency beyond numpy/scipy.  Two models are
read straight from their published coefficient files in data/ —

  gufm1   1590-1990  Jackson, Jonkers & Walker (2000), "Four centuries of
                     geomagnetic secular variation from historical records",
                     Phil. Trans. R. Soc. A 358, 957-990.  Degree 14,
                     cubic B-splines in time on 2.5-year knots, built from
                     ~365,000 historical observations, the bulk of them
                     compass bearings logged by merchant and naval mariners.
                     File: data/gufm1.txt (geomag.colorado.edu, redistributed
                     with the permission of Prof. Andrew Jackson).

  IGRF-14 1900-2030  International Geomagnetic Reference Field, 14th
                     generation (IAGA Working Group V-MOD, 2024).  Degree 13,
                     5-yearly epochs with linear interpolation between them.
                     File: data/IGRF14.shc.

Both are spherical-harmonic (Gauss) expansions of the scalar potential

    V(r,th,ph) = a * SUM_n (a/r)^(n+1) SUM_m [g_n^m cos(m ph)
                                              + h_n^m sin(m ph)] P_n^m(cos th)

with Schmidt semi-normalised associated Legendre functions P_n^m and
a = 6371.2 km.  B = -grad V, reported in the local geodetic frame as
X (north), Y (east), Z (down), plus F, declination D and inclination I.

Verified in verify_geomag.py against the independent `ppigrf` package, the
IGRF's own published dipole coefficients, and observed dip-pole positions.
"""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import numpy as np

A_REF_KM = 6371.2                    # geomagnetic reference radius
DATA = Path(__file__).resolve().parent / "data"


# ---------------------------------------------------------------------------
# Schmidt semi-normalised associated Legendre functions and d/d(theta)
# ---------------------------------------------------------------------------
def legendre_schmidt(nmax: int, theta: np.ndarray):
    """P[n][m](cos theta) and dP/dtheta, Schmidt semi-normalised.

    theta is an array of colatitudes in radians.  Returns two
    (nmax+1, nmax+1, len(theta)) arrays.  Standard recursion, the same one
    the IGRF's own reference implementation uses.
    """
    theta = np.atleast_1d(np.asarray(theta, dtype=float))
    ct, st = np.cos(theta), np.sin(theta)
    P = np.zeros((nmax + 1, nmax + 1, theta.size))
    dP = np.zeros_like(P)
    P[0, 0] = 1.0

    for n in range(1, nmax + 1):
        for m in range(0, n + 1):
            if m == n:
                k = math.sqrt(1.0 - 1.0 / (2.0 * n)) if n > 1 else 1.0
                P[n, n] = k * (st * P[n - 1, n - 1])
                dP[n, n] = k * (st * dP[n - 1, n - 1] + ct * P[n - 1, n - 1])
            else:
                d = math.sqrt(n * n - m * m)
                a1 = (2 * n - 1) / d
                P[n, m] = a1 * ct * P[n - 1, m]
                dP[n, m] = a1 * (ct * dP[n - 1, m] - st * P[n - 1, m])
                if n - 2 >= m:
                    a2 = math.sqrt((n - 1) ** 2 - m * m) / d
                    P[n, m] -= a2 * P[n - 2, m]
                    dP[n, m] -= a2 * dP[n - 2, m]
    return P, dP


# ---------------------------------------------------------------------------
# Field synthesis
# ---------------------------------------------------------------------------
def synth(g: np.ndarray, h: np.ndarray, lat_deg, lon_deg,
          r_km: float = A_REF_KM):
    """Field from Gauss coefficients at geocentric lat/lon (degrees).

    g, h are (nmax+1, nmax+1) arrays in nT.  Returns a dict of arrays:
    X (north), Y (east), Z (down), H (horizontal), F (total) in nT, and
    D (declination) and I (inclination) in degrees.
    """
    nmax = g.shape[0] - 1
    lat, lon = np.broadcast_arrays(np.asarray(lat_deg, dtype=float),
                                   np.asarray(lon_deg, dtype=float))
    shape = lat.shape          # () for scalar input, so float() still works
    lat, lon = np.atleast_1d(lat).ravel(), np.atleast_1d(lon).ravel()

    # Guard the poles: 1/sin(theta) appears in the east component.
    theta = np.radians(90.0 - np.clip(lat, -89.9999, 89.9999))
    phi = np.radians(lon)
    P, dP = legendre_schmidt(nmax, theta)
    st = np.sin(theta)

    X = np.zeros_like(theta)
    Y = np.zeros_like(theta)
    Z = np.zeros_like(theta)
    ar = A_REF_KM / r_km
    for n in range(1, nmax + 1):
        f = ar ** (n + 2)
        for m in range(0, n + 1):
            cm, sm = np.cos(m * phi), np.sin(m * phi)
            gc_hs = g[n, m] * cm + h[n, m] * sm
            gs_hc = g[n, m] * sm - h[n, m] * cm
            X += f * gc_hs * dP[n, m]
            if m:
                Y += f * (m / st) * gs_hc * P[n, m]
            Z -= f * (n + 1) * gc_hs * P[n, m]

    H = np.hypot(X, Y)
    out = dict(X=X, Y=Y, Z=Z, H=H, F=np.hypot(H, Z),
               D=np.degrees(np.arctan2(Y, X)),
               I=np.degrees(np.arctan2(Z, H)))
    return {k: v.reshape(shape) for k, v in out.items()}


# ---------------------------------------------------------------------------
# IGRF-14 (.shc: epochs + piecewise-linear interpolation)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _load_igrf(path: str = None):
    p = Path(path) if path else DATA / "IGRF14.shc"
    lines = [ln for ln in p.read_text().splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    hdr = lines[0].split()
    nmin, nmax, nepochs = int(hdr[0]), int(hdr[1]), int(hdr[2])
    years = np.array([float(x) for x in lines[1].split()])
    assert len(years) == nepochs, "SHC epoch row does not match the header"
    G = np.zeros((nmax + 1, nmax + 1, nepochs))
    H = np.zeros_like(G)
    for ln in lines[2:]:
        parts = ln.split()
        n, m = int(parts[0]), int(parts[1])
        vals = np.array([float(x) for x in parts[2:2 + nepochs]])
        if m >= 0:
            G[n, m] = vals
        else:
            H[n, -m] = vals
    _ = nmin
    return years, G, H


def igrf_coeffs(year: float, path: str = None):
    """Gauss coefficients (g, h) in nT at a decimal year, 1900-2030."""
    years, G, H = _load_igrf(path)
    y = float(np.clip(year, years[0], years[-1]))
    k = int(np.searchsorted(years, y, side="right") - 1)
    k = min(max(k, 0), len(years) - 2)
    f = (y - years[k]) / (years[k + 1] - years[k])
    g = G[:, :, k] + f * (G[:, :, k + 1] - G[:, :, k])
    h = H[:, :, k] + f * (H[:, :, k + 1] - H[:, :, k])
    return g, h


IGRF_RANGE = (1900.0, 2030.0)


# ---------------------------------------------------------------------------
# gufm1 (cubic B-splines in time)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _load_gufm1(path: str = None):
    """Parse gufm1.txt.

    Layout (matching the model's own Fortran reader):
        line 1            free-text title
        then, whitespace-separated:
            lmax, nspl
            knots[nspl + 4]                    cubic B-spline knot vector
            coeffs[nspl][lmax*(lmax+2)]        harmonic index varies fastest
    """
    p = Path(path) if path else DATA / "gufm1.txt"
    text = p.read_text().splitlines()
    tok = " ".join(text[1:]).split()
    lmax, nspl = int(tok[0]), int(tok[1])
    nco = lmax * (lmax + 2)
    knots = np.array([float(x) for x in tok[2:2 + nspl + 4]])
    flat = np.array([float(x) for x in tok[2 + nspl + 4:]])
    assert flat.size == nspl * nco, (
        f"gufm1: expected {nspl * nco} coefficients, found {flat.size}")
    coeffs = flat.reshape(nspl, nco)          # [spline, harmonic]
    return lmax, nspl, knots, coeffs


def _harmonic_index(lmax: int):
    """Map the flat gufm1 harmonic ordering to (n, m, is_h) triples.

    Order is the standard g10, g11, h11, g20, g21, h21, g22, h22, ...
    """
    out = []
    for n in range(1, lmax + 1):
        out.append((n, 0, False))
        for m in range(1, n + 1):
            out.append((n, m, False))
            out.append((n, m, True))
    return out


@lru_cache(maxsize=1)
def _gufm1_spline():
    from scipy.interpolate import BSpline
    lmax, nspl, knots, coeffs = _load_gufm1()
    # BSpline(t, c, k) evaluates SUM_i c_i N_{i,k+1}(x) — exactly gufm1's
    # cubic (k=3) representation, with c shaped (nspl, ncoeff).
    return lmax, BSpline(knots, coeffs, 3, extrapolate=False)


GUFM1_RANGE = (1590.0, 1990.0)


def gufm1_coeffs(year: float):
    """Gauss coefficients (g, h) in nT at a decimal year, 1590-1990."""
    lmax, spl = _gufm1_spline()
    y = float(np.clip(year, *GUFM1_RANGE))
    vec = np.asarray(spl(y), dtype=float)
    g = np.zeros((lmax + 1, lmax + 1))
    h = np.zeros_like(g)
    for k, (n, m, is_h) in enumerate(_harmonic_index(lmax)):
        (h if is_h else g)[n, m] = vec[k]
    return g, h


# ---------------------------------------------------------------------------
# Unified accessor
# ---------------------------------------------------------------------------
def coeffs_for(year: float):
    """Best available coefficients for a year, and which model supplied them.

    gufm1 below 1900, IGRF from 1900 on — IGRF is the modern standard and is
    constrained by satellite data over its later epochs, while gufm1 is the
    only model that reaches back to the 16th century.  The two agree closely
    across their 1900-1990 overlap (see verify_geomag.py).
    """
    if year < IGRF_RANGE[0]:
        return (*gufm1_coeffs(year), "gufm1")
    return (*igrf_coeffs(year), "IGRF-14")


def field_at(year: float, lat_deg, lon_deg, r_km: float = A_REF_KM):
    g, h, model = coeffs_for(year)
    out = synth(g, h, lat_deg, lon_deg, r_km)
    out["model"] = model
    return out


# ---------------------------------------------------------------------------
# Dip poles (where the field is vertical)
# ---------------------------------------------------------------------------
def dip_pole(year: float, north: bool = True, r_km: float = A_REF_KM):
    """Locate a magnetic dip pole by coarse search then local refinement.

    The dip poles are where inclination reaches +-90 deg; unlike the
    geomagnetic (dipole) poles they are not antipodal, because the real
    field is not a pure dipole.
    """
    g, h, _m = coeffs_for(year)
    target = 90.0 if north else -90.0
    lat_lo, lat_hi = (55.0, 89.9) if north else (-89.9, -55.0)
    lon_lo, lon_hi = -180.0, 180.0
    best = (None, None)
    for step in (4.0, 1.0, 0.25, 0.05, 0.01):
        lats = np.arange(lat_lo, lat_hi + 1e-9, step)
        lons = np.arange(lon_lo, lon_hi + 1e-9, step)
        LA, LO = np.meshgrid(lats, lons, indexing="ij")
        res = synth(g, h, LA, LO, r_km)
        err = np.abs(res["I"] - target)
        k = np.unravel_index(np.argmin(err), err.shape)
        blat, blon = float(LA[k]), float(LO[k])
        best = (blat, blon)
        lat_lo, lat_hi = max(-89.9, blat - step), min(89.9, blat + step)
        # The field is periodic in longitude, so the refinement window is
        # allowed to run past +-180; only the answer needs normalising.
        lon_lo, lon_hi = blon - step, blon + step
    blat, blon = best
    return blat, (blon + 180.0) % 360.0 - 180.0
