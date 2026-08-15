"""
Glyph Composer link levels: a LevelSpec can ask for a companion Link
(type=7) edge from each of its nodes back to its parent, rendered as any
geometry stretched between the two (the 2026-08-15 link-geometries feature).
Separating a level from its parent (dist_tz) and letting the link span the
gap is what turns a composed glyph from touching shells into a jointed,
branching structure — pearls on a string, limbs on a tree.

Contract pinned here:

  * link_geo=None (the default, and what every pre-existing template loads
    as) emits exactly what generate_nodes always emitted — no type-7 rows;
  * a linked level emits child-then-edge pairs with sequential ids, the edge's
    parent_id naming the A-end and extras['child_id'] the B-end, so the
    Composer's insert (which just offsets start_id) and Draw Mode stamping
    stay coherent with no remapping;
  * links inherit their child's gradient-resolved color unless the level
    carries its own link colors;
  * recipe_node_count stays exact, JSON round-trips, and
    snapshot_level_rotations never lets an edge (rotation always 0) stand in
    for its level.

Qt is needed for the dialog half but a GL context is not — same arrangement
as tests/test_glyph_composer_topo_scale.py, so everything runs headless.
"""
import json
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import numpy as np

from glyphviz_core import glyph_recipe as gr
from glyphviz_core.geometry_data import (
    GEO_CONE, GEO_CYLINDER, GEO_LINE, GEO_SPHERE,
)
from glyphviz_core.link_geometry import link_glyph_matrix, local_z_span
from glyphviz_core.node import NODE_TYPE_LINK
from glyphviz_core.scene import Scene
from glyphviz_core.topology import TOPO_NONE, TOPO_SPHERE


def _linked_recipe(link_geo=GEO_CYLINDER, **level1_kwargs):
    """One trunk, three children pushed off the trunk's surface, linked back
    to it — the smallest recipe where a link has a gap to span."""
    level0 = gr.LevelSpec(count=1, geometry=GEO_SPHERE, topo=TOPO_SPHERE,
                          dist_mode=gr.DIST_LINEAR)
    level1 = gr.LevelSpec(count=3, geometry=GEO_SPHERE, topo=TOPO_NONE,
                          dist_mode=gr.DIST_ANGULAR, dist_tz=2.0,
                          scale_x=0.4, scale_y=0.4, scale_z=0.4,
                          color_start=(200, 60, 40, 255),
                          color_end=(40, 60, 200, 255),
                          link_geo=link_geo, link_ratio=0.25,
                          **level1_kwargs)
    return gr.GlyphRecipe(name="Linked", levels=[level0, level1])


# --- emission ---------------------------------------------------------------

def test_no_link_fields_means_no_links():
    """A recipe that never mentions links produces zero type-7 rows — the
    entire pre-existing template population must generate unchanged."""
    nodes = gr.generate_nodes(gr.default_recipe(), start_id=1)
    assert all(n.type != NODE_TYPE_LINK for n in nodes)


def test_linked_level_emits_child_then_edge_pairs():
    nodes = gr.generate_nodes(_linked_recipe(), start_id=1)
    assert len(nodes) == 1 + 3 * 2
    assert [n.id for n in nodes] == list(range(1, 8))

    root = nodes[0]
    links = [n for n in nodes if n.type == NODE_TYPE_LINK]
    assert len(links) == 3
    for link in links:
        # A-end is the parent, B-end is the node emitted immediately before.
        b_end = nodes[link.id - 2]
        assert link.parent_id == root.id
        assert link.extras['child_id'] == b_end.id
        assert b_end.type == 5
        assert link.geometry == GEO_CYLINDER
        assert link.ratio == 0.25
        assert link.branch_level == b_end.branch_level
        # A link IS its edge — its own pose must stay inert defaults.
        assert (link.translate_x, link.translate_y, link.translate_z) == (0, 0, 0)
        assert (link.scale_x, link.scale_y, link.scale_z) == (1, 1, 1)


def test_link_geo_is_ignored_on_the_root_level():
    """A root's parent is whatever the glyph lands under (a grid, nothing) —
    that edge is not part of the glyph and must never be emitted."""
    r = _linked_recipe()
    r.levels[0].link_geo = GEO_CYLINDER
    nodes = gr.generate_nodes(r, start_id=1)
    links = [n for n in nodes if n.type == NODE_TYPE_LINK]
    assert len(links) == 3                      # level 1's only
    assert all(ln.parent_id == nodes[0].id for ln in links)


