#!/usr/bin/env python3
"""
build_cedar_runoff_scene.py — After the Cedar Fire: does the same rain make a bigger river?
==========================================================================================

The San Diego River Watershed Atlas's headline question, answered where the
public record can answer it.

WHY NOT THE ATLAS'S OWN GAUGE
-----------------------------
The Cedar Fire (October 2003) burned 80% of the land draining to the Mast Rd
gauge — but 85% of that burn lies above El Capitan and San Vicente dams
(measured here from NLDI basins and the FRAP perimeter), so the reservoirs
absorb whatever the burn scar did to runoff. No gauge above either dam has a
record spanning 2003. So the scene compares two undammed mountain creeks:

  * SWEETWATER RIVER NEAR DESCANSO (USGS 11015000, daily since 1905), whose
    basin in Cuyamaca Rancho State Park the Cedar Fire burned 78% of — the
    BURNED basin — with rain from Cuyamaca (GHCN USC00042239);
  * CAMPO CREEK NEAR CAMPO (USGS 11012500, daily since 1936), 26 km south-east,
    which no fire has burned more than 16% of since 1960 — the CONTROL — with
    rain from Campo (GHCN USC00041424).

THE QUESTION, MADE MEASURABLE
-----------------------------
Every storm since 1960 at each gauge: rain arriving on a day with at least
0.5 in and three days totalling at least 1.5 in, lasting while daily rain
stays at or above 0.2 in. For each storm, what the creek did (the peak daily
mean flow during the storm and the day after) and what it would NORMALLY have
done: a regression on the pre-fire storms (October 1960 to the fire),

    ln(peak + 1) = a + b ln(storm rain) + c ln(60-day prior rain + 1) + d ln(flow before + 0.1)

so a storm's "expected" peak already accounts for how big it was, how wet the
ground was, and how much water was already in the creek. Observed divided by
expected is the storm's multiplier.

A co-op rain gauge's "day" ends when the observer reads it. Cuyamaca is read at
08:00, so most of a day's total fell the calendar day BEFORE and it is shifted
one day earlier; Campo is read at 17:00 (15:00 since the 2010s), so its total
is mostly that day's and is not shifted. The shift comes from each station's
recorded observation hour, never from which choice makes the result larger;
the build prints the result under the other shift as a sensitivity check.

THE SCENE
---------
  * The map: relief, both basins and the San Diego River watershed outlined,
    the Cedar perimeter (and every other fire that burned a twentieth of
    either basin since 1950), the gauges, rain stations and the Mast Rd gauge.
  * Two STORM SLABS behind the map's north edge, one per creek, the control
    further back and higher. Time runs west to east across the map's width.
    Every storm is a sphere: depth is its EXPECTED peak (how big a storm it
    was in flow terms), height is observed over expected on a log scale, so
    the flat floor is "normal" and a stem stands up out of it (orange: the
    creek ran higher than that storm normally gave) or hangs below (blue).
    A white line is the three-winter rolling average; a wall marks the fire.
  * Playback runs month by month: storms arrive in their month and a "now"
    frame slides east through both slabs.

DATA (public, keyless; caches under data/)
------------------------------------------
  USGS NWIS daily values and site service; USGS NLDI basins; RCC-ACIS daily
  precipitation; CAL FIRE FRAP perimeters (the Burn Record example's cache);
  USGS WBD HUC-10 divide (the Watershed example's cache); AWS Terrain Tiles;
  OpenTopoMap.

USAGE
-----
    python build_cedar_runoff_scene.py            # uses data/ caches
    python build_cedar_runoff_scene.py --refresh  # re-fetch
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DATA = HERE / "data"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "examples" / "San_Diego_River_Watershed_Example"))
sys.path.insert(0, str(REPO / "examples" / "San_Diego_River_Pulse_Example"))
sys.path.insert(0, str(REPO / "examples" / "San_Diego_Fire_History_Example"))

import build_fire_history_scene as fh                               # noqa: E402
import build_pulse_scene as pu                                      # noqa: E402
import build_watershed_scene as fm                                  # noqa: E402
import watershed_data as wd                                         # noqa: E402
from glyphviz_core import basemap as bm                             # noqa: E402
from glyphviz_core import terrain as tr                             # noqa: E402

# ---------------------------------------------------------------------------
# 1. CONFIGURATION
# ---------------------------------------------------------------------------

OUT_STEM = "sd_cedar_runoff"

FIRE_DAY = dt.date(2003, 10, 25)
BASELINE_START = dt.date(1960, 10, 1)          # ten winters after Conejos (1950)
T0, T1 = dt.date(1960, 10, 1), dt.date(2025, 10, 1)

BASINS = [
    dict(key="sweetwater", site="11015000", rain="USC00042239", role="burned",
         title="Sweetwater River near Descanso", color=(255, 170, 90)),
    dict(key="campo", site="11012500", rain="USC00041424", role="control",
         title="Campo Creek near Campo", color=(120, 215, 230)),
]
MAST_RD = "11022480"
DAMS = [("El Capitan Dam", -116.8095, 32.8839), ("San Vicente Dam", -116.9265, 32.9133)]

# Storm definition (see the module docstring).
STORM_START_IN, STORM_3DAY_IN, STORM_CONTINUE_IN = 0.5, 1.5, 0.2
ANTECEDENT_DAYS, MAX_MISSING_ANTECEDENT = 60, 6

PERIODS = [  # (first day, label, colour)
    (dt.date(1900, 1, 1), "before the fire", (150, 165, 190)),
    (FIRE_DAY, "winters 1–3 after", (255, 105, 35)),
    (dt.date(2006, 10, 1), "winters 4–8 after", (250, 195, 60)),
    (dt.date(2011, 10, 1), "winter 9 on", (105, 205, 165)),
]
WINDOWS = [(2004, 2006), (2007, 2011), (2012, 2025)]

PLATE_HEIGHT = 260.0
TERRAIN_EXAG = 4.0
SURFACE_COLS = 300
DEM_ZOOM = 11
MAP_PAD_DEG = 0.03
LINE_CLEARANCE = 0.8

LOG_MAX = 3.5                                   # log10(q + 1): 0 .. ~3,160 cfs
SLAB_GAP, SLAB_DEPTH = 36.0, 46.0               # behind the map's north edge; y = expected peak
SLAB_STEP_Y, SLAB_STEP_Z = 70.0, 110.0          # the control slab: further back and higher
SLAB_BASE_Z = 45.0                              # the burned slab's floor, clear of the ground
Z_PER_DECADE = 40.0                             # ×10 stands 40 units tall
# A creek that barely ran for a storm has a residual heading for minus
# infinity; below ×0.1 a stem stops (and says so in its label). Above, ×46 —
# the largest in the record — still fits.
EXCESS_UP, EXCESS_DOWN = 70.0, 40.0
STEM_R = 0.28

BG_COLOR = (12, 14, 18)
TAG_COLOR = (236, 238, 232)
LATTICE = (95, 105, 112)
UP_COLOR, DOWN_COLOR = (255, 150, 60), (90, 140, 225)

GEO_CUBE, GEO_SPHERE, GEO_OCTA, GEO_PIN, GEO_CYLINDER, GEO_POINT = 1, 3, 11, 16, 19, 22
GEO_CUBE_WIRE = 0
TOPO_PLOT, TOPO_SURFACE = 16, 17
NODE_WORLD, NODE_GLYPH, NODE_GRID = 0, 5, 6
CUBE_HALF = 1.0 / math.sqrt(3.0)

MONTHS = [(y, m) for y in range(T0.year, T1.year + 1) for m in range(1, 13)
          if T0 <= dt.date(y, m, 1) < T1]
N = len(MONTHS)                                 # 780 monthly frames


def water_year(d: dt.date) -> int:
    return d.year + 1 if d.month >= 10 else d.year


def month_frame(d: dt.date) -> int:
    return (d.year - T0.year) * 12 + d.month - T0.month


def period_of(d: dt.date) -> int:
    return max(i for i, (first, _l, _c) in enumerate(PERIODS) if d >= first)


def log_axis(q: float) -> float:
    return max(0.0, min(LOG_MAX, math.log10(max(q, 0.0) + 1.0))) / LOG_MAX


# ---------------------------------------------------------------------------
# 2. DATA
# ---------------------------------------------------------------------------

def _cached(name: str, refresh: bool, fetch):
    path = DATA / name
    if path.is_file() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    DATA.mkdir(parents=True, exist_ok=True)
    obj = fetch()
    path.write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")
    return obj


def fetch_flow(site: str, refresh: bool) -> dict:
    """{"site", "name", "lon", "lat", "drain_sq_mi", "first_day", "cfs": [...]},
    one entry per day from first_day, None where the record has no value."""
    def fetch():
        txt = wd._get("https://waterservices.usgs.gov/nwis/dv/",
                      {"format": "rdb", "sites": site, "parameterCd": "00060",
                       "statCd": "00003", "startDT": "1950-01-01"}).decode()
        rows = [l.split("\t") for l in txt.splitlines() if l and not l.startswith("#")]
        vcol = next(i for i, h in enumerate(rows[0]) if h.endswith("_00060_00003"))
        dcol = rows[0].index("datetime")
        got = {}
        for r in rows[2:]:
            try:
                got[r[dcol]] = float(r[vcol])
            except (ValueError, IndexError):
                continue
        first = dt.date.fromisoformat(min(got))
        n = (dt.date.fromisoformat(max(got)) - first).days + 1
        meta = wd._get("https://waterservices.usgs.gov/nwis/site/",
                       {"format": "rdb", "sites": site, "siteOutput": "expanded"}).decode()
        m = [l.split("\t") for l in meta.splitlines() if l and not l.startswith("#")]
        info = dict(zip(m[0], m[2]))
        return dict(site=site, name=info["station_nm"], lon=float(info["dec_long_va"]),
                    lat=float(info["dec_lat_va"]),
                    drain_sq_mi=float(info["drain_area_va"] or "nan"),
                    first_day=first.isoformat(),
                    cfs=[got.get((first + dt.timedelta(days=i)).isoformat()) for i in range(n)])
    return _cached(f"flow_daily_{site}.json", refresh, fetch)


def fetch_rain(sid: str, refresh: bool) -> dict:
    """{"sid", "name", "lon", "lat", "elev_ft", "first_day", "inches": [...]}: ACIS
    daily precipitation; a trace is 0.0; missing, and days folded into a
    later accumulated total ("S"), are None."""
    def fetch():
        res = json.loads(wd._get("https://data.rcc-acis.org/StnData", body={
            "sid": sid, "sdate": "1959-01-01", "edate": "por", "elems": [{"name": "pcpn"}],
            "meta": "name,ll,elev"}))
        vals = []
        for _day, v in res["data"]:
            vals.append(None if v in ("M", "S") else 0.0 if v == "T"
                        else float(v.rstrip("ASL")) if v.rstrip("ASL") else None)
        return dict(sid=sid, name=res["meta"]["name"].title(), lon=res["meta"]["ll"][0],
                    lat=res["meta"]["ll"][1], elev_ft=res["meta"].get("elev"),
                    first_day=res["data"][0][0], inches=vals)
    return _cached(f"rain_daily_{sid}.json", refresh, fetch)


def fetch_obs_hour(sid: str, refresh: bool) -> dict:
    """The hour a station's daily precipitation is read, from ACIS ('add': 't'),
    tallied over the scene's span. -> {"sid", "modal_hour", "counts": {hour: days}}"""
    def fetch():
        res = json.loads(wd._get("https://data.rcc-acis.org/StnData", body={
            "sid": sid, "sdate": T0.isoformat(), "edate": (T1 - dt.timedelta(days=1)).isoformat(),
            "elems": [{"name": "pcpn", "add": "t"}]}))
        counts: dict[str, int] = {}
        for _day, (v, hour) in res["data"]:
            if v != "M" and hour not in (None, -1):
                counts[str(hour)] = counts.get(str(hour), 0) + 1
        modal = max(counts, key=counts.get)
        return dict(sid=sid, modal_hour=int(modal), counts=counts)
    return _cached(f"rain_obs_hour_{sid}.json", refresh, fetch)


