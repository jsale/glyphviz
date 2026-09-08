"""
Link (type=7) glyph placement — the transform that stretches an ordinary
glyph geometry along the axis between a link's two endpoints.

No OpenGL/Qt dependency, so the math is testable headlessly and reusable by a
future non-GL presentation layer (OpenXR, three.js) the same way
`gizmo.py` / `placement.py` / `camera_smoothing.py` are.

ANTz's rule, read from the source (`npDrawLink`, npgldraw.c:961-1067): a link
node is drawn like any other node — `npGLSurface` renders whatever
`node->geometry` says — but with a bespoke matrix instead of the node's own
transform:

    glTranslatef (A)                                 // the A-end's world pos
    glRotatef (rotZ * kRADtoDEG - 90, 0,0,1)         // rotZ = atan2(uy, ux)
    glRotatef (rotX * kRADtoDEG + 90, 1,0,0)         // rotX = asin(uz)
    glScalef  (ratio, ratio, distance * 0.5)         // "cyl is 2 units"
    glTranslatef (0, 0, kNPoffsetUnit)               // = 1.0

So: **`ratio` is the thickness on both cross-axes and the endpoint distance is
the length**, which is exactly what makes a link able to distort a glyph
arbitrarily along its connection axis. The node's own `translate`/`rotate`/
`scale` play no part — a link has no independent pose, it *is* the edge.

Two deliberate refinements over ANTz's version:

1. **The glyph's own local Z extent is mapped onto the A→B segment**, rather
   than assuming every shape spans 2 units in z. For the symmetric shapes
   (cube, sphere, cylinder, cone, the polyhedra, an imported mesh — all built
   on -1..+1 here, see `glyphviz_gl/geometry.py`) this reduces *exactly* to
   ANTz's `distance * 0.5` about the midpoint. It differs only for Pin, whose
   apex sits at its local origin and whose dome tops out at
   PIN_HEIGHT + PIN_RADIUS (GlyphViz's 2026-08-14 rebuild) — ANTz papered over
   that with a conditional -1 unit nudge inside npGLSurface (npgeometry.c:205),
   which left a pin link hanging off past its B-end. Here a Pin link's tip sits
   on A and its dome lands on B.

2. **`geometry` alone selects the mode** (no new column), but three ids stay
   line-drawn rather than becoming stretched glyphs — see
   LINK_LINE_GEOMETRIES.

The rotation is built column-by-column from the same composition ANTz uses,
not from an arbitrary-up cross product, so an asymmetric or textured glyph
rolls about the link axis exactly the way ANTz rolls it: column 2 is the unit
A→B direction, and column 0 is horizontal (zero z) — the "left" of the
heading — so a link's glyph keeps a consistent, gravity-referenced roll as it
swings around, instead of flipping when the reference axis is crossed.
"""
import math

import numpy as np

from .geometry_data import (
    GEO_LINE, GEO_LINE_PRISM, GEO_PIN, GEO_PIN_WIRE, GEO_POINT,
    PIN_HEIGHT, PIN_RADIUS,
)

# Geometry ids that keep drawing a link as a LINE rather than as a stretched
# glyph:
#   27 GEO_LINE        -- the classic thin GL_LINES connector, and the default.
#   28 GEO_LINE_PRISM  -- the textured scrolling tube (its own bespoke draw).
#   22 GEO_POINT       -- a fixed-pixel-size GL_POINTS sprite has no extent to
#                         stretch along anything, so there is no sensible glyph
#                         reading of it; it also keeps every pre-existing file
#                         that parked links on Point (e.g. the GTDB
#                         Org_Event_Network example's 6400 edges) rendering
#                         unchanged.
LINK_LINE_GEOMETRIES = frozenset({GEO_LINE, GEO_LINE_PRISM, GEO_POINT})

# Local-space z extent (min, max) of each glyph, i.e. the span that gets mapped
# onto the A→B segment. Everything absent from this table uses
# DEFAULT_LOCAL_Z_SPAN, which is the convention every shape in
# glyphviz_gl/geometry.py is built on -- unit radius about the local origin.
DEFAULT_LOCAL_Z_SPAN = (-1.0, 1.0)
_LOCAL_Z_SPAN = {
    # The pin stands ON its apex at the local origin (see _draw_pin).
    GEO_PIN:      (0.0, PIN_HEIGHT + PIN_RADIUS),
    GEO_PIN_WIRE: (0.0, PIN_HEIGHT + PIN_RADIUS),
}


