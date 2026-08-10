#!/usr/bin/env python3
"""
autosleep_2025_glyphviz1.py
============================
Generates a GlyphViz-native CSV pair from a year of Apple Watch sleep data
(captured via the AutoSleep app), visualized as a 3-level hierarchy:

  branch_level 0 - one Rod-topology cylinder per month (a subtle low-alpha
                    spine; days ring off it)
  branch_level 1 - one day ring per day: a solid Torus whose children are
                    placed around its tube, scaled by that day's total
                    sleep hours. Color diverges blue/red with (deep sleep -
                    7-day deep average) -- blue nights slept deeper than
                    your own recent trend, red nights shallower. Laid side
                    by side along a month, consecutive rings overlap enough
                    to read as one continuous ribbed pipe.
  branch_level 2 - one small octahedron per slept hour, ringing the tube as
                    a radial fringe, plus one octahedron at the top of each
                    ring (day rings are rotated 90 deg about Z to put a
                    fixed ring position there) whose scale_y is that day's
                    hours of deep sleep * DEEP_UNIT (1h -> a uniform
                    octahedron; scale_x/scale_z pinned at the floor).

V2 (2026-08-10): rebuilt on GlyphViz's native minimal-dialect node CSV
(no more borrowed 94-column ANTz header rows) to fix three things Jeff
flagged against the original ANTz reference render:
  - Hourly octahedra were WAY too pointy. Root cause (verified against the
    real engine, glyphviz_core.topology.compute_world_transforms): the old
    day-ring scale was non-uniform (5, 5, 0.5) -- a flattened disc, not a
    round tube. GlyphViz's "legacy scale inheritance" carries a parent's
    PER-AXIS scale straight through to children, so that flattening got
    baked unevenly into whichever world axis each hour-tick's own local
    axes happened to land on (a 0.1/0.1/1.0 tick came out ~0.05/0.5/5.0 in
    world space -- a 1:10:100 ratio, not the authored 1:1:10). Fix: give
    the day ring a UNIFORM scale (DAY_RADIUS on all three axes) so a
    child's own scale ratio survives into world space unchanged, and
    shrink the tick's own long axis so it reads as a small fringe spike
    (~1 world unit) instead of a radial needle as long as the ring itself.
  - Background was a dark teal (50, 101, 101) inherited byte-for-byte from
    the ANTz World row. Fixed with an explicit World row (id=1, type=0)
    set to pure black.
  - Channel tracks animated the hourly octahedra's alpha in and out for no
    data-driven reason. Dropped entirely -- no ch-map/ch-tracks output,
    no ch_input_id column. (A second AutoSleep-family example using
    channels meaningfully is the planned follow-up.)

Also switched every rotated node to GlyphViz's own EULER_XYZ rotation
convention (rotation_mode=0, explicit per node-csv-format.md) rather than
leaving rotation_mode unset -- except the month glyph, whose rotate_x=90/
rotate_y=90 was tuned for ANTz's Heading/Tilt/Roll convention and still
needs rotation_mode=1 to reorient its Rod-topology children along world X
exactly as before.

V3 (2026-08-10, same day): two more corrections from Jeff after seeing V2:
  - Day-ring scale now encodes total sleep hours (DAY_RADIUS_BASE +
    DAY_RADIUS_PER_HOUR * hours), which is what Jeff remembered the
    original design meaning. The V2 (and original ANTz-derived) script
    actually computed this exact quantity as `p_scale` and then never used
    it -- a real dead-code bug, not a design choice; day-ring scale was
    silently constant. Restored and wired in for real this time.
  - Month groups were ~300 world units apart (the fixed MONTH_X_STEP=400
    carried over from the ANTz version) while a month's own days only
    span ~90 world units -- a gap equivalent to ~100 empty day-slots, which
    read as "separated by multiple months." MONTH_X_STEP is now derived
    from the Rod-topology day-placement math itself (see _rod_day_offset
    below) so the gap between month groups comes out to ~GAP_DAYS days,
    not a hand-picked constant that happened to assume a very different
    per-day spacing.

V4 (2026-08-10, same day): two more corrections from Jeff:
  - Day rings now carry rotate_z=90 so the deep marker's fixed ring
    position (DEEP_XPOS) lands at the top of the ring instead of the side.
  - Deep sleep is now conveyed by the marker's scale_x/scale_y RATIO
    (scale_x = DEEP_UNIT * deep_hours, scale_y = scale_z = DEEP_UNIT)
    instead of an absolute scale_y magnitude, so it isn't confounded by
    the day ring's own (now hours-driven) scale.

V5 (2026-08-10, same day): the ratio idea was right but scale_x/scale_z
were floating with deep_hours, which (combined with the renderer's 0.2
floor) both hid the effect on most days and let neighboring markers
overlap. Simplified per Jeff: scale_x/scale_z pinned at DEEP_UNIT (0.2,
exactly the floor -- small enough to avoid overlap, no reason to go
smaller), scale_y = DEEP_UNIT * deep_hours (the axis aligned with the
ring's own large-diameter plane). 1h deep sleep -> a uniform 0.2 octahedron.

V6 (2026-08-10, same day): dropped the DEEP_UNIT multiplier on scale_y --
it's deep_hours directly now. Apple changed AutoSleep's deep-sleep
detection algorithm partway through this dataset (visibly, in the render:
tall spikes early on, then uniformly floored-at-0.2 markers from
2024-01-14 onward), so most of 2024-2025 rarely reports over an hour of
deep sleep and the 0.2x scaling was compressing what little signal is
left. The pre-2024-01-14 nights will render very tall by comparison --
that's the real data, not a bug.

Design note (flagging an assumption, not just making it silently): the day
ring's color still encodes (deep sleep - 7-day rolling average of deep
sleep), not literal total hours slept. That's what actually produced the
reference image's blue/red pattern, and it's a richer signal (trending
better/worse vs. your own baseline) than a flat hours-slept gradient would
be -- but Jeff, if you'd rather it be literal total sleep hours, that's a
one-function swap (see `diverging_color` and its call site below).

Input
-----
Requires your own AutoSleep CSV export (in the app: Settings > Export CSV),
saved next to this script as AUTOSLEEP_RAW_CSV below. Expected columns
(fuzzy-matched, case-insensitive): a date/ISO8601 column, bedtime, waketime,
asleep, deep, deepAvg7, quality. Personal health data isn't included in this
repo -- the gv_*.csv files already in this folder are the output of a prior
run and can be loaded into GlyphViz directly without rerunning this script.

Output (written next to this script)
-------------------------------------
  autosleep_2025_gv_node.csv
  autosleep_2025_gv_tag.csv

Usage
-----
  python autosleep_2025_glyphviz1.py [--profile AllLayers|DaysPlusDeep|HoursOnly|MonthsOnly]
"""

