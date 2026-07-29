"""
Channels animation engine unit tests.

The contract (see glyphviz_core/channel_engine.py): a ch-map row binds one
channel to one node attribute fed by one track, values are absolute (never
deltas, never interpolated), integer-valued fields are rounded and clamped to
their own valid range, and Stop restores every touched field to its CSV value.

These tests pin the bindable-attribute set itself, because it is the file
format's public surface: an attribute that silently stops binding breaks
authored scenes with no error anywhere. They also pin the transform/
non-transform split, which the viewport's playback fast path relies on to
decide whose subtree needs fresh matrices each frame.
"""
import numpy as np
import pytest

from glyphviz_core.channel_engine import ChannelEngine
from glyphviz_core.color_palette import PALETTE_COUNT, resolve_palette_color
from glyphviz_core.geometry_data import GEO_COUNT
from glyphviz_core.node import (
    NODE_TYPE_WORLD, RENDER_MODE_COUNT, RENDER_MODE_SCREEN, Node,
)
from glyphviz_core.scene import Scene
from glyphviz_core.topology import TOPO_COUNT, TOPO_SPHERE, TOPO_TORUS


def _node(node_id, channel=0, **overrides):
    kw = dict(
        id=node_id, type=1, parent_id=0, branch_level=0,
        translate_x=0.0, translate_y=0.0, translate_z=0.0,
        rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=100, color_g=110, color_b=120, color_a=255,
        geometry=11, hide=0, topo=0,
    )
    kw.update(overrides)
    node = Node(**kw)
    if channel:
        node.extras['ch_input_id'] = channel
    return node


def _engine(nodes, map_rows, frames):
    """Build a loaded engine from (channel_id, track_id, attribute) rows and a
    list of {track_id: value} frame dicts — the in-memory equivalent of what
    channel_loader produces from the two CSVs."""
    ch_map = {}
    for cid, tid, attr in map_rows:
        ch_map.setdefault(cid, []).append((tid, attr))
    track_ids = sorted({tid for _c, tid, _a in map_rows})
    id_to_col = {tid: i for i, tid in enumerate(track_ids)}
    tracks = np.array([[f.get(tid, 0.0) for tid in track_ids] for f in frames],
                      dtype=np.float64)
    engine = ChannelEngine()
    engine.load(ch_map, tracks, id_to_col, nodes)
    return engine


# --------------------------------------------------------------- shape ----

def test_shape_fields_bind():
    """ratio/topo/geometry/mesh_id animate a glyph's form, not just its
    placement and color."""
    n = _node(1, channel=1, topo=TOPO_TORUS, ratio=0.1)
    eng = _engine([n],
                  [(1, 10, 'ratio'), (1, 11, 'topo'),
                   (1, 12, 'geometry'), (1, 13, 'mesh_id')],
                  [{10: 0.1, 11: TOPO_TORUS, 12: 11, 13: 0},
                   {10: 0.4, 11: TOPO_SPHERE, 12: 3, 13: 2}])
    eng.apply_frame(1)
    assert n.ratio == pytest.approx(0.4)
    assert (n.topo, n.geometry, n.mesh_id) == (TOPO_SPHERE, 3, 2)


def test_shape_fields_are_transform_bound():
    """ratio/topo/geometry change where children sit (torus placement radius,
    the placement rule itself, and a World Grid's flat/globe form), so the
    fast path must refresh their subtrees — color/texture must not."""
    nodes = [_node(1, channel=1), _node(2, channel=2)]
    eng = _engine(nodes,
                  [(1, 10, 'ratio'), (1, 11, 'topo'), (1, 12, 'geometry'),
                   (2, 13, 'color_r'), (2, 14, 'texture_id'),
                   (2, 15, 'hide'), (2, 16, 'show_text')],
                  [{}, {}])
    assert eng.bound_node_ids == {1, 2}
    assert eng.transform_bound_node_ids == {1}


# ------------------------------------------------------------- palette ----

def test_color_index_resolves_to_rgb():
    """A single track carrying a palette index paints the glyph — the one
    place palette resolution runs without a =/- keypress."""
    n = _node(1, channel=1, palette_id=0, color_index=0)
    eng = _engine([n], [(1, 10, 'color_index'), (1, 11, 'palette_id')],
                  [{10: 0, 11: 0}, {10: 5, 11: 2}])
    eng.apply_frame(1)
    assert (n.palette_id, n.color_index) == (2, 5)
    assert (n.color_r, n.color_g, n.color_b) == resolve_palette_color(2, 5)


def test_palette_resolution_leaves_alpha_alone():
    n = _node(1, channel=1, color_a=77)
    eng = _engine([n], [(1, 10, 'color_index')], [{10: 3}])
    eng.apply_frame(0)
    assert n.color_a == 77


def test_reset_restores_palette_driven_rgb():
    """color_r/g/b are overwritten by resolution even though no track bound
    them, so Stop has to put them back too."""
    n = _node(1, channel=1, color_r=100, color_g=110, color_b=120)
    eng = _engine([n], [(1, 10, 'color_index')], [{10: 4}])
    eng.apply_frame(0)
    assert (n.color_r, n.color_g, n.color_b) != (100, 110, 120)
    eng.reset()
    assert (n.color_r, n.color_g, n.color_b) == (100, 110, 120)
    assert n.color_index == 0


# ---------------------------------------------------------- visibility ----

