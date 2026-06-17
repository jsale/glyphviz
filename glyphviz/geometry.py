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

# IDs match ANTz kNPgeo* enum
GEO_CUBE_WIRE      = 0
GEO_CUBE           = 1
GEO_SPHERE_WIRE    = 2
GEO_SPHERE         = 3
GEO_CONE_WIRE      = 4
GEO_CONE           = 5
GEO_TORUS_WIRE     = 6
GEO_TORUS          = 7
GEO_DODECA_WIRE    = 8
GEO_DODECA         = 9
GEO_OCTA_WIRE      = 10
GEO_OCTA           = 11
GEO_TETRA_WIRE     = 12
GEO_TETRA          = 13
GEO_ICOSA_WIRE     = 14
GEO_ICOSA          = 15
GEO_PIN            = 16
GEO_PIN_WIRE       = 17
GEO_CYLINDER_WIRE  = 18
GEO_CYLINDER       = 19
GEO_GRID_WIRE      = 20
GEO_GRID           = 21
GEO_POINT          = 22
GEO_COUNT          = 23

GEO_NAMES = {
    GEO_CUBE_WIRE:     "Cube Wire",
    GEO_CUBE:          "Cube",
    GEO_SPHERE_WIRE:   "Sphere Wire",
    GEO_SPHERE:        "Sphere",
    GEO_CONE_WIRE:     "Cone Wire",
    GEO_CONE:          "Cone",
    GEO_TORUS_WIRE:    "Torus Wire",
    GEO_TORUS:         "Torus",
    GEO_DODECA_WIRE:   "Dodecahedron Wire",
    GEO_DODECA:        "Dodecahedron",
    GEO_OCTA_WIRE:     "Octahedron Wire",
    GEO_OCTA:          "Octahedron",
    GEO_TETRA_WIRE:    "Tetrahedron Wire",
    GEO_TETRA:         "Tetrahedron",
    GEO_ICOSA_WIRE:    "Icosahedron Wire",
    GEO_ICOSA:         "Icosahedron",
    GEO_PIN:           "Pin",
    GEO_PIN_WIRE:      "Pin Wire",
    GEO_CYLINDER_WIRE: "Cylinder Wire",
    GEO_CYLINDER:      "Cylinder",
    GEO_GRID_WIRE:     "Grid Wire",
    GEO_GRID:          "Grid",
    GEO_POINT:         "Point",
}

_WIRE_IDS = frozenset({
    GEO_CUBE_WIRE, GEO_SPHERE_WIRE, GEO_CONE_WIRE, GEO_TORUS_WIRE,
    GEO_DODECA_WIRE, GEO_OCTA_WIRE, GEO_TETRA_WIRE, GEO_ICOSA_WIRE,
    GEO_PIN_WIRE, GEO_CYLINDER_WIRE, GEO_GRID_WIRE,
})

# Maps each wireframe geometry to its solid equivalent for FBO picking:
# the pick pass draws solid silhouettes so any click inside the bounding
# shape registers a hit, not just clicks that land on a visible wire.
WIRE_TO_SOLID = {
    GEO_CUBE_WIRE:     GEO_CUBE,
    GEO_SPHERE_WIRE:   GEO_SPHERE,
    GEO_CONE_WIRE:     GEO_CONE,
    GEO_TORUS_WIRE:    GEO_TORUS,
    GEO_DODECA_WIRE:   GEO_DODECA,
    GEO_OCTA_WIRE:     GEO_OCTA,
    GEO_TETRA_WIRE:    GEO_TETRA,
    GEO_ICOSA_WIRE:    GEO_ICOSA,
    GEO_PIN_WIRE:      GEO_PIN,
    GEO_CYLINDER_WIRE: GEO_CYLINDER,
    GEO_GRID_WIRE:     GEO_GRID,
}


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


# A torus glyph's shape — not just its size — is governed by its per-node
# `ratio` property (mirrors GaiaViz/ANTz: "ratio sets the inner and outer
# radius of a torus... default ratio is 0.1 = 10% of the outer radius"):
# the minor (tube) radius is `ratio` of the torus's overall ("outer") radius,
# and the major (orbital) radius makes up the remainder, so the rendered
# donut's total extent always equals the unit "size" radius passed to
# GeoRenderer.draw — exposed so topology code can place children precisely
# on the rendered surface.
TORUS_DEFAULT_RATIO = 0.14  # half of the prior fixed minor-radius proportion (0.28)


def torus_radii(ratio: float, size: float = 1.0) -> tuple[float, float]:
    """Major/minor radii of a torus glyph for a given `ratio` and overall size."""
    minor = ratio * size
    return size - minor, minor


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


def _new_quadric(wire: bool, textured: bool = False):
    q = gluNewQuadric()
    gluQuadricNormals(q, GLU_SMOOTH)
    if wire:
        gluQuadricDrawStyle(q, GLU_LINE)
    if textured and not wire:
        gluQuadricTexture(q, GL_TRUE)
    return q


# Cylinder/rod proportions relative to the unit "size" radius — exposed so
# topology code can place children precisely on the rendered surface.
CYLINDER_RADIUS_RATIO = 1.0
CYLINDER_HEIGHT_RATIO = 2.0

