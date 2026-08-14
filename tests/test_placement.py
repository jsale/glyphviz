"""
ANTz-style wrapped placement for newly created objects.

What matters here is the wrap, and that the two entry points agree: children
are placed by ordinal (`wrapped_grid_offset`) and roots by stepping on from
the previous one (`step_from`), so a run of Shift+N and a run of N have to
walk the same lattice or the two gestures would drift apart.

GUI wiring is pinned in tests/test_placement_gui.py.
"""
import math

import pytest

from glyphviz_core.placement import (
    DEFAULT_PLACEMENT_STEP, PLACEMENT_WRAP, columns_per_row, step_from,
    wrapped_grid_offset,
)


# --- columns per row -------------------------------------------------------

@pytest.mark.parametrize("step, expected", [
    (15.0, 24),      # ANTz's own: 24 x 15 deg = one lap
    (5.0, 72),       # GlyphViz default
    (10.0, 36),
    (360.0, 1),      # a step of exactly one lap: one per row
    (400.0, 1),      # over a lap: still one per row, never zero
    (7.0, 52),       # 51 x 7 = 357 still fits; 52 x 7 = 364 does not
])
def test_columns_per_row(step, expected):
    assert columns_per_row(step) == expected


def test_every_column_stays_below_a_full_lap():
    """The invariant the column count exists to guarantee: no object in a row
    reaches 360 (which on a circular topology IS the first object's slot)."""
    for step in (1.0, 3.0, 5.0, 7.0, 15.0, 45.0, 137.0):
        cols = columns_per_row(step)
        assert (cols - 1) * step < PLACEMENT_WRAP
        assert cols * step >= PLACEMENT_WRAP


def test_zero_step_never_divides_by_zero():
    assert columns_per_row(0.0) == 1


# --- placement by ordinal (children) ---------------------------------------

def test_first_child_sits_at_the_parent_origin():
    assert wrapped_grid_offset(0, DEFAULT_PLACEMENT_STEP) == (0.0, 0.0)


def test_children_step_along_x_within_a_row():
    step = DEFAULT_PLACEMENT_STEP
    assert wrapped_grid_offset(1, step) == (5.0, 0.0)
    assert wrapped_grid_offset(3, step) == (15.0, 0.0)
    assert wrapped_grid_offset(71, step) == (355.0, 0.0)


def test_child_wraps_to_a_new_row_at_a_full_lap():
    """The whole point: the 73rd child at step 5 would land on top of the
    first, so it starts a new row instead."""
    step = DEFAULT_PLACEMENT_STEP
    assert wrapped_grid_offset(72, step) == (0.0, 5.0)
    assert wrapped_grid_offset(73, step) == (5.0, 5.0)
    assert wrapped_grid_offset(144, step) == (0.0, 10.0)


def test_antz_step_reproduces_antz_rows():
    """ANTz stepped 15 deg and bumped y every 24 children (npnode.c:363-370)."""
    assert wrapped_grid_offset(23, 15.0) == (345.0, 0.0)
    assert wrapped_grid_offset(24, 15.0) == (0.0, 15.0)
    assert wrapped_grid_offset(47, 15.0) == (345.0, 15.0)
    assert wrapped_grid_offset(48, 15.0) == (0.0, 30.0)


def test_no_two_children_share_a_slot():
    """Across several laps and several steps, every ordinal gets its own
    (x, y) — the property 'they don't overlap' actually reduces to."""
    for step in (1.0, 5.0, 7.0, 15.0):
        seen = {wrapped_grid_offset(i, step) for i in range(500)}
        assert len(seen) == 500


def test_y_keeps_climbing_rather_than_wrapping():
    """Deliberate divergence from ANTz, which folded y back into -180..180
    (npnode.c:378-384) and so eventually reused slots. A long run of presses
    grows a taller grid instead."""
    x, y = wrapped_grid_offset(72 * 60, DEFAULT_PLACEMENT_STEP)
    assert (x, y) == (0.0, 300.0)


def test_zero_step_stacks_at_the_origin():
    assert wrapped_grid_offset(9, 0.0) == (0.0, 0.0)


def test_negative_step_is_read_as_a_distance():
    assert wrapped_grid_offset(3, -5.0) == wrapped_grid_offset(3, 5.0)


# --- placement relative to the previous object (roots) ---------------------

def test_root_steps_on_from_the_previous_one():
    assert step_from(0.0, 0.0, 5.0) == (5.0, 0.0)
    assert step_from(40.0, 0.0, 5.0) == (45.0, 0.0)


def test_root_wraps_to_a_new_row_too():
    assert step_from(355.0, 0.0, 5.0) == (0.0, 5.0)
    assert step_from(345.0, 15.0, 15.0) == (0.0, 30.0)


def test_root_stepping_from_a_dragged_object_keeps_the_offset():
    """Roots key off wherever the previous object actually IS, so dragging one
    somewhere carries the next creation along with it."""
    assert step_from(100.0, 60.0, 5.0) == (105.0, 60.0)


def test_zero_step_leaves_a_root_where_the_last_one_is():
    assert step_from(20.0, 5.0, 0.0) == (20.0, 5.0)


# --- the two entry points describe ONE lattice -----------------------------

def test_stepping_repeatedly_reproduces_the_ordinal_lattice():
    for step in (1.0, 5.0, 7.0, 15.0, 45.0):
        pos = (0.0, 0.0)
        for i in range(1, 200):
            pos = step_from(pos[0], pos[1], step)
            expected = wrapped_grid_offset(i, step)
            assert math.isclose(pos[0], expected[0], abs_tol=1e-9)
            assert math.isclose(pos[1], expected[1], abs_tol=1e-9)
