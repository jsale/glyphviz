#!/usr/bin/env python3
"""
build_storm_scene.py — the storm winter of 2004-05, one frame per day
====================================================================

A scene of the San Diego River Watershed Atlas: the wet season of 2004-05,
1 October 2004 to 30 April 2005, at DAILY resolution. At Lakeside 2 E it was
the second-wettest of 64 complete water years (29.3 in; 1978 had 29.5), and
Mast Rd's 11th-highest mean flow of 110. It was also the second winter after
the Cedar Fire (October 2003) burned across the upper watershed; the first
winter was dry (9.7 in at Lakeside), so this was the burn scar's first real
test.

The Phase 1 frame (terrain, divide, rivers, gauges, places) is rebuilt
unchanged underneath, and three layers are laid over it:

  * FLOW RIBBONS over the reach each USGS gauge measures, exactly as in The
    Pulse but daily: width is the day's mean flow (log), colour is the day's
    rank among every recorded day in the same calendar month of that gauge's
    whole record, so "wetter than usual" means the same thing it does there.
  * THE RAIN FIELD. A column over every NOAA daily rain gauge in the map
    window that reported on most days (18 stations), height the day's rain and
    colour its amount. Flags are drawn, not smoothed: a missing day hides the
    column, and a total ACCUMULATED over several days (an observer who could
    not read the gauge every day) is drawn as a WIRE column on the day it was
    read, with the days it covers hidden.
  * THE PANEL beyond the east edge: the season's daily flow at all three
    gauges (log) and daily rain at Cuyamaca (mountains) and Lakeside (valley),
    with a cursor, the month and day read out, and the peak days marked.

Data: ../San_Diego_River_Watershed_Example/watershed_data.py (shared data/).
Layers shared with The Pulse: ../San_Diego_River_Pulse_Example/build_pulse_scene.py.

USAGE
-----
    python build_storm_scene.py              # build (uses cached data)
    python build_storm_scene.py --refresh    # re-download everything
"""

from __future__ import annotations

import argparse
import bisect
import calendar
import datetime as dt
import math
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "examples" / "San_Diego_River_Watershed_Example"))
sys.path.insert(0, str(REPO / "examples" / "San_Diego_River_Pulse_Example"))

import build_pulse_scene as pu                                      # noqa: E402
import build_watershed_scene as fm                                  # noqa: E402
import watershed_data as wd                                         # noqa: E402

# ---------------------------------------------------------------------------
# 1. CONFIGURATION
# ---------------------------------------------------------------------------

OUT_STEM = "sd_river_storm_2005"
SDATE, EDATE = "2004-10-01", "2005-04-30"
MIN_REPORTING_DAYS = 100                 # a rain gauge reporting less is left out

MAST, FASHION, LOS_COCHES = pu.MAST, pu.FASHION, pu.LOS_COCHES
CUYAMACA_COOP, LAKESIDE_COOP = "042239", "044710"
PHASE1_COOP = {"042239", "044412", "044710", "042406"}   # already have a marker

RAIN_UNITS_PER_INCH = 8.0                # a daily column: 8 world units per inch
# Colour by the day's AMOUNT (inches). A daily field has no century of
# history per station to rank against, and for a storm the amount is the point.
AMOUNT_RAMP = [(0.0, (196, 204, 212)), (0.25, (150, 195, 240)), (1.0, (70, 140, 255)),
               (2.0, (120, 84, 236)), (4.0, (200, 70, 205))]

PANEL_GAP, PANEL_Z0 = 26.0, 96.0
LEGEND_TOP = 250.0
SWATCH_GAP = 120.0                       # line/bar swatches sit this far north of the panel
FLOW_H, RAIN_H, STRIP_GAP = 80.0, 70.0, 30.0
FLOW_LOG = (-1.0, 3.5)                   # daily mean, 0.1 .. ~3,200 cfs
PANEL_RAIN_PER_INCH = 12.0               # panel bars: a 4-inch day spans ~48 units

GAUGE_LINE = {MAST: (150, 230, 255), FASHION: (80, 150, 255), LOS_COCHES: (140, 225, 150)}
STATION_BAR = {CUYAMACA_COOP: (200, 176, 255), LAKESIDE_COOP: (255, 214, 150)}
CURSOR_COLOR = pu.CURSOR_COLOR

