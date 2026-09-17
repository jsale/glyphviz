"""
Geometry type constants, names, and a display-list renderer.

All shapes are compiled at unit scale (fits within radius ~1).
Caller applies glScalef(rx, ry, rz) before calling draw() — independent
per-axis factors let a node's scale_x/y/z stretch its glyph non-uniformly.
No GLUT dependency — all polyhedra built from vertex/face data.
"""
import math

from OpenGL.GL import *
from OpenGL.GLU import *

from glyphviz_core.geometry_data import (
    GEO_CUBE_WIRE, GEO_CUBE, GEO_SPHERE_WIRE, GEO_SPHERE, GEO_CONE_WIRE,
    GEO_CONE, GEO_TORUS_WIRE, GEO_TORUS, GEO_DODECA_WIRE, GEO_DODECA,
    GEO_OCTA_WIRE, GEO_OCTA, GEO_TETRA_WIRE, GEO_TETRA, GEO_ICOSA_WIRE,
    GEO_ICOSA, GEO_PIN, GEO_PIN_WIRE, GEO_CYLINDER_WIRE, GEO_CYLINDER,
    GEO_GRID_WIRE, GEO_GRID, GEO_POINT, GEO_MESH, GEO_CIRCLE, GEO_CROSS,
    GEO_STAR, GEO_COUNT, GEO_NAMES,
    GEO_CUBE_INTERIOR, GEO_SPHERE_INTERIOR,
    GEO_CYLINDER_INTERIOR, GEO_CYLINDER_INTERIOR_OPEN,
    GEO_RING, GEO_RING_WIRE, RATIO_SHAPED_GEOMETRIES, ring_dims,
    WIRE_TO_SOLID, TORUS_DEFAULT_RATIO, torus_radii, CYLINDER_RADIUS_RATIO,
    CYLINDER_HEIGHT_RATIO, ROD_RADIUS_FACTOR, ROD_HEIGHT_FACTOR,
    GRID_HALF_EXTENT, PIN_HEIGHT, PIN_RADIUS,
)
from glyphviz_core.mesh_loader import MeshData

_WIRE_IDS = frozenset({
    GEO_CUBE_WIRE, GEO_SPHERE_WIRE, GEO_CONE_WIRE, GEO_TORUS_WIRE,
    GEO_DODECA_WIRE, GEO_OCTA_WIRE, GEO_TETRA_WIRE, GEO_ICOSA_WIRE,
    GEO_PIN_WIRE, GEO_CYLINDER_WIRE, GEO_GRID_WIRE, GEO_RING_WIRE,
})


# ---------------------------------------------------------------------------
# Vector helpers (plain tuples — no numpy needed)
# ---------------------------------------------------------------------------

def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])

def _sub(a, b):
    return (a[0]-b[0], a[1]-b[1], a[2]-b[2])

def _dot(a, b):
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]

def _norm(v):
    d = math.sqrt(_dot(v, v))
    return (v[0]/d, v[1]/d, v[2]/d) if d > 1e-12 else (0.0, 1.0, 0.0)

def _vert_uv(v):
    """Spherical UV from a vertex on (or near) the unit sphere.
    u = normalised longitude, v = normalised latitude."""
    x, y, z = v
    L = math.sqrt(x*x + y*y + z*z)
    if L < 1e-12:
        return 0.5, 0.5
    nx, ny, nz = x/L, y/L, z/L
    u = 0.5 + math.atan2(nx, nz) / (2.0 * math.pi)
    vt = 0.5 + math.asin(max(-1.0, min(1.0, ny))) / math.pi
    return u, vt

def _face_normal(v0, v1, v2):
    return _norm(_cross(_sub(v1, v0), _sub(v2, v0)))

def _outward_tri(verts, a, b, c):
    """Return (a,b,c) or (a,c,b) so the face normal points away from origin."""
    n = _face_normal(verts[a], verts[b], verts[c])
    return (a, b, c) if _dot(n, verts[a]) >= 0 else (a, c, b)


# ---------------------------------------------------------------------------
# Polyhedron data — computed once at module load
# ---------------------------------------------------------------------------

def _build_triangular_faces(verts):
    """Find all outward-CCW triangular faces of a convex polyhedron on the unit sphere."""
    n = len(verts)
    # find edge length²: smallest nonzero pairwise distance²
    dists = [
        sum((verts[i][k]-verts[j][k])**2 for k in range(3))
        for i in range(n) for j in range(i+1, n)
    ]
    edge_d2 = min(dists)
    tol = edge_d2 * 0.06

    adj = [set() for _ in range(n)]
    idx = 0
    for i in range(n):
        for j in range(i+1, n):
            if abs(dists[idx] - edge_d2) < tol:
                adj[i].add(j)
                adj[j].add(i)
            idx += 1

    faces = []
    for i in range(n):
        for j in sorted(adj[i]):
            if j <= i:
                continue
            for k in sorted(adj[i] & adj[j]):
                if k <= j:
                    continue
                faces.append(_outward_tri(verts, i, j, k))
    return faces


def _build_pentagon_faces(verts, face_normals):
    """Build dodecahedron pentagon faces from icosahedron face-normal directions."""
    faces = []
    for fn in face_normals:
        # 5 vertices with highest projection onto fn
        ranked = sorted(range(len(verts)), key=lambda i: -_dot(fn, verts[i]))
        fv = ranked[:5]

        # Project onto face plane and sort by angle for CCW order
        cx = sum(verts[v][0] for v in fv) / 5
        cy = sum(verts[v][1] for v in fv) / 5
        cz = sum(verts[v][2] for v in fv) / 5
        centroid = (cx, cy, cz)

        first = verts[fv[0]]
        u = _norm(_sub(first, centroid))
        w = _cross(fn, u)  # perp in face plane

        def _angle(vi):
            p = _sub(verts[vi], centroid)
            return math.atan2(_dot(p, w), _dot(p, u))

        fv.sort(key=_angle)

        # Ensure CCW winding
        n = _face_normal(verts[fv[0]], verts[fv[1]], verts[fv[2]])
        if _dot(n, fn) < 0:
            fv.reverse()
        faces.append(tuple(fv))
    return faces