def shift_for(obs_hour: int) -> int:
    """Days to move a gauge's totals EARLIER: a reading before noon covers more
    of the previous calendar day than of its own."""
    return 1 if 0 < obs_hour < 12 else 0


def _rings(geo: dict) -> list[list]:
    out = []
    for f in geo["features"]:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        out += [[q[:2] for q in p[0]] for p in polys]
    return out


def fetch_basin(site: str, refresh: bool) -> list[list]:
    return _rings(_cached(f"basin_{site}.geojson", refresh, lambda: json.loads(wd._get(
        f"https://api.water.usgs.gov/nldi/linked-data/nwissite/USGS-{site}/basin",
        {"simplified": "false"}))))


def fetch_dam_basin(name: str, lon: float, lat: float, refresh: bool) -> list[list]:
    def fetch():
        pos = json.loads(wd._get("https://api.water.usgs.gov/nldi/linked-data/comid/position",
                                 {"coords": f"POINT({lon} {lat})"}))
        comid = pos["features"][0]["properties"]["comid"]
        return json.loads(wd._get(f"https://api.water.usgs.gov/nldi/linked-data/comid/{comid}/basin"))
    key = name.lower().replace(" ", "_")
    return _rings(_cached(f"basin_{key}.geojson", refresh, fetch))


