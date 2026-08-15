"""
Link (type=7) glyph placement — the transform that stretches an arbitrary
glyph geometry along the axis between a link's two endpoints.

The load-bearing claims, all pinned below:

  * the glyph SPANS the edge — its local z extent lands exactly on A and B,
    for symmetric shapes and for the Pin (whose apex is its local origin);
  * `ratio` is the thickness on both cross-axes, and nothing else scales it;
  * the rotation reproduces ANTz's own Rz(atan2 - 90) . Rx(asin + 90)
    composition, so a textured/asymmetric glyph rolls the way ANTz rolls it;
  * the three line-mode ids stay line-drawn, which is what keeps every
    pre-existing file rendering unchanged.

GUI/renderer wiring is pinned in tests/test_link_geometry_viewport.py.
"""
import math

import numpy as np
import pytest

from glyphviz_core.geometry_data import (
    GEO_CUBE, GEO_CUBE_WIRE, GEO_CYLINDER, GEO_LINE, GEO_LINE_PRISM, GEO_MESH,
    GEO_OCTA, GEO_PIN, GEO_PIN_WIRE, GEO_POINT, GEO_SPHERE, GEO_STAR,
    GEO_TORUS, PIN_HEIGHT, PIN_RADIUS,
)
from glyphviz_core.link_geometry import (
    DEFAULT_LOCAL_Z_SPAN, LINK_LINE_GEOMETRIES, is_glyph_link,
    link_axis_basis, link_gl_matrix, link_glyph_matrix, local_z_span,
)


def _apply(M, p):
    """Transform a local-space point by a row-major 4x4."""
    v = M @ np.array([p[0], p[1], p[2], 1.0])
    return v[:3]


# --- which ids are glyph links ---------------------------------------------

@pytest.mark.parametrize("geo", sorted(LINK_LINE_GEOMETRIES))
def test_line_modes_are_not_glyph_links(geo):
    assert not is_glyph_link(geo)


def test_line_modes_are_exactly_line_prism_point():
    assert LINK_LINE_GEOMETRIES == {GEO_LINE, GEO_LINE_PRISM, GEO_POINT}


@pytest.mark.parametrize("geo", [
    GEO_CUBE, GEO_CUBE_WIRE, GEO_SPHERE, GEO_CYLINDER, GEO_OCTA, GEO_PIN,
    GEO_TORUS, GEO_MESH, GEO_STAR,
])
def test_real_glyphs_are_glyph_links(geo):
    assert is_glyph_link(geo)


# --- the glyph spans the edge ----------------------------------------------

@pytest.mark.parametrize("a, b", [
    ((0.0, 0.0, 0.0), (10.0, 0.0, 0.0)),        # along +X
    ((0.0, 0.0, 0.0), (0.0, 7.0, 0.0)),         # along +Y
    ((0.0, 0.0, 0.0), (0.0, 0.0, 5.0)),         # straight up (atan2(0,0))
    ((0.0, 0.0, 0.0), (0.0, 0.0, -5.0)),        # straight down
    ((-3.0, 2.0, 1.0), (4.0, -6.0, 9.0)),       # general
    ((100.0, -50.0, 20.0), (100.5, -50.25, 20.1)),   # short, off-origin
])
def test_symmetric_glyph_lands_on_both_endpoints(a, b):
    """A -1..+1 glyph's two z poles map onto A and B exactly."""
    M = link_glyph_matrix(a, b, 0.3, GEO_CUBE)
    assert np.allclose(_apply(M, (0.0, 0.0, -1.0)), a)
    assert np.allclose(_apply(M, (0.0, 0.0, 1.0)), b)


def test_pin_apex_on_a_and_dome_on_b():
    """The Pin stands on its apex at its local origin and tops out at
    PIN_HEIGHT + PIN_RADIUS, so its span is 0..1.1, not -1..1. Mapping the
    real span is what keeps a Pin link from hanging off past its B-end (which
    ANTz's fixed 'distance * 0.5' did)."""
    a, b = (1.0, 2.0, 3.0), (1.0, 2.0, 13.0)
    top = PIN_HEIGHT + PIN_RADIUS
    for geo in (GEO_PIN, GEO_PIN_WIRE):
        assert local_z_span(geo) == (0.0, top)
        M = link_glyph_matrix(a, b, 0.2, geo)
        assert np.allclose(_apply(M, (0.0, 0.0, 0.0)), a)
        assert np.allclose(_apply(M, (0.0, 0.0, top)), b)


