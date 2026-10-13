"""
Read the `batting` table of the Lahman database (loaded by lahman_to_mysql.py)
and write the whole history of major-league batting as a GlyphViz scene.

This is an update of one of the best-loved ANTz visualisations: every
player-season in the American and National Leagues, one hyperglyph each.

THE GLYPH -- one player, one season
-----------------------------------
    sphere (centre)   Batting average.  Its SIZE and its shade of GRAY both
                      follow the average, so a good hitter is a big pale
                      sphere and a poor one a small dark one.
    four shapes       Pushed out around the sphere at 90 degree intervals.
                      Each one's SIZE is a count, and each stat has its own
                      SHAPE as well as its colour, so one stat can be picked
                      out of 40,000 glyphs with Select By > Geometry:
                          cyan     icosahedron   doubles   (2B)
                          magenta  octahedron    triples   (3B)
                          yellow   cylinder      home runs (HR)
                          orange   dodecahedron  RBI
                      A zero count draws nothing, so the shapes present are
                      themselves information.

The shapes are CHILDREN of the sphere, and a child inherits its parent's scale
(see the glyphviz-skill rule "Resize a hyperglyph by scaling the ROOT").  The
ANTz original let that happen, so a small sphere carried proportionally small
cubes.  Here each child's scale is DIVIDED by the sphere's, so a shape's world
size is its count and nothing else -- a 22-home-run cylinder is the same size on
a .200 hitter and a .400 hitter.  Its distance from the sphere is likewise set
in world units (the sphere's radius plus a gap plus the shape's own radius), so
shapes sit just clear of the sphere however small the sphere is.

WHERE THE GLYPH SITS -- three axes, three increments
----------------------------------------------------
    x   the PLAYER, alphabetical by last name, 0.1 units per player
    y   the TEAM, alphabetical by team id, 10 units per team
    z   the YEAR, 1 unit per year (z = year - 1870, as in the original)

Each league is ranked on its own, so the American League fills x = -180 ... and
the National League starts one quarter of an AL-width beyond it -- a gap the
original used, reproduced exactly.  Both leagues share the same y and z.  A
player who played in both leagues has a slot in each.

All of that was read back out of the original ANTz node and tag files rather
than assumed; the README says how.  Which player-seasons qualify was checked
the same way: the original file's 34,681 seasons are exactly the AL/NL seasons
1876-2012 with MORE THAN 100 at-bats (not 150, which is what its title card
says) -- so 100 is the default here, and --min-ab changes it.

Usage
-----
    python lahman_batting_to_glyphviz.py --user root
    python lahman_batting_to_glyphviz.py --out mine --first-year 1900 \
        --last-year 2025 --min-ab 150

Connection settings are the same as lahman_to_mysql.py (MYSQL_HOST, MYSQL_PORT,
MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE).  Needs `pip install pymysql`.
Open the resulting node CSV in GlyphViz (File > Open, or drag it onto the
window).  Labels are inline `text`, so no tag file is written; select a glyph
(or rubber-band a group) to read what it is, or press T.
"""

import argparse
import csv
import getpass
import os
import re
import sys
import unicodedata
from collections import namedtuple
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Constants: the data -> picture mapping
# ---------------------------------------------------------------------------

LEAGUES = (("AL", "AMERICAN LEAGUE"), ("NL", "NATIONAL LEAGUE"))

# Position increments, read from the original ANTz file.
X_START = -180.0
X_STEP = 0.1               # per player
Y_START = -180.0
Y_STEP = 10.0              # per team
YEAR_ZERO = 1870           # z = year - YEAR_ZERO  (1876 -> 6)
LEAGUE_GAP_FRACTION = 0.25  # of the American League's width

# The sphere: SIZE = t**2 and GRAY = GRAY_MIN + (GRAY_MAX-GRAY_MIN) * t, where
# t runs 0..1 across the batting averages in the scene.  The original squared
# t for size and used a plain linear ramp for the gray.  GRAY_MIN is above 0
# so a poor hitter's sphere -- and its label, which takes the sphere's colour --
# can still be read against a dark background.
GRAY_MIN, GRAY_MAX = 90, 255