def area_fractions(target: list[list], fires: list[dict], min_frac: float, step: float = 0.003,
                   within: list[list] | None = None) -> list[tuple[dict, float, np.ndarray]]:
    """Fraction of the `target` rings' area inside each fire, on a lon/lat
    sample grid. -> [(fire, fraction, burned-sample mask)]."""
    allc = np.array([q for r in target for q in r])
    mn, mx = allc.min(axis=0), allc.max(axis=0)
    X, Y = np.meshgrid(np.arange(mn[0], mx[0], step), np.arange(mn[1], mx[1], step))
    px, py = X.ravel(), Y.ravel()
    inside = np.zeros(px.shape, dtype=bool)
    for r in target:
        inside |= fh.points_in_ring(px, py, r)
    px, py = px[inside], py[inside]
    out = []
    for f in fires:
        v = np.array([q for p in f["polys"] for q in p[0]])
        a, b = v.min(axis=0), v.max(axis=0)
        if a[0] > mx[0] or b[0] < mn[0] or a[1] > mx[1] or b[1] < mn[1]:
            continue
        hit = np.zeros(px.shape, dtype=bool)
        for p in f["polys"]:
            h = fh.points_in_ring(px, py, p[0])
            for hole in p[1:]:
                h &= ~fh.points_in_ring(px, py, hole)
            hit |= h
        if hit.mean() >= min_frac:
            out.append((f, float(hit.mean()), hit))
    return out, px, py


# ---------------------------------------------------------------------------
# 3. STORMS AND THE PRE-FIRE MODEL
# ---------------------------------------------------------------------------

@dataclass
class Storm:
    day: dt.date
    rain: float              # inches, the storm's total
    ante: float              # inches in the 60 days before
    base: float              # cfs, lowest daily flow in the 3 days before
    peak: float              # cfs, highest daily mean flow, storm days + 1
    expected: float = 0.0    # cfs, the pre-fire model's peak for this storm
    residual: float = 0.0    # ln(peak + 1) - ln(expected + 1)

    @property
    def multiplier(self) -> float:
        return math.exp(self.residual)


def daily(series: list, first_day: str, day: dt.date):
    i = (day - dt.date.fromisoformat(first_day)).days
    return series[i] if 0 <= i < len(series) else None


def find_storms(flow: dict, rain: dict, shift: int) -> list[Storm]:
    """Storms between T0 and T1 (see the module docstring). `shift` reads the
    rain gauge's day d+shift as day d's rain."""
    days = [T0 - dt.timedelta(days=ANTECEDENT_DAYS + 3) + dt.timedelta(days=i)
            for i in range((T1 - T0).days + ANTECEDENT_DAYS + 12)]
    rv = np.array([np.nan if (v := daily(rain["inches"], rain["first_day"],
                                         d + dt.timedelta(days=shift))) is None else v
                   for d in days])
    fv = np.array([np.nan if (v := daily(flow["cfs"], flow["first_day"], d)) is None else v
                   for d in days])
    out, i = [], ANTECEDENT_DAYS + 3
    while i < len(days) - 8:
        if (days[i] < T1 and rv[i] >= STORM_START_IN and not np.isnan(rv[i:i + 3]).any()
                and np.nansum(rv[i:i + 3]) >= STORM_3DAY_IN):
            j = i + 1
            while j < len(days) and not np.isnan(rv[j]) and rv[j] >= STORM_CONTINUE_IN:
                j += 1
            end = max(j, i + 3)
            before, during = fv[i - 3:i], fv[i:end + 1]
            ante = rv[i - ANTECEDENT_DAYS:i]
            if (not np.isnan(before).all() and not np.isnan(during).all()
                    and np.isnan(ante).sum() <= MAX_MISSING_ANTECEDENT):
                out.append(Storm(days[i], float(np.nansum(rv[i:end])), float(np.nansum(ante)),
                                 float(np.nanmin(before)), float(np.nanmax(during))))
            i = end
        else:
            i += 1
    return out


def design_row(s: Storm) -> list[float]:
    return [1.0, math.log(s.rain), math.log(s.ante + 1.0), math.log(s.base + 0.1)]


def fit(storms: list[Storm]) -> tuple[np.ndarray, float, int]:
    pre = [s for s in storms if BASELINE_START <= s.day < FIRE_DAY]
    A = np.array([design_row(s) for s in pre])
    y = np.array([math.log(s.peak + 1.0) for s in pre])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    return coef, float((y - A @ coef).std()), len(pre)


@dataclass
class Basin:
    spec: dict
    flow: dict
    rain: dict
    rings: list[list]
    storms: list[Storm]
    coef: np.ndarray
    sd: float
    n_pre: int
    shift: int
    shift_sd: dict
    obs: dict
    fires: list[tuple[dict, float]]
    cedar_frac: float
    windows: dict = field(default_factory=dict)
    pre_windows: list[float] = field(default_factory=list)
    other_shift: dict = field(default_factory=dict)   # the same summary with the other shift


