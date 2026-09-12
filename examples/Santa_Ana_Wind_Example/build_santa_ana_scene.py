#!/usr/bin/env python3
"""
build_santa_ana_scene.py — San Diego County wind, December 2012
================================================================

Phase 0 of the San Diego River Watershed Atlas: Jeff's own HPWREN/SDG&E
mesonet archive, restored as a GlyphViz scene.

WHAT THIS IS
------------
130 weather stations across San Diego County, every ten minutes for the whole
of December 2012 (4,428 frames), each drawn as a cone that points downwind.
The month contains two opposite weather regimes, and the whole point of the
scene is that you can see the switch happen:

  * Dec 13-18 — onshore storms. Vanes point inland, gusts to 65 mph, the
    county is blue (humid).
  * Dec 19-21 — a Santa Ana. Over about twelve hours on the 19th the entire
    field swings offshore and the colour collapses to red as relative
    humidity falls below 25% at 61% of stations. Gusts to 50 mph.

That flip, seen across 130 stations at once, is the thing a chart cannot show
and a 3D scene can.

SOURCE DATA (not committed — Jeff's personal archive, read at generation time)
-----------------------------------------------------------------------------
  <archive>/station_data/dec2012/sdge_data_DD_MM_YY_HH_MM_SS.txt
        4,428 files, one per ten-minute scrape, ~130 station rows each.
        Headerless but SELF-DESCRIBING: every row carries the station
        abbreviation, its name, and its lat/lon, so placement needs no
        lookup. 18 comma-separated fields:

          [ 0] station abbreviation        [ 9] relative humidity %
          [ 1] "M/D/YYYY H"  (obs hour)    [10] unidentified
          [ 2] observation minute          [11] unidentified
          [ 3] wind speed      mph         [12] unidentified
          [ 4] wind direction  deg FROM    [13] unidentified
          [ 5] wind gust       mph         [14] unidentified
          [ 6] gust direction  deg FROM    [15] station name
          [ 7] air temperature degF        [16] latitude   "33.35N"
          [ 8] dew point       degF        [17] longitude  "-117.27W"

        Fields 10-14 are deliberately left unidentified rather than guessed
        at; nothing here uses them. Units are IMPERIAL (degF / mph), confirmed
        against sens_sm_mappings.txt in the archive root. Jeff's later scrape
        (C:\\Jeff\\...\\dashboards\\weather\\csv) is METRIC — do not merge the
        two without converting.

        The 7-9 / 3-6 decoding is confirmed by physics, not by assumption:
        temp == dew point exactly where RH == 100, and the offshore-flow and
        low-humidity fractions rise and fall together across Dec 19-21 the way
        a Santa Ana does. See --scan.

  <archive>/sdge_met_locations.csv
        158-station gazetteer: abbrev, lat, lon, elevation ft, name, zone.
        NOTE: this file is CR-delimited (old Mac line endings) and reads as a
        single line unless split on "\\r" — see read_gazetteer(). Two HPWREN
        rows carry a placeholder elevation of exactly 1000 ft; they are used
        as-is and listed in the run report.

Only derived products are written into the repo. The 4 GB archive stays put.

HOW THE SCENE IS BUILT
----------------------
World Grid (type 6, flat) with its extents window set to exactly the bounding
box the basemap was rendered for, so the OpenTopoMap terrain texture registers
with child placement. Stations are children of the grid:

    translate_x = longitude        translate_y = latitude
    translate_z = elevation in km  (grid scale_z is the vertical exaggeration)

Grid scale re-spaces child POSITIONS per axis but never child glyph size, so
the cones stay a readable size however far apart the stations are spread.
scale_x is set to scale_y * cos(mid-latitude) so the map is locally conformal.

AIMING THE CONES — measured, not assumed
----------------------------------------
GEO_CONE is built along +Z (gluCylinder after a -h/2 translate: base at
z = -1, apex at z = +1, radius 1). A node loaded from CSV without a
rotation_mode column defaults to ROTATION_MODE_HEADING_TILT_ROLL, ANTz's
Z-X-Z convention. Probing the real engine through compute_world_transforms:

    rotate_x = 90, rotate_y = B   ->   apex points at compass bearing B,
                                       dead level (vertical residual 6e-17)

across the full sweep B = 0, 45, ... 315. So rotate_y IS the bearing, with no
conversion — which is exactly the binding Jeff's 2012 ANTz scene animated.

Wind direction in the data is meteorological (the direction the wind comes
FROM). A cone reads as an arrow, so it is pointed the way the air is GOING:

    rotate_y = (direction_from + 180) mod 360

WHAT EACH CHANNEL DRIVES (6 tracks per station, 7 bindings)
-----------------------------------------------------------
    rotate_y            downwind bearing
    scale_z             cone length      <- wind speed
    scale_x, scale_y    cone radius      <- gust factor (gust / sustained),
                                            i.e. how turbulent the air is
                                            (both read the SAME track)
    color_r/g/b         relative humidity on a dry-hot to moist-cool ramp

Colour carries humidity rather than speed on purpose. Speed is already the
length, and the variable that makes a Santa Ana legible — and that connects
this scene to the fire phases of the Atlas — is how dry the air is.

USAGE
-----
    python build_santa_ana_scene.py --scan          # characterise the month
    python build_santa_ana_scene.py                 # build everything
    python build_santa_ana_scene.py --no-basemap    # skip the tile fetch
    python build_santa_ana_scene.py --stride 6      # hourly, for a quick look
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

USER_AGENT = "GlyphViz/1.0 (desktop data-visualization app; example build)"

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO))

# ---------------------------------------------------------------------------
# 1. CONFIGURATION
# ---------------------------------------------------------------------------

DEFAULT_ARCHIVE = Path(
    r"G:\Backups\ED3D Laptop\2025_05_18\xampp3\htdocs\antz\toroids\hpwren_sdge"
)
MONTH_DIR = "dec2012"

OUT_STEM = "santa_ana_wind"
BASEMAP_PROVIDER = "opentopomap"      # terrain: wind follows topography
BASEMAP_TARGET_PX = 2048
# The module default of 60 tiles backs this window off to zoom 10 (1195 px
# across a 328-unit plate, ~3.6 px/unit). Zoom 11 needs ~80 tiles and doubles
# that, which is worth it for a map you fly down into. Tiles are cached, so
# a rebuild re-fetches nothing.
BASEMAP_TILE_CAP = 140

PAD_FRAC = 0.04                       # cushion around the station bbox

PLATE_HEIGHT = 260.0                  # world units north-south
VERT_EXAG = 15.0                      # elevation exaggeration vs true scale

# Cone sizing (world units; a unit cone is 2 long and 1 in radius, so
# scale_x = s gives a base diameter of 2s and scale_z = t gives a length of 2t).
#
# The cone holds a FIXED length:diameter ratio at every wind speed and scales
# uniformly. The first version drove length from speed and width from the gust
# factor independently, which at low speed produced short wide cones that read
# as blobs rather than arrows — a group of them lost its direction entirely.
# Holding the aspect constant means direction reads identically at 2 mph and at
# 40, which is what Jeff's own ANTz version did and is the right call.
CONE_ASPECT = 3.0                     # length / base diameter — always > 1
SIZE_MIN, SIZE_MAX = 0.95, 2.9        # uniform scale factor s
SPEED_FULL_MPH = 40.0                 # speed at which the cone reaches SIZE_MAX

# Gust factor moved off the cone's width and onto a small bead at the vane's
# pivot, so it stops competing with direction. Set GUST_BEAD = False to drop it.
GUST_BEAD = True
GUST_FACTOR_MAX = 3.0
BEAD_MIN, BEAD_MAX = 0.40, 1.60
BEAD_COLOR = (236, 240, 245)

# The terrain map is desaturated and darkened at build time so the warm cones
# have something to read against. Baked into the PNG rather than done with grid
# alpha: no blending, no depth-sort surprises. --map-alpha still exists if you
# want to fade it further at load time.
MAP_GREY = True
# Not fully grey: OpenTopoMap's ocean is a pale cyan that desaturates to almost
# exactly the same value as the coastal plain, so a 100% grey map loses the
# coastline entirely. Keeping a fifth of the colour puts the shore back without
# letting the terrain compete with the humidity ramp.
MAP_GREY_MIX = 0.80
# 0.64 was tuned for the flat grid plate. The terrain mesh is LIT, which
# brightens it again on top of this, so the relief version wants a darker
# source or the mountains blow out to white.
MAP_BRIGHTNESS = 0.48
MAP_ALPHA = 255

# Relative-humidity colour ramp: bone dry -> saturated
RH_RAMP = [
    (0.0,   (214,  62,  38)),         # fire weather
    (15.0,  (240, 120,  44)),
    (30.0,  (243, 186,  68)),
    (50.0,  (207, 214, 140)),
    (70.0,  (120, 176, 200)),
    (100.0, (44,   94, 168)),         # saturated
]

BG_COLOR = (16, 20, 26, 255)
TAG_COLOR = (232, 238, 240)
TAG_FONT_SIZE = 12

# --- Terrain surface -------------------------------------------------------
# A TOPO_SURFACE mesh built from free AWS Terrarium DEM tiles.
#
# TWO different vertical exaggerations, on purpose. The stations keep the 15x
# that makes the county's 13 ft -> 5,795 ft transect readable; the terrain gets
# 6x, because at 15x the relief turns into spikes that swallow the wind field
# and the mountain stations — which are the interesting ones in a Santa Ana —
# disappear into it. Jeff's call, 2026-09-12, after raising the overlap risk
# himself.
#
# The lower surface is not enough on its own: near sea level both the station
# and the terrain sit at z ~ 0 whatever the exaggeration, so a coastal cone
# would still be half-buried. Every station is therefore ALSO lifted by a fixed
# STATION_CLEARANCE in world units. Being a constant, it shifts the whole field
# without touching the *relative* elevation encoding.
SURFACE = True
SURFACE_VERT_EXAG = 6.0               # vs VERT_EXAG = 15.0 for the stations
STATION_CLEARANCE = 7.0               # world units, uniform
SURFACE_COLS = 120                    # lattice columns; rows follow plate aspect
# The mesh IS the surface, so each vertex's own glyph is shrunk away. Three
# things that do NOT work, all measured rather than assumed:
#   * hide=1 — the overlay builds its quads from the parent's *visible*
#     children (viewport.py `_draw_topology_overlays`), so hiding the vertices
#     deletes the mesh with them.
#   * color_a=0 — the mesh takes each corner's colour including alpha
#     (`glColor4f(..., nn.color_a / 255.0)`), so a transparent vertex makes a
#     transparent surface.
#   * GEO_POINT, the obvious choice and what Surface_Example uses — point
#     sprites are sized `max(2.0, ratio * 20.0)` pixels, a hard 2 px floor, and
#     11,400 of them read as speckle across the relief.
# A sub-pixel SOLID glyph does work, and a sub-pixel WIRE one does not: wire
# geometry rasterises a minimum 1 px line, while a sub-pixel triangle covers no
# sample and is dropped. Verified side by side on a 30x30 test surface — the
# wire build shows the full dot grid, the solid build is perfectly clean.
SURFACE_POINT_GEOMETRY = 1            # GEO_CUBE — solid, so sub-pixel culls
SURFACE_POINT_SCALE = 0.002
DEM_TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
DEM_ZOOM = 11                         # ~30 m/px at this latitude
DEM_SEA_LEVEL_M = -2.0                # anything below this is clamped to 0

TIMELINE_GAP = 18.0                   # world units south of the plate edge
CURSOR_SCALE = 2.6                    # the "now" bead; clock offsets divide by it
LEGEND_GAP = 46.0                     # world units west of the plate edge

GEO_CUBE_WIRE, GEO_CUBE, GEO_SPHERE, GEO_CONE, GEO_POINT = 0, 1, 3, 5, 22
TOPO_SURFACE = 17

# Node types. NODE_GLYPH is the ordinary drawable row — type 0 is the World
# row and type 1 is a camera, and BOTH are in node.NON_VISUAL_TYPES, so a
# glyph authored as type 0 loads fine, validates fine, and renders nothing.
NODE_WORLD, NODE_GLYPH, NODE_GRID = 0, 5, 6

# Stations pinned with a permanent label, for orientation. Kept to a handful —
# every station carries a tag, but all show_text labels draw at once.
# Four, widely separated: the coast, the watershed, the high mountains and the
# desert. Julian and Ramona were in here too and their labels collided with
# Borrego's from the usual viewing angles — all show_text labels draw at once,
# so a pin costs more than it looks.
PINNED = {"SOB": "Solana Beach", "MTL": "Mission Trails",
          "MLG": "Mt. Laguna", "BRG": "Borrego"}

# The scrape and the gazetteer disagree on one abbreviation: the feed reports
# Ranchita (33.21N, -116.50W) as RCH, the gazetteer lists it as RAN. Without
# this the station loses its 4,124 ft elevation and sits on the coastal plane.
ABBREV_ALIASES = {"RCH": "RAN"}


# ---------------------------------------------------------------------------
# 2. READING THE ARCHIVE
# ---------------------------------------------------------------------------

@dataclass
class Obs:
    speed: float        # mph
    direction: float    # degrees the wind comes FROM
    gust: float         # mph
    temp_f: float
    dew_f: float
    rh: float           # percent


def read_gazetteer(path: Path) -> dict[str, dict]:
    """Parse sdge_met_locations.csv -> {abbrev: {lat, lon, elev_ft, name, zone}}.

    The file is CR-delimited, so a naive readlines() returns one 8 KB line.
    """
    txt = path.read_bytes().decode("utf-8", "replace")
    lines = [l for l in txt.replace("\r\n", "\n").replace("\r", "\n").split("\n")
             if l.strip()]
    out: dict[str, dict] = {}
    for line in lines:
        p = line.split(",")
        if len(p) < 6:
            continue
        try:
            out[p[0]] = dict(lat=float(p[1]), lon=float(p[2]),
                             elev_ft=int(p[3]), name=p[4], zone=p[5])
        except ValueError:
            continue
    return out


def _parse_latlon(tok: str) -> float:
    """'33.35N' / '-117.27W' -> signed decimal degrees."""
    tok = tok.strip()
    hemi = tok[-1].upper() if tok and tok[-1].isalpha() else ""
    val = float(tok[:-1] if hemi else tok)
    if hemi in ("S", "W"):
        val = -abs(val)
    return val


def read_scrape(path: Path) -> tuple[datetime | None, dict[str, tuple[Obs, float, float, str]]]:
    """One scrape file -> (observation time, {abbrev: (Obs, lat, lon, name)})."""
    out: dict[str, tuple[Obs, float, float, str]] = {}
    when: datetime | None = None
    for line in path.read_text(errors="replace").splitlines():
        p = line.split(",")
        if len(p) != 18:
            continue
        try:
            date_part, hour = p[1].rsplit(" ", 1)
            t = datetime.strptime(f"{date_part} {int(hour):02d}:{int(p[2]):02d}",
                                  "%m/%d/%Y %H:%M")
            obs = Obs(speed=float(p[3]), direction=float(p[4]), gust=float(p[5]),
                      temp_f=float(p[7]), dew_f=float(p[8]), rh=float(p[9]))
            out[p[0]] = (obs, _parse_latlon(p[16]), _parse_latlon(p[17]), p[15])
            if when is None:
                when = t
        except (ValueError, IndexError):
            continue
    return when, out


def read_month(month_dir: Path, stride: int = 1, limit: int | None = None):
    """-> (frames, stations) where frames is [(datetime, {abbrev: Obs})] in time
    order and stations is {abbrev: {lat, lon, name}} seen anywhere in the month."""
    files = sorted(month_dir.glob("sdge_data_*.txt"))
    if not files:
        raise SystemExit(f"No scrape files under {month_dir}")
    frames: list[tuple[datetime, dict[str, Obs]]] = []
    stations: dict[str, dict] = {}
    for path in files:
        when, obs = read_scrape(path)
        if when is None or not obs:
            continue
        frames.append((when, {a: v[0] for a, v in obs.items()}))
        for a, (_o, lat, lon, name) in obs.items():
            stations.setdefault(a, dict(lat=lat, lon=lon, name=name))
    frames.sort(key=lambda r: r[0])
    if stride > 1:
        frames = frames[::stride]
    if limit:
        frames = frames[:limit]
    return frames, stations


# ---------------------------------------------------------------------------
# 3. ENCODINGS
# ---------------------------------------------------------------------------

def rh_color(rh: float) -> tuple[int, int, int]:
    rh = max(0.0, min(100.0, rh))
    for (a_v, a_c), (b_v, b_c) in zip(RH_RAMP, RH_RAMP[1:]):
        if rh <= b_v:
            t = 0.0 if b_v == a_v else (rh - a_v) / (b_v - a_v)
            return tuple(int(round(a_c[i] + t * (b_c[i] - a_c[i]))) for i in range(3))
    return RH_RAMP[-1][1]


def cone_size(speed: float) -> tuple[float, float]:
    """-> (radius scale, length scale) for a wind speed.

    Uniform in the sense that matters: the returned pair always stands in the
    ratio CONE_ASPECT, so the glyph is the same *shape* at every wind speed and
    only its size changes. Length is therefore never shorter than the base
    diameter, and a field of these reads as arrows at any speed.
    """
    t = min(max(speed, 0.0) / SPEED_FULL_MPH, 1.0) ** 0.6
    s = SIZE_MIN + t * (SIZE_MAX - SIZE_MIN)
    return round(s, 3), round(s * CONE_ASPECT, 3)


def gust_factor(speed: float, gust: float) -> float:
    """How much rougher the gusts are than the sustained wind. Undefined at
    zero wind, so calm is pinned to 1.0 (the smallest bead)."""
    if speed <= 0.5:
        return 1.0
    return max(1.0, min(gust / speed, GUST_FACTOR_MAX))


def bead_size(speed: float, gust: float) -> float:
    t = (gust_factor(speed, gust) - 1.0) / (GUST_FACTOR_MAX - 1.0)
    return round(BEAD_MIN + t * (BEAD_MAX - BEAD_MIN), 3)


def downwind_bearing(direction_from: float) -> float:
    return round((direction_from + 180.0) % 360.0, 1)


def signature_frame(frames) -> int:
    """Index of the most Santa Ana-like frame in the month.

    Channels are not applied until playback starts, so whatever is written
    into the node CSV is what the scene looks like at rest — in GlyphViz
    before you press play, and in every headless render, since export_frame.py
    loads nodes only. Authoring the peak of the event into those columns makes
    the still frame the story rather than 130 cones all pointing north at a
    default size.

    Score = (fraction of stations with offshore flow) x (fraction below 25% RH).
    Both have to be high at once, which is what separates a Santa Ana from an
    ordinary dry day or an ordinary windy one.
    """
    best_i, best_score = 0, -1.0
    for i, (_when, obs) in enumerate(frames):
        if not obs:
            continue
        offshore = sum(1 for o in obs.values() if 0 <= o.direction <= 135) / len(obs)
        dry = sum(1 for o in obs.values() if o.rh < 25) / len(obs)
        score = offshore * dry
        if score > best_score:
            best_i, best_score = i, score
    return best_i


# ---------------------------------------------------------------------------
# 4. SCENE BUILDER
# ---------------------------------------------------------------------------

COLUMNS = ["id", "type", "parent_id", "branch_level", "child_id",
           "translate_x", "translate_y", "translate_z",
           "rotate_x", "rotate_y", "rotate_z",
           "scale_x", "scale_y", "scale_z",
           "color_r", "color_g", "color_b", "color_a", "color_index",
           "geometry", "hide", "topo", "ratio", "texture_id",
           "ch_input_id", "show_text",
           "trigger_lo_x", "trigger_hi_x", "trigger_lo_y", "trigger_hi_y",
           "segments_x", "segments_y",
           "tag_color_mode", "tag_color_r", "tag_color_g", "tag_color_b",
           "tag_font_size", "text", "link"]

DEFAULTS = dict(child_id=0, translate_x=0.0, translate_y=0.0, translate_z=0.0,
                rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
                scale_x=1.0, scale_y=1.0, scale_z=1.0,
                color_r=255, color_g=255, color_b=255, color_a=255,
                color_index=0, geometry=GEO_SPHERE, hide=0, topo=0, ratio=0.1,
                texture_id=0, ch_input_id=0, show_text=0,
                trigger_lo_x=0, trigger_hi_x=0, trigger_lo_y=0, trigger_hi_y=0,
                segments_x=16, segments_y=16,
                tag_color_mode=0, tag_color_r=255, tag_color_g=255,
                tag_color_b=255, tag_font_size=TAG_FONT_SIZE, text="", link="")


@dataclass
class SceneBuilder:
    rows: list[dict] = field(default_factory=list)
    next_id: int = 1

    def add(self, **kw) -> int:
        row = {**DEFAULTS, "id": self.next_id, **kw}
        self.rows.append(row)
        self.next_id += 1
        return row["id"]

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=COLUMNS)


@dataclass
class Layout:
    lon_min: float
    lon_max: float
    lat_min: float
    lat_max: float
    scale_x: float
    scale_y: float
    scale_z: float

    @property
    def half_w(self) -> float:
        return (self.lon_max - self.lon_min) / 2.0 * self.scale_x

    @property
    def half_h(self) -> float:
        return (self.lat_max - self.lat_min) / 2.0 * self.scale_y


def make_layout(lon_min, lon_max, lat_min, lat_max) -> Layout:
    lat_span = lat_max - lat_min
    lat_ctr = (lat_min + lat_max) / 2.0
    sy = PLATE_HEIGHT / lat_span
    sx = sy * math.cos(math.radians(lat_ctr))      # locally conformal
    # translate_z is in kilometres; true scale would be sy / 111.32 world
    # units per km, so the exaggeration multiplies that.
    sz = (sy / 111.32) * VERT_EXAG
    return Layout(lon_min, lon_max, lat_min, lat_max,
                  round(sx, 4), round(sy, 4), round(sz, 4))


def surface_scale_z(layout: Layout) -> float:
    """World units per kilometre for the terrain mesh — the same true scale the
    stations use, at the lower SURFACE_VERT_EXAG."""
    return (layout.scale_y / 111.32) * SURFACE_VERT_EXAG


def lattice_axes(layout: Layout) -> tuple[list[float], list[float]]:
    """The terrain mesh's lon and lat axes. One definition, shared by the mesh
    builder and the clearance calculation, so the two cannot drift apart."""
    cols = SURFACE_COLS
    rows = max(2, int(round(cols * (2 * layout.half_h) / (2 * layout.half_w))))
    lons = [layout.lon_min + (layout.lon_max - layout.lon_min) * i / (cols - 1)
            for i in range(cols)]
    lats = [layout.lat_min + (layout.lat_max - layout.lat_min) * j / (rows - 1)
            for j in range(rows)]
    return lons, lats


def mesh_height_near(dem, dem_origin, lons, lats, lon, lat) -> float:
    """Highest DEM height, in km, among the four mesh vertices bracketing a
    point — i.e. the top of the quad actually drawn under it.

    Sampling the DEM at the point itself is NOT the right test: the rendered
    surface is a lattice, and its nearest corner can sit well above a station
    standing on a valley floor between ridges.
    """
    import bisect
    i = min(max(bisect.bisect_left(lons, lon) - 1, 0), len(lons) - 2)
    j = min(max(bisect.bisect_left(lats, lat) - 1, 0), len(lats) - 2)
    dlon = (lons[-1] - lons[0]) / (len(lons) - 1) / 2.0
    dlat = (lats[-1] - lats[0]) / (len(lats) - 1) / 2.0
    return max(elev_km(sample_dem_cell(dem, dem_origin, lons[a] - dlon,
                                       lons[a] + dlon, lats[b] - dlat,
                                       lats[b] + dlat))
               for a in (i, i + 1) for b in (j, j + 1))


def world_xy(layout: Layout, lon: float, lat: float) -> tuple[float, float]:
    """Where a World Grid child at (lon, lat) lands in world units.

    The grid recentres its extents window on the midpoint and scales per axis,
    so the surface mesh — which is a root node, not a grid child — has to
    reproduce that mapping itself to sit under the stations.
    """
    lon_c = (layout.lon_min + layout.lon_max) / 2.0
    lat_c = (layout.lat_min + layout.lat_max) / 2.0
    return ((lon - lon_c) * layout.scale_x, (lat - lat_c) * layout.scale_y)


def build_terrain(sb: SceneBuilder, layout: Layout, dem, dem_origin,
                  map_path: Path | None) -> int:
    """TOPO_SURFACE mesh under the wind field. -> node count added.

    Structure mirrors Surface_Example: the parent is a ROOT at the origin with
    scale 1 and topo 17, and its children sit at literal Cartesian (x, y) with
    translate_z as the height there — so the world-unit coordinates go straight
    into the children and nothing has to be undone later. The viewport groups
    them back into a grid by their distinct (x, y) values and draws a lit,
    per-vertex-coloured quad mesh; each child also draws its own small point.
    """
    lons, lats = lattice_axes(layout)
    cols, rows = len(lons), len(lats)
    sz = surface_scale_z(layout)

    tex = None
    if map_path is not None and map_path.is_file():
        from PIL import Image
        tex = np.asarray(Image.open(map_path).convert("RGB"))

    parent = sb.add(type=NODE_GLYPH, parent_id=0, branch_level=0,
                    geometry=GEO_POINT, topo=TOPO_SURFACE,
                    translate_x=0.0, translate_y=0.0, translate_z=0.0,
                    scale_x=1.0, scale_y=1.0, scale_z=1.0,
                    color_r=200, color_g=200, color_b=200, color_a=255,
                    text=f"Terrain · {SURFACE_VERT_EXAG:g}x vertical exaggeration")

    added = 1
    dlon = (lons[-1] - lons[0]) / (cols - 1) / 2.0
    dlat = (lats[-1] - lats[0]) / (rows - 1) / 2.0
    for lat in lats:
        for lon in lons:
            km = elev_km(sample_dem_cell(dem, dem_origin, lon - dlon,
                                         lon + dlon, lat - dlat, lat + dlat))
            wx, wy = world_xy(layout, lon, lat)
            if tex is not None:
                u = (lon - layout.lon_min) / (layout.lon_max - layout.lon_min)
                v = (layout.lat_max - lat) / (layout.lat_max - layout.lat_min)
                px = min(int(u * (tex.shape[1] - 1)), tex.shape[1] - 1)
                py = min(int(v * (tex.shape[0] - 1)), tex.shape[0] - 1)
                c = tuple(int(x) for x in tex[py, px])
            else:
                t = min(km / 1.8, 1.0)
                c = (int(70 + 150 * t), int(85 + 130 * t), int(70 + 90 * t))
            sb.add(type=NODE_GLYPH, parent_id=parent, branch_level=1,
                   geometry=SURFACE_POINT_GEOMETRY, topo=0,
                   translate_x=round(wx, 3), translate_y=round(wy, 3),
                   translate_z=round(km * sz, 3),
                   scale_x=SURFACE_POINT_SCALE, scale_y=SURFACE_POINT_SCALE,
                   scale_z=SURFACE_POINT_SCALE,
                   color_r=c[0], color_g=c[1], color_b=c[2], color_a=255)
            added += 1
    return added


def build_scene(frames, stations, gaz, layout: Layout, have_basemap: bool,
                sig_index: int, dem=None, dem_origin=None,
                map_path: Path | None = None):
    """-> (node DataFrame, {abbrev: channel_id}, cursor_channel_id, notes)"""
    sb = SceneBuilder()
    notes: list[str] = []
    sig_when, sig_obs = frames[sig_index]

    # -- World row: background and scene-wide tag styling --------------------
    sb.add(type=NODE_WORLD, parent_id=0, branch_level=0, geometry=0,
           color_r=BG_COLOR[0], color_g=BG_COLOR[1],
           color_b=BG_COLOR[2], color_a=BG_COLOR[3],
           tag_color_mode=1, tag_color_r=TAG_COLOR[0],
           tag_color_g=TAG_COLOR[1], tag_color_b=TAG_COLOR[2],
           tag_font_size=TAG_FONT_SIZE)

    # -- The county, as a flat World Grid ------------------------------------
    # Extents are exactly the window the basemap was rendered for, so the
    # texture registers with child placement.
    # With a terrain mesh present the grid goes WIRE: an opaque flat map at
    # z = 0 would be hidden under the relief everywhere inland and z-fight with
    # it along the coast, where both sit at zero. Wire leaves the graticule as
    # a reference plane and hands the imagery to the surface, which carries it
    # per-vertex.
    grid_solid = have_basemap and dem is None
    grid_id = sb.add(type=NODE_GRID, parent_id=0, branch_level=0,
                     geometry=GEO_CUBE if grid_solid else GEO_CUBE_WIRE,
                     translate_x=0.0, translate_y=0.0, translate_z=0.0,
                     scale_x=layout.scale_x, scale_y=layout.scale_y,
                     scale_z=layout.scale_z,
                     texture_id=1 if grid_solid else 0,
                     trigger_lo_x=round(layout.lon_min, 6),
                     trigger_hi_x=round(layout.lon_max, 6),
                     trigger_lo_y=round(layout.lat_min, 6),
                     trigger_hi_y=round(layout.lat_max, 6),
                     segments_x=16, segments_y=12,
                     color_r=255, color_g=255, color_b=255, color_a=MAP_ALPHA,
                     text=f"San Diego County · {sig_when:%d %b %Y %H:%M} "
                          f"· Santa Ana")

    # -- Terrain -------------------------------------------------------------
    if dem is not None:
        n_terrain = build_terrain(sb, layout, dem, dem_origin, map_path)
        notes.append(f"terrain mesh: {n_terrain - 1} points at "
                     f"{SURFACE_VERT_EXAG:g}x exaggeration, stations lifted "
                     f"{STATION_CLEARANCE:g} world units clear of it")

    # -- Stations ------------------------------------------------------------
    # Channel ids are assigned in blocks up front rather than as the loop goes,
    # so the cone block and the bead block cannot collide: cones take 1..N,
    # beads N+1..2N, and the timeline cursor and clock follow.
    ordered_stations = sorted(stations)
    n_st = len(ordered_stations)

    # A station's height comes from the GAZETTEER at 15x; the ground under it
    # comes from the DEM at 6x. Those two disagree — a valley-floor station can
    # have a DEM sample above its listed elevation — so a flat
    # STATION_CLEARANCE does not actually guarantee clearance. Measure the
    # worst disagreement first and lift everything by that much plus the
    # clearance. Still ONE uniform offset, so relative elevation is untouched,
    # but now the tightest station really does sit STATION_CLEARANCE clear.
    clearance_km = 0.0
    if dem is not None:
        ssz = surface_scale_z(layout)
        _mlons, _mlats = lattice_axes(layout)
        worst = 0.0
        for abbrev in ordered_stations:
            g = gaz.get(abbrev) or gaz.get(ABBREV_ALIASES.get(abbrev, ""))
            base_z = (g["elev_ft"] if g else 0) * 0.0003048 * layout.scale_z
            terr_z = mesh_height_near(dem, dem_origin, _mlons, _mlats,
                                      stations[abbrev]["lon"],
                                      stations[abbrev]["lat"]) * ssz
            worst = max(worst, terr_z - base_z)
        clearance_km = (worst + STATION_CLEARANCE) / layout.scale_z
        notes.append(f"station lift {worst + STATION_CLEARANCE:.1f} world units "
                     f"({STATION_CLEARANCE:g} clearance + {worst:.1f} to cover the "
                     f"worst gazetteer-vs-DEM disagreement)")
    station_channel: dict[str, int] = {a: i + 1 for i, a in enumerate(ordered_stations)}
    bead_channel: dict[str, int] = (
        {a: n_st + i + 1 for i, a in enumerate(ordered_stations)} if GUST_BEAD else {}
    )
    missing_elev: list[str] = []
    placeholder_elev: list[str] = []

    for abbrev in ordered_stations:
        meta = stations[abbrev]
        g = gaz.get(abbrev) or gaz.get(ABBREV_ALIASES.get(abbrev, ""))
        if g is None:
            elev_ft = 0
            missing_elev.append(abbrev)
            name = meta["name"]
        else:
            elev_ft = g["elev_ft"]
            name = g["name"] or meta["name"]
            if elev_ft == 1000:
                placeholder_elev.append(abbrev)
        # translate_z is in kilometres and the grid multiplies it by scale_z,
        # so a clearance expressed in WORLD units has to be divided back out.
        station_km = elev_ft * 0.0003048 + clearance_km

        ch = station_channel[abbrev]
        label = f"{name} ({abbrev}) · {elev_ft:,} ft"

        # Authored pose = the signature frame, so the scene reads correctly
        # at rest (see signature_frame()).
        o = sig_obs.get(abbrev)
        if o is None:
            ry, rad, ln, bead, col = 0.0, SIZE_MIN, SIZE_MIN * CONE_ASPECT, \
                BEAD_MIN, (180, 180, 180)
        else:
            ry = downwind_bearing(o.direction)
            rad, ln = cone_size(o.speed)
            bead = bead_size(o.speed, o.gust)
            col = rh_color(o.rh)

        sb.add(type=NODE_GLYPH, parent_id=grid_id, branch_level=1, geometry=GEO_CONE,
               translate_x=round(meta["lon"], 5),
               translate_y=round(meta["lat"], 5),
               translate_z=round(station_km, 6),
               rotate_x=90.0,               # tip the cone into the horizontal
               rotate_y=ry,                 # animated: downwind bearing
               scale_x=rad, scale_y=rad, scale_z=ln,
               color_r=col[0], color_g=col[1], color_b=col[2], color_a=255,
               segments_x=14, segments_y=2,
               ch_input_id=ch,
               show_text=1 if abbrev in PINNED else 0,
               text=label)

        # Gust bead: a sibling at the same point, which is the cone's pivot
        # (the cone is centred on its station). Its own channel, because
        # sharing the cone's would hand it the cone's rotation and length too.
        if GUST_BEAD:
            bch = bead_channel[abbrev]
            sb.add(type=NODE_GLYPH, parent_id=grid_id, branch_level=1,
                   geometry=GEO_SPHERE,
                   translate_x=round(meta["lon"], 5),
                   translate_y=round(meta["lat"], 5),
                   translate_z=round(station_km, 6),
                   scale_x=bead, scale_y=bead, scale_z=bead,
                   color_r=BEAD_COLOR[0], color_g=BEAD_COLOR[1],
                   color_b=BEAD_COLOR[2], color_a=255,
                   segments_x=10, segments_y=8,
                   ch_input_id=bch,
                   text=f"{name} ({abbrev}) · gust factor")

    if missing_elev:
        notes.append(f"{len(missing_elev)} station(s) absent from the gazetteer, "
                     f"placed at elevation 0: {', '.join(sorted(missing_elev))}")
    if placeholder_elev:
        notes.append(f"{len(placeholder_elev)} station(s) carry the gazetteer's "
                     f"placeholder 1000 ft elevation: "
                     f"{', '.join(sorted(placeholder_elev))}")

    # -- Timeline bar (world coordinates, south of the plate) ----------------
    cursor_ch = n_st + len(bead_channel) + 1
    ty = -(layout.half_h + TIMELINE_GAP)
    day_of = sorted({f[0].date() for f in frames})
    n_days = len(day_of)

    def x_of_day(i: int) -> float:
        if n_days <= 1:
            return 0.0
        return round(-layout.half_w + (2 * layout.half_w) * i / (n_days - 1), 3)

    for i, d in enumerate(day_of):
        # Every fifth day only. The month's first scrape is timestamped
        # Nov 30 23:40, so labelling day 1 as well puts two labels on top of
        # each other at the left end of the bar.
        major = d.day % 5 == 0
        sb.add(type=NODE_GLYPH, parent_id=0, branch_level=0, geometry=GEO_CUBE,
               translate_x=x_of_day(i), translate_y=ty, translate_z=0.0,
               scale_x=0.5, scale_y=0.5, scale_z=2.2 if major else 1.2,
               color_r=150, color_g=160, color_b=170, color_a=255,
               show_text=1 if major else 0,
               text=f"{d:%b} {d.day}" if major else d.isoformat())

    sig_x = round(-layout.half_w + (2 * layout.half_w)
                  * (sig_index / max(len(frames) - 1, 1)), 3)
    cursor_id = sb.add(type=NODE_GLYPH, parent_id=0, branch_level=0, geometry=GEO_SPHERE,
                       translate_x=sig_x, translate_y=ty, translate_z=4.0,
                       scale_x=CURSOR_SCALE, scale_y=CURSOR_SCALE,
                       scale_z=CURSOR_SCALE,
                       color_r=255, color_g=236, color_b=140, color_a=255,
                       segments_x=16, segments_y=12,
                       ch_input_id=cursor_ch,
                       text="now")

    # -- Running clock, riding the cursor ------------------------------------
    # Channels can animate show_text but NOT the text itself — a tag's string
    # is authored, not bindable. So the readout is built as a bank of
    # pre-labelled invisible nodes with only one of each bank showing at a
    # time: 31 date labels and 144 time-of-day labels (one per ten-minute slot
    # of a day), 175 nodes and 175 tracks, rather than one node per frame,
    # which would be 4,428 tracks and a far larger file for the same result.
    #
    # They are CHILDREN of the cursor bead, so they inherit its animated
    # translate_x and travel along the bar with it. Offsets are divided by the
    # cursor's own scale, which a child's translate is multiplied by.
    # They stack vertically: a tag draws to the RIGHT of its glyph, so two
    # labels side by side would overwrite each other.
    clock_channels: dict[str, dict] = {"date": {}, "time": {}}
    next_clock_ch = cursor_ch + 1
    for i, d in enumerate(day_of):
        clock_channels["date"][d.isoformat()] = next_clock_ch + i
    next_clock_ch += len(day_of)
    slots = sorted({(w.hour, w.minute // 10 * 10) for w, _ in frames})
    for i, slot in enumerate(slots):
        clock_channels["time"][slot] = next_clock_ch + i
    next_clock_ch += len(slots)

    # The signature frame's own two labels are the pair left showing at rest.
    inv = 1.0 / CURSOR_SCALE
    sig_date = sig_when.date().isoformat()
    sig_slot = (sig_when.hour, sig_when.minute // 10 * 10)
    for d, cch in clock_channels["date"].items():
        sb.add(type=NODE_GLYPH, parent_id=cursor_id, branch_level=1, geometry=0,
               translate_x=0.0, translate_y=0.0, translate_z=36.0 * inv,
               scale_x=0.1, scale_y=0.1, scale_z=0.1, color_a=0,
               ch_input_id=cch, show_text=1 if d == sig_date else 0,
               text=datetime.fromisoformat(d).strftime("%a %d %b %Y"))
    for slot, cch in clock_channels["time"].items():
        sb.add(type=NODE_GLYPH, parent_id=cursor_id, branch_level=1, geometry=0,
               translate_x=0.0, translate_y=0.0, translate_z=25.0 * inv,
               scale_x=0.1, scale_y=0.1, scale_z=0.1, color_a=0,
               ch_input_id=cch, show_text=1 if slot == sig_slot else 0,
               text=f"{slot[0]:02d}:{slot[1]:02d}")

    # -- Legend: the humidity ramp, stacked downward beside the plate --------
    # Entries stack DOWNWARD in z, never side by side: a tag label draws to the
    # right of its glyph, so a horizontal legend overwrites its own text.
    # 20 units of separation keeps the labels clear when the whole 328-unit
    # plate is in frame; at 11 they collided.
    lx = -(layout.half_w + LEGEND_GAP)
    top_z = 120.0
    step_z = 20.0
    sb.add(type=NODE_GLYPH, parent_id=0, branch_level=0, geometry=0,
           translate_x=lx, translate_y=0.0, translate_z=top_z + step_z,
           scale_x=0.1, scale_y=0.1, scale_z=0.1,
           color_a=0, show_text=1,
           text="Relative humidity")
    for i, rh in enumerate((5, 20, 35, 55, 75, 95)):
        c = rh_color(rh)
        sb.add(type=NODE_GLYPH, parent_id=0, branch_level=0, geometry=GEO_CUBE,
               translate_x=lx, translate_y=0.0, translate_z=top_z - i * step_z,
               scale_x=6.0, scale_y=6.0, scale_z=6.0,
               color_r=c[0], color_g=c[1], color_b=c[2], color_a=255,
               show_text=1, text=f"{rh}%" + ("  fire weather" if rh <= 20 else ""))
    sb.add(type=NODE_GLYPH, parent_id=0, branch_level=0, geometry=0,
           translate_x=lx, translate_y=0.0, translate_z=top_z - 6 * step_z - 8,
           scale_x=0.1, scale_y=0.1, scale_z=0.1,
           color_a=0, show_text=1,
           text="cone points downwind")

    return (sb.to_dataframe(), station_channel, bead_channel, cursor_ch,
            clock_channels, notes)


# ---------------------------------------------------------------------------
# 5. CHANNEL FILES
# ---------------------------------------------------------------------------

def build_channels(frames, stations, station_channel, bead_channel, cursor_ch,
                   clock_channels, layout):
    """Six tracks per cone (one shared by scale_x and scale_y), one per gust
    bead (shared by all three axes), the timeline cursor, and one per clock
    label. -> (ch_map_df, ch_tracks_df)"""
    map_rows: list[dict] = []
    track_of: dict[tuple[str, str], int] = {}
    next_track = 1

    def bind(abbrev: str, key: str, attrs: list[str]) -> int:
        nonlocal next_track
        tid = next_track
        next_track += 1
        track_of[(abbrev, key)] = tid
        for attr in attrs:
            map_rows.append(dict(id=len(map_rows) + 1,
                                 channel_id=station_channel[abbrev],
                                 track_id=tid, attribute=attr,
                                 track_table_id=0, ch_map_table_id=0,
                                 record_id=0))
        return tid

    ordered = sorted(station_channel, key=lambda a: station_channel[a])
    CONE_KEYS = ("dir", "rad", "len", "cr", "cg", "cb")
    for abbrev in ordered:
        bind(abbrev, "dir", ["rotate_y"])
        bind(abbrev, "rad", ["scale_x", "scale_y"])   # one track, two axes
        bind(abbrev, "len", ["scale_z"])
        bind(abbrev, "cr", ["color_r"])
        bind(abbrev, "cg", ["color_g"])
        bind(abbrev, "cb", ["color_b"])

    # Gust beads: one track apiece, read by all three scale axes so the bead
    # stays a sphere.
    bead_track: dict[str, int] = {}
    for abbrev in ordered:
        if abbrev not in bead_channel:
            continue
        bead_track[abbrev] = next_track
        for attr in ("scale_x", "scale_y", "scale_z"):
            map_rows.append(dict(id=len(map_rows) + 1,
                                 channel_id=bead_channel[abbrev],
                                 track_id=next_track, attribute=attr,
                                 track_table_id=0, ch_map_table_id=0,
                                 record_id=0))
        next_track += 1

    cursor_track = next_track
    next_track += 1
    map_rows.append(dict(id=len(map_rows) + 1, channel_id=cursor_ch,
                         track_id=cursor_track, attribute="translate_x",
                         track_table_id=0, ch_map_table_id=0, record_id=0))

    # Clock labels: show_text, one track each, exactly one of each bank on.
    clock_track: dict[tuple[str, object], int] = {}
    for bank in ("date", "time"):
        for key, cch in clock_channels[bank].items():
            clock_track[(bank, key)] = next_track
            map_rows.append(dict(id=len(map_rows) + 1, channel_id=cch,
                                 track_id=next_track, attribute="show_text",
                                 track_table_id=0, ch_map_table_id=0,
                                 record_id=0))
            next_track += 1

    ch_map_df = pd.DataFrame(map_rows)

    n = len(frames)
    cols: dict[str, list] = {"cyclecount": list(range(1, n + 1))}
    for abbrev in ordered:
        for key in CONE_KEYS:
            cols[f"ch{track_of[(abbrev, key)]}"] = [0] * n
        if abbrev in bead_track:
            cols[f"ch{bead_track[abbrev]}"] = [0] * n
    for tid in clock_track.values():
        cols[f"ch{tid}"] = [0] * n

    # Carry-forward: a station missing from one scrape keeps its last reading
    # rather than snapping to a default.
    last: dict[str, tuple] = {}
    for fi, (when, obs) in enumerate(frames):
        for abbrev in ordered:
            o = obs.get(abbrev)
            if o is None:
                vals = last.get(abbrev)
                if vals is None:
                    continue
            else:
                c = rh_color(o.rh)
                rad, ln = cone_size(o.speed)
                vals = (downwind_bearing(o.direction), rad, ln,
                        c[0], c[1], c[2], bead_size(o.speed, o.gust))
                last[abbrev] = vals
            for key, v in zip(CONE_KEYS, vals):
                cols[f"ch{track_of[(abbrev, key)]}"][fi] = v
            if abbrev in bead_track:
                cols[f"ch{bead_track[abbrev]}"][fi] = vals[6]

        cols[f"ch{clock_track[('date', when.date().isoformat())]}"][fi] = 1
        cols[f"ch{clock_track[('time', (when.hour, when.minute // 10 * 10))]}"][fi] = 1

    span = 2 * layout.half_w
    cols[f"ch{cursor_track}"] = [
        round(-layout.half_w + span * (f / max(n - 1, 1)), 3) for f in range(n)
    ]
    return ch_map_df, pd.DataFrame(cols)


# ---------------------------------------------------------------------------
# 6. BASEMAP
# ---------------------------------------------------------------------------

def fetch_basemap(lon_min, lon_max, lat_min, lat_max, out_path: Path):
    """-> the BBox actually rendered (which becomes the grid's extents)."""
    from glyphviz_core import basemap as bm

    bbox = bm.BBox(lon_min, lon_max, lat_min, lat_max)
    plan = bm.plan_basemap(bbox, provider_key=BASEMAP_PROVIDER,
                           target_px=BASEMAP_TARGET_PX,
                           tile_cap=BASEMAP_TILE_CAP)
    print(f"  basemap: {plan.provider.label}  zoom {plan.zoom}  "
          f"{plan.tile_count} tiles  -> {plan.out_w}x{plan.out_h}px")

    def progress(done, total):
        if done % 10 == 0 or done == total:
            print(f"    tiles {done}/{total}", end="\r", flush=True)

    bm.build_basemap(plan, out_path, progress=progress)

    # Desaturate and darken in place. Warm cones over a full-colour
    # OpenTopoMap fight for attention — greens and browns sit right on top of
    # the humidity ramp. Grey terrain keeps the relief and the roads legible
    # while handing the whole colour channel to the data. Baked into the PNG
    # rather than done with grid alpha, so there is no blending or depth-sort
    # behaviour to go wrong; --map-alpha can still fade it further at load.
    if MAP_GREY:
        from PIL import Image, ImageEnhance
        img = Image.open(out_path).convert("RGB")
        img = Image.blend(img, img.convert("L").convert("RGB"), MAP_GREY_MIX)
        img = ImageEnhance.Brightness(img).enhance(MAP_BRIGHTNESS)
        img.save(out_path, format="PNG")
        print(f"  map {MAP_GREY_MIX:.0%} desaturated, "
              f"brightness {MAP_BRIGHTNESS}")

    print(f"  wrote {out_path.name}  ({out_path.stat().st_size/1e6:.1f} MB)")
    return plan.bbox


# ---------------------------------------------------------------------------
# 6b. DIGITAL ELEVATION MODEL
# ---------------------------------------------------------------------------

def _tile_xy(lon: float, lat: float, z: int) -> tuple[float, float]:
    """Fractional slippy-tile coordinates."""
    n = 1 << z
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def fetch_dem(lon_min, lon_max, lat_min, lat_max, zoom=DEM_ZOOM, progress=None):
    """Stitch AWS Terrarium tiles over the window and return a plate carrée
    elevation grid in metres, north-up.

    Terrarium encodes height as (R*256 + G + B/256) - 32768 metres. Each tile
    is decoded to float BEFORE anything is resampled — interpolating the raw
    RGB would mix the high and low bytes of neighbouring heights and produce
    nonsense. Free, no key, no registration.
    """
    import urllib.request
    from PIL import Image
    from glyphviz_core import basemap as bm

    # Share the app's own tile cache directory, so a rebuild re-fetches
    # nothing and a free public tile service is not hammered on every run.
    cache = bm.default_cache_dir()
    cache.mkdir(parents=True, exist_ok=True)

    tx0, ty0 = _tile_xy(lon_min, lat_max, zoom)     # north-west corner
    tx1, ty1 = _tile_xy(lon_max, lat_min, zoom)     # south-east corner
    x0, x1 = int(math.floor(tx0)), int(math.floor(tx1))
    y0, y1 = int(math.floor(ty0)), int(math.floor(ty1))
    n_x, n_y = x1 - x0 + 1, y1 - y0 + 1
    total = n_x * n_y

    canvas = np.zeros((n_y * 256, n_x * 256), dtype=np.float32)
    done = 0
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            cached = cache / f"terrarium_{zoom}_{tx}_{ty}.png"
            if cached.is_file():
                data = cached.read_bytes()
            else:
                url = DEM_TILE_URL.format(z=zoom, x=tx, y=ty)
                req = urllib.request.Request(url,
                                             headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = r.read()
                try:
                    cached.write_bytes(data)
                except OSError:
                    pass          # cache is a convenience, never a requirement
            rgb = np.asarray(Image.open(io.BytesIO(data)).convert("RGB")).astype(np.float32)
            elev = (rgb[:, :, 0] * 256.0 + rgb[:, :, 1] + rgb[:, :, 2] / 256.0) - 32768.0
            canvas[(ty - y0) * 256:(ty - y0 + 1) * 256,
                   (tx - x0) * 256:(tx - x0 + 1) * 256] = elev
            done += 1
            if progress:
                progress(done, total)
    # Flatten the sea BEFORE any averaging. The Pacific bottoms out near
    # -6,700 m in this window, and a cell straddling the coast would average
    # that against the land and punch a hole through the shoreline.
    np.maximum(canvas, 0.0, out=canvas)
    return canvas, (x0, y0, zoom)


def sample_dem(canvas, origin, lon, lat) -> float:
    """Bilinear sample of the stitched Mercator canvas at a lon/lat, in metres.

    Sampling straight out of Mercator rather than reprojecting first: the
    lookup already converts lon/lat to tile space, so the projection is handled
    exactly and no resampling error is introduced.
    """
    x0, y0, zoom = origin
    fx, fy = _tile_xy(lon, lat, zoom)
    px = (fx - x0) * 256.0
    py = (fy - y0) * 256.0
    h, w = canvas.shape
    px = min(max(px, 0.0), w - 1.001)
    py = min(max(py, 0.0), h - 1.001)
    ix, iy = int(px), int(py)
    tx, ty = px - ix, py - iy
    a = canvas[iy, ix] * (1 - tx) + canvas[iy, ix + 1] * tx
    b = canvas[iy + 1, ix] * (1 - tx) + canvas[iy + 1, ix + 1] * tx
    return float(a * (1 - ty) + b * ty)


def sample_dem_cell(canvas, origin, lon0, lon1, lat0, lat1) -> float:
    """Mean height in metres over a lon/lat rectangle.

    The mesh is far coarser than the DEM — a 120-column lattice over a
    2,816 px canvas is one vertex per ~23 px — so point-sampling picks whatever
    single pixel happens to land under each vertex and the surface comes out
    as noise: individual crags and gullies aliased into spikes, with the real
    landform lost between them. Averaging the cell is the correct
    downsample and is what makes the relief read as relief.
    """
    x0, y0, zoom = origin
    ax, ay = _tile_xy(lon0, lat1, zoom)      # lat1 = north edge -> smaller y
    bx, by = _tile_xy(lon1, lat0, zoom)
    h, w = canvas.shape
    px0 = int(max((ax - x0) * 256.0, 0)); px1 = int(min((bx - x0) * 256.0, w - 1))
    py0 = int(max((ay - y0) * 256.0, 0)); py1 = int(min((by - y0) * 256.0, h - 1))
    if px1 <= px0 or py1 <= py0:
        return sample_dem(canvas, origin, (lon0 + lon1) / 2, (lat0 + lat1) / 2)
    return float(canvas[py0:py1 + 1, px0:px1 + 1].mean())


def elev_km(metres: float) -> float:
    """Metres above sea level -> kilometres, with the ocean flattened to 0."""
    return max(metres, 0.0) / 1000.0 if metres > DEM_SEA_LEVEL_M else 0.0


# ---------------------------------------------------------------------------
# 7. SCAN MODE
# ---------------------------------------------------------------------------

def scan(frames):
    print(f"\nframes: {len(frames)}   {frames[0][0]} -> {frames[-1][0]}")
    byday = collections.defaultdict(list)
    for when, obs in frames:
        if not obs:
            continue
        offshore = sum(1 for o in obs.values() if 0 <= o.direction <= 135) / len(obs)
        dry = sum(1 for o in obs.values() if o.rh < 25) / len(obs)
        byday[when.date()].append((offshore, dry,
                                   max(o.gust for o in obs.values())))
    print(f"\n{'date':<12}{'offshore':>10}{'RH<25%':>10}{'peak gust':>11}")
    for d in sorted(byday):
        v = byday[d]
        off = sum(x[0] for x in v) / len(v) * 100
        dry = sum(x[1] for x in v) / len(v) * 100
        gust = max(x[2] for x in v)
        flag = "  <-- SANTA ANA" if off > 60 and dry > 25 else ""
        print(f"{d}  {off:8.1f}% {dry:8.1f}% {gust:8.1f} mph{flag}")


# ---------------------------------------------------------------------------
# 8. VALIDATION
# ---------------------------------------------------------------------------

def validate(df: pd.DataFrame, ch_map: pd.DataFrame, ch_tracks: pd.DataFrame
             ) -> list[str]:
    problems: list[str] = []

    if (df["id"] != range(1, len(df) + 1)).any():
        problems.append("node ids are not 1..N in order")
    ids = set(df["id"])
    for _, r in df.iterrows():
        if r["parent_id"] != 0 and r["parent_id"] not in ids:
            problems.append(f"node {r['id']} has dangling parent {r['parent_id']}")

    # A glyph accidentally authored as type 0 or 1 lands in NON_VISUAL_TYPES
    # and silently renders nothing, so count what should actually be drawable.
    from glyphviz_core.node import NON_VISUAL_TYPES
    n_world = int((df["type"] == NODE_WORLD).sum())
    if n_world != 1:
        problems.append(f"expected exactly one World row (type 0), found {n_world}")
    drawable = int((~df["type"].isin(NON_VISUAL_TYPES)).sum())
    if drawable != len(df) - 1:
        problems.append(
            f"{len(df) - 1 - drawable} node(s) beyond the World row are a "
            f"non-visual type and would render nothing")

    grids = df[df["type"] == NODE_GRID]
    if len(grids) != 1:
        problems.append(f"expected exactly one World Grid, found {len(grids)}")
    for _, g in grids.iterrows():
        if not (g["trigger_hi_x"] > g["trigger_lo_x"]
                and g["trigger_hi_y"] > g["trigger_lo_y"]):
            problems.append("grid extents are degenerate (hi <= lo)")

    # Every bound node's channel must exist in the map, and every mapped track
    # must exist as a column in the tracks table.
    mapped = set(ch_map["channel_id"])
    for cid in df.loc[df["ch_input_id"] > 0, "ch_input_id"]:
        if cid not in mapped:
            problems.append(f"ch_input_id {cid} has no ch-map entry")
    cols = set(ch_tracks.columns)
    for tid in ch_map["track_id"]:
        if f"ch{tid}" not in cols:
            problems.append(f"ch-map references missing track column ch{tid}")

    from glyphviz_core import channel_engine as ce
    for attr in sorted(set(ch_map["attribute"])):
        if attr not in ce._ATTR_TO_FIELD:
            problems.append(f"attribute {attr!r} is not bindable")

    if ch_tracks.isna().any().any():
        problems.append("ch-tracks contains NaN")

    return problems


# ---------------------------------------------------------------------------
# 9. MAIN
# ---------------------------------------------------------------------------

def main() -> int:
    global MAP_GREY, MAP_ALPHA, GUST_BEAD
    global SURFACE, SURFACE_COLS, SURFACE_VERT_EXAG, STATION_CLEARANCE
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE,
                    help="hpwren_sdge archive root")
    ap.add_argument("--month", default=MONTH_DIR)
    ap.add_argument("--out-dir", type=Path, default=HERE)
    ap.add_argument("--stride", type=int, default=1,
                    help="take every Nth frame (6 = hourly)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-basemap", action="store_true")
    ap.add_argument("--map-colour", "--map-color", dest="map_colour",
                    action="store_true",
                    help="keep the terrain map in full colour (default: grey)")
    ap.add_argument("--map-alpha", type=int, default=MAP_ALPHA,
                    help="grid alpha 0-255; lower fades the map further")
    ap.add_argument("--no-gust-bead", action="store_true",
                    help="drop the gust-factor bead at each station")
    ap.add_argument("--no-surface", action="store_true",
                    help="skip the DEM terrain mesh (flat textured grid instead)")
    ap.add_argument("--surface-res", type=int, default=SURFACE_COLS,
                    help=f"terrain lattice columns (default {SURFACE_COLS})")
    ap.add_argument("--surface-exag", type=float, default=SURFACE_VERT_EXAG,
                    help=f"terrain vertical exaggeration "
                         f"(default {SURFACE_VERT_EXAG:g}; stations use {VERT_EXAG:g})")
    ap.add_argument("--clearance", type=float, default=STATION_CLEARANCE,
                    help=f"world units to lift every station above the terrain "
                         f"(default {STATION_CLEARANCE:g})")
    ap.add_argument("--scan", action="store_true",
                    help="characterise the month and exit")
    args = ap.parse_args()

    MAP_GREY = not args.map_colour
    MAP_ALPHA = max(0, min(255, args.map_alpha))
    GUST_BEAD = not args.no_gust_bead
    SURFACE = not args.no_surface
    SURFACE_COLS = max(2, args.surface_res)
    SURFACE_VERT_EXAG = args.surface_exag
    STATION_CLEARANCE = args.clearance

    month_dir = args.archive / "station_data" / args.month
    gaz_path = args.archive / "sdge_met_locations.csv"
    if not month_dir.is_dir():
        raise SystemExit(f"Month directory not found: {month_dir}")

    print(f"Reading {month_dir} …")
    frames, stations = read_month(month_dir, stride=args.stride, limit=args.limit)
    print(f"  {len(frames)} frames, {len(stations)} stations, "
          f"{frames[0][0]} -> {frames[-1][0]}")

    if args.scan:
        scan(frames)
        return 0

    gaz = read_gazetteer(gaz_path) if gaz_path.is_file() else {}
    print(f"  gazetteer: {len(gaz)} stations")

    lons = [s["lon"] for s in stations.values()]
    lats = [s["lat"] for s in stations.values()]
    lon_pad = (max(lons) - min(lons)) * PAD_FRAC
    lat_pad = (max(lats) - min(lats)) * PAD_FRAC
    want = (min(lons) - lon_pad, max(lons) + lon_pad,
            min(lats) - lat_pad, max(lats) + lat_pad)
    print(f"  station window: lon {want[0]:.3f}..{want[1]:.3f}  "
          f"lat {want[2]:.3f}..{want[3]:.3f}")

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    media = out_dir / "media"

    have_basemap = False
    if not args.no_basemap:
        media.mkdir(exist_ok=True)
        try:
            bbox = fetch_basemap(*want, media / "01_sdcounty_terrain.png")
            want = (bbox.lon_min, bbox.lon_max, bbox.lat_min, bbox.lat_max)
            have_basemap = True
        except Exception as exc:
            print(f"  basemap fetch failed ({exc}); continuing without it")

    layout = make_layout(*want)
    print(f"  layout: plate {2*layout.half_w:.1f} x {2*layout.half_h:.1f} units, "
          f"scale ({layout.scale_x}, {layout.scale_y}, {layout.scale_z}), "
          f"vertical exaggeration {VERT_EXAG}x")

    sig = signature_frame(frames)
    print(f"  signature frame: {sig} of {len(frames)} — {frames[sig][0]} "
          f"(authored into the node CSV as the scene's resting pose)")

    dem = dem_origin = None
    if SURFACE:
        def dem_progress(done, total):
            if done % 10 == 0 or done == total:
                print(f"    DEM tiles {done}/{total}", end="\r", flush=True)
        try:
            print(f"  fetching DEM (AWS Terrarium, zoom {DEM_ZOOM}) …")
            dem, dem_origin = fetch_dem(*want, progress=dem_progress)
            print(f"\n  DEM {dem.shape[1]}x{dem.shape[0]} px, "
                  f"{dem.min():.0f}..{dem.max():.0f} m")
        except Exception as exc:
            print(f"\n  DEM fetch failed ({exc}); continuing without terrain")
            dem = dem_origin = None

    (df, station_channel, bead_channel, cursor_ch, clock_channels,
     notes) = build_scene(frames, stations, gaz, layout, have_basemap, sig,
                          dem, dem_origin,
                          media / "01_sdcounty_terrain.png" if have_basemap else None)
    ch_map, ch_tracks = build_channels(
        frames, stations, station_channel, bead_channel, cursor_ch,
        clock_channels, layout)

    problems = validate(df, ch_map, ch_tracks)
    if problems:
        print("\nVALIDATION FAILED:")
        for p in problems:
            print("  -", p)
        return 1

    node_path = out_dir / f"{OUT_STEM}_gv_node.csv"
    map_path = out_dir / f"{OUT_STEM}_gv_ch-map.csv"
    trk_path = out_dir / f"{OUT_STEM}_gv_ch-tracks.csv"
    df.to_csv(node_path, index=False)
    ch_map.to_csv(map_path, index=False)
    ch_tracks.to_csv(trk_path, index=False)

    print(f"\nWrote:")
    for p in (node_path, map_path, trk_path):
        print(f"  {p.name:<34} {p.stat().st_size/1e6:8.2f} MB")
    print(f"\n  {len(df)} nodes, {len(station_channel)} animated stations, "
          f"{len(ch_tracks.columns)-1} tracks, {len(ch_tracks)} frames")
    for n in notes:
        print(f"  note: {n}")
    print("\nOpen the node CSV in GlyphViz (File > Open) with media/ alongside it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
