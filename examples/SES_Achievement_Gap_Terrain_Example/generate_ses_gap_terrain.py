#!/usr/bin/env python3
"""
generate_ses_gap_terrain.py
============================
"The forest, not the trees": two stacked GlyphViz TOPO_SURFACE meshes over
the same (grade, year) grid, built from the same San Diego Unified STAR
testing database as CalStateTesting_Example (calstatetesting_all) -- one
mesh for economically-disadvantaged students' average CST proficiency,
one for non-disadvantaged, both keyed by the literal CDE `subgroup` codes
(31 = Economically Disadvantaged, 111 = Not Economically Disadvantaged;
see CalStateTesting_Example/generate_calstate_testing.py's docstring for how
the wider subgroup-code landscape was confirmed against CDE's STAR Research
File documentation).

Why a terrain, and why two of them
-----------------------------------
A real, persistent achievement gap exists in this data: 15-35 percentage
points of `percentaboveproficient`, every grade (2-11), every year
(2003-2012) -- both groups improve over the decade, but the gap barely
narrows (e.g. grade 8: disadvantaged 13.3%->47.0%, non-disadvantaged
36.5%->75.7%, 2003->2012). Rather than computing the gap as a single
abstract number per cell, this renders BOTH groups' own proficiency as two
separate terrains sharing the same (grade, year) XY grid -- the vertical
gap *between* the two surfaces at any point IS the achievement gap, and is
visually legible without reading an axis label, while each surface's own
slope still shows that group's real trend over time.

How TOPO_SURFACE works (glyphviz_core/topology.py's `_surface_offset`,
glyphviz_gl/viewport.py's `_draw_topology_overlays`): children of a
Surface-topology root sit at their own literal Cartesian translate_x/y (the
grid position) with translate_z as the height; the renderer regroups a
Surface root's children back into a grid purely from their distinct
(translate_x, translate_y) values (no row/col column needed) and draws a
lit, per-vertex-colored GL_QUADS mesh between them -- confirmed against
Surface_Example/generate_surface_example.py, which establishes the same
pattern for a real DEM. Each grid cell here is a real, discrete (grade,
year) pair -- not interpolated -- so root scale stays 1.0 and grid spacing
is baked directly into each child's translate_x/y (GRID_SPACING_X/Y below).

Color: each surface keeps a fixed hue (warm orange-red for disadvantaged,
cool blue for non-disadvantaged) so the two meshes stay visually distinct
regardless of height, with HSV *value* (brightness) driven by that cell's
own proficiency (0-100% -> 40%-100% brightness) -- a heatmap within each
mesh's own hue family.

Two interchangeable data sources (--source csv|mysql), same generation logic
-----------------------------------------------------------------------------
Same convention as generate_calstate_testing.py. `--source mysql` runs one
aggregate query per (year, grade) against a live MySQL server:
  SELECT subgroup, SUM(studentstested), SUM(studentstested*percentaboveproficient)
  FROM sdusd<year> WHERE testtype=%s AND school>1 AND subgroup IN (%s,%s)
    AND grade=%s
  GROUP BY subgroup
`--source csv` runs the equivalent pandas groupby against sdusd<year>.csv
files in --data-dir (the same files generate_calstate_testing.py reads).
Either way the weighted (by studentstested) average proficiency per
(year, grade, subgroup) is what becomes that cell's height.

--group-a-code/--group-b-code default to the Economically-Disadvantaged
split (31/111), but this generalizes to any other binary subgroup pair in
the same data -- e.g. disability status (128/99) or English-learner status
(160/180) -- by overriding those two flags and the matching --group-a-label/
--group-b-label.

Output files (written to --output-dir, default: this script's directory)
--------------------------------------------------------------------------
  {PREFIX}_gv_node.csv   2 Surface roots (group A, group B) + one child per
                         (grade, year) cell with real data, per root
  {PREFIX}_gv_tag.csv    one label per child: grade/year/group/proficiency

Usage
-----
  python generate_ses_gap_terrain.py --source mysql
  python generate_ses_gap_terrain.py --source mysql --start-year 2003 --end-year 2012 \
      --group-a-code 128 --group-a-label "Students with Disability" \
      --group-b-code 99  --group-b-label "No Reported Disability"

Load in GlyphViz: File > Open Node CSV -> {PREFIX}_gv_node.csv
"""

import argparse
import colorsys
import csv
from pathlib import Path

import pandas as pd