GEO_CUBE_WIRE, GEO_CUBE, GEO_OCTA = 0, 1, 11
GEO_CYLINDER_WIRE, GEO_CYLINDER = 18, 19
GEO_SPHERE, GEO_POINT = 3, 22
TOPO_PLOT, NODE_GLYPH = 16, 5
CUBE_HALF = pu.CUBE_HALF


# ---------------------------------------------------------------------------
# 2. DATA ON THE SCENE CLOCK
# ---------------------------------------------------------------------------

def season_days() -> list[dt.date]:
    a, b = dt.date.fromisoformat(SDATE), dt.date.fromisoformat(EDATE)
    return [a + dt.timedelta(days=i) for i in range((b - a).days + 1)]


def daily_flow(site: str, days: list[dt.date], refresh: bool) -> tuple[list, list]:
    """-> (cfs per scene day or None, percentile per day or None). The
    percentile ranks the day among EVERY recorded day in the same calendar
    month of the gauge's whole record."""
    rec = wd.fetch_daily_flow(site, refresh)
    first = dt.date.fromisoformat(rec["first_day"])
    by_month: dict[int, list[float]] = {}
    for i, v in enumerate(rec["cfs"]):
        if v is not None:
            by_month.setdefault((first + dt.timedelta(days=i)).month, []).append(v)
    for vs in by_month.values():
        vs.sort()
    vals, pct = [], []
    for d in days:
        i = (d - first).days
        v = rec["cfs"][i] if 0 <= i < len(rec["cfs"]) else None
        vals.append(v)
        if v is None:
            pct.append(None)
        else:
            vs = by_month[d.month]
            lo, hi = bisect.bisect_left(vs, v), bisect.bisect_right(vs, v)
            pct.append((lo + 0.5 * (hi - lo)) / len(vs))
    return vals, pct


def coop_id(st: dict) -> str | None:
    return next((s.split()[0] for s in st["sids"] if s.endswith(" 2")), None)


def amount_color(inches: float) -> tuple[int, int, int]:
    for (a0, c0), (a1, c1) in zip(AMOUNT_RAMP, AMOUNT_RAMP[1:]):
        if inches <= a1:
            t = (inches - a0) / (a1 - a0)
            return tuple(int(round(p + (q - p) * t)) for p, q in zip(c0, c1))
    return AMOUNT_RAMP[-1][1]


def day_label(d: dt.date) -> str:
    return f"{d.day} {calendar.month_name[d.month]} {d.year}"


# ---------------------------------------------------------------------------
# 3. SCENE
# ---------------------------------------------------------------------------

@dataclass
class Built:
    df: pd.DataFrame
    ch_map: pd.DataFrame
    ch_tracks: pd.DataFrame
    notes: list[str]
    checks: dict


