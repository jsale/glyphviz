#!/usr/bin/env python3
"""
hyperglyph_generator.py
========================
Procedural design engine for GlyphViz "hyperglyphs": multi-level branching
node hierarchies intended as music-synesthesia glyphs. Built on top of the
same GlyphRecipe/LevelSpec model that powers the Glyph Composer GUI
(glyphviz_core/glyph_recipe.py) — every design this module produces also
saves a recipe .json, so any generated hyperglyph can be opened in
Tools > Glyph Composer for hand-tweaking afterward.

This module is import-only logic (no CLI, no notebook cells) so it can be
shared by generate_hyperglyphs.py and generate_hyperglyphs.ipynb.

Design loop
-----------
Each call to generate_batch() writes, per design:
  - a stamped gv_node.csv / gv_tag.csv pair (loadable directly in GlyphViz)
  - a matching recipe .json (openable in Glyph Composer)
and appends one row to hyperglyph_lab/ratings.csv with the design's
parameters plus blank rating/categories/notes columns.

Rating loop (the "learning" part): after Jeff scores past designs in
ratings.csv, new batches spend part of their budget "exploiting" — mutating
a past top-rated design's recipe with small random jitter — instead of
pure random exploration. See RatingsStore.top_designs() and mutate_recipe().
"""
from __future__ import annotations

import colorsys
import csv
import random
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from glyphviz_core.node import Node
from glyphviz_core.geometry_data import (
    GEO_CUBE, GEO_CUBE_WIRE, GEO_SPHERE, GEO_SPHERE_WIRE, GEO_CONE, GEO_CONE_WIRE,
    GEO_TORUS, GEO_TORUS_WIRE, GEO_DODECA, GEO_DODECA_WIRE, GEO_OCTA, GEO_OCTA_WIRE,
    GEO_TETRA, GEO_TETRA_WIRE, GEO_ICOSA, GEO_ICOSA_WIRE, GEO_PIN, GEO_PIN_WIRE,
    GEO_CYLINDER, GEO_CYLINDER_WIRE, GEO_POINT, GEO_CIRCLE, GEO_CROSS, GEO_STAR,
)
from glyphviz_core.topology import (
    TOPO_SPHERE, TOPO_TORUS, TOPO_CYLINDER, TOPO_PIN, TOPO_ROD, TOPO_POINT,
    TOPO_ZSPHERE, TOPO_ZTORUS, TOPO_ZCYLINDER, TOPO_ZROD, TOPO_SPIRAL,
)
from glyphviz_core.glyph_recipe import (
    GlyphRecipe, LevelSpec, generate_nodes,
    DIST_LINEAR, DIST_ANGULAR,
    save_recipe, load_recipe,
)
from glyphviz_core.csv_reader import save_node_csv, save_tag_csv, stamp_node_and_tag_paths

# ------------------------------------------------------------------------------
# Aesthetic vocabulary
# ------------------------------------------------------------------------------

# Topologies whose angular coordinate (translate_x = 0..360) is what
# DIST_ANGULAR feeds children. Cube/Plane/None/Video/Plot/Surface use tx for
# something else entirely (face-plane UV, plot index, ...) and would fling
# angularly-distributed children into nonsense positions, so they're excluded
# from the branching pool. (Confirmed against Topology-Guide.md conventions —
# see gaiaviz-skill/references/structure/Topology-Guide.md.)
ANGULAR_SAFE_TOPOS = [
    TOPO_SPHERE, TOPO_TORUS, TOPO_CYLINDER, TOPO_PIN, TOPO_ROD, TOPO_POINT,
    TOPO_ZSPHERE, TOPO_ZTORUS, TOPO_ZCYLINDER, TOPO_ZROD, TOPO_SPIRAL,
]