def analyse(spec: dict, refresh: bool, fires: list[dict], notes: list[str]) -> Basin:
    flow = fetch_flow(spec["site"], refresh)
    rain = fetch_rain(spec["rain"], refresh)
    rings = fetch_basin(spec["site"], refresh)
    trials = {}
    for shift in (0, 1):
        storms = find_storms(flow, rain, shift)
        coef, sd, n_pre = fit(storms)
        trials[shift] = (sd, storms, coef, n_pre)
    obs = fetch_obs_hour(spec["rain"], refresh)
    shift = shift_for(obs["modal_hour"])
    for sd_, storms_, coef_, _n in trials.values():
        for s in storms_:
            pred = float(np.array(design_row(s)) @ coef_)
            s.expected = math.exp(pred) - 1.0
            s.residual = math.log(s.peak + 1.0) - pred
    sd, storms, coef, n_pre = trials[shift]
    burned, _px, _py = area_fractions(rings, [f for f in fires if f["year"] >= 1950], 0.02)
    fire_rows = sorted(((f, frac) for f, frac, _ in burned), key=lambda t: t[0]["year"])
    cedar = next((frac for f, frac in fire_rows
                  if f["year"] == 2003 and (f["name"] or "").upper() == "CEDAR"), 0.0)
    b = Basin(spec, flow, rain, rings, storms, coef, sd, n_pre, shift,
              {k: round(v[0], 3) for k, v in trials.items()}, obs, fire_rows, cedar)

    def window_mean(a, c, pool):
        rs = [s.residual for s in pool if a <= water_year(s.day) <= c]
        return (len(rs), math.exp(sum(rs) / len(rs))) if rs else (0, float("nan"))

    def summary(pool):
        return ({w: window_mean(*w, pool) for w in WINDOWS},
                [m for a in range(BASELINE_START.year + 1, 2002)
                 for n, m in [window_mean(a, a + 2, pool)] if n >= 6])

    b.windows, b.pre_windows = summary(storms)
    other = trials[1 - shift][1]
    ow, opre = summary(other)
    b.other_shift = dict(shift=1 - shift, windows=ow, pre_max=max(opre), pre_count=len(opre))
    notes.append(f"{spec['title']}: {len(storms)} storms, {n_pre} pre-fire; rain read at "
                 f"{obs['modal_hour']:02d}:00 -> shift {shift} day (residual sd {trials[0][0]:.3f} "
                 f"unshifted vs {trials[1][0]:.3f} shifted); "
                 f"Cedar burned {cedar:.0%}; " + "; ".join(
                     f"WY{a}-{c}: {n} storms x{m:.2f}" for (a, c), (n, m) in b.windows.items())
                 + f"; pre-fire 3-winter windows {len(b.pre_windows)}, max x{max(b.pre_windows):.2f}"
                 + f" | with shift {1 - shift}: " + "; ".join(
                     f"WY{a}-{c}: {n} storms x{m:.2f}" for (a, c), (n, m) in ow.items())
                 + f"; pre-fire max x{max(opre):.2f}")
    return b


# ---------------------------------------------------------------------------
# 4. BASEMAP
# ---------------------------------------------------------------------------

def fetch_basemap(want: bm.BBox, out_path: Path, highlight: list[list]) -> bm.BBox:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
    plan = bm.plan_basemap(want, provider_key="opentopomap", target_px=2048, tile_cap=90)
    print(f"  basemap: {plan.provider.label}, zoom {plan.zoom}, {plan.tile_count} tiles")
    bm.build_basemap(plan, out_path)
    img = Image.open(out_path).convert("RGB")
    w, h = img.size
    b = plan.bbox

    def tone(src, grey, bright):
        return ImageEnhance.Brightness(
            Image.blend(src, src.convert("L").convert("RGB"), grey)).enhance(bright)

    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    for ring in highlight:
        draw.polygon([((lon - b.lon_min) / (b.lon_max - b.lon_min) * w,
                       (b.lat_max - lat) / (b.lat_max - b.lat_min) * h) for lon, lat in ring],
                     fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(2.0))
    Image.composite(tone(img, 0.55, 0.62), tone(img, 0.92, 0.3), mask).save(out_path)
    return plan.bbox


# ---------------------------------------------------------------------------
# 5. SCENE
# ---------------------------------------------------------------------------

@dataclass
class Built:
    df: pd.DataFrame
    ch_map: pd.DataFrame
    ch_tracks: pd.DataFrame
    notes: list[str]
    checks: dict


def fmt_month(y: int, m: int) -> str:
    return f"{dt.date(y, m, 1):%b} {y}"


