#!/usr/bin/env python3
"""
autosleep_2025_glyphviz1.py
============================
Generates GlyphViz/GaiaViz CSV files from a year of Apple Watch sleep data
(captured via the AutoSleep app), visualized as a 3-level hierarchy:

  branch_level 0 - one Rod-topology cylinder per month
  branch_level 1 - one day disc per day: a wireframe cylinder (flattened on Z)
                    using Torus topology to ring its hourly children; color
                    diverges blue/red with (deep sleep - 7-day deep average)
  branch_level 2 - one octahedron per slept hour, plus one extra octahedron
                    scaled in Y by that day's total deep sleep

Channel tracks animate the alpha channel of the branch_level-2 octahedrons.

Input
-----
Requires your own AutoSleep CSV export (in the app: Settings > Export CSV),
saved next to this script as AUTOSLEEP_RAW_CSV below. Expected columns
(fuzzy-matched, case-insensitive): a date/ISO8601 column, bedtime, waketime,
asleep, deep, deepAvg7, quality. Personal health data isn't included in this
repo -- the four gv_*.csv files already in this folder are the output of a
prior run and can be loaded into GlyphViz directly without rerunning this
script.

Output (written next to this script)
-------------------------------------
  autosleep_2025_gv_node.csv
  autosleep_2025_gv_tag.csv
  autosleep_2025_gv_ch-tracks.csv
  autosleep_2025_gv_ch-map.csv

Usage
-----
  python autosleep_2025_glyphviz1.py [--profile AllLayers|DaysPlusDeep|HoursOnly|MonthsOnly]
"""

import csv, math, re, argparse
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import numpy as np

# ------------------ PATHS ------------------
SCRIPT_DIR = Path(__file__).resolve().parent
AUTOSLEEP_RAW_CSV = SCRIPT_DIR / "autosleep_2025_raw_export.csv"

NODE_OUT  = SCRIPT_DIR / "autosleep_2025_gv_node.csv"
TAG_OUT   = SCRIPT_DIR / "autosleep_2025_gv_tag.csv"
CH_OUT    = SCRIPT_DIR / "autosleep_2025_gv_ch-tracks.csv"
CHMAP_OUT = SCRIPT_DIR / "autosleep_2025_gv_ch-map.csv"

# 7 literal ANTz/GaiaViz node-header rows: column names + 6 default records.
HEADER7 = [
    "id,type,data,selected,parent_id,branch_level,child_id,child_index,child_count,ch_input_id,ch_output_id,ch_last_updated,average,interval,aux_a_x,aux_a_y,aux_a_z,aux_b_x,aux_b_y,aux_b_z,color_shift,rotate_vec_x,rotate_vec_y,rotate_vec_z,rotate_vec_s,scale_x,scale_y,scale_z,translate_x,translate_y,translate_z,tag_offset_x,tag_offset_y,tag_offset_z,rotate_rate_x,rotate_rate_y,rotate_rate_z,rotate_x,rotate_y,rotate_z,scale_rate_x,scale_rate_y,scale_rate_z,translate_rate_x,translate_rate_y,translate_rate_z,translate_vec_x,translate_vec_y,translate_vec_z,shader,geometry,line_width,point_size,ratio,color_index,color_r,color_g,color_b,color_a,color_fade,texture_id,hide,freeze,topo,facet,auto_zoom_x,auto_zoom_y,auto_zoom_z,trigger_hi_x,trigger_hi_y,trigger_hi_z,trigger_lo_x,trigger_lo_y,trigger_lo_z,set_hi_x,set_hi_y,set_hi_z,set_lo_x,set_lo_y,set_lo_z,proximity_x,proximity_y,proximity_z,proximity_mode_x,proximity_mode_y,proximity_mode_z,segments_x,segments_y,segments_z,tag_mode,format_id,table_id,record_id,size\n",
    "1,0,1,0,0,0,1,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,1,1,1,1,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0.1,0,50,101,101,255,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,16,16,0,0,0,0,0,420\n",
    "2,1,2,0,0,0,2,2,3,0,0,0,0,1,0,0,0,0,0,0,0,0,0.008645,0.825266,-0.564678,1,1,1,-32.446629,-180.908295,143.514175,0,0,1,0,0,0,55.620094,0.6002,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0.1,0,50,101,101,255,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,214.306686,0,0,0,0,0,16,16,0,0,0,0,0,420\n",
    "3,1,3,0,2,1,3,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,-1,1,1,1,-0.5,0,571.75,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0.1,0,50,101,101,255,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,16,16,0,0,0,0,0,420\n",
    "4,1,4,0,2,1,4,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,1,0,1,1,1,0,-90,7,0,0,1,0,0,0,90,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0.1,0,50,101,101,255,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,16,16,0,0,0,0,0,420\n",
    "5,1,5,0,2,1,5,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,-1,0,0,1,1,1,85,0,7,0,0,1,0,0,0,90,270,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0.1,0,50,101,101,255,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,16,16,0,0,0,0,0,420\n",
    "6,6,6,1,0,0,0,1,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0.1,3,0,0,255,150,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,12,6,0,0,0,0,0,420\n",
]
COLS = HEADER7[0].rstrip("\n").split(",")

