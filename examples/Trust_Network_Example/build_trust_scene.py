"""
Build the Trust Network scene: the Bitcoin OTC web of trust, in which every
user is a HYPERGLYPH whose children are their own reputation.

Bitcoin OTC was an over-the-counter trading channel where people sent real
money to strangers, so they rated each other afterwards: a signed score from
-10 to +10, stamped with a time.  35,592 of those ratings survive, and one
in ten is negative -- which in a marketplace means somebody is calling
somebody else a thief.

What makes this a GlyphViz scene rather than a graph drawing is that a node
here is not a coloured dot.  Each user is a three-level glyph:

    branch_level 0   the user.  Shape = reputation class, colour = mean
                     rating received, size = how many ratings they carry.
                     Topology Sphere, so its children place by lon/lat.

    branch_level 1   two hubs, at the user's north and south poles: ratings
                     RECEIVED (north) and ratings GIVEN (south).  Sphere
                     topology as well, so their own children ring them.

    branch_level 2   five bins per hub, spaced around it at 72 degrees, one
                     per band of the trust scale.  Size = how many ratings
                     fell in that band.  Empty bands are hidden, so the
                     number of spokes is itself information.

A user's reputation is therefore legible as a SHAPE.  A trader with a fat
green spoke to the north has been vouched for many times; a red spoke to the
north means they have been accused, and a red spoke to the SOUTH means they
are the one doing the accusing.  Roots are world-aligned and carry no
rotation, so every glyph in the scene shares one frame -- north is always
"received", and a given band always sits at the same bearing.  That is what
makes the shapes comparable at a glance rather than merely decorative.

Usage
-----
    python build_trust_scene.py              # write in place
    python build_trust_scene.py --out DIR    # write elsewhere
    python build_trust_scene.py --fetch      # re-download the source

Source data (cached in data/):

  soc-sign-bitcoinotc.csv.gz   S. Kumar, F. Spezzano, V. S. Subrahmanian and
      C. Faloutsos, "Edge Weight Prediction in Weighted Signed Networks",
      ICDM 2016.  Distributed by SNAP, snap.stanford.edu/data.
"""

import argparse
import csv
import datetime as dt
import gzip
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from glyphviz_core.graph import Graph  # noqa: E402
from glyphviz_core.graph_layout import (  # noqa: E402
    fit_to_radius, forceatlas2_3d, layout_quality, pivot_mds_3d,
)

CRLF = chr(13) + chr(10)   # CSVs are written with CRLF line endings

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
SOURCE_NAME = "soc-sign-bitcoinotc.csv.gz"
SOURCE_URL = "https://snap.stanford.edu/data/soc-sign-bitcoinotc.csv.gz"

TYPE_WORLD, TYPE_GLYPH, TYPE_LINK = 0, 5, 7
GEO_CUBE, GEO_SPHERE, GEO_CONE = 1, 3, 5
GEO_DODEC, GEO_OCTA, GEO_TETRA, GEO_ICOSA = 9, 11, 13, 15
GEO_POINT, GEO_LINE = 22, 27
TOPO_NONE, TOPO_SPHERE = 0, 2
ROTATION_MODE_EULER_XYZ = 0

BACKGROUND = (6, 8, 15)
RADIUS = 200.0

# Only users with at least this many ratings RECEIVED are kept.  This is the
# filter that makes the hyperglyph honest: a user rated twice has no
# distribution to show, and a scene full of one-spoke glyphs would imply a
# structure that is not in the data.
MIN_RATINGS_RECEIVED = 8

# A user needs this many negative ratings before their accusers are drawn as
# cones rather than lines.  20 accounts clear it, carrying 504 cones between
# them -- see the link loop for why the shape is rationed.
CONE_THRESHOLD = 14

# Root glyph size -- and with it the whole hyperglyph, because children
# inherit the root's scale and the entire assembly is exactly proportional
# to it (measured: extent = 3.61 x root scale for the offsets below).  The
# cap keeps the biggest glyph clear of its neighbours: the layout's median
# nearest-neighbour spacing is about 21 world units, so 2.20 x 3.61 = 7.9
# still leaves a wide gap between two large adjacent traders.
ROOT_SCALE_MIN, ROOT_SCALE_MAX = 0.60, 2.30
HUB_ALTITUDE, HUB_SCALE = 1.4, 0.75
BIN_ALTITUDE, BIN_SCALE_MIN, BIN_SCALE_MAX = 1.0, 0.20, 0.55
GLYPH_EXTENT_PER_SCALE = 2.83   # measured through Scene.world_pos

# Every child is joined to its parent by a LIMB -- a type-7 link drawn as a
# stretched cylinder.  This is the Glyph Composer's own idiom for a
# hyperglyph (see LevelSpec.link_geo in glyphviz_core/glyph_recipe.py): "the
# link becomes the visible limb between them".  Without limbs the children
# read as loose dots floating near a node rather than as parts of it -- the
# first cut of this scene had none, and at any distance where two users were
# both in frame their spokes blended into one uniform field.  Limb radius is
# proportional to the root's scale because `ratio` is in WORLD units, so a
# fixed value would look like scaffolding on the small glyphs and thread on
# the large ones.
LIMB_ARM_RATIO = 0.085
LIMB_SPOKE_RATIO = 0.048
GEO_CYLINDER = 19