def build(layout: fm.Layout, lattice: tr.Lattice, map_path: Path | None, basins: list[Basin],
          fires: list[dict], context: dict, notes: list[str]) -> Built:
    R = pu.Rows([])
    ch = pu.Channels(N)
    b = layout.bbox
    hw, hh = layout.half_w, layout.half_h
    zpm = layout.z_per_m
    rest = N - 1
    checks: dict = {"storms": [], "stems": [], "points": []}

    def add(**kw) -> int:
        return R.add(type=NODE_GLYPH, parent_id=0, branch_level=0, **kw)

    def label(x, y, z, text, pinned=1, **kw) -> int:
        return add(geometry=GEO_CUBE, scale_x=0.0, scale_y=0.0, scale_z=0.0,
                   translate_x=fm._r(x), translate_y=fm._r(y), translate_z=fm._r(z),
                   show_text=pinned, text=text, **kw)

    def polyline(pts, width, color, text="", ch_input=0, hide=0) -> int:
        ax, ay, az = pts[0]
        par = add(geometry=GEO_POINT, topo=TOPO_PLOT, ratio=width, color_r=color[0],
                  color_g=color[1], color_b=color[2], color_a=0, translate_x=fm._r(ax),
                  translate_y=fm._r(ay), translate_z=fm._r(az), text=text,
                  ch_input_id=ch_input, hide=hide)
        for x, y, z in pts:
            R.add(type=NODE_GLYPH, parent_id=par, branch_level=1, geometry=GEO_CUBE,
                  scale_x=0.0, scale_y=0.0, scale_z=0.0, translate_x=fm._r(x - ax),
                  translate_y=fm._r(y - ay), translate_z=fm._r(z - az),
                  color_r=color[0], color_g=color[1], color_b=color[2])
        return par

    def draped(ring, width, color, text, simplify_m=40.0) -> int:
        lo, la = tr.simplify_polyline([q[0] for q in ring], [q[1] for q in ring], simplify_m)
        dl, dt_, dh = tr.drape_polyline(lattice, lo, la, clearance=LINE_CLEARANCE / zpm)
        wx, wy = layout.world_xy(dl, dt_)
        polyline(list(zip(wx, wy, dh * zpm)), width, color, text)
        return len(dl)

    R.add(type=NODE_WORLD, parent_id=0, branch_level=0, geometry=0,
          color_r=BG_COLOR[0], color_g=BG_COLOR[1], color_b=BG_COLOR[2],
          tag_color_mode=1, tag_color_r=TAG_COLOR[0], tag_color_g=TAG_COLOR[1],
          tag_color_b=TAG_COLOR[2], tag_font_size=12,
          text="San Diego River Watershed Atlas · After the Cedar Fire · does the same rain make a bigger river?")
    grid = R.add(type=NODE_GRID, parent_id=0, branch_level=0, geometry=GEO_CUBE_WIRE,
                 scale_x=layout.sx, scale_y=layout.sy, scale_z=fm._r(layout.grid_scale_z, 5),
                 trigger_lo_x=fm._r(b.lon_min, 6), trigger_hi_x=fm._r(b.lon_max, 6),
                 trigger_lo_y=fm._r(b.lat_min, 6), trigger_hi_y=fm._r(b.lat_max, 6),
                 segments_x=6, segments_y=4, color_r=70, color_g=78, color_b=84, color_a=90,
                 text=f"Map window · lon {b.lon_min:.2f}..{b.lon_max:.2f}, lat {b.lat_min:.2f}..{b.lat_max:.2f}")

    # -- Terrain -------------------------------------------------------------------
    textured = map_path is not None and map_path.is_file()
    terrain = add(geometry=GEO_POINT, topo=TOPO_SURFACE, color_a=255,
                  texture_id=1 if textured else 0,
                  text=(f"Terrain · USGS 3DEP via AWS Terrain Tiles · {lattice.cols}x{lattice.rows} "
                        f"lattice · {TERRAIN_EXAG:g}x vertical exaggeration"))
    LON, LAT = np.meshgrid(lattice.lons, lattice.lats)
    WX, WY = layout.world_xy(LON, LAT)
    WZ = lattice.heights * zpm
    for j in range(lattice.rows):
        for i in range(lattice.cols):
            t = min(lattice.heights[j, i] / 2000.0, 1.0)
            R.add(type=NODE_GLYPH, parent_id=terrain, branch_level=1, geometry=GEO_CUBE,
                  scale_x=0.0, scale_y=0.0, scale_z=0.0, translate_x=fm._r(WX[j, i]),
                  translate_y=fm._r(WY[j, i]), translate_z=fm._r(WZ[j, i]),
                  color_r=int(50 + 90 * t), color_g=int(55 + 85 * t), color_b=int(50 + 70 * t))

    # -- Map lines -------------------------------------------------------------------
    draped(context["divide"], 0.08, (140, 215, 255),
           f"San Diego River watershed divide · {context['divide_km2']:,.0f} km² · the Atlas's home basin")
    shown = set()
    for bs in basins:
        spec = bs.spec
        for ring in bs.rings:
            draped(ring, 0.16, spec["color"],
                   f"{spec['title']} basin · USGS {spec['site']} · {bs.flow['drain_sq_mi']:g} sq mi · "
                   f"{spec['role']}", simplify_m=30.0)
        for f, frac in bs.fires:
            if frac < 0.05 or f["oid"] in shown:
                continue
            shown.add(f["oid"])
            cedar = f["year"] == 2003 and (f["name"] or "").upper() == "CEDAR"
            for p in f["polys"]:
                draped(p[0], 0.14 if cedar else 0.06, (240, 70, 45) if cedar else (170, 110, 90),
                       f"{fh.title(f['name'])} · {f['year']} · {f['acres']:,.0f} acres · burned "
                       f"{frac:.0%} of the {spec['title']} basin", simplify_m=60.0)
    notes.append(f"map fires drawn (>=5% of a basin): {len(shown)}")

    def point(lon, lat, geometry, size, color, text, pinned=False, lift=0.0) -> int:
        km = lattice.surface_height(lon, lat) / 1000.0 + lift / layout.grid_scale_z
        nid = R.add(type=NODE_GLYPH, parent_id=grid, branch_level=1, geometry=geometry,
                    translate_x=fm._r(lon, 6), translate_y=fm._r(lat, 6), translate_z=fm._r(km, 6),
                    scale_x=size, scale_y=size, scale_z=size, color_r=color[0], color_g=color[1],
                    color_b=color[2], show_text=1 if pinned else 0, text=text,
                    segments_x=12, segments_y=10)
        checks["points"].append((nid, lon, lat, lift))
        return nid

    for bs in basins:
        fl, rn, spec = bs.flow, bs.rain, bs.spec
        point(fl["lon"], fl["lat"], GEO_PIN, 3.0, spec["color"],
              f"{spec['title']} gauge · {spec['role']} basin", pinned=True)
        point(rn["lon"], rn["lat"], GEO_OCTA, 1.6, (190, 170, 250),
              f"NOAA GHCN {rn['sid']} · {rn['name']} · {rn['elev_ft']:,.0f} ft · daily rain for the "
              f"{spec['title']} storms")
    mast = context["mast"]
    point(mast["lon"], mast["lat"], GEO_PIN, 2.4, (230, 230, 230),
          f"Mast Rd gauge (the Atlas's own) · the Cedar Fire burned {context['mast_burn']:.0%} of its "
          f"basin, and {context['above_dams']:.0%} of that burn drains into El Capitan or San Vicente "
          f"reservoir before reaching it")
    for (name, lon, lat), share in zip(DAMS, context["dam_shares"]):
        point(lon, lat, GEO_CUBE, 1.6, (200, 225, 240),
              f"{name} · {share:.0%} of the Cedar burn in the Mast Rd basin drains into this reservoir")
    cedar_f = context["cedar"]
    ring0 = max((p[0] for p in cedar_f["polys"]), key=len)
    cx, cy = np.array(ring0).mean(axis=0)
    point(float(cx), float(cy), GEO_CUBE, 0.0, (255, 255, 255),
          f"Cedar Fire · Oct 2003 · {cedar_f['acres']:,.0f} acres", pinned=True, lift=6.0)
    mx, my = layout.world_xy(mast["lon"], mast["lat"])
    label(float(mx), float(my), 22.0,
          f"Mast Rd gauge · {context['above_dams']:.0%} of its Cedar burn is above two dams")

    # -- The storm slabs -----------------------------------------------------------------
    # One per creek, behind the map's north edge. Time runs west to east across
    # the map's own width; depth is the storm's EXPECTED peak (how big a storm
    # it was, in flow terms); height is its excess over expected, so the flat
    # floor is "normal" and a storm's stem stands up out of it or hangs below.
    # The control slab sits behind and above the burned one.
    def t_x(d: dt.date) -> float:
        return -hw + (d - T0).days / (T1 - T0).days * 2.0 * hw

    def z_excess(residual_ln: float) -> float:
        return max(-EXCESS_DOWN, min(EXCESS_UP, residual_ln / math.log(10.0) * Z_PER_DECADE))

    storm_ch: dict[int, int] = {}

    def month_channel(k: int) -> int:
        if k not in storm_ch:
            storm_ch[k] = ch.channel(hide=[0 if f >= k else 1 for f in range(N)])
        return storm_ch[k]

    now_x = [fm._r(t_x(dt.date(y, m, 15))) for y, m in MONTHS]
    checks["slabs"] = {}
    for c_i, bs in enumerate(basins):
        spec = bs.spec
        y0 = hh + SLAB_GAP + c_i * SLAB_STEP_Y
        y1 = y0 + SLAB_DEPTH
        zb = SLAB_BASE_Z + c_i * SLAB_STEP_Z
        xa, xb = -hw, hw

        def sy_(q):
            return y0 + log_axis(q) * SLAB_DEPTH

        polyline([(xa, y0, zb), (xb, y0, zb), (xb, y1, zb), (xa, y1, zb), (xa, y0, zb)],
                 0.07, (170, 178, 184), f"{spec['title']} · normal: every storm exactly as expected")
        for q in (9, 99, 999):
            polyline([(xa, sy_(q), zb), (xb, sy_(q), zb)], 0.03, LATTICE,
                     f"expected peak {q + 1:,} cfs")
        for q in (9, 999):
            label(xa - 3.0, sy_(q), zb, f"{q + 1:,} cfs")
        for yr in range(1970, 2030, 10):
            xx = t_x(dt.date(yr, 1, 1))
            polyline([(xx, y0, zb), (xx, y1, zb)], 0.03, LATTICE, str(yr))
            if c_i == 0:
                label(xx, y0 - 2.0, zb - EXCESS_DOWN - 4.0, str(yr))
        for mult in (0.1, 10):
            zz = zb + z_excess(math.log(mult))
            polyline([(xa, y1, zz), (xb, y1, zz)], 0.03, LATTICE,
                     f"×{mult:g} expected" + (" (stems stop here)" if mult < 1 else ""))
            label(xb + 3.0, y1, zz, f"×{mult:g}")
        for mult in (0.1, 10):
            zz = zb + z_excess(math.log(mult))
            polyline([(xa, y1, zb), (xa, y1, zz)], 0.05, LATTICE, "")
        label(xb + 3.0, y1, zb, "×1 (normal)")
        head = (f"{spec['title']} · the Cedar Fire burned {bs.cedar_frac:.0%} of its basin"
                if spec["role"] == "burned" else f"{spec['title']} · unburned control basin")
        label(xa, y1, zb + EXCESS_UP + 30.0, head)

        fx = t_x(FIRE_DAY)
        wall = (240, 70, 45) if spec["role"] == "burned" else (140, 128, 128)
        polyline([(fx, y0, zb - EXCESS_DOWN), (fx, y1, zb - EXCESS_DOWN), (fx, y1, zb + EXCESS_UP),
                  (fx, y0, zb + EXCESS_UP), (fx, y0, zb - EXCESS_DOWN)], 0.1, wall,
                 "Cedar Fire · 25 October 2003")

        for s in bs.storms:
            k = month_frame(s.day)
            cid = month_channel(k)
            p = period_of(s.day)
            col = PERIODS[p][2]
            x, y = t_x(s.day), sy_(s.expected)
            dz = z_excess(s.residual)
            r = 0.7 + 0.7 * min(1.0, max(0.0, math.log(s.rain / STORM_3DAY_IN) / math.log(8.0)))
            text = (f"{spec['title']} · storm of {s.day:%d %b %Y} · {s.rain:.2f} in of rain, "
                    f"{s.ante:.1f} in in the 60 days before, {s.base:g} cfs before · peak "
                    f"{s.peak:,.1f} cfs vs {max(s.expected, 0):,.1f} expected · ×{s.multiplier:.2f} · "
                    f"{PERIODS[p][1]}")
            sid = add(geometry=GEO_SPHERE, translate_x=fm._r(x), translate_y=fm._r(y),
                      translate_z=fm._r(zb + dz), scale_x=fm._r(r), scale_y=fm._r(r), scale_z=fm._r(r),
                      color_r=col[0], color_g=col[1], color_b=col[2], segments_x=10, segments_y=8,
                      ch_input_id=cid, text=text)
            checks["storms"].append((sid, c_i, s, k))
            if abs(dz) > 0.1:
                sc = UP_COLOR if dz > 0 else DOWN_COLOR
                tid = add(geometry=GEO_CYLINDER, translate_x=fm._r(x), translate_y=fm._r(y),
                          translate_z=fm._r(zb + dz / 2.0), scale_x=STEM_R, scale_y=STEM_R,
                          scale_z=fm._r(abs(dz) / 2.0, 4), color_r=sc[0], color_g=sc[1], color_b=sc[2],
                          segments_x=6, segments_y=1, ch_input_id=cid, text=text)
                checks["stems"].append((tid, c_i, s, k, zb))

        # The rolling three-winter average excess, along the back edge.
        by_wy: dict[int, list[float]] = {}
        for s in bs.storms:
            by_wy.setdefault(water_year(s.day), []).append(s.residual)
        runs, pts = [], []
        for wy_ in range(T0.year + 1, T1.year + 1):
            rs = [r_ for w in (wy_ - 1, wy_, wy_ + 1) for r_ in by_wy.get(w, [])]
            if len(rs) < 3:
                if len(pts) >= 2:
                    runs.append(pts)
                pts = []
                continue
            pts.append((t_x(dt.date(wy_, 4, 1)), y1, zb + z_excess(sum(rs) / len(rs))))
        if len(pts) >= 2:
            runs.append(pts)
        for run in runs:
            polyline(run, 0.22, (245, 245, 245),
                     f"{spec['title']} · each winter with the one before and after: average excess")
        checks.setdefault("avg_runs", []).append(sum(len(r_) for r_ in runs))

        # The numbers, on one line under the title: pinned per window they
        # collided, the windows being only eight years apart on a 65-year axis.
        (n1, m1), (n2, m2), (n3, m3) = (bs.windows[w] for w in WINDOWS)
        label(xa, y1, zb + EXCESS_UP + 22.0,
              f"storms ran ×{m1:.2f} expected in winters 2004–06 ({n1}), ×{m2:.2f} in 2007–11, "
              f"×{m3:.2f} since · before the fire, no three winters above ×{max(bs.pre_windows):.2f}")
        if spec["role"] == "burned":
            xmas = max((s for s in bs.storms if FIRE_DAY <= s.day < dt.date(2004, 3, 1)),
                       key=lambda s: s.residual)
            label(t_x(xmas.day) + 4.0, sy_(xmas.expected), zb + z_excess(xmas.residual) - 6.0,
                  f"25 Dec 2003: ×{xmas.multiplier:.0f}")
            checks["xmas"] = xmas
        checks["slabs"][c_i] = (y0, zb)

        nf = polyline([(0.0, y0, zb - EXCESS_DOWN), (0.0, y1, zb - EXCESS_DOWN),
                       (0.0, y1, zb + EXCESS_UP), (0.0, y0, zb + EXCESS_UP),
                       (0.0, y0, zb - EXCESS_DOWN)], 0.08, (255, 236, 150), "Now",
                      ch_input=ch.channel(translate_x=now_x))
        R.set(nf, translate_x=now_x[rest])
        checks.setdefault("now_frames", []).append(nf)

    # Leader lines from each gauge up to its slab's south-west corner.
    for c_i, bs in enumerate(basins):
        gx, gy = layout.world_xy(bs.flow["lon"], bs.flow["lat"])
        gz = lattice.surface_height(bs.flow["lon"], bs.flow["lat"]) * zpm + 6.0
        y0, zb = checks["slabs"][c_i]
        polyline([(float(gx), float(gy), gz), (float(gx), float(gy), zb),
                  (float(gx), y0, zb)], 0.04, bs.spec["color"],
                 f"{bs.spec['title']} gauge → its storms")

    # Readout: one year and one month label on per frame, riding a bead above
    # the burned slab's now frame.
    y0, zb = checks["slabs"][0]
    bead = add(geometry=GEO_OCTA, translate_x=now_x[rest], translate_y=fm._r(y0),
               translate_z=fm._r(zb + EXCESS_UP + 2.0), scale_x=1.2, scale_y=1.2, scale_z=1.2,
               color_r=255, color_g=236, color_b=150, ch_input_id=ch.channel(translate_x=now_x),
               text="Now")
    checks["bead"] = bead
    checks["years"], checks["months"] = {}, {}
    for yr in range(T0.year, T1.year + 1):
        on = [1 if y == yr else 0 for y, _m in MONTHS]
        checks["years"][yr] = R.add(type=NODE_GLYPH, parent_id=bead, branch_level=1, geometry=GEO_CUBE,
                                    scale_x=0.0, scale_y=0.0, scale_z=0.0,
                                    translate_z=fm._r(4.0 / 1.2, 4), translate_x=fm._r(1.5 / 1.2, 4),
                                    show_text=on[rest], ch_input_id=ch.channel(show_text=on),
                                    text=str(yr))
    for mo in range(1, 13):
        on = [1 if m == mo else 0 for _y, m in MONTHS]
        checks["months"][mo] = R.add(type=NODE_GLYPH, parent_id=bead, branch_level=1, geometry=GEO_CUBE,
                                     scale_x=0.0, scale_y=0.0, scale_z=0.0,
                                     translate_z=fm._r(10.0 / 1.2, 4), translate_x=fm._r(1.5 / 1.2, 4),
                                     show_text=on[rest], ch_input_id=ch.channel(show_text=on),
                                     text=f"{dt.date(2000, mo, 1):%b}")

    # -- Legend, off the map's west edge -----------------------------------------------
    lx, ly = -hw - 60.0, -hh * 0.3
    z = 64.0
    label(lx, ly, z + 11.0, "Behind the map, each sphere is one storm (size = its rain):")
    for _first, name, col in PERIODS:
        add(geometry=GEO_SPHERE, translate_x=fm._r(lx), translate_y=fm._r(ly), translate_z=fm._r(z),
            scale_x=1.2, scale_y=1.2, scale_z=1.2, color_r=col[0], color_g=col[1], color_b=col[2],
            show_text=1, text=name)
        z -= 8.0
    for col, name in ((UP_COLOR, "above the floor: the creek ran higher than that storm normally gave"),
                      (DOWN_COLOR, "below: lower")):
        add(geometry=GEO_CYLINDER, translate_x=fm._r(lx), translate_y=fm._r(ly), translate_z=fm._r(z),
            scale_x=0.5, scale_y=0.5, scale_z=2.6, color_r=col[0], color_g=col[1], color_b=col[2],
            show_text=1, text=name)
        z -= 8.0
    label(lx, ly, z, "white line = three-winter average · time runs west to east")
    z -= 8.0
    label(lx, ly, z, f"relief {TERRAIN_EXAG:g}x exaggerated")

    ch_map, ch_tracks = ch.frames()
    checks.update(rest=rest, t_x=t_x, now_x=now_x, z_excess=z_excess)
    return Built(R.frame(), ch_map, ch_tracks, notes, checks)


