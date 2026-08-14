"""Save Selection As… — selection export unit tests.

The contract (see glyphviz_core/selection_export.py): a subset of a scene's
nodes has to be repaired before it can stand alone as a file, because
topology._resolve_hierarchy silently treats a node with a missing parent as a
ROOT — and a root's translate IS its world position, with no topology offset.

The central test here is test_bake_keeps_every_world_matrix: export a middle
slice of a deep, rotated, scaled hierarchy, reload it through the real CSV
writer/reader into a real Scene, and require node_world_matrix to agree with
the source scene for every node — the single source of truth for where a
glyph actually lands (see scene.py's design contract).
"""
import math

import numpy as np
import pytest

from glyphviz_core.channel_engine import channel_ids_for_nodes
from glyphviz_core.channel_loader import (
    export_channel_subset, load_ch_map, load_ch_tracks,
)
from glyphviz_core.csv_reader import load_node_csv, save_node_csv
from glyphviz_core.node import (
    NODE_TYPE_GRID, NODE_TYPE_LINK, NODE_TYPE_WORLD,
    ROTATION_MODE_EULER_XYZ, ROTATION_MODE_HEADING_TILT_ROLL, Node,
)
from glyphviz_core.scene import Scene, node_world_matrix
from glyphviz_core.selection_export import (
    DETACH_ANCESTORS, DETACH_BAKE, DETACH_RAW, ExportOptions,
    build_selection, decompose_basis, euler_xyz_from_matrix,
)
from glyphviz_core.topology import (
    TOPO_CUBE, TOPO_NONE, TOPO_ROD, TOPO_SPHERE, TOPO_TORUS,
    local_rotation_matrix,
)

BASE_SCALE = 1.0


def _node(node_id, **overrides):
    kw = dict(
        id=node_id, type=5, parent_id=0, branch_level=0,
        translate_x=0.0, translate_y=0.0, translate_z=0.0,
        rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=255, color_g=128, color_b=0, color_a=255,
        geometry=3, hide=0, topo=TOPO_NONE,
    )
    kw.update(overrides)
    return Node(**kw)


def _deep_scene():
    """A hierarchy with something to lose at every level.

    1  World row (scene settings, never selectable in bulk)
    2  root, Sphere topology, rotated and scaled — so its children's
       translate means longitude/latitude/altitude, not world units
      3  Cube topology, rotated in the ANTz Heading/Tilt/Roll convention
        4  Torus topology, non-uniformly scaled
          5  leaf
          8  rod (exercises the ANTz cap-offset branch of node_world_matrix)
        6  leaf
      7  link joining 4 and 6, both inside the subtree under 3
      9  link joining 6 to root 2, i.e. one end outside that subtree
    """
    nodes = [
        _node(1, type=NODE_TYPE_WORLD, color_r=10, color_g=20, color_b=30),
        _node(2, topo=TOPO_SPHERE, translate_x=100.0, translate_y=-40.0,
              translate_z=8.0, rotate_x=15.0, rotate_y=35.0, rotate_z=-25.0,
              scale_x=1.5, scale_y=1.5, scale_z=1.5),
        _node(3, parent_id=2, branch_level=1, topo=TOPO_CUBE,
              translate_x=30.0, translate_y=45.0, translate_z=5.0,
              rotate_x=20.0, rotate_y=-10.0, rotate_z=70.0,
              rotation_mode=ROTATION_MODE_HEADING_TILT_ROLL,
              scale_x=0.8, scale_y=0.8, scale_z=0.8),
        _node(4, parent_id=3, branch_level=2, topo=TOPO_TORUS, subspace=2,
              translate_x=90.0, translate_y=-30.0, translate_z=2.0,
              rotate_x=5.0, rotate_y=45.0, rotate_z=0.0,
              scale_x=0.6, scale_y=0.6, scale_z=0.6),
        _node(5, parent_id=4, branch_level=3,
              translate_x=200.0, translate_y=60.0, translate_z=1.0,
              scale_x=0.4, scale_y=0.4, scale_z=0.4),
        _node(6, parent_id=3, branch_level=2,
              translate_x=-120.0, translate_y=15.0, translate_z=3.0),
        _node(7, type=NODE_TYPE_LINK, parent_id=4, branch_level=3),
        _node(8, parent_id=4, branch_level=3, topo=TOPO_ROD,
              translate_x=45.0, translate_y=10.0, translate_z=2.0,
              scale_x=0.5, scale_y=0.5, scale_z=2.0),
        _node(9, type=NODE_TYPE_LINK, parent_id=6, branch_level=3),
    ]
    for n in nodes:
        n.extras = {'record_id': n.id}
    nodes[6].extras['child_id'] = 6    # link 7: 4 -> 6, both under node 3
    nodes[8].extras['child_id'] = 2    # link 9: 6 -> 2, one end outside
    return nodes


