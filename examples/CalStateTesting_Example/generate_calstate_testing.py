#!/usr/bin/env python3
"""
generate_calstate_testing.py
=============================
Python port of Jeff's original PHP/MySQL generator
(files_for_star_test_example/get_calstate_testing_data_allyears_dbquery_v1.php)
for the California STAR standardized-test-score visualization (San Diego
Unified School District, 2003-2012): one node tree per (year, school),
fanning out into 6 demographic-subgroup branches, each fanning out into up
to 25 real CST/CAPA test-score branches.

Glyph design (Jeff): a central wireframe sphere represents one K-12 school
(~50 in the district for a given year); a thin torus anchored to it carries
6 colored subgroup branches (Males/Females/Black/Asian/Hispanic/Caucasian),
each sized by how many students were tested; each subgroup fans out into
per-test branches sized by mean scale score and colored by percent-above-
proficient banding.

4-level hierarchy (branch_level 0-3), exactly matching the PHP's math:
  BL0  one node per (school, year). Geometry=Sphere-Wire, Topo=Pin.
       translate_x/y from a fixed lat/lon -> world-XY scale+offset
       (mapminlat/lon constants below); translate_z = (year-2002)*2 stacks
       years vertically. scale=0.25. lat/lon are clamped to the county
       bounding box (clamp_to_county()) before projection -- schoollatlng
       is a shared lookup table, not SDUSD-only, and a handful of
       schoolcodes otherwise resolve thousands of units off-scene.
  BL1  torus anchor, child of BL0, Topo=Torus, ratio=0.06, color_a=155
       (translucent). Always at local origin (anchors at its parent).
  BL2  6 demographic subgroups, child of BL1, fixed evenly around the torus
       at translate_x = j*360/6 regardless of which groups are enabled.
       Geometry is hardcoded to Cylinder-Wire (matches the PHP, which sets
       $bl2_geom from a form field but then unconditionally overwrites it
       -- dead form parameter, intentionally not exposed here). scale =
       2*log(1 + total_subgroup_tested/25). Default Topo=Rod (6), which is
       what the real reference run (antz0001node.csv, validated below) used
       -- the PHP's own literal default is Torus (3) but that wasn't what
       produced the screenshots Jeff shared.
  BL3  up to 25 real tests (testid 7..31; 0-6 are reserved/unused slots in
       the source data), child of BL2, fanned along local X via
       translate_x = k*280/32 - 40. scale = mean_scale_score/600; color
       banded by percent-above-proficient (proficiency_color() below).
       Geometry=Octahedron by default (not the PHP's literal Torus -- Jeff
       found Torus tanked framerate at full scale: ~25 tests x 6 groups x
       dozens of schools x up to 10 years, all torus meshes; Octahedron
       fixed it). Only written when scale_x > 0.01 (matches PHP's filter
       for no-data/zero-score tests) -- the id counter still advances for
       skipped tests so id numbering matches a from-scratch PHP run.

Two interchangeable data sources (--source csv|mysql), same generation logic
--------------------------------------------------------------------------
The PHP original queried a live MySQL database directly; this port supports
that path too, not just the CSV-export path, via a small DataSource
abstraction (CsvDataSource / MySqlDataSource below) -- everything from the
geo-projection math down to tag text is identical regardless of source.

  --source csv (default). Reads, from --data-dir:
    sdusd<year>.csv     one row per (school, grade, subgroup, test)
    schoollatlng.csv    schoolcode -> latitude/longitude
    schoolnames.csv     schoolcode -> schoolname
  None of these are checked into this repo -- exported from Jeff's MySQL
  `calstatetesting_all` database.

  --source mysql. Runs the same 4 queries the PHP ran, literally, against
  a live MySQL server (--db-host/--db-user/--db-password/--db-name, default
  localhost/root/""/calstatetesting_all -- the PHP's own mysqli_connect()
  call): `SELECT DISTINCT school FROM sdusd<year> WHERE grade=%s`,
  `SELECT * FROM schoollatlng WHERE schoolcode=%s`, `SELECT * FROM
  schoolnames WHERE schoolcode=%s`, and the per-school test-data SELECT
  (subgroup, testtype, totalsubgrouptested, grade, testid, studentstested,
  meanscalescore, percentaboveproficient ... WHERE school=%s AND
  testtype='C' AND grade=%s). Requires `pip install pymysql` (not a hard
  dependency of the csv path). school_info() results are cached per process
  since the same schoolcode is looked up once per year in the PHP.

Validated against ground truth
-------------------------------
The PHP's exact arithmetic (geo-projection, log-scaled subgroup size,
score/proficiency-banded test branches, id-increment-even-when-filtered
sequencing) was checked field-by-field against a real PHP-generated
antz0001node.csv/antz0001tag.csv pair (grade 8, year 2003, "John Muir"
school) -- e.g. node id 9 (BL2, Males, j=0): translate_x=0, scale_x=
3.3278521954363 = 2*log(1+107/25), geometry=18, topo=6, ratio=0.45,
color=(0,0,255); node id 57 (BL3, k=28 -> tests[21]="CST General
Mathematics"): scale_x=0.46183333333333 = 277.1/600, color=(80,80,80)
(0-20% band). This script reproduces that arithmetic; it does not
reproduce the legacy ANTz id numbering (the real file prepends 6
camera/world/grid housekeeping rows before the data starts at id 7) since
GlyphViz's own examples don't use that preamble -- ids here start at 1.

Output files (written to --output-dir, default: this script's directory)
--------------------------------------------------------------------------
  {PREFIX}_gv_node.csv   BL0..BL3 node hierarchy for every (year, school),
                         plus one ground-plane node (see GROUND_* constants,
                         disable with --no-ground-image) textured with the
                         San Diego County satellite image at media/
                         map00001.jpg -- GlyphViz auto-loads any media/
                         folder next to the node CSV on open, assigning
                         texture_id by alphanumeric order (1 = first file),
                         so no manifest/extra wiring is needed beyond that
                         file being present.
  {PREFIX}_gv_tag.csv    matching tag/label text per node (the ground plane
                         has none, matching the PHP)

--mode gap and --mode grades (two additional scenes, same underlying data)
--------------------------------------------------------------------------
Beyond the --mode demographics (default) scene above, this script can build
two other readings of the same decade of data:

  --mode gap  -- makes the achievement gap a literal geometric feature
      instead of a number. Per (school, year), each of the 4 ethnicities gets
      TWO adjacent BL2 nodes -- disadvantaged and non-disadvantaged cross-
      codes (200/202/204/206 vs 220/222/224/226) -- instead of one, with a
      Link (type=7, GEO_LINE_PRISM) "gap bridge" connecting them. The pair's
      angular separation, the bridge's color band (green->red), and its
      thickness all scale with the ELA mean-scale-score gap, so scanning up
      the Z-stacked years shows the gap visibly widening, narrowing, or
      closing per ethnicity. IMPORTANT: SDUSD only started publishing these
      disadvantaged/non-disadvantaged crosses in 2008 -- 2003-2007 rows are
      all zero for these codes (verified against the live database, 2026-07-
      22). Use --start-year 2008 --end-year 2012, not the full decade.
      Example: examples/CalStateTesting_Example/AchievementGap/.

  --mode grades -- one Spiral-topology (TOPO_SPIRAL) anchor per (school,
      year) instead of the fixed 6-slot demographic torus, fanning out EVERY
      real tested grade level (2-11, 13) as its own climbing-helix arm
      (grade 2 = innermost/lowest, grade 13 = outermost/highest, colored by
      a rainbow gradient -- GRADE_COLORS) instead of picking one grade up
      front. Uses the 'All Students' aggregate (subgroup=1, present every
      year, unlike the gap-mode cross-codes) so it safely spans the full
      2003-2012 decade. --grade is not required (and ignored) in this mode --
      a school's real grade span (elementary/middle/high) falls out of the
      data via DataSource.schools_and_grades(). Roughly 6x the node count of
      one --mode demographics grade-8-only scene (~35k-50k nodes for the full
      decade) -- within the range already proven at perf-round-2 scale, but
      each --mode grades year issues one MySQL query per (school, grade)
      pair (~900-1000/year), so a full 10-year run takes several minutes.
      Example: examples/CalStateTesting_Example/GradesCube/.

Usage
-----
  python generate_calstate_testing.py --grade 8 --start-year 2003 --end-year 2003
  python generate_calstate_testing.py --grade 8 --start-year 2003 --end-year 2012 \
      --data-dir "C:/Jeff/python/glyphviz/glyphviz_examples/CalStateTesting_Example"
  python generate_calstate_testing.py --source mysql --grade 8 --start-year 2003 --end-year 2012
  python generate_calstate_testing.py --source mysql --mode gap --grade 8 \
      --start-year 2008 --end-year 2012 --prefix CalStateTesting_AchievementGap_Example
  python generate_calstate_testing.py --source mysql --mode grades \
      --start-year 2003 --end-year 2012 --prefix CalStateTesting_GradesCube_Example

Load in GlyphViz: File > Open Node CSV -> {PREFIX}_gv_node.csv
"""

