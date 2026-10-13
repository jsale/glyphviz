# MLB batting history, 1876-2025

Every American League and National League player-season, one hyperglyph each:
40,342 of them in the 1871-2025 Lahman database, 187,530 nodes. An update of
the ANTz batting-statistics visualisation, rebuilt from the database instead of
from a spreadsheet.

## Getting the data

The scene is built from the SABR Lahman Baseball Database. It is not included
here (it is large, and you should have the current release): download the
comma-delimited version from <https://sabr.org/lahman-database/> and unzip it
so its CSV files sit in a folder named `lahman_1871-2025_csv` beside these
scripts, or point `--csv-dir` at wherever they are.

The database is copyright SABR, donated by Sean Lahman, and licensed under
Creative Commons Attribution-ShareAlike 3.0 Unported. The scene file here is
derived from it, so it carries the same licence.

## Running it

```
pip install pymysql            # + cryptography if MySQL 8 refuses the login
set MYSQL_PASSWORD=...         # or you will be prompted

python lahman_to_mysql.py           --csv-dir <folder of Lahman CSVs> --user root
python lahman_batting_to_glyphviz.py --user root
```

The first script makes one table per CSV, named like the file, lower-cased
(`Batting.csv` -> `batting`, `FieldingOFsplit.csv` -> `fieldingofsplit`), in a
`lahman` database it creates if needed. Column types are inferred from the data;
a blank cell is NULL; `playerID`, `yearID`, `teamID`, `lgID` and `franchID` are
indexed. An existing table is skipped unless `--replace` is given, and a table
that fails part-way is dropped again rather than left half loaded.

The second reads `batting` joined to `people` and writes
`MLB_Batting_History_gv_node.csv` beside the scripts (about 25 MB; it ships ready-made in this folder). Open it in GlyphViz, or
drag it onto the window. Labels are inline `text`, so there is no tag file.
Select a glyph, or rubber-band a group, to read it; **T** toggles labels.

Options worth knowing: `--min-ab`, `--first-year`, `--last-year`,
`--team-labels-every`, `--avg-range LO HI`, `--child-scale`,
`--triples-gain`. Settings can come from
`MYSQL_HOST/PORT/USER/PASSWORD/DATABASE`.

## The glyph

| part | encodes |
|---|---|
| sphere, centre | batting average: its **size** (square of the position in the scene's range) and its **gray** (linear, 90 to 255) |
| cyan icosahedron | doubles |
| magenta octahedron | triples |
| yellow cylinder | home runs |
| orange dodecahedron | RBI |

Each shape's size is its count: 0.05 x 0.25 world units per double, triple or
home run, and 0.01 x 0.25 per RBI. They are children of the sphere on a Point
topology, at 0/90/180/270 degrees, each placed just clear of the sphere's skin.
A count of zero draws no shape.

**Sizes do not depend on the sphere.** A child normally inherits its parent's
scale; here each child's scale is divided by the sphere's, so a 22-home-run
cylinder is the same size on a .200 hitter and a .400 hitter. Distances are set
the same way, in world units. (Checked through GlyphViz's own engine on 10,936
sampled shapes: size and distance are right to 4e-7, and each shape/count pair
has exactly one world size.) The sphere is never smaller than scale 0.01, since
the division needs a nonzero parent. `--child-scale` changes the overall size
of the shapes (default 0.25, which keeps a typical glyph about as big as it was
when sizes were inherited).

Position: **x** = player (alphabetical by last name, 0.1 per player), **y** =
team (alphabetical by team id, 10 per team), **z** = year (1 per year,
`year - 1870`). Each league is ranked on its own: the American League starts at
x = -180 and the National League one quarter of an AL-width beyond its end.

The scene also carries the axes (with letter ticks, team ticks and year
ticks), each league's title, the labelled example glyph (George Altman, CHN
1962, drawn 60x life size), a legend, and a batting-average key.

## What was read out of the original files, and what was not

The ANTz node file was decoded rather than guessed at, then checked by
rebuilding its 1876-2012 range from the new database (`--last-year 2012`):

* **Qualifying seasons: more than 100 at-bats, not 150.** The original title
  card says 150, but the AL/NL seasons 1876-2012 with `AB > 100` number exactly
  34,681, which is exactly the original's glyph count. 100 is the default;
  `--min-ab 150` gives what the title card says.
* y matches the original on every one of 33,350 matched seasons, z likewise.
  x is within 0.5 units for 98% (rank correlation 0.9999995); the rest are
  players whose slot shifted by one because the database has been corrected
  since 2012.
* Cube scales match on 99.7% or better; the exceptions are revised statistics.
* The gap between the leagues is exactly 0.25 x the AL's width.
* The label format ("Alfredo Amezaga ANA 2003 Batting Avg: .210") is the
  original's, for every part of every glyph. Names follow the current
  database, so a few differ in spelling from 2012 ("A. J. Ellis").

**Two deliberate differences** from the original:

1. *Sphere size and gray are normalised over both leagues together.* The
   original normalised each league separately (AL .086-.426, NL .058-.440), so
   the same average drew a slightly different sphere on each side. Here a .300
   hitter looks the same in both leagues. `--avg-range` pins the range.
2. *The gray ramp starts at 90, not 0.* Labels take their node's colour, and a
   label in near-black cannot be read on this background.

## Tuning one stat while you look at it

Each stat has its own geometry and no other node uses it, so **Select By >
Geometry > 11: Octahedron > Select All Matching** selects every triples shape
and nothing else. Then arm **Size** (with "Lock X/Y/Z together" ticked) and drag
a handle: Size multiplies each selected node's scale by the same factor, so the
counts stay proportional and the whole stat grows or shrinks together. (Typing a
number into the Properties scale boxes would not do this; it writes the same
absolute value to every selected node and flattens the data.) 19 Cylinder, 9
Dodecahedron and 15 Icosahedron pick out home runs, RBI and doubles the same
way.

The original did not exaggerate triples: its triples cubes used the same
0.05 per unit as doubles and home runs. They looked small because the counts
are (at most 36, against 67 doubles and 73 home runs). To bake an exaggeration
in, `--triples-gain 2` doubles the octahedron's size.

## Testing

Both scripts were run against a real MySQL 8.4 server: all 27 tables loaded
with row counts matching the CSVs (batting 128,598; people 24,270), and the
export was loaded and rendered by GlyphViz's own loader and renderer.
