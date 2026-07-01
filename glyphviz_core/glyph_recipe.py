"""
Pure-logic glyph recipe: a tree of LevelSpec objects that drives
generate_nodes() to produce a hierarchical Node list.  No UI or GL dependency.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field, asdict

from .geometry_data import GEO_SPHERE
from .node import Node, ROTATION_MODE_EULER_XYZ
from .topology import (
    TOPO_SPHERE, TOPO_NONE, TOPO_NAMES,
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
