#!/usr/bin/env python3
"""
build_fire_history_scene.py — The Burn Record: San Diego County, 1910-2025
=========================================================================

A San Diego River Watershed Atlas scene, widened to the whole county. Every
wildfire perimeter CAL FIRE has mapped in San Diego County since 1910, laid
down on the county's relief as a STRATIGRAPHY:

  * THE GROUND KEEPS ITS FIRES. The county is cut into 1.5 km cells. Each
    calendar year a cell burns (at least half of it inside that year's
    perimeters) adds one tile to that cell's stack, oldest at the bottom,
    coloured by twenty-year era. Ground that burns again and again rises into a tall
    banded column; ground that has not burned since 1910 stays bare relief.
    The stack IS the fire-return record, readable without playing anything.
  * THE YEARS ARRIVE. Playback runs 1910 -> 2025 at four frames a year. A
    year's new tiles land white-hot, cool through orange over the next year
    and settle into their era colour, while that year's perimeters burn on
    the ground as outlines for a year and a half and then go out.
  * THE LEDGER. Behind the county's north edge, a bar per year of acres mapped, split by
    the cause FRAP records (lightning / people and equipment / miscellaneous
    or unknown), with a cursor and a readout that track the clock.

What this scene shows that no earlier Atlas scene can: time as ACCUMULATION on
the ground. The Pulse and the Storm Winter animate a quantity that rises and
falls; the Fire Siege stacks twelve days of hours into a cube. Here nothing
goes away — every year leaves a layer.

DATA (all public, keyless; derived caches under data/)
------------------------------------------------------
  Fires     CAL FIRE FRAP "California Fire Perimeters (all)", FeatureServer
            layer 0 — final perimeter shapes, YEAR_, ALARM_DATE (day
            precision), GIS_ACRES, CAUSE. Kept: every perimeter with a vertex
            or its centroid inside the county. The cache stores them
            simplified at 20 m, coordinates to 1e-5 degrees.
  County    US Census TIGERweb, GEOID 06073.
  Terrain   USGS 3DEP via AWS Terrain Tiles (glyphviz_core.terrain), basemap
            OpenTopoMap via glyphviz_core.basemap, toned dark at build time.
  Places    USGS GNIS (The National Map geonames service).

RULES THAT DECIDE WHAT A TILE MEANS (also in the README)
--------------------------------------------------------
  * A cell burns in year Y when at least half of a 4x4 grid of sample points
    across it lies inside the UNION of year Y's perimeters (holes excluded).
    Using the union means duplicate or adjoining same-year records cannot
    double-count, and a cell burns at most once per calendar year.
  * The tile is attributed to whichever of that year's fires covered the
    most sample points.
  * FRAP is incomplete before about 1950 and omits most fires under ~10 acres
    throughout; a bare cell means "no mapped fire", not "never burned".

USAGE
-----
    python build_fire_history_scene.py              # uses data/ caches; writes Burn_Record/ + Burn_Record.zip
    python build_fire_history_scene.py --refresh    # re-fetch everything
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import tempfile
import time
from collections import Counter, defaultdict
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

import build_pulse_scene as pu                                      # noqa: E402
import build_watershed_scene as fm                                  # noqa: E402
import watershed_data as wd                                         # noqa: E402
from glyphviz_core import basemap as bm                             # noqa: E402
from glyphviz_core import terrain as tr                             # noqa: E402

# ---------------------------------------------------------------------------
# 1. CONFIGURATION
# ---------------------------------------------------------------------------

OUT_STEM = "sd_fire_history"
# The scene is 17 MB of CSV, so it ships as SCENE_DIR.zip and the unzipped
# folder is gitignored (the Tropical Cyclone and GTDB examples' convention).
SCENE_DIR = "Burn_Record"
FIRST_YEAR, LAST_YEAR = 1910, 2025
YEARS = list(range(FIRST_YEAR, LAST_YEAR + 1))
FPY = 4                                     # frames per year
N = len(YEARS) * FPY                        # 464 frames

COUNTY_GEOID = "06073"
FRAP_ALL = ("https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/"
            "California_Historic_Fire_Perimeters/FeatureServer/0")
CACHE_SIMPLIFY_M = 20.0

CELL_KM = 1.5
SUBSAMPLES = 4                              # per axis -> 16 points per cell
BURN_FRACTION = 0.5

PLATE_HEIGHT = 260.0
TERRAIN_EXAG = 3.0
SURFACE_COLS = 300
DEM_ZOOM = 11
MAP_PAD_DEG = 0.02
MAP_INSIDE_GREY, MAP_INSIDE_BRIGHT = 0.88, 0.46
MAP_OUTSIDE_GREY, MAP_OUTSIDE_BRIGHT = 0.95, 0.17

TILE_FILL = 0.86                            # tile width / cell width
TILE_STEP = 1.7                             # world units per layer
TILE_THICK = 1.25                           # world units, < TILE_STEP: a visible seam
TILE_CLEARANCE = 0.25
CUBE_HALF = 1.0 / math.sqrt(3.0)            # GEO_CUBE is inscribed in the unit sphere

PERIM_SIMPLIFY_M = 90.0
PERIM_CLEARANCE = 0.5                       # world units above the surface
PERIM_FRAMES = 6                            # a year and a half on the ground
PERIM_COLOR = (255, 150, 55)
# Above the tiles, so the divide stays visible where the ground has burned
# most: a 7-tile stack stands ~12 units over the surface.
DIVIDE_CLEARANCE = 14.0
DIVIDE_STYLE = (0.1, (140, 215, 255))

# Twenty-year eras, cool for the oldest layers and warm for the newest, so the
# eye reads a stack's age before it reads a legend. Decades were tried first:
# twelve steps of one ramp left neighbouring decades indistinguishable (the
# 1990s, 2000s and 2010s all read as one orange), and a layer you cannot date
# by eye defeats the stack.
# Hues are chosen as they RENDER, under the scene's lighting, not as they read
# in a swatch: a yellow-green and an amber that differ on paper both come out
# yellow on a lit tile top.
ERAS = [(1910, 1929, (135, 90, 210)), (1930, 1949, (55, 110, 230)),
        (1950, 1969, (30, 185, 195)), (1970, 1989, (70, 185, 80)),
        (1990, 2009, (245, 135, 25)), (2010, 2025, (220, 40, 110))]
GLOW = [(255, 255, 236), (255, 232, 150), (255, 190, 90), (250, 140, 55)]
COOL_FRAMES = 4                              # ember -> era colour, after GLOW

CAUSE_GROUPS = [
    ("lightning", (1,), (150, 195, 255)),
    ("people and equipment", (2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 15, 16, 18, 19),
     (255, 145, 60)),
    ("miscellaneous or unknown", (9, 14, 17, None), (150, 150, 158)),
]
CAUSE_NAMES = {1: "lightning", 2: "equipment use", 3: "smoking", 4: "campfire",
               5: "debris burning", 6: "railroad", 7: "arson", 8: "playing with fire",
               9: "miscellaneous", 10: "vehicle", 11: "power line",
               12: "firefighter training", 13: "non-firefighter training",
               14: "unknown", 15: "structure", 16: "aircraft", 17: "volcanic",
               18: "escaped prescribed burn", 19: "illegal alien campfire"}

STRIP_GAP = 30.0                             # north of the plate
STRIP_H = 80.0                               # the tallest year
STRIP_BAR_FILL = 0.7

PLACES = [("Oceanside", 3, "Populated Place"), ("Escondido", 3, "Populated Place"),
          ("Ramona", 3, "Populated Place"), ("Julian", 3, "Populated Place"),
          ("Borrego Springs", 3, "Populated Place"), ("Alpine", 3, "Populated Place"),
          ("San Diego", 3, "Populated Place"), ("Campo", 3, "Populated Place")]

BG_COLOR = (12, 14, 18)
TAG_COLOR = (236, 238, 232)

GEO_CUBE, GEO_OCTA, GEO_POINT = 1, 11, 22
GEO_CUBE_WIRE = 0
TOPO_PLOT, TOPO_SURFACE = 16, 17
NODE_WORLD, NODE_GLYPH, NODE_GRID = 0, 5, 6


def year_frame(y: int) -> int:
    return (y - FIRST_YEAR) * FPY


def lerp(a, b, t):
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def era_color(year: int) -> tuple[int, int, int]:
    for first, last, col in ERAS:
        if first <= year <= last:
            return col
    raise ValueError(f"{year} is outside every era")


def tile_color_at(year: int, k: int) -> tuple[int, int, int] | None:
    """Colour of a year-Y tile at frame k, or None while it has not burned."""
    j = k - year_frame(year)
    if j < 0:
        return None
    if j < len(GLOW):
        return GLOW[j]
    j -= len(GLOW)
    if j < COOL_FRAMES:
        return lerp(GLOW[-1], era_color(year), (j + 1) / COOL_FRAMES)
    return era_color(year)


def cause_group(code) -> int:
    for i, (_n, codes, _c) in enumerate(CAUSE_GROUPS):
        if code in codes:
            return i
    return 2


def title(name) -> str:
    """'Cedar Fire', or 'Unnamed fire' for the many early records with no name."""
    if not name or not str(name).strip():
        return "Unnamed fire"
    return str(name).strip().title().replace("#", "No. ") + " Fire"


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


def fetch_county(refresh: bool) -> list[list]:
    """-> the county's outer rings (lon, lat)."""
    geo = _cached("county_06073.geojson", refresh, lambda: json.loads(wd._get(
        "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/"
        "MapServer/1/query", {"where": f"GEOID='{COUNTY_GEOID}'",
                              "outFields": "NAME,AREALAND,AREAWATER",
                              "outSR": "4326", "f": "geojson"})))
    g = geo["features"][0]["geometry"]
    polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
    return [[p[:2] for p in poly[0]] for poly in polys]