import argparse
import csv
import math
from pathlib import Path

import pandas as pd

OUTPUT_DIR = Path(__file__).parent
DEFAULT_DATA_DIR = Path(r"C:\Jeff\python\glyphviz\glyphviz_examples\CalStateTesting_Example")
PREFIX = "CalStateTesting_Example"

TOPO_TORUS = 3
TOPO_PIN = 5
TOPO_ROD = 6
TOPO_PLANE = 8
TOPO_SPIRAL = 14

NODE_TYPE_PIN = 5
NODE_TYPE_LINK = 7  # graph edge, parent_id=A-end / child_id=B-end (glyphviz_core.node.NODE_TYPE_LINK)

GEO_CUBE = 1
GEO_SPHERE_WIRE = 2
GEO_SPHERE = 3
GEO_CONE = 5
GEO_TORUS = 7
GEO_DODECA = 9
GEO_OCTA = 11
GEO_TETRA = 13
GEO_ICOSA = 15
GEO_CYLINDER_WIRE = 18
GEO_GRID = 21
GEO_LINE_PRISM = 28  # textured tube between a Link's A-end/B-end -- see geometry_data.py

# Ground-plane satellite image (media/map00001.jpg, the same map00001.jpg the
# PHP's own $files_to_zip bundled) -- a single static node, not per-year/
# school, matching the one extra row Jeff's reference node CSV appends after
# the main loop. Position/scale hand-tuned by Jeff in the live app against
# this example's real school marker positions (supersedes the original
# reference-row values, which didn't actually line up).
GROUND_SCALE = 270.0
GROUND_TX = 10
GROUND_TY = -6.5
GROUND_RATIO = 0.1
GROUND_COLOR = (200, 200, 200)
GROUND_TEXTURE_ID = 1
GROUND_FACET = 1
GROUND_SEGMENTS = 16

