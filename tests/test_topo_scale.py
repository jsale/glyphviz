"""
Topology Scale (Node.topo_scale) — the per-parent size of a topology's
coordinate system.

A topology reads some of a child's translate axes as ANGLES (longitude,
latitude, orbital angle) and others as DISTANCES (a cube facet's two axes,
Pin/Cylinder height, altitude above a sphere, all three axes of a Cartesian
topology). Values authored for the angular reading — 0..360 — are enormous
when read as distances, so switching a parent from Sphere to Cube used to
throw its children hundreds of times their own parent's radius away, off
screen and effectively unfindable. topo_scale multiplies the distance-valued
axes so the two families can be brought into the same neighborhood.

What's pinned here:
  * angular axes are NEVER scaled, at any topo_scale — the property the whole
    design rests on, checked per topology against LINEAR_PLACEMENT_AXES so a
    future topology can't quietly land in the wrong column;
  * the default 1.0 reproduces GlyphViz's original placement exactly, and a
    CSV with no topo_scale column loads as 1.0 and saves back without one;
  * TOPO_SCALE_ANTZ puts a child at translate 180 exactly on a cube facet's
    edge (ANTz's "360 units across a facet"), which is the landmark that makes
    an angular layout survive the switch to a linear topology;
  * all three placement paths agree — the batched full recompute, the
    per-frame partial update behind Channels playback, and the scalar
    placement_offset the transform gizmo differentiates;
  * World Grid children and root nodes are exempt.

Scenes go through a real CSV and the real loader wherever a load-side default
is part of what's being tested.
"""
import numpy as np
import pandas as pd
import pytest

from glyphviz_core.csv_reader import _COL_ORDER, load_node_csv, save_node_csv
from glyphviz_core.node import (
    DEFAULT_TOPO_SCALE, TOPO_SCALE_ANTZ, GRID_GLOBE_RADIUS, Node,
    NODE_TYPE_GRID,
)
from glyphviz_core.scene import Scene
from glyphviz_core import topology as tp

BASE_SCALE = 1.0

# Every topology that places children, with a translate triple whose three
# components are distinct and large enough that a missed scaling shows up.
PLACEMENT_TOPOS = sorted(tp.LINEAR_PLACEMENT_AXES)
PROBE = (150.0, 40.0, 3.0)


def _node(**overrides):
    base = dict(
        id=1, type=5, parent_id=0, branch_level=0,
        translate_x=0.0, translate_y=0.0, translate_z=0.0,
        rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=200, color_g=200, color_b=200, color_a=255,
        geometry=3, hide=0, topo=0,
    )
    base.update(overrides)
    return Node(**base)


def _pair(parent_topo, k, translate=PROBE, subspace=0, **parent_kw):
    """A parent at the origin plus one child at `translate`."""
    parent = _node(id=1, topo=parent_topo, topo_scale=k, **parent_kw)
    child = _node(id=2, parent_id=1, branch_level=1,
                  translate_x=translate[0], translate_y=translate[1],
                  translate_z=translate[2], subspace=subspace)
    return [parent, child]


def _child_offset(nodes):
    """The child's world position relative to its parent."""
    t = tp.compute_world_transforms(nodes, BASE_SCALE)
    return t.world_pos[1] - t.world_pos[0]


def _row(**overrides):
    row = {c: 0 for c in _COL_ORDER}
    row.update(scale_x=1, scale_y=1, scale_z=1, ratio=0.1, type=5)
    row.update(overrides)
    return row


# --- the invariant the design rests on: angular axes never move -------------

@pytest.mark.parametrize("topo", PLACEMENT_TOPOS)
def test_angular_axes_are_never_scaled(topo):
    """For each topology, vary ONLY the axes it reads as angles and confirm
    topo_scale has no effect on the resulting placement — across four orders
    of magnitude. This is what lets a user turn the knob down to rescue a cube
    without their spheres, tori and cylinders deforming."""
    axes = tp.LINEAR_PLACEMENT_AXES[topo]
    angular = [i for i, is_linear in enumerate(axes) if not is_linear]
    if not angular:
        pytest.skip(f"{tp.TOPO_NAMES[topo]} has no angular axis")
    # Zero the distance axes so only the angular ones contribute.
    translate = tuple(PROBE[i] if i in angular else 0.0 for i in range(3))
    ref = _child_offset(_pair(topo, DEFAULT_TOPO_SCALE, translate))
    for k in (0.001, TOPO_SCALE_ANTZ, 0.5, 40.0):
        got = _child_offset(_pair(topo, k, translate))
        assert got == pytest.approx(ref, abs=1e-12), (
            f"{tp.TOPO_NAMES[topo]}: topo_scale={k} moved an angular placement")


