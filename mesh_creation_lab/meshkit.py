"""
meshkit — a small procedural mesh library for authoring GlyphViz GEO_MESH shapes.

Everything here is plain numpy and writes Wavefront OBJ with texture
coordinates, so the output loads through glyphviz_core.mesh_loader unchanged.
It exists because GlyphViz's example scenes need *models* — a tree, a
building, an aircraft — and hand-writing OBJ vertex tables is not a thing
anyone should do twice.

Three facts about the import pipeline shape this whole module, and a generator
that ignores them will produce a scene that looks wrong for reasons that are
very hard to see afterwards:

1. **Every mesh is re-centred and normalized to radius 1** on load (see
   `load_mesh_file`). A model's own units are therefore irrelevant — only its
   proportions survive — and its origin ends up at the *bounding-box centre*,
   not wherever you built it around. `Mesh.placement()` reports exactly what
   the loader will do, so a generator can work out where the model's feet
   will land and place the node accordingly. Use it; do not estimate.

2. **Sharp edges come from the crease angle, not from split vertices.** The
   loader welds coincident vertices, so duplicating them to force a hard edge
   is wasted effort. Build clean shared geometry and let
   `mesh_loader.DEFAULT_CREASE_ANGLE` decide; 40 degrees keeps flat panels
   crisp and barrels round.

3. **UVs are preserved, and a UV difference prevents welding.** So a seam is
   made by giving the two sides different texture coordinates, which is also
   the only reason a generator here ever needs to duplicate a position.

A GlyphViz node colours a whole mesh with one flat colour, so a multi-coloured
model is built as several meshes — one per material — assembled as sibling or
child nodes in the scene. `Model` is the small container for that: named parts
that each become their own OBJ file and their own node.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# --------------------------------------------------------------------------
# transforms — 4x4, column-vector convention (M @ p)
# --------------------------------------------------------------------------


def identity() -> np.ndarray:
    return np.eye(4)


def translate(x=0.0, y=0.0, z=0.0) -> np.ndarray:
    m = np.eye(4)
    m[:3, 3] = (x, y, z)
    return m


def scale(x=1.0, y=None, z=None) -> np.ndarray:
    if y is None:
        y = x
    if z is None:
        z = x
    m = np.eye(4)
    m[0, 0], m[1, 1], m[2, 2] = x, y, z
    return m


def rot_x(deg: float) -> np.ndarray:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    m = np.eye(4)
    m[1, 1], m[1, 2], m[2, 1], m[2, 2] = c, -s, s, c
    return m


def rot_y(deg: float) -> np.ndarray:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    m = np.eye(4)
    m[0, 0], m[0, 2], m[2, 0], m[2, 2] = c, s, -s, c
    return m


def rot_z(deg: float) -> np.ndarray:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    m = np.eye(4)
    m[0, 0], m[0, 1], m[1, 0], m[1, 1] = c, -s, s, c
    return m


def mirror_x() -> np.ndarray:
    """Reflection through the x = 0 plane.

    **This, not a rotation, is what makes a left/right pair.** The tempting
    shortcut for a wing or a fin is to place each side with `rot_z(-90 * side)`
    — but negating an angle ROTATES the part, it does not reflect it, so the
    left copy comes out turned 180 degrees about the vertical. Anything
    fore-and-aft asymmetric then points the wrong way: a swept wing sweeps
    forward on one side, an aerofoil puts its round leading edge at the back.
    The result is a pinwheel that is rotationally symmetric and not mirror
    symmetric, and from most angles it just looks subtly wrong rather than
    obviously broken. Use `mirror_pair()`.
    """
    return scale(-1.0, 1.0, 1.0)


def mirror_pair(target: "Mesh", part: "Mesh", matrix: np.ndarray) -> None:
    """Add *part* placed by *matrix*, plus its mirror image through x = 0.

    Place the +X (right-hand) side only; the left side is derived, so the two
    cannot drift apart and no per-side sign needs to be reasoned about.
    """
    placed = part.transform(matrix)
    target.extend(placed)
    target.extend(placed, mirror_x())


def compose(*mats) -> np.ndarray:
    """Left-to-right reading order: compose(A, B) applies A, then B."""
    out = np.eye(4)
    for m in mats:
        out = m @ out
    return out


def _norm(v):
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


# --------------------------------------------------------------------------
# Mesh
# --------------------------------------------------------------------------

@dataclass
class Placement:
    """What `load_mesh_file` will do to this mesh, worked out ahead of time.

    `radius` is the divisor it applies, `center` the point it moves to the
    origin. The rest are the model's extents *after* that, in the unit-radius
    space a GlyphViz node scales: multiply any of them by the node's scale to
    get world units.
    """
    center: np.ndarray
    radius: float
    half: np.ndarray        # half-extents after normalization (x, y, z)
    bottom: float           # z of the lowest point (negative, normally)
    top: float

    @property
    def ground_z(self) -> float:
        """Node translate_z that sets this model's lowest point on z=0, per
        unit of node scale. A model normalized so its base sits 0.7 below its
        centre needs translate_z = 0.7 * scale to stand on the ground."""
        return -self.bottom

    def scale_for_height(self, world_height: float) -> float:
        """Node scale that makes the model *world_height* units tall."""
        span = self.top - self.bottom
        return world_height / span if span > 1e-12 else 1.0

    def scale_for_length(self, world_length: float, axis: int = 1) -> float:
        span = 2.0 * self.half[axis]
        return world_length / span if span > 1e-12 else 1.0


class Mesh:
    """A triangle soup with texture coordinates, built incrementally."""

    def __init__(self, name: str = "mesh"):
        self.name = name
        self._v: list[tuple[float, float, float]] = []
        self._uv: list[tuple[float, float]] = []
        self._f: list[tuple[int, int, int]] = []

    # -- construction ------------------------------------------------------

    def vert(self, p, uv=(0.0, 0.0)) -> int:
        self._v.append((float(p[0]), float(p[1]), float(p[2])))
        self._uv.append((float(uv[0]), float(uv[1])))
        return len(self._v) - 1

    def tri(self, a: int, b: int, c: int) -> None:
        self._f.append((a, b, c))

    def quad(self, a: int, b: int, c: int, d: int) -> None:
        """Two triangles across a-c, wound in the order given."""
        self._f.append((a, b, c))
        self._f.append((a, c, d))

    def add_quad(self, p0, p1, p2, p3, uvs=None) -> None:
        """A standalone quad from four positions (CCW seen from the front)."""
        if uvs is None:
            uvs = ((0, 0), (1, 0), (1, 1), (0, 1))
        i = [self.vert(p, uv) for p, uv in zip((p0, p1, p2, p3), uvs)]
        self.quad(*i)

    def extend(self, other: "Mesh", matrix: np.ndarray | None = None) -> None:
        """Append *other*, optionally transformed. Indices are rebased.

        A matrix with NEGATIVE determinant (any reflection — see `mirror_x`)
        reverses each triangle's winding as it is copied. It has to: winding is
        what the importer's crease pass reads a face normal from, so a mirrored
        part copied verbatim would carry inward normals and shade as a dark
        hole beside its correctly-lit twin.
        """
        base = len(self._v)
        verts = np.asarray(other._v, dtype=float)
        flip = False
        if len(verts):
            if matrix is not None:
                h = np.hstack([verts, np.ones((len(verts), 1))])
                verts = (matrix @ h.T).T[:, :3]
                flip = float(np.linalg.det(matrix[:3, :3])) < 0.0
            self._v.extend(map(tuple, verts))
            self._uv.extend(other._uv)
        if flip:
            self._f.extend((a + base, c + base, b + base) for a, b, c in other._f)
        else:
            self._f.extend((a + base, b + base, c + base) for a, b, c in other._f)

    def transform(self, matrix: np.ndarray) -> "Mesh":
        """A transformed copy."""
        out = Mesh(self.name)
        out.extend(self, matrix)
        return out

    # -- inspection --------------------------------------------------------

    @property
    def vertices(self) -> np.ndarray:
        return np.asarray(self._v, dtype=float).reshape(-1, 3)

    @property
    def faces(self) -> np.ndarray:
        return np.asarray(self._f, dtype=np.int64).reshape(-1, 3)

    def __len__(self) -> int:
        return len(self._f)

    def placement(self) -> Placement:
        """Predict the loader's normalization. See the module docstring —
        this is how a generator learns where its model's feet will be."""
        v = self.vertices
        lo, hi = v.min(axis=0), v.max(axis=0)
        center = (lo + hi) / 2.0
        centred = v - center
        radius = float(np.max(np.linalg.norm(centred, axis=1)))
        if radius < 1e-12:
            radius = 1.0
        half = (hi - lo) / 2.0 / radius
        return Placement(center=center, radius=radius, half=half,
                         bottom=float(centred[:, 2].min() / radius),
                         top=float(centred[:, 2].max() / radius))

    # -- output ------------------------------------------------------------

    def save_obj(self, path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        out = [f"# {self.name} — generated by meshkit.py",
               f"# {len(self._v)} vertices, {len(self._f)} triangles", ""]
        for x, y, z in self._v:
            out.append(f"v {x:.5g} {y:.5g} {z:.5g}")
        for u, v in self._uv:
            out.append(f"vt {u:.4g} {v:.4g}")
        out.append("")
        for a, b, c in self._f:
            out.append(f"f {a+1}/{a+1} {b+1}/{b+1} {c+1}/{c+1}")
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
        return path


@dataclass
class Part:
    """How to hang one part of a multi-part model off its rig node.

    Both numbers are in the model's OWN units and are the same for every
    instance of the model, which is the point: a scene places twenty aircraft
    by writing twenty rig nodes, and every aircraft's parts are byte-identical
    rows underneath.
    """
    name: str
    offset: tuple[float, float, float]   # child translate_x/y/z
    scale: float                         # child scale_x/y/z


@dataclass
class Model:
    """A multi-part model: one Mesh per material, because a GlyphViz node
    paints a whole mesh in a single flat colour.

    **The problem this solves.** `load_mesh_file` re-centres and normalizes
    every file on its own bounding box, so parts built in one coordinate
    system arrive in several different ones — a fuselage and its canopy each
    become a unit-radius blob centred on itself, and stacking them at the same
    node position interleaves them into rubbish. The fix is to undo that
    per-file normalization at the scene level, which `assembly()` computes.

    **The rig.** Each instance is one hidden parent node carrying position,
    rotation and size; the parts are its children. That works because a
    topo-None parent composes exactly (verified against the real engine):

        child world position = rig_pos + R_rig @ (child_translate * rig_scale)
        child drawn scale    = child_scale * rig_scale

    Substituting a part's `offset` and `scale` into those makes every part
    land as if the whole model had been normalized once, together.
    """
    name: str
    parts: dict[str, Mesh] = field(default_factory=dict)

    def part(self, key: str) -> Mesh:
        if key not in self.parts:
            self.parts[key] = Mesh(f"{self.name}_{key}")
        return self.parts[key]

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        pts = np.vstack([m.vertices for m in self.parts.values() if len(m)])
        return pts.min(axis=0), pts.max(axis=0)

    def assembly(self, anchor=None) -> dict[str, Part]:
        """Per-part rig offsets and scales, in model units.

        `anchor` is the point of the model that the rig node sits at —
        default the bounding-box centre, but a vehicle usually wants its
        centre of mass and a building or a tree wants the middle of its base,
        so that placing it is just "put the rig where the thing goes".
        """
        if anchor is None:
            lo, hi = self.bounds()
            anchor = (lo + hi) / 2.0
        anchor = np.asarray(anchor, dtype=float)
        out = {}
        for key, mesh in self.parts.items():
            if not len(mesh):
                continue
            pl = mesh.placement()
            out[key] = Part(name=key,
                            offset=tuple(pl.center - anchor),
                            scale=pl.radius)
        return out

    def rig_scale(self, world_size: float, axis: int = 2) -> float:
        """The rig node scale that makes the assembled model *world_size*
        units along one axis (0=x, 1=y, 2=z)."""
        lo, hi = self.bounds()
        span = float(hi[axis] - lo[axis])
        return world_size / span if span > 1e-12 else 1.0

    def save(self, folder, prefix: str = "") -> dict[str, Path]:
        folder = Path(folder)
        return {k: m.save_obj(folder / f"{prefix}{k}.obj")
                for k, m in self.parts.items() if len(m)}


# --------------------------------------------------------------------------
# builders
# --------------------------------------------------------------------------

def box(size=(1.0, 1.0, 1.0), center=(0.0, 0.0, 0.0),
        uv_scale=1.0, uv_world=False, name="box") -> Mesh:
    """An axis-aligned box.

    `uv_world=True` scales each face's UVs by its own world size instead of
    mapping 0..1 across it, so a texture keeps a constant real-world size
    across boxes of different shapes — which is what you want for brick,
    cladding or window grids, and not what you want for a label or a poster.
    """
    m = Mesh(name)
    sx, sy, sz = (float(s) / 2.0 for s in size)
    cx, cy, cz = center

    # (axis normal, the two in-plane axes) for each of the six faces
    faces = [
        ((1, 0, 0), (0, 1, 0), (0, 0, 1), sx, sy, sz),
        ((-1, 0, 0), (0, -1, 0), (0, 0, 1), sx, sy, sz),
        ((0, 1, 0), (-1, 0, 0), (0, 0, 1), sy, sx, sz),
        ((0, -1, 0), (1, 0, 0), (0, 0, 1), sy, sx, sz),
        ((0, 0, 1), (1, 0, 0), (0, 1, 0), sz, sx, sy),
        ((0, 0, -1), (-1, 0, 0), (0, 1, 0), sz, sx, sy),
    ]
    for n, u, v, dn, du, dv in faces:
        n, u, v = np.array(n, float), np.array(u, float), np.array(v, float)
        c = np.array((cx, cy, cz), float) + n * dn
        su = (du * 2 * uv_scale) if uv_world else uv_scale
        sv = (dv * 2 * uv_scale) if uv_world else uv_scale
        corners = [c - u * du - v * dv, c + u * du - v * dv,
                   c + u * du + v * dv, c - u * du + v * dv]
        uvs = [(0, 0), (su, 0), (su, sv), (0, sv)]
        m.add_quad(*corners, uvs=uvs)
    return m


def ring(n: int, radius: float = 1.0, z: float = 0.0,
         phase: float = 0.0) -> np.ndarray:
    """*n* points evenly around a circle in the z=const plane."""
    a = np.linspace(0, 2 * math.pi, n, endpoint=False) + phase
    return np.stack([np.cos(a) * radius, np.sin(a) * radius,
                     np.full(n, float(z))], axis=1)


def loft(sections, closed=True, cap_start=False, cap_end=False,
         uv_v=None, uv_u_repeat=1.0, name="loft") -> Mesh:
    """Skin a stack of equal-length cross-sections.

    `closed` joins each section's last point back to its first (a tube);
    `uv_v` supplies the v coordinate per section, defaulting to normalized
    arc length along the stack so a texture doesn't bunch up where sections
    crowd together.
    """
    secs = [np.asarray(s, dtype=float).reshape(-1, 3) for s in sections]
    if len(secs) < 2:
        raise ValueError("loft needs at least two sections")
    n = len(secs[0])
    if any(len(s) != n for s in secs):
        raise ValueError("all sections must have the same point count")

    if uv_v is None:
        centres = np.array([s.mean(axis=0) for s in secs])
        steps = np.linalg.norm(np.diff(centres, axis=0), axis=1)
        run = np.concatenate([[0.0], np.cumsum(steps)])
        uv_v = run / run[-1] if run[-1] > 1e-12 else np.linspace(0, 1, len(secs))

    m = Mesh(name)
    # A tube needs a seam: the wrap-around column is duplicated with u=1
    # instead of u=0, which is also what stops the loader welding it shut.
    cols = n + 1 if closed else n
    idx = np.zeros((len(secs), cols), dtype=int)
    for i, sec in enumerate(secs):
        for j in range(cols):
            p = sec[j % n]
            u = (j / n) * uv_u_repeat if closed else (j / max(n - 1, 1)) * uv_u_repeat
            idx[i, j] = m.vert(p, (u, float(uv_v[i])))

    for i in range(len(secs) - 1):
        for j in range(cols - 1):
            m.quad(int(idx[i, j]), int(idx[i, j + 1]),
                   int(idx[i + 1, j + 1]), int(idx[i + 1, j]))

    if cap_start:
        _cap(m, secs[0], flip=True)
    if cap_end:
        _cap(m, secs[-1], flip=False)
    return m


def _cap(m: Mesh, sec: np.ndarray, flip: bool) -> None:
    """Close a section with a triangle fan from its centroid."""
    c = sec.mean(axis=0)
    span = float(np.max(np.linalg.norm(sec - c, axis=1))) or 1.0
    ci = m.vert(c, (0.5, 0.5))
    ids = [m.vert(p, (0.5 + (p[0] - c[0]) / (2 * span),
                      0.5 + (p[1] - c[1]) / (2 * span))) for p in sec]
    n = len(ids)
    for k in range(n):
        a, b = ids[k], ids[(k + 1) % n]
        m.tri(ci, b, a) if flip else m.tri(ci, a, b)


def revolve(profile, segments=32, cap=False, name="revolve") -> Mesh:
    """Spin a (radius, z) profile around the z axis."""
    profile = np.asarray(profile, dtype=float).reshape(-1, 2)
    secs = []
    for r, z in profile:
        secs.append(ring(segments, radius=max(float(r), 0.0), z=float(z)))
    v = np.concatenate([[0.0], np.cumsum(
        np.linalg.norm(np.diff(profile, axis=0), axis=1))])
    v = v / v[-1] if v[-1] > 1e-12 else None
    return loft(secs, closed=True, cap_start=cap, cap_end=cap, uv_v=v, name=name)


def frames_along(path: np.ndarray, up=(0.0, 0.0, 1.0)) -> np.ndarray:
    """Parallel-transport frames along a polyline: (K, 3, 3) with columns
    (right, forward-normal, tangent). Parallel transport is used rather than a
    fixed up vector so a path that turns straight up — a tree trunk, a climbing
    flight path — doesn't spin or degenerate where the tangent meets `up`."""
    path = np.asarray(path, dtype=float).reshape(-1, 3)
    k = len(path)
    tangents = np.zeros_like(path)
    tangents[1:-1] = path[2:] - path[:-2]
    tangents[0] = path[1] - path[0]
    tangents[-1] = path[-1] - path[-2]
    tangents = np.array([_norm(t) for t in tangents])

    ref = _norm(up)
    if abs(float(np.dot(tangents[0], ref))) > 0.99:
        ref = np.array([1.0, 0.0, 0.0])
    out = np.zeros((k, 3, 3))
    right = _norm(np.cross(ref, tangents[0]))
    for i in range(k):
        if i:
            # rotate the previous frame onto the new tangent, minimally
            axis = np.cross(tangents[i - 1], tangents[i])
            s = float(np.linalg.norm(axis))
            if s > 1e-9:
                axis = axis / s
                ang = math.atan2(s, float(np.dot(tangents[i - 1], tangents[i])))
                ca, sa = math.cos(ang), math.sin(ang)
                right = (right * ca + np.cross(axis, right) * sa
                         + axis * float(np.dot(axis, right)) * (1 - ca))
            right = _norm(right - tangents[i] * float(np.dot(right, tangents[i])))
        up2 = _norm(np.cross(tangents[i], right))
        out[i] = np.stack([right, up2, tangents[i]], axis=1)
    return out


def tube(path, radii, segments=8, cap_start=True, cap_end=True,
         uv_u_repeat=1.0, name="tube") -> Mesh:
    """A swept circular tube along a polyline — branches, cables, pipes."""
    path = np.asarray(path, dtype=float).reshape(-1, 3)
    radii = np.broadcast_to(np.asarray(radii, dtype=float), (len(path),))
    frames = frames_along(path)
    circle = ring(segments, 1.0, 0.0)[:, :2]
    secs = []
    for p, r, f in zip(path, radii, frames):
        pts = p + (circle[:, 0:1] * f[:, 0] + circle[:, 1:2] * f[:, 1]) * r
        secs.append(pts)
    return loft(secs, closed=True, cap_start=cap_start, cap_end=cap_end,
                uv_u_repeat=uv_u_repeat, name=name)


def prism(polygon, z0: float, z1: float, cap=True, uv_world=False,
          uv_scale=1.0, name="prism") -> Mesh:
    """Extrude a 2-D polygon (CCW) between two heights — building footprints,
    road segments, wing cross-sections."""
    poly = np.asarray(polygon, dtype=float).reshape(-1, 2)
    n = len(poly)
    m = Mesh(name)

    edge = np.linalg.norm(np.diff(np.vstack([poly, poly[:1]]), axis=0), axis=1)
    run = np.concatenate([[0.0], np.cumsum(edge)])
    total = run[-1] or 1.0
    h = z1 - z0
    for i in range(n):
        j = (i + 1) % n
        a, b = poly[i], poly[j]
        if uv_world:
            u0, u1, vv = run[i] * uv_scale, run[i + 1] * uv_scale, h * uv_scale
        else:
            u0, u1, vv = run[i] / total, run[i + 1] / total, 1.0
        m.add_quad((a[0], a[1], z0), (b[0], b[1], z0),
                   (b[0], b[1], z1), (a[0], a[1], z1),
                   uvs=[(u0, 0), (u1, 0), (u1, vv), (u0, vv)])
    if cap:
        lo, hi = poly.min(axis=0), poly.max(axis=0)
        span = np.maximum(hi - lo, 1e-9)
        top = [m.vert((p[0], p[1], z1), tuple((p - lo) / span)) for p in poly]
        bot = [m.vert((p[0], p[1], z0), tuple((p - lo) / span)) for p in poly]
        for k in range(1, n - 1):          # fan — fine for convex footprints
            m.tri(top[0], top[k], top[k + 1])
            m.tri(bot[0], bot[k + 1], bot[k])
    return m


def surface(fn, nu: int, nv: int, u_range=(0.0, 1.0), v_range=(0.0, 1.0),
            wrap_u=False, name="surface") -> Mesh:
    """Tessellate a parametric surface fn(u, v) -> (x, y, z)."""
    us = np.linspace(*u_range, nu)
    vs = np.linspace(*v_range, nv)
    m = Mesh(name)
    idx = np.zeros((nu, nv), dtype=int)
    for i, u in enumerate(us):
        for j, v in enumerate(vs):
            idx[i, j] = m.vert(fn(float(u), float(v)),
                               (i / (nu - 1), j / (nv - 1)))
    for i in range(nu - 1 if not wrap_u else nu):
        i2 = (i + 1) % nu
        if not wrap_u and i2 == 0:
            continue
        for j in range(nv - 1):
            m.quad(int(idx[i, j]), int(idx[i2, j]),
                   int(idx[i2, j + 1]), int(idx[i, j + 1]))
    return m


def polygon_regular(n: int, radius: float = 1.0, phase: float = 0.0) -> np.ndarray:
    a = np.linspace(0, 2 * math.pi, n, endpoint=False) + phase
    return np.stack([np.cos(a) * radius, np.sin(a) * radius], axis=1)


def rect(w: float, h: float, cx: float = 0.0, cy: float = 0.0) -> np.ndarray:
    return np.array([(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2),
                     (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)])


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)