# Geo-registration bounding box (San Diego County) -- $mapminlat etc. in the PHP.
MAP_MIN_LAT = 32.547103
MAP_MAX_LAT = 32.972668
MAP_MIN_LON = -116.794333
MAP_MAX_LON = -117.313437
X_SCALE = -360 / (MAP_MAX_LON - MAP_MIN_LON)
Y_SCALE = 360 / (MAP_MAX_LAT - MAP_MIN_LAT)
_LAT_LO, _LAT_HI = min(MAP_MIN_LAT, MAP_MAX_LAT), max(MAP_MIN_LAT, MAP_MAX_LAT)
_LON_LO, _LON_HI = min(MAP_MIN_LON, MAP_MAX_LON), max(MAP_MIN_LON, MAP_MAX_LON)


def clamp_to_county(lat, lon):
    """schoollatlng is a shared, multi-project lookup table (not SDUSD-only)
    -- a handful of schoolcodes resolve to lat/lon thousands of units outside
    San Diego County (numeric collisions with other entities, not real SDUSD
    placements). Rather than dropping those schools (losing real test-score
    data) or leaving them flung far off-scene, clamp to the county's own
    bounding box so they land at the nearest edge instead."""
    return max(_LAT_LO, min(lat, _LAT_HI)), max(_LON_LO, min(lon, _LON_HI))

# $colortable -- only the indices actually used by the generator are needed.
COLOR_TABLE = {
    0: (255, 0, 0), 2: (0, 0, 255), 5: (255, 255, 0), 6: (255, 153, 0),
    12: (204, 102, 0), 17: (255, 255, 255), 26: (127, 127, 127),
}

# $proficiencycolor -- banded by percent-above-proficient: >80, 60-80, 40-60, 20-40, 0-20, else.
PROFICIENCY_COLORS_DEFAULT = [(0, 255, 0), (0, 215, 50), (0, 255, 255), (0, 215, 215), (120, 0, 120), (80, 80, 80)]
PROFICIENCY_COLORS_PRISM = [(255, 0, 0), (255, 127, 0), (255, 255, 0), (0, 220, 100), (0, 0, 255), (80, 80, 80)]

GROUPS = ["Males", "Females", "Black/African-American", "Asian", "Hispanic/Latino", "Caucasian"]
GROUP_KEYS = ["males", "females", "black", "asian", "hispanic", "white"]
GROUP_COLOR_INDEX = [2, 0, 12, 5, 6, 17]

SUBGROUPS_DISADV = [3, 4, 200, 202, 204, 206]
SUBGROUPS_NONDISADV = [3, 4, 220, 222, 224, 226]

# --mode gap only needs the 4 ethnicity crosses -- Male/Female (index 0-1 above)
# have no disadvantaged/non-disadvantaged split, so they don't fit the gap story.
ETHNICITY_GROUPS = GROUPS[2:]
ETHNICITY_COLOR_INDEX = GROUP_COLOR_INDEX[2:]
GAP_DISADV_CODES = SUBGROUPS_DISADV[2:]        # [200, 202, 204, 206]
GAP_NONDISADV_CODES = SUBGROUPS_NONDISADV[2:]  # [220, 222, 224, 226]
GAP_CODES = GAP_DISADV_CODES + GAP_NONDISADV_CODES  # bucket order: 4 disadv, then 4 non-disadv

# CST English-Language Arts (testid 7, TESTS[0]) is the one test given at every
# tested grade 2-11 -- Math's testid varies by grade/course (General Math vs
# Algebra I vs Geometry ...), so ELA is the only apples-to-apples score axis
# across grade levels. Used as --mode gap's single gap metric.
ELA_TESTID = 7

# Gap-bridge color bands by ELA mean-scale-score gap (non-disadv minus disadv):
# green = nearly closed, red = severe and unclosed. A non-positive gap (closed
# or reversed) gets its own cyan band rather than folding into the green one.
GAP_BAND_COLORS = [(0, 210, 60), (230, 210, 0), (255, 140, 0), (220, 0, 0)]
GAP_CLOSED_COLOR = (0, 230, 230)


def gap_band(gap_mss):
    if gap_mss <= 0:
        return GAP_CLOSED_COLOR
    if gap_mss <= 10:
        return GAP_BAND_COLORS[0]
    if gap_mss <= 25:
        return GAP_BAND_COLORS[1]
    if gap_mss <= 40:
        return GAP_BAND_COLORS[2]
    return GAP_BAND_COLORS[3]


# --mode grades: every real tested grade level (testid 0-6/12-31 reserved-slot
# quirk doesn't apply here -- this is the *grade* column, not testid). Schools
# only test a handful of consecutive grades (elementary vs middle vs high), so
# this is a modest per-school-year fan-out, not a huge one.
ALL_GRADES = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13]

# Grade-node color gradient, grade 2 (innermost/lowest) -> grade 13 (outermost/
# highest) -- a rainbow ramp so color alone hints at grade level at a glance,
# reinforcing the "Grade: N" tag-search workflow.
GRADE_COLORS = [
    (60, 90, 255), (60, 150, 255), (60, 200, 220), (60, 220, 140), (120, 220, 60),
    (200, 220, 60), (255, 200, 60), (255, 150, 60), (255, 100, 60), (255, 60, 90),
    (220, 60, 200),
]

GRADE_SPIRAL_STEP_DEG = 30.0      # angular spacing per grade slot (12 slots tile 360)
GRADE_SPIRAL_RADIAL_STEP = 0.35   # radial growth per grade -- turns the ring into a climbing helix

