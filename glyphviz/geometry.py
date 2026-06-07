"""
Geometry type constants, names, and a display-list renderer.

All shapes are compiled at unit scale (fits within radius ~1).
Caller applies glScalef(r, r, r) before calling draw().
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
GEO_POINT          = 20
GEO_COUNT          = 21

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
    GEO_POINT:         "Point",
}

_WIRE_IDS = frozenset({
    GEO_CUBE_WIRE, GEO_SPHERE_WIRE, GEO_CONE_WIRE, GEO_TORUS_WIRE,
    GEO_DODECA_WIRE, GEO_OCTA_WIRE, GEO_TETRA_WIRE, GEO_ICOSA_WIRE,
    GEO_PIN_WIRE, GEO_CYLINDER_WIRE,
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


# ---------------------------------------------------------------------------
# Draw helpers (called inside glNewList / glEndList)
# ---------------------------------------------------------------------------

def _draw_tri_solid(verts, faces):
    glBegin(GL_TRIANGLES)
    for f in faces:
        n = _face_normal(verts[f[0]], verts[f[1]], verts[f[2]])
        glNormal3f(*n)
        for vi in f:
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


def _draw_poly_solid(verts, faces):
    """Draw polygonal (pentagon) faces as triangle fans."""
    for f in faces:
        n = _face_normal(verts[f[0]], verts[f[1]], verts[f[2]])
        glNormal3f(*n)
        glBegin(GL_TRIANGLE_FAN)
        for vi in f:
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


def _draw_cube(solid: bool):
    if solid:
        glBegin(GL_QUADS)
        for (quad, normal) in _CUBE_QUADS:
            glNormal3f(*normal)
            for vi in quad:
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


# Torus proportions relative to the unit "size" radius passed to GeoRenderer.draw
# — exposed so topology code can place children precisely on the rendered surface.
TORUS_MAJOR_RATIO = 0.72
TORUS_MINOR_RATIO = 0.28


def _draw_torus(solid: bool, r_major=TORUS_MAJOR_RATIO, r_minor=TORUS_MINOR_RATIO, rings=24, sides=16):
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
            for th in (th0, th1):
                ct, st = math.cos(th), math.sin(th)
                glNormal3f(cp*ct, cp*st, sp)
                glVertex3f((r_major+r_minor*cp)*ct, (r_major+r_minor*cp)*st, r_minor*sp)
        glEnd()


def _new_quadric(wire: bool):
    q = gluNewQuadric()
    gluQuadricNormals(q, GLU_SMOOTH)
    if wire:
        gluQuadricDrawStyle(q, GLU_LINE)
    return q


# Cylinder/rod proportions relative to the unit "size" radius — exposed so
# topology code can place children precisely on the rendered surface.
CYLINDER_RADIUS_RATIO = 1.0
CYLINDER_HEIGHT_RATIO = 2.0


def _draw_cylinder(solid: bool, r=CYLINDER_RADIUS_RATIO, h=CYLINDER_HEIGHT_RATIO, slices=16):
    q = _new_quadric(not solid)
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


def _draw_cone(solid: bool, r=1.0, h=2.0, slices=16):
    q = _new_quadric(not solid)
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


def _draw_sphere(solid: bool, r=1.0, slices=16, stacks=12):
    q = _new_quadric(not solid)
    if not solid:
        glDisable(GL_LIGHTING)
    gluSphere(q, r, slices, stacks)
    if not solid:
        glEnable(GL_LIGHTING)
    gluDeleteQuadric(q)


def _draw_pin(solid: bool):
    q = _new_quadric(not solid)
    if not solid:
        glDisable(GL_LIGHTING)
    glPushMatrix()
    glTranslatef(0.0, 0.55, 0.0)
    gluSphere(q, 0.45, 12, 8)
    glPopMatrix()
    glPushMatrix()
    glRotatef(90.0, 1.0, 0.0, 0.0)
    glTranslatef(0.0, 0.0, -0.1)
    gluCylinder(q, 0.12, 0.03, 1.1, 8, 1)
    glPopMatrix()
    if not solid:
        glEnable(GL_LIGHTING)
    gluDeleteQuadric(q)


# ---------------------------------------------------------------------------
# GeoRenderer — compiles all shapes into OpenGL display lists
# ---------------------------------------------------------------------------

class GeoRenderer:
    def __init__(self):
        self._lists: dict[int, int] = {}
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
            GEO_TORUS:         lambda: _draw_torus(True),
            GEO_TORUS_WIRE:    lambda: _draw_torus(False),
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

        for geo_id in range(GEO_COUNT):
            if geo_id == GEO_POINT:
                continue
            fn = _DISPATCH.get(geo_id)
            if fn is None:
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

    def draw(self, geo_id: int, r: float):
        if not self._ready:
            return
        if geo_id == GEO_POINT:
            glDisable(GL_LIGHTING)
            glPointSize(max(2.0, r * 2))
            glBegin(GL_POINTS)
            glVertex3f(0.0, 0.0, 0.0)
            glEnd()
            glPointSize(1.0)
            glEnable(GL_LIGHTING)
            return
        dl = self._lists.get(geo_id, self._lists.get(GEO_SPHERE))
        if dl:
            glPushMatrix()
            glScalef(r, r, r)
            glCallList(dl)
            glPopMatrix()
