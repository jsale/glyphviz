"""
furniture — the school's furnishings, each modelled once in metres.

"Minimal but effective" was the brief, so every piece is a handful of boxes
and lathe-turned profiles, sized from real furniture (a 0.45 m seat, a 0.75 m
table, a 2 m bookcase) so that a person-sized camera flying through the rooms
finds them at the height it expects. A piece is ONE mesh in ONE flat colour
wherever that reads well enough; the few that need two materials (a bookcase's
spines, an easel's drawing) are built as separate meshes and assembled on a
rig by the scene.

Every builder puts the piece's origin at the middle of its footprint on the
floor, so the scene places furniture by "where it stands" and a yaw.
"""
from __future__ import annotations

import math

import numpy as np

import meshkit as mk


def _box(m, w, d, h, x=0.0, y=0.0, z0=0.0, uv_world=True):
    m.extend(mk.box(size=(w, d, h), center=(x, y, z0 + h / 2),
                    uv_world=uv_world, uv_scale=1.0))


def _cyl(m, r, z0, z1, x=0.0, y=0.0, seg=14):
    c = mk.revolve([(0.0, z0), (r, z0), (r, z1), (0.0, z1)], segments=seg)
    m.extend(c, mk.translate(x, y, 0))


def chair(seat=0.45):
    m = mk.Mesh("chair")
    _box(m, 0.44, 0.42, 0.05, z0=seat - 0.05)
    for sx in (-0.19, 0.19):
        for sy in (-0.18, 0.18):
            _box(m, 0.04, 0.04, seat - 0.05, sx, sy)
    _box(m, 0.44, 0.04, 0.45, 0.0, 0.19, seat)          # back (+y)
    return m


def stool(h=0.62):
    m = mk.Mesh("stool")
    _cyl(m, 0.18, h - 0.04, h)
    for k in range(3):
        a = k * 2 * math.pi / 3
        p0 = np.array([math.cos(a) * 0.20, math.sin(a) * 0.20, 0.0])
        p1 = np.array([math.cos(a) * 0.10, math.sin(a) * 0.10, h - 0.04])
        m.extend(mk.tube([p0, p1], 0.018, segments=5))
    return m


def table_round(r=0.7, h=0.75):
    m = mk.Mesh("table_round")
    _cyl(m, r, h - 0.04, h, seg=24)
    _cyl(m, 0.07, 0.0, h - 0.04, seg=10)
    _cyl(m, 0.32, 0.0, 0.04, seg=16)
    return m


def table_rect(w=1.8, d=0.9, h=0.75, leg=0.06):
    m = mk.Mesh("table_rect")
    _box(m, w, d, 0.05, z0=h - 0.05)
    for sx in (-1, 1):
        for sy in (-1, 1):
            _box(m, leg, leg, h - 0.05, sx * (w / 2 - 0.08), sy * (d / 2 - 0.08))
    return m


def bench(length=1.6, h=0.45, d=0.36):
    m = mk.Mesh("bench")
    _box(m, length, d, 0.06, z0=h - 0.06)
    for sx in (-1, 1):
        _box(m, 0.06, d * 0.9, h - 0.06, sx * (length / 2 - 0.15))
    return m


def bookcase_parts(w=1.0, h=2.0, d=0.34):
    """(carcass, front): the front is a single quad whose UVs span the whole
    books texture once; the carcass is plain wood. Two meshes, because a node
    paints one texture -- and a carcass wearing book spines on its sides
    reads as wallpaper, not furniture."""
    carcass = mk.Mesh("bookcase_carcass")
    t = 0.03
    _box(carcass, t, d, h, -w / 2 + t / 2)
    _box(carcass, t, d, h, w / 2 - t / 2)
    _box(carcass, w, d, t, z0=h - t)
    _box(carcass, w, d, 0.08)
    _box(carcass, w, t, h, 0.0, d / 2 - t / 2)              # back panel (+y)
    front = mk.Mesh("bookcase_front")
    y = -d / 2 + 0.06
    front.add_quad((-w / 2 + t, y, 0.08), (w / 2 - t, y, 0.08),
                   (w / 2 - t, y, h - t), (-w / 2 + t, y, h - t),
                   uvs=[(0.02, 0.0), (0.98, 0.0), (0.98, 1.0), (0.02, 1.0)])
    # second shelf face behind it so the books have depth from an angle
    front.add_quad((-w / 2 + t, y + 0.18, 0.08), (w / 2 - t, y + 0.18, 0.08),
                   (w / 2 - t, y + 0.18, h - t), (-w / 2 + t, y + 0.18, h - t),
                   uvs=[(0.02, 0.0), (0.98, 0.0), (0.98, 1.0), (0.02, 1.0)])
    return carcass, front


