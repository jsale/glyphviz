#!/usr/bin/env python3
r"""
generate_vehicle_sales_example.py
=================================
Turns the Kaggle used-vehicle auction dataset (~559k rows: make, model, body,
year, condition, odometer, MMR wholesale book value, selling price, sale date)
into two ready-to-load GlyphViz scenes. The point of the demo: aggregate a
half-million messy categorical records into a few hundred glyphs whose *every*
visual attribute encodes a statistic, so market structure you weren't looking
for is just visible.

Scene 1 -- Market_Galaxy/  (node + tag + ch-map + ch-tracks)
------------------------------------------------------------
A slowly rotating torus ring of the top makes, each make a sphere with its
top models orbiting it (Sphere topology):

  ring position   makes ordered cheap -> luxury around the torus
  make size       sales volume (sqrt scale)
  make color      median selling price vs MMR book value (blue = sells under
                  book, white = at book, red = over book)
  model geometry  dominant body class: Sedan=sphere, SUV=cube, Truck=cylinder,
                  Coupe=cone, Convertible=torus, Van=dodeca, Wagon=icosa,
                  Hatchback=octa, other=tetra
  model altitude  median odometer -- every model orbits clear of its make's
                  surface, and higher-mileage models orbit higher
  model size      volume within the make;  model color  price vs MMR
  Channels        weekly market pulse baked from sale dates (Dec 2014 - Jul
                  2015): every make breathes with its weekly sales volume
                  (scale) and bobs above/below the ring by how far that week's
                  median deal ran over/under book value (translate_z)

Scene 2 -- Depreciation_Grid/  (node + tag)
-------------------------------------------
A make x model-year bar field over a wire ground grid:

  rows (Y)     top makes, ordered cheap -> luxury away from the viewer
  columns (X)  model year (oldest left)
  bar height   median selling price   -- the depreciation curve in relief
  bar radius   sales volume (sqrt scale)
  bar color    median odometer (dark blue = low miles -> yellow = high miles)

Scene 3 -- Raw_Auction_Field/  (node + tag; ~100k nodes)
---------------------------------------------------------
NO aggregation: a seeded random sample of 20,000 raw sale records, one
5-node glyph per record (100k nodes total -- a deliberate performance
stress test at GlyphViz's practical node budget):

  wire cube (BL0)   the car: exterior-paint color, size = MMR wholesale
                    value (sqrt-normalized), Cube topology
  interior solid    body-class geometry (sedan=sphere, SUV=cube, ...) at the
                    cube's center, colored the interior color
  +Z facet glyph    octa wire, size + color = auction condition grade (1-49)
  +X facet glyph    dodeca wire, color = this sale's % vs MMR (blue under /
                    red over book)
  +Y facet glyph    transmission: gold tetra wire = manual, dim sphere wire
                    = automatic/unlisted

Spatial distribution (raw values, only normalized to world units):
  X  sale timestamp (2 units/day; simultaneous sales fan out +0.03/car so
     same-second auction batches don't stack)
  Y  model year (8 units/year)
  Z  odometer (0..120 units at 300k miles)

Every car carries a tag with the full raw record (year make model trim,
condition, miles, price vs MMR, colors, state, sale date).

Output (subfolder per scene because GlyphViz auto-discovers channel files as
"the single ch-map/ch-tracks pair sitting next to the node CSV"):

  Market_Galaxy/VehicleGalaxy_gv_node.csv        + _gv_tag.csv
  Market_Galaxy/VehicleGalaxy_gv_ch-map.csv      + _gv_ch-tracks.csv
  Depreciation_Grid/DepreciationGrid_gv_node.csv + _gv_tag.csv
  Raw_Auction_Field/RawAuctionField_gv_node.csv  + _gv_tag.csv

Usage
-----
  python generate_vehicle_sales_example.py
  python generate_vehicle_sales_example.py --input path\to\car_prices.csv ^
      --output-dir out --top-makes 24 --models-per-make 12

Load in GlyphViz: File > Open Node CSV -> either scene's *_gv_node.csv (tags
load automatically; the galaxy's Channels files are picked up from its
folder -- just start Channels playback).
"""

import argparse
import csv
import math
from pathlib import Path

import numpy as np
import pandas as pd

# Geometry / topology ids (glyphviz_core.geometry_data / topology)
GEO_CUBE_WIRE, GEO_CUBE, GEO_SPHERE_WIRE, GEO_SPHERE, GEO_CONE = 0, 1, 2, 3, 5
GEO_TORUS_WIRE, GEO_TORUS, GEO_DODECA_WIRE, GEO_DODECA = 6, 7, 8, 9
GEO_OCTA_WIRE, GEO_OCTA, GEO_TETRA_WIRE, GEO_TETRA = 10, 11, 12, 13
GEO_ICOSA, GEO_CYLINDER, GEO_GRID_WIRE, GEO_POINT = 15, 19, 20, 22
TOPO_NONE, TOPO_CUBE, TOPO_SPHERE, TOPO_TORUS = 0, 1, 2, 3