# Geometry "families" — picking one family per design (rather than a fully
# free-for-all mix of all 24 usable shapes) is what keeps a 5-level, 2000-node
# hyperglyph reading as one coherent creature instead of visual noise.
# GEO_MESH is intentionally excluded: it needs a real mesh_id reference we
# don't have here.
GEO_FAMILIES = {
    "platonic": [GEO_TETRA, GEO_TETRA_WIRE, GEO_OCTA, GEO_OCTA_WIRE,
                 GEO_DODECA, GEO_DODECA_WIRE, GEO_ICOSA, GEO_ICOSA_WIRE,
                 GEO_CUBE, GEO_CUBE_WIRE],
    "round": [GEO_SPHERE, GEO_SPHERE_WIRE, GEO_TORUS, GEO_TORUS_WIRE,
              GEO_CYLINDER, GEO_CYLINDER_WIRE, GEO_CONE, GEO_CONE_WIRE],
    "wire_only": [GEO_CUBE_WIRE, GEO_SPHERE_WIRE, GEO_CONE_WIRE, GEO_TORUS_WIRE,
                  GEO_DODECA_WIRE, GEO_OCTA_WIRE, GEO_TETRA_WIRE, GEO_ICOSA_WIRE,
                  GEO_PIN_WIRE, GEO_CYLINDER_WIRE],
    "spiky": [GEO_CONE, GEO_CONE_WIRE, GEO_PIN, GEO_PIN_WIRE, GEO_TETRA,
              GEO_TETRA_WIRE, GEO_STAR],
    "particles": [GEO_POINT, GEO_CIRCLE, GEO_CROSS, GEO_STAR],
    "mixed": [GEO_SPHERE, GEO_TORUS, GEO_CYLINDER, GEO_OCTA, GEO_ICOSA,
              GEO_DODECA, GEO_CONE, GEO_PIN, GEO_CIRCLE, GEO_STAR],
}

# Hue-relationship schemes (colour theory, not random RGB per level — keeps
# a whole hyperglyph's palette feeling designed rather than noisy).
PALETTE_SCHEMES = [
    "monochrome", "analogous", "complementary", "triadic",
    "split_complementary", "rainbow",
]

MIN_BRANCH = 2
MAX_BRANCH = 12


# ------------------------------------------------------------------------------
# Node-count budgeting
# ------------------------------------------------------------------------------

def _total_nodes(counts: list[int]) -> int:
    """1 (root) + running child-count products, i.e. the full-tree node total
    for per-level branching factors `counts` (root's own count is always 1)."""
    total = 1
    running = 1
    for c in counts:
        running *= c
        total += running
    return total


def pick_level_counts(depth: int, max_nodes: int, rng: random.Random) -> list[int]:
    """Pick `depth` branching factors (children-per-parent for levels 1..depth)
    that keep the full tree at or under max_nodes, randomized around a scale
    appropriate to the budget rather than uniformly maxed out — organic,
    asymmetric branch counts read as more "grown" than a perfectly regular
    tree with identical counts at every level."""
    if depth <= 0:
        return []
    guess = max(MIN_BRANCH, round(max_nodes ** (1.0 / depth)))
    counts = [
        max(1, rng.randint(max(MIN_BRANCH, guess - 2), min(MAX_BRANCH, guess + 2)))
        for _ in range(depth)
    ]
    # Greedily shrink whichever level currently has the most nodes-under-it
    # until the budget is met (favors trimming leaf/near-leaf levels first,
    # since those levels multiply the total the most).
    while _total_nodes(counts) > max_nodes and any(c > 1 for c in counts):
        idx = max(range(depth), key=lambda i: (counts[i] > 1, i))
        counts[idx] -= 1
    return counts


# ------------------------------------------------------------------------------
# Colour
# ------------------------------------------------------------------------------

def _hsv_to_rgb255(h: float, s: float, v: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))
    return int(round(r * 255)), int(round(g * 255)), int(round(b * 255))


def make_palette(scheme: str, n_levels: int, rng: random.Random) -> list[float]:
    """Return one base hue (0..1) per level, related according to `scheme`."""
    base = rng.random()
    if n_levels <= 1:
        return [base]
    if scheme == "monochrome":
        return [base] * n_levels
    if scheme == "analogous":
        spread = 0.10
        return [(base + (i / (n_levels - 1) - 0.5) * 2 * spread) % 1.0 for i in range(n_levels)]
    if scheme == "complementary":
        return [(base if i % 2 == 0 else base + 0.5) % 1.0 for i in range(n_levels)]
    if scheme == "triadic":
        offsets = [0.0, 1 / 3, 2 / 3]
        return [(base + offsets[i % 3]) % 1.0 for i in range(n_levels)]
    if scheme == "split_complementary":
        offsets = [0.0, 0.5 - 0.08, 0.5 + 0.08]
        return [(base + offsets[i % 3]) % 1.0 for i in range(n_levels)]
    if scheme == "rainbow":
        return [(i / n_levels) % 1.0 for i in range(n_levels)]
    return [base] * n_levels


# ------------------------------------------------------------------------------
# Recipe randomization
# ------------------------------------------------------------------------------