GEO_SPHERE, GEO_CONE, GEO_POINT, GEO_CYLINDER, GEO_PRISM = 3, 5, 22, 19, 28
GEO_DODECA, GEO_OCTA, GEO_ICOSA = 9, 11, 15

# The four child shapes: (stat, long name, longitude on the sphere, colour,
# geometry, scale per unit).  "Scale per unit" is the shape's size, in world
# units, per count BEFORE CHILD_SCALE is applied.
CUBES = (
    ("2B", "doubles", 0.0, (0, 255, 255), GEO_ICOSA, 0.05),
    ("3B", "triples", 90.0, (255, 0, 255), GEO_OCTA, 0.05),
    ("HR", "home runs", 180.0, (255, 255, 0), GEO_CYLINDER, 0.05),
    ("RBI", "RBI", 270.0, (255, 153, 0), GEO_DODECA, 0.01),
)
SHAPE_NAMES = {GEO_ICOSA: "icosahedron", GEO_OCTA: "octahedron",
               GEO_CYLINDER: "cylinder", GEO_DODECA: "dodecahedron"}
# How far each geometry reaches along its own +Z, which under a Point parent is
# straight out from the sphere (measured, glyphviz-skill rule 2).  Placement
# uses it so a shape's NEAR face, not its centre, clears the sphere.
OUTWARD_EXTENT = {GEO_ICOSA: 0.851, GEO_OCTA: 1.0, GEO_CYLINDER: 1.0,
                  GEO_DODECA: 0.934}

# World-unit size of a shape per count is per_unit * CHILD_SCALE.  0.25 puts the
# typical glyph at about the size the inherited-scale version drew it (median
# sphere scale ~0.28), so the scene reads as the same density.  --child-scale.
CHILD_SCALE = 0.25
# --triples-gain multiplies the triples shape only, for when the rarest hit
# needs to be seen from far away.  It lives here so add_glyph, the example
# glyph and the legend all agree.
STAT_GAIN = {"2B": 1.0, "3B": 1.0, "HR": 1.0, "RBI": 1.0}
# Gap between the sphere's skin and a shape's near face, in world units.
CHILD_GAP = 0.04
# A sphere is never smaller than this (scale).  Its children's scale is divided
# by it, so exactly 0 -- the lowest average in the scene -- is not available.
SPHERE_MIN = 0.01

TYPE_WORLD, TYPE_GLYPH, TYPE_LINK = 0, 5, 7
TOPO_NONE, TOPO_POINT = 0, 7

BACKGROUND = (4, 6, 12)
AXIS_RGB = (160, 178, 215)      # axes and ticks: kept clear of the data colours
TITLE_RGB = (255, 255, 255)

# The example glyph and the average key are real glyphs drawn this many times
# larger than life.
SPECIMEN_MAGNIFY = 60.0
KEY_MAGNIFY = 25.0
KEY_SPACING = 64.0
SPECIMEN = ("altmage01", 1962, "CHN")     # George Altman, the legend glyph
KEY_AVERAGES = (0.150, 0.200, 0.250, 0.300, 0.350, 0.400)

# Axes: arrowhead length and shaft thickness, in world units (a link's `ratio`
# is its thickness).  YEAR_STEP is the spacing of the labelled year ticks.
ARROW_HEAD, ARROW_SHAFT = 14.0, 0.8
YEAR_STEP = 25
LETTER_GAP = 22.0      # least spacing, in units, between two NAMED initials

Season = namedtuple("Season", "pid first last year team lg ab h d2 d3 hr rbi")

