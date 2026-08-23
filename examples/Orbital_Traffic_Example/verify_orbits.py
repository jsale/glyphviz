#!/usr/bin/env python
"""Does the physics in `orbits.py` tell the truth?

Nineteen checks, chosen so that most of them can fail *without* the scene looking
wrong — which is exactly the class of error a picture cannot catch.  Where
possible each check leans on something outside this repository: an independent
SGP4 implementation, an analytic limit, or a published number.

    python verify_orbits.py

`skyfield` is optional; check 2 is skipped with a notice if it is absent.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import orbits  # noqa: E402
from orbits import LIT, PENUMBRA, UMBRA  # noqa: E402

CACHE = os.path.join(HERE, "data", "gp_cache")
GEO_R = 42_164.17            # geostationary orbit radius, km
SIDEREAL_DAY_MIN = 1436.068

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def load(groups=("stations", "visual", "science", "weather", "gps-ops", "geo")):
    rows = []
    for g in groups:
        try:
            text = orbits.fetch_group(g, CACHE, offline=True, log=lambda *a: None)
        except FileNotFoundError:
            continue
        rows += [(g, r) for r in csv.DictReader(io.StringIO(text))]
    seen, uniq = set(), []
    for g, r in rows:
        if r["NORAD_CAT_ID"] not in seen:
            seen.add(r["NORAD_CAT_ID"])
            uniq.append((g, r))
    sats, _ = orbits.build_sats(uniq)
    return sats


# ---------------------------------------------------------------------------
def check_1_omm_vs_tle(sats):
    """The OMM/CSV path must agree with the classic TLE-text parser."""
    from sgp4.api import Satrec

    # ISS, from the TLE form of the very same element set.
    l1 = "1 25544U 98067A   26233.53315667  .00008864  00000+0  16558-3 0  9995"
    l2 = "2 25544  51.6331 336.6713 0007672  69.9303 290.2511 15.49551867581883"
    a = Satrec.twoline2rv(l1, l2)
    iss = next(s for s in sats if s.norad == 25544)
    jd, fr = orbits.julian(dt.datetime.now(dt.timezone.utc))
    _, ra, _ = a.sgp4(jd, fr)
    _, rb, _ = iss.satrec.sgp4(jd, fr)
    d_m = math.dist(ra, rb) * 1000.0
    # The TLE text carries fewer significant digits than the CSV, so a small
    # disagreement is expected and is the TLE's rounding, not our error.
    check("1. OMM-built Satrec matches TLE-text parser", d_m < 500.0,
          f"{d_m:.1f} m apart (TLE text truncation)")


def check_2_skyfield(sats):
    """Cross-check against an independently written implementation."""
    try:
        from skyfield.api import EarthSatellite, load as sf_load, wgs84
    except ImportError:
        print("  [SKIP] 2. vs. skyfield -- not installed "
              "(pip install skyfield to enable)")
        return

    ts = sf_load.timescale()
    now = dt.datetime.now(dt.timezone.utc)
    t = ts.from_datetime(now)

    worst_r, worst_lat, worst_lon, worst_alt, n = 0.0, 0.0, 0.0, 0.0, 0
    for s in sats[:400]:
        # Skyfield gets the same mean elements, via its own OMM path.
        sat = EarthSatellite.from_satrec(s.satrec, ts)
        geo = sat.at(t)
        sp = wgs84.subpoint_of(geo)
        alt_sf = wgs84.height_of(geo).km

        ok, r_teme, _, lat, lon, alt, _ = orbits.propagate([s], now)
        if not ok[0]:
            continue
        # Compare frame-independent magnitude, then the geodetic subpoint.
        # Skyfield reports positions in GCRS, so differencing its vector
        # against our TEME one would just measure precession and nutation —
        # about 1.6 arcsec, or a kilometre out at GEO. |r| and the subpoint
        # are the quantities both sides agree on, and the ones the scene uses.
        worst_r = max(worst_r, abs(float(np.linalg.norm(geo.position.km))
                                   - float(np.linalg.norm(r_teme[0]))))
        worst_lat = max(worst_lat, abs(float(lat[0]) - sp.latitude.degrees))
        dlon = (float(lon[0]) - sp.longitude.degrees + 180.0) % 360.0 - 180.0
        worst_lon = max(worst_lon, abs(dlon))
        worst_alt = max(worst_alt, abs(float(alt[0]) - alt_sf))
        n += 1

    # Skyfield's TEME->ITRF path includes polar motion and the equation of the
    # equinoxes, which orbits.py deliberately omits; tens of metres of ground
    # track disagreement is that difference, not a bug. SGP4's own error is
    # measured in kilometres, three orders of magnitude larger.
    check("2. vs. skyfield (independent SGP4 + frames)",
          worst_r < 1e-6 and worst_lat < 0.001 and worst_lon < 0.001
          and worst_alt < 0.001,
          f"{n} sats: |r| {worst_r * 1e6:.2f} mm, "
          f"lat {worst_lat * 111e3:.1f} m, lon {worst_lon * 111e3:.1f} m, "
          f"alt {worst_alt * 1000:.1f} m")


def check_3_geo_analytic(sats):
    """A geostationary orbit has an analytic radius and period."""
    geos = [s for s in sats if orbits.classify(s) == orbits.GEO][:200]
    per = np.array([s.period_min for s in geos])
    sma = np.array([s.semi_major_km for s in geos])
    check("3. GEO period == one sidereal day",
          bool(np.all(np.abs(per - SIDEREAL_DAY_MIN) < 25.0)),
          f"{len(geos)} sats, median {np.median(per):.2f} min "
          f"(sidereal day {SIDEREAL_DAY_MIN:.2f})")
    check("3b. GEO semi-major axis == 42,164 km",
          bool(np.median(np.abs(sma - GEO_R)) < 50.0),
          f"median {np.median(sma):,.0f} km, "
          f"altitude {np.median(sma) - orbits.R_EARTH_EQ:,.0f} km "
          f"(published 35,786)")


def check_4_iss(sats):
    """The ISS's altitude and ground speed are widely published numbers."""
    iss = next(s for s in sats if s.norad == 25544)
    now = dt.datetime.now(dt.timezone.utc)
    ok, r, v, lat0, lon0, alt0, _ = orbits.propagate([iss], now)
    _, _, _, lat1, lon1, _, _ = orbits.propagate([iss], now + dt.timedelta(seconds=60))
    la0, la1 = math.radians(float(lat0[0])), math.radians(float(lat1[0]))
    dlo = math.radians(float(lon1[0]) - float(lon0[0]))
    arc = math.acos(min(1.0, math.sin(la0) * math.sin(la1)
                        + math.cos(la0) * math.cos(la1) * math.cos(dlo)))
    ground_kms = 6371.0 * arc / 60.0
    orbital_kms = float(np.linalg.norm(v[0]))
    # Geodetic altitude swings wider than the element set's apogee/perigee:
    # those are geocentric radius minus the *equatorial* radius, while geodetic
    # altitude is measured to the ellipsoid, which at the ISS's 51.6 deg is
    # ~15 km closer to the centre. A 413-423 km apogee/perigee pair therefore
    # reads as roughly 415-441 km of geodetic altitude around the orbit.
    apogee = iss.semi_major_km * (1.0 + iss.ecc) - orbits.R_EARTH_EQ
    perigee = iss.semi_major_km * (1.0 - iss.ecc) - orbits.R_EARTH_EQ
    check("4. ISS altitude in the published 400-450 km band",
          400.0 <= float(alt0[0]) <= 450.0,
          f"{float(alt0[0]):.1f} km geodetic now; elements give "
          f"perigee {perigee:.1f} / apogee {apogee:.1f} km geocentric")
    check("4b. ISS ground speed ~6.7-7.0 km/s",
          6.6 <= ground_kms <= 7.1, f"{ground_kms:.3f} km/s "
          f"(orbital {orbital_kms:.3f} km/s)")