def random_recipe(branch_levels: int, max_nodes: int, rng: random.Random,
                   name: str = "Hyperglyph") -> tuple[GlyphRecipe, dict]:
    """Build a fresh, fully-random GlyphRecipe. Returns (recipe, design_meta)
    where design_meta records the higher-level creative choices (family,
    palette scheme, ...) for the ratings-CSV manifest row."""
    depth = max(0, branch_levels - 1)  # levels 1..depth branch; level 0 is the trunk
    counts = pick_level_counts(depth, max_nodes, rng)

    family_name = rng.choice(list(GEO_FAMILIES.keys()))
    geo_pool = GEO_FAMILIES[family_name]
    palette_scheme = rng.choice(PALETTE_SCHEMES)
    hues = make_palette(palette_scheme, branch_levels, rng)
    translucent = rng.random() < 0.3

    levels: list[LevelSpec] = []

    # -- Trunk (level 0): always a single centered root. --
    r0, g0, b0 = _hsv_to_rgb255(hues[0], rng.uniform(0.55, 0.9), rng.uniform(0.75, 1.0))
    a0 = rng.randint(160, 220) if translucent else 255
    trunk_topo = rng.choice(ANGULAR_SAFE_TOPOS)
    root_scale = rng.uniform(0.8, 1.6)
    levels.append(LevelSpec(
        count=1, geometry=rng.choice(geo_pool), topo=trunk_topo,
        ratio=rng.uniform(0.1, 0.3), dist_mode=DIST_LINEAR, dist_step=0.0,
        scale_x=root_scale, scale_y=root_scale, scale_z=root_scale,
        rotate_x=rng.uniform(0, 360), rotate_y=rng.uniform(0, 360), rotate_z=rng.uniform(0, 360),
        color_start=(r0, g0, b0, a0), color_end=None,
    ))

    cumulative_scale = root_scale
    parent_topo = trunk_topo
    for i, count in enumerate(counts, start=1):
        is_leaf = (i == len(counts))
        # Branching level's own placement topology (irrelevant if leaf, but
        # harmless to set — keeps the recipe editable/coherent in Composer).
        this_topo = parent_topo if is_leaf else rng.choice(ANGULAR_SAFE_TOPOS)

        shrink = rng.uniform(0.4, 0.75)
        cumulative_scale *= shrink
        stretch = rng.random() < 0.3
        if stretch:
            axis = rng.choice([0, 1, 2])
            stretch_factors = [1.0, 1.0, 1.0]
            stretch_factors[axis] = rng.uniform(1.4, 2.6)
            sx, sy, sz = (cumulative_scale * f for f in stretch_factors)
        else:
            jitter = rng.uniform(0.9, 1.1)
            sx = sy = sz = cumulative_scale * jitter

        dist_mode = DIST_ANGULAR if rng.random() < 0.75 else DIST_LINEAR
        spread = rng.uniform(1.4, 3.2)

        hue = hues[i % len(hues)]
        sat = rng.uniform(0.55, 0.95)
        val = rng.uniform(0.7, 1.0)
        rs, gs, bs = _hsv_to_rgb255(hue, sat, val)
        a_start = rng.randint(140, 210) if translucent else 255
        gradient = rng.random() < 0.6
        if gradient:
            hue_end = (hue + rng.uniform(-0.12, 0.12)) % 1.0
            re_, ge_, be_ = _hsv_to_rgb255(hue_end, sat * rng.uniform(0.7, 1.0), val * rng.uniform(0.6, 1.0))
            a_end = rng.randint(120, 200) if translucent else 255
            color_end = (re_, ge_, be_, a_end)
        else:
            color_end = None

        levels.append(LevelSpec(
            count=count, geometry=rng.choice(geo_pool), topo=this_topo,
            ratio=rng.uniform(0.08, 0.35),
            dist_mode=dist_mode,
            dist_step=cumulative_scale * rng.uniform(1.5, 3.0),
            dist_axis=rng.choice([0, 1, 2]),
            dist_tilt=rng.uniform(-30.0, 30.0),
            dist_tz=cumulative_scale * spread,
            scale_x=sx, scale_y=sy, scale_z=sz,
            rotate_x=rng.uniform(-45, 45), rotate_y=rng.uniform(-45, 45), rotate_z=rng.uniform(-45, 45),
            color_start=(rs, gs, bs, a_start), color_end=color_end,
        ))
        parent_topo = this_topo

    recipe = GlyphRecipe(name=name, levels=levels)
    meta = {
        "generation_mode": "random",
        "parent_design_id": "",
        "geometry_family": family_name,
        "palette_scheme": palette_scheme,
        "translucent": translucent,
        "level_counts": counts,
    }
    return recipe, meta


