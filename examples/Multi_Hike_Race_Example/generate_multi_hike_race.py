#!/usr/bin/env python3
"""
generate_multi_hike_race.py
=============================
A "ghost race" demo: Jeff's 3 fastest and 3 slowest recorded hikes up
Cowles Mountain (San Diego, CA), animated simultaneously on the real DEM
terrain from Surface_Example. Two separate glyph families per hike, deliberately
decoupled (per Jeff's design correction -- v1 wrongly nested the dashboard
under the climber):
  - a bare GEO_PIN climber, GPS-driven up the real terrain, carrying only its
    date/time/stat tag -- no children.
  - a "dashboard" anchor sitting off to the side of the mountain entirely,
    holding 3 stat satellites (total time, max HR, avg HR) and 3 large
    TOPO_PLOT panels (elevation, heart rate, pace) as children, each with a
    needle sibling that traverses it in sync with its climber's real-time
    position -- the visible link between "where on the mountain" and
    "physiological state at that moment".
Fast hikes (warm palette) summit and freeze early; slow hikes (cool palette)
are still climbing.

Source data (NOT checked into this repo -- Jeff's personal Strava export,
read from --data-dir at generation time only; only the derived per-frame
positions/values below are committed):
  <data-dir>/cowles_mountain_matches.csv   158 candidate Cowles hikes
  <data-dir>/all_hikes_list.csv            HR summary stats per hike id
  <data-dir>/hike_<id>_streams.csv          per-sample lat/lon/altitude/HR/velocity

Geo-registration
----------------
The Surface_Example DEM/aerial JPGs carry no lat/lon extent, so the real
GPS tracks are registered onto that pixel grid with a 2-point similarity
transform (rotation + uniform scale + translation, solved via complex
arithmetic from 2 lat/lon<->pixel correspondences -- exact for 2 points,
not a least-squares fit). Anchors used (confirmed against
hike_2674068909_streams.csv and Jeff's visual ID of the trailhead):
  trailhead: lat/lon (32.825471, -117.021868) <-> pixel (250, 110)
  summit:    lat/lon (32.812849, -117.032018) <-> pixel (139, 300)
            (480.3m recorded altitude -- matches Cowles' known ~1593ft/485m
            summit, a good sanity check that the anchor pick is right)

A climber's world Z comes from sampling the DEM's own grayscale at its
registered pixel (glued to the rendered terrain surface, immune to
barometric GPS altitude drift) -- NOT from the GPS altitude stream, which
is reserved for what it's actually for: the elevation plot/needle, where
the real recorded value matters more than surface-snapping.

Shared timeline
---------------
All 6 hikes resample onto one common real-elapsed-minutes grid (1800
frames = 60s at the app's default 30fps Channels playback), spanning
0..max(elapsed_minutes) across the 6 selected hikes. Hikes that finish
early simply freeze (clip the query time to that hike's own duration
before interpolating) rather than zero-padding -- so fast climbers visibly
stop at the summit while slow ones are still en route. This is the literal
"race" framing: position on the mountain at a given frame reflects each
hike's real pace, not a duration-normalized percentage.

Plot/needle convention (matching Topology_Example's Plot topology: raw
Cartesian, x=time-like axis, z=value axis): each dashboard lays its 3 plots
out side by side along LOCAL X, in the same order and at the same fixed
offsets for every hike (PLOT_X_OFFSETS: elevation 0, heart rate 105, pace 210;
PLOT_WIDTH=100 -- doubled from Jeff's original suggestion of 50 for
readability), each panel x = elevation minutes scaled to a shared
0..PLOT_WIDTH range (so a slower hike's curve is visibly longer, not just
normalized), z = the metric normalized 0..
PLOT_HEIGHT across all 6 hikes so panels are comparable. Because every
dashboard uses identical local offsets and differs only in its own Y
placement (see "Dashboard layout" below), the same metric's panel always
occupies the same (X, Z) band -- "lining up" the 6 heart-rate plots (or
elevation, or pace) is just a matter of scanning across Y at that band, no
per-metric alignment math needed at view time.

The needle for each plot is a sibling of that plot node (a child of the
dashboard, not the plot) whose per-frame track values are precomputed as the
plot's own fixed local offset + the current data point's local (x, z) --
giving the "jumps along the same coordinates as the plot children" behavior
without any engine change, since the offset is baked in at generation time.

Dashboard layout
----------------
6 dashboards distributed along world Y (per Jeff: a horizontal row of
panels reads more intuitively for comparison than a vertical tower),
starting well clear of the terrain's footprint -- TERRAIN_SCALE=10 puts the
mountain at roughly X:-190..190, Y:-180..180, so DASHBOARD_X0=220 sits
outside that. Dashboard i is at (DASHBOARD_X0, i * DASHBOARD_Y_SPACING,
DASHBOARD_Z0), fastest hike nearest Y=0, slowest farthest out. With
PLOT_WIDTH=100 x 3 panels this is a genuinely large structure (worth knowing
before orbiting around to find it).

Terrain scale
-------------
The terrain's native grid (1 grid-index unit = 1 world unit, per
Surface_Example) renders ~10x smaller than the PLOT_WIDTH=100 dashboards --
per Jeff, scale the mountain up rather than shrink the plots down. The
terrain root's own scale_x/y/z is set to TERRAIN_SCALE=10 (cascades onto
every terrain child's translate+scale for free); the climber, being a
separate top-level node rather than a terrain child, has its geo-registered
grid position/height multiplied by the same TERRAIN_SCALE explicitly so it
stays glued to the now-larger mesh.

Output files (written to OUTPUT_DIR)
-------------------------------------
  {PREFIX}_gv_node.csv       terrain mesh (from Surface_Example's DEM/aerial
                              JPGs, duplicated here for a self-contained load)
                              + 6 climbers (on the mountain) + 6 dashboards
                              (distributed along Y, off to the side)
  {PREFIX}_gv_tag.csv        per-climber date/time/stats label + per-dashboard
                              identifying label + per-stat-satellite label
  {PREFIX}_gv_ch-map.csv     channel -> attribute bindings (climbers + needles)
  {PREFIX}_gv_ch-tracks.csv  1800 frames x 54 tracks

Usage
-----
  python generate_multi_hike_race.py
  python generate_multi_hike_race.py --data-dir "C:/Jeff/python/strava/strava_hikes_data"

Load in GlyphViz: File > Open Node CSV -> {PREFIX}_gv_node.csv
"""