# ---------------------------------------------------------------------------
# 6. VERIFICATION
# ---------------------------------------------------------------------------

def refit_independently(storms: list[Storm]) -> np.ndarray:
    """The pre-fire fit again by the normal equations, not lstsq."""
    pre = [s for s in storms if BASELINE_START <= s.day < FIRE_DAY]
    A = np.array([design_row(s) for s in pre])
    y = np.array([math.log(s.peak + 1.0) for s in pre])
    return np.linalg.solve(A.T @ A, A.T @ y)


def verify(node_path: Path, map_path: Path, tracks_path: Path, built: Built, layout: fm.Layout,
           lattice: tr.Lattice, basins: list[Basin]) -> list[str]:
    from glyphviz_core.channel_engine import ChannelEngine
    from glyphviz_core.channel_loader import load_ch_map, load_ch_tracks
    from glyphviz_core.csv_reader import load_node_csv
    from glyphviz_core.scene import Scene

    rep = []
    for bs in basins:
        diff = float(np.abs(refit_independently(bs.storms) - bs.coef).max())
        rep.append(f"{bs.spec['title']}: normal-equation refit differs from lstsq by {diff:.2e}")

    nodes = load_node_csv(str(node_path))
    by_id = {n.id: n for n in nodes}
    scene = Scene(nodes)
    worst = 0.0
    for sid, c_i, s, _k in built.checks["storms"]:
        y0, zb = built.checks["slabs"][c_i]
        want = (built.checks["t_x"](s.day), y0 + log_axis(s.expected) * SLAB_DEPTH,
                zb + built.checks["z_excess"](s.residual))
        wp = scene.world_pos(sid)
        worst = max(worst, *(abs(a - b_) for a, b_ in zip(wp, want)))
    stem_bad = 0
    for tid, c_i, s, _k, zb in built.checks["stems"]:
        nd, wp = by_id[tid], scene.world_pos(tid)
        lo_, hi_ = sorted((zb, zb + built.checks["z_excess"](s.residual)))
        if abs((wp[2] - nd.scale_z) - lo_) > 2e-3 or abs((wp[2] + nd.scale_z) - hi_) > 2e-3:
            stem_bad += 1
    worst_pt = max(max(abs(scene.world_pos(nid)[0] - layout.world_xy(lo, la)[0]),
                       abs(scene.world_pos(nid)[1] - layout.world_xy(lo, la)[1]))
                   for nid, lo, la, _l in built.checks["points"])
    rep.append(f"storms: {len(built.checks['storms'])} placed, worst error {worst:.4f}; stems "
               f"{len(built.checks['stems'])}, ends off the floor/sphere {stem_bad}; map points "
               f"xy error {worst_pt:.5f}")

    eng = ChannelEngine()
    tracks, id_to_col = load_ch_tracks(str(tracks_path))
    eng.load(load_ch_map(str(map_path)), tracks, id_to_col, nodes)
    wrong_hide = wrong_read = 0
    worst_now = 0.0
    frames = sorted({0, month_frame(dt.date(2003, 12, 1)), month_frame(dt.date(2005, 1, 1)), 600, N - 1})
    for k in frames:
        eng.apply_frame(k)
        sc = Scene(nodes)
        for nid, _c, _s, sk, *_rest in built.checks["storms"] + built.checks["stems"]:
            if bool(by_id[nid].hide) != (sk > k):
                wrong_hide += 1
        y, m = MONTHS[k]
        ys = [yy for yy, nid in built.checks["years"].items() if by_id[nid].show_text]
        ms = [mm for mm, nid in built.checks["months"].items() if by_id[nid].show_text]
        if ys != [y] or ms != [m]:
            wrong_read += 1
        for nf in built.checks["now_frames"] + [built.checks["bead"]]:
            worst_now = max(worst_now, abs(sc.world_pos(nf)[0] - built.checks["now_x"][k]))
    eng.reset()
    rep.append(f"playback at {len(frames)} frames: wrong storm/stem visibility {wrong_hide}, wrong "
               f"readout {wrong_read}, now-frame error {worst_now:.4f}; engine {eng.frame_count} frames, "
               f"{len(eng.bound_node_ids):,} bound nodes")
    return rep