import csv, re, argparse
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import numpy as np

# ------------------ PATHS ------------------
SCRIPT_DIR = Path(__file__).resolve().parent
AUTOSLEEP_RAW_CSV = SCRIPT_DIR / "autosleep_2025_raw_export.csv"

NODE_OUT = SCRIPT_DIR / "autosleep_2025_gv_node.csv"
TAG_OUT  = SCRIPT_DIR / "autosleep_2025_gv_tag.csv"

NODE_COLS = [
    "id", "type", "parent_id", "branch_level",
    "translate_x", "translate_y", "translate_z",
    "rotate_x", "rotate_y", "rotate_z", "rotation_mode",
    "scale_x", "scale_y", "scale_z",
    "color_r", "color_g", "color_b", "color_a",
    "geometry", "hide", "topo", "ratio",
]


def _row(**kw):
    """A node row with the sane defaults every column has on load."""
    row = dict.fromkeys(NODE_COLS, 0)
    row.update(dict(
        branch_level=0, rotation_mode=0,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=255, color_g=255, color_b=255, color_a=255,
        geometry=11, topo=0, ratio=0.1,
    ))
    row.update(kw)
    return row


# ------------------ LAYOUT & GLYPH PARAMS ------------------
MONTH_Y_STEP     = 150.0
DAY_OFFSET_X     = 180.0
UNIT_LEN_PER_DAY = 25
HOUR_START_X     = -180.0
HOUR_STEP_X      = 15.0

MONTH_GEOM     = 19   # GEO_CYLINDER solid
MONTH_TOPO     = 6    # TOPO_ROD
MONTH_RADIUS   = 2.2
MONTH_HALF_LEN = 2.2
MONTH_ROT_X    = 90.0
MONTH_ROT_Y    = 90.0   # tuned for HTR (rotation_mode=1) -- see build_month_row()

DAY_GEOM           = 7    # GEO_TORUS solid (was 18, GEO_CYLINDER_WIRE -- mismatched
                           # against topo=3/Torus, and hid the ring shape entirely)