# ---- Tetrahedron (4 verts on unit sphere) -----------------------------------
_s8 = math.sqrt(8/9)
_s2 = math.sqrt(2/9)
_s6 = math.sqrt(2/3)
_TETRA_VERTS = [
    (0.0,   0.0,   1.0),
    (_s8,   0.0,  -1/3),
    (-_s2,  _s6,  -1/3),
    (-_s2, -_s6,  -1/3),
]
_TETRA_FACES = [_outward_tri(_TETRA_VERTS, *t) for t in
                [(0,1,2), (0,2,3), (0,3,1), (1,3,2)]]

# ---- Octahedron (6 verts on unit sphere) ------------------------------------
_OCTA_VERTS = [
    (1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1),
]
_OCTA_FACES = _build_triangular_faces(_OCTA_VERTS)

# ---- Icosahedron (12 verts on unit sphere) -----------------------------------
_phi = (1 + math.sqrt(5)) / 2
_icosa_n = math.sqrt(1 + _phi*_phi)
_ICOSA_VERTS = [
    (0,         1/_icosa_n,  _phi/_icosa_n),
    (0,        -1/_icosa_n,  _phi/_icosa_n),
    (0,         1/_icosa_n, -_phi/_icosa_n),
    (0,        -1/_icosa_n, -_phi/_icosa_n),
    (1/_icosa_n,  _phi/_icosa_n, 0),
    (-1/_icosa_n, _phi/_icosa_n, 0),
    (1/_icosa_n, -_phi/_icosa_n, 0),
    (-1/_icosa_n,-_phi/_icosa_n, 0),
    (_phi/_icosa_n, 0,  1/_icosa_n),
    (-_phi/_icosa_n, 0, 1/_icosa_n),
    (_phi/_icosa_n, 0, -1/_icosa_n),
    (-_phi/_icosa_n, 0,-1/_icosa_n),
]
_ICOSA_FACES = _build_triangular_faces(_ICOSA_VERTS)

# ---- Dodecahedron (20 verts on unit sphere) ----------------------------------
_inv_phi = 1.0 / _phi
_dodeca_scale = 1.0 / math.sqrt(3.0)
_DODECA_VERTS = [v for v in [
    (_s3x * _dodeca_scale, _s3y * _dodeca_scale, _s3z * _dodeca_scale)
    for (_s3x, _s3y, _s3z) in [
        ( 1,  1,  1), ( 1,  1, -1), ( 1, -1,  1), ( 1, -1, -1),
        (-1,  1,  1), (-1,  1, -1), (-1, -1,  1), (-1, -1, -1),
        (0, _phi, _inv_phi), (0, _phi, -_inv_phi),
        (0, -_phi, _inv_phi), (0, -_phi, -_inv_phi),
        (_inv_phi, 0,  _phi), (_inv_phi, 0, -_phi),
        (-_inv_phi, 0, _phi), (-_inv_phi, 0, -_phi),
        (_phi,  _inv_phi, 0), (_phi, -_inv_phi, 0),
        (-_phi,  _inv_phi, 0), (-_phi, -_inv_phi, 0),
    ]
]]
# Face normals = icosahedron vertices (dodecahedron/icosahedron are duals)
_DODECA_FACE_NORMALS = [_norm(v) for v in _ICOSA_VERTS]
_DODECA_FACES = _build_pentagon_faces(_DODECA_VERTS, _DODECA_FACE_NORMALS)

# ---- Cube (8 verts on unit sphere) ------------------------------------------
_c = 1.0 / math.sqrt(3.0)
_CUBE_VERTS = [
    ( _c,  _c,  _c), ( _c,  _c, -_c),
    ( _c, -_c,  _c), ( _c, -_c, -_c),
    (-_c,  _c,  _c), (-_c,  _c, -_c),
    (-_c, -_c,  _c), (-_c, -_c, -_c),
]
# Quads: indices listed CCW from outside
_CUBE_QUADS = [
    ((0, 4, 6, 2), (0, 0, 1)),    # +Z, normal (0,0,1)
    ((1, 3, 7, 5), (0, 0,-1)),    # -Z
    ((0, 2, 3, 1), (1, 0, 0)),    # +X
    ((4, 5, 7, 6), (-1,0, 0)),    # -X
    ((0, 1, 5, 4), (0, 1, 0)),    # +Y
    ((2, 6, 7, 3), (0,-1, 0)),    # -Y
]
# UV corners for each quad vertex (CCW order matches _CUBE_QUADS winding)
_CUBE_UVS = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))


# ---------------------------------------------------------------------------
# Draw helpers (called inside glNewList / glEndList)
# ---------------------------------------------------------------------------

def _draw_tri_solid(verts, faces, textured: bool = False):
    glBegin(GL_TRIANGLES)
    for f in faces:
        n = _face_normal(verts[f[0]], verts[f[1]], verts[f[2]])
        glNormal3f(*n)
        for vi in f:
            if textured:
                glTexCoord2f(*_vert_uv(verts[vi]))
            glVertex3f(*verts[vi])
    glEnd()


def _draw_tri_wire(verts, faces):
    glDisable(GL_LIGHTING)
    for f in faces:
        glBegin(GL_LINE_LOOP)
        for vi in f:
            glVertex3f(*verts[vi])
        glEnd()
    glEnable(GL_LIGHTING)


def _draw_poly_solid(verts, faces, textured: bool = False):
    """Draw polygonal (pentagon) faces as triangle fans."""
    for f in faces:
        n = _face_normal(verts[f[0]], verts[f[1]], verts[f[2]])
        glNormal3f(*n)
        glBegin(GL_TRIANGLE_FAN)
        for vi in f:
            if textured:
                glTexCoord2f(*_vert_uv(verts[vi]))
            glVertex3f(*verts[vi])
        glEnd()


def _draw_poly_wire(verts, faces):
    glDisable(GL_LIGHTING)
    for f in faces:
        glBegin(GL_LINE_LOOP)
        for vi in f:
            glVertex3f(*verts[vi])
        glEnd()
    glEnable(GL_LIGHTING)


def _draw_cube(solid: bool, textured: bool = False):
    if solid:
        glBegin(GL_QUADS)
        for (quad, normal) in _CUBE_QUADS:
            glNormal3f(*normal)
            for i, vi in enumerate(quad):
                if textured:
                    glTexCoord2f(*_CUBE_UVS[i])
                glVertex3f(*_CUBE_VERTS[vi])
        glEnd()
    else:
        glDisable(GL_LIGHTING)
        for (quad, _) in _CUBE_QUADS:
            glBegin(GL_LINE_LOOP)
            for vi in quad:
                glVertex3f(*_CUBE_VERTS[vi])
            glEnd()
        glEnable(GL_LIGHTING)


