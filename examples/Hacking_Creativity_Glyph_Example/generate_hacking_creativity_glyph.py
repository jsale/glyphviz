#!/usr/bin/env python3
"""
generate_hacking_creativity_glyph.py
=====================================
Legible single-person "creative style" glyph for the Hacking Creativity
dataset (Red Bull High Performance Team / Vibrant Data Mappr, 2015) --
replacing Jeff's original 2015 ANTz hyperglyph, which packed one ring/cube
per raw survey question (100+ permanently tag-labeled primitives per person)
into a single glyph and was, by his own assessment, too dense to read.

Design
------
Per person:
  - Root sphere = identity core. Color = a pale tint hashed from their
    Louvain0 ClusterLabel (so every member of the same creative-style
    cluster renders the same root hue, even across different parts of the
    scene). Scale nudges up slightly with network degree.
  - A ring of up to 13 *fixed* angular slots, one per Mappr-derived
    creative-style dimension (Pace, Mood, Kinetic/Cerebral/Intuitive, etc.).
    These are Mappr's own distillation of the ~120 raw survey answers, so
    they're the always-visible primary signal -- not the raw answers
    themselves. A slot is left empty (no sphere) if that dimension wasn't
    computed for this person: an honest gap, not papered over. Each present
    slot's hue is fixed by its dimension (same angle + hue on every
    person's glyph, so two people's rings are directly comparable at a
    glance); brightness is a hash of this person's specific category value,
    so two different values are visually distinguishable without implying
    a false order across dimensions that aren't actually ordinal (e.g.
    "Doer/Envisioner/Evaluator/Ideator" has no natural ordering).
  - A faint outer wire-torus halo encodes raw network reach (degree /
    betweenness centrality) as secondary context, kept visually subordinate
    (thin, translucent) to the personal-style ring.
  - Every node has a tag, but they're meant to be viewed with GlyphViz's
    existing "Tags: Selected Only" toggle on (Viewport.show_tags_selected_
    only) -- raw survey answers and exact dimension values are on-demand
    detail, not painted on screen all at once.

Cluster-exemplar mode (default) builds ONE characteristic glyph per Louvain0
cluster (13, not ~662) rather than one per person. This replaced an earlier
per-person "all participants" layout after checking the data directly: the
13 derived dimension columns turned out to be 100% identical within a
cluster (they're literally what `ClusterLabel` is assembled from, not an
independent per-person measurement), so showing more than one person's
dimension-ring per cluster added zero information. The real per-person
variation in this dataset lives in raw survey text and network position --
so the exemplar glyph keeps the dimension ring (now correctly shown once,
since it's exactly representative) and replaces the old per-person halo
with cluster-level network statistics, which is where actual within-cluster
spread exists:
  - Root size = cluster size (log-normalized across all 13 clusters).
  - Halo (color temperature white->gold, tube thickness) = mean degree
    within the cluster.
  - A "hub spike" (a marker raised along the root's own axis) = the
    highest single degree in the cluster, so a cluster with one
    well-connected hub looks visibly different from a uniformly
    peripheral one even at the same mean degree.
  - Three small cube markers (centrality / bridging / diversity, their
    Louvain0 cluster-level averages) sit below the dimension ring,
    deliberately a different geometry so they're not mistaken for more
    dimension slots; brightness = normalized magnitude.

Usage
-----
    python generate_hacking_creativity_glyph.py                 # 13 cluster-exemplar glyphs (default)
    python generate_hacking_creativity_glyph.py --id 218         # one real person's glyph, centered at the origin
    python generate_hacking_creativity_glyph.py --out-dir DIR

Load in GlyphViz: File > Open Node CSV -> Hacking_Creativity_Glyph_Example_gv_node.csv
Then enable Display > "Tags: Selected Only" and click any node to read its detail.
"""
import argparse
import colorsys
import csv
import hashlib
import math
import re
import warnings
from pathlib import Path

import pandas as pd

XLSX_PATH = r"C:\xampp\htdocs\antz\toroids\hacking_creativity\CreativitySurvey+PeopleNetworkWithCalcAttrib.xlsx"

OUTPUT_DIR = Path(__file__).parent
PREFIX = "Hacking_Creativity_Glyph_Example"

DIMENSIONS = [
    "Time", "Juggle/Specialist", "Focus", "Details",
    "Kinetic/Cerebral/Intuitive", "Organization", "Process", "Pace",
    "Confidence", "Social/Solitary", "Mood", "Adaptable/Determined",
    "Chance/Risk/Habit",
]
N_DIMS = len(DIMENSIONS)