# The five bands of the trust scale.  The split points are the data's own:
# +1 is by far the most common rating (20,048 of 35,592) and means little
# more than "the trade completed", so it gets a muted band of its own rather
# than being averaged in with a genuine +5.  -10 is the second most common
# value in the whole file, and it is an accusation of theft.
BINS = [
    (-10, -5, "strong distrust", (232, 58, 58)),
    (-4, -1, "distrust", (226, 132, 60)),
    (1, 2, "routine trust", (128, 146, 178)),
    (3, 5, "trust", (96, 206, 148)),
    (6, 10, "strong trust", (86, 240, 118)),
]

# Reputation classes by mean rating received.  Shape as well as colour, so
# Select By > Geometry pulls out every distrusted account in one action.
CLASSES = [
    (-99.0, -0.5, "distrusted", GEO_TETRA, (232, 58, 58)),
    (-0.5, 0.75, "mixed", GEO_CUBE, (222, 140, 74)),
    (0.75, 1.5, "routine", GEO_SPHERE, (136, 152, 184)),
    (1.5, 2.5, "trusted", GEO_ICOSA, (96, 206, 148)),
    (2.5, 99.0, "highly trusted", GEO_DODEC, (86, 240, 118)),
]

NEUTRAL = (136, 152, 184)
LINK_POSITIVE = (66, 88, 128)
LINK_STRONG = (86, 210, 140)
LINK_NEGATIVE = (236, 62, 62)


# ---------------------------------------------------------------------------
# Source data
# ---------------------------------------------------------------------------

def fetch_source(force=False):
    import urllib.request
    DATA.mkdir(parents=True, exist_ok=True)
    target = DATA / SOURCE_NAME
    if target.exists() and not force:
        return
    print("  fetching %s" % SOURCE_NAME)
    req = urllib.request.Request(SOURCE_URL,
                                 headers={"User-Agent": "GlyphViz"})
    target.write_bytes(urllib.request.urlopen(req, timeout=120).read())


def read_ratings():
    """Raw rating events: source, target, rating, unix time (seconds)."""
    path = DATA / SOURCE_NAME
    if not path.exists():
        raise SystemExit("missing %s - run with --fetch" % path)
    rows = [line.split(",") for line in
            gzip.open(path, "rt").read().splitlines() if line.strip()]
    src = np.array([int(r[0]) for r in rows], dtype=np.int64)
    dst = np.array([int(r[1]) for r in rows], dtype=np.int64)
    rating = np.array([int(r[2]) for r in rows], dtype=np.int64)
    when = np.array([float(r[3]) for r in rows], dtype=np.float64)
    return src, dst, rating, when


def bin_of(rating):
    for index, (lo, hi, _name, _rgb) in enumerate(BINS):
        if lo <= rating <= hi:
            return index
    return 2


def class_of(mean_rating):
    for index, (lo, hi, _n, _g, _c) in enumerate(CLASSES):
        if lo <= mean_rating < hi:
            return index
    return len(CLASSES) - 1


def mean_color(mean):
    """Diverging slate -> red or slate -> green across the mean rating."""
    t = max(-1.0, min(1.0, float(mean) / 3.0))
    base = np.array(NEUTRAL, dtype=float)
    end = np.array((232, 58, 58) if t < 0 else (86, 240, 118), dtype=float)
    rgb = base + (end - base) * abs(t)
    return tuple(int(round(v)) for v in rgb)


# ---------------------------------------------------------------------------
# Scene writing
# ---------------------------------------------------------------------------

COLUMNS = [
    "id", "type", "parent_id", "branch_level", "child_id",
    "translate_x", "translate_y", "translate_z",
    "rotate_x", "rotate_y", "rotate_z",
    "scale_x", "scale_y", "scale_z",
    "color_r", "color_g", "color_b", "color_a",
    "geometry", "hide", "topo", "ratio", "rotation_mode",
    "ch_input_id", "text", "show_text",
    "render_mode", "fog_enabled", "fog_start", "fog_end",
    "tag_color_mode", "tag_color_r", "tag_color_g", "tag_color_b",
    "ref_grid_color_r", "ref_grid_color_g", "ref_grid_color_b",
]

DEFAULTS = {
    "parent_id": 0, "branch_level": 0, "child_id": 0,
    "translate_x": 0.0, "translate_y": 0.0, "translate_z": 0.0,
    "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
    "scale_x": 1.0, "scale_y": 1.0, "scale_z": 1.0,
    "color_r": 255, "color_g": 255, "color_b": 255, "color_a": 255,
    "geometry": GEO_SPHERE, "hide": 0, "topo": TOPO_NONE, "ratio": 0.1,
    "rotation_mode": ROTATION_MODE_EULER_XYZ, "ch_input_id": 0,
    "text": "", "show_text": 0,
    "render_mode": 0, "fog_enabled": 0, "fog_start": 0.0, "fog_end": 0.0,
    "tag_color_mode": 0, "tag_color_r": 255, "tag_color_g": 255,
    "tag_color_b": 200,
    "ref_grid_color_r": 56, "ref_grid_color_g": 56, "ref_grid_color_b": 71,
}


