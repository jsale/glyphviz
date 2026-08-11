"""
The optional minimum rendered glyph size (Scene.scale_floor).

GlyphViz's earliest commits clamped every glyph's rendered scale to 0.2 per
axis so a near-zero-scale node stayed big enough to click. That silently
overrode authored data, so the clamp is now OFF by default and opt-in via
View > Enforce Minimum Glyph Size.

What's pinned here: the default really is off (authored scale renders exactly,
however small), the option really does clamp when switched on, all three code
paths that build draw scale agree with each other under both settings, and
World Grids stay exempt either way — their footprint has to match where their
children land, which the clamp would break.

Scenes go through a real CSV and the real loader, so a load-side default can't
quietly make the test pass on numbers the app would never see.
"""
import math
import os

import numpy as np
import pandas as pd
import pytest

from glyphviz_core.csv_reader import _COL_ORDER, load_node_csv
from glyphviz_core.node import NODE_TYPE_GRID
from glyphviz_core.scene import (
    DEFAULT_SCALE_FLOOR, NO_SCALE_FLOOR, Scene, node_world_matrix,
)
from glyphviz_core import topology as topo

TINY = 0.05          # well under the floor at base_scale 1.0
BIG = 4.0            # well over it


def _row(**overrides):
    row = {c: 0 for c in _COL_ORDER}
    row.update(scale_x=1, scale_y=1, scale_z=1, ratio=0.1, type=5)
    row.update(overrides)
    return row


def _scene(tmp_path, rows, base_scale=1.0, scale_floor=NO_SCALE_FLOOR):
    path = tmp_path / "gv_node.csv"
    pd.DataFrame(rows)[_COL_ORDER].to_csv(path, index=False)
    return Scene(load_node_csv(str(path)), base_scale=base_scale,
                 scale_floor=scale_floor)


def _rendered_scale(scene, node_id):
    """Per-axis rendered size of a node = column norms of its draw matrix."""
    M = node_world_matrix(scene.node_by_id(node_id), scene)
    return tuple(math.sqrt(sum(M[i][j] ** 2 for i in range(3)))
                 for j in range(3))


# --- the default: authored scale, unclamped ---

def test_scene_default_has_no_floor():
    assert Scene([]).scale_floor == 0.0


def test_tiny_glyph_renders_at_authored_scale(tmp_path):
    """The regression this whole change is about: 0.05 must render as 0.05."""
    scene = _scene(tmp_path, [_row(id=1, scale_x=TINY, scale_y=TINY,
                                   scale_z=TINY)])
    assert _rendered_scale(scene, 1) == pytest.approx((TINY, TINY, TINY))


def test_per_axis_proportions_survive(tmp_path):
    """A thin sliver keeps its aspect ratio instead of being squared up by a
    floor that only lifts the small axes."""
    scene = _scene(tmp_path, [_row(id=1, scale_x=BIG, scale_y=TINY,
                                   scale_z=TINY)])
    assert _rendered_scale(scene, 1) == pytest.approx((BIG, TINY, TINY))


# --- the option, switched on ---

def test_floor_option_clamps_small_axes(tmp_path):
    scene = _scene(tmp_path, [_row(id=1, scale_x=BIG, scale_y=TINY,
                                   scale_z=0.0)],
                   scale_floor=DEFAULT_SCALE_FLOOR)
    assert _rendered_scale(scene, 1) == pytest.approx(
        (BIG, DEFAULT_SCALE_FLOOR, DEFAULT_SCALE_FLOOR))


def test_floor_applies_after_base_scale(tmp_path):
    """The clamp is on rendered size (scale x base_scale), not raw scale — so
    raising Global Scale lifts a glyph off the floor."""
    rows = [_row(id=1, scale_x=TINY, scale_y=TINY, scale_z=TINY)]
    floored = _scene(tmp_path, rows, base_scale=1.0,
                     scale_floor=DEFAULT_SCALE_FLOOR)
    assert _rendered_scale(floored, 1) == pytest.approx(
        (DEFAULT_SCALE_FLOOR,) * 3)
    lifted = _scene(tmp_path, rows, base_scale=10.0,
                    scale_floor=DEFAULT_SCALE_FLOOR)
    assert _rendered_scale(lifted, 1) == pytest.approx((TINY * 10,) * 3)


def test_toggling_on_a_live_scene_takes_effect(tmp_path):
    """Setting scale_floor + invalidate() is all the viewport does — the
    batched draw cache must pick the new value up, not serve stale matrices."""
    scene = _scene(tmp_path, [_row(id=1, scale_x=TINY, scale_y=TINY,
                                   scale_z=TINY)])
    node = scene.node_by_id(1)
    assert scene.node_draw_data(node)[2] == pytest.approx(TINY)
    scene.scale_floor = DEFAULT_SCALE_FLOOR
    scene.invalidate()
    assert scene.node_draw_data(node)[2] == pytest.approx(DEFAULT_SCALE_FLOOR)


