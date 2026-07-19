#!/usr/bin/env python3
"""
build_sd_quake_scene.py — GlyphViz World Grid + Channels exemplar
=================================================================

Fetches the USGS earthquake catalog for the San Diego city region and builds
a two-World-Grid GlyphViz scene with a Channels time-replay animation:

  * Grid A — whole-earth reference map at the origin, textured with the
    NASA Blue Marble equirectangular image (media/01_bluemarble.png).
  * Grid B — the San Diego region, scaled up to dominate the scene,
    hovering directly above its own footprint on the world map, textured
    with the georeferenced aerial mosaic (media/02_sandiego_aerial.png).
  * A footprint rectangle on the world map (4 corner glyphs + 4 Link
    edges) marking the region Grid B covers, plus 4 Link edges rising
    from those corners to Grid B's corners — the classic cartographic
    "inset zoom" callout, lifted into a true 3D frustum.
  * Earthquake hypocenters as children of Grid B: longitude/latitude from
    the catalog, depth hanging *beneath* the aerial plate (translate_z =
    -depth_km, vertically exaggerated by the grid's scale_z knob),
    magnitude encoded as glyph size AND a cold-to-hot color gradient,
    with inline labels for M >= LABEL_MIN_MAG and a U-key link to each
    event's USGS page.
  * CHANNELS TIME REPLAY — one animation frame per calendar month. Every
    hypocenter is born invisible (color_a 0), flashes to 255 the month it
    happened, then settles to a dim "memory" alpha; in the final seconds
    of the loop the whole catalog relights to full brightness before the
    cycle restarts. A timeline bar with decade ticks runs along the south
    edge of the world map, and a spinning cursor sweeps it via a
    translate_x channel. Playback OFF (or Stop) shows the complete static
    catalog — the channel files only ever *animate* the CSV's values.

    Channel compression: events sharing a birth month share one channel
    (one color_a track), so ~630 animated nodes need only ~250 channels
    plus 1 for the cursor — the pattern documented in
    glyphviz-skill/references/channels-animation.md.

Data source: USGS FDSN Event Web Service (public domain)
    https://earthquake.usgs.gov/fdsnws/event/1/
    Queried with format=csv, a lat/lon bounding box, and paged with
    offset when a count-first probe reports more than PAGE_SIZE events.
    A live fetch also snapshots the tidied catalog to data/usgs_catalog.csv
    so the scene can be rebuilt offline (--offline data/usgs_catalog.csv).

Usage:
    python build_sd_quake_scene.py                     # live fetch, build
    python build_sd_quake_scene.py --start 1980-01-01 --min-mag 1.0
    python build_sd_quake_scene.py --offline data/usgs_catalog.csv
    python build_sd_quake_scene.py --structure-only    # grids + callout only

Requires: pandas, requests (pip install pandas requests)
"""

from __future__ import annotations

import argparse
import io
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

try:
    import requests
except ImportError:  # requests only needed for live fetching
    requests = None

# ---------------------------------------------------------------------------
# 1. GEOREFERENCING CONSTANTS
# ---------------------------------------------------------------------------
# The aerial mosaic (media/02_sandiego_aerial.png, 1398 x 2048 px) carries no
# embedded geodata, so its extents were derived visually from landmarks,
# assuming square ground pixels (standard for aerial mosaics):
#
#   anchor                     lat        lon        solves to (x%, y%)
#   Mission Bay (center)       32.777   -117.235       21%, 50%
#   MCAS Miramar (runways)     32.868   -117.143       48%, 28%
#   Lake Murray                32.783   -117.043       78%, 49%
#   Sweetwater Reservoir       32.694   -117.006       89%, 70%
#
# Estimated uncertainty ~ +/- 0.02 deg. If you obtain the mosaic's true
# corner coordinates, just replace the four numbers below — everything
# downstream (grid extents, texture registration, event filtering) follows.
SD_LON_MIN, SD_LON_MAX = -117.31, -116.97       # trigger_lo_x, trigger_hi_x
SD_LAT_MIN, SD_LAT_MAX = 32.57, 32.98           # trigger_lo_y, trigger_hi_y
SD_IMG_ASPECT = 1398 / 2048                     # aerial pixel aspect (w/h)

