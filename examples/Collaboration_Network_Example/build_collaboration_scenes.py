"""
Build the Collaboration Network scenes: 3D force-directed graph layouts of
scientific co-authorship, laid out with GlyphViz's own ForceAtlas2.

Two scenes, from two of Mark Newman's published co-authorship networks:

  Condensed_Matter/           3,900-odd physicists, one glyph each, positioned
                              by ForceAtlas2 in three dimensions and coloured
                              by Louvain community.  The flagship: a static
                              constellation you fly through.

  Network_Science_Emergence/  the 379-author giant component of the network
                              science community, with the SOLVER ITSELF bound
                              to Channels — press play and the layout
                              crystallises out of a random cloud.

Both are ordinary GlyphViz scenes with no topology involved: a force layout
produces free world positions, and a node with no parent has
translate_x/y/z = its world position exactly.  So every author is a ROOT
node with topo None, and every collaboration is a type-7 Link between two of
them.  Nothing here needs placement offsets, topo_scale, or a World Grid.

Usage
-----
    python build_collaboration_scenes.py                 # write in place
    python build_collaboration_scenes.py --out DIR       # write elsewhere
    python build_collaboration_scenes.py --only condmat

Source data (cached in data/, re-downloadable with --fetch):

  cond-mat-2005.gml  M. E. J. Newman, "The structure of scientific
                     collaboration networks", PNAS 98, 404-409 (2001);
                     this edition covers arXiv cond-mat preprints posted
                     1995-01-01 to 2005-03-31.  Weighted per Newman,
                     Phys. Rev. E 64, 016132 (2001).
  netscience.gml     M. E. J. Newman, "Finding community structure in
                     networks using the eigenvectors of matrices",
                     Phys. Rev. E 74, 036104 (2006).
"""

import argparse
import colorsys
import csv
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from glyphviz_core.graph import (  # noqa: E402
    Graph, core_numbers, filter_edges, louvain_communities, modularity,
)
from glyphviz_core.graph_layout import (  # noqa: E402
    fit_to_radius, forceatlas2_3d, layout_quality, pivot_mds_3d,
)

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

SOURCES = {
    "cond-mat-2005.zip":
        "https://websites.umich.edu/~mejn/netdata/cond-mat-2005.zip",
    "netscience.zip":
        "https://websites.umich.edu/~mejn/netdata/netscience.zip",
}

# Node/geometry constants (see glyphviz-skill/references/node-csv-format.md).
TYPE_WORLD, TYPE_GLYPH, TYPE_LINK = 0, 5, 7
GEO_SPHERE_SOLID = 3
GEO_POINT = 22
GEO_LINE = 27
TOPO_NONE = 0
ROTATION_MODE_EULER_XYZ = 0

# Shape carries community membership as well as colour, so that Select By >
# Geometry pulls out a whole sub-network in one action — colour alone is
# only readable, not selectable.
#
# Four families are deliberately left out.  Pin stands on its apex rather
# than straddling its origin, so a pin node would sit visibly off the
# position the solver computed for it.  Grid is a flat plate that vanishes
# edge-on.  Point is a fixed-pixel sprite that ignores scale, so it would
# not carry the degree encoding.  Mesh needs an imported file.  That leaves
# nine solids and their nine wireframes.
#
# Solids come first: they are the most distinct from each other and the best
# looking, so the largest communities get them.  Sphere is held back out of
# the cycle entirely and used for everything past the end of it, so "select
# all spheres" means "the communities with no shape of their own" instead of
# colliding with community 0.
COMMUNITY_GEOMETRIES = [
    1,    # Cube
    13,   # Tetrahedron
    11,   # Octahedron
    5,    # Cone
    19,   # Cylinder
    7,    # Torus
    15,   # Icosahedron
    9,    # Dodecahedron
    0,    # Cube wire
    12,   # Tetrahedron wire
    10,   # Octahedron wire
    4,    # Cone wire
    18,   # Cylinder wire
    6,    # Torus wire
    14,   # Icosahedron wire
    8,    # Dodecahedron wire
    2,    # Sphere wire
]
GEO_TORUS = (6, 7)
TORUS_RATIO = 0.35   # the 0.1 default draws a torus as an almost invisible hoop


