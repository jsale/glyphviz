"""
Scene merge (File > Merge Node CSV…) unit tests.

The contract (see glyphviz_core/scene_merge.py): loading a second node file
INTO a loaded scene rebases it onto a fresh id block above everything already
present, and rewrites every id-bearing field that goes with it — parent_id, a
link's extras['child_id'], and extras['record_id'] (the tag file's join key).
Per-file infrastructure rows (World, Camera) are dropped rather than
duplicated, channel bindings are cleared because channel ids live in the
incoming file's own ch-map id space, and node coordinates are left alone so
the two scenes overlay in one world space.
"""
import csv

import pytest

from glyphviz_core.csv_reader import (
    _COL_ORDER, load_node_csv, save_node_csv, save_tag_csv,
)
from glyphviz_core.node import (
    NODE_TYPE_CAMERA, NODE_TYPE_LINK, NODE_TYPE_WORLD, Node,
)
from glyphviz_core.scene import Scene
from glyphviz_core.scene_merge import merge_nodes


def _node(node_id, **overrides):
    kw = dict(
        id=node_id, type=5, parent_id=0, branch_level=0,
        translate_x=0.0, translate_y=0.0, translate_z=0.0,
        rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=255, color_g=0, color_b=0, color_a=255,
        geometry=3, hide=0, topo=0,
    )
    kw.update(overrides)
    return Node(**kw)


def _scene_a():
    """Two-node host scene: root 1 with child 2."""
    return [_node(1, translate_x=10.0), _node(2, parent_id=1, branch_level=1, translate_x=3.0)]


def _scene_b():
    """Guest scene whose ids collide with _scene_a()'s, exercising every
    rewrite rule: a World row, a Camera row, a glyph with a channel binding,
    a child, an orphan (parented onto the dropped camera), an internal link
    and a link with a dangling B-end."""
    b = [
        _node(1, type=NODE_TYPE_WORLD),
        _node(2, type=NODE_TYPE_CAMERA),
        _node(3, translate_x=100.0),
        _node(4, parent_id=3, branch_level=1, translate_x=5.0),
        _node(5, parent_id=2, translate_x=7.0),                       # child of the camera
        _node(6, type=NODE_TYPE_LINK, parent_id=3, branch_level=1),   # B-end inside
        _node(7, type=NODE_TYPE_LINK, parent_id=3, branch_level=1),   # B-end outside
    ]
    for n in b:
        n.extras = {'record_id': n.id, 'ch_input_id': 0}
    b[2].extras['ch_input_id'] = 7
    b[5].extras['child_id'] = 4
    b[6].extras['child_id'] = 99
    return b


# --- id rebasing -------------------------------------------------------

def test_new_ids_start_above_the_host_and_never_collide():
    a, b = _scene_a(), _scene_b()
    r = merge_nodes(a, b)
    assert min(n.id for n in r.nodes) == max(n.id for n in a) + 1
    merged = a + r.nodes
    assert len({n.id for n in merged}) == len(merged)


def test_parent_ids_are_remapped_into_the_new_block():
    a, b = _scene_a(), _scene_b()
    r = merge_nodes(a, b)
    child = next(n for n in r.nodes if n.id == r.id_map[4])
    assert child.parent_id == r.id_map[3]


def test_roots_stay_roots():
    r = merge_nodes(_scene_a(), _scene_b())
    root = next(n for n in r.nodes if n.id == r.id_map[3])
    assert root.parent_id == 0


def test_incoming_list_is_not_mutated():
    b = _scene_b()
    before = [(n.id, n.parent_id, dict(n.extras)) for n in b]
    merge_nodes(_scene_a(), b)
    assert [(n.id, n.parent_id, dict(n.extras)) for n in b] == before


