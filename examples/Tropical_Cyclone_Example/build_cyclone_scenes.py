#!/usr/bin/env python3
"""
build_cyclone_scenes.py — 184 years of tropical cyclones on a GlyphViz globe
============================================================================

Builds three World-Grid *globe* scenes from IBTrACS, the international best
track archive (every tropical cyclone humanity has tracked, 1842-present):

  Global_Tracks/   Every storm position ever recorded, placed by lon/lat on
                   a Blue-Marble globe with **elevation = wind speed**.  The
                   tracks stop being lines on a map and become a relief:
                   ridges of intensity standing over the warm oceans, each
                   one rising as the storm spins up and sinking back as it
                   recurves poleward and dies.  Storms with no intensity in
                   the record (most of the 19th century) lie flat and gray —
                   the shape of the archive itself is part of the picture.

  Seasonal_Pulse/  The same globe animated over ONE composite calendar year:
                   184 years of storms collapsed onto day-of-year, so every
                   track point lights on its own day and fades over the next
                   fortnight.  The two hemispheres breathe in antiphase, the
                   basins switch on in sequence, and the equator and South
                   Atlantic stay empty all year.  A subsolar-latitude marker
                   rides the same clock, tying the pulse to its cause.

  Poleward_Drift/  One glyph per storm at its point of **lifetime maximum
                   intensity**, animated by season, with two rings marking
                   the running mean |LMI latitude| per hemisphere.  Over the
                   satellite era those rings creep away from the equator —
                   the poleward migration of peak tropical-cyclone intensity
                   (cf. Kossin, Emanuel & Vecchi 2014).  See the README for
                   the trend this build measured.

Data source: NOAA NCEI IBTrACS v04r01 (public domain)
    https://www.ncei.noaa.gov/products/international-best-track-archive
    The full ALL-basin CSV is ~330 MB, so the default build reads a local
    copy you point it at (--source) or downloads once (--download), then
    snapshots a compact tidy subset to data/ibtracs_tidy.csv.gz that every
    later rebuild can use offline.

Usage:
    python build_cyclone_scenes.py --download        # fetch, tidy, build all
    python build_cyclone_scenes.py --source raw.csv  # tidy a local raw CSV
    python build_cyclone_scenes.py                   # rebuild from snapshot
    python build_cyclone_scenes.py --only Global_Tracks

Requires: pandas, numpy (requests only for --download)
"""

from __future__ import annotations

import argparse
import math
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
SNAPSHOT = DATA / "ibtracs_tidy.csv.gz"

IBTRACS_URL = ("https://www.ncei.noaa.gov/data/"
               "international-best-track-archive-for-climate-stewardship-"
               "ibtracs/v04r01/access/csv/ibtracs.ALL.list.v04r01.csv")

# ---------------------------------------------------------------------------
# 1. SCENE CONSTANTS (the knobs)
# ---------------------------------------------------------------------------
GLOBE_R = 180.0 / math.pi        # world radius of a scale-1 globe (57.2958)

# Global_Tracks
ELEV_PER_KT = 0.14               # 1 kt of wind -> this many world units up
ELEV_FLOOR = 0.6                 # keep every point clear of the globe skin
TRACK_STRIDE_H = 12              # hours between kept track points
LABEL_TOP_N = 24                 # label this many of the fiercest storms

# Seasonal_Pulse
PULSE_STRIDE_H = 24              # coarser: the pulse is about timing
PULSE_FRAMES = 366               # one frame per day of a composite year
PULSE_DECAY_DAYS = 14.0          # brightness half-life after a point's day
PULSE_ALPHA_HI = 255
PULSE_ALPHA_LO = 26              # residue so the climatology stays readable
SUN_CHANNEL = 900_000
CURSOR_CHANNEL = 900_001

# Poleward_Drift
# Satellite era only, and this matters. Run the same regression back to 1950
# and the northern trend flips to -0.16 deg/decade: before geostationary
# coverage the archive simply missed storms, and it missed them unevenly by
# latitude, so a longer window measures the growth of the observing system
# rather than the behaviour of the atmosphere. Annual storm counts with a
# usable intensity peak go 41 (1950) -> 74 (1970) -> ~100 (1990 onward).
DRIFT_FIRST_SEASON = 1980
DRIFT_HOLD_FRAMES = 40
RING_N_CHANNEL = 900_010
RING_S_CHANNEL = 900_020
RING_STANDOFF = 1.05             # latitude rings float just clear of the globe

BG_COLOR = (6, 9, 22, 255)       # deep ocean night
ACCENT = (255, 196, 92)          # captions / timeline furniture

