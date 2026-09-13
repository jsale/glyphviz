#!/usr/bin/env python3
"""
build_fire_siege_scene.py — the May 2014 fire siege as a space-time cube
=======================================================================

Phase 3 of the San Diego River Watershed Atlas, and the first of its fire
scenes. Between 13 and 16 May 2014, during a Santa Ana, eight fires with
mapped perimeters broke out across northern San Diego County. This scene puts
twelve days of that week, 11-23 May 2014, into a SPACE-TIME CUBE:

    the county map is the floor, and TIME RISES: one world unit per hour.

  * STATION THREADS. Every SDG&E weather station is a vertical thread from
    the floor (Sunday 11 May, midnight) to the top (Friday 23 May, midnight),
    coloured hour by hour by relative humidity. When a Santa Ana arrives the
    whole county turns red at the same height.
  * FIRE-ALERT DISCS. Jeff Sale's own 2014 HPWREN/SDG&E fire-alert index,
    ported unchanged: a station is in alert when its sustained wind is over
    25 mph, blowing FROM between 10 and 110 degrees (offshore), with relative
    humidity under 25%. Severity = (wind - 25) + (25 - RH). Each ten-minute
    alert is a disc on that station's thread, its radius the severity, so a
    run of alerts stacks into a spindle.
  * FIRES. Each fire is a prism: its mapped perimeter drawn at the height of
    its ignition and again at the height it was declared out, joined by
    vertical edges, with its footprint also traced on the floor.
  * THE NOW PLANE. A frame sweeps up through the cube as the clock plays, with
    every station's wind riding on it as a cone (pointing downwind, sized by
    speed, coloured by humidity) and a flame over each fire while it burns.

DATA
----
  Weather   Jeff Sale's archive of the SDG&E weather-station network, scraped
            every ten minutes (May 2014 folder, 128 stations). Only DERIVED
            values for this window are written into data/, never the raw
            archive; a rebuild works from that cache without the archive.
            TIME: archive stamps are Pacific STANDARD time all year (checked
            at the 9 Mar 2014 DST change: the file names skip 02:00, the stamps
            do not), so they are shifted +1 h to PDT, the clock used here.
  Fires     CAL FIRE FRAP perimeters (final shapes; day-precision dates) and
            CAL FIRE's incident list (start and extinguished times to the
            minute, UTC -> PDT). Matched by name, except FRAP's COMBAT, which
            is the incident CAL FIRE calls San Mateo (matched by its location
            falling inside the perimeter; both are 1,457 acres).

USAGE
-----
    python build_fire_siege_scene.py                  # uses data/ caches
    python build_fire_siege_scene.py --refresh        # re-read the archive, re-fetch fires
    python build_fire_siege_scene.py --archive PATH   # archive root (hpwren_sdge)
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
sys.path.insert(0, str(REPO / "examples" / "Santa_Ana_Wind_Example"))

import build_pulse_scene as pu                                      # noqa: E402
import build_santa_ana_scene as sa                                  # noqa: E402
import build_watershed_scene as fm                                  # noqa: E402
import watershed_data as wd                                         # noqa: E402
from glyphviz_core import basemap as bm                             # noqa: E402
from glyphviz_core import terrain as tr                             # noqa: E402

# ---------------------------------------------------------------------------
# 1. CONFIGURATION
# ---------------------------------------------------------------------------

OUT_STEM = "sd_fire_siege_2014"
DEFAULT_ARCHIVE = sa.DEFAULT_ARCHIVE
MONTH_DIR = "may2014"
T0 = dt.datetime(2014, 5, 11)                 # PDT, the floor of the cube
DAYS = 12
STEP = dt.timedelta(minutes=10)
N = DAYS * 24 * 6                             # 1,728 ten-minute frames
STAMP_TO_PDT = dt.timedelta(hours=1)          # archive stamps are PST
UTC_TO_PDT = dt.timedelta(hours=-7)

UNITS_PER_HOUR = 0.8                          # the cube is 230 units tall
PLATE_HEIGHT = 260.0

# Jeff Sale's 2014 fire-alert index (calculate_2014_fire_alert_levels_*.php).
ALERT_WIND_MPH = 25.0
ALERT_RH = 25.0
ALERT_DIR = (10.0, 110.0)                     # degrees wind comes FROM, exclusive

DISC_R0, DISC_R_PER_SEVERITY = 0.5, 0.08
SEVERITY_RAMP = [(0.0, (255, 222, 110)), (15.0, (250, 150, 50)), (30.0, (220, 50, 40))]
THREAD_WIDTH = 0.13                           # ratio; x 20 = pixels
FIRE_COLOR, FIRE_OUT_COLOR, FIRE_FLOOR_COLOR = (255, 120, 40), (150, 90, 70), (200, 70, 40)
PLANE_COLOR = (255, 236, 150)
FIRE_EDGES = 6
PERIMETER_SIMPLIFY_M = 40.0

MAP_GREY_MIX, MAP_BRIGHTNESS = 0.80, 0.34     # the grid draws unlit: a dark floor
BG_COLOR = (14, 17, 22)

GEO_CUBE, GEO_SPHERE, GEO_CONE, GEO_OCTA, GEO_CYLINDER = 1, 3, 5, 11, 19
GEO_GRID, GEO_POINT = 21, 22
TOPO_PLOT, NODE_WORLD, NODE_GLYPH, NODE_GRID = 16, 0, 5, 6


def z_of(k: float) -> float:
    """Height of ten-minute frame k (fractional allowed)."""
    return k / 6.0 * UNITS_PER_HOUR


def frame_of(t_pdt: dt.datetime) -> float:
    return (t_pdt - T0) / STEP


def when(k: int) -> dt.datetime:
    return T0 + k * STEP


def fmt_day(t: dt.datetime) -> str:
    return f"{t:%a} {t.day} {t:%b}"


def fmt_when(t: dt.datetime) -> str:
    return f"{fmt_day(t)} {t:%H:%M} PDT"


# ---------------------------------------------------------------------------
# 2. DATA
# ---------------------------------------------------------------------------

def load_mesonet(archive: Path, refresh: bool) -> dict:
    """Derived ten-minute station series for the window, cached in data/.

    -> {"t0", "step_min", "n", "filled", "stations": {abbrev: {name, lat, lon,
    elev_ft, ws, wd, gust, temp_f, rh}}} with one entry per frame, None where
    the station did not report. Nothing is filled here: alerts and humidity
    threads use observations only. (The wind cones bridge a single missed
    scrape for display, so they do not flicker; see build().)
    """
    cache = DATA / f"mesonet_{T0:%Y-%m-%d}_{DAYS}d.json"
    if cache.is_file() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8"))
    month = archive / "station_data" / MONTH_DIR
    if not month.is_dir():
        raise SystemExit(f"No cached {cache.name} and no archive at {month}")
    gaz = sa.read_gazetteer(archive / "sdge_met_locations.csv")
    stations: dict[str, dict] = {}
    off_grid = 0
    for path in sorted(month.glob("sdge_data_*.txt")):
        for line in path.read_text(errors="replace").splitlines():
            f = line.split(",")
            if len(f) != 17:
                continue
            try:
                t = dt.datetime.strptime(f[1], "%Y%m%d.%H%M%S") + STAMP_TO_PDT
                ws, wd_, gust, _dmg, temp, _dp, rh = (float(x) for x in f[2:9])
                lat, lon = float(f[14]), float(f[15])
            except ValueError:
                continue
            k = frame_of(t)
            if k != int(k):
                off_grid += 1
                continue
            k = int(k)
            if not 0 <= k < N:
                continue
            s = stations.get(f[0])
            if s is None:
                g = gaz.get(f[0]) or gaz.get(sa.ABBREV_ALIASES.get(f[0], ""))
                s = stations[f[0]] = dict(name=f[16].strip(), lat=lat, lon=lon,
                                          elev_ft=g["elev_ft"] if g else None,
                                          **{c: [None] * N for c in ("ws", "wd", "gust", "temp_f", "rh")})
            for c, v in zip(("ws", "wd", "gust", "temp_f", "rh"), (ws, wd_, gust, temp, rh)):
                s[c][k] = int(v) if v == int(v) else v
    single_gaps = sum(1 for s in stations.values() for k in range(1, N - 1)
                      if s["ws"][k] is None and s["ws"][k - 1] is not None
                      and s["ws"][k + 1] is not None)
    out = dict(t0=T0.isoformat(), clock="PDT", step_min=10, n=N, single_gaps=single_gaps,
               off_grid_rows=off_grid,
               source="SDG&E weather network, ten-minute scrapes archived by Jeff Sale "
                      "(may2014); stamps are PST, shifted +1 h",
               stations=dict(sorted(stations.items())))
    DATA.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    return out


def is_alert(ws, wd_, rh) -> bool:
    """Jeff's condition, exactly as his PHP wrote it."""
    return (ws is not None and wd_ is not None and rh is not None
            and ws > ALERT_WIND_MPH and 0 <= rh < ALERT_RH and ALERT_DIR[0] < wd_ < ALERT_DIR[1])


