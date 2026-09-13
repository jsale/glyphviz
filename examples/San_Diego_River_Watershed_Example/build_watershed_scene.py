#!/usr/bin/env python3
"""
build_watershed_scene.py — the San Diego River watershed, source to sea
======================================================================

Phase 1 of the San Diego River Watershed Atlas: "The Frame". No time axis yet.
This scene exists to establish that the place is legible and that you can fly
it — every later phase (the century of rain and flow, the fires, the footage)
is laid over this frame.

WHAT IS IN IT
-------------
  * The watershed's own relief: a 300-column TOPO_SURFACE built from USGS 3DEP
    elevation (via AWS Terrain Tiles), draped with an OpenTopoMap basemap that
    is dimmed OUTSIDE the watershed divide, so the basin reads as a shape.
  * The divide itself, and the internal divides between its three HUC-10
    sub-basins, draped onto the terrain as lines.
  * The whole NHDPlus river network upstream of the mouth — 267 runs of
    constant Strahler order, width and colour by order, so you can watch the
    river grow as tributaries join it. The mainstem is brighter.
  * El Capitan and San Vicente reservoirs as shoreline outlines.
  * The three USGS stream gauges and four long-record NOAA rain stations at
    their true coordinates, and a dozen named places, all verified against
    federal gazetteers rather than typed in.

Data: see watershed_data.py (all public, keyless, cached under data/).
Terrain: glyphviz_core/terrain.py — and read its docstring before touching
the draping, because a line sampled from the DEM is BURIED under this surface.

HOW THE SCENE IS BUILT
----------------------
Two frames that share one mapping from lon/lat to world units:

  * A World Grid (wire, dim) whose extents are exactly the basemap window.
    Point features — gauges, rain stations, places — are its children at
    translate_x = lon, translate_y = lat, translate_z = km, and the grid's
    scale_z is the vertical exaggeration.
  * Root-level TOPO_SURFACE and TOPO_PLOT parents whose children sit at
    literal world coordinates (Plot and Surface are Cartesian, and a grid
    would re-space their vertices). world_xy() reproduces the grid's own
    mapping so both frames coincide — verified in verify_scene().

Every point feature stands on the RENDERED surface (terrain.Lattice.
surface_height), not on the DEM or on its gazetteer elevation, and every line
is draped the same way with a fixed clearance in world units.

USAGE
-----
    python build_watershed_scene.py                  # build (uses cached data)
    python build_watershed_scene.py --refresh        # re-download public data
    python build_watershed_scene.py --home LON,LAT   # add a "you are here" —
                                                     # never commit that build
"""

from __future__ import annotations

import argparse
import math
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

import watershed_data as wd                                         # noqa: E402
from glyphviz_core import basemap as bm                             # noqa: E402
from glyphviz_core import terrain as tr                             # noqa: E402

# ---------------------------------------------------------------------------
# 1. CONFIGURATION
# ---------------------------------------------------------------------------

OUT_STEM = "sd_river_watershed"
PAD_FRAC = 0.04                      # map window beyond the divide's bbox

PLATE_HEIGHT = 260.0                 # world units north-south
TERRAIN_EXAG = 5.0                   # vertical exaggeration
SURFACE_COLS = 300                   # Jeff's call after the budget prototype
DEM_ZOOM = 12                        # ~32 m/px; ~7 DEM px per lattice column

BASEMAP_PROVIDER = "opentopomap"
BASEMAP_TARGET_PX = 2048
BASEMAP_TILE_CAP = 80
# The map is toned at build time, differently inside and outside the divide:
# the watershed stays close to full colour, everything beyond it goes dark and
# grey, so the basin's shape is legible before a single line is drawn. Baked
# into the PNG — GlyphViz has no filled polygons, and a baked mask has no
# blending or depth-order behaviour to go wrong.
MAP_INSIDE_GREY, MAP_INSIDE_BRIGHT = 0.15, 0.78
MAP_OUTSIDE_GREY, MAP_OUTSIDE_BRIGHT = 0.90, 0.26

LINE_CLEARANCE = 0.8                 # world units above the rendered surface
# Source lines are simplified before draping. NHDPlus carries a vertex every
# ~50 m and the WBD divide is denser; at this lattice (~213 m) 20 m is
# sub-pixel from any overview, and every dropped vertex is a node saved.
SIMPLIFY_M = 20.0
POINT_CLEARANCE = 0.0                # point glyphs sit ON the surface

