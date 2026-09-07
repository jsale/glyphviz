"""
Point Cloud topology (TOPO_POINTCLOUD) — placement rules and batch building.

Qt-free and GL-free: everything here is glyphviz_core.point_cloud plus the
topology math it sits on. The rendering side is pinned in
tests/test_point_cloud_gui.py.

What matters most in this file is the back-compat claim the whole design
rests on: a cloud parent places its children with plain Cartesian offsets,
which is byte-for-byte what an UNKNOWN topo id already did, so a topo=18
file opened by a build that predates this topology puts every point in
exactly the right place.
"""
import numpy as np
import pytest

from glyphviz_core import point_cloud as pc
from glyphviz_core.geometry_data import GEO_POINT, GEO_SPHERE
from glyphviz_core.node import Node, NODE_TYPE_LINK, NODE_TYPE_WORLD
from glyphviz_core.scene import Scene
from glyphviz_core.topology import (
    LINEAR_PLACEMENT_AXES, TOPO_COUNT, TOPO_NAMES, TOPO_NONE, TOPO_PLANE,
    TOPO_POINTCLOUD, TOPO_SPHERE, placement_offset,
)


def _node(**kw):
    base = dict(
        id=1, type=5, parent_id=0, branch_level=0,
        translate_x=0.0, translate_y=0.0, translate_z=0.0,
        rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=200, color_g=200, color_b=200, color_a=255,
        geometry=GEO_SPHERE, hide=0, topo=TOPO_NONE,
    )
    base.update(kw)
    return Node(**base)


def _cloud(n=5, **parent_kw):
    """A cloud parent plus n points at known, distinct coordinates."""
    parent = _node(id=1, topo=TOPO_POINTCLOUD, **parent_kw)
    pts = [
        _node(id=10 + i, parent_id=1, branch_level=1, geometry=GEO_POINT,
              translate_x=float(i), translate_y=float(2 * i),
              translate_z=float(-i),
              color_r=i, color_g=10 + i, color_b=20 + i, color_a=200 + i)
        for i in range(n)
    ]
    return parent, pts


# --- registration ----------------------------------------------------------

def test_topology_is_registered():
    assert TOPO_POINTCLOUD == 18
    assert TOPO_COUNT == 19          # so every dropdown/cycler picks it up
    assert TOPO_NAMES[TOPO_POINTCLOUD] == "Point Cloud"


def test_all_three_axes_are_distances():
    """Nothing about a cloud is angular, so topo_scale multiplies all of it —
    which is what lets a scan authored in metres be retuned with one field."""
    assert LINEAR_PLACEMENT_AXES[TOPO_POINTCLOUD] == (True, True, True)


# --- placement -------------------------------------------------------------

def test_placement_is_plain_cartesian():
    parent, _ = _cloud()
    assert placement_offset(parent, 3.0, -4.0, 5.0, 1.0) == (3.0, -4.0, 5.0)


def test_placement_matches_an_unknown_topo_id_exactly():
    """The back-compat claim, stated as a test.

    A build predating this topology treats topo=18 as unknown and falls back
    to Cartesian. If that fallback and _pointcloud_offset ever diverged, every
    existing cloud file would silently relocate when opened by the older
    build (or the newer one, depending which side moved).
    """
    cloud = _node(id=1, topo=TOPO_POINTCLOUD)
    unknown = _node(id=1, topo=999)
    for tx, ty, tz in [(0, 0, 0), (7.5, -2.25, 13.0), (-180.0, 90.0, 1e3)]:
        assert (placement_offset(cloud, tx, ty, tz, 3.0)
                == placement_offset(unknown, tx, ty, tz, 3.0))


def test_placement_matches_plane_and_none():
    """Same Cartesian layout as Plane/None — a distinct semantic, not a
    distinct coordinate system (the same relationship Plot and Surface have
    to Plane)."""
    args = (11.0, -3.0, 4.0, 3.0)
    got = placement_offset(_node(topo=TOPO_POINTCLOUD), *args)
    assert got == placement_offset(_node(topo=TOPO_PLANE), *args)
    assert got == placement_offset(_node(topo=TOPO_NONE), *args)


def test_batched_engine_agrees_with_the_scalar_path():
    """Scene's vectorized engine has no case for TOPO_POINTCLOUD at all — it
    rides the Cartesian default fill. Pin that this really does produce the
    same world positions the scalar placement_offset would."""
    parent, pts = _cloud(4)
    parent.translate_x, parent.translate_y, parent.translate_z = 5.0, -6.0, 7.0
    scene = Scene([parent] + pts, base_scale=3.0)
    for p in pts:
        off = placement_offset(parent, p.translate_x, p.translate_y,
                               p.translate_z, 3.0)
        want = (5.0 + off[0], -6.0 + off[1], 7.0 + off[2])
        assert scene.world_pos(p.id) == pytest.approx(want)


def test_topo_scale_still_reaches_the_points():
    """All three axes are linear, so a cloud parent's topo_scale is a plain
    per-axis multiplier — the knob that rescales an imported scan."""
    parent = _node(id=1, topo=TOPO_POINTCLOUD, topo_scale=0.5)
    assert placement_offset(parent, 10.0, 20.0, -30.0, 1.0) == (5.0, 10.0, -15.0)


# --- membership ------------------------------------------------------------

