#!/usr/bin/env python3
"""
verify_geomag.py — independent checks on geomag.py's field synthesis.

Four checks, none of which reuse geomag.py's own machinery for the answer:

 1. IGRF-14 vs. the `ppigrf` package (a separate, independently written
    implementation reading the same .shc file).  Optional — skipped with a
    notice if ppigrf is not importable.  Point it at an extracted copy with
    PPIGRF_PATH=<dir> if it is not installed.
 2. The axial-dipole analytic limit: with only g10 nonzero the field must be
    exactly Z = -2 g10 cos(theta), X = g10 sin(theta), Y = 0.
 3. Observed dip-pole positions, which are published independently of any
    single model and are what a compass actually does.
 4. gufm1 vs. IGRF-14 across their 1900-1990 overlap: two models built from
    largely different data must agree if both are right.

Usage:  python verify_geomag.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geomag                                                     # noqa: E402

fails: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail
                                                      else ""))
    if not ok:
        fails.append(label)


SITES = [("Greenwich", 51.48, 0.0), ("Boulder", 40.02, -105.27),
         ("Cape Town", -33.92, 18.42), ("Sydney", -33.87, 151.21),
         ("Singapore", 1.35, 103.82), ("Reykjavik", 64.13, -21.90),
         ("Rio", -22.91, -43.17), ("Anchorage", 61.22, -149.90)]

# ---------------------------------------------------------------------------
print("\n1. IGRF-14 vs. the independent `ppigrf` implementation")
# ---------------------------------------------------------------------------
if os.environ.get("PPIGRF_PATH"):
    sys.path.insert(0, os.environ["PPIGRF_PATH"])
try:
    import ppigrf
    worst_F, worst_D, worst_I = 0.0, 0.0, 0.0
    for year in (1905.0, 1950.0, 1985.5, 2000.0, 2020.0, 2025.0):
        # ppigrf takes a datetime; converting the decimal year with its own
        # helper keeps both codes on the identical epoch. (Using a naive
        # July 1st instead shifts ppigrf by half a year of secular variation
        # and shows up as a ~60 nT "disagreement" that is entirely ours.)
        date = ppigrf.ppigrf.yearfrac_to_datetime(np.array([year]))[0]
        for name, lat, lon in SITES:
            # Compare in the geocentric frame both codes actually solve in.
            r = geomag.A_REF_KM
            theta = 90.0 - lat
            Br, Bth, Bph = ppigrf.igrf_gc(r, theta, lon, date)
            # ppigrf geocentric -> local: X(north) = -Bth, Y(east) = Bph,
            # Z(down) = -Br
            pX, pY, pZ = (float(np.ravel(-Bth)[0]), float(np.ravel(Bph)[0]),
                          float(np.ravel(-Br)[0]))
            pF = np.sqrt(pX ** 2 + pY ** 2 + pZ ** 2)
            pD = np.degrees(np.arctan2(pY, pX))
            pI = np.degrees(np.arctan2(pZ, np.hypot(pX, pY)))

            m = geomag.field_at(year, lat, lon)
            gF, gD, gI = float(m["F"]), float(m["D"]), float(m["I"])
            worst_F = max(worst_F, abs(gF - pF))
            worst_D = max(worst_D, abs((gD - pD + 180) % 360 - 180))
            worst_I = max(worst_I, abs(gI - pI))
    print(f"     8 sites x 6 epochs; worst |dF| {worst_F:.3e} nT, "
          f"|dD| {worst_D:.3e} deg, |dI| {worst_I:.3e} deg")
    # 0.1 nT out of a ~50,000 nT field is 2 ppm — the level at which two
    # independent implementations differ only in summation order and in how
    # each rounds the epoch interpolation, not in physics.
    check(worst_F < 0.1 and worst_D < 1e-3 and worst_I < 1e-3,
          "matches ppigrf to 2 ppm of field strength")
except ImportError:
    print("     ppigrf not importable — skipping this check "
          "(set PPIGRF_PATH=<dir> to enable it)")

# ---------------------------------------------------------------------------
print("\n2. Axial-dipole analytic limit")
# ---------------------------------------------------------------------------
g = np.zeros((2, 2))
h = np.zeros((2, 2))
g[1, 0] = -30000.0
lats = np.array([-80.0, -45.0, 0.0, 30.0, 60.0, 85.0])
res = geomag.synth(g, h, lats, np.zeros_like(lats))
th = np.radians(90.0 - lats)
# B = -grad V, so for the axial dipole X = -g10 sin(theta): with Earth's
# negative g10 that is a NORTHWARD horizontal field, which is what a compass
# does. Z = -2 g10 cos(theta) is downward in the northern hemisphere.
want_X = -g[1, 0] * np.sin(th)
want_Z = -2.0 * g[1, 0] * np.cos(th)
check(np.allclose(res["X"], want_X, atol=1e-9)
      and np.allclose(res["Z"], want_Z, atol=1e-9)
      and np.allclose(res["Y"], 0.0, atol=1e-9),
      "X = g10 sin(theta), Z = -2 g10 cos(theta), Y = 0",
      f"max err {max(np.abs(res['X']-want_X).max(), np.abs(res['Z']-want_Z).max()):.2e} nT")
# Sign sanity: Earth's g10 is negative, so the field must point north and,
# in the northern hemisphere, downward.
res60 = geomag.field_at(2020.0, 60.0, 0.0)
check(float(res60["X"]) > 0 and float(res60["Z"]) > 0,
      "real field at 60N points north and downward",
      f"X={float(res60['X']):.0f} nT Z={float(res60['Z']):.0f} nT")

# ---------------------------------------------------------------------------
print("\n3. Observed dip-pole positions")
# ---------------------------------------------------------------------------
# Observed / survey-derived dip-pole positions (NOAA NCEI and BGS North and
# South Magnetic Pole tables). These come from actual magnetic surveys, so
# they are an outside check rather than another model. Compared as a
# great-circle separation, since near the pole a tiny position error spans a
# huge longitude difference; 2 deg is ~220 km, well inside the scatter
# between published pole determinations themselves.
POLES = [(1900.0, True, 70.5, -96.2), (1948.0, True, 73.9, -100.9),
         (2001.0, True, 81.3, -110.8), (2020.0, True, 86.50, 164.04),
         (1962.0, False, -67.5, 140.0), (2000.0, False, -64.7, 138.0),
         (2020.0, False, -64.07, 135.88)]


def great_circle(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(lon2 - lon1)
    return float(np.degrees(np.arccos(np.clip(
        np.sin(p1) * np.sin(p2) + np.cos(p1) * np.cos(p2) * np.cos(dl),
        -1, 1))))


for year, north, want_lat, want_lon in POLES:
    lat, lon = geomag.dip_pole(year, north=north)
    sep = great_circle(lat, lon, want_lat, want_lon)
    tag = "N" if north else "S"
    check(sep < 2.0, f"{tag} dip pole {int(year)}",
          f"computed {lat:6.2f},{lon:8.2f}  observed {want_lat:6.2f},"
          f"{want_lon:8.2f}   separation {sep:.2f} deg (~{sep*111:.0f} km)")

# ---------------------------------------------------------------------------
print("\n4. gufm1 vs. IGRF-14 across their 1900-1990 overlap")
# ---------------------------------------------------------------------------
worst = 0.0
rows = []
for year in (1900.0, 1920.0, 1940.0, 1960.0, 1980.0, 1990.0):
    gg, gh = geomag.gufm1_coeffs(year)
    ig, ih = geomag.igrf_coeffs(year)
    lat = np.repeat(np.arange(-80, 81, 20.0), 18)
    lon = np.tile(np.arange(-180, 180, 20.0), 9)
    a = geomag.synth(gg, gh, lat, lon)
    b = geomag.synth(ig, ih, lat, lon)
    rms = float(np.sqrt(np.mean((a["F"] - b["F"]) ** 2)))
    med = float(np.median(np.abs(a["F"] - b["F"])))
    rows.append((year, rms, med))
    worst = max(worst, rms)
for year, rms, med in rows:
    print(f"     {int(year)}:  RMS |F| difference {rms:8.1f} nT   "
          f"median {med:7.1f} nT   ({med/50000*100:.2f}% of a typical 50000 nT)")
check(worst < 1500.0,
      "two independently built models agree to better than ~3% of field",
      f"worst RMS {worst:.0f} nT")

# ---------------------------------------------------------------------------
print("\n5. The South Atlantic Anomaly is where it should be, and growing")
# ---------------------------------------------------------------------------
LA, LO = np.meshgrid(np.arange(-60.0, 20.1, 2.0),
                     np.arange(-100.0, 40.1, 2.0), indexing="ij")
lat, lon = LA.ravel(), LO.ravel()
mins = []
for year in (1600.0, 1700.0, 1800.0, 1900.0, 1950.0, 2000.0, 2025.0):
    F = geomag.field_at(year, lat, lon)["F"]
    k = int(np.argmin(F))
    mins.append((year, float(F[k]), float(lat[k]), float(lon[k])))
    print(f"     {int(year)}:  weakest field in the S Atlantic window "
          f"{F[k]/1000:6.2f} uT at {lat[k]:6.1f} lat {lon[k]:7.1f} lon")
check(mins[-1][1] < mins[0][1],
      "the anomaly's minimum field is weaker now than in 1600",
      f"{mins[0][1]/1000:.1f} uT -> {mins[-1][1]/1000:.1f} uT")

print("\n" + ("ALL CHECKS PASSED" if not fails
             else f"{len(fails)} CHECK(S) FAILED: {fails}"))
sys.exit(1 if fails else 0)