import argparse
import colorsys
import csv
from pathlib import Path

import numpy as np
import pandas as pd
from PySide6.QtGui import QImage

OUTPUT_DIR = Path(__file__).parent
PREFIX = "Multi_Hike_Race_Example"
SURFACE_DIR = OUTPUT_DIR.parent / "Surface_Example"
DEM_JPG = SURFACE_DIR / "cowles_dem_lowres.jpg"
AERIAL_JPG = SURFACE_DIR / "cowles_aerial_lowres.jpg"

DEFAULT_DATA_DIR = Path(r"C:\Jeff\python\strava\strava_hikes_data")

TOPO_NONE = 0
TOPO_PIN = 5
TOPO_PLOT = 16
TOPO_SURFACE = 17

GEO_CUBE_WIRE, GEO_CUBE = 0, 1
GEO_OCTA_WIRE, GEO_OCTA = 10, 11
GEO_PIN, GEO_PIN_WIRE = 16, 17
GEO_POINT = 22

# The app's default Global Scale (Scene.base_scale) changed 3.0 -> 1.0 after
# this example's node sizes were originally tuned, which shrinks every
# regular-mesh glyph's rendered size 3x (Point-topology markers are exempt --
# their on-screen size comes from `ratio`, not `scale`, see geometry.py).
# Multiplying the affected scale constants below by NODE_SIZE_SCALE restores
# the originally-tuned proportions under the new default.
NODE_SIZE_SCALE = 3.0

NEEDLE_SCALE = 1.0 * NODE_SIZE_SCALE   # Jeff: the v4 needles (scale 1.2, GEO_POINT) were "nearly impossible to see";
                      # 4.0 (GEO_OCTA) turned out way too large at normal viewing distance -- 1.0 (pre-NODE_SIZE_SCALE) is right
NEEDLE_COLOR = (255, 255, 255)  # white -- same-as-hike-color made it low-contrast against its own plot line

