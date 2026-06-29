#!/usr/bin/env python3
"""
generate_district_heatmap.py
==============================
"The forest, not the trees" (#3 in this series, after CalStateTesting_Example
and SES_Achievement_Gap_Terrain_Example): every San Diego Unified school as
one flat, color-animated marker laid directly over the district's real
satellite image, color-coded by CST proficiency and animated across all 10
years (2003-2012) via GlyphViz's Channels (ch-map/ch-tracks) system -- the
first real-data generator in this repo to actually drive Channels end-to-end
(it's a still-pending high-priority feature per the project's own roadmap).

Why a flat animated heatmap, not another terrain
--------------------------------------------------
SES_Achievement_Gap_Terrain_Example already shows grade x year as a 3-D
surface; this is deliberately its 2-D geographic companion -- "where" rather
than "which grade" -- one node per *school*, fixed at its real (lat, lon),
with color (not height) carrying the time-varying signal. Geometry is
GEO_CIRCLE (24, glyphviz_core/geometry_data.py's flat, world-scaled marker
shape) rather than GEO_POINT, since a heatmap dot should visually scale with
the map the way the satellite image does, not stay a constant screen size.

Geo-projection: must match CalStateTesting_Example/generate_calstate_testing.py
exactly (same MAP_MIN/MAX_LAT/LON, X_SCALE, Y_SCALE, clamp_to_county) so
school markers land in the same coordinate space as the satellite image --
both are duplicated here (not imported) for a self-contained load, the same
choice Multi_Hike_Race_Example made when reusing Surface_Example's terrain
math and DEM/aerial JPGs.

Color: a simple traffic-light gradient (red=low proficiency, yellow=mid,
green=high), hue interpolated linearly by `percentaboveproficient` -- not
the discrete 5-band scheme generate_calstate_testing.py uses for individual
test glyphs, since a smooth gradient reads better at this map-overview scale.

Animation: glyphviz_core/channel_engine.py's `apply_frame()` does no
interpolation -- it reads the exact row at that frame index. So the smooth
year-to-year color fade seen in the app is precomputed here at generation
time (np.interp on each school's own real per-year proficiency values onto
a dense common frame grid, FRAMES_PER_YEAR apart) and baked directly into
ch-tracks.csv, the same approach Multi_Hike_Race_Example used for its GPS
tracks. Schools missing data in some years hold flat at their nearest known
year (np.interp's default extrapolation) rather than going blank.

Known data gap: subgroup=1 ("All Students") before 2010
-----------------------------------------------------------
Confirmed against the live database: `percentaboveproficient` for subgroup=1
("All Students") is a literal 0.0 for every school and grade, 2003-2009 --
`studentstested` is real/nonzero throughout, but that one derived field was
apparently never computed for this specific subgroup before 2010 (other
subgroup codes, e.g. 31/111 as used by SES_Achievement_Gap_Terrain_Example,
don't have this gap -- confirmed real, smoothly-varying values across the
full decade). Both fetchers below treat a weighted-sum of exactly 0 (with a
nonzero student count) as "not actually computed" rather than a real 0%
score, so np.interp holds flat at the nearest real year (2010 here) instead
of animating through 7 years of false "0% proficient" red.

That fix alone still left a flat 2003-2009 in the *default* run, though --
subgroup=1's gap isn't partial, it's 100% of schools, every one of those
years. There's no real data to recover for that exact subgroup. The actual
fix is the default: --subgroup-codes now defaults to [3, 4] (Males +
Females summed together) instead of [1] -- confirmed against the live
database that 3+4's combined population count matches subgroup=1's
reported student count almost exactly (e.g. 2003: 248,871 vs 248,420), but
3 and 4 individually have real, smoothly-varying percentaboveproficient
across the full decade. So "Males+Females combined" is a faithful stand-in
for "All Students" that doesn't inherit the gap.

Two interchangeable data sources (--source csv|mysql), same generation logic
-----------------------------------------------------------------------------
Same convention as the other two examples. `--source mysql` runs, per
(year, school), the weighted-average-proficiency aggregate across
--min-grade..--max-grade for one or more subgroup codes summed together
(default 3 4 = Males+Females, see above); `--source csv` runs the pandas
equivalent against sdusd<year>.csv files. --subgroup-codes generalizes this
to any other subgroup's own geographic trend (e.g. just 31 = Economically
Disadvantaged) instead of the district-wide default.

Output files (written to --output-dir, default: this script's directory)
--------------------------------------------------------------------------
  {PREFIX}_gv_node.csv       ground-plane satellite image + one GEO_CIRCLE
                             marker per school (color animated via Channels)
  {PREFIX}_gv_tag.csv        one label per school: name + first/last-year
                             proficiency
  {PREFIX}_gv_ch-map.csv     channel -> color_r/g/b bindings per school
  {PREFIX}_gv_ch-tracks.csv  dense per-frame interpolated color tracks

Usage
-----
  python generate_district_heatmap.py --source mysql
  python generate_district_heatmap.py --source mysql --subgroup-codes 31 \
      --subgroup-label "Economically Disadvantaged"

Load in GlyphViz: File > Open Node CSV -> {PREFIX}_gv_node.csv, then press
Play (Channels) to watch the decade unfold.
"""

