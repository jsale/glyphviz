"""
World Grid (type=6) unit tests.

The contract (see CLAUDE.md and topology.py's "World Grid semantics" block):
a World Grid is a real, movable/rotatable/scalable node whose children attach
explicitly via parent_id = grid.id and place by lon (translate_x) / lat
(translate_y) / elevation (translate_z) within the grid's extents window
(Node.grid_extents, default whole earth). Scaling a grid re-spaces children's
POSITIONS per axis but never their rendered size or their own subtrees'
internal spacing — the ANTz-documented Grid rule, and the fix for the V1
attempt's mouse hypersensitivity. The grid's own draw matrix spans exactly
its extents window times its raw scale (no base_scale, no 0.2 floor), so the
rendered rectangle stays 1:1 under its children.
"""
import math

import numpy as np
import pandas as pd
import pytest

from glyphviz_core.csv_reader import _COL_ORDER, load_node_csv, save_node_csv
from glyphviz_core.node import (
    GRID_DEFAULT_EXTENTS, GRID_GLOBE_RADIUS, NODE_TYPE_GRID, Node,
)
from glyphviz_core.scene import Scene, node_world_matrix
from glyphviz_core import topology as topo


def _row(**overrides):
    row = {c: 0 for c in _COL_ORDER}
    row.update(
        scale_x=1, scale_y=1, scale_z=1,
        ratio=0.1, type=5,
    )
    row.update(overrides)
    return row


def _grid_row(**overrides):
    row = _row(type=NODE_TYPE_GRID, topo=topo.TOPO_PLANE, geometry=20)
    row.update(overrides)
    return row


def _write_csv(tmp_path, rows, name="gv_node.csv"):
    path = tmp_path / name
    pd.DataFrame(rows)[_COL_ORDER].to_csv(path, index=False)
    return path


def _scene(tmp_path, rows, base_scale=1.0):
    nodes = load_node_csv(str(_write_csv(tmp_path, rows)))
    return Scene(nodes, base_scale=base_scale)


def _rendered_scale(scene, node_id):
    """Per-axis rendered size of a node = column norms of its draw matrix."""
    node = scene.node_by_id(node_id)
    M = node_world_matrix(node, scene)
    return tuple(
        math.sqrt(sum(M[i][j] ** 2 for i in range(3))) for j in range(3)
    )


# ---------------------------------------------------------------------------
# Default whole-earth window: exact 1:1 with world coordinates.
# ---------------------------------------------------------------------------

def test_default_grid_children_map_one_to_one(tmp_path):
    """Grid at origin, scale 1: a child at translate (180, 90, 0) lands at
    world (180, 90, 0), exactly aligned with a non-child node at the same
    coordinates."""
    scene = _scene(tmp_path, [
        _grid_row(id=1),
        _row(id=2, parent_id=1, branch_level=1, translate_x=180.0, translate_y=90.0),
        _row(id=3, parent_id=0, translate_x=180.0, translate_y=90.0),
    ])
    assert scene.world_pos(2) == pytest.approx((180.0, 90.0, 0.0))
    assert scene.world_pos(2) == pytest.approx(scene.world_pos(3))


def test_grid_moves_children_ride_along(tmp_path):
    """Jeff's spec addendum: grids move in x/y/z like any node, carrying
    children rigidly."""
    scene = _scene(tmp_path, [
        _grid_row(id=1, translate_x=1000.0, translate_y=-50.0, translate_z=7.0),
        _row(id=2, parent_id=1, branch_level=1,
             translate_x=-117.2, translate_y=32.7, translate_z=3.0),
    ])
    assert scene.world_pos(2) == pytest.approx((1000.0 - 117.2, -50.0 + 32.7, 10.0))


def test_grid_scale_respaces_children_per_axis(tmp_path):
    scene = _scene(tmp_path, [
        _grid_row(id=1, scale_x=2.0, scale_y=3.0, scale_z=10.0),
        _row(id=2, parent_id=1, branch_level=1,
             translate_x=10.0, translate_y=20.0, translate_z=1.5),
    ])
    assert scene.world_pos(2) == pytest.approx((20.0, 60.0, 15.0))


# ---------------------------------------------------------------------------
# The type-6 rule: grid scale never touches child rendered size or the
# child's own subtree spacing.
# ---------------------------------------------------------------------------

def test_grid_scale_does_not_resize_children(tmp_path):
    scene = _scene(tmp_path, [
        _grid_row(id=1, scale_x=50.0, scale_y=25.0, scale_z=10.0),
        _row(id=2, parent_id=1, branch_level=1, translate_x=10.0),
    ], base_scale=3.0)
    # base_scale (3.0) * own scale (1,1,1) — no trace of the grid's scale.
    assert _rendered_scale(scene, 2) == pytest.approx((3.0, 3.0, 3.0))