def is_glyph_link(geometry: int) -> bool:
    """True when a Link node's `geometry` names a real 3-D glyph to be
    stretched between its two ends, rather than one of the line modes."""
    return geometry not in LINK_LINE_GEOMETRIES


def local_z_span(geometry: int) -> tuple[float, float]:
    """The (min, max) local-z extent `link_glyph_matrix` maps onto the edge."""
    return _LOCAL_Z_SPAN.get(geometry, DEFAULT_LOCAL_Z_SPAN)


def link_axis_basis(a_pos, b_pos) -> tuple[tuple, tuple, tuple, float] | None:
    """Orthonormal (col0, col1, col2) rotation columns for the edge A→B, plus
    its length. col2 is the unit A→B direction. Returns None when the two ends
    coincide (nothing to orient).

    Reproduces ANTz's Rz(atan2(uy,ux) - 90°) · Rx(asin(uz) + 90°) composition,
    where u is the *B→A* unit vector — hence the sign flips below. Straight
    from that product:

        col0 = ( sz, -cz,   0 )
        col1 = (-cz*sx, -sz*sx,  cx )
        col2 = (-cz*cx, -sz*cx, -sx )  ==  -u  ==  the A→B direction

    A perfectly vertical edge lands on atan2(0, 0) == 0, which is well-defined
    in both C and Python and gives col0 = (0, -1, 0) — so no special case is
    needed, just the shared roll convention degrading gracefully.
    """
    ax, ay, az = a_pos
    bx, by, bz = b_pos
    # u points B→A, matching ANTz's `vec = parent->world - child->world`.
    ux, uy, uz = ax - bx, ay - by, az - bz
    length = math.sqrt(ux * ux + uy * uy + uz * uz)
    if length < 1e-9:
        return None
    ux, uy, uz = ux / length, uy / length, uz / length

    rot_z = math.atan2(uy, ux)
    rot_x = math.asin(max(-1.0, min(1.0, uz)))
    cz, sz = math.cos(rot_z), math.sin(rot_z)
    cx, sx = math.cos(rot_x), math.sin(rot_x)

    col0 = (sz, -cz, 0.0)
    col1 = (-cz * sx, -sz * sx, cx)
    col2 = (-cz * cx, -sz * cx, -sx)
    return col0, col1, col2, length


def link_glyph_matrix(a_pos, b_pos, ratio: float,
                      geometry: int = 0) -> np.ndarray | None:
    """World matrix (float64 row-major 4x4, same shape/convention as
    `scene.node_world_matrix`) that places a unit glyph so it spans the edge
    A→B: `ratio` wide on both cross-axes, `geometry`'s local z span stretched
    to the endpoint distance.

    Returns None for a degenerate (zero-length) edge — there is no axis to
    orient along and no sane fallback, so the caller skips the draw.
    """
    basis = link_axis_basis(a_pos, b_pos)
    if basis is None:
        return None
    col0, col1, col2, length = basis

    z_min, z_max = local_z_span(geometry)
    span = z_max - z_min
    if span <= 1e-9:
        # A flat glyph (Grid/Circle/Cross/Star) has no z extent to stretch;
        # fall back to ANTz's fixed 2-unit assumption so it lands centered on
        # the edge rather than dividing by zero.
        z_min, span = DEFAULT_LOCAL_Z_SPAN[0], 2.0
    z_scale = length / span

    # Offset along the edge that puts local z == z_min on the A-end. For the
    # symmetric default span this is +length/2, i.e. ANTz's midpoint.
    offset = -z_min * z_scale

    M = np.zeros((4, 4), dtype=np.float64)
    M[:3, 0] = np.asarray(col0) * ratio
    M[:3, 1] = np.asarray(col1) * ratio
    M[:3, 2] = np.asarray(col2) * z_scale
    M[:3, 3] = (a_pos[0] + col2[0] * offset,
                a_pos[1] + col2[1] * offset,
                a_pos[2] + col2[2] * offset)
    M[3, 3] = 1.0
    return M


def link_gl_matrix(a_pos, b_pos, ratio: float,
                   geometry: int = 0) -> np.ndarray | None:
    """`link_glyph_matrix` as a float32 column-major flat array, ready for
    glMultMatrixf — mirroring `Scene.node_draw_data`'s gl_matrix."""
    M = link_glyph_matrix(a_pos, b_pos, ratio, geometry)
    if M is None:
        return None
    return M.astype(np.float32).T.flatten()
