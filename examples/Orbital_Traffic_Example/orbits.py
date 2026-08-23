"""Orbital mechanics for the Live Sky scene.

Everything the generator needs that is physics rather than CSV plumbing:
fetching and caching CelesTrak GP element sets, SGP4 propagation, the
TEME -> ECEF -> geodetic chain, the solar direction, the conical shadow test
that decides whether a satellite is in sunlight, and ground-station look
angles.

Nothing in here knows about GlyphViz.  `verify_orbits.py` checks it against
independent implementations and against analytic limits.
"""

from __future__ import annotations

import datetime as dt
import math
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

import numpy as np
from sgp4.api import Satrec, SatrecArray, jday

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
R_EARTH_EQ = 6378.137                     # WGS-84 semi-major axis, km
F_WGS84 = 1.0 / 298.257223563             # WGS-84 flattening
E2_WGS84 = F_WGS84 * (2.0 - F_WGS84)      # first eccentricity squared
R_SUN = 696_000.0                         # solar radius, km
AU = 149_597_870.7                        # km

CELESTRAK_GP = "https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=csv"
CELESTRAK_SATCAT = "https://celestrak.org/pub/satcat.csv"

# CelesTrak refreshes GP data every 2 hours and temporarily firewalls IPs that
# poll faster than that.  Never shorten this.
GP_MIN_AGE_S = 2 * 3600

USER_AGENT = "GlyphViz Orbital_Traffic_Example (+https://github.com/jsale/glyphviz)"


# ---------------------------------------------------------------------------
# 1. Fetching, with the cache discipline CelesTrak requires
# ---------------------------------------------------------------------------
class NotUpdated(Exception):
    """CelesTrak answered 'GP data has not updated' — use the cache."""


def _fetch(url: str, timeout: float = 60.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _is_gp_csv(body: str) -> bool:
    """A real GP CSV starts with the OMM header.

    CelesTrak answers a too-soon repeat request with **HTTP 200** and a plain
    text body ("GP data has not updated since your last successful download
    of GROUP=... Data is updated once every 2 hours."), not an error status.
    A fetcher that trusts the status code parses that as an empty CSV and
    quietly destroys its own cache, then keeps hammering the server until the
    IP is blocked.  Sniffing the header is the whole defence.
    """
    return body.lstrip().startswith("OBJECT_NAME")


def fetch_group(group: str, cache_dir: str, *, offline: bool = False,
                min_age_s: float = GP_MIN_AGE_S, log=print) -> str:
    """Return the GP CSV text for one CelesTrak group, refreshing politely.

    The cached copy is returned untouched when it is younger than `min_age_s`,
    when the network fails, or when CelesTrak says the data has not changed.
    """
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, f"{group}.csv")
    have = os.path.exists(path)
    age = (time.time() - os.path.getmtime(path)) if have else float("inf")

    if offline or (have and age < min_age_s):
        if not have:
            raise FileNotFoundError(
                f"--offline needs a cached copy of GROUP={group} in {cache_dir}")
        return _read(path)

    try:
        body = _fetch(CELESTRAK_GP.format(group=group))
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        if have:
            log(f"  ! {group}: fetch failed ({e}); using cache "
                f"({age / 3600:.1f} h old)")
            return _read(path)
        raise

    if not _is_gp_csv(body):
        first = " ".join(body.split())[:90]
        if have:
            log(f"  · {group}: not updated upstream; using cache "
                f"({age / 3600:.1f} h old)")
            return _read(path)
        raise NotUpdated(
            f"CelesTrak returned no data for GROUP={group} and there is no "
            f"cache to fall back on: {first!r}")

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(body)
    os.replace(tmp, path)
    log(f"  + {group}: {body.count(chr(10)) - 1} objects (fresh)")
    return body