# $tests, indexed by testid-7 (testid 0-6 are reserved/unused slots in the source data).
TESTS = [
    "CST English-Language Arts", "CST Mathematics", "CST Algebra I", "CST Integrated Math 1",
    "CST Geometry", "CST Integrated Math 2", "CST Algebra II", "CST Integrated Math 3",
    "CST Summative High School Mathematics", "NA", "NA", "CST World History", "CST U.S. History",
    "CST Biology", "CST Chemistry", "CST Earth Science", "CST Physics",
    "CST Integrated/Coordinated Science 1", "CST Integrated/Coordinated Science 2",
    "CST Integrated/Coordinated Science 3", "CST Integrated/Coordinated Science 4",
    "CST General Mathematics", "CST History - Social Science Grade 8",
    "CAPA English-Language Arts", "CAPA Mathematics", "CST Life Science",
]

NODE_FIELDS = [
    "id", "type", "parent_id", "branch_level", "child_id",
    "translate_x", "translate_y", "translate_z",
    "rotate_x", "rotate_y", "rotate_z",
    "scale_x", "scale_y", "scale_z",
    "color_r", "color_g", "color_b", "color_a",
    "geometry", "hide", "topo", "ratio", "rotate_rate_y",
    "texture_id", "facet", "segments_x", "segments_y",
]


def fmt_num(x):
    """Mirrors PHP's bare numeric-to-string cast: whole values print without
    a trailing '.0' (e.g. tag text 'Pct. Prof: 19', not '19.0')."""
    f = float(x)
    return str(int(f)) if f == int(f) else str(f)


def proficiency_color(pct_above_proficient, prism):
    colors = PROFICIENCY_COLORS_PRISM if prism else PROFICIENCY_COLORS_DEFAULT
    if pct_above_proficient > 80:
        return colors[0]
    if 60 < pct_above_proficient <= 80:
        return colors[1]
    if 40 < pct_above_proficient <= 60:
        return colors[2]
    if 20 < pct_above_proficient <= 40:
        return colors[3]
    if 0 < pct_above_proficient <= 20:
        return colors[4]
    return colors[5]


def bl3_geometry(k, geom_on):
    if not geom_on:
        # Octahedron, not the PHP's literal Torus default -- Jeff found Torus
        # (a much higher-poly mesh, x ~25 test glyphs x 6 groups x dozens of
        # schools) tanked framerate; Octahedron fixed it with no visual loss
        # at this glyph size.
        return GEO_OCTA
    return {7: GEO_CUBE, 8: GEO_SPHERE, 11: GEO_CONE, 18: GEO_TORUS,
            20: GEO_DODECA, 21: GEO_OCTA, 22: GEO_TETRA, 23: GEO_ICOSA}.get(k, GEO_OCTA)


def node_row(node_id, parent_id, branch_level, tx, ty, tz, scale, color, geometry, topo, ratio,
             rotate_rate_y=0.0, texture_id=0, facet=0, segments_x=16, segments_y=16,
             node_type=NODE_TYPE_PIN, child_id=0, color_a=255):
    r, g, b = color
    return {
        "id": node_id, "type": node_type, "parent_id": parent_id, "branch_level": branch_level,
        "child_id": child_id,
        "translate_x": round(tx, 6), "translate_y": round(ty, 6), "translate_z": round(tz, 6),
        "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
        "scale_x": round(scale, 6), "scale_y": round(scale, 6), "scale_z": round(scale, 6),
        "color_r": r, "color_g": g, "color_b": b, "color_a": color_a,
        "geometry": geometry, "hide": 0, "topo": topo, "ratio": ratio,
        "rotate_rate_y": round(rotate_rate_y, 6),
        "texture_id": texture_id, "facet": facet,
        "segments_x": segments_x, "segments_y": segments_y,
    }


def ground_plane_node(node_id):
    """The satellite-image ground plane (see GROUND_* constants above) --
    a single top-level node, parent_id=0, no tag (the PHP didn't write one
    for it either)."""
    return node_row(node_id, 0, 0, GROUND_TX, GROUND_TY, 0.0, GROUND_SCALE, GROUND_COLOR,
                     GEO_GRID, TOPO_PLANE, ratio=GROUND_RATIO, texture_id=GROUND_TEXTURE_ID,
                     facet=GROUND_FACET, segments_x=GROUND_SEGMENTS, segments_y=GROUND_SEGMENTS)


def _bucket_test_rows(rows, subgroup_codes):
    """Shared by both DataSources: mirrors the PHP's $query_GetTestData loop
    -- buckets (subgroup, testid, meanscalescore, percentaboveproficient,
    totalsubgrouptested) rows into [group_index][testid] arrays. Sized to
    len(subgroup_codes) -- 6 for --mode demographics, 8 for --mode gap."""
    n_groups = len(subgroup_codes)
    mean_scale_score = [[0.0] * 32 for _ in range(n_groups)]
    percent_above_proficient = [[0.0] * 32 for _ in range(n_groups)]
    total_subgroup_tested = [0] * n_groups

    for subgroup, totalsubgrouptested, testid, meanscalescore, percentaboveproficient in rows:
        subgroup = int(subgroup)
        if subgroup not in subgroup_codes:
            continue
        group_idx = subgroup_codes.index(subgroup)
        testid = int(testid)
        if not (0 <= testid < 32):
            continue
        total_subgroup_tested[group_idx] = int(totalsubgrouptested)
        mean_scale_score[group_idx][testid] = float(meanscalescore)
        percent_above_proficient[group_idx][testid] = float(percentaboveproficient)

    return mean_scale_score, percent_above_proficient, total_subgroup_tested