# Rod topology scales the cylinder geometry: narrow (0.25x) and long (5x).
ROD_RADIUS_FACTOR = 0.25
ROD_HEIGHT_FACTOR = 5.0


def _draw_cylinder(solid: bool, r=CYLINDER_RADIUS_RATIO, h=CYLINDER_HEIGHT_RATIO, slices=16, textured: bool = False):
    q = _new_quadric(not solid, textured=textured and solid)
    if not solid:
        glDisable(GL_LIGHTING)
    glPushMatrix()
    glTranslatef(0.0, 0.0, -h/2.0)
    gluCylinder(q, r, r, h, slices, 1)
    if solid:
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


def _draw_pin(solid: bool, textured: bool = False):
    """Pushpin shape: ball "head" at the top, tapering "needle" pointing
    down — both built along local +Z/-Z so an unrotated pin stands upright
    in the (now Z-up, ANTz-aligned) world, matching GEO_CYLINDER/GEO_CONE's
    own local-Z-axis convention."""
    q = _new_quadric(not solid, textured=textured and solid)
    if not solid:
        glDisable(GL_LIGHTING)
    glPushMatrix()
    glTranslatef(0.0, 0.0, 0.22)
    gluSphere(q, 0.12, 12, 8)
    glPopMatrix()
    glPushMatrix()
    glTranslatef(0.0, 0.0, 0.1)
    glRotatef(180.0, 1.0, 0.0, 0.0)
    gluCylinder(q, 0.12, 0.03, 1.1, 8, 1)
    glPopMatrix()
    if not solid:
        glEnable(GL_LIGHTING)
    gluDeleteQuadric(q)


# Flat square ("Grid"/"Square") glyph — lies in the local XY plane, normal
# along +Z, matching ANTz's Grid node (topo=plane, geometry=Square) and the
# viewport's own XY-at-Z=0 world grid orientation. Half-extent chosen so the
# square's corners reach exactly radius 1.0, per this module's "fits within
# radius ~1" convention.
GRID_HALF_EXTENT = 1.0 / math.sqrt(2.0)


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


# ---------------------------------------------------------------------------
# GeoRenderer — compiles all shapes into OpenGL display lists
# ---------------------------------------------------------------------------

class GeoRenderer:
    def __init__(self):
        self._lists: dict[int, int] = {}
        self._tex_dispatch: dict[int, object] = {}
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
        }

        # Textured variants call geometry functions directly (bypassing display
        # lists) so that glTexCoord2f / gluQuadricTexture calls are live.
        self._tex_dispatch = {
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
        }

        for geo_id in range(GEO_COUNT):
            if geo_id == GEO_POINT:
                continue
            fn = _DISPATCH.get(geo_id)
            if fn is None:
                # GEO_TORUS/GEO_TORUS_WIRE are deliberately absent: their
                # shape (not just size) depends on each node's own `ratio`,
                # so they're drawn immediately per-node in draw() instead of
                # baked into one fixed-shape display list.
                continue
            dl = glGenLists(1)
            glNewList(dl, GL_COMPILE)
            try:
                fn()
            except Exception:
                _draw_sphere(True)
            glEndList()
            self._lists[geo_id] = dl

        self._ready = True

    def draw(self, geo_id: int, rx: float, ry: float, rz: float,
             ratio: float = TORUS_DEFAULT_RATIO, gl_tex_name: int = 0):
        if not self._ready:
            return
        if geo_id == GEO_POINT:
            # Points have no orientation/extent to stretch — fall back to
            # an average size for the on-screen point sprite.
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
            glPointSize(max(2.0, ((rx + ry + rz) / 3.0) * 2))
            glBegin(GL_POINTS)
            glVertex3f(0.0, 0.0, 0.0)
            glEnd()
            glPointSize(1.0)
            if was_lit:
                glEnable(GL_LIGHTING)
            return

        textured = gl_tex_name > 0 and geo_id not in _WIRE_IDS

        if geo_id in (GEO_TORUS, GEO_TORUS_WIRE):
            # Each node may set its own torus `ratio` (major/minor radius
            # proportions), so — unlike the other glyphs — its shape can't be
            # captured by a single fixed-shape display list scaled per node;
            # draw it immediately with radii derived from this node's ratio.
            r_major, r_minor = torus_radii(ratio)
            if textured:
                glEnable(GL_TEXTURE_2D)
                glBindTexture(GL_TEXTURE_2D, gl_tex_name)
            glPushMatrix()
            glScalef(rx, ry, rz)
            _draw_torus(geo_id == GEO_TORUS, r_major, r_minor, textured=textured)
            glPopMatrix()
            if textured:
                glBindTexture(GL_TEXTURE_2D, 0)
                glDisable(GL_TEXTURE_2D)
            return

        if textured:
            fn = self._tex_dispatch.get(geo_id)
            if fn is not None:
                glEnable(GL_TEXTURE_2D)
                glBindTexture(GL_TEXTURE_2D, gl_tex_name)
                glPushMatrix()
                glScalef(rx, ry, rz)
                fn()
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