# ---------------------------------------------------------------------------
# Interior variants — the shape seen from WITHIN, culled from without
# (geometry_data.INTERIOR_GEOMETRIES)
# ---------------------------------------------------------------------------

def _unlit(draw):
    """Run *draw* with lighting off, restoring whatever was there before.

    An interior surface exists to carry an image, and it must carry it at
    full brightness — the same call the World Grid's globe makes, and for the
    same reason (see viewport._draw_world_grid: "drawn unlit so the map reads
    at full brightness with no day/night shading").

    Lighting it instead is not an option worth having here. A reflection
    carries normals through the inverse transpose, which for diag(-1,1,1)
    maps a sphere's outward normal to the outward normal at the mirrored
    point — still OUTWARD, i.e. facing away from a viewer inside. Measured:
    a white interior sphere came back at 0.505 grey, exactly the ambient
    terms (0.2 global + 0.3 GL_LIGHT0) with no diffuse contribution at all,
    identical whichever way the camera faced. Flipping the normals instead
    would light it, but GL_LIGHT0's position is set with an identity
    modelview, making it an eye-space headlight — so a video would carry a
    bright patch that slid around as the viewer turned.

    glPushAttrib rather than a glIsEnabled/restore pair (the GEO_POINT
    dance below) because these builders are compiled into display lists,
    where a query would run once at COMPILE time and bake in the wrong
    answer. It also has to be a save/restore rather than a bare
    glEnable(GL_LIGHTING) at the end: the colour-ID pick pass turns lighting
    off for its whole render and relies on it staying off, and interior ids
    are not covered by the wire→solid pick substitution, so they run there
    too — re-enabling would bleed lit shading into every node picked after
    them and corrupt their ID colours.
    """
    glPushAttrib(GL_LIGHTING_BIT)
    glDisable(GL_LIGHTING)
    draw()
    glPopAttrib()


def _mirrored(draw):
    """Run *draw* reflected through the plane x = 0.

    That one reflection does two of the three things an interior surface
    needs, and does them to whatever the existing builder emits — so an
    interior variant is the same shape, tessellation and UV layout as its
    exterior twin rather than a second implementation that has to be kept in
    step with it:

      * the composite matrix's determinant goes negative, so every face's
        winding flips in window space and paintGL's GL_CULL_FACE(GL_BACK)
        keeps the INSIDE surface and discards the outside;
      * the image is mirrored in the surface's angular direction, cancelling
        the mirroring inherent in viewing any surface from behind — so text
        in a texture or video reads FORWARDS from inside. Verified by
        rendering a chiral texture: unmirrored geometry shows it reversed.

    The third — brightness — is _unlit's job; normals survive the reflection
    still pointing outward, which is why.

    Exact only for shapes with no face perpendicular to x — which covers the
    sphere and the cylinder, both surfaces of revolution about z. A cube's
    ±x faces would come back mirrored, so it gets _draw_cube_interior below.
    """
    glPushMatrix()
    glScalef(-1.0, 1.0, 1.0)
    draw()
    glPopMatrix()


# Each interior cube face as (outward axis, which way is UP on it). The four
# walls stand upright (+z up). Floor and ceiling have no intrinsic up, so they
# take OPPOSITE y — and that is not a typo. An orbit camera looking down has
# screen-up pointing away from its azimuth and one looking up has it pointing
# along; giving both faces the same y would leave one of the two 180° round
# from the other (measured). As set here, a viewer at the centre facing +y
# reads the wall ahead, the floor and the ceiling all the same way up.
_CUBE_INTERIOR_FACES = (
    (( 1.0,  0.0,  0.0), (0.0,  0.0, 1.0)),
    ((-1.0,  0.0,  0.0), (0.0,  0.0, 1.0)),
    (( 0.0,  1.0,  0.0), (0.0,  0.0, 1.0)),
    (( 0.0, -1.0,  0.0), (0.0,  0.0, 1.0)),
    (( 0.0,  0.0,  1.0), (0.0,  1.0, 0.0)),   # ceiling, looked up at
    (( 0.0,  0.0, -1.0), (0.0, -1.0, 0.0)),   # floor, looked down at
)


def _draw_cube_interior(textured: bool = False):
    """The cube's six faces turned inward, each mapping the full texture
    upright and unmirrored as seen from the centre.

    Built face by face rather than by _mirrored(_draw_cube): a single
    reflection cannot un-mirror all six faces at once — the two perpendicular
    to the mirror axis swap places without their own UVs turning over, and
    would read backwards. Here each face gets a screen-space basis for a
    viewer at the origin looking at it (right = axis x up), which lays u to
    the viewer's right and v upward and, being right-handed, winds the quad
    CCW from inside for free."""
    glBegin(GL_QUADS)
    for axis, up in _CUBE_INTERIOR_FACES:
        right = _cross(axis, up)
        # Faces point inward: the viewer is on the other side of them.
        glNormal3f(-axis[0], -axis[1], -axis[2])
        for u, v in _CUBE_UVS:
            # u,v in {0,1} → corner offsets in {-1,+1} along right/up.
            su, sv = 2.0 * u - 1.0, 2.0 * v - 1.0
            if textured:
                glTexCoord2f(u, v)
            glVertex3f(*[(axis[k] + su * right[k] + sv * up[k]) * _c
                         for k in range(3)])
    glEnd()


_TORUS_DEFAULT_MAJOR, _TORUS_DEFAULT_MINOR = torus_radii(TORUS_DEFAULT_RATIO)