class CsvDataSource:
    """Reads sdusd<year>.csv / schoollatlng.csv / schoolnames.csv exported
    from the MySQL database. Each year's sdusd table is loaded once and
    cached (the PHP re-queries per school; pandas filtering in memory is
    the natural equivalent here)."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        latlng_df = pd.read_csv(data_dir / "schoollatlng.csv")
        self._latlng = {int(row.schoolcode): (float(row.latitude), float(row.longitude))
                         for row in latlng_df.itertuples()}
        names_df = pd.read_csv(data_dir / "schoolnames.csv")
        self._names = {int(row.schoolcode): str(row.schoolname) for row in names_df.itertuples()}
        self._sdusd_cache = {}

    def _sdusd(self, year):
        if year not in self._sdusd_cache:
            path = self.data_dir / f"sdusd{year}.csv"
            self._sdusd_cache[year] = pd.read_csv(path) if path.exists() else None
        return self._sdusd_cache[year]

    def schools_for_grade(self, year, grade):
        df = self._sdusd(year)
        if df is None:
            return []
        schools = df.loc[(df["grade"] == grade) & (df["school"] > 1), "school"].unique().tolist()
        return sorted(int(s) for s in schools)

    def schools_and_grades(self, year):
        """(--mode grades) distinct (school, grade) pairs with an 'All
        Students' (subgroup=1) CST result -- every real tested grade, not
        just one, so a school's actual grade span (elementary/middle/high)
        falls out of the data instead of being hardcoded."""
        df = self._sdusd(year)
        if df is None:
            return []
        sub = df[(df["school"] > 1) & (df["grade"].isin(ALL_GRADES))
                 & (df["testtype"] == "C") & (df["subgroup"] == 1)]
        pairs = sub[["school", "grade"]].drop_duplicates()
        return sorted((int(r.school), int(r.grade)) for r in pairs.itertuples())

    def school_info(self, code):
        lat, lon = self._latlng.get(code, (MAP_MIN_LAT, MAP_MIN_LON))
        name = self._names.get(code, "No Name Available")
        return lat, lon, name

    def test_data(self, year, code, grade, subgroup_codes):
        df = self._sdusd(year)
        rows = df[(df["school"] == code) & (df["testtype"] == "C") & (df["grade"] == grade)]
        tuples = ((r.subgroup, r.totalsubgrouptested, r.testid, r.meanscalescore, r.percentaboveproficient)
                   for r in rows.itertuples())
        return _bucket_test_rows(tuples, subgroup_codes)


class MySqlDataSource:
    """Runs the PHP's own queries directly against a live MySQL server."""

    def __init__(self, host, user, password, database):
        import pymysql
        self._conn = pymysql.connect(host=host, user=user, password=password,
                                      database=database, connect_timeout=10)
        self._school_info_cache = {}

    def schools_for_grade(self, year, grade):
        table = f"sdusd{int(year)}"
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT DISTINCT `school` FROM `{table}` WHERE `grade` = %s", (grade,))
            codes = [int(row[0]) for row in cur.fetchall()]
        return sorted(c for c in codes if c > 1)

    def schools_and_grades(self, year):
        """(--mode grades) distinct (school, grade) pairs with an 'All
        Students' (subgroup=1) CST result -- see CsvDataSource's twin method."""
        table = f"sdusd{int(year)}"
        placeholders = ",".join(["%s"] * len(ALL_GRADES))
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT DISTINCT school, grade FROM `{table}` WHERE school > 1 "
                f"AND grade IN ({placeholders}) AND testtype = 'C' AND subgroup = 1",
                tuple(ALL_GRADES))
            pairs = [(int(r[0]), int(r[1])) for r in cur.fetchall()]
        return sorted(pairs)

    def school_info(self, code):
        if code in self._school_info_cache:
            return self._school_info_cache[code]
        with self._conn.cursor() as cur:
            cur.execute("SELECT latitude, longitude FROM schoollatlng WHERE `schoolcode` = %s", (code,))
            row = cur.fetchone()
            lat, lon = (float(row[0]), float(row[1])) if row else (MAP_MIN_LAT, MAP_MIN_LON)

            cur.execute("SELECT schoolname FROM schoolnames WHERE `schoolcode` = %s", (code,))
            row = cur.fetchone()
            name = str(row[0]) if row else "No Name Available"

        self._school_info_cache[code] = (lat, lon, name)
        return lat, lon, name

    def test_data(self, year, code, grade, subgroup_codes):
        table = f"sdusd{int(year)}"
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT subgroup, testtype, totalsubgrouptested, grade, testid, studentstested, "
                f"meanscalescore, percentaboveproficient FROM `{table}` "
                f"WHERE school = %s AND testtype = 'C' AND grade = %s", (code, grade))
            rows = ((subgroup, totalsubgrouptested, testid, meanscalescore, percentaboveproficient)
                     for subgroup, _testtype, totalsubgrouptested, _grade, testid, _studentstested,
                         meanscalescore, percentaboveproficient in cur.fetchall())
            return _bucket_test_rows(rows, subgroup_codes)