def fetch_satcat(cache_path: str, *, offline: bool = False,
                 max_age_s: float = 24 * 3600, log=print) -> str:
    """SATCAT metadata (owner, object type, RCS, launch/decay dates)."""
    have = os.path.exists(cache_path)
    age = (time.time() - os.path.getmtime(cache_path)) if have else float("inf")
    if offline or (have and age < max_age_s):
        if not have:
            raise FileNotFoundError(f"--offline needs a cached {cache_path}")
        return _read(cache_path)
    try:
        body = _fetch(CELESTRAK_SATCAT, timeout=120.0)
        if not body.lstrip().startswith("OBJECT_NAME"):
            raise NotUpdated("SATCAT response was not a CSV")
        os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
        tmp = cache_path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            fh.write(body)
        os.replace(tmp, cache_path)
        log(f"  + satcat: {body.count(chr(10)) - 1} rows (fresh)")
        return body
    except Exception as e:
        if have:
            log(f"  ! satcat: {e}; using cache ({age / 3600:.1f} h old)")
            return _read(cache_path)
        raise


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# 2. Element sets -> propagators
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class Sat:
    norad: int
    name: str
    intl_id: str
    group: str
    epoch: dt.datetime
    mean_motion: float          # rev/day
    ecc: float
    inc_deg: float
    satrec: Satrec

    @property
    def period_min(self) -> float:
        return 1440.0 / self.mean_motion

    @property
    def semi_major_km(self) -> float:
        mu = 398_600.4418
        n = self.mean_motion * 2.0 * math.pi / 86400.0      # rad/s
        return (mu / (n * n)) ** (1.0 / 3.0)


def satrec_from_omm(row: dict) -> Satrec:
    """Build a Satrec from OMM/CSV mean elements, bypassing TLE text.

    The CSV carries more significant digits than the 69-character TLE it
    replaces, so this is the more accurate of the two paths — `verify_orbits`
    measures the difference at tens of metres.
    """
    ep = dt.datetime.fromisoformat(row["EPOCH"])
    if ep.tzinfo is None:
        ep = ep.replace(tzinfo=dt.timezone.utc)
    jd, fr = jday(ep.year, ep.month, ep.day, ep.hour, ep.minute,
                  ep.second + ep.microsecond / 1e6)
    s = Satrec()
    s.sgp4init(
        2,                                       # WGS-72, the SGP4 standard
        "i",
        int(row["NORAD_CAT_ID"]),
        (jd + fr) - 2433281.5,                   # epoch, days since 1949-12-31
        float(row["BSTAR"]),
        float(row["MEAN_MOTION_DOT"]),
        float(row["MEAN_MOTION_DDOT"]),
        float(row["ECCENTRICITY"]),
        math.radians(float(row["ARG_OF_PERICENTER"])),
        math.radians(float(row["INCLINATION"])),
        math.radians(float(row["MEAN_ANOMALY"])),
        float(row["MEAN_MOTION"]) * 2.0 * math.pi / 1440.0,   # rad/min
        math.radians(float(row["RA_OF_ASC_NODE"])),
    )
    return s


def build_sats(rows) -> tuple[list[Sat], int]:
    """rows: iterable of (group, omm_dict). Returns (sats, n_rejected)."""
    sats, bad = [], 0
    for group, r in rows:
        try:
            ep = dt.datetime.fromisoformat(r["EPOCH"])
            if ep.tzinfo is None:
                ep = ep.replace(tzinfo=dt.timezone.utc)
            sats.append(Sat(
                norad=int(r["NORAD_CAT_ID"]),
                name=r["OBJECT_NAME"].strip(),
                intl_id=r.get("OBJECT_ID", "").strip(),
                group=group,
                epoch=ep,
                mean_motion=float(r["MEAN_MOTION"]),
                ecc=float(r["ECCENTRICITY"]),
                inc_deg=float(r["INCLINATION"]),
                satrec=satrec_from_omm(r),
            ))
        except Exception:
            bad += 1
    return sats, bad


# ---------------------------------------------------------------------------
# 3. Time and reference frames
# ---------------------------------------------------------------------------
def julian(when: dt.datetime) -> tuple[float, float]:
    when = when.astimezone(dt.timezone.utc)
    return jday(when.year, when.month, when.day, when.hour, when.minute,
                when.second + when.microsecond / 1e6)


def gmst_rad(jd: float, fr: float) -> float:
    """Greenwich Mean Sidereal Time, IAU-82 polynomial (arcsecond-class)."""
    d = (jd - 2451545.0) + fr
    t = d / 36525.0
    deg = (280.46061837 + 360.98564736629 * d
           + 0.000387933 * t * t - t * t * t / 38_710_000.0)
    return math.radians(deg % 360.0)


def teme_to_ecef(r_teme: np.ndarray, theta: float) -> np.ndarray:
    """Rotate TEME -> ECEF about the pole by GMST.

    Polar motion and the equation of the equinoxes are neglected: both are
    well under a kilometre at these altitudes, far inside SGP4's own error.
    """
    c, s = math.cos(theta), math.sin(theta)
    x, y, z = r_teme[..., 0], r_teme[..., 1], r_teme[..., 2]
    return np.stack([x * c + y * s, -x * s + y * c, z], axis=-1)