def test_merging_the_same_list_twice_keeps_stacking():
    a = _scene_a()
    r1 = merge_nodes(a, _scene_b())
    a = a + r1.nodes
    r2 = merge_nodes(a, _scene_b())
    merged = a + r2.nodes
    assert len({n.id for n in merged}) == len(merged)


def test_empty_incoming_is_a_no_op():
    r = merge_nodes(_scene_a(), [])
    assert r.nodes == [] and r.count == 0


# --- infrastructure rows -----------------------------------------------

def test_world_and_camera_rows_are_dropped_when_the_host_has_a_world():
    a = _scene_a() + [_node(9, type=NODE_TYPE_WORLD)]
    r = merge_nodes(a, _scene_b())
    assert r.skipped_global == 2
    assert not any(n.type in (NODE_TYPE_WORLD, NODE_TYPE_CAMERA) for n in r.nodes)


def test_world_row_is_kept_when_the_host_has_none():
    # Merging into a scene with no World row must carry the incoming scene
    # settings (background, fog, tag styling) rather than silently lose them.
    r = merge_nodes([], _scene_b())
    assert sum(1 for n in r.nodes if n.type == NODE_TYPE_WORLD) == 1
    assert r.skipped_global == 1        # the Camera row only


def test_only_the_first_world_row_survives_a_merge_into_an_empty_scene():
    b = [_node(1, type=NODE_TYPE_WORLD), _node(2, type=NODE_TYPE_WORLD), _node(3)]
    r = merge_nodes([], b)
    assert sum(1 for n in r.nodes if n.type == NODE_TYPE_WORLD) == 1
    assert r.skipped_global == 1


def test_a_node_parented_onto_a_dropped_row_is_re_rooted():
    r = merge_nodes(_scene_a(), _scene_b())
    orphan = next(n for n in r.nodes if n.id == r.id_map[5])
    assert (orphan.parent_id, orphan.branch_level) == (0, 0)
    assert r.rerooted == 1


def test_a_dangling_parent_in_the_source_file_is_re_rooted_too():
    b = [_node(1, parent_id=42)]
    r = merge_nodes(_scene_a(), b)
    assert r.nodes[0].parent_id == 0
    assert r.rerooted == 1


# --- links --------------------------------------------------------------

def test_internal_link_b_end_is_remapped():
    r = merge_nodes(_scene_a(), _scene_b())
    link = next(n for n in r.nodes if n.id == r.id_map[6])
    assert link.extras['child_id'] == r.id_map[4]


def test_link_with_an_outside_b_end_is_dropped_not_left_dangling():
    r = merge_nodes(_scene_a(), _scene_b())
    assert r.dropped_links == 1
    assert 7 not in {old for old, new in r.id_map.items()
                     if new in {n.id for n in r.nodes}}


# --- tag join key -------------------------------------------------------

