"""
Direct (non-golden-master) unit tests for topology placement math and the
node-CSV facet/subspace round-trip.

Cube facet-to-axis values are ground truth from Jeff's own ANTz session
(2026-06-23): facet 1=+X, 2=-X, 3=+Y, 4=-Y, 5=+Z, 6=-Z (1-indexed in the
legacy 'facet' CSV column; GlyphViz's Node.subspace is the 0-indexed
equivalent, i.e. subspace = facet - 1).
"""
import math

import pandas as pd
import pytest

from glyphviz_core.csv_reader import _COL_ORDER, load_node_csv, save_node_csv
from glyphviz_core.node import Node, NODE_TYPE_GRID
from glyphviz_core import topology as topo


def _row(**overrides):
    row = {c: 0 for c in _COL_ORDER}
    row.update(
        scale_x=1, scale_y=1, scale_z=1,
        ratio=0.1, type=5,
    )
    row.update(overrides)
    return row


def _write_csv(tmp_path, rows, name="node.csv"):
    path = tmp_path / name
    pd.DataFrame(rows)[_COL_ORDER].to_csv(path, index=False)
    return path


# ---------------------------------------------------------------------------
# facet (1-indexed, legacy ANTz CSV column) <-> subspace (0-indexed, Node field)
# ---------------------------------------------------------------------------

def test_facet_column_loads_into_zero_indexed_subspace(tmp_path):
    rows = [_row(id=34, parent_id=0, topo=topo.TOPO_CUBE, facet=0)]
    rows += [
        _row(id=34 + facet, parent_id=34, facet=facet)
        for facet in range(1, 7)
    ]
    nodes = load_node_csv(str(_write_csv(tmp_path, rows)))
    by_id = {n.id: n for n in nodes}
    for facet in range(1, 7):
        assert by_id[34 + facet].subspace == facet - 1


def test_facet_zero_defaults_to_subspace_zero(tmp_path):
    rows = [_row(id=1, parent_id=0, topo=topo.TOPO_NONE, facet=0)]
    nodes = load_node_csv(str(_write_csv(tmp_path, rows)))
    assert nodes[0].subspace == 0


def test_subspace_column_takes_priority_over_facet(tmp_path):
    """GaiaViz's np_ dialect spells this column 'subspace' (already 0-indexed)
    instead of 'facet' — if a file somehow has both, 'subspace' wins."""
    rows = [_row(id=1, parent_id=0, topo=topo.TOPO_CUBE, facet=6, subspace=2)]
    path = tmp_path / "node.csv"
    pd.DataFrame(rows).to_csv(path, index=False)  # includes both columns
    nodes = load_node_csv(str(path))
    assert nodes[0].subspace == 2


def test_subspace_round_trips_through_save_as_facet(tmp_path):
    node = Node(
        id=2, type=5, parent_id=1, branch_level=1,
        translate_x=0, translate_y=0, translate_z=0,
        rotate_x=0, rotate_y=0, rotate_z=0,
        scale_x=1, scale_y=1, scale_z=1,
        color_r=0, color_g=0, color_b=0, color_a=255,
        geometry=1, hide=0, topo=topo.TOPO_CUBE, subspace=4,
    )
    path = tmp_path / "node.csv"
    save_node_csv([node], str(path))
    reloaded = load_node_csv(str(path))
    assert reloaded[0].subspace == 4


# ---------------------------------------------------------------------------
# Cube facet -> world axis (ground truth: facet 1-6 = +X,-X,+Y,-Y,+Z,-Z)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("subspace,axis", [
    (0, (1, 0, 0)),    # +X
    (1, (-1, 0, 0)),   # -X
    (2, (0, 1, 0)),    # +Y
    (3, (0, -1, 0)),   # -Y
    (4, (0, 0, 1)),    # +Z
    (5, (0, 0, -1)),   # -Z
])
def test_cube_offset_face_centers_on_correct_world_axis(subspace, axis):
    offset = topo._cube_offset(0, 0, 0, 10.0, 0.1, subspace)
    expected = tuple(10.0 * a for a in axis)
    for got, exp in zip(offset, expected):
        assert got == pytest.approx(exp)