DAY_TOPO           = 3    # TOPO_TORUS (rings the hourly children)
DAY_RATIO          = 0.15 # tube/major fraction; thicker than the original 0.1
                           # so the ring reads as a visible tube, not a thin wire
PARENT_ALPHA       = 230

# Day-ring scale encodes that day's TOTAL sleep hours (this is the quantity
# the original ANTz-derived script computed as `p_scale` and then never
# actually used -- day-ring size was silently constant; see V3 note above).
# Tuned so a ~7h night lands close to the old fixed radius (4.5).
DAY_RADIUS_BASE     = 2.0
DAY_RADIUS_PER_HOUR = 0.35
DAY_RADIUS_MIN      = 1.5   # floor for missing/zero-hours days

def day_ring_radius(total_hours):
    return max(DAY_RADIUS_MIN, DAY_RADIUS_BASE + DAY_RADIUS_PER_HOUR * total_hours)


def _rod_day_offset(d):
    """World-space X offset of day `d` from its month's own center, after
    Rod-topology placement + the month glyph's own MONTH_RADIUS scale.
    Mirrors glyphviz_core.topology's Rod formula (translate_x normalized
    0-180 spans 10*B of rendered length, B = the global base_scale of 1.0):
    offset = ((d*UNIT_LEN_PER_DAY - DAY_OFFSET_X) / 180) * 10 * MONTH_RADIUS.
    Used only to size MONTH_X_STEP below -- day nodes still go through the
    real Rod topology at load time, this just predicts its output."""
    local_x = d * UNIT_LEN_PER_DAY - DAY_OFFSET_X
    return local_x * (10.0 / 180.0) * MONTH_RADIUS

# MONTH_X_STEP was a flat 400 world units carried over from the ANTz
# version, while a month's own days only span ~90 world units under the
# Rod-topology math above -- a ~300-unit gap, equivalent to ~100 empty
# day-slots, which read as "separated by multiple months." Instead, derive
# the step so consecutive month groups sit GAP_DAYS day-slots apart.
GAP_DAYS           = 5.0
DAY_WORLD_STEP     = _rod_day_offset(1) - _rod_day_offset(0)
NOMINAL_MONTH_DAYS = 30   # real months vary 28-31; MONTH_X_STEP is one fixed
                          # calendar-grid column width, so the realized gap
                          # is ~GAP_DAYS +/- 1 day depending on month length
MONTH_X_STEP = (GAP_DAYS * DAY_WORLD_STEP
                + _rod_day_offset(NOMINAL_MONTH_DAYS) - _rod_day_offset(1))

DEEP_DELTA_BAND_H = 0.5
DELTA_GAMMA       = 0.5
COLOR_NEUTRAL     = (200, 200, 200)
COLOR_ABOVE       = ( 40, 80, 255)
COLOR_BELOW       = (255, 80,  40)


def diverging_color(diff_hours, neutral, above, below, band_h=0.8, gamma=0.7, alpha=230):
    if diff_hours is None:
        r, g, b = neutral
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
    return int(np.clip(r, 0, 255)), int(np.clip(g, 0, 255)), int(np.clip(b, 0, 255)), int(alpha)


# One octahedron per slept hour, ringing the tube as a small radial fringe.
# Local scale is small: a day ring's effective world size is its own
# (now hours-driven) radius *cascaded through the month glyph's own
# MONTH_RADIUS scale* (GlyphViz's recursive scale inheritance -- verified
# against the real engine at ~9.9x for a ~7h night, not the ~4.5x an
# isolated day-ring-only test would suggest), so a modest local scale here
# still reads as a proper fringe rather than a needle, and scales up and
# down naturally with each day's own ring size.
TICK_GEOM  = 11              # GEO_OCTA solid
TICK_SCALE = (0.07, 0.07, 0.10)  # -> ~0.7-1.0 world units, under the tube's
                                  # own ~1.5 world-unit radius (was 0.1/0.1/
                                  # 1.0 under a flattened, non-uniform parent
                                  # -- ~5 world units, a radial needle)
TICK_TZ    = 0.05            # nudges the tick just past the tube surface so
                              # it doesn't sink halfway into the solid mesh
SLEEP_COL  = (90, 210, 130, 200)