QUERY = """
SELECT b.playerID, p.nameFirst, p.nameLast, b.yearID, b.teamID, b.lgID,
       b.AB, b.H,
       COALESCE(b.`2B`, 0), COALESCE(b.`3B`, 0),
       COALESCE(b.HR, 0), COALESCE(b.RBI, 0)
FROM batting b
JOIN people p ON p.playerID = b.playerID
WHERE b.lgID IN ('AL', 'NL')
  AND b.yearID BETWEEN {first} AND {last}
  AND b.AB > {min_ab}
ORDER BY b.lgID, b.teamID, p.nameLast, p.nameFirst, b.yearID, b.stint
"""


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def fetch_seasons(conn, first, last, min_ab):
    """Every qualifying batting row, as Season tuples."""
    sql = QUERY.format(first=int(first), last=int(last), min_ab=max(int(min_ab), 0))   # AB > 0: a batting average needs one
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    return [Season(r[0], (r[1] or "").strip(), (r[2] or "").strip(), int(r[3]),
                   r[4], r[5], int(r[6]), int(r[7]), int(r[8]), int(r[9]),
                   int(r[10]), int(r[11])) for r in rows]


def avg_milli(season):
    """Batting average in thousandths, rounded half up (.2425 -> 243) the way a
    box score does.  Integer arithmetic: float rounding would make it .242."""
    return (2000 * season.h + season.ab) // (2 * season.ab)


def format_avg(milli):
    return "%d.%03d" % divmod(milli, 1000) if milli >= 1000 else ".%03d" % milli


def clean(text):
    """Label text: no control characters (one bad byte can drop every tag)."""
    return re.sub(r"[\x00-\x1f\x7f]", " ", text).strip()


def person_name(season):
    return clean("%s %s" % (season.first, season.last))


def sort_key(season):
    """Alphabetical by last name, then first, ignoring accents and case."""
    def fold(s):
        return unicodedata.normalize("NFKD", s).encode(
            "ascii", "ignore").decode().casefold()
    return fold(season.last), fold(season.first), season.pid


class Layout:
    """Where every league's players, teams and years go."""

    def __init__(self, seasons):
        self.leagues = {}
        x_cursor = X_START
        al_width = None
        for code, _name in LEAGUES:
            mine = [s for s in seasons if s.lg == code]
            by_player = {}
            for s in mine:
                by_player.setdefault(s.pid, s)
            players = sorted(by_player.values(), key=sort_key)
            teams = sorted({s.team for s in mine})
            if code != LEAGUES[0][0]:
                x_cursor += LEAGUE_GAP_FRACTION * al_width
            rank = {s.pid: i for i, s in enumerate(players)}
            width = X_STEP * max(len(players) - 1, 0)
            if al_width is None:
                al_width = width
            self.leagues[code] = {
                "x0": x_cursor, "x1": x_cursor + width,
                "y0": Y_START, "y1": Y_START + Y_STEP * max(len(teams) - 1, 0),
                "rank": rank, "players": players,
                "team_rank": {t: i for i, t in enumerate(teams)},
                "teams": teams, "seasons": len(mine),
            }
            x_cursor += width

    def position(self, s):
        lg = self.leagues[s.lg]
        return (lg["x0"] + X_STEP * lg["rank"][s.pid],
                lg["y0"] + Y_STEP * lg["team_rank"][s.team],
                float(s.year - YEAR_ZERO))


class Sphere:
    """Batting average -> sphere scale and gray, normalised over the scene."""

    def __init__(self, lo, hi):
        self.lo, self.hi = lo, max(hi, lo + 1e-9)

    def t(self, avg):
        return min(1.0, max(0.0, (avg - self.lo) / (self.hi - self.lo)))

    def scale(self, avg):
        return max(SPHERE_MIN, self.t(avg) ** 2)

    def gray(self, avg):
        return int(round(GRAY_MIN + (GRAY_MAX - GRAY_MIN) * self.t(avg)))


# ---------------------------------------------------------------------------
# Scene writing
# ---------------------------------------------------------------------------

COLUMNS = [
    "id", "type", "parent_id", "branch_level", "child_id",
    "translate_x", "translate_y", "translate_z",
    "rotate_x", "rotate_y", "rotate_z",
    "scale_x", "scale_y", "scale_z",
    "color_r", "color_g", "color_b", "color_a",
    "geometry", "hide", "topo", "ratio", "text", "show_text",
    "tag_color_mode", "ref_grid_color_r", "ref_grid_color_g",
    "ref_grid_color_b",
]