# ------------------ LAYOUT & GLYPH PARAMS ------------------
MONTH_X_STEP   = 400.0
MONTH_Y_STEP   = 150.0
DAY_OFFSET_X      = 180.0
UNIT_LEN_PER_DAY  = 25
HOUR_START_X  = -180.0
HOUR_STEP_X   = 15.0

MONTH_GEOM     = 19   # GEO_CYLINDER
MONTH_TOPO     = 6    # TOPO_ROD
MONTH_RADIUS   = 2.2
MONTH_HALF_LEN = 2.2
MONTH_ROT_X    = 90.0
MONTH_ROT_Y    = 90.0

PARENT_GEOM        = 18   # GEO_CYLINDER_WIRE
PARENT_TOPO        = 3    # TOPO_TORUS (rings the hourly children)
PARENT_ALPHA       = 230
PARENT_SCALE_BASE  = 2.2
PARENT_SCALE_PER_H = 0.30

DEEP_DELTA_BAND_H = 0.5
DELTA_GAMMA       = 0.5
COLOR_NEUTRAL     = (200, 200, 200)
COLOR_ABOVE       = ( 40, 80, 255)
COLOR_BELOW       = (255, 80,  40)

def diverging_color(diff_hours, neutral, above, below, band_h=0.8, gamma=0.7, alpha=230):
    if diff_hours is None:
        r,g,b = neutral
        return int(r), int(g), int(b), int(alpha)
    t = float(diff_hours) / max(1e-9, band_h)
    t = max(-1.0, min(1.0, t))
    if t >= 0:
        w = t ** gamma
        r = neutral[0] + w * (above[0] - neutral[0])
        g = neutral[1] + w * (above[1] - neutral[1])
        b = neutral[2] + w * (above[2] - neutral[2])
    else:
        w = (-t) ** gamma
        r = neutral[0] + w * (below[0] - neutral[0])
        g = neutral[1] + w * (below[1] - neutral[1])
        b = neutral[2] + w * (below[2] - neutral[2])
    return int(np.clip(r,0,255)), int(np.clip(g,0,255)), int(np.clip(b,0,255)), int(alpha)

TICK_GEOM   = 11   # GEO_OCTA
SLEEP_COL   = ( 90, 210, 130, 200)

DEEP_GEOM      = 11   # GEO_OCTA
DEEP_XPOS      = 180.0
DEEP_BAR_BASE  = 0.1
DEEP_BAR_PER_H = 0.6
DEEP_COLOR     = ( 80, 255, 80, 240)

FRAMES = 360
CH1_MIN, CH1_MAX = 100, 220
CH2_MIN, CH2_MAX = 100, 255

