"""
site_plan — the Banyan Tree community: land, water, roads, homes and trees,
laid out from "The Initial Community" drawing.

The drawing was digitized by hand (its lines are too broken to trace
automatically): every coordinate in the tables below is a pixel position on
`drawings/banyan_community.png`, converted by `W()` at 0.39 m/px with the
Main Hall's centre on the scene origin. That scale makes the school the same
size here as on its own floor plan, and the whole community about 11 acres --
"several acres", as the plan intended.

Where the drawing is a diagram rather than a plan, it is read generously:

* The hills to the north-west rise into real terrain; the forests to the
  north-east are coast live oak, sycamore and Coulter pine -- the backcountry
  above Escondido and Julian that the page names.
* The lake's west lobe runs up to the school's corner, because the floor
  plan's "POND" and its Underwater Observation Area are on that corner too:
  the pond is the lake.
* The playground's circled feature is read as the big tree the school is
  named for: a Moreton Bay fig, the banyan-like fig that does grow in San
  Diego, with aerial roots and the kids-only tree house the page asks for.
* The ring of wedges between the homes and the Main Hall is read as the
  commons: one raised garden terrace per family, around a story circle.
"""
from __future__ import annotations

import functools
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage as ndi

import meshkit as mk
import texkit as tk
import furniture as fu
import organic as og
import plan_trace as pt
import textures as tx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "Tree"))
from build_tree import grow, build_trunk, build_canopy   # noqa: E402

M_PER_APX = 0.39
MAIN_HALL_APX = (276.0, 470.0)

# terrain / site-map extents (metres)
X0, X1, Y0, Y1 = -150.0, 160.0, -122.0, 124.0


def W(ax, ay):
    """Community-plan pixel -> scene metres."""
    return ((ax - MAIN_HALL_APX[0]) * M_PER_APX, (MAIN_HALL_APX[1] - ay) * M_PER_APX)


def WL(pts):
    return [W(*p) for p in pts]


# ----------------------------------------------------------------------------
# the plan, digitized (community-plan pixels)
# ----------------------------------------------------------------------------

ROAD_ENTRANCE = [(0, 366), (40, 365), (80, 368), (120, 368), (160, 362),
                 (195, 350), (212, 338)]
ROAD_GARDEN_LOOP = [(212, 338), (214, 305), (226, 284), (250, 272), (300, 271),
                    (324, 282), (342, 312), (358, 336), (386, 346), (406, 366),
                    (418, 385), (406, 414), (376, 430), (336, 441), (292, 447),
                    (262, 440), (244, 421), (226, 398), (212, 372), (212, 338)]
ROAD_OUTER_LOOP = [(92, 368), (90, 420), (96, 480), (104, 540), (118, 592),
                   (148, 636), (200, 664), (258, 676), (320, 668), (386, 640),
                   (432, 610), (452, 590)]
ROAD_SPURS = [
    [(250, 272), (252, 250), (256, 234)],          # to water reclamation
    [(324, 282), (330, 268)],                      # to the greenhouse
]
PATHS = [
    [(452, 590), (436, 560), (412, 535), (398, 510), (394, 495)],   # pool -> school
    [(232, 405), (258, 423), (285, 440)],          # garden walkway (pergola)
    [(418, 385), (450, 374), (500, 364), (545, 360), (572, 345), (600, 330)],
    [(545, 360), (548, 382), (562, 398), (600, 404)],
    [(398, 462), (450, 478), (520, 492), (575, 502), (612, 505)],
    [(194, 449), (215, 470), (232, 492)],          # dwelling paths to commons
    [(160, 485), (200, 490), (232, 492)],
    [(160, 535), (200, 512), (232, 492)],
    [(220, 590), (228, 540), (232, 492)],
    [(300, 580), (280, 545), (250, 510), (232, 492)],
    [(232, 492), (276, 520), (320, 530), (343, 516)],   # commons -> courtyard
]
TRAILS = [   # hiking + mountain biking, up into the hills
    [(150, 362), (128, 345), (100, 328), (70, 305), (42, 282), (12, 258), (-20, 236)],
    [(205, 345), (196, 318), (212, 290), (224, 262), (206, 240), (172, 226), (130, 214)],
    [(70, 305), (60, 270), (75, 236), (60, 200)],
]

LAKE = [   # world metres; the west lobe is the floor plan's pond
    (56.2, 33.5), (64.0, 28.1), (72.5, 28.5), (82.7, 24.6), (93.2, 22.6),
    (101.0, 19.5), (104.9, 12.5), (103.0, 4.7), (95.9, -0.8), (85.4, -4.3),
    (73.7, -4.7), (63.2, -2.3), (52.3, 1.6), (46.0, 0.3), (42.7, 0.4),
    (42.3, 1.5), (37.9, 6.4), (36.1, 6.2), (35.9, 10.9), (38.6, 14.2),
    (43.7, 19.5), (47.6, 25.7), (52.3, 30.4)]

POOL_APX = [(455, 560), (470, 553), (480, 560), (495, 562), (525, 568), (530, 580),
            (527, 605), (510, 610), (485, 606), (470, 610), (455, 600), (450, 580)]

CORE_APX = [(70, 350), (200, 290), (240, 240), (420, 236), (440, 330), (580, 340),
            (590, 520), (560, 625), (450, 650), (300, 700), (140, 666), (80, 570),
            (68, 450)]

DWELLINGS = [   # centre (community px), pods (dx, dy, rx, ry) in metres, roof, yaw
    dict(c=(180, 449), pods=[(0, 0, 4.6, 4.0), (5.2, 2.0, 3.0, 2.7), (-3.4, 4.0, 2.4, 2.2)],
         roof='sod', yaw=20),
    dict(c=(150, 485), pods=[(0, 0, 4.0, 4.8), (-1.5, -5.2, 2.8, 2.4)], roof='plaster', yaw=-10),
    dict(c=(148, 540), pods=[(0, 0, 4.4, 3.8), (4.4, -2.8, 2.9, 2.6), (-3.0, -4.0, 2.6, 2.3),
                             (-4.0, 3.0, 2.0, 1.9)], roof='sod', yaw=35),
    dict(c=(217, 595), pods=[(0, 0, 4.8, 3.6), (-4.6, -3.2, 2.8, 3.0), (3.6, 3.6, 2.6, 2.4)],
         roof='shingle', yaw=-25),
    dict(c=(305, 585), pods=[(0, 0, 4.2, 4.2), (4.8, -1.4, 3.0, 2.6), (-2.0, -4.8, 2.6, 2.2),
                             (-4.4, 1.6, 2.2, 2.4)], roof='plaster', yaw=10),
]

COMMONS_C = (-17.0, -12.0)
COMMONS_R = (9.0, 21.0)
COMMONS_ANG = (160.0, 285.0)
COMMONS_WEDGES = 5

PLAYGROUND = dict(fig=W(430, 497), dome=(49.0, -20.0), swings=(63.0, -22.5),
                  slide=(54.0, -12.5), sandbox=(45.5, -11.0))
SAUNA = (63.0, -39.0)
BARN = (W(378, 397), -16.0)
GREENHOUSE = dict(c=((17.2 + 44.5) / 2, (86.6 + 74.1) / 2), L=26.0, Wd=10.0)
HYDRO = dict(c=(36.6, 69.6), L=11.0, Wd=8.0)
RECLAIM = W(268, 256)
PUMP = W(208, 348)
PV = dict(c=(-10.0, 13.0), rows=3)
DISH = (-13.5, 9.6)
ENTRANCE_SIGN = W(28, 350)
BRIDGE = (W(418, 385), 30.0)


# ----------------------------------------------------------------------------
# noise and geometry helpers
# ----------------------------------------------------------------------------

def vnoise(x, y, scale, seed=0):
    rng = np.random.default_rng(seed)
    perm = rng.random((257, 257))
    gx, gy = np.asarray(x) / scale + 1000.0, np.asarray(y) / scale + 1000.0
    ix, iy = np.floor(gx).astype(int), np.floor(gy).astype(int)
    fx, fy = gx - ix, gy - iy
    sx, sy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    ix, iy = ix % 256, iy % 256
    a, b = perm[iy, ix], perm[iy, ix + 1]
    c, d = perm[iy + 1, ix], perm[iy + 1, ix + 1]
    return a + (b - a) * sx + (c - a) * sy + (a - b - c + d) * sx * sy


def fbm(x, y, scale, octaves=5, seed=0):
    tot, amp, s, acc = 0.0, 1.0, scale, 0.0
    for o in range(octaves):
        acc = acc + amp * vnoise(x, y, s, seed + 17 * o)
        tot += amp
        amp *= 0.5
        s *= 0.5
    return acc / tot


def gauss(x, y, c, s):
    return np.exp(-(((x - c[0]) / s[0]) ** 2 + ((y - c[1]) / s[1]) ** 2) / 2)


def poly_mask(grid: og.Grid, shape, poly_world, width=0):
    img = Image.new('L', (shape[1], shape[0]), 0)
    d = ImageDraw.Draw(img)
    cols, rows = grid.pixel(*np.array(poly_world).T)
    pts = list(zip(cols.tolist(), rows.tolist()))
    if width:
        d.line(pts, fill=255, width=int(width), joint='curve')
    else:
        d.polygon(pts, fill=255)
    return np.asarray(img) > 0


def smooth_poly(pts, closed=False, passes=3, spacing=1.5):
    p = np.asarray(pts, float)
    if closed:
        p = np.vstack([p, p[:1]])
    p = og.resample(p, spacing)
    for _ in range(passes):
        if closed:
            p = 0.25 * np.roll(p, 1, 0) + 0.5 * p + 0.25 * np.roll(p, -1, 0)
        else:
            p[1:-1] = 0.25 * p[:-2] + 0.5 * p[1:-1] + 0.25 * p[2:]
    return p


def scale_poly(pts, k):
    p = np.asarray(pts, float)
    c = p.mean(0)
    return c + (p - c) * k