def test_flat_glyph_falls_back_to_the_two_unit_convention():
    """Grid/Circle/Cross/Star have no z extent — no division by zero, and the
    plate lands centered on the edge."""
    a, b = (0.0, 0.0, 0.0), (0.0, 0.0, 8.0)
    M = link_glyph_matrix(a, b, 0.5, GEO_STAR)
    assert M is not None
    assert np.allclose(_apply(M, (0.0, 0.0, 0.0)), (0.0, 0.0, 4.0))


def test_unknown_geometry_uses_the_default_span():
    assert local_z_span(GEO_SPHERE) == DEFAULT_LOCAL_Z_SPAN
    assert local_z_span(9999) == DEFAULT_LOCAL_Z_SPAN


# --- ratio is the thickness, on both cross-axes -----------------------------

@pytest.mark.parametrize("ratio", [0.01, 0.1, 1.0, 4.5])
def test_ratio_is_the_cross_axis_thickness(ratio):
    M = link_glyph_matrix((0.0, 0.0, 0.0), (0.0, 0.0, 20.0), ratio, GEO_CUBE)
    assert np.linalg.norm(M[:3, 0]) == pytest.approx(ratio)
    assert np.linalg.norm(M[:3, 1]) == pytest.approx(ratio)


def test_ratio_never_touches_length():
    """Changing thickness must not move the endpoints — the two are
    independent, which is the whole point of using one field for thickness."""
    a, b = (0.0, 0.0, 0.0), (3.0, 4.0, 0.0)
    thin = link_glyph_matrix(a, b, 0.05, GEO_CYLINDER)
    fat = link_glyph_matrix(a, b, 3.0, GEO_CYLINDER)
    for M in (thin, fat):
        assert np.allclose(_apply(M, (0.0, 0.0, -1.0)), a)
        assert np.allclose(_apply(M, (0.0, 0.0, 1.0)), b)
    assert np.linalg.norm(thin[:3, 2]) == pytest.approx(np.linalg.norm(fat[:3, 2]))


def test_length_column_is_half_the_distance_for_symmetric_glyphs():
    """ANTz's `glScalef(ratio, ratio, distance * 0.5)`, exactly."""
    a, b = (0.0, 0.0, 0.0), (6.0, 8.0, 0.0)   # distance 10
    M = link_glyph_matrix(a, b, 0.2, GEO_SPHERE)
    assert np.linalg.norm(M[:3, 2]) == pytest.approx(5.0)


# --- rotation: ANTz's composition, column for column ------------------------

def _antz_basis(a, b):
    """Rz(atan2(uy,ux) - 90) . Rx(asin(uz) + 90) built from literal rotation
    matrices, as npDrawLink composes it with two glRotatef calls (npgldraw.c
    :1026-1027). u is the B->A unit vector, matching its `vec`."""
    u = np.array(a, dtype=float) - np.array(b, dtype=float)
    u /= np.linalg.norm(u)
    rot_z = math.degrees(math.atan2(u[1], u[0])) - 90.0
    rot_x = math.degrees(math.asin(u[2])) + 90.0
    cz, sz = math.cos(math.radians(rot_z)), math.sin(math.radians(rot_z))
    cx, sx = math.cos(math.radians(rot_x)), math.sin(math.radians(rot_x))
    Rz = np.array([[cz, -sz, 0.0], [sz, cz, 0.0], [0.0, 0.0, 1.0]])
    Rx = np.array([[1.0, 0.0, 0.0], [0.0, cx, -sx], [0.0, sx, cx]])
    return Rz @ Rx