def test_cube_offset_inplane_axes_match_antz_ground_truth():
    """+X face: local-x (right when facing it) = world +Y, local-y (up) = world +Z
    — derived from Jeff's confirmed facet/coordinate convention and verified
    against the existing _CUBE_FACES table."""
    offset = topo._cube_offset(5.0, 7.0, 0.0, 10.0, 0.1, 0)
    assert offset == pytest.approx((10.0, 5.0, 7.0))


# ---------------------------------------------------------------------------
# compute_world_positions end-to-end with a real legacy-ANTz-style CSV
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Cylinder (4): translate_x=angle(deg), translate_y=height, translate_z=radial
# (translate_z=0 is the rendered surface, per the Zcylinder spec text:
# "akin to cylindrical coords but with radius=0.0" implies base Cylinder's
# z=0 is the nonzero rendered radius, not the axis).
# ---------------------------------------------------------------------------

def test_cylinder_offset_on_surface_at_zero_angle():
    x, y, z = topo._cylinder_offset(0.0, 0.0, 0.0, 10.0, 0.1)
    assert (x, y, z) == pytest.approx((10.0, 0.0, 0.0))


def test_cylinder_offset_height_is_literal_not_normalized():
    x, y, z = topo._cylinder_offset(0.0, 25.0, 0.0, 10.0, 0.1)
    assert (x, y, z) == pytest.approx((10.0, 0.0, 25.0))


def test_cylinder_offset_angle_90_degrees():
    x, y, z = topo._cylinder_offset(90.0, 0.0, 0.0, 10.0, 0.1)
    assert (x, y, z) == pytest.approx((0.0, 10.0, 0.0), abs=1e-9)


# ---------------------------------------------------------------------------
# Z-topology variants: surface/radius term zeroed relative to their base topology.
# ---------------------------------------------------------------------------

def test_zcube_offset_drops_base_radius_term():
    # At tz=0, a Zcube child sits at the parent's center, unlike Cube (radius away).
    assert topo._zcube_offset(0, 0, 0, 10.0, 0.1, 0) == pytest.approx((0.0, 0.0, 0.0))
    # With tz != 0 it still moves outward along the face normal.
    assert topo._zcube_offset(0, 0, 5, 10.0, 0.1, 0) == pytest.approx((5.0, 0.0, 0.0))


def test_zsphere_offset_center_at_zero_altitude():
    assert topo._zsphere_offset(45.0, 30.0, 0.0, 10.0, 0.1) == pytest.approx((0.0, 0.0, 0.0))


def test_zsphere_offset_matches_point_offset():
    """Topology-Guide.md describes Point as 'similar to Sphere ... but center
    is translate_z=0.0' — the same description given for Zsphere — so their
    position math should coincide (the documented difference between them is
    a separate rendering rule, not placement)."""
    args = (12.0, -20.0, 7.0, 10.0, 0.1)
    assert topo._zsphere_offset(*args) == pytest.approx(topo._point_offset(*args))


def test_ztorus_offset_zero_thickness_sits_on_major_circle():
    # At tz=0 a Ztorus child sits exactly on the major (orbital) circle —
    # unlike Torus, where tz=0 still rides the tube's outer surface
    # (radial = major_r + minor_r, not major_r alone).
    from glyphviz_core.geometry_data import torus_radii
    major_r, _minor_r = torus_radii(0.1, 10.0)
    x, y, z = topo._ztorus_offset(0.0, 0.0, 0.0, 10.0, 0.1)
    assert (x, y, z) == pytest.approx((major_r, 0.0, 0.0))


def test_ztorus_offset_tz_offsets_directly_no_minor_radius():
    x, y, z = topo._ztorus_offset(0.0, 90.0, 4.0, 10.0, 0.1)
    # v=90 puts the tube angle straight up: z should equal tz exactly (tube_r=tz).
    assert z == pytest.approx(4.0)


def test_zcylinder_offset_radius_zero_collapses_to_axis():
    assert topo._zcylinder_offset(45.0, 7.0, 0.0, 10.0, 0.1) == pytest.approx((0.0, 0.0, 7.0))


def test_zcylinder_offset_tz_offsets_directly_from_axis():
    x, y, z = topo._zcylinder_offset(0.0, 0.0, 3.0, 10.0, 0.1)
    assert (x, y, z) == pytest.approx((3.0, 0.0, 0.0))


