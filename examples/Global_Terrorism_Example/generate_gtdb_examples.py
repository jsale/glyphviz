#!/usr/bin/env python3
r"""
generate_gtdb_examples.py
=========================
Turns the Global Terrorism Database (START/University of Maryland, 1970-2020,
~210k incident rows) into three ready-to-load GlyphViz scenes that share one
visual vocabulary: the 9 GTD attack types keep the same legend colors
everywhere, so what you learn reading one scene transfers to the others.

Scene 1 -- Organization_Profiles/  (node + tag)
------------------------------------------------
A wall of "profile rosette" hyperglyphs, one per terrorist organization
(default: every org with >= 10 attributed attacks), arrayed in X/Z and
sorted most-active first (top-left, reading order). Each rosette is a
fixed layout you learn once and can then read at a glance on any org:

  center octahedron   size = log(total attacks); color = the org's
                      DOMINANT attack type (legend color)
  clock ring          12 objects evenly spaced (360/12 = 30 deg apart) on
                      a vertical wire ring at fixed positions -- Assassin-
                      ation at 12 o'clock, then clockwise in GTD attacktype
                      order (Armed Assault, Bombing, Hijacking, Barricade,
                      Kidnapping, Infrastructure, Unarmed, Unknown), then
                      solid red sphere = total killed (log), orange wire
                      sphere = total wounded (log), blue wire sphere =
                      geographic reach (log #countries struck). Size =
                      log(count); zero/absent categories leave a gap.
  sparkline           activity timeline under the glyph, separate from the
                      ring: a Plot-topology polyline of attacks per 5-year
                      bin (1970-2020), normalized to the org's own peak --
                      the *shape* of a campaign (rise, peak, collapse,
                      resurgence)

Hierarchy: the tagged center octahedron IS the branch-level-0 root (so
Tab-through-root-objects reads each org's summary), the wire ring is its
BL1 child, and the 12 ring objects + sparkline hang off the ring at BL2
(bin points BL3). Zero killed/wounded/reach counts omit their sphere.

Scene 2 -- Event_Cloud/  (node + tag; one node per incident, ~205k)
--------------------------------------------------------------------
No aggregation: every GTD incident is one octahedron.

  X  longitude (degrees)         Y  latitude (degrees)
  Z  date (2 world units/year above the 1970 ground grid)
  color   attack type (legend)
  size    log(killed + wounded), floored so zero-casualty events stay visible
  tags    org | date | city, country | attack type | target | casualties

  Incidents with no coordinates fall back to their country's centroid
  (computed from the geocoded incidents in the same country).

  A NASA Blue Marble world map (media/bluemarble-2048.png, 2:1
  equirectangular) underlies the cloud on a solid textured Grid plane that
  exactly covers lon -180..180 / lat -90..90. GlyphViz auto-loads the
  media/ folder next to the node CSV, so the map is texture_id=1.

Scene 3 -- Org_Event_Network/  (node + tag)
--------------------------------------------
Scenes 1 + 2 combined (including the Blue Marble map plane from its own
media/ folder): the top N organizations (default 16) float as
rosettes on a ring high above their full event cloud, and type-7 link
lines tie each org to its most lethal events (default 400/org -- links are
drawn per-frame, so unlimited links on a 12k-attack org would kill the
framerate; raise --links-per-org if your GPU disagrees). Each org gets a
distinct link hue so the cones of attribution stay separable, and its
rosette carries a small matching beacon so the cone can be traced back.

Scene 4 -- Time_Replay/  (node + tag + ch-map + ch-tracks)
-----------------------------------------------------------
"Fifty years in sixty seconds": the event cloud flattened onto the Blue
Marble map and replayed through Channels. Playback time IS calendar time
-- every frame is half a month, 1224 frames covering 1970-2020. Each
incident starts invisible (color_a 0); when its month arrives it flashes
to full alpha and decays to a faint persistent ember, so the map
accumulates the whole history as playback runs: Northern Ireland and
Italy pulsing in the 70s, Latin America in the 80s, Iraq erupting after
2003, the 2014 ISIS surge. A yellow cursor sweeps the bottom edge --
x = current date, height = worldwide attacks that month.

Channels playback redraws the scene every frame (the retained display
list can't help while node data is changing), which costs ~10 us/node
per frame -- so unlike scene 2 this scene is NOT the full 205k cloud.
It shows the ~10k most severe incidents (--replay-events), chosen by a
per-month quota proportional to sqrt(that month's worldwide attack
count): quiet early decades keep their handful of events, the 2014
surge still reads as a surge, and every incident with >= 50 casualties
is always included. The channel data itself stays tiny no matter the
node count: incidents sharing a birth month share one alpha-envelope
track (612 tracks + 2 cursor tracks), so nodes-per-track scales freely.

Load the node CSV, open the Channels panel, press play (~10 FPS is a
good speed; each visual second then covers ~5 months).

Scene 5 -- Campaign_Pulse/  (node + tag + ch-map + ch-tracks)
--------------------------------------------------------------
"Campaigns breathe": the scene-1 rosette wall for the top 100 orgs,
animated on the same half-month-per-frame clock as scene 4. Each
rosette's size tracks its org's trailing-12-month attack count relative
to its OWN historical peak (full size = at its peak right now, nub =
dormant), and its ring spins at the current intensity -- so a campaign
in full swing visibly churns, a defeated org freezes mid-pose, and the
whole wall becomes a synchronized census: Shining Path fading as the
LTTE rises, al-Qaeda's spike against the Taliban's long burn, the 2014
ISIS ignition. Ring rotation is an absolute-angle track (cumulative
activity), so total turns = total attacks, scrubbing the slider works,
and reset restores the exact CSV pose. ~2.7k nodes, so playback stays
smooth at 15-30 FPS.

Usage
-----
  python generate_gtdb_examples.py
  python generate_gtdb_examples.py --input path\to\globalterrorismdb.xlsx ^
      --output-dir out --min-attacks 10 --network-orgs 16 --links-per-org 400

The 100 MB xlsx takes ~2 min to parse, so the needed columns are cached to
a pickle next to your temp dir on first run and reused after (--no-cache to
force a re-read).

Load in GlyphViz: File > Open Node CSV -> any scene's *_gv_node.csv
(tags load automatically).
"""

import argparse
import colorsys
import csv
import math
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

# Geometry / topology ids (glyphviz_core.geometry_data / topology)
GEO_SPHERE_WIRE, GEO_SPHERE = 2, 3
GEO_TORUS_WIRE = 6
GEO_OCTA = 11
GEO_GRID_WIRE, GEO_GRID = 20, 21
GEO_POINT = 22
TOPO_NONE, TOPO_PLOT = 0, 16
NODE_TYPE_PIN, NODE_TYPE_LINK = 5, 7

# GTD attacktype1 codes -> legend RGB (matches the ANTz-era GTDB legend)
ATTACK_RGB = {
    1: (0, 255, 0),      # Assassination
    2: (0, 0, 255),      # Armed Assault
    3: (0, 255, 255),    # Bombing/Explosion
    4: (255, 0, 255),    # Hijacking
    5: (255, 255, 0),    # Hostage Taking (Barricade Incident)
    6: (255, 150, 0),    # Hostage Taking (Kidnapping)
    7: (255, 0, 90),     # Facility/Infrastructure Attack
    8: (0, 255, 130),    # Unarmed Assault
    9: (160, 160, 160),  # Unknown
}
ATTACK_SHORT = {
    1: "Assassination", 2: "Armed Assault", 3: "Bombing/Explosion",
    4: "Hijacking", 5: "Hostage (Barricade)", 6: "Kidnapping",
    7: "Infrastructure Attack", 8: "Unarmed Assault", 9: "Unknown",
}