class SceneBuilder:
    def __init__(self):
        self.rows = []
        self._next_id = 1

    def add(self, **kw):
        row = dict(DEFAULTS)
        row.update(kw)
        row["id"] = self._next_id
        self._next_id += 1
        self.rows.append(row)
        return row["id"]

    def world(self, background, fog):
        return self.add(type=TYPE_WORLD, hide=1,
                        color_r=background[0], color_g=background[1],
                        color_b=background[2], color_a=255,
                        fog_enabled=1, fog_start=fog[0], fog_end=fog[1],
                        tag_color_mode=1,
                        ref_grid_color_r=20, ref_grid_color_g=22,
                        ref_grid_color_b=32)

    def write(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=COLUMNS,
                                    lineterminator="\r\n")
            writer.writeheader()
            for row in self.rows:
                writer.writerow(row)
        print("    %s  (%d rows)" % (path.name, len(self.rows)))


# ---------------------------------------------------------------------------
# The hyperglyph
# ---------------------------------------------------------------------------

def add_hyperglyph(builder, position, scale, geometry, color, text, pinned,
                   recv_bins, given_bins, recv_mean, given_mean,
                   force_all_bins=False, part_labels=None, who="",
                   channels=None):
    """
    One user, as a three-level glyph.  Returns the root node's id.

    The two hubs sit at the root's poles (latitude +-90 on its Sphere
    topology) and each hub's five bins ring it at 72 degree steps.  The ring
    lands perpendicular to its own arm for free: a Sphere parent gives its
    children an outward base rotation, so a hub standing at the north pole
    has its own equator facing out along the arm.

    EVERY node carries a text label -- root, hub, spoke and limb alike, and
    the labels restate in words exactly what the shape, size and colour
    already encode.  That redundancy is the point: reading a glyph is an
    acquired skill, and the fastest way to acquire it is to have the reading
    spelled out next to the thing being read.  Only a handful are PINNED
    (`show_text`); the rest appear on selection or with the T key.

    `channels` optionally supplies the ch_input_id for each part, keyed
    "root" / "recv" / "given" / "recv3" / "given0" and so on, so the parts
    can appear at the moment the data says they did.
    """
    labels = part_labels or {}
    chans = channels or {}
    root = builder.add(
        type=TYPE_GLYPH, parent_id=0, branch_level=0,
        translate_x=round(float(position[0]), 4),
        translate_y=round(float(position[1]), 4),
        translate_z=round(float(position[2]), 4),
        scale_x=round(scale, 4), scale_y=round(scale, 4),
        scale_z=round(scale, 4),
        color_r=color[0], color_g=color[1], color_b=color[2], color_a=255,
        geometry=geometry, topo=TOPO_SPHERE, ch_input_id=chans.get("root", 0),
        text=text, show_text=1 if pinned else 0)

    def limb(a, b, rgb, ratio, tag, channel):
        builder.add(type=TYPE_LINK, parent_id=a, child_id=b, branch_level=1,
                    geometry=GEO_CYLINDER, ratio=round(ratio * scale, 4),
                    color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
                    color_a=255, ch_input_id=channel, text=tag)

    for latitude, counts, mean, key, word in (
            (90.0, recv_bins, recv_mean, "recv", "RECEIVED"),
            (-90.0, given_bins, given_mean, "given", "GIVEN")):
        total = int(sum(counts))
        if not total and not force_all_bins:
            continue
        hub_rgb = mean_color(mean) if total else (100, 108, 128)
        hub_channel = chans.get(key, 0)
        hub_text = labels.get(key) or (
            "%s - %s %d ratings, mean %+.1f" % (who, word, total, mean))
        hub = builder.add(
            type=TYPE_GLYPH, parent_id=root, branch_level=1,
            translate_x=0.0, translate_y=latitude, translate_z=HUB_ALTITUDE,
            scale_x=HUB_SCALE, scale_y=HUB_SCALE, scale_z=HUB_SCALE,
            color_r=hub_rgb[0], color_g=hub_rgb[1], color_b=hub_rgb[2],
            color_a=255, geometry=GEO_OCTA, topo=TOPO_SPHERE,
            ch_input_id=hub_channel,
            text=hub_text, show_text=1 if labels.get(key) else 0)
        limb(root, hub, hub_rgb, LIMB_ARM_RATIO,
             "%s - %s arm" % (who, word.lower()), hub_channel)

        biggest = max(max(counts) if len(counts) else 0, 1)
        for index, count in enumerate(counts):
            if count == 0 and not force_all_bins:
                continue
            share = (count / biggest) ** 0.5
            size = BIN_SCALE_MIN + (BIN_SCALE_MAX - BIN_SCALE_MIN) * share
            if count == 0:
                size = BIN_SCALE_MIN
            lo, hi, band, rgb = BINS[index]
            slot = "%s%d" % (key, index)
            spoke_channel = chans.get(slot, hub_channel)
            spoke_text = labels.get(slot) or (
                "%s - %s %s (%+d to %+d): %d"
                % (who, word.lower(), band, lo, hi, count))
            spoke = builder.add(
                type=TYPE_GLYPH, parent_id=hub, branch_level=2,
                translate_x=index * 72.0, translate_y=0.0,
                translate_z=BIN_ALTITUDE,
                scale_x=round(size, 4), scale_y=round(size, 4),
                scale_z=round(size, 4),
                color_r=rgb[0], color_g=rgb[1], color_b=rgb[2], color_a=255,
                geometry=GEO_SPHERE, topo=TOPO_NONE,
                ch_input_id=spoke_channel,
                text=spoke_text, show_text=1 if labels.get(slot) else 0)
            limb(hub, spoke, rgb, LIMB_SPOKE_RATIO,
                 "%s - %s %s spoke" % (who, word.lower(), band),
                 spoke_channel)
    return root