DEFAULTS = {
    "parent_id": 0, "branch_level": 0, "child_id": 0,
    "translate_x": 0, "translate_y": 0, "translate_z": 0,
    "rotate_x": 0, "rotate_y": 0, "rotate_z": 0,
    "scale_x": 1, "scale_y": 1, "scale_z": 1,
    "color_r": 255, "color_g": 255, "color_b": 255, "color_a": 255,
    "geometry": GEO_SPHERE, "hide": 0, "topo": TOPO_NONE, "ratio": 0.1,
    "text": "", "show_text": 0, "tag_color_mode": 0,
    "ref_grid_color_r": 56, "ref_grid_color_g": 56, "ref_grid_color_b": 71,
}


def num(v, places=6):
    """Shortest faithful decimal: 6.0 -> 6, 0.133010381 -> 0.133, never -0."""
    text = ("%.*f" % (places, v)).rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


class SceneBuilder:
    def __init__(self):
        self.rows = []

    def add(self, **kw):
        row = dict(DEFAULTS)
        row.update(kw)
        row["id"] = len(self.rows) + 1
        self.rows.append(row)
        return row["id"]

    def world(self):
        # tag_color_mode = 1 draws each label in its own node's colour, which
        # is what lets the example glyph's labels match their shapes.
        return self.add(type=TYPE_WORLD, hide=1, tag_color_mode=1,
                        color_r=BACKGROUND[0], color_g=BACKGROUND[1],
                        color_b=BACKGROUND[2], ref_grid_color_r=26,
                        ref_grid_color_g=30, ref_grid_color_b=46)

    def write(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh, lineterminator="\r\n")
            writer.writerow(COLUMNS)
            for row in self.rows:
                writer.writerow([
                    num(row[c]) if isinstance(row[c], float) else row[c]
                    for c in COLUMNS])
        os.replace(tmp, path)          # a reader never sees a half-written file


# ---------------------------------------------------------------------------
# The hyperglyph
# ---------------------------------------------------------------------------

def child_placement(root_scale, magnify, per_unit, geometry, count, stat):
    """
    Where one child shape sits and how big it is, as the (scale, translate_z)
    to WRITE, plus its outward half-extent in world units.

    A child inherits its parent's scale, so the scale written is the wanted
    WORLD size divided by the parent's -- that division is what makes a shape's
    size depend on its count alone.  `root_scale` is the scale as written
    (already magnified), which is the divisor the engine will actually use.
    Under a Point-topology parent translate_z is the full reach, again in the
    parent's units: sphere radius + gap + the shape's own outward extent, in
    world units, divided by the same scale.
    """
    world = per_unit * CHILD_SCALE * STAT_GAIN[stat] * count * magnify
    half = OUTWARD_EXTENT[geometry] * world
    reach = root_scale + CHILD_GAP * magnify + half
    return world / root_scale, reach / root_scale, half


def add_glyph(b, season, position, sphere, magnify=1.0, parts=None,
              pinned=False):
    """
    One player-season: a sphere with up to four shapes around it.  `magnify`
    scales the whole assembly and `parts` optionally overrides the label of
    "avg", "2B", "3B", "HR", "RBI".
    """
    parts = parts or {}
    avg = avg_milli(season) / 1000.0
    who = "%s %s %d" % (person_name(season), season.team, season.year)
    scale = float("%.6f" % (sphere.scale(avg) * magnify))
    gray = sphere.gray(avg)
    root = b.add(
        type=TYPE_GLYPH, branch_level=0,
        translate_x=position[0], translate_y=position[1],
        translate_z=position[2],
        scale_x=scale, scale_y=scale, scale_z=scale,
        color_r=gray, color_g=gray, color_b=gray,
        geometry=GEO_SPHERE, topo=TOPO_POINT,
        text=parts.get("avg") or "%s Batting Avg: %s" % (
            who, format_avg(avg_milli(season))),
        show_text=1 if pinned else 0)
    counts = {"2B": season.d2, "3B": season.d3, "HR": season.hr,
              "RBI": season.rbi}
    for stat, _long, longitude, rgb, geometry, per_unit in CUBES:
        count = counts[stat]
        if count <= 0:
            continue
        size, reach, _half = child_placement(scale, magnify, per_unit,
                                             geometry, count, stat)
        b.add(type=TYPE_GLYPH, parent_id=root, branch_level=1,
              translate_x=longitude, translate_z=reach,
              scale_x=size, scale_y=size, scale_z=size,
              color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
              geometry=geometry, topo=TOPO_NONE,
              text=parts.get(stat) or "%s %s: %d" % (who, stat, count),
              show_text=1 if pinned else 0)
    return root