# ----------------------------------------------------------------------------
# layout: the one source both the painter and the modeller read
# ----------------------------------------------------------------------------

class Layout:
    """Every placement decision, made once. The site map texture paints
    shadows under the very trees the scene plants, so the two must agree."""

    def __init__(self):
        self.plan = pt.trace()
        self.lake = np.array(LAKE)
        self.pool = scale_poly(WL(POOL_APX), 0.6)
        self.core = np.array(WL(CORE_APX))
        self.roads = [smooth_poly(WL(ROAD_ENTRANCE)),
                      smooth_poly(WL(ROAD_GARDEN_LOOP[:-1]), closed=True),
                      smooth_poly(WL(ROAD_OUTER_LOOP))] + \
                     [smooth_poly(WL(r), passes=1) for r in ROAD_SPURS]
        self.paths = [smooth_poly(WL(p), passes=2) for p in PATHS]
        self.trails = [smooth_poly(WL(t), passes=3) for t in TRAILS]
        self.loop = smooth_poly(WL(ROAD_GARDEN_LOOP[:-1]), closed=True)
        # a raster of the site for masks and distance fields, 0.5 m/px
        self.g = og.Grid(m=0.5, origin=(X0, Y1))
        self.shape = (int((Y1 - Y0) / 0.5), int((X1 - X0) / 0.5))
        self.lake_mask = poly_mask(self.g, self.shape, self.lake)
        self.core_mask = poly_mask(self.g, self.shape, self.core)
        self.lake_in = ndi.distance_transform_edt(self.lake_mask) * 0.5
        self.lake_out = ndi.distance_transform_edt(~self.lake_mask) * 0.5
        self.core_out = ndi.distance_transform_edt(~self.core_mask) * 0.5
        self.dwellings = [self._dwelling_layout(d) for d in DWELLINGS]
        self.pool_in = ndi.distance_transform_edt(
            poly_mask(self.g, self.shape, scale_poly(self.pool, 1.04))) * 0.5
        self.pads = self._pads()
        self.pad_out = ndi.distance_transform_edt(~self.pads) * 0.5
        self.trees = self._plant_trees()

    def _dwelling_layout(self, d):
        cx, cy = W(*d['c'])
        a = math.radians(d['yaw'])
        R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
        pods = []
        for dx, dy, rx, ry in d['pods']:
            p = R @ np.array([dx, dy])
            pods.append((cx + p[0], cy + p[1], rx, ry))
        return dict(c=(cx, cy), pods=pods, roof=d['roof'], yaw=d['yaw'])

    def _pads(self):
        """Ground that must be flat and just below z=0: under every building."""
        H, Wd = self.shape
        cols, rows = np.meshgrid(np.arange(Wd), np.arange(H))
        x, y = self.g.world(cols, rows)
        pc, pr = pt.to_plan(x, y)
        school = ndi.map_coordinates(self.plan.building.astype(float), [pr, pc],
                                     order=0, mode='constant') > 0.5
        pads = school.copy()
        for d in self.dwellings:
            for (px, py, rx, ry) in d['pods']:
                pads |= ((x - px) / (rx + 2.5)) ** 2 + ((y - py) / (ry + 2.5)) ** 2 <= 1
        for (c, L, Wd_) in ((GREENHOUSE['c'], GREENHOUSE['L'] + 4, GREENHOUSE['Wd'] + 4),
                            (HYDRO['c'], HYDRO['L'] + 4, HYDRO['Wd'] + 4)):
            pads |= (np.abs(x - c[0]) < L / 2) & (np.abs(y - c[1]) < Wd_ / 2)
        pads |= poly_mask(self.g, self.shape, scale_poly(self.loop, 0.9))
        pool = poly_mask(self.g, self.shape, scale_poly(self.pool, 1.35))
        pads |= pool
        for (px, py), r in ((SAUNA, 6), (BARN[0], 9), (RECLAIM, 12), (PUMP, 5),
                            (PLAYGROUND['dome'], 6), (COMMONS_C, 23), (PLAYGROUND['fig'], 13),
                            (TOWER_XY, 6), (ENTRANCE_SIGN, 5)):
            pads |= (x - px) ** 2 + (y - py) ** 2 <= r * r
        # the school's surroundings stay level too, so it doesn't sit in a dip
        pads = ndi.binary_dilation(pads, iterations=4)
        return pads & ~self.lake_mask

    def sample(self, field, x, y, order=1):
        c, r = self.g.pixel(x, y)
        return ndi.map_coordinates(field, [np.atleast_1d(r), np.atleast_1d(c)],
                                   order=order, mode='nearest')

    def height(self, x, y):
        """Terrain elevation (m). Hills NW, a gentle forest rise NE, the lake
        bowl, and level pads under everything built."""
        scalar = np.ndim(x) == 0
        x, y = np.asarray(x, float), np.asarray(y, float)
        hills = (26 * gauss(x, y, (-130, 100), (55, 42))
                 + 15 * gauss(x, y, (-70, 128), (38, 26))
                 + 11 * gauss(x, y, (-155, 20), (26, 50))
                 + 7 * gauss(x, y, (120, 100), (48, 34))
                 + 4 * gauss(x, y, (150, -90), (40, 45)))
        rough = fbm(x, y, 60, 5, seed=11) - 0.5
        hill_w = np.clip(hills / 10, 0, 1)
        h = hills + rough * (1.6 + 6.0 * hill_w)
        h -= 0.03 * np.clip(-(y + 50), 0, None) * (1 - hill_w)
        core_d = self.sample(self.core_out, x, y)
        flat = 1 - tx_smooth(0, 35, core_d)
        h = h * (1 - flat) + (rough * 0.3) * flat
        pad_d = self.sample(self.pad_out, x, y)
        pad_w = 1 - tx_smooth(0, 8, pad_d)
        h = h * (1 - pad_w) + (-0.06) * pad_w
        pool_d = self.sample(self.pool_in, x, y)
        h = np.where(pool_d > 0, -1.45, h)
        # The terrain runs under the school at grade, so anything built below
        # grade must have the ground taken out from under it, or the ground
        # is what you see: the Main Hall's sunken lower level. Over-cut by a
        # terrain cell so the slope back up is hidden beneath the floor slab.
        from school import PIT_C, PIT_RX, PIT_RY
        e = (((x - PIT_C[0]) / (PIT_RX + 1.6)) ** 2
             + ((y - PIT_C[1]) / (PIT_RY + 1.6)) ** 2)
        h = np.where(e <= 1.0, -1.3, h)
        lin = self.sample(self.lake_in, x, y)
        lout = self.sample(self.lake_out, x, y)
        inside = lin > 0
        bowl = -0.5 - 2.3 * tx_smooth(0, 9, lin)
        shore = tx_smooth(0, 6, lout)
        h = np.where(inside, bowl, h * shore + (-0.35) * (1 - shore))
        return float(np.ravel(h)[0]) if scalar else h

    # -- trees ---------------------------------------------------------

    def _blocked(self, x, y, margin):
        """True where a tree must not stand: roads, buildings, lake, paths."""
        if self.sample(self.pad_out, x, y)[0] < margin:
            return True
        if self.sample(self.lake_out, x, y)[0] < margin * 0.6:
            return True
        for line in self.roads + self.paths:
            if np.min(np.hypot(line[:, 0] - x, line[:, 1] - y)) < margin + 2.5:
                return True
        if np.min(np.hypot(self.loop[:, 0] - x, self.loop[:, 1] - y)) < margin + 3:
            return True
        return False

    def _in_garden(self, x, y):
        return poly_contains(self.loop, x, y)

    def _plant_trees(self):
        rng = np.random.default_rng(2026)
        trees = []

        def poisson(region_fn, spacing, count_try, kind_fn, margin=3.0):
            pts = []
            for _ in range(count_try):
                x = rng.uniform(X0 + 6, X1 - 6)
                y = rng.uniform(Y0 + 6, Y1 - 6)
                if not region_fn(x, y):
                    continue
                if any((x - px) ** 2 + (y - py) ** 2 < spacing ** 2 for px, py in pts):
                    continue
                if self._blocked(x, y, margin) or self._in_garden(x, y):
                    continue
                pts.append((x, y))
                trees.append(dict(kind=kind_fn(x, y), x=x, y=y,
                                  yaw=float(rng.uniform(0, 360)),
                                  s=float(rng.uniform(0.8, 1.2))))

        # forest NE: oak and sycamore low, pine on the rise
        poisson(lambda x, y: (y > 40 and x > 36 and not (x < 50 and y < 90))
                or (x > 108 and y > -40),
                8.5, 9000,
                lambda x, y: 'pine' if (x - 120) ** 2 + (y - 100) ** 2 < 32 ** 2
                and rng.random() < 0.6 else ('sycamore' if rng.random() < 0.25 else 'oak'))
        # the hills: scattered oaks in the folds, pines toward the ridge
        poisson(lambda x, y: (x < -60 and y > 40) or (x < -110),
                13.0, 6000,
                lambda x, y: 'pine' if rng.random() < 0.45 else 'oak', margin=2.0)
        # shading the homes and the commons, and the lake shore
        for d in self.dwellings:
            for k in range(3):
                a = rng.uniform(0, 2 * math.pi)
                r = rng.uniform(10, 15)
                x, y = d['c'][0] + math.cos(a) * r, d['c'][1] + math.sin(a) * r
                if not self._blocked(x, y, 2.0):
                    trees.append(dict(kind='oak', x=x, y=y, yaw=float(rng.uniform(0, 360)),
                                      s=float(rng.uniform(0.9, 1.15))))
        for k in range(26):
            t = rng.uniform(0, 1)
            i = int(t * (len(self.lake) - 1))
            p = self.lake[i] + (self.lake[(i + 1) % len(self.lake)] - self.lake[i]) * rng.random()
            c = self.lake.mean(0)
            out = (p - c) / (np.linalg.norm(p - c) + 1e-9)
            x, y = p + out * rng.uniform(4, 9)
            if p[0] < 50 and p[1] < 15:          # leave the pond by the school open
                continue
            if not self._blocked(x, y, 1.5):
                trees.append(dict(kind='sycamore', x=float(x), y=float(y),
                                  yaw=float(rng.uniform(0, 360)), s=float(rng.uniform(0.8, 1.05))))
        # olives along the entrance road
        road = self.roads[0]
        for k in range(4, len(road) - 6, 7):
            for side in (-1, 1):
                p, q = road[k], road[k + 1]
                t = (q - p) / (np.linalg.norm(q - p) + 1e-9)
                n = np.array([-t[1], t[0]]) * side * 6.0
                x, y = p + n
                trees.append(dict(kind='olive', x=float(x), y=float(y),
                                  yaw=float(rng.uniform(0, 360)), s=float(rng.uniform(0.9, 1.1))))
        # chaparral: low shrubs on the hills
        for _ in range(3000):
            x, y = rng.uniform(X0 + 3, X1 - 3), rng.uniform(Y0 + 3, Y1 - 3)
            hill = (x < -55 and y > 30) or (x < -105) or (y < -95)
            if not hill or rng.random() < 0.3:
                continue
            if self._blocked(x, y, 1.0):
                continue
            trees.append(dict(kind='shrub', x=x, y=y, yaw=float(rng.uniform(0, 360)),
                              s=float(rng.uniform(0.6, 1.5))))
            if sum(1 for t in trees if t['kind'] == 'shrub') >= 240:
                break
        return trees