# Terrain (must match Surface_Example/generate_surface_example.py's grid math
# exactly so the registered GPS pixels land in the same grid-coordinate space
# -- TERRAIN_SCALE is then applied uniformly on top, see below).
STRIDE = 10
EXAGGERATION = 12.0
TERRAIN_CHILD_SCALE = 0.15

# The terrain's native grid (1 grid-index unit = 1 world unit) renders ~10x
# smaller than the PLOT_WIDTH=50 dashboards Jeff wants to keep -- per Jeff,
# scale the mountain up rather than shrink the plots down. The terrain ROOT's
# own scale_x/y/z cascades onto every terrain child's translate+scale for
# free (same mechanism that bit the dashboard scale earlier), so only the
# root's scale needs to change there; the climber is a separate top-level
# node (not a terrain child), so its geo-registered grid position/height are
# multiplied by this same factor explicitly in the per-hike loop below.
TERRAIN_SCALE = 10.0

# Geo-registration anchors (see module docstring).
ANCHOR_TRAILHEAD_LATLON = (32.825471, -117.021868)
ANCHOR_TRAILHEAD_PIXEL = (250.0, 110.0)
ANCHOR_SUMMIT_LATLON = (32.812849, -117.032018)
ANCHOR_SUMMIT_PIXEL = (139.0, 300.0)

N_FAST = 3                # trimmed from 10 -- 6 hikes total reads more clearly and performs
N_SLOW = 3                # better on average machines than the original 20
N_FRAMES = 1800           # 60s at the app's default 30fps Channels playback
PLOT_POINTS = 50          # static points per plot polyline
PLOT_WIDTH = 100.0        # doubled from Jeff's original 50 for readability
PLOT_GAP = 5.0            # gap between consecutive panels along local X -- unchanged, still fine
PLOT_HEIGHT = 30.0
PLOT_X_OFFSETS = {
    "elevation": 0.0,
    "heartrate": PLOT_WIDTH + PLOT_GAP,
    "pace": 2 * (PLOT_WIDTH + PLOT_GAP),
}
CLIMBER_SCALE = 0.4 * TERRAIN_SCALE * NODE_SIZE_SCALE   # keep the same relative prominence on the now-bigger mountain
PACE_CLIP_MIN_KMH = 2.0   # clip absurd instantaneous pace spikes (near-stops)
PACE_CLIP_MAX_MIN_KM = 30.0

# Dashboard placement: clear of the terrain's footprint (mountain now spans
# roughly X:-190..190, Y:-180..180 at TERRAIN_SCALE=10), distributed along Y
# (per Jeff: horizontal comparison reads more intuitively than a vertical
# tower) -- fastest hike's dashboard nearest Y=0, slowest farthest out. All
# dashboards share the same X/Z, so every metric's panel sits at the same
# (X-band, Z-band) on every dashboard -- aligned for horizontal scanning.
DASHBOARD_X0 = 220.0
DASHBOARD_Y_SPACING = 40.0
DASHBOARD_Z0 = 0.0
STAT_OFFSETS = [(-10.0, -4.0, 0.0), (-10.0, 0.0, 0.0), (-10.0, 4.0, 0.0)]  # before the plot row

NODE_ID_BLOCK = 250        # ids reserved per hike (climber+dashboard+stats+plots+points+needles)


# ===========================================================================
# Geo-registration: 2-point similarity transform (lat/lon -> DEM pixel)
# ===========================================================================

def build_geo_transform():
    """Returns a function mapping (lat, lon) -> (pixel_x, pixel_y), exact at
    the two anchor points, via a complex-number similarity transform (no
    shear -- 2 points fully determine rotation+scale+translation)."""
    lat0, lon0 = ANCHOR_TRAILHEAD_LATLON
    lat1, lon1 = ANCHOR_SUMMIT_LATLON
    cos_ref = np.cos(np.radians(lat0))

    def to_local(lat, lon):
        return (lon - lon0) * cos_ref + 1j * (lat - lat0)

    local1 = to_local(lat1, lon1)
    px0 = complex(*ANCHOR_TRAILHEAD_PIXEL)
    px1 = complex(*ANCHOR_SUMMIT_PIXEL)

    a = (px1 - px0) / local1
    b = px0

    def latlon_to_pixel(lat, lon):
        p = a * to_local(lat, lon) + b
        return p.real, p.imag

    return latlon_to_pixel