# ---------------------------------------------------------------------------
# Axes, league titles and the labelled example glyph
#
# GlyphViz draws no screen-space overlay, so all of it is real geometry:
# Point glyphs (a few pixels wide, so never mistaken for data) that carry a
# PINNED label, joined by Link nodes drawn as square prisms and cones.  (Not
# cylinders or cubes: those ids belong to the data's shapes, and keeping them
# unshared is what lets Select By > Geometry pick out exactly one stat.)
# ---------------------------------------------------------------------------

def label(b, x, y, z, text, rgb=AXIS_RGB):
    return b.add(type=TYPE_GLYPH, translate_x=x, translate_y=y, translate_z=z,
                 color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
                 geometry=GEO_POINT, ratio=0.12, text=text, show_text=1)


def tick(b, x, y, z, rgb=AXIS_RGB):
    """An unlabelled Point glyph: a tick mark, or an anchor for a link."""
    return b.add(type=TYPE_GLYPH, translate_x=x, translate_y=y, translate_z=z,
                 color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
                 geometry=GEO_POINT, ratio=0.12)


def arrow(b, start, end, start_text, end_text, head, shaft, rgb=AXIS_RGB):
    """A shaft (cylinder link) ending in a cone link whose apex is `end`."""
    length = sum((e - s) ** 2 for s, e in zip(start, end)) ** 0.5
    base = tuple(e - (e - s) * head / length for s, e in zip(start, end))
    a = label(b, *start, start_text, rgb) if start_text else \
        tick(b, *start, rgb=rgb)
    m = tick(b, *base, rgb=rgb)
    tip = label(b, *end, end_text, rgb) if end_text else \
        tick(b, *end, rgb=rgb)
    for p, c, geo, ratio in ((a, m, GEO_PRISM, shaft),
                             (m, tip, GEO_CONE, shaft * 5.5)):
        b.add(type=TYPE_LINK, parent_id=p, child_id=c, branch_level=1,
              geometry=geo, ratio=ratio, color_r=rgb[0], color_g=rgb[1],
              color_b=rgb[2])