def test_grid_scale_does_not_stretch_grandchild_spacing(tmp_path):
    """A glyph subtree sitting on a grid keeps its internal layout identical
    whatever the grid's scale — only where the subtree SITS changes."""
    def rows(grid_scale):
        return [
            _grid_row(id=1, scale_x=grid_scale, scale_y=grid_scale),
            _row(id=2, parent_id=1, branch_level=1, translate_x=10.0, topo=topo.TOPO_NONE),
            _row(id=3, parent_id=2, branch_level=2, translate_x=4.0, translate_y=5.0),
        ]
    small = _scene(tmp_path, rows(1.0))
    big = _scene(tmp_path, rows(40.0), base_scale=1.0)
    off_small = np.array(small.world_pos(3)) - np.array(small.world_pos(2))
    off_big = np.array(big.world_pos(3)) - np.array(big.world_pos(2))
    assert off_big == pytest.approx(off_small)


def test_plane_topo_parent_that_is_not_a_grid_keeps_legacy_scale_inheritance(tmp_path):
    """The no-size-inherit rule keys on TYPE=6, not on topo=Plane: an
    ordinary glyph with Plane topology still stretches its children's
    rendered shape with its scale, exactly as before this feature."""
    scene = _scene(tmp_path, [
        _row(id=1, parent_id=0, topo=topo.TOPO_PLANE, scale_x=5.0),
        _row(id=2, parent_id=1, branch_level=1, translate_x=1.0),
    ])
    assert _rendered_scale(scene, 2) == pytest.approx((5.0, 1.0, 1.0))


# ---------------------------------------------------------------------------
# Region extents: the window recenters child placement and the grid's own
# footprint; grid rotation carries children.
# ---------------------------------------------------------------------------

def test_region_extents_recenter_children_on_grid(tmp_path):
    """Contiguous-US-style window: a child at the window's midpoint sits at
    the grid's own position; window edges sit at the footprint edges."""
    rows = [
        _grid_row(id=1, trigger_lo_x=-125.0, trigger_hi_x=-66.0,
                  trigger_lo_y=24.0, trigger_hi_y=49.0),
        _row(id=2, parent_id=1, branch_level=1,
             translate_x=-95.5, translate_y=36.5),   # window midpoint
        _row(id=3, parent_id=1, branch_level=1,
             translate_x=-66.0, translate_y=49.0),   # window max corner
    ]
    scene = _scene(tmp_path, rows)
    assert scene.world_pos(2) == pytest.approx((0.0, 0.0, 0.0))
    assert scene.world_pos(3) == pytest.approx((29.5, 12.5, 0.0))
    # Footprint half-spans match the window: the max-corner child sits exactly
    # on the rendered rectangle's corner.
    grid = scene.node_by_id(1)
    assert grid.grid_half_extents() == pytest.approx((29.5, 12.5))
    assert _rendered_scale(scene, 1) == pytest.approx((29.5, 12.5, 1.0))


def test_degenerate_extents_fall_back_to_whole_earth(tmp_path):
    """Legacy files hold all-zero trigger columns — those must read as the
    default whole-earth window, per axis."""
    scene = _scene(tmp_path, [_grid_row(id=1)])
    assert scene.node_by_id(1).grid_extents() == pytest.approx(GRID_DEFAULT_EXTENTS)


def test_grid_rotation_carries_children(tmp_path):
    """Rotating the grid about Z swings a child on its +X axis around with
    it. The CSV has no rotation_mode column, so the grid loads as ANTz
    Heading/Tilt/Roll, where rotate_z=90 (Roll) is Rz(-90): +X lands on -Y."""
    scene = _scene(tmp_path, [
        _grid_row(id=1, rotate_z=90.0),
        _row(id=2, parent_id=1, branch_level=1, translate_x=10.0),
    ])
    assert scene.world_pos(2) == pytest.approx((0.0, -10.0, 0.0), abs=1e-9)


# ---------------------------------------------------------------------------
# The grid's own draw matrix: extents x raw scale, no base_scale, no floor.
# ---------------------------------------------------------------------------

def test_grid_draw_matrix_spans_extents_at_raw_scale(tmp_path):
    scene = _scene(tmp_path, [_grid_row(id=1, scale_x=2.0, scale_y=1.0)],
                   base_scale=3.0)
    # Half-spans 180/90 times raw scale — base_scale (3.0) must NOT leak in,
    # or the rendered rectangle would detach from the children it frames.
    assert _rendered_scale(scene, 1) == pytest.approx((360.0, 90.0, 1.0))