GEO_SPHERE = 3
GEO_TORUS_WIRE = 6
GEO_CUBE = 1
GEO_POINT = 22

# Single-person geometry, in "raw" units -- a child's *world* size/position
# is this raw value times the root's own scale (matrices compose down the
# hierarchy automatically), so these constants should NOT also be
# multiplied by the population shrink factor; only the root itself (which
# has no parent to inherit a multiplier from) needs that applied directly.
ROOT_SCALE_BASE = 1.0
ROOT_SCALE_PER_DEGREE = 0.01
SPOKE_SCALE = 0.3          # own-scale; world size = root_scale * this
SPOKE_RADIAL_OFFSET = 1.5
HALO_RADIAL_OFFSET = 2.6
HALO_TUBE_RATIO = 0.12

# Cluster-exemplar layout: 13 glyphs, one per cluster, arranged in a grid.
# Spacing must clear the largest cluster's halo radius (root_scale can reach
# ~1.8, and halo sits at root_scale*(1+HALO_RADIAL_OFFSET) =~ 1.8*3.6 =~ 6.5),
# so two max-size neighbors need >= ~13 between centers; pad well past that.
CLUSTER_LAYOUT_SPACING = 20.0
CLUSTERS_PER_ROW = 4


def load_all_people() -> pd.DataFrame:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        nodes = pd.read_excel(XLSX_PATH, sheet_name="Nodes")
    return nodes.iloc[1:].reset_index(drop=True)  # row 0 is a bogus header-artifact row


def top_ranked(value) -> str | None:
    """Pull the first quoted item out of a Mappr ranked-list string like
    '["Nature"~"History"~...]'."""
    if not isinstance(value, str):
        return None
    m = re.search(r'"([^"]+)"', value)
    return m.group(1) if m else None


def value_band(value: str) -> float:
    bands = (0.45, 0.65, 0.9)
    h = int(hashlib.md5(value.encode()).hexdigest(), 16)
    return bands[h % len(bands)]


def dim_color(dim_index: int, value: str) -> tuple[int, int, int]:
    hue = dim_index / N_DIMS
    v = value_band(value)
    r, g, b = colorsys.hsv_to_rgb(hue, 0.85, v)
    return round(r * 255), round(g * 255), round(b * 255)


def cluster_color(cluster_label) -> tuple[int, int, int]:
    h = int(hashlib.md5(str(cluster_label).encode()).hexdigest(), 16)
    hue = (h % 360) / 360.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.25, 0.92)  # pale -- recedes vs. bright spokes
    return round(r * 255), round(g * 255), round(b * 255)