# --- the three draw-scale code paths must agree ---

@pytest.mark.parametrize('floor', [NO_SCALE_FLOOR, DEFAULT_SCALE_FLOOR])
def test_batch_bake_matches_node_world_matrix(tmp_path, floor):
    """_bake_draw_data (whole scene, vectorized) vs node_world_matrix (one
    node, scalar) — the render/pick contract requires identical numbers."""
    rows = [
        _row(id=1, scale_x=TINY, scale_y=BIG, scale_z=TINY),
        _row(id=2, parent_id=1, branch_level=1, topo=topo.TOPO_SPHERE,
             translate_x=30, translate_y=45, scale_x=0.01, scale_y=0.01,
             scale_z=0.01),
        _row(id=3, parent_id=1, branch_level=1, topo=topo.TOPO_ROD,
             scale_x=TINY, scale_y=TINY, scale_z=TINY),
    ]
    scene = _scene(tmp_path, rows, scale_floor=floor)
    for node in scene.nodes:
        batched = scene.node_draw_data(node)[0]
        assert np.allclose(batched, node_world_matrix(node, scene))


@pytest.mark.parametrize('floor', [NO_SCALE_FLOOR, DEFAULT_SCALE_FLOOR])
def test_refresh_rows_matches_full_bake(tmp_path, floor):
    """The Channels-playback row-subset path (_bake_draw_rows) must reach the
    same matrices as a full recompute after an animated scale change."""
    rows = [_row(id=1, scale_x=BIG, scale_y=BIG, scale_z=BIG),
            _row(id=2, parent_id=1, branch_level=1, translate_z=10)]
    scene = _scene(tmp_path, rows, scale_floor=floor)
    scene.node_draw_data(scene.node_by_id(1))     # force the first bake
    for n in scene.nodes:
        n.scale_x = n.scale_y = n.scale_z = TINY
    assert scene.refresh_rows(scene.rows_for_ids([1, 2])) is True
    partial = [scene.node_draw_data(n)[0].copy() for n in scene.nodes]

    scene.invalidate()
    full = [scene.node_draw_data(n)[0] for n in scene.nodes]
    for p, f in zip(partial, full):
        assert np.allclose(p, f)


# --- World Grids are exempt either way ---

@pytest.mark.parametrize('floor', [NO_SCALE_FLOOR, DEFAULT_SCALE_FLOOR])
def test_grid_footprint_never_floored(tmp_path, floor):
    """A grid's rendered rectangle is extents x raw scale so it stays under
    the children it frames; clamping any axis would slide it off them."""
    tiny_z = 0.001
    scene = _scene(tmp_path, [_row(id=1, type=NODE_TYPE_GRID,
                                   topo=topo.TOPO_PLANE, geometry=20,
                                   scale_x=tiny_z, scale_y=tiny_z,
                                   scale_z=tiny_z)],
                   base_scale=3.0, scale_floor=floor)
    half_lon, half_lat = scene.node_by_id(1).grid_half_extents()
    assert _rendered_scale(scene, 1) == pytest.approx(
        (tiny_z * half_lon, tiny_z * half_lat, tiny_z))


# --- viewport wiring ---

def test_viewport_toggle_drives_the_scene(tmp_path):
    """Viewport.enforce_scale_floor is what the checkbox and the View menu
    action both set; it must reach the Scene and survive a scene reload."""
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    pytest.importorskip('PySide6.QtWidgets')
    from PySide6.QtWidgets import QApplication
    from glyphviz_gl.viewport import Viewport

    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication([])
        except Exception as exc:                        # pragma: no cover
            pytest.skip(f'Qt unavailable: {exc}')

    vp = Viewport()
    nodes = [n for n in _scene(
        tmp_path, [_row(id=1, scale_x=TINY, scale_y=TINY, scale_z=TINY)]).nodes]
    vp.set_nodes(nodes)
    assert vp.enforce_scale_floor is False
    assert vp._scene.scale_floor == 0.0
    assert max(vp._radius_of(nodes[0])) == pytest.approx(TINY)

    vp.enforce_scale_floor = True
    assert vp._scene.scale_floor == DEFAULT_SCALE_FLOOR
    assert max(vp._radius_of(nodes[0])) == pytest.approx(DEFAULT_SCALE_FLOOR)

    vp.set_nodes(nodes)          # a reload builds a fresh Scene
    assert vp._scene.scale_floor == DEFAULT_SCALE_FLOOR

    vp.enforce_scale_floor = False
    assert vp._scene.scale_floor == 0.0