def build(frame: fm.Frame, refresh: bool) -> Built:
    layout, lattice, b = frame.layout, frame.lattice, frame.window
    base = fm.build(layout, lattice, frame.dem, frame.map_path, home=None)
    notes = list(base.notes)
    checks = base.checks
    checks["columns"] = []
    R, grid_id = pu.rows_without_legend(
        base, "San Diego River Watershed Atlas · The Storm Winter, 2004-05")
    outer, _inner, _area = wd.dissolve(wd.fetch_huc10())

    days = season_days()
    n = len(days)
    flows = {s: daily_flow(s, days, refresh) for s in (MAST, FASHION, LOS_COCHES)}
    notes.append(f"clock: {n} daily frames, {days[0]} .. {days[-1]}")
    for s, (vals, _p) in flows.items():
        notes.append(f"flow {s}: {sum(v is not None for v in vals)} of {n} days, "
                     f"peak {max(v for v in vals if v is not None):,.0f} cfs")
    ch = pu.Channels(n)

    # -- Which rain gauges ----------------------------------------------------------
    bbox = (round(b.lon_min, 2), round(b.lat_min, 2), round(b.lon_max, 2), round(b.lat_max, 2))
    field_ = wd.fetch_daily_rain_field(bbox, SDATE, EDATE, refresh)
    stations = []
    for st in field_:
        reporting = sum(1 for v, fl in st["days"] if fl != "M")
        inside_map = b.lon_min <= st["lon"] <= b.lon_max and b.lat_min <= st["lat"] <= b.lat_max
        if not inside_map:
            continue
        if reporting < MIN_REPORTING_DAYS or len(st["days"]) != n:
            notes.append(f"rain gauge left out: {st['name']} reported {reporting} of {n} days")
            continue
        stations.append(st)
    notes.append(f"rain field: {len(stations)} gauges, "
                 f"{sum(wd.point_in_rings(s['lon'], s['lat'], outer) for s in stations)} "
                 f"inside the divide")

    # The resting pose (what the CSV holds and every screenshot shows) is the
    # day that is both wet across the field and high at Mast Rd: the field's
    # mean rain plus Mast Rd's flow, each as a fraction of its season maximum.
    # The flow peak alone (11 Jan) comes after the rain, with the columns
    # already short; the rain peak alone (27 Oct) has a smaller river.
    def field_mean(f):
        vs = [st["days"][f][0] for st in stations if st["days"][f][1] in ("", "T")]
        return sum(vs) / len(vs) if vs else 0.0
    means = [field_mean(f) for f in range(n)]
    mast = [v or 0.0 for v in flows[MAST][0]]
    rest = max(range(n), key=lambda f: means[f] / max(means) + mast[f] / max(mast))
    notes.append(f"resting pose: frame {rest}, {days[rest]} (field mean "
                 f"{means[rest]:.2f} in, Mast Rd {mast[rest]:,.0f} cfs)")

    # -- Flow ribbons -------------------------------------------------------------
    for site, coords, what in pu.gauge_reaches(notes):
        vals, pct = flows[site]
        pu.add_flow_ribbon(
            R, ch, frame, checks, coords, vals, pu.pct_colors(pct), rest,
            text=(f"Flow ribbon · USGS {site} {pu.GAUGE_NAMES[site]} · {what} · "
                  f"width = daily mean flow (log), colour = this day against every "
                  f"recorded day of the same month since the gauge began"),
            link=f"https://waterdata.usgs.gov/monitoring-location/{site}/")

    # -- The rain field -----------------------------------------------------------

    by_coop = {}
    for st in stations:
        coop = coop_id(st)
        by_coop[coop] = st
        inside = wd.point_in_rings(st["lon"], st["lat"], outer)
        where = "inside the divide" if inside else "outside the divide"
        vals = [v if fl not in ("M", "S") else None for v, fl in st["days"]]
        geo = [GEO_CYLINDER_WIRE if fl == "A" else GEO_CYLINDER for _v, fl in st["days"]]
        cols = [amount_color(v or 0.0) for v in vals]
        accumulated = sum(1 for _v, fl in st["days"] if fl == "A")
        total = sum(v for v in vals if v is not None)
        nid = pu.add_rain_column(
            R, ch, frame, checks, grid_id, st["lon"], st["lat"], vals, cols, rest,
            text=(f"Daily rainfall · NOAA {st['name']} ({st['elev_ft']:,.0f} ft, {where}) · "
                  f"{total:.1f} in over the season"
                  + (f" · wire = a total accumulated over several days "
                     f"({accumulated} such readings)" if accumulated else "")),
            units_per_inch=RAIN_UNITS_PER_INCH, geometry_t=geo)
        checks["columns"][-1] = checks["columns"][-1] + (
            [v is None for v in vals], geo)
        if coop not in PHASE1_COOP:
            ground_km = lattice.surface_height(st["lon"], st["lat"]) / 1000.0
            R.add(type=NODE_GLYPH, parent_id=grid_id, branch_level=1, geometry=GEO_OCTA,
                  translate_x=fm._r(st["lon"], 6), translate_y=fm._r(st["lat"], 6),
                  translate_z=fm._r(ground_km, 6), scale_x=1.2, scale_y=1.2, scale_z=1.2,
                  color_r=190, color_g=170, color_b=250,
                  text=f"NOAA rain gauge · {st['name']} · {st['elev_ft']:,.0f} ft · {where}")

    # -- The panel ------------------------------------------------------------------
    px = layout.half_w + PANEL_GAP
    Y0 = layout.half_h
    X_LINE, X_BAR, X_BACK = px - 0.6, px - 0.2, px + 0.6
    F_Z0, F_TOP = PANEL_Z0, PANEL_Z0 + FLOW_H
    R_Z0 = F_TOP + STRIP_GAP
    R_TOP = R_Z0 + RAIN_H

    def py(f: float) -> float:
        return Y0 - 2 * Y0 * f / (n - 1)

    def flow_z(cfs: float) -> float:
        t = (math.log10(max(cfs, 10 ** FLOW_LOG[0])) - FLOW_LOG[0]) / (FLOW_LOG[1] - FLOW_LOG[0])
        return F_Z0 + 3 + (FLOW_H - 6) * min(max(t, 0.0), 1.0)

    def add(**kw) -> int:
        return R.add(type=NODE_GLYPH, parent_id=0, branch_level=0, **kw)

    def label(y, z, text):
        return add(geometry=GEO_CUBE, scale_x=0.0, scale_y=0.0, scale_z=0.0,
                   translate_x=fm._r(px - 1.0), translate_y=fm._r(y), translate_z=fm._r(z),
                   show_text=1, text=text)

    def polyline(pts, width, color, text, show=0, anchor=0):
        ay, az = pts[anchor]
        par = add(geometry=GEO_POINT, topo=TOPO_PLOT, ratio=width, color_r=color[0],
                  color_g=color[1], color_b=color[2], color_a=0,
                  translate_x=fm._r(X_LINE), translate_y=fm._r(ay), translate_z=fm._r(az),
                  show_text=show, text=text)
        for y, z in pts:
            R.add(type=NODE_GLYPH, parent_id=par, branch_level=1, geometry=GEO_CUBE,
                  scale_x=0.0, scale_y=0.0, scale_z=0.0, translate_y=fm._r(y - ay),
                  translate_z=fm._r(z - az), color_r=color[0], color_g=color[1],
                  color_b=color[2])
        return par

    def backing(z0, z1, text):
        add(geometry=GEO_CUBE, translate_x=fm._r(X_BACK), translate_y=0.0,
            translate_z=fm._r((z0 + z1) / 2), scale_x=fm._r(0.3 / CUBE_HALF, 4),
            scale_y=fm._r((Y0 + 5) / CUBE_HALF, 4),
            scale_z=fm._r(((z1 - z0) / 2 + 2) / CUBE_HALF, 4),
            color_r=22, color_g=28, color_b=32, text=text)

    # Flow strip.
    backing(F_Z0 - 1, F_TOP + 1, "Daily mean flow at the three gauges, log scale")
    label(py(0), F_TOP + 8, "Daily river flow (log scale)")
    for e in range(int(FLOW_LOG[0]), int(math.floor(FLOW_LOG[1])) + 1):
        polyline([(py(0) + 2, flow_z(10 ** e)), (py(n - 1) - 2, flow_z(10 ** e))], 0.03,
                 (70, 84, 90), f"{10 ** e:,g} cfs", show=1 if e % 2 == 0 else 0, anchor=1)
    for site in (LOS_COCHES, MAST, FASHION):
        vals, _p = flows[site]
        run = [(f, v) for f, v in enumerate(vals) if v is not None]
        polyline([(py(f), flow_z(v)) for f, v in run], 0.08, GAUGE_LINE[site],
                 f"Daily mean flow · USGS {site} {pu.GAUGE_NAMES[site]}")
    # Which line is which: swatches stacked beside the strip's north end.
    for k, site in enumerate((FASHION, MAST, LOS_COCHES)):
        c = GAUGE_LINE[site]
        add(geometry=GEO_CUBE, translate_x=fm._r(X_LINE), translate_y=fm._r(py(0) + SWATCH_GAP),
            translate_z=fm._r(F_TOP - 12 - 14 * k), scale_x=1.6, scale_y=1.6, scale_z=1.6,
            color_r=c[0], color_g=c[1], color_b=c[2], show_text=1,
            text=pu.GAUGE_NAMES[site].split(",")[0])

    # Rain strip: two stations' daily bars hanging from the top, side by side
    # within each day.
    backing(R_Z0 - 1, R_TOP + 1, "Daily rainfall at Cuyamaca and Lakeside 2 E")
    label(py(0), R_TOP + 8, "Daily rainfall (bars hang down)")
    polyline([(py(0) + 2, R_TOP - PANEL_RAIN_PER_INCH), (py(n - 1) - 2, R_TOP - PANEL_RAIN_PER_INCH)],
             0.03, (84, 76, 100), "1 inch in a day", show=1, anchor=1)
    day_w = 2 * Y0 / (n - 1)
    for k, coop in enumerate((CUYAMACA_COOP, LAKESIDE_COOP)):
        st = by_coop.get(coop)
        if st is None:
            continue
        c = STATION_BAR[coop]
        for f, (v, fl) in enumerate(st["days"]):
            if fl in ("M", "S") or not v:
                continue
            half = v * PANEL_RAIN_PER_INCH / 2
            add(geometry=GEO_CUBE_WIRE if fl == "A" else GEO_CUBE,
                translate_x=fm._r(X_BAR), translate_y=fm._r(py(f) + (k - 0.5) * day_w * 0.45),
                translate_z=fm._r(R_TOP - half), scale_x=fm._r(0.2 / CUBE_HALF, 4),
                scale_y=fm._r(day_w * 0.22 / CUBE_HALF, 4), scale_z=fm._r(half / CUBE_HALF, 4),
                color_r=c[0], color_g=c[1], color_b=c[2],
                text=f"{st['name']} · {day_label(days[f])} · {v:.2f} in"
                     + (" (accumulated over several days)" if fl == "A" else ""))
        add(geometry=GEO_CUBE, translate_x=fm._r(X_LINE), translate_y=fm._r(py(0) + SWATCH_GAP),
            translate_z=fm._r(R_TOP - 12 - 14 * k), scale_x=1.6, scale_y=1.6, scale_z=1.6,
            color_r=c[0], color_g=c[1], color_b=c[2], show_text=1,
            text=f"{st['name']} ({st['elev_ft']:,.0f} ft)")

    # Month ticks under the flow strip.
    for f, d in enumerate(days):
        if d.day == 1:
            add(geometry=GEO_CUBE, translate_x=fm._r(X_LINE), translate_y=fm._r(py(f)),
                translate_z=fm._r(F_Z0 - 3), scale_x=0.3, scale_y=0.3, scale_z=1.6,
                color_r=150, color_g=160, color_b=170, show_text=1,
                text=calendar.month_abbr[d.month])

    # The peak days, from the data; gauges that peak on the same day share one
    # marker and one label.
    peaks: dict[int, list[str]] = {}
    for site in (MAST, FASHION, LOS_COCHES):
        vals, _p = flows[site]
        f = max(range(n), key=lambda i: vals[i] or -1)
        peaks.setdefault(f, []).append(
            f"{pu.GAUGE_NAMES[site].split(',')[0].replace(' nr Lakeside', '')} "
            f"{vals[f]:,.0f} cfs")
    for row, (f, parts) in enumerate(sorted(peaks.items())):
        text = f"Season's highest daily flow · {day_label(days[f])} · {', '.join(parts)}"
        polyline([(py(f), F_Z0 + 0.5), (py(f), R_TOP - 0.5)], 0.03, (235, 200, 140), text)
        add(geometry=GEO_CUBE, translate_x=fm._r(X_LINE), translate_y=fm._r(py(f)),
            translate_z=fm._r(F_Z0 - 13 - 9 * row), scale_x=0.5, scale_y=0.5, scale_z=0.5,
            color_r=235, color_g=200, color_b=140, show_text=1, text=text)

    # Cursor spanning both strips.
    cur_scale, cur_z = 1.3, R_TOP + 3.0
    checks["cursor"] = [py(f) for f in range(n)]
    cursor = add(geometry=GEO_SPHERE, translate_x=fm._r(px - 1.5), translate_y=fm._r(py(rest)),
                 translate_z=fm._r(cur_z), scale_x=cur_scale, scale_y=cur_scale,
                 scale_z=cur_scale, color_r=CURSOR_COLOR[0], color_g=CURSOR_COLOR[1],
                 color_b=CURSOR_COLOR[2], segments_x=16, segments_y=12,
                 ch_input_id=ch.channel(translate_y=[fm._r(py(f)) for f in range(n)]),
                 text="today, on the season")
    R.add(type=NODE_GLYPH, parent_id=cursor, branch_level=1, geometry=GEO_CUBE,
          translate_z=fm._r(-(cur_z - (F_Z0 + R_TOP) / 2) / cur_scale, 4),
          scale_x=fm._r(0.2 / CUBE_HALF / cur_scale, 4),
          scale_y=fm._r(0.2 / CUBE_HALF / cur_scale, 4),
          scale_z=fm._r(((R_TOP - F_Z0) / 2) / CUBE_HALF / cur_scale, 4),
          color_r=CURSOR_COLOR[0], color_g=CURSOR_COLOR[1], color_b=CURSOR_COLOR[2],
          text="today, on the season")

    # Readout at the panel's top right: one month label (with its year) and
    # one day-of-month label showing per frame.
    ry = py(n - 1)
    checks["readout"] = dict(days=days, month_ids={}, day_ids={})
    for ym in sorted({(d.year, d.month) for d in days}):
        on = [1 if (d.year, d.month) == ym else 0 for d in days]
        checks["readout"]["month_ids"][ym] = add(
            geometry=GEO_CUBE, scale_x=0.0, scale_y=0.0, scale_z=0.0,
            translate_x=fm._r(px - 1.0), translate_y=fm._r(ry), translate_z=fm._r(R_TOP + 12),
            ch_input_id=ch.channel(show_text=on), show_text=on[rest],
            text=f"{calendar.month_name[ym[1]]} {ym[0]}")
    for dom in range(1, 32):
        on = [1 if d.day == dom else 0 for d in days]
        if not any(on):
            continue
        checks["readout"]["day_ids"][dom] = add(
            geometry=GEO_CUBE, scale_x=0.0, scale_y=0.0, scale_z=0.0,
            translate_x=fm._r(px - 1.0), translate_y=fm._r(ry), translate_z=fm._r(R_TOP + 22),
            ch_input_id=ch.channel(show_text=on), show_text=on[rest], text=str(dom))

    # -- Legend, north of the plate ---------------------------------------------------
    lx, ly = -layout.half_w * 0.75, layout.half_h + 60.0
    z = LEGEND_TOP
    step = 16.0

    def legend_text(text):
        add(geometry=GEO_CUBE, scale_x=0.0, scale_y=0.0, scale_z=0.0,
            translate_x=fm._r(lx), translate_y=fm._r(ly), translate_z=fm._r(z),
            show_text=1, text=text)

    legend_text("River ribbon width · daily mean flow")
    for cfs in (1000, 100, 10, 1):
        z -= step
        par = add(geometry=GEO_POINT, topo=TOPO_PLOT, ratio=pu.ribbon_ratio(cfs),
                  color_r=228, color_g=226, color_b=214, color_a=0,
                  translate_x=fm._r(lx), translate_y=fm._r(ly - 7), translate_z=fm._r(z),
                  show_text=1, text=f"{cfs:,} cfs")
        for dy in (14.0, 0.0):
            R.add(type=NODE_GLYPH, parent_id=par, branch_level=1, geometry=GEO_CUBE,
                  scale_x=0.0, scale_y=0.0, scale_z=0.0, translate_y=dy,
                  color_r=228, color_g=226, color_b=214)
    z -= step * 1.3
    legend_text("Ribbon colour · this day against the same month in other years")
    for p, text in ((1.0, "wettest"), (0.5, "typical"), (0.0, "driest")):
        z -= step
        c = pu.ramp(p)
        add(geometry=GEO_CUBE, translate_x=fm._r(lx), translate_y=fm._r(ly),
            translate_z=fm._r(z), scale_x=3.0, scale_y=3.0, scale_z=3.0,
            color_r=c[0], color_g=c[1], color_b=c[2], show_text=1, text=text)
    z -= step * 1.3
    legend_text("Rain column · the day's rain")
    for inches in (4.0, 2.0, 1.0, 0.25):
        z -= step
        c = amount_color(inches)
        add(geometry=GEO_CUBE, translate_x=fm._r(lx), translate_y=fm._r(ly),
            translate_z=fm._r(z), scale_x=3.0, scale_y=3.0, scale_z=3.0,
            color_r=c[0], color_g=c[1], color_b=c[2], show_text=1,
            text=f"{inches:g} in ({inches * RAIN_UNITS_PER_INCH:g} units tall)")
    z -= step
    add(geometry=GEO_CYLINDER_WIRE, translate_x=fm._r(lx), translate_y=fm._r(ly),
        translate_z=fm._r(z), scale_x=pu.RAIN_RADIUS, scale_y=pu.RAIN_RADIUS, scale_z=3.0,
        color_r=200, color_g=200, color_b=210, show_text=1,
        text="wire = several days' rain read at once")
    notes.append(f"legend: {LEGEND_TOP:g} .. {z:g}")

    ch_map, ch_tracks = ch.frames()
    return Built(R.frame(), ch_map, ch_tracks, notes, checks)