# ------------------ PROFILES ------------------
PROFILES = {
    "AllLayers": {"months": True, "days": True, "hours": True, "deep_bar": True, "ch_ids": {"months": 0, "days": 2, "hours": 1, "deep": 0}},
    "DaysPlusDeep": {"months": False, "days": True, "hours": False, "deep_bar": True, "ch_ids": {"months": 0, "days": 2, "hours": 0, "deep": 0}},
    "HoursOnly": {"months": False, "days": True, "hours": True, "deep_bar": False, "ch_ids": {"months": 0, "days": 0, "hours": 1, "deep": 0}},
    "MonthsOnly": {"months": True, "days": False, "hours": False, "deep_bar": False, "ch_ids": {"months": 0, "days": 0, "hours": 0, "deep": 0}},
}

# ------------------ HELPERS ------------------
def new_row(): return {c: 0 for c in COLS}

def write_row(w, row):
    row["size"] = 420
    row["record_id"] = row.get("id", 0)
    w.writerow([row.get(c, 0) for c in COLS])

def parse_dt(s):
    if pd.isna(s) or s == "": return None
    try: return pd.to_datetime(s)
    except Exception:
        try: return datetime.strptime(str(s), "%Y-%m-%d %H:%M:%S")
        except Exception:
            try: return pd.to_datetime(str(s), errors="coerce")
            except Exception: return None

_num_re = re.compile(r"^\s*-?\d+(?:[.,]\d+)?\s*$")
def parse_hours(val):
    if val is None or (isinstance(val, float) and np.isnan(val)): return None
    s = str(val).strip()
    if not s or s.lower() in {"na","nan","none","null","-"}: return None
    if _num_re.match(s): return float(s.replace(",", "."))
    try:
        td = pd.to_timedelta(s, errors="raise")
        return td.total_seconds() / 3600.0
    except Exception:
        parts = s.split(":")
        try:
            if len(parts) == 2:
                h, m = int(parts[0]), int(parts[1]); return h + m/60.0
            elif len(parts) == 3:
                h, m, sec = int(parts[0]), int(parts[1]), int(float(parts[2])); return h + m/60.0 + sec/3600.0
        except Exception:
            return None
    return None

def parse_quality(val):
    if val is None or (isinstance(val, float) and np.isnan(val)): return None
    s = str(val).strip().replace("%","")
    if not s: return None
    try: return float(s.replace(",", "."))
    except Exception: return None

def find_col_exact_or_frag(cols, preferred_exact=None, fallback_frag=None):
    if preferred_exact and preferred_exact in cols: return preferred_exact
    if fallback_frag:
        for c in cols:
            if fallback_frag.lower() in c.lower():
                return c
    return None

def hour_overlaps_sleep(s, e, hour_start):
    for base in (0, 1440):
        hs = hour_start + base
        he = hs + 60
        if hs < e and he > s:
            return True
    return False

# ------------------ LOAD CSV ------------------
if not AUTOSLEEP_RAW_CSV.exists():
    raise SystemExit(
        f"Missing input data CSV: {AUTOSLEEP_RAW_CSV}\n"
        "Export your sleep history from the AutoSleep app (Settings > Export CSV) "
        f"and save it as {AUTOSLEEP_RAW_CSV.name} next to this script.\n"
        "The gv_*.csv files already in this folder are pre-generated and can be "
        "loaded into GlyphViz directly without rerunning this script."
    )

df_raw = pd.read_csv(AUTOSLEEP_RAW_CSV)
cols_in = list(df_raw.columns)

col_date     = find_col_exact_or_frag(cols_in, "ISO8601", "date") or find_col_exact_or_frag(cols_in, "fromDate", "from")
col_bedtime  = find_col_exact_or_frag(cols_in, "bedtime", "bed")
col_waketime = find_col_exact_or_frag(cols_in, "waketime", "wake")
col_asleep   = find_col_exact_or_frag(cols_in, "asleep", "asleep")
col_deep     = find_col_exact_or_frag(cols_in, "deep", "deep")
col_deep7    = find_col_exact_or_frag(cols_in, "deepAvg7", "deepavg7")
col_quality  = find_col_exact_or_frag(cols_in, "quality", "qual")