def pixel_to_grid(px, py, n_cols, n_rows):
    """Matches Surface_Example/generate_surface_example.py's centered,
    row-flipped grid-index convention exactly (continuous, not snapped)."""
    x_off = -(n_cols - 1) / 2.0
    y_off = -(n_rows - 1) / 2.0
    ci = px / STRIDE
    ri = py / STRIDE
    gx = ci + x_off
    gy = (n_rows - 1 - ri) + y_off
    return gx, gy


def sample_dem_height(dem: QImage, px, py, exaggeration=EXAGGERATION):
    x = int(round(min(max(px, 0), dem.width() - 1)))
    y = int(round(min(max(py, 0), dem.height() - 1)))
    c = dem.pixelColor(x, y)
    gray = (c.red() + c.green() + c.blue()) / 3.0
    return (gray / 255.0) * exaggeration


# ===========================================================================
# Color palette: warm family (fast) / cool family (slow)
# ===========================================================================

def build_palette(n_fast, n_slow):
    colors = []
    for i in range(n_fast):
        hue = 0.02 + 0.10 * (i / max(n_fast - 1, 1))   # red -> orange/yellow
        r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 1.0)
        colors.append((int(r * 255), int(g * 255), int(b * 255)))
    for i in range(n_slow):
        hue = 0.55 + 0.20 * (i / max(n_slow - 1, 1))   # cyan -> blue/violet
        r, g, b = colorsys.hsv_to_rgb(hue, 0.75, 0.95)
        colors.append((int(r * 255), int(g * 255), int(b * 255)))
    return colors


# ===========================================================================
# Hike selection + resampling
# ===========================================================================

def select_hikes(data_dir: Path, n_fast: int, n_slow: int) -> pd.DataFrame:
    matches = pd.read_csv(data_dir / "cowles_mountain_matches.csv")
    matches = matches[matches["has_gps"]].copy()

    def stream_path(hike_id):
        cleaned = data_dir / f"hike_{hike_id}_streams_CLEANED.csv"
        plain = data_dir / f"hike_{hike_id}_streams.csv"
        if cleaned.exists():
            return cleaned
        if plain.exists():
            return plain
        return None

    matches["stream_path"] = matches["id"].map(stream_path)
    matches = matches[matches["stream_path"].notna()].copy()
    matches = matches.sort_values("elapsed_minutes").reset_index(drop=True)

    fast = matches.head(n_fast).copy()
    fast["group"] = "fast"
    slow = matches.tail(n_slow).copy()
    slow["group"] = "slow"
    selected = pd.concat([fast, slow], ignore_index=True)

    hr_list = data_dir / "all_hikes_list.csv"
    if hr_list.exists():
        hr_df = pd.read_csv(hr_list)[["id", "average_heartrate", "max_heartrate"]]
        selected = selected.merge(hr_df, on="id", how="left")
    else:
        selected["average_heartrate"] = np.nan
        selected["max_heartrate"] = np.nan

    print(f"Selected {len(fast)} fastest + {len(slow)} slowest hikes "
          f"({selected['elapsed_minutes'].min():.1f}-{selected['elapsed_minutes'].max():.1f} min)")
    return selected


def resample_hike(stream_path: Path, common_time_grid: np.ndarray) -> dict:
    """Interpolates one hike's stream onto the shared real-elapsed-minutes
    grid, freezing (clipping query time) past the hike's own duration."""
    df = pd.read_csv(stream_path)
    t = df["time_minutes"].values
    t_max = t.max()
    t_query = np.minimum(common_time_grid, t_max)

    lat = np.interp(t_query, t, df["latitude"].values)
    lon = np.interp(t_query, t, df["longitude"].values)
    elev = np.interp(t_query, t, df["altitude_meters"].values)

    if "heartrate_bpm" in df.columns and df["heartrate_bpm"].notna().any():
        hr_series = df["heartrate_bpm"].ffill().bfill().values
    else:
        hr_series = np.zeros(len(df))
    hr = np.interp(t_query, t, hr_series)

    vel_kmh = np.interp(t_query, t, df["velocity_mps"].values) * 3.6
    vel_kmh_clipped = np.maximum(vel_kmh, PACE_CLIP_MIN_KMH)
    pace_min_km = np.minimum(60.0 / vel_kmh_clipped, PACE_CLIP_MAX_MIN_KM)

    return {
        "t_minutes": t_query, "lat": lat, "lon": lon,
        "elevation": elev, "heartrate": hr, "pace": pace_min_km,
        "duration_min": t_max,
    }