@pytest.mark.parametrize("topo", PLACEMENT_TOPOS)
def test_linear_axes_scale_linearly(topo):
    """Each distance-valued axis must respond in exact proportion. Checked one
    axis at a time against the parent's base radius term, which does NOT
    scale — so the test also catches a scaling that wrongly swallowed the
    surface offset."""
    axes = tp.LINEAR_PLACEMENT_AXES[topo]
    linear = [i for i, is_linear in enumerate(axes) if is_linear]
    assert linear, f"{tp.TOPO_NAMES[topo]} claims no linear axis"
    for i in linear:
        translate = tuple(PROBE[i] if j == i else 0.0 for j in range(3))
        base = _child_offset(_pair(topo, 0.0, translate))     # base term only
        full = _child_offset(_pair(topo, 1.0, translate))
        half = _child_offset(_pair(topo, 0.5, translate))
        contribution = full - base
        assert np.linalg.norm(contribution) > 1e-9, (
            f"{tp.TOPO_NAMES[topo]} axis {i} claims to be linear but "
            "contributes nothing")
        assert (half - base) == pytest.approx(contribution * 0.5, abs=1e-12)


# --- the default reproduces the original behavior ---------------------------

def test_default_is_one():
    assert _node().topo_scale == DEFAULT_TOPO_SCALE == 1.0


@pytest.mark.parametrize("topo", PLACEMENT_TOPOS)
def test_unset_matches_explicit_one(topo):
    """A node that never mentions topo_scale places children identically to
    one explicitly set to 1.0 — the no-regression guarantee for every file
    written before the field existed."""
    unset = _pair(topo, DEFAULT_TOPO_SCALE)
    explicit = _pair(topo, 1.0)
    assert _child_offset(unset) == pytest.approx(_child_offset(explicit))


# --- the ANTz landmark ------------------------------------------------------

@pytest.mark.parametrize("face", range(6))
def test_antz_scale_puts_180_on_the_facet_edge(face):
    """ANTz's convention: a facet is 360 units across, so translate 180 lands
    exactly on its edge — one base radius from the face center, in the face's
    own u direction. That correspondence is the reason this value is a preset
    button."""
    nodes = _pair(tp.TOPO_CUBE, TOPO_SCALE_ANTZ, translate=(180.0, 0.0, 0.0),
                  subspace=face)
    off = _child_offset(nodes)
    normal, u, _v = tp._CUBE_FACES[face]
    expected = (np.array(normal, dtype=float) * BASE_SCALE
                + np.array(u, dtype=float) * BASE_SCALE)
    assert off == pytest.approx(expected, abs=1e-12)


def test_antz_scale_keeps_children_near_a_switched_parent():
    """The end-to-end symptom: 12 children authored as degrees, under a parent
    stepped from Sphere to Cube. At 1.0 they scatter to hundreds of times the
    parent's radius; at the ANTz scale they stay in its neighborhood."""
    def spread(topo, k):
        parent = _node(id=1, topo=topo, topo_scale=k,
                       scale_x=9.0, scale_y=9.0, scale_z=9.0)
        kids = [_node(id=10 + j, parent_id=1, branch_level=1,
                      translate_x=j * 30.0, translate_y=(j % 4) * 25.0 - 30.0)
                for j in range(12)]
        t = tp.compute_world_transforms([parent] + kids, BASE_SCALE)
        d = np.linalg.norm(t.world_pos[1:] - t.world_pos[0], axis=1)
        return d.max() / 9.0        # in multiples of the parent's radius

    assert spread(tp.TOPO_SPHERE, DEFAULT_TOPO_SCALE) == pytest.approx(1.0)
    assert spread(tp.TOPO_CUBE, DEFAULT_TOPO_SCALE) > 300     # the bug
    assert spread(tp.TOPO_CUBE, TOPO_SCALE_ANTZ) < 3          # the fix