# ---------------------------------------------------------------------------
# Legend and anatomy key
# ---------------------------------------------------------------------------

def build_legend(builder, class_counts, bin_counts, radius):
    """
    A world-space key: reputation classes, then the trust bands the glyph
    spokes stand for, then how the two kinds of link read.

    GlyphViz draws no screen-space overlay, so the legend is real geometry.
    Rows run down -Z (screen-up is +Z at the default framing) offset along
    +Y (screen-right), and hang off a single title node so the whole key
    drags as one object.  Headings are Point glyphs, which stay a couple of
    pixels wide and so cannot be mistaken for a swatch.
    """
    entries = []
    for index, (_lo, _hi, name, geo, rgb) in enumerate(CLASSES):
        entries.append(("swatch", geo, rgb,
                        "%s  (%d)" % (name, class_counts[index])))
    entries.append(("heading", None, None, "spokes = ratings by band"))
    for index, (lo, hi, name, rgb) in enumerate(BINS):
        span = "%+d" % lo if lo == hi else "%+d to %+d" % (lo, hi)
        entries.append(("swatch", GEO_SPHERE, rgb,
                        "%s  %s  (%d)" % (name, span, bin_counts[index])))
    entries.append(("heading", None, None, "links"))
    entries.append(("swatch", GEO_SPHERE, LINK_POSITIVE,
                    "thin line = a positive rating"))
    entries.append(("swatch", GEO_SPHERE, LINK_NEGATIVE,
                    "red line = a negative rating"))
    entries.append(("swatch", GEO_CONE, LINK_NEGATIVE,
                    "red cone = one aimed at a pilloried account"))

    rows_total = len(entries) + 2
    spacing = min(radius * 0.058, radius * 1.95 / max(rows_total, 1))
    glyph = radius * 0.013

    title = builder.add(
        type=TYPE_GLYPH, parent_id=0, branch_level=0,
        translate_x=0.0, translate_y=radius * 1.12, translate_z=radius * 1.02,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=214, color_g=220, color_b=236, color_a=255,
        geometry=GEO_POINT, ratio=0.15, topo=TOPO_NONE,
        text="Bitcoin OTC web of trust", show_text=1)
    builder.add(
        type=TYPE_GLYPH, parent_id=title, branch_level=1,
        translate_x=0.0, translate_y=0.0, translate_z=-spacing,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=150, color_g=158, color_b=178, color_a=255,
        geometry=GEO_POINT, ratio=0.12, topo=TOPO_NONE,
        text="shape + colour = reputation class", show_text=1)

    row = 1
    for kind, geo, rgb, text in entries:
        row += 1
        if kind == "heading":
            builder.add(
                type=TYPE_GLYPH, parent_id=title, branch_level=1,
                translate_x=0.0, translate_y=0.0, translate_z=-row * spacing,
                scale_x=1.0, scale_y=1.0, scale_z=1.0,
                color_r=150, color_g=158, color_b=178, color_a=255,
                geometry=GEO_POINT, ratio=0.12, topo=TOPO_NONE,
                text=text, show_text=1)
            continue
        builder.add(
            type=TYPE_GLYPH, parent_id=title, branch_level=1,
            translate_x=0.0, translate_y=0.0, translate_z=-row * spacing,
            scale_x=glyph, scale_y=glyph, scale_z=glyph,
            color_r=rgb[0], color_g=rgb[1], color_b=rgb[2], color_a=255,
            geometry=geo, topo=TOPO_NONE, text=text, show_text=1)
    return title


def build_anatomy_key(builder, radius):
    """
    One enlarged specimen glyph, with its parts labelled.

    A legend can name the colours but it cannot explain a three-level glyph;
    the quickest way to teach the shape is to stand a big one next to the
    scene with its poles called out.  All ten bins are forced visible here,
    unlike in the scene, because this is the template rather than a reading.
    """
    scale = radius * 0.072
    counts_recv = [1, 2, 6, 4, 2]
    counts_given = [0, 1, 5, 3, 1]
    add_hyperglyph(
        builder,
        position=(0.0, -radius * 1.52, radius * 0.30),
        scale=scale, geometry=GEO_ICOSA, color=NEUTRAL,
        text="one user, as a glyph", pinned=True,
        recv_bins=counts_recv, given_bins=counts_given,
        recv_mean=1.8, given_mean=1.2, force_all_bins=True,
        who="the key",
        part_labels={"recv": "north: ratings RECEIVED",
                     "given": "south: ratings GIVEN"})


# ---------------------------------------------------------------------------
# Incremental layout: the graph finding its shape as it grows
# ---------------------------------------------------------------------------