def test_record_id_follows_the_new_id_so_tag_rows_stay_unique(tmp_path):
    a, b = _scene_a(), _scene_b()
    a[0].text, a[0].extras = 'host one', {'record_id': 1}
    b[2].text = 'guest three'
    b[3].text = 'guest four'
    merged = a + merge_nodes(a, b).nodes

    tag_path = tmp_path / 'merged_gv_tag.csv'
    save_tag_csv(merged, str(tag_path))
    with open(tag_path, encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    record_ids = [r['record_id'] for r in rows]
    assert len(set(record_ids)) == len(record_ids) == 3


def test_native_nodes_without_a_record_id_column_are_left_alone():
    # gv_ native files have no record_id column; save_node_csv falls back to
    # node.id, so merge must not invent the key.
    b = [_node(1)]
    r = merge_nodes(_scene_a(), b)
    assert 'record_id' not in r.nodes[0].extras


# --- channel bindings ---------------------------------------------------

def test_channel_bindings_are_cleared():
    r = merge_nodes(_scene_a(), _scene_b())
    assert r.cleared_channels == 1
    assert all(int(n.extras.get('ch_input_id', 0)) == 0 for n in r.nodes)


@pytest.mark.parametrize('key', ['ch_input_id', 'np_ch_in_id', 'ch_output_id', 'np_ch_out_id'])
def test_every_channel_key_spelling_is_cleared(key):
    b = [_node(1)]
    b[0].extras = {key: 12}
    r = merge_nodes(_scene_a(), b)
    assert r.nodes[0].extras[key] == 0
    assert r.cleared_channels == 1


# --- geometry -----------------------------------------------------------

def test_coordinates_are_preserved_so_the_scenes_overlay():
    r = merge_nodes(_scene_a(), _scene_b())
    assert next(n for n in r.nodes if n.id == r.id_map[3]).translate_x == 100.0
    assert next(n for n in r.nodes if n.id == r.id_map[4]).translate_x == 5.0


def test_host_world_positions_are_untouched_by_a_merge():
    a = _scene_a()
    before = Scene(list(a), 1.0)
    before._ensure()
    expected = {n.id: before.world_pos(n.id) for n in a}
    merged = a + merge_nodes(a, _scene_b()).nodes
    after = Scene(merged, 1.0)
    after._ensure()
    assert {i: after.world_pos(i) for i in expected} == expected


def test_a_scene_merged_into_itself_lands_exactly_on_top():
    a = _scene_a()
    r = merge_nodes(a, a)
    merged = a + r.nodes
    sc = Scene(merged, 1.0)
    sc._ensure()
    assert sc.world_pos(r.id_map[2]) == sc.world_pos(2)


def test_branch_levels_are_recomputed_as_true_depth():
    b = [_node(1), _node(2, parent_id=1, branch_level=7), _node(3, parent_id=2, branch_level=7)]
    r = merge_nodes(_scene_a(), b)
    assert [n.branch_level for n in r.nodes] == [0, 1, 2]


# --- round-trip ---------------------------------------------------------

def test_merged_scene_round_trips_through_the_csv(tmp_path):
    a = _scene_a()
    merged = a + merge_nodes(a, _scene_b()).nodes
    path = tmp_path / 'merged_gv_node.csv'
    save_node_csv(merged, str(path))
    back = load_node_csv(str(path))
    assert [n.id for n in back] == [n.id for n in merged]
    assert [n.parent_id for n in back] == [n.parent_id for n in merged]
    assert [n.translate_x for n in back] == [n.translate_x for n in merged]
    assert [int(n.extras.get('child_id', 0)) for n in back] == \
           [int(n.extras.get('child_id', 0)) for n in merged]


def test_companion_tag_file_rides_along_on_the_merge(tmp_path):
    # load_node_csv resolves gv_tag.csv into node.text/link before merge_nodes
    # ever sees the nodes, so tags need no special handling — assert it.
    node_path = tmp_path / 'guest_gv_node.csv'
    with open(node_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        cols = ['id', 'type', 'parent_id', 'branch_level',
                'translate_x', 'translate_y', 'translate_z',
                'rotate_x', 'rotate_y', 'rotate_z',
                'scale_x', 'scale_y', 'scale_z',
                'color_r', 'color_g', 'color_b', 'color_a',
                'geometry', 'hide', 'topo']
        w.writerow(cols)
        w.writerow([1, 5, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 255, 0, 0, 255, 3, 0, 0])
        w.writerow([2, 5, 1, 1, 0, 0, 0, 0, 0, 0, 1, 1, 1, 255, 0, 0, 255, 3, 0, 0])
    with open(tmp_path / 'guest_gv_tag.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['id', 'table_id', 'record_id', 'title'])
        w.writerow([0, 0, 2, '<a href="https://example.com">guest two</a>'])

    guest = load_node_csv(str(node_path))
    r = merge_nodes(_scene_a(), guest)
    tagged = next(n for n in r.nodes if n.id == r.id_map[2])
    assert (tagged.text, tagged.link) == ('guest two', 'https://example.com')