def build_person(
    p: dict, person_id: int, center: tuple[float, float, float],
    scale: float, nid: int, tag_id: int,
) -> tuple[list[dict], list[dict], int, int]:
    """Returns (node_rows, tag_rows, next_nid, next_tag_id) for one person,
    rooted at world position *center*, scaled by *scale* (1.0 = the
    single-person preview's own native size)."""
    node_rows, tag_rows = [], []

    root_id = nid
    degree = float(p.get("degree") or 0)
    root_color = cluster_color(p.get("ClusterLabel"))
    root_scale = (ROOT_SCALE_BASE + ROOT_SCALE_PER_DEGREE * degree) * scale
    node_rows.append({
        "id": root_id, "type": 5, "parent_id": 0, "branch_level": 0,
        "translate_x": round(center[0], 4), "translate_y": round(center[1], 4),
        "translate_z": round(center[2], 4),
        "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
        "scale_x": root_scale, "scale_y": root_scale, "scale_z": root_scale,
        "color_r": root_color[0], "color_g": root_color[1], "color_b": root_color[2], "color_a": 255,
        "geometry": GEO_SPHERE, "hide": 0, "topo": 4,  # Cylinder: rings its children
        "ratio": 0.15, "facet": 1,
    })

    inspiration = top_ranked(p.get("Where you get inspiration."))
    best_at = top_ranked(p.get("Best at"))
    role = top_ranked(p.get("Others describe your role"))
    drive = top_ranked(p.get("What drives you"))
    identity_bits = [
        f"id {person_id} -- cluster: {p.get('ClusterLabel')}",
        f"Inspired primarily by: {inspiration}" if inspiration else None,
        f"Sees self as: {role}" if role else None,
        f"Best at: {best_at}" if best_at else None,
        f"Driven by: {drive}" if drive else None,
        f"Network reach: degree {int(degree)}, betweenness "
        f"{float(p.get('betweennessCentrality') or 0):.3f}",
    ]
    tag_rows.append({
        "id": tag_id, "table_id": 0, "record_id": root_id,
        "title": " | ".join(b for b in identity_bits if b),
    })
    tag_id += 1
    nid += 1

    for i, dim in enumerate(DIMENSIONS):
        value = p.get(dim)
        if not isinstance(value, str) or value.strip() in ("", "."):
            continue  # honest gap: dimension not computed for this person
        angle = i * (360.0 / N_DIMS)
        color = dim_color(i, value)
        spoke_id = nid
        node_rows.append({
            "id": spoke_id, "type": 5, "parent_id": root_id, "branch_level": 1,
            "translate_x": round(angle, 4), "translate_y": 0.0,
            "translate_z": round(SPOKE_RADIAL_OFFSET, 4),
            "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
            "scale_x": SPOKE_SCALE, "scale_y": SPOKE_SCALE, "scale_z": SPOKE_SCALE,
            "color_r": color[0], "color_g": color[1], "color_b": color[2], "color_a": 255,
            "geometry": GEO_SPHERE, "hide": 0, "topo": 0,
            "ratio": 0.1, "facet": 1,
        })
        tag_rows.append({
            "id": tag_id, "table_id": 0, "record_id": spoke_id,
            "title": f"{dim}: {value}",
        })
        tag_id += 1
        nid += 1

    # Network-context halo: a faint wire torus around the whole spoke ring.
    halo_id = nid
    node_rows.append({
        "id": halo_id, "type": 5, "parent_id": root_id, "branch_level": 1,
        "translate_x": 0.0, "translate_y": 0.0,
        "translate_z": round(HALO_RADIAL_OFFSET, 4),
        "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
        "scale_x": 1.0, "scale_y": 1.0, "scale_z": 1.0,
        "color_r": 200, "color_g": 200, "color_b": 200, "color_a": 110,
        "geometry": GEO_TORUS_WIRE, "hide": 0, "topo": 0,
        "ratio": HALO_TUBE_RATIO, "facet": 1,
    })
    tag_rows.append({
        "id": tag_id, "table_id": 0, "record_id": halo_id,
        "title": (
            f"Network context: degree {int(degree)}, betweenness "
            f"{float(p.get('betweennessCentrality') or 0):.3f}, "
            f"bridging {float(p.get('bridging_Louvain0') or 0):.2f}, "
            f"cluster size {p.get('ClusterSize')}, "
            f"diversity {float(p.get('diversity_Louvain0') or 0):.2f}"
        ),
    })
    tag_id += 1
    nid += 1

    return node_rows, tag_rows, nid, tag_id


def cluster_sort_key(cluster: str) -> int:
    m = re.search(r"(\d+)$", str(cluster))
    return int(m.group(1)) if m else 0


def cluster_dimension_value(members: pd.DataFrame, dim: str) -> str | None:
    vals = members[dim].dropna()
    vals = vals[vals.astype(str).str.strip() != "."]
    return None if vals.empty else vals.mode().iloc[0]


def make_normalizer(values, log: bool = False):
    xs = [math.log(max(v, 1.0)) if log else float(v) for v in values]
    lo, hi = min(xs), max(xs)
    span = (hi - lo) or 1.0
    return lambda v: ((math.log(max(v, 1.0)) if log else float(v)) - lo) / span