def test_grid_draw_matrix_skips_render_floor(tmp_path):
    scene = _scene(tmp_path, [_grid_row(id=1, scale_x=0.05, scale_y=0.05,
                                        scale_z=0.05)])
    # 0.05 * 180 / 0.05 * 90 — and scale_z stays raw 0.05, under the 0.2
    # floor ordinary glyphs get.
    assert _rendered_scale(scene, 1) == pytest.approx((9.0, 4.5, 0.05))


# ---------------------------------------------------------------------------
# Globe form: a grid with Sphere/Sphere Wire geometry places children by KML
# lon/lat/elevation on a sphere of radius GRID_GLOBE_RADIUS (180/pi — the
# flat 1:1 map rolled up so the equator is exactly 360 world units).
# ---------------------------------------------------------------------------

def _globe_row(**overrides):
    row = _grid_row(geometry=2)   # GEO_SPHERE_WIRE
    row.update(overrides)
    return row


def test_globe_children_place_by_kml_lon_lat(tmp_path):
    R = GRID_GLOBE_RADIUS
    scene = _scene(tmp_path, [
        _globe_row(id=1),
        _row(id=2, parent_id=1, branch_level=1, translate_x=0.0, translate_y=0.0),
        _row(id=3, parent_id=1, branch_level=1, translate_x=90.0, translate_y=0.0),
        _row(id=4, parent_id=1, branch_level=1, translate_x=0.0, translate_y=90.0),
        _row(id=5, parent_id=1, branch_level=1, translate_x=180.0, translate_y=0.0),
    ])
    assert scene.world_pos(2) == pytest.approx((R, 0.0, 0.0))        # lon 0 -> +X
    assert scene.world_pos(3) == pytest.approx((0.0, R, 0.0), abs=1e-9)   # lon 90 -> +Y
    assert scene.world_pos(4) == pytest.approx((0.0, 0.0, R), abs=1e-9)   # north pole -> +Z
    assert scene.world_pos(5) == pytest.approx((-R, 0.0, 0.0), abs=1e-9)  # antimeridian -> -X


def test_globe_elevation_is_radial(tmp_path):
    R = GRID_GLOBE_RADIUS
    scene = _scene(tmp_path, [
        _globe_row(id=1),
        _row(id=2, parent_id=1, branch_level=1,
             translate_x=0.0, translate_y=0.0, translate_z=5.0),
    ])
    assert scene.world_pos(2) == pytest.approx((R + 5.0, 0.0, 0.0))


def test_globe_scale_respaces_but_never_resizes(tmp_path):
    R = GRID_GLOBE_RADIUS
    scene = _scene(tmp_path, [
        _globe_row(id=1, scale_x=2.0, scale_y=2.0, scale_z=2.0),
        _row(id=2, parent_id=1, branch_level=1, translate_x=0.0, translate_y=0.0),
    ], base_scale=3.0)
    assert scene.world_pos(2) == pytest.approx((2.0 * R, 0.0, 0.0))
    # Child rendered size: base_scale x own scale only, no globe 2x.
    assert _rendered_scale(scene, 2) == pytest.approx((3.0, 3.0, 3.0))


def test_globe_children_orient_outward(tmp_path):
    """A globe child's local +Z (the KML surface normal) points radially
    outward at its lon/lat, matching TOPO_SPHERE children."""
    scene = _scene(tmp_path, [
        _globe_row(id=1),
        _row(id=2, parent_id=1, branch_level=1, translate_x=45.0, translate_y=45.0),
    ])
    M = node_world_matrix(scene.node_by_id(2), scene)
    z_axis = np.array([M[0][2], M[1][2], M[2][2]])
    z_axis /= np.linalg.norm(z_axis)
    lon, lat = math.radians(45.0), math.radians(45.0)
    outward = np.array([math.cos(lat) * math.cos(lon),
                        math.cos(lat) * math.sin(lon), math.sin(lat)])
    assert z_axis == pytest.approx(outward)


def test_globe_draw_matrix_is_radius_times_raw_scale(tmp_path):
    R = GRID_GLOBE_RADIUS
    scene = _scene(tmp_path, [_globe_row(id=1, scale_x=2.0)], base_scale=3.0)
    assert _rendered_scale(scene, 1) == pytest.approx((2.0 * R, R, R))


def test_toggling_geometry_switches_flat_and_globe(tmp_path):
    """The flat<->globe toggle is just a geometry change + invalidate —
    exactly what the Geometry dropdown / Shape combo do."""
    R = GRID_GLOBE_RADIUS
    scene = _scene(tmp_path, [
        _grid_row(id=1),   # flat wire
        _row(id=2, parent_id=1, branch_level=1, translate_x=90.0, translate_y=0.0),
    ])
    assert scene.world_pos(2) == pytest.approx((90.0, 0.0, 0.0))
    grid = scene.node_by_id(1)
    grid.geometry = 2   # GEO_SPHERE_WIRE -> globe
    scene.invalidate()
    assert scene.world_pos(2) == pytest.approx((0.0, R, 0.0), abs=1e-9)
    grid.geometry = 20  # GEO_GRID_WIRE -> flat again
    scene.invalidate()
    assert scene.world_pos(2) == pytest.approx((90.0, 0.0, 0.0))