TOWER_XY = (-13.9, 0.6)


def tx_smooth(e0, e1, x):
    t = np.clip((np.asarray(x, float) - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def poly_contains(poly, x, y):
    p = np.asarray(poly)
    xs, ys = p[:, 0], p[:, 1]
    xj, yj = np.roll(xs, 1), np.roll(ys, 1)
    cross = ((ys > y) != (yj > y)) & (x < (xj - xs) * (y - ys) / (yj - ys + 1e-12) + xs)
    return bool(np.sum(cross) % 2)


@functools.lru_cache(maxsize=1)
def layout() -> Layout:
    return Layout()


# ----------------------------------------------------------------------------
# textures
# ----------------------------------------------------------------------------

SITE_PX = 2048


def site_to_px(x, y):
    return ((np.asarray(x) - X0) / (X1 - X0) * SITE_PX,
            (Y1 - np.asarray(y)) / (Y1 - Y0) * SITE_PX)


def paint_site_map(L: Layout):
    """The whole site as one image draped on the terrain: meadow, chaparral,
    forest floor, roads, paths, beds, the lakebed -- with the hillshade and
    the shadows of every tree and building baked in."""
    S = SITE_PX
    ys, xs = np.mgrid[0:S, 0:S]
    x = X0 + (xs + 0.5) / S * (X1 - X0)
    y = Y1 - (ys + 0.5) / S * (Y1 - Y0)
    print("    site map: terrain")
    h = L.height(x, y)
    dzdx = np.gradient(h, axis=1) / ((X1 - X0) / S)
    dzdy = -np.gradient(h, axis=0) / ((Y1 - Y0) / S)
    n = np.stack([-dzdx, -dzdy, np.ones_like(h)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    sun = np.array([-0.5, 0.45, 0.74])
    sun /= np.linalg.norm(sun)
    shade = np.clip(n @ sun, 0, 1)

    meadow = fbm(x, y, 40, 5, seed=3)
    fine = fbm(x, y, 3, 3, seed=8)
    gold = np.array([0.66, 0.60, 0.36])
    green = np.array([0.42, 0.48, 0.24])
    hills = np.clip((h - 2) / 14, 0, 1)
    wet = np.clip(1 - L.sample(L.lake_out, x.ravel(), y.ravel()).reshape(S, S) / 18, 0, 1)
    mix = np.clip(0.35 + 0.6 * (meadow - 0.5) + 0.5 * wet - 0.2 * hills, 0, 1)
    img = gold * (1 - mix[..., None]) + green * mix[..., None]
    chap = (fbm(x, y, 9, 4, seed=21) > 0.55 - 0.25 * hills) & (hills > 0.15)
    img = np.where(chap[..., None], np.array([0.30, 0.33, 0.20]), img)
    img *= (0.86 + 0.22 * fine)[..., None]

    # forest floor under the NE wood
    forest = np.zeros((S, S))
    for t in L.trees:
        if t['kind'] in ('oak', 'pine', 'sycamore'):
            px, py = site_to_px(t['x'], t['y'])
            forest[int(np.clip(py, 0, S - 1)), int(np.clip(px, 0, S - 1))] = 1
    forest = ndi.gaussian_filter(forest, 18) * 900
    fw = np.clip(forest, 0, 1)[..., None] * 0.7
    img = img * (1 - fw) + np.array([0.33, 0.30, 0.20]) * fw

    print("    site map: roads, paths, gardens")
    # Roads, paths and beds are drawn at 2x and filtered down, so their edges
    # are antialiased: at 0.15 m/px a hard-edged line staircases visibly from
    # a walking-height camera.
    SS = 2
    canvas = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).resize(
        (S * SS, S * SS), Image.BILINEAR)
    d = ImageDraw.Draw(canvas)
    mpp = (X1 - X0) / (S * SS)

    def to_px(x, y):                 # site metres -> 2x canvas pixels
        px, py = site_to_px(x, y)
        return px * SS, py * SS

    def line(pts, width_m, col):
        px, py = to_px(pts[:, 0], pts[:, 1])
        d.line(list(zip(px.tolist(), py.tolist())), fill=col,
               width=max(int(width_m / mpp), 1), joint='curve')

    def poly(pts, col, outline=None, width=1):
        px, py = to_px(np.asarray(pts)[:, 0], np.asarray(pts)[:, 1])
        d.polygon(list(zip(px.tolist(), py.tolist())), fill=col, outline=outline)

    def ellipse(c, rx, ry, col):
        px, py = to_px(c[0], c[1])
        d.ellipse([px - rx / mpp, py - ry / mpp, px + rx / mpp, py + ry / mpp], fill=col)

    # lakebed and shore
    poly(scale_poly(L.lake, 1.05), (176, 160, 118))
    poly(L.lake, (58, 70, 52))
    # garden loop interior: beds west, orchard middle, paddock east
    inner = scale_poly(L.loop, 0.86)
    poly(inner, (118, 128, 66))
    for gx in np.arange(-14, 12, 2.6):
        bed = np.array([(gx, 34), (gx + 1.4, 34), (gx + 1.4, 62), (gx, 62)])
        poly(bed, (92, 66, 44))
    paddock = np.array([(32, 34), (52, 34), (52, 19), (32, 19)])
    poly(paddock, (150, 126, 86))
    for t in L.trails:
        line(t, 1.2, (170, 150, 112))
    for r in L.roads:
        line(r, 6.4, (128, 112, 86))
        line(r, 5.0, (186, 168, 128))
    for p in L.paths:
        line(p, 2.0, (198, 182, 146))
    # commons green and terraces
    ellipse(COMMONS_C, 8.5, 8.5, (96, 128, 60))
    ellipse(COMMONS_C, 3.6, 3.6, (180, 160, 130))
    # playground: wood-chip mulch; pool deck stone
    ellipse(PLAYGROUND['fig'], 13, 12, (136, 110, 76))
    ellipse(PLAYGROUND['dome'], 6, 6, (150, 122, 84))
    poly(scale_poly(L.pool, 1.35), (196, 186, 166))
    ellipse(SAUNA, 5.5, 5.5, (196, 186, 166))
    # water reclamation reed bed
    rx, ry = RECLAIM
    poly([(rx - 4, ry - 9), (rx + 9, ry - 9), (rx + 9, ry - 2), (rx - 4, ry - 2)], (64, 84, 52))
    img = np.asarray(canvas.resize((S, S), Image.LANCZOS)).astype(float) / 255.0
    mpp = (X1 - X0) / S

    print("    site map: shadows and light")
    off = np.array([1.2, -1.0])          # sun from the north-west -> shadows SE
    sh_img = Image.new('L', (S, S), 0)
    sd = ImageDraw.Draw(sh_img)
    radius = dict(oak=6.5, pine=3.6, sycamore=5.5, olive=3.0, shrub=1.0, fruit=2.4)
    for t in L.trees:
        r = radius.get(t['kind'], 3) * t['s']
        cx, cy = t['x'] + off[0] * r * 0.5, t['y'] + off[1] * r * 0.5
        px, py = site_to_px(cx, cy)
        sd.ellipse([px - r / mpp, py - r / mpp, px + r / mpp, py + r / mpp], fill=150)
    # buildings cast soft shadows too
    plan = L.plan
    for d_ in L.dwellings:
        for (px_, py_, rx_, ry_) in d_['pods']:
            cx, cy = px_ + 1.6, py_ - 1.4
            qx, qy = site_to_px(cx, cy)
            sd.ellipse([qx - rx_ / mpp, qy - ry_ / mpp, qx + rx_ / mpp, qy + ry_ / mpp], fill=170)
    sh = np.asarray(sh_img.filter(ImageFilter.GaussianBlur(4))) / 255.0
    # the school's footprint shadow, from the traced plan
    sx, sy = np.meshgrid(np.arange(S), np.arange(S))
    wx = X0 + (sx + 0.5) / S * (X1 - X0) - 2.0
    wy = Y1 - (sy + 0.5) / S * (Y1 - Y0) + 1.8
    pc, pr = pt.to_plan(wx, wy)
    sch = ndi.map_coordinates(plan.building.astype(float), [pr, pc], order=1, mode='constant')
    sh = np.maximum(sh, ndi.gaussian_filter(sch, 3) * 0.7)
    img *= (1 - 0.45 * sh)[..., None]
    img *= (0.74 + 0.42 * shade)[..., None]
    return np.clip(img, 0, 1)


def crops(seed=4):
    """Garden-bed tops: rows of greens on dark soil (one tile per bed)."""
    H, Wd = 512, 128
    rng = np.random.default_rng(seed)
    soil = tk.tint(tk.fbm(H, Wd, 8, 4, seed=seed), (0.22, 0.15, 0.09), (0.36, 0.25, 0.15))
    img = soil.copy()
    yy, xx = np.mgrid[0:H, 0:Wd]
    for row, (col, sz) in enumerate([((0.30, 0.55, 0.22), 10), ((0.45, 0.62, 0.20), 7),
                                     ((0.20, 0.42, 0.18), 12)]):
        cxr = (row + 0.5) * Wd / 3
        for cy in range(6, H, int(sz * 1.6)):
            r = sz * rng.uniform(0.7, 1.1)
            m = (xx - cxr) ** 2 + (yy - cy) ** 2 < r * r
            img[m] = np.array(col) * rng.uniform(0.8, 1.2)
    return img


def wildflower_bed(seed=9):
    img = crops(seed)
    rng = np.random.default_rng(seed)
    H, Wd, _ = img.shape
    dots = rng.random((H, Wd)) > 0.985
    pal = np.array([[0.95, 0.75, 0.2], [0.85, 0.35, 0.55], [0.6, 0.4, 0.85], [0.95, 0.95, 0.9]])
    img[dots] = pal[rng.integers(0, 4, dots.sum())]
    return img


def title_sign():
    """The title block of Jeff's community drawing, for the entrance sign."""
    g = Image.open(HERE / "drawings" / "banyan_community.png").convert('L')
    crop = g.crop((70, 60, 380, 150))
    arr = np.asarray(crop).astype(float) / 255.0
    ink = np.array([0.18, 0.12, 0.06])
    board = np.array([0.88, 0.80, 0.62])
    img = ink + (board - ink) * arr[..., None]
    grain = tk.fbm(img.shape[0], img.shape[1], 6, 4, seed=3)
    img *= (0.9 + 0.12 * grain)[..., None]
    return img


def paint_textures(media_dir, put):
    L = layout()
    T = {}

    def p(role, fname, img):
        put(role, fname, img)
        T[role] = fname

    print("    painting the site map")
    p('site', "site_map.png", paint_site_map(L))
    p('water', "water.png", tx.water())
    p('pool', "pool_water.png", tx.pool_water())
    p('bark', "bark.png", tk.bark(256, 256, seed=2))
    p('fig_bark', "bark_fig.png", tx.fig_bark())
    p('leaves', "leaves.png", tk.foliage(256, 256, seed=5, base=(0.20, 0.36, 0.16)))
    p('leaves_pine', "leaves_pine.png", tk.foliage(256, 256, seed=7, base=(0.14, 0.28, 0.16)))
    p('leaves_olive', "leaves_olive.png", tk.foliage(256, 256, seed=9, base=(0.38, 0.44, 0.30)))
    p('leaves_syc', "leaves_sycamore.png", tk.foliage(256, 256, seed=11, base=(0.34, 0.48, 0.20)))
    p('cottage', "cottage_wall.png", tx.cottage_wall())
    p('sod', "roof_sod.png", tx.sod_roof())
    p('shingle', "roof_shingle.png", tx.cedar_shingle())
    p('solar', "solar.png", tx.solar())
    p('crops', "crops.png", crops())
    p('flowers', "flower_bed.png", wildflower_bed())
    p('sign', "entrance_sign.png", title_sign())
    return T


# ----------------------------------------------------------------------------
# modelling
# ----------------------------------------------------------------------------

def terrain_mesh(L: Layout, cell=1.5):
    xs = np.arange(X0, X1 + 1e-6, cell)
    ys = np.arange(Y0, Y1 + 1e-6, cell)
    X, Y = np.meshgrid(xs, ys)
    Z = L.height(X, Y)
    m = mk.Mesh("terrain")
    ny, nx = X.shape
    u = (X - X0) / (X1 - X0)
    v = (Y - Y0) / (Y1 - Y0)
    idx = np.zeros(X.shape, int)
    for j in range(ny):
        for i in range(nx):
            idx[j, i] = m.vert((X[j, i], Y[j, i], Z[j, i]), (u[j, i], v[j, i]))
    for j in range(ny - 1):
        for i in range(nx - 1):
            m.quad(idx[j, i], idx[j, i + 1], idx[j + 1, i + 1], idx[j + 1, i])
    return m


def water_mesh(L: Layout, poly, z, uv_scale=1 / 12.0):
    g = og.Grid(m=0.25, origin=(float(np.min(poly[:, 0])) - 3, float(np.max(poly[:, 1])) + 3))
    shape = (int((np.ptp(poly[:, 1]) + 6) / 0.25), int((np.ptp(poly[:, 0]) + 6) / 0.25))
    mask = poly_mask(g, shape, poly)
    return og.slab_from_mask(mask, g, lambda x, y: np.full(np.shape(x), z), cell=8,
                             uv_fn=lambda x, y: (x * uv_scale, y * uv_scale), name="water"), g, mask


def plant(kit, tex, spec, x, y, z, yaw, scale, label, leaf_tex=None):
    """One tree: a hidden rig at the base, trunk and canopy under it. Each
    part sits at its own bounding-box centre at scale = its radius (pos 0 +
    the placement offset Kit.place adds), which `Model.assembly` with the
    anchor at the trunk base makes exact."""
    rig = kit.rig((x, y, z), yaw=yaw, s=scale, text=label)
    for key in ('trunk', 'canopy'):
        kit.place(spec['files'][key], (0.0, 0.0, 0.0), parent=rig,
                  color=spec['bt'] if key == 'trunk' else spec['lt'],
                  texture=tex['bark'] if key == 'trunk' else tex[leaf_tex or spec['leaf']])
    return rig


def build_trees(kit, tex, L: Layout):
    """Five species from the lab's tree grower, plus a shrub, each modelled
    once and planted many times."""
    species = {
        'oak': (7, dict(depth=5, base_len=4.2, base_rad=0.55, spread=(32, 62),
                        shrink=0.78, split=(2, 3)), 1.15, 'leaves', (245, 236, 226), (236, 244, 226)),
        'pine': (21, dict(depth=5, base_len=9.0, base_rad=0.42, spread=(14, 30),
                          shrink=0.70, taper=0.62), 0.55, 'leaves_pine', (225, 215, 205), (220, 240, 225)),
        'sycamore': (33, dict(depth=5, base_len=6.0, base_rad=0.45, spread=(22, 44),
                              shrink=0.76), 0.85, 'leaves_syc', (252, 250, 245), (240, 250, 225)),
        'olive': (41, dict(depth=4, base_len=2.2, base_rad=0.26, spread=(30, 55),
                           shrink=0.8), 1.0, 'leaves_olive', (230, 225, 215), (235, 240, 230)),
        'fruit': (51, dict(depth=4, base_len=1.6, base_rad=0.16, spread=(30, 55),
                           shrink=0.78), 1.05, 'leaves', (240, 230, 220), (230, 250, 220)),
    }
    built = {}
    for name, (seed, kw, cs, leaf_tex, bark_tint, leaf_tint) in species.items():
        r = np.random.default_rng(seed)
        branches, tips = grow(r, **kw)
        model = mk.Model(name)
        model.parts['trunk'] = build_trunk(branches)
        model.parts['canopy'] = build_canopy(r, tips, cs)
        files = {k: kit.mesh(f"tree_{name}_{k}.obj", m) for k, m in model.parts.items()}
        lo, hi = model.bounds()
        built[name] = dict(files=files, asm=model.assembly(anchor=(0, 0, 0)),
                           height=float(hi[2]), leaf=leaf_tex, bt=bark_tint, lt=leaf_tint)
    shrub = mk.Mesh("shrub")
    rng = np.random.default_rng(5)
    for k in range(4):
        a = k * math.pi / 2 + rng.uniform(-0.4, 0.4)
        shrub.extend(fu.blob(0.9, 0.8, 0.55, seg=(8, 5)),
                     mk.translate(math.cos(a) * 0.6, math.sin(a) * 0.6, 0.0))
    kit.mesh("tree_shrub.obj", shrub)

    target = dict(oak=11.0, pine=17.0, sycamore=14.0, olive=5.0, fruit=4.0)
    names = dict(oak="Coast live oak", pine="Coulter pine", sycamore="Western sycamore",
                 olive="Olive — along the entrance road", fruit="Avocado — the orchard")
    counts = {}
    for t in L.trees:
        z = float(L.height(t['x'], t['y']))
        counts[t['kind']] = counts.get(t['kind'], 0) + 1
        if t['kind'] == 'shrub':
            kit.place("tree_shrub.obj", (t['x'], t['y'], z - 0.1), yaw=t['yaw'], s=t['s'],
                      color=(84, 96, 60), text="Chaparral — chamise and scrub oak")
            continue
        spec = built[t['kind']]
        sc = target[t['kind']] / spec['height'] * t['s']
        plant(kit, tex, spec, t['x'], t['y'], z - 0.15, t['yaw'], sc, names[t['kind']])
    print("  trees:", ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    return built


def build(kit, tex, school, pieces):
    L = layout()
    pieces_ref.update(pieces)
    pieces_ref['lounger'] = kit.mesh("site_lounger.obj", lounger())
    print("  site: terrain")
    kit.world("site_terrain.obj", terrain_mesh(L), color=(255, 255, 255),
              texture=tex['site'],
              text="The land — about 11 acres in the hills north-east of San "
                   "Diego, digitized from 'The Initial Community'")
    print("  site: water")
    lake, _, _ = water_mesh(L, L.lake, -0.42)
    kit.world("site_lake.obj", lake, color=(225, 240, 245), texture=tex['water'],
              alpha=215, text="Lake & pond", pin=True)
    build_pool(kit, tex, L)
    build_buildings(kit, tex, L)
    build_dwellings(kit, tex, L)
    build_commons(kit, tex, L, pieces)
    build_garden(kit, tex, L)
    build_playground(kit, tex, L)
    built = build_trees(kit, tex, L)
    plant_orchard(kit, tex, L, built)
    # the courtyard's young tree
    cx, cy = school.courtyard_tree
    plant(kit, tex, built['olive'], cx, cy, 0.03, 40.0, 4.2 / built['olive']['height'],
          "The courtyard tree — a young olive")
    # places that are areas rather than objects get a wooden trail sign
    kit.mesh("site_signpost.obj", signpost())
    for (x, y), label in (
            (W(150, 362), "Hills — hiking and mountain biking"),
            (W(420, 300), "Forests — oak, sycamore and pine"),
            (W(545, 360), "Nature Trails"),
            ((PLAYGROUND['fig'][0] - 12.0, PLAYGROUND['fig'][1] - 4.0), "Playground")):
        kit.place("site_signpost.obj", (x, y, float(L.height(x, y)) - 0.05), yaw=30,
                  color=(150, 110, 72), text=label, pin=label.startswith("Hills"))


def build_pool(kit, tex, L):
    poly = L.pool
    water, g, mask = water_mesh(L, poly, -0.12, uv_scale=1 / 4.0)
    kit.world("site_pool_water.obj", water, color=(240, 250, 255), texture=tex['pool'],
              alpha=230, text="Pool", pin=True)
    coping = ndi.binary_dilation(mask, iterations=3) & ~mask
    m = og.walls_from_mask(coping, g, -1.4, 0.12, uv_scale=0.5)
    m.extend(og.slab_from_mask(coping, g, lambda x, y: np.full(np.shape(x), 0.12), cell=1,
                               uv_fn=lambda x, y: (x * 0.5, y * 0.5)))
    kit.world("site_pool_coping.obj", m, color=(245, 240, 232), texture=tex['stone'],
              text="Pool coping — fieldstone")
    # lounge chairs
    c = poly.mean(0)
    for k in range(5):
        x, y = c[0] - 6 + k * 2.4, c[1] - 9.5
        kit.place(pieces_ref['lounger'], (x, y, 0.0), yaw=0, color=(236, 236, 230),
                  text="Pool lounger")


# Shared furniture pieces (registered by the school) plus the site's own,
# filled in by build() so the builders below can reach them.
pieces_ref = {}


def _gable_box(m, w, d, h, roof_h, cx=0.0, cy=0.0):
    """A rectangular building with a gable roof along x (walls + roof)."""
    m.extend(mk.box(size=(w, d, h), center=(cx, cy, h / 2), uv_world=True, uv_scale=0.5))
    roof = mk.Mesh("roof")
    x0, x1 = cx - w / 2 - 0.4, cx + w / 2 + 0.4
    y0, y1 = cy - d / 2 - 0.4, cy + d / 2 + 0.4
    z0, z1 = h, h + roof_h
    roof.add_quad((x0, y0, z0), (x1, y0, z0), (x1, cy, z1), (x0, cy, z1),
                  uvs=[(0, 0), (w / 2, 0), (w / 2, d / 2), (0, d / 2)])
    roof.add_quad((x1, y1, z0), (x0, y1, z0), (x0, cy, z1), (x1, cy, z1),
                  uvs=[(0, 0), (w / 2, 0), (w / 2, d / 2), (0, d / 2)])
    gable = mk.Mesh("gable")
    for x, sgn in ((cx - w / 2, -1), (cx + w / 2, 1)):
        a = gable.vert((x, cy - d / 2, h), (0, 0))
        b = gable.vert((x, cy + d / 2, h), (1, 0))
        c = gable.vert((x, cy, h + roof_h * 0.92), (0.5, 0.5))
        if sgn > 0:
            gable.tri(a, c, b)
        else:
            gable.tri(a, b, c)
    m.extend(gable)
    return roof


def build_buildings(kit, tex, L):
    """The support buildings, each a small honest shape."""
    # greenhouse: a gothic-arch hoop house, glass skin and white ribs
    gc, gl, gw = GREENHOUSE['c'], GREENHOUSE['L'], GREENHOUSE['Wd']
    prof = []
    for t in np.linspace(0, 1, 13):
        a = t * math.pi
        x = -math.cos(a) * gw / 2
        z = 1.4 + math.sin(a) ** 0.8 * 3.6
        prof.append((x, z))
    glass, ribs = mk.Mesh("gh_glass"), mk.Mesh("gh_ribs")
    secs = []
    for s in np.linspace(-gl / 2, gl / 2, 2):
        secs.append([(gc[0] + s, gc[1] + x, z) for (x, z) in
                     [(-gw / 2, 0.0)] + prof + [(gw / 2, 0.0)]])
    glass.extend(mk.loft(secs, closed=False))
    for s in (-gl / 2, gl / 2):
        pts = [(gc[0] + s, gc[1] + x, z) for (x, z) in [(-gw / 2, 0.0)] + prof + [(gw / 2, 0.0)]]
        fan = mk.Mesh("end")
        ci = fan.vert((gc[0] + s, gc[1], 1.6))
        ids = [fan.vert(p) for p in pts]
        for k in range(len(ids) - 1):
            fan.tri(ci, ids[k], ids[k + 1])
        glass.extend(fan)
    for s in np.linspace(-gl / 2, gl / 2, 14):
        pts = [(gc[0] + s, gc[1] + x, z) for (x, z) in [(-gw / 2, 0.0)] + prof + [(gw / 2, 0.0)]]
        ribs.extend(mk.tube(pts, 0.06, segments=5))
    for x in (-gw / 2 + 0.05, gw / 2 - 0.05, 0.0):
        ribs.extend(mk.tube([(gc[0] - gl / 2, gc[1] + x, 1.4 if x else 1.4),
                             (gc[0] + gl / 2, gc[1] + x, 1.4)], 0.05, segments=5))
    hc, hl, hw = HYDRO['c'], HYDRO['L'], HYDRO['Wd']
    hx = mk.Mesh("hydro")
    hx.extend(mk.box(size=(hl, hw, 3.2), center=(hc[0], hc[1], 1.6)))
    glass.extend(hx)
    kit.world("site_greenhouse_ribs.obj", ribs, color=(238, 240, 240),
              text="Greenhouse & Hydroponics — frame")
    tables = mk.Mesh("gh_tables")
    plants = mk.Mesh("gh_plants")
    for row in (-2.6, 0.0, 2.6):
        tables.extend(mk.box(size=(gl - 3, 1.3, 0.8), center=(gc[0], gc[1] + row, 0.4)))
        for k in np.arange(-gl / 2 + 2, gl / 2 - 2, 0.7):
            plants.extend(fu.blob(0.32, 0.32, 0.22, seg=(6, 4)),
                          mk.translate(gc[0] + k, gc[1] + row, 0.8))
    for row in (-2.0, 0.0, 2.0):
        tables.extend(mk.box(size=(hl - 2, 0.6, 1.0), center=(hc[0], hc[1] + row, 0.5)))
        for k in np.arange(-hl / 2 + 1.5, hl / 2 - 1.5, 0.5):
            plants.extend(fu.blob(0.18, 0.18, 0.16, seg=(6, 4)),
                          mk.translate(hc[0] + k, hc[1] + row, 1.0))
    kit.world("site_greenhouse_tables.obj", tables, color=(150, 120, 90),
              text="Greenhouse benches and hydroponic channels")
    kit.world("site_greenhouse_plants.obj", plants, color=(80, 150, 70),
              text="Seedlings and greens")
    kit.world("site_greenhouse_glass.obj", glass, color=(205, 235, 240), alpha=80,
              text="Greenhouse & Hydroponics", pin=True)

    # barn: red gambrel-ish barn with a paddock fence, goats and chickens
    (bx, by), yaw = BARN
    barn = mk.Mesh("barn")
    roof = _gable_box(barn, 10.0, 7.0, 3.6, 2.6)
    kit.place(kit.mesh("site_barn.obj", barn), (bx, by, -0.05), yaw=yaw,
              color=(150, 52, 40), texture=0, text="Barn — goats, chickens, tools")
    kit.place(kit.mesh("site_barn_roof.obj", roof), (bx, by, -0.05), yaw=yaw,
              color=(110, 106, 100), text="Barn roof")
    fence = mk.Mesh("fence")
    corners = [(32, 34), (52, 34), (52, 19), (32, 19), (32, 34)]
    for a, b in zip(corners[:-1], corners[1:]):
        a, b = np.array(a, float), np.array(b, float)
        n = int(np.linalg.norm(b - a) / 2.4)
        for k in range(n + 1):
            p = a + (b - a) * k / n
            fence.extend(mk.box(size=(0.12, 0.12, 1.2), center=(p[0], p[1], 0.6)))
        for z in (0.55, 1.05):
            fence.extend(mk.tube([(a[0], a[1], z), (b[0], b[1], z)], 0.04, segments=4))
    kit.world("site_fence.obj", fence, color=(150, 120, 86), text="Paddock fence")
    goat = goat_mesh()
    kit.mesh("site_goat.obj", goat)
    rng = np.random.default_rng(8)
    for k in range(6):
        x, y = rng.uniform(36, 50), rng.uniform(21, 31)
        kit.place("site_goat.obj", (x, y, 0.0), yaw=float(rng.uniform(0, 360)),
                  color=[(236, 232, 222), (120, 84, 60), (60, 52, 46)][k % 3],
                  text="Goat — the kids take care of them")
    hen = fu.blob(0.18, 0.13, 0.15, "hen", seg=(8, 5))
    hen.extend(fu.blob(0.07, 0.07, 0.07, seg=(6, 4)), mk.translate(0.17, 0.0, 0.22))
    kit.mesh("site_hen.obj", hen)
    for k in range(10):
        x, y = bx + rng.uniform(-7, 7), by - 5 + rng.uniform(-3, 2)
        kit.place("site_hen.obj", (x, y, 0.0), yaw=float(rng.uniform(0, 360)),
                  color=[(240, 236, 226), (176, 96, 48)][k % 2], text="Chicken")

    # water reclamation: tanks, a treatment shed, and a reed-bed wetland
    rx, ry = RECLAIM
    tanks = mk.Mesh("tanks")
    for dx in (-2.6, 2.6):
        tanks.extend(mk.revolve([(0.0, 0.0), (2.2, 0.0), (2.2, 3.0), (2.0, 3.3), (0.0, 3.4)],
                                segments=20), mk.translate(rx + dx, ry + 4.0, 0.0))
    kit.world("site_reclaim_tanks.obj", tanks, color=(176, 180, 176),
              text="Water Reclamation — settling tanks")
    reeds = mk.Mesh("reeds")
    rng2 = np.random.default_rng(12)
    for _ in range(160):
        x, y = rng2.uniform(rx - 3.5, rx + 8.5), rng2.uniform(ry - 8.5, ry - 2.5)
        h = rng2.uniform(0.8, 1.8)
        reeds.extend(mk.revolve([(0.0, 0.0), (0.12, 0.0), (0.0, h)], segments=4),
                     mk.translate(x, y, -0.1))
    kit.world("site_reclaim_reeds.obj", reeds, color=(108, 140, 62),
              text="Constructed wetland — reeds finish the water for the garden")
    shed = mk.Mesh("shed")
    sroof = _gable_box(shed, 4.0, 3.0, 2.6, 1.2)
    kit.place(kit.mesh("site_shed.obj", shed), (rx - 6.0, ry + 4.0, -0.05), yaw=90,
              color=(196, 186, 168), text="Water Reclamation — pump and filter shed")
    kit.place(kit.mesh("site_shed_roof.obj", sroof), (rx - 6.0, ry + 4.0, -0.05), yaw=90,
              color=(120, 90, 66), text="Shed roof")

    # pumping station: a little fieldstone hut
    px, py = PUMP
    pump = mk.Mesh("pump")
    proof = _gable_box(pump, 3.4, 5.0, 2.6, 1.3)
    kit.place(kit.mesh("site_pump.obj", pump), (px, py, -0.05), yaw=8,
              color=(250, 245, 238), texture=tex['stone'], text="Pumping Station")
    kit.place(kit.mesh("site_pump_roof.obj", proof), (px, py, -0.05), yaw=8,
              color=(120, 90, 66), text="Pumping Station roof")

    # photovoltaic array + satellite dish
    pvc = PV['c']
    frames, panels = mk.Mesh("pv_frames"), mk.Mesh("pv_panels")
    for r in range(PV['rows']):
        y = pvc[1] + 3.0 - r * 3.0
        tilt = math.radians(28)
        w, d = 8.0, 1.8
        z0, z1 = 0.6, 0.6 + d * math.sin(tilt)
        y0, y1 = y - d * math.cos(tilt) / 2, y + d * math.cos(tilt) / 2
        panels.add_quad((pvc[0] - w / 2, y0, z0), (pvc[0] + w / 2, y0, z0),
                        (pvc[0] + w / 2, y1, z1), (pvc[0] - w / 2, y1, z1),
                        uvs=[(0, 0), (4, 0), (4, 1), (0, 1)])
        for k in np.linspace(-w / 2 + 0.3, w / 2 - 0.3, 4):
            frames.extend(mk.box(size=(0.08, 0.08, z0), center=(pvc[0] + k, y0, z0 / 2)))
            frames.extend(mk.box(size=(0.08, 0.08, z1), center=(pvc[0] + k, y1, z1 / 2)))
    kit.world("site_pv_frames.obj", frames, color=(150, 152, 156), text="PV array frame")
    kit.world("site_pv_panels.obj", panels, color=(255, 255, 255), texture=tex['solar'],
              text="Photovoltaic Array — tilted south")
    dish = mk.revolve([(0.0, 0.0), (0.6, 0.06), (1.1, 0.25), (1.4, 0.45), (1.42, 0.5),
                       (0.0, 0.5)], segments=20)
    dish_m = mk.Mesh("dish")
    dish_m.extend(dish, mk.compose(mk.rot_x(-55), mk.translate(0, 0, 2.4)))
    dish_m.extend(mk.revolve([(0.0, 0.0), (0.12, 0.0), (0.08, 2.3), (0.0, 2.3)], segments=8))
    kit.place(kit.mesh("site_dish.obj", dish_m), (DISH[0], DISH[1], 0.0), yaw=200,
              color=(232, 232, 236), text="Satellite Dish — the Internet link")

    # shower & sauna: a round cedar hut, conical shingle roof, and a hot tub
    sx, sy = SAUNA
    hut = mk.revolve([(0.0, 0.0), (2.6, 0.0), (2.6, 2.6), (0.0, 2.6)], segments=24)
    hut._uv = [(math.atan2(y, x) * 2, z * 0.6) for (x, y, z) in hut._v]
    kit.place(kit.mesh("site_sauna.obj", hut), (sx, sy, -0.05), color=(250, 240, 230),
              texture=tex['planks'], text="Shower & Sauna — cedar")
    cone = mk.revolve([(0.0, 2.55), (3.1, 2.55), (0.0, 4.6)], segments=24)
    cone._uv = [(math.atan2(y, x) * 2, math.hypot(x, y) * 0.8) for (x, y, z) in cone._v]
    kit.place(kit.mesh("site_sauna_roof.obj", cone), (sx, sy, -0.05), color=(250, 240, 230),
              texture=tex['shingle'], text="Sauna roof — cedar shingles")
    tub = mk.revolve([(0.0, 0.0), (1.3, 0.0), (1.3, 0.75), (1.15, 0.75), (1.15, 0.55),
                      (0.0, 0.55)], segments=24)
    kit.place(kit.mesh("site_hot_tub.obj", tub), (sx - 4.4, sy + 2.0, 0.0),
              color=(150, 104, 70), text="Hot tub — perfect for after-dinner discussions")

    # entrance sign between two stone pillars
    ex, ey = ENTRANCE_SIGN
    pillars = mk.Mesh("pillars")
    for dx in (-2.6, 2.6):
        pillars.extend(mk.revolve([(0.0, 0.0), (0.55, 0.0), (0.5, 2.4), (0.6, 2.5),
                                   (0.6, 2.7), (0.0, 2.7)], segments=10),
                       mk.translate(dx, 0, 0))
    pillars._uv = [(x * 1.2 + y, z * 0.8) for (x, y, z) in pillars._v]
    kit.place(kit.mesh("site_entrance_pillars.obj", pillars), (ex, ey, float(L.height(ex, ey))),
              yaw=-90, color=(250, 245, 238), texture=tex['stone'],
              text="Entrance")
    kit.place(pieces_ref['board'], (ex, ey, float(L.height(ex, ey)) + 1.0), yaw=-90,
              s=(4.6, 3.0, 4.6 * 90 / 310), color=(255, 255, 255), texture=tex['sign'],
              text="The Banyan Tree — A Community School for Life", pin=True)

    # bridge where the garden loop crosses the lake's inlet
    (bx2, by2), byaw = BRIDGE
    br = mk.Mesh("bridge")
    br.extend(mk.box(size=(7.0, 4.4, 0.25), center=(0, 0, 0.35)))
    for sy_ in (-2.1, 2.1):
        for k in np.linspace(-3.3, 3.3, 7):
            br.extend(mk.box(size=(0.12, 0.12, 1.0), center=(k, sy_, 0.85)))
        br.extend(mk.tube([(-3.4, sy_, 1.3), (3.4, sy_, 1.3)], 0.06, segments=5))
    br._uv = [(x * 0.5, y * 0.5 + z) for (x, y, z) in br._v]
    kit.place(kit.mesh("site_bridge.obj", br), (bx2, by2, 0.0), yaw=byaw,
              color=(240, 225, 205), texture=tex['planks'],
              text="Bridge — redwood, over the lake's inlet")


def signpost():
    m = mk.Mesh("signpost")
    m.extend(mk.box(size=(0.14, 0.14, 2.3), center=(0, 0, 1.15)))
    for z, ang in ((1.95, 15), (1.55, -25)):
        b = mk.box(size=(1.2, 0.05, 0.28), center=(0.5, 0, 0))
        m.extend(b, mk.compose(mk.rot_z(ang), mk.translate(0, 0.08, z)))
    return m


def lounger():
    m = mk.Mesh("lounger")
    m.extend(mk.box(size=(0.7, 1.4, 0.08), center=(0, -0.2, 0.32)))
    back = mk.box(size=(0.7, 0.7, 0.08), center=(0, 0.35, 0))
    m.extend(back, mk.compose(mk.rot_x(40), mk.translate(0, 0.62, 0.55)))
    for sx in (-0.3, 0.3):
        for sy in (-0.8, 0.5):
            m.extend(mk.box(size=(0.05, 0.05, 0.3), center=(sx, sy, 0.15)))
    return m


def goat_mesh():
    g = mk.Mesh("goat")
    g.extend(fu.blob(0.55, 0.24, 0.24, seg=(10, 6)), mk.translate(0, 0, 0.42))
    g.extend(fu.blob(0.15, 0.11, 0.14, seg=(8, 5)), mk.translate(0.55, 0, 0.78))
    for sx in (-0.35, 0.35):
        for sy in (-0.13, 0.13):
            g.extend(mk.tube([(sx, sy, 0.0), (sx, sy, 0.55)], 0.04, segments=5))
    g.extend(mk.tube([(0.6, -0.05, 1.02), (0.5, -0.08, 1.18)], 0.02, segments=4))
    g.extend(mk.tube([(0.6, 0.05, 1.02), (0.5, 0.08, 1.18)], 0.02, segments=4))
    return g


def pillow_roof(mask, grid, eave_z, rise, L_m=1.8, name="roof"):
    interior = ndi.binary_erosion(mask, iterations=1)
    dist = ndi.distance_transform_edt(interior) * grid.m

    def z_fn(x, y):
        c, r = grid.pixel(x, y)
        d = ndi.map_coordinates(dist, [r, c], order=1, mode='nearest')
        return eave_z + rise * (1 - np.exp(-d / L_m))
    return og.slab_from_mask(mask, grid, z_fn, cell=3,
                             uv_fn=lambda x, y: (x * 0.25, y * 0.25), name=name)


def build_dwellings(kit, tex, L):
    """Five family homes: clusters of round pods with curved plaster walls
    and pillowed roofs -- living sod, plaster, or cedar shingle."""
    roof_tex = dict(sod='sod', plaster='roof', shingle='shingle')
    roof_col = dict(sod=(255, 255, 255), plaster=(255, 248, 236), shingle=(250, 240, 230))
    for k, d in enumerate(L.dwellings, 1):
        pods = d['pods']
        xs = [p[0] for p in pods]
        ys = [p[1] for p in pods]
        pad = 7.0
        x0, x1 = min(xs) - pad, max(xs) + pad
        y0, y1 = min(ys) - pad, max(ys) + pad
        g = og.Grid(m=0.1, origin=(x0, y1))
        H, Wd = int((y1 - y0) / 0.1), int((x1 - x0) / 0.1)
        cols, rows = np.meshgrid(np.arange(Wd), np.arange(H))
        X, Y = g.world(cols, rows)
        foot = np.zeros((H, Wd), bool)
        for (px, py, rx, ry) in pods:
            foot |= ((X - px) / rx) ** 2 + ((Y - py) / ry) ** 2 <= 1
        foot = ndi.binary_closing(foot, iterations=6)
        band = foot & ~ndi.binary_erosion(foot, iterations=4)
        # a front door facing the commons, and a glass door to the garden
        tc = np.array(COMMONS_C) - np.array(d['c'])
        a = math.atan2(tc[1], tc[0])
        door = np.zeros_like(band)
        for aa, wdt in ((a, 1.1), (a + math.pi * 0.85, 1.6)):
            dirv = np.array([math.cos(aa), math.sin(aa)])
            rel = np.stack([X - d['c'][0], Y - d['c'][1]], -1)
            along = rel @ dirv
            perp = np.abs(rel @ np.array([-dirv[1], dirv[0]]))
            door |= (along > 0) & (perp < wdt / 2)
        walls_mask = band & ~door
        top = lambda x, y, k=k: 2.9 + 0.18 * np.sin(1.1 * x + k) * np.cos(0.9 * y)  # noqa: E731
        walls = og.walls_from_mask(walls_mask, g, -0.4, top, uv_scale=1 / 3.0)
        walls.extend(og.slab_from_mask(walls_mask, g, top, cell=2,
                                       uv_fn=lambda x, y: (x / 3, 0.5)))
        roof = pillow_roof(foot, g, 3.12, 1.6 if d['roof'] != 'shingle' else 2.4)
        floor = og.slab_from_mask(foot, g, lambda x, y: np.full(np.shape(x), 0.04), cell=6,
                                  uv_fn=lambda x, y: (x * 0.5, y * 0.5))
        label = (f"Dwelling {k} — a family's own home (co-housing: private homes, "
                 f"shared commons)")
        kit.world(f"home{k}_walls.obj", walls, color=(255, 252, 245), texture=tex['cottage'],
                  text=label)
        kit.world(f"home{k}_floor.obj", floor, color=(230, 220, 205), texture=tex['planks'],
                  text=f"Dwelling {k} — floor")
        kit.world(f"home{k}_roof.obj", roof, color=roof_col[d['roof']],
                  texture=tex[roof_tex[d['roof']]],
                  text=f"Dwelling {k} — {'living sod' if d['roof'] == 'sod' else d['roof']} roof")
        # a stone chimney on the largest pod
        px, py, rx, ry = pods[0]
        ch = mk.revolve([(0.0, 0.0), (0.45, 0.0), (0.38, 5.6), (0.48, 5.8), (0.48, 6.0),
                         (0.0, 6.0)], segments=10)
        ch._uv = [(math.atan2(y, x), z * 0.7) for (x, y, z) in ch._v]
        kit.place(kit.mesh("home_chimney.obj", ch), (px + rx * 0.45, py + ry * 0.3, 0.0),
                  color=(250, 245, 238), texture=tex['stone'], text=f"Dwelling {k} — chimney")


def build_commons(kit, tex, L, pieces):
    """Wedge terraces round a story circle: one raised bed per family."""
    cx, cy = COMMONS_C
    r0, r1 = COMMONS_R
    a0, a1 = COMMONS_ANG
    n = COMMONS_WEDGES
    gap = 4.0
    beds, tops = mk.Mesh("beds"), mk.Mesh("tops")
    span = (a1 - a0) / n
    for k in range(n):
        s0 = math.radians(a0 + k * span + gap / 2)
        s1 = math.radians(a0 + (k + 1) * span - gap / 2)
        arc = np.linspace(s0, s1, 10)
        outer = [(cx + r1 * math.cos(t), cy + r1 * math.sin(t)) for t in arc]
        inner = [(cx + r0 * math.cos(t), cy + r0 * math.sin(t)) for t in arc[::-1]]
        poly = outer + inner
        g = og.Grid(m=0.1, origin=(cx - r1 - 1, cy + r1 + 1))
        shape = (int((2 * r1 + 2) / 0.1), int((2 * r1 + 2) / 0.1))
        mask = poly_mask(g, shape, poly)
        beds.extend(og.walls_from_mask(mask, g, -0.2, 0.5, uv_scale=0.5))
        tops.extend(og.slab_from_mask(ndi.binary_erosion(mask, iterations=2), g,
                                      lambda x, y: np.full(np.shape(x), 0.46), cell=6,
                                      uv_fn=lambda x, y: (x * 0.25, y * 0.25)))
    kit.world("commons_terraces.obj", beds, color=(250, 245, 238), texture=tex['stone'],
              text="The Commons", pin=True)
    kit.world("commons_beds.obj", tops, color=(255, 255, 255), texture=tex['flowers'],
              text="The Commons — a raised garden terrace for each family, round "
                   "a shared green and a story circle")
    ring = mk.revolve([(0.9, 0.0), (1.4, 0.0), (1.4, 0.35), (0.9, 0.35), (0.9, 0.0)], segments=24)
    ring._uv = [(math.atan2(y, x), z + math.hypot(x, y)) for (x, y, z) in ring._v]
    kit.place(kit.mesh("commons_fire_ring.obj", ring), (cx, cy, 0.0), color=(250, 245, 238),
              texture=tex['stone'], text="Story circle — values taught by stories")
    for k in range(6):
        a = k * 60 + 15
        x = cx + 3.4 * math.cos(math.radians(a))
        y = cy + 3.4 * math.sin(math.radians(a))
        kit.place(pieces['log_bench'], (x, y, 0.0), yaw=a + 90, s=(0.8, 1, 1),
                  color=(140, 100, 66), text="Log bench")


def build_garden(kit, tex, L):
    """Raised cedar beds, a pergola walkway from the Main Hall."""
    beds, tops = mk.Mesh("gbeds"), mk.Mesh("gtops")
    for gx in np.arange(-14, 12, 2.6):
        for gy0, gy1 in ((34.5, 47.5), (48.5, 61.5)):
            beds.extend(mk.prism(mk.rect(1.3, gy1 - gy0, gx + 0.7, (gy0 + gy1) / 2), -0.1, 0.4,
                                 uv_world=True, uv_scale=1.0))
            tops.add_quad((gx + 0.12, gy0 + 0.08, 0.41), (gx + 1.28, gy0 + 0.08, 0.41),
                          (gx + 1.28, gy1 - 0.08, 0.41), (gx + 0.12, gy1 - 0.08, 0.41),
                          uvs=[(0, 0), (1, 0), (1, (gy1 - gy0) / 4), (0, (gy1 - gy0) / 4)])
    kit.world("garden_beds.obj", beds, color=(240, 225, 210), texture=tex['planks'],
              text="Garden, Orchard, Husbandry", pin=True)
    kit.world("garden_crops.obj", tops, color=(255, 255, 255), texture=tex['crops'],
              text="Garden — cedar raised beds; each child plans and keeps a plot")
    # pergola along the walkway from the school to the garden
    path = L.paths[1]
    pg = mk.Mesh("pergola")
    for k in range(0, len(path), 2):
        p = path[k]
        t = path[min(k + 1, len(path) - 1)] - path[max(k - 1, 0)]
        t /= np.linalg.norm(t) + 1e-9
        nrm = np.array([-t[1], t[0]])
        for side in (-1, 1):
            q = p + nrm * side * 1.6
            pg.extend(mk.box(size=(0.18, 0.18, 2.7), center=(q[0], q[1], 1.35)))
        a, b = p - nrm * 2.0, p + nrm * 2.0
        pg.extend(mk.tube([(a[0], a[1], 2.75), (b[0], b[1], 2.75)], 0.09, segments=4))
    for side in (-1, 1):
        rail = [(p[0] + side * 1.6 * (-(path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)])[1]
                                      / (np.linalg.norm(path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]) + 1e-9)),
                 p[1] + side * 1.6 * ((path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)])[0]
                                      / (np.linalg.norm(path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]) + 1e-9)),
                 2.62) for i, p in enumerate(path)]
        pg.extend(mk.tube(rail, 0.08, segments=4))
    kit.world("garden_pergola.obj", pg, color=(150, 96, 62),
              text="Pergola — the walkway from the Main Hall to the garden")