def test_cloud_parent_ids_finds_only_cloud_parents():
    parent, pts = _cloud(3)
    other = _node(id=90, topo=TOPO_SPHERE)
    nodes = [parent, other] + pts
    assert pc.cloud_parent_ids(nodes) == {1}


def test_a_link_is_never_a_cloud_parent():
    """A Link's topo column is meaningless — it renders as an edge between
    two ends and has no children. Same exclusion _SceneScan makes for Plot
    and Surface."""
    link = _node(id=7, type=NODE_TYPE_LINK, topo=TOPO_POINTCLOUD)
    assert not pc.is_cloud_parent(link)
    assert pc.cloud_parent_ids([link]) == set()


def test_drawable_children_filters_hidden_links_and_world_rows():
    parent, pts = _cloud(4)
    pts[1].hide = 1
    pts[2].type = NODE_TYPE_LINK
    pts[3].type = NODE_TYPE_WORLD
    kids = pc.drawable_children(pts, show_hidden=False)
    assert [k.id for k in kids] == [10]
    # show_hidden brings back the hidden point but never the Link/World rows
    kids = pc.drawable_children(pts, show_hidden=True)
    assert [k.id for k in kids] == [10, 11]


# --- batch building --------------------------------------------------------

def test_build_batch_carries_ids_positions_and_colors():
    _, pts = _cloud(3)
    positions = np.array([[1., 2., 3.], [4., 5., 6.], [7., 8., 9.]])
    batch = pc.build_batch(pts, positions)
    assert len(batch) == 3
    assert list(batch.ids) == [10, 11, 12]
    assert batch.positions.dtype == np.float32
    np.testing.assert_allclose(batch.positions, positions)
    # colors come straight off each node, in order
    assert list(batch.colors[0]) == [0, 10, 20, 200]
    assert list(batch.colors[2]) == [2, 12, 22, 202]
    assert batch.colors.dtype == np.uint8


def test_build_batch_index_order_is_the_child_order():
    """CloudBatch.ids[i] must name the node drawn at vertex i — that identity
    is what makes the color-ID pick pass resolve to the right node."""
    _, pts = _cloud(6)
    pts.reverse()
    positions = np.arange(18, dtype=float).reshape(6, 3)
    batch = pc.build_batch(pts, positions)
    assert list(batch.ids) == [p.id for p in pts]
    np.testing.assert_allclose(batch.positions[3], positions[3])


def test_build_batch_returns_none_for_an_empty_cloud():
    assert pc.build_batch([], np.zeros((0, 3))) is None


def test_build_batch_refuses_a_position_count_mismatch():
    """A silent partial batch would draw some points at other points'
    coordinates — far worse than drawing nothing."""
    _, pts = _cloud(3)
    assert pc.build_batch(pts, np.zeros((2, 3))) is None


# --- point size ------------------------------------------------------------

def test_point_size_reads_ratio_like_links_and_plots_do():
    assert pc.point_size(_node(ratio=0.1)) == pytest.approx(2.0)
    assert pc.point_size(_node(ratio=0.5)) == pytest.approx(10.0)


def test_point_size_is_clamped_at_both_ends():
    """Below 1 px a point stops rasterizing; past the driver maximum
    glPointSize is silently ignored, which would make the field look broken
    at some values and not others."""
    assert pc.point_size(_node(ratio=0.0)) == pc.MIN_POINT_SIZE
    assert pc.point_size(_node(ratio=-5.0)) == pc.MIN_POINT_SIZE
    assert pc.point_size(_node(ratio=1e6)) == pc.MAX_POINT_SIZE


# --- pick colors -----------------------------------------------------------

def test_id_colors_match_the_renderer_encoding_bit_for_bit():
    """The per-glyph pick pass writes (id & 0xFF, id >> 8, id >> 16). A cloud
    point has to encode identically or the FBO read decodes it as a different
    node."""
    ids = np.array([1, 255, 256, 65535, 65536, 16777215], dtype=np.int64)
    cols = pc.id_colors(ids)
    for i, nid in enumerate(ids):
        assert tuple(cols[i]) == (nid & 0xFF, (nid >> 8) & 0xFF,
                                  (nid >> 16) & 0xFF, 255)


def test_id_colors_are_opaque():
    """The pick FBO is cleared to alpha 0 and background is read as "nothing
    hit" — a translucent point would blend toward it and decode wrong."""
    cols = pc.id_colors(np.arange(1, 50, dtype=np.int64))
    assert (cols[:, 3] == 255).all()


# --- Scene.world_pos_rows (the batched gather the builder is fed from) ------

def test_world_pos_rows_matches_world_pos_one_at_a_time():
    parent, pts = _cloud(5)
    parent.translate_z = 4.0
    scene = Scene([parent] + pts, base_scale=1.0)
    ids = [p.id for p in pts]
    mask, positions = scene.world_pos_rows(ids)
    assert mask.all()
    for i, nid in enumerate(ids):
        assert tuple(positions[i]) == pytest.approx(scene.world_pos(nid))


def test_world_pos_rows_flags_unresolvable_ids():
    parent, pts = _cloud(3)
    scene = Scene([parent] + pts, base_scale=1.0)
    mask, positions = scene.world_pos_rows([10, 999, 12])
    assert list(mask) == [True, False, True]
    assert positions.shape == (2, 3)