@pytest.mark.parametrize("a, b", [
    ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
    ((0.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    ((0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    ((0.0, 0.0, 0.0), (0.0, 0.0, -1.0)),
    ((2.0, -1.0, 4.0), (-5.0, 3.0, -2.0)),
    ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)),
])
def test_basis_matches_antz_rotation_composition(a, b):
    col0, col1, col2, length = link_axis_basis(a, b)
    expected = _antz_basis(a, b)
    got = np.column_stack([col0, col1, col2])
    assert np.allclose(got, expected, atol=1e-12)
    assert length == pytest.approx(
        float(np.linalg.norm(np.array(b, dtype=float) - np.array(a))))


@pytest.mark.parametrize("a, b", [
    ((0.0, 0.0, 0.0), (3.0, 0.0, 0.0)),
    ((0.0, 0.0, 0.0), (0.0, 0.0, 9.0)),
    ((7.0, 1.0, -2.0), (-1.0, 5.0, 6.0)),
])
def test_basis_is_a_right_handed_orthonormal_frame(a, b):
    col0, col1, col2, _ = link_axis_basis(a, b)
    R = np.column_stack([col0, col1, col2])
    assert np.allclose(R.T @ R, np.eye(3), atol=1e-12)
    assert np.linalg.det(R) == pytest.approx(1.0)


@pytest.mark.parametrize("a, b", [
    ((0.0, 0.0, 0.0), (5.0, 0.0, 0.0)),
    ((0.0, 0.0, 0.0), (0.0, 0.0, 5.0)),
    ((1.0, 2.0, 3.0), (-4.0, 0.5, 8.0)),
])
def test_third_column_is_the_unit_a_to_b_direction(a, b):
    _, _, col2, length = link_axis_basis(a, b)
    d = (np.array(b, dtype=float) - np.array(a)) / length
    assert np.allclose(col2, d, atol=1e-12)


def test_roll_reference_is_horizontal():
    """col0 has zero z for every non-degenerate edge — the glyph's roll is
    gravity-referenced, so a link doesn't spin about its own axis as it swings
    around (which an arbitrary-up cross product would do)."""
    for b in [(1.0, 0.0, 0.0), (0.0, 1.0, 0.3), (-2.0, 5.0, -7.0), (0.1, 0.1, 20.0)]:
        col0, _, _, _ = link_axis_basis((0.0, 0.0, 0.0), b)
        assert col0[2] == pytest.approx(0.0, abs=1e-12)


# --- degenerate edges -------------------------------------------------------

def test_coincident_endpoints_have_no_transform():
    p = (4.0, 4.0, 4.0)
    assert link_axis_basis(p, p) is None
    assert link_glyph_matrix(p, p, 0.2, GEO_CUBE) is None
    assert link_gl_matrix(p, p, 0.2, GEO_CUBE) is None


# --- the GL form ------------------------------------------------------------

def test_gl_matrix_is_the_column_major_float32_transpose():
    """Same convention as Scene.node_draw_data's gl_matrix, so glMultMatrixf
    reads it correctly."""
    a, b = (1.0, -2.0, 3.0), (4.0, 5.0, -6.0)
    M = link_glyph_matrix(a, b, 0.25, GEO_CYLINDER)
    gl = link_gl_matrix(a, b, 0.25, GEO_CYLINDER)
    assert gl.dtype == np.float32
    assert gl.shape == (16,)
    assert np.allclose(gl.reshape(4, 4), M.T.astype(np.float32))
    # Column-major: the translation is the LAST ROW of the flat 4x4.
    assert np.allclose(gl.reshape(4, 4)[3, :3], M[:3, 3], atol=1e-5)


# --- properties that have to hold across the whole sphere of directions -----

def test_every_direction_spans_its_edge():
    """Sweep the full sphere: no direction may leave the glyph short of, past,
    or off its endpoints (this is what a hyperglyph full of links depends on)."""
    a = np.array([2.0, -3.0, 1.5])
    for i in range(24):
        for j in range(1, 12):
            th = 2.0 * math.pi * i / 24.0
            ph = math.pi * j / 12.0
            d = np.array([math.sin(ph) * math.cos(th),
                          math.sin(ph) * math.sin(th),
                          math.cos(ph)])
            b = a + d * 17.0
            M = link_glyph_matrix(a, b, 0.4, GEO_OCTA)
            assert np.allclose(_apply(M, (0.0, 0.0, -1.0)), a, atol=1e-9)
            assert np.allclose(_apply(M, (0.0, 0.0, 1.0)), b, atol=1e-9)