def community_geometry(index):
    """Shape for a community by size rank; Sphere once the cycle runs out."""
    if index < len(COMMUNITY_GEOMETRIES):
        return COMMUNITY_GEOMETRIES[index]
    return GEO_SPHERE_SOLID


def geometry_ratio(geometry):
    """`ratio` a geometry needs to render sensibly at glyph size."""
    return TORUS_RATIO if geometry in GEO_TORUS else 0.1

BACKGROUND = (7, 9, 16)
FRINGE_COLOR = (96, 106, 128)     # communities past the palette
BRIDGE_COLOR = (74, 84, 108)      # edges that cross communities

# World-unit radius each layout is fitted into.  Glyph sizes, fog distances
# and edge thickness are all expressed against these, so a scene stays
# internally consistent if one of them is changed.
RADIUS_CONDMAT = 200.0
RADIUS_NETSCI = 70.0


def fog_for(radius):
    """
    Fog start/end for a layout of the given radius.

    Auto-framing parks the camera at a couple of radii out, so the scene
    spans roughly 1x to 3x radius in depth from there.  Starting the fade at
    2x and finishing at 5.5x leaves the near face fully lit and washes the
    far side into the background — which is the depth cue that keeps a 3D
    graph from reading as a flat tangle.
    """
    return (2.0 * radius, 5.5 * radius)


# ---------------------------------------------------------------------------
# Source data
# ---------------------------------------------------------------------------

def fetch_sources(force=False):
    """Download the source archives into data/ if they are not there."""
    import urllib.request
    DATA.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        target = DATA / name
        if target.exists() and not force:
            continue
        print("  fetching %s" % name)
        req = urllib.request.Request(url, headers={"User-Agent": "GlyphViz"})
        target.write_bytes(urllib.request.urlopen(req, timeout=120).read())


_NODE_RE = re.compile(r'node\s*\[\s*id\s+(\d+)\s*label\s+"([^"]*)"')
_EDGE_RE = re.compile(
    r'edge\s*\[\s*source\s+(\d+)\s*target\s+(\d+)\s*value\s+([0-9.eE+-]+)')


def read_gml(zip_name, member):
    """
    Parse one of Newman's weighted co-authorship GML files.

    These files are strictly regular — every node block is id + label, every
    edge block is source + target + value — so two regexes read them
    correctly and much faster than a general GML parser.  `Graph` handles
    deduplication and orientation, so nothing here has to.
    """
    path = DATA / zip_name
    if not path.exists():
        raise SystemExit(
            "missing %s - run with --fetch to download it" % path)
    text = zipfile.ZipFile(path).read(member).decode("utf-8", "replace")

    names = {}
    for raw_id, label in _NODE_RE.findall(text):
        names[int(raw_id)] = label
    pairs = _EDGE_RE.findall(text)
    edges = np.array([(int(a), int(b)) for a, b, _ in pairs], dtype=np.int64)
    weights = np.array([float(v) for _, _, v in pairs], dtype=np.float64)

    n = max(names) + 1 if names else 0
    labels = [names.get(i, "") for i in range(n)]
    return Graph(n, edges, weights), labels


def tidy_name(raw):
    """
    "BARABASI, A" -> "Barabasi, A".

    Newman's files are uppercase and ASCII-folded.  Title-casing them makes
    labels readable in the viewport; the surname stays first so a viewer can
    scan an alphabetical cluster.  Control characters are stripped because
    one bad byte silently breaks tag parsing downstream.
    """
    raw = unicodedata.normalize("NFKC", raw)
    raw = "".join(c for c in raw if unicodedata.category(c)[0] != "C")
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) == 2 and parts[1]:
        surname = parts[0].title()
        initials = parts[1].upper()
        return "%s, %s" % (surname, initials)
    return raw.title()