def _draw_torus(solid: bool, r_major=_TORUS_DEFAULT_MAJOR, r_minor=_TORUS_DEFAULT_MINOR, rings=24, sides=16, textured: bool = False):
    tau = 2 * math.pi
    if not solid:
        glDisable(GL_LIGHTING)
        for i in range(rings):
            th = tau * i / rings
            glBegin(GL_LINE_LOOP)
            for j in range(sides):
                ph = tau * j / sides
                x = (r_major + r_minor * math.cos(ph)) * math.cos(th)
                y = (r_major + r_minor * math.cos(ph)) * math.sin(th)
                z = r_minor * math.sin(ph)
                glVertex3f(x, y, z)
            glEnd()
        for j in range(sides):
            ph = tau * j / sides
            cp, sp = math.cos(ph), math.sin(ph)
            glBegin(GL_LINE_LOOP)
            for i in range(rings):
                th = tau * i / rings
                glVertex3f((r_major+r_minor*cp)*math.cos(th),
                           (r_major+r_minor*cp)*math.sin(th),
                           r_minor*sp)
            glEnd()
        glEnable(GL_LIGHTING)
        return

    for i in range(rings):
        th0, th1 = tau*i/rings, tau*(i+1)/rings
        glBegin(GL_QUAD_STRIP)
        for j in range(sides + 1):
            ph = tau * j / sides
            cp, sp = math.cos(ph), math.sin(ph)
            for k, th in enumerate((th0, th1)):
                ct, st = math.cos(th), math.sin(th)
                if textured:
                    glTexCoord2f((i + k) / rings, j / sides)
                glNormal3f(cp*ct, cp*st, sp)
                glVertex3f((r_major+r_minor*cp)*ct, (r_major+r_minor*cp)*st, r_minor*sp)
        glEnd()


def _draw_ring(solid: bool, ratio: float = TORUS_DEFAULT_RATIO, rings=48,
               rungs=12, textured: bool = False):
    """A torus with a RECTANGULAR cross-section — a flat machined band, the
    ring an armillary sphere or a graduated dial is built from.

    Four faces, each with its own constant normal and duplicated corner
    vertices, so the edges stay crisp instead of shading smoothly round the way
    the torus's tube does. `ratio` is the radial width via `ring_dims` (the
    torus's own extents, restated as a box); the local half-height comes from
    the same number, so the default cross-section is square and the node's
    `scale_z` is what makes the band tall or thin.

    Texture rule — the reason this shape exists: **every face carries a full
    0..1 UV span of its own**, with u running around the ring and v across the
    band, rather than v walking once around the cross-section perimeter the way
    _draw_torus's does. So a strip of degree markings appears once, undistorted,
    on the outer wall AND once on the top face, and you choose which one the
    viewer reads by choosing the aspect (wide+thin = a dial read face-on;
    narrow+tall = a band read from outside). A perimeter-walking v would smear
    one image across all four faces and break it at every corner.

    Each face's u runs in the direction that reads FORWARDS from that face's
    natural viewing side — decreasing angle on the inner wall (seen from within
    the hole) and on the underside, increasing elsewhere. Equivalently: on all
    four faces (du x dv) points along the face normal, so no face is mirrored.
    tests/test_ring_geometry.py pins exactly that.
    """
    tau = 2 * math.pi
    r_out, r_in, half_h = ring_dims(ratio)
    has_hole = r_in > 1e-6

    if not solid:
        glDisable(GL_LIGHTING)
        for r, z in ((r_out, half_h), (r_out, -half_h),
                     (r_in, half_h), (r_in, -half_h)):
            if r <= 1e-6:
                continue
            glBegin(GL_LINE_LOOP)
            for i in range(rings):
                th = tau * i / rings
                glVertex3f(r * math.cos(th), r * math.sin(th), z)
            glEnd()
        for j in range(rungs):          # the cross-section, drawn as a rung
            th = tau * j / rungs
            ct, st = math.cos(th), math.sin(th)
            glBegin(GL_LINE_LOOP)
            for r, z in ((r_in, -half_h), (r_out, -half_h),
                         (r_out, half_h), (r_in, half_h)):
                glVertex3f(r * ct, r * st, z)
            glEnd()
        glEnable(GL_LIGHTING)
        return

    def tex(u, v):
        if textured:
            glTexCoord2f(u, v)

    # Outer wall — normals point away from the axis, v runs bottom to top.
    glBegin(GL_QUAD_STRIP)
    for i in range(rings + 1):
        th = tau * i / rings
        ct, st = math.cos(th), math.sin(th)
        u = i / rings
        glNormal3f(ct, st, 0.0)
        tex(u, 1.0)
        glVertex3f(r_out * ct, r_out * st, half_h)
        tex(u, 0.0)
        glVertex3f(r_out * ct, r_out * st, -half_h)
    glEnd()

    # Inner wall — normals point at the axis, so it is what you see across the
    # hole from outside and what surrounds you standing inside a large ring.
    if has_hole:
        glBegin(GL_QUAD_STRIP)
        for i in range(rings + 1):
            th = tau * i / rings
            ct, st = math.cos(th), math.sin(th)
            u = 1.0 - i / rings
            glNormal3f(-ct, -st, 0.0)
            tex(u, 0.0)
            glVertex3f(r_in * ct, r_in * st, -half_h)
            tex(u, 1.0)
            glVertex3f(r_in * ct, r_in * st, half_h)
        glEnd()

    # Top and bottom annulus faces — v = 0 at the outer rim on both.
    for sign in (1.0, -1.0):
        glNormal3f(0.0, 0.0, sign)
        glBegin(GL_QUAD_STRIP)
        for i in range(rings + 1):
            th = tau * i / rings
            ct, st = math.cos(th), math.sin(th)
            u = i / rings if sign > 0 else 1.0 - i / rings
            near_r, near_v = (r_in, 1.0) if sign > 0 else (r_out, 0.0)
            far_r, far_v = (r_out, 0.0) if sign > 0 else (r_in, 1.0)
            tex(u, near_v)
            glVertex3f(near_r * ct, near_r * st, sign * half_h)
            tex(u, far_v)
            glVertex3f(far_r * ct, far_r * st, sign * half_h)
        glEnd()


def _new_quadric(wire: bool, textured: bool = False):
    q = gluNewQuadric()
    gluQuadricNormals(q, GLU_SMOOTH)
    if wire:
        gluQuadricDrawStyle(q, GLU_LINE)
    if textured and not wire:
        gluQuadricTexture(q, GL_TRUE)
    return q


def _draw_cylinder(solid: bool, r=CYLINDER_RADIUS_RATIO, h=CYLINDER_HEIGHT_RATIO, slices=16, textured: bool = False,
                   caps: bool = True):
    """The tube, plus (unless *caps* is False) a disk closing each end.

    Capless is only meaningful on the interior variant — from outside, an
    open tube just shows you its far inner wall through the hole — so
    everything else leaves the default alone."""
    q = _new_quadric(not solid, textured=textured and solid)
    if not solid:
        glDisable(GL_LIGHTING)
    glPushMatrix()
    glTranslatef(0.0, 0.0, -h/2.0)
    gluCylinder(q, r, r, h, slices, 1)
    if solid and caps:
        glPushMatrix()
        glRotatef(180.0, 1.0, 0.0, 0.0)
        gluDisk(q, 0.0, r, slices, 1)
        glPopMatrix()
        glTranslatef(0.0, 0.0, h)
        gluDisk(q, 0.0, r, slices, 1)
    glPopMatrix()
    if not solid:
        glEnable(GL_LIGHTING)
    gluDeleteQuadric(q)