rows = []
for _, r in df_raw.iterrows():
    d  = parse_dt(r[col_date]) if col_date else None
    st = parse_dt(r[col_bedtime]) if col_bedtime else None
    en = parse_dt(r[col_waketime]) if col_waketime else None
    if st and en and en < st: en = en + timedelta(days=1)
    hrs  = parse_hours(r[col_asleep]) if col_asleep else None
    if hrs is None and st and en: hrs = (en - st).total_seconds() / 3600.0
    deep = parse_hours(r[col_deep]) if col_deep else None
    deep7= parse_hours(r[col_deep7]) if col_deep7 else None
    qual = parse_quality(r[col_quality]) if col_quality else None
    rows.append({
        "date": pd.to_datetime(d).date() if d is not None else None,
        "start": st, "end": en,
        "hours": hrs, "deep": deep, "deepAvg7": deep7, "quality": qual
    })

df = (pd.DataFrame(rows)
        .dropna(subset=["date"])
        .sort_values("date")
        .reset_index(drop=True))
dt = pd.to_datetime(df["date"])
df["year"]  = dt.dt.year
df["month"] = dt.dt.month
df["day"]   = dt.dt.day

def sleeping_minutes(row):
    if row["start"] is None or row["end"] is None: return None
    s = row["start"].hour * 60 + row["start"].minute
    e = row["end"].hour * 60 + row["end"].minute
    if e < s: e += 1440
    return s, e
df["sleep_interval"] = df.apply(sleeping_minutes, axis=1)

years = sorted(df["year"].unique().tolist())
year_to_row = {y:i for i, y in enumerate(years)}

month_centers = {}
for y in years:
    yrow = year_to_row[y]
    for mo in range(1, 12+1):
        month_centers[(y, mo)] = ((mo - 1) * MONTH_X_STEP, yrow * MONTH_Y_STEP, 0.0)

month_days = df.groupby(["year","month"])["day"].max().rename("days_in_month").reset_index()

# ------------------ CLI ------------------
p = argparse.ArgumentParser()
p.add_argument("--profile", default="AllLayers", choices=list(PROFILES.keys()))
p.add_argument("--months", dest="months", action="store_true")
p.add_argument("--no-months", dest="months", action="store_false")
p.add_argument("--days", dest="days", action="store_true")
p.add_argument("--no-days", dest="days", action="store_false")
p.add_argument("--hours", dest="hours", action="store_true")
p.add_argument("--no-hours", dest="hours", action="store_false")
p.add_argument("--deep-bar", dest="deep_bar", action="store_true")
p.add_argument("--no-deep-bar", dest="deep_bar", action="store_false")
p.set_defaults(months=None, days=None, hours=None, deep_bar=None)
args = p.parse_args([] if '__file__' not in globals() else None)

cfg = dict(PROFILES[args.profile])
for key in ("months","days","hours","deep_bar"):
    val = getattr(args, key)
    if val is not None:
        cfg[key] = bool(val)