def panel(w=1.0, h=1.0, d=0.04, name="panel"):
    """A board with its front (-y) face mapped 0..1 -- easel drawings, the
    cubby wall, the entrance sign. Other faces sample the texture's corner."""
    m = mk.Mesh(name)
    x0, x1, z0, z1 = -w / 2, w / 2, 0.0, h
    yf, yb = -d / 2, d / 2
    c = [(0.005, 0.005)] * 4
    m.add_quad((x0, yf, z0), (x1, yf, z0), (x1, yf, z1), (x0, yf, z1),
               uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
    m.add_quad((x1, yb, z0), (x0, yb, z0), (x0, yb, z1), (x1, yb, z1), uvs=c)
    m.add_quad((x0, yb, z0), (x0, yf, z0), (x0, yf, z1), (x0, yb, z1), uvs=c)
    m.add_quad((x1, yf, z0), (x1, yb, z0), (x1, yb, z1), (x1, yf, z1), uvs=c)
    m.add_quad((x0, yf, z1), (x1, yf, z1), (x1, yb, z1), (x0, yb, z1), uvs=c)
    m.add_quad((x0, yb, z0), (x1, yb, z0), (x1, yf, z0), (x0, yf, z0), uvs=c)
    return m


def easel_frame(h=1.9):
    m = mk.Mesh("easel_frame")
    for sx in (-0.38, 0.38):
        m.extend(mk.tube([(sx, -0.25, 0.0), (sx * 0.25, 0.0, h)], 0.025, segments=5))
    m.extend(mk.tube([(0.0, 0.55, 0.0), (0.0, 0.02, h * 0.92)], 0.022, segments=5))
    _box(m, 1.0, 0.08, 0.05, 0.0, -0.17, 0.62)               # the ledge
    return m


def armchair():
    m = mk.Mesh("armchair")
    _box(m, 0.80, 0.80, 0.42)
    _box(m, 0.80, 0.18, 0.80, 0.0, 0.31, 0.0)
    for sx in (-1, 1):
        _box(m, 0.14, 0.80, 0.62, sx * 0.33)
    return m


def blob(rx, ry, rz, name="blob", squash=0.0, seg=(12, 8)):
    """A soft rounded lump: bean bag, cushion, shrub."""
    def f(u, v):
        th, ph = u * 2 * math.pi, v * math.pi
        z = math.cos(ph)
        r = 1.0 - squash * max(0.0, -z)
        return (math.sin(ph) * math.cos(th) * rx * r,
                math.sin(ph) * math.sin(th) * ry * r,
                rz * (1 + z))
    return mk.surface(f, seg[0], seg[1], wrap_u=True, name=name)


def beanbag():
    return blob(0.45, 0.45, 0.32, "beanbag", squash=0.3)


def cushion():
    return blob(0.30, 0.30, 0.07, "cushion")


def rug(rx=1.6, ry=1.1, seg=32):
    """A thin elliptical rug, 1.5 cm proud of the floor."""
    pts = [(math.cos(a) * rx, math.sin(a) * ry)
           for a in np.linspace(0, 2 * math.pi, seg, endpoint=False)]
    return mk.prism(pts, 0.0, 0.015, name="rug")


def piano():
    m = mk.Mesh("piano")
    _box(m, 1.50, 0.60, 1.25)                         # case
    _box(m, 1.40, 0.30, 0.08, 0.0, -0.40, 0.70)       # keybed
    _box(m, 1.50, 0.08, 0.62, 0.0, -0.26, 0.0)        # lower panel
    return m


def pingpong():
    m = mk.Mesh("pingpong")
    _box(m, 2.74, 1.525, 0.04, z0=0.72)
    for sx in (-1, 1):
        _box(m, 0.08, 1.2, 0.72, sx * 0.9)
    _box(m, 0.02, 1.72, 0.15, z0=0.76)                # net
    return m


def computer():
    m = mk.Mesh("computer")
    _box(m, 0.56, 0.05, 0.36, 0.0, 0.10, 0.12)        # screen
    _box(m, 0.06, 0.05, 0.12, 0.0, 0.12, 0.0)
    _box(m, 0.22, 0.18, 0.015, 0.0, 0.12, 0.0)
    _box(m, 0.45, 0.15, 0.02, 0.0, -0.15, 0.0)        # keyboard
    return m


def counter(w=2.0, d=0.62, h=0.92):
    m = mk.Mesh("counter")
    _box(m, w, d, h - 0.04)
    _box(m, w + 0.04, d + 0.03, 0.04, z0=h - 0.04)
    return m


def fridge():
    m = mk.Mesh("fridge")
    _box(m, 0.75, 0.70, 1.85)
    return m


def globe_stand():
    m = mk.Mesh("globe_stand")
    _cyl(m, 0.25, 0.0, 0.04)
    _cyl(m, 0.03, 0.04, 0.80)
    m.extend(mk.tube([(0.0, 0.0, 0.62)] + [
        (0.33 * math.sin(a), 0.0, 1.0 - 0.33 * math.cos(a) * 1.0 + 0.0)
        for a in np.linspace(0.2, math.pi * 0.95, 9)], 0.012, segments=5))
    return m


def globe_ball():
    return mk.surface(lambda u, v: (
        0.3 * math.sin(v * math.pi) * math.cos(u * 2 * math.pi),
        0.3 * math.sin(v * math.pi) * math.sin(u * 2 * math.pi),
        1.0 + 0.3 * math.cos(v * math.pi)), 18, 10, wrap_u=True, name="globe_ball")


def display_case():
    plinth = mk.Mesh("case_plinth")
    _box(plinth, 1.2, 0.6, 0.85)
    glass = mk.Mesh("case_glass")
    _box(glass, 1.16, 0.56, 0.55, z0=0.86)
    return plinth, glass


def potted_plant():
    pot = mk.revolve([(0.0, 0.0), (0.16, 0.0), (0.22, 0.40), (0.24, 0.42),
                      (0.0, 0.42)], segments=12, name="pot")
    leaves = mk.Mesh("plant")
    rng = np.random.default_rng(4)
    for k in range(5):
        a = k * 2 * math.pi / 5 + rng.uniform(-0.3, 0.3)
        leaves.extend(blob(0.22, 0.22, 0.22, seg=(8, 6)),
                      mk.translate(math.cos(a) * 0.14, math.sin(a) * 0.14,
                                   0.42 + rng.uniform(0.15, 0.45)))
    return pot, leaves


def telescope():
    m = mk.Mesh("telescope")
    for k in range(3):
        a = k * 2 * math.pi / 3
        m.extend(mk.tube([(math.cos(a) * 0.45, math.sin(a) * 0.45, 0.0),
                          (0.0, 0.0, 1.15)], 0.025, segments=5))
    tube = mk.revolve([(0.0, -0.7), (0.11, -0.7), (0.11, 0.7), (0.13, 0.75),
                       (0.13, 0.9), (0.0, 0.9)], segments=14)
    m.extend(tube, mk.compose(mk.rot_x(-50), mk.translate(0.0, 0.0, 1.25)))
    return m


def spiral_stair(height=4.2, radius=1.1, steps=18, turn=1.15):
    """Wedge treads around a central post -- the library stair the plan draws
    as a small spiral, rising to the roof terrace."""
    treads = mk.Mesh("spiral_treads")
    post = mk.Mesh("spiral_post")
    _cyl(post, 0.08, 0.0, height + 1.0, seg=10)
    rise = height / steps
    for k in range(steps):
        a0 = k * (2 * math.pi * turn / steps)
        a1 = a0 + 2 * math.pi * turn / steps * 1.15
        z = (k + 1) * rise
        pts = [(math.cos(a0) * 0.1, math.sin(a0) * 0.1)]
        for a in np.linspace(a0, a1, 4):
            pts.append((math.cos(a) * radius, math.sin(a) * radius))
        pts.append((math.cos(a1) * 0.1, math.sin(a1) * 0.1))
        treads.extend(mk.prism(pts, z - 0.05, z))
    # handrail: a helix at the tread tips
    rail = []
    for t in np.linspace(0, 1, 40):
        a = t * 2 * math.pi * turn
        rail.append((math.cos(a) * radius, math.sin(a) * radius, t * height + 0.95))
    post.extend(mk.tube(rail, 0.025, segments=5))
    return treads, post


def stair_flight(p0, p1, width, z0, z1, rise=0.18):
    """A straight flight from p0 (at z0) to p1 (at z1), world coords."""
    m = mk.Mesh("stair")
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    run = p1 - p0
    L = float(np.linalg.norm(run))
    u = run / L
    n = np.array([-u[1], u[0]])
    count = max(int(abs(z1 - z0) / rise), 2)
    for k in range(count):
        t0, t1 = k / count, (k + 1) / count
        a, b = p0 + run * t0, p0 + run * t1
        z = z0 + (z1 - z0) * (k + 1) / count
        lo = min(z0, z) - 0.02
        poly = [a - n * width / 2, b - n * width / 2, b + n * width / 2, a + n * width / 2]
        if np.cross(np.append(poly[1] - poly[0], 0), np.append(poly[2] - poly[1], 0))[2] < 0:
            poly = poly[::-1]
        m.extend(mk.prism([tuple(p) for p in poly], lo, z, uv_world=True, uv_scale=1.0))
    return m


def crate(s=0.6):
    m = mk.Mesh("crate")
    _box(m, s, s, s * 0.8)
    return m


def shelving(w=1.8, d=0.5, h=2.0):
    m = mk.Mesh("shelving")
    for sx in (-1, 1):
        for sy in (-1, 1):
            _box(m, 0.04, 0.04, h, sx * (w / 2 - 0.02), sy * (d / 2 - 0.02))
    for z in np.linspace(0.1, h - 0.03, 5):
        _box(m, w, d, 0.03, z0=float(z))
    return m


def desk():
    m = table_rect(1.5, 0.75, 0.74)
    _box(m, 0.42, 0.68, 0.66, 0.50, 0.0, 0.0)          # drawer pedestal
    return m


def filing_cabinet():
    m = mk.Mesh("filing")
    _box(m, 0.46, 0.62, 1.30)
    return m


def log_bench(length=2.4, r=0.22):
    m = mk.Mesh("log_bench")
    m.extend(mk.tube([(-length / 2, 0.0, r), (length / 2, 0.0, r)], r, segments=9))
    return m