# One octahedron per day, at a FIXED ring position (same angle every day,
# on top of the ring -- day rings are rotated 90 deg about Z so this
# position lands at the top). scale_x and scale_z are pinned at the
# renderer's own 0.2-per-axis floor (see node-csv-format.md) -- small
# enough to avoid neighboring markers overlapping, and there's no reason
# to go smaller since 0.2 is the floor anyway. scale_y -- the axis aligned
# with the ring's own (large-diameter) plane -- is deep_hours directly
# (unscaled), so 1h deep sleep gives a perfectly uniform 0.2/0.2/0.2
# octahedron and scale_y grows/shrinks from there.
DEEP_GEOM   = 11    # GEO_OCTA solid
DEEP_XPOS   = 180.0
DEEP_TZ     = 0.08
DEEP_UNIT   = 0.2   # scale_x, scale_z; scale_y = deep_hours (unscaled)
DEEP_COLOR  = (80, 255, 80, 240)

# ------------------ PROFILES ------------------
PROFILES = {
    "AllLayers":    {"months": True,  "days": True, "hours": True,  "deep_bar": True},
    "DaysPlusDeep": {"months": False, "days": True, "hours": False, "deep_bar": True},
    "HoursOnly":    {"months": False, "days": True, "hours": True,  "deep_bar": False},
    "MonthsOnly":   {"months": True,  "days": False, "hours": False, "deep_bar": False},
}

# ------------------ HELPERS ------------------
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
    if not s or s.lower() in {"na", "nan", "none", "null", "-"}: return None
    if _num_re.match(s): return float(s.replace(",", "."))
    try:
        td = pd.to_timedelta(s, errors="raise")
        return td.total_seconds() / 3600.0
    except Exception:
        parts = s.split(":")
        try:
            if len(parts) == 2:
                h, m = int(parts[0]), int(parts[1]); return h + m / 60.0
            elif len(parts) == 3:
                h, m, sec = int(parts[0]), int(parts[1]), int(float(parts[2])); return h + m / 60.0 + sec / 3600.0
        except Exception:
            return None
    return None

def parse_quality(val):
    if val is None or (isinstance(val, float) and np.isnan(val)): return None
    s = str(val).strip().replace("%", "")
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
    deep  = parse_hours(r[col_deep]) if col_deep else None
    deep7 = parse_hours(r[col_deep7]) if col_deep7 else None
    qual  = parse_quality(r[col_quality]) if col_quality else None
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
year_to_row = {y: i for i, y in enumerate(years)}

month_centers = {}
for y in years:
    yrow = year_to_row[y]
    for mo in range(1, 12 + 1):
        month_centers[(y, mo)] = ((mo - 1) * MONTH_X_STEP, yrow * MONTH_Y_STEP, 0.0)

month_days = df.groupby(["year", "month"])["day"].max().rename("days_in_month").reset_index()

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
for key in ("months", "days", "hours", "deep_bar"):
    val = getattr(args, key)
    if val is not None:
        cfg[key] = bool(val)