# ------------------ WRITE NODE & TAG CSVs ------------------
with open(NODE_OUT, "w", encoding="utf-8", newline="") as fn, \
     open(TAG_OUT,  "w", encoding="utf-8", newline="") as ft:

    # 7 header rows verbatim for node file
    fn.writelines(HEADER7)

    node_writer = csv.writer(fn)
    tag_writer  = csv.writer(ft)
    tag_writer.writerow(["id","record_id","table_id","title","description"])

    next_id = 100000
    month_node_id = {}

    # Months (visible or invisible anchor)
    for (y, mo), (cx, cy, cz) in month_centers.items():
        if month_days[(month_days["year"]==y)&(month_days["month"]==mo)].empty:
            continue
        mid = next_id; next_id += 1
        month_node_id[(y, mo)] = mid
        row = new_row()
        if cfg["months"]:
            row.update({
                "id": mid, "type": 5, "data": mid,
                "parent_id": 0, "branch_level": 0,
                "translate_x": cx, "translate_y": cy, "translate_z": cz,
                "rotate_x": MONTH_ROT_X, "rotate_y": MONTH_ROT_Y,
                "scale_x": MONTH_HALF_LEN, "scale_y": MONTH_RADIUS, "scale_z": MONTH_RADIUS,
                "geometry": MONTH_GEOM, "topo": MONTH_TOPO,
                "color_r": 160, "color_g": 160, "color_b": 160, "color_a": 80,
                "ch_input_id": cfg["ch_ids"]["months"]
            })
        else:
            row.update({
                "id": mid, "type": 5, "data": mid,
                "parent_id": 0, "branch_level": 0,
                "translate_x": cx, "translate_y": cy, "translate_z": cz,
                "scale_x": 0.001, "scale_y": 0.001, "scale_z": 0.001,
                "geometry": 0, "topo": 0,
                "color_r": 0, "color_g": 0, "color_b": 0, "color_a": 0,
                "ch_input_id": 0
            })
        write_row(node_writer, row)

        # Month tag (count of days present in data)
        ndays = int(month_days[(month_days["year"]==y)&(month_days["month"]==mo)]["days_in_month"].iloc[0])
        tag_writer.writerow([mid, mid, 0, f"{y}-{mo:02d} | month anchor | days={ndays} ", ""])

    # Days + children
    for _, r in df.iterrows():
        y, mo, d = int(r["year"]), int(r["month"]), int(r["day"])
        if (y, mo) not in month_node_id: continue
        pid = month_node_id[(y, mo)]
        local_x = d * UNIT_LEN_PER_DAY - DAY_OFFSET_X

        did = next_id; next_id += 1
        total_hours = float(r["hours"]) if r["hours"] is not None else 0.0
        deep  = float(r["deep"]) if r["deep"] is not None else None
        deep7 = float(r["deepAvg7"]) if r["deepAvg7"] is not None else None
        q     = float(r["quality"]) if r["quality"] is not None else None

        # Day parent
        row = new_row()
        if cfg["days"]:
            p_scale = PARENT_SCALE_BASE + PARENT_SCALE_PER_H * total_hours
            cr, cg, cb, ca = diverging_color(
                diff_hours = (deep - deep7) if (deep is not None and deep7 is not None) else None,
                neutral    = COLOR_NEUTRAL,
                above      = COLOR_ABOVE,
                below      = COLOR_BELOW,
                band_h     = DEEP_DELTA_BAND_H,
                gamma      = DELTA_GAMMA,
                alpha      = PARENT_ALPHA
            )
            row.update({
                "id": did, "type": 5, "data": did,
                "parent_id": pid, "branch_level": 1,
                "translate_x": local_x, "translate_y": 0.0, "translate_z": 0.0,
                "scale_x": 5, "scale_y": 5, "scale_z": 0.5,
                "geometry": PARENT_GEOM, "topo": PARENT_TOPO, "ratio": 0.1,
                "color_r": cr, "color_g": cg, "color_b": cb, "color_a": ca,
                "ch_input_id": cfg["ch_ids"]["days"]
            })
        else:
            row.update({
                "id": did, "type": 5, "data": did,
                "parent_id": pid, "branch_level": 1,
                "translate_x": local_x, "translate_y": 0.0, "translate_z": 0.0,
                "scale_x": 0.001, "scale_y": 0.001, "scale_z": 0.001,
                "geometry": 0, "topo": 0,
                "color_r": 0, "color_g": 0, "color_b": 0, "color_a": 0,
                "ch_input_id": 0
            })
        write_row(node_writer, row)

        # Day tag
        st_str = r["start"].strftime("%Y-%m-%d %H:%M") if r["start"] else "NA"
        en_str = r["end"].strftime("%Y-%m-%d %H:%M")   if r["end"]   else "NA"
        parts = [f"{y}-{mo:02d}-{d:02d}", f"hrs={total_hours:.2f}"]
        if deep  is not None:  parts.append(f"deep={deep:.2f}")
        if deep7 is not None:  parts.append(f"deepAvg7={deep7:.2f}")
        if q     is not None:  parts.append(f"qual={q:.0f}")
        parts += [f"start={st_str}", f"end={en_str}"]
        tag_writer.writerow([did, did, 0, " | ".join(parts) + " ", ""])

        # Hours
        s_e = r["sleep_interval"]
        if cfg["hours"] and s_e is not None:
            s, e = s_e
            wraps = e > 1440
            for k in range(24):
                hour_start = k * 60
                if not hour_overlaps_sleep(s, e, hour_start):
                    continue
                hx = HOUR_START_X + k * HOUR_STEP_X
                hour_end = hour_start + 60
                if wraps and hour_end <= 1440:
                    hx += 180.0
                tid = next_id; next_id += 1
                row = new_row()
                row.update({
                    "id": tid, "type": 5, "data": tid,
                    "parent_id": did, "branch_level": 2,
                    "translate_x": hx, "translate_y": 0.0, "translate_z": 0.0,
                    "scale_x": 0.1, "scale_y": 0.1, "scale_z": 1,
                    "geometry": TICK_GEOM, "topo": 2,
                    "color_r": SLEEP_COL[0], "color_g": SLEEP_COL[1], "color_b": SLEEP_COL[2], "color_a": SLEEP_COL[3],
                    "ch_input_id": cfg["ch_ids"]["hours"]
                })
                write_row(node_writer, row)
                hh = k % 24
                tag_writer.writerow([tid, tid, 0, f"{y}-{mo:02d}-{d:02d} hour={hh:02d}:00 sleep ", ""])

        # Deep bar
        if cfg["deep_bar"] and (deep is not None) and deep > 0:
            sid = next_id; next_id += 1
            sy = DEEP_BAR_BASE + DEEP_BAR_PER_H * deep
            row = new_row()
            row.update({
                "id": sid, "type": 5, "data": sid,
                "parent_id": did, "branch_level": 2,
                "translate_x": DEEP_XPOS, "translate_y": 0.0, "translate_z": 0.0,
                "rotate_y": 90.0,
                "scale_x": 0.1, "scale_y": 1*sy, "scale_z": 0.1,
                "geometry": DEEP_GEOM, "topo": 2,
                "color_r": DEEP_COLOR[0], "color_g": DEEP_COLOR[1], "color_b": DEEP_COLOR[2], "color_a": DEEP_COLOR[3],
                "ch_input_id": cfg["ch_ids"]["deep"]
            })
            write_row(node_writer, row)
            tag_writer.writerow([sid, sid, 0, f"{y}-{mo:02d}-{d:02d} deep={deep:.2f}h ", ""])