# Strahler order -> (line width ratio, colour). ratio * 20 = pixels.
ORDER_STYLE = {
    1: (0.05, (120, 170, 205)),
    2: (0.07, (100, 175, 225)),
    3: (0.10, (80, 180, 240)),
    4: (0.14, (60, 190, 250)),
    5: (0.20, (40, 205, 255)),
}
MAINSTEM_BOOST = (1.25, (150, 230, 255))   # width factor, colour
DIVIDE_STYLE = (0.12, (240, 196, 110))
SUBDIVIDE_STYLE = (0.05, (190, 160, 110))
SHORELINE_STYLE = (0.09, (170, 235, 245))

BG_COLOR = (14, 18, 22, 255)
TAG_COLOR = (236, 240, 236)
TAG_FONT_SIZE = 12

GEO_CUBE, GEO_SPHERE, GEO_OCTA, GEO_PIN, GEO_POINT = 1, 3, 11, 16, 22
GEO_CUBE_WIRE = 0
TOPO_PLOT, TOPO_SURFACE = 16, 17
NODE_WORLD, NODE_GLYPH, NODE_GRID = 0, 5, 6

# Labels that are always on. Kept to a handful — every node carries a tag, but
# pinned ones all draw at once.
# Santee, Cowles Mountain and the Mast Rd gauge sit within 5 km of each
# other, and so do Ocean Beach and the mouth; pinning all of them stacked
# five captions on top of each other in the overview. The gauge and mouth
# captions carry the neighbourhood name instead.
PINNED_PLACES = {"Cuyamaca Peak"}


# ---------------------------------------------------------------------------
# 2. LAYOUT — one lon/lat -> world mapping for both frames
# ---------------------------------------------------------------------------

@dataclass
class Layout:
    bbox: bm.BBox
    sx: float                        # world units per degree of longitude
    sy: float                        # world units per degree of latitude
    exag: float

    @property
    def lon_c(self) -> float:
        return (self.bbox.lon_min + self.bbox.lon_max) / 2.0

    @property
    def lat_c(self) -> float:
        return (self.bbox.lat_min + self.bbox.lat_max) / 2.0

    @property
    def half_w(self) -> float:
        return (self.bbox.lon_max - self.bbox.lon_min) / 2.0 * self.sx

    @property
    def half_h(self) -> float:
        return (self.bbox.lat_max - self.bbox.lat_min) / 2.0 * self.sy

    @property
    def z_per_m(self) -> float:
        """World units per metre of elevation, exaggeration included."""
        return self.sy / 111_320.0 * self.exag

    @property
    def grid_scale_z(self) -> float:
        """The grid's scale_z: world units per KILOMETRE of translate_z."""
        return self.z_per_m * 1000.0

    def world_xy(self, lon, lat):
        """Where a grid child at lon/lat lands. The grid recentres its extents
        on the midpoint and scales per axis; Plot and Surface children have to
        reproduce that themselves."""
        return ((np.asarray(lon) - self.lon_c) * self.sx,
                (np.asarray(lat) - self.lat_c) * self.sy)


def make_layout(bbox: bm.BBox) -> Layout:
    sy = PLATE_HEIGHT / (bbox.lat_max - bbox.lat_min)
    sx = sy * math.cos(math.radians((bbox.lat_min + bbox.lat_max) / 2.0))
    return Layout(bbox, round(sx, 4), round(sy, 4), TERRAIN_EXAG)


# ---------------------------------------------------------------------------
# 3. ROWS
# ---------------------------------------------------------------------------

COLUMNS = ["id", "type", "parent_id", "branch_level", "child_id",
           "translate_x", "translate_y", "translate_z",
           "rotate_x", "rotate_y", "rotate_z",
           "scale_x", "scale_y", "scale_z",
           "color_r", "color_g", "color_b", "color_a",
           "geometry", "hide", "topo", "ratio", "texture_id", "show_text",
           "trigger_lo_x", "trigger_hi_x", "trigger_lo_y", "trigger_hi_y",
           "segments_x", "segments_y",
           "tag_color_mode", "tag_color_r", "tag_color_g", "tag_color_b",
           "tag_font_size", "text", "link"]