def _scene(nodes):
    return Scene(nodes, base_scale=BASE_SCALE)


def _matrices(scene, ids):
    return {
        i: node_world_matrix(scene.node_by_id(i), scene)
        for i in ids if scene.node_by_id(i) is not None
    }


def _glyph_ids(export):
    return [n.id for n in export.nodes if n.type != NODE_TYPE_WORLD]


# --- the decomposition the bake rests on -------------------------------------

@pytest.mark.parametrize("angles", [
    (0.0, 0.0, 0.0),
    (30.0, 45.0, 60.0),
    (-120.0, 15.0, 175.0),
    (10.0, -80.0, -95.0),
    (0.0, 90.0, 0.0),      # gimbal lock
    (33.0, -90.0, 21.0),   # gimbal lock, rotation split between rx and rz
])
def test_euler_xyz_roundtrip(angles):
    """euler_xyz_from_matrix inverts topology's Euler XYZ matrix builder —
    including at gimbal lock, where the recovered angles differ from the
    input but must still rebuild the same matrix."""
    R = np.array(local_rotation_matrix(*angles, ROTATION_MODE_EULER_XYZ))
    recovered = euler_xyz_from_matrix(R)
    R2 = np.array(local_rotation_matrix(*recovered, ROTATION_MODE_EULER_XYZ))
    assert np.allclose(R, R2, atol=1e-12)


def test_decompose_basis_exact_for_rotation_and_scale():
    R = np.array(local_rotation_matrix(20.0, -35.0, 80.0, ROTATION_MODE_EULER_XYZ))
    s = np.array([2.0, 0.5, 3.25])
    A = R @ np.diag(s)
    R2, s2, shear = decompose_basis(A)
    assert shear == pytest.approx(0.0, abs=1e-12)
    assert np.allclose(s2, s)
    assert np.allclose(R2 @ np.diag(s2), A, atol=1e-12)


def test_decompose_basis_folds_reflection_into_z_scale():
    """A negative scale field upstream leaves a left-handed basis. R stays a
    true rotation (det +1) and the sign rides on the Z scale, so the product
    is still exact."""
    R = np.array(local_rotation_matrix(10.0, 20.0, 30.0, ROTATION_MODE_EULER_XYZ))
    A = R @ np.diag([1.0, -2.0, 1.0])
    R2, s2, shear = decompose_basis(A)
    assert np.linalg.det(R2) == pytest.approx(1.0)
    assert shear == pytest.approx(0.0, abs=1e-12)
    assert np.allclose(R2 @ np.diag(s2), A, atol=1e-12)


def test_decompose_basis_collapsed_axis_is_still_exact():
    """A zero-scale axis is not an approximation: whatever rotation column
    pairs with it is annihilated by the zero."""
    R = np.array(local_rotation_matrix(45.0, 0.0, 0.0, ROTATION_MODE_EULER_XYZ))
    A = R @ np.diag([1.0, 0.0, 2.0])
    R2, s2, shear = decompose_basis(A)
    assert shear == pytest.approx(0.0, abs=1e-12)
    assert np.allclose(R2 @ np.diag(s2), A, atol=1e-12)