BODY_GEOMETRY = {
    "Sedan": GEO_SPHERE, "SUV": GEO_CUBE, "Truck": GEO_CYLINDER,
    "Coupe": GEO_CONE, "Convertible": GEO_TORUS, "Van": GEO_DODECA,
    "Wagon": GEO_ICOSA, "Hatchback": GEO_OCTA, "Other": GEO_TETRA,
}

# --- Market Galaxy proportions (tuned for the base_scale=1.0 default) ---
# The renderer floors every node's rendered scale at max(scale * base_scale,
# 0.2) per axis (scene.node_world_matrix), and that floor multiplies through
# the parent basis. So the ring radius must NOT be encoded as a huge parent
# scale with tiny child scales (a 26-scale root would floor its 0.04-scale
# children up to 5-unit monsters). Instead the root anchor keeps scale 1,
# makes are placed at explicit Cartesian ring positions with absolute scales,
# the wire torus is purely decorative, and every raw scale stays >= 0.2.
RING_GLYPH_SCALE = 24.0      # decorative wire torus size
RING_TUBE_RATIO = 0.012      # hairline tube (minor radius 0.29) threaded through
                             # the makes -- any thicker and the wireframe reads
                             # as a braided cable that competes with the data
RING_RADIUS = RING_GLYPH_SCALE * (1.0 - RING_TUBE_RATIO)   # tube centerline = 23.3
                             # world; chord between 24 makes ~6.1
RING_SPIN = 0.03             # rotate_rate_z deg/cycle: full lap in ~5.5 min at 30fps
MAKE_SCALE_MIN, MAKE_SCALE_MAX = 0.7, 1.2       # absolute world radius (beads on wire)
MODEL_SCALE_MIN, MODEL_SCALE_MAX = 0.25, 0.50   # x make scale (raw stays >= 0.2)
# Sphere-topology altitude is in units of the parent's radius (surface = 0).
# The fleet is dominated by low-mileage off-lease cars, so a raw odometer
# mapping would leave model bodies straddling the solid make sphere; the
# floor keeps even a zero-mile model orbiting fully clear of the surface
# (min center distance 1.65 x parent radius > 1 + max model radius 0.5),
# and miles still read as height above it.
ODOMETER_ALT_MIN = 0.65      # altitude floor (clears the surface by > model radius)
ODOMETER_ALT_SPAN = 0.65     # additional altitude at 150k+ median miles
# MMR *is* the market median, so median %-vs-book deltas are tiny but
# systematic: the top-24 makes span just -0.9%..+0.3% (Mercedes resells under
# book, Honda over). Clips are calibrated to saturate at that real spread.
MAKE_DELTA_CLIP = 1.0        # +/-% vs MMR that saturates the make color ramp
MODEL_DELTA_CLIP = 5.0       # models swing wider (5th..95th pct ~ -8%..+3.5%)

# --- Channels (weekly market pulse) ---
FRAMES_PER_WEEK = 12         # 30 weeks -> ~360 frames = 12 s loop at 30 fps
PULSE_FLOOR, PULSE_GAIN = 0.70, 0.50   # scale = base * (floor + gain * vol/peak);
                                       # 1.2x ceiling keeps pulsing neighbors apart
BOB_RANGE = 2.0              # world-Z bob (makes sit in the anchor's Cartesian
                             # space) at the weekly-delta clip
BOB_DELTA_CLIP = 2.5         # +/-% weekly median vs MMR at full bob

# --- Raw Auction Field (scene 3: one 5-node glyph per raw sale record) ---
RAW_ROWS_DEFAULT = 20_000    # x 5 nodes/record + 4 axis anchors ~= 100k nodes
CAR_X_PER_DAY = 2.0          # sale-timestamp axis
CAR_SAME_TIME_EPS = 0.03     # incremental X fan-out for identical timestamps
CAR_Y_PER_YEAR = 8.0         # model-year axis
CAR_Z_SPAN, CAR_ODO_CLIP = 120.0, 300_000.0   # odometer axis
CAR_SCALE_MIN, CAR_SCALE_MAX = 0.35, 1.2      # cube size by sqrt(MMR / p99)
CUBE_HALF_EXTENT = 1.0 / math.sqrt(3.0)       # cube verts sit on the unit sphere
# Cube topology places children at (base_radius + tz) along the facet normal;
# this tz pulls a child's center back onto the rendered face plane.
FACE_MOUNT_TZ = -(1.0 - CUBE_HALF_EXTENT)
INTERIOR_SCALE = 0.45        # solid body-class glyph inside the wire cube
COND_SCALE_MIN, COND_SCALE_MAX = 0.2, 0.55    # +Z facet glyph over condition 1..49
DEAL_SCALE, TRANS_SCALE = 0.35, 0.3           # +X / +Y facet glyphs