def test_zrod_offset_matches_zcylinder_placement():
    args = (15.0, 40.0, 5.0, 10.0, 0.1)
    assert topo._zrod_offset(*args) == pytest.approx(topo._zcylinder_offset(*args))


def test_cube_children_spread_across_all_six_faces(tmp_path):
    """Regression test for the bug where the legacy 'facet' column was never
    read into Node.subspace, so every Cube child silently landed on the same
    face (+X) regardless of its assigned facet."""
    rows = [_row(id=34, parent_id=0, topo=topo.TOPO_CUBE, scale_x=1, scale_y=1, scale_z=1)]
    rows += [
        _row(id=34 + facet, parent_id=34, facet=facet, translate_z=0)
        for facet in range(1, 7)
    ]
    nodes = load_node_csv(str(_write_csv(tmp_path, rows)))
    from glyphviz_core.scene import Scene
    scene = Scene(nodes, base_scale=1.0)
    positions = {n.id: scene.world_pos(n.id) for n in nodes}

    dominant_axes = set()
    for facet in range(1, 7):
        pos = positions[34 + facet]
        dominant_axis = max(range(3), key=lambda i: abs(pos[i]))
        dominant_axes.add((dominant_axis, pos[dominant_axis] > 0))
    # All 6 children must land on 6 *different* signed axes, not collapse onto one.
    assert len(dominant_axes) == 6


# ---------------------------------------------------------------------------
# World Grid (type=6): root glyphs with no explicit parent implicitly attach
# to the scene's Grid node (see Scene.grid_node(), compute_world_bases'/
# compute_world_positions' `grid` param), exactly like any other child of a
# TOPO_PLANE parent -- scaling the grid deliberately re-spaces attached
# children (confirmed wanted: e.g. spreading glyphs out across a bigger
# map-textured floor), but must NOT also distort their own rendered shape
# (NO_SIZE_INHERIT_TOPOS, confirmed separately).
# ---------------------------------------------------------------------------

def test_root_glyph_position_scales_with_grid(tmp_path):
    """A root glyph (parent_id=0, no real parent) inherits the grid's own
    position and per-axis scale through TOPO_PLANE's plain Cartesian offset
    -- moving/scaling the grid carries every attached root glyph with it and
    re-spaces it, same as moving/scaling any other Plane-topology parent."""
    rows = [
        _row(id=1, parent_id=0, type=NODE_TYPE_GRID, topo=topo.TOPO_PLANE,
             translate_x=100.0, translate_y=0.0, scale_x=2.0, scale_y=1.0),
        _row(id=2, parent_id=0, translate_x=10.0, translate_y=20.0),
    ]
    nodes = load_node_csv(str(_write_csv(tmp_path, rows)))
    from glyphviz_core.scene import Scene
    scene = Scene(nodes, base_scale=1.0)
    pos = scene.world_pos(2)
    # grid world pos (100, 0, 0) + grid_scale * (translate_x, translate_y, 0)
    assert pos == pytest.approx((100.0 + 2.0 * 10.0, 0.0 + 1.0 * 20.0, 0.0))


def test_grid_scale_does_not_affect_attached_glyph_shape(tmp_path):
    """A root glyph's rendered size must stay exactly as if no grid existed,
    regardless of the grid's own (possibly very non-uniform) scale."""
    rows = [
        _row(id=1, parent_id=0, type=NODE_TYPE_GRID, topo=topo.TOPO_PLANE,
             scale_x=50.0, scale_y=50.0, scale_z=1.0),
        _row(id=2, parent_id=0, translate_x=10.0, translate_y=20.0,
             scale_x=1.0, scale_y=1.0, scale_z=1.0),
    ]
    nodes = load_node_csv(str(_write_csv(tmp_path, rows)))
    from glyphviz_core.scene import Scene
    from glyphviz_core.scene import node_world_matrix
    scene = Scene(nodes, base_scale=3.0)
    glyph = next(n for n in nodes if n.id == 2)
    M = node_world_matrix(glyph, scene)
    rendered_scale = tuple(
        math.sqrt(sum(M[i][j] ** 2 for i in range(3))) for j in range(3)
    )
    # base_scale (3.0) * the glyph's own scale (1,1,1) -- no trace of the grid's 50x.
    assert rendered_scale == pytest.approx((3.0, 3.0, 3.0))