def lerp_color(c0: tuple[int, int, int], c1: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return tuple(round(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))


def build_cluster_exemplar(
    cluster: str, members: pd.DataFrame, center: tuple[float, float, float],
    norm: dict, nid: int, tag_id: int,
) -> tuple[list[dict], list[dict], int, int]:
    """Returns (node_rows, tag_rows, next_nid, next_tag_id) for one cluster's
    characteristic glyph, rooted at world position *center*."""
    node_rows, tag_rows = [], []
    label = members["ClusterLabel"].iloc[0]
    n = len(members)
    mean_degree = members["degree"].mean()
    max_degree = members["degree"].max()
    mean_centrality = members["centrality_Louvain0"].mean()
    mean_bridging = members["bridging_Louvain0"].mean()
    mean_diversity = members["diversity_Louvain0"].mean()

    size_t = norm["size"](n)
    degree_t = norm["mean_degree"](mean_degree)
    maxdeg_t = norm["max_degree"](max_degree)
    central_t = norm["centrality"](mean_centrality)
    bridge_t = norm["bridging"](mean_bridging)
    divers_t = norm["diversity"](mean_diversity)

    root_id = nid
    root_color = cluster_color(label)
    root_scale = ROOT_SCALE_BASE + 0.8 * size_t
    node_rows.append({
        "id": root_id, "type": 5, "parent_id": 0, "branch_level": 0,
        "translate_x": round(center[0], 4), "translate_y": round(center[1], 4),
        "translate_z": round(center[2], 4),
        "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
        "scale_x": root_scale, "scale_y": root_scale, "scale_z": root_scale,
        "color_r": root_color[0], "color_g": root_color[1], "color_b": root_color[2], "color_a": 255,
        "geometry": GEO_SPHERE, "hide": 0, "topo": 4,  # Cylinder: rings its children
        "ratio": 0.15, "facet": 1,
    })
    tag_rows.append({
        "id": tag_id, "table_id": 0, "record_id": root_id,
        "title": (
            f"{cluster}: {label} -- {n} members | mean degree {mean_degree:.1f} "
            f"(highest {int(max_degree)}) | mean centrality {mean_centrality:.2f}, "
            f"bridging {mean_bridging:.2f}, diversity {mean_diversity:.2f}"
        ),
    })
    tag_id += 1
    nid += 1

    for i, dim in enumerate(DIMENSIONS):
        value = cluster_dimension_value(members, dim)
        if value is None:
            continue  # this dimension wasn't computed for anyone in the cluster
        angle = i * (360.0 / N_DIMS)
        color = dim_color(i, value)
        spoke_id = nid
        node_rows.append({
            "id": spoke_id, "type": 5, "parent_id": root_id, "branch_level": 1,
            "translate_x": round(angle, 4), "translate_y": 0.0,
            "translate_z": round(SPOKE_RADIAL_OFFSET, 4),
            "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
            "scale_x": SPOKE_SCALE, "scale_y": SPOKE_SCALE, "scale_z": SPOKE_SCALE,
            "color_r": color[0], "color_g": color[1], "color_b": color[2], "color_a": 255,
            "geometry": GEO_SPHERE, "hide": 0, "topo": 0,
            "ratio": 0.1, "facet": 1,
        })
        tag_rows.append({
            "id": tag_id, "table_id": 0, "record_id": spoke_id,
            "title": f"{dim}: {value} (shared by all {n} members of this cluster)",
        })
        tag_id += 1
        nid += 1

    # Halo = mean degree within the cluster (white -> gold as it rises).
    halo_id = nid
    halo_color = lerp_color((190, 190, 205), (255, 195, 60), degree_t)
    node_rows.append({
        "id": halo_id, "type": 5, "parent_id": root_id, "branch_level": 1,
        "translate_x": 0.0, "translate_y": 0.0,
        "translate_z": round(HALO_RADIAL_OFFSET, 4),
        "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
        "scale_x": 1.0, "scale_y": 1.0, "scale_z": 1.0,
        "color_r": halo_color[0], "color_g": halo_color[1], "color_b": halo_color[2], "color_a": 160,
        "geometry": GEO_TORUS_WIRE, "hide": 0, "topo": 0,
        "ratio": round(0.08 + 0.22 * degree_t, 4), "facet": 1,
    })
    tag_rows.append({
        "id": tag_id, "table_id": 0, "record_id": halo_id,
        "title": f"Mean degree within cluster: {mean_degree:.1f}",
    })
    tag_id += 1
    nid += 1

    # Hub spike: raised along the root's own axis, height/size = highest
    # single degree in the cluster -- a tall spike means this archetype has
    # at least one well-connected hub, not just uniformly peripheral members.
    spike_id = nid
    node_rows.append({
        "id": spike_id, "type": 5, "parent_id": root_id, "branch_level": 1,
        "translate_x": 0.0, "translate_y": round(1.0 + 3.0 * maxdeg_t, 4),
        "translate_z": 0.0,
        "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
        "scale_x": 0.2 + 0.18 * maxdeg_t, "scale_y": 0.2 + 0.18 * maxdeg_t, "scale_z": 0.2 + 0.18 * maxdeg_t,
        "color_r": 255, "color_g": 200, "color_b": 60, "color_a": 255,
        "geometry": GEO_SPHERE, "hide": 0, "topo": 0,
        "ratio": 0.1, "facet": 1,
    })
    tag_rows.append({
        "id": tag_id, "table_id": 0, "record_id": spike_id,
        "title": f"Highest-degree member in this cluster: degree {int(max_degree)}",
    })
    tag_id += 1
    nid += 1

    # Three cube markers (centrality / bridging / diversity), deliberately a
    # different geometry from the dimension-ring spheres and sitting below
    # the equator, so they read as cluster-level network stats, not more
    # dimension slots.
    for j, (stat_name, t, val) in enumerate((
        ("Centrality", central_t, mean_centrality),
        ("Bridging", bridge_t, mean_bridging),
        ("Diversity", divers_t, mean_diversity),
    )):
        marker_id = nid
        bright = round(70 + 160 * t)
        node_rows.append({
            "id": marker_id, "type": 5, "parent_id": root_id, "branch_level": 1,
            "translate_x": round(j * 120.0, 4), "translate_y": -1.3,
            "translate_z": round(SPOKE_RADIAL_OFFSET * 0.7, 4),
            "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
            "scale_x": 0.25 + 0.22 * t, "scale_y": 0.25 + 0.22 * t, "scale_z": 0.25 + 0.22 * t,
            "color_r": bright, "color_g": bright, "color_b": bright, "color_a": 255,
            "geometry": GEO_CUBE, "hide": 0, "topo": 0,
            "ratio": 1.0, "facet": 1,
        })
        tag_rows.append({
            "id": tag_id, "table_id": 0, "record_id": marker_id,
            "title": f"{stat_name} (mean within cluster): {val:.2f}",
        })
        tag_id += 1
        nid += 1

    return node_rows, tag_rows, nid, tag_id


def build_all_clusters(df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    node_rows, tag_rows = [], []
    nid, tag_id = 1, 1

    clusters = sorted(df["Cluster"].unique(), key=cluster_sort_key)
    members_by_cluster = {c: df[df["Cluster"] == c] for c in clusters}
    print(f"  {len(clusters)} clusters, {len(df)} participants")

    norm = {
        "size": make_normalizer([len(m) for m in members_by_cluster.values()], log=True),
        "mean_degree": make_normalizer([m["degree"].mean() for m in members_by_cluster.values()]),
        "max_degree": make_normalizer([m["degree"].max() for m in members_by_cluster.values()], log=True),
        "centrality": make_normalizer([m["centrality_Louvain0"].mean() for m in members_by_cluster.values()]),
        "bridging": make_normalizer([m["bridging_Louvain0"].mean() for m in members_by_cluster.values()]),
        "diversity": make_normalizer([m["diversity_Louvain0"].mean() for m in members_by_cluster.values()]),
    }

    for idx, cluster in enumerate(clusters):
        col, row = idx % CLUSTERS_PER_ROW, idx // CLUSTERS_PER_ROW
        center = (col * CLUSTER_LAYOUT_SPACING, -row * CLUSTER_LAYOUT_SPACING, 0.0)
        c_node_rows, c_tag_rows, nid, tag_id = build_cluster_exemplar(
            cluster, members_by_cluster[cluster], center, norm, nid, tag_id,
        )
        node_rows.extend(c_node_rows)
        tag_rows.extend(c_tag_rows)

    return node_rows, tag_rows


NODE_FIELDS = [
    "id", "type", "parent_id", "branch_level",
    "translate_x", "translate_y", "translate_z",
    "rotate_x", "rotate_y", "rotate_z",
    "scale_x", "scale_y", "scale_z",
    "color_r", "color_g", "color_b", "color_a",
    "geometry", "hide", "topo", "ratio", "facet",
]
TAG_FIELDS = ["id", "table_id", "record_id", "title"]


def write_csvs(node_rows: list[dict], tag_rows: list[dict], out_dir: Path, prefix: str) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    node_path = out_dir / f"{prefix}_gv_node.csv"
    tag_path = out_dir / f"{prefix}_gv_tag.csv"
    with open(node_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=NODE_FIELDS)
        w.writeheader()
        w.writerows(node_rows)
    with open(tag_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TAG_FIELDS)
        w.writeheader()
        w.writerows(tag_rows)
    print(f"  {node_path.name}: {len(node_rows)} nodes")
    print(f"  {tag_path.name}: {len(tag_rows)} tags")
    return node_path, tag_path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--id", type=int, default=None,
                     help="Generate one real person's glyph at the origin instead of the 13 cluster exemplars.")
    ap.add_argument("--out-dir", type=Path, default=OUTPUT_DIR)
    args = ap.parse_args()

    df = load_all_people()

    if args.id is not None:
        row = df[df["id"] == args.id]
        if row.empty:
            raise SystemExit(f"id {args.id} not found")
        node_rows, tag_rows, _, _ = build_person(
            row.iloc[0].to_dict(), args.id, (0.0, 0.0, 0.0), 1.0, 1, 1,
        )
        write_csvs(node_rows, tag_rows, args.out_dir, f"{PREFIX}_person{args.id}")
    else:
        node_rows, tag_rows = build_all_clusters(df)
        write_csvs(node_rows, tag_rows, args.out_dir, PREFIX)

    print("Done.")


if __name__ == "__main__":
    main()