# Saffir-Simpson-style intensity ladder: (min_kt, label, rgb, palette-0 idx)
CATEGORIES = [
    (137, "Cat 5", (255, 120, 255), 8),
    (113, "Cat 4", (255, 48, 40), 2),
    (96,  "Cat 3", (255, 132, 24), 17),
    (83,  "Cat 2", (255, 190, 30), 6),
    (64,  "Cat 1", (255, 246, 96), 4),
    (34,  "Trop. storm", (86, 232, 160), 1),
    (0,   "Depression", (72, 168, 232), 12),
]
NO_WIND_RGB = (104, 112, 128)    # position known, intensity unrecorded
NO_WIND_IDX = 15


def category(wind_kt: float | None):
    """(label, rgb, palette-0 index) for a wind speed in knots."""
    if wind_kt is None or not np.isfinite(wind_kt):
        return ("Unrecorded", NO_WIND_RGB, NO_WIND_IDX)
    for lo, name, rgb, idx in CATEGORIES:
        if wind_kt >= lo:
            return (name, rgb, idx)
    return ("Depression", CATEGORIES[-1][2], CATEGORIES[-1][3])


def elevation(wind_kt: float | None) -> float:
    if wind_kt is None or not np.isfinite(wind_kt):
        return ELEV_FLOOR
    return round(ELEV_FLOOR + max(wind_kt, 0.0) * ELEV_PER_KT, 3)


def point_ratio(wind_kt: float | None) -> float:
    """Point glyphs size from `ratio` (pixels = ratio*20), not scale."""
    if wind_kt is None or not np.isfinite(wind_kt):
        return 0.07
    return round(min(0.07 + 0.0016 * max(wind_kt, 0.0), 0.30), 3)


def sanitize(text: str) -> str:
    """Strip control characters — one bad byte can kill every label."""
    return "".join(c for c in str(text)
                   if unicodedata.category(c)[0] != "C").strip()


# ---------------------------------------------------------------------------
# 2. DATA ACQUISITION AND TIDYING
# ---------------------------------------------------------------------------
RAW_COLS = ["SID", "SEASON", "BASIN", "SUBBASIN", "NAME", "ISO_TIME",
            "NATURE", "TRACK_TYPE", "LAT", "LON", "WMO_WIND", "WMO_PRES",
            "USA_WIND", "USA_PRES", "DIST2LAND"]

BASIN_NAMES = {"NA": "N Atlantic", "EP": "E Pacific", "WP": "W Pacific",
               "NI": "N Indian", "SI": "S Indian", "SP": "S Pacific",
               "SA": "S Atlantic"}


def download_raw(dest: Path) -> Path:
    try:
        import requests
    except ImportError:
        raise SystemExit("--download needs the 'requests' package")
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading IBTrACS v04r01 (~330 MB) -> {dest}")
    with requests.get(IBTRACS_URL, stream=True, timeout=120) as r:
        r.raise_for_status()
        got = 0
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
                got += len(chunk)
                print(f"\r  {got/1e6:7.1f} MB", end="", flush=True)
    print()
    return dest


def tidy_raw(path: Path) -> pd.DataFrame:
    """Read the raw archive and reduce it to the columns the scenes need.

    keep_default_na=False matters: the North Atlantic's basin code is the
    literal string "NA", which pandas would otherwise read as missing and
    silently delete the most-studied basin in the archive.
    """
    print(f"Reading {path} ...")
    df = pd.read_csv(path, usecols=RAW_COLS, skiprows=[1], low_memory=False,
                     keep_default_na=False, na_values=[""])
    df = df[df.TRACK_TYPE == "main"].copy()
    for c in ("LAT", "LON", "WMO_WIND", "USA_WIND", "WMO_PRES", "USA_PRES",
              "DIST2LAND", "SEASON"):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["wind"] = df.WMO_WIND.where(df.WMO_WIND.notna(), df.USA_WIND)
    df["pres"] = df.WMO_PRES.where(df.WMO_PRES.notna(), df.USA_PRES)
    when = pd.to_datetime(df.ISO_TIME, format="%Y-%m-%d %H:%M:%S",
                          errors="coerce")
    df["hour"] = when.dt.hour
    df["minute"] = when.dt.minute
    df["doy"] = when.dt.dayofyear
    df["date"] = when.dt.strftime("%Y-%m-%d")

    df = df[when.notna() & df.LAT.notna() & df.LON.notna()]
    df = df[(df.LAT.between(-90, 90)) & (df.LON.between(-180, 180))]
    # synoptic reports only — the archive interpolates 3-hourly in places
    df = df[(df.minute == 0) & (df.hour.isin([0, 6, 12, 18]))]

    out = df[["SID", "SEASON", "BASIN", "NAME", "NATURE", "date", "hour",
              "doy", "LAT", "LON", "wind", "pres", "DIST2LAND"]].copy()
    out.columns = ["sid", "season", "basin", "name", "nature", "date",
                   "hour", "doy", "lat", "lon", "wind", "pres", "dist2land"]
    out = out.sort_values(["sid", "date", "hour"]).reset_index(drop=True)
    print(f"  tidied to {len(out):,} synoptic points / "
          f"{out.sid.nunique():,} storms, seasons "
          f"{int(out.season.min())}-{int(out.season.max())}")
    return out