def points_in_ring(px: np.ndarray, py: np.ndarray, ring) -> np.ndarray:
    """Even-odd point-in-polygon, vectorised over points."""
    r = np.asarray(ring, dtype=np.float64)[:, :2]
    x0, y0 = r[:-1, 0], r[:-1, 1]
    x1, y1 = r[1:, 0], r[1:, 1]
    inside = np.zeros(px.shape, dtype=bool)
    for a, b, c, d in zip(x0, y0, x1, y1):
        if b == d:
            continue
        crosses = (b > py) != (d > py)
        xi = a + (py - b) * (c - a) / (d - b)
        inside ^= crosses & (px < xi)
    return inside


def fetch_fires(refresh: bool, county: list[list], notes: list[str]) -> list[dict]:
    """Every FRAP perimeter touching the county, simplified and cached.

    -> [{oid, year, name, alarm, acres, cause, unit, polys: [[outer, hole...]]}]
    """
    def fetch():
        lon = [p[0] for ring in county for p in ring]
        lat = [p[1] for ring in county for p in ring]
        env = f"{min(lon)},{min(lat)},{max(lon)},{max(lat)}"
        feats, off = [], 0
        while True:
            res = json.loads(wd._get(f"{FRAP_ALL}/query", {
                "where": "1=1", "geometry": env, "geometryType": "esriGeometryEnvelope",
                "inSR": "4326", "spatialRel": "esriSpatialRelIntersects",
                "outFields": "OBJECTID,YEAR_,FIRE_NAME,ALARM_DATE,GIS_ACRES,CAUSE,UNIT_ID",
                "returnGeometry": "true", "outSR": "4326", "f": "geojson",
                "orderByFields": "OBJECTID", "resultOffset": off,
                "resultRecordCount": 500}))
            feats += res["features"]
            off += len(res["features"])
            print(f"  FRAP: {off} perimeters")
            if len(res["features"]) < 500:
                break
        out = []
        for f in feats:
            p, g = f["properties"], f["geometry"]
            if not g or not p.get("YEAR_"):
                continue
            polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
            keep = []
            for poly in polys:
                rings = []
                for ring in poly:
                    lo, la = tr.simplify_polyline([q[0] for q in ring], [q[1] for q in ring],
                                                  CACHE_SIMPLIFY_M)
                    if len(lo) >= 4:
                        rings.append([[round(float(a), 5), round(float(b), 5)]
                                      for a, b in zip(lo, la)])
                if rings:
                    keep.append(rings)
            if not keep:
                continue
            verts = np.array([q for poly in keep for q in poly[0]])
            touching = any(points_in_ring(verts[:, 0], verts[:, 1], ring).any()
                           for ring in county)
            if not touching:
                cx, cy = verts.mean(axis=0)
                touching = any(points_in_ring(np.array([cx]), np.array([cy]), ring)[0]
                               for ring in county)
            if not touching:
                continue
            alarm = p.get("ALARM_DATE")
            out.append(dict(oid=p["OBJECTID"], year=int(p["YEAR_"]), name=p.get("FIRE_NAME"),
                            # timedelta, not time.gmtime: Windows refuses
                            # the negative epochs of every pre-1970 fire.
                            alarm=((dt.datetime(1970, 1, 1) + dt.timedelta(milliseconds=alarm))
                                   .strftime("%Y-%m-%d") if alarm else None),
                            acres=round(float(p.get("GIS_ACRES") or 0.0), 1),
                            cause=p.get("CAUSE"), unit=p.get("UNIT_ID"), polys=keep))
        out.sort(key=lambda f: (f["year"], f["oid"]))
        return dict(source=f"{FRAP_ALL} (simplified {CACHE_SIMPLIFY_M:g} m)",
                    fetched=time.strftime("%Y-%m-%d"), fires=out)

    fires = _cached("frap_perimeters_county.json", refresh, fetch)["fires"]
    before = len(fires)
    fires = [f for f in fires if FIRST_YEAR <= f["year"] <= LAST_YEAR]
    if before != len(fires):
        notes.append(f"{before - len(fires)} perimeters outside {FIRST_YEAR}-{LAST_YEAR} left out")
    return fires


