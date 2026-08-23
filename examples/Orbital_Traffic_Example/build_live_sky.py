#!/usr/bin/env python
"""Live Sky — every tracked satellite on a globe, where it is right now.

Fetches CelesTrak GP element sets, propagates them with SGP4 to the current
instant, and writes a GlyphViz World Grid globe scene in which each object sits
at its true sub-satellite point and its true altitude.

Two things make it more than dots on a sphere:

  * **Sunlight.**  A conical umbra/penumbra test decides which satellites are
    lit and which are in Earth's shadow, and the terminator is drawn as a real
    great circle.  Hue is the orbit regime; brightness is whether the Sun is
    shining on it.

  * **Ground station horizons.**  Link edges run from each ground station to
    the satellites currently above its horizon, ranked by elevation angle.
    Watch Svalbard for ten seconds and the case for polar ground stations
    makes itself.

Usage
-----
    python build_live_sky.py                    # fetch (politely) and build once
    python build_live_sky.py --offline          # rebuild from the bundled cache
    python build_live_sky.py --watch 1          # live: rewrite every second
    python build_live_sky.py --max-alt-km 2000  # LEO close-up
    python build_live_sky.py --groups active    # the whole catalogue (16k)

Then open `Live_Sky/live_sky_gv_node.csv` in GlyphViz and turn on
**File > Watch and Reload** (Ctrl+R).

Node ids are allocated from a fixed layout and never move between rewrites —
including the link pool, whose unused slots are hidden rather than dropped —
so a reload preserves your camera *and* your selection even though the set of
visible edges churns every second.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import orbits  # noqa: E402
from orbits import GEO, HEO, LEO, LIT, MEO, PENUMBRA, UMBRA, Station  # noqa: E402

# ---------------------------------------------------------------------------
# 1. Scene constants
# ---------------------------------------------------------------------------
GLOBE_R = 180.0 / math.pi              # world radius of a scale-1 globe
KM_PER_UNIT = orbits.R_EARTH_EQ / GLOBE_R      # = 111.32 km per world unit

DEFAULT_GROUPS = ["stations", "visual", "science", "weather", "iridium-NEXT",
                  "gps-ops", "galileo", "glo-ops", "beidou", "geo"]

BG = (6, 8, 18, 255)
TAG_FONT_PT = 13

# Hue carries the orbit regime; brightness carries sunlight.
REGIME_RGB = {
    LEO: (90, 210, 255),      # cyan
    MEO: (255, 190, 80),      # amber
    GEO: (255, 120, 190),     # rose
    HEO: (150, 255, 140),     # green
}
REGIME_ORDER = [LEO, MEO, GEO, HEO]
REGIME_NOTE = {
    LEO: "LEO  below 2,000 km",
    MEO: "MEO  2,000 km to GEO",
    GEO: "GEO  35,786 km, one sidereal day",
    HEO: "HEO  eccentric",
}
SHADE = {LIT: 1.0, PENUMBRA: 0.52, UMBRA: 0.26}
SHADE_NOTE = {LIT: "sunlit", PENUMBRA: "penumbra", UMBRA: "eclipsed"}

# geometry ids by SATCAT object type
GEO_BY_TYPE = {"PAY": 11, "R/B": 19, "DEB": 13}     # octahedron / cylinder / tetra
GEO_UNKNOWN = 1                                     # cube

GEO_SPHERE, GEO_PIN, GEO_LINE, GEO_OCTA = 3, 16, 27, 11

SUN_RGB = (255, 238, 150)
TERM_RGB = (255, 158, 60)
STATION_RGB = (215, 235, 255)
LINK_RGB = (120, 255, 190)

N_TERMINATOR = 180                     # points on the day/night great circle
LEGEND_X = -360.0                      # just clear of the GEO ring at 321.5

# Ground stations: real sites, chosen to spread across latitudes so the
# polar/equatorial contrast in coverage is visible.
STATIONS = [
    Station("Svalbard (SvalSat)", "KSAT",        78.229,   15.408),
    Station("Troll",              "KSAT",       -72.012,    2.535),
    Station("Poker Flat",         "NASA/UAF",    65.117, -147.470),
    Station("Kiruna",             "ESA",         67.857,   20.964),
    Station("Goldstone",          "NASA DSN",    35.426, -116.890),
    Station("Madrid",             "NASA DSN",    40.429,   -4.249),
    Station("Canberra",           "NASA DSN",   -35.402,  148.982),
    Station("Wallops",            "NASA",        37.925,  -75.475),
    Station("Kourou",             "ESA",          5.252,  -52.805),
    Station("McMurdo",            "NASA MGS",   -77.839,  166.669),
]

COLUMNS = [
    "id", "type", "parent_id", "branch_level", "child_id",
    "translate_x", "translate_y", "translate_z",
    "rotate_x", "rotate_y", "rotate_z",
    "scale_x", "scale_y", "scale_z",
    "color_r", "color_g", "color_b", "color_a",
    "geometry", "hide", "topo", "ratio", "texture_id",
    "trigger_lo_x", "trigger_hi_x", "trigger_lo_y", "trigger_hi_y",
    "segments_x", "segments_y",
    "show_text", "rotation_mode", "render_mode",
    "tag_color_mode", "tag_font_size", "text", "link",
]
DEFAULTS = {c: 0 for c in COLUMNS}
DEFAULTS.update(scale_x=1.0, scale_y=1.0, scale_z=1.0, color_a=255,
                ratio=0.1, text="", link="")


# ---------------------------------------------------------------------------
# 2. Small helpers
# ---------------------------------------------------------------------------
def sanitize(t) -> str:
    """Strip control characters — one stray byte can kill every label."""
    return "".join(c for c in str(t) if c >= " " and c != "\x7f").strip()


def dim(rgb, f: float):
    return tuple(int(round(max(0.0, min(255.0, c * f)))) for c in rgb)


def parse_csv(text: str):
    return list(csv.DictReader(io.StringIO(text)))


def load_satcat(path: str, *, offline: bool, log):
    """NORAD id -> {object type, owner, RCS, launch date}."""
    rows = parse_csv(orbits.fetch_satcat(path, offline=offline, log=log))
    out = {}
    for r in rows:
        try:
            norad = int(r["NORAD_CAT_ID"])
        except (KeyError, ValueError):
            continue
        rcs = r.get("RCS", "")
        out[norad] = {
            "type": (r.get("OBJECT_TYPE") or "").strip() or "UNK",
            "owner": (r.get("OWNER") or "").strip() or "?",
            "rcs": float(rcs) if rcs.strip() else None,
            "launched": (r.get("LAUNCH_DATE") or "").strip(),
        }
    return out


def _ages_h(epoch_ts: np.ndarray) -> np.ndarray:
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    return (now - epoch_ts) / 3600.0


def _age_str(epoch_ts: np.ndarray) -> str:
    """Report the *median* element age, not the newest epoch.

    A handful of objects always sit at the extremes — a long-period orbit like
    Chandra gets element sets dated a day and a half into the future, and a
    forgotten piece of debris can carry a month-old fit.  The newest epoch
    describes neither; the median describes the catalogue.
    """
    h = float(np.median(_ages_h(epoch_ts)))
    return f"{h:.1f} h" if abs(h) < 48 else f"{h / 24:.1f} d"


def glyph_scale(rcs, base: float) -> float:
    """Radar cross section (m^2) -> glyph size, log-compressed.

    RCS spans four orders of magnitude, so a linear map would render every
    object but the ISS as a dot.  Objects with no published RCS get the
    bottom of the range rather than a guess.
    """
    if rcs is None or rcs <= 0.0:
        return round(base * 0.5, 3)
    return round(base * min(2.0, 0.5 + 0.5 * math.log10(1.0 + rcs)), 3)


# ---------------------------------------------------------------------------
# 3. Scene assembly
# ---------------------------------------------------------------------------
class SceneBuilder:
    """Writes rows into a fixed id layout.

    Every id below is a pure function of the *configuration*, never of the
    moment being rendered — that is what lets `--watch` rewrite the file once
    a second without the viewer losing your selection.
    """

    def __init__(self, sats, meta, stations, links_per_station: int):
        self.rows: list[dict] = []
        self.sats = sats
        self.meta = meta
        self.stations = stations
        self.links_per_station = links_per_station

        nid = 1
        self.id_world = nid; nid += 1
        self.id_globe = nid; nid += 1
        self.id_clock = nid; nid += 1
        self.id_sun = nid; nid += 1
        self.id_legend0 = nid; nid += len(REGIME_ORDER) + len(SHADE) + 2
        self.id_term0 = nid; nid += N_TERMINATOR          # terminator markers
        self.id_termlink0 = nid; nid += N_TERMINATOR      # ...and their edges
        self.id_station0 = nid; nid += len(stations)
        self.id_sat0 = nid; nid += len(sats)
        self.id_link0 = nid; nid += len(stations) * links_per_station
        self.id_end = nid

    def add(self, **kw):
        row = dict(DEFAULTS)
        row.update(kw)
        self.rows.append(row)
        return row["id"]

    # -- static furniture ---------------------------------------------------
    def world(self):
        self.add(id=self.id_world, type=0, parent_id=0, branch_level=0,
                 color_r=BG[0], color_g=BG[1], color_b=BG[2], color_a=BG[3],
                 geometry=0, tag_color_mode=1, tag_font_size=TAG_FONT_PT)

    def globe(self):
        self.add(id=self.id_globe, type=6, parent_id=0, branch_level=0,
                 geometry=GEO_SPHERE, texture_id=1, segments_x=36, segments_y=18,
                 color_r=64, color_g=96, color_b=132, color_a=255,
                 scale_x=1.0, scale_y=1.0, scale_z=1.0)

    def legend(self):
        """A colour key west of the GEO ring, where nothing else ever lands."""
        nid = self.id_legend0
        z = 60.0
        self.add(id=nid, type=5, parent_id=0, branch_level=0,
                 translate_x=LEGEND_X, translate_y=0.0, translate_z=z,
                 scale_x=4.0, scale_y=4.0, scale_z=4.0, geometry=GEO_OCTA,
                 color_r=255, color_g=255, color_b=255, show_text=1,
                 text="hue = orbit regime")
        nid += 1
        for regime in REGIME_ORDER:
            z -= 16.0
            rgb = REGIME_RGB[regime]
            self.add(id=nid, type=5, parent_id=0, branch_level=0,
                     translate_x=LEGEND_X, translate_y=0.0, translate_z=z,
                     scale_x=5.0, scale_y=5.0, scale_z=5.0, geometry=GEO_OCTA,
                     color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
                     show_text=1, text=REGIME_NOTE[regime])
            nid += 1
        z -= 26.0
        self.add(id=nid, type=5, parent_id=0, branch_level=0,
                 translate_x=LEGEND_X, translate_y=0.0, translate_z=z,
                 scale_x=4.0, scale_y=4.0, scale_z=4.0, geometry=GEO_OCTA,
                 color_r=255, color_g=255, color_b=255, show_text=1,
                 text="brightness = sunlight")
        nid += 1
        for state in (LIT, PENUMBRA, UMBRA):
            z -= 16.0
            rgb = dim(REGIME_RGB[LEO], SHADE[state])
            self.add(id=nid, type=5, parent_id=0, branch_level=0,
                     translate_x=LEGEND_X, translate_y=0.0, translate_z=z,
                     scale_x=5.0, scale_y=5.0, scale_z=5.0, geometry=GEO_OCTA,
                     color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
                     show_text=1, text=SHADE_NOTE[state])
            nid += 1

    # -- everything that moves ---------------------------------------------
    def clock(self, when, counts, age_str, n_links):
        lit, pen, umb = counts
        self.add(id=self.id_clock, type=5, parent_id=0, branch_level=0,
                 translate_x=0.0, translate_y=0.0, translate_z=340.0,
                 scale_x=6.0, scale_y=6.0, scale_z=6.0, geometry=GEO_OCTA,
                 color_r=255, color_g=255, color_b=255, color_a=255,
                 show_text=1,
                 text=sanitize(
                     f"{when:%Y-%m-%d %H:%M:%S} UTC   |   "
                     f"{lit + pen + umb} objects   |   "
                     f"{lit} sunlit / {pen} penumbra / {umb} eclipsed   |   "
                     f"{n_links} station links   |   "
                     f"elements median {age_str} old"))

    def sun_marker(self, sub_lat, sub_lon):
        self.add(id=self.id_sun, type=5, parent_id=self.id_globe, branch_level=1,
                 translate_x=round(sub_lon, 4), translate_y=round(sub_lat, 4),
                 translate_z=2.5, scale_x=4.0, scale_y=4.0, scale_z=4.0,
                 geometry=GEO_SPHERE,
                 color_r=SUN_RGB[0], color_g=SUN_RGB[1], color_b=SUN_RGB[2],
                 show_text=1,
                 text=sanitize(f"sub-solar point  {sub_lat:+.1f}, {sub_lon:+.1f}"
                               "  (Sun directly overhead)"))

    def terminator(self, sub_lat, sub_lon):
        pts = orbits.terminator_ring(sub_lat, sub_lon, N_TERMINATOR)
        for k, (la, lo) in enumerate(pts):
            self.add(id=self.id_term0 + k, type=5, parent_id=self.id_globe,
                     branch_level=1,
                     translate_x=round(lo, 4), translate_y=round(la, 4),
                     translate_z=0.45,
                     scale_x=0.45, scale_y=0.45, scale_z=0.45,
                     geometry=GEO_SPHERE,
                     color_r=TERM_RGB[0], color_g=TERM_RGB[1], color_b=TERM_RGB[2],
                     color_a=255)
        for k in range(N_TERMINATOR):
            a = self.id_term0 + k
            b = self.id_term0 + (k + 1) % N_TERMINATOR
            self.add(id=self.id_termlink0 + k, type=7, parent_id=a, child_id=b,
                     branch_level=2, geometry=GEO_LINE, ratio=0.09,
                     scale_x=1.0, scale_y=1.0, scale_z=1.0,
                     color_r=TERM_RGB[0], color_g=TERM_RGB[1], color_b=TERM_RGB[2],
                     color_a=210)

    def station_markers(self):
        for k, st in enumerate(self.stations):
            self.add(id=self.id_station0 + k, type=5, parent_id=self.id_globe,
                     branch_level=1,
                     translate_x=round(st.lon, 4), translate_y=round(st.lat, 4),
                     translate_z=0.0,
                     scale_x=2.6, scale_y=2.6, scale_z=2.6, geometry=GEO_PIN,
                     color_r=STATION_RGB[0], color_g=STATION_RGB[1],
                     color_b=STATION_RGB[2], show_text=1,
                     text=sanitize(f"{st.name} ({st.operator})"))

    def satellites(self, visible, lat, lon, alt, speed, state, base_scale):
        """One row per object, always — hidden rather than dropped when a
        propagation fails or the altitude filter excludes it, so ids hold."""
        shown = 0
        for i, sat in enumerate(self.sats):
            m = self.meta[i]
            vis = bool(visible[i])
            rgb = dim(REGIME_RGB[m["regime"]], SHADE[int(state[i])])
            s = m["scale"] * base_scale
            self.add(
                id=self.id_sat0 + i, type=5, parent_id=self.id_globe,
                branch_level=1,
                translate_x=round(float(lon[i]), 4) if vis else 0.0,
                translate_y=round(float(lat[i]), 4) if vis else 0.0,
                translate_z=round(float(alt[i]) / KM_PER_UNIT, 4) if vis else 0.0,
                scale_x=s, scale_y=s, scale_z=s,
                color_r=rgb[0], color_g=rgb[1], color_b=rgb[2], color_a=255,
                geometry=m["geometry"], hide=0 if vis else 1,
                text=sanitize(
                    f"{sat.name}  |  {sat.norad}  |  {m['regime']}  |  "
                    f"{alt[i]:,.0f} km  |  {speed[i]:.2f} km/s  |  "
                    f"{SHADE_NOTE[int(state[i])]}  |  {m['owner']}"),
                link=f"https://celestrak.org/satcat/table-satcat.php?CATNR={sat.norad}")
            shown += vis
        return shown

    def station_links(self, visible_by_station):
        """A fixed pool of edges; unused slots are hidden, never removed."""
        used = 0
        for k, st in enumerate(self.stations):
            base = self.id_link0 + k * self.links_per_station
            picks = visible_by_station[k]
            for j in range(self.links_per_station):
                lid = base + j
                if j < len(picks):
                    sat_index, elev = picks[j]
                    # Bright and thick overhead, dim and thin near the horizon:
                    # elevation is the whole reason one pass is usable and
                    # another is not.
                    f = 0.35 + 0.65 * (elev / 90.0)
                    rgb = dim(LINK_RGB, f)
                    self.add(id=lid, type=7,
                             parent_id=self.id_station0 + k,
                             child_id=self.id_sat0 + sat_index,
                             branch_level=2, geometry=GEO_LINE,
                             ratio=round(0.05 + 0.10 * (elev / 90.0), 4),
                             scale_x=1.0, scale_y=1.0, scale_z=1.0,
                             color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
                             color_a=int(150 + 105 * (elev / 90.0)))
                    used += 1
                else:
                    # A hidden self-link: both ends resolve, nothing draws.
                    self.add(id=lid, type=7,
                             parent_id=self.id_station0 + k,
                             child_id=self.id_station0 + k,
                             branch_level=2, geometry=GEO_LINE, ratio=0.05,
                             scale_x=1.0, scale_y=1.0, scale_z=1.0,
                             color_r=LINK_RGB[0], color_g=LINK_RGB[1],
                             color_b=LINK_RGB[2], color_a=255, hide=1)
        return used


# ---------------------------------------------------------------------------
# 4. Validation — cheap checks that would have caught every bug we hit
# ---------------------------------------------------------------------------
def validate(rows, builder):
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate node ids")
    known = set(ids)
    for r in rows:
        if r["parent_id"] and r["parent_id"] not in known:
            raise SystemExit(f"node {r['id']}: dangling parent {r['parent_id']}")
        if r["type"] == 7:
            # A link with an unresolved end draws nothing at all, silently.
            if r["child_id"] not in known:
                raise SystemExit(f"link {r['id']}: dangling child_id {r['child_id']}")
            if r["ratio"] <= 0:
                raise SystemExit(f"link {r['id']}: ratio must be > 0")
        for c in ("color_r", "color_g", "color_b", "color_a"):
            if not 0 <= r[c] <= 255:
                raise SystemExit(f"node {r['id']}: {c} out of range ({r[c]})")
        if not r["hide"] and r["type"] == 5:
            if min(r["scale_x"], r["scale_y"], r["scale_z"]) < 0.2:
                raise SystemExit(f"node {r['id']}: visible glyph below the "
                                 f"0.2 scale floor")
        if not (0 <= r["geometry"] <= 28):
            raise SystemExit(f"node {r['id']}: geometry {r['geometry']}")
    if max(ids) >= builder.id_end:
        raise SystemExit("id allocation overflowed its fixed layout")


def write_atomic(rows, path):
    """Temp file + os.replace, so Watch and Reload never sees a torn CSV."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\r\n")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# 5. One frame
