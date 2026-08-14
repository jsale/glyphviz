"""
Pure-logic glyph recipe: a tree of LevelSpec objects that drives
generate_nodes() to produce a hierarchical Node list.  No UI or GL dependency.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field, asdict, replace

from .geometry_data import GEO_SPHERE
from .node import (
    DEFAULT_TOPO_SCALE, TOPO_SCALE_ANTZ, Node, ROTATION_MODE_EULER_XYZ,
)
from .topology import (
    LINEAR_PLACEMENT_AXES, TOPO_SPHERE, TOPO_NONE, TOPO_NAMES,
)

# Distribution modes -----------------------------------------------------------
DIST_LINEAR   = "linear"    # evenly spaced along a Cartesian axis
DIST_ANGULAR  = "angular"   # ring via parent topology's angular coordinate (tx=0..360)
DIST_CIRCULAR = "circular"  # evenly spaced in a circle in world XY (root only)
DIST_GRID     = "grid"      # rectangular grid in world XY (root only)
DIST_RANDOM   = "random"    # uniform random within a bounding cube (root only)

ROOT_DIST_MODES    = [DIST_LINEAR, DIST_CIRCULAR, DIST_GRID, DIST_RANDOM]
NONROOT_DIST_MODES = [DIST_ANGULAR, DIST_LINEAR]

DIST_LABELS = {
    DIST_LINEAR:   "Linear (along axis)",
    DIST_ANGULAR:  "Angular (ring around parent)",
    DIST_CIRCULAR: "Circular (world ring)",
    DIST_GRID:     "Grid (world XY)",
    DIST_RANDOM:   "Random",
}


@dataclass
class LevelSpec:
    count: int             = 5
    geometry: int          = GEO_SPHERE
    topo: int              = TOPO_SPHERE
    ratio: float           = 0.3

    # Topology Scale of THIS level's nodes — the size of the coordinate system
    # their children are placed in (Node.topo_scale). While topo_scale_auto is
    # set the stored number is ignored and suggested_topo_scale() supplies the
    # value instead; see effective_topo_scale below for why that is the default.
    topo_scale: float      = DEFAULT_TOPO_SCALE
    topo_scale_auto: bool  = True

    # Which distribution to use (see DIST_* constants)
    dist_mode: str         = DIST_ANGULAR

    # -- Linear params (all levels) --
    dist_step: float       = 2.0        # spacing between items
    dist_axis: int         = 0          # 0=X, 1=Y, 2=Z

    # -- Angular params (non-root) --
    dist_tilt: float       = 0.0        # translate_y (latitude/tilt/height per parent topo)
    dist_tz: float         = 0.0        # translate_z (altitude/radius offset)

    # -- Circular params (root only) --
    dist_radius: float     = 3.0

    # -- Grid params (root only) --
    dist_grid_cols: int    = 3
    dist_grid_sx: float    = 2.0
    dist_grid_sy: float    = 2.0

    # -- Random params (root only) --
    dist_bounds: float     = 5.0

    # Transform
    scale_x: float         = 1.0
    scale_y: float         = 1.0
    scale_z: float         = 1.0
    rotate_x: float        = 0.0
    rotate_y: float        = 0.0
    rotate_z: float        = 0.0

    # Color (RGBA 0-255 tuples)
    color_start: tuple     = (180, 100, 200, 255)
    color_end: tuple|None  = None       # None = solid colour, no gradient


def default_recipe() -> GlyphRecipe:
    level0 = LevelSpec(count=1, geometry=GEO_SPHERE, topo=TOPO_SPHERE,
                       dist_mode=DIST_LINEAR, dist_step=2.0,
                       color_start=(140, 180, 220, 255))
    level1 = LevelSpec(count=6, geometry=GEO_SPHERE, topo=TOPO_NONE,
                       dist_mode=DIST_ANGULAR, scale_x=0.5, scale_y=0.5, scale_z=0.5,
                       color_start=(220, 140, 80, 255), color_end=(80, 200, 180, 255))
    return GlyphRecipe(name="My Glyph", levels=[level0, level1])


@dataclass
class GlyphRecipe:
    name: str                   = "My Glyph"
    levels: list[LevelSpec]     = field(default_factory=lambda: [
        LevelSpec(dist_mode=DIST_LINEAR)
    ])


# ------------------------------------------------------------------------------
# Topology Scale auto-fit
# ------------------------------------------------------------------------------
#
# A recipe describes its child placement in ONE vocabulary — DIST_ANGULAR hands
# the next level translate_x = 0..360 — but the parent's topology decides
# whether translate_x means degrees or world units (topology.
# LINEAR_PLACEMENT_AXES). Under Sphere/Torus/Cylinder that 0..360 is a full
# revolution; under Cube/Pin/Plane/None it is 360 WORLD UNITS, which throws the
# children hundreds of parent-radii away — off screen, with no clue where they
# went. That mismatch is exactly what Node.topo_scale exists to reconcile, so
# rather than make every Composer user discover the field the hard way, a level
# whose scale the user has not touched picks the value that keeps its own
# children in frame.

def suggested_topo_scale(recipe: GlyphRecipe, level_idx: int) -> float:
    """The Topology Scale that keeps level_idx's children next to it, given how
    the NEXT level asks to be distributed.

    TOPO_SCALE_ANTZ (1/180) is the answer whenever a 0..360 angular sweep is
    about to be read as a distance: it is the convention under which a linear
    axis spans the parent's own extent, so the same degree-authored numbers
    land on the parent's surface instead of far past it. Everything else —
    including any level with no children to place — stays at 1.0, so a scene
    that was already correct is left alone.
    """
    if level_idx + 1 >= len(recipe.levels):
        return DEFAULT_TOPO_SCALE          # leaf: no children to place
    if recipe.levels[level_idx + 1].dist_mode != DIST_ANGULAR:
        return DEFAULT_TOPO_SCALE          # not authored in degrees
    topo = recipe.levels[level_idx].topo
    linear_x = LINEAR_PLACEMENT_AXES.get(topo, (True, True, True))[0]
    return TOPO_SCALE_ANTZ if linear_x else DEFAULT_TOPO_SCALE


def effective_topo_scale(recipe: GlyphRecipe, level_idx: int) -> float:
    """The Topology Scale generate_nodes() will actually stamp on level_idx —
    the user's number once they have taken the level off auto, the suggestion
    until then."""
    spec = recipe.levels[level_idx]
    if spec.topo_scale_auto:
        return suggested_topo_scale(recipe, level_idx)
    return spec.topo_scale


# ------------------------------------------------------------------------------
# Node generation
# ------------------------------------------------------------------------------

def generate_nodes(recipe: GlyphRecipe,
                   start_id: int = 1,
                   parent_id: int = 0,
                   base_branch_level: int = 0) -> list[Node]:
    """Return a flat list of Nodes representing the full glyph hierarchy."""
    nodes: list[Node] = []
    if recipe.levels:
        _gen_level(recipe, 0, parent_id, TOPO_NONE,
                   start_id, base_branch_level, nodes)
    return nodes


def _gen_level(recipe, level_idx, parent_id, parent_topo,
               start_id, branch_level, nodes):
    if level_idx >= len(recipe.levels):
        return
    spec = recipe.levels[level_idx]
    is_root = (level_idx == 0)
    positions = _distribute(spec, parent_topo, is_root)
    topo_scale = effective_topo_scale(recipe, level_idx)

    for i, (tx, ty, tz) in enumerate(positions):
        node_id = start_id + len(nodes)
        t = i / max(spec.count - 1, 1) if spec.count > 1 else 0.0
        r, g, b, a = _lerp_color(spec.color_start, spec.color_end, t)

        node = Node(
            id=node_id,
            type=5,
            parent_id=parent_id,
            branch_level=branch_level,
            translate_x=tx, translate_y=ty, translate_z=tz,
            rotate_x=spec.rotate_x, rotate_y=spec.rotate_y, rotate_z=spec.rotate_z,
            scale_x=spec.scale_x, scale_y=spec.scale_y, scale_z=spec.scale_z,
            color_r=r, color_g=g, color_b=b, color_a=a,
            geometry=spec.geometry,
            hide=0,
            topo=spec.topo,
            ratio=spec.ratio,
            topo_scale=topo_scale,
            rotation_mode=ROTATION_MODE_EULER_XYZ,
        )
        nodes.append(node)

        _gen_level(recipe, level_idx + 1, node_id, spec.topo,
                   start_id, branch_level + 1, nodes)


def _distribute(spec: LevelSpec, parent_topo: int, is_root: bool) -> list[tuple]:
    n = max(spec.count, 1)
    mode = spec.dist_mode

    if mode == DIST_ANGULAR:
        # Evenly spaced in the angular coordinate of the parent topology.
        # translate_x is the angular dimension (0..360) for Sphere/Torus/Cylinder.
        return [
            (i * 360.0 / n, spec.dist_tilt, spec.dist_tz)
            for i in range(n)
        ]

    if mode == DIST_LINEAR:
        step = spec.dist_step
        total = step * (n - 1)
        start = -total / 2.0
        ax = spec.dist_axis
        pts = []
        for i in range(n):
            v = start + i * step
            pts.append(
                (v, 0.0, 0.0) if ax == 0 else
                (0.0, v, 0.0) if ax == 1 else
                (0.0, 0.0, v)
            )
        return pts

    if mode == DIST_CIRCULAR:
        r = spec.dist_radius
        return [
            (math.cos(i * 2 * math.pi / n) * r,
             math.sin(i * 2 * math.pi / n) * r,
             0.0)
            for i in range(n)
        ]

    if mode == DIST_GRID:
        cols = max(spec.dist_grid_cols, 1)
        rows = math.ceil(n / cols)
        sx, sy = spec.dist_grid_sx, spec.dist_grid_sy
        cx = (cols - 1) * sx / 2.0
        cy = (rows - 1) * sy / 2.0
        pts = []
        for i in range(n):
            row, col = divmod(i, cols)
            pts.append((col * sx - cx, row * sy - cy, 0.0))
        return pts

    if mode == DIST_RANDOM:
        b = spec.dist_bounds
        return [(random.uniform(-b, b), random.uniform(-b, b), 0.0)
                for _ in range(n)]

    # Fallback
    return [(0.0, 0.0, 0.0)] * n


def _lerp_color(start, end, t):
    if end is None:
        return tuple(int(v) for v in start)
    return tuple(int(round(s + t * (e - s))) for s, e in zip(start, end))


# ------------------------------------------------------------------------------
# Recipe measurement
# ------------------------------------------------------------------------------

def recipe_node_count(recipe: GlyphRecipe) -> int:
    """How many nodes generate_nodes() will produce, without producing them.

    Each level contributes the running product of every count down to it, so
    the answer is exact for the full tree (generate_nodes expands every level
    under every parent)."""
    total = 0
    running = 1
    for spec in recipe.levels:
        running *= max(spec.count, 1)
        total += running
    return total


# Above this, a recipe is still perfectly valid — the JSON is a few hundred
# bytes whatever the tree expands to — but it stops being comfortable to EDIT
# in the Glyph Composer, whose Auto Preview regenerates and re-bakes the whole
# tree 350 ms after every keystroke (see glyph_composer_dialog._do_preview).
# That cost is what a caller offering to hand a recipe to the Composer should
# warn about; it is an editing-ergonomics threshold, not a correctness limit.
COMPOSER_EDIT_NODE_WARN = 2000


# ------------------------------------------------------------------------------
# Live-orientation capture
# ------------------------------------------------------------------------------

def _composer_safe_angle(deg: float) -> float:
    """Fold `deg` into the Composer's rotation spin-box range (-360..360).

    Rate animation integrates rotate_x/y/z without wraparound (see
    viewport._apply_rate_animation), so a glyph left spinning reaches
    thousands of degrees — the same orientation, but a number the spin box
    would silently CLAMP to 360 the moment the level is selected, quietly
    losing exactly the state we set out to capture. Values already in range
    are returned untouched rather than folded to 0..360, so a static recipe
    round-trips byte-identically instead of having every authored -20.0
    rewritten as 340.0."""
    return deg if -360.0 <= deg <= 360.0 else deg % 360.0


def snapshot_level_rotations(recipe: GlyphRecipe,
                             nodes: list[Node]) -> GlyphRecipe:
    """Return a copy of `recipe` whose per-level rotate_x/y/z are taken from
    the CURRENT orientation of `nodes` — the live, animated node objects a
    viewport has been integrating rate fields into — rather than from the
    values the recipe was authored with.

    `nodes` must be a generate_nodes() result for this recipe (the level a
    node belongs to is read off its branch_level, relative to the first
    node's, so any base_branch_level offset works).

    **A recipe stores one rotation per LEVEL, and idle motion gives every
    NODE its own axis and speed** (hyperglyph_generator.apply_idle_motion), so
    siblings drift apart and no single value can describe them all. The
    capture is therefore exact for a level holding one node — always true of
    level 0, the trunk — and takes the first node encountered at each deeper
    level as its representative. First-node is deliberate over an average of
    the siblings: it is an orientation that genuinely occurred on screen, and
    it stays stable as the spread grows, where a circular mean of nodes
    scattered right around the circle is both meaningless and liable to flip.

    Only rotation is captured, because only rotation drifts: apply_idle_motion
    sets rotate_rate_* alone, and translate/scale have no LevelSpec field that
    could hold a per-node result anyway (position comes from the dist_* params).
    """
    levels = [replace(spec) for spec in recipe.levels]
    if levels and nodes:
        base = nodes[0].branch_level
        seen: set[int] = set()
        for n in nodes:
            idx = n.branch_level - base
            if 0 <= idx < len(levels) and idx not in seen:
                seen.add(idx)
                levels[idx].rotate_x = _composer_safe_angle(n.rotate_x)
                levels[idx].rotate_y = _composer_safe_angle(n.rotate_y)
                levels[idx].rotate_z = _composer_safe_angle(n.rotate_z)
    return GlyphRecipe(name=recipe.name, levels=levels)


# ------------------------------------------------------------------------------
# JSON serialization
# ------------------------------------------------------------------------------

def recipe_to_dict(r: GlyphRecipe) -> dict:
    levels = []
    for spec in r.levels:
        d = asdict(spec)
        d["color_start"] = list(d["color_start"])
        if d["color_end"] is not None:
            d["color_end"] = list(d["color_end"])
        levels.append(d)
    return {"name": r.name, "levels": levels}


def recipe_from_dict(d: dict) -> GlyphRecipe:
    levels = []
    for sd in d.get("levels", []):
        cs = tuple(sd.get("color_start", [180, 100, 200, 255]))
        ce_raw = sd.get("color_end")
        ce = tuple(ce_raw) if ce_raw is not None else None
        spec = LevelSpec(
            count            = sd.get("count", 5),
            geometry         = sd.get("geometry", GEO_SPHERE),
            topo             = sd.get("topo", TOPO_SPHERE),
            ratio            = sd.get("ratio", 0.3),
            # Templates written before Topology Scale existed carry neither
            # key. They load onto auto, which is what fixes the ones whose
            # children were flying off; the stored 1.0 is what auto falls back
            # to anyway, so nothing else moves.
            topo_scale       = sd.get("topo_scale", DEFAULT_TOPO_SCALE),
            topo_scale_auto  = sd.get("topo_scale_auto", True),
            dist_mode        = sd.get("dist_mode", DIST_ANGULAR),
            dist_step        = sd.get("dist_step", 2.0),
            dist_axis        = sd.get("dist_axis", 0),
            dist_tilt        = sd.get("dist_tilt", 0.0),
            dist_tz          = sd.get("dist_tz", 0.0),
            dist_radius      = sd.get("dist_radius", 3.0),
            dist_grid_cols   = sd.get("dist_grid_cols", 3),
            dist_grid_sx     = sd.get("dist_grid_sx", 2.0),
            dist_grid_sy     = sd.get("dist_grid_sy", 2.0),
            dist_bounds      = sd.get("dist_bounds", 5.0),
            scale_x          = sd.get("scale_x", 1.0),
            scale_y          = sd.get("scale_y", 1.0),
            scale_z          = sd.get("scale_z", 1.0),
            rotate_x         = sd.get("rotate_x", 0.0),
            rotate_y         = sd.get("rotate_y", 0.0),
            rotate_z         = sd.get("rotate_z", 0.0),
            color_start      = cs,
            color_end        = ce,
        )
        levels.append(spec)
    return GlyphRecipe(name=d.get("name", "My Glyph"), levels=levels)


def save_recipe(r: GlyphRecipe, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(recipe_to_dict(r), f, indent=2)


def load_recipe(path: str) -> GlyphRecipe:
    with open(path, "r", encoding="utf-8") as f:
        return recipe_from_dict(json.load(f))