def fetch_places(refresh: bool, notes: list[str]) -> list[dict]:
    def fetch():
        out = []
        for name, layer, fclass in PLACES:
            time.sleep(1.0)
            res = json.loads(wd._get(
                f"https://carto.nationalmap.gov/arcgis/rest/services/geonames/MapServer/{layer}/query",
                {"where": f"gaz_name = '{name}' AND state_alpha = 'CA' AND county_name = 'San Diego'",
                 "outFields": "gaz_id,gaz_name,gaz_featureclass", "returnGeometry": "true",
                 "outSR": "4326", "f": "json"}))
            hits = [f for f in res.get("features", [])
                    if f["attributes"]["gaz_featureclass"] == fclass]
            if len(hits) != 1:
                out.append(dict(name=name, missing=len(hits)))
                continue
            a, g = hits[0]["attributes"], hits[0]["geometry"]
            pts = g["points"] if "points" in g else [[g["x"], g["y"]]]
            out.append(dict(name=a["gaz_name"], gnis_id=a["gaz_id"], lon=pts[0][0],
                            lat=pts[0][1]))
        return out
    places = _cached("gnis_places.json", refresh, fetch)
    for p in places:
        if "missing" in p:
            notes.append(f"GNIS: {p['name']} matched {p['missing']} features, left out")
    return [p for p in places if "missing" not in p]


# ---------------------------------------------------------------------------
# 3. THE BURN RECORD: cells x years
# ---------------------------------------------------------------------------

@dataclass
class Cell:
    lon: float
    lat: float
    burns: list[tuple[int, int]] = field(default_factory=list)   # (year, fire index)


def burn_cells(fires: list[dict], county: list[list], window: bm.BBox
               ) -> tuple[list[Cell], float, float]:
    lat_c = (window.lat_min + window.lat_max) / 2
    dlat = CELL_KM / 110.574
    dlon = CELL_KM / (111.320 * math.cos(math.radians(lat_c)))
    lons = np.arange(window.lon_min + dlon / 2, window.lon_max, dlon)
    lats = np.arange(window.lat_min + dlat / 2, window.lat_max, dlat)
    CX, CY = np.meshgrid(lons, lats)
    cx, cy = CX.ravel(), CY.ravel()
    in_county = np.zeros(cx.shape, dtype=bool)
    for ring in county:
        in_county |= points_in_ring(cx, cy, ring)
    idx = np.flatnonzero(in_county)
    cx, cy = cx[idx], cy[idx]
    offs = (np.arange(SUBSAMPLES) + 0.5) / SUBSAMPLES - 0.5
    ox, oy = np.meshgrid(offs * dlon, offs * dlat)
    ox, oy = ox.ravel(), oy.ravel()                     # (S,)
    cells = [Cell(float(a), float(b)) for a, b in zip(cx, cy)]

    by_year: dict[int, list[int]] = defaultdict(list)
    for i, f in enumerate(fires):
        by_year[f["year"]].append(i)
    need = math.ceil(BURN_FRACTION * SUBSAMPLES * SUBSAMPLES)
    for year in sorted(by_year):
        union = {}                                         # cell -> (S,) bool
        per_fire = {}                                      # cell -> {fire: count}
        for fi in by_year[year]:
            f = fires[fi]
            allv = np.array([q for poly in f["polys"] for q in poly[0]])
            mn, mx = allv.min(axis=0), allv.max(axis=0)
            sel = np.flatnonzero((cx >= mn[0] - dlon) & (cx <= mx[0] + dlon)
                                 & (cy >= mn[1] - dlat) & (cy <= mx[1] + dlat))
            if not len(sel):
                continue
            px = (cx[sel][:, None] + ox[None, :]).ravel()
            py = (cy[sel][:, None] + oy[None, :]).ravel()
            hit = np.zeros(px.shape, dtype=bool)
            for poly in f["polys"]:
                h = points_in_ring(px, py, poly[0])
                for hole in poly[1:]:
                    h &= ~points_in_ring(px, py, hole)
                hit |= h
            hit = hit.reshape(len(sel), -1)
            for row, c in enumerate(sel):
                if hit[row].any():
                    union[c] = union.get(c, np.zeros(len(ox), bool)) | hit[row]
                    per_fire.setdefault(c, {})[fi] = int(hit[row].sum())
        for c, u in union.items():
            if u.sum() >= need:
                best = max(per_fire[c].items(), key=lambda kv: (kv[1], -kv[0]))[0]
                cells[c].burns.append((year, best))
    return cells, dlon, dlat