import argparse
import csv
from pathlib import Path

import numpy as np
import pandas as pd

OUTPUT_DIR = Path(__file__).parent
DEFAULT_DATA_DIR = Path(r"C:\Jeff\python\glyphviz\glyphviz_examples\CalStateTesting_Example")
PREFIX = "District_Heatmap_Example"

TOPO_PLANE = 8       # glyphviz_core/topology.py
GEO_GRID = 21         # glyphviz_core/geometry_data.py -- ground-plane satellite image
GEO_CIRCLE = 24       # flat, world-scaled marker -- one per school

# Geo-registration bounding box (San Diego County) -- must match
# CalStateTesting_Example/generate_calstate_testing.py exactly so school
# markers land in the same coordinate space as the (duplicated) satellite image.
MAP_MIN_LAT, MAP_MAX_LAT = 32.547103, 32.972668
MAP_MIN_LON, MAP_MAX_LON = -116.794333, -117.313437
X_SCALE = -360 / (MAP_MAX_LON - MAP_MIN_LON)
Y_SCALE = 360 / (MAP_MAX_LAT - MAP_MIN_LAT)
_LAT_LO, _LAT_HI = min(MAP_MIN_LAT, MAP_MAX_LAT), max(MAP_MIN_LAT, MAP_MAX_LAT)
_LON_LO, _LON_HI = min(MAP_MIN_LON, MAP_MAX_LON), max(MAP_MIN_LON, MAP_MAX_LON)

# Ground-plane satellite image -- media/map00001.jpg duplicated here (same
# file as CalStateTesting_Example's) for a self-contained load. Position/
# scale hand-tuned by Jeff in the live app against the real school marker
# positions; the same values are used in CalStateTesting_Example's
# ground_plane_node() since both examples share the same geo-projection and
# satellite image. No texture_id animation, so no Channels binding needed
# for this node.
GROUND_SCALE = 84.0
GROUND_TX, GROUND_TY = -11.176, -49.39
GROUND_TEXTURE_ID = 1

MARKER_SCALE = 1.0   # GEO_CIRCLE's native radius is 1.0 at scale=1.0 -- school
                      # nearest-neighbor distances in this projection have a
                      # ~4.6-unit median (and several genuinely co-located
                      # duplicates at ~0), so anything much bigger than this
                      # starts visually merging adjacent schools together
MARKER_Z = 2.0   # small lift above the ground plane to avoid z-fighting

FRAMES_PER_YEAR = 30   # 30fps -> 1 second of animation per year

NODE_FIELDS = [
    "id", "type", "parent_id", "branch_level",
    "translate_x", "translate_y", "translate_z",
    "rotate_x", "rotate_y", "rotate_z",
    "scale_x", "scale_y", "scale_z",
    "color_r", "color_g", "color_b", "color_a",
    "geometry", "hide", "topo", "ratio",
    "texture_id", "ch_input_id",
]