def _draw_cone(solid: bool, r=1.0, h=2.0, slices=16, textured: bool = False):
    q = _new_quadric(not solid, textured=textured and solid)
    if not solid:
        glDisable(GL_LIGHTING)
    glPushMatrix()
    glTranslatef(0.0, 0.0, -h/2.0)
    gluCylinder(q, r, 0.0, h, slices, 1)
    if solid:
        glPushMatrix()
        glRotatef(180.0, 1.0, 0.0, 0.0)
        gluDisk(q, 0.0, r, slices, 1)
        glPopMatrix()
    glPopMatrix()
    if not solid:
        glEnable(GL_LIGHTING)
    gluDeleteQuadric(q)


def _draw_sphere(solid: bool, r=1.0, slices=16, stacks=12, textured: bool = False):
    q = _new_quadric(not solid, textured=textured and solid)
    if not solid:
        glDisable(GL_LIGHTING)
    gluSphere(q, r, slices, stacks)
    if not solid:
        glEnable(GL_LIGHTING)
    gluDeleteQuadric(q)


def _pin_bands(dome_stacks=4):
    """The pin's meridian, as (lower, upper) ring pairs bottom to top; each
    ring is (radius, z, normal_radial, normal_z).

    The rim appears in two consecutive bands carrying two different normals —
    the cone's and the dome's — because the surface genuinely creases there
    and a single averaged normal would smear the join. The two rings sit at
    the same (radius, z), so the crease costs no extra geometry.
    """
    h, r = PIN_HEIGHT, PIN_RADIUS
    # Outward normal of a cone whose apex is at the origin: the surface widens
    # as it rises, so it faces out AND DOWN — (h, -r) normalised, in
    # (radial, z). Constant over the whole lateral surface, apex included.
    n = math.hypot(h, r)
    cone_nr, cone_nz = h / n, -r / n
    yield (0.0, 0.0, cone_nr, cone_nz), (r, h, cone_nr, cone_nz)
    lower = (r, h, 1.0, 0.0)                  # the rim again, dome-side normal
    for j in range(1, dome_stacks + 1):
        ph = (math.pi / 2.0) * j / dome_stacks
        cp, sp = math.cos(ph), math.sin(ph)
        upper = (r * cp, h + r * sp, cp, sp)
        yield lower, upper
        lower = upper


def _pin_outline(dome_stacks=4):
    """(radius, z) profile points, apex to pole — the meridian the wire pin
    traces. Read off the same bands the solid is built from, so the two are
    the same shape by construction rather than by matched edits."""
    points = [(0.0, 0.0)]
    for _lower, upper in _pin_bands(dome_stacks):
        if upper[:2] != points[-1]:
            points.append(upper[:2])
    return points


def _pin_uv(u: float, z: float) -> tuple[float, float]:
    """Pin texture mapping: u wraps once around the axis, v runs 0 at the tip
    to 1 at the top of the dome — continuous across the cone/dome junction,
    unlike two separately-textured quadrics would be."""
    return u, z / (PIN_HEIGHT + PIN_RADIUS)


def _draw_pin(solid: bool, textured: bool = False, slices=12, dome_stacks=4):
    """Pushpin: a 10:1 cone standing on its apex at the local origin, shaft
    rising along +Z, capped by a dome — ANTz's "ice-cream cone" shape
    (DrawPinDL, npgeometry.c:493) in both proportion and placement, and
    matching GEO_CYLINDER/GEO_CONE's own local-Z-axis convention so an
    unrotated pin stands upright in the Z-up world.

    Built by hand rather than from GLU quadrics, which is what closes the two
    holes the previous version had: gluCylinder draws a *lateral surface only*
    — no end caps, ever — so a pin made from one is open at both ends unless
    the caller adds gluDisks (as _draw_cone and _draw_cylinder do, and this
    shape did not). Here the cone tapers to a genuine apex, so the bottom
    needs no cap at all.

    Only the UPPER half of the ball is built. Its rim is *exactly* the cone's
    base circle — same radius, same z — so the dome IS the cone's cap: the
    junction is watertight with no base disk, and the lower hemisphere would
    be sealed inside the cone where nothing could ever see it. That halves the
    ball's facets and drops two disks, for a glyph that is strictly more
    closed than the one it replaces.
    """
    tau = math.pi * 2.0

    if not solid:
        glDisable(GL_LIGHTING)
        outline = _pin_outline(dome_stacks)
        # Meridians: one unbroken line from the apex, out to the rim, then up
        # over the dome to the pole — so the wire pin reads as one silhouette
        # rather than a cone and a ball that happen to touch.
        for i in range(slices):
            th = tau * i / slices
            ct, st = math.cos(th), math.sin(th)
            glBegin(GL_LINE_STRIP)
            for rad, z in outline:
                glVertex3f(rad * ct, rad * st, z)
            glEnd()
        # Latitudes: the shared rim, then each dome band. The apex and the
        # pole are points, not rings, so both ends are skipped.
        for rad, z in outline[1:-1]:
            glBegin(GL_LINE_LOOP)
            for i in range(slices):
                th = tau * i / slices
                glVertex3f(rad * math.cos(th), rad * math.sin(th), z)
            glEnd()
        glEnable(GL_LIGHTING)
        return

    # Solid: one quad strip per band, walking the meridian bottom to top. The
    # first band degenerates to triangles at the apex, which is what a cone
    # tip is. Upper-then-lower vertex order per step gives outward-CCW
    # winding, so the shape survives paintGL's GL_CULL_FACE(GL_BACK).
    for lower, upper in _pin_bands(dome_stacks):
        glBegin(GL_QUAD_STRIP)
        for i in range(slices + 1):
            u = i / slices
            th = tau * u
            ct, st = math.cos(th), math.sin(th)
            for rad, z, nr, nz in (upper, lower):
                if textured:
                    glTexCoord2f(*_pin_uv(u, z))
                glNormal3f(nr * ct, nr * st, nz)
                glVertex3f(rad * ct, rad * st, z)
        glEnd()