# ===========================================================================
# Node/tag/channel writers
# ===========================================================================

NODE_FIELDS = [
    "id", "type", "parent_id", "branch_level",
    "translate_x", "translate_y", "translate_z",
    "rotate_x", "rotate_y", "rotate_z",
    "scale_x", "scale_y", "scale_z",
    "color_r", "color_g", "color_b", "color_a",
    "geometry", "hide", "topo", "ratio", "ch_input_id",
]


def base_row(node_id, parent_id, branch_level, tx, ty, tz, scale, color, geometry,
             topo=TOPO_NONE, ch_input_id=0, ratio=0.1):
    r, g, b = color
    return {
        "id": node_id, "type": 5, "parent_id": parent_id, "branch_level": branch_level,
        "translate_x": round(tx, 4), "translate_y": round(ty, 4), "translate_z": round(tz, 4),
        "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
        "scale_x": scale, "scale_y": scale, "scale_z": scale,
        "color_r": r, "color_g": g, "color_b": b, "color_a": 255,
        "geometry": geometry, "hide": 0, "topo": topo, "ratio": ratio,
        "ch_input_id": ch_input_id,
    }


def build_terrain_nodes(dem: QImage, aerial: QImage):
    """Inlined from Surface_Example/generate_surface_example.py (kept in
    lockstep with STRIDE/EXAGGERATION above) so this example loads as one
    self-contained file."""
    w, h = dem.width(), dem.height()
    rows_px = list(range(0, h, STRIDE))
    cols_px = list(range(0, w, STRIDE))
    n_cols, n_rows = len(cols_px), len(rows_px)
    x_off = -(n_cols - 1) / 2.0
    y_off = -(n_rows - 1) / 2.0

    nodes = [{
        "id": 1, "type": 5, "parent_id": 0, "branch_level": 0,
        "translate_x": 0.0, "translate_y": 0.0, "translate_z": 0.0,
        "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
        # TERRAIN_SCALE cascades onto every child's translate+scale below for
        # free (see the constant's comment) -- this is the only place the
        # mountain's overall size is controlled.
        "scale_x": TERRAIN_SCALE, "scale_y": TERRAIN_SCALE, "scale_z": TERRAIN_SCALE,
        "color_r": 128, "color_g": 128, "color_b": 128, "color_a": 255,
        "geometry": GEO_POINT, "hide": 0, "topo": TOPO_SURFACE, "ratio": 0.1,
        "ch_input_id": 0,
    }]
    next_id = 2
    for ri, y in enumerate(rows_px):
        for ci, x in enumerate(cols_px):
            dem_c = dem.pixelColor(x, y)
            gray = (dem_c.red() + dem_c.green() + dem_c.blue()) / 3.0
            tz = (gray / 255.0) * EXAGGERATION
            aerial_c = aerial.pixelColor(x, y)
            nodes.append({
                "id": next_id, "type": 5, "parent_id": 1, "branch_level": 1,
                "translate_x": round(ci + x_off, 4),
                "translate_y": round((n_rows - 1 - ri) + y_off, 4),
                "translate_z": round(tz, 4),
                "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
                "scale_x": TERRAIN_CHILD_SCALE, "scale_y": TERRAIN_CHILD_SCALE, "scale_z": TERRAIN_CHILD_SCALE,
                "color_r": aerial_c.red(), "color_g": aerial_c.green(), "color_b": aerial_c.blue(), "color_a": 255,
                "geometry": GEO_POINT, "hide": 0, "topo": 0, "ratio": 0.1,
                "ch_input_id": 0,
            })
            next_id += 1
    return nodes, next_id, n_cols, n_rows


