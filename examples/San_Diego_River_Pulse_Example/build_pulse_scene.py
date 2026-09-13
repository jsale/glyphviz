#!/usr/bin/env python3
"""
build_pulse_scene.py — the San Diego River's pulse, one frame per month since 1912
=================================================================================

Phase 2 of the San Diego River Watershed Atlas: "The Pulse". Time arrives.
The Phase 1 frame (terrain, divide, river network, gauges, rain stations,
places) is rebuilt unchanged underneath, and three layers are laid over it:

  * FLOW RIBBONS. Each of the three USGS gauges drives a ribbon draped over
    the reach it measures: Mast Rd -> Fashion Valley, Fashion Valley -> the
    sea, and Los Coches Creek from its gauge to the river. Ribbon WIDTH is
    that month's mean flow on a log scale, so every winter swells the river
    and every summer shrinks it to a thread; ribbon COLOUR says whether the
    month was wetter or drier than the same calendar month in the gauge's
    other years. A month the gauge did not record hides its ribbon.
  * RAIN COLUMNS. A column rises over each of the four long-record NOAA rain
    stations, its height that month's total rainfall and its colour the same
    wetter/drier-than-usual scale. A month with too many missing days hides
    the column (only Cuyamaca comes close to a complete century).
  * THE PANEL, standing beyond the plate's east edge, in two strips. Below,
    THE CENTURY: every water year since 1913, Mast Rd's annual mean flow as a
    line (log) and Cuyamaca's annual rainfall as bars hanging from the top
    (the hydrologist's convention), with the dams and the Cedar Fire marked
    and a cursor sweeping it. Above, THE LAST TEN YEARS: a live monthly
    window that scrolls with the clock, its right-hand end always "now", with
    the month and year read out beside it. Monthly data across the whole
    century is 1,372 samples on one panel and reads as a barcode; that is
    why the monthly detail lives in the window.

Clock: one Channels frame per calendar month, May 1912 (the first month of
the Mast Rd record) through the last month the gauge has recorded in full.

Data: ../San_Diego_River_Watershed_Example/watershed_data.py, cached under
that folder's data/ — the Atlas phases share one data directory.

USAGE
-----
    python build_pulse_scene.py              # build (uses cached data)
    python build_pulse_scene.py --refresh    # re-download everything
"""

from __future__ import annotations

import argparse
import bisect
import math
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
FRAME_DIR = REPO / "examples" / "San_Diego_River_Watershed_Example"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(FRAME_DIR))

import build_watershed_scene as fm                                  # noqa: E402
import watershed_data as wd                                         # noqa: E402
from glyphviz_core import terrain as tr                             # noqa: E402

# ---------------------------------------------------------------------------
# 1. CONFIGURATION
# ---------------------------------------------------------------------------

OUT_STEM = "sd_river_pulse"
FIRST_MONTH = "1912-05"                  # the Mast Rd record's first month
MAX_MISSING_FLOW_DAYS = 3                # a month missing more is a gap

MAST, FASHION, LOS_COCHES = "11022480", "11023000", "11022200"
CUYAMACA = "USC00042239"

# Ribbon width: log10(cfs) from RIBBON_LOG_LO to RIBBON_LOG_HI maps onto
# RIBBON_PX, in screen pixels (ratio * 20). Below DRY_CFS the river is dry and
# the ribbon drops to a 1-pixel ochre thread.
RIBBON_LOG_LO, RIBBON_LOG_HI = -1.0, 3.0       # 0.1 .. 1,000 cfs
RIBBON_PX = (2.0, 14.0)
DRY_CFS = 0.005
DRY_PX = 1.0
RIBBON_CLEARANCE = 1.6                   # world units; the static line is at 0.8

# Rain columns (grid children, world units).
RAIN_UNITS_PER_INCH = 1.5
RAIN_RADIUS = 1.4
RAIN_LIFT = 1.8                          # clears the station's own octahedron
RAIN_MIN_HALF = 0.05                     # a dry month is a thin disc

# Wetter/drier-than-usual ramp, by the month's percentile among the same
# calendar month in that series' other years.
RAMP = [(0.0, (196, 120, 52)), (0.25, (222, 180, 110)), (0.5, (228, 226, 214)),
        (0.75, (120, 190, 245)), (1.0, (40, 120, 255))]

# The panel stands beyond the plate's east edge, facing the opening camera
# (which looks east from over the Pacific), time running north -> south so it
# reads left -> right on screen. Two strips: the century below, a scrolling
# ten-year monthly window above.
PANEL_GAP = 26.0
PANEL_SPAN = 1.0                         # fraction of the plate's N-S half-extent
PANEL_Z0 = 96.0                          # clears the skyline AND its labels
CENTURY_H = 76.0
CENTURY_FLOW_LOG = (-1.0, 3.0)           # annual mean, 0.1 .. 1,000 cfs
CENTURY_RAIN_PER_INCH = 0.45             # annual totals reach ~80 in
STRIP_GAP = 34.0
WINDOW_MONTHS = 120
WINDOW_H = 100.0
WINDOW_FLOW_LOG = (-2.0, 3.5)            # monthly mean, 0.01 .. ~3,200 cfs
WINDOW_RAIN_PER_INCH = 1.1               # monthly totals reach 36.5 in

LEGEND_TOP, LEGEND_STEP = 190.0, 16.0

FLOW_LINE = (150, 230, 255)
RAIN_LINE = (190, 170, 250)
CURSOR_COLOR = (255, 226, 120)

GEO_CUBE_WIRE, GEO_CUBE, GEO_SPHERE, GEO_CYLINDER, GEO_POINT = 0, 1, 3, 19, 22
# GEO_CUBE is inscribed in the unit sphere: its half-extent is 1/sqrt(3), not
# 1 like the cylinder's. A bar that must span an exact height divides by this.
CUBE_HALF = 1.0 / math.sqrt(3.0)
MAX_MISSING_RAIN_MONTHS = 2              # a water year missing more is a gap
TOPO_PLOT = 16
NODE_GLYPH = 5


# ---------------------------------------------------------------------------
# 2. SERIES
# ---------------------------------------------------------------------------