# ---------------------------------------------------------------------------
# 4. VERIFICATION
# ---------------------------------------------------------------------------

def verify_playback(node_path: Path, map_path: Path, tracks_path: Path,
                    built: Built, frame: fm.Frame) -> list[str]:
    """Apply frames through the real loaders + ChannelEngine and compare the
    rain columns, the cursor and the readout with the source data."""
    from glyphviz_core.channel_engine import ChannelEngine
    from glyphviz_core.channel_loader import load_ch_map, load_ch_tracks
    from glyphviz_core.csv_reader import load_node_csv
    from glyphviz_core.scene import Scene

    nodes = load_node_csv(str(node_path))
    eng = ChannelEngine()
    tracks, id_to_col = load_ch_tracks(str(tracks_path))
    eng.load(load_ch_map(str(map_path)), tracks, id_to_col, nodes)
    by_id = {nd.id: nd for nd in nodes}
    layout, lattice = frame.layout, frame.lattice
    cursor_id = next(nd.id for nd in nodes if nd.text == "today, on the season"
                     and nd.parent_id == 0)
    ro = built.checks["readout"]
    worst_xy = worst_h = worst_cur = 0.0
    wrong_hide = wrong_geo = wrong_readout = below = 0
    sample = sorted({0, 40, 101, 102, 150, eng.frame_count - 1})
    for f in sample:
        eng.apply_frame(f)
        scene = Scene(nodes)
        for nid, lon, lat, half, _tz, hidden, geo in built.checks["columns"]:
            nd = by_id[nid]
            if bool(nd.hide) != hidden[f]:
                wrong_hide += 1
            if nd.geometry != geo[f]:
                wrong_geo += 1
            if nd.hide:
                continue
            wp = scene.world_pos(nid)
            ex, ey = layout.world_xy(lon, lat)
            worst_xy = max(worst_xy, abs(wp[0] - ex), abs(wp[1] - ey))
            worst_h = max(worst_h, abs(nd.scale_z - half[f]))
            if wp[2] - nd.scale_z < lattice.surface_height(lon, lat) * layout.z_per_m + 1.0:
                below += 1
        worst_cur = max(worst_cur, abs(scene.world_pos(cursor_id)[1] - built.checks["cursor"][f]))
        d = ro["days"][f]
        shown_m = [k for k, i in ro["month_ids"].items() if by_id[i].show_text]
        shown_d = [k for k, i in ro["day_ids"].items() if by_id[i].show_text]
        if shown_m != [(d.year, d.month)] or shown_d != [d.day]:
            wrong_readout += 1
    eng.reset()
    return [f"engine: {eng.frame_count} frames, {len(eng.bound_node_ids)} bound nodes",
            f"rain columns at {len(sample)} frames: xy offset {worst_xy:.6f}, height error "
            f"{worst_h:.6f}, wrong hide {wrong_hide}, wrong solid/wire {wrong_geo}, bases "
            f"below station top {below}; cursor error {worst_cur:.4f}; wrong readout "
            f"{wrong_readout}"]


# ---------------------------------------------------------------------------
# 5. MAIN
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", type=Path, default=HERE)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    frame = fm.prepare_frame(args.out_dir, args.refresh, True)
    built = build(frame, args.refresh)
    problems = fm.validate(built.df) + pu.validate_channels(built.df, built.ch_map,
                                                            built.ch_tracks)
    if problems:
        print("\nVALIDATION FAILED:")
        for p in problems:
            print("  -", p)
        return 1

    from glyphviz_core.csv_reader import load_node_csv, save_node_csv
    node_path = args.out_dir / f"{OUT_STEM}_gv_node.csv"
    map_path = args.out_dir / f"{OUT_STEM}_gv_ch-map.csv"
    tracks_path = args.out_dir / f"{OUT_STEM}_gv_ch-tracks.csv"
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "raw_gv_node.csv"
        built.df.to_csv(raw, index=False)
        save_node_csv(load_node_csv(str(raw)), str(node_path))
    pu.write_csv(built.ch_map, map_path)
    pu.write_csv(built.ch_tracks, tracks_path)

    print(f"\nWrote {node_path.name}: {len(built.df):,} nodes, "
          f"{node_path.stat().st_size / 1e6:.2f} MB")
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