def normalize(values_by_hike: dict, key: str):
    all_vals = np.concatenate([v[key] for v in values_by_hike.values()])
    return float(np.nanmin(all_vals)), float(np.nanmax(all_vals))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR,
                         help=f"directory with cowles_mountain_matches.csv / hike_<id>_streams.csv (default {DEFAULT_DATA_DIR})")
    args = parser.parse_args()

    dem = QImage(str(DEM_JPG))
    aerial = QImage(str(AERIAL_JPG))
    if dem.isNull() or aerial.isNull():
        raise SystemExit(f"Could not load {DEM_JPG} / {AERIAL_JPG}")

    selected = select_hikes(args.data_dir, N_FAST, N_SLOW)
    palette = build_palette(N_FAST, N_SLOW)
    latlon_to_pixel = build_geo_transform()

    print("\nResampling hikes onto shared real-elapsed-time grid...")
    common_max_minutes = float(selected["elapsed_minutes"].max())
    common_time_grid = np.linspace(0.0, common_max_minutes, N_FRAMES)

    resampled = {}
    for _, hike in selected.iterrows():
        resampled[hike["id"]] = resample_hike(Path(hike["stream_path"]), common_time_grid)

    elev_min, elev_max = normalize(resampled, "elevation")
    hr_min, hr_max = normalize(resampled, "heartrate")
    pace_min, pace_max = normalize(resampled, "pace")
    print(f"  elevation {elev_min:.0f}-{elev_max:.0f}m, HR {hr_min:.0f}-{hr_max:.0f}bpm, "
          f"pace {pace_min:.1f}-{pace_max:.1f} min/km")

    print("\nBuilding terrain mesh (Surface_Example DEM)...")
    nodes, next_id, n_cols, n_rows = build_terrain_nodes(dem, aerial)
    print(f"  {len(nodes)} terrain nodes")

    tags = []
    ch_map_rows = []
    ch_track_cols: dict[int, np.ndarray] = {}

    def metric_xz(values, t_minutes, lo, hi, x_offset):
        x = x_offset + (t_minutes / common_max_minutes) * PLOT_WIDTH
        z = ((values - lo) / (hi - lo)) * PLOT_HEIGHT
        return x, z

    for hike_idx, (_, hike) in enumerate(selected.iterrows()):
        hike_id = int(hike["id"])
        data = resampled[hike_id]
        color = palette[hike_idx]
        base = next_id + hike_idx * NODE_ID_BLOCK
        # id layout within this hike's NODE_ID_BLOCK-sized slot:
        #   base+0  climber (on the mountain)
        #   base+10 dashboard root (off to the side)
        #   base+11..13  stat satellites (children of dashboard)
        #   base+20..   plot panels + their PLOT_POINTS polyline children
        #   base+230..232 needles (kept clear of the plot/point id range above)
        climber_id = base
        dashboard_id = base + 10
        ch_climber = 10 * hike_idx + 1
        ch_needle = {"elevation": 10 * hike_idx + 2, "heartrate": 10 * hike_idx + 3, "pace": 10 * hike_idx + 4}
        track_climber = {"x": 9 * hike_idx, "y": 9 * hike_idx + 1, "z": 9 * hike_idx + 2}
        track_needle = {
            "elevation": (9 * hike_idx + 3, 9 * hike_idx + 4),
            "heartrate": (9 * hike_idx + 5, 9 * hike_idx + 6),
            "pace": (9 * hike_idx + 7, 9 * hike_idx + 8),
        }

        # --- climber: bare pin, GPS-driven up the real terrain, no children ---
        px, py = latlon_to_pixel(data["lat"], data["lon"])
        gx, gy = pixel_to_grid(px, py, n_cols, n_rows)
        gz = np.array([sample_dem_height(dem, px[i], py[i]) for i in range(len(px))])
        # The climber is a top-level node, not a terrain child, so it doesn't
        # inherit the terrain root's TERRAIN_SCALE cascade automatically --
        # apply the same factor explicitly so it stays glued to the mesh.
        gx, gy, gz = gx * TERRAIN_SCALE, gy * TERRAIN_SCALE, gz * TERRAIN_SCALE
        ch_track_cols[track_climber["x"]] = gx
        ch_track_cols[track_climber["y"]] = gy
        ch_track_cols[track_climber["z"]] = gz

        nodes.append(base_row(
            climber_id, 0, 0, gx[0], gy[0], gz[0], CLIMBER_SCALE, color,
            GEO_PIN, topo=TOPO_NONE, ch_input_id=ch_climber,
        ))
        ch_map_rows.append({"id": len(ch_map_rows), "channel_id": ch_climber,
                             "track_id": track_climber["x"], "attribute": "translate_x",
                             "track_table_id": 0, "ch_map_table_id": 0, "record_id": 0})
        ch_map_rows.append({"id": len(ch_map_rows), "channel_id": ch_climber,
                             "track_id": track_climber["y"], "attribute": "translate_y",
                             "track_table_id": 0, "ch_map_table_id": 0, "record_id": 0})
        ch_map_rows.append({"id": len(ch_map_rows), "channel_id": ch_climber,
                             "track_id": track_climber["z"], "attribute": "translate_z",
                             "track_table_id": 0, "ch_map_table_id": 0, "record_id": 0})

        total_min = float(hike["elapsed_minutes"])
        max_hr = float(hike["max_heartrate"]) if pd.notna(hike.get("max_heartrate")) else float(np.nanmax(data["heartrate"]))
        avg_hr = float(hike["average_heartrate"]) if pd.notna(hike.get("average_heartrate")) else float(np.nanmean(data["heartrate"]))

        date_str = str(hike["date"])[:16]
        tags.append({
            "id": len(tags), "table_id": 0, "record_id": climber_id,
            "title": f"{hike['group'].upper()} #{hike_idx + 1}: {date_str}  "
                     f"{total_min:.0f}min  avgHR {avg_hr:.0f}  maxHR {max_hr:.0f}",
        })

        # --- dashboard: separate anchor off to the side, distributed along Y
        # (per Jeff: horizontal comparison reads more intuitively than a
        # vertical tower) ---
        # NOTE: scale must stay 1.0 -- the engine cascades a parent's own
        # scale onto its children's local-offset translates (same mechanism
        # as Surface_Example's terrain root), so anything else here would
        # silently shrink/grow PLOT_WIDTH/PLOT_X_OFFSETS away from the literal
        # world-unit values Jeff specified.
        dash_x, dash_y, dash_z = DASHBOARD_X0, hike_idx * DASHBOARD_Y_SPACING, DASHBOARD_Z0
        nodes.append(base_row(
            dashboard_id, 0, 0, dash_x, dash_y, dash_z, 1.0, color, GEO_PIN,
        ))
        tags.append({
            "id": len(tags), "table_id": 0, "record_id": dashboard_id,
            "title": f"{hike['group']} #{hike_idx + 1}: {str(hike['date'])[:10]}",
        })

        # --- stat satellites (static: total time / max HR / avg HR) ---
        # Cube size encodes the normalized value at a glance; the tag gives
        # the literal label + number, since size/position alone (per Jeff's
        # feedback on v2) didn't make it clear what each cube represented.
        stats = [
            ("Total time", f"{total_min:.0f} min", total_min / 150.0, base + 11),
            ("Max HR", f"{max_hr:.0f} bpm", max_hr / 200.0, base + 12),
            ("Avg HR", f"{avg_hr:.0f} bpm", avg_hr / 200.0, base + 13),
        ]
        for (sx, sy, sz), (label, value_str, frac, stat_id) in zip(STAT_OFFSETS, stats):
            stat_scale = max(0.05, min(0.6, frac)) * 5.0 * NODE_SIZE_SCALE
            nodes.append(base_row(
                stat_id, dashboard_id, 1, sx, sy, sz, stat_scale, color, GEO_CUBE,
            ))
            tags.append({
                "id": len(tags), "table_id": 0, "record_id": stat_id,
                "title": f"{label}: {value_str}",
            })

        # --- plot panels + needles (per metric), laid out side by side along
        # local X at identical offsets for every dashboard, so the same metric
        # always occupies the same X band across all 6 stacked dashboards ---
        metrics = {
            "elevation": (data["elevation"], elev_min, elev_max),
            "heartrate": (data["heartrate"], hr_min, hr_max),
            "pace": (data["pace"], pace_min, pace_max),
        }
        point_id = base + 20
        for metric_name, (values, lo, hi) in metrics.items():
            x_offset = PLOT_X_OFFSETS[metric_name]
            plot_id = point_id
            point_id += 1
            nodes.append(base_row(
                plot_id, dashboard_id, 1, 0.0, 0.0, 0.0, 1.0, color, GEO_POINT,
                topo=TOPO_PLOT, ratio=0.1,
            ))

            # static polyline: PLOT_POINTS samples evenly across this hike's
            # own duration (shared time scale, so a slower hike's curve is
            # visibly longer on the same panel).
            t_static = np.linspace(0.0, data["duration_min"], PLOT_POINTS)
            v_static = np.interp(t_static, data["t_minutes"], values)
            x_static, z_static = metric_xz(v_static, t_static, lo, hi, x_offset)
            for px_i, pz_i in zip(x_static, z_static):
                nodes.append(base_row(
                    point_id, plot_id, 2, px_i, 0.0, pz_i, 0.6, color, GEO_POINT, ratio=0.04,
                ))
                point_id += 1

            # needle: sibling of the plot node (child of the dashboard), tracks =
            # the metric's per-frame local (x, z) -- "same coordinates as the
            # plot children", baked in at generation time via x_offset above.
            x_anim, z_anim = metric_xz(values, data["t_minutes"], lo, hi, x_offset)
            tx_id, tz_id = track_needle[metric_name]
            ch_track_cols[tx_id] = x_anim
            ch_track_cols[tz_id] = z_anim
            needle_id = base + 230 + list(metrics.keys()).index(metric_name)
            nodes.append(base_row(
                needle_id, dashboard_id, 1, x_anim[0], 0.0, z_anim[0],
                NEEDLE_SCALE, NEEDLE_COLOR, GEO_OCTA, ch_input_id=ch_needle[metric_name],
            ))
            ch_map_rows.append({"id": len(ch_map_rows), "channel_id": ch_needle[metric_name],
                                 "track_id": tx_id, "attribute": "translate_x",
                                 "track_table_id": 0, "ch_map_table_id": 0, "record_id": 0})
            ch_map_rows.append({"id": len(ch_map_rows), "channel_id": ch_needle[metric_name],
                                 "track_id": tz_id, "attribute": "translate_z",
                                 "track_table_id": 0, "ch_map_table_id": 0, "record_id": 0})

    # --- write files ---
    node_path = OUTPUT_DIR / f"{PREFIX}_gv_node.csv"
    with open(node_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=NODE_FIELDS)
        w.writeheader()
        w.writerows(nodes)
    print(f"\n{node_path.name}: {len(nodes)} nodes")

    tag_path = OUTPUT_DIR / f"{PREFIX}_gv_tag.csv"
    with open(tag_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "table_id", "record_id", "title"])
        w.writeheader()
        w.writerows(tags)
    print(f"{tag_path.name}: {len(tags)} labels")

    ch_map_path = OUTPUT_DIR / f"{PREFIX}_gv_ch-map.csv"
    with open(ch_map_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "channel_id", "track_id", "attribute",
                                          "track_table_id", "ch_map_table_id", "record_id"])
        w.writeheader()
        w.writerows(ch_map_rows)
    print(f"{ch_map_path.name}: {len(ch_map_rows)} channel mappings")

    track_ids = sorted(ch_track_cols.keys())
    track_cols = [f"ch{tid}" for tid in track_ids]
    ch_tracks_path = OUTPUT_DIR / f"{PREFIX}_gv_ch-tracks.csv"
    with open(ch_tracks_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cyclecount"] + track_cols)
        stacked = np.column_stack([ch_track_cols[tid] for tid in track_ids])
        for frame_idx in range(N_FRAMES):
            w.writerow([frame_idx] + [round(float(v), 5) for v in stacked[frame_idx]])
    print(f"{ch_tracks_path.name}: {N_FRAMES} frames x {len(track_ids)} tracks")

    print(f"\nDone. Open GlyphViz, then: File > Open Node CSV -> {node_path.name}")


if __name__ == "__main__":
    main()
