"""
Kissing in 24 Dimensions: the Leech lattice seen through the HCS.

Bosonic string theory lives in 26 dimensions: the string vibrates in the 24
directions across it, and the other two are the sheet it sweeps out (time and
the string's own length). Those 24 directions are where the Leech lattice
lives, the most symmetric arrangement of points in 24-D. Its spheres each
touch 196,560 others, the most possible in 24-D.

The scene shows 759 of those 196,560 neighbours: one family, 2 on the eight
places of a Golay octad and 0 on the other sixteen. Each is a 24-D point, and
the HCS draws it as one leaf on 24 nested circles: every coordinate is one
circle, 0 sits at 0 deg and 2 at 90 deg (scale s = 2).

    cloud     759 glyphs at their 24-D HCS leaves, coloured by their angle to
              the octad being walked: gold = it, orange = touching it (60 deg,
              the kissing angle; 280 of them), blue = 75.5 deg (448),
              violet = 90 deg (30)
    chain     the 24 nested HCS circles as a real node chain, one spinner per
              dimension, walking from octad to octad
    kisses    280 threads from the walked octad to the octads it touches
    right     the 24 places as a 4 x 6 grid (the MOG layout), the walked
              octad's eight places lit, and its coordinates
    top       the story, one caption per octad visited
    bottom    the colour legend

Layout: the app frames a scene on the bounding box of its nodes, and a
pinned label runs RIGHT of its node in screen pixels. So two hidden anchors
fix the box at WIDTH, the story's anchors sit on its left edge (the text
runs in over the empty top band), and the right board sits on the right
edge, its text running out into the margin the camera leaves.

    python generate_leech_kissing.py [--out DIR]    -> Leech_Kissing/  (~2 s)
"""
import argparse
import colorsys
from pathlib import Path

import numpy as np

import leech
import string_kit as kit
from string_kit import GEO_CUBE, GEO_POINT, GEO_CYLINDER, TYPE_LINK

HERE = Path(__file__).resolve().parent
STEM = "Leech_Kissing"

S = 2.0                     # HCS scale: the coordinate value 2 lands at 90 deg
R1 = 4.0                    # radius of dimension 1's circle (world units)
RATIO = 0.85                # each nested circle's radius / its parent's
POINT = 0.3                 # cloud glyph size
LIFT = 30.0                 # world z of the turn frame: everything above the ground grid
WIDTH = 64.0                # the framed box's width (wall y from -WIDTH/2 to +WIDTH/2)
CLOUD_Y = -7.0              # wall y of the cloud's middle
LINE = 1.8                  # caption line pitch (world units, about 18 px at the opening view)

HOLD, MOVE = 225, 75        # frames: hold on an octad, walk to the next
STEPS = 6                   # octads visited per loop
FRAMES = STEPS * (HOLD + MOVE)

BG = (8, 9, 20)
# Rainbow palette (palette_id 2) indices: one color_index track per glyph.
PALETTE = 2
CAT_INDEX = {8: 16, 4: 8, 2: 72, 0: 100}
CAT_COLOR = {8: (255, 193, 0), 4: (255, 96, 0), 2: (0, 153, 255), 0: (185, 0, 255)}
KISS = (255, 150, 60, 110)
LEAF = (255, 255, 255, 255)

# The tour: each step's relation to the previous octad (places shared).
TOUR_CAPS = (4, 2, 0, 4, 2)
CAP_WORDS = {4: "shares 4 places: it TOUCHES the last (60 deg)",
             2: "shares 2 places: 75.5 deg from the last",
             0: "shares no places: 90 deg from the last"}

# One caption per octad visited (lines of at most ~80 characters).
STORY = (
    ("Bosonic string theory needs 26 dimensions: the string vibrates in 24,",
     "and the other 2 are the sheet it sweeps out (time, and its own length).",
     "The 24 are home to the Leech lattice. Each of its spheres touches",
     "196,560 others: the most possible in 24-D (proved in 1979)."),
    ("These 759 glyphs are one family of those 196,560 neighbours:",
     "2 on the 8 places of a Golay octad, 0 on the other 16.",
     "Each glyph is ONE point in 24 dimensions."),
    ("HCS: every coordinate is a circle, 0 at 0 deg and 2 at 90 deg.",
     "Circle k+1 rides the point chosen on circle k, 0.85x smaller.",
     "The white leaf at the end of all 24 circles is the 24-D point."),
    ("Two octads sharing 4 places: dot product 4 x 2 x 2 = 16, half the length^2 of 32,",
     "so they sit 60 deg apart -- and equal spheres 60 deg apart just TOUCH.",
     "Orange threads: the 280 octads touching the walked one."),
    ("Every octad sees the same crowd: 280 touching, 448 at 75.5 deg, 30 at 90 deg.",
     "That sameness is symmetry: the Mathieu group M24 carries any octad",
     "onto any other, and the Leech lattice's own symmetry group contains it."),
    ("All 196,560 come in 3 shapes: 97,152 like these (with signs), 98,304 of",
     "the form (-3, 1^23), and 1,104 of the form (4, 4, 0^22).",
     "A bosonic string curled up on this lattice has 324 + 196,560 = 196,884",
     "states at level 2: the number that started Monstrous Moonshine."),
)