def _draw_grid_wire(segments=8):
    """Graph-paper-style lattice of lines spanning the square."""
    glDisable(GL_LIGHTING)
    s = GRID_HALF_EXTENT
    glBegin(GL_LINES)
    for i in range(segments + 1):
        t = -s + (2.0 * s) * i / segments
        glVertex3f(t, -s, 0.0)
        glVertex3f(t,  s, 0.0)
        glVertex3f(-s, t, 0.0)
        glVertex3f( s, t, 0.0)
    glEnd()
    glEnable(GL_LIGHTING)


def _draw_grid_solid(textured: bool = False):
    """Flat square plate, drawn double-sided (opposing normals on each face)
    so it reads correctly from either side, matching ANTz's default Grid shape."""
    s = GRID_HALF_EXTENT
    _corners = (
        ((-s, -s), (0.0, 0.0)),
        (( s, -s), (1.0, 0.0)),
        (( s,  s), (1.0, 1.0)),
        ((-s,  s), (0.0, 1.0)),
    )
    glBegin(GL_QUADS)
    glNormal3f(0.0, 0.0, 1.0)
    for (x, y), (u, v) in _corners:
        if textured:
            glTexCoord2f(u, v)
        glVertex3f(x, y, 0.0)
    glNormal3f(0.0, 0.0, -1.0)
    for (x, y), (u, v) in reversed(_corners):
        if textured:
            glTexCoord2f(u, v)
        glVertex3f(x, y, 0.0)
    glEnd()


def _flat_marker_uv(x: float, y: float) -> tuple[float, float]:
    """Map a flat XY marker vertex to texture space. Circle/Cross/Star are all
    built on a unit radius, so the same [-1,1]^2 -> [0,1]^2 mapping the Grid
    uses across its own square applies unchanged -- which means the texture is
    *cropped* to the glyph's silhouette (a Circle shows a circular crop of the
    image, a Cross the image's central strips) rather than stretched to fit."""
    return (x + 1.0) * 0.5, (y + 1.0) * 0.5


def _flat_double_sided_fan(points: list[tuple[float, float]],
                           textured: bool = False):
    """Shared helper for Circle/Star: triangle-fan a flat, star-shaped (i.e.
    every boundary point visible from the center) 2-D outline from the
    origin, drawn double-sided like _draw_grid_solid so it reads correctly
    from either side."""
    loop = points + [points[0]]
    glBegin(GL_TRIANGLE_FAN)
    glNormal3f(0.0, 0.0, 1.0)
    if textured:
        glTexCoord2f(0.5, 0.5)
    glVertex3f(0.0, 0.0, 0.0)
    for x, y in loop:
        if textured:
            glTexCoord2f(*_flat_marker_uv(x, y))
        glVertex3f(x, y, 0.0)
    glEnd()
    glBegin(GL_TRIANGLE_FAN)
    glNormal3f(0.0, 0.0, -1.0)
    if textured:
        glTexCoord2f(0.5, 0.5)
    glVertex3f(0.0, 0.0, 0.0)
    for x, y in reversed(loop):
        if textured:
            glTexCoord2f(*_flat_marker_uv(x, y))
        glVertex3f(x, y, 0.0)
    glEnd()


def _draw_circle(segments=24, textured: bool = False):
    """Flat circular disc in the XY plane -- a Point glyph with a real,
    lit/scaled outline instead of a fixed-pixel GL_POINTS sprite."""
    pts = [(math.cos(2.0 * math.pi * i / segments),
            math.sin(2.0 * math.pi * i / segments)) for i in range(segments)]
    _flat_double_sided_fan(pts, textured)


def _draw_star(points=5, inner_ratio=0.382, textured: bool = False):
    """Flat N-pointed star outline in the XY plane (default inner_ratio
    approximates a classic regular 5-point star)."""
    verts = []
    for i in range(points * 2):
        r = 1.0 if i % 2 == 0 else inner_ratio
        a = math.pi / 2.0 + i * math.pi / points
        verts.append((r * math.cos(a), r * math.sin(a)))
    _flat_double_sided_fan(verts, textured)


def _draw_cross(half_width=0.3, textured: bool = False):
    """Flat plus-sign ("+") marker: two perpendicular bars in the XY plane,
    each drawn double-sided like _draw_grid_solid. Built from two quads
    rather than one concave outline since legacy GL_POLYGON requires convex
    geometry."""
    s, w = 1.0, half_width
    bars = (
        ((-s, -w), (s, -w), (s, w), (-s, w)),
        ((-w, -s), (w, -s), (w, s), (-w, s)),
    )
    glBegin(GL_QUADS)
    glNormal3f(0.0, 0.0, 1.0)
    for bar in bars:
        for x, y in bar:
            if textured:
                glTexCoord2f(*_flat_marker_uv(x, y))
            glVertex3f(x, y, 0.0)
    glNormal3f(0.0, 0.0, -1.0)
    for bar in bars:
        for x, y in reversed(bar):
            if textured:
                glTexCoord2f(*_flat_marker_uv(x, y))
            glVertex3f(x, y, 0.0)
    glEnd()


# ---------------------------------------------------------------------------
# GeoRenderer — compiles all shapes into OpenGL display lists
# ---------------------------------------------------------------------------