def test_decompose_basis_reports_shear():
    sheared = np.array([[1.0, 0.4, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    _R, _s, shear = decompose_basis(sheared)
    assert shear > 0.3


# --- the core fidelity guarantee ---------------------------------------------

def test_bake_keeps_every_world_matrix():
    """Export the subtree under node 3 — whose parent is a rotated, scaled
    Sphere, so its translate means longitude/latitude — and require every
    exported node to land exactly where it was, through a real CSV round
    trip."""
    src = _scene(_deep_scene())
    export = build_selection(src, {3})
    ids = _glyph_ids(export)
    assert set(ids) == {3, 4, 5, 6, 7, 8}   # subtree + the internal link

    before = _matrices(src, ids)
    reloaded = _scene(export.nodes)
    after = _matrices(reloaded, ids)
    for i in ids:
        assert np.allclose(before[i], after[i], atol=1e-9), f"node {i} moved"

    assert export.detached_ids == [3]
    assert export.approximated_ids == []


def test_bake_survives_the_csv_round_trip(tmp_path):
    """Same guarantee, but through save_node_csv/load_node_csv — the 6-dp
    column formatting has to be fine enough to hold the baked values."""
    src = _scene(_deep_scene())
    export = build_selection(src, {4})
    path = tmp_path / "fragment_gv_node.csv"
    save_node_csv(export.nodes, str(path))

    reloaded = _scene(load_node_csv(str(path)))
    ids = _glyph_ids(export)
    before = _matrices(src, ids)
    after = _matrices(reloaded, ids)
    for i in ids:
        assert np.allclose(before[i], after[i], atol=1e-5), f"node {i} moved"


def test_bake_holds_at_every_depth():
    """Detaching deeper into the chain is the same guarantee, one level at a
    time — including node 8, the rod, whose draw matrix carries the ANTz cap
    offset."""
    for root_id in (2, 3, 4, 5, 8):
        src = _scene(_deep_scene())
        export = build_selection(src, {root_id})
        ids = _glyph_ids(export)
        before = _matrices(src, ids)
        after = _matrices(_scene(export.nodes), ids)
        for i in ids:
            assert np.allclose(before[i], after[i], atol=1e-9), \
                f"node {i} moved when detaching {root_id}"


def test_raw_mode_is_the_bug_bake_fixes():
    """The control case. Node 3's translate (30, 45, 5) is longitude/latitude/
    altitude on its Sphere parent; saved raw it reloads as literal world
    (30, 45, 5), hundreds of units from where it was drawn."""
    src = _scene(_deep_scene())
    raw = build_selection(src, {3}, ExportOptions(detach=DETACH_RAW))
    node = next(n for n in raw.nodes if n.id == 3)
    assert (node.translate_x, node.translate_y, node.translate_z) == (30.0, 45.0, 5.0)

    was = np.array(src.world_pos(3))
    now = np.array(_scene(raw.nodes).world_pos(3))
    assert np.linalg.norm(was - now) > 50.0

    baked = build_selection(src, {3}, ExportOptions(detach=DETACH_BAKE))
    stayed = np.array(_scene(baked.nodes).world_pos(3))
    assert np.allclose(was, stayed, atol=1e-9)


def test_bake_leaves_the_childrens_coordinate_system_alone():
    """topo/ratio/topo_scale/subspace describe the frame a node offers its
    CHILDREN, so a detach must not touch them — only the fields saying where
    the node itself sits."""
    src = _scene(_deep_scene())
    export = build_selection(src, {4})
    before = src.node_by_id(4)
    after = next(n for n in export.nodes if n.id == 4)
    assert (after.topo, after.ratio, after.topo_scale, after.subspace) == \
           (before.topo, before.ratio, before.topo_scale, before.subspace)
    assert after.rotation_mode == ROTATION_MODE_EULER_XYZ   # the mode that can hold any rotation


def test_bake_reports_shear_from_a_squashed_ancestor():
    """A non-uniform ancestor scale under rotation shears the child's basis,
    which no rotate+scale pair can express. It must be counted, not hidden."""
    nodes = _deep_scene()
    parent = next(n for n in nodes if n.id == 2)
    parent.scale_x, parent.scale_y, parent.scale_z = (3.0, 1.0, 0.5)
    src = _scene(nodes)
    export = build_selection(src, {3})
    assert export.approximated_ids == [3]


def test_uniformly_scaled_ancestor_is_not_flagged():
    src = _scene(_deep_scene())          # node 2 is scaled 1.5 uniformly
    export = build_selection(src, {3})
    assert export.approximated_ids == []


def test_detached_node_with_rates_is_reported():
    """Rates on a Sphere child orbit it in longitude; on a root the same
    numbers drift it through world XYZ. The export can't fix that, so it
    says so."""
    nodes = _deep_scene()
    next(n for n in nodes if n.id == 3).translate_rate_x = 0.5
    export = build_selection(_scene(nodes), {3})
    assert export.animated_detached == [3]


# --- membership rules ---------------------------------------------------------

def test_descendants_come_along_by_default():
    """The closure under node 4 is {5, 7, 8} — but link 7's B-end is node 6,
    which lives on the other branch, so the link is dropped on the way out.
    Descendant membership and link validity are separate rules."""
    src = _scene(_deep_scene())
    export = build_selection(src, {4})
    assert export.descendants_added == 3
    assert set(_glyph_ids(export)) == {4, 5, 8}
    assert export.dropped_links == 1


def test_descendants_can_be_left_out():
    src = _scene(_deep_scene())
    export = build_selection(src, {4}, ExportOptions(include_descendants=False))
    assert set(_glyph_ids(export)) == {4}
    assert export.descendants_added == 0


def test_selection_of_scattered_leaves_detaches_each_one():
    """Two leaves from different branches: each is re-rooted independently,
    and both keep their world placement."""
    src = _scene(_deep_scene())
    export = build_selection(src, {5, 6})
    assert set(_glyph_ids(export)) == {5, 6}
    assert sorted(export.detached_ids) == [5, 6]
    after = _scene(export.nodes)
    for i in (5, 6):
        assert np.allclose(src.world_pos(i), after.world_pos(i), atol=1e-9)


def test_link_with_both_ends_inside_is_pulled_in_unselected():
    """Link 7 joins 4 and 6 and was never selected; without it, saving both
    ends would silently lose the edge."""
    src = _scene(_deep_scene())
    export = build_selection(src, {4, 6}, ExportOptions(include_descendants=False))
    assert 7 in _glyph_ids(export)
    assert export.links_added == 1


def test_link_with_one_end_outside_is_dropped():
    """Link 9 joins 6 to root 2. Exporting the subtree under 3 takes 6 but
    not 2, so the link goes rather than dangle."""
    src = _scene(_deep_scene())
    export = build_selection(src, {3})
    assert 9 not in _glyph_ids(export)
    assert export.dropped_links == 1


def test_world_row_travels_with_the_selection():
    src = _scene(_deep_scene())
    export = build_selection(src, {5})
    world = export.nodes[0]
    assert world.type == NODE_TYPE_WORLD and export.world_row
    assert (world.color_r, world.color_g, world.color_b) == (10, 20, 30)
    assert _scene(export.nodes).world_node() is not None


def test_world_row_can_be_declined():
    src = _scene(_deep_scene())
    export = build_selection(src, {5}, ExportOptions(include_world_row=False))
    assert not export.world_row
    assert all(n.type != NODE_TYPE_WORLD for n in export.nodes)


def test_selecting_the_world_row_does_not_export_it_as_a_glyph():
    """The World row is reachable by clicking its table row. It must arrive
    through the include_world_row path (once, at the head of the file), not
    as a selected member."""
    src = _scene(_deep_scene())
    export = build_selection(src, {1, 5})
    assert [n.id for n in export.nodes].count(1) == 1
    assert export.nodes[0].id == 1


def test_empty_selection_produces_nothing():
    src = _scene(_deep_scene())
    assert build_selection(src, set()).count == 0
    assert build_selection(src, {1}).count == 0      # World row alone isn't a selection


def test_branch_levels_are_restated():
    src = _scene(_deep_scene())
    export = build_selection(src, {4})
    levels = {n.id: n.branch_level for n in export.nodes}
    assert levels[4] == 0     # was 2, now a root
    assert levels[5] == 1     # was 3
    assert levels[8] == 1


def test_ids_are_preserved():
    """Ids keep their source values, so extras['record_id'] — the tag file's
    join key — stays valid without rewriting the tag rows."""
    src = _scene(_deep_scene())
    export = build_selection(src, {3})
    for n in export.nodes:
        assert n.extras.get('record_id') == n.id


# --- the other two detach policies -------------------------------------------

def test_ancestors_mode_brings_the_chain_and_needs_no_bake():
    src = _scene(_deep_scene())
    export = build_selection(src, {5}, ExportOptions(detach=DETACH_ANCESTORS))
    assert set(_glyph_ids(export)) == {2, 3, 4, 5}
    assert export.ancestors_added == 3
    assert export.detached_ids == []

    ids = _glyph_ids(export)
    before = _matrices(src, ids)
    after = _matrices(_scene(export.nodes), ids)
    for i in ids:
        assert np.allclose(before[i], after[i], atol=1e-12)
    # untouched, not baked: the ancestors' own authored fields are intact
    assert next(n for n in export.nodes if n.id == 3).rotation_mode == \
        ROTATION_MODE_HEADING_TILT_ROLL


def test_ancestors_mode_on_a_root_selection_adds_nothing():
    src = _scene(_deep_scene())
    export = build_selection(src, {2}, ExportOptions(detach=DETACH_ANCESTORS))
    assert export.ancestors_added == 0
    assert export.detached_ids == []


# --- World Grid children ------------------------------------------------------

def _grid_scene(globe: bool):
    """A World Grid with one child holding a small subtree. The child's
    translate is longitude/latitude within the grid's window — the case where
    a naive save is most obviously wrong."""
    grid = _node(10, type=NODE_TYPE_GRID, geometry=3 if globe else 1,
                 translate_x=5.0, translate_y=-3.0, translate_z=0.0,
                 rotate_z=12.0, scale_x=1.0, scale_y=1.0, scale_z=1.0)
    grid.set_grid_extents(-120.0, -60.0, 20.0, 50.0)
    child = _node(11, parent_id=10, branch_level=1, topo=TOPO_SPHERE,
                  translate_x=-117.2, translate_y=32.7, translate_z=4.0,
                  scale_x=0.7, scale_y=0.7, scale_z=0.7)
    leaf = _node(12, parent_id=11, branch_level=2,
                 translate_x=45.0, translate_y=20.0, translate_z=1.0)
    for n in (grid, child, leaf):
        n.extras.setdefault('record_id', n.id)
    return [grid, child, leaf]


@pytest.mark.parametrize("globe", [False, True])
def test_grid_child_detaches_without_moving(globe):
    src = _scene(_grid_scene(globe))
    export = build_selection(src, {11})
    assert set(_glyph_ids(export)) == {11, 12}
    ids = [11, 12]
    before = _matrices(src, ids)
    after = _matrices(_scene(export.nodes), ids)
    for i in ids:
        assert np.allclose(before[i], after[i], atol=1e-9), f"node {i} moved"


def test_grid_comes_along_in_ancestors_mode():
    src = _scene(_grid_scene(globe=False))
    export = build_selection(src, {11}, ExportOptions(detach=DETACH_ANCESTORS))
    assert set(_glyph_ids(export)) == {10, 11, 12}
    ids = [10, 11, 12]
    before = _matrices(src, ids)
    after = _matrices(_scene(export.nodes), ids)
    for i in ids:
        assert np.allclose(before[i], after[i], atol=1e-12)


# --- channel companions ------------------------------------------------------

def _write_channel_files(tmp_path):
    """A 4-channel scene's companions: channel N drives track N."""
    map_path = tmp_path / "src_gv_ch-map.csv"
    tracks_path = tmp_path / "src_gv_ch-tracks.csv"
    map_path.write_text(
        "id,channel_id,track_id,attribute,track_table_id,ch_map_table_id,record_id\n"
        "0,1,1,translate_z,0,0,0\n"
        "1,2,2,translate_z,0,0,0\n"
        "2,3,3,scale_x,0,0,0\n"
        "3,4,4,color_index,0,0,0\n",
        encoding='utf-8')
    tracks_path.write_text(
        "cyclecount,ch1,ch2,ch3,ch4\n"
        "0,0.1,0.2,0.3,0.4\n"
        "1,1.1,1.2,1.3,1.4\n",
        encoding='utf-8')
    return map_path, tracks_path


def test_channel_subset_keeps_only_the_bound_channels(tmp_path):
    src_map, src_tracks = _write_channel_files(tmp_path)
    out_map = tmp_path / "frag_gv_ch-map.csv"
    out_tracks = tmp_path / "frag_gv_ch-tracks.csv"

    channels, tracks = export_channel_subset(
        src_map, src_tracks, {2, 3}, out_map, out_tracks)
    assert (channels, tracks) == (2, 2)

    kept = load_ch_map(out_map)
    assert set(kept) == {2, 3}
    _data, id_to_col = load_ch_tracks(out_tracks)
    assert set(id_to_col) == {2, 3}
    # scene-level columns are not track columns and must survive
    assert out_tracks.read_text(encoding='utf-8').splitlines()[0].startswith("cyclecount")


def test_channel_subset_writes_nothing_when_no_channel_matches(tmp_path):
    """An empty ch-map would still be picked up by find_channel_files and
    would shadow a real one sharing the folder."""
    src_map, src_tracks = _write_channel_files(tmp_path)
    out_map = tmp_path / "frag_gv_ch-map.csv"
    out_tracks = tmp_path / "frag_gv_ch-tracks.csv"
    assert export_channel_subset(src_map, src_tracks, {99}, out_map, out_tracks) == (0, 0)
    assert not out_map.exists() and not out_tracks.exists()


def test_channel_ids_are_read_off_the_exported_nodes():
    nodes = _deep_scene()
    next(n for n in nodes if n.id == 5).extras['ch_input_id'] = 7
    next(n for n in nodes if n.id == 6).extras['ch_input_id'] = 9
    export = build_selection(_scene(nodes), {4})     # takes 5, not 6
    assert channel_ids_for_nodes(export.nodes) == {7}


def test_channel_bindings_survive_the_export():
    """Unlike scene merge — which clears them, because it rebases ids into a
    host scene's ch-map space — an export preserves ids, so the binding still
    means what it did."""
    nodes = _deep_scene()
    next(n for n in nodes if n.id == 5).extras['ch_input_id'] = 7
    export = build_selection(_scene(nodes), {5})
    assert next(n for n in export.nodes if n.id == 5).extras['ch_input_id'] == 7


def test_detached_grid_keeps_its_footprint_and_its_children():
    """A grid can be selected on its own (G key). Its rendered rectangle is
    extents x raw scale, so the bake has to leave both the footprint and the
    child placement alone."""
    nodes = _grid_scene(globe=False)
    root = _node(20, topo=TOPO_NONE, translate_x=40.0, rotate_z=25.0)
    nodes[0].parent_id = 20
    nodes[0].branch_level = 1
    src = _scene([root] + nodes)
    export = build_selection(src, {10})
    ids = [10, 11, 12]
    before = _matrices(src, ids)
    after = _matrices(_scene(export.nodes), ids)
    for i in ids:
        assert np.allclose(before[i], after[i], atol=1e-9), f"node {i} moved"