# --- Rosette layout ---
# Hierarchy (Tab-navigation friendly: the BL0 root is the tagged, visible
# center octahedron, so tabbing root-to-root reads each org's summary):
#   BL0  center octahedron        scale = log(total attacks)  <- org tag
#   BL1  wire toroid ring          raw scale RING_R / center scale, so the
#                                  ring is the same world size on every org
#   BL2  ring objects / plot       children of the toroid
# Scale cascades multiplicatively down the hierarchy, so BL2 sizes and
# offsets are expressed in ring units (world value / RING_R). The renderer
# floors each node's OWN raw scale at 0.2 before the parent multiplies it,
# so no BL2 element can render smaller than 0.2 * RING_R = 0.52 world --
# the MIN/SPAN ramps below are calibrated to that floor.
RING_R = 2.6                 # world radius of the ring
RING_RATIO = 0.02            # hairline wire torus through the ring objects
CENTER_MIN, CENTER_SPAN = 0.55, 0.95
# BL2 raw ramps (multiply by RING_R for world size: 0.52 .. ~1.3)
BEAD_MIN, BEAD_SPAN = 0.2, 0.22          # 9 attack-type octahedra
CASUALTY_MIN, CASUALTY_SPAN = 0.2, 0.3   # killed/wounded spheres -- same
                                          # geometry+color as before, just
                                          # relocated onto the ring, so their
                                          # slightly larger size is still
                                          # what sets them apart from beads
REACH_MIN, REACH_SPAN = 0.2, 0.28        # country-reach wire sphere
# Round 4 (at Jeff's request): killed/wounded/reach moved off separate
# "above"/"below" spires onto the ring itself, at 3 of 12 evenly-spaced
# slots, fixing their overlap with the ring beads and each other. Only the
# activity plot still floats off the ring, on its own below.
RING_SLOTS = 12                # 9 attack types + killed + wounded + reach
SLOT_DEG = 360.0 / RING_SLOTS
SPARK_Z = -5.2                # plot anchor below the glyph, separate (ring-
                               # local translate_y = SPARK_Z/RING_R = -2.0)
SPARK_HALF_W = 3.3           # sparkline spans x -3.3..+3.3
SPARK_H = 2.2                # peak bin height
BIN_YEARS = 5
YEAR_LO, YEAR_HI = 1970, 2020
N_BINS = (YEAR_HI - YEAR_LO) // BIN_YEARS + 1     # 11 bins
GRID_DX, GRID_DZ = 10.5, 14.0

# --- Event cloud ---
Z_PER_YEAR = 2.0             # date axis: 1970-2020 -> 0..102 world units
EVENT_MIN, EVENT_SPAN = 0.2, 1.3
CAS_CAP = 500.0              # casualties that saturate the size ramp (log)
# World-map plane under the cloud. Every GlyphViz glyph fits within radius
# 1.0, so the flat Grid square is inscribed in the unit sphere: corners at
# radius 1.0 -> edge half-extent 1/sqrt(2) (geometry_data.GRID_HALF_EXTENT).
# Spanning +/-180 deg of longitude therefore takes scale 180*sqrt(2) ~ 254.56
# (not 180, and not 360), and +/-90 deg latitude takes 90*sqrt(2) ~ 127.28.
MAP_SCALE_X = 180.0 * math.sqrt(2.0)
MAP_SCALE_Y = 90.0 * math.sqrt(2.0)
MAP_Z = -0.5                 # just below the 1970 events to avoid z-fighting
MAP_TEXTURE_ID = 1           # first image in the media/ folder next to the
                             # node CSV (bluemarble-2048.png, a 2:1
                             # equirectangular NASA Blue Marble, auto-loads
                             # as texture 1; textures modulate node color,
                             # so the map plane must stay white)

# --- Time replay (scene 4) ---
# Playback time is calendar time: every channel frame is half a month.
REPLAY_MONTHS = (YEAR_HI - YEAR_LO + 1) * 12          # 612
REPLAY_FRAMES_PER_MONTH = 2
REPLAY_FRAMES = REPLAY_MONTHS * REPLAY_FRAMES_PER_MONTH   # 1224
# Alpha envelope shared by every incident born in the same month: 0 until
# the month arrives, flash to 255, exponential decay (tau ~ 2 months) to a
# persistent ember. The CSV alpha is the ember too, so the freshly loaded
# scene previews the full 50-year footprint before playback zeroes it.
REPLAY_EMBER_A, REPLAY_FLASH_A = 35, 255
REPLAY_DECAY_TAU = 3.5               # frames
REPLAY_ALWAYS_CAS = 50               # casualties that bypass the month quota
# Bigger marks than scene 2's: ~5% of the events carry the whole picture.
REPLAY_EVENT_MIN, REPLAY_EVENT_SPAN = 0.45, 2.0
# Later months sit a hair higher so fresh flashes draw over old embers.
REPLAY_Z0, REPLAY_Z_PER_MONTH = 0.3, 0.004
# Time cursor sweeping the bottom edge of the map (below lat -90, so it
# never intersects the plane): channel CURSOR_CH drives translate_x along
# the date sweep and scale_z by that month's worldwide attack count.
CURSOR_Y, CURSOR_Z = -102.0, 0.0
CURSOR_H_MIN, CURSOR_H_SPAN = 0.5, 7.5
CURSOR_CH = REPLAY_MONTHS + 1                        # 613
CURSOR_X_TRACK, CURSOR_H_TRACK = REPLAY_MONTHS, REPLAY_MONTHS + 1

# --- Campaign pulse (scene 5) ---
# Same clock as scene 4: 1224 frames, half a month each, 1970-2020.
# Center octahedron scale: the org's trailing-12-month attack count as a
# fraction of its OWN historical peak (sqrt-softened), times its scene-1
# CSV size -- so a rosette at full size means "this org is at its peak
# right now", and the wall's relative sizes stay comparable (the ceiling
# is still log total attacks). Dormant orgs shrink to a 0.2-raw nub,
# which the scale cascade carries down to the whole rosette.
PULSE_FLOOR = 0.2
# Ring spin: rotate_z is an ABSOLUTE angle track (cumulative campaign
# activity), not a rate -- playback is deterministic, scrubbing works,
# and reset() restores the CSV pose exactly (a rate channel would leave
# the integrated rotation wherever playback stopped). Spin speed peaks
# at this many degrees per frame when the org is at its own peak.
PULSE_SPIN_MAX_DEG = 8.0
PULSE_CURSOR_H_MIN, PULSE_CURSOR_H_SPAN = 0.5, 5.5

# --- Org/Event network ---
NET_RING_R = 115.0           # org rosettes on this ring...
NET_RING_Z = 135.0           # ...this far above the 1970 map plane
LINK_RATIO = 0.008           # per-frame drawn lines: keep them hairline
LINK_ALPHA = 70
BEACON_Z = 2.9                # world distance above the glyph