class GeoRenderer:
    def __init__(self):
        self._lists: dict[int, int] = {}
        self._tex_lists: dict[int, int] = {}
        self._ratio_lists: dict[tuple, int] = {}   # (geo_id, textured, rounded ratio) -> display list
        self._mesh_lists: dict[int, int] = {}   # mesh_id -> display list
        self._mesh_uv: dict[int, bool] = {}     # mesh_id -> list carries texture coords
        self._ready = False

    def setup(self):
        """Call once from within an active OpenGL context."""
        if self._ready:
            return
        glEnable(GL_NORMALIZE)

        _DISPATCH = {
            GEO_CUBE:          lambda: _draw_cube(True),
            GEO_CUBE_WIRE:     lambda: _draw_cube(False),
            GEO_SPHERE:        lambda: _draw_sphere(True),
            GEO_SPHERE_WIRE:   lambda: _draw_sphere(False),
            GEO_CONE:          lambda: _draw_cone(True),
            GEO_CONE_WIRE:     lambda: _draw_cone(False),
            GEO_CYLINDER:      lambda: _draw_cylinder(True),
            GEO_CYLINDER_WIRE: lambda: _draw_cylinder(False),
            GEO_GRID:          lambda: _draw_grid_solid(),
            GEO_GRID_WIRE:     lambda: _draw_grid_wire(),
            GEO_PIN:           lambda: _draw_pin(True),
            GEO_PIN_WIRE:      lambda: _draw_pin(False),
            GEO_TETRA:         lambda: _draw_tri_solid(_TETRA_VERTS, _TETRA_FACES),
            GEO_TETRA_WIRE:    lambda: _draw_tri_wire(_TETRA_VERTS, _TETRA_FACES),
            GEO_OCTA:          lambda: _draw_tri_solid(_OCTA_VERTS, _OCTA_FACES),
            GEO_OCTA_WIRE:     lambda: _draw_tri_wire(_OCTA_VERTS, _OCTA_FACES),
            GEO_ICOSA:         lambda: _draw_tri_solid(_ICOSA_VERTS, _ICOSA_FACES),
            GEO_ICOSA_WIRE:    lambda: _draw_tri_wire(_ICOSA_VERTS, _ICOSA_FACES),
            GEO_DODECA:        lambda: _draw_poly_solid(_DODECA_VERTS, _DODECA_FACES),
            GEO_DODECA_WIRE:   lambda: _draw_poly_wire(_DODECA_VERTS, _DODECA_FACES),
            GEO_CIRCLE:        lambda: _draw_circle(),
            GEO_CROSS:         lambda: _draw_cross(),
            GEO_STAR:          lambda: _draw_star(),
            GEO_CUBE_INTERIOR:          lambda: _unlit(_draw_cube_interior),
            GEO_SPHERE_INTERIOR:        lambda: _unlit(
                lambda: _mirrored(lambda: _draw_sphere(True))),
            GEO_CYLINDER_INTERIOR:      lambda: _unlit(
                lambda: _mirrored(lambda: _draw_cylinder(True))),
            GEO_CYLINDER_INTERIOR_OPEN: lambda: _unlit(
                lambda: _mirrored(lambda: _draw_cylinder(True, caps=False))),
        }

        # Textured variants are also compiled into display lists, same as the
        # untextured shapes above: glTexCoord2f / gluQuadricTexture calls are
        # ordinary GL commands and get captured into the list just like
        # glVertex3f/glNormal3f — the texture *binding* stays outside the
        # list and is set per-node in draw() via glBindTexture before
        # glCallList, so one compiled list is shared across every node using
        # that geometry, whatever texture each one binds.
        _TEX_DISPATCH = {
            GEO_CUBE:     lambda: _draw_cube(True, True),
            GEO_SPHERE:   lambda: _draw_sphere(True, textured=True),
            GEO_CONE:     lambda: _draw_cone(True, textured=True),
            GEO_CYLINDER: lambda: _draw_cylinder(True, textured=True),
            GEO_GRID:     lambda: _draw_grid_solid(True),
            GEO_PIN:      lambda: _draw_pin(True, True),
            GEO_TETRA:    lambda: _draw_tri_solid(_TETRA_VERTS, _TETRA_FACES, True),
            GEO_OCTA:     lambda: _draw_tri_solid(_OCTA_VERTS, _OCTA_FACES, True),
            GEO_ICOSA:    lambda: _draw_tri_solid(_ICOSA_VERTS, _ICOSA_FACES, True),
            GEO_DODECA:   lambda: _draw_poly_solid(_DODECA_VERTS, _DODECA_FACES, True),
            GEO_CIRCLE:   lambda: _draw_circle(textured=True),
            GEO_CROSS:    lambda: _draw_cross(textured=True),
            GEO_STAR:     lambda: _draw_star(textured=True),
            GEO_CUBE_INTERIOR:          lambda: _unlit(
                lambda: _draw_cube_interior(textured=True)),
            GEO_SPHERE_INTERIOR:        lambda: _unlit(
                lambda: _mirrored(lambda: _draw_sphere(True, textured=True))),
            GEO_CYLINDER_INTERIOR:      lambda: _unlit(
                lambda: _mirrored(lambda: _draw_cylinder(True, textured=True))),
            GEO_CYLINDER_INTERIOR_OPEN: lambda: _unlit(
                lambda: _mirrored(
                    lambda: _draw_cylinder(True, textured=True, caps=False))),
        }

        for geo_id in range(GEO_COUNT):
            if geo_id == GEO_POINT:
                continue
            fn = _DISPATCH.get(geo_id)
            if fn is None:
                # RATIO_SHAPED_GEOMETRIES (the torus and the flat ring, wire
                # and solid) are deliberately absent: their shape (not just
                # size) depends on each node's own `ratio`, so they're compiled
                # lazily per distinct ratio in draw() instead of baked into one
                # fixed-shape list here.
                continue
            dl = glGenLists(1)
            glNewList(dl, GL_COMPILE)
            try:
                fn()
            except Exception:
                _draw_sphere(True)
            glEndList()
            self._lists[geo_id] = dl

        for geo_id, fn in _TEX_DISPATCH.items():
            dl = glGenLists(1)
            glNewList(dl, GL_COMPILE)
            try:
                fn()
            except Exception:
                _draw_sphere(True, textured=True)
            glEndList()
            self._tex_lists[geo_id] = dl

        self._ready = True

    def register_mesh(self, mesh_id: int, mesh: MeshData) -> None:
        """Compile *mesh* (already normalized to radius ~1 by mesh_loader)
        into a display list addressable by mesh_id. Must be called with an
        active GL context. Replaces any previous list for the same id.

        A mesh that carries UVs gets its texture coordinates baked into the
        same list rather than a separate textured variant: glTexCoord2f is
        simply ignored while GL_TEXTURE_2D is disabled, so one list serves
        both the untextured and textured draw. (The built-in geometries need
        the _lists/_tex_lists pair because their textured forms differ in
        tessellation, not just in having coordinates.)"""
        old = self._mesh_lists.pop(mesh_id, None)
        if old:
            glDeleteLists(old, 1)
        uvs = mesh.uvs
        dl = glGenLists(1)
        glNewList(dl, GL_COMPILE)
        # Normals come from the mesh per CORNER when the import worked out
        # its creases (mesh_loader._crease_normals), so a cube's corners stay
        # square instead of shading like a beach ball; `normal_for` falls back
        # to the smoothed per-vertex normal when it didn't.
        glBegin(GL_TRIANGLES)
        for fi, face in enumerate(mesh.faces):
            for k, vi in enumerate(face):
                n = mesh.normal_for(fi, k, vi)
                v = mesh.vertices[vi]
                glNormal3f(float(n[0]), float(n[1]), float(n[2]))
                if uvs is not None:
                    glTexCoord2f(float(uvs[vi][0]), float(uvs[vi][1]))
                glVertex3f(float(v[0]), float(v[1]), float(v[2]))
        glEnd()
        glEndList()
        self._mesh_lists[mesh_id] = dl
        self._mesh_uv[mesh_id] = uvs is not None

    def ensure_ratio_list(self, geo_id: int, textured: bool, ratio: float) -> int:
        """Return (compiling on first use) the display list for one of the
        RATIO_SHAPED_GEOMETRIES — a torus or a flat ring — at this node's
        `ratio`. Each node may set its own (major/minor radius proportions for
        the torus, radial band width for the ring), so — unlike the other
        glyphs — the shape can't be baked into one fixed-shape list at setup()
        time; instead one list is cached per distinct (quantized) ratio
        actually seen, and reused by every node/frame sharing that ratio.

        Note the ring's HEIGHT is deliberately not part of the key: it rides on
        the node's `scale_z` through glScalef, outside the compiled geometry,
        which is what keeps this cache one-dimensional.

        Ratio is a proportion of the overall radius, quantized to 1% steps
        here so the cache stays bounded (~100 lists per geo/textured pair)
        even when a Channels animation sweeps ratio continuously — nothing
        evicts these lists, and a compiled one may be referenced by the
        retained scene display list, so they can never be freed. 1% of a
        glyph's radius is well under a pixel of tube thickness at normal
        zoom. The geometry is built from the quantized value, so every node
        landing in a bucket renders identically to the list it shares.

        Kept separate from draw() so callers about to compile their own
        display list (the viewport's retained scene list) can pre-warm every
        ratio first — glNewList must never nest, so the lazy compile here would
        be an invalid operation if it fired mid-bake."""
        quantized = round(ratio, 2)
        key = (geo_id, textured, quantized)
        dl = self._ratio_lists.get(key)
        if dl is None:
            dl = glGenLists(1)
            glNewList(dl, GL_COMPILE)
            if geo_id in (GEO_RING, GEO_RING_WIRE):
                _draw_ring(geo_id == GEO_RING, quantized, textured=textured)
            else:
                r_major, r_minor = torus_radii(quantized)
                _draw_torus(geo_id == GEO_TORUS, r_major, r_minor,
                            textured=textured)
            glEndList()
            self._ratio_lists[key] = dl
        return dl

    def draw(self, geo_id: int, rx: float, ry: float, rz: float,
             ratio: float = TORUS_DEFAULT_RATIO, gl_tex_name: int = 0,
             mesh_id: int = 0):
        if not self._ready:
            return
        if geo_id == GEO_MESH:
            dl = self._mesh_lists.get(mesh_id)
            if dl:
                # Imported files can't be trusted to share the procedural
                # shapes' outward-CCW winding convention (see _outward_tri
                # above), so skip the back-face cull that relies on it.
                glDisable(GL_CULL_FACE)
                # Only a mesh whose file carried UVs can be textured: with no
                # coordinates every vertex would inherit whatever texcoord was
                # current, smearing one texel over the whole model -- visibly
                # worse than the flat node color, so leave that mesh untextured.
                mesh_tex = gl_tex_name > 0 and self._mesh_uv.get(mesh_id, False)
                if mesh_tex:
                    glEnable(GL_TEXTURE_2D)
                    glBindTexture(GL_TEXTURE_2D, gl_tex_name)
                glPushMatrix()
                glScalef(rx, ry, rz)
                glCallList(dl)
                glPopMatrix()
                if mesh_tex:
                    glBindTexture(GL_TEXTURE_2D, 0)
                    glDisable(GL_TEXTURE_2D)
                glEnable(GL_CULL_FACE)
                return
            geo_id = GEO_SPHERE   # no mesh loaded yet — fall back like other unknown ids
        if geo_id == GEO_POINT:
            # Points have no orientation/extent to stretch, and callers always
            # pass rx=ry=rz=1 here (node scale is already baked into the
            # modelview matrix, which a GL_POINTS sprite's pixel size ignores)
            # -- so scale can't drive point size. Use `ratio` instead, with
            # the same ratio*20 convention as Link/Plot line width, so it's
            # the one control that actually resizes a Point glyph on screen.
            # Restore whatever lighting state we found (rather than forcing
            # it back on) -- callers like the color-ID pick pass disable
            # lighting for their whole render and rely on it staying off;
            # GEO_POINT isn't covered by the wire->solid pick substitution,
            # so it's the one geometry that runs during picking too, and
            # force-enabling here was bleeding lit shading into every node
            # drawn afterward in that pass, corrupting their flat ID colors.
            was_lit = glIsEnabled(GL_LIGHTING)
            if was_lit:
                glDisable(GL_LIGHTING)
            glPointSize(max(2.0, ratio * 20.0))
            glBegin(GL_POINTS)
            glVertex3f(0.0, 0.0, 0.0)
            glEnd()
            glPointSize(1.0)
            if was_lit:
                glEnable(GL_LIGHTING)
            return

        textured = gl_tex_name > 0 and geo_id not in _WIRE_IDS

        if geo_id in RATIO_SHAPED_GEOMETRIES:
            dl = self.ensure_ratio_list(geo_id, textured, ratio)
            if textured:
                glEnable(GL_TEXTURE_2D)
                glBindTexture(GL_TEXTURE_2D, gl_tex_name)
            glPushMatrix()
            glScalef(rx, ry, rz)
            glCallList(dl)
            glPopMatrix()
            if textured:
                glBindTexture(GL_TEXTURE_2D, 0)
                glDisable(GL_TEXTURE_2D)
            return

        if textured:
            dl = self._tex_lists.get(geo_id)
            if dl is not None:
                glEnable(GL_TEXTURE_2D)
                glBindTexture(GL_TEXTURE_2D, gl_tex_name)
                glPushMatrix()
                glScalef(rx, ry, rz)
                glCallList(dl)
                glPopMatrix()
                glBindTexture(GL_TEXTURE_2D, 0)
                glDisable(GL_TEXTURE_2D)
                return

        dl = self._lists.get(geo_id, self._lists.get(GEO_SPHERE))
        if dl:
            glPushMatrix()
            glScalef(rx, ry, rz)
            glCallList(dl)
            glPopMatrix()