# --- exemptions -------------------------------------------------------------

@pytest.mark.parametrize("geometry", [0, 2])   # flat window, and globe (sphere)
def test_world_grid_children_are_exempt(geometry):
    """A grid's footprint is drawn from the same extents window its children's
    coordinates are read in. Scaling one without the other would slide the
    frame out from under them, so grid children ignore topo_scale entirely."""
    def offset(k):
        grid = _node(id=1, type=NODE_TYPE_GRID, topo=tp.TOPO_PLANE,
                     geometry=geometry, topo_scale=k)
        child = _node(id=2, parent_id=1, branch_level=1,
                      translate_x=90.0, translate_y=30.0, translate_z=5.0)
        return _child_offset([grid, child])

    ref = offset(DEFAULT_TOPO_SCALE)
    for k in (0.001, TOPO_SCALE_ANTZ, 25.0):
        assert offset(k) == pytest.approx(ref, abs=1e-12)


def test_linear_placement_axes_reports_grid_as_exempt():
    grid = _node(id=1, type=NODE_TYPE_GRID, topo=tp.TOPO_PLANE)
    assert tp.linear_placement_axes(grid) == (False, False, False)
    assert tp.scale_linear_axes(grid, 1.0, 2.0, 3.0) == (1.0, 2.0, 3.0)


def test_roots_are_exempt():
    """A root's translate IS its world position, not an offset from anything,
    so its own topo_scale must not move it."""
    for k in (DEFAULT_TOPO_SCALE, TOPO_SCALE_ANTZ, 50.0):
        root = _node(id=1, topo=tp.TOPO_PLANE, topo_scale=k,
                     translate_x=7.0, translate_y=-3.0, translate_z=2.0)
        t = tp.compute_world_transforms([root], BASE_SCALE)
        assert t.world_pos[0] == pytest.approx((7.0, -3.0, 2.0))


# --- the three placement paths agree ---------------------------------------

@pytest.mark.parametrize("topo", PLACEMENT_TOPOS)
@pytest.mark.parametrize("k", [DEFAULT_TOPO_SCALE, TOPO_SCALE_ANTZ, 7.0])
def test_scalar_placement_offset_matches_batched(topo, k):
    """placement_offset is what the transform gizmo differentiates to find
    which way a translate field pushes a node; it has to speak the same
    coordinate system the renderer places in."""
    nodes = _pair(topo, k)
    scalar = tp.placement_offset(nodes[0], *PROBE, BASE_SCALE, nodes[1].subspace)
    assert np.array(scalar) == pytest.approx(_child_offset(nodes), abs=1e-12)


@pytest.mark.parametrize("topo", PLACEMENT_TOPOS)
def test_partial_update_matches_full_recompute(topo):
    """update_world_transform_rows is the per-frame fast path behind Channels
    playback. Animating a parent's topo_scale has to land in the same place a
    full recompute would."""
    nodes = _pair(topo, DEFAULT_TOPO_SCALE)
    t = tp.compute_world_transforms(nodes, BASE_SCALE)
    nodes[0].topo_scale = TOPO_SCALE_ANTZ
    tp.update_world_transform_rows(nodes, BASE_SCALE, t,
                                   np.array([0, 1], dtype=np.int64))
    fresh = tp.compute_world_transforms(nodes, BASE_SCALE)
    assert t.world_pos == pytest.approx(fresh.world_pos, abs=1e-12)
    assert t.world_basis == pytest.approx(fresh.world_basis, abs=1e-12)


# --- CSV round trip ---------------------------------------------------------

def test_missing_column_loads_as_one(tmp_path):
    path = tmp_path / "gv_node.csv"
    pd.DataFrame([_row(id=1, topo=tp.TOPO_CUBE)])[_COL_ORDER].to_csv(
        path, index=False)
    assert load_node_csv(str(path))[0].topo_scale == DEFAULT_TOPO_SCALE