def test_grid_node_itself_stays_at_its_own_origin(tmp_path):
    """The grid is the anchor, not anchored to itself -- its own world
    position is just its own translate_x/y/z, exactly like any other root."""
    rows = [_row(id=1, parent_id=0, type=NODE_TYPE_GRID, topo=topo.TOPO_PLANE,
                  translate_x=5.0, translate_y=-3.0)]
    nodes = load_node_csv(str(_write_csv(tmp_path, rows)))
    from glyphviz_core.scene import Scene
    scene = Scene(nodes, base_scale=1.0)
    assert scene.world_pos(1) == pytest.approx((5.0, -3.0, 0.0))


def test_no_grid_node_root_glyph_unaffected_backward_compat(tmp_path):
    """A scene with zero Grid rows behaves exactly as before this feature --
    a root glyph's world position is its own translate_x/y/z, untouched."""
    rows = [_row(id=2, parent_id=0, translate_x=10.0, translate_y=20.0)]
    nodes = load_node_csv(str(_write_csv(tmp_path, rows)))
    from glyphviz_core.scene import Scene
    scene = Scene(nodes, base_scale=1.0)
    assert scene.world_pos(2) == pytest.approx((10.0, 20.0, 0.0))


def test_world_and_camera_nodes_do_not_attach_to_grid(tmp_path):
    """World (type=0) and Camera (type=1) rows keep parent_id=0's original
    'no parent at all' meaning even when a Grid node exists -- only ordinary
    glyphs implicitly attach to it."""
    rows = [
        _row(id=1, parent_id=0, type=NODE_TYPE_GRID, topo=topo.TOPO_PLANE,
             translate_x=100.0, scale_x=2.0),
        _row(id=2, parent_id=0, type=0, translate_x=10.0),    # World
        _row(id=3, parent_id=0, type=1, translate_x=10.0),    # Camera
    ]
    nodes = load_node_csv(str(_write_csv(tmp_path, rows)))
    from glyphviz_core.scene import Scene
    scene = Scene(nodes, base_scale=1.0)
    assert scene.world_pos(2) == pytest.approx((10.0, 0.0, 0.0))
    assert scene.world_pos(3) == pytest.approx((10.0, 0.0, 0.0))


# ---------------------------------------------------------------------------
# rotation_mode: GlyphViz-only EULER_XYZ vs ANTz's only-ever HEADING_TILT_ROLL.
# Missing column must default to HEADING_TILT_ROLL so every pre-existing file
# (no such column) keeps rendering exactly as it did before this feature.
# ---------------------------------------------------------------------------

def test_missing_rotation_mode_column_defaults_to_heading_tilt_roll(tmp_path):
    rows = [_row(id=1, parent_id=0)]
    nodes = load_node_csv(str(_write_csv(tmp_path, rows)))
    assert nodes[0].rotation_mode == 1  # ROTATION_MODE_HEADING_TILT_ROLL


def test_explicit_rotation_mode_column_overrides_legacy_default(tmp_path):
    rows = [_row(id=1, parent_id=0, rotation_mode=0)]
    path = tmp_path / "node.csv"
    pd.DataFrame(rows).to_csv(path, index=False)  # extra col, not reindexed away
    nodes = load_node_csv(str(path))
    assert nodes[0].rotation_mode == 0  # ROTATION_MODE_EULER_XYZ


def test_rotation_mode_round_trips_through_save(tmp_path):
    node = Node(
        id=2, type=5, parent_id=1, branch_level=1,
        translate_x=0, translate_y=0, translate_z=0,
        rotate_x=30, rotate_y=0, rotate_z=0,
        scale_x=1, scale_y=1, scale_z=1,
        color_r=0, color_g=0, color_b=0, color_a=255,
        geometry=1, hide=0, topo=topo.TOPO_NONE, rotation_mode=0,
    )
    path = tmp_path / "node.csv"
    save_node_csv([node], str(path))
    reloaded = load_node_csv(str(path))
    assert reloaded[0].rotation_mode == 0