DEFAULTS = dict(child_id=0, translate_x=0.0, translate_y=0.0, translate_z=0.0,
                rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
                scale_x=1.0, scale_y=1.0, scale_z=1.0,
                color_r=255, color_g=255, color_b=255, color_a=255,
                geometry=GEO_SPHERE, hide=0, topo=0, ratio=0.1, texture_id=0,
                show_text=0, trigger_lo_x=0, trigger_hi_x=0, trigger_lo_y=0,
                trigger_hi_y=0, segments_x=16, segments_y=16,
                tag_color_mode=0, tag_color_r=255, tag_color_g=255,
                tag_color_b=255, tag_font_size=11, text="", link="")


@dataclass
class Rows:
    rows: list[dict] = field(default_factory=list)

    def add(self, **kw) -> int:
        nid = len(self.rows) + 1
        self.rows.append({**DEFAULTS, "id": nid, **kw})
        return nid

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=COLUMNS)


def _r(x: float, nd: int = 3) -> float:
    v = round(float(x), nd)
    return 0.0 if v == 0 else v


# ---------------------------------------------------------------------------
# 4. BASEMAP
# ---------------------------------------------------------------------------

def fetch_basemap(want: bm.BBox, out_path: Path, divide_ring: list) -> bm.BBox:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

    plan = bm.plan_basemap(want, provider_key=BASEMAP_PROVIDER,
                           target_px=BASEMAP_TARGET_PX, tile_cap=BASEMAP_TILE_CAP)
    print(f"  basemap: {plan.provider.label}, zoom {plan.zoom}, "
          f"{plan.tile_count} tiles -> {plan.out_w}x{plan.out_h}px")
    bm.build_basemap(plan, out_path)
    img = Image.open(out_path).convert("RGB")
    w, h = img.size
    b = plan.bbox

    def tone(src, grey, bright):
        out = Image.blend(src, src.convert("L").convert("RGB"), grey)
        return ImageEnhance.Brightness(out).enhance(bright)

    inside = tone(img, MAP_INSIDE_GREY, MAP_INSIDE_BRIGHT)
    outside = tone(img, MAP_OUTSIDE_GREY, MAP_OUTSIDE_BRIGHT)
    mask = Image.new("L", (w, h), 0)
    pts = [((lon - b.lon_min) / (b.lon_max - b.lon_min) * w,
            (b.lat_max - lat) / (b.lat_max - b.lat_min) * h) for lon, lat in divide_ring]
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(2.0))
    Image.composite(inside, outside, mask).save(out_path, format="PNG")
    print(f"  map toned inside/outside the divide -> {out_path.name} "
          f"({out_path.stat().st_size / 1e6:.1f} MB)")
    return plan.bbox


# ---------------------------------------------------------------------------
# 5. SCENE
# ---------------------------------------------------------------------------

@dataclass
class Built:
    df: pd.DataFrame
    notes: list[str]
    checks: dict