RELAX_PER_FRAME = 30
# Per-iteration displacement cap during the incremental run, as a fraction
# of the layout's RMS radius.  Much tighter than the 0.10 default because 30
# iterations compound inside a single frame: at 0.02 about 11 visible nodes
# per frame streaked more than 25 world units, and at 0.004 none do, while
# the finished layout is unchanged (spacing 21.5 vs 22.3).  Cheap insurance
# -- the cap bounds the path, never the equilibrium.
RELAX_MAX_STEP = 0.004


def layout_history(core, first_seen, scene_edges, edge_times, frame_times,
                   seed=7):
    """
    Re-run ForceAtlas2 at every frame on only the graph that existed then.

    The source data carries no coordinates at all -- just who rated whom,
    when -- so every position in this scene is something the solver invents.
    That means there is a real spatial history to show, and it is a better
    one than replaying the solver against the finished edge list: here the
    layout is *chasing* the data, re-arranging each frame because new
    ratings have arrived, which is how a force layout actually behaves when
    you stream a network into it.

    A trader who appears is seeded at the centroid of whoever has already
    rated them, plus a little jitter, rather than at a random point -- a
    live layout does the same, and it stops newcomers from flying in across
    the whole scene.

    Returns one (n, 3) array per frame, all in a SINGLE common frame of
    reference taken from the final layout, so the structure visibly grows
    outward instead of being renormalised to the same size every frame.
    """
    rng = np.random.default_rng(seed)
    n = core.n
    positions = rng.normal(scale=2.0, size=(n, 3))
    present = np.zeros(n, dtype=bool)

    neighbours = [[] for _ in range(n)]
    for a, b, _r in scene_edges:
        neighbours[a].append(b)
        neighbours[b].append(a)

    order = np.argsort(edge_times)
    sorted_times = np.asarray(edge_times)[order]
    history = []
    cursor = 0
    live_edges = []
    # Carried across frames.  Without this the speed controller restarts
    # cold on every call and the whole layout twitches once per frame:
    # measured at 71 world units of median per-frame motion in a scene of
    # radius 200, none of which was the coherent outward growth you want to
    # see -- it was the solver re-ramping 120 times.
    speed = speed_efficiency = None

    for t_frame in frame_times:
        while cursor < len(order) and sorted_times[cursor] <= t_frame:
            a, b, _r = scene_edges[order[cursor]]
            live_edges.append((a, b))
            cursor += 1

        arriving = np.flatnonzero((first_seen <= t_frame) & ~present)
        for node in arriving:
            known = [q for q in neighbours[node] if present[q]]
            if known:
                positions[node] = (positions[known].mean(axis=0)
                                   + rng.normal(scale=0.5, size=3))
            else:
                positions[node] = rng.normal(scale=2.0, size=3)
        present[arriving] = True

        members = np.flatnonzero(present)
        if len(members) > 2 and live_edges:
            index = {int(m): i for i, m in enumerate(members)}
            pairs = np.array([[index[a], index[b]] for a, b in live_edges
                              if a in index and b in index], dtype=np.int64)
            if len(pairs):
                sub = Graph(len(members), pairs)
                result = forceatlas2_3d(
                    sub, iterations=RELAX_PER_FRAME, scaling=2.0,
                    gravity=15.0, repulsion_falloff=2.0, max_step=RELAX_MAX_STEP,
                    positions=positions[members], seed=seed, tolerance=0.0,
                    speed=speed, speed_efficiency=speed_efficiency)
                positions[members] = result.positions
                speed = result.speed
                speed_efficiency = result.speed_efficiency
        history.append(positions.copy())

    # One transform for every frame, taken from the finished layout.
    final = history[-1]
    centre = final.mean(axis=0)
    reference = np.percentile(np.linalg.norm(final - centre, axis=1), 98.0)
    factor = RADIUS / max(reference, 1e-9)
    return [(frame - centre) * factor for frame in history]


# ---------------------------------------------------------------------------
# Channels: the network growing over real time
# ---------------------------------------------------------------------------

FRAMES = 120


def write_channels(scene_dir, stem, frames, user_tracks):
    """
    Write the ch-map / ch-tracks pair for the growth animation.

    Two kinds of channel, and the split is what keeps this affordable.

    **Bucket channels** (one per frame) each own a single `hide` track that
    is 1 before that frame and 0 from it onward.  Any node that comes into
    existence at that moment binds to it -- a hub, a spoke, a limb, an
    accusation.  Since a channel drives EVERY node bound to it, all 25
    pieces of a user's glyph and all 17,235 rating links between users cost
    120 tracks between them rather than one each.  That is the whole trick:
    appearance is a shared event, so it deserves a shared channel.

    **User channels** (one per trader) carry what is genuinely per-user and
    continuous: the root's colour as its reputation moves, and its size as
    ratings accumulate.  Their `hide` binding points back at the user's own
    bucket track, so a root appears in step with the rest of its glyph
    without needing a track of its own.

    Note `scale_x`, `scale_y` and `scale_z` are three bindings onto ONE
    track -- the ch-map is a list of (track, attribute) pairs, so a track
    may be read by as many attributes as want it.
    """
    scene_dir.mkdir(parents=True, exist_ok=True)
    n_users = len(user_tracks)

    map_path = scene_dir / ("%s_gv_ch-map.csv" % stem)
    with open(map_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator=CRLF)
        w.writerow(["id", "channel_id", "track_id", "attribute",
                    "track_table_id", "ch_map_table_id", "record_id"])
        row_id = 0
        for frame in range(frames):
            w.writerow([row_id, frame + 1, frame + 1, "hide", 0, 0, 0])
            row_id += 1
        for i, (bucket, scale_t, r_t, g_t, b_t, x_t, y_t, z_t) in                 enumerate(user_tracks):
            channel = frames + 1 + i
            for track, attr in ((bucket + 1, "hide"),
                                (scale_t, "scale_x"), (scale_t, "scale_y"),
                                (scale_t, "scale_z"),
                                (r_t, "color_r"), (g_t, "color_g"),
                                (b_t, "color_b"),
                                (x_t, "translate_x"), (y_t, "translate_y"),
                                (z_t, "translate_z")):
                w.writerow([row_id, channel, track, attr, 0, 0, 0])
                row_id += 1
    print("    %s  (%d bindings)" % (map_path.name, row_id))
    return map_path