# ---------------------------------------------------------------------------
# 2. SCENE LAYOUT CONSTANTS (the knobs)
# ---------------------------------------------------------------------------
WORLD_GRID_SCALE = 0.6          # whole-earth plate: 360x180 deg -> 216x108 units
SD_PLATE_HEIGHT = 280.0         # world-unit height of the San Diego plate
SD_HOVER_Z = 230.0              # how high Grid B floats above the world map
DEPTH_EXAGGERATION = 6.5        # Grid B scale_z: 1 km of depth -> this many units
LABEL_MIN_MAG = 3.5             # inline text labels for events at/above this
MAG_FLOOR, MAG_CEIL = 0.0, 5.5  # magnitude range mapped to size/color ramps
AMBER = (255, 179, 64)          # callout / marker accent color
BG_COLOR = (10, 12, 26, 255)    # World-row background (deep space blue)

# Channels time replay -------------------------------------------------------
EVENT_ALPHA = 235               # static CSV alpha (playback off / after Stop)
ALPHA_FLASH = 255               # alpha the month an event is born
ALPHA_SETTLE = 145              # dim "memory" alpha after the flash decays
FLASH_DECAY_FRAMES = 8          # frames for the 255 -> settle decay
HOLD_FRAMES = 48                # extra frames appended after the last month
RELIGHT_FRAMES = 24             # tail of the hold: everything ramps to EVENT_ALPHA
CURSOR_CHANNEL = 500            # channel id for the timeline cursor

# Timeline bar (south of the world plate, in world coordinates) --------------
TL_X_MAX = 180.0 * WORLD_GRID_SCALE          # bar spans the plate's width
TL_X_MIN = -TL_X_MAX
TL_Y = -(90.0 * WORLD_GRID_SCALE) - 8.0      # 8 units south of the plate edge
TL_Z = 0.0

# Derived Grid B transform.  Height fixes scale_y; width follows the image
# aspect exactly, so the texture renders undistorted.  (Over a 0.4 deg window
# this is within ~2% of a locally conformal scale_x = scale_y*cos(lat) map —
# far inside the georeferencing uncertainty.)
SD_LON_SPAN = SD_LON_MAX - SD_LON_MIN
SD_LAT_SPAN = SD_LAT_MAX - SD_LAT_MIN
SD_LON_CTR = (SD_LON_MIN + SD_LON_MAX) / 2.0
SD_LAT_CTR = (SD_LAT_MIN + SD_LAT_MAX) / 2.0
SD_SCALE_Y = SD_PLATE_HEIGHT / SD_LAT_SPAN
SD_SCALE_X = (SD_PLATE_HEIGHT * SD_IMG_ASPECT) / SD_LON_SPAN
# Grid B hovers directly above its true location on the world map:
SD_GRID_POS = (SD_LON_CTR * WORLD_GRID_SCALE, SD_LAT_CTR * WORLD_GRID_SCALE,
               SD_HOVER_Z)

# ---------------------------------------------------------------------------
# 3. USGS FDSN FETCH
# ---------------------------------------------------------------------------
FDSN_BASE = "https://earthquake.usgs.gov/fdsnws/event/1"
PAGE_SIZE = 20000               # FDSN hard limit per query
USER_AGENT = "GlyphViz-WorldGrid-exemplar/1.1 (scientific visualization demo)"