def ecef_to_geodetic(r_ecef: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """ECEF km -> (lat_deg, lon_deg, alt_km) on the WGS-84 ellipsoid."""
    x, y, z = r_ecef[..., 0], r_ecef[..., 1], r_ecef[..., 2]
    lon = np.degrees(np.arctan2(y, x))
    hyp = np.hypot(x, y)
    lat = np.arctan2(z, hyp)                     # geocentric first guess
    alt = np.zeros_like(lat)
    for _ in range(6):                           # converges in ~3
        sin_lat = np.sin(lat)
        n = R_EARTH_EQ / np.sqrt(1.0 - E2_WGS84 * sin_lat * sin_lat)
        alt = hyp / np.maximum(np.cos(lat), 1e-12) - n
        lat = np.arctan2(z, hyp * (1.0 - E2_WGS84 * n / (n + alt)))
    return np.degrees(lat), lon, alt


def geodetic_to_ecef(lat_deg: float, lon_deg: float, alt_km: float = 0.0) -> np.ndarray:
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    n = R_EARTH_EQ / math.sqrt(1.0 - E2_WGS84 * math.sin(lat) ** 2)
    return np.array([
        (n + alt_km) * math.cos(lat) * math.cos(lon),
        (n + alt_km) * math.cos(lat) * math.sin(lon),
        (n * (1.0 - E2_WGS84) + alt_km) * math.sin(lat),
    ])


def propagate(sats: list[Sat], when: dt.datetime):
    """Propagate every satellite to one instant.

    Returns (ok, r_teme, v_teme, lat, lon, alt_km, theta) with `ok` masking
    the objects SGP4 could not propagate (decayed, degenerate elements).
    """
    jd, fr = julian(when)
    arr = SatrecArray([s.satrec for s in sats])
    err, r, v = arr.sgp4(np.array([jd]), np.array([fr]))
    ok = err[:, 0] == 0
    r_teme, v_teme = r[:, 0, :], v[:, 0, :]
    # A propagation failure leaves NaNs behind; keep the arrays finite so the
    # downstream vector maths never has to special-case them.
    r_teme = np.where(ok[:, None], r_teme, 0.0)
    v_teme = np.where(ok[:, None], v_teme, 0.0)
    theta = gmst_rad(jd, fr)
    lat, lon, alt = ecef_to_geodetic(teme_to_ecef(r_teme, theta))
    return ok, r_teme, v_teme, lat, lon, alt, theta


# ---------------------------------------------------------------------------
# 4. Where the Sun is, and who can see it
# ---------------------------------------------------------------------------
def sun_vector_eci(jd: float, fr: float) -> tuple[np.ndarray, float]:
    """Geocentric solar position, equatorial mean equinox of date.

    The low-precision series from the Astronomical Almanac (good to ~0.01 deg,
    which is ~26,000 km at 1 AU and utterly irrelevant to a shadow test that
    only cares about the direction).  Returned as (unit vector, distance km).
    """
    n = (jd - 2451545.0) + fr
    mean_lon = math.radians((280.460 + 0.9856474 * n) % 360.0)
    mean_anom = math.radians((357.528 + 0.9856003 * n) % 360.0)
    ecl_lon = mean_lon + math.radians(1.915) * math.sin(mean_anom) \
        + math.radians(0.020) * math.sin(2.0 * mean_anom)
    obliq = math.radians(23.439 - 0.0000004 * n)
    dist = (1.00014
            - 0.01671 * math.cos(mean_anom)
            - 0.00014 * math.cos(2.0 * mean_anom)) * AU
    u = np.array([
        math.cos(ecl_lon),
        math.cos(obliq) * math.sin(ecl_lon),
        math.sin(obliq) * math.sin(ecl_lon),
    ])
    return u, dist


def subsolar_point(when: dt.datetime) -> tuple[float, float]:
    """(lat, lon) of the point with the Sun directly overhead."""
    jd, fr = julian(when)
    u, _ = sun_vector_eci(jd, fr)
    dec = math.degrees(math.asin(u[2]))
    ra = math.atan2(u[1], u[0])
    lon = math.degrees(ra - gmst_rad(jd, fr))
    return dec, (lon + 180.0) % 360.0 - 180.0


# Illumination states
LIT, PENUMBRA, UMBRA = 0, 1, 2


def illumination(r_teme: np.ndarray, jd: float, fr: float) -> np.ndarray:
    """Classify each satellite as LIT / PENUMBRA / UMBRA.

    A conical shadow, not the usual cylinder: the Sun is an extended source,
    so Earth casts a converging umbra ringed by a diverging penumbra.  With

        a_umb = asin((R_sun - R_earth) / d_sun)
        a_pen = asin((R_sun + R_earth) / d_sun)

    the shadow radii a distance `x` down the anti-solar axis are
    `R_earth -+ x*tan(a)`.  The umbra tapers to a point about 1.4 million km
    behind Earth — well beyond GEO, so every orbit here can be fully eclipsed.
    The atmosphere is ignored; refraction would soften the boundary by a few
    tens of kilometres.
    """
    u_sun, d_sun = sun_vector_eci(jd, fr)
    tan_umb = math.tan(math.asin((R_SUN - R_EARTH_EQ) / d_sun))
    tan_pen = math.tan(math.asin((R_SUN + R_EARTH_EQ) / d_sun))

    along = r_teme @ u_sun                     # + = sunward hemisphere
    r_mag = np.linalg.norm(r_teme, axis=-1)
    x = -along                                 # distance down the shadow axis
    perp = np.sqrt(np.maximum(r_mag * r_mag - along * along, 0.0))

    r_umb = R_EARTH_EQ - x * tan_umb
    r_pen = R_EARTH_EQ + x * tan_pen

    state = np.full(r_teme.shape[0], LIT, dtype=np.int8)
    behind = along < 0.0
    state[behind & (perp < r_pen)] = PENUMBRA
    state[behind & (perp < r_umb)] = UMBRA
    return state


def terminator_ring(sub_lat: float, sub_lon: float, n: int = 180):
    """Points on the great circle 90 deg from the sub-solar point.

    That circle is the day/night terminator: the locus where the Sun sits on
    the horizon.  Built as the circle whose pole is the sub-solar direction.
    """
    la, lo = math.radians(sub_lat), math.radians(sub_lon)
    pole = np.array([math.cos(la) * math.cos(lo),
                     math.cos(la) * math.sin(lo),
                     math.sin(la)])
    # Any vector not parallel to the pole gives us an in-plane basis.
    seed = np.array([0.0, 0.0, 1.0])
    if abs(pole[2]) > 0.9:
        seed = np.array([1.0, 0.0, 0.0])
    u = np.cross(pole, seed)
    u /= np.linalg.norm(u)
    v = np.cross(pole, u)
    out = []
    for k in range(n):
        t = 2.0 * math.pi * k / n
        p = math.cos(t) * u + math.sin(t) * v
        out.append((math.degrees(math.asin(max(-1.0, min(1.0, p[2])))),
                    math.degrees(math.atan2(p[1], p[0]))))
    return out


# ---------------------------------------------------------------------------
# 5. Ground stations
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class Station:
    name: str
    operator: str
    lat: float
    lon: float
    alt_km: float = 0.0


def look_angles(station: Station, r_ecef: np.ndarray):
    """Elevation and range from one station to every satellite.

    Elevation is measured from the station's local geodetic horizon, so it is
    the angle an antenna would actually be commanded to.
    """
    lat, lon = math.radians(station.lat), math.radians(station.lon)
    site = geodetic_to_ecef(station.lat, station.lon, station.alt_km)
    up = np.array([math.cos(lat) * math.cos(lon),
                   math.cos(lat) * math.sin(lon),
                   math.sin(lat)])
    d = r_ecef - site
    rng = np.linalg.norm(d, axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        sin_el = (d @ up) / np.maximum(rng, 1e-9)
    return np.degrees(np.arcsin(np.clip(sin_el, -1.0, 1.0))), rng


# ---------------------------------------------------------------------------
# 6. Orbit classification
# ---------------------------------------------------------------------------
LEO, MEO, GEO, HEO = "LEO", "MEO", "GEO", "HEO"
SIDEREAL_DAY_MIN = 1436.068


def classify(sat: Sat) -> str:
    """LEO / MEO / GEO / HEO from the element set alone.

    Deliberately element-based rather than snapshot-altitude-based: a Molniya
    is an HEO whether you catch it at perigee or apogee.
    """
    a = sat.semi_major_km
    apogee = a * (1.0 + sat.ecc) - R_EARTH_EQ
    perigee = a * (1.0 - sat.ecc) - R_EARTH_EQ
    if sat.ecc > 0.25:
        return HEO
    if abs(sat.period_min - SIDEREAL_DAY_MIN) < 25.0:
        return GEO
    if apogee < 2000.0:
        return LEO
    if perigee > 2000.0:
        return MEO
    return HEO