def test_ids_survive_composer_style_offsets():
    """The Composer inserts with start_id = max scene id + 1 and Draw Mode
    stamps under a grid — both just offset the family, so a link's child_id
    must be an absolute id inside it."""
    nodes = gr.generate_nodes(_linked_recipe(), start_id=500, parent_id=42,
                              base_branch_level=3)
    by_id = {n.id: n for n in nodes}
    links = [n for n in nodes if n.type == NODE_TYPE_LINK]
    assert len(links) == 3
    for link in links:
        assert link.extras['child_id'] in by_id
        assert by_id[link.extras['child_id']].type == 5
        assert link.parent_id in by_id          # A-end is the in-family trunk
    assert nodes[0].parent_id == 42
    assert all(n.branch_level >= 4 for n in nodes[1:])


def test_recipe_node_count_stays_exact_with_links():
    for recipe in (
        gr.default_recipe(),
        _linked_recipe(),
        gr.GlyphRecipe(levels=[
            gr.LevelSpec(count=2, dist_mode=gr.DIST_LINEAR),
            gr.LevelSpec(count=3, link_geo=GEO_CYLINDER),
            gr.LevelSpec(count=2),
            gr.LevelSpec(count=2, link_geo=GEO_LINE),
        ]),
    ):
        assert gr.recipe_node_count(recipe) == \
            len(gr.generate_nodes(recipe, start_id=1))


# --- color ------------------------------------------------------------------

def test_links_inherit_their_childs_gradient_color():
    nodes = gr.generate_nodes(_linked_recipe(), start_id=1)
    for link in (n for n in nodes if n.type == NODE_TYPE_LINK):
        b_end = nodes[link.id - 2]
        assert (link.color_r, link.color_g, link.color_b, link.color_a) == \
            (b_end.color_r, b_end.color_g, b_end.color_b, b_end.color_a)
    # The inherited colors themselves span the sibling gradient.
    links = [n for n in nodes if n.type == NODE_TYPE_LINK]
    assert links[0].color_r != links[-1].color_r


def test_custom_link_colors_gradient_across_siblings():
    r = _linked_recipe(link_color_start=(100, 80, 60, 255),
                       link_color_end=(0, 80, 200, 255))
    links = [n for n in gr.generate_nodes(r, start_id=1)
             if n.type == NODE_TYPE_LINK]
    assert (links[0].color_r, links[0].color_b) == (100, 60)
    assert (links[-1].color_r, links[-1].color_b) == (0, 200)


# --- serialization ----------------------------------------------------------

def test_json_round_trip_preserves_link_fields():
    r = _linked_recipe(link_color_start=(1, 2, 3, 4), link_color_end=(5, 6, 7, 8))
    d = json.loads(json.dumps(gr.recipe_to_dict(r)))     # through real JSON
    back = gr.recipe_from_dict(d)
    spec = back.levels[1]
    assert spec.link_geo == GEO_CYLINDER
    assert spec.link_ratio == 0.25
    assert spec.link_color_start == (1, 2, 3, 4)
    assert spec.link_color_end == (5, 6, 7, 8)
    assert back.levels[0].link_geo is None


def test_pre_link_template_loads_linkless():
    """A template written before links existed carries none of the keys —
    it must load exactly as it always did."""
    d = gr.recipe_to_dict(gr.default_recipe())
    for level in d["levels"]:
        for key in ("link_geo", "link_ratio", "link_color_start",
                    "link_color_end"):
            level.pop(key, None)
    back = gr.recipe_from_dict(d)
    assert all(spec.link_geo is None for spec in back.levels)
    assert all(n.type != NODE_TYPE_LINK
               for n in gr.generate_nodes(back, start_id=1))


# --- interplay with the rest of the pipeline --------------------------------

def test_snapshot_level_rotations_never_samples_an_edge():
    r = _linked_recipe()
    r.levels[1].rotate_x = 45.0
    nodes = gr.generate_nodes(r, start_id=1)
    # Force the pathological order: an edge encountered before any of its
    # level's real nodes.
    reordered = [nodes[0]] + [n for n in nodes[1:] if n.type == NODE_TYPE_LINK] \
        + [n for n in nodes[1:] if n.type != NODE_TYPE_LINK]
    snap = gr.snapshot_level_rotations(r, reordered)
    assert snap.levels[1].rotate_x == 45.0     # not the edge's inert 0.0