def write_tracks(scene_dir, stem, frames, bucket_count, per_user):
    """
    ch-tracks: one row per frame, one column per track.

    Columns 1..frames are the bucket tracks; everything after is four
    columns per user (size, then red, green, blue).
    """
    total = bucket_count + 7 * len(per_user)
    path = scene_dir / ("%s_gv_ch-tracks.csv" % stem)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator=CRLF)
        w.writerow(["cyclecount"] + ["ch%d" % (t + 1) for t in range(total)])
        for frame in range(frames):
            row = [1.0 if frame < b else 0.0 for b in range(bucket_count)]
            for scale_series, r_s, g_s, b_s, xs, ys, zs in per_user:
                row.extend((scale_series[frame], r_s[frame], g_s[frame],
                            b_s[frame], xs[frame], ys[frame], zs[frame]))
            w.writerow([frame] + [format(v, ".3f") for v in row])
    print("    %s  (%d frames x %d tracks)" % (path.name, frames, total))
    return path


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_scene(out_dir, seed=7):
    print("Bitcoin_Trust")
    src, dst, rating, when = read_ratings()
    users = np.unique(np.concatenate([src, dst]))
    index = {u: i for i, u in enumerate(users)}
    si = np.array([index[u] for u in src])
    di = np.array([index[u] for u in dst])
    n = len(users)
    print("    source: %d users, %d ratings, %.0f%% negative"
          % (n, len(rating), 100 * (rating < 0).mean()))

    received = np.bincount(di, minlength=n)
    keep_mask = received >= MIN_RATINGS_RECEIVED
    inside = keep_mask[si] & keep_mask[di]

    graph = Graph(n, np.stack([si, di], axis=1)[inside],
                  np.abs(rating[inside]).astype(float))
    core, keep = graph.giant_component()
    print("    kept users with >= %d ratings received: %d users, %d edges"
          % (MIN_RATINGS_RECEIVED, core.n, core.m))

    # Per-user rating profiles, over the kept population only.
    order = {int(orig): i for i, orig in enumerate(keep)}
    recv_bins = np.zeros((core.n, len(BINS)), dtype=np.int64)
    given_bins = np.zeros((core.n, len(BINS)), dtype=np.int64)
    recv_sum = np.zeros(core.n)
    recv_n = np.zeros(core.n)
    given_sum = np.zeros(core.n)
    given_n = np.zeros(core.n)
    scene_edges = []
    edge_times = []
    for e in np.flatnonzero(inside):
        a, b, r = order.get(int(si[e])), order.get(int(di[e])), int(rating[e])
        if a is None or b is None:
            continue
        slot = bin_of(r)
        recv_bins[b, slot] += 1
        given_bins[a, slot] += 1
        recv_sum[b] += r
        recv_n[b] += 1
        given_sum[a] += r
        given_n[a] += 1
        scene_edges.append((a, b, r))
        edge_times.append(float(when[e]))
    recv_mean = recv_sum / np.maximum(recv_n, 1)
    given_mean = given_sum / np.maximum(given_n, 1)
    negatives = sum(1 for _a, _b, r in scene_edges if r < 0)
    print("    rating events drawn: %d (%d negative, %.0f%%)"
          % (len(scene_edges), negatives,
             100 * negatives / max(len(scene_edges), 1)))


    # Glyph size from ratings received, on a square root because the count
    # is heavy tailed (the busiest account carries 535).
    activity = recv_n.copy()
    share = np.sqrt(activity / max(activity.max(), 1.0))
    scales = ROOT_SCALE_MIN + (ROOT_SCALE_MAX - ROOT_SCALE_MIN) * share
    classes = np.array([class_of(m) for m in recv_mean])
    class_counts = np.bincount(classes, minlength=len(CLASSES))
    for i, (_lo, _hi, name, _g, _c) in enumerate(CLASSES):
        print("      %-15s %4d users" % (name, class_counts[i]))

    # Pin two kinds of label: the busiest accounts, and the worst-rated ones
    # with enough history to mean it.  Those are the two ends of the story.
    # Few, because show_text PINS a label on for good -- the viewport
    # cannot turn these off, only the node's own hide can.  This graph is
    # denser than the co-authorship ones and its hubs sit close together,
    # so a dozen pins overlap into a smear.
    pinned = set(np.argsort(-activity)[:4].tolist())
    eligible = np.flatnonzero(recv_n >= 10)
    pinned |= set(eligible[np.argsort(recv_mean[eligible])][:4].tolist())

    # ---- when each thing first exists -------------------------------
    # The animation is the network GROWING over its real five years, not a
    # replay of the solver, because this dataset is timestamped and its own
    # history is a better story than the layout's.  Each part of the scene
    # is stamped with the moment the data says it began: a user with their
    # first rating either way, a hub with the first rating in that
    # direction, a spoke with the first rating in that BAND, and an
    # accusation with the moment it was made.
    span_lo, span_hi = float(when.min()), float(when.max())

    def bucket_of(t):
        share = (float(t) - span_lo) / max(span_hi - span_lo, 1.0)
        return int(min(FRAMES - 1, max(0, round(share * (FRAMES - 1)))))

    first_seen = np.full(core.n, np.inf)
    hub_seen = {"recv": np.full(core.n, np.inf),
                "given": np.full(core.n, np.inf)}
    spoke_seen = {"recv": np.full((core.n, len(BINS)), np.inf),
                  "given": np.full((core.n, len(BINS)), np.inf)}
    for (a, b, r), t in zip(scene_edges, edge_times):
        slot = bin_of(r)
        for who_, key in ((b, "recv"), (a, "given")):
            first_seen[who_] = min(first_seen[who_], t)
            hub_seen[key][who_] = min(hub_seen[key][who_], t)
            spoke_seen[key][who_, slot] = min(spoke_seen[key][who_, slot], t)

    frame_times = np.linspace(span_lo, span_hi, FRAMES)
    history = layout_history(core, first_seen, scene_edges, edge_times,
                             frame_times, seed=seed)
    positions = history[-1]
    quality = layout_quality(positions)
    print("    incremental ForceAtlas2: %d frames x %d relax steps | "
          "final spacing p50 %.1f"
          % (FRAMES, RELAX_PER_FRAME, quality["spacing_p50"]))
    # Measured over nodes VISIBLE in both frames only.  Counting all of them
    # measures hidden newcomers teleporting from their random start to their
    # seeded position, which reports ~45 world units of churn for an
    # animation that is actually smooth -- a real trap, since those nodes
    # are not on screen when they move.
    travel = []
    jumpy = []
    for i in range(len(history) - 1):
        seen = first_seen <= frame_times[i]
        if seen.sum() < 2:
            continue
        step = np.linalg.norm(history[i + 1][seen] - history[i][seen], axis=1)
        travel.append(float(np.median(step)))
        jumpy.append(int((step > 25.0).sum()))
    print("    per-frame travel (visible nodes): median %.1f world units, "
          "%.1f nodes/frame moving over 25"
          % (float(np.median(travel)), float(np.mean(jumpy))))

    widest = scales.max() * GLYPH_EXTENT_PER_SCALE
    print("    hyperglyph extent: %.1f world units at the largest, against "
          "%.1f of spacing" % (widest, quality["spacing_p50"]))
    if widest > quality["spacing_p50"]:
        print("    WARNING: glyphs are wider than the gaps between them")


    # Per-frame reputation and volume for every trader, which is what the
    # four private tracks per user carry.  Cumulative over the ratings
    # RECEIVED so far, so a glyph swells as it earns a history and shifts
    # colour if that history turns against it.
    received_events = [[] for _ in range(core.n)]
    for (a, b, r), t in zip(scene_edges, edge_times):
        received_events[b].append((t, r))
    peak = max(recv_n.max(), 1.0)
    per_user = []
    for i in range(core.n):
        events = sorted(received_events[i])
        times = np.array([e[0] for e in events]) if events else np.zeros(0)
        vals = np.array([e[1] for e in events], dtype=float) if events             else np.zeros(0)
        counts = np.searchsorted(times, frame_times, side="right")
        sums = np.concatenate([[0.0], np.cumsum(vals)])[counts]
        means = sums / np.maximum(counts, 1)
        sizes = ROOT_SCALE_MIN + (ROOT_SCALE_MAX - ROOT_SCALE_MIN) *             np.sqrt(counts / peak)
        rgb = np.array([mean_color(m) for m in means], dtype=float)
        track = np.array([frame[i] for frame in history])
        per_user.append((sizes, rgb[:, 0], rgb[:, 1], rgb[:, 2],
                         track[:, 0], track[:, 1], track[:, 2]))


    # How many negative ratings each user RECEIVED -- the cone rule below
    # keys off this, not off the individual rating.
    negatives_received = np.zeros(core.n, dtype=np.int64)
    for _a, b, r in scene_edges:
        if r < 0:
            negatives_received[b] += 1
    pilloried = np.flatnonzero(negatives_received >= CONE_THRESHOLD)

    builder = SceneBuilder()
    builder.world(BACKGROUND, fog=(2.0 * RADIUS, 5.5 * RADIUS))

    node_ids = []
    user_tracks = []
    for i in range(core.n):
        cls = classes[i]
        who = "user %d" % users[keep[i]]
        text = ("%s - %d received (mean %+.1f), %d given - %s"
                % (who, int(recv_n[i]), recv_mean[i], int(given_n[i]),
                   CLASSES[cls][2]))
        # Four private tracks per user, laid out after the bucket block.
        base = FRAMES + 1 + 7 * i
        user_tracks.append((bucket_of(first_seen[i]), base, base + 1,
                            base + 2, base + 3, base + 4, base + 5,
                            base + 6))
        chans = {"root": FRAMES + 1 + i}
        for key in ("recv", "given"):
            if np.isfinite(hub_seen[key][i]):
                chans[key] = bucket_of(hub_seen[key][i]) + 1
            for slot in range(len(BINS)):
                t = spoke_seen[key][i, slot]
                if np.isfinite(t):
                    chans["%s%d" % (key, slot)] = bucket_of(t) + 1
        node_ids.append(add_hyperglyph(
            builder, positions[i], float(scales[i]), CLASSES[cls][3],
            mean_color(recv_mean[i]), text, i in pinned,
            recv_bins[i].tolist(), given_bins[i].tolist(),
            recv_mean[i], given_mean[i], who=who, channels=chans))

    # Links carry the rating twice over: by geometry, and by how loudly they
    # are drawn.
    #
    # A negative rating is the signal, and draws as a stretched CONE whose
    # apex lands on the accused -- an accusation is directed, and a cone is
    # the shape that says so.  Its radius is set against the GLYPH size, not
    # the link length: the first cut of this scene sized them as a fraction
    # of a 75-unit span, which is a needle end-on and a red girder wider
    # than a whole user once you fly in among them.
    #
    # A positive rating is mostly ambient.  +1 alone accounts for 12,042 of
    # the 17,235 ratings here and means little more than "the trade
    # completed", so it is drawn at low alpha and lets the eye through,
    # while a genuine +8 is bright and green.  Fading by strength keeps
    # every rating in the scene without letting the routine ones bury the
    # meaningful ones.
    cone_targets = set(pilloried.tolist())
    cones = 0
    for (a, b, r), t in zip(scene_edges, edge_times):
        stamp = dt.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d")
        label = ("%+d from user %d to user %d, %s"
                 % (r, users[keep[a]], users[keep[b]], stamp))
        channel = bucket_of(t) + 1
        if r < 0:
            # A cone is solid along its whole length, so one passing near the
            # camera is a red girder no matter how thin it is in world units
            # -- there is no radius that is both visible from outside the
            # scene and unobtrusive from inside it.  So the shape is spent
            # where it earns its keep: on the handful of accounts the
            # marketplace really turned on, each of which ends up inside a
            # visible starburst of arrows.  Every other negative rating is a
            # red line -- still there, still counted, but not solid, so the
            # rest of the volume stays flyable and the glyphs stay readable.
            magnitude = min(abs(r), 10) / 10.0
            if b in cone_targets:
                cones += 1
                builder.add(
                    type=TYPE_LINK, parent_id=node_ids[a],
                    child_id=node_ids[b], branch_level=1, geometry=GEO_CONE,
                    ratio=round(0.08 + 0.18 * magnitude, 3),
                    color_r=LINK_NEGATIVE[0], color_g=LINK_NEGATIVE[1],
                    color_b=LINK_NEGATIVE[2], color_a=235,
                    ch_input_id=channel, text=label)
            else:
                builder.add(
                    type=TYPE_LINK, parent_id=node_ids[a],
                    child_id=node_ids[b], branch_level=1, geometry=GEO_LINE,
                    ratio=0.05,
                    color_r=LINK_NEGATIVE[0], color_g=LINK_NEGATIVE[1],
                    color_b=LINK_NEGATIVE[2], color_a=150,
                    ch_input_id=channel, text=label)
        else:
            strength = min(r, 10) / 10.0
            rgb = [int(round(LINK_POSITIVE[c] +
                             (LINK_STRONG[c] - LINK_POSITIVE[c]) * strength))
                   for c in range(3)]
            builder.add(
                type=TYPE_LINK, parent_id=node_ids[a], child_id=node_ids[b],
                branch_level=1, geometry=GEO_LINE, ratio=0.05,
                color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
                color_a=int(round(30 + 95 * strength)),
                ch_input_id=channel, text=label)

    print("    negative links: %d as cones (accusations that stuck), "
          "%d as lines, converging on %d accounts"
          % (cones, negatives - cones, len(pilloried)))

    bin_counts = recv_bins.sum(axis=0)
    build_legend(builder, class_counts, bin_counts, RADIUS)
    build_anatomy_key(builder, RADIUS)

    scene_dir = out_dir / "Bitcoin_Trust"
    builder.write(scene_dir / "Bitcoin_Trust_gv_node.csv")
    write_channels(scene_dir, "Bitcoin_Trust", FRAMES, user_tracks)
    write_tracks(scene_dir, "Bitcoin_Trust", FRAMES, FRAMES, per_user)
    print("    animation spans %s to %s in %d frames"
          % (dt.datetime.utcfromtimestamp(span_lo).strftime("%Y-%m"),
             dt.datetime.utcfromtimestamp(span_hi).strftime("%Y-%m"), FRAMES))
    return core, positions


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(HERE))
    ap.add_argument("--fetch", action="store_true",
                    help="re-download the source archive into data/")
    args = ap.parse_args()
    fetch_source(force=args.fetch)
    build_scene(Path(args.out))
    print("done -> %s" % args.out)


if __name__ == "__main__":
    main()