OUTPUT_DIR = Path(__file__).parent
DEFAULT_DATA_DIR = Path(r"C:\Jeff\python\glyphviz\glyphviz_examples\CalStateTesting_Example")
PREFIX = "SES_Achievement_Gap_Terrain_Example"

TOPO_SURFACE = 17   # glyphviz_core/topology.py
GEO_POINT = 22       # glyphviz_core/geometry_data.py
GEO_CUBE = 1

MIN_GRADE_DEFAULT = 2
MAX_GRADE_DEFAULT = 11
GRID_SPACING_X = 8.0   # world units per grade step
GRID_SPACING_Y = 8.0   # world units per year step
Z_SCALE = 1.0           # world units of height per proficiency percentage point
MARKER_SCALE = 2.0      # GEO_CUBE child glyph size

GROUP_A_CODE_DEFAULT, GROUP_A_LABEL_DEFAULT = 31, "Economically Disadvantaged"
GROUP_B_CODE_DEFAULT, GROUP_B_LABEL_DEFAULT = 111, "Not Economically Disadvantaged"
GROUP_A_HUE, GROUP_B_HUE = 0.05, 0.58   # warm orange-red / cool blue
SATURATION = 0.85
VALUE_LO, VALUE_HI = 0.40, 1.0          # brightness range across 0-100% proficiency

NODE_FIELDS = [
    "id", "type", "parent_id", "branch_level",
    "translate_x", "translate_y", "translate_z",
    "rotate_x", "rotate_y", "rotate_z",
    "scale_x", "scale_y", "scale_z",
    "color_r", "color_g", "color_b", "color_a",
    "geometry", "hide", "topo", "ratio",
]


def proficiency_to_color(pct, hue):
    value = VALUE_LO + (VALUE_HI - VALUE_LO) * max(0.0, min(pct, 100.0)) / 100.0
    r, g, b = colorsys.hsv_to_rgb(hue, SATURATION, value)
    return int(r * 255), int(g * 255), int(b * 255)


def fetch_grid_mysql(host, user, password, database, start_year, end_year,
                      min_grade, max_grade, testtype, group_a_code, group_b_code):
    import pymysql
    conn = pymysql.connect(host=host, user=user, password=password, database=database, connect_timeout=10)
    cur = conn.cursor()
    grid = {}
    for year in range(start_year, end_year + 1):
        table = f"sdusd{int(year)}"
        for grade in range(min_grade, max_grade + 1):
            cur.execute(
                f"SELECT subgroup, SUM(studentstested), SUM(studentstested*percentaboveproficient) "
                f"FROM `{table}` WHERE testtype=%s AND school>1 AND subgroup IN (%s,%s) AND grade=%s "
                f"GROUP BY subgroup", (testtype, group_a_code, group_b_code, grade))
            cell = {}
            for subgroup, n, weighted in cur.fetchall():
                n = float(n) if n else 0.0
                weighted = float(weighted) if weighted else 0.0
                if n > 0:
                    cell[int(subgroup)] = weighted / n
            if group_a_code in cell and group_b_code in cell:
                grid[(year, grade)] = cell
    conn.close()
    return grid


def fetch_grid_csv(data_dir, start_year, end_year, min_grade, max_grade,
                    testtype, group_a_code, group_b_code):
    grid = {}
    for year in range(start_year, end_year + 1):
        path = Path(data_dir) / f"sdusd{year}.csv"
        if not path.exists():
            print(f"  skipping {year}: {path.name} not found")
            continue
        df = pd.read_csv(path)
        scoped = df[(df["testtype"] == testtype) & (df["school"] > 1)
                     & (df["subgroup"].isin([group_a_code, group_b_code]))]
        for grade in range(min_grade, max_grade + 1):
            by_grade = scoped[scoped["grade"] == grade]
            cell = {}
            for subgroup, sub_df in by_grade.groupby("subgroup"):
                n = float(sub_df["studentstested"].sum())
                if n > 0:
                    weighted = float((sub_df["studentstested"] * sub_df["percentaboveproficient"]).sum())
                    cell[int(subgroup)] = weighted / n
            if group_a_code in cell and group_b_code in cell:
                grid[(year, grade)] = cell
    return grid