def severity(ws, rh) -> float:
    return (ws - ALERT_WIND_MPH) + (ALERT_RH - rh)


@dataclass
class Fire:
    name: str
    frap_name: str
    start: dt.datetime            # PDT
    out: dt.datetime              # PDT
    acres_mapped: float
    acres_reported: float
    cause: int | None
    rings: list[list]             # outer ring of every part, lon/lat
    matched_by: str


def load_fires(refresh: bool, notes: list[str]) -> list[Fire]:
    geo = wd.fetch_fire_perimeters(2014, refresh)
    incidents = [i for i in wd.fetch_calfire_incidents(2014, refresh)
                 if "San Diego" in str(i.get("County"))]
    t_end = T0 + DAYS * dt.timedelta(days=1)
    fires = []

    def pdt(s: str) -> dt.datetime:
        return dt.datetime.fromisoformat(s.replace("Z", "")) + UTC_TO_PDT

    for feat in geo["features"]:
        p, g = feat["properties"], feat["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        rings = [poly[0] for poly in polys]
        match, how = None, ""
        for i in incidents:
            if i["Name"].strip().lower().removesuffix(" fire") == p["FIRE_NAME"].lower():
                match, how = i, "name"
        if match is None:
            for i in incidents:
                if i.get("Longitude") and wd.point_in_rings(i["Longitude"], i["Latitude"], rings):
                    match, how = i, "location"
        if match is None or not match.get("Started"):
            continue
        start = pdt(match["Started"])
        if not T0 <= start < t_end:
            continue
        out = pdt(match["ExtinguishedDate"])
        name = match["Name"].strip().removesuffix(" Fire").removesuffix(" fire")
        fires.append(Fire(name, p["FIRE_NAME"], start, out, float(p["GIS_ACRES"]),
                          float(match.get("AcresBurned") or 0), p.get("CAUSE"), rings, how))
        if how != "name":
            notes.append(f"fire: FRAP {p['FIRE_NAME']} = CAL FIRE {match['Name'].strip()} "
                         f"(matched by {how})")
    matched = {f.name.lower() for f in fires}
    for i in incidents:
        s = i.get("Started", "")
        if s and T0 <= pdt(s) < t_end and i["Name"].strip().lower().removesuffix(" fire") not in matched:
            notes.append(f"fire without a mapped perimeter, left out: {i['Name'].strip()} "
                         f"({i.get('AcresBurned')} ac)")
    fires.sort(key=lambda f: f.start)
    return fires


# ---------------------------------------------------------------------------
# 3. CHANNELS WITH SHARED TRACKS
# ---------------------------------------------------------------------------

@dataclass
class Tracks:
    """Channel ids and tracks where several channels may READ ONE TRACK — the
    now-plane height is one track that every riding glyph shares."""
    map_rows: list[dict] = field(default_factory=list)
    tracks: dict[int, list] = field(default_factory=dict)
    next_ch: int = 1

    def track(self, values) -> int:
        assert len(values) == N
        tid = len(self.tracks) + 1
        self.tracks[tid] = list(values)
        return tid

    def channel(self, **attrs) -> int:
        """attrs: attribute -> track id (int) or a list of values."""
        ch = self.next_ch
        self.next_ch += 1
        for attr, t in attrs.items():
            tid = t if isinstance(t, int) else self.track(t)
            self.map_rows.append(dict(id=len(self.map_rows) + 1, channel_id=ch,
                                      track_id=tid, attribute=attr, track_table_id=0,
                                      ch_map_table_id=0, record_id=0))
        return ch

    def frames(self):
        data = {"cyclecount": list(range(1, N + 1))}
        data.update({f"ch{t}": v for t, v in self.tracks.items()})
        return pd.DataFrame(self.map_rows), pd.DataFrame(data)


# ---------------------------------------------------------------------------
# 4. SCENE
# ---------------------------------------------------------------------------

def ramp(points, v):
    for (a, ca), (b, cb) in zip(points, points[1:]):
        if v <= b:
            t = 0.0 if b == a else max(0.0, (v - a) / (b - a))
            return tuple(int(round(x + (y - x) * t)) for x, y in zip(ca, cb))
    return points[-1][1]


@dataclass
class Built:
    df: pd.DataFrame
    ch_map: pd.DataFrame
    ch_tracks: pd.DataFrame
    notes: list[str]
    checks: dict


def build(layout: fm.Layout, meso: dict, fires: list[Fire], map_path: Path | None,
          notes: list[str]) -> Built:
    R = pu.Rows([])
    ch = Tracks()
    b = layout.bbox
    hw, hh = layout.half_w, layout.half_h
    top = z_of(N)
    checks: dict = {"markers": [], "discs": [], "fires": [], "cones": []}
    stations = meso["stations"]

    def xy(lon, lat):
        x, y = layout.world_xy(lon, lat)
        return float(x), float(y)

    def add(**kw) -> int:
        return R.add(type=NODE_GLYPH, parent_id=0, branch_level=0, **kw)

    def plot(pts, width, color, text="", show=0, colors=None, anchor=0, hide=0,
             ch_input=0) -> int:
        ax, ay, az = pts[anchor]
        par = add(geometry=GEO_POINT, topo=TOPO_PLOT, ratio=width, color_r=color[0],
                  color_g=color[1], color_b=color[2], color_a=0, translate_x=fm._r(ax),
                  translate_y=fm._r(ay), translate_z=fm._r(az), show_text=show, text=text,
                  hide=hide, ch_input_id=ch_input)
        for i, (x, y, z) in enumerate(pts):
            c = colors[i] if colors else color
            R.add(type=NODE_GLYPH, parent_id=par, branch_level=1, geometry=GEO_CUBE,
                  scale_x=0.0, scale_y=0.0, scale_z=0.0, translate_x=fm._r(x - ax),
                  translate_y=fm._r(y - ay), translate_z=fm._r(z - az),
                  color_r=c[0], color_g=c[1], color_b=c[2])
        return par

    def label(x, y, z, text, pinned=1, **kw) -> int:
        return add(geometry=GEO_CUBE, scale_x=0.0, scale_y=0.0, scale_z=0.0,
                   translate_x=fm._r(x), translate_y=fm._r(y), translate_z=fm._r(z),
                   show_text=pinned, text=text, **kw)

    # -- World row and floor ------------------------------------------------------
    R.add(type=NODE_WORLD, parent_id=0, branch_level=0, geometry=0,
          color_r=BG_COLOR[0], color_g=BG_COLOR[1], color_b=BG_COLOR[2],
          tag_color_mode=1, tag_color_r=234, tag_color_g=238, tag_color_b=236,
          tag_font_size=12,
          text="San Diego River Watershed Atlas · Phase 3 · The May 2014 Fire Siege")
    R.add(type=NODE_GRID, parent_id=0, branch_level=0, geometry=GEO_GRID,
          texture_id=1 if map_path else 0, scale_x=layout.sx, scale_y=layout.sy, scale_z=1.0,
          trigger_lo_x=fm._r(b.lon_min, 6), trigger_hi_x=fm._r(b.lon_max, 6),
          trigger_lo_y=fm._r(b.lat_min, 6), trigger_hi_y=fm._r(b.lat_max, 6),
          segments_x=8, segments_y=6, color_r=255, color_g=255, color_b=255,
          text=(f"San Diego County · the floor of the cube is Sun 11 May 2014 00:00 PDT · "
                f"lon {b.lon_min:.2f}..{b.lon_max:.2f}, lat {b.lat_min:.2f}..{b.lat_max:.2f}"))

    # -- The time frame: a ring at every midnight, the day named at a corner -------
    for d in range(DAYS + 1):
        z = z_of(d * 144)
        corners = [(-hw, -hh, z), (hw, -hh, z), (hw, hh, z), (-hw, hh, z), (-hw, -hh, z)]
        plot(corners, 0.04, (88, 96, 104), f"Midnight · {fmt_day(T0 + dt.timedelta(days=d))} 2014")
        # Named at the north-west corner: the opening view looks in from the
        # south-west, where the fire captions already crowd the near corner.
        label(-hw - 4, hh, z, fmt_day(T0 + dt.timedelta(days=d)))
    for x, y in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)):
        plot([(x, y, 0.0), (x, y, top)], 0.04, (88, 96, 104), "Time rises one unit per hour")

    # -- Stations: floor marker + humidity thread + alert discs ----------------------
    total_alerts = 0
    for abbr, s in stations.items():
        x, y = xy(s["lon"], s["lat"])
        alerts = [k for k in range(N) if is_alert(s["ws"][k], s["wd"][k], s["rh"][k])]
        total_alerts += len(alerts)
        rhs = [v for v in s["rh"] if v is not None]
        elev = f"{s['elev_ft']:,} ft" if s["elev_ft"] is not None else "elevation unknown"
        mid = add(geometry=GEO_SPHERE, translate_x=fm._r(x), translate_y=fm._r(y),
                  translate_z=0.0, scale_x=0.7, scale_y=0.7, scale_z=0.7,
                  color_r=210, color_g=214, color_b=220, segments_x=10, segments_y=8,
                  text=(f"{s['name']} ({abbr}) · {elev} · {len(alerts)} ten-minute fire "
                        f"alerts · lowest humidity {min(rhs):.0f}%" if rhs else s["name"]))
        checks["markers"].append((mid, s["lon"], s["lat"]))

        # Hourly mean humidity, one vertex per hour at the hour's middle; a
        # station with no report in an hour breaks its thread there.
        hourly = []
        for h in range(DAYS * 24):
            vs = [v for v in s["rh"][h * 6:h * 6 + 6] if v is not None]
            hourly.append(sum(vs) / len(vs) if vs else None)
        run: list = []
        for h, v in enumerate(hourly + [None]):
            if v is None:
                if len(run) >= 2:
                    plot([(x, y, z_of(hh_ * 6 + 3)) for hh_, _ in run], THREAD_WIDTH,
                         (200, 200, 200),
                         f"{s['name']} · hourly relative humidity, "
                         f"{fmt_when(when(run[0][0] * 6))} to {fmt_when(when(run[-1][0] * 6 + 5))}",
                         colors=[sa.rh_color(vv) for _, vv in run])
                run = []
            else:
                run.append((h, v))

        half_t = UNITS_PER_HOUR / 6 / 2
        for k in alerts:
            sev = severity(s["ws"][k], s["rh"][k])
            c = ramp(SEVERITY_RAMP, sev)
            r = DISC_R0 + DISC_R_PER_SEVERITY * sev
            nid = add(geometry=GEO_CYLINDER, translate_x=fm._r(x), translate_y=fm._r(y),
                      translate_z=fm._r(z_of(k) + half_t, 4), scale_x=fm._r(r, 3),
                      scale_y=fm._r(r, 3), scale_z=fm._r(half_t, 4),
                      color_r=c[0], color_g=c[1], color_b=c[2], segments_x=12, segments_y=2,
                      text=(f"Fire alert · {s['name']} · {fmt_when(when(k))} · wind "
                            f"{s['ws'][k]} mph from {s['wd'][k]}°, gusts {s['gust'][k]}, "
                            f"humidity {s['rh'][k]}%, {s['temp_f'][k]}°F · severity {sev:g}"))
            checks["discs"].append((nid, k))
    notes.append(f"stations: {len(stations)}, fire-alert discs: {total_alerts}")

    # -- Fires: perimeter at ignition, at out, on the floor; vertical edges ---------
    used_label_z: list[float] = []
    for f in fires:
        k0, k1 = frame_of(f.start), frame_of(f.out)
        z0, z1 = z_of(k0), z_of(min(k1, N))
        parts = []
        for ring in f.rings:
            lons, lats = tr.simplify_polyline([p[0] for p in ring], [p[1] for p in ring],
                                              PERIMETER_SIMPLIFY_M)
            if len(lons) >= 4:
                parts.append([xy(lo, la) for lo, la in zip(lons, lats)])
        parts.sort(key=len, reverse=True)
        cause = {2: "equipment use", 14: "unknown"}.get(f.cause, f"CAL FIRE cause code {f.cause}")
        head = (f"{f.name} Fire · ignited {fmt_when(f.start)} · out {fmt_when(f.out)} · "
                f"{f.acres_mapped:,.0f} acres mapped ({f.acres_reported:,.0f} reported) · "
                f"cause: {cause}")
        for i, part in enumerate(parts):
            main = i == 0
            ign = plot([(x, y, z0) for x, y in part], 0.14 if main else 0.1, FIRE_COLOR,
                       head if main else f"{f.name} Fire · perimeter at ignition")
            if main:
                checks["fires"].append((ign, f, z0))
                # The pinned name sits at the OUT ring, with the date span.
                # All eight fires ignited within 72 hours, so names pinned at
                # ignition sat at one height and overwrote each other; the
                # out times run from 15 to 22 May and spread them apart. The
                # full record is on the ignition ring (click it).
                x_, y_ = part[0]
                span = (f"{f.start.day}–{f.out.day} May" if f.out.date() != f.start.date()
                        else f"{f.start.day} May")
                # Tomahawk and River were declared out at the same minute, so
                # a label landing within 5 units of an earlier one steps up.
                lz = z1 + 2.5
                while any(abs(lz - u) < 5.0 for u in used_label_z):
                    lz += 6.0
                used_label_z.append(lz)
                label(x_, y_, lz, f"{f.name} Fire · {span}")
            plot([(x, y, z1) for x, y in part], 0.07, FIRE_OUT_COLOR,
                 f"{f.name} Fire · declared out {fmt_when(f.out)}")
            plot([(x, y, 0.05) for x, y in part], 0.07, FIRE_FLOOR_COLOR,
                 f"{f.name} Fire · mapped footprint")
        main = parts[0]
        for j in range(FIRE_EDGES):
            x, y = main[int(j * len(main) / FIRE_EDGES)]
            plot([(x, y, z0), (x, y, z1)], 0.05, FIRE_COLOR,
                 f"{f.name} Fire · burning {fmt_when(f.start)} to {fmt_when(f.out)}")
        notes.append(f"fire {f.name}: {fmt_when(f.start)} -> {fmt_when(f.out)}, "
                     f"{f.acres_mapped:,.0f} ac mapped, {sum(len(p) for p in parts)} perimeter "
                     f"vertices, matched by {f.matched_by}")

    # -- The resting pose: the ten minutes with the most stations in alert ----------
    alert_count = [sum(1 for s in stations.values() if is_alert(s["ws"][k], s["wd"][k], s["rh"][k]))
                   for k in range(N)]
    rest = max(range(N), key=lambda k: alert_count[k])
    notes.append(f"resting pose: frame {rest}, {fmt_when(when(rest))}, "
                 f"{alert_count[rest]} stations in alert")

    # -- The now plane and everything that rides it -----------------------------------
    plane_z = ch.track([fm._r(z_of(k), 4) for k in range(N)])
    readout_day_z = ch.track([fm._r(z_of(k) + 20, 4) for k in range(N)])
    readout_time_z = ch.track([fm._r(z_of(k) + 6, 4) for k in range(N)])
    plot([(-hw, -hh, 0.0), (hw, -hh, 0.0), (hw, hh, 0.0), (-hw, hh, 0.0), (-hw, -hh, 0.0)],
         0.12, PLANE_COLOR, "Now", ch_input=ch.channel(translate_z=plane_z))
    R.rows[-6]["translate_z"] = fm._r(z_of(rest), 4)
    checks["plane"] = R.rows[-6]["id"]

    for abbr, s in stations.items():
        x, y = xy(s["lon"], s["lat"])
        rot, rad, ln, hide, cols = [], [], [], [], []

        def observed(k):
            return None not in (s["ws"][k], s["wd"][k], s["rh"][k])

        for k in range(N):
            ws_, wd_, rh = s["ws"][k], s["wd"][k], s["rh"][k]
            # One missed scrape between two observations holds the previous
            # cone for display (it would otherwise blink off for ten minutes);
            # anything longer hides it. Alerts never use held values.
            bridged = (not observed(k) and 0 < k < N - 1 and observed(k - 1)
                       and observed(k + 1) and not hide[-1])
            if bridged:
                hide.append(0)
                rot.append(rot[-1]); rad.append(rad[-1]); ln.append(ln[-1])
                cols.append(cols[-1])
                continue
            if ws_ is None or wd_ is None or rh is None:
                hide.append(1)
                rot.append(rot[-1] if rot else 0.0)
                rad.append(rad[-1] if rad else 0.0)
                ln.append(ln[-1] if ln else 0.0)
                cols.append(cols[-1] if cols else (0, 0, 0))
                continue
            r_, l_ = sa.cone_size(ws_)
            hide.append(0)
            rot.append(sa.downwind_bearing(wd_))
            rad.append(r_)
            ln.append(l_)
            cols.append(sa.rh_color(rh))
        rad_t = ch.track(rad)
        nid = add(geometry=GEO_CONE, translate_x=fm._r(x), translate_y=fm._r(y),
                  translate_z=fm._r(z_of(rest), 4), rotate_x=90.0, rotate_y=rot[rest],
                  scale_x=rad[rest], scale_y=rad[rest], scale_z=ln[rest], hide=hide[rest],
                  color_r=cols[rest][0], color_g=cols[rest][1], color_b=cols[rest][2],
                  segments_x=12, segments_y=4,
                  ch_input_id=ch.channel(translate_z=plane_z, rotate_y=rot, scale_x=rad_t,
                                         scale_y=rad_t, scale_z=ln, hide=hide,
                                         color_r=[c[0] for c in cols],
                                         color_g=[c[1] for c in cols],
                                         color_b=[c[2] for c in cols]),
                  text=f"{s['name']} · wind now · points downwind, size = speed, "
                       f"colour = humidity")
        checks["cones"].append((nid, abbr))

    for f in fires:
        cx = sum(p[0] for p in f.rings[0]) / len(f.rings[0])
        cy_ = sum(p[1] for p in f.rings[0]) / len(f.rings[0])
        x, y = xy(cx, cy_)
        k0, k1 = frame_of(f.start), frame_of(f.out)
        burning = [0 if k0 <= k < k1 else 1 for k in range(N)]
        add(geometry=GEO_OCTA, translate_x=fm._r(x), translate_y=fm._r(y),
            translate_z=fm._r(z_of(rest), 4), scale_x=2.4, scale_y=2.4, scale_z=3.6,
            color_r=255, color_g=110, color_b=30, hide=burning[rest],
            ch_input_id=ch.channel(translate_z=plane_z, hide=burning),
            text=f"{f.name} Fire · burning now")

    # Readout at the plane's north-east corner: one day label and one
    # time-of-day label showing per frame.
    checks["readout"] = {"days": {}, "times": {}}
    for d in range(DAYS):
        on = [1 if when(k).date() == (T0 + dt.timedelta(days=d)).date() else 0 for k in range(N)]
        checks["readout"]["days"][d] = label(
            hw + 6, -hh - 6, z_of(rest) + 20, fmt_day(T0 + dt.timedelta(days=d)) + " 2014",
            pinned=on[rest], ch_input_id=ch.channel(translate_z=readout_day_z, show_text=on))
    for slot in range(144):
        on = [1 if k % 144 == slot else 0 for k in range(N)]
        t = T0 + slot * STEP
        checks["readout"]["times"][slot] = label(
            hw + 6, -hh - 6, z_of(rest) + 6, f"{t:%H:%M} PDT", pinned=on[rest],
            ch_input_id=ch.channel(translate_z=readout_time_z, show_text=on))

    # -- Legend, beyond the east edge ---------------------------------------------
    lx, ly = hw + 30, -hh - 70
    z = top + 60.0              # above the cube, clear of the running readout

    def step(n=1.0):
        nonlocal z
        z -= 13.0 * n

    # Short lines: a tag draws to the right of its glyph, and at the opening
    # view the long versions ran off the screen. The full definitions are in
    # the README and on the discs' own labels.
    label(lx, ly, z, "1 unit up = 1 hour")
    step(1.5)
    label(lx, ly, z, "Thread colour = humidity")
    for rh in (5, 20, 40, 70, 95):
        step()
        c = sa.rh_color(rh)
        add(geometry=GEO_CUBE, translate_x=fm._r(lx), translate_y=fm._r(ly), translate_z=fm._r(z),
            scale_x=2.5, scale_y=2.5, scale_z=2.5, color_r=c[0], color_g=c[1], color_b=c[2],
            show_text=1, text=f"{rh}%")
    step(1.5)
    label(lx, ly, z, "Disc = fire alert (Sale, 2014)")
    step(0.9)
    label(lx, ly, z, "offshore wind > 25 mph, RH < 25%")
    for sev in (30, 15, 3):
        step()
        c = ramp(SEVERITY_RAMP, sev)
        r = DISC_R0 + DISC_R_PER_SEVERITY * sev
        add(geometry=GEO_CYLINDER, translate_x=fm._r(lx), translate_y=fm._r(ly),
            translate_z=fm._r(z), scale_x=r, scale_y=r, scale_z=0.3, color_r=c[0],
            color_g=c[1], color_b=c[2], show_text=1,
            text=f"severity {sev}", )
    step(1.5)
    c = FIRE_COLOR
    add(geometry=GEO_OCTA, translate_x=fm._r(lx), translate_y=fm._r(ly), translate_z=fm._r(z),
        scale_x=2.0, scale_y=2.0, scale_z=3.0, color_r=c[0], color_g=c[1], color_b=c[2],
        show_text=1, text="Fire: ignition ring to out ring")
    notes.append(f"legend: {top + 60:g} .. {z:g}; cube top {top:g}")

    ch_map, ch_tracks = ch.frames()
    checks.update(rest=rest, alert_count=alert_count)
    return Built(R.frame(), ch_map, ch_tracks, notes, checks)


