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
from glyphviz_core.node import Node
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
    offset = topo._cube_offset(0, 0, 0, 10.0, 0.1, (1.0, 1.0, 1.0), subspace)
    expected = tuple(10.0 * a for a in axis)
    for got, exp in zip(offset, expected):
        assert got == pytest.approx(exp)


def test_cube_offset_inplane_axes_match_antz_ground_truth():
    """+X face: local-x (right when facing it) = world +Y, local-y (up) = world +Z
    — derived from Jeff's confirmed facet/coordinate convention and verified
    against the existing _CUBE_FACES table."""
    offset = topo._cube_offset(5.0, 7.0, 0.0, 10.0, 0.1, (1.0, 1.0, 1.0), 0)
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
    x, y, z = topo._cylinder_offset(0.0, 0.0, 0.0, 10.0, 0.1, (1.0, 1.0, 1.0))
    assert (x, y, z) == pytest.approx((10.0, 0.0, 0.0))


def test_cylinder_offset_height_is_literal_not_normalized():
    x, y, z = topo._cylinder_offset(0.0, 25.0, 0.0, 10.0, 0.1, (1.0, 1.0, 1.0))
    assert (x, y, z) == pytest.approx((10.0, 0.0, 25.0))


def test_cylinder_offset_angle_90_degrees():
    x, y, z = topo._cylinder_offset(90.0, 0.0, 0.0, 10.0, 0.1, (1.0, 1.0, 1.0))
    assert (x, y, z) == pytest.approx((0.0, 10.0, 0.0), abs=1e-9)


# ---------------------------------------------------------------------------
# Z-topology variants: surface/radius term zeroed relative to their base topology.
# ---------------------------------------------------------------------------

def test_zcube_offset_drops_base_radius_term():
    # At tz=0, a Zcube child sits at the parent's center, unlike Cube (radius away).
    assert topo._zcube_offset(0, 0, 0, 10.0, 0.1, (1.0, 1.0, 1.0), 0) == pytest.approx((0.0, 0.0, 0.0))
    # With tz != 0 it still moves outward along the face normal.
    assert topo._zcube_offset(0, 0, 5, 10.0, 0.1, (1.0, 1.0, 1.0), 0) == pytest.approx((5.0, 0.0, 0.0))


def test_zsphere_offset_center_at_zero_altitude():
    assert topo._zsphere_offset(45.0, 30.0, 0.0, 10.0, 0.1, (1.0, 1.0, 1.0)) == pytest.approx((0.0, 0.0, 0.0))


def test_zsphere_offset_matches_point_offset():
    """Topology-Guide.md describes Point as 'similar to Sphere ... but center
    is translate_z=0.0' — the same description given for Zsphere — so their
    position math should coincide (the documented difference between them is
    the scale-cascade rule, not placement)."""
    args = (12.0, -20.0, 7.0, 10.0, 0.1, (2.0, 1.0, 0.5))
    assert topo._zsphere_offset(*args) == pytest.approx(topo._point_offset(*args))


def test_ztorus_offset_zero_thickness_sits_on_major_circle():
    # At tz=0 a Ztorus child sits exactly on the major (orbital) circle —
    # unlike Torus, where tz=0 still rides the tube's outer surface
    # (radial = major_r + minor_r, not major_r alone).
    from glyphviz_core.geometry_data import torus_radii
    major_r, _minor_r = torus_radii(0.1, 10.0)
    x, y, z = topo._ztorus_offset(0.0, 0.0, 0.0, 10.0, 0.1, (1.0, 1.0, 1.0))
    assert (x, y, z) == pytest.approx((major_r, 0.0, 0.0))


def test_ztorus_offset_tz_offsets_directly_no_minor_radius():
    x, y, z = topo._ztorus_offset(0.0, 90.0, 4.0, 10.0, 0.1, (1.0, 1.0, 1.0))
    # v=90 puts the tube angle straight up: z should equal tz exactly (tube_r=tz).
    assert z == pytest.approx(4.0)


def test_zcylinder_offset_radius_zero_collapses_to_axis():
    assert topo._zcylinder_offset(45.0, 7.0, 0.0, 10.0, 0.1, (1.0, 1.0, 1.0)) == pytest.approx((0.0, 0.0, 7.0))


def test_zcylinder_offset_tz_offsets_directly_from_axis():
    x, y, z = topo._zcylinder_offset(0.0, 0.0, 3.0, 10.0, 0.1, (1.0, 1.0, 1.0))
    assert (x, y, z) == pytest.approx((3.0, 0.0, 0.0))


def test_zrod_offset_matches_zcylinder_placement():
    args = (15.0, 40.0, 5.0, 10.0, 0.1, (1.5, 0.5, 2.0))
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