def build_arg_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", choices=["csv", "mysql"], default="csv")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR,
                         help=f"(--source csv) directory with sdusd<year>.csv files (default {DEFAULT_DATA_DIR})")
    parser.add_argument("--db-host", default="localhost", help="(--source mysql)")
    parser.add_argument("--db-user", default="root", help="(--source mysql)")
    parser.add_argument("--db-password", default="", help="(--source mysql)")
    parser.add_argument("--db-name", default="calstatetesting_all", help="(--source mysql)")
    parser.add_argument("--start-year", type=int, default=2003)
    parser.add_argument("--end-year", type=int, default=2012)
    parser.add_argument("--min-grade", type=int, default=MIN_GRADE_DEFAULT)
    parser.add_argument("--max-grade", type=int, default=MAX_GRADE_DEFAULT)
    parser.add_argument("--testtype", default="C", help="STAR testtype code (default 'C' = CST)")
    parser.add_argument("--group-a-code", type=int, default=GROUP_A_CODE_DEFAULT)
    parser.add_argument("--group-a-label", default=GROUP_A_LABEL_DEFAULT)
    parser.add_argument("--group-b-code", type=int, default=GROUP_B_CODE_DEFAULT)
    parser.add_argument("--group-b-label", default=GROUP_B_LABEL_DEFAULT)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--prefix", default=PREFIX)
    return parser


def _surface_root(node_id, hue):
    r, g, b = proficiency_to_color(70, hue)
    return {
        "id": node_id, "type": 5, "parent_id": 0, "branch_level": 0,
        "translate_x": 0.0, "translate_y": 0.0, "translate_z": 0.0,
        "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
        "scale_x": 1.0, "scale_y": 1.0, "scale_z": 1.0,
        "color_r": r, "color_g": g, "color_b": b, "color_a": 255,
        "geometry": GEO_POINT, "hide": 0, "topo": TOPO_SURFACE, "ratio": 0.1,
    }


def _surface_child(node_id, parent_id, grade, year, min_grade, start_year, pct, hue):
    r, g, b = proficiency_to_color(pct, hue)
    tx = (grade - min_grade) * GRID_SPACING_X
    ty = (year - start_year) * GRID_SPACING_Y
    tz = pct * Z_SCALE
    return {
        "id": node_id, "type": 5, "parent_id": parent_id, "branch_level": 1,
        "translate_x": round(tx, 4), "translate_y": round(ty, 4), "translate_z": round(tz, 4),
        "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
        "scale_x": MARKER_SCALE, "scale_y": MARKER_SCALE, "scale_z": MARKER_SCALE,
        "color_r": r, "color_g": g, "color_b": b, "color_a": 255,
        "geometry": GEO_CUBE, "hide": 0, "topo": 0, "ratio": 0.1,
    }


def generate(args):
    if args.source == "csv":
        print(f"Loading sdusd<year>.csv from {args.data_dir} ...")
        grid = fetch_grid_csv(args.data_dir, args.start_year, args.end_year,
                               args.min_grade, args.max_grade, args.testtype,
                               args.group_a_code, args.group_b_code)
    else:
        print(f"Connecting to mysql://{args.db_user}@{args.db_host}/{args.db_name} ...")
        grid = fetch_grid_mysql(args.db_host, args.db_user, args.db_password, args.db_name,
                                 args.start_year, args.end_year, args.min_grade, args.max_grade,
                                 args.testtype, args.group_a_code, args.group_b_code)

    print(f"  {len(grid)} (year, grade) cells with data for both groups "
          f"(grades {args.min_grade}-{args.max_grade}, years {args.start_year}-{args.end_year})")

    root_a_id, root_b_id = 1, 2
    nodes = [_surface_root(root_a_id, GROUP_A_HUE), _surface_root(root_b_id, GROUP_B_HUE)]
    tags = []
    next_id = 3

    for (year, grade), cell in sorted(grid.items()):
        for root_id, code, label, hue in (
            (root_a_id, args.group_a_code, args.group_a_label, GROUP_A_HUE),
            (root_b_id, args.group_b_code, args.group_b_label, GROUP_B_HUE),
        ):
            pct = cell[code]
            node_id = next_id
            next_id += 1
            nodes.append(_surface_child(node_id, root_id, grade, year,
                                         args.min_grade, args.start_year, pct, hue))
            tags.append({"id": len(tags), "table_id": 0, "record_id": node_id,
                         "title": f"Grade {grade} | {year} | {label}: {pct:.1f}% above proficient"})

    gap_values = [cell[args.group_b_code] - cell[args.group_a_code] for cell in grid.values()]
    if gap_values:
        print(f"  achievement gap range: {min(gap_values):.1f} to {max(gap_values):.1f} percentage points")

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

    print(f"\nDone. Open GlyphViz, then: File > Open Node CSV -> {node_path.name}")
    return node_path, tag_path


def main():
    generate(build_arg_parser().parse_args())


if __name__ == "__main__":
    main()