def dim_colors(n=24):
    """One hue per dimension, the same on its HCS circle and its board cell."""
    return [tuple(int(round(255 * c)) for c in colorsys.hsv_to_rgb(k / n, 0.75, 1.0))
            for k in range(n)]


def pick_tour(o):
    """Octad 0, then each next octad the first one sharing TOUR_CAPS[j]
    places with the last and not yet visited."""
    caps = o @ o.T
    tour = [0]
    for c in TOUR_CAPS:
        last = tour[-1]
        tour.append(next(int(k) for k in np.flatnonzero(caps[last] == c) if k not in tour))
    return tour


def schedule():
    """Per frame: the step (index into the tour) and the blend u from the
    previous octad (0) to this step's (1). Step j walks over frames
    [j*(H+M), j*(H+M)+M), then holds. Step 0 walks in from the last octad,
    so the loop closes."""
    f = np.arange(FRAMES)
    step = f // (HOLD + MOVE)
    t = f % (HOLD + MOVE)
    u = kit.ease(np.minimum(t / MOVE, 1.0))
    return step, u


def places(row):
    return " ".join(str(k + 1) for k in np.flatnonzero(row))


def build(out_dir):
    o = leech.octads()
    vecs = 2 * o
    ang = kit.hcs_angle(vecs, S)                        # (759, 24): 0 or 90 deg
    leaves = kit.hcs_chain(ang, R1, RATIO)
    centre = 0.5 * (leaves.min(axis=0) + leaves.max(axis=0))
    caps = o @ o.T
    tour = pick_tour(o)
    step, u = schedule()
    target = np.array(tour)[step]
    prev = np.array(tour)[(step - 1) % STEPS]
    hold = u >= 1.0

    cols = dim_colors()
    sc = kit.Scene(FRAMES, extra_cols=("palette_id", "color_index"))
    turn, wall = kit.frames_of_reference(sc, BG, LIFT)
    for side in (-1, 1):
        sc.node(wall, pos=(0.0, side * WIDTH / 2, 0.0), hide=1, geometry=GEO_POINT,
                text=f"framing anchor ({'left' if side < 0 else 'right'} edge of the opening view)")

    # The HCS frame: circle 1 stands in the wall's plane, facing the camera,
    # and the chain's origin shifts so the cloud's middle is at (0, CLOUD_Y, 0).
    face = sc.node(wall, pos=(0.0, CLOUD_Y, 0.0), rot=(0, 90, 0), hide=1, geometry=GEO_POINT,
                   text="HCS frame: circle 1 faces the viewer")
    hcs = sc.node(face, pos=tuple(-centre), hide=1, geometry=GEO_POINT,
                  text="HCS origin: centre of dimension 1's circle")

    # ---- the cloud ----
    cloud_ids = []
    for k in range(len(o)):
        cap = caps[target, k]                           # (frames,)
        idx = np.vectorize(CAT_INDEX.get)(cap)
        ch = sc.channel([(sc.track(idx), "color_index")])
        cloud_ids.append(sc.node(
            hcs, pos=tuple(leaves[k]), scale=POINT, color=(*CAT_COLOR[int(cap[0])], 230),
            ch=ch, palette_id=PALETTE, color_index=int(idx[0]),
            text=f"octad {k + 1}: 2 on places {places(o[k])}, 0 elsewhere "
                 "-- one 24-D Leech-lattice vector"))

    # ---- kisses: threads to the 280 touching octads, while holding ----
    for j, a in enumerate(tour):
        vis = hold & (step == j)
        ch = kit.hide_channel(sc, vis)
        for b in np.flatnonzero(caps[a] == 4):
            sc.node(cloud_ids[a], type=TYPE_LINK, child_id=cloud_ids[b], ratio=0.02,
                    color=KISS, geometry=GEO_CYLINDER, ch=ch, hide=int(not vis[0]),
                    text=f"octad {a + 1} touches octad {b + 1} (4 shared places, 60 deg)")

    # ---- the chain: 24 nested HCS circles walking the tour ----
    chain_ang = (1 - u)[:, None] * ang[prev] + u[:, None] * ang[target]   # (frames, 24)
    circle = kit.unit_circle()
    parent, radius = hcs, R1
    for d in range(24):
        level = sc.node(parent, pos=(1.0, 0.0, 0.0) if d else (0.0, 0.0, 0.0),
                        rot=(90.0, 0.0, 0.0) if d else (0.0, 0.0, 0.0),
                        scale=RATIO if d else R1, hide=1, geometry=GEO_POINT,
                        text=f"dimension {d + 1} circle frame")
        kit.polyline(sc, level, circle, (*cols[d], 200),
                     f"dimension {d + 1}: HCS circle (0 at 0 deg, 2 at 90 deg, "
                     "infinity at 180 deg)", ratio=0.06)
        spin = sc.node(level, rot=(0.0, 0.0, float(chain_ang[0, d])), hide=1, geometry=GEO_POINT,
                       ch=sc.channel([(sc.track(chain_ang[:, d], 3), "rotate_z")]),
                       text=f"dimension {d + 1} spinner: rotate_z = the HCS angle of x{d + 1}")
        if d == 23:
            sc.node(spin, pos=(1.0, 0.0, 0.0), scale=0.6 / radius, color=LEAF,
                    text="the leaf: the walked octad's 24-D point")
        else:
            sc.node(spin, pos=(1.0, 0.0, 0.0), scale=0.15 / radius, color=(*cols[d], 255),
                    text=f"x{d + 1} chosen -- the centre of dimension {d + 2}'s circle")
        parent, radius = spin, radius * RATIO

    # ---- right board: the 24 places, MOG layout (4 rows x 6 columns) ----
    rb = kit.board(sc, wall, (0.0, 0.5 * WIDTH - 12.0, 12.0), label="places board")
    pitch = 2.4
    kit.caption(sc, rb, (-1.2, 2.6), "The 24 places (MOG layout); lit = the walked octad",
                color=kit.TITLE, size=0.2)
    for d in range(24):
        col, row = d // 4, d % 4
        x, y = pitch * col, -pitch * row
        sc.node(rb, pos=(x, y, 0.0), scale=(1.5, 1.5, 0.1), color=(*cols[d], 50),
                geometry=GEO_CUBE, show_text=1, text=f"{d + 1}")
        lit = vecs[target, d] > 0
        sc.node(rb, pos=(x, y, 0.15), scale=(1.35, 1.35, 0.1), color=(*cols[d], 255),
                geometry=GEO_CUBE, ch=kit.hide_channel(sc, lit), hide=int(not lit[0]),
                text=f"place {d + 1} lit: x{d + 1} = 2")
    y0 = -pitch * 3 - 2.6
    for j, a in enumerate(tour):
        vis = step == j
        x = [str(int(v)) for v in vecs[a]]
        rows = [f"octad {a + 1}, a 24-D vector of length^2 32:",
                "x1-12  = " + " ".join(x[:12]),
                "x13-24 = " + " ".join(x[12:]),
                (f"from octad {tour[j - 1] + 1}: " + CAP_WORDS[TOUR_CAPS[j - 1]]) if j else
                f"from octad {tour[-1] + 1} (the loop closes)"]
        for i, t in enumerate(rows):
            kit.caption(sc, rb, (-1.2, y0 - LINE * i), t, visible=vis, size=0.2)

    # ---- bottom: the legend ----
    lb = kit.board(sc, wall, (0.0, -0.5 * WIDTH, -22.0), label="legend board")
    legend = [("gold: the walked octad", CAT_COLOR[8]),
              ("orange: touching it, 60 deg (280 of the 759)", CAT_COLOR[4]),
              ("blue: 75.5 deg from it (448)", CAT_COLOR[2]),
              ("violet: 90 deg from it (30)", CAT_COLOR[0])]
    for i, (t, c) in enumerate(legend):
        kit.caption(sc, lb, (0.0, -LINE * i), t, color=c, size=0.35)

    # ---- top: the story ----
    tb = kit.board(sc, wall, (0.0, -0.5 * WIDTH, 30.0), label="story board")
    kit.caption(sc, tb, (0.0, 0.0), "Kissing in 24 dimensions: the Leech lattice, through the HCS",
                color=kit.TITLE, size=0.3)
    for j, lines in enumerate(STORY):
        vis = step == j
        for i, t in enumerate(lines):
            kit.caption(sc, tb, (0.0, -LINE * (i + 1.5)), t, visible=vis, size=0.2)

    sc.write(out_dir, STEM)
    return sc, tour


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / STEM))
    args = ap.parse_args()
    sc, tour = build(args.out)
    print(f"{STEM}: {len(sc.rows)} nodes, {len(sc.tracks)} tracks, {FRAMES} frames; "
          f"tour {[t + 1 for t in tour]} -> {args.out}")


if __name__ == "__main__":
    main()