def build_arg_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", choices=["csv", "mysql"], default="csv")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR,
                         help=f"(--source csv) directory with sdusd<year>.csv / schoollatlng.csv / schoolnames.csv (default {DEFAULT_DATA_DIR})")
    parser.add_argument("--db-host", default="localhost", help="(--source mysql)")
    parser.add_argument("--db-user", default="root", help="(--source mysql)")
    parser.add_argument("--db-password", default="", help="(--source mysql)")
    parser.add_argument("--db-name", default="calstatetesting_all", help="(--source mysql)")
    parser.add_argument("--grade", type=int, default=None,
                         help="grade level to visualize, e.g. 8 (required for --mode demographics/gap; "
                              "ignored -- and not required -- for --mode grades, which fans every real "
                              "tested grade per school instead of one)")
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument("--mode", choices=["demographics", "gap", "grades"], default="demographics",
                         help="demographics (default): 6 fixed subgroup branches, single proficiency "
                              "color per test. gap: 4 ethnicity PAIRS (disadvantaged + non-disadvantaged "
                              "cross-codes side by side) with a color/thickness-banded Link bridge between "
                              "each pair encoding the ELA score gap -- makes the achievement gap a literal "
                              "geometric feature instead of a number; only has data from 2008 on. grades: "
                              "one Spiral anchor per (school, year) fanning EVERY tested grade level (2-11, "
                              "13) as a climbing helix arm instead of picking a single grade up front, using "
                              "the All-Students aggregate so it's safe across the full 2003-2012 decade.")
    parser.add_argument("--disadvantaged", choices=["disadv", "nondisadv"], default="nondisadv",
                         help="(--mode demographics only) subgroup code set: disadvantaged (200s) or "
                              "non-disadvantaged (220s)")
    parser.add_argument("--max-branch-level", type=int, choices=[0, 1, 2, 3], default=3)
    parser.add_argument("--bl2-topo", type=int, default=TOPO_ROD,
                         help="topo for the 6 demographic-subgroup nodes (default 6=Rod, matching the validated reference run)")
    parser.add_argument("--exclude-groups", nargs="*", default=[], choices=GROUP_KEYS,
                         help="demographic subgroups to omit (default: all 6 included)")
    parser.add_argument("--prism", action="store_true", help="use the prism (red..blue) proficiency palette instead of green/cyan/purple")
    parser.add_argument("--geom", action="store_true", help="vary BL3 test-node geometry by test id instead of using Torus for all")
    parser.add_argument("--rotation", action="store_true", help="spin BL3 test nodes (rotate_rate_y) proportional to percent-above-proficient")
    parser.add_argument("--dbquery-flag", action="store_true",
                         help="encode record_id as <year-2-digits><schoolcode> instead of the sequential node id")
    parser.add_argument("--no-ground-image", action="store_true",
                         help="omit the satellite-image ground plane (media/map00001.jpg, texture_id=1)")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--prefix", default=PREFIX)
    return parser


def emit_bl3(next_id, bl2_id, group_idx, mean_scale_score, percent_above_proficient, args):
    """Up to 25 real-test branches fanned along local X under one subgroup/
    grade node. Shared by --mode demographics (one branch per group), --mode
    gap (two independent fans -- disadvantaged and non-disadvantaged -- per
    ethnicity), and --mode grades (one fan per grade level). Returns
    (next_id, new_nodes, new_tags); tags omit "id" (assigned by the caller,
    which knows the running tags list length)."""
    new_nodes, new_tags = [], []
    for k in range(7, 32):
        bl3_id = next_id
        next_id += 1
        scale = mean_scale_score[group_idx][k] / 600
        if scale <= 0.01:
            continue
        pct_prof = percent_above_proficient[group_idx][k]
        color = proficiency_color(pct_prof, args.prism)
        geometry = bl3_geometry(k, args.geom)
        rotate_rate_y = pct_prof / 10 if args.rotation else 0.0
        new_nodes.append(node_row(bl3_id, bl2_id, 3, k * 280 / 32 - 40, 0, 0, scale,
                                   color, geometry, TOPO_TORUS, ratio=0.08,
                                   rotate_rate_y=rotate_rate_y))
        new_tags.append({"node_id": bl3_id,
                          "title": f"Test: {TESTS[k - 7]} MSS: {fmt_num(mean_scale_score[group_idx][k])} "
                                   f"Pct. Prof: {fmt_num(pct_prof)}"})
    return next_id, new_nodes, new_tags


def _write_output(args, nodes, tags, next_id):
    """Shared by generate() and generate_grades_cube(): ground plane + CSV
    writing. Returns (node_path, tag_path)."""
    if not args.no_ground_image:
        nodes.append(ground_plane_node(next_id))
        next_id += 1

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