def plant_orchard(kit, tex, L, built):
    spec = built['fruit']
    rng = np.random.default_rng(31)
    for i, gx in enumerate(np.arange(15, 36, 5.0)):
        for j, gy in enumerate(np.arange(40, 66, 5.0)):
            x, y = gx + rng.normal(0, 0.3), gy + rng.normal(0, 0.3)
            if not poly_contains(scale_poly(L.loop, 0.84), x, y):
                continue
            plant(kit, tex, spec, x, y, 0.0, float(rng.uniform(0, 360)),
                  4.2 / spec['height'] * rng.uniform(0.85, 1.1), "Orchard — avocado")


def fig_tree():
    """A Moreton Bay fig: a buttressed trunk, long horizontal limbs, aerial
    roots dropping from them to become new trunks -- the banyan habit the
    school is named for ('the branches send out shoots that root to form
    secondary trunks')."""
    rng = np.random.default_rng(77)
    trunk, canopy = mk.Mesh("fig_trunk"), mk.Mesh("fig_canopy")
    # buttressed main trunk
    secs = []
    for z in np.linspace(0, 4.5, 10):
        ring = []
        for j in range(18):
            th = 2 * math.pi * j / 18
            r = 1.1 + 0.9 * max(0.0, math.cos(4 * th)) ** 2 * math.exp(-z / 1.0) + 0.3 * math.exp(-z)
            ring.append((r * math.cos(th), r * math.sin(th), z))
        secs.append(ring)
    trunk.extend(mk.loft(secs, closed=True, cap_end=True, uv_u_repeat=3))
    limbs = []
    for k in range(7):
        a = k * 2 * math.pi / 7 + rng.uniform(-0.25, 0.25)
        L = rng.uniform(8, 12)
        pts = []
        for t in np.linspace(0, 1, 8):
            r = t * L
            z = 4.2 + 2.2 * math.sin(t * math.pi * 0.7) - t * 0.8
            pts.append((r * math.cos(a), r * math.sin(a), z))
        trunk.extend(mk.tube(pts, np.linspace(0.65, 0.18, 8), segments=8))
        limbs.append(pts)
        # aerial roots dropping to the ground from along the limb
        for t in (0.45, 0.7, 0.9):
            i = int(t * 7)
            x, y, z = pts[i]
            r = 0.06 if t > 0.8 else 0.16
            trunk.extend(mk.tube([(x, y, z), (x + rng.normal(0, 0.2), y + rng.normal(0, 0.2), 0.0)],
                                 r, segments=6))
    for pts in limbs:
        for t in (0.35, 0.6, 0.85, 1.0):
            x, y, z = pts[int(t * 7)]
            for _ in range(2):
                canopy.extend(fu.blob(rng.uniform(2.6, 3.6), rng.uniform(2.6, 3.6),
                                      rng.uniform(1.2, 1.7), seg=(9, 6)),
                              mk.translate(x + rng.normal(0, 1.2), y + rng.normal(0, 1.2),
                                           z + rng.uniform(0.6, 1.6)))
    canopy.extend(fu.blob(5.5, 5.5, 2.5, seg=(12, 7)), mk.translate(0, 0, 6.2))
    return trunk, canopy


