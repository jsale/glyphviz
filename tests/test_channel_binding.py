"""
Channel binding helpers: reading, writing and describing a node's ch_input_id.

The GUI half — the Properties panel's "Channel In" row, and the rebind that
makes a live animation pick the change up — is in
tests/test_channel_binding_gui.py. This file is Qt-free.
"""
import numpy as np
import pytest

from glyphviz_core.channel_engine import (
    ChannelEngine, channel_attrs, channel_id_of, channel_ids_for_nodes,
    set_channel_id,
)
from glyphviz_core.node import Node


def _node(node_id=1, **overrides):
    base = dict(
        id=node_id, type=5, parent_id=0, branch_level=0,
        translate_x=0.0, translate_y=0.0, translate_z=0.0,
        rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=200, color_g=200, color_b=200, color_a=255,
        geometry=3, hide=0, topo=0,
    )
    base.update(overrides)
    return Node(**base)


# --- set_channel_id ---------------------------------------------------------

def test_sets_the_native_key_on_a_node_that_has_none():
    node = _node()
    set_channel_id(node, 4)
    assert node.extras == {'ch_input_id': 4}
    assert channel_id_of(node) == 4


def test_zero_means_unbound_and_is_still_written():
    """0 has to be written, not deleted: an explicit 0 is what the 94-column
    save format carries, and channel_id_of already reads a missing key as 0."""
    node = _node()
    set_channel_id(node, 7)
    set_channel_id(node, 0)
    assert node.extras['ch_input_id'] == 0
    assert channel_id_of(node) == 0


@pytest.mark.parametrize("key", ['ch_input_id', 'np_ch_in_id', 'ch_input_id '])
def test_writes_back_through_the_spelling_the_file_used(key):
    """channel_id_of reads the FIRST key present, so adding a second spelling
    would leave two columns that disagree — and would grow a GaiaViz file a
    column it never had."""
    node = _node()
    node.extras[key] = 2
    set_channel_id(node, 9)
    assert node.extras == {key: 9}
    assert channel_id_of(node) == 9


def test_value_is_stored_as_an_int():
    node = _node()
    set_channel_id(node, 3.0)
    assert node.extras['ch_input_id'] == 3
    assert isinstance(node.extras['ch_input_id'], int)


def test_round_trips_through_channel_ids_for_nodes():
    nodes = [_node(1), _node(2), _node(3)]
    set_channel_id(nodes[0], 5)
    set_channel_id(nodes[1], 5)
    set_channel_id(nodes[2], 0)
    assert channel_ids_for_nodes(nodes) == {5}


# --- channel_attrs ----------------------------------------------------------

def test_attrs_are_ch_map_order_deduped():
    ch_map = {3: [(1, 'translate_z'), (2, 'color_r'), (5, 'translate_z')]}
    assert channel_attrs(ch_map, 3) == ['translate_z', 'color_r']


def test_attrs_filters_to_what_the_engine_can_actually_bind():
    """Same filter load() applies, so the hint promises only what will happen."""
    ch_map = {3: [(1, 'not_a_field'), (2, 'scale_x')]}
    assert channel_attrs(ch_map, 3) == ['scale_x']


def test_attrs_of_an_absent_channel_is_empty():
    assert channel_attrs({3: [(1, 'scale_x')]}, 99) == []


# --- rebinding through the engine ------------------------------------------

def _tracks():
    # two tracks x three frames
    return np.array([[0.0, 10.0], [5.0, 20.0], [9.0, 30.0]]), {1: 0, 2: 1}


def test_engine_binds_a_node_the_moment_its_id_is_set():
    """The whole point of the feature: nothing about the loaded channel data
    changes, only the node's id, and a reload of the engine picks it up."""
    ch_map = {3: [(1, 'translate_z')]}
    tracks, id_to_col = _tracks()
    node = _node(translate_z=-1.0)
    engine = ChannelEngine()

    engine.load(ch_map, tracks, id_to_col, [node])
    assert not engine.has_bindings

    set_channel_id(node, 3)
    engine.load(ch_map, tracks, id_to_col, [node])
    assert engine.bound_node_ids == {1}
    engine.apply_frame(2)
    assert node.translate_z == 9.0


def test_reset_before_reload_is_what_preserves_the_saved_value():
    """Pins the ordering _ch_rebind depends on: load() snapshots the CURRENT
    field values as the ones reset() will restore, so reloading mid-animation
    without resetting first bakes that frame into the scene permanently."""
    ch_map = {3: [(1, 'translate_z')]}
    tracks, id_to_col = _tracks()
    node = _node(translate_z=-1.0)
    set_channel_id(node, 3)
    engine = ChannelEngine()
    engine.load(ch_map, tracks, id_to_col, [node])
    engine.apply_frame(2)
    assert node.translate_z == 9.0

    engine.reset()
    set_channel_id(node, 0)
    engine.load(ch_map, tracks, id_to_col, [node])
    assert not engine.has_bindings
    assert node.translate_z == -1.0