# ---------------------------------------------------------------------------
# 7. MAIN
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", type=Path, default=HERE)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--no-basemap", action="store_true")
    args = ap.parse_args()
    notes: list[str] = []

    print("Data (cached under data/):")
    county = fh.fetch_county(False)
    fires = fh.fetch_fires(False, county, notes)
    basins = [analyse(spec, args.refresh, fires, notes) for spec in BASINS]

    # Mast Rd: how much of its basin the Cedar Fire burned, and how much of
    # that burn lies above each dam.
    cedar = next(f for f in fires if f["year"] == 2003 and (f["name"] or "").upper() == "CEDAR")
    mast_flow = fetch_flow(MAST_RD, args.refresh)
    mast_rings = fetch_basin(MAST_RD, args.refresh)
    [(_f, mast_burn, hit)], px, py = area_fractions(mast_rings, [cedar], 0.0, step=0.002)
    shares = []
    above = np.zeros(hit.shape, dtype=bool)
    for name, lon, lat in DAMS:
        inside = np.zeros(px.shape, dtype=bool)
        for ring in fetch_dam_basin(name, lon, lat, args.refresh):
            inside |= fh.points_in_ring(px, py, ring)
        shares.append(float((hit & inside).sum() / hit.sum()))
        above |= inside
    above_dams = float((hit & above).sum() / hit.sum())
    notes.append(f"Mast Rd basin: Cedar burned {mast_burn:.0%}; of that, "
                 + ", ".join(f"{s:.0%} above {n}" for (n, _a, _b), s in zip(DAMS, shares))
                 + f"; {above_dams:.0%} above either dam")
    outer, _inner, divide_km2 = wd.dissolve(wd.fetch_huc10())
    context = dict(divide=max(outer, key=len), divide_km2=divide_km2, mast=mast_flow,
                   mast_burn=mast_burn, dam_shares=shares, above_dams=above_dams, cedar=cedar)

    pts = [q for bs in basins for r in bs.rings for q in r] + \
          [q for p in cedar["polys"] for q in p[0]] + [[mast_flow["lon"], mast_flow["lat"]]]
    lons, lats = [q[0] for q in pts], [q[1] for q in pts]
    window = bm.BBox(min(lons) - MAP_PAD_DEG, max(lons) + MAP_PAD_DEG,
                     min(lats) - MAP_PAD_DEG, max(lats) + MAP_PAD_DEG)
    map_path = None
    if not args.no_basemap:
        (args.out_dir / "media").mkdir(parents=True, exist_ok=True)
        map_path = args.out_dir / "media" / "01_relief.png"
        window = fetch_basemap(window, map_path, [r for bs in basins for r in bs.rings])
    sy = PLATE_HEIGHT / (window.lat_max - window.lat_min)
    sx = sy * math.cos(math.radians((window.lat_min + window.lat_max) / 2.0))
    layout = fm.Layout(window, round(sx, 4), round(sy, 4), TERRAIN_EXAG)
    dem = tr.fetch_dem(window, zoom=DEM_ZOOM)
    lattice = tr.build_lattice(dem, window, cols=SURFACE_COLS)

    built = build(layout, lattice, map_path, basins, fires, context, notes)
    problems = fm.validate(built.df) + pu.validate_channels(built.df, built.ch_map, built.ch_tracks)
    if problems:
        print("\nVALIDATION FAILED:")
        for p in problems:
            print("  -", p)
        return 1

    from glyphviz_core.csv_reader import load_node_csv, save_node_csv
    node_path = args.out_dir / f"{OUT_STEM}_gv_node.csv"
    map_csv = args.out_dir / f"{OUT_STEM}_gv_ch-map.csv"
    tracks_csv = args.out_dir / f"{OUT_STEM}_gv_ch-tracks.csv"
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "raw_gv_node.csv"
        built.df.to_csv(raw, index=False)
        save_node_csv(load_node_csv(str(raw)), str(node_path))
    pu.write_csv(built.ch_map, map_csv)
    pu.write_csv(built.ch_tracks, tracks_csv)
    print(f"\nWrote {node_path.name}: {len(built.df):,} nodes, {node_path.stat().st_size / 1e6:.2f} MB")
    print(f"      {tracks_csv.name}: {N} frames x {len(built.ch_tracks.columns) - 1} tracks, "
          f"{tracks_csv.stat().st_size / 1e6:.2f} MB")
    for n_ in built.notes:
        print(f"  note: {n_}")
    print("\nVerification (real loader, Scene, ChannelEngine):")
    for line in verify(node_path, map_csv, tracks_csv, built, layout, lattice, basins):
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