def treehouse():
    """Platform in the fig's limbs, a little cabin, a rope ladder."""
    deck, cabin, roof = mk.Mesh("th_deck"), mk.Mesh("th_cabin"), mk.Mesh("th_roof")
    deck.extend(mk.revolve([(0.0, 0.0), (2.6, 0.0), (2.6, 0.2), (0.0, 0.2)], segments=8))
    for k in range(16):
        a = 2 * math.pi * k / 16
        deck.extend(mk.box(size=(0.08, 0.08, 0.9),
                           center=(2.45 * math.cos(a), 2.45 * math.sin(a), 0.65)))
    deck.extend(mk.tube([(2.45 * math.cos(a), 2.45 * math.sin(a), 1.1)
                         for a in np.linspace(0, 2 * math.pi, 17)], 0.05, segments=4))
    for k, z in enumerate(np.linspace(-5.0, 0.0, 12)):
        deck.extend(mk.box(size=(0.6, 0.06, 0.05), center=(2.9, 0.0, z)))
    for sy in (-0.3, 0.3):
        deck.extend(mk.tube([(2.9, sy, -5.0), (2.9, sy, 0.1)], 0.025, segments=4))
    cabin.extend(mk.box(size=(2.4, 2.0, 1.8), center=(-0.4, 0.0, 1.1)))
    rf = _gable_box(mk.Mesh("tmp"), 2.4, 2.0, 0.0, 1.1, cx=-0.4)
    roof.extend(rf, mk.translate(0, 0, 2.0))
    return deck, cabin, roof