# ---------------------------------------------------------------------------
# 5. BASEMAP
# ---------------------------------------------------------------------------

def fetch_basemap(want: bm.BBox, out_path: Path) -> bm.BBox:
    from PIL import Image, ImageEnhance
    plan = bm.plan_basemap(want, provider_key="opentopomap", target_px=2048, tile_cap=140)
    print(f"  basemap: {plan.provider.label}, zoom {plan.zoom}, {plan.tile_count} tiles")
    bm.build_basemap(plan, out_path)
    img = Image.open(out_path).convert("RGB")
    img = Image.blend(img, img.convert("L").convert("RGB"), MAP_GREY_MIX)
    ImageEnhance.Brightness(img).enhance(MAP_BRIGHTNESS).save(out_path, format="PNG")
    return plan.bbox


# ---------------------------------------------------------------------------
# 6. VERIFICATION
# ---------------------------------------------------------------------------

def verify(node_path: Path, map_path: Path, tracks_path: Path, built: Built,
           layout: fm.Layout, meso: dict) -> list[str]:
    """Through the real loader, Scene and ChannelEngine: stations sit at their
    lon/lat, every alert disc at its time, every fire at its ignition time,
    and at sampled frames the plane, the cones' bearings and hiding, and the
    readout are what the source data says."""
    from glyphviz_core.channel_engine import ChannelEngine
    from glyphviz_core.channel_loader import load_ch_map, load_ch_tracks
    from glyphviz_core.csv_reader import load_node_csv
    from glyphviz_core.scene import Scene, node_world_matrix

    nodes = load_node_csv(str(node_path))
    by_id = {n.id: n for n in nodes}
    scene = Scene(nodes)
    rep = []
    worst = max(max(abs(scene.world_pos(nid)[0] - layout.world_xy(lo, la)[0]),
                    abs(scene.world_pos(nid)[1] - layout.world_xy(lo, la)[1]))
                for nid, lo, la in built.checks["markers"])
    worst_disc = max(abs(scene.world_pos(nid)[2] - z_of(k) - UNITS_PER_HOUR / 12)
                     for nid, k in built.checks["discs"])
    recount = sum(1 for s in meso["stations"].values() for k in range(N)
                  if is_alert(s["ws"][k], s["wd"][k], s["rh"][k]))
    worst_fire = max(abs(scene.world_pos(nid)[2] - z_of(frame_of(f.start)))
                     for nid, f, _z in built.checks["fires"])
    rep.append(f"stations at lon/lat: worst offset {worst:.5f}; alert discs "
               f"{len(built.checks['discs'])} (independent recount {recount}), worst time "
               f"error {worst_disc:.4f} units; fires at ignition height: worst {worst_fire:.4f}")

    eng = ChannelEngine()
    tracks, id_to_col = load_ch_tracks(str(tracks_path))
    eng.load(load_ch_map(str(map_path)), tracks, id_to_col, nodes)
    worst_plane = worst_bearing = 0.0
    wrong_hide = wrong_readout = 0
    sample = sorted({0, 431, built.checks["rest"], 900, N - 1})
    for k in sample:
        eng.apply_frame(k)
        sc = Scene(nodes)
        worst_plane = max(worst_plane, abs(sc.world_pos(built.checks["plane"])[2] - z_of(k)))
        for nid, abbr in built.checks["cones"]:
            s = meso["stations"][abbr]

            def obs(i):
                return 0 <= i < N and None not in (s["ws"][i], s["wd"][i], s["rh"][i])
            missing = not obs(k)
            held = missing and obs(k - 1) and obs(k + 1)
            nd = by_id[nid]
            if bool(nd.hide) != (missing and not held):
                wrong_hide += 1
            if missing or s["ws"][k] == 0:
                continue
            axis = node_world_matrix(nd, sc)[:3, 2]
            bearing = math.degrees(math.atan2(axis[0], axis[1])) % 360
            want = sa.downwind_bearing(s["wd"][k])
            worst_bearing = max(worst_bearing, abs((bearing - want + 180) % 360 - 180))
        d, slot = divmod(k, 144)
        days_on = [i for i, nid in built.checks["readout"]["days"].items() if by_id[nid].show_text]
        times_on = [i for i, nid in built.checks["readout"]["times"].items() if by_id[nid].show_text]
        if days_on != [d] or times_on != [slot]:
            wrong_readout += 1
    eng.reset()
    rep.append(f"at {len(sample)} frames: plane height error {worst_plane:.4f}, cone bearing "
               f"error {worst_bearing:.3f}°, wrong cone hide {wrong_hide}, wrong readout "
               f"{wrong_readout}; engine {eng.frame_count} frames, "
               f"{len(eng.bound_node_ids)} bound nodes")
    return rep