# ---------------------------------------------------------------------------
# Colour
# ---------------------------------------------------------------------------

def community_palette(count):
    """
    A categorical palette sized to the communities that actually matter.

    Hues step by the golden angle rather than evenly, so *consecutive*
    community ranks land far apart on the colour wheel — which is what
    matters here, because the ranks are ordered by size and the largest few
    communities are the ones a viewer compares side by side.  Three tiers of
    saturation/value break ties once the hues start coming back around.

    Everything is kept bright and mid-to-high value because the scene
    background is nearly black; ANTz's PALETTE_20 is not used since it
    contains both black and white.
    """
    tiers = [(0.72, 1.00), (0.95, 0.86), (0.52, 0.98)]
    out = []
    for i in range(count):
        hue = (0.07 + i * 0.6180339887) % 1.0
        sat, val = tiers[i % len(tiers)]
        r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
        out.append((int(round(r * 255)), int(round(g * 255)),
                    int(round(b * 255))))
    return out


def dim(rgb, factor):
    return tuple(int(round(c * factor)) for c in rgb)


def community_names(graph, labels, communities, count):
    """
    Name each community after its most-connected member.

    Louvain hands back numbered partitions, which tells a viewer nothing.
    The highest-degree author inside a community is both a genuine
    description of it — these are collaboration groups, and their busiest
    member is who the group is built around — and a name a reader of the
    field will recognise, which is what makes the legend worth reading.
    """
    degrees = graph.degrees()
    out = []
    for c in range(count):
        members = np.flatnonzero(communities == c)
        if not len(members):
            out.append(("(empty)", 0))
            continue
        top = members[np.argmax(degrees[members])]
        out.append((tidy_name(labels[top]), int(len(members))))
    return out