def build_playground(kit, tex, L):
    fx, fy = PLAYGROUND['fig']
    trunk, canopy = fig_tree()
    kit.place(kit.mesh("fig_trunk.obj", trunk), (fx, fy, -0.1), color=(250, 248, 244),
              texture=tex['fig_bark'],
              text="The Banyan", pin=True)
    kit.place(kit.mesh("fig_canopy.obj", canopy), (fx, fy, -0.1), color=(225, 240, 220),
              texture=tex['leaves'],
              text="The Banyan — a Moreton Bay fig, its aerial roots becoming new "
                   "trunks: 'a fitting symbol at many levels'")
    deck, cabin, roof = treehouse()
    hx, hy, hz = fx + 3.2, fy - 1.0, 4.6
    kit.place(kit.mesh("treehouse_deck.obj", deck), (hx, hy, hz), yaw=-30, color=(232, 214, 190),
              texture=tex['planks'], text="Kids-only tree house — rope ladder up")
    kit.place(kit.mesh("treehouse_cabin.obj", cabin), (hx, hy, hz), yaw=-30, color=(214, 120, 70),
              text="Tree house")
    kit.place(kit.mesh("treehouse_roof.obj", roof), (hx, hy, hz), yaw=-30, color=(70, 110, 90),
              text="Tree house roof")

    # geodesic climbing dome: a nod to Buckminster Fuller ("Dare to be naive")
    dx, dy = PLAYGROUND['dome']
    kit.place(kit.mesh("play_dome.obj", geodesic_dome(3.0)), (dx, dy, 0.0),
              color=(220, 70, 50), text="Geodesic climbing dome — for Buckminster "
                                        "Fuller: 'Dare to be naive'")
    sw = mk.Mesh("swings")
    for x in (-2.6, 2.6):
        for y in (-1.0, 1.0):
            sw.extend(mk.tube([(x, y, 0.0), (x * 0.9, 0.0, 2.6)], 0.06, segments=5))
    sw.extend(mk.tube([(-2.6, 0, 2.6), (2.6, 0, 2.6)], 0.07, segments=5))
    for x in (-1.3, 0.0, 1.3):
        for y in (-0.2, 0.2):
            sw.extend(mk.tube([(x, y, 2.55), (x, y, 0.55)], 0.012, segments=3))
        sw.extend(mk.box(size=(0.55, 0.2, 0.04), center=(x, 0, 0.53)))
    sx, sy = PLAYGROUND['swings']
    kit.place(kit.mesh("play_swings.obj", sw), (sx, sy, 0.0), yaw=25, color=(60, 110, 170),
              text="Swings")
    sl = mk.Mesh("slide")
    sl.extend(mk.box(size=(1.2, 1.2, 0.1), center=(0, 0, 1.8)))
    for x in (-0.55, 0.55):
        for y in (-0.55, 0.55):
            sl.extend(mk.box(size=(0.1, 0.1, 1.8), center=(x, y, 0.9)))
    for k in range(6):
        sl.extend(mk.box(size=(0.7, 0.08, 0.06), center=(0, -0.6 - k * 0.12, 0.3 * k)))
    ch = []
    for t in np.linspace(0, 1, 12):
        ch.append((0.0, 0.6 + t * 3.4, 1.8 * (1 - t) ** 1.4 + 0.15))
    sl.extend(mk.tube(ch, 0.35, segments=8))
    kit.place(kit.mesh("play_slide.obj", sl), (*PLAYGROUND['slide'], 0.0), yaw=-60,
              color=(240, 190, 50), text="Slide")
    sb = mk.prism(mk.rect(4.0, 4.0), -0.05, 0.3)
    kit.place(kit.mesh("play_sandbox.obj", sb), (*PLAYGROUND['sandbox'], 0.0), yaw=15,
              color=(150, 110, 70), text="Sandbox frame")
    sand = mk.prism(mk.rect(3.7, 3.7), -0.05, 0.22)
    kit.place(kit.mesh("play_sand.obj", sand), (*PLAYGROUND['sandbox'], 0.0), yaw=15,
              color=(226, 206, 160), text="Sand")