@dataclass
class Series:
    """One monthly series on the scene clock: value per frame or None."""
    key: str
    values: list[float | None]
    pct: list[float | None] = field(default_factory=list)

    def percentiles(self, months: list[str]) -> None:
        """Mid-rank percentile of each month among the same calendar month in
        the series' other years. Ties (dry months, mostly) share a rank."""
        by_cal: dict[str, list[float]] = {}
        for m, v in zip(months, self.values):
            if v is not None:
                by_cal.setdefault(m[5:], []).append(v)
        for vs in by_cal.values():
            vs.sort()
        self.pct = []
        for m, v in zip(months, self.values):
            if v is None:
                self.pct.append(None)
                continue
            vs = by_cal[m[5:]]
            lo, hi = bisect.bisect_left(vs, v), bisect.bisect_right(vs, v)
            self.pct.append((lo + 0.5 * (hi - lo)) / len(vs))


def last_complete_month(flow: dict) -> str:
    return max(k for k, v in flow["months"].items() if v["days"] == v["of"])


def flow_series(site: str, months: list[str], refresh: bool) -> Series:
    got = wd.fetch_monthly_flow(site, refresh)["months"]
    vals = []
    for m in months:
        r = got.get(m)
        vals.append(r["cfs"] if r and r["of"] - r["days"] <= MAX_MISSING_FLOW_DAYS
                    else None)
    s = Series(site, vals)
    s.percentiles(months)
    return s


def rain_series(ghcn: str, months: list[str], refresh: bool) -> Series:
    got = wd.fetch_monthly_rain(ghcn, refresh)["months"]
    s = Series(ghcn, [got.get(m) for m in months])
    s.percentiles(months)
    return s


def ramp(p: float) -> tuple[int, int, int]:
    for (p0, c0), (p1, c1) in zip(RAMP, RAMP[1:]):
        if p <= p1:
            t = 0.0 if p1 == p0 else (p - p0) / (p1 - p0)
            return tuple(int(round(a + (b - a) * t)) for a, b in zip(c0, c1))
    return RAMP[-1][1]


def ribbon_ratio(cfs: float) -> float:
    if cfs < DRY_CFS:
        return DRY_PX / 20.0
    t = (math.log10(cfs) - RIBBON_LOG_LO) / (RIBBON_LOG_HI - RIBBON_LOG_LO)
    t = min(max(t, 0.0), 1.0)
    return round((RIBBON_PX[0] + (RIBBON_PX[1] - RIBBON_PX[0]) * t) / 20.0, 4)


def month_label(m: str) -> str:
    import calendar
    return f"{calendar.month_name[int(m[5:])]} {m[:4]}"


# ---------------------------------------------------------------------------
# 3. CHANNELS
# ---------------------------------------------------------------------------