def test_generated_links_span_a_real_gap_through_the_real_engine():
    """End to end through the actual transform engine: the generated family,
    resolved by Scene, hands link_glyph_matrix two distinct endpoints, and the
    stretched glyph's local z-span lands exactly on them — i.e. the limb
    really does bridge parent to child."""
    nodes = gr.generate_nodes(_linked_recipe(link_geo=GEO_CONE), start_id=1)
    scene = Scene(nodes, 1.0)
    scene._ensure()
    links = [n for n in nodes if n.type == NODE_TYPE_LINK]
    assert links
    for link in links:
        a = np.asarray(scene.world_pos(link.parent_id))
        b = np.asarray(scene.world_pos(int(link.extras['child_id'])))
        assert np.linalg.norm(b - a) > 1.0     # dist_tz opened a real gap
        M = link_glyph_matrix(a, b, link.ratio, link.geometry)
        assert M is not None
        z_min, z_max = local_z_span(link.geometry)
        for local_z, end in ((z_min, a), (z_max, b)):
            p = M @ np.array([0.0, 0.0, local_z, 1.0])
            assert np.allclose(p[:3], end, atol=1e-9)


# --- dialog wiring (headless Qt) --------------------------------------------

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtWidgets import QApplication                # noqa: E402

from glyphviz_gl import main_window as mw                 # noqa: E402
from glyphviz_gl.glyph_composer_dialog import (           # noqa: E402
    GlyphComposerDialog,
)


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication([])
        except Exception as exc:                          # pragma: no cover
            pytest.skip(f'Qt unavailable: {exc}')
    return app


@pytest.fixture
def dlg(qapp):
    win = mw.MainWindow()
    d = GlyphComposerDialog(win)
    yield d
    d.close()
    win.close()


def test_root_level_offers_no_link_group(dlg):
    dlg._level_list.setCurrentRow(0)
    assert dlg._w_link_box is None


def test_checking_the_box_writes_a_cylinder_link(dlg):
    dlg._level_list.setCurrentRow(1)
    assert dlg._w_link_box is not None
    assert not dlg._w_link_box.isChecked()     # default recipe has no links

    dlg._w_link_box.setChecked(True)
    dlg._w_link_ratio.setValue(0.4)
    dlg._save_params()
    spec = dlg._recipe.levels[1]
    assert spec.link_geo == GEO_CYLINDER       # the offered default
    assert spec.link_ratio == 0.4
    assert spec.link_color_start is None       # inherit is the default
    assert "⌁" in dlg._level_label(1)

    dlg._w_link_box.setChecked(False)
    dlg._save_params()
    assert dlg._recipe.levels[1].link_geo is None


def test_form_round_trips_a_loaded_link_level(dlg):
    dlg._recipe = _linked_recipe(link_color_start=(10, 20, 30, 255),
                                 link_color_end=None)
    dlg._current_level = None
    dlg._refresh_level_list()
    dlg._level_list.setCurrentRow(1)

    assert dlg._w_link_box.isChecked()
    assert dlg._w_link_geo.currentData() == GEO_CYLINDER
    assert dlg._w_link_ratio.value() == pytest.approx(0.25)
    assert not dlg._w_link_inherit.isChecked()

    dlg._save_params()                          # untouched form must not drift
    spec = dlg._recipe.levels[1]
    assert spec.link_geo == GEO_CYLINDER
    assert spec.link_color_start == (10, 20, 30, 255)
    assert spec.link_color_end is None


def test_insert_into_scene_lands_coherent_links(dlg):
    """The wow path end to end: compose a linked glyph, insert it, and the
    main window's scene holds type-7 edges whose two ends both resolve."""
    dlg._recipe = _linked_recipe()
    dlg._current_level = None
    dlg._refresh_level_list()
    dlg._level_list.setCurrentRow(1)
    before = len(dlg._main_win.nodes)

    dlg._insert_into_scene()

    nodes = dlg._main_win.nodes
    assert len(nodes) == before + 7
    by_id = {n.id: n for n in nodes}
    links = [n for n in nodes if n.type == NODE_TYPE_LINK]
    assert len(links) == 3
    for link in links:
        assert link.parent_id in by_id
        assert int(link.extras['child_id']) in by_id