def build_legend(builder, palette, entries, fringe_members, radius, title,
                 subtitle=None):
    """
    A world-space colour key: a column of coloured spheres, each labelled.

    GlyphViz draws no screen-space overlay, so a legend has to be part of
    the scene — which is fine, because tag text is billboarded and stays
    readable from any angle.  The column runs down **-Z** because +Z is
    screen-up at the default framing, so it reads as a vertical list from
    wherever the camera ends up; it is offset along +Y (screen-right) to
    clear the graph.

    The entries are CHILDREN of the title node, so the whole legend is one
    movable group: drag the title marker and the key follows.  The title is
    a Point glyph rather than a sphere precisely so it does not look like
    another category.

    Sizes are proportional to the layout radius, which keeps the on-screen
    result identical between a 200-unit scene and a 70-unit one — both are
    framed to fill the viewport, so only the ratio matters.
    """
    # Rows are spaced for comfortable reading, but never so generously that
    # the column outgrows the layout it belongs to: a legend taller than the
    # scene pushes the auto-framing to fit ITSELF, shrinking the graph and
    # still clipping its own last rows.  32 communities plus headings is 36
    # rows, which is exactly where that starts to bite.
    rows_total = (len(entries) + (1 if subtitle else 0)
                  + (1 if fringe_members else 0) + 1)
    spacing = min(radius * 0.058, radius * 1.95 / max(rows_total, 1))
    glyph = radius * 0.012

    title_id = builder.add(
        type=TYPE_GLYPH, parent_id=0, branch_level=0,
        # Just outside the layout on screen-right.  Kept close in rather than
        # pushed clear of it: tag text is drawn to the RIGHT of its anchor and
        # is not part of the bounding box auto-framing measures, so a legend
        # parked further out simply hangs its labels off the edge of the view.
        translate_x=0.0, translate_y=radius * 1.12, translate_z=radius * 1.02,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=210, color_g=216, color_b=232, color_a=255,
        geometry=GEO_POINT, ratio=0.15, topo=TOPO_NONE,
        text=title, show_text=1)

    # Two heading lines rather than one long one: tag text is drawn to the
    # right of its anchor and is never wrapped or measured by auto-framing,
    # so a heading much longer than the widest entry simply runs off the
    # side of the view.  Both headings use Point glyphs, which stay a couple
    # of pixels wide and so cannot be mistaken for a category swatch.
    row = 0
    if subtitle:
        row += 1
        builder.add(
            type=TYPE_GLYPH, parent_id=title_id, branch_level=1,
            translate_x=0.0, translate_y=0.0, translate_z=-row * spacing,
            scale_x=1.0, scale_y=1.0, scale_z=1.0,
            color_r=150, color_g=158, color_b=178, color_a=255,
            geometry=GEO_POINT, ratio=0.12, topo=TOPO_NONE,
            text=subtitle, show_text=1)

    # Each swatch is drawn with its community's ACTUAL geometry, so the key
    # doubles as a shape key: find the shape here, then Select By > Geometry
    # to grab that whole sub-network in the scene.
    for index, (name, size) in enumerate(entries):
        row += 1
        r, g, b = palette[index]
        geo = community_geometry(index)
        builder.add(
            type=TYPE_GLYPH, parent_id=title_id, branch_level=1,
            translate_x=0.0, translate_y=0.0, translate_z=-row * spacing,
            scale_x=glyph, scale_y=glyph, scale_z=glyph,
            color_r=r, color_g=g, color_b=b, color_a=255,
            geometry=geo, ratio=geometry_ratio(geo), topo=TOPO_NONE,
            text="%s  (%d)" % (name, size), show_text=1)

    if fringe_members:
        row += 1
        builder.add(
            type=TYPE_GLYPH, parent_id=title_id, branch_level=1,
            translate_x=0.0, translate_y=0.0, translate_z=-row * spacing,
            scale_x=glyph, scale_y=glyph, scale_z=glyph,
            color_r=FRINGE_COLOR[0], color_g=FRINGE_COLOR[1],
            color_b=FRINGE_COLOR[2], color_a=255,
            geometry=GEO_SPHERE_SOLID, topo=TOPO_NONE,
            text="smaller communities  (%d)" % fringe_members, show_text=1)

    # The edge colouring needs saying too: it is the one thing in the scene
    # a viewer cannot work out from the node key alone.
    row += 1
    builder.add(
        type=TYPE_GLYPH, parent_id=title_id, branch_level=1,
        translate_x=0.0, translate_y=0.0, translate_z=-row * spacing,
        scale_x=glyph * 0.8, scale_y=glyph * 0.8, scale_z=glyph * 0.8,
        color_r=BRIDGE_COLOR[0], color_g=BRIDGE_COLOR[1],
        color_b=BRIDGE_COLOR[2], color_a=255,
        geometry=GEO_SPHERE_SOLID, topo=TOPO_NONE,
        text="pale links join two communities", show_text=1)
    return title_id


def report_quality(positions, communities, scales):
    """
    Print the numbers that decide whether the scene is legible.

    Worth having in the build output rather than a one-off script: the
    layout parameters that keep glyphs from interpenetrating are specific to
    each graph, so a future change to the filters or the fit radius needs
    this visible to catch the regression it causes.
    """
    q = layout_quality(positions, communities,
                       glyph_diameter=2.0 * np.asarray(scales))
    print("    spacing p50 %.2f (p5 %.2f) | glyph diameter median %.2f"
          " | overlapping %.0f%% | separation %.2f"
          % (q["spacing_p50"], q["spacing_p5"], 2.0 * float(np.median(scales)),
             100 * q.get("overlap", 0.0), q.get("separation", float("nan"))))


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
    "geometry": GEO_SPHERE_SOLID, "hide": 0, "topo": TOPO_NONE,
    "ratio": 0.1, "rotation_mode": ROTATION_MODE_EULER_XYZ,
    "ch_input_id": 0, "text": "", "show_text": 0,
    "render_mode": 0, "fog_enabled": 0, "fog_start": 0.0, "fog_end": 0.0,
    "tag_color_mode": 0, "tag_color_r": 255, "tag_color_g": 255,
    "tag_color_b": 200,
    "ref_grid_color_r": 56, "ref_grid_color_g": 56, "ref_grid_color_b": 71,
}