def add_axes(b, layout, first_year, last_year, team_label_every):
    """
    Three labelled axes per league, plus the league's title.  Label text runs
    to the RIGHT of its node and does not shrink with distance, so every label
    is kept short, and only every `team_label_every`-th team is NAMED (every
    team still gets a tick): at the spacing teams sit, naming all of them
    prints neighbouring codes over one another until you zoom in.
    """
    z_top = last_year - YEAR_ZERO
    for code, title in LEAGUES:
        lg = layout.leagues[code]
        x0, x1, y0, y1 = lg["x0"], lg["x1"], lg["y0"], lg["y1"]

        # Players: an arrow along x, with a tick at each initial letter.
        arrow(b, (x0, y0 - 14, 0), (x1 + 14, y0 - 14, 0),
              "", "", ARROW_HEAD, ARROW_SHAFT)
        label(b, x0, y0 - 27, 0, "PLAYERS A-Z, by last name")
        seen, last_x = set(), None
        for rank, s in enumerate(lg["players"]):
            initial = sort_key(s)[0][:1].upper()
            if initial and initial not in seen:
                seen.add(initial)
                x = x0 + X_STEP * rank
                # A rare initial can land a few units from its neighbour;
                # it still gets its tick, but only a roomy one is NAMED.
                if last_x is None or x - last_x >= LETTER_GAP:
                    label(b, x, y0 - 7, 0, initial)
                    last_x = x
                else:
                    tick(b, x, y0 - 7, 0)

        # Teams: an arrow along y, a labelled tick at every team.
        shaft_x = x0 - 24
        arrow(b, (shaft_x, y0 - 8, 0), (shaft_x, y1 + 30, 0),
              "", "TEAMS A-Z", ARROW_HEAD, ARROW_SHAFT)
        last_rank = len(lg["teams"]) - 1
        for team, rank in lg["team_rank"].items():
            if rank % team_label_every == 0 or rank == last_rank:
                label(b, shaft_x, y0 + Y_STEP * rank, 0, team)
            else:
                tick(b, shaft_x, y0 + Y_STEP * rank, 0)

        # Time: an arrow straight up from the front corner, with year ticks.
        tx, ty = x0 - 64, y0 - 40
        arrow(b, (tx, ty, 0), (tx, ty, z_top + 20),
              "", "TIME %d-%d" % (first_year, last_year),
              ARROW_HEAD, ARROW_SHAFT)
        first_tick = ((first_year + YEAR_STEP - 1) // YEAR_STEP) * YEAR_STEP
        for year in range(first_tick, last_year + 1, YEAR_STEP):
            label(b, tx, ty, year - YEAR_ZERO, str(year))

        label(b, x0, y0 - 48, 0, title, TITLE_RGB)
        label(b, x0, y0 - 70, 0,
              "%s players, %s seasons" % ("{:,}".format(len(lg["players"])),
                                          "{:,}".format(lg["seasons"])),
              AXIS_RGB)


def add_example(b, layout, seasons, sphere, first_year, last_year):
    """
    The labelled example glyph, the legend and the batting-average key, in
    front of the data.

    The glyph's own parts are not labelled where they sit: a label takes its
    node's colour and a cyan label on a cyan shape cannot be read.  Each part
    gets a label on a Point just OUTSIDE it, in the part's colour.  Offsets are
    in world units, derived from the same sizes the glyph is drawn at, so they
    track SPECIMEN_MAGNIFY.
    """
    al, nl = layout.leagues["AL"], layout.leagues["NL"]
    cx = (al["x1"] + nl["x0"]) / 2.0
    cy = al["y0"] - 190
    cz = 40.0
    pid, year, team = SPECIMEN
    chosen = next((s for s in seasons
                   if (s.pid, s.year, s.team) == (pid, year, team)), None)
    if chosen is None:               # a narrowed --first-year/--min-ab run
        chosen = max(seasons, key=lambda s: s.hr)
    who = "%s, %s %d" % (person_name(chosen), chosen.team, chosen.year)
    milli = avg_milli(chosen)
    # Its own text says it is the example, so it is never mistaken for the
    # real 1962 season it copies when that one is selected in the data.
    note = " (example glyph, %dx life size)" % SPECIMEN_MAGNIFY
    stem = "%s %s %d" % (person_name(chosen), chosen.team, chosen.year)
    add_glyph(b, chosen, (cx, cy, cz), sphere, magnify=SPECIMEN_MAGNIFY,
              parts={"avg": "%s Batting Avg: %s%s"
                            % (stem, format_avg(milli), note),
                     "2B": "%s 2B: %d%s" % (stem, chosen.d2, note),
                     "3B": "%s 3B: %d%s" % (stem, chosen.d3, note),
                     "HR": "%s HR: %d%s" % (stem, chosen.hr, note),
                     "RBI": "%s RBI: %d%s" % (stem, chosen.rbi, note)})

    root = float("%.6f" % (sphere.scale(milli / 1000.0) * SPECIMEN_MAGNIFY))
    counts = {"2B": chosen.d2, "3B": chosen.d3, "HR": chosen.hr,
              "RBI": chosen.rbi}
    rgb = {stat: c for stat, _l, _lon, c, _g, _p in CUBES}
    # Distance of each shape's far edge from the sphere's centre, in world
    # units: what child_placement wrote, times the root scale it divides by.
    far = {}
    for stat, _l, _lon, _c, geometry, per_unit in CUBES:
        _size, local_reach, half = child_placement(
            root, SPECIMEN_MAGNIFY, per_unit, geometry, counts[stat], stat)
        far[stat] = (local_reach * root, half)
    # Longitude 0/90/180/270 on the sphere lies along +x/+y/-x/-y.  Labels sit
    # just OUTSIDE their shape (text runs rightward from its node).
    label(b, cx + far["2B"][0] + far["2B"][1] + 4, cy, cz,
          "%d 2B" % counts["2B"], rgb["2B"])
    label(b, cx, cy + far["3B"][0] + far["3B"][1] + 9, cz,
          "%d 3B" % counts["3B"], rgb["3B"])
    label(b, cx - far["HR"][0] - far["HR"][1], cy - far["HR"][1] - 9, cz,
          "%d HR" % counts["HR"], rgb["HR"])
    label(b, cx, cy - far["RBI"][0] - far["RBI"][1] - 9, cz,
          "%d RBI" % counts["RBI"], rgb["RBI"])
    label(b, cx + root * 0.45, cy - root * 0.95 - 8, cz,
          "%s avg" % format_avg(milli), (230, 230, 230))
    label(b, cx - 70, cy - far["RBI"][0] - far["RBI"][1] - 60, cz,
          "%s, %dx life size" % (who, SPECIMEN_MAGNIFY), TITLE_RGB)

    # The legend, to the left of the glyph.  Each line steps down AND back, so
    # the lines stay apart seen from the side and from above.
    lines = (
        ("BATTING LEGEND", TITLE_RGB),
        ("Home runs: yellow cylinder", rgb["HR"]),
        ("RBI: orange dodecahedron", rgb["RBI"]),
        ("Doubles: cyan icosahedron", rgb["2B"]),
        ("Triples: magenta octahedron", rgb["3B"]),
        ("Batting average: sphere size and gray", (200, 200, 200)),
        ("shape size = count (RBI counts 1/5 as much)", AXIS_RGB),
    )
    for i, (text, color) in enumerate(lines):
        label(b, cx - 560, cy + 70 - 24 * i, cz + 30 - 9 * i, text, color)

    # The batting-average key, to the right: the bare sphere at six averages,
    # so the size ramp (squared) and the gray ramp can be read straight off.
    key_x0 = cx + 200
    label(b, key_x0 - 20, cy + 70, cz + 30,
          "BATTING AVERAGE KEY (%dx life size)" % KEY_MAGNIFY, TITLE_RGB)
    blank = Season("", "", "", 0, "", "", 1000, 0, 0, 0, 0, 0)
    for i, avg_value in enumerate(KEY_AVERAGES):
        k_milli = int(round(avg_value * 1000))
        x = key_x0 + i * KEY_SPACING
        add_glyph(b, blank._replace(h=k_milli), (x, cy, cz), sphere,
                  magnify=KEY_MAGNIFY,
                  parts={"avg": "Batting average %s" % format_avg(k_milli)})
        radius = sphere.scale(avg_value) * KEY_MAGNIFY
        label(b, x - 12, cy - radius - 10, cz, format_avg(k_milli),
              (230, 230, 230))


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def build_scene(seasons, first_year, last_year, avg_range=None,
                team_label_every=3):
    layout = Layout(seasons)
    avgs = [avg_milli(s) / 1000.0 for s in seasons]
    lo, hi = avg_range if avg_range else (min(avgs), max(avgs))
    sphere = Sphere(lo, hi)

    b = SceneBuilder()
    b.world()
    for s in sorted(seasons, key=lambda s: (s.lg, s.team, sort_key(s), s.year)):
        add_glyph(b, s, layout.position(s), sphere)
    data_rows = len(b.rows)
    add_axes(b, layout, first_year, last_year, max(1, team_label_every))
    add_example(b, layout, seasons, sphere, first_year, last_year)
    return b, layout, sphere, data_rows


def main(argv=None):
    global CHILD_SCALE
    ap = argparse.ArgumentParser(
        description="Export the Lahman batting table as a GlyphViz scene.")
    ap.add_argument("--out", default=str(HERE),
                    help="output folder (default: beside this script)")
    ap.add_argument("--name", default="MLB_Batting_History",
                    help="file stem; the node file is <name>_gv_node.csv")
    ap.add_argument("--first-year", type=int, default=1876,
                    help="1876 is the first National League season")
    ap.add_argument("--last-year", type=int, default=None,
                    help="default: the latest season in the table")
    ap.add_argument("--min-ab", type=int, default=100,
                    help="a season qualifies with MORE than this many "
                         "at-bats (default 100, which reproduces the "
                         "original file exactly)")
    ap.add_argument("--child-scale", type=float, default=CHILD_SCALE,
                    metavar="K",
                    help="world size of a child shape per count is "
                         "per-unit x K (default %g)" % CHILD_SCALE)
    ap.add_argument("--triples-gain", type=float, default=1.0, metavar="G",
                    help="multiply the triples (magenta octahedron) size by G "
                         "(default 1: the original never exaggerated it)")
    ap.add_argument("--team-labels-every", type=int, default=3, metavar="N",
                    help="name every Nth team on the team axis (default 3; "
                         "1 names them all, which only reads once zoomed in)")
    ap.add_argument("--avg-range", type=float, nargs=2, metavar=("LO", "HI"),
                    help="batting averages mapped to the smallest/largest "
                         "sphere (default: the lowest/highest in the scene)")
    ap.add_argument("--host", default=os.environ.get("MYSQL_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int,
                    default=int(os.environ.get("MYSQL_PORT", "3306")))
    ap.add_argument("--user", default=os.environ.get("MYSQL_USER", "root"))
    ap.add_argument("--password", default=os.environ.get("MYSQL_PASSWORD"))
    ap.add_argument("--database",
                    default=os.environ.get("MYSQL_DATABASE", "lahman"))
    args = ap.parse_args(argv)

    try:
        import pymysql
    except ImportError:
        sys.exit("This script needs PyMySQL:  pip install pymysql")
    CHILD_SCALE = args.child_scale
    STAT_GAIN["3B"] = args.triples_gain
    password = args.password
    if password is None:
        password = getpass.getpass("MySQL password for %s@%s: "
                                   % (args.user, args.host))
    try:
        conn = pymysql.connect(host=args.host, port=args.port, user=args.user,
                               password=password, database=args.database,
                               charset="utf8mb4")
    except RuntimeError as exc:           # MySQL 8 auth without TLS
        sys.exit("%s\n(for MySQL 8's default login:  pip install cryptography)"
                 % exc)
    except pymysql.MySQLError as exc:
        sys.exit("Could not connect to %s@%s/%s: %s"
                 % (args.user, args.host, args.database, exc))

    try:
        last = args.last_year
        if last is None:
            with conn.cursor() as cur:
                cur.execute("SELECT MAX(yearID) FROM batting")
                (last,) = cur.fetchone()
        seasons = fetch_seasons(conn, args.first_year, last, args.min_ab)
    except pymysql.ProgrammingError as exc:
        sys.exit("Query failed (%s).\nIs `batting` and `people` loaded into "
                 "`%s`?  Run lahman_to_mysql.py first." % (exc, args.database))
    finally:
        conn.close()
    if not seasons:
        sys.exit("No batting rows matched -- is the `batting` table loaded?")

    b, layout, sphere, data_rows = build_scene(
        seasons, args.first_year, last, args.avg_range,
        args.team_labels_every)
    path = Path(args.out) / ("%s_gv_node.csv" % args.name)
    b.write(path)

    print("%s seasons, %s nodes -> %s" % ("{:,}".format(len(seasons)),
                                         "{:,}".format(len(b.rows)), path))
    for code, title in LEAGUES:
        lg = layout.leagues[code]
        print("  %-16s %5d players  %3d teams  x %8.1f .. %8.1f   y %6.1f .. %6.1f"
              % (title, len(lg["players"]), len(lg["teams"]),
                 lg["x0"], lg["x1"], lg["y0"], lg["y1"]))
    print("  batting average %.3f (smallest sphere) .. %.3f (largest)"
          % (sphere.lo, sphere.hi))
    print("  years %d..%d  (z %d..%d)" % (args.first_year, last,
          args.first_year - YEAR_ZERO, last - YEAR_ZERO))


if __name__ == "__main__":
    main()