def load_snapshot() -> pd.DataFrame:
    if not SNAPSHOT.exists():
        raise SystemExit(
            f"No snapshot at {SNAPSHOT}.\n"
            "Run once with --download (fetches ~330 MB from NOAA) or "
            "--source <ibtracs.ALL.list.v04r01.csv>.")
    df = pd.read_csv(SNAPSHOT, keep_default_na=False, na_values=[""])
    for c in ("lat", "lon", "wind", "pres", "dist2land", "season", "doy",
              "hour"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def decimate(df: pd.DataFrame, stride_hours: int) -> pd.DataFrame:
    """Keep one synoptic report every `stride_hours` (they are 6 h apart)."""
    step = max(int(stride_hours // 6), 1)
    if step == 1:
        return df
    return df[df.groupby("sid").cumcount() % step == 0].copy()


# ---------------------------------------------------------------------------
# 3. SHARED SCENE BUILDER
# ---------------------------------------------------------------------------
COLUMNS = ["id", "type", "parent_id", "branch_level", "child_id",
           "translate_x", "translate_y", "translate_z",
           "rotate_x", "rotate_y", "rotate_z",
           "scale_x", "scale_y", "scale_z",
           "color_r", "color_g", "color_b", "color_a", "color_index",
           "geometry", "hide", "topo", "ratio", "texture_id",
           "ch_input_id", "rotate_rate_z", "show_text",
           "trigger_lo_x", "trigger_hi_x", "trigger_lo_y", "trigger_hi_y",
           "segments_x", "segments_y", "rotation_mode", "text", "link"]

DEFAULTS = dict(child_id=0, translate_x=0.0, translate_y=0.0,
                translate_z=0.0, rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
                scale_x=1.0, scale_y=1.0, scale_z=1.0,
                color_r=255, color_g=255, color_b=255, color_a=255,
                color_index=0, geometry=3, hide=0, topo=0, ratio=0.1,
                texture_id=0, ch_input_id=0, rotate_rate_z=0.0, show_text=0,
                trigger_lo_x=0, trigger_hi_x=0, trigger_lo_y=0,
                trigger_hi_y=0, segments_x=16, segments_y=16,
                rotation_mode=0, text="", link="")


@dataclass
class SceneBuilder:
    rows: list[dict] = field(default_factory=list)
    next_id: int = 1

    def add(self, **kw) -> int:
        self.rows.append({**DEFAULTS, "id": self.next_id, **kw})
        self.next_id += 1
        return self.next_id - 1

    def world(self, **kw) -> int:
        return self.add(type=0, parent_id=0, branch_level=0, geometry=0,
                        color_r=BG_COLOR[0], color_g=BG_COLOR[1],
                        color_b=BG_COLOR[2], color_a=BG_COLOR[3], **kw)

    def globe(self, **kw) -> int:
        """Blue-Marble globe: a World Grid with Sphere-solid geometry places
        children by KML lon/lat on a sphere of radius 180/pi."""
        opts = dict(type=6, parent_id=0, branch_level=0, geometry=3,
                    texture_id=1, segments_x=36, segments_y=18,
                    color_r=70, color_g=110, color_b=150, color_a=255,
                    text="Earth")
        opts.update(kw)
        return self.add(**opts)

    def track_points(self, df: pd.DataFrame, globe_id: int,
                     channel_of=None, alpha: int = 235) -> int:
        """One Point glyph per track position: lon/lat on the globe,
        elevation = wind speed, color = intensity category."""
        n = 0
        for p in df.itertuples(index=False):
            w = float(p.wind) if np.isfinite(p.wind) else None
            _lab, rgb, cidx = category(w)
            ch = int(channel_of(p)) if channel_of is not None else 0
            self.add(type=5, parent_id=globe_id, branch_level=1,
                     translate_x=round(float(p.lon), 4),
                     translate_y=round(float(p.lat), 4),
                     translate_z=elevation(w),
                     scale_x=0.3, scale_y=0.3, scale_z=0.3,
                     geometry=22, ratio=point_ratio(w),
                     color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
                     color_a=alpha, color_index=cidx, ch_input_id=ch)
            n += 1
        return n

    def caption(self, x, y, z, text, size=2.0, rgb=ACCENT, pin=1, **kw):
        return self.add(type=5, parent_id=0, branch_level=0,
                        translate_x=x, translate_y=y, translate_z=z,
                        scale_x=size, scale_y=size, scale_z=size,
                        geometry=11, color_r=rgb[0], color_g=rgb[1],
                        color_b=rgb[2], color_a=230, show_text=pin,
                        text=sanitize(text), **kw)

    # Legend geometry. The swatches are deliberately large and widely spaced:
    # tag text is drawn a few pixels from its node's *projected* position, so
    # a column that looks generous in world units still crowds on screen once
    # perspective has had its way with it.
    LEGEND_SPACING = 7.5
    LEGEND_SWATCH = 2.4

    def legend(self, x0: float, z0: float) -> None:
        """Intensity key, standing beside the globe."""
        rows = [(f"{name} ({lo}+ kt)" if lo else f"{name} (<34 kt)", rgb, cidx)
                for lo, name, rgb, cidx in CATEGORIES]
        rows.append(("Intensity unrecorded", NO_WIND_RGB, NO_WIND_IDX))
        top = z0 + self.LEGEND_SPACING * len(rows) / 2.0
        self.caption(x0, 0.0, top + self.LEGEND_SPACING,
                     "Wind speed = height above sea level", size=1.8)
        for k, (label, rgb, cidx) in enumerate(rows):
            self.add(type=5, parent_id=0, branch_level=0,
                     translate_x=x0, translate_y=0.0,
                     translate_z=top - k * self.LEGEND_SPACING,
                     scale_x=self.LEGEND_SWATCH, scale_y=self.LEGEND_SWATCH,
                     scale_z=self.LEGEND_SWATCH, geometry=3,
                     color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
                     color_a=255, color_index=cidx, show_text=1, text=label)

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=COLUMNS)


# ---------------------------------------------------------------------------
# 4. SCENE 1 — GLOBAL TRACKS
# ---------------------------------------------------------------------------
def build_global_tracks(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    pts = decimate(df, TRACK_STRIDE_H)
    sb = SceneBuilder()
    sb.world()
    g = sb.globe()
    n = sb.track_points(pts, g)

    # Label the fiercest storms at their moment of peak intensity.
    have = df[df.wind.notna()]
    peaks = have.loc[have.groupby("sid").wind.idxmax()]
    peaks = peaks.sort_values("wind", ascending=False).head(LABEL_TOP_N)
    for p in peaks.itertuples(index=False):
        nm = sanitize(p.name) if str(p.name) not in ("", "NOT_NAMED") \
            else "unnamed"
        sb.add(type=5, parent_id=g, branch_level=1,
               translate_x=round(float(p.lon), 4),
               translate_y=round(float(p.lat), 4),
               translate_z=elevation(float(p.wind)) + 2.0,
               scale_x=1.1, scale_y=1.1, scale_z=1.1, geometry=26,
               color_r=255, color_g=255, color_b=255, color_a=255,
               # Deliberately NOT pinned: two dozen pinned labels stack into
               # an unreadable heap over the Pacific. The white stars mark
               # the peaks; T reveals who they were.
               show_text=0,
               text=f"{nm} {int(p.season)} - {int(p.wind)} kt "
                    f"({BASIN_NAMES.get(str(p.basin), str(p.basin))})")

    sb.legend(-GLOBE_R - 52.0, -18.0)
    sb.caption(0.0, 0.0, GLOBE_R + 34.0,
               f"{df.sid.nunique():,} tropical cyclones, "
               f"{int(df.season.min())}-{int(df.season.max())}  |  "
               f"IBTrACS v04r01", size=2.4)
    return sb.to_dataframe(), {"points": n, "storms": int(pts.sid.nunique())}


# ---------------------------------------------------------------------------
# 5. SCENE 2 — SEASONAL PULSE (composite calendar year)
# ---------------------------------------------------------------------------
def circular_alpha(frame: int, day: int, frames: int) -> int:
    """Bright on the point's own day, decaying over PULSE_DECAY_DAYS, and
    wrapping across the year boundary so the loop has no seam."""
    d = (frame - day) % frames
    if d > frames / 2:
        d -= frames                      # nearest signed distance
    if d < 0:
        return PULSE_ALPHA_LO            # not yet — the residue only
    f = math.exp(-d / PULSE_DECAY_DAYS)
    return int(round(PULSE_ALPHA_LO + (PULSE_ALPHA_HI - PULSE_ALPHA_LO) * f))


def solar_declination(doy: int) -> float:
    """Subsolar latitude, degrees (standard cosine approximation)."""
    return -23.44 * math.cos(math.radians(360.0 / 365.0 * (doy + 10)))


MONTHS = [(1, "Jan"), (32, "Feb"), (60, "Mar"), (91, "Apr"), (121, "May"),
          (152, "Jun"), (182, "Jul"), (213, "Aug"), (244, "Sep"),
          (274, "Oct"), (305, "Nov"), (335, "Dec")]


def build_seasonal_pulse(df: pd.DataFrame):
    pts = decimate(df, PULSE_STRIDE_H)
    pts = pts[pts.doy.notna()].copy()
    pts["doy"] = pts.doy.astype(int).clip(1, PULSE_FRAMES)

    sb = SceneBuilder()
    sb.world()
    g = sb.globe()
    n = sb.track_points(pts, g, channel_of=lambda p: int(p.doy),
                        alpha=PULSE_ALPHA_HI)

    # Subsolar-latitude marker: the driver of the whole pulse.
    sun = sb.add(type=5, parent_id=g, branch_level=1,
                 translate_x=0.0, translate_y=0.0, translate_z=26.0,
                 scale_x=3.2, scale_y=3.2, scale_z=3.2, geometry=3,
                 color_r=255, color_g=232, color_b=150, color_a=255,
                 color_index=4, ch_input_id=SUN_CHANNEL, show_text=1,
                 text="subsolar latitude")

    # Calendar bar under the globe, with a channel-driven cursor. Kept
    # narrower than the storm cloud: the camera auto-fits the whole bounding
    # box, so an over-wide bar pushes the viewer back and shrinks both the
    # globe and the legend text along with it.
    bar_z = -GLOBE_R - 20.0
    x_lo, x_hi = -105.0, 105.0

    def x_of(day: int) -> float:
        return round(x_lo + (x_hi - x_lo) * (day - 1) / (PULSE_FRAMES - 1), 3)

    ends = []
    for x in (x_lo, x_hi):
        ends.append(sb.add(type=5, parent_id=0, branch_level=0,
                           translate_x=x, translate_y=0.0, translate_z=bar_z,
                           scale_x=0.9, scale_y=0.9, scale_z=0.9, geometry=1,
                           color_r=ACCENT[0], color_g=ACCENT[1],
                           color_b=ACCENT[2], color_a=255))
    sb.add(type=7, parent_id=ends[0], child_id=ends[1], branch_level=1,
           geometry=27, color_r=ACCENT[0], color_g=ACCENT[1],
           color_b=ACCENT[2], color_a=180)
    for day, label in MONTHS:
        sb.add(type=5, parent_id=0, branch_level=0,
               translate_x=x_of(day), translate_y=0.0, translate_z=bar_z + 2.0,
               scale_x=0.8, scale_y=0.8, scale_z=2.6, geometry=1,
               color_r=ACCENT[0], color_g=ACCENT[1], color_b=ACCENT[2],
               color_a=225, show_text=1, text=label)
    sb.add(type=5, parent_id=0, branch_level=0,
           translate_x=x_lo, translate_y=0.0, translate_z=bar_z + 5.0,
           scale_x=3.4, scale_y=3.4, scale_z=3.4, geometry=11,
           rotate_rate_z=0.7, color_r=255, color_g=246, color_b=190,
           color_a=255, ch_input_id=CURSOR_CHANNEL)

    sb.legend(-GLOBE_R - 52.0, -18.0)
    sb.caption(0.0, 0.0, GLOBE_R + 34.0,
               f"One composite year: every storm "
               f"{int(df.season.min())}-{int(df.season.max())} "
               f"placed on its day of the year", size=2.4)

    # --- channels -----------------------------------------------------------
    days = sorted(pts.doy.unique())
    map_rows = [dict(id=i + 1, channel_id=int(d), track_id=int(d),
                     attribute="color_a", track_table_id=0,
                     ch_map_table_id=0, record_id=0)
                for i, d in enumerate(days)]
    map_rows.append(dict(id=len(map_rows) + 1, channel_id=SUN_CHANNEL,
                         track_id=SUN_CHANNEL, attribute="translate_y",
                         track_table_id=0, ch_map_table_id=0, record_id=0))
    map_rows.append(dict(id=len(map_rows) + 1, channel_id=CURSOR_CHANNEL,
                         track_id=CURSOR_CHANNEL, attribute="translate_x",
                         track_table_id=0, ch_map_table_id=0, record_id=0))
    ch_map = pd.DataFrame(map_rows)

    data = {"cyclecount": list(range(1, PULSE_FRAMES + 1))}
    for d in days:
        data[f"ch{int(d)}"] = [circular_alpha(f, int(d), PULSE_FRAMES)
                               for f in range(PULSE_FRAMES)]
    data[f"ch{SUN_CHANNEL}"] = [round(solar_declination(f), 3)
                                for f in range(PULSE_FRAMES)]
    data[f"ch{CURSOR_CHANNEL}"] = [x_of(f + 1) for f in range(PULSE_FRAMES)]
    ch_tracks = pd.DataFrame(data)

    _ = sun
    return (sb.to_dataframe(), ch_map, ch_tracks,
            {"points": n, "channels": len(days) + 2,
             "frames": PULSE_FRAMES})


# ---------------------------------------------------------------------------
# 6. SCENE 3 — POLEWARD DRIFT (lifetime maximum intensity)
# ---------------------------------------------------------------------------
def lmi_table(df: pd.DataFrame) -> pd.DataFrame:
    """One row per storm: the position where it was at its strongest."""
    tro = df[(df.nature == "TS") & df.wind.notna()].copy()
    lmi = tro.loc[tro.groupby("sid").wind.idxmax()].copy()
    lmi = lmi[lmi.season >= DRIFT_FIRST_SEASON]
    # Drop a trailing partial season (the archive is updated in-year, and a
    # half-finished season would drag the endpoint of every trend).
    counts = lmi.groupby("season").size()
    if len(counts) > 3:
        typical = counts.iloc[:-1].median()
        while len(counts) > 3 and counts.iloc[-1] < 0.6 * typical:
            lmi = lmi[lmi.season != counts.index[-1]]
            counts = counts.iloc[:-1]
    lmi["hemi"] = np.where(lmi.lat >= 0, "N", "S")
    lmi["abslat"] = lmi.lat.abs()
    return lmi.sort_values("season").reset_index(drop=True)


def hemisphere_trend(lmi: pd.DataFrame, hemi: str, first: int, last: int):
    """Annual mean |LMI latitude|, its least-squares trend in deg/decade,
    and |slope| / standard-error-of-slope as a rough significance ratio."""
    s = lmi[(lmi.hemi == hemi) & lmi.season.between(first, last)]
    ann = s.groupby("season").abslat.mean()
    if len(ann) < 3:
        return ann, float("nan"), float("nan")
    x, y = ann.index.values.astype(float), ann.values
    slope, icept = np.polyfit(x, y, 1)
    resid = y - (slope * x + icept)
    se = math.sqrt((resid ** 2).sum() / (len(x) - 2)
                   / ((x - x.mean()) ** 2).sum())
    return ann, slope * 10.0, (abs(slope / se) if se else float("nan"))


def build_poleward_drift(df: pd.DataFrame):
    lmi = lmi_table(df)
    seasons = sorted(int(s) for s in lmi.season.unique())
    first, last = seasons[0], seasons[-1]
    total = len(seasons) + DRIFT_HOLD_FRAMES

    sb = SceneBuilder()
    sb.world()
    g = sb.globe()

    season_channel = {s: i + 1 for i, s in enumerate(seasons)}
    for p in lmi.itertuples(index=False):
        w = float(p.wind)
        _lab, rgb, cidx = category(w)
        sb.add(type=5, parent_id=g, branch_level=1,
               translate_x=round(float(p.lon), 4),
               translate_y=round(float(p.lat), 4),
               translate_z=elevation(w),
               scale_x=0.3, scale_y=0.3, scale_z=0.3,
               geometry=22, ratio=round(point_ratio(w) * 1.35, 3),
               # Visible in the CSV: playback overrides alpha frame by frame,
               # and Stop restores these values, so someone who opens the
               # scene and never presses Space still sees the whole
               # climatology rather than an empty globe.
               color_r=rgb[0], color_g=rgb[1], color_b=rgb[2], color_a=205,
               color_index=cidx,
               ch_input_id=season_channel[int(p.season)])

    # Two rings at the running-mean |LMI latitude|, one per hemisphere.
    # A latitude circle is a root-level torus: radius GLOBE_R*cos(lat),
    # centred on the spin axis at height GLOBE_R*sin(lat), stood off the
    # surface by RING_STANDOFF so it neither z-fights the globe nor hides
    # inside it. A fat tube (ratio) is what makes it readable at all — at
    # the hairline default the ring vanishes against the graticule.
    rings = {}
    for hemi, chan, rgb in (("N", RING_N_CHANNEL, (120, 230, 255)),
                            ("S", RING_S_CHANNEL, (255, 150, 200))):
        rings[hemi] = sb.add(
            type=5, parent_id=0, branch_level=0,
            translate_x=0.0, translate_y=0.0, translate_z=0.0,
            scale_x=GLOBE_R, scale_y=GLOBE_R, scale_z=GLOBE_R,
            geometry=6, ratio=0.028,
            color_r=rgb[0], color_g=rgb[1], color_b=rgb[2], color_a=235,
            ch_input_id=chan, show_text=1,
            text=f"mean latitude of peak intensity ({hemi} hemisphere)")

    ann_n, trend_n, sig_n = hemisphere_trend(lmi, "N", first, last)
    ann_s, trend_s, sig_s = hemisphere_trend(lmi, "S", first, last)

    sb.legend(-GLOBE_R - 52.0, -18.0)
    sb.caption(0.0, 0.0, GLOBE_R + 40.0,
               f"Where each storm peaked, {first}-{last}", size=2.4)
    sb.caption(0.0, 0.0, GLOBE_R + 32.0,
               f"mean |latitude| of lifetime maximum intensity drifts poleward:"
               f"  N {trend_n:+.2f} deg/decade ({sig_n:.1f} sigma)"
               f"   S {trend_s:+.2f} deg/decade ({sig_s:.1f} sigma)",
               size=1.5)

    # --- channels -----------------------------------------------------------
    map_rows = [dict(id=i + 1, channel_id=ch, track_id=ch,
                     attribute="color_a", track_table_id=0,
                     ch_map_table_id=0, record_id=0)
                for i, (_s, ch) in enumerate(sorted(season_channel.items()))]
    for chan, attr in ((RING_N_CHANNEL, "translate_z"),
                       (RING_N_CHANNEL, "scale_x"),
                       (RING_N_CHANNEL, "scale_y"),
                       (RING_S_CHANNEL, "translate_z"),
                       (RING_S_CHANNEL, "scale_x"),
                       (RING_S_CHANNEL, "scale_y")):
        map_rows.append(dict(id=len(map_rows) + 1, channel_id=chan,
                             track_id=chan if attr == "translate_z"
                             else chan + 1,
                             attribute=attr, track_table_id=0,
                             ch_map_table_id=0, record_id=0))
    ch_map = pd.DataFrame(map_rows)

    def alpha_track(birth_idx: int) -> list[int]:
        out = []
        for f in range(total):
            if f < birth_idx:
                out.append(0)
            elif f == birth_idx:
                out.append(255)
            else:
                age = f - birth_idx
                out.append(int(round(max(150 * math.exp(-age / 26.0), 55))))
        # relight everything for the last stretch: the full climatology
        for f in range(total - DRIFT_HOLD_FRAMES + 12, total):
            if out[f] > 0:
                out[f] = 200
        return out

    data = {"cyclecount": list(range(1, total + 1))}
    for s, ch in sorted(season_channel.items()):
        data[f"ch{ch}"] = alpha_track(seasons.index(s))

    def running_mean(ann: pd.Series) -> list[float]:
        """Value shown at each frame: mean |LMI lat| so far, smoothed."""
        vals, acc = [], []
        for s in seasons:
            if s in ann.index:
                acc.append(float(ann.loc[s]))
            window = acc[-9:] if len(acc) >= 9 else acc
            vals.append(sum(window) / len(window) if window else 15.0)
        vals += [vals[-1]] * DRIFT_HOLD_FRAMES
        return vals

    for hemi, chan, sign, ann in (("N", RING_N_CHANNEL, 1.0, ann_n),
                                  ("S", RING_S_CHANNEL, -1.0, ann_s)):
        lat = running_mean(ann)
        r = GLOBE_R * RING_STANDOFF
        data[f"ch{chan}"] = [round(sign * r * math.sin(math.radians(v)), 3)
                             for v in lat]
        data[f"ch{chan + 1}"] = [round(r * math.cos(math.radians(v)), 3)
                                 for v in lat]
    ch_tracks = pd.DataFrame(data)

    return (sb.to_dataframe(), ch_map, ch_tracks,
            {"storms": len(lmi), "seasons": len(seasons), "frames": total,
             "trend_n": trend_n, "trend_s": trend_s,
             "sig_n": sig_n, "sig_s": sig_s,
             "first": first, "last": last})


# ---------------------------------------------------------------------------
# 7. VALIDATION AND OUTPUT
# ---------------------------------------------------------------------------
BINDABLE = ({f"{p}_{a}" for p in ("translate", "rotate", "scale") for a in "xyz"}
            | {f"{p}_rate_{a}" for p in ("translate", "rotate", "scale")
               for a in "xyz"}
            | {"color_r", "color_g", "color_b", "color_a", "color_index",
               "palette_id", "texture_id", "ratio", "topo", "geometry",
               "mesh_id", "hide", "show_text", "render_mode", "fog_enabled",
               "fog_start", "fog_end"})


def validate(df: pd.DataFrame) -> list[str]:
    p = []
    if df.id.duplicated().any():
        p.append("duplicate ids")
    if (df.id < 1).any():
        p.append("ids must be >= 1")
    known = set(df.id)
    if len(df[(df.parent_id != 0) & (~df.parent_id.isin(known))]):
        p.append("rows with unknown parent_id")
    links = df[df.type == 7]
    if len(links) and (~links.child_id.isin(known)).any():
        p.append("link child_id references a missing node")
    for c in ("color_r", "color_g", "color_b", "color_a"):
        if ((df[c] < 0) | (df[c] > 255)).any():
            p.append(f"{c} out of 0..255")
    vis = df[(df.hide == 0) & (df.type.isin([5, 7]))]
    if (vis[["scale_x", "scale_y", "scale_z"]] < 0.2).any(axis=None):
        p.append("visible glyph with raw scale < 0.2")
    if df[df.type == 6].empty:
        p.append("no World Grid in the scene")
    kids = df[df.parent_id.isin(set(df[df.type == 6].id))]
    if len(kids) and (kids.translate_x.abs().max() > 180.0
                      or kids.translate_y.abs().max() > 90.0):
        p.append("globe child outside lon/lat range")
    return p


def validate_channels(df, ch_map, ch_tracks) -> list[str]:
    p = []
    channels = set(ch_map.channel_id)
    used = set(df.loc[df.ch_input_id != 0, "ch_input_id"])
    if used - channels:
        p.append(f"ch_input_id with no map row: {sorted(used - channels)[:6]}")
    if channels - used:
        p.append(f"map channel with no node: {sorted(channels - used)[:6]}")
    track_cols = {int(c[2:]) for c in ch_tracks.columns
                  if c.startswith("ch") and c[2:].isdigit()}
    if set(ch_map.track_id) - track_cols:
        p.append(f"map track_id with no ch<id> column: "
                 f"{sorted(set(ch_map.track_id) - track_cols)[:6]}")
    if set(ch_map.attribute) - BINDABLE:
        p.append(f"unbindable attributes: "
                 f"{sorted(set(ch_map.attribute) - BINDABLE)}")
    for t in ch_map.loc[ch_map.attribute == "color_a", "track_id"]:
        col = ch_tracks[f"ch{t}"]
        if ((col < 0) | (col > 255)).any():
            p.append(f"ch{t}: alpha out of 0..255")
            break
    scale_tracks = set(ch_map.loc[ch_map.attribute.isin(
        ["scale_x", "scale_y", "scale_z"]), "track_id"])
    for t in scale_tracks:
        if (ch_tracks[f"ch{t}"] < 0.2).any():
            p.append(f"ch{t}: animated scale below the 0.2 render floor")
            break
    return p


def write_csv(df: pd.DataFrame, path: Path, float_format="%.4f") -> None:
    """4 dp is 0.4 m of ground resolution at the equator on a scale-1 globe —
    far finer than best-track position uncertainty, and it keeps the biggest
    scene's node CSV to a size git is comfortable with."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8", lineterminator="\r\n",
              float_format=float_format)
    back = pd.read_csv(path, encoding="utf-8", low_memory=False)
    assert len(back) == len(df), f"round-trip row-count mismatch: {path}"


def emit(name: str, stem: str, node_df, ch_map=None, ch_tracks=None) -> bool:
    out = HERE / name
    problems = validate(node_df)
    if ch_map is not None:
        problems += validate_channels(node_df, ch_map, ch_tracks)
    if problems:
        for x in problems:
            print(f"  VALIDATION FAILURE [{name}]: {x}", file=sys.stderr)
        return False
    write_csv(node_df, out / f"{stem}_gv_node.csv")
    msg = f"  {name}: {len(node_df):,} nodes"
    if ch_map is not None:
        write_csv(ch_map, out / f"{stem}_gv_ch-map.csv", float_format=None)
        write_csv(ch_tracks, out / f"{stem}_gv_ch-tracks.csv",
                  float_format="%.3f")
        msg += (f", {len(ch_map):,} bindings, {len(ch_tracks):,} frames x "
                f"{len(ch_tracks.columns)-1:,} tracks")
    print(msg + "  [validation clean]")
    return True


# ---------------------------------------------------------------------------
# 8. MAIN
# ---------------------------------------------------------------------------
SCENES = ("Global_Tracks", "Seasonal_Pulse", "Poleward_Drift")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--download", action="store_true",
                    help="fetch the ~330 MB IBTrACS archive from NOAA")
    ap.add_argument("--source", metavar="CSV",
                    help="tidy a local raw ibtracs.ALL.list.v04r01.csv")
    ap.add_argument("--only", choices=SCENES, action="append",
                    help="build only the named scene(s)")
    args = ap.parse_args()

    if args.download or args.source:
        raw = Path(args.source) if args.source else \
            download_raw(DATA / "ibtracs.ALL.raw.csv")
        tidy = tidy_raw(raw)
        DATA.mkdir(parents=True, exist_ok=True)
        tidy.to_csv(SNAPSHOT, index=False, encoding="utf-8",
                    compression="gzip")
        print(f"  snapshot -> {SNAPSHOT} "
              f"({SNAPSHOT.stat().st_size/1e6:.1f} MB)")
    else:
        tidy = load_snapshot()
        print(f"Loaded snapshot: {len(tidy):,} synoptic points / "
              f"{tidy.sid.nunique():,} storms")

    wanted = args.only or list(SCENES)
    ok = True

    if "Global_Tracks" in wanted:
        node, info = build_global_tracks(tidy)
        ok &= emit("Global_Tracks", "CycloneTracks", node)
        print(f"     {info['points']:,} track points, "
              f"{info['storms']:,} storms")

    if "Seasonal_Pulse" in wanted:
        node, cmap, ctr, info = build_seasonal_pulse(tidy)
        ok &= emit("Seasonal_Pulse", "SeasonalPulse", node, cmap, ctr)

    if "Poleward_Drift" in wanted:
        node, cmap, ctr, info = build_poleward_drift(tidy)
        ok &= emit("Poleward_Drift", "PolewardDrift", node, cmap, ctr)
        print(f"     {info['storms']:,} storms {info['first']}-{info['last']};"
              f" mean |LMI lat| trend  N {info['trend_n']:+.3f}"
              f" ({info['sig_n']:.1f}s)  S {info['trend_s']:+.3f}"
              f" ({info['sig_s']:.1f}s) deg/decade")

    print("\nOpen any scene's node CSV in GlyphViz (its media/ folder and "
          "ch files sit beside it). Space plays the animated ones.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