def test_globe_partial_refresh_matches_full_recompute(tmp_path):
    rows = [
        _globe_row(id=1, scale_x=1.5, scale_y=1.5, scale_z=1.5, rotate_z=20.0),
        _row(id=2, parent_id=1, branch_level=1, translate_x=-117.0, translate_y=33.0),
        _row(id=3, parent_id=2, branch_level=2, translate_x=1.0),
    ]
    nodes = load_node_csv(str(_write_csv(tmp_path, rows)))
    t = topo.compute_world_transforms(nodes, base_scale=1.0)
    nodes[1].translate_x = 2.4
    nodes[1].translate_y = 48.9
    nodes[1].translate_z = 3.0
    topo.update_world_transform_rows(nodes, 1.0, t, np.array([1, 2]))
    fresh = topo.compute_world_transforms(nodes, base_scale=1.0)
    np.testing.assert_allclose(t.world_pos, fresh.world_pos, atol=1e-12)
    np.testing.assert_allclose(t.world_basis, fresh.world_basis, atol=1e-12)
    np.testing.assert_allclose(t.parent_basis, fresh.parent_basis, atol=1e-12)


# ---------------------------------------------------------------------------
# Channels partial refresh (update_world_transform_rows) must agree with the
# full recompute for grid children — playback animates map points in place.
# ---------------------------------------------------------------------------

def test_partial_refresh_matches_full_recompute_for_grid_children(tmp_path):
    rows = [
        _grid_row(id=1, scale_x=2.0, scale_y=3.0, rotate_z=30.0,
                  trigger_lo_x=-125.0, trigger_hi_x=-66.0,
                  trigger_lo_y=24.0, trigger_hi_y=49.0),
        _row(id=2, parent_id=1, branch_level=1, translate_x=-100.0, translate_y=30.0),
        _row(id=3, parent_id=2, branch_level=2, translate_x=1.0),
    ]
    nodes = load_node_csv(str(_write_csv(tmp_path, rows)))
    t = topo.compute_world_transforms(nodes, base_scale=1.0)
    # Mutate the child + descendant, then partially refresh those rows only.
    nodes[1].translate_x = -80.0
    nodes[1].translate_y = 40.0
    nodes[2].translate_x = 2.5
    topo.update_world_transform_rows(nodes, 1.0, t, np.array([1, 2]))
    fresh = topo.compute_world_transforms(nodes, base_scale=1.0)
    np.testing.assert_allclose(t.world_pos, fresh.world_pos, atol=1e-12)
    np.testing.assert_allclose(t.world_basis, fresh.world_basis, atol=1e-12)
    np.testing.assert_allclose(t.parent_basis, fresh.parent_basis, atol=1e-12)


# ---------------------------------------------------------------------------
# CSV round-trip: extents/segments live in real 94-column fields.
# ---------------------------------------------------------------------------

def test_extents_and_segments_round_trip_through_save(tmp_path):
    grid = Node(
        id=1, type=NODE_TYPE_GRID, parent_id=0, branch_level=0,
        translate_x=0, translate_y=0, translate_z=0,
        rotate_x=0, rotate_y=0, rotate_z=0,
        scale_x=1, scale_y=1, scale_z=1,
        color_r=64, color_g=80, color_b=96, color_a=255,
        geometry=20, hide=0, topo=topo.TOPO_PLANE,
    )
    grid.set_grid_extents(-117.5, -116.25, 32.5, 33.75)   # fractional degrees
    grid.set_grid_segments(10, 5)
    path = tmp_path / "gv_node.csv"
    save_node_csv([grid], str(path))
    reloaded = load_node_csv(str(path))[0]
    assert reloaded.grid_extents() == pytest.approx((-117.5, -116.25, 32.5, 33.75))
    assert reloaded.grid_segments() == (10, 5)


def test_integral_trigger_values_still_write_as_ints(tmp_path):
    """Legacy files hold integer zeros in the trigger columns; the
    int-or-float formatting keeps those byte-identical on save."""
    rows = [_row(id=1, parent_id=0)]
    nodes = load_node_csv(str(_write_csv(tmp_path, rows)))
    out = tmp_path / "out_node.csv"
    save_node_csv(nodes, str(out))
    df = pd.read_csv(out, dtype=str)
    for col in ('trigger_hi_x', 'trigger_lo_x', 'trigger_hi_y', 'trigger_lo_y'):
        assert df[col].iloc[0] == '0'