def generate_grades_cube(args, source):
    """--mode grades: one Spiral-topology anchor per (school, year), fanning
    out EVERY tested grade level (2-11, 13) as its own climbing helix arm
    (inner/low = grade 2, outer/high = grade 13) instead of picking a single
    grade up front -- each grade arm carries its own up-to-25 real-test
    branches. Uses the 'All Students' aggregate (subgroup=1, present every
    year) rather than the demographic subgroup codes so it can safely span
    the full 2003-2012 decade (--mode gap's ethnicity/disadv-status crosses
    only exist from 2008 on -- see GAP_CODES)."""
    nodes, tags = [], []
    next_id = 1

    for year in range(args.start_year, args.end_year + 1):
        pairs = source.schools_and_grades(year)
        grades_by_school = {}
        for school, grade in pairs:
            grades_by_school.setdefault(school, []).append(grade)
        schools = sorted(grades_by_school)
        print(f"  {year}: {len(schools)} schools, {len(pairs)} (school, grade) branches")

        for school_code in schools:
            lat, lon, school_name = source.school_info(school_code)
            lat, lon = clamp_to_county(lat, lon)

            if args.dbquery_flag:
                record_id = int(f"{str(year)[2:4]}{school_code}")

            # --- BL0: one wireframe sphere per (school, year) ---
            bl0_id = next_id
            next_id += 1
            tx = X_SCALE * (lon - MAP_MIN_LON) + 180
            ty = Y_SCALE * (lat - MAP_MIN_LAT) - 180
            tz = (year - 2002) * 2
            nodes.append(node_row(bl0_id, 0, 0, tx, ty, tz, 0.25, COLOR_TABLE[26],
                                   GEO_SPHERE_WIRE, TOPO_PIN, ratio=0.1))
            tag_text = f"School: {school_name} | Year: {year}"
            tags.append({"id": len(tags), "table_id": 0,
                         "record_id": record_id if args.dbquery_flag else bl0_id, "title": tag_text})

            if args.max_branch_level < 1:
                continue

            # --- BL1: thin torus anchor, Spiral topology carries the grade arms ---
            bl1_id = next_id
            next_id += 1
            nodes.append(node_row(bl1_id, bl0_id, 1, 0, 0, 0, 1.0, COLOR_TABLE[26],
                                   GEO_TORUS, TOPO_SPIRAL, ratio=0.06))
            nodes[-1]["color_a"] = 100
            tags.append({"id": len(tags), "table_id": 0,
                         "record_id": record_id if args.dbquery_flag else bl1_id, "title": tag_text})

            if args.max_branch_level < 2:
                continue

            # --- BL2: every real tested grade, climbing the spiral ---
            for grade in sorted(grades_by_school[school_code]):
                mean_scale_score, percent_above_proficient, total_subgroup_tested = source.test_data(
                    year, school_code, grade, [1])

                grade_slot = ALL_GRADES.index(grade)
                grade_id = next_id
                next_id += 1
                scale = 2 * math.log1p(total_subgroup_tested[0] / 25)
                grade_tag_num = 12 if grade == 13 else grade
                nodes.append(node_row(grade_id, bl1_id, 2,
                                       grade_slot * GRADE_SPIRAL_STEP_DEG, 0,
                                       grade_slot * GRADE_SPIRAL_RADIAL_STEP,
                                       scale, GRADE_COLORS[grade_slot], GEO_CYLINDER_WIRE,
                                       TOPO_ROD, ratio=0.4))
                grade_record_id = record_id if args.dbquery_flag else grade_id
                tags.append({"id": len(tags), "table_id": 0, "record_id": grade_record_id,
                             "title": f"Grade: {grade_tag_num} | School: {school_name} | Year: {year} "
                                      f"| # Tested: {total_subgroup_tested[0]}"})

                if args.max_branch_level < 3:
                    continue

                # --- BL3: up to 25 real tests, fanned along local X ---
                next_id, new_nodes, new_tags = emit_bl3(
                    next_id, grade_id, 0, mean_scale_score, percent_above_proficient, args)
                nodes.extend(new_nodes)
                for t in new_tags:
                    tags.append({"id": len(tags), "table_id": 0,
                                 "record_id": record_id if args.dbquery_flag else t["node_id"],
                                 "title": t["title"]})

    return _write_output(args, nodes, tags, next_id)