print("Wrote nodes & tags:")
print(" ", NODE_OUT)
print(" ", TAG_OUT)

# ------------------ CHANNELS & MAP ------------------
CYCLE = "cycleCount"
rows_c = []
for t in range(FRAMES):
    s1 = 0.5 + 0.5 * math.sin(2*math.pi * (t/60.0))
    s2 = 0.5 + 0.5 * math.sin(2*math.pi * (t/240.0))
    ch1 = int(round(CH1_MIN + s1*(CH1_MAX-CH1_MIN)))
    ch2 = int(round(CH2_MIN + s2*(CH2_MAX-CH2_MIN)))
    rows_c.append({CYCLE: t+1, "ch1": ch1, "ch2": ch2, "ch3": 0})
pd.DataFrame(rows_c, columns=[CYCLE,"ch1","ch2","ch3"]).to_csv(CH_OUT, index=False)
print("Wrote channels:", CH_OUT)

df_map = pd.DataFrame([
    {"id": 1, "channel_id": 1, "track_id": 1, "attribute": "color_a",
     "track_table_id": 0, "ch_map_table_id": 0, "record_id": 0},
    {"id": 2, "channel_id": 2, "track_id": 2, "attribute": "color_a",
     "track_table_id": 0, "ch_map_table_id": 0, "record_id": 0},
])
df_map.to_csv(CHMAP_OUT, index=False)
print("Wrote channel map:", CHMAP_OUT)
