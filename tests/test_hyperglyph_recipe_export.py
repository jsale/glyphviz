"""
Exporting a Hyperglyph Generator design as a Glyph Composer recipe.

Two things are pinned here. First, that the export carries the design across
intact — the same tree comes back out of the .json. Second, and the reason the
feature needed thinking about at all, that a glyph left SPINNING in the preview
can be saved as the pose it had reached: rate animation integrates rotate_x/y/z
with no wraparound, so the captured numbers have to be folded back into the
range the Composer's rotation spin boxes accept or the state would be silently
clamped away on load.

Pure logic — no Qt, no GL. The dialog wiring is pinned in
tests/test_hyperglyph_dialog.py.
"""
import json
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from glyphviz_core import glyph_recipe as gr
from glyphviz_core.glyph_recipe import (
    COMPOSER_EDIT_NODE_WARN, GlyphRecipe, LevelSpec, generate_nodes,
    load_recipe, recipe_node_count, save_recipe, snapshot_level_rotations,
)


def _hyperglyph_generator():
    lab = Path(__file__).resolve().parent.parent / 'hyperglyph_lab'
    sys.path.insert(0, str(lab))
    try:
        import hyperglyph_generator as hg
    finally:
        sys.path.remove(str(lab))
    return hg


def _design(seed=7, branch_levels=4, max_nodes=500):
    """A real Generator design, the way the dialog builds one."""
    hg = _hyperglyph_generator()
    recipe, _ = hg.random_recipe(branch_levels, max_nodes, random.Random(seed),
                                 name=f'Hyperglyph_{seed}')
    return recipe


def _spun(recipe, seed=7, cycles=6000.0):
    """A generated tree wound forward the way the preview viewport winds one:
    idle motion assigns per-node rotate_rate_*, then _apply_rate_animation
    accumulates rate x cycles into rotate_* with no wraparound."""
    hg = _hyperglyph_generator()
    nodes = generate_nodes(recipe, start_id=1)
    hg.assign_color_index(nodes)
    hg.apply_idle_motion(nodes, random.Random(seed))
    for n in nodes:
        n.rotate_x += n.rotate_rate_x * cycles
        n.rotate_y += n.rotate_rate_y * cycles
        n.rotate_z += n.rotate_rate_z * cycles
    return nodes


# --- node counting ------------------------------------------------------------

def test_recipe_node_count_matches_generation():
    """The warning threshold is only meaningful if the count it tests is the
    real one — measured without paying for the tree."""
    for seed in range(6):
        recipe = _design(seed=seed)
        assert recipe_node_count(recipe) == len(generate_nodes(recipe))


def test_recipe_node_count_handles_zero_count_levels():
    r = GlyphRecipe(levels=[LevelSpec(count=1), LevelSpec(count=0)])
    # _distribute floors count at 1, so the count must too rather than
    # collapsing the whole subtree to zero.
    assert recipe_node_count(r) == len(generate_nodes(r))


def test_default_dialog_budget_stays_under_the_warning():
    """The dialog's default Max Nodes is 500 — a routine design must not trip
    the large-hyperglyph prompt, or the prompt becomes noise to click through."""
    for seed in range(8):
        assert recipe_node_count(_design(seed=seed, max_nodes=500)) <= COMPOSER_EDIT_NODE_WARN


# --- capture off: the design as authored --------------------------------------

def test_static_recipe_round_trips_unchanged(tmp_path):
    """Idle Motion off means nothing moved, so a capture must be a no-op —
    including NOT folding authored negative rotations into 0..360, which would
    churn every file for no reason."""
    recipe = _design()
    assert any(lvl.rotate_x < 0 or lvl.rotate_y < 0 or lvl.rotate_z < 0
               for lvl in recipe.levels), 'fixture should hold negative angles'

    nodes = generate_nodes(recipe, start_id=1)
    snapped = snapshot_level_rotations(recipe, nodes)
    assert gr.recipe_to_dict(snapped) == gr.recipe_to_dict(recipe)

    path = tmp_path / 'static.json'
    save_recipe(snapped, str(path))
    assert gr.recipe_to_dict(load_recipe(str(path))) == gr.recipe_to_dict(recipe)


def test_capture_leaves_everything_but_rotation_alone():
    """Only rotation drifts, so only rotation may be rewritten — a capture that
    disturbed counts, topo_scale_auto or colors would quietly redesign the
    glyph on its way to disk."""
    recipe = _design()
    snapped = snapshot_level_rotations(recipe, _spun(recipe))

    assert len(snapped.levels) == len(recipe.levels)
    assert snapped.name == recipe.name
    for before, after in zip(recipe.levels, snapped.levels):
        for f in ('count', 'geometry', 'topo', 'ratio', 'topo_scale',
                  'topo_scale_auto', 'dist_mode', 'dist_step', 'dist_axis',
                  'dist_tilt', 'dist_tz', 'scale_x', 'scale_y', 'scale_z',
                  'color_start', 'color_end'):
            assert getattr(after, f) == getattr(before, f), f