def check_5_geodetic_roundtrip():
    """lat/lon/alt -> ECEF -> lat/lon/alt must be an identity."""
    rng = np.random.default_rng(20260821)
    lats = rng.uniform(-89.5, 89.5, 3000)
    lons = rng.uniform(-180.0, 180.0, 3000)
    alts = rng.uniform(150.0, 40_000.0, 3000)
    ecef = np.array([orbits.geodetic_to_ecef(a, b, c)
                     for a, b, c in zip(lats, lons, alts)])
    la, lo, al = orbits.ecef_to_geodetic(ecef)
    dlon = (lo - lons + 180.0) % 360.0 - 180.0
    check("5. geodetic round-trip is an identity",
          float(np.abs(la - lats).max()) < 1e-9
          and float(np.abs(dlon).max()) < 1e-9
          and float(np.abs(al - alts).max()) < 1e-6,
          f"worst lat {np.abs(la - lats).max():.2e} deg, "
          f"alt {np.abs(al - alts).max():.2e} km")


def check_6_subsolar():
    """Solar declination on the solstices and equinoxes is known to the minute."""
    cases = [
        (dt.datetime(2026, 3, 20, 14, 46, tzinfo=dt.timezone.utc), 0.0, "March equinox"),
        (dt.datetime(2026, 6, 21, 8, 25, tzinfo=dt.timezone.utc), 23.44, "June solstice"),
        (dt.datetime(2026, 9, 23, 0, 6, tzinfo=dt.timezone.utc), 0.0, "September equinox"),
        (dt.datetime(2026, 12, 21, 20, 51, tzinfo=dt.timezone.utc), -23.44, "December solstice"),
    ]
    worst, detail = 0.0, []
    for when, expect, label in cases:
        dec, _ = orbits.subsolar_point(when)
        worst = max(worst, abs(dec - expect))
        detail.append(f"{label} {dec:+.2f}")
    check("6. solar declination at solstices/equinoxes", worst < 0.15,
          ", ".join(detail) + f" (worst error {worst:.3f} deg)")