# ---------------------------------------------------------------------------
# 4. BASEMAP
# ---------------------------------------------------------------------------

def fetch_basemap(want: bm.BBox, out_path: Path, county: list[list]) -> bm.BBox:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
    plan = bm.plan_basemap(want, provider_key="opentopomap", target_px=2048, tile_cap=90)
    print(f"  basemap: {plan.provider.label}, zoom {plan.zoom}, {plan.tile_count} tiles "
          f"-> {plan.out_w}x{plan.out_h}px")
    bm.build_basemap(plan, out_path)
    img = Image.open(out_path).convert("RGB")
    w, h = img.size
    b = plan.bbox

    def tone(src, grey, bright):
        return ImageEnhance.Brightness(
            Image.blend(src, src.convert("L").convert("RGB"), grey)).enhance(bright)

    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    for ring in county:
        draw.polygon([((lon - b.lon_min) / (b.lon_max - b.lon_min) * w,
                       (b.lat_max - lat) / (b.lat_max - b.lat_min) * h) for lon, lat in ring],
                     fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(2.0))
    Image.composite(tone(img, MAP_INSIDE_GREY, MAP_INSIDE_BRIGHT),
                    tone(img, MAP_OUTSIDE_GREY, MAP_OUTSIDE_BRIGHT), mask).save(out_path)
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