def test_capture_does_not_mutate_the_live_recipe():
    """The dialog keeps regenerating and inserting from self._recipe after a
    save, so the capture has to hand back a copy."""
    recipe = _design()
    before = gr.recipe_to_dict(recipe)
    snapshot_level_rotations(recipe, _spun(recipe))
    assert gr.recipe_to_dict(recipe) == before


# --- capture on: the pose on screen -------------------------------------------

def test_trunk_is_captured_exactly():
    """Level 0 holds exactly one node, so its pose is representable with no
    approximation at all — that node's live orientation, modulo a full turn."""
    recipe = _design()
    nodes = _spun(recipe)
    snapped = snapshot_level_rotations(recipe, nodes)
    trunk = nodes[0]
    for axis in 'xyz':
        live = getattr(trunk, f'rotate_{axis}')
        saved = getattr(snapped.levels[0], f'rotate_{axis}')
        assert (live - saved) % 360.0 == pytest.approx(0.0, abs=1e-9) or \
               (live - saved) % 360.0 == pytest.approx(360.0, abs=1e-9)


def test_deeper_levels_take_their_first_node():
    """A recipe has one rotation per level while idle motion gives every node
    its own axis and speed, so the capture is a representative, not an average
    — pinned to the first node at each level."""
    recipe = _design()
    nodes = _spun(recipe)
    snapped = snapshot_level_rotations(recipe, nodes)

    seen = set()
    for n in nodes:
        if n.branch_level in seen:
            continue
        seen.add(n.branch_level)
        lvl = snapped.levels[n.branch_level]
        for axis in 'xyz':
            live = getattr(n, f'rotate_{axis}')
            saved = getattr(lvl, f'rotate_{axis}')
            assert (live - saved) % 360.0 < 1e-9 or 360.0 - (live - saved) % 360.0 < 1e-9
    assert len(seen) == len(recipe.levels)


def test_capture_actually_changed_the_pose():
    """Guard against a capture that silently does nothing: a spun glyph must
    come back with different numbers from the authored ones."""
    recipe = _design()
    snapped = snapshot_level_rotations(recipe, _spun(recipe))
    changed = sum(
        1 for b, a in zip(recipe.levels, snapped.levels)
        if (b.rotate_x, b.rotate_y, b.rotate_z) != (a.rotate_x, a.rotate_y, a.rotate_z)
    )
    assert changed >= len(recipe.levels) - 1   # the trunk carries no rate


def test_captured_angles_fit_the_composer_spin_boxes():
    """THE point of the fold. glyph_composer_dialog builds its rotation spin
    boxes with setRange(-360, 360); a glyph left spinning reaches thousands of
    degrees, and an out-of-range value is clamped to 360 the moment the level
    is selected — losing exactly the state we set out to save."""
    recipe = _design()
    nodes = _spun(recipe, cycles=200000.0)
    assert max(abs(n.rotate_x) for n in nodes) > 360.0, 'fixture should overflow'

    snapped = snapshot_level_rotations(recipe, nodes)
    for lvl in snapped.levels:
        for axis in 'xyz':
            assert -360.0 <= getattr(lvl, f'rotate_{axis}') <= 360.0


def test_capture_survives_the_json_round_trip(tmp_path):
    """End to end: spin, save, and reopen the file the Composer would open."""
    recipe = _design()
    snapped = snapshot_level_rotations(recipe, _spun(recipe))
    path = tmp_path / 'posed.json'
    save_recipe(snapped, str(path))

    assert json.loads(path.read_text(encoding='utf-8'))['name'] == recipe.name
    assert gr.recipe_to_dict(load_recipe(str(path))) == gr.recipe_to_dict(snapped)


def test_capture_handles_an_inserted_branch_level_offset():
    """Levels are identified by branch_level RELATIVE to the first node, so a
    tree generated under a selected parent (base_branch_level > 0) maps onto
    the same recipe levels rather than falling off the end."""
    recipe = _design()
    nodes = generate_nodes(recipe, start_id=50, parent_id=9, base_branch_level=3)
    for n in nodes:
        n.rotate_y += 1000.0
    snapped = snapshot_level_rotations(recipe, nodes)
    assert all(lvl.rotate_y != before.rotate_y
               for lvl, before in zip(snapped.levels, recipe.levels))


def test_capture_tolerates_an_empty_node_list():
    recipe = _design()
    assert gr.recipe_to_dict(snapshot_level_rotations(recipe, [])) \
        == gr.recipe_to_dict(recipe)