def test_default_value_writes_no_column(tmp_path):
    """Byte-stability for the ~50 example files and every user file: a scene
    nobody has retuned must not grow a column on save."""
    path = tmp_path / "gv_node.csv"
    save_node_csv([_node(id=1, topo=tp.TOPO_CUBE)], str(path))
    assert 'topo_scale' not in pd.read_csv(path).columns


def test_non_default_value_round_trips(tmp_path):
    path = tmp_path / "gv_node.csv"
    save_node_csv([_node(id=1, topo=tp.TOPO_CUBE, topo_scale=TOPO_SCALE_ANTZ),
                   _node(id=2, topo=tp.TOPO_SPHERE)], str(path))
    assert 'topo_scale' in pd.read_csv(path).columns
    reloaded = load_node_csv(str(path))
    # Written with significant-figure precision, not 6 fixed decimals: 1/180
    # must not come back as a flat 0.005556.
    assert reloaded[0].topo_scale == pytest.approx(TOPO_SCALE_ANTZ, rel=1e-9)
    assert reloaded[1].topo_scale == DEFAULT_TOPO_SCALE


def test_round_trip_preserves_placement(tmp_path):
    """The value is only worth saving if the scene reopens looking the same."""
    path = tmp_path / "gv_node.csv"
    nodes = _pair(tp.TOPO_CUBE, TOPO_SCALE_ANTZ)
    save_node_csv(nodes, str(path))
    before = _child_offset(nodes)
    after = _child_offset(load_node_csv(str(path)))
    assert after == pytest.approx(before, rel=1e-9)


# --- the "your children just flew away" hint -------------------------------

def test_scattered_children_ratio_flags_the_bad_case():
    """Scene.worst_child_placement_ratio is what the GUI hint reads. It must
    stay quiet for a child sitting on its parent's surface and speak up for
    one flung into the distance."""
    # translate_z = 0 on a Sphere parent means "on the surface", so the child
    # sits at exactly the parent's own radius: a ratio of 1.
    on_surface = Scene(_pair(tp.TOPO_SPHERE, DEFAULT_TOPO_SCALE,
                             translate=(150.0, 40.0, 0.0)), BASE_SCALE)
    ratio, node_id = on_surface.worst_child_placement_ratio([1])
    assert ratio == pytest.approx(1.0) and node_id == 1

    flung = Scene(_pair(tp.TOPO_CUBE, DEFAULT_TOPO_SCALE), BASE_SCALE)
    ratio, node_id = flung.worst_child_placement_ratio([1])
    assert ratio > 20.0 and node_id == 1

    rescued = Scene(_pair(tp.TOPO_CUBE, TOPO_SCALE_ANTZ), BASE_SCALE)
    assert rescued.worst_child_placement_ratio([1])[0] < 20.0


def test_scattered_children_ratio_ignores_childless_and_unknown():
    scene = Scene(_pair(tp.TOPO_CUBE, DEFAULT_TOPO_SCALE), BASE_SCALE)
    assert scene.worst_child_placement_ratio([]) == (0.0, -1)
    assert scene.worst_child_placement_ratio([999]) == (0.0, -1)
    assert scene.worst_child_placement_ratio([2]) == (0.0, -1)   # the leaf


# --- Channels binding -------------------------------------------------------

def test_topo_scale_is_a_transform_binding():
    """Bound as an animatable attribute, and registered as one that re-places
    descendants — without that second entry, playback would move the parent's
    coordinate system while its children kept last frame's matrices."""
    from glyphviz_core import channel_engine as ce
    assert ce._ATTR_TO_FIELD['topo_scale'] == 'topo_scale'
    assert 'topo_scale' in ce._TRANSFORM_FIELDS
    assert 'topo_scale' not in ce._INT_FIELDS      # a multiplier, not an id


def test_globe_grid_radius_is_the_antz_correspondence():
    """Sanity anchor for the constant: a World Grid globe already rolls the
    flat 1:1 map onto a sphere at radius 180/pi, i.e. one degree = one world
    unit. TOPO_SCALE_ANTZ is that same correspondence for a linear axis."""
    assert GRID_GLOBE_RADIUS * TOPO_SCALE_ANTZ * 180.0 == pytest.approx(
        GRID_GLOBE_RADIUS)