def geodesic_dome(r=3.0, freq=2):
    """Struts of a frequency-2 icosahedral geodesic hemisphere."""
    t = (1 + 5 ** 0.5) / 2
    v = np.array([(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t),
                  (0, -1, -t), (0, 1, -t), (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)], float)
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    f = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4),
         (11, 10, 2), (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8),
         (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    # orient so a vertex is at the top (z)
    edges = set()
    pts = {}

    def key(p):
        return tuple(np.round(p, 5))
    for a, b, c in f:
        A, B, C = v[a], v[b], v[c]
        grid = {}
        for i in range(freq + 1):
            for j in range(freq + 1 - i):
                p = A + (B - A) * i / freq + (C - A) * j / freq
                p /= np.linalg.norm(p)
                grid[(i, j)] = key(p)
        for (i, j), p in grid.items():
            for di, dj in ((1, 0), (0, 1), (-1, 1)):
                q = grid.get((i + di, j + dj))
                if q:
                    edges.add(tuple(sorted((p, q))))
    m = mk.Mesh("dome")
    R = mk.rot_x(-math.degrees(math.atan2(1, t)))[:3, :3]
    for p, q in edges:
        P, Q = R @ np.array(p), R @ np.array(q)
        if P[2] < -0.05 or Q[2] < -0.05:
            continue
        m.extend(mk.tube([tuple(P * r), tuple(Q * r)], 0.045, segments=5,
                         cap_start=False, cap_end=False))
    return m