def fetch_usgs_catalog(start: str, end: str | None, min_mag: float | None,
                       retries: int = 3) -> pd.DataFrame:
    """Count-first, paged, retrying pull of the regional catalog as CSV."""
    if requests is None:
        raise RuntimeError("The 'requests' package is required for live "
                           "fetching: pip install requests")
    common = {
        "starttime": start,
        "minlatitude": SD_LAT_MIN, "maxlatitude": SD_LAT_MAX,
        "minlongitude": SD_LON_MIN, "maxlongitude": SD_LON_MAX,
        "eventtype": "earthquake",
    }
    if end:
        common["endtime"] = end
    if min_mag is not None:
        common["minmagnitude"] = min_mag
    headers = {"User-Agent": USER_AGENT}

    def _get(url, params):
        last = None
        for attempt in range(retries):
            try:
                r = requests.get(url, params=params, headers=headers,
                                 timeout=60)
                r.raise_for_status()
                return r
            except Exception as exc:            # noqa: BLE001 - report last
                last = exc
                wait = 2 ** attempt
                print(f"    attempt {attempt + 1} failed ({exc}); "
                      f"retrying in {wait}s", file=sys.stderr)
                time.sleep(wait)
        raise RuntimeError(f"USGS request failed after {retries} attempts: "
                           f"{last}")

    # Etiquette: probe /count before pulling data, then page if needed.
    count = int(_get(f"{FDSN_BASE}/count",
                     {**common, "format": "geojson"}).json()["count"])
    print(f"  USGS reports {count} events in the window")

    frames = []
    offset = 1                                   # FDSN offsets are 1-based
    while offset <= max(count, 1):
        params = {**common, "format": "csv", "orderby": "time-asc",
                  "limit": PAGE_SIZE, "offset": offset}
        text = _get(f"{FDSN_BASE}/query", params).text
        page = pd.read_csv(io.StringIO(text))
        if page.empty:
            break
        frames.append(page)
        offset += PAGE_SIZE
    df = (pd.concat(frames, ignore_index=True)
          if frames else pd.DataFrame(columns=["time", "latitude",
                                               "longitude", "depth", "mag",
                                               "id", "place"]))
    return tidy_catalog(df)


def load_offline_catalog(path: str) -> pd.DataFrame:
    """Load a USGS-format CSV export (columns: time, latitude, longitude,
    depth, mag, id, place ...).  SCEC catalogs can be used by renaming
    columns to match before calling."""
    return tidy_catalog(pd.read_csv(path))