def clamp_to_county(lat, lon):
    """See generate_calstate_testing.py's clamp_to_county() -- same fix,
    same reason (schoollatlng is a shared, multi-project lookup table)."""
    return max(_LAT_LO, min(lat, _LAT_HI)), max(_LON_LO, min(lon, _LON_HI))


def proficiency_to_heat_color(pct):
    """Traffic-light gradient: red (0%) -> yellow (~50%) -> green (100%)."""
    import colorsys
    hue = 0.33 * max(0.0, min(pct, 100.0)) / 100.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 0.9)
    return int(r * 255), int(g * 255), int(b * 255)


def fetch_school_series_mysql(host, user, password, database, start_year, end_year,
                               min_grade, max_grade, testtype, subgroup_codes):
    import pymysql
    conn = pymysql.connect(host=host, user=user, password=password, database=database, connect_timeout=10)
    cur = conn.cursor()

    placeholders = ",".join(["%s"] * len(subgroup_codes))
    series = {}   # school -> {year: pct}
    for year in range(start_year, end_year + 1):
        table = f"sdusd{int(year)}"
        cur.execute(
            f"SELECT school, SUM(studentstested), SUM(studentstested*percentaboveproficient) "
            f"FROM `{table}` WHERE testtype=%s AND subgroup IN ({placeholders}) AND school>1 "
            f"AND grade BETWEEN %s AND %s GROUP BY school",
            (testtype, *subgroup_codes, min_grade, max_grade))
        for school, n, weighted in cur.fetchall():
            n = float(n) if n else 0.0
            weighted = float(weighted) if weighted else 0.0
            # weighted==0 with n>0 means percentaboveproficient was never
            # actually computed for this (year, school, subgroup) -- not a
            # real "0% proficient" score (see module docstring's "Known data
            # gap" section). Treat as no-data so np.interp holds flat at the
            # nearest real year instead of showing a false low score.
            if n > 0 and weighted > 0:
                series.setdefault(int(school), {})[year] = weighted / n

    cur.execute("SELECT schoolcode, latitude, longitude FROM schoollatlng")
    latlng = {int(r[0]): (float(r[1]), float(r[2])) for r in cur.fetchall()}
    cur.execute("SELECT schoolcode, schoolname FROM schoolnames")
    names = {int(r[0]): str(r[1]) for r in cur.fetchall()}

    conn.close()
    return series, latlng, names


def fetch_school_series_csv(data_dir, start_year, end_year, min_grade, max_grade,
                             testtype, subgroup_codes):
    data_dir = Path(data_dir)
    series = {}
    for year in range(start_year, end_year + 1):
        path = data_dir / f"sdusd{year}.csv"
        if not path.exists():
            print(f"  skipping {year}: {path.name} not found")
            continue
        df = pd.read_csv(path)
        scoped = df[(df["testtype"] == testtype) & (df["subgroup"].isin(subgroup_codes))
                     & (df["school"] > 1) & (df["grade"] >= min_grade) & (df["grade"] <= max_grade)]
        for school, sub_df in scoped.groupby("school"):
            n = float(sub_df["studentstested"].sum())
            if n > 0:
                weighted = float((sub_df["studentstested"] * sub_df["percentaboveproficient"]).sum())
                # See the mysql fetcher's comment -- weighted==0 with n>0 means
                # percentaboveproficient was never computed for this cell, not
                # a real zero score.
                if weighted > 0:
                    series.setdefault(int(school), {})[year] = weighted / n

    latlng_df = pd.read_csv(data_dir / "schoollatlng.csv")
    latlng = {int(r.schoolcode): (float(r.latitude), float(r.longitude)) for r in latlng_df.itertuples()}
    names_df = pd.read_csv(data_dir / "schoolnames.csv")
    names = {int(r.schoolcode): str(r.schoolname) for r in names_df.itertuples()}

    return series, latlng, names