class SceneBuilder:
    """Accumulates rows and writes a minimal-dialect node CSV."""

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

    def world(self, background, fog=None, tag_color_mode=1):
        """
        The optional type-0 row carrying scene-wide look.

        Fog is on by default in these scenes and is doing real work rather
        than decoration: occlusion is the reason 3D graph layouts have a bad
        reputation, and fading distant nodes into the background is the
        cheapest depth cue there is.  It is what makes the far side of the
        constellation read as far rather than as clutter.
        """
        kw = dict(type=TYPE_WORLD, hide=1,
                  color_r=background[0], color_g=background[1],
                  color_b=background[2], color_a=255,
                  tag_color_mode=tag_color_mode,
                  ref_grid_color_r=22, ref_grid_color_g=24,
                  ref_grid_color_b=34)
        if fog:
            kw.update(fog_enabled=1, fog_start=fog[0], fog_end=fog[1])
        return self.add(**kw)

    def write(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\r\n")
            writer.writeheader()
            for row in self.rows:
                writer.writerow(row)
        print("    %s  (%d rows)" % (path.name, len(self.rows)))


def node_scales(degrees, low=0.25, high=1.40):
    """
    Glyph size from degree, on a square root.

    Degree is heavy-tailed — the top author here has an order of magnitude
    more collaborators than the median — so a linear map would leave almost
    every node at the floor.  A square root compresses the tail while
    keeping the hubs visibly bigger, and the floor stays well above the 0.2
    at which a glyph gets hard to click.

    The absolute numbers are tied to `fit_to_radius`: what matters is glyph
    diameter against the layout's nearest-neighbour spacing, and these
    defaults are set so that the median glyph is roughly a quarter of the
    median gap.  Change the fit radius and these have to move with it.
    """
    d = np.asarray(degrees, dtype=np.float64)
    if not len(d) or d.max() <= 0:
        return np.full(len(d), low)
    t = np.sqrt(d / d.max())
    return low + (high - low) * t


def build_graph_scene(builder, graph, labels, positions, communities,
                      palette_size, label_count, edge_alpha,
                      scale_low=0.25, scale_high=1.40):
    """
    Write author glyphs plus collaboration links into `builder`.

    Returns the list of node ids, indexed the same way the graph is, so a
    caller can bind channels to them afterwards.
    """
    degrees = graph.degrees()
    scales = node_scales(degrees, scale_low, scale_high)
    palette = community_palette(palette_size)
    colors = [palette[c] if c < palette_size else FRINGE_COLOR
              for c in communities]

    # EVERY author carries their name in `text` — each glyph is a person and
    # ought to be able to say so, whether by selection, the node table, or
    # turning tag labels on.  What varies is `show_text`, which PINS a label
    # on regardless of the viewport's tag settings: only the biggest hubs get
    # that, because 3,900 pinned labels would be a white sheet.  Everyone
    # else's name appears on demand.
    ranked = np.argsort(-degrees)
    pinned = set(int(i) for i in ranked[:label_count])

    node_ids = []
    for i in range(graph.n):
        r, g, b = colors[i]
        geo = community_geometry(communities[i])
        node_ids.append(builder.add(
            type=TYPE_GLYPH, parent_id=0, branch_level=0,
            translate_x=round(float(positions[i, 0]), 4),
            translate_y=round(float(positions[i, 1]), 4),
            translate_z=round(float(positions[i, 2]), 4),
            scale_x=round(float(scales[i]), 4),
            scale_y=round(float(scales[i]), 4),
            scale_z=round(float(scales[i]), 4),
            color_r=r, color_g=g, color_b=b, color_a=255,
            geometry=geo, ratio=geometry_ratio(geo), topo=TOPO_NONE,
            text=tidy_name(labels[i]), show_text=1 if i in pinned else 0))

    # Edges: an edge inside a community takes that community's colour dimmed,
    # so clusters read as solid bodies; an edge BETWEEN communities takes a
    # neutral grey, so the bridges — the interesting part of a collaboration
    # network — stay visible as structure rather than disappearing into
    # whichever cluster happens to be brighter.
    for (a, b), _w in zip(graph.edges, graph.weights):
        ca, cb = communities[a], communities[b]
        if ca == cb:
            rgb = dim(colors[a], 0.62)
        else:
            rgb = BRIDGE_COLOR
        builder.add(
            type=TYPE_LINK, parent_id=node_ids[a], child_id=node_ids[b],
            branch_level=1, geometry=GEO_LINE, ratio=0.05,
            color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
            color_a=edge_alpha)
    return node_ids


# ---------------------------------------------------------------------------
# Scene 1 — Condensed Matter
# ---------------------------------------------------------------------------

def build_condensed_matter(out_dir, seed=7):
    print("Condensed_Matter")
    graph, labels = read_gml("cond-mat-2005.zip", "cond-mat-2005.gml")
    print("    source: %d authors, %d collaborations" % (graph.n, graph.m))

    # Two filters, in this order and for two different reasons.  The weight
    # filter keeps only repeated collaboration: Newman's weight counts a
    # shared paper as 1/(authors-1), so w >= 0.8 means "these two have really
    # worked together" and drops the single 40-author paper that would
    # otherwise contribute a 40-clique of people who have never met.  The
    # 3-core then removes the fringe that survives that — authors hanging off
    # the structure by one or two threads, who add rows and no shape.
    strong = filter_edges(graph, 0.8)
    core, keep = strong.subgraph(np.flatnonzero(core_numbers(strong) >= 3))
    core, keep2 = core.giant_component()
    keep = keep[keep2]
    labels = [labels[i] for i in keep]
    print("    filtered: %d authors, %d collaborations (avg degree %.1f)"
          % (core.n, core.m, 2 * core.m / core.n))

    communities = louvain_communities(core, seed=seed)
    print("    %d communities, modularity Q = %.3f"
          % (communities.max() + 1, modularity(core, communities)))

    # repulsion_falloff=2.0 is the whole reason this scene reads as a
    # network instead of a hairball.  ForceAtlas2's published repulsion
    # falls off as 1/d, which is the 2D Coulomb law; in three dimensions
    # that is far too long-ranged, and it packs 4,000 authors into a dense
    # ball with a few filaments whipping off it.  1/d^2 is the 3D law and
    # gives an evenly filled volume with the communities visibly apart.
    # See `graph_layout.forceatlas2_3d` for the measurements.
    start = pivot_mds_3d(core, pivots=64, seed=seed)
    result = forceatlas2_3d(core, iterations=900, scaling=2.0, gravity=15.0,
                            repulsion_falloff=2.0, positions=start, seed=seed,
                            tolerance=1e-5)
    print("    ForceAtlas2: %d iterations%s"
          % (result.iterations, " (converged)" if result.converged else ""))
    positions = fit_to_radius(result.positions, RADIUS_CONDMAT)

    report_quality(positions, communities,
                   node_scales(core.degrees(), 0.25, 1.40))

    builder = SceneBuilder()
    builder.world(BACKGROUND, fog=fog_for(RADIUS_CONDMAT), tag_color_mode=1)
    # 32 rather than a dozen: Louvain splits this graph into 58 communities
    # of remarkably even size (177 down to 73), so a small palette would
    # leave 44% of the authors in undifferentiated grey and the scene would
    # read as mostly fringe.  32 covers 79% and the golden-angle hues stay
    # distinguishable between spatial neighbours, which is what matters.
    build_graph_scene(builder, core, labels, positions, communities,
                      palette_size=32, label_count=30, edge_alpha=110,
                      scale_low=0.25, scale_high=1.40)
    total = int(communities.max()) + 1
    named = community_names(core, labels, communities, 32)
    build_legend(builder, community_palette(32), named,
                 fringe_members=int((communities >= 32).sum()),
                 radius=RADIUS_CONDMAT,
                 title="Shape + colour = a collaboration group",
                 subtitle="each named by its busiest member")
    print("    legend: %d named communities, %d in the grey remainder"
          % (32, total - 32))
    builder.write(out_dir / "Condensed_Matter" /
                  "Condensed_Matter_gv_node.csv")
    return core, communities, positions


# ---------------------------------------------------------------------------
# Scene 2 — Network Science, with the solver on Channels
# ---------------------------------------------------------------------------

def build_network_science(out_dir, seed=5, frames=140):
    print("Network_Science_Emergence")
    graph, labels = read_gml("netscience.zip", "netscience.gml")
    core, keep = graph.giant_component()
    labels = [labels[i] for i in keep]
    print("    giant component: %d authors, %d collaborations"
          % (core.n, core.m))

    communities = louvain_communities(core, seed=seed)
    print("    %d communities, modularity Q = %.3f"
          % (communities.max() + 1, modularity(core, communities)))

    # Deliberately NOT seeded with pivot MDS: this scene exists to show the
    # solver working, and starting from an already-sane embedding would skip
    # the part worth watching.  Every iteration is captured and resampled
    # below.  Same 3D repulsion law as the Condensed Matter scene; lighter
    # gravity because this component is small and sparse and does not need
    # holding together.
    result = forceatlas2_3d(core, iterations=700, scaling=2.0, gravity=5.0,
                            repulsion_falloff=2.0, seed=seed,
                            snapshot_every=1, tolerance=0.0)
    print("    ForceAtlas2: %d iterations, %d snapshots"
          % (result.iterations, len(result.snapshots)))

    frames_xyz = _convergence_frames(result, frames, radius=RADIUS_NETSCI)
    positions = frames_xyz[-1]
    report_quality(positions, communities,
                   node_scales(core.degrees(), 0.35, 1.90))

    builder = SceneBuilder()
    builder.world(BACKGROUND, fog=fog_for(RADIUS_NETSCI), tag_color_mode=1)
    node_ids = build_graph_scene(builder, core, labels, positions,
                                 communities, palette_size=14,
                                 label_count=24, edge_alpha=125,
                                 scale_low=0.35, scale_high=1.90)
    named = community_names(core, labels, communities, 14)
    build_legend(builder, community_palette(14), named,
                 fringe_members=int((communities >= 14).sum()),
                 radius=RADIUS_NETSCI,
                 title="Shape + colour = a collaboration group",
                 subtitle="each named by its busiest member")

    # One channel per author, three tracks each (x, y, z).  The links need no
    # channels at all: a Link draws between its two endpoints' CURRENT world
    # positions, so all 914 of them follow for free.
    for i, nid in enumerate(node_ids):
        builder.rows[nid - 1]["ch_input_id"] = i + 1

    scene_dir = out_dir / "Network_Science_Emergence"
    builder.write(scene_dir / "Network_Science_Emergence_gv_node.csv")
    _write_channels(scene_dir, "Network_Science_Emergence", frames_xyz)
    return core, communities, positions


def _convergence_frames(result, frames, radius):
    """
    Turn a solver run into animation frames.

    Three things happen here, each fixing something that makes a raw
    snapshot dump look wrong:

    1. **Non-linear resampling.**  A force layout does most of its visible
       work in the first few dozen iterations and then creeps.  Sampling
       iterations evenly would spend most of the animation on a picture that
       has stopped changing, so frames are drawn on a power-law schedule
       that is dense early and sparse late.

    2. **Per-frame rescaling.**  ForceAtlas2 expands as it runs, by a factor
       of many.  Applying the final frame's scale to all of them would leave
       the first two thirds of the animation as a dot.  Each frame is fitted
       to the same radius instead, so what the viewer sees is structure
       rearranging rather than a zoom-out.

    3. **Procrustes alignment to the final frame.**  The layout has no
       preferred orientation and drifts rotationally over 700 iterations.
       Aligning every frame to the finished one means the constellation
       assembles in place, and the animation ends exactly on the static
       positions stored in the node CSV.
    """
    snaps = [p for _i, p in result.snapshots]
    if not snaps:
        raise SystemExit("solver produced no snapshots")

    total = len(snaps)
    t = np.linspace(0.0, 1.0, frames) ** 2.2
    picks = np.unique((t * (total - 1)).round().astype(int))
    picks = np.append(picks, total - 1)
    picks = np.unique(picks)

    fitted = [fit_to_radius(snaps[i], radius) for i in picks]
    reference = fitted[-1]
    return [_align_to(p, reference) for p in fitted]


def _align_to(pos, reference):
    """Optimal rotation (no reflection) taking `pos` onto `reference`."""
    u, _s, vt = np.linalg.svd(pos.T @ reference)
    rot = u @ vt
    if np.linalg.det(rot) < 0:          # reject reflections
        u[:, -1] *= -1
        rot = u @ vt
    return pos @ rot


def _write_channels(scene_dir, stem, frames_xyz):
    """
    Write the ch-map / ch-tracks pair.

    Layout: author i owns channel i+1 and tracks 3i+1..3i+3, bound to
    translate_x, translate_y and translate_z.  translate_* is in
    `_TRANSFORM_FIELDS`, so a frame change re-places the node and everything
    drawn from its position — including every link that touches it.
    """
    n = frames_xyz[0].shape[0]
    scene_dir.mkdir(parents=True, exist_ok=True)

    map_path = scene_dir / ("%s_gv_ch-map.csv" % stem)
    with open(map_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\r\n")
        w.writerow(["id", "channel_id", "track_id", "attribute",
                    "track_table_id", "ch_map_table_id", "record_id"])
        row_id = 0
        for i in range(n):
            for axis, attr in enumerate(
                    ("translate_x", "translate_y", "translate_z")):
                w.writerow([row_id, i + 1, 3 * i + axis + 1, attr, 0, 0, 0])
                row_id += 1
    print("    %s  (%d bindings)" % (map_path.name, 3 * n))

    tracks_path = scene_dir / ("%s_gv_ch-tracks.csv" % stem)
    with open(tracks_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\r\n")
        w.writerow(["cyclecount"] + ["ch%d" % (t + 1) for t in range(3 * n)])
        for frame, pos in enumerate(frames_xyz):
            flat = pos.reshape(-1)
            w.writerow([frame] + [format(v, ".3f") for v in flat])
    print("    %s  (%d frames x %d tracks)"
          % (tracks_path.name, len(frames_xyz), 3 * n))


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(HERE),
                    help="output directory (default: this example folder)")
    ap.add_argument("--only", choices=["condmat", "netsci"],
                    help="build just one scene")
    ap.add_argument("--fetch", action="store_true",
                    help="re-download the source archives into data/")
    args = ap.parse_args()

    if args.fetch:
        fetch_sources(force=True)
    else:
        fetch_sources(force=False)

    out = Path(args.out)
    if args.only != "netsci":
        build_condensed_matter(out)
    if args.only != "condmat":
        build_network_science(out)
    print("done -> %s" % out)


if __name__ == "__main__":
    main()