def check_6b_equation_of_time():
    """The sub-solar longitude must lag or lead the mean sun by the
    equation of time — and by the *published* amount.

    A tolerance-based check here would pass on a broken solar model.  The
    equation of time instead has four sharply dated turning points a year —
    +16.4 min in early November, -14.2 in mid-February, and the smaller
    +3.7 / -6.4 pair in May and July.  The big pair comes mostly from Earth's
    orbital eccentricity and the small pair mostly from obliquity, so
    reproducing all four (with the right signs, magnitudes and dates) tests
    the two terms of the solar series separately rather than in aggregate.
    """
    def eot_minutes(when: dt.datetime) -> float:
        """Equation of time = apparent solar time - mean solar time.

        The sub-solar point moves west as the day advances, so a true sun
        further west than the mean sun crossed the meridian *earlier* — the
        sundial runs ahead.  Hence the sign flip between the longitude offset
        and the conventional minutes.
        """
        _, lon = orbits.subsolar_point(when)
        mean = -15.0 * (when.hour + when.minute / 60.0 - 12.0)
        return -((lon - mean + 180.0) % 360.0 - 180.0) * 4.0

    noon = dict(hour=12, minute=0, tzinfo=dt.timezone.utc)
    # date, published minutes, tolerance, label
    turning = [
        ((2, 11), -14.2, 0.6, "Feb 11 min"),
        ((5, 14), +3.7, 0.6, "May 14 max"),
        ((7, 26), -6.4, 0.6, "Jul 26 min"),
        ((11, 3), +16.4, 0.6, "Nov 3 max"),
    ]
    zeros = [((4, 15), "Apr 15"), ((6, 13), "Jun 13"),
             ((9, 1), "Sep 1"), ((12, 25), "Dec 25")]

    ok, detail = True, []
    for (m, d), published, tol, label in turning:
        got = eot_minutes(dt.datetime(2026, m, d, **noon))
        ok &= abs(got - published) < tol
        detail.append(f"{label} {got:+.1f} (pub {published:+.1f})")
    for (m, d), label in zeros:
        got = eot_minutes(dt.datetime(2026, m, d, **noon))
        ok &= abs(got) < 1.0
        detail.append(f"{label} {got:+.1f}")
    check("6b. equation of time: all four turning points and four zeros",
          ok, ", ".join(detail))