# ---------------------------------------------------------------------------
# 7. MAIN
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", type=Path, default=HERE)
    ap.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--no-basemap", action="store_true")
    args = ap.parse_args()
    notes: list[str] = []

    meso = load_mesonet(args.archive, args.refresh)
    notes.append(f"weather: {len(meso['stations'])} stations x {meso['n']} frames, "
                 f"{meso['single_gaps']} single missed scrapes (cones hold through them; "
                 f"alerts and threads do not)")
    fires = load_fires(args.refresh, notes)

    lons = [s["lon"] for s in meso["stations"].values()]
    lats = [s["lat"] for s in meso["stations"].values()]
    pw, ph = (max(lons) - min(lons)) * 0.04, (max(lats) - min(lats)) * 0.04
    window = bm.BBox(min(lons) - pw, max(lons) + pw, min(lats) - ph, max(lats) + ph)
    map_path = None
    if not args.no_basemap:
        (args.out_dir / "media").mkdir(parents=True, exist_ok=True)
        map_path = args.out_dir / "media" / "01_county_map.png"
        window = fetch_basemap(window, map_path)
    sy = PLATE_HEIGHT / (window.lat_max - window.lat_min)
    sx = sy * math.cos(math.radians((window.lat_min + window.lat_max) / 2))
    layout = fm.Layout(window, round(sx, 4), round(sy, 4), 1.0)

    built = build(layout, meso, fires, map_path, notes)
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
    for line in verify(node_path, map_csv, tracks_csv, built, layout, meso):
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
