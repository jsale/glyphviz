"""Qt-free math for Draw Mode (D key): turning a viewport click into a new
child of a World Grid.

Draw Mode stamps objects where the cursor meets a grid's drawing plane, one
per click — or one every `spacing_px` of cursor travel during a drag, the
"stamp spacing" rule from Jeff's 2D fractal-forest drawing tool. The Qt side
(glyphviz_gl/viewport.py) only tracks the gesture and forwards screen
coordinates; everything geometric lives here so it's testable headlessly.

The inversion this module performs is exact, not approximate: a flat World
Grid places a child at

    world = grid_pos + grid_world_basis @ (lon - c_lon, lat - c_lat, z)

(compute_world_transforms' flat_child branch, where grid_world_basis is the
grid's rotation x cumulative raw scale and (c_lon, c_lat) the extents-window
center). grid_hit() transforms the click ray into that local frame and
intersects it with the z = draw_z plane, so a stamped child at the returned
(lon, lat) lands under the cursor by construction — whatever the grid's
translate/rotate/scale or nesting.
"""

import random

import numpy as np

_EPS = 1e-9


def screen_ray(mv: np.ndarray, proj: np.ndarray, x: float, y: float,
               width: float, height: float
               ) -> tuple[np.ndarray, np.ndarray] | None:
    """World-space ray under widget pixel (x, y).

    mv/proj are the row-major 4x4 camera matrices the viewport captures each
    paint (_mv_matrix/_proj_matrix). Returns (origin, unit direction), or
    None when the composite matrix is singular (never for a real camera).
    """
    mvp = np.asarray(proj, dtype=np.float64) @ np.asarray(mv, dtype=np.float64)
    try:
        inv = np.linalg.inv(mvp)
    except np.linalg.LinAlgError:
        return None
    ndc_x = 2.0 * x / width - 1.0
    ndc_y = 1.0 - 2.0 * y / height     # widget y grows down, NDC y grows up
    near = inv @ np.array([ndc_x, ndc_y, -1.0, 1.0])
    far = inv @ np.array([ndc_x, ndc_y, 1.0, 1.0])
    if abs(near[3]) < _EPS or abs(far[3]) < _EPS:
        return None
    near = near[:3] / near[3]
    far = far[:3] / far[3]
    direction = far - near
    norm = np.linalg.norm(direction)
    if norm < _EPS:
        return None
    return near, direction / norm


def grid_hit(ray_origin, ray_direction, grid_pos, grid_basis, grid_center,
             draw_z: float = 0.0) -> tuple[float, float] | None:
    """(lon, lat) child coordinates where the ray meets the grid's drawing
    plane (grid-local z = draw_z), or None.

    grid_pos / grid_basis are the grid's world_pos and full world_basis from
    SceneTransforms (Scene.world_pos / Scene.basis_matrices), grid_center is
    Node.grid_center(). None when the basis is singular (a zero-scale axis),
    the ray runs parallel to the plane, or the plane lies behind the camera.
    """
    basis = np.asarray(grid_basis, dtype=np.float64)
    try:
        inv = np.linalg.inv(basis)
    except np.linalg.LinAlgError:
        return None
    local_o = inv @ (np.asarray(ray_origin, dtype=np.float64)
                     - np.asarray(grid_pos, dtype=np.float64))
    local_d = inv @ np.asarray(ray_direction, dtype=np.float64)
    if abs(local_d[2]) < _EPS:
        return None
    t = (draw_z - local_o[2]) / local_d[2]
    if t <= 0.0:
        return None
    hit = local_o + local_d * t
    c_lon, c_lat = grid_center
    return float(hit[0] + c_lon), float(hit[1] + c_lat)


def place_stamp(nodes, base_branch_level: int, lon: float, lat: float,
                z: float, heading_jitter_deg: float = 0.0,
                scale_jitter_pct: float = 0.0, rng=None
                ) -> tuple[float, float]:
    """Land a freshly generated stamp at (lon, lat, z) on its grid, with
    per-stamp jitter. Mutates `nodes` in place; returns the (heading_deg,
    scale_factor) actually drawn, for status display and tests.

    `nodes` is either the single object of a plain stamp or a whole
    hyperglyph from glyph_recipe.generate_nodes(..., parent_id=grid.id,
    base_branch_level=grid.branch_level + 1). Only the stamp's ROOTS (rows
    at base_branch_level — usually one, but a recipe whose level 0 is a
    cluster has several) are touched: their translate is offset to the
    stamp point, and every deeper node rides along through the hierarchy.

    Jitter is drawn ONCE per stamp, not per node, so a multi-root cluster
    stays coherent: heading_jitter_deg adds a uniform random spin in
    [-j, +j] to each root's rotate_z (which rotates its whole subtree —
    child placement composes the parent's rotation), and scale_jitter_pct
    multiplies all three root scale axes by one uniform random factor in
    [1 - p/100, 1 + p/100] (proportions preserved; subtree spacing scales
    with it). Both default to 0 = off. Pass a random.Random as `rng` for
    reproducibility.
    """
    if rng is None:
        rng = random
    heading = rng.uniform(-heading_jitter_deg, heading_jitter_deg) \
        if heading_jitter_deg else 0.0
    factor = 1.0 + rng.uniform(-scale_jitter_pct, scale_jitter_pct) / 100.0 \
        if scale_jitter_pct else 1.0
    for n in nodes:
        if n.branch_level == base_branch_level:
            n.translate_x += lon
            n.translate_y += lat
            n.translate_z += z
            n.rotate_z += heading
            n.scale_x *= factor
            n.scale_y *= factor
            n.scale_z *= factor
    return heading, factor


def should_stamp(last_xy: tuple[float, float] | None, x: float, y: float,
                 spacing_px: float) -> bool:
    """Drag-stroke gate: stamp when the cursor is at least spacing_px from
    the previous stamp (always, for the stroke's first point). spacing 0
    means every mouse-move event stamps — maximum density, matching the
    fractal-forest tool's convention."""
    if last_xy is None:
        return True
    dx = x - last_xy[0]
    dy = y - last_xy[1]
    return (dx * dx + dy * dy) >= spacing_px * spacing_px