# Exterior/interior paint names -> RGB tuned for the black viewport ("black"
# cars render dark gray, not invisible). '�' is the dataset's mojibake
# for "unknown".
PAINT_RGB = {
    "black": (75, 75, 80), "white": (240, 240, 240), "silver": (200, 205, 210),
    "gray": (140, 140, 145), "blue": (70, 110, 230), "red": (220, 50, 45),
    "green": (60, 160, 75), "gold": (205, 170, 80), "beige": (225, 205, 170),
    "burgundy": (130, 35, 55), "brown": (125, 85, 55), "orange": (240, 130, 40),
    "purple": (140, 80, 200), "off-white": (235, 230, 215),
    "yellow": (240, 220, 60), "charcoal": (100, 100, 105),
    "turquoise": (70, 200, 200), "pink": (240, 140, 180), "lime": (170, 230, 60),
    "tan": (210, 180, 140),
}
PAINT_FALLBACK = (110, 110, 115)

# --- Depreciation Grid proportions ---
YEAR_SPACING, MAKE_SPACING = 6.0, 8.0
BAR_HEIGHT_PER_DOLLAR = 1.0 / 1500.0   # $30k median -> 20-unit bar
BAR_RADIUS_MIN, BAR_RADIUS_MAX = 0.7, 2.2
ODOMETER_COLOR_CLIP = 150_000.0

NODE_FIELDS = [
    "id", "type", "parent_id", "branch_level",
    "translate_x", "translate_y", "translate_z",
    "rotate_x", "rotate_y", "rotate_z",
    "scale_x", "scale_y", "scale_z",
    "color_r", "color_g", "color_b", "color_a",
    "geometry", "hide", "topo", "ratio", "rotate_rate_z", "ch_input_id",
]
TAG_FIELDS = ["id", "table_id", "record_id", "title"]


# ===========================================================================
# Loading and cleaning
# ===========================================================================

def classify_body(body: str) -> str:
    b = str(body).casefold()
    if "suv" in b:
        return "SUV"
    if "sedan" in b:
        return "Sedan"
    if "cab" in b or "pickup" in b:
        return "Truck"
    if "coupe" in b or "koup" in b:
        return "Coupe"
    if "convertible" in b:
        return "Convertible"
    if "van" in b:
        return "Van"
    if "wagon" in b:
        return "Wagon"
    if "hatchback" in b:
        return "Hatchback"
    return "Other"


def canonical_display(series: pd.Series, keys: pd.Series) -> dict[str, str]:
    """Most-frequent original spelling per canonical key ('bmw' -> 'BMW')."""
    return series.groupby(keys).agg(lambda s: s.mode().iloc[0]).to_dict()


def load_and_clean(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, on_bad_lines="skip")
    df = df.dropna(subset=["make", "model", "sellingprice", "mmr"])
    df = df[(df["sellingprice"] >= 500) & (df["mmr"] >= 500)].copy()

    # Canonical keys fold case/punctuation variants ("Land Rover"/"landrover")
    df["make_key"] = df["make"].str.casefold().str.replace(r"[^a-z0-9]", "", regex=True)
    df["model_key"] = df["model"].str.casefold().str.replace(r"[^a-z0-9]", "", regex=True)
    df["body_class"] = df["body"].map(classify_body, na_action="ignore").fillna("Other")
    df["delta_pct"] = (df["sellingprice"] - df["mmr"]) / df["mmr"] * 100.0

    # "Tue Dec 16 2014 12:30:00 GMT-0800 (PST)" -> chars 4:15 = "Dec 16 2014"
    df["sale_date"] = pd.to_datetime(df["saledate"].str.slice(4, 15),
                                     format="%b %d %Y", errors="coerce")
    return df


# ===========================================================================
# Color ramps (255-based RGB for the black GlyphViz viewport)
# ===========================================================================

def _lerp(c0, c1, t):
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c0, c1))


def diverging_color(value: float, clip: float) -> tuple[int, int, int]:
    """Blue (under book) -> near-white (at book) -> red (over book)."""
    t = max(-1.0, min(1.0, value / clip))
    if t < 0:
        return _lerp((235, 235, 235), (60, 110, 255), -t)
    return _lerp((235, 235, 235), (255, 80, 40), t)