@dataclass
class Channels:
    """Allocates channel ids and tracks; one track per bound attribute."""
    n_frames: int
    map_rows: list[dict] = field(default_factory=list)
    tracks: dict[int, list] = field(default_factory=dict)
    next_id: int = 1

    def channel(self, **attr_tracks) -> int:
        ch = self.next_id
        self.next_id += 1
        for attr, values in attr_tracks.items():
            assert len(values) == self.n_frames, attr
            tid = len(self.tracks) + 1
            self.tracks[tid] = list(values)
            self.map_rows.append(dict(id=len(self.map_rows) + 1, channel_id=ch,
                                      track_id=tid, attribute=attr,
                                      track_table_id=0, ch_map_table_id=0,
                                      record_id=0))
        return ch

    def frames(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        data = {"cyclecount": list(range(1, self.n_frames + 1))}
        for tid, vals in self.tracks.items():
            data[f"ch{tid}"] = vals
        return pd.DataFrame(self.map_rows), pd.DataFrame(data)


# ---------------------------------------------------------------------------
# 4. SCENE
# ---------------------------------------------------------------------------

COLUMNS = fm.COLUMNS + ["ch_input_id"]


@dataclass
class Rows:
    rows: list[dict]

    def add(self, **kw) -> int:
        nid = len(self.rows) + 1
        self.rows.append({**fm.DEFAULTS, "ch_input_id": 0, "id": nid, **kw})
        return nid

    def set(self, nid: int, **kw) -> None:
        self.rows[nid - 1].update(kw)

    def frame(self) -> pd.DataFrame:
        df = pd.DataFrame(self.rows, columns=COLUMNS)
        df["ch_input_id"] = df["ch_input_id"].fillna(0).astype(int)
        return df


def nearest_index(coords, lon, lat) -> tuple[int, float]:
    c = np.asarray(coords)[:, :2]
    k = math.cos(math.radians(lat))
    d = np.hypot((c[:, 0] - lon) * k, c[:, 1] - lat) * 111_320.0
    i = int(d.argmin())
    return i, float(d[i])


@dataclass
class Built:
    df: pd.DataFrame
    ch_map: pd.DataFrame
    ch_tracks: pd.DataFrame
    notes: list[str]
    checks: dict


# ---------------------------------------------------------------------------
# Shared layers — also used by the Atlas's storm scene
# ---------------------------------------------------------------------------

GAUGE_NAMES = {MAST: "Mast Rd, Santee", FASHION: "Fashion Valley",
               LOS_COCHES: "Los Coches Creek nr Lakeside"}


def rows_without_legend(base, title: str) -> tuple[Rows, int]:
    """The Phase 1 rows minus its Strahler legend (the last seven rows; a
    scene with time needs that space for its own legend), retitled.
    -> (rows, World Grid id)."""
    recs = base.df.to_dict("records")
    assert recs[-7]["text"] == "Strahler stream order", recs[-7]["text"]
    assert recs[-1]["text"].startswith("relief"), recs[-1]["text"]
    R = Rows([{**r, "ch_input_id": 0} for r in recs[:-7]])
    assert R.rows[0]["type"] == fm.NODE_WORLD
    R.set(1, text=title)
    grid_id = next(r["id"] for r in R.rows if r["type"] == fm.NODE_GRID)
    return R, grid_id


def _join(runs) -> list:
    out: list = []
    for s in sorted(runs, key=lambda s: s.drainage_km2):
        pts = s.coords
        if out and wd._key(out[-1]) == wd._key(pts[0]):
            pts = pts[1:]
        out.extend(pts)
    return out


def gauge_reaches(notes: list[str]) -> list[tuple[str, list, str]]:
    """The stretch of channel each gauge measures, upstream -> downstream:
    Mast Rd -> Fashion Valley, Fashion Valley -> the sea, and Los Coches Creek
    from its gauge to the river. -> [(site, lon/lat coords, description)]."""
    gauges = {g["site"]: g for g in wd.fetch_gauges()}
    streams = wd.build_streams(wd.fetch_network())
    main_coords = _join(s for s in streams if s.mainstem)
    lc_coords = _join(s for s in streams if s.name.strip() == "Los Coches Creek")
    i_mast, d_mast = nearest_index(main_coords, gauges[MAST]["lon"], gauges[MAST]["lat"])
    i_fv, d_fv = nearest_index(main_coords, gauges[FASHION]["lon"], gauges[FASHION]["lat"])
    i_lc, d_lc = nearest_index(lc_coords, gauges[LOS_COCHES]["lon"], gauges[LOS_COCHES]["lat"])
    notes.append(f"gauge-to-channel distance: Mast Rd {d_mast:.0f} m, "
                 f"Fashion Valley {d_fv:.0f} m, Los Coches {d_lc:.0f} m")
    return [
        (MAST, main_coords[i_mast:i_fv + 1], "Mast Rd -> Fashion Valley"),
        (FASHION, main_coords[i_fv:], "Fashion Valley -> the sea"),
        (LOS_COCHES, lc_coords[i_lc:], "Los Coches Creek, gauge -> the river"),
    ]


def pct_colors(pct: list) -> list[tuple[int, int, int]]:
    """Ramp colour per frame; a gap carries the previous colour forward rather
    than flashing black on the frame the glyph comes back (it is hidden
    meanwhile anyway)."""
    cols = [ramp(p) if p is not None else (0, 0, 0) for p in pct]
    for f in range(1, len(cols)):
        if pct[f] is None:
            cols[f] = cols[f - 1]
    return cols


def add_flow_ribbon(R: Rows, ch: Channels, frame: fm.Frame, checks: dict, coords,
                    values: list, cols: list, rest: int, text: str, link: str) -> int:
    """A ribbon draped over *coords*: width <- log flow (the Plot parent's
    bound ratio), colour <- *cols* (one channel shared by every vertex), hidden
    where *values* is None. -> parent id."""
    layout, lattice = frame.layout, frame.lattice
    clear_m = RIBBON_CLEARANCE / layout.z_per_m
    lons, lats = tr.simplify_polyline([p[0] for p in coords],
                                      [p[1] for p in coords], fm.SIMPLIFY_M)
    dl, dt, dh = tr.drape_polyline(lattice, lons, lats, clearance=clear_m)
    wx, wy = layout.world_xy(dl, dt)
    wz = dh * layout.z_per_m
    ratio_t = [ribbon_ratio(v) if v is not None else DRY_PX / 20.0 for v in values]
    hide_t = [0 if v is not None else 1 for v in values]
    par_ch = ch.channel(ratio=ratio_t, hide=hide_t)
    kid_ch = ch.channel(color_r=[c[0] for c in cols], color_g=[c[1] for c in cols],
                        color_b=[c[2] for c in cols])
    c_rest = cols[rest]
    ax, ay = float(wx[0]), float(wy[0])
    az = lattice.surface_height(dl[0], dt[0]) * layout.z_per_m
    parent = R.add(type=NODE_GLYPH, parent_id=0, branch_level=0,
                   geometry=GEO_POINT, topo=TOPO_PLOT, ratio=ratio_t[rest],
                   hide=hide_t[rest], color_r=c_rest[0], color_g=c_rest[1],
                   color_b=c_rest[2], color_a=0,
                   translate_x=fm._r(ax), translate_y=fm._r(ay),
                   translate_z=fm._r(az), ch_input_id=par_ch, text=text, link=link)
    for k in range(len(dl)):
        R.add(type=NODE_GLYPH, parent_id=parent, branch_level=1,
              geometry=GEO_CUBE, scale_x=0.0, scale_y=0.0, scale_z=0.0,
              translate_x=fm._r(wx[k] - ax), translate_y=fm._r(wy[k] - ay),
              translate_z=fm._r(wz[k] - az),
              color_r=c_rest[0], color_g=c_rest[1], color_b=c_rest[2],
              ch_input_id=kid_ch)
    checks["lines"].append((parent, dl, dt))
    return parent


def add_rain_column(R: Rows, ch: Channels, frame: fm.Frame, checks: dict, grid_id: int,
                    lon: float, lat: float, values: list, cols: list, rest: int,
                    text: str, units_per_inch: float = RAIN_UNITS_PER_INCH,
                    geometry_t: list | None = None) -> int:
    """A World Grid child standing on the rendered surface at lon/lat whose
    height is *values* (inches) and colour *cols*, hidden where a value is
    None. *geometry_t*, when given, is also bound (solid vs wire). -> id."""
    layout, lattice = frame.layout, frame.lattice
    gsz = layout.grid_scale_z
    ground_km = lattice.surface_height(lon, lat) / 1000.0
    half = [max((v or 0.0) * units_per_inch / 2.0, RAIN_MIN_HALF) for v in values]
    tz = [round(ground_km + (RAIN_LIFT + h) / gsz, 6) for h in half]
    hide_t = [0 if v is not None else 1 for v in values]
    tracks = dict(scale_z=[round(h, 4) for h in half], translate_z=tz, hide=hide_t,
                  color_r=[c[0] for c in cols], color_g=[c[1] for c in cols],
                  color_b=[c[2] for c in cols])
    if geometry_t is not None:
        tracks["geometry"] = geometry_t
    cch = ch.channel(**tracks)
    nid = R.add(type=NODE_GLYPH, parent_id=grid_id, branch_level=1,
                geometry=geometry_t[rest] if geometry_t else GEO_CYLINDER,
                translate_x=fm._r(lon, 6), translate_y=fm._r(lat, 6),
                translate_z=tz[rest], scale_x=RAIN_RADIUS, scale_y=RAIN_RADIUS,
                scale_z=round(half[rest], 4), hide=hide_t[rest],
                color_r=cols[rest][0], color_g=cols[rest][1], color_b=cols[rest][2],
                ch_input_id=cch, segments_x=16, segments_y=4, text=text)
    checks["columns"].append((nid, lon, lat, half, tz))
    return nid


def build(frame: fm.Frame, refresh: bool) -> Built:
    layout, lattice = frame.layout, frame.lattice
    base = fm.build(layout, lattice, frame.dem, frame.map_path, home=None)
    notes = list(base.notes)
    checks = base.checks
    checks["columns"] = []

    R, grid_id = rows_without_legend(base, "San Diego River Watershed Atlas · "
                                           "Phase 2 · The Pulse")

    # -- Clock ----------------------------------------------------------------
    mast_raw = wd.fetch_monthly_flow(MAST, refresh)
    last = last_complete_month(mast_raw)
    months = wd._month_keys(FIRST_MONTH, last)
    n = len(months)
    flows = {s: flow_series(s, months, refresh) for s in (MAST, FASHION, LOS_COCHES)}
    rains = {s: rain_series(s, months, refresh) for s in wd.RAIN_STATIONS}
    notes.append(f"clock: {n} monthly frames, {months[0]} .. {months[-1]}")
    for s, se in flows.items():
        notes.append(f"flow {s}: {sum(v is not None for v in se.values)} of {n} months")
    for s, se in rains.items():
        notes.append(f"rain {s}: {sum(v is not None for v in se.values)} of {n} months")

    # The resting pose — what the CSV holds, and so what every screenshot and
    # every pre-playback view shows (export_frame does not apply channels):
    # the month, with all three gauges and Cuyamaca reporting, of the highest
    # flows (log, summed across the gauges). Absolute, not percentile: ranked
    # by percentile the winner is a summer storm (Aug 2023) that is unusual
    # for August but leaves the river a thread.
    def score(f):
        vs = [flows[s].values[f] for s in flows] + [rains[CUYAMACA].values[f]]
        if any(v is None for v in vs):
            return -99.0
        return sum(math.log10(max(v, 0.01)) for v in vs[:3])
    rest = max(range(n), key=score)
    notes.append(f"resting pose: frame {rest}, {month_label(months[rest])}")

    ch = Channels(n)

    # -- Flow ribbons ---------------------------------------------------------
    for site, coords, what in gauge_reaches(notes):
        se = flows[site]
        add_flow_ribbon(
            R, ch, frame, checks, coords, se.values, pct_colors(se.pct), rest,
            text=(f"Flow ribbon · USGS {site} {GAUGE_NAMES[site]} · "
                  f"{what} · width = monthly mean flow (log), "
                  f"colour = wetter/drier than usual for the month"),
            link=f"https://waterdata.usgs.gov/monitoring-location/{site}/")
        v0 = se.values[rest]
        notes.append(f"ribbon {site} ({what}): {len(checks['lines'][-1][1])} draped "
                     f"vertices, at rest {v0 if v0 is None else round(v0, 1)} cfs")

    # -- Rain columns -----------------------------------------------------------
    for st in wd.fetch_rain_stations():
        se = rains[st["ghcn"]]
        add_rain_column(
            R, ch, frame, checks, grid_id, st["lon"], st["lat"], se.values,
            pct_colors(se.pct), rest,
            text=(f"Monthly rainfall · NOAA GHCN {st['ghcn']} {st['name']} · "
                  f"height = inches ({RAIN_UNITS_PER_INCH:g} world units per "
                  f"inch), colour = wetter/drier than usual for the month"))

    # -- The panel: two strips standing beyond the plate's east edge ----------
    # Lower, THE CENTURY: one point per water year, readable at a glance, with
    # a cursor sweeping it. Upper, THE LAST TEN YEARS: a live monthly window
    # that scrolls as the clock runs, its right-hand end always "now". At
    # century scale a monthly line is 1,372 samples across the panel and reads
    # as a barcode, which is why the monthly detail lives in the window.
    px = layout.half_w + PANEL_GAP
    Y0 = layout.half_h * PANEL_SPAN
    X_LINE, X_BAR, X_BACK = px - 0.6, px - 0.2, px + 0.6

    def polyline(pts, width, color, label, show=0, anchor=0, kid_channels=None,
                 kid_hide=None):
        """pts = [(y, z)] at X_LINE. The invisible parent handle, which carries
        the label, sits at pts[anchor]."""
        ay, az = pts[anchor]
        par = R.add(type=NODE_GLYPH, parent_id=0, branch_level=0,
                    geometry=GEO_POINT, topo=TOPO_PLOT, ratio=width,
                    color_r=color[0], color_g=color[1], color_b=color[2], color_a=0,
                    translate_x=fm._r(X_LINE), translate_y=fm._r(ay),
                    translate_z=fm._r(az), show_text=show, text=label)
        for k, (y, z) in enumerate(pts):
            R.add(type=NODE_GLYPH, parent_id=par, branch_level=1, geometry=GEO_CUBE,
                  scale_x=0.0, scale_y=0.0, scale_z=0.0,
                  translate_y=fm._r(y - ay), translate_z=fm._r(z - az),
                  color_r=color[0], color_g=color[1], color_b=color[2],
                  hide=kid_hide[k] if kid_hide else 0,
                  ch_input_id=kid_channels[k] if kid_channels else 0)
        return par

    def label(y, z, text, pinned=1):
        return R.add(type=NODE_GLYPH, parent_id=0, branch_level=0, geometry=GEO_CUBE,
                     scale_x=0.0, scale_y=0.0, scale_z=0.0, translate_x=fm._r(px - 1.0),
                     translate_y=fm._r(y), translate_z=fm._r(z), show_text=pinned,
                     text=text)

    def backing(z0, z1, text):
        R.add(type=NODE_GLYPH, parent_id=0, branch_level=0, geometry=GEO_CUBE,
              translate_x=fm._r(X_BACK), translate_y=0.0,
              translate_z=fm._r((z0 + z1) / 2), scale_x=fm._r(0.3 / CUBE_HALF, 4),
              scale_y=fm._r((Y0 + 5) / CUBE_HALF, 4),
              scale_z=fm._r(((z1 - z0) / 2 + 2) / CUBE_HALF, 4),
              color_r=22, color_g=28, color_b=32, text=text)

    def log_z(cfs, lo, hi, z0, z1):
        t = (math.log10(max(cfs, 10 ** lo)) - lo) / (hi - lo)
        return z0 + (z1 - z0) * min(max(t, 0.0), 1.0)

    def runs(values):
        cur = []
        for i, v in enumerate(values):
            if v is None:
                if len(cur) >= 2:
                    yield cur
                cur = []
            else:
                cur.append((i, v))
        if len(cur) >= 2:
            yield cur

    # ---- The century strip -------------------------------------------------
    C_Z0, C_TOP = PANEL_Z0, PANEL_Z0 + CENTURY_H

    def cy(f: float) -> float:
        return Y0 - 2 * Y0 * f / (n - 1)

    def c_flow_z(cfs):
        return log_z(cfs, *CENTURY_FLOW_LOG, C_Z0 + 3, C_Z0 + CENTURY_H / 2)

    import calendar
    wys = []                     # (water year, centre frame, mean cfs|None, rain|None)
    for wy in range(int(months[0][:4]) + 1, int(months[-1][:4]) + 1):
        idx = [months.index(f"{wy - 1}-{m:02d}") if f"{wy - 1}-{m:02d}" in months else None
               for m in (10, 11, 12)] + \
              [months.index(f"{wy}-{m:02d}") if f"{wy}-{m:02d}" in months else None
               for m in range(1, 10)]
        if any(i is None for i in idx):
            continue
        q = [flows[MAST].values[i] for i in idx]
        days = [calendar.monthrange(int(months[i][:4]), int(months[i][5:]))[1] for i in idx]
        mean = (sum(v * d for v, d in zip(q, days)) / sum(days)
                if all(v is not None for v in q) else None)
        r = [rains[CUYAMACA].values[i] for i in idx]
        missing = sum(v is None for v in r)
        # A year missing one or two months still has a true LOWER BOUND; it is
        # drawn as a wire bar and labelled "at least". More missing than that
        # and the bar would mislead, so the year is a gap.
        total = sum(v for v in r if v is not None) if missing <= MAX_MISSING_RAIN_MONTHS else None
        wys.append((wy, idx[0] + 5.5, mean, total, missing))
    totals = sorted(t for _w, _c, _m, t, miss in wys if t is not None and miss == 0)
    notes.append(f"water years {wys[0][0]}..{wys[-1][0]}: "
                 f"{sum(m is not None for _w, _c, m, _t, _x in wys)} with a complete Mast Rd "
                 f"year; Cuyamaca {len(totals)} complete, "
                 f"{sum(1 for *_a, t, miss in wys if t is not None and miss)} lower bounds")

    backing(C_Z0 - 1, C_TOP + 1,
            "The century · every water year (October-September) since 1913")
    label(cy(0), C_TOP + 9, "Every water year since 1913")
    for e in range(int(CENTURY_FLOW_LOG[0]), int(CENTURY_FLOW_LOG[1]) + 1):
        polyline([(cy(0) + 2, c_flow_z(10 ** e)), (cy(n - 1) - 2, c_flow_z(10 ** e))],
                 0.03, (70, 84, 90), f"{10 ** e:g} cfs", show=1 if e % 2 else 0, anchor=1)
    ref_in = 40
    polyline([(cy(0) + 2, C_TOP - ref_in * CENTURY_RAIN_PER_INCH),
              (cy(n - 1) - 2, C_TOP - ref_in * CENTURY_RAIN_PER_INCH)],
             0.03, (84, 76, 100), f"{ref_in} in a year", show=1, anchor=1)

    bar_half_w = (2 * Y0 * 12 / (n - 1)) * 0.42
    for wy, cf, mean, total, miss in wys:
        if total is None:
            continue
        half = total * CENTURY_RAIN_PER_INCH / 2
        if miss:
            c, geo = (150, 140, 170), GEO_CUBE_WIRE
            what = (f"at least {total:.1f} in ({miss} month{'s' if miss > 1 else ''} "
                    f"not recorded)")
        else:
            lo, hi = bisect.bisect_left(totals, total), bisect.bisect_right(totals, total)
            c, geo = ramp((lo + 0.5 * (hi - lo)) / len(totals)), GEO_CUBE
            what = f"{total:.1f} in"
        R.add(type=NODE_GLYPH, parent_id=0, branch_level=0, geometry=geo,
              translate_x=fm._r(X_BAR), translate_y=fm._r(cy(cf)),
              translate_z=fm._r(C_TOP - half), scale_x=fm._r(0.2 / CUBE_HALF, 4),
              scale_y=fm._r(bar_half_w / CUBE_HALF, 4),
              scale_z=fm._r(half / CUBE_HALF, 4), color_r=c[0], color_g=c[1], color_b=c[2],
              text=(f"Water year {wy} · Cuyamaca {what}"
                    + (f" · Mast Rd mean {mean:,.1f} cfs" if mean is not None else
                       " · Mast Rd year incomplete")))
    for run in runs([m for _w, _c, m, _t, _x in wys]):
        polyline([(cy(wys[i][1]), c_flow_z(v)) for i, v in run], 0.08, FLOW_LINE,
                 f"Mast Rd annual mean flow, water years {wys[run[0][0]][0]}..{wys[run[-1][0]][0]}")

    for f, m in enumerate(months):
        if m.endswith("-01") and int(m[:4]) % 10 == 0:
            major = int(m[:4]) % 20 == 0
            R.add(type=NODE_GLYPH, parent_id=0, branch_level=0, geometry=GEO_CUBE,
                  translate_x=fm._r(X_LINE), translate_y=fm._r(cy(f)),
                  translate_z=fm._r(C_Z0 - 3.0), scale_x=0.3, scale_y=0.3,
                  scale_z=2.0 if major else 1.0, color_r=150, color_g=160, color_b=170,
                  show_text=1 if major else 0, text=m[:4])

    # Events: what the data itself shows (the record month, the 1916 gap) and
    # the two dams that change what the gauge sees. Dates: City of San Diego
    # (dams), CAL FIRE FRAP (Cedar). Pinned labels stagger downward so
    # neighbours a decade apart do not overwrite each other.
    def event(m: str, text: str, row: int | None, color=(200, 190, 170)):
        f = months.index(m)
        polyline([(cy(f), C_Z0 + 0.5), (cy(f), C_TOP - 0.5)], 0.03, color, text)
        if row is not None:
            R.add(type=NODE_GLYPH, parent_id=0, branch_level=0, geometry=GEO_CUBE,
                  translate_x=fm._r(X_LINE), translate_y=fm._r(cy(f)),
                  translate_z=fm._r(C_Z0 - 13 - 9 * row), scale_x=0.5, scale_y=0.5,
                  scale_z=0.5, color_r=color[0], color_g=color[1], color_b=color[2],
                  show_text=1, text=text)

    rec = max(range(n), key=lambda f: flows[MAST].values[f] or -1)
    wettest = max(range(n), key=lambda f: rains[CUYAMACA].values[f] or -1)
    event(months[rec], f"{month_label(months[rec])} · the record month at Mast Rd, "
          f"{flows[MAST].values[rec]:,.0f} cfs mean", None)
    gap_1916 = [m for m, v in zip(months, flows[MAST].values) if v is None and m < "1920"]
    if gap_1916:
        event(gap_1916[0], f"No Mast Rd record {month_label(gap_1916[0])} – "
              f"{month_label(gap_1916[-1])}; {month_label(months[wettest])} is Cuyamaca's "
              f"wettest month on record, {rains[CUYAMACA].values[wettest]:.1f} in", None)
    event("1934-12", "El Capitan Dam completed, 1934", 0, (235, 200, 140))
    event("1943-06", "San Vicente Dam completed, 1943", 1, (235, 200, 140))
    event("2003-10", "Cedar Fire, October 2003", 2, (240, 130, 90))

    cur_scale = 1.3
    cur_z = C_TOP + 3.0
    checks["cursor"] = dict(y=[cy(f) for f in range(n)])
    cursor = R.add(type=NODE_GLYPH, parent_id=0, branch_level=0, geometry=GEO_SPHERE,
                   translate_x=fm._r(px - 1.5), translate_y=fm._r(cy(rest)),
                   translate_z=fm._r(cur_z), scale_x=cur_scale, scale_y=cur_scale,
                   scale_z=cur_scale, color_r=CURSOR_COLOR[0],
                   color_g=CURSOR_COLOR[1], color_b=CURSOR_COLOR[2],
                   ch_input_id=ch.channel(translate_y=[fm._r(cy(f)) for f in range(n)]),
                   segments_x=16, segments_y=12, text="now, on the century")
    # The bar is the cursor's child so it rides along; a child's translate and
    # scale are multiplied by its parent's scale, hence the divisions.
    R.add(type=NODE_GLYPH, parent_id=cursor, branch_level=1, geometry=GEO_CUBE,
          translate_z=fm._r(-(cur_z - (C_Z0 + C_TOP) / 2) / cur_scale, 4),
          scale_x=fm._r(0.2 / CUBE_HALF / cur_scale, 4),
          scale_y=fm._r(0.2 / CUBE_HALF / cur_scale, 4),
          scale_z=fm._r((CENTURY_H / 2) / CUBE_HALF / cur_scale, 4),
          color_r=CURSOR_COLOR[0], color_g=CURSOR_COLOR[1], color_b=CURSOR_COLOR[2],
          text="now, on the century")

    # ---- The last-ten-years window ------------------------------------------
    W = WINDOW_MONTHS
    W_Z0 = C_TOP + STRIP_GAP
    W_TOP = W_Z0 + WINDOW_H

    def wy_(k: int) -> float:
        return Y0 - 2 * Y0 * k / (W - 1)

    def w_flow_z(cfs):
        return log_z(cfs, *WINDOW_FLOW_LOG, W_Z0 + 4, W_Z0 + WINDOW_H * 0.56)

    backing(W_Z0 - 1, W_TOP + 1, "The last ten years, month by month")
    label(wy_(0), W_TOP + 9, "The last 10 years, month by month")
    for e in range(int(WINDOW_FLOW_LOG[0]), int(math.floor(WINDOW_FLOW_LOG[1])) + 1):
        polyline([(wy_(0) + 2, w_flow_z(10 ** e)), (wy_(W - 1) - 2, w_flow_z(10 ** e))],
                 0.03, (70, 84, 90), f"{10 ** e:g} cfs", show=1 if e % 2 == 0 else 0,
                 anchor=1)
    polyline([(wy_(0) + 2, W_TOP - 10 * WINDOW_RAIN_PER_INCH),
              (wy_(W - 1) - 2, W_TOP - 10 * WINDOW_RAIN_PER_INCH)],
             0.03, (84, 76, 100), "10 in a month", show=1, anchor=1)
    label(wy_(0), W_Z0 - 5, "ten years earlier")

    def slot_values(series: Series, k: int) -> list:
        """Slot k of the window holds the month (W-1-k) months before now."""
        back = W - 1 - k
        return [series.values[f - back] if f - back >= 0 else None for f in range(n)]

    # The line is built from W-1 two-vertex SEGMENTS, not one polyline: a Plot
    # drops a hidden vertex and joins its neighbours straight across, which
    # would draw a confident line over a gauge gap (1923-25 did exactly that).
    # A segment with a hidden end has one visible vertex and draws nothing.
    # Both ends of neighbouring segments read the same channel, so this costs
    # nodes, not tracks.
    slot_ch, slot_z, slot_hide = [], [], []
    for k in range(W):
        vals = slot_values(flows[MAST], k)
        z = [fm._r(w_flow_z(v) if v is not None else W_Z0 + 4) for v in vals]
        hide_t = [0 if v is not None else 1 for v in vals]
        slot_z.append(z[rest])
        slot_hide.append(hide_t[rest])
        # Every segment parent sits at z = W_Z0, so a vertex's bound
        # translate_z (relative to its parent) is its height in the strip.
        slot_ch.append(ch.channel(translate_z=[round(v - W_Z0, 3) for v in z],
                                  hide=hide_t))
    window_check = {}                 # slot -> (a vertex node id, expected strip z)
    for k in range(W - 1):
        par = R.add(type=NODE_GLYPH, parent_id=0, branch_level=0, geometry=GEO_POINT,
                    topo=TOPO_PLOT, ratio=0.08, color_r=FLOW_LINE[0],
                    color_g=FLOW_LINE[1], color_b=FLOW_LINE[2], color_a=0,
                    translate_x=fm._r(X_LINE), translate_y=fm._r(wy_(k)),
                    translate_z=fm._r(W_Z0),
                    text="Mast Rd monthly mean flow, the ten years up to now (log scale)")
        for j in (k, k + 1):
            vid = R.add(type=NODE_GLYPH, parent_id=par, branch_level=1, geometry=GEO_CUBE,
                        scale_x=0.0, scale_y=0.0, scale_z=0.0,
                        translate_y=fm._r(wy_(j) - wy_(k)),
                        translate_z=fm._r(slot_z[j] - W_Z0),
                        color_r=FLOW_LINE[0], color_g=FLOW_LINE[1], color_b=FLOW_LINE[2],
                        hide=slot_hide[j], ch_input_id=slot_ch[j])
            window_check.setdefault(j, (vid, j))
    checks["window"] = dict(slots=window_check, W=W, z0=W_Z0,
                            expect=lambda f, k: (None if slot_values(flows[MAST], k)[f] is None
                                                 else w_flow_z(slot_values(flows[MAST], k)[f])))

    bar_w = (2 * Y0 / (W - 1)) * 0.4
    for k in range(W):
        vals = slot_values(rains[CUYAMACA], k)
        half = [max((v or 0.0) * WINDOW_RAIN_PER_INCH / 2, 0.02) for v in vals]
        hide_t = [0 if v is not None else 1 for v in vals]
        tz = [fm._r(W_TOP - h, 3) for h in half]
        now = k == W - 1
        col = (235, 220, 255) if now else RAIN_LINE
        R.add(type=NODE_GLYPH, parent_id=0, branch_level=0, geometry=GEO_CUBE,
              translate_x=fm._r(X_BAR), translate_y=fm._r(wy_(k)), translate_z=tz[rest],
              scale_x=fm._r(0.2 / CUBE_HALF, 4), scale_y=fm._r(bar_w / CUBE_HALF, 4),
              scale_z=fm._r(half[rest] / CUBE_HALF, 4),
              hide=hide_t[rest], color_r=col[0], color_g=col[1], color_b=col[2],
              ch_input_id=ch.channel(scale_z=[round(h / CUBE_HALF, 4) for h in half],
                                     translate_z=tz, hide=hide_t),
              text=("Cuyamaca rainfall, this month" if now else
                    f"Cuyamaca rainfall, {W - 1 - k} months before now"))

    # The "now" bead on the window's right-hand end: this month's flow, in the
    # wetter/drier colour the ribbons use.
    se = flows[MAST]
    zb = [fm._r(w_flow_z(v) if v is not None else W_Z0 + 4) for v in se.values]
    cb = [ramp(p) if p is not None else (0, 0, 0) for p in se.pct]
    for f in range(1, n):
        if se.pct[f] is None:
            cb[f] = cb[f - 1]
    hb = [0 if v is not None else 1 for v in se.values]
    R.add(type=NODE_GLYPH, parent_id=0, branch_level=0, geometry=GEO_SPHERE,
          translate_x=fm._r(X_LINE - 1.0), translate_y=fm._r(wy_(W - 1)),
          translate_z=zb[rest], scale_x=1.5, scale_y=1.5, scale_z=1.5, hide=hb[rest],
          color_r=cb[rest][0], color_g=cb[rest][1], color_b=cb[rest][2],
          segments_x=16, segments_y=12,
          ch_input_id=ch.channel(translate_z=zb, hide=hb, color_r=[c[0] for c in cb],
                                 color_g=[c[1] for c in cb], color_b=[c[2] for c in cb]),
          text="Mast Rd flow this month · colour = wetter/drier than usual for the month")

    # Running readout at the window's "now" end. Channels animate show_text,
    # never the text itself, so it is a bank of pre-labelled nodes with one of
    # each showing per frame: one per year, one per calendar month.
    ry = wy_(W - 1)
    checks["readout"] = dict(months=months, year_ids={}, month_ids={})
    for y in sorted({m[:4] for m in months}):
        on = [1 if m[:4] == y else 0 for m in months]
        checks["readout"]["year_ids"][y] = len(R.rows) + 1
        R.add(type=NODE_GLYPH, parent_id=0, branch_level=0, geometry=GEO_CUBE,
              scale_x=0.0, scale_y=0.0, scale_z=0.0, translate_x=fm._r(px - 1.0),
              translate_y=fm._r(ry), translate_z=fm._r(W_TOP + 21),
              ch_input_id=ch.channel(show_text=on), show_text=on[rest], text=y)
    for mi in range(1, 13):
        on = [1 if int(m[5:]) == mi else 0 for m in months]
        checks["readout"]["month_ids"][mi] = len(R.rows) + 1
        R.add(type=NODE_GLYPH, parent_id=0, branch_level=0, geometry=GEO_CUBE,
              scale_x=0.0, scale_y=0.0, scale_z=0.0, translate_x=fm._r(px - 1.0),
              translate_y=fm._r(ry), translate_z=fm._r(W_TOP + 11),
              ch_input_id=ch.channel(show_text=on), show_text=on[rest],
              text=calendar.month_name[mi])

    # -- Legend, where the Phase 1 scene keeps its Strahler legend -------------
    # North of the plate, which the opening view shows on the left. Entries
    # stack DOWNWARD: a tag draws to the right of its glyph, so a row of them
    # side by side would overwrite each other.
    lx, ly = -layout.half_w * 0.55, layout.half_h + 24.0
    z = LEGEND_TOP

    def legend_text(text):
        R.add(type=NODE_GLYPH, parent_id=0, branch_level=0, geometry=GEO_CUBE,
              scale_x=0.0, scale_y=0.0, scale_z=0.0, translate_x=fm._r(lx),
              translate_y=fm._r(ly), translate_z=fm._r(z), show_text=1, text=text)

    legend_text("River ribbon width · monthly mean flow")
    for cfs in (1000, 100, 10, 1):
        z -= LEGEND_STEP
        # A real two-vertex Plot line at exactly the width the ribbons use.
        par = R.add(type=NODE_GLYPH, parent_id=0, branch_level=0, geometry=GEO_POINT,
                    topo=TOPO_PLOT, ratio=ribbon_ratio(cfs), color_r=228, color_g=226,
                    color_b=214, color_a=0, translate_x=fm._r(lx),
                    translate_y=fm._r(ly - 7), translate_z=fm._r(z), show_text=1,
                    text=f"{cfs:,} cfs")
        for dy in (14.0, 0.0):
            R.add(type=NODE_GLYPH, parent_id=par, branch_level=1, geometry=GEO_CUBE,
                  scale_x=0.0, scale_y=0.0, scale_z=0.0, translate_y=dy,
                  color_r=228, color_g=226, color_b=214)
    z -= LEGEND_STEP * 1.3
    legend_text("Colour · this month against the same month in other years")
    for p, text in ((1.0, "wettest"), (0.5, "typical"), (0.0, "driest")):
        z -= LEGEND_STEP
        c = ramp(p)
        R.add(type=NODE_GLYPH, parent_id=0, branch_level=0, geometry=GEO_CUBE,
              translate_x=fm._r(lx), translate_y=fm._r(ly), translate_z=fm._r(z),
              scale_x=3.0, scale_y=3.0, scale_z=3.0, color_r=c[0], color_g=c[1],
              color_b=c[2], show_text=1, text=text)
    z -= LEGEND_STEP * 1.3
    legend_text("Rain column height · rainfall in the month")
    half = 10 * RAIN_UNITS_PER_INCH / 2
    z -= LEGEND_STEP * 0.6 + half
    R.add(type=NODE_GLYPH, parent_id=0, branch_level=0, geometry=GEO_CYLINDER,
          translate_x=fm._r(lx), translate_y=fm._r(ly), translate_z=fm._r(z),
          scale_x=RAIN_RADIUS, scale_y=RAIN_RADIUS, scale_z=half,
          color_r=228, color_g=226, color_b=214, segments_x=16, segments_y=4,
          show_text=1, text="10 inches")
    z -= half
    notes.append(f"legend: {LEGEND_TOP:g} .. {z:g} world units")

    ch_map, ch_tracks = ch.frames()
    return Built(R.frame(), ch_map, ch_tracks, notes, checks)


# ---------------------------------------------------------------------------
# 5. VALIDATION + VERIFICATION
# ---------------------------------------------------------------------------

def validate_channels(df, ch_map, ch_tracks) -> list[str]:
    from glyphviz_core.channel_engine import _ATTR_TO_FIELD
    problems = []
    channels = set(ch_map["channel_id"])
    used = set(df.loc[df.ch_input_id != 0, "ch_input_id"])
    if used - channels:
        problems.append(f"ch_input_id with no map row: {sorted(used - channels)[:10]}")
    if channels - used:
        problems.append(f"map channel with no node: {sorted(channels - used)[:10]}")
    cols = {int(c[2:]) for c in ch_tracks.columns if c.startswith("ch") and c[2:].isdigit()}
    if set(ch_map["track_id"]) - cols:
        problems.append("map track_id with no ch<id> column")
    bad = set(ch_map["attribute"]) - set(_ATTR_TO_FIELD)
    if bad:
        problems.append(f"unbindable attributes: {sorted(bad)}")
    if ch_tracks.isna().any().any():
        problems.append("NaN in the tracks")
    return problems


def verify_playback(node_path: Path, map_path: Path, tracks_path: Path,
                    built: Built, frame: fm.Frame) -> list[str]:
    """Load all three files through the real loaders and ChannelEngine, apply
    sampled frames, and check what the scene then holds against the source
    series computed independently here."""
    from glyphviz_core.channel_engine import ChannelEngine
    from glyphviz_core.channel_loader import load_ch_map, load_ch_tracks
    from glyphviz_core.csv_reader import load_node_csv
    from glyphviz_core.scene import Scene

    nodes = load_node_csv(str(node_path))
    engine = ChannelEngine()
    tracks, id_to_col = load_ch_tracks(str(tracks_path))
    engine.load(load_ch_map(str(map_path)), tracks, id_to_col, nodes)
    by_id = {nd.id: nd for nd in nodes}
    report = [f"engine: {engine.frame_count} frames, "
              f"{len(engine.bound_node_ids)} bound nodes"]

    layout, lattice = frame.layout, frame.lattice
    worst_h = worst_xy = 0.0
    below = 0
    for f in (0, engine.frame_count // 3, engine.frame_count - 1):
        engine.apply_frame(f)
        scene = Scene(nodes)
        for nid, lon, lat, half, tz in built.checks["columns"]:
            nd = by_id[nid]
            if nd.hide:
                continue
            wp = scene.world_pos(nid)
            ex, ey = layout.world_xy(lon, lat)
            worst_xy = max(worst_xy, abs(wp[0] - ex), abs(wp[1] - ey))
            base_z = wp[2] - nd.scale_z
            ground = lattice.surface_height(lon, lat) * layout.z_per_m
            worst_h = max(worst_h, abs(nd.scale_z - half[f]))
            if base_z < ground + 1.0:
                below += 1
    report.append(f"rain columns at 3 frames: xy offset {worst_xy:.6f}, "
                  f"height error {worst_h:.6f}, bases below station top: {below}")

    # The scrolling window, the cursor and the readout, at frames spread over
    # the whole clock (including 1924, inside the Mast Rd gap).
    win, cur, ro = built.checks["window"], built.checks["cursor"], built.checks["readout"]
    cursor_id = next(nd.id for nd in nodes if nd.text == "now, on the century"
                     and nd.parent_id == 0)
    worst_win = worst_cur = 0.0
    wrong_hide = wrong_readout = 0
    sample = sorted({0, 130, 144, 500, 968, engine.frame_count - 1})
    for f in sample:
        engine.apply_frame(f)
        scene = Scene(nodes)
        for k, (vid, _j) in win["slots"].items():
            want = win["expect"](f, k)
            nd = by_id[vid]
            if (want is None) != bool(nd.hide):
                wrong_hide += 1
            if want is not None:
                worst_win = max(worst_win, abs(scene.world_pos(vid)[2] - want))
        worst_cur = max(worst_cur, abs(scene.world_pos(cursor_id)[1] - cur["y"][f]))
        m = ro["months"][f]
        shown_y = [y for y, i in ro["year_ids"].items() if by_id[i].show_text]
        shown_m = [mi for mi, i in ro["month_ids"].items() if by_id[i].show_text]
        if shown_y != [m[:4]] or shown_m != [int(m[5:])]:
            wrong_readout += 1
    report.append(f"window at {len(sample)} frames x {len(win['slots'])} slots: height error "
                  f"{worst_win:.4f}, wrong gap state {wrong_hide}; cursor error "
                  f"{worst_cur:.4f}; frames with a wrong month/year readout {wrong_readout}")
    engine.reset()
    return report


# ---------------------------------------------------------------------------
# 6. MAIN
# ---------------------------------------------------------------------------

def write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, encoding="utf-8", lineterminator="\r\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", type=Path, default=HERE)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--cols", type=int, default=fm.SURFACE_COLS)
    args = ap.parse_args()

    out_dir = args.out_dir
    frame = fm.prepare_frame(out_dir, args.refresh, True, args.cols)
    built = build(frame, args.refresh)

    problems = fm.validate(built.df) + validate_channels(built.df, built.ch_map,
                                                         built.ch_tracks)
    if problems:
        print("\nVALIDATION FAILED:")
        for p in problems:
            print("  -", p)
        return 1

    from glyphviz_core.csv_reader import load_node_csv, save_node_csv
    node_path = out_dir / f"{OUT_STEM}_gv_node.csv"
    map_path = out_dir / f"{OUT_STEM}_gv_ch-map.csv"
    tracks_path = out_dir / f"{OUT_STEM}_gv_ch-tracks.csv"
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "raw_gv_node.csv"
        built.df.to_csv(raw, index=False)
        save_node_csv(load_node_csv(str(raw)), str(node_path))
    write_csv(built.ch_map, map_path)
    write_csv(built.ch_tracks, tracks_path)

    print(f"\nWrote {node_path.name}: {len(built.df):,} nodes, "
          f"{node_path.stat().st_size / 1e6:.2f} MB")
    print(f"      {map_path.name}: {len(built.ch_map)} bindings")
    print(f"      {tracks_path.name}: {len(built.ch_tracks)} frames x "
          f"{len(built.ch_tracks.columns) - 1} tracks, "
          f"{tracks_path.stat().st_size / 1e6:.2f} MB")
    for n_ in built.notes:
        print(f"  note: {n_}")
    print("\nVerification (real loader + Scene):")
    for line in fm.verify_scene(node_path, frame.layout, frame.lattice, built.checks):
        print(f"  {line}")
    for line in verify_playback(node_path, map_path, tracks_path, built, frame):
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