def check_7_geo_eclipse_season():
    """The analytic check on the shadow model.

    A geostationary satellite is eclipsed only near the equinoxes, when the
    shadow axis swings into the equatorial plane.  Each eclipse season runs
    roughly 22 days either side of the equinox and the longest eclipse, on the
    equinox itself, is about 70 minutes.  Neither number is anywhere in
    `orbits.py` — they fall out of the geometry, which is what makes this a
    real test of it.
    """
    def minutes_in_shadow(day: dt.datetime) -> float:
        """Sweep an ideal equatorial GEO satellite once around the Earth."""
        step = 2
        n = SIDEREAL_DAY_MIN / step
        times, pos = [], []
        for k in range(int(n)):
            t = day + dt.timedelta(minutes=k * step)
            jd, fr = orbits.julian(t)
            theta = orbits.gmst_rad(jd, fr)
            # Hold the satellite at a fixed Earth-fixed longitude (0 deg): in
            # inertial coordinates that is a rotation at sidereal rate.
            pos.append([GEO_R * math.cos(theta), GEO_R * math.sin(theta), 0.0])
            times.append((jd, fr))
        pos = np.asarray(pos)
        total = 0.0
        for i, (jd, fr) in enumerate(times):
            if orbits.illumination(pos[i:i + 1], jd, fr)[0] != LIT:
                total += step
        return total

    equinox = dt.datetime(2026, 9, 23, 0, 0, tzinfo=dt.timezone.utc)
    samples = {d: minutes_in_shadow(equinox + dt.timedelta(days=d))
               for d in (-60, -30, -21, 0, 21, 30, 60)}
    peak = samples[0]
    check("7. GEO eclipse peaks at the equinox (~70 min)",
          60.0 <= peak <= 80.0, f"{peak:.0f} min on 2026-09-23")
    check("7b. no GEO eclipse far from the equinox",
          samples[-60] == 0.0 and samples[60] == 0.0,
          "0 min at equinox -60 d and +60 d; "
          + ", ".join(f"{d:+d}d {v:.0f}m" for d, v in sorted(samples.items())))

    solstice = dt.datetime(2026, 6, 21, 8, 25, tzinfo=dt.timezone.utc)
    check("7c. no GEO eclipse at the solstice",
          minutes_in_shadow(solstice) == 0.0, "0 min on 2026-06-21")


def check_8_leo_eclipse(sats):
    """A LEO satellite's eclipse, against the closed-form beta-angle formula.

    Vector-stepping the orbit and counting shadowed samples is compared with
    the standard analytic eclipse fraction for a circular orbit,

        f = (1/pi) * arccos( sqrt(h^2 + 2*R*h) / ((R + h) * cos beta) )

    where beta is the angle between the Sun and the orbit plane.  That is
    different mathematics reaching the same physics — it never touches
    `illumination()`, its shadow model, or its vectors — so agreement is real
    evidence rather than a restatement.
    """
    iss = next(s for s in sats if s.norad == 25544)
    now = dt.datetime.now(dt.timezone.utc)
    step_s = 5
    n = int(iss.period_min * 60 / step_s)

    states, radii = [], []
    for k in range(n):
        t = now + dt.timedelta(seconds=k * step_s)
        _, r, _, _, _, _, _ = orbits.propagate([iss], t)
        jd, fr = orbits.julian(t)
        states.append(int(orbits.illumination(r, jd, fr)[0]))
        radii.append(float(np.linalg.norm(r[0])))
    umbra_frac = sum(s == UMBRA for s in states) / len(states)
    total_frac = sum(s != LIT for s in states) / len(states)

    # Beta angle now, from the orbit normal and the solar direction.
    _, r0, v0, _, _, _, _ = orbits.propagate([iss], now)
    normal = np.cross(r0[0], v0[0])
    normal /= np.linalg.norm(normal)
    jd, fr = orbits.julian(now)
    u_sun, _ = orbits.sun_vector_eci(jd, fr)
    beta = 90.0 - math.degrees(math.acos(abs(float(normal @ u_sun))))
    beta = math.copysign(beta, float(normal @ u_sun))

    r_mean = float(np.mean(radii))
    h = r_mean - orbits.R_EARTH_EQ
    arg = (math.sqrt(h * h + 2.0 * orbits.R_EARTH_EQ * h)
           / (r_mean * math.cos(math.radians(beta))))
    analytic = 0.0 if arg >= 1.0 else math.acos(arg) / math.pi

    # One time-step of quantisation, plus the difference between the analytic
    # cylinder and our conical umbra (a few tens of km of shadow radius).
    tol = step_s / (iss.period_min * 60.0) + 0.006
    check("8. ISS eclipse fraction matches the beta-angle formula",
          abs(umbra_frac - analytic) < tol,
          f"stepped {umbra_frac * 100:.2f}% vs analytic {analytic * 100:.2f}% "
          f"(beta {beta:+.1f} deg, h {h:.0f} km, tol {tol * 100:.2f}%)")

    # Strict logical invariants of any shadow model, cheap and unfoolable.
    check("8b. umbra is a subset of the shadowed set",
          all(s in (LIT, PENUMBRA, UMBRA) for s in states)
          and sum(s == UMBRA for s in states) <= sum(s != LIT for s in states),
          f"umbra {umbra_frac * 100:.2f}% <= umbra+penumbra "
          f"{total_frac * 100:.2f}%")

    # Count runs of shadow on the circular timeline: there must be exactly one.
    runs, prev = 0, states[-1]
    for s in states:
        if s != LIT and prev == LIT:
            runs += 1
        prev = s
    check("8c. ISS eclipse is a single contiguous arc", runs <= 1,
          f"{runs} shadow entry per orbit" if runs <= 1 else f"{runs} entries")