# ------------------ WRITE NODE & TAG CSVs ------------------
with open(NODE_OUT, "w", newline="", encoding="utf-8") as fn, \
     open(TAG_OUT, "w", newline="", encoding="utf-8") as ft:

    node_writer = csv.DictWriter(fn, fieldnames=NODE_COLS)
    node_writer.writeheader()
    tag_writer = csv.writer(ft)
    tag_writer.writerow(["id", "record_id", "table_id", "title", "description"])

    # World row: pure black background (the original ANTz World row's dark
    # teal (50, 101, 101) was carried over byte-for-byte -- that's the fix
    # for Jeff's "background should be black" note).
    node_writer.writerow(_row(id=1, type=0, color_r=0, color_g=0, color_b=0, color_a=255))

    next_id = 100000
    month_node_id = {}

    # Months (visible or invisible anchor)
    for (y, mo), (cx, cy, cz) in month_centers.items():
        if month_days[(month_days["year"] == y) & (month_days["month"] == mo)].empty:
            continue
        mid = next_id; next_id += 1
        month_node_id[(y, mo)] = mid
        if cfg["months"]:
            row = _row(
                id=mid, type=5, parent_id=0, branch_level=0,
                translate_x=cx, translate_y=cy, translate_z=cz,
                rotate_x=MONTH_ROT_X, rotate_y=MONTH_ROT_Y, rotation_mode=1,  # HTR
                scale_x=MONTH_HALF_LEN, scale_y=MONTH_RADIUS, scale_z=MONTH_RADIUS,
                geometry=MONTH_GEOM, topo=MONTH_TOPO,
                color_r=160, color_g=160, color_b=160, color_a=80,
            )
        else:
            row = _row(
                id=mid, type=5, parent_id=0, branch_level=0,
                translate_x=cx, translate_y=cy, translate_z=cz,
                scale_x=0.001, scale_y=0.001, scale_z=0.001,
                geometry=0, topo=0, color_a=0,
            )
        node_writer.writerow(row)

        ndays = int(month_days[(month_days["year"] == y) & (month_days["month"] == mo)]["days_in_month"].iloc[0])
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

        if cfg["days"]:
            cr, cg, cb, ca = diverging_color(
                diff_hours=(deep - deep7) if (deep is not None and deep7 is not None) else None,
                neutral=COLOR_NEUTRAL, above=COLOR_ABOVE, below=COLOR_BELOW,
                band_h=DEEP_DELTA_BAND_H, gamma=DELTA_GAMMA, alpha=PARENT_ALPHA,
            )
            day_radius = day_ring_radius(total_hours)
            row = _row(
                id=did, type=5, parent_id=pid, branch_level=1,
                translate_x=local_x, translate_y=0.0, translate_z=0.0,
                rotate_z=90.0, rotation_mode=0,  # brings the deep marker (DEEP_XPOS) to the top
                scale_x=day_radius, scale_y=day_radius, scale_z=day_radius,
                geometry=DAY_GEOM, topo=DAY_TOPO, ratio=DAY_RATIO,
                color_r=cr, color_g=cg, color_b=cb, color_a=ca,
            )
        else:
            row = _row(
                id=did, type=5, parent_id=pid, branch_level=1,
                translate_x=local_x, translate_y=0.0, translate_z=0.0,
                scale_x=0.001, scale_y=0.001, scale_z=0.001,
                geometry=0, topo=0, color_a=0,
            )
        node_writer.writerow(row)

        st_str = r["start"].strftime("%Y-%m-%d %H:%M") if r["start"] else "NA"
        en_str = r["end"].strftime("%Y-%m-%d %H:%M") if r["end"] else "NA"
        parts = [f"{y}-{mo:02d}-{d:02d}", f"hrs={total_hours:.2f}"]
        if deep  is not None: parts.append(f"deep={deep:.2f}")
        if deep7 is not None: parts.append(f"deepAvg7={deep7:.2f}")
        if q     is not None: parts.append(f"qual={q:.0f}")
        parts += [f"start={st_str}", f"end={en_str}"]
        tag_writer.writerow([did, did, 0, " | ".join(parts) + " ", ""])

        # Hours: one small octahedron per slept hour, fringing the tube.
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
                row = _row(
                    id=tid, type=5, parent_id=did, branch_level=2,
                    translate_x=hx, translate_y=0.0, translate_z=TICK_TZ,
                    scale_x=TICK_SCALE[0], scale_y=TICK_SCALE[1], scale_z=TICK_SCALE[2],
                    geometry=TICK_GEOM, topo=2,
                    color_r=SLEEP_COL[0], color_g=SLEEP_COL[1], color_b=SLEEP_COL[2], color_a=SLEEP_COL[3],
                )
                node_writer.writerow(row)
                hh = k % 24
                tag_writer.writerow([tid, tid, 0, f"{y}-{mo:02d}-{d:02d} hour={hh:02d}:00 sleep ", ""])

        # Deep marker: fixed ring position (top, once the day ring is
        # rotated 90 deg -- see above). scale_x/scale_z pinned at the
        # floor; scale_y is deep hours directly, unscaled (1h -> a uniform
        # 0.2/0.2/0.2 octahedron; less than that hits the 0.2 floor, which
        # is expected and correct for Apple's post-2024 AutoSleep algorithm
        # that rarely reports over an hour of deep sleep -- see V6 note).
        if cfg["deep_bar"] and (deep is not None) and deep > 0:
            sid = next_id; next_id += 1
            row = _row(
                id=sid, type=5, parent_id=did, branch_level=2,
                translate_x=DEEP_XPOS, translate_y=0.0, translate_z=DEEP_TZ,
                scale_x=DEEP_UNIT, scale_y=deep, scale_z=DEEP_UNIT,
                geometry=DEEP_GEOM, topo=2,
                color_r=DEEP_COLOR[0], color_g=DEEP_COLOR[1], color_b=DEEP_COLOR[2], color_a=DEEP_COLOR[3],
            )
            node_writer.writerow(row)
            tag_writer.writerow([sid, sid, 0, f"{y}-{mo:02d}-{d:02d} deep={deep:.2f}h ", ""])

print("Wrote nodes & tags:")
print(" ", NODE_OUT)
print(" ", TAG_OUT)