NODE_FIELDS = [
    "id", "type", "parent_id", "branch_level", "child_id",
    "translate_x", "translate_y", "translate_z",
    "rotate_x", "rotate_y", "rotate_z",
    "scale_x", "scale_y", "scale_z",
    "color_r", "color_g", "color_b", "color_a",
    "geometry", "hide", "topo", "ratio", "texture_id",
]
TAG_FIELDS = ["id", "table_id", "record_id", "title"]
# Scene 4 additionally binds nodes to channels.
REPLAY_NODE_FIELDS = NODE_FIELDS + ["ch_input_id"]
CH_MAP_FIELDS = ["id", "channel_id", "track_id", "attribute",
                 "track_table_id", "ch_map_table_id", "record_id"]


# ===========================================================================
# Loading
# ===========================================================================

COLS = {   # xlsx column index -> name (GTD 0522 release layout)
    0: "eventid", 1: "iyear", 2: "imonth", 3: "iday",
    8: "country_txt", 10: "region_txt", 12: "city",
    13: "latitude", 14: "longitude",
    26: "success", 27: "suicide",
    28: "attacktype1", 29: "attacktype1_txt",
    35: "targtype1_txt",
    58: "gname",
    98: "nkill", 101: "nwound",
}


def load_gtdb(xlsx: Path, cache: Path, use_cache: bool) -> pd.DataFrame:
    if use_cache and cache.exists():
        print(f"  using cached columns: {cache}")
        df = pd.read_pickle(cache)
    else:
        import openpyxl
        print(f"  parsing {xlsx} (takes ~2 min) ...")
        wb = openpyxl.load_workbook(xlsx, read_only=True)
        ws = wb[wb.sheetnames[0]]
        idx = sorted(COLS)
        data = {name: [] for name in COLS.values()}
        for row in ws.iter_rows(min_row=2, values_only=True):
            for i in idx:
                data[COLS[i]].append(row[i])
        wb.close()
        df = pd.DataFrame(data)
        df.to_pickle(cache)
        print(f"  cached to {cache}")

    for col in ("latitude", "longitude", "nkill", "nwound"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["nkill"] = df["nkill"].fillna(0.0)
    df["nwound"] = df["nwound"].fillna(0.0)
    df["casualties"] = df["nkill"] + df["nwound"]
    df["imonth"] = df["imonth"].clip(lower=1)   # 0 = unknown month/day
    df["iday"] = df["iday"].clip(lower=1)
    df["frac_year"] = (df["iyear"] - YEAR_LO) + (df["imonth"] - 1) / 12.0 \
        + (df["iday"] - 1) / 365.0
    df["gname"] = df["gname"].astype(str).str.strip()

    # Country-centroid fallback for the ~2% of incidents with no coordinates.
    known = df.dropna(subset=["latitude", "longitude"])
    cent = known.groupby("country_txt")[["latitude", "longitude"]].mean()
    missing = df["latitude"].isna() | df["longitude"].isna()
    fb = df.loc[missing, "country_txt"].map(cent["latitude"])
    df.loc[missing, "latitude"] = fb
    df.loc[missing, "longitude"] = df.loc[missing, "country_txt"].map(cent["longitude"])
    still = int(df["latitude"].isna().sum())
    print(f"  {missing.sum()} incidents used country-centroid coords; "
          f"{still} had neither and are dropped from event scenes")
    return df


# ===========================================================================
# Per-organization stats
# ===========================================================================

def org_stats(df: pd.DataFrame, min_attacks: int) -> pd.DataFrame:
    known = df[df["gname"] != "Unknown"]
    g = known.groupby("gname")
    stats = g.agg(
        attacks=("eventid", "size"),
        killed=("nkill", "sum"),
        wounded=("nwound", "sum"),
        countries=("country_txt", "nunique"),
        year_lo=("iyear", "min"),
        year_hi=("iyear", "max"),
        suicide=("suicide", "mean"),
        success=("success", "mean"),
    )
    stats = stats[stats["attacks"] >= min_attacks].sort_values(
        "attacks", ascending=False)

    # attack-type counts per org (columns 1..9)
    type_counts = (known[known["gname"].isin(stats.index)]
                   .groupby(["gname", "attacktype1"]).size().unstack(fill_value=0)
                   .reindex(columns=range(1, 10), fill_value=0)
                   .reindex(stats.index))
    # 5-year-bin activity per org
    bin_idx = ((known["iyear"] - YEAR_LO) // BIN_YEARS).clip(0, N_BINS - 1)
    bins = (known[known["gname"].isin(stats.index)]
            .groupby(["gname", bin_idx]).size().unstack(fill_value=0)
            .reindex(columns=range(N_BINS), fill_value=0)
            .reindex(stats.index))
    # top target + top country per org
    top_target = g["targtype1_txt"].agg(lambda s: s.mode().iloc[0]).reindex(stats.index)
    top_country = g["country_txt"].agg(lambda s: s.mode().iloc[0]).reindex(stats.index)
    stats["top_target"] = top_target
    stats["top_country"] = top_country
    stats["dominant_type"] = type_counts.idxmax(axis=1)
    return stats, type_counts, bins


# ===========================================================================
# Helpers
# ===========================================================================

def logn(value: float, cap: float) -> float:
    """log1p normalized to 0..1 against a cap."""
    return math.log1p(max(0.0, min(value, cap))) / math.log1p(cap)


def tidy_text(s: str) -> str:
    """Strip control characters from tag titles: one stray control byte makes
    the whole tag CSV silently unloadable."""
    return "".join("?" if (ord(c) < 32 or 127 <= ord(c) <= 159) else c
                   for c in str(s))


def node_row(node_id, parent_id, branch_level, tx, ty, tz, s, color, geometry,
             topo, *, node_type=NODE_TYPE_PIN, child_id=0, alpha=255, hide=0,
             ratio=0.1, rx=0.0, sy=None, sz=None, texture_id=0):
    return {
        "id": node_id, "type": node_type, "parent_id": parent_id,
        "branch_level": branch_level, "child_id": child_id,
        "translate_x": round(tx, 4), "translate_y": round(ty, 4),
        "translate_z": round(tz, 4),
        "rotate_x": rx, "rotate_y": 0.0, "rotate_z": 0.0,
        "scale_x": round(s, 4), "scale_y": round(s if sy is None else sy, 4),
        "scale_z": round(s if sz is None else sz, 4),
        "color_r": color[0], "color_g": color[1], "color_b": color[2],
        "color_a": alpha,
        "geometry": geometry, "hide": hide, "topo": topo, "ratio": ratio,
        "texture_id": texture_id,
    }


def write_csv(path: Path, fieldnames, rows):
    if "title" in fieldnames:
        for row in rows:
            row["title"] = tidy_text(row["title"])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"  {path.name}: {len(rows)} rows")


def fmt_pct(v: float) -> str:
    return f"{v * 100:.0f}%"


# ===========================================================================
# The rosette builder (shared by scenes 1 and 3)
# ===========================================================================

class Norms:
    """Global log-scale caps so rosettes are comparable across orgs."""

    def __init__(self, stats: pd.DataFrame, type_counts: pd.DataFrame):
        self.max_attacks = float(stats["attacks"].max())
        self.max_type = float(type_counts.to_numpy().max())
        self.max_killed = float(stats["killed"].max())
        self.max_wounded = float(stats["wounded"].max())
        self.max_countries = float(stats["countries"].max())


def build_rosette(nodes, tags, next_id, gname, st, tcounts, tbins,
                  norms: Norms, x, y, z, beacon_rgb=None):
    """Append one org rosette; returns (next_id, root_node_id).

    The BL0 root is the center octahedron itself (visible + tagged, so
    Tab-through-roots reads each org). The BL1 toroid compensates the
    root's varying scale (raw = RING_R / c_scale) so every ring renders at
    world radius RING_R; every BL2 child then lives in "ring units" -- its
    offsets and sizes are multiplied by RING_R via the scale cascade.
    The toroid is stood upright to face the viewer with rotate_x = -90:
    Heading/Tilt/Roll builds Rx(-rx), so -90 maps ring-local +Y to world
    +Z (up) and the ring is the local XY unit circle.
    """
    dom = int(st["dominant_type"])
    root = next_id
    c_scale = CENTER_MIN + CENTER_SPAN * logn(st["attacks"], norms.max_attacks)
    nodes.append(node_row(root, 0, 0, x, y, z, c_scale, ATTACK_RGB[dom],
                          GEO_OCTA, TOPO_NONE))
    tags.append({"id": len(tags), "table_id": 0, "record_id": root, "title": (
        f"{gname} | {st['attacks']:.0f} attacks {st['year_lo']:.0f}-{st['year_hi']:.0f}"
        f" | {st['killed']:.0f} killed {st['wounded']:.0f} wounded"
        f" | dominant: {ATTACK_SHORT[dom]} | top target: {st['top_target']}"
        f" | suicide {fmt_pct(st['suicide'])} | success {fmt_pct(st['success'])}")})
    nid = root + 1

    # BL1: vertical hairline ring, world radius RING_R on every org
    ring_id = nid
    nodes.append(node_row(ring_id, root, 1, 0, 0, 0, RING_R / c_scale,
                          (90, 95, 105), GEO_TORUS_WIRE, TOPO_NONE, alpha=120,
                          ratio=RING_RATIO, rx=-90))
    tags.append({"id": len(tags), "table_id": 0, "record_id": ring_id,
                 "title": (f"{gname} | ring, 12 slots clockwise from 12: "
                           f"Assassination, Armed Assault, Bombing, Hijacking, "
                           f"Barricade, Kidnapping, Infrastructure, Unarmed, "
                           f"Unknown, Killed, Wounded, Countries Struck")})
    nid += 1

    def spire(world_z: float) -> tuple[float, float, float]:
        """Ring-local offset for a point at (0, 0, world_z) from the center."""
        return (0.0, world_z / RING_R, 0.0)

    # BL2: all 12 ring categories -- 9 attack-type beads, killed, wounded,
    # and country-reach -- at fixed evenly-spaced slots (slot 0 at 12
    # o'clock, clockwise). A category's angular position never depends on
    # which other categories are present, so a zero/absent one leaves a
    # gap instead of shifting its neighbors. Killed/wounded/reach keep the
    # same geometry+color they always had (solid red / wire orange / wire
    # blue sphere), which is what sets them apart from the attack-type
    # octahedra now that they all share the ring -- moving them off their
    # old separate "spire" position is what fixed their overlap with the
    # beads. Zero counts skip the slot entirely: the 0.2 raw-scale floor
    # would otherwise render "0" as a 0.52-world sphere.
    # (count, cap, color, geometry, min/span, tag-title fn) for each slot
    ring_items = (
        [(tcounts[a], norms.max_type, ATTACK_RGB[a], GEO_OCTA,
          BEAD_MIN, BEAD_SPAN,
          lambda c, a=a: f"{ATTACK_SHORT[a]}: {c} attacks")
         for a in range(1, 10)]
        + [(st["killed"], norms.max_killed, (255, 40, 40), GEO_SPHERE,
            CASUALTY_MIN, CASUALTY_SPAN, lambda c: f"{c} killed"),
           (st["wounded"], norms.max_wounded, (255, 150, 0), GEO_SPHERE_WIRE,
            CASUALTY_MIN, CASUALTY_SPAN, lambda c: f"{c} wounded"),
           (st["countries"], norms.max_countries, (80, 140, 255),
            GEO_SPHERE_WIRE, REACH_MIN, REACH_SPAN,
            lambda c: (f"struck in {c} "
                       f"{'country' if c == 1 else 'countries'}"
                       f" | most: {st['top_country']}"))]
    )
    for slot, (count, cap, color, geo, mn, span, title_fn) in enumerate(ring_items):
        count = int(count)
        if count <= 0:
            continue
        theta = math.radians(90 - slot * SLOT_DEG)
        s = mn + span * logn(count, cap)
        nodes.append(node_row(nid, ring_id, 2, math.cos(theta),
                              math.sin(theta), 0.0, s, color, geo, TOPO_NONE))
        tags.append({"id": len(tags), "table_id": 0, "record_id": nid,
                     "title": f"{gname} | {title_fn(count)}"})
        nid += 1

    # BL2 activity sparkline anchor. Raw scale 1/RING_R makes its own world
    # scale exactly 1.0, so the BL3 bin points keep plain world-unit offsets
    # and the 0.2-scale points render at 0.2 world -- no floor distortion.
    peak = max(int(tbins.max()), 1)
    peak_bin = int(tbins.idxmax())
    plot_id = nid
    nodes.append(node_row(plot_id, ring_id, 2, *spire(SPARK_Z), 1.0 / RING_R,
                          (120, 125, 135), GEO_POINT, TOPO_PLOT, ratio=0.05))
    tags.append({"id": len(tags), "table_id": 0, "record_id": plot_id, "title": (
        f"{gname} | activity {YEAR_LO}-{YEAR_HI} in {BIN_YEARS}-yr bins | peak "
        f"{YEAR_LO + peak_bin * BIN_YEARS}-{YEAR_LO + peak_bin * BIN_YEARS + 4}: "
        f"{peak} attacks")})
    nid += 1
    step = 2 * SPARK_HALF_W / (N_BINS - 1)
    for i in range(N_BINS):
        cnt = int(tbins[i])
        h = SPARK_H * logn(cnt, peak) if cnt else 0.0
        shade = (235, 235, 240) if cnt else (100, 100, 110)
        # Anchor local +Y is world +Z (inherited toroid rotation), so bin
        # height rides the local Y axis.
        nodes.append(node_row(nid, plot_id, 3, -SPARK_HALF_W + i * step, h,
                              0.0, 0.2, shade, GEO_OCTA, TOPO_NONE))
        tags.append({"id": len(tags), "table_id": 0, "record_id": nid, "title":
                     f"{gname} | {YEAR_LO + i * BIN_YEARS}-"
                     f"{min(YEAR_LO + i * BIN_YEARS + 4, YEAR_HI)}: {cnt} attacks"})
        nid += 1

    # BL2 org-colored beacon (network scene): ties rosette to its link cone
    if beacon_rgb is not None:
        nodes.append(node_row(nid, ring_id, 2, *spire(BEACON_Z), 0.6 / RING_R,
                              beacon_rgb, GEO_OCTA, TOPO_NONE))
        tags.append({"id": len(tags), "table_id": 0, "record_id": nid,
                     "title": f"{gname} | link-line color beacon"})
        nid += 1

    return nid, root


# ===========================================================================
# Scene 1: Organization Profiles wall
# ===========================================================================

def build_org_profiles(stats, type_counts, bins, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    norms = Norms(stats, type_counts)
    n = len(stats)
    ncols = max(1, math.ceil(math.sqrt(n * GRID_DZ / GRID_DX)))
    nrows = math.ceil(n / ncols)

    nodes, tags = [], []
    # Legend/description anchor above the top-left corner of the wall
    legend_id = 1
    x0 = -(ncols - 1) * GRID_DX / 2.0
    z_top = (nrows - 1) * GRID_DZ + 14.0
    nodes.append(node_row(legend_id, 0, 0, x0, 0, z_top, 0.6, (200, 200, 210),
                          GEO_SPHERE_WIRE, TOPO_NONE))
    tags.append({"id": 0, "table_id": 0, "record_id": legend_id, "title": (
        f"GTD ORGANIZATION PROFILES | {n} orgs, most active top-left | "
        f"center size = attacks, color = dominant attack type | ring beads "
        f"clockwise from 12: Assassination, Armed Assault, Bombing, Hijacking, "
        f"Barricade, Kidnapping, Infrastructure, Unarmed, Unknown | above: red "
        f"= killed, orange = wounded | below: blue = countries struck | "
        f"baseline: attacks per 5 yr, 1970-2020")})

    next_id = 2
    for i, (gname, st) in enumerate(stats.iterrows()):
        col, row = i % ncols, i // ncols
        x = x0 + col * GRID_DX
        z = (nrows - 1 - row) * GRID_DZ
        next_id, _ = build_rosette(nodes, tags, next_id, gname, st,
                                   type_counts.loc[gname], bins.loc[gname],
                                   norms, x, 0.0, z)

    write_csv(out_dir / "OrgProfiles_gv_node.csv", NODE_FIELDS, nodes)
    write_csv(out_dir / "OrgProfiles_gv_tag.csv", TAG_FIELDS, tags)


# ===========================================================================
# Scene 2: Event Cloud
# ===========================================================================

def event_nodes(df, nodes, tags, start_id) -> int:
    """Append one octahedron per incident; returns (next free id, eventid->id)."""
    ev = df.dropna(subset=["latitude", "longitude"]).sort_values("frac_year")
    zz = ev["frac_year"].to_numpy() * Z_PER_YEAR
    scale = EVENT_MIN + EVENT_SPAN * (
        np.log1p(np.minimum(ev["casualties"].to_numpy(), CAS_CAP))
        / math.log1p(CAS_CAP))
    nid = start_id
    id_of_event = {}
    cols = ["eventid", "gname", "iyear", "imonth", "iday", "city",
            "country_txt", "attacktype1", "attacktype1_txt", "targtype1_txt",
            "nkill", "nwound", "longitude", "latitude"]
    for i, r in enumerate(ev[cols].itertuples(index=False)):
        color = ATTACK_RGB.get(int(r.attacktype1), ATTACK_RGB[9])
        nodes.append(node_row(nid, 0, 0, float(r.longitude), float(r.latitude),
                              float(zz[i]), float(scale[i]), color,
                              GEO_OCTA, TOPO_NONE))
        cas = ""
        if r.nkill or r.nwound:
            cas = f" | {r.nkill:.0f} killed {r.nwound:.0f} wounded"
        city = (f"{r.city}, " if not pd.isna(r.city) and str(r.city) != "Unknown"
                else "")
        tags.append({"id": len(tags), "table_id": 0, "record_id": nid, "title": (
            f"{r.gname} | {r.iyear}-{r.imonth:02d}-{r.iday:02d}"
            f" | {city}{r.country_txt} | {r.attacktype1_txt}"
            f" | {r.targtype1_txt}{cas}")})
        id_of_event[r.eventid] = nid
        nid += 1
    return nid, id_of_event


def add_map_furniture(nodes, tags, next_id, *, textured: bool) -> int:
    """World-map plane at 1970 plus decade markers up the date axis.

    The plane exactly covers lon -180..180 / lat -90..90 (see the MAP_SCALE
    comment up top for the sqrt(2) factor). With *textured* it's a solid
    white grid showing texture 1 -- the equirectangular world map from the
    media/ folder next to the node CSV; otherwise a dark wire placeholder
    with the same footprint, so dropping a map in media/ and setting
    texture_id=1 later lines up with no other change."""
    if textured:
        nodes.append(node_row(next_id, 0, 0, 0, 0, MAP_Z, MAP_SCALE_X,
                              (255, 255, 255), GEO_GRID, TOPO_NONE,
                              sy=MAP_SCALE_Y, sz=1.0,
                              texture_id=MAP_TEXTURE_ID))
    else:
        nodes.append(node_row(next_id, 0, 0, 0, 0, MAP_Z, MAP_SCALE_X,
                              (55, 60, 75), GEO_GRID_WIRE, TOPO_NONE,
                              alpha=130, sy=MAP_SCALE_Y, sz=1.0))
    tags.append({"id": len(tags), "table_id": 0, "record_id": next_id, "title": (
        "GTD EVENT CLOUD | X longitude, Y latitude, Z date (1970 at the map, "
        "2 units/yr) | color = attack type | size = killed + wounded (log)")})
    next_id += 1
    for decade in range(YEAR_LO, YEAR_HI + 1, 10):
        z = (decade - YEAR_LO) * Z_PER_YEAR
        nodes.append(node_row(next_id, 0, 0, -195.0, -60.0, z, 0.8,
                              (200, 200, 210), GEO_SPHERE_WIRE, TOPO_NONE))
        tags.append({"id": len(tags), "table_id": 0, "record_id": next_id,
                     "title": str(decade)})
        next_id += 1
    return next_id


def build_event_cloud(df, out_dir: Path, max_events: int):
    out_dir.mkdir(parents=True, exist_ok=True)
    ev = df if not max_events else df.nlargest(max_events, "casualties")
    nodes, tags = [], []
    next_id = add_map_furniture(nodes, tags, 1, textured=True)
    next_id, _ = event_nodes(ev, nodes, tags, next_id)
    write_csv(out_dir / "EventCloud_gv_node.csv", NODE_FIELDS, nodes)
    write_csv(out_dir / "EventCloud_gv_tag.csv", TAG_FIELDS, tags)


# ===========================================================================
# Scene 3: Org/Event Network
# ===========================================================================

def build_network(df, stats, type_counts, bins, out_dir: Path,
                  n_orgs: int, links_per_org: int):
    out_dir.mkdir(parents=True, exist_ok=True)
    norms = Norms(stats, type_counts)   # same norms as scene 1: comparable
    top = stats.head(n_orgs)
    ev = df[df["gname"].isin(top.index)]
    print(f"  {n_orgs} orgs, {len(ev)} of their events, "
          f"<= {links_per_org} links each")

    nodes, tags = [], []
    next_id = add_map_furniture(nodes, tags, 1, textured=True)
    next_id, id_of_event = event_nodes(ev, nodes, tags, next_id)

    # Org rosettes on a ring high above the cloud + org-colored link hues
    center_of_org, hue_of_org = {}, {}
    for i, (gname, st) in enumerate(top.iterrows()):
        rgb = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(
            i / max(len(top), 1), 0.85, 1.0))
        hue_of_org[gname] = rgb
        ang = math.radians(90.0 - i * 360.0 / len(top))
        x = NET_RING_R * math.cos(ang)
        y = 10.0 + NET_RING_R * math.sin(ang)
        next_id, center_id = build_rosette(
            nodes, tags, next_id, gname, st, type_counts.loc[gname],
            bins.loc[gname], norms, x, y, NET_RING_Z, beacon_rgb=rgb)
        center_of_org[gname] = center_id

    # Link lines: each org's most lethal events -> its rosette center
    n_links = 0
    for gname in top.index:
        sub = ev[ev["gname"] == gname]
        if links_per_org:
            sub = sub.nlargest(links_per_org, "casualties")
        rgb = hue_of_org[gname]
        for eid in sub["eventid"]:
            if eid not in id_of_event:
                continue
            nodes.append(node_row(
                next_id, id_of_event[eid], 1, 0, 0, 0, 0.2, rgb, GEO_POINT,
                TOPO_NONE, node_type=NODE_TYPE_LINK,
                child_id=center_of_org[gname], alpha=LINK_ALPHA,
                ratio=LINK_RATIO))
            next_id += 1
            n_links += 1
    print(f"  {n_links} link lines")

    write_csv(out_dir / "OrgEventNetwork_gv_node.csv", NODE_FIELDS, nodes)
    write_csv(out_dir / "OrgEventNetwork_gv_tag.csv", TAG_FIELDS, tags)


# ===========================================================================
# Scene 4: Time Replay (Channels)
# ===========================================================================

def build_time_replay(df, out_dir: Path, budget: int):
    out_dir.mkdir(parents=True, exist_ok=True)

    # Month index 0..611 for every incident (load_gtdb already clipped
    # unknown imonth to 1). Monthly totals use the FULL dataset so the
    # cursor's height meter stays honest regardless of the node budget.
    month_all = ((df["iyear"] - YEAR_LO) * 12 + df["imonth"] - 1).clip(
        0, REPLAY_MONTHS - 1).astype(int)
    monthly_counts = month_all.value_counts().reindex(
        range(REPLAY_MONTHS), fill_value=0)

    # --- Select ~budget incidents: per-month quota ~ sqrt(monthly count),
    # most casualties first, plus everything >= REPLAY_ALWAYS_CAS.
    ev = df.dropna(subset=["latitude", "longitude"]).copy()
    ev["month"] = month_all.loc[ev.index]
    sqrt_counts = np.sqrt(monthly_counts.to_numpy(dtype=float))
    factor = budget / max(sqrt_counts.sum(), 1.0)
    quota = pd.Series(np.maximum(1, np.round(sqrt_counts * factor)),
                      index=monthly_counts.index)
    ev = ev.sort_values(["month", "casualties"], ascending=[True, False])
    rank_in_month = ev.groupby("month").cumcount()
    keep = (rank_in_month < ev["month"].map(quota)) \
        | (ev["casualties"] >= REPLAY_ALWAYS_CAS)
    sel = ev[keep].sort_values("frac_year")
    print(f"  {len(sel)} of {len(ev)} incidents selected "
          f"(quota factor {factor:.2f}, {int((ev['casualties'] >= REPLAY_ALWAYS_CAS).sum())} "
          f"with >= {REPLAY_ALWAYS_CAS} casualties always in)")

    # --- Shared channel tracks: one alpha envelope per month + 2 cursor
    # tracks. Column ch<m> is month m's envelope (channel_id m+1).
    frames = np.arange(REPLAY_FRAMES, dtype=float)[:, None]
    onset = (np.arange(REPLAY_MONTHS, dtype=float)
             * REPLAY_FRAMES_PER_MONTH)[None, :]
    dt = frames - onset
    env = np.where(dt < 0, 0.0, REPLAY_EMBER_A
                   + (REPLAY_FLASH_A - REPLAY_EMBER_A)
                   * np.exp(-np.maximum(dt, 0) / REPLAY_DECAY_TAU))
    cursor_x = -180.0 + 360.0 * frames[:, 0] / (REPLAY_FRAMES - 1)
    peak = float(monthly_counts.max())
    cursor_h = CURSOR_H_MIN + CURSOR_H_SPAN * np.repeat(
        np.log1p(monthly_counts.to_numpy(dtype=float)) / math.log1p(peak),
        REPLAY_FRAMES_PER_MONTH)
    tracks = {"cyclecount": np.arange(REPLAY_FRAMES)}
    for m in range(REPLAY_MONTHS):
        tracks[f"ch{m}"] = np.round(env[:, m]).astype(int)
    tracks[f"ch{CURSOR_X_TRACK}"] = np.round(cursor_x, 2)
    tracks[f"ch{CURSOR_H_TRACK}"] = np.round(cursor_h, 3)
    pd.DataFrame(tracks).to_csv(out_dir / "TimeReplay_gv_ch-tracks.csv",
                                index=False)
    print(f"  TimeReplay_gv_ch-tracks.csv: {REPLAY_FRAMES} frames x "
          f"{REPLAY_MONTHS + 2} tracks")

    # --- Channel map: channel m+1 -> track m -> color_a; the cursor
    # channel drives two attributes from its own tracks.
    ch_rows = [{"id": m, "channel_id": m + 1, "track_id": m,
                "attribute": "color_a", "track_table_id": 0,
                "ch_map_table_id": 0, "record_id": 0}
               for m in range(REPLAY_MONTHS)]
    ch_rows.append({"id": REPLAY_MONTHS, "channel_id": CURSOR_CH,
                    "track_id": CURSOR_X_TRACK, "attribute": "translate_x",
                    "track_table_id": 0, "ch_map_table_id": 0, "record_id": 0})
    ch_rows.append({"id": REPLAY_MONTHS + 1, "channel_id": CURSOR_CH,
                    "track_id": CURSOR_H_TRACK, "attribute": "scale_z",
                    "track_table_id": 0, "ch_map_table_id": 0, "record_id": 0})
    write_csv(out_dir / "TimeReplay_gv_ch-map.csv", CH_MAP_FIELDS, ch_rows)

    # --- Nodes. Every row needs ch_input_id (0 = not channel-bound).
    nodes, tags = [], []

    def add(row, ch_input_id=0):
        row["ch_input_id"] = ch_input_id
        nodes.append(row)

    # Blue Marble plane (same footprint math as scene 2's furniture).
    add(node_row(1, 0, 0, 0, 0, MAP_Z, MAP_SCALE_X, (255, 255, 255),
                 GEO_GRID, TOPO_NONE, sy=MAP_SCALE_Y, sz=1.0,
                 texture_id=MAP_TEXTURE_ID))
    tags.append({"id": 0, "table_id": 0, "record_id": 1, "title": (
        f"GTD TIME REPLAY {YEAR_LO}-{YEAR_HI} | Channels playback: each "
        f"frame = half a month | incidents flash on their date, then fade "
        f"to embers | color = attack type, size = casualties (log) | "
        f"yellow cursor: position = current date, height = worldwide "
        f"attacks that month | {len(sel)} most severe of {len(df)} "
        f"incidents (per-month quota) | play at ~10 FPS")})

    # Time cursor + decade tick marks along the bottom edge.
    add(node_row(2, 0, 0, -180.0, CURSOR_Y, CURSOR_Z, 2.0, (255, 230, 90),
                 GEO_OCTA, TOPO_NONE, sz=CURSOR_H_MIN), ch_input_id=CURSOR_CH)
    tags.append({"id": 1, "table_id": 0, "record_id": 2, "title": (
        "TIME CURSOR | x = current date (1970 left edge, 2020 right) | "
        "height = attacks worldwide that month")})
    next_id = 3
    for decade in range(YEAR_LO, YEAR_HI + 1, 10):
        f = (decade - YEAR_LO) * 12 * REPLAY_FRAMES_PER_MONTH
        x = -180.0 + 360.0 * f / (REPLAY_FRAMES - 1)
        add(node_row(next_id, 0, 0, x, CURSOR_Y, 0.0, 0.8, (200, 200, 210),
                     GEO_SPHERE_WIRE, TOPO_NONE))
        tags.append({"id": len(tags), "table_id": 0, "record_id": next_id,
                     "title": str(decade)})
        next_id += 1

    # One octahedron per selected incident, chronological order (fresh
    # flashes blend over older embers), bound to its birth month's channel.
    cols = ["gname", "iyear", "imonth", "iday", "city", "country_txt",
            "attacktype1", "attacktype1_txt", "targtype1_txt",
            "nkill", "nwound", "longitude", "latitude", "month"]
    scale = REPLAY_EVENT_MIN + REPLAY_EVENT_SPAN * (
        np.log1p(np.minimum(sel["casualties"].to_numpy(), CAS_CAP))
        / math.log1p(CAS_CAP))
    for i, r in enumerate(sel[cols].itertuples(index=False)):
        color = ATTACK_RGB.get(int(r.attacktype1), ATTACK_RGB[9])
        z = REPLAY_Z0 + int(r.month) * REPLAY_Z_PER_MONTH
        add(node_row(next_id, 0, 0, float(r.longitude), float(r.latitude),
                     z, float(scale[i]), color, GEO_OCTA, TOPO_NONE,
                     alpha=REPLAY_EMBER_A), ch_input_id=int(r.month) + 1)
        cas = ""
        if r.nkill or r.nwound:
            cas = f" | {r.nkill:.0f} killed {r.nwound:.0f} wounded"
        city = (f"{r.city}, " if not pd.isna(r.city) and str(r.city) != "Unknown"
                else "")
        tags.append({"id": len(tags), "table_id": 0, "record_id": next_id,
                     "title": (
            f"{r.gname} | {r.iyear}-{r.imonth:02d}-{r.iday:02d}"
            f" | {city}{r.country_txt} | {r.attacktype1_txt}"
            f" | {r.targtype1_txt}{cas}")})
        next_id += 1

    write_csv(out_dir / "TimeReplay_gv_node.csv", REPLAY_NODE_FIELDS, nodes)
    write_csv(out_dir / "TimeReplay_gv_tag.csv", TAG_FIELDS, tags)

    # Blue Marble texture: copy from a sibling scene's media/ if available.
    dst = out_dir / "media" / "bluemarble-2048.png"
    if not dst.exists():
        for sibling in ("Event_Cloud", "Org_Event_Network"):
            src = out_dir.parent / sibling / "media" / "bluemarble-2048.png"
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
                print(f"  media/bluemarble-2048.png copied from {sibling}/")
                break
        else:
            print("  WARNING: no bluemarble-2048.png found to copy -- put a "
                  "2:1 equirectangular world map at media/bluemarble-2048.png")


# ===========================================================================
# Scene 5: Campaign Pulse (Channels)
# ===========================================================================

def build_campaign_pulse(df, stats, type_counts, bins, out_dir: Path,
                         n_orgs: int):
    out_dir.mkdir(parents=True, exist_ok=True)
    norms = Norms(stats, type_counts)   # same ceilings as scene 1
    top = stats.head(n_orgs)
    n = len(top)

    # Per-org monthly attack counts -> trailing-12-month "intensity".
    known = df[df["gname"].isin(top.index)]
    month = ((known["iyear"] - YEAR_LO) * 12 + known["imonth"] - 1).clip(
        0, REPLAY_MONTHS - 1).astype(int)
    monthly = (known.groupby(["gname", month]).size().unstack(fill_value=0)
               .reindex(columns=range(REPLAY_MONTHS), fill_value=0)
               .reindex(top.index))
    trail12 = monthly.T.rolling(12, min_periods=1).sum().T
    frac = trail12.div(trail12.max(axis=1), axis=0).to_numpy()   # 0..1 per org

    # --- Tracks, linearly interpolated between month samples (frame 2m).
    month_frames = np.arange(REPLAY_MONTHS) * REPLAY_FRAMES_PER_MONTH
    frames = np.arange(REPLAY_FRAMES)
    tracks = {"cyclecount": frames}
    c_scales = {}
    for i, gname in enumerate(top.index):
        c_scale = CENTER_MIN + CENTER_SPAN * logn(
            top.loc[gname, "attacks"], norms.max_attacks)
        c_scales[gname] = c_scale
        s = np.maximum(PULSE_FLOOR, c_scale * np.sqrt(frac[i]))
        tracks[f"ch{i}"] = np.round(np.interp(frames, month_frames, s), 4)
        spin = np.cumsum(PULSE_SPIN_MAX_DEG * REPLAY_FRAMES_PER_MONTH
                         * frac[i])
        tracks[f"ch{n + i}"] = np.round(
            np.interp(frames, month_frames, spin), 2)

    # Wall layout (same formula as scene 1).
    ncols = max(1, math.ceil(math.sqrt(n * GRID_DZ / GRID_DX)))
    nrows = math.ceil(n / ncols)
    x0 = -(ncols - 1) * GRID_DX / 2.0
    x1 = x0 + (ncols - 1) * GRID_DX

    # Cursor: x sweeps the wall's width; height = monthly attacks of the
    # displayed orgs (log-normalized).
    wall_monthly = monthly.sum(axis=0).to_numpy(dtype=float)
    peak = float(wall_monthly.max())
    cursor_x = np.interp(frames, [0, REPLAY_FRAMES - 1], [x0, x1])
    h = PULSE_CURSOR_H_MIN + PULSE_CURSOR_H_SPAN * (
        np.log1p(wall_monthly) / math.log1p(peak))
    tracks[f"ch{2 * n}"] = np.round(cursor_x, 2)
    tracks[f"ch{2 * n + 1}"] = np.round(
        np.interp(frames, month_frames, h), 3)
    pd.DataFrame(tracks).to_csv(out_dir / "CampaignPulse_gv_ch-tracks.csv",
                                index=False)
    print(f"  CampaignPulse_gv_ch-tracks.csv: {REPLAY_FRAMES} frames x "
          f"{2 * n + 2} tracks")

    # --- Channel map: per org, channel i+1 drives the center's XYZ scale
    # from track i; channel n+i+1 rolls the ring from track n+i.
    ch_rows = []
    for i in range(n):
        for attr in ("scale_x", "scale_y", "scale_z"):
            ch_rows.append({"id": len(ch_rows), "channel_id": i + 1,
                            "track_id": i, "attribute": attr,
                            "track_table_id": 0, "ch_map_table_id": 0,
                            "record_id": 0})
        ch_rows.append({"id": len(ch_rows), "channel_id": n + i + 1,
                        "track_id": n + i, "attribute": "rotate_z",
                        "track_table_id": 0, "ch_map_table_id": 0,
                        "record_id": 0})
    cursor_ch = 2 * n + 1
    ch_rows.append({"id": len(ch_rows), "channel_id": cursor_ch,
                    "track_id": 2 * n, "attribute": "translate_x",
                    "track_table_id": 0, "ch_map_table_id": 0, "record_id": 0})
    ch_rows.append({"id": len(ch_rows), "channel_id": cursor_ch,
                    "track_id": 2 * n + 1, "attribute": "scale_z",
                    "track_table_id": 0, "ch_map_table_id": 0, "record_id": 0})
    write_csv(out_dir / "CampaignPulse_gv_ch-map.csv", CH_MAP_FIELDS, ch_rows)

    # --- Nodes: the scene-1 rosette wall for the top N orgs, with each
    # rosette's center and ring bound to its org's channels.
    nodes, tags = [], []
    legend_id = 1
    z_top = (nrows - 1) * GRID_DZ + 14.0
    nodes.append(node_row(legend_id, 0, 0, x0, 0, z_top, 0.6, (200, 200, 210),
                          GEO_SPHERE_WIRE, TOPO_NONE))
    tags.append({"id": 0, "table_id": 0, "record_id": legend_id, "title": (
        f"GTD CAMPAIGN PULSE {YEAR_LO}-{YEAR_HI} | top {n} orgs, most active "
        f"top-left | Channels playback: each frame = half a month | rosette "
        f"size = trailing-12-month attacks vs the org's own peak (full size "
        f"= at its peak, nub = dormant) | ring spin speed = current "
        f"intensity, total turns = cumulative attacks | cursor below: "
        f"position = date, height = attacks/month by these orgs | play at "
        f"~15-30 FPS")})

    next_id = 2
    for i, (gname, st) in enumerate(top.iterrows()):
        col, row = i % ncols, i // ncols
        x = x0 + col * GRID_DX
        z = (nrows - 1 - row) * GRID_DZ
        idx0 = len(nodes)
        next_id, _ = build_rosette(nodes, tags, next_id, gname, st,
                                   type_counts.loc[gname], bins.loc[gname],
                                   norms, x, 0.0, z)
        nodes[idx0]["ch_input_id"] = i + 1          # center octahedron
        nodes[idx0 + 1]["ch_input_id"] = n + i + 1  # BL1 ring

    # Time cursor + decade ticks under the wall.
    cursor_z = -12.0
    cursor_id = next_id
    nodes.append(node_row(cursor_id, 0, 0, x0, 0.0, cursor_z, 1.5,
                          (255, 230, 90), GEO_OCTA, TOPO_NONE,
                          sz=PULSE_CURSOR_H_MIN))
    nodes[-1]["ch_input_id"] = cursor_ch
    tags.append({"id": len(tags), "table_id": 0, "record_id": cursor_id,
                 "title": ("TIME CURSOR | x = current date (1970 left, 2020 "
                           "right) | height = attacks/month by these orgs")})
    next_id += 1
    for decade in range(YEAR_LO, YEAR_HI + 1, 10):
        f = (decade - YEAR_LO) * 12 * REPLAY_FRAMES_PER_MONTH
        x = x0 + (x1 - x0) * f / (REPLAY_FRAMES - 1)
        nodes.append(node_row(next_id, 0, 0, x, 0.0, cursor_z, 0.7,
                              (200, 200, 210), GEO_SPHERE_WIRE, TOPO_NONE))
        tags.append({"id": len(tags), "table_id": 0, "record_id": next_id,
                     "title": str(decade)})
        next_id += 1

    for row in nodes:
        row.setdefault("ch_input_id", 0)
    write_csv(out_dir / "CampaignPulse_gv_node.csv", REPLAY_NODE_FIELDS, nodes)
    write_csv(out_dir / "CampaignPulse_gv_tag.csv", TAG_FIELDS, tags)


# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=Path(
        r"C:\xampp\htdocs\antz\toroids\gtdb\new\globalterrorismdb_0522dist.xlsx"))
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent)
    parser.add_argument("--cache", type=Path, default=Path(
        tempfile.gettempdir()) / "gtdb_0522_cache.pkl")
    parser.add_argument("--no-cache", action="store_true",
                        help="re-parse the xlsx even if a cache exists")
    parser.add_argument("--min-attacks", type=int, default=10,
                        help="min attributed attacks for a profile rosette "
                             "(1 = every named org; default 10)")
    parser.add_argument("--max-events", type=int, default=0,
                        help="cap Event Cloud size, keeping the most lethal "
                             "(0 = all ~205k incidents)")
    parser.add_argument("--network-orgs", type=int, default=16,
                        help="organizations on the network ring")
    parser.add_argument("--links-per-org", type=int, default=400,
                        help="max link lines per org, most lethal events "
                             "first (0 = every event; drawn per-frame, so "
                             "high values cost FPS)")
    parser.add_argument("--replay-events", type=int, default=10_000,
                        help="approximate incident count for the Time_Replay "
                             "scene; Channels playback redraws every node "
                             "each frame, so bigger = slower (default 10000 "
                             "~ 100 ms/frame)")
    parser.add_argument("--pulse-orgs", type=int, default=100,
                        help="organizations on the Campaign_Pulse wall "
                             "(default 100 ~ 2.7k nodes, smooth playback)")
    parser.add_argument("--scenes", default="1,2,3,4,5",
                        help="comma-separated scene numbers to build "
                             "(default all: 1,2,3,4,5)")
    args = parser.parse_args()
    scenes = {int(s) for s in args.scenes.split(",") if s.strip()}

    print(f"Reading GTDB ...")
    df = load_gtdb(args.input, args.cache, not args.no_cache)
    print(f"  {len(df)} incidents {df['iyear'].min()}-{df['iyear'].max()}, "
          f"{df['gname'].nunique()} named orgs")

    if scenes & {1, 3, 5}:
        print("\nOrganization stats ...")
        stats, type_counts, bins = org_stats(df, args.min_attacks)
        print(f"  {len(stats)} orgs with >= {args.min_attacks} attacks")

    if 1 in scenes:
        print("\nScene 1: Organization Profiles")
        build_org_profiles(stats, type_counts, bins,
                           args.output_dir / "Organization_Profiles")

    if 2 in scenes:
        print("\nScene 2: Event Cloud")
        build_event_cloud(df, args.output_dir / "Event_Cloud", args.max_events)

    if 3 in scenes:
        print("\nScene 3: Org/Event Network")
        build_network(df, stats, type_counts, bins,
                      args.output_dir / "Org_Event_Network",
                      args.network_orgs, args.links_per_org)

    if 4 in scenes:
        print("\nScene 4: Time Replay")
        build_time_replay(df, args.output_dir / "Time_Replay",
                          args.replay_events)

    if 5 in scenes:
        print("\nScene 5: Campaign Pulse")
        build_campaign_pulse(df, stats, type_counts, bins,
                             args.output_dir / "Campaign_Pulse",
                             args.pulse_orgs)

    print("\nDone. File > Open Node CSV -> Organization_Profiles/"
          "OrgProfiles_gv_node.csv, Event_Cloud/EventCloud_gv_node.csv, "
          "Org_Event_Network/OrgEventNetwork_gv_node.csv, Time_Replay/"
          "TimeReplay_gv_node.csv, or Campaign_Pulse/CampaignPulse_gv_node"
          ".csv (the last two animate: Channels panel > play).")


if __name__ == "__main__":
    main()