def sequential_color(t: float) -> tuple[int, int, int]:
    """Odometer ramp: deep blue -> teal -> yellow."""
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return _lerp((25, 35, 90), (30, 160, 170), t * 2)
    return _lerp((30, 160, 170), (250, 220, 60), (t - 0.5) * 2)


# ===========================================================================
# Node/tag row helpers
# ===========================================================================

def node_row(node_id, parent_id, branch_level, tx, ty, tz, sx, sy, sz,
             color, geometry, topo, *, alpha=255, hide=0, ratio=0.1,
             rotate_rate_z=0.0, ch_input_id=0):
    return {
        "id": node_id, "type": 5, "parent_id": parent_id,
        "branch_level": branch_level,
        "translate_x": round(tx, 4), "translate_y": round(ty, 4),
        "translate_z": round(tz, 4),
        "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
        "scale_x": round(sx, 4), "scale_y": round(sy, 4), "scale_z": round(sz, 4),
        "color_r": color[0], "color_g": color[1], "color_b": color[2],
        "color_a": alpha,
        "geometry": geometry, "hide": hide, "topo": topo, "ratio": ratio,
        "rotate_rate_z": rotate_rate_z, "ch_input_id": ch_input_id,
    }


def fmt_money(v: float) -> str:
    return f"${v / 1000:.1f}k" if v >= 1000 else f"${v:.0f}"


def fmt_miles(v: float) -> str:
    return f"{v / 1000:.0f}k mi"


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"  {path.name}: {len(rows)} rows")


# ===========================================================================
# Scene 1: Market Galaxy
# ===========================================================================

def fibonacci_lat_lon(i: int, n: int) -> tuple[float, float]:
    """Even sphere coverage: latitude from equal-area bands, golden-angle lon."""
    lat = math.degrees(math.asin(2.0 * (i + 0.5) / n - 1.0))
    lon = (i * 137.50776) % 360.0
    return lon, lat


def build_market_galaxy(df: pd.DataFrame, out_dir: Path, top_makes: int,
                        models_per_make: int):
    out_dir.mkdir(parents=True, exist_ok=True)
    make_disp = canonical_display(df["make"], df["make_key"])
    model_disp = canonical_display(df["model"], df["model_key"])

    makes = (df.groupby("make_key")
               .agg(count=("sellingprice", "size"),
                    med_price=("sellingprice", "median"),
                    med_delta=("delta_pct", "median"),
                    med_odo=("odometer", "median"))
               .nlargest(top_makes, "count")
               .sort_values("med_price"))        # ring order: cheap -> luxury

    nodes, tags = [], []
    dated = df[df["sale_date"].notna()]
    root_tag = (f"Used-vehicle auction market | {len(df) / 1000:.0f}k sales "
                f"{dated['sale_date'].min():%b %Y} - {dated['sale_date'].max():%b %Y} | "
                f"ring runs cheap -> luxury | blue under book / red over book")
    # Hidden anchor at scale 1: spins the whole galaxy, and its Cartesian
    # (topo None) space is what make positions and the bob channel live in.
    nodes.append(node_row(1, 0, 0, 0, 0, 0, 1.0, 1.0, 1.0, (0, 0, 0),
                          GEO_POINT, TOPO_NONE, hide=1,
                          rotate_rate_z=RING_SPIN))
    tags.append({"id": 0, "table_id": 0, "record_id": 1, "title": root_tag})
    # Decorative thin wire torus threaded through the make beads
    nodes.append(node_row(2, 1, 1, 0, 0, 0, RING_GLYPH_SCALE, RING_GLYPH_SCALE,
                          RING_GLYPH_SCALE, (50, 55, 70), GEO_TORUS_WIRE,
                          TOPO_NONE, alpha=110, ratio=RING_TUBE_RATIO))

    next_id = 3
    vol_max = makes["count"].max()
    for ring_idx, (mkey, m) in enumerate(makes.iterrows()):
        make_id = next_id
        next_id += 1
        angle = math.radians(ring_idx * 360.0 / len(makes))
        mscale = MAKE_SCALE_MIN + (MAKE_SCALE_MAX - MAKE_SCALE_MIN) * math.sqrt(
            m["count"] / vol_max)
        nodes.append(node_row(
            make_id, 1, 1,
            RING_RADIUS * math.cos(angle), RING_RADIUS * math.sin(angle), 0.0,
            mscale, mscale, mscale,
            diverging_color(m["med_delta"], MAKE_DELTA_CLIP),
            GEO_SPHERE, TOPO_SPHERE, ch_input_id=ring_idx + 1))
        tags.append({
            "id": len(tags), "table_id": 0, "record_id": make_id,
            "title": (f"{make_disp[mkey]} | {m['count']:.0f} sold | "
                      f"med {fmt_money(m['med_price'])} | "
                      f"{m['med_delta']:+.1f}% vs MMR | {fmt_miles(m['med_odo'])}")})

        models = (df[df["make_key"] == mkey]
                  .groupby("model_key")
                  .agg(count=("sellingprice", "size"),
                       med_price=("sellingprice", "median"),
                       med_delta=("delta_pct", "median"),
                       med_odo=("odometer", "median"),
                       body=("body_class", lambda s: s.mode().iloc[0]))
                  .query("count >= 25")
                  .nlargest(models_per_make, "count"))
        if models.empty:
            continue
        mvol_max = models["count"].max()
        for j, (dkey, d) in enumerate(models.iterrows()):
            lon, lat = fibonacci_lat_lon(j, len(models))
            odo = 0.0 if pd.isna(d["med_odo"]) else d["med_odo"]
            alt = ODOMETER_ALT_MIN + ODOMETER_ALT_SPAN * min(odo / 150_000.0, 1.0)
            cscale = MODEL_SCALE_MIN + (MODEL_SCALE_MAX - MODEL_SCALE_MIN) * math.sqrt(
                d["count"] / mvol_max)
            nodes.append(node_row(
                next_id, make_id, 2, lon, lat, alt, cscale, cscale, cscale,
                diverging_color(d["med_delta"], MODEL_DELTA_CLIP),
                BODY_GEOMETRY[d["body"]], TOPO_NONE))
            tags.append({
                "id": len(tags), "table_id": 0, "record_id": next_id,
                "title": (f"{make_disp[mkey]} {model_disp[dkey]} [{d['body']}] | "
                          f"{d['count']:.0f} sold | med {fmt_money(d['med_price'])} | "
                          f"{d['med_delta']:+.1f}% vs MMR | {fmt_miles(odo)}")})
            next_id += 1

    write_csv(out_dir / "VehicleGalaxy_gv_node.csv", NODE_FIELDS, nodes)
    write_csv(out_dir / "VehicleGalaxy_gv_tag.csv", TAG_FIELDS, tags)
    build_market_pulse_channels(df, out_dir, makes)