def mutate_recipe(base: GlyphRecipe, rng: random.Random, max_nodes: int,
                   jitter: float = 0.2) -> GlyphRecipe:
    """Perturb a past (presumably good) recipe: numeric fields get gaussian-ish
    multiplicative jitter, a couple of discrete fields occasionally re-roll.
    Branch-level *count* (depth) is preserved as-is from `base` — the explore
    /exploit split in generate_batch always mutates a design that already
    matches the requested depth."""
    new_levels: list[LevelSpec] = []
    for lvl in base.levels:
        d = replace(lvl)

        def jit(v: float) -> float:
            return v * rng.uniform(1 - jitter, 1 + jitter)

        d.ratio = max(0.02, jit(d.ratio))
        d.scale_x, d.scale_y, d.scale_z = jit(d.scale_x), jit(d.scale_y), jit(d.scale_z)
        d.rotate_x = (d.rotate_x + rng.uniform(-20, 20)) % 360
        d.rotate_y = (d.rotate_y + rng.uniform(-20, 20)) % 360
        d.rotate_z = (d.rotate_z + rng.uniform(-20, 20)) % 360
        d.dist_step = jit(d.dist_step) if d.dist_step else d.dist_step
        d.dist_tilt = d.dist_tilt + rng.uniform(-10, 10)
        d.dist_tz = jit(d.dist_tz) if d.dist_tz else d.dist_tz
        d.count = max(1, int(round(jit(d.count)))) if d.count > 1 else 1

        if rng.random() < 0.15:
            for fam in GEO_FAMILIES.values():
                if d.geometry in fam:
                    d.geometry = rng.choice(fam)
                    break
        if rng.random() < 0.1 and d.topo in ANGULAR_SAFE_TOPOS:
            d.topo = rng.choice(ANGULAR_SAFE_TOPOS)

        def jit_color(c):
            if c is None:
                return None
            h, s, v = colorsys.rgb_to_hsv(*(x / 255.0 for x in c[:3]))
            h = (h + rng.uniform(-0.04, 0.04)) % 1.0
            r, g, b = _hsv_to_rgb255(h, s, v)
            return (r, g, b, c[3])

        d.color_start = jit_color(d.color_start) or d.color_start
        d.color_end = jit_color(d.color_end)
        new_levels.append(d)

    # Re-clamp the mutated tree back inside the node budget if jitter pushed
    # counts (levels[1:]) over it.
    counts = [lvl.count for lvl in new_levels[1:]]
    while _total_nodes(counts) > max_nodes and any(c > 1 for c in counts):
        idx = max(range(len(counts)), key=lambda i: (counts[i] > 1, i))
        counts[idx] -= 1
    for lvl, c in zip(new_levels[1:], counts):
        lvl.count = c

    return GlyphRecipe(name=base.name + " (variant)", levels=new_levels)


# ------------------------------------------------------------------------------
# Idle motion
# ------------------------------------------------------------------------------

def apply_idle_motion(nodes: list[Node], rng: random.Random) -> None:
    """Give non-root nodes a slow rotate_rate_* spin, alternating direction by
    branch depth (an "orrery": each ring of children counter-rotates against
    its parent ring), so a freshly-loaded hyperglyph reads as alive even
    before any Channels/audio data drives it. scale_rate/translate_rate are
    intentionally left alone: those fields integrate a constant per-cycle
    delta forever (see glyphviz_gl/viewport.py's _apply_rate_animation) with
    no wraparound, so they would keep growing/drifting rather than pulsing —
    only rotation is safe for unattended, unbounded idle looping."""
    for node in nodes:
        if node.branch_level == 0:
            continue
        direction = 1.0 if node.branch_level % 2 == 0 else -1.0
        speed = rng.uniform(0.04, 0.3) * direction
        axis = rng.choice(("x", "y", "z"))
        setattr(node, f"rotate_rate_{axis}", speed)


# ------------------------------------------------------------------------------
# Ratings store
# ------------------------------------------------------------------------------

RATINGS_FIELDS = [
    "design_id", "created_at", "node_csv", "tag_csv", "recipe_json",
    "branch_levels", "requested_max_nodes", "actual_node_count", "seed",
    "generation_mode", "parent_design_id", "geometry_family", "palette_scheme",
    "translucent", "rating", "categories", "notes",
]