def generate(args):
    """Runs the full generation pipeline for one parsed argparse.Namespace
    (from build_arg_parser().parse_args()) and writes the node/tag CSVs.
    Returns (node_path, tag_path). Factored out of main() so notebooks/other
    scripts can call this directly instead of shelling out to the CLI."""
    if args.source == "csv":
        print(f"Loading lookup tables from {args.data_dir} ...")
        source = CsvDataSource(args.data_dir)
    else:
        print(f"Connecting to mysql://{args.db_user}@{args.db_host}/{args.db_name} ...")
        source = MySqlDataSource(args.db_host, args.db_user, args.db_password, args.db_name)

    if args.mode == "grades":
        return generate_grades_cube(args, source)

    if args.grade is None:
        raise SystemExit("--grade is required for --mode demographics/gap")

    subgroup_codes = GAP_CODES if args.mode == "gap" else (
        SUBGROUPS_DISADV if args.disadvantaged == "disadv" else SUBGROUPS_NONDISADV)
    enabled_groups = [key not in args.exclude_groups for key in GROUP_KEYS]
    grade_for_tag = 12 if args.grade == 13 else args.grade

    nodes = []
    tags = []
    next_id = 1

    for year in range(args.start_year, args.end_year + 1):
        schools = source.schools_for_grade(year, args.grade)
        print(f"  {year}: {len(schools)} schools at grade {args.grade}")

        for school_code in schools:
            lat, lon, school_name = source.school_info(school_code)
            lat, lon = clamp_to_county(lat, lon)

            mean_scale_score, percent_above_proficient, total_subgroup_tested = source.test_data(
                year, school_code, args.grade, subgroup_codes)

            if args.dbquery_flag:
                record_id = int(f"{str(year)[2:4]}{school_code}")
            # else: record_id is just next_id, assigned per node below.

            # --- BL0: one wireframe sphere per (school, year) ---
            bl0_id = next_id
            next_id += 1
            tx = X_SCALE * (lon - MAP_MIN_LON) + 180
            ty = Y_SCALE * (lat - MAP_MIN_LAT) - 180
            tz = (year - 2002) * 2
            nodes.append(node_row(bl0_id, 0, 0, tx, ty, tz, 0.25, COLOR_TABLE[26],
                                   GEO_SPHERE_WIRE, TOPO_PIN, ratio=0.1))
            tag_text = f"Grade: {grade_for_tag} | School: {school_name} | Year: {year}"
            tags.append({"id": len(tags), "table_id": 0,
                         "record_id": record_id if args.dbquery_flag else bl0_id, "title": tag_text})

            if args.max_branch_level < 1:
                continue

            # --- BL1: torus anchor ---
            bl1_id = next_id
            next_id += 1
            nodes.append(node_row(bl1_id, bl0_id, 1, 0, 0, 0, 1.0, COLOR_TABLE[26],
                                   GEO_TORUS, TOPO_TORUS, ratio=0.06))
            nodes[-1]["color_a"] = 155
            tags.append({"id": len(tags), "table_id": 0,
                         "record_id": record_id if args.dbquery_flag else bl1_id, "title": tag_text})

            if args.max_branch_level < 2:
                continue

            if args.mode == "gap":
                # --- BL2: 4 ethnicity PAIRS (disadv + non-disadv side by side) ---
                for i, ethnicity in enumerate(ETHNICITY_GROUPS):
                    d_idx, n_idx = i, i + 4  # GAP_CODES bucket order: 4 disadv, then 4 non-disadv
                    d_mss = mean_scale_score[d_idx][ELA_TESTID]
                    n_mss = mean_scale_score[n_idx][ELA_TESTID]
                    gap = (n_mss - d_mss) if (d_mss > 0 and n_mss > 0) else None
                    # Angular separation of the pair also grows with the gap --
                    # severe gaps push the two nodes visibly further apart on
                    # the ring, not just a different bridge color/thickness.
                    half_gap_deg = 6 + min(30, abs(gap) / 2) if gap is not None else 10
                    base_angle = i * 90
                    eth_color = COLOR_TABLE[ETHNICITY_COLOR_INDEX[i]]

                    def emit_gap_bl2(angle, idx, label, color_a):
                        nonlocal next_id
                        node_id = next_id
                        next_id += 1
                        scale = 2 * math.log1p(total_subgroup_tested[idx] / 25)
                        nodes.append(node_row(node_id, bl1_id, 2, angle, 0, 0, scale,
                                               eth_color, GEO_CYLINDER_WIRE, TOPO_ROD,
                                               ratio=0.45, color_a=color_a))
                        rid = record_id if args.dbquery_flag else node_id
                        tags.append({"id": len(tags), "table_id": 0, "record_id": rid,
                                     "title": f"Grade: {args.grade} Group: {ethnicity} ({label}) "
                                              f"# Subgroup Tested: {total_subgroup_tested[idx]}"})
                        if args.max_branch_level >= 3:
                            next_id, new_nodes, new_tags = emit_bl3(
                                next_id, node_id, idx, mean_scale_score, percent_above_proficient, args)
                            nodes.extend(new_nodes)
                            for t in new_tags:
                                tags.append({"id": len(tags), "table_id": 0,
                                             "record_id": record_id if args.dbquery_flag else t["node_id"],
                                             "title": t["title"]})
                        return node_id

                    d_id = emit_gap_bl2(base_angle - half_gap_deg, d_idx, "Disadv", 255)
                    n_id = emit_gap_bl2(base_angle + half_gap_deg, n_idx, "Non-Disadv", 140)

                    if gap is not None:
                        bridge_id = next_id
                        next_id += 1
                        thickness = max(0.05, min(0.5, 0.05 + abs(gap) / 250))
                        nodes.append(node_row(bridge_id, d_id, 2, 0, 0, 0, 1.0, gap_band(gap),
                                               GEO_LINE_PRISM, 0, ratio=thickness,
                                               node_type=NODE_TYPE_LINK, child_id=n_id))
                        tags.append({"id": len(tags), "table_id": 0,
                                     "record_id": record_id if args.dbquery_flag else bridge_id,
                                     "title": f"Gap: {ethnicity} ELA MSS Delta={gap:+.1f} "
                                              f"(Disadv {fmt_num(d_mss)} vs Non-Disadv {fmt_num(n_mss)}) "
                                              f"| Grade {args.grade} | {year}"})
                continue

            # --- BL2: 6 demographic subgroups ---
            for j in range(6):
                if not enabled_groups[j]:
                    continue
                bl2_id = next_id
                next_id += 1
                scale = 2 * math.log1p(total_subgroup_tested[j] / 25)
                ratio = 0.45 if args.bl2_topo == 6 else 0.25
                nodes.append(node_row(bl2_id, bl1_id, 2, j * 360 / 6, 0, 0, scale,
                                       COLOR_TABLE[GROUP_COLOR_INDEX[j]], GEO_CYLINDER_WIRE,
                                       args.bl2_topo, ratio=ratio))
                bl2_record_id = record_id if args.dbquery_flag else bl2_id
                tags.append({"id": len(tags), "table_id": 0, "record_id": bl2_record_id,
                             "title": f"Grade: {args.grade} Group: {GROUPS[j]} "
                                      f"# Subgroup Tested: {total_subgroup_tested[j]}"})

                if args.max_branch_level < 3:
                    continue

                # --- BL3: up to 25 real tests, fanned along local X ---
                next_id, new_nodes, new_tags = emit_bl3(
                    next_id, bl2_id, j, mean_scale_score, percent_above_proficient, args)
                nodes.extend(new_nodes)
                for t in new_tags:
                    tags.append({"id": len(tags), "table_id": 0,
                                 "record_id": record_id if args.dbquery_flag else t["node_id"],
                                 "title": t["title"]})

    return _write_output(args, nodes, tags, next_id)


def main():
    generate(build_arg_parser().parse_args())


if __name__ == "__main__":
    main()