def tidy_catalog(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize, bound-check, and sort the catalog."""
    need = {"time", "latitude", "longitude", "depth", "mag"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"catalog is missing columns: {sorted(missing)}")
    df = df.copy()
    df["mag"] = pd.to_numeric(df["mag"], errors="coerce").fillna(0.0)
    df["depth"] = pd.to_numeric(df["depth"], errors="coerce").fillna(0.0)
    df = df[(df.longitude >= SD_LON_MIN) & (df.longitude <= SD_LON_MAX)
            & (df.latitude >= SD_LAT_MIN) & (df.latitude <= SD_LAT_MAX)]
    if "type" in df.columns:                     # belt-and-suspenders
        df = df[df["type"].astype(str).str.lower() == "earthquake"]
    if "id" not in df.columns:
        df["id"] = ""
    return df.sort_values("time").reset_index(drop=True)


# ---------------------------------------------------------------------------
# 4. VISUAL ENCODINGS
# ---------------------------------------------------------------------------
def mag_t(mag: float) -> float:
    """Magnitude -> 0..1 parameter."""
    t = (mag - MAG_FLOOR) / (MAG_CEIL - MAG_FLOOR)
    return min(max(t, 0.0), 1.0)


def mag_to_scale(mag: float) -> float:
    """Magnitude -> glyph scale.  Quadratic so big events pop; floored at
    the renderer's 0.2 minimum; capped so M5+ doesn't swallow the plate."""
    return round(min(0.25 + 0.11 * max(mag, 0.0) ** 2, 4.0), 3)


_RAMP = [(40, 70, 200), (0, 200, 230), (255, 200, 40), (255, 60, 30)]


def mag_to_color(mag: float) -> tuple[int, int, int]:
    """Cold deep blue -> cyan -> gold -> red across MAG_FLOOR..MAG_CEIL."""
    t = mag_t(mag) * (len(_RAMP) - 1)
    i = min(int(t), len(_RAMP) - 2)
    f = t - i
    a, b = _RAMP[i], _RAMP[i + 1]
    return tuple(int(round(a[k] + (b[k] - a[k]) * f)) for k in range(3))


def sanitize(label: str) -> str:
    """Strip control characters — one bad byte can kill all tags."""
    return "".join(c for c in str(label)
                   if unicodedata.category(c)[0] != "C").strip()


# ---------------------------------------------------------------------------
# 5. SCENE BUILDER
# ---------------------------------------------------------------------------
COLUMNS = ["id", "type", "parent_id", "branch_level", "child_id",
           "translate_x", "translate_y", "translate_z",
           "rotate_x", "rotate_y", "rotate_z",
           "scale_x", "scale_y", "scale_z",
           "color_r", "color_g", "color_b", "color_a", "color_index",
           "geometry", "hide", "topo", "ratio", "texture_id",
           "ch_input_id", "rotate_rate_z",
           "trigger_lo_x", "trigger_hi_x", "trigger_lo_y", "trigger_hi_y",
           "segments_x", "segments_y", "text", "link"]

DEFAULTS = dict(child_id=0, translate_x=0.0, translate_y=0.0, translate_z=0.0,
                rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
                scale_x=1.0, scale_y=1.0, scale_z=1.0,
                color_r=255, color_g=255, color_b=255, color_a=255,
                color_index=0, geometry=3, hide=0, topo=0, ratio=0.1,
                texture_id=0, ch_input_id=0, rotate_rate_z=0.0,
                trigger_lo_x=0, trigger_hi_x=0, trigger_lo_y=0,
                trigger_hi_y=0, segments_x=16, segments_y=16,
                text="", link="")


@dataclass
class SceneBuilder:
    rows: list[dict] = field(default_factory=list)
    next_id: int = 1

    def add(self, **kw) -> int:
        row = {**DEFAULTS, "id": self.next_id, **kw}
        self.rows.append(row)
        self.next_id += 1
        return row["id"]

    # -- structural pieces ---------------------------------------------------
    def build_structure(self) -> dict:
        """World row, both grids, footprint rectangle, callout frustum.
        Returns the ids other pieces need."""
        # World row: background only, never drawn.
        self.add(type=0, parent_id=0, branch_level=0,
                 color_r=BG_COLOR[0], color_g=BG_COLOR[1],
                 color_b=BG_COLOR[2], color_a=BG_COLOR[3], geometry=0)

        # Grid A — whole-earth reference (explicit whole-earth window).
        world_grid = self.add(
            type=6, parent_id=0, branch_level=0, geometry=21,
            scale_x=WORLD_GRID_SCALE, scale_y=WORLD_GRID_SCALE,
            scale_z=WORLD_GRID_SCALE, texture_id=1,
            trigger_lo_x=-180, trigger_hi_x=180,
            trigger_lo_y=-90, trigger_hi_y=90,
            segments_x=36, segments_y=18,
            text="Earth reference (Blue Marble)")

        # Grid B — San Diego, hovering above its own footprint.
        sd_grid = self.add(
            type=6, parent_id=0, branch_level=0, geometry=21,
            translate_x=round(SD_GRID_POS[0], 4),
            translate_y=round(SD_GRID_POS[1], 4),
            translate_z=SD_GRID_POS[2],
            scale_x=round(SD_SCALE_X, 4), scale_y=round(SD_SCALE_Y, 4),
            scale_z=DEPTH_EXAGGERATION, texture_id=2,
            trigger_lo_x=SD_LON_MIN, trigger_hi_x=SD_LON_MAX,
            trigger_lo_y=SD_LAT_MIN, trigger_hi_y=SD_LAT_MAX,
            segments_x=1, segments_y=1,
            text="San Diego region")

        # "You are here" halo on the world map (schematic marker — the true
        # footprint is ~0.2 units wide at this map scale).  Slow spin.
        self.add(type=5, parent_id=world_grid, branch_level=1,
                 translate_x=SD_LON_CTR, translate_y=SD_LAT_CTR,
                 translate_z=0.3, scale_x=3, scale_y=3, scale_z=3,
                 geometry=6, ratio=0.06, rotate_rate_z=0.2,
                 color_r=AMBER[0], color_g=AMBER[1], color_b=AMBER[2],
                 color_a=220, text="San Diego")

        # True-scale footprint corners on the world map (lon/lat under the
        # grid) and matching corners on the San Diego plate.
        corners = [(SD_LON_MIN, SD_LAT_MIN), (SD_LON_MAX, SD_LAT_MIN),
                   (SD_LON_MAX, SD_LAT_MAX), (SD_LON_MIN, SD_LAT_MAX)]
        w_ids, s_ids = [], []
        for lon, lat in corners:
            w_ids.append(self.add(
                type=5, parent_id=world_grid, branch_level=1,
                translate_x=lon, translate_y=lat, translate_z=0.2,
                scale_x=0.2, scale_y=0.2, scale_z=0.2, geometry=3,
                color_r=AMBER[0], color_g=AMBER[1], color_b=AMBER[2],
                color_a=255))
        for lon, lat in corners:
            s_ids.append(self.add(
                type=5, parent_id=sd_grid, branch_level=1,
                translate_x=lon, translate_y=lat, translate_z=0.5,
                scale_x=0.6, scale_y=0.6, scale_z=0.6, geometry=3,
                color_r=AMBER[0], color_g=AMBER[1], color_b=AMBER[2],
                color_a=255))

        # Footprint rectangle: Link edges chaining the world-map corners.
        for i in range(4):
            self.add(type=7, parent_id=w_ids[i], child_id=w_ids[(i + 1) % 4],
                     branch_level=2, geometry=27,
                     color_r=AMBER[0], color_g=AMBER[1], color_b=AMBER[2],
                     color_a=200)
        # Callout frustum: each world-map corner up to its plate corner.
        for i in range(4):
            self.add(type=7, parent_id=w_ids[i], child_id=s_ids[i],
                     branch_level=2, geometry=27,
                     color_r=AMBER[0], color_g=AMBER[1], color_b=AMBER[2],
                     color_a=150)
        return {"world_grid": world_grid, "sd_grid": sd_grid}

    # -- timeline (root-level, world coordinates) ---------------------------
    def build_timeline(self, y0: int, m0: int, n_months: int) -> None:
        """Bar + decade ticks south of the world plate, and the channel-
        driven cursor.  x maps month index 0..n_months-1 onto
        TL_X_MIN..TL_X_MAX (the plate's full width)."""
        def x_of(month_idx: int) -> float:
            f = month_idx / max(n_months - 1, 1)
            return round(TL_X_MIN + (TL_X_MAX - TL_X_MIN) * f, 3)

        # Endpoints + the bar itself (a Link edge between them).
        left = self.add(type=5, parent_id=0, branch_level=0,
                        translate_x=TL_X_MIN, translate_y=TL_Y,
                        translate_z=TL_Z, scale_x=0.8, scale_y=0.8,
                        scale_z=0.8, geometry=1,
                        color_r=AMBER[0], color_g=AMBER[1], color_b=AMBER[2],
                        color_a=255)
        right = self.add(type=5, parent_id=0, branch_level=0,
                         translate_x=TL_X_MAX, translate_y=TL_Y,
                         translate_z=TL_Z, scale_x=0.8, scale_y=0.8,
                         scale_z=0.8, geometry=1,
                         color_r=AMBER[0], color_g=AMBER[1], color_b=AMBER[2],
                         color_a=255)
        self.add(type=7, parent_id=left, child_id=right, branch_level=1,
                 geometry=27, color_r=AMBER[0], color_g=AMBER[1],
                 color_b=AMBER[2], color_a=180)

        # Decade ticks with year labels (first decade at/after the catalog
        # start; the T key toggles the labels in-app).
        first_decade = y0 + (-y0) % 10 if y0 % 10 else y0
        year = first_decade
        while (year - y0) * 12 - (m0 - 1) < n_months:
            m_idx = (year - y0) * 12 - (m0 - 1)
            if m_idx >= 0:
                self.add(type=5, parent_id=0, branch_level=0,
                         translate_x=x_of(m_idx), translate_y=TL_Y,
                         translate_z=TL_Z + 1.2, scale_x=0.7, scale_y=0.7,
                         scale_z=2.2, geometry=1,
                         color_r=AMBER[0], color_g=AMBER[1],
                         color_b=AMBER[2], color_a=220, text=str(year))
            year += 10

        # The cursor: channel-driven translate_x sweep, spinning octahedron.
        self.add(type=5, parent_id=0, branch_level=0,
                 translate_x=TL_X_MIN, translate_y=TL_Y,
                 translate_z=TL_Z + 3.5, scale_x=3.5, scale_y=3.5,
                 scale_z=3.5, geometry=11, rotate_rate_z=0.6,
                 color_r=255, color_g=220, color_b=120, color_a=255,
                 ch_input_id=CURSOR_CHANNEL, text="now")

    # -- data ---------------------------------------------------------------
    def add_earthquakes(self, catalog: pd.DataFrame, sd_grid: int,
                        month_channel: dict[int, int] | None = None) -> int:
        """month_channel maps an event's birth-month index to its shared
        channel id (None = no Channels animation)."""
        n = 0
        for ev in catalog.itertuples(index=False):
            mag = float(ev.mag)
            r, g, b = mag_to_color(mag)
            s = mag_to_scale(mag)
            date = sanitize(str(ev.time))[:10]
            label = (f"M{mag:.1f} {date}" if mag >= LABEL_MIN_MAG else "")
            url = (f"https://earthquake.usgs.gov/earthquakes/eventpage/"
                   f"{sanitize(str(ev.id))}" if str(ev.id) else "")
            ch = (month_channel.get(int(ev.month_idx), 0)
                  if month_channel is not None else 0)
            self.add(type=5, parent_id=sd_grid, branch_level=1,
                     translate_x=round(float(ev.longitude), 6),
                     translate_y=round(float(ev.latitude), 6),
                     translate_z=round(-float(ev.depth), 4),
                     scale_x=s, scale_y=s, scale_z=s,
                     color_r=r, color_g=g, color_b=b, color_a=EVENT_ALPHA,
                     color_index=1 + round(mag_t(mag) * 19),
                     geometry=3, ch_input_id=ch, text=label, link=url)
            n += 1
        return n

    # -- output -------------------------------------------------------------
    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=COLUMNS)


# ---------------------------------------------------------------------------
# 6. CHANNELS BUILDER (time replay)
# ---------------------------------------------------------------------------
def month_indices(catalog: pd.DataFrame) -> tuple[pd.DataFrame, int, int, int]:
    """Add a month_idx column (months since the first event's month).
    Returns (catalog, first_year, first_month, n_months)."""
    when = pd.to_datetime(catalog["time"], format="mixed", utc=True)
    y0, m0 = int(when.iloc[0].year), int(when.iloc[0].month)
    idx = (when.dt.year - y0) * 12 + (when.dt.month - m0)
    catalog = catalog.copy()
    catalog["month_idx"] = idx.astype(int)
    n_months = int(idx.max()) + 1
    return catalog, y0, m0, n_months


def birth_alpha(frame: int, birth: int, n_months: int, total: int) -> int:
    """Alpha track value for an event born at month `birth`, at `frame`.
    0 before birth; ALPHA_FLASH decaying to ALPHA_SETTLE after; in the
    final RELIGHT_FRAMES of the hold tail, ramp everything to EVENT_ALPHA."""
    if frame < birth:
        base = 0
    else:
        t = (frame - birth) / FLASH_DECAY_FRAMES
        base = (ALPHA_SETTLE
                + (ALPHA_FLASH - ALPHA_SETTLE) * max(0.0, 1.0 - t))
    ramp_start = total - RELIGHT_FRAMES
    if frame >= ramp_start and base > 0:
        f = (frame - ramp_start) / max(RELIGHT_FRAMES - 1, 1)
        base = max(base, ALPHA_SETTLE + (EVENT_ALPHA - ALPHA_SETTLE) * f)
    return int(round(base))


def build_channel_files(catalog: pd.DataFrame, n_months: int
                        ) -> tuple[pd.DataFrame, pd.DataFrame,
                                   dict[int, int]]:
    """Returns (ch_map_df, ch_tracks_df, month_channel).
    One channel+track per distinct birth month (color_a), plus the cursor
    channel (translate_x).  Total frames = n_months + HOLD_FRAMES."""
    total = n_months + HOLD_FRAMES
    births = sorted(catalog["month_idx"].unique())
    month_channel = {int(b): i + 1 for i, b in enumerate(births)}

    map_rows = [dict(id=i + 1, channel_id=ch, track_id=ch,
                     attribute="color_a", track_table_id=0,
                     ch_map_table_id=0, record_id=0)
                for i, (_b, ch) in enumerate(sorted(month_channel.items()))]
    map_rows.append(dict(id=len(map_rows) + 1, channel_id=CURSOR_CHANNEL,
                         track_id=CURSOR_CHANNEL, attribute="translate_x",
                         track_table_id=0, ch_map_table_id=0, record_id=0))
    ch_map_df = pd.DataFrame(map_rows)

    data: dict[str, list] = {"cyclecount": list(range(1, total + 1))}
    for b, ch in sorted(month_channel.items()):
        data[f"ch{ch}"] = [birth_alpha(f, b, n_months, total)
                           for f in range(total)]
    span = TL_X_MAX - TL_X_MIN
    data[f"ch{CURSOR_CHANNEL}"] = [
        round(TL_X_MIN + span * min(f, n_months - 1)
              / max(n_months - 1, 1), 3)
        for f in range(total)]
    ch_tracks_df = pd.DataFrame(data)
    return ch_map_df, ch_tracks_df, month_channel


# ---------------------------------------------------------------------------
# 7. VALIDATION
# ---------------------------------------------------------------------------
def validate(df: pd.DataFrame) -> list[str]:
    """Pre-delivery checks per the GlyphViz authoring rules."""
    problems = []
    if df["id"].duplicated().any():
        problems.append("duplicate ids")
    if (df["id"] < 1).any():
        problems.append("ids must be >= 1")
    known = set(df["id"])
    bad_parents = df[(df.parent_id != 0) & (~df.parent_id.isin(known))]
    if len(bad_parents):
        problems.append(f"{len(bad_parents)} rows with unknown parent_id")
    links = df[df.type == 7]
    if len(links) and (~links.child_id.isin(known)).any():
        problems.append("link child_id references a missing node")
    for c in ("color_r", "color_g", "color_b", "color_a"):
        if ((df[c] < 0) | (df[c] > 255)).any():
            problems.append(f"{c} out of 0..255")
    vis = df[(df.hide == 0) & (df.type.isin([5, 7]))]
    if ((vis[["scale_x", "scale_y", "scale_z"]] < 0.2).any(axis=None)):
        problems.append("visible glyph with raw scale < 0.2")
    grids = df[df.type == 6]
    for _, gr in grids.iterrows():
        if not (gr.trigger_hi_x > gr.trigger_lo_x
                and gr.trigger_hi_y > gr.trigger_lo_y):
            problems.append(f"grid id {gr.id}: degenerate extents window")
    return problems


BINDABLE = {f"translate_{a}" for a in "xyz"} | \
    {f"rotate_{a}" for a in "xyz"} | {f"scale_{a}" for a in "xyz"} | \
    {f"translate_rate_{a}" for a in "xyz"} | \
    {f"rotate_rate_{a}" for a in "xyz"} | \
    {f"scale_rate_{a}" for a in "xyz"} | \
    {"color_r", "color_g", "color_b", "color_a", "texture_id"}


def validate_channels(df: pd.DataFrame, ch_map_df: pd.DataFrame,
                      ch_tracks_df: pd.DataFrame) -> list[str]:
    """The three-way join the engine never checks for you: node
    ch_input_id -> map channel_id -> tracks ch<id> column, and the
    attribute names must be bindable."""
    problems = []
    channels = set(ch_map_df["channel_id"])
    used = set(df.loc[df.ch_input_id != 0, "ch_input_id"])
    orphaned = used - channels
    if orphaned:
        problems.append(f"ch_input_id with no map row: {sorted(orphaned)}")
    unused = channels - used
    if unused:
        problems.append(f"map channel with no node: {sorted(unused)}")
    track_cols = {int(c[2:]) for c in ch_tracks_df.columns
                  if c.startswith("ch") and c[2:].isdigit()}
    missing = set(ch_map_df["track_id"]) - track_cols
    if missing:
        problems.append(f"map track_id with no ch<id> column: "
                        f"{sorted(missing)}")
    bad_attr = set(ch_map_df["attribute"]) - BINDABLE
    if bad_attr:
        problems.append(f"unbindable attributes: {sorted(bad_attr)}")
    alpha_cols = [f"ch{t}" for t in
                  ch_map_df.loc[ch_map_df.attribute == "color_a", "track_id"]]
    for c in alpha_cols:
        if ((ch_tracks_df[c] < 0) | (ch_tracks_df[c] > 255)).any():
            problems.append(f"tracks column {c}: alpha out of 0..255")
    return problems


def write_csv(df: pd.DataFrame, path: str, float_format=None) -> None:
    df.to_csv(path, index=False, encoding="utf-8", lineterminator="\r\n",
              float_format=float_format)
    back = pd.read_csv(path, encoding="utf-8")
    assert len(back) == len(df), f"round-trip row-count mismatch: {path}"


def channel_paths(node_out: str) -> tuple[str, str]:
    """Derive the ch-map/ch-tracks paths from the node CSV path, swapping
    a trailing 'node' stem for the channel names (gv naming convention)."""
    p = Path(node_out)
    stem = p.stem
    if stem.endswith("node"):
        base = stem[: -len("node")]
    else:
        base = stem + "_"
    return (str(p.with_name(f"{base}ch-map{p.suffix}")),
            str(p.with_name(f"{base}ch-tracks{p.suffix}")))


# ---------------------------------------------------------------------------
# 8. MAIN
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--start", default="1960-01-01",
                    help="catalog start date (default 1960-01-01)")
    ap.add_argument("--end", default=None, help="catalog end date")
    ap.add_argument("--min-mag", type=float, default=None,
                    help="minimum magnitude filter")
    ap.add_argument("--offline", metavar="CSV",
                    help="use a local USGS-format CSV instead of the API")
    ap.add_argument("--structure-only", action="store_true",
                    help="build the two-grid callout scene with no events")
    ap.add_argument("--no-channels", action="store_true",
                    help="skip the time-replay channel files")
    ap.add_argument("--out", default="sd_quakes_gv_node.csv",
                    help="output node CSV path")
    args = ap.parse_args()

    catalog = None
    if not args.structure_only:
        try:
            if args.offline:
                print(f"Loading offline catalog: {args.offline}")
                catalog = load_offline_catalog(args.offline)
            else:
                print("Fetching USGS FDSN catalog "
                      f"({args.start} .. {args.end or 'now'}, "
                      f"lon {SD_LON_MIN}..{SD_LON_MAX}, "
                      f"lat {SD_LAT_MIN}..{SD_LAT_MAX})")
                catalog = fetch_usgs_catalog(args.start, args.end,
                                             args.min_mag)
                snap = Path(args.out).parent / "data" / "usgs_catalog.csv"
                snap.parent.mkdir(parents=True, exist_ok=True)
                catalog.to_csv(snap, index=False, encoding="utf-8")
                print(f"  snapshot -> {snap}")
            print(f"  {len(catalog)} events after tidy/bounds filtering")
        except Exception as exc:                 # noqa: BLE001
            print(f"\nDATA ACQUISITION FAILED: {exc}", file=sys.stderr)
            print("Building the structural scene anyway (grids + callout); "
                  "re-run with network access or --offline for the full "
                  "scene.\n", file=sys.stderr)

    with_channels = catalog is not None and len(catalog) and \
        not args.no_channels

    sb = SceneBuilder()
    ids = sb.build_structure()

    ch_map_df = ch_tracks_df = None
    month_channel = None
    if with_channels:
        catalog, y0, m0, n_months = month_indices(catalog)
        ch_map_df, ch_tracks_df, month_channel = \
            build_channel_files(catalog, n_months)
        sb.build_timeline(y0, m0, n_months)
        print(f"  Channels: {n_months} months + {HOLD_FRAMES} hold frames, "
              f"{len(month_channel)} birth-month channels + cursor")

    n_quakes = (sb.add_earthquakes(catalog, ids["sd_grid"], month_channel)
                if catalog is not None else 0)

    df = sb.to_dataframe()
    problems = validate(df)
    if with_channels:
        problems += validate_channels(df, ch_map_df, ch_tracks_df)
    if problems:
        for p in problems:
            print(f"VALIDATION FAILURE: {p}", file=sys.stderr)
        return 1

    write_csv(df, args.out, float_format="%.6f")
    msgs = [f"Wrote {args.out}: {len(df)} rows ({n_quakes} earthquakes)"]
    if with_channels:
        map_path, tracks_path = channel_paths(args.out)
        write_csv(ch_map_df, map_path)
        write_csv(ch_tracks_df, tracks_path)
        msgs.append(f"Wrote {map_path}: {len(ch_map_df)} bindings")
        msgs.append(f"Wrote {tracks_path}: {len(ch_tracks_df)} frames x "
                    f"{len(ch_tracks_df.columns) - 1} tracks")
    print(". ".join(msgs) + ". Validation clean.")
    print("Open the node CSV in GlyphViz (File > Open) with the media/ "
          "folder beside it; the ch files auto-load. Space plays.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