def build(layout: Layout, lattice: tr.Lattice, dem: tr.Dem,
          map_path: Path | None, home: tuple[float, float] | None) -> Built:
    R = Rows()
    notes: list[str] = []
    checks: dict = {"points": [], "lines": []}
    clear_m = LINE_CLEARANCE / layout.z_per_m
    b = layout.bbox

    huc = wd.fetch_huc10()
    outer, inner, area_km2 = wd.dissolve(huc)
    divide = max(outer, key=len)
    streams = wd.build_streams(wd.fetch_network())
    mainstem = [s for s in streams if s.mainstem]
    main_km = sum(s.length_km for s in mainstem)
    gauges = wd.fetch_gauges()
    rain = wd.fetch_rain_stations()
    places = wd.fetch_places()
    shores = wd.reservoir_shorelines(wd.fetch_reservoirs())

    def inside(lon, lat) -> bool:
        return wd.point_in_rings(lon, lat, outer)

    def surface_km(lon, lat) -> float:
        return lattice.surface_height(lon, lat) / 1000.0

    # -- World row ----------------------------------------------------------
    R.add(type=NODE_WORLD, parent_id=0, branch_level=0, geometry=0,
          color_r=BG_COLOR[0], color_g=BG_COLOR[1], color_b=BG_COLOR[2],
          color_a=BG_COLOR[3], tag_color_mode=1, tag_color_r=TAG_COLOR[0],
          tag_color_g=TAG_COLOR[1], tag_color_b=TAG_COLOR[2],
          tag_font_size=TAG_FONT_SIZE,
          text="San Diego River Watershed Atlas · Phase 1 · The Frame")

    # -- World Grid: the lon/lat frame for point features -------------------
    grid = R.add(type=NODE_GRID, parent_id=0, branch_level=0,
                 geometry=GEO_CUBE_WIRE,
                 scale_x=layout.sx, scale_y=layout.sy,
                 scale_z=_r(layout.grid_scale_z, 5),
                 trigger_lo_x=_r(b.lon_min, 6), trigger_hi_x=_r(b.lon_max, 6),
                 trigger_lo_y=_r(b.lat_min, 6), trigger_hi_y=_r(b.lat_max, 6),
                 segments_x=8, segments_y=5,
                 color_r=90, color_g=100, color_b=96, color_a=110,
                 text=(f"San Diego River watershed · {area_km2:,.0f} km² "
                       f"({area_km2 / 2.58999:,.0f} sq mi) · "
                       f"lon {b.lon_min:.2f}..{b.lon_max:.2f}, "
                       f"lat {b.lat_min:.2f}..{b.lat_max:.2f}"))

    # -- Terrain ------------------------------------------------------------
    textured = map_path is not None and map_path.is_file()
    tex = None
    if textured:
        from PIL import Image
        tex = np.asarray(Image.open(map_path).convert("RGB"))
    terrain = R.add(type=NODE_GLYPH, parent_id=0, branch_level=0,
                    # color_a MUST stay 255: a textured Surface is drawn
                    # with its parent's alpha, so 0 erases the whole mesh.
                    # (The 2 px point it also draws sits under the terrain.)
                    geometry=GEO_POINT, topo=TOPO_SURFACE, color_a=255,
                    texture_id=1 if textured else 0,
                    text=(f"Terrain · USGS 3DEP via AWS Terrain Tiles · "
                          f"{lattice.cols}x{lattice.rows} lattice, "
                          f"~{(b.lon_max - b.lon_min) / (lattice.cols - 1) * 111.32 * math.cos(math.radians(layout.lat_c)) * 1000:.0f} m spacing · "
                          f"{TERRAIN_EXAG:g}x vertical exaggeration"))
    LON, LAT = np.meshgrid(lattice.lons, lattice.lats)
    WX, WY = layout.world_xy(LON, LAT)
    WZ = lattice.heights * layout.z_per_m
    for j in range(lattice.rows):
        for i in range(lattice.cols):
            if tex is not None:
                u = (lattice.lons[i] - b.lon_min) / (b.lon_max - b.lon_min)
                v = (b.lat_max - lattice.lats[j]) / (b.lat_max - b.lat_min)
                c = tex[min(int(v * (tex.shape[0] - 1)), tex.shape[0] - 1),
                        min(int(u * (tex.shape[1] - 1)), tex.shape[1] - 1)]
            else:
                t = min(lattice.heights[j, i] / 2000.0, 1.0)
                c = (70 + 150 * t, 85 + 130 * t, 70 + 90 * t)
            # Scale 0: the mesh is the picture, and a zero-scale solid glyph is
            # skipped by the renderer outright (viewport._draws_nothing).
            R.add(type=NODE_GLYPH, parent_id=terrain, branch_level=1,
                  geometry=GEO_CUBE, scale_x=0.0, scale_y=0.0, scale_z=0.0,
                  translate_x=_r(WX[j, i]), translate_y=_r(WY[j, i]),
                  translate_z=_r(WZ[j, i]),
                  color_r=int(c[0]), color_g=int(c[1]), color_b=int(c[2]))

    # -- Draped lines -------------------------------------------------------
    def line(coords, width, color, label, link="", per_vertex=None,
             anchor="last") -> int:
        lons, lats = tr.simplify_polyline([p[0] for p in coords],
                                          [p[1] for p in coords], SIMPLIFY_M)
        dl, dt, dh = tr.drape_polyline(lattice, lons, lats, clearance=clear_m)
        wx, wy = layout.world_xy(dl, dt)
        wz = dh * layout.z_per_m
        # The parent is an invisible, clickable handle ON the surface at the
        # line's downstream end (or first point) — clicking it selects the
        # stream and shows its label. It sits below the draped line, so its
        # depth write cannot nick the line.
        k = -1 if anchor == "last" else 0
        ax, ay = float(wx[k]), float(wy[k])
        az = lattice.surface_height(dl[k], dt[k]) * layout.z_per_m
        parent = R.add(type=NODE_GLYPH, parent_id=0, branch_level=0,
                       geometry=GEO_POINT, topo=TOPO_PLOT, ratio=width,
                       color_r=color[0], color_g=color[1], color_b=color[2],
                       color_a=0, translate_x=_r(ax), translate_y=_r(ay),
                       translate_z=_r(az), text=label, link=link)
        for n in range(len(dl)):
            col = per_vertex[n] if per_vertex is not None else color
            R.add(type=NODE_GLYPH, parent_id=parent, branch_level=1,
                  geometry=GEO_CUBE, scale_x=0.0, scale_y=0.0, scale_z=0.0,
                  translate_x=_r(wx[n] - ax), translate_y=_r(wy[n] - ay),
                  translate_z=_r(wz[n] - az),
                  color_r=col[0], color_g=col[1], color_b=col[2])
        checks["lines"].append((parent, dl, dt))
        return len(dl)

    n = line(divide, *DIVIDE_STYLE,
             label=(f"Watershed divide · {area_km2:,.1f} km² "
                    f"({area_km2 / 2.58999:,.1f} sq mi) · USGS WBD HUC-10 "
                    f"{', '.join(wd.HUC10)}"),
             anchor="first")
    notes.append(f"divide: {len(divide)} vertices -> {n} draped")
    for k, sub in enumerate(inner):
        line(sub, *SUBDIVIDE_STYLE,
             label="Sub-basin divide · between the Upper San Diego River, "
                   "San Vicente Creek and Lower San Diego River HUC-10 units")

    n_verts = 0
    for s in sorted(streams, key=lambda s: (s.order, s.mainstem)):
        width, color = ORDER_STYLE[s.order]
        if s.mainstem:
            width *= MAINSTEM_BOOST[0]
            color = MAINSTEM_BOOST[1]
        name = s.name.strip() or "Unnamed tributary"
        if s.mainstem:
            name = "San Diego River (mainstem)"
        label = (f"{name} · Strahler order {s.order} · {s.length_km:.1f} km "
                 f"this reach · drains {s.drainage_km2:,.1f} km² at its "
                 f"downstream end")
        n_verts += line(s.coords, width, color, label,
                        link=f"https://api.water.usgs.gov/nldi/linked-data/"
                             f"comid/{s.comids[-1]}")
    notes.append(f"river network: {len(streams)} runs, {n_verts} draped vertices; "
                 f"mainstem {main_km:.1f} km ({main_km / 1.609344:.1f} mi)")

    for sh in shores:
        common = ("El Capitan Reservoir (NHD: El Capitan Lake)"
                  if sh["name"] == "El Capitan Lake" else sh["name"])
        line(sh["ring"], *SHORELINE_STYLE,
             label=f"{common} · shoreline · {sh['area_km2']:.2f} km² (NHDPlus)",
             anchor="first")

    # -- Point features on the grid ------------------------------------------
    def point(lon, lat, geometry, size, color, label, pinned=False, link="",
              z_extra_world=0.0) -> int:
        km = surface_km(lon, lat) + (POINT_CLEARANCE + z_extra_world) / layout.grid_scale_z
        nid = R.add(type=NODE_GLYPH, parent_id=grid, branch_level=1,
                    geometry=geometry, translate_x=_r(lon, 6),
                    translate_y=_r(lat, 6), translate_z=_r(km, 6),
                    scale_x=size, scale_y=size, scale_z=size,
                    color_r=color[0], color_g=color[1], color_b=color[2],
                    show_text=1 if pinned else 0, text=label, link=link,
                    segments_x=16, segments_y=12)
        checks["points"].append((nid, lon, lat, z_extra_world))
        return nid

    def side(lon, lat) -> str:
        return "" if inside(lon, lat) else " · just outside the divide"

    def feet(lon, lat) -> str:
        # The DEM at the point itself, not the cell-averaged mesh, which
        # understates every summit (Cuyamaca Peak by ~250 ft at 300 columns).
        return f"{dem.sample(lon, lat) * 3.28084:,.0f} ft"

    for g in gauges:
        nm = (g["name"].replace(" R A ", " River at ").replace(" C NR ", " Creek near ")
              .replace(" NR ", " near ").replace(" AT ", " at ").title()
              .replace(" Ca", ", CA"))
        span = {"11022480": "daily discharge since 1912",
                "11023000": "daily discharge since 1982",
                "11022200": "daily discharge since 1983"}[g["site"]]
        pinned = g["site"] == "11022480"
        label = ("Mast Rd gauge · Santee · flow since 1912" if pinned else
                 f"USGS {g['site']} · {nm} · {span} · drains "
                 f"{g['drain_sq_mi']:g} sq mi{side(g['lon'], g['lat'])}")
        point(g["lon"], g["lat"], GEO_PIN, 2.6, (250, 250, 250), label,
              pinned=pinned,
              link=f"https://waterdata.usgs.gov/monitoring-location/{g['site']}/")

    for r_ in rain:
        point(r_["lon"], r_["lat"], GEO_OCTA, 1.6, (190, 170, 250),
              f"NOAA GHCN {r_['ghcn']} · {r_['name']} · {r_['elev_ft']:,.0f} ft · "
              f"daily precipitation {r_['first'][:4]}–{r_['last'][:4]}"
              f"{side(r_['lon'], r_['lat'])}",
              link=f"https://www.ncei.noaa.gov/cdo-web/datasets/GHCND/stations/"
                   f"GHCND:{r_['ghcn']}/detail")

    def in_window(lon, lat) -> bool:
        return b.lon_min <= lon <= b.lon_max and b.lat_min <= lat <= b.lat_max

    for p in places:
        pts = p["points"]
        if p["feature_class"] == "Valley" and len(pts) >= 2:
            # A valley's GNIS points are its mouth and its head; the label
            # belongs in the middle, not at the mouth (which for Mission
            # Valley is the river mouth itself).
            lon, lat = (pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2
        else:
            # A Range carries several points and the primary one can fall
            # off the map: Volcan Mountains' is 3 km north of the window's
            # edge, which left a sphere floating beyond the plate.
            lon, lat = next((q for q in pts if in_window(*q)), pts[0])
        if not in_window(lon, lat):
            notes.append(f"skipped {p['name']}: no GNIS point inside the map window")
            continue
        pinned = p["name"] in PINNED_PLACES
        label = (f"{p['name']} · {feet(lon, lat)}" if pinned else
                 f"{p['name']} · {p['feature_class'].lower()} · {feet(lon, lat)} · "
                 f"GNIS {p['gnis_id']}{side(lon, lat)}")
        point(lon, lat, GEO_SPHERE, 1.1, (255, 226, 170), label, pinned=pinned)

    el_cap = next((s for s in shores if s["name"] == "El Capitan Lake"), None)
    if el_cap:
        ring = np.array(el_cap["ring"])
        point(float(ring[:, 0].mean()), float(ring[:, 1].mean()), GEO_SPHERE, 1.1,
              (255, 226, 170), "El Capitan Reservoir", pinned=True)

    head = mainstem[0].coords[0]
    mouth = mainstem[-1].coords[-1]
    point(head[0], head[1], GEO_SPHERE, 1.4, (150, 230, 255),
          f"River source · {feet(*head)} · {main_km / 1.609344:.0f} mi to the sea",
          pinned=True)
    point(mouth[0], mouth[1], GEO_SPHERE, 1.4, (150, 230, 255),
          "River mouth · Ocean Beach", pinned=True)

    if home is not None:
        point(home[0], home[1], GEO_PIN, 3.2, (255, 120, 90),
              "You are here", pinned=True)
        notes.append("HOME MARKER INCLUDED — do not commit this build")

    # -- Legend: Strahler order, stacked downward beside the plate ----------
    # North of the plate and off it: from the opening view (over the Pacific,
    # looking up the valley) that is empty space to the left of the basin.
    # 20 units between entries — at 11 they overwrote each other.
    lx = -layout.half_w * 0.55
    ly = layout.half_h + 24.0
    top = 70.0
    step = 20.0
    R.add(type=NODE_GLYPH, parent_id=0, branch_level=0, geometry=GEO_CUBE,
          translate_x=lx, translate_y=ly, translate_z=top + step, scale_x=0.0, scale_y=0.0,
          scale_z=0.0, show_text=1, text="Strahler stream order")
    for order in range(1, 6):
        width, color = ORDER_STYLE[order]
        count = sum(1 for s in streams if s.order == order)
        km = sum(s.length_km for s in streams if s.order == order)
        R.add(type=NODE_GLYPH, parent_id=0, branch_level=0, geometry=GEO_CUBE,
              translate_x=lx, translate_y=ly, translate_z=top - (order - 1) * step,
              scale_x=2.0 + width * 20, scale_y=2.0 + width * 20, scale_z=1.2,
              color_r=color[0], color_g=color[1], color_b=color[2], show_text=1,
              text=f"{order} · {km:,.0f} km")
    R.add(type=NODE_GLYPH, parent_id=0, branch_level=0, geometry=GEO_CUBE,
          translate_x=lx, translate_y=ly, translate_z=top - 5 * step - 3.0, scale_x=0.0,
          scale_y=0.0, scale_z=0.0, show_text=1,
          text=f"relief {TERRAIN_EXAG:g}x exaggerated")

    return Built(R.frame(), notes, checks)


# ---------------------------------------------------------------------------
# 6. VALIDATION + VERIFICATION THROUGH THE REAL ENGINE
# ---------------------------------------------------------------------------

def validate(df: pd.DataFrame) -> list[str]:
    from glyphviz_core.node import NON_VISUAL_TYPES
    problems = []
    if (df["id"] != range(1, len(df) + 1)).any():
        problems.append("node ids are not 1..N in order")
    ids = set(df["id"])
    bad = df[(df["parent_id"] != 0) & (~df["parent_id"].isin(ids))]
    if len(bad):
        problems.append(f"{len(bad)} dangling parent ids")
    if int((df["type"] == NODE_WORLD).sum()) != 1:
        problems.append("expected exactly one World row")
    drawable = int((~df["type"].isin(NON_VISUAL_TYPES)).sum())
    if drawable != len(df) - 1:
        problems.append(f"{len(df) - 1 - drawable} non-World rows are a non-visual type")
    if df[["translate_x", "translate_y", "translate_z"]].isna().any().any():
        problems.append("NaN in a translate column")
    return problems


def verify_scene(node_path: Path, layout: Layout, lattice: tr.Lattice,
                 checks: dict) -> list[str]:
    """Load the saved CSV through the real loader and Scene, and measure:
    the two frames coincide, every point glyph stands on the rendered surface,
    and every draped vertex is on or above it."""
    from glyphviz_core.csv_reader import load_node_csv
    from glyphviz_core.scene import Scene

    nodes = load_node_csv(str(node_path))
    scene = Scene(nodes)
    report = []

    worst_xy = 0.0
    worst_z = 0.0
    for nid, lon, lat, extra in checks["points"]:
        wp = scene.world_pos(nid)
        ex, ey = layout.world_xy(lon, lat)
        worst_xy = max(worst_xy, abs(wp[0] - ex), abs(wp[1] - ey))
        want_z = lattice.surface_height(lon, lat) * layout.z_per_m + extra
        worst_z = max(worst_z, abs(wp[2] - want_z))
    report.append(f"point glyphs: {len(checks['points'])}, grid-vs-surface frame "
                  f"offset {worst_xy:.6f} world units, height error {worst_z:.6f}")

    by_parent: dict[int, list] = {}
    for nd in nodes:
        if nd.parent_id:
            by_parent.setdefault(nd.parent_id, []).append(nd)
    below = 0
    total = 0
    min_gap = float("inf")
    for parent, dl, dt in checks["lines"]:
        kids = by_parent[parent]
        zs = np.array([scene.world_pos(k.id)[2] for k in kids])
        surf = np.asarray(lattice.surface_height(dl, dt)) * layout.z_per_m
        gap = zs - surf
        below += int((gap < -1e-3).sum())
        total += len(gap)
        min_gap = min(min_gap, float(gap.min()))
    report.append(f"draped vertices: {total}, below the rendered surface: {below}, "
                  f"tightest gap {min_gap:.3f} world units "
                  f"(clearance {LINE_CLEARANCE:g}, CSV rounding 0.001)")
    return report


# ---------------------------------------------------------------------------
# 7. MAIN
# ---------------------------------------------------------------------------

@dataclass
class Frame:
    """Everything a scene laid over this frame needs: the map window, the
    lon/lat -> world mapping, the DEM and the rendered lattice."""
    window: bm.BBox
    layout: Layout
    dem: tr.Dem
    lattice: tr.Lattice
    map_path: Path | None


def prepare_frame(out_dir: Path, refresh: bool = False, basemap: bool = True,
                  cols: int = SURFACE_COLS, exag: float | None = None) -> Frame:
    """Fetch the public data, the toned basemap (into out_dir/media) and the
    DEM, and build the lattice. Later Atlas phases call this so their scenes
    sit on exactly the same frame as this one."""
    global TERRAIN_EXAG
    if exag is not None:
        TERRAIN_EXAG = exag

    print("Public data (cached under data/):")
    huc = wd.fetch_huc10(refresh)
    outer, _inner, area = wd.dissolve(huc)
    for fetch in (wd.fetch_network, wd.fetch_gauges, wd.fetch_rain_stations,
                  wd.fetch_places, wd.fetch_reservoirs):
        fetch(refresh)
    print(f"  watershed {area:,.1f} km², divide ring {len(max(outer, key=len))} vertices")

    xs = [p[0] for ring in outer for p in ring]
    ys = [p[1] for ring in outer for p in ring]
    pw, ph = (max(xs) - min(xs)) * PAD_FRAC, (max(ys) - min(ys)) * PAD_FRAC
    window = bm.BBox(min(xs) - pw, max(xs) + pw, min(ys) - ph, max(ys) + ph)

    media = out_dir / "media"
    map_path = None
    if basemap:
        media.mkdir(parents=True, exist_ok=True)
        map_path = media / "01_watershed_terrain.png"
        window = fetch_basemap(window, map_path, max(outer, key=len))

    layout = make_layout(window)
    print(f"  plate {2 * layout.half_w:.1f} x {2 * layout.half_h:.1f} world units, "
          f"{layout.z_per_m * 1000:.3f} units/km vertical ({TERRAIN_EXAG:g}x)")

    print(f"  DEM zoom {DEM_ZOOM} …")
    dem = tr.fetch_dem(window, zoom=DEM_ZOOM)
    lattice = tr.build_lattice(dem, window, cols=cols)
    print(f"  lattice {lattice.cols}x{lattice.rows}, "
          f"{lattice.heights.min():.0f}..{lattice.heights.max():.0f} m "
          f"(DEM max {dem.heights.max():.0f} m)")
    return Frame(window, layout, dem, lattice, map_path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", type=Path, default=HERE)
    ap.add_argument("--refresh", action="store_true",
                    help="re-download the public data under data/")
    ap.add_argument("--no-basemap", action="store_true")
    ap.add_argument("--cols", type=int, default=SURFACE_COLS)
    ap.add_argument("--exag", type=float, default=TERRAIN_EXAG)
    ap.add_argument("--home", default=None,
                    help="LON,LAT for a 'you are here' pin (never commit it)")
    args = ap.parse_args()

    home = tuple(float(v) for v in args.home.split(",")) if args.home else None
    out_dir = args.out_dir
    fr = prepare_frame(out_dir, args.refresh, not args.no_basemap, args.cols, args.exag)
    window, layout, dem, lattice, map_path = (fr.window, fr.layout, fr.dem,
                                              fr.lattice, fr.map_path)

    built = build(layout, lattice, dem, map_path, home)
    problems = validate(built.df)
    for nid, lon, lat, _extra in built.checks["points"]:
        if not (window.lon_min <= lon <= window.lon_max
                and window.lat_min <= lat <= window.lat_max):
            problems.append(f"node {nid} at {lon:.4f},{lat:.4f} is off the map plate")
    if problems:
        print("\nVALIDATION FAILED:")
        for p in problems:
            print("  -", p)
        return 1

    # Round-trip through the app's own loader and compact writer: the saved
    # file is exactly what GlyphViz would write for this scene.
    from glyphviz_core.csv_reader import load_node_csv, save_node_csv
    node_path = out_dir / f"{OUT_STEM}_gv_node.csv"
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "raw_gv_node.csv"
        built.df.to_csv(raw, index=False)
        save_node_csv(load_node_csv(str(raw)), str(node_path))

    print(f"\nWrote {node_path.name}: {len(built.df):,} nodes, "
          f"{node_path.stat().st_size / 1e6:.2f} MB")
    for n in built.notes:
        print(f"  note: {n}")
    print("\nVerification (real loader + Scene):")
    for line in verify_scene(node_path, layout, lattice, built.checks):
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