def build_arg_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", choices=["csv", "mysql"], default="csv")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR,
                         help=f"(--source csv) directory with sdusd<year>.csv / schoollatlng.csv / schoolnames.csv (default {DEFAULT_DATA_DIR})")
    parser.add_argument("--db-host", default="localhost", help="(--source mysql)")
    parser.add_argument("--db-user", default="root", help="(--source mysql)")
    parser.add_argument("--db-password", default="", help="(--source mysql)")
    parser.add_argument("--db-name", default="calstatetesting_all", help="(--source mysql)")
    parser.add_argument("--start-year", type=int, default=2003)
    parser.add_argument("--end-year", type=int, default=2012)
    parser.add_argument("--min-grade", type=int, default=2)
    parser.add_argument("--max-grade", type=int, default=11)
    parser.add_argument("--testtype", default="C", help="STAR testtype code (default 'C' = CST)")
    parser.add_argument("--subgroup-codes", type=int, nargs="+", default=[3, 4],
                         help="CDE subgroup code(s), summed together (default 3 4 = Males+Females, "
                              "a stand-in for 'All Students' -- see module docstring's 'Known data gap': "
                              "subgroup=1's own percentaboveproficient is a literal 0.0 placeholder "
                              "before 2010, while 3+4's combined population/score matches it almost "
                              "exactly and has real data for the full decade)")
    parser.add_argument("--subgroup-label", default="All Students")
    parser.add_argument("--frames-per-year", type=int, default=FRAMES_PER_YEAR)
    parser.add_argument("--marker-scale", type=float, default=MARKER_SCALE)
    parser.add_argument("--no-ground-image", action="store_true",
                         help="omit the satellite-image ground plane (media/map00001.jpg, texture_id=1)")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--prefix", default=PREFIX)
    return parser


def ground_plane_node(node_id):
    return {
        "id": node_id, "type": 5, "parent_id": 0, "branch_level": 0,
        "translate_x": GROUND_TX, "translate_y": GROUND_TY, "translate_z": 0.0,
        "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
        "scale_x": GROUND_SCALE, "scale_y": GROUND_SCALE, "scale_z": GROUND_SCALE,
        "color_r": 200, "color_g": 200, "color_b": 200, "color_a": 255,
        "geometry": GEO_GRID, "hide": 0, "topo": TOPO_PLANE, "ratio": 0.1,
        "texture_id": GROUND_TEXTURE_ID, "ch_input_id": 0,
    }


def school_node(node_id, tx, ty, color, marker_scale, ch_input_id):
    r, g, b = color
    return {
        "id": node_id, "type": 5, "parent_id": 0, "branch_level": 0,
        "translate_x": round(tx, 4), "translate_y": round(ty, 4), "translate_z": MARKER_Z,
        "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
        "scale_x": marker_scale, "scale_y": marker_scale, "scale_z": marker_scale,
        "color_r": r, "color_g": g, "color_b": b, "color_a": 255,
        "geometry": GEO_CIRCLE, "hide": 0, "topo": 0, "ratio": 0.1,
        "texture_id": 0, "ch_input_id": ch_input_id,
    }