# ---------------------------------------------------------------------------
def build_frame(builder, when, *, base_scale, max_alt_km, min_elev,
                age_str, log):
    sats = builder.sats
    ok, r_teme, v_teme, lat, lon, alt, theta = orbits.propagate(sats, when)
    jd, fr = orbits.julian(when)
    state = orbits.illumination(r_teme, jd, fr)
    state[~ok] = LIT
    speed = np.linalg.norm(v_teme, axis=1)
    sub_lat, sub_lon = orbits.subsolar_point(when)

    # One visibility mask, used for the glyphs, the edges and the tallies
    # alike. Deriving the station links from anything looser would draw edges
    # reaching out to satellites the altitude filter has hidden — an edge to
    # an invisible endpoint still draws, because a link reads its ends'
    # world positions and never looks at their `hide` flag.
    visible = ok & np.isfinite(alt) & (alt > 0.0)
    if max_alt_km is not None:
        visible &= alt <= max_alt_km

    # Ground-station look angles, from ECEF positions.
    r_ecef = orbits.teme_to_ecef(r_teme, theta)
    visible_by_station, n_above = [], 0
    for st in builder.stations:
        elev, _ = orbits.look_angles(st, r_ecef)
        cand = np.where(visible & (elev >= min_elev))[0]
        n_above += len(cand)
        # An antenna farm tracks a handful of passes, not everything in the
        # sky; taking the highest-elevation few also keeps the GEO belt from
        # burying every LEO pass under 500 near-identical edges.
        cand = cand[np.argsort(-elev[cand])][:builder.links_per_station]
        visible_by_station.append([(int(i), float(elev[i])) for i in cand])

    builder.rows.clear()
    builder.world()
    builder.globe()
    builder.legend()
    builder.sun_marker(sub_lat, sub_lon)
    builder.terminator(sub_lat, sub_lon)
    builder.station_markers()
    shown = builder.satellites(visible, lat, lon, alt, speed, state, base_scale)
    n_links = builder.station_links(visible_by_station)
    # Tally only what is on screen, so the caption describes the picture the
    # viewer is actually looking at rather than the catalogue behind it.
    counts = (int((visible & (state == LIT)).sum()),
              int((visible & (state == PENUMBRA)).sum()),
              int((visible & (state == UMBRA)).sum()))
    builder.clock(when, counts, age_str, n_links)
    return builder.rows, dict(shown=shown, links=n_links, counts=counts,
                              sub=(sub_lat, sub_lon), above=n_above,
                              failed=int((~ok).sum()))