class RatingsStore:
    """Thin CSV-backed log of every design ever generated, plus Jeff's
    hand-entered rating/categories/notes. Not a database — just a manifest
    meant to be opened in Excel/pandas and edited by hand between runs."""

    def __init__(self, path: Path):
        self.path = Path(path)
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=RATINGS_FIELDS).writeheader()

    def load(self) -> list[dict]:
        with open(self.path, "r", newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def append(self, row: dict) -> None:
        with open(self.path, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=RATINGS_FIELDS).writerow(row)

    def top_designs(self, min_rating: float = 7.0, limit: int = 10) -> list[dict]:
        rated = []
        for row in self.load():
            try:
                rating = float(row.get("rating", "") or "nan")
            except ValueError:
                continue
            if rating >= min_rating and row.get("recipe_json"):
                rated.append((rating, row))
        rated.sort(key=lambda t: t[0], reverse=True)
        return [row for _, row in rated[:limit]]

    def set_rating(self, design_id: str, rating=None, categories: str | None = None,
                    notes: str | None = None) -> None:
        """Rewrite the row for `design_id` with the given rating/categories/notes
        (whichever are not None), leaving everything else untouched. Lets Jeff
        score designs from the notebook instead of hand-editing the CSV."""
        all_rows = self.load()
        found = False
        for row in all_rows:
            if row["design_id"] == design_id:
                if rating is not None:
                    row["rating"] = str(rating)
                if categories is not None:
                    row["categories"] = categories
                if notes is not None:
                    row["notes"] = notes
                found = True
                break
        if not found:
            raise KeyError(f"No design_id {design_id!r} in {self.path}")
        with open(self.path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=RATINGS_FIELDS)
            writer.writeheader()
            writer.writerows(all_rows)


# ------------------------------------------------------------------------------
# Batch generation
# ------------------------------------------------------------------------------

def generate_batch(branch_levels: int, max_nodes: int, count: int,
                    output_dir: str | Path, name_prefix: str = "hyperglyph",
                    explore_ratio: float | None = None, seed: int | None = None,
                    idle_motion: bool = True,
                    ratings_path: str | Path | None = None) -> list[dict]:
    """Generate `count` unique hyperglyphs, each with up to `branch_levels`
    levels (including the trunk) and at most `max_nodes` total nodes.

    explore_ratio: fraction of the batch that is fresh random exploration
    rather than a mutated variant of a past top-rated design. None = auto
    (100% explore until ratings.csv has >=3 designs rated >=7, then 40%
    explore / 60% exploit).

    Returns the list of manifest dict rows written to ratings.csv (also
    useful directly in a notebook without re-reading the CSV).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ratings = RatingsStore(Path(ratings_path) if ratings_path else output_dir.parent / "ratings.csv")

    top = ratings.top_designs(min_rating=7.0, limit=10)
    if explore_ratio is None:
        explore_ratio = 1.0 if len(top) < 3 else 0.4

    master_rng = random.Random(seed)
    rows = []

    for i in range(count):
        design_seed = master_rng.randrange(2**31)
        rng = random.Random(design_seed)
        name = f"{name_prefix}_{i:03d}"

        parent_design_id = ""
        if top and rng.random() >= explore_ratio:
            source_row = rng.choice(top)
            try:
                base_recipe = load_recipe(source_row["recipe_json"])
                recipe = mutate_recipe(base_recipe, rng, max_nodes)
                recipe.name = name
                meta = {
                    "generation_mode": "mutated",
                    "parent_design_id": source_row["design_id"],
                    "geometry_family": source_row.get("geometry_family", ""),
                    "palette_scheme": source_row.get("palette_scheme", ""),
                    "translucent": source_row.get("translucent", ""),
                }
                parent_design_id = source_row["design_id"]
            except (FileNotFoundError, KeyError, ValueError):
                recipe, meta = random_recipe(branch_levels, max_nodes, rng, name=name)
        else:
            recipe, meta = random_recipe(branch_levels, max_nodes, rng, name=name)

        nodes = generate_nodes(recipe)
        if idle_motion:
            apply_idle_motion(nodes, rng)

        node_path, tag_path = stamp_node_and_tag_paths(output_dir / f"{name}_gv_node.csv")
        save_node_csv(nodes, str(node_path))
        save_tag_csv(nodes, str(tag_path))  # empty (no text/link set) but kept for pairing convention
        recipe_path = node_path.with_name(node_path.stem.replace("_gv_node", "") + "_recipe.json")
        save_recipe(recipe, str(recipe_path))

        design_id = node_path.stem
        row = {
            "design_id": design_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "node_csv": str(node_path),
            "tag_csv": str(tag_path),
            "recipe_json": str(recipe_path),
            "branch_levels": branch_levels,
            "requested_max_nodes": max_nodes,
            "actual_node_count": len(nodes),
            "seed": design_seed,
            "generation_mode": meta["generation_mode"],
            "parent_design_id": parent_design_id,
            "geometry_family": meta.get("geometry_family", ""),
            "palette_scheme": meta.get("palette_scheme", ""),
            "translucent": meta.get("translucent", ""),
            "rating": "",
            "categories": "",
            "notes": "",
        }
        ratings.append(row)
        rows.append(row)

    return rows