def test_untouched_legacy_rotation_mode_omits_column_on_save(tmp_path):
    """A node loaded from a column-less legacy file (rotation_mode defaults
    to HEADING_TILT_ROLL=1 on load) and saved without being touched should
    NOT grow a new column — keeps untouched legacy files byte-for-byte
    stable. (A *new* node at the dataclass default of 0/EULER_XYZ is the
    opposite case — see test_rotation_mode_round_trips_through_save — and
    DOES need the column, since omitting it would misread as legacy on
    reload.)"""
    node = Node(
        id=1, type=5, parent_id=0, branch_level=0,
        translate_x=0, translate_y=0, translate_z=0,
        rotate_x=0, rotate_y=0, rotate_z=0,
        scale_x=1, scale_y=1, scale_z=1,
        color_r=0, color_g=0, color_b=0, color_a=255,
        geometry=1, hide=0, topo=topo.TOPO_NONE, rotation_mode=1,
    )
    path = tmp_path / "node.csv"
    save_node_csv([node], str(path))
    header = path.read_text().splitlines()[0]
    assert "rotation_mode" not in header


def test_rate_fields_round_trip_through_save(tmp_path):
    node = Node(
        id=3, type=5, parent_id=0, branch_level=0,
        translate_x=0, translate_y=0, translate_z=0,
        rotate_x=0, rotate_y=0, rotate_z=0,
        scale_x=1, scale_y=1, scale_z=1,
        color_r=0, color_g=0, color_b=0, color_a=255,
        geometry=1, hide=0, topo=topo.TOPO_NONE,
        translate_rate_x=0.5, translate_rate_y=-0.25, translate_rate_z=0.1,
        rotate_rate_x=1.0, rotate_rate_y=2.0, rotate_rate_z=-3.0,
        scale_rate_x=0.01, scale_rate_y=0.0, scale_rate_z=-0.02,
    )
    path = tmp_path / "node.csv"
    save_node_csv([node], str(path))
    reloaded = load_node_csv(str(path))[0]
    assert reloaded.translate_rate_x == pytest.approx(0.5)
    assert reloaded.translate_rate_y == pytest.approx(-0.25)
    assert reloaded.translate_rate_z == pytest.approx(0.1)
    assert reloaded.rotate_rate_x == pytest.approx(1.0)
    assert reloaded.rotate_rate_y == pytest.approx(2.0)
    assert reloaded.rotate_rate_z == pytest.approx(-3.0)
    assert reloaded.scale_rate_x == pytest.approx(0.01)
    assert reloaded.scale_rate_y == pytest.approx(0.0)
    assert reloaded.scale_rate_z == pytest.approx(-0.02)


def test_missing_rate_columns_default_to_zero(tmp_path):
    """A node CSV authored without the rate columns at all (pre-existing
    minimal files) should load rates as 0.0 rather than raising a KeyError."""
    rows = [_row(id=1, parent_id=0, topo=topo.TOPO_NONE)]
    minimal_cols = [c for c in _COL_ORDER if 'rate' not in c]
    path = tmp_path / "node.csv"
    pd.DataFrame(rows)[minimal_cols].to_csv(path, index=False)
    nodes = load_node_csv(str(path))
    assert nodes[0].translate_rate_x == 0.0
    assert nodes[0].rotate_rate_y == 0.0
    assert nodes[0].scale_rate_z == 0.0


@pytest.mark.parametrize("heading", [0.0, 60.0, 120.0, 180.0, 240.0, 300.0])
def test_heading_tilt_roll_holds_constant_elevation_while_euler_xyz_wobbles(heading):
    """Same two numbers (rotate_x=30 fixed, rotate_y=heading swept) feed into
    both conventions. HEADING_TILT_ROLL composes Heading(z)-then-Tilt(x), the
    standard spherical-coordinate parameterization, so the boresight's
    z-component (elevation) stays constant across the sweep. EULER_XYZ
    composes rotate_x-then-rotate_y as plain axis rotations, which do not
    correspond to azimuth/elevation, so elevation visibly varies instead."""
    tilt = 30.0
    htr = topo.local_rotation_matrix(tilt, heading, 0.0, 1)
    xyz = topo.local_rotation_matrix(tilt, heading, 0.0, 0)
    htr_z = htr[2][2]
    xyz_z = xyz[2][2]
    assert htr_z == pytest.approx(math.cos(math.radians(tilt)))
    if heading not in (0.0, 180.0):
        assert xyz_z != pytest.approx(htr_z, abs=0.05)