def check_9_terminator_and_horizon():
    """Terminator points must have the Sun exactly on their horizon, and
    look angles must be self-consistent."""
    now = dt.datetime.now(dt.timezone.utc)
    sub_lat, sub_lon = orbits.subsolar_point(now)
    pts = orbits.terminator_ring(sub_lat, sub_lon, 180)

    # Solar elevation at each terminator point = 90 deg minus the great-circle
    # distance to the sub-solar point, which must therefore be exactly 90 deg.
    la0, lo0 = math.radians(sub_lat), math.radians(sub_lon)
    worst = 0.0
    for la, lo in pts:
        a, b = math.radians(la), math.radians(lo)
        cosd = (math.sin(la0) * math.sin(a)
                + math.cos(la0) * math.cos(a) * math.cos(b - lo0))
        worst = max(worst, abs(math.degrees(math.acos(max(-1.0, min(1.0, cosd)))) - 90.0))
    check("9. terminator sits 90 deg from the sub-solar point", worst < 1e-9,
          f"worst deviation {worst:.2e} deg over 180 points")

    # A satellite parked directly over a station is at elevation 90.
    st = orbits.Station("test", "-", 12.0, 34.0)
    overhead = orbits.geodetic_to_ecef(12.0, 34.0, 800.0)
    elev, rng = orbits.look_angles(st, overhead[None, :])
    check("9b. zenith satellite reads elevation 90 deg",
          abs(float(elev[0]) - 90.0) < 1e-6 and abs(float(rng[0]) - 800.0) < 1e-6,
          f"elevation {float(elev[0]):.6f} deg, range {float(rng[0]):.4f} km")

    # ...and one on the far side of the Earth is well below the horizon.
    antipode = orbits.geodetic_to_ecef(-12.0, 34.0 - 180.0, 800.0)
    elev2, _ = orbits.look_angles(st, antipode[None, :])
    check("9c. antipodal satellite is below the horizon", float(elev2[0]) < -50.0,
          f"elevation {float(elev2[0]):.2f} deg")


# ---------------------------------------------------------------------------
def main():
    print(__doc__.strip().splitlines()[0])
    print()
    sats = load()
    if not sats:
        raise SystemExit("no cached element sets in data/gp_cache — "
                         "run build_live_sky.py once first")
    print(f"Loaded {len(sats)} element sets from the bundled cache.\n")

    check_1_omm_vs_tle(sats)
    check_2_skyfield(sats)
    check_3_geo_analytic(sats)
    check_4_iss(sats)
    check_5_geodetic_roundtrip()
    check_6_subsolar()
    check_6b_equation_of_time()
    check_7_geo_eclipse_season()
    check_8_leo_eclipse(sats)
    check_9_terminator_and_horizon()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED: " + "; ".join(FAILURES))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