def build_market_pulse_channels(df: pd.DataFrame, out_dir: Path,
                                makes: pd.DataFrame):
    """Weekly volume/delta per make -> per-frame scale + elevation tracks.

    Two tracks per make: track 2i drives scale_x/y/z (volume pulse), track
    2i+1 drives translate_z (elevation off the ring = weekly % vs book value).
    """
    dated = df[df["sale_date"].notna() & df["make_key"].isin(makes.index)].copy()
    week = ((dated["sale_date"] - dated["sale_date"].min()).dt.days // 7)
    dated["week"] = week

    # Keep the contiguous run of weeks with real market activity (the data
    # trails off into a few straggler sales at the end).
    totals = dated.groupby("week").size()
    active = totals[totals >= 200].index
    lo, hi = int(active.min()), int(active.max())
    dated = dated[(dated["week"] >= lo) & (dated["week"] <= hi)]
    dated["week"] -= lo
    n_weeks = hi - lo + 1

    vol = (dated.groupby(["make_key", "week"]).size()
                .unstack(fill_value=0)
                .reindex(index=makes.index, columns=range(n_weeks), fill_value=0))
    delta = (dated.groupby(["make_key", "week"])["delta_pct"].median()
                  .unstack()
                  .reindex(index=makes.index, columns=range(n_weeks))
                  .interpolate(axis=1, limit_direction="both")
                  .fillna(0.0))

    vol_max = makes["count"].max()
    n_frames = n_weeks * FRAMES_PER_WEEK
    frame_x = np.arange(n_frames) / FRAMES_PER_WEEK
    # Sample points 0..n_weeks with week 0 repeated at the end -> seamless loop
    week_x = np.arange(n_weeks + 1, dtype=float)

    ch_map_rows, columns = [], {}
    for i, (mkey, m) in enumerate(makes.iterrows()):
        base = MAKE_SCALE_MIN + (MAKE_SCALE_MAX - MAKE_SCALE_MIN) * math.sqrt(
            m["count"] / vol_max)
        v = vol.loc[mkey].to_numpy(dtype=float)
        pulse = base * (PULSE_FLOOR + PULSE_GAIN * v / max(v.max(), 1.0))
        d = np.clip(delta.loc[mkey].to_numpy(dtype=float),
                    -BOB_DELTA_CLIP, BOB_DELTA_CLIP)
        bob = BOB_RANGE * d / BOB_DELTA_CLIP

        columns[2 * i] = np.interp(frame_x, week_x, np.append(pulse, pulse[0]))
        columns[2 * i + 1] = np.interp(frame_x, week_x, np.append(bob, bob[0]))
        for attr, track in (("scale_x", 2 * i), ("scale_y", 2 * i),
                            ("scale_z", 2 * i), ("translate_z", 2 * i + 1)):
            ch_map_rows.append({
                "id": len(ch_map_rows), "channel_id": i + 1, "track_id": track,
                "attribute": attr, "track_table_id": 0, "ch_map_table_id": 0,
                "record_id": 0})

    write_csv(out_dir / "VehicleGalaxy_gv_ch-map.csv",
              ["id", "channel_id", "track_id", "attribute",
               "track_table_id", "ch_map_table_id", "record_id"], ch_map_rows)

    tracks_path = out_dir / "VehicleGalaxy_gv_ch-tracks.csv"
    track_ids = sorted(columns)
    with open(tracks_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cyclecount"] + [f"ch{t}" for t in track_ids])
        for fr in range(n_frames):
            w.writerow([fr] + [round(float(columns[t][fr]), 4) for t in track_ids])
    print(f"  {tracks_path.name}: {n_frames} frames x {len(track_ids)} tracks "
          f"({n_weeks} market weeks, {n_frames / 30:.0f}s loop)")


# ===========================================================================
# Scene 2: Depreciation Grid
# ===========================================================================

def build_depreciation_grid(df: pd.DataFrame, out_dir: Path, grid_makes: int,
                            year_min: int, min_cell: int):
    out_dir.mkdir(parents=True, exist_ok=True)
    make_disp = canonical_display(df["make"], df["make_key"])

    sub = df[df["year"] >= year_min]
    top = (sub.groupby("make_key")["sellingprice"]
              .agg(count="size", med_price="median")
              .nlargest(grid_makes, "count")
              .sort_values("med_price"))         # rows: cheap near -> luxury far
    years = list(range(year_min, int(sub["year"].max()) + 1))

    cells = (sub[sub["make_key"].isin(top.index)]
             .groupby(["make_key", "year"])
             .agg(count=("sellingprice", "size"),
                  med_price=("sellingprice", "median"),
                  med_delta=("delta_pct", "median"),
                  med_odo=("odometer", "median"))
             .query(f"count >= {min_cell}"))

    x0 = -(len(years) - 1) * YEAR_SPACING / 2.0
    y0 = -(len(top) - 1) * MAKE_SPACING / 2.0
    half_x = (len(years) + 1) * YEAR_SPACING / 2.0
    half_y = (len(top) + 1) * MAKE_SPACING / 2.0

    nodes = [node_row(1, 0, 0, 0, 0, 0, 0.1, 0.1, 0.1, (0, 0, 0),
                      GEO_POINT, TOPO_NONE, hide=1)]
    tags = [{"id": 0, "table_id": 0, "record_id": 1,
             "title": ("Depreciation grid | X: model year | Y: make (cheap -> "
                       "luxury) | height: median price | color: median miles")}]
    # Ground grid (own scale, so bars stay children of the unit-scale root)
    nodes.append(node_row(2, 1, 1, 0, 0, 0, half_x * math.sqrt(2),
                          half_y * math.sqrt(2), 1.0, (55, 60, 75),
                          GEO_GRID_WIRE, TOPO_NONE, alpha=140))

    next_id = 3
    count_max = cells["count"].max()
    for row_idx, (mkey, mrow) in enumerate(top.iterrows()):
        y = y0 + row_idx * MAKE_SPACING
        # Row label anchor at the left edge
        nodes.append(node_row(next_id, 1, 1, x0 - YEAR_SPACING * 1.5, y, 0.5,
                              0.4, 0.4, 0.4, (170, 170, 180), GEO_SPHERE,
                              TOPO_NONE))
        tags.append({"id": len(tags), "table_id": 0, "record_id": next_id,
                     "title": f"{make_disp[mkey]} (med {fmt_money(mrow['med_price'])})"})
        next_id += 1
        for col_idx, yr in enumerate(years):
            if (mkey, yr) not in cells.index:
                continue
            c = cells.loc[(mkey, yr)]
            h = c["med_price"] * BAR_HEIGHT_PER_DOLLAR
            r = BAR_RADIUS_MIN + (BAR_RADIUS_MAX - BAR_RADIUS_MIN) * math.sqrt(
                c["count"] / count_max)
            odo = 0.0 if pd.isna(c["med_odo"]) else c["med_odo"]
            nodes.append(node_row(
                next_id, 1, 1, x0 + col_idx * YEAR_SPACING, y, h / 2.0,
                r, r, h / 2.0,          # cylinder geometry spans local z -1..+1
                sequential_color(odo / ODOMETER_COLOR_CLIP),
                GEO_CYLINDER, TOPO_NONE))
            tags.append({
                "id": len(tags), "table_id": 0, "record_id": next_id,
                "title": (f"{make_disp[mkey]} {yr} | {c['count']:.0f} sold | "
                          f"med {fmt_money(c['med_price'])} | "
                          f"{c['med_delta']:+.1f}% vs MMR | {fmt_miles(odo)}")})
            next_id += 1

    for col_idx, yr in enumerate(years):    # Year labels along the near edge
        nodes.append(node_row(next_id, 1, 1, x0 + col_idx * YEAR_SPACING,
                              y0 - MAKE_SPACING, 0.5, 0.4, 0.4, 0.4,
                              (170, 170, 180), GEO_SPHERE, TOPO_NONE))
        tags.append({"id": len(tags), "table_id": 0, "record_id": next_id,
                     "title": str(yr)})
        next_id += 1

    write_csv(out_dir / "DepreciationGrid_gv_node.csv", NODE_FIELDS, nodes)
    write_csv(out_dir / "DepreciationGrid_gv_tag.csv", TAG_FIELDS, tags)


# ===========================================================================
# Scene 3: Raw Auction Field (one glyph per raw sale record, ~100k nodes)
# ===========================================================================

RAW_NODE_FIELDS = NODE_FIELDS + ["facet"]   # facet: 1-indexed Cube face selector


def build_raw_auction_field(df: pd.DataFrame, out_dir: Path, n_rows: int,
                            seed: int):
    out_dir.mkdir(parents=True, exist_ok=True)
    complete = df.dropna(subset=["year", "condition", "odometer", "color",
                                 "interior", "sale_date"])
    # ~200 records are timestamped Jan/Feb 2014, ten months before the real
    # auction window (Dec 2014 - Jul 2015); they'd stretch the time axis 2.5x
    # for nothing. (The May gap inside the window is real market structure
    # and stays.)
    window_start = complete["sale_date"].max() - pd.Timedelta(days=270)
    stragglers = int((complete["sale_date"] < window_start).sum())
    complete = complete[complete["sale_date"] >= window_start]
    print(f"  dropped {stragglers} timestamp stragglers "
          f"(before {window_start:%b %Y})")
    sample = (complete.sample(n=min(n_rows, len(complete)), random_state=seed)
                      .sort_values("saledate", kind="stable"))
    print(f"  sampled {len(sample)} of {len(complete)} complete raw records "
          f"(seed {seed})")

    day = (sample["sale_date"] - sample["sale_date"].min()).dt.days
    # Same-second auction batches fan out along +X instead of stacking
    dup_rank = sample.groupby("saledate").cumcount()
    xs = (day * CAR_X_PER_DAY + dup_rank * CAR_SAME_TIME_EPS).to_numpy()
    ys = ((sample["year"] - sample["year"].min()) * CAR_Y_PER_YEAR).to_numpy()
    zs = (np.minimum(sample["odometer"].to_numpy(), CAR_ODO_CLIP)
          / CAR_ODO_CLIP * CAR_Z_SPAN)
    mmr_p99 = float(sample["mmr"].quantile(0.99))
    car_scales = CAR_SCALE_MIN + (CAR_SCALE_MAX - CAR_SCALE_MIN) * np.sqrt(
        np.minimum(sample["mmr"].to_numpy(), mmr_p99) / mmr_p99)

    def paint(name) -> tuple[int, int, int]:
        return PAINT_RGB.get(str(name).strip().casefold(), PAINT_FALLBACK)

    nodes, tags = [], []

    def add_node(row_dict, facet=1):
        row_dict["facet"] = facet
        nodes.append(row_dict)

    # Axis anchors (tagged wire spheres at the three axis extremes + origin)
    year_min = int(sample["year"].min())
    for nid, (x, y, z, title) in enumerate([
        (0, 0, 0, (f"RAW AUCTION FIELD | {len(sample)} sale records | "
                   f"X sale date | Y model year (from {year_min}) | Z odometer")),
        (float(xs.max()) + 10, 0, 0, f"Sale date -> {sample['sale_date'].max():%b %Y}"),
        (0, float(ys.max()) + 10, 0, f"Model year -> {int(sample['year'].max())}"),
        (0, 0, CAR_Z_SPAN + 10, f"Odometer -> {CAR_ODO_CLIP / 1000:.0f}k+ mi"),
    ], start=1):
        add_node(node_row(nid, 0, 0, x, y, z, 0.6, 0.6, 0.6, (170, 170, 180),
                          GEO_SPHERE_WIRE, TOPO_NONE))
        tags.append({"id": len(tags), "table_id": 0, "record_id": nid,
                     "title": title})

    next_id = 5
    for i, (_, r) in enumerate(sample.iterrows()):
        s = float(car_scales[i])
        car_id = next_id
        # BL0: the car -- wire cube, exterior paint, sized by MMR
        add_node(node_row(car_id, 0, 0, float(xs[i]), float(ys[i]), float(zs[i]),
                          s, s, s, paint(r["color"]), GEO_CUBE_WIRE, TOPO_CUBE))
        trim = "" if pd.isna(r["trim"]) else f" {r['trim']}"
        tags.append({
            "id": len(tags), "table_id": 0, "record_id": car_id,
            "title": (f"{r['year']:.0f} {r['make']} {r['model']}{trim} | "
                      f"cond {r['condition']:.0f}/49 | {fmt_miles(r['odometer'])} | "
                      f"sold {fmt_money(r['sellingprice'])} "
                      f"(MMR {fmt_money(r['mmr'])}) | "
                      f"{r['color']}/{r['interior']} | {r['state']} | "
                      f"{r['sale_date']:%m/%d/%Y}")})
        # Interior: solid body-class glyph at the cube's center (tz=-1 puts the
        # Cube-topology placement distance at zero)
        add_node(node_row(car_id + 1, car_id, 1, 0.0, 0.0, -1.0,
                          INTERIOR_SCALE, INTERIOR_SCALE, INTERIOR_SCALE,
                          paint(r["interior"]),
                          BODY_GEOMETRY[r["body_class"]], TOPO_NONE))
        # +Z facet: condition grade (size + color)
        cond = float(r["condition"]) / 49.0
        csize = COND_SCALE_MIN + (COND_SCALE_MAX - COND_SCALE_MIN) * cond
        add_node(node_row(car_id + 2, car_id, 1, 0.0, 0.0, FACE_MOUNT_TZ,
                          csize, csize, csize, sequential_color(cond),
                          GEO_OCTA_WIRE, TOPO_NONE), facet=5)
        # +X facet: this sale's % over/under MMR book value
        add_node(node_row(car_id + 3, car_id, 1, 0.0, 0.0, FACE_MOUNT_TZ,
                          DEAL_SCALE, DEAL_SCALE, DEAL_SCALE,
                          diverging_color(float(r["delta_pct"]), MODEL_DELTA_CLIP),
                          GEO_DODECA_WIRE, TOPO_NONE), facet=1)
        # +Y facet: transmission (manual is rare -- make it pop)
        manual = str(r["transmission"]).casefold() == "manual"
        add_node(node_row(car_id + 4, car_id, 1, 0.0, 0.0, FACE_MOUNT_TZ,
                          TRANS_SCALE, TRANS_SCALE, TRANS_SCALE,
                          (240, 180, 80) if manual else (120, 130, 160),
                          GEO_TETRA_WIRE if manual else GEO_SPHERE_WIRE,
                          TOPO_NONE), facet=3)
        next_id += 5

    write_csv(out_dir / "RawAuctionField_gv_node.csv", RAW_NODE_FIELDS, nodes)
    write_csv(out_dir / "RawAuctionField_gv_tag.csv", TAG_FIELDS, tags)


# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path,
                        default=Path(r"C:\Jeff\python\vehicle_sales_data\car_prices.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent)
    parser.add_argument("--top-makes", type=int, default=24,
                        help="makes on the galaxy ring")
    parser.add_argument("--models-per-make", type=int, default=12)
    parser.add_argument("--grid-makes", type=int, default=20,
                        help="make rows in the depreciation grid")
    parser.add_argument("--year-min", type=int, default=1998)
    parser.add_argument("--min-cell", type=int, default=30,
                        help="min sales for a make x year bar")
    parser.add_argument("--raw-rows", type=int, default=RAW_ROWS_DEFAULT,
                        help="raw sale records in the Auction Field (5 nodes each)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    print(f"Reading {args.input} ...")
    df = load_and_clean(args.input)
    print(f"  {len(df)} usable sales, {df['make_key'].nunique()} makes, "
          f"{df['model_key'].nunique()} models")

    print("\nScene 1: Market Galaxy")
    build_market_galaxy(df, args.output_dir / "Market_Galaxy",
                        args.top_makes, args.models_per_make)

    print("\nScene 2: Depreciation Grid")
    build_depreciation_grid(df, args.output_dir / "Depreciation_Grid",
                            args.grid_makes, args.year_min, args.min_cell)

    print("\nScene 3: Raw Auction Field")
    build_raw_auction_field(df, args.output_dir / "Raw_Auction_Field",
                            args.raw_rows, args.seed)

    print("\nDone. In GlyphViz: File > Open Node CSV -> "
          "Market_Galaxy/VehicleGalaxy_gv_node.csv (start Channels playback "
          "for the weekly market pulse), "
          "Depreciation_Grid/DepreciationGrid_gv_node.csv, or "
          "Raw_Auction_Field/RawAuctionField_gv_node.csv (~100k nodes -- "
          "performance stress test).")


if __name__ == "__main__":
    main()
