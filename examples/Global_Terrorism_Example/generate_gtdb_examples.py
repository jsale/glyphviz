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
  clock ring          up to 9 octahedron beads on a vertical wire ring at
                      fixed positions -- Assassination at 12 o'clock, then
                      clockwise in GTD attacktype order (Armed Assault,
                      Bombing, Hijacking, Barricade, Kidnapping,
                      Infrastructure, Unarmed, Unknown). Bead size =
                      log(count), legend color; absent types leave a gap.
  above               solid red sphere = total killed (log); orange wire
                      sphere above it = total wounded (log)
  below               blue wire sphere = geographic reach (log #countries)
  sparkline           activity timeline under the glyph: a Plot-topology
                      polyline of attacks per 5-year bin (1970-2020),
                      normalized to the org's own peak -- the *shape* of a
                      campaign (rise, peak, collapse, resurgence)

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

Scene 3 -- Org_Event_Network/  (node + tag)
--------------------------------------------
Scenes 1 + 2 combined: the top N organizations (default 16) float as
rosettes on a ring high above their full event cloud, and type-7 link
lines tie each org to its most lethal events (default 400/org -- links are
drawn per-frame, so unlimited links on a 12k-attack org would kill the
framerate; raise --links-per-org if your GPU disagrees). Each org gets a
distinct link hue so the cones of attribution stay separable, and its
rosette carries a small matching beacon so the cone can be traced back.

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
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

# Geometry / topology ids (glyphviz_core.geometry_data / topology)
GEO_SPHERE_WIRE, GEO_SPHERE = 2, 3
GEO_TORUS_WIRE = 6
GEO_OCTA = 11
GEO_GRID_WIRE = 20
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

# --- Rosette layout (all children of a hidden unit-scale anchor, Cartesian
# offsets in the X/Z plane so the glyph faces a viewer looking down -Y;
# raw scales stay >= 0.2 everywhere -- the renderer floors below that) ---
RING_R = 2.6                 # attack-type bead ring radius
RING_RATIO = 0.02            # hairline wire torus behind the beads
BEAD_MIN, BEAD_SPAN = 0.22, 0.9
CENTER_MIN, CENTER_SPAN = 0.55, 0.95
KILLED_Z, WOUNDED_Z = 4.2, 6.6
CASUALTY_MIN, CASUALTY_SPAN = 0.2, 1.1
REACH_Z = -4.4
REACH_MIN, REACH_SPAN = 0.25, 1.0
SPARK_Z = -8.2               # plot anchor under the glyph
SPARK_HALF_W = 3.3           # sparkline spans x -3.3..+3.3
SPARK_H = 2.2                # peak bin height
BIN_YEARS = 5
YEAR_LO, YEAR_HI = 1970, 2020
N_BINS = (YEAR_HI - YEAR_LO) // BIN_YEARS + 1     # 11 bins
GRID_DX, GRID_DZ = 10.5, 18.5

# --- Event cloud ---
Z_PER_YEAR = 2.0             # date axis: 1970-2020 -> 0..102 world units
EVENT_MIN, EVENT_SPAN = 0.2, 1.3
CAS_CAP = 500.0              # casualties that saturate the size ramp (log)

# --- Org/Event network ---
NET_RING_R = 115.0           # org rosettes on this ring...
NET_RING_Z = 135.0           # ...this far above the 1970 map plane
LINK_RATIO = 0.008           # per-frame drawn lines: keep them hairline
LINK_ALPHA = 70
BEACON_Z = 8.6               # org-colored beacon above the wounded sphere

NODE_FIELDS = [
    "id", "type", "parent_id", "branch_level", "child_id",
    "translate_x", "translate_y", "translate_z",
    "rotate_x", "rotate_y", "rotate_z",
    "scale_x", "scale_y", "scale_z",
    "color_r", "color_g", "color_b", "color_a",
    "geometry", "hide", "topo", "ratio",
]
TAG_FIELDS = ["id", "table_id", "record_id", "title"]


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
             ratio=0.1, rx=0.0, sy=None, sz=None):
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
    """Append one org rosette; returns (next_id, center_node_id)."""
    anchor = next_id
    nodes.append(node_row(anchor, 0, 0, x, y, z, 1.0, (0, 0, 0),
                          GEO_POINT, TOPO_NONE, hide=1))
    nid = anchor + 1

    # Center octahedron: total volume + dominant attack type
    dom = int(st["dominant_type"])
    center_id = nid
    c_scale = CENTER_MIN + CENTER_SPAN * logn(st["attacks"], norms.max_attacks)
    nodes.append(node_row(nid, anchor, 1, 0, 0, 0, c_scale, ATTACK_RGB[dom],
                          GEO_OCTA, TOPO_NONE))
    tags.append({"id": len(tags), "table_id": 0, "record_id": nid, "title": (
        f"{gname} | {st['attacks']:.0f} attacks {st['year_lo']:.0f}-{st['year_hi']:.0f}"
        f" | {st['killed']:.0f} killed {st['wounded']:.0f} wounded"
        f" | dominant: {ATTACK_SHORT[dom]} | top target: {st['top_target']}"
        f" | suicide {fmt_pct(st['suicide'])} | success {fmt_pct(st['success'])}")})
    nid += 1

    # Vertical hairline ring the beads sit on (rotate 90 about X -> X/Z plane)
    nodes.append(node_row(nid, anchor, 1, 0, 0, 0, RING_R, (90, 95, 105),
                          GEO_TORUS_WIRE, TOPO_NONE, alpha=120,
                          ratio=RING_RATIO, rx=90))
    nid += 1

    # Attack-type beads at fixed clock positions (type 1 at 12 o'clock)
    for atype in range(1, 10):
        cnt = int(tcounts[atype])
        if cnt == 0:
            continue
        theta = math.radians(90 - (atype - 1) * 40)
        b = BEAD_MIN + BEAD_SPAN * logn(cnt, norms.max_type)
        nodes.append(node_row(nid, anchor, 1, RING_R * math.cos(theta), 0,
                              RING_R * math.sin(theta), b, ATTACK_RGB[atype],
                              GEO_OCTA, TOPO_NONE))
        tags.append({"id": len(tags), "table_id": 0, "record_id": nid,
                     "title": f"{gname} | {ATTACK_SHORT[atype]}: {cnt} attacks"})
        nid += 1

    # Casualty spire: killed (solid red) with wounded (wire orange) above
    k = CASUALTY_MIN + CASUALTY_SPAN * logn(st["killed"], norms.max_killed)
    nodes.append(node_row(nid, anchor, 1, 0, 0, KILLED_Z, k, (255, 40, 40),
                          GEO_SPHERE, TOPO_NONE))
    tags.append({"id": len(tags), "table_id": 0, "record_id": nid,
                 "title": f"{gname} | {st['killed']:.0f} killed"})
    nid += 1
    w = CASUALTY_MIN + CASUALTY_SPAN * logn(st["wounded"], norms.max_wounded)
    nodes.append(node_row(nid, anchor, 1, 0, 0, WOUNDED_Z, w, (255, 150, 0),
                          GEO_SPHERE_WIRE, TOPO_NONE))
    tags.append({"id": len(tags), "table_id": 0, "record_id": nid,
                 "title": f"{gname} | {st['wounded']:.0f} wounded"})
    nid += 1

    # Reach sphere: how many countries the org has struck
    r = REACH_MIN + REACH_SPAN * logn(st["countries"], norms.max_countries)
    nodes.append(node_row(nid, anchor, 1, 0, 0, REACH_Z, r, (80, 140, 255),
                          GEO_SPHERE_WIRE, TOPO_NONE))
    tags.append({"id": len(tags), "table_id": 0, "record_id": nid, "title": (
        f"{gname} | struck in {st['countries']:.0f} "
        f"{'country' if st['countries'] == 1 else 'countries'}"
        f" | most: {st['top_country']}")})
    nid += 1

    # Activity sparkline: Plot-topology polyline, 5-year bins, own-peak scale
    peak = max(int(tbins.max()), 1)
    peak_bin = int(tbins.idxmax())
    plot_id = nid
    nodes.append(node_row(plot_id, anchor, 1, 0, 0, SPARK_Z, 0.2,
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
        nodes.append(node_row(nid, plot_id, 2, -SPARK_HALF_W + i * step, 0, h,
                              0.2, shade, GEO_OCTA, TOPO_NONE))
        tags.append({"id": len(tags), "table_id": 0, "record_id": nid, "title":
                     f"{gname} | {YEAR_LO + i * BIN_YEARS}-"
                     f"{min(YEAR_LO + i * BIN_YEARS + 4, YEAR_HI)}: {cnt} attacks"})
        nid += 1

    # Org-colored beacon (network scene): ties the rosette to its link cone
    if beacon_rgb is not None:
        nodes.append(node_row(nid, anchor, 1, 0, 0, BEACON_Z, 0.6, beacon_rgb,
                              GEO_OCTA, TOPO_NONE))
        tags.append({"id": len(tags), "table_id": 0, "record_id": nid,
                     "title": f"{gname} | link-line color beacon"})
        nid += 1

    return nid, center_id


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


def add_map_furniture(nodes, tags, next_id) -> int:
    """Ground grid at 1970 plus decade markers up the date axis."""
    nodes.append(node_row(next_id, 0, 0, 0, 10, -0.5, 195.0, (55, 60, 75),
                          GEO_GRID_WIRE, TOPO_NONE, alpha=130, sy=100.0, sz=1.0))
    tags.append({"id": len(tags), "table_id": 0, "record_id": next_id, "title": (
        "GTD EVENT CLOUD | X longitude, Y latitude, Z date (1970 at the grid, "
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
    next_id = add_map_furniture(nodes, tags, 1)
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
    next_id = add_map_furniture(nodes, tags, 1)
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
    args = parser.parse_args()

    print(f"Reading GTDB ...")
    df = load_gtdb(args.input, args.cache, not args.no_cache)
    print(f"  {len(df)} incidents {df['iyear'].min()}-{df['iyear'].max()}, "
          f"{df['gname'].nunique()} named orgs")

    print("\nOrganization stats ...")
    stats, type_counts, bins = org_stats(df, args.min_attacks)
    print(f"  {len(stats)} orgs with >= {args.min_attacks} attacks")

    print("\nScene 1: Organization Profiles")
    build_org_profiles(stats, type_counts, bins,
                       args.output_dir / "Organization_Profiles")

    print("\nScene 2: Event Cloud")
    build_event_cloud(df, args.output_dir / "Event_Cloud", args.max_events)

    print("\nScene 3: Org/Event Network")
    build_network(df, stats, type_counts, bins,
                  args.output_dir / "Org_Event_Network",
                  args.network_orgs, args.links_per_org)

    print("\nDone. File > Open Node CSV -> Organization_Profiles/"
          "OrgProfiles_gv_node.csv, Event_Cloud/EventCloud_gv_node.csv, or "
          "Org_Event_Network/OrgEventNetwork_gv_node.csv.")


if __name__ == "__main__":
    main()