def test_hide_and_show_text_bind_as_flags():
    n = _node(1, channel=1, hide=0, show_text=0)
    eng = _engine([n], [(1, 10, 'hide'), (1, 11, 'show_text')],
                  [{10: 0, 11: 0}, {10: 1, 11: 1}, {10: 7, 11: 0.6}])
    eng.apply_frame(1)
    assert (n.hide, n.show_text) == (1, 1)
    eng.apply_frame(2)
    assert (n.hide, n.show_text) == (1, 1), "any positive value reads as on"
    eng.apply_frame(0)
    assert (n.hide, n.show_text) == (0, 0)


# --------------------------------------------------- World scene fields ----

def test_world_scene_fields_bind():
    """render_mode/fog_* are read only off the World node (Scene.world_node),
    and its color_r/g/b is the scene background."""
    w = _node(1, channel=9, type=NODE_TYPE_WORLD, color_r=10)
    eng = _engine([w],
                  [(9, 10, 'render_mode'), (9, 11, 'fog_enabled'),
                   (9, 12, 'fog_start'), (9, 13, 'fog_end'), (9, 14, 'color_r')],
                  [{10: 0, 11: 0, 12: 0.0, 13: 0.0, 14: 10},
                   {10: RENDER_MODE_SCREEN, 11: 1, 12: 50.0, 13: 900.0, 14: 200}])
    eng.apply_frame(1)
    assert w.render_mode == RENDER_MODE_SCREEN
    assert w.fog_enabled == 1
    assert (w.fog_start, w.fog_end) == (50.0, 900.0)
    assert w.color_r == 200
    assert eng.transform_bound_node_ids == set(), "scene settings move nothing"


def test_world_scene_fields_reset():
    w = _node(1, channel=9, type=NODE_TYPE_WORLD, color_r=10)
    eng = _engine([w], [(9, 10, 'render_mode'), (9, 11, 'color_r')],
                  [{10: RENDER_MODE_SCREEN, 11: 200}])
    eng.apply_frame(0)
    eng.reset()
    assert w.render_mode == 0
    assert w.color_r == 10


# -------------------------------------------------------------- clamps ----

@pytest.mark.parametrize("attr, raw, expected", [
    ('color_r', 400, 255),
    ('color_r', -5, 0),
    ('topo', 999, TOPO_COUNT - 1),
    ('geometry', 999, GEO_COUNT - 1),
    ('palette_id', 999, PALETTE_COUNT - 1),
    ('render_mode', 99, RENDER_MODE_COUNT - 1),
    ('hide', 7, 1),
    ('fog_enabled', 3, 1),
    ('mesh_id', -4, 0),
    ('color_index', -3, 0),
    ('texture_id', -1, 0),
])
def test_int_fields_clamp_to_valid_range(attr, raw, expected):
    """An out-of-range track value must land on a usable value, not index off
    the end of a palette/geometry table at draw time."""
    n = _node(1, channel=1)
    eng = _engine([n], [(1, 10, attr)], [{10: raw}])
    eng.apply_frame(0)
    value = getattr(n, attr)
    assert value == expected
    assert isinstance(value, int)


def test_float_fields_are_not_clamped():
    """fog_start/translate_* mean exactly what the track says, including
    negatives."""
    w = _node(1, channel=9, type=NODE_TYPE_WORLD)
    eng = _engine([w], [(9, 10, 'fog_start'), (9, 11, 'fog_end')],
                  [{10: -10.0, 11: 1e6}])
    eng.apply_frame(0)
    assert w.fog_start == -10.0
    assert w.fog_end == 1e6


def test_unknown_attribute_is_skipped_silently():
    n = _node(1, channel=1)
    eng = _engine([n], [(1, 10, 'ratio'), (1, 11, 'no_such_attr')], [{10: 0.3}])
    assert len(eng._bindings) == 1
    eng.apply_frame(0)
    assert n.ratio == pytest.approx(0.3)


# ------------------------------------------------------------ fast path ----

def test_shape_change_partial_refresh_matches_full_recompute():
    """Scene.refresh_rows (the no-revision-bump playback path) must place a
    child identically to a from-scratch compute after its parent's ratio and
    topo animate — the contract update_world_transform_rows now documents."""
    parent = _node(1, channel=1, topo=TOPO_TORUS, ratio=0.1,
                   scale_x=3.0, scale_y=3.0, scale_z=3.0)
    child = _node(2, parent_id=1, branch_level=1,
                  translate_x=45.0, translate_y=30.0)
    nodes = [parent, child]
    eng = _engine(nodes, [(1, 10, 'ratio'), (1, 11, 'topo')],
                  [{10: 0.1, 11: TOPO_TORUS}, {10: 0.4, 11: TOPO_SPHERE}])

    scene = Scene(nodes, base_scale=1.0)
    before = scene.world_pos(2)

    eng.apply_frame(1)
    rows = scene.rows_for_ids({1, 2})   # bound node + its descendants
    scene.refresh_rows(rows)
    fast = scene.world_pos(2)
    fast_matrix = scene.node_draw_data(child)[0]

    fresh = Scene(nodes, base_scale=1.0)
    assert fast == pytest.approx(fresh.world_pos(2), abs=1e-12)
    assert np.allclose(fast_matrix, fresh.node_draw_data(child)[0], atol=1e-12)
    assert fast != pytest.approx(before), "the shape change should have moved it"