# ---------------------------------------------------------------------------
# 6. Main
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Build the Live Sky GlyphViz scene from CelesTrak GP data.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--groups", nargs="+", default=DEFAULT_GROUPS,
                    help="CelesTrak GROUP names (default: a ~1,100-object mix "
                         "spanning LEO through GEO). 'active' is all 16k.")
    ap.add_argument("--offline", action="store_true",
                    help="never touch the network; build from data/gp_cache")
    ap.add_argument("--out", default=os.path.join(HERE, "Live_Sky",
                                                  "live_sky_gv_node.csv"))
    ap.add_argument("--watch", type=float, metavar="SECONDS",
                    help="rewrite the scene every SECONDS (1 matches the "
                         "viewer's file-poll rate)")
    ap.add_argument("--max-alt-km", type=float, default=None,
                    help="hide objects above this altitude (2000 = LEO only)")
    ap.add_argument("--glyph-scale", type=float, default=1.6,
                    help="multiplier on the RCS-derived glyph size")
    ap.add_argument("--min-elev", type=float, default=5.0,
                    help="horizon mask for ground-station links, degrees")
    ap.add_argument("--links-per-station", type=int, default=10,
                    help="highest-elevation passes edged per station")
    args = ap.parse_args(argv)

    log = print
    log("Live Sky - CelesTrak GP -> SGP4 -> GlyphViz\n")

    # -- data ---------------------------------------------------------------
    cache_dir = os.path.join(HERE, "data", "gp_cache")
    log("Element sets:")
    rows = []
    for g in args.groups:
        try:
            text = orbits.fetch_group(g, cache_dir, offline=args.offline, log=log)
        except Exception as e:
            log(f"  ! {g}: {e} - skipped")
            continue
        for r in parse_csv(text):
            rows.append((g, r))
    if not rows:
        raise SystemExit("no element sets available")

    # CelesTrak lists some objects in several groups; first listing wins.
    seen, uniq = set(), []
    for g, r in rows:
        n = r.get("NORAD_CAT_ID")
        if n and n not in seen:
            seen.add(n)
            uniq.append((g, r))
    log(f"  = {len(uniq)} unique objects "
        f"({len(rows) - len(uniq)} duplicate listings dropped)\n")

    log("Metadata:")
    satcat = load_satcat(os.path.join(HERE, "data", "satcat.csv"),
                         offline=args.offline, log=log)
    log(f"  = {len(satcat)} SATCAT rows\n")

    sats, bad = orbits.build_sats(uniq)
    if bad:
        log(f"  ! {bad} element sets rejected as unparseable")
    # A stable sort key is what keeps node ids fixed across rewrites.
    sats.sort(key=lambda s: s.norad)

    meta = []
    for s in sats:
        info = satcat.get(s.norad, {})
        meta.append({
            "regime": orbits.classify(s),
            "owner": info.get("owner", "?"),
            "geometry": GEO_BY_TYPE.get(info.get("type", ""), GEO_UNKNOWN),
            "scale": glyph_scale(info.get("rcs"), 1.0),
        })
    tally = {r: sum(1 for m in meta if m["regime"] == r) for r in REGIME_ORDER}
    log(f"{len(sats)} propagators ready - "
        + ", ".join(f"{k} {v}" for k, v in tally.items() if v))

    epochs = np.array([s.epoch.timestamp() for s in sats])
    log(f"element epochs: median {_age_str(epochs)}, "
        f"{int((_ages_h(epochs) > 168).sum())} older than a week, "
        f"{int((_ages_h(epochs) < 0).sum())} dated ahead of now")

    builder = SceneBuilder(sats, meta, STATIONS, args.links_per_station)
    log(f"id layout: 1..{builder.id_end - 1} "
        f"(satellites {builder.id_sat0}..{builder.id_sat0 + len(sats) - 1}, "
        f"link pool {builder.id_link0}..{builder.id_end - 1})\n")

    # -- render loop --------------------------------------------------------
    n = 0
    while True:
        t0 = time.perf_counter()
        now = dt.datetime.now(dt.timezone.utc)
        age_str = _age_str(epochs)
        rows, stats = build_frame(builder, now, base_scale=args.glyph_scale,
                                  max_alt_km=args.max_alt_km,
                                  min_elev=args.min_elev,
                                  age_str=age_str, log=log)
        if n == 0:
            validate(rows, builder)
        write_atomic(rows, args.out)
        ms = (time.perf_counter() - t0) * 1000.0
        lit, pen, umb = stats["counts"]
        n += 1

        if not args.watch:
            log(f"{now:%Y-%m-%d %H:%M:%S} UTC")
            log(f"  sub-solar point   {stats['sub'][0]:+.2f}, {stats['sub'][1]:+.2f}")
            log(f"  illumination      {lit} sunlit, {pen} penumbra, {umb} eclipsed")
            log(f"  above {args.min_elev:.0f} deg     {stats['above']} "
                f"station-satellite pairs -> {stats['links']} edges drawn")
            log(f"  rendered          {stats['shown']} of {len(sats)} objects"
                + (f", {stats['failed']} propagation failures"
                   if stats["failed"] else ""))
            log(f"  elements          median {age_str} old")
            log(f"  wrote             {len(rows)} nodes in {ms:.0f} ms -> "
                f"{args.out}")
            log("\nOpen it in GlyphViz. For live motion, rerun with --watch 1 "
                "and turn on\nFile > Watch and Reload (Ctrl+R).")
            return 0

        print(f"\r{now:%H:%M:%S} UTC  {stats['shown']} shown  "
              f"{lit}/{pen}/{umb} sun/pen/ecl  {stats['links']} edges  "
              f"{ms:5.1f} ms  (frame {n})   ", end="", flush=True)
        sleep = args.watch - (time.perf_counter() - t0)
        if sleep > 0:
            time.sleep(sleep)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nstopped")