def generate(args):
    if args.source == "csv":
        print(f"Loading sdusd<year>.csv from {args.data_dir} ...")
        series, latlng, names = fetch_school_series_csv(
            args.data_dir, args.start_year, args.end_year, args.min_grade, args.max_grade,
            args.testtype, args.subgroup_codes)
    else:
        print(f"Connecting to mysql://{args.db_user}@{args.db_host}/{args.db_name} ...")
        series, latlng, names = fetch_school_series_mysql(
            args.db_host, args.db_user, args.db_password, args.db_name,
            args.start_year, args.end_year, args.min_grade, args.max_grade,
            args.testtype, args.subgroup_codes)

    schools = sorted(code for code, by_year in series.items() if by_year and code in latlng)
    print(f"  {len(schools)} schools with {args.subgroup_label!r} data and a known lat/lon")
    years_per_school = [len(series[code]) for code in schools]
    full_coverage = sum(1 for n in years_per_school if n == args.end_year - args.start_year + 1)
    print(f"  {full_coverage}/{len(schools)} schools have real (non-placeholder) data for every year "
          f"in range; the rest hold flat at their nearest known year outside their real coverage")

    n_years = args.end_year - args.start_year + 1
    n_frames = (n_years - 1) * args.frames_per_year + 1
    frame_years = np.linspace(args.start_year, args.end_year, n_frames)

    nodes = []
    tags = []
    ch_map_rows = []
    ch_track_cols = {}
    next_id = 1
    next_track_id = 0

    if not args.no_ground_image:
        nodes.append(ground_plane_node(next_id))
        next_id += 1

    for school_code in schools:
        by_year = series[school_code]
        years_known = sorted(by_year)
        pct_known = [by_year[y] for y in years_known]
        pct_frames = np.interp(frame_years, years_known, pct_known)

        lat, lon = clamp_to_county(*latlng[school_code])
        tx = X_SCALE * (lon - MAP_MIN_LON) + 180
        ty = Y_SCALE * (lat - MAP_MIN_LAT) - 180

        node_id = next_id
        next_id += 1
        ch_input_id = node_id
        first_color = proficiency_to_heat_color(pct_frames[0])
        nodes.append(school_node(node_id, tx, ty, first_color, args.marker_scale, ch_input_id))

        track_r, track_g, track_b = next_track_id, next_track_id + 1, next_track_id + 2
        next_track_id += 3
        colors = np.array([proficiency_to_heat_color(p) for p in pct_frames])
        ch_track_cols[track_r] = colors[:, 0].astype(float)
        ch_track_cols[track_g] = colors[:, 1].astype(float)
        ch_track_cols[track_b] = colors[:, 2].astype(float)
        for track_id, attr in ((track_r, "color_r"), (track_g, "color_g"), (track_b, "color_b")):
            ch_map_rows.append({"id": len(ch_map_rows), "channel_id": ch_input_id, "track_id": track_id,
                                 "attribute": attr, "track_table_id": 0, "ch_map_table_id": 0, "record_id": 0})

        school_name = names.get(school_code, "No Name Available")
        tags.append({"id": len(tags), "table_id": 0, "record_id": node_id,
                     "title": f"{school_name}: {pct_known[0]:.1f}% ({years_known[0]}) "
                              f"-> {pct_known[-1]:.1f}% ({years_known[-1]})"})

    args.output_dir.mkdir(parents=True, exist_ok=True)
    node_path = args.output_dir / f"{args.prefix}_gv_node.csv"
    with open(node_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=NODE_FIELDS)
        w.writeheader()
        w.writerows(nodes)
    print(f"\n{node_path.name}: {len(nodes)} nodes")

    tag_path = args.output_dir / f"{args.prefix}_gv_tag.csv"
    with open(tag_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "table_id", "record_id", "title"])
        w.writeheader()
        w.writerows(tags)
    print(f"{tag_path.name}: {len(tags)} labels")

    ch_map_path = args.output_dir / f"{args.prefix}_gv_ch-map.csv"
    with open(ch_map_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "channel_id", "track_id", "attribute",
                                          "track_table_id", "ch_map_table_id", "record_id"])
        w.writeheader()
        w.writerows(ch_map_rows)
    print(f"{ch_map_path.name}: {len(ch_map_rows)} channel mappings")

    track_ids = sorted(ch_track_cols.keys())
    track_cols = [f"ch{tid}" for tid in track_ids]
    ch_tracks_path = args.output_dir / f"{args.prefix}_gv_ch-tracks.csv"
    with open(ch_tracks_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cyclecount"] + track_cols)
        stacked = np.column_stack([ch_track_cols[tid] for tid in track_ids]) if track_ids else np.zeros((n_frames, 0))
        for frame_idx in range(n_frames):
            w.writerow([frame_idx] + [round(float(v), 2) for v in stacked[frame_idx]])
    print(f"{ch_tracks_path.name}: {n_frames} frames x {len(track_ids)} tracks "
          f"({args.frames_per_year} frames/year, {n_years} years)")

    print(f"\nDone. Open GlyphViz, then: File > Open Node CSV -> {node_path.name}")
    return node_path, tag_path


def main():
    generate(build_arg_parser().parse_args())


if __name__ == "__main__":
    main()