def build(layout: fm.Layout, lattice: tr.Lattice, dem: tr.Dem, map_path: Path | None,
          county: list[list], fires: list[dict], cells: list[Cell], dlon: float, dlat: float,
          places: list[dict], notes: list[str]) -> Built:
    R = pu.Rows([])
    ch = pu.Channels(N)
    b = layout.bbox
    hw, hh = layout.half_w, layout.half_h
    zpm = layout.z_per_m
    checks: dict = {"tiles": [], "perims": [], "places": []}

    def add(**kw) -> int:
        return R.add(type=NODE_GLYPH, parent_id=0, branch_level=0, **kw)

    def label(x, y, z, text, pinned=1, **kw) -> int:
        return add(geometry=GEO_CUBE, scale_x=0.0, scale_y=0.0, scale_z=0.0,
                   translate_x=fm._r(x), translate_y=fm._r(y), translate_z=fm._r(z),
                   show_text=pinned, text=text, **kw)

    R.add(type=NODE_WORLD, parent_id=0, branch_level=0, geometry=0,
          color_r=BG_COLOR[0], color_g=BG_COLOR[1], color_b=BG_COLOR[2],
          tag_color_mode=1, tag_color_r=TAG_COLOR[0], tag_color_g=TAG_COLOR[1],
          tag_color_b=TAG_COLOR[2], tag_font_size=12,
          text="San Diego River Watershed Atlas · The Burn Record · San Diego County wildfires 1910–2025")
    grid = R.add(type=NODE_GRID, parent_id=0, branch_level=0, geometry=GEO_CUBE_WIRE,
                 scale_x=layout.sx, scale_y=layout.sy, scale_z=fm._r(layout.grid_scale_z, 5),
                 trigger_lo_x=fm._r(b.lon_min, 6), trigger_hi_x=fm._r(b.lon_max, 6),
                 trigger_lo_y=fm._r(b.lat_min, 6), trigger_hi_y=fm._r(b.lat_max, 6),
                 segments_x=8, segments_y=5, color_r=70, color_g=78, color_b=84, color_a=90,
                 text=(f"San Diego County · lon {b.lon_min:.2f}..{b.lon_max:.2f}, "
                       f"lat {b.lat_min:.2f}..{b.lat_max:.2f}"))

    # -- Terrain ------------------------------------------------------------------
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
            c = (40 + 80 * t, 44 + 76 * t, 40 + 60 * t)
            R.add(type=NODE_GLYPH, parent_id=terrain, branch_level=1, geometry=GEO_CUBE,
                  scale_x=0.0, scale_y=0.0, scale_z=0.0, translate_x=fm._r(WX[j, i]),
                  translate_y=fm._r(WY[j, i]), translate_z=fm._r(WZ[j, i]),
                  color_r=int(c[0]), color_g=int(c[1]), color_b=int(c[2]))

    # -- Year channels: one per year for its tiles, one for its perimeters ----------
    burn_years = sorted({y for c in cells for y, _ in c.burns})
    tile_ch = {}
    for y in burn_years:
        cols = [tile_color_at(y, k) for k in range(N)]
        tile_ch[y] = ch.channel(hide=[0 if c else 1 for c in cols],
                                color_r=[(c or (0, 0, 0))[0] for c in cols],
                                color_g=[(c or (0, 0, 0))[1] for c in cols],
                                color_b=[(c or (0, 0, 0))[2] for c in cols])
    fire_years = sorted({f["year"] for f in fires})
    perim_ch = {y: ch.channel(hide=[0 if 0 <= k - year_frame(y) < PERIM_FRAMES else 1
                                    for k in range(N)]) for y in fire_years}
    rest = N - 1

    # -- Tiles ------------------------------------------------------------------------
    half = CELL_KM / 110.574 * layout.sy * TILE_FILL / 2.0
    tile_s = fm._r(half / CUBE_HALF, 4)
    tile_sz = fm._r(TILE_THICK / 2.0 / CUBE_HALF, 4)
    offs = np.array([-0.5, 0.0, 0.5])
    n_tiles = 0
    tallest = max(cells, key=lambda c: len(c.burns))
    for c in cells:
        if not c.burns:
            continue
        fx = (c.lon + offs[:, None] * dlon * TILE_FILL + 0 * offs[None, :]).ravel()
        fy = (c.lat + 0 * offs[:, None] + offs[None, :] * dlat * TILE_FILL).ravel()
        ground = float(np.max(lattice.surface_height(fx, fy))) * zpm
        x, y = layout.world_xy(c.lon, c.lat)
        years = [yy for yy, _ in c.burns]
        where = f"{c.lat:.3f}° N {abs(c.lon):.3f}° W"
        record = (f"this {CELL_KM:g} km cell ({where}) has burned "
                  f"{'once' if len(years) == 1 else f'{len(years)} times'}"
                  + (f": {', '.join(map(str, years))}" if len(years) > 1 else ""))
        for k, (yy, fi) in enumerate(c.burns):
            f = fires[fi]
            z = ground + TILE_CLEARANCE + k * TILE_STEP + TILE_THICK / 2.0
            col = era_color(yy)
            cause = CAUSE_NAMES.get(f["cause"], "not recorded")
            nid = add(geometry=GEO_CUBE, translate_x=fm._r(x), translate_y=fm._r(y),
                      translate_z=fm._r(z), scale_x=tile_s, scale_y=tile_s, scale_z=tile_sz,
                      color_r=col[0], color_g=col[1], color_b=col[2],
                      ch_input_id=tile_ch[yy],
                      text=(f"{title(f['name'])} · {yy} · {f['acres']:,.0f} acres mapped · "
                            f"cause: {cause} · {record}"))
            checks["tiles"].append((nid, c, k, yy, ground))
            n_tiles += 1
    notes.append(f"cells: {len(cells):,} inside the county, {sum(1 for c in cells if c.burns):,} "
                 f"burned at least once, {n_tiles:,} tiles; tallest stack {len(tallest.burns)} at "
                 f"{tallest.lat:.3f}N {tallest.lon:.3f}W ({', '.join(str(y) for y, _ in tallest.burns)})")
    hist = Counter(len(c.burns) for c in cells)
    notes.append("cells by times burned: " + ", ".join(f"{k}x {hist[k]:,}" for k in sorted(hist)))

    # -- Perimeters: a burning outline for a year and a half, then gone ------------------
    clear_m = PERIM_CLEARANCE / zpm
    n_verts = 0
    for f in fires:
        cause = CAUSE_NAMES.get(f["cause"], "not recorded")
        head = (f"{title(f['name'])} · {f['year']}"
                + (f" · alarm {f['alarm']}" if f["alarm"] else "")
                + f" · {f['acres']:,.0f} acres mapped · cause: {cause} (FRAP code {f['cause']})"
                + f" · unit {f['unit']}")
        for p_i, poly in enumerate(f["polys"]):
            ring = poly[0]
            lo, la = tr.simplify_polyline([q[0] for q in ring], [q[1] for q in ring],
                                          PERIM_SIMPLIFY_M)
            if len(lo) < 4:
                continue
            dl, dt_, dh = tr.drape_polyline(lattice, lo, la, clearance=clear_m)
            wx, wy = layout.world_xy(dl, dt_)
            wz = dh * zpm
            width = 0.07 + 0.05 * min(1.0, math.log10(max(f["acres"], 10.0)) / 5.0)
            par = add(geometry=GEO_POINT, topo=TOPO_PLOT, ratio=fm._r(width, 3),
                      color_r=PERIM_COLOR[0], color_g=PERIM_COLOR[1], color_b=PERIM_COLOR[2],
                      color_a=0, translate_x=fm._r(wx[0]), translate_y=fm._r(wy[0]),
                      translate_z=fm._r(wz[0]), hide=0 if 0 <= rest - year_frame(f["year"]) < PERIM_FRAMES else 1,
                      ch_input_id=perim_ch[f["year"]],
                      text=head if p_i == 0 else f"{title(f['name'])} · {f['year']} · outlying part")
            for n in range(len(dl)):
                R.add(type=NODE_GLYPH, parent_id=par, branch_level=1, geometry=GEO_CUBE,
                      scale_x=0.0, scale_y=0.0, scale_z=0.0,
                      translate_x=fm._r(wx[n] - wx[0]), translate_y=fm._r(wy[n] - wy[0]),
                      translate_z=fm._r(wz[n] - wz[0]),
                      color_r=PERIM_COLOR[0], color_g=PERIM_COLOR[1], color_b=PERIM_COLOR[2])
            checks["perims"].append((par, f["year"]))
            n_verts += len(dl)
    notes.append(f"perimeters: {len(fires):,} fires, {len(checks['perims']):,} outline parts, "
                 f"{n_verts:,} draped vertices")

    # -- The Atlas's own watershed, for orientation within the series --------------
    outer, _inner, area_km2 = wd.dissolve(wd.fetch_huc10())
    divide = max(outer, key=len)
    lo, la = tr.simplify_polyline([q[0] for q in divide], [q[1] for q in divide], 60.0)
    dl, dt_, dh = tr.drape_polyline(lattice, lo, la, clearance=DIVIDE_CLEARANCE / zpm)
    wx, wy = layout.world_xy(dl, dt_)
    wz = dh * zpm
    par = add(geometry=GEO_POINT, topo=TOPO_PLOT, ratio=DIVIDE_STYLE[0],
              color_r=DIVIDE_STYLE[1][0], color_g=DIVIDE_STYLE[1][1], color_b=DIVIDE_STYLE[1][2],
              color_a=0, translate_x=fm._r(wx[0]), translate_y=fm._r(wy[0]),
              translate_z=fm._r(wz[0]),
              text=(f"San Diego River watershed divide · {area_km2:,.0f} km² · the Watershed "
                    f"Atlas's home basin"))
    for n in range(len(dl)):
        R.add(type=NODE_GLYPH, parent_id=par, branch_level=1, geometry=GEO_CUBE,
              scale_x=0.0, scale_y=0.0, scale_z=0.0, translate_x=fm._r(wx[n] - wx[0]),
              translate_y=fm._r(wy[n] - wy[0]), translate_z=fm._r(wz[n] - wz[0]),
              color_r=DIVIDE_STYLE[1][0], color_g=DIVIDE_STYLE[1][1], color_b=DIVIDE_STYLE[1][2])
    notes.append(f"watershed divide: {len(dl)} draped vertices")

    # -- Places --------------------------------------------------------------------
    for p in places:
        km = lattice.surface_height(p["lon"], p["lat"]) / 1000.0
        nid = R.add(type=NODE_GLYPH, parent_id=grid, branch_level=1, geometry=GEO_OCTA,
                    translate_x=fm._r(p["lon"], 6), translate_y=fm._r(p["lat"], 6),
                    translate_z=fm._r(km + 1.2 / layout.grid_scale_z, 6),
                    scale_x=0.9, scale_y=0.9, scale_z=0.9, color_r=235, color_g=235, color_b=225,
                    show_text=1, text=p["name"])
        checks["places"].append((nid, p["lon"], p["lat"]))

    # -- The ledger: acres per year by cause, behind the north edge ----------------
    # North, not south: the opening view looks in from the south, where a
    # ledger stands between the camera and the county; behind it, it reads as
    # a skyline over the map.
    acres = {y: [0.0, 0.0, 0.0] for y in YEARS}
    counts = {y: 0 for y in YEARS}
    for f in fires:
        acres[f["year"]][cause_group(f["cause"])] += f["acres"]
        counts[f["year"]] += 1
    top_year = max(YEARS, key=lambda y: sum(acres[y]))
    top = sum(acres[top_year])
    per_acre = STRIP_H / top
    sy_ = hh + STRIP_GAP
    slot = 2.0 * hw / len(YEARS)
    bar_half = slot * STRIP_BAR_FILL / 2.0

    def year_x(y: float) -> float:
        return -hw + (y - FIRST_YEAR + 0.5) * slot

    for y in YEARS:
        z = 0.0
        for gi, (gname, _codes, gcol) in enumerate(CAUSE_GROUPS):
            a = acres[y][gi]
            if a <= 0:
                continue
            hgt = a * per_acre
            add(geometry=GEO_CUBE, translate_x=fm._r(year_x(y)), translate_y=fm._r(sy_),
                translate_z=fm._r(z + hgt / 2.0), scale_x=fm._r(bar_half / CUBE_HALF, 4),
                scale_y=fm._r(bar_half / CUBE_HALF, 4), scale_z=fm._r(hgt / 2.0 / CUBE_HALF, 4),
                color_r=gcol[0], color_g=gcol[1], color_b=gcol[2],
                text=f"{y} · {a:,.0f} acres mapped · cause {gname} · {counts[y]} perimeters that year")
            z += hgt
    tick = 100_000
    for a in range(tick, int(top) + 1, tick):
        z = a * per_acre
        pts = [(-hw, sy_, z), (hw, sy_, z)]
        par = add(geometry=GEO_POINT, topo=TOPO_PLOT, ratio=0.03, color_r=90, color_g=96,
                  color_b=100, color_a=0, translate_x=fm._r(-hw), translate_y=fm._r(sy_),
                  translate_z=fm._r(z), text=f"{a:,} acres")
        for (px_, py_, pz_) in pts:
            R.add(type=NODE_GLYPH, parent_id=par, branch_level=1, geometry=GEO_CUBE,
                  scale_x=0.0, scale_y=0.0, scale_z=0.0, translate_x=fm._r(px_ + hw),
                  translate_y=0.0, translate_z=0.0, color_r=90, color_g=96, color_b=100)
        label(hw + 4.0, sy_, z, f"{a // 1000:,}k acres")
    for y in range(FIRST_YEAR, LAST_YEAR + 1, 10):
        label(year_x(y) - slot / 2, sy_ - 1.0, -5.0, str(y))
    label(-hw, sy_, STRIP_H + 14.0, "Acres mapped each year, by recorded cause")

    # Cursor: a bead under the ledger riding translate_x, with the year and that
    # year's acres as children (two banks, one label of each on per frame).
    cursor_x = [fm._r(year_x(YEARS[k // FPY] + (k % FPY) / FPY)) for k in range(N)]
    cur_scale = 1.4
    cursor = add(geometry=GEO_OCTA, translate_x=cursor_x[rest], translate_y=fm._r(sy_ - 1.5),
                 translate_z=fm._r(STRIP_H + 4.0), scale_x=cur_scale, scale_y=cur_scale,
                 scale_z=cur_scale, color_r=255, color_g=236, color_b=150,
                 ch_input_id=ch.channel(translate_x=cursor_x), text="Now")
    stem = add(geometry=GEO_POINT, topo=TOPO_PLOT, ratio=0.06, color_r=255, color_g=236,
               color_b=150, color_a=0, translate_x=cursor_x[rest], translate_y=fm._r(sy_ - 0.8),
               translate_z=0.0, ch_input_id=ch.channel(translate_x=cursor_x), text="Now")
    for zz in (0.0, STRIP_H + 2.0):
        R.add(type=NODE_GLYPH, parent_id=stem, branch_level=1, geometry=GEO_CUBE,
              scale_x=0.0, scale_y=0.0, scale_z=0.0, translate_z=fm._r(zz),
              color_r=255, color_g=236, color_b=150)
    checks["cursor"] = (cursor, cursor_x)
    checks["readout"] = {}
    for y in YEARS:
        on = [1 if YEARS[k // FPY] == y else 0 for k in range(N)]
        nid = R.add(type=NODE_GLYPH, parent_id=cursor, branch_level=1, geometry=GEO_CUBE,
                    scale_x=0.0, scale_y=0.0, scale_z=0.0, translate_z=fm._r(6.0 / cur_scale, 4),
                    show_text=on[rest], ch_input_id=ch.channel(show_text=on),
                    text=f"{y} · {sum(acres[y]):,.0f} acres · {counts[y]} fires")
        checks["readout"][y] = nid
    # The year again at the head of the legend, over the Pacific, where it can
    # be read from the opening view without finding the cursor.
    checks["big_year"] = {}
    for y in YEARS:
        on = [1 if YEARS[k // FPY] == y else 0 for k in range(N)]
        checks["big_year"][y] = label(-hw - 40.0, -hh * 0.15, 100.0, f"Now: {y}", pinned=on[rest],
                                      ch_input_id=ch.channel(show_text=on))
    notes.append(f"ledger: tallest year {top_year} ({top:,.0f} acres); resting pose frame {rest} "
                 f"({YEARS[rest // FPY]})")

    # -- Legend, over the Pacific off the west edge -------------------------------------
    lx, ly = -hw - 40.0, -hh * 0.15
    z = 84.0

    def step(n=1.0):
        nonlocal z
        z -= 10.0 * n

    label(lx, ly, z, "One tile = one year this ground burned")
    step(0.8)
    label(lx, ly, z, f"(half or more of a {CELL_KM:g} km cell inside that year's perimeters)")
    step(1.4)
    for first, last, col in reversed(ERAS):
        add(geometry=GEO_CUBE, translate_x=fm._r(lx), translate_y=fm._r(ly), translate_z=fm._r(z),
            scale_x=tile_s, scale_y=tile_s, scale_z=tile_sz, color_r=col[0], color_g=col[1],
            color_b=col[2], show_text=1, text=f"{first}–{last}")
        step()
    step(0.3)
    label(lx, ly, z, "New tiles land white-hot and cool to their era")
    step()
    label(lx, ly, z, "Orange outline = that year's perimeters, burning")
    step()
    label(lx, ly, z, f"Relief {TERRAIN_EXAG:g}x exaggerated · CAL FIRE FRAP perimeters")
    step(1.6)
    label(lx, ly, z, "Ledger bars, by recorded cause:")
    for gname, _codes, gcol in CAUSE_GROUPS:
        step()
        add(geometry=GEO_CUBE, translate_x=fm._r(lx), translate_y=fm._r(ly), translate_z=fm._r(z),
            scale_x=1.2, scale_y=1.2, scale_z=1.2, color_r=gcol[0], color_g=gcol[1],
            color_b=gcol[2], show_text=1, text=gname)

    ch_map, ch_tracks = ch.frames()
    checks.update(rest=rest, acres=acres, year_x=year_x)
    return Built(R.frame(), ch_map, ch_tracks, notes, checks)


# ---------------------------------------------------------------------------
# 6. VERIFICATION
# ---------------------------------------------------------------------------

def independent_burn_years(c: Cell, fires_by_year: dict, dlon: float, dlat: float) -> list[int]:
    """The same rule, recomputed a second way: pure-Python ray casting
    (watershed_data.point_in_rings) over every perimeter, cell by cell."""
    offs = [(i + 0.5) / SUBSAMPLES - 0.5 for i in range(SUBSAMPLES)]
    pts = [(c.lon + a * dlon, c.lat + b * dlat) for a in offs for b in offs]
    need = math.ceil(BURN_FRACTION * len(pts))
    out = []
    for year, fs in sorted(fires_by_year.items()):
        hit = 0
        for (px, py) in pts:
            for f in fs:
                if any(wd.point_in_rings(px, py, [poly[0]]) and
                       not any(wd.point_in_rings(px, py, [h]) for h in poly[1:])
                       for poly in f["polys"]):
                    hit += 1
                    break
        if hit >= need:
            out.append(year)
    return out


def verify(node_path: Path, map_path: Path, tracks_path: Path, built: Built,
           layout: fm.Layout, lattice: tr.Lattice, fires: list[dict], dlon: float,
           dlat: float) -> list[str]:
    from glyphviz_core.channel_engine import ChannelEngine
    from glyphviz_core.channel_loader import load_ch_map, load_ch_tracks
    from glyphviz_core.csv_reader import load_node_csv
    from glyphviz_core.scene import Scene

    rep = []
    nodes = load_node_csv(str(node_path))
    by_id = {n.id: n for n in nodes}
    scene = Scene(nodes)
    zpm = layout.z_per_m

    worst_xy = worst_z = 0.0
    buried = 0
    for nid, c, k, _y, ground in built.checks["tiles"]:
        wp = scene.world_pos(nid)
        ex, ey = layout.world_xy(c.lon, c.lat)
        worst_xy = max(worst_xy, abs(wp[0] - ex), abs(wp[1] - ey))
        want = ground + TILE_CLEARANCE + k * TILE_STEP + TILE_THICK / 2.0
        worst_z = max(worst_z, abs(wp[2] - want))
        bottom = wp[2] - by_id[nid].scale_z * CUBE_HALF
        h = lattice.surface_height(c.lon, c.lat) * zpm
        if bottom < h - 1e-3:
            buried += 1
    worst_pl = max(max(abs(scene.world_pos(nid)[0] - layout.world_xy(lo, la)[0]),
                       abs(scene.world_pos(nid)[1] - layout.world_xy(lo, la)[1]))
                   for nid, lo, la in built.checks["places"]) if built.checks["places"] else 0.0
    rep.append(f"tiles: {len(built.checks['tiles']):,}, xy error {worst_xy:.5f}, stacking error "
               f"{worst_z:.4f}, bottoms below the surface at the cell centre {buried}; "
               f"places xy error {worst_pl:.5f}")

    # Independent recount of the burn rule on a sample of cells.
    by_year = defaultdict(list)
    for f in fires:
        by_year[f["year"]].append(f)
    cells = {}
    for _nid, c, _k, _y, _g in built.checks["tiles"]:
        cells[id(c)] = c
    sample = sorted(cells.values(), key=lambda c: (-len(c.burns), c.lon, c.lat))[:25]
    rng = np.random.default_rng(7)
    rest_cells = [c for c in cells.values() if c not in sample]
    sample += [rest_cells[i] for i in rng.choice(len(rest_cells), 25, replace=False)]
    mism = 0
    for c in sample:
        near = {y: [f for f in fs if any(
            min(q[0] for q in poly[0]) - dlon <= c.lon <= max(q[0] for q in poly[0]) + dlon and
            min(q[1] for q in poly[0]) - dlat <= c.lat <= max(q[1] for q in poly[0]) + dlat
            for poly in f["polys"])] for y, fs in by_year.items()}
        near = {y: fs for y, fs in near.items() if fs}
        if independent_burn_years(c, near, dlon, dlat) != [y for y, _ in c.burns]:
            mism += 1
    rep.append(f"independent recount (pure-Python ray casting) on {len(sample)} cells, "
               f"the 25 tallest + 25 random: mismatches {mism}")

    eng = ChannelEngine()
    tracks, id_to_col = load_ch_tracks(str(tracks_path))
    eng.load(load_ch_map(str(map_path)), tracks, id_to_col, nodes)
    wrong_tile = wrong_col = wrong_perim = wrong_read = 0
    worst_cur = 0.0
    frames = sorted({0, year_frame(1970), year_frame(2003) + 1, year_frame(2007) + 5, N - 1})
    cur_id, cur_x = built.checks["cursor"]
    for k in frames:
        eng.apply_frame(k)
        year_now = YEARS[k // FPY]
        for nid, _c, _k, y, _g in built.checks["tiles"]:
            nd = by_id[nid]
            want = tile_color_at(y, k)
            if bool(nd.hide) != (want is None):
                wrong_tile += 1
            elif want is not None and (nd.color_r, nd.color_g, nd.color_b) != want:
                wrong_col += 1
        for nid, y in built.checks["perims"]:
            if bool(by_id[nid].hide) != (not 0 <= k - year_frame(y) < PERIM_FRAMES):
                wrong_perim += 1
        on = [y for y, nid in built.checks["readout"].items() if by_id[nid].show_text]
        big = [y for y, nid in built.checks["big_year"].items() if by_id[nid].show_text]
        if on != [year_now] or big != [year_now]:
            wrong_read += 1
        worst_cur = max(worst_cur, abs(Scene(nodes).world_pos(cur_id)[0] - cur_x[k]))
    eng.reset()
    rep.append(f"playback at {len(frames)} frames: wrong tile visibility {wrong_tile}, wrong tile "
               f"colour {wrong_col}, wrong perimeter visibility {wrong_perim}, wrong readout "
               f"{wrong_read}, cursor error {worst_cur:.4f}; engine {eng.frame_count} frames, "
               f"{len(eng.bound_node_ids):,} bound nodes")
    return rep


# ---------------------------------------------------------------------------
# 7. MAIN
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", type=Path, default=HERE / SCENE_DIR,
                    help=f"where the scene is written (default {SCENE_DIR}/ beside this script)")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--no-basemap", action="store_true")
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--no-zip", action="store_true",
                    help=f"skip writing {SCENE_DIR}.zip beside the scene folder")
    args = ap.parse_args()
    notes: list[str] = []

    print("Public data (cached under data/):")
    county = fetch_county(args.refresh)
    fires = fetch_fires(args.refresh, county, notes)
    places = fetch_places(args.refresh, notes)
    print(f"  {len(fires):,} perimeters {FIRST_YEAR}-{LAST_YEAR}")

    lon = [p[0] for ring in county for p in ring]
    lat = [p[1] for ring in county for p in ring]
    window = bm.BBox(min(lon) - MAP_PAD_DEG, max(lon) + MAP_PAD_DEG,
                     min(lat) - MAP_PAD_DEG, max(lat) + MAP_PAD_DEG)
    map_path = None
    if not args.no_basemap:
        (args.out_dir / "media").mkdir(parents=True, exist_ok=True)
        map_path = args.out_dir / "media" / "01_county_relief.png"
        window = fetch_basemap(window, map_path, county)
    sy = PLATE_HEIGHT / (window.lat_max - window.lat_min)
    sx = sy * math.cos(math.radians((window.lat_min + window.lat_max) / 2.0))
    layout = fm.Layout(window, round(sx, 4), round(sy, 4), TERRAIN_EXAG)
    print(f"  DEM zoom {DEM_ZOOM} …")
    dem = tr.fetch_dem(window, zoom=DEM_ZOOM)
    lattice = tr.build_lattice(dem, window, cols=SURFACE_COLS)
    print(f"  lattice {lattice.cols}x{lattice.rows}")

    t0 = time.time()
    cells, dlon, dlat = burn_cells(fires, county, window)
    print(f"  burn record: {time.time() - t0:.1f} s")

    built = build(layout, lattice, dem, map_path, county, fires, cells, dlon, dlat, places, notes)
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
    if not args.no_verify:
        print("\nVerification (real loader, Scene, ChannelEngine):")
        for line in verify(node_path, map_csv, tracks_csv, built, layout, lattice, fires, dlon, dlat):
            print(f"  {line}")
    if not args.no_zip:
        zpath = write_scene_zip(args.out_dir)
        print(f"\nZipped {zpath.name}: {zpath.stat().st_size / 1e6:.1f} MB")
    return 0


def write_scene_zip(scene_dir: Path) -> Path:
    """<scene>.zip beside the scene folder, holding the folder itself — the
    form the repo ships (the folder is gitignored) and that GlyphViz extracts
    beside itself when the zip is dropped on the window."""
    import zipfile
    zpath = scene_dir.parent / f"{scene_dir.name}.zip"
    files = sorted(p for p in scene_dir.rglob("*") if p.is_file())
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files:
            z.write(p, (Path(scene_dir.name) / p.relative_to(scene_dir)).as_posix())
    return zpath


if __name__ == "__main__":
    raise SystemExit(main())
