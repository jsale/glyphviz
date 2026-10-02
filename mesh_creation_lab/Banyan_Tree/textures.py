"""
textures — the Banyan Tree's materials, painted procedurally.

Jeff's drawings are black and white, so every colour here is an
interpretation, chosen for the place the school was meant to be: the oak and
chaparral hills north-east of San Diego, built (per the elevation) of stone,
mortar, reinforced concrete, redwood and cedar, in the manner of James
Hubbell -- lime plaster, fieldstone, and coloured tile set into the work.

GlyphViz lights a scene with one headlight, so these textures carry their own
light: wall bases are darker than wall tops, floors darken toward the walls,
and the site map has the terrain's hillshade baked in. That baked shading is
most of what makes the result read as a place rather than as coloured plastic.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage as ndi

import texkit as tk


def _rng(seed):
    return np.random.default_rng(seed)


def voronoi_cells(h, w, n, seed=0, wrap=True):
    """Label image of jittered Voronoi cells and distance-to-edge (pixels),
    tiling seamlessly when `wrap` -- for stone, flagstone and mosaic."""
    from scipy.spatial import cKDTree
    rng = _rng(seed)
    pts = rng.random((n, 2)) * (h, w)
    if wrap:
        offs = [(dy, dx) for dy in (-h, 0, h) for dx in (-w, 0, w)]
        allp = np.vstack([pts + o for o in offs])
        ids = np.tile(np.arange(n), 9)
    else:
        allp, ids = pts, np.arange(n)
    yy, xx = np.mgrid[0:h, 0:w]
    q = np.stack([yy.ravel(), xx.ravel()], 1).astype(float)
    d, i = cKDTree(allp).query(q, k=2)
    lab = ids[i[:, 0]].reshape(h, w)
    edge = (d[:, 1] - d[:, 0]).reshape(h, w)
    return lab, edge


# --------------------------------------------------------------------------
# masonry and plaster
# --------------------------------------------------------------------------

def fieldstone(h=512, w=512, seed=0, stones=90):
    """Rounded fieldstones bedded in mortar -- the elevation's 'Stone, Mortar'."""
    rng = _rng(seed)
    lab, edge = voronoi_cells(h, w, stones, seed)
    hue = rng.random(stones)
    base = np.stack([0.50 + 0.18 * hue, 0.46 + 0.12 * hue, 0.40 + 0.06 * hue], 1)
    shade = rng.uniform(0.70, 1.15, stones)
    img = base[lab] * shade[lab][..., None]
    # dome each stone: bright centre, dark toward its joint
    dome = np.clip(edge / 9.0, 0, 1) ** 0.5
    img *= (0.55 + 0.5 * dome)[..., None]
    img *= (0.85 + 0.3 * tk.fbm(h, w, period=16, octaves=4, seed=seed + 1))[..., None]
    mortar = np.clip(1.0 - edge / 2.2, 0, 1)
    img = tk.overlay(img, np.array([0.70, 0.67, 0.60]) *
                     (0.8 + 0.3 * tk.fbm(h, w, 32, 3, seed=seed + 2))[..., None], mortar)
    return np.clip(img, 0, 1)


def _arch_window(img, cx, y0, y1, half_w, frame, glass, sill):
    """Paint one round-topped window into an (H, W, 3) image, rows y-down."""
    H, W, _ = img.shape
    yy, xx = np.mgrid[0:H, 0:W]
    dx = np.minimum(np.abs(xx - cx), W - np.abs(xx - cx))   # wraps
    r = half_w
    top = y0 + r
    in_rect = (dx <= r) & (yy >= top) & (yy <= y1)
    in_arch = ((dx ** 2 + (yy - top) ** 2) <= r * r) & (yy < top)
    win = in_rect | in_arch
    rf = r + max(3, r * 0.16)
    in_rect_f = (dx <= rf) & (yy >= top) & (yy <= y1 + 4)
    in_arch_f = ((dx ** 2 + (yy - top) ** 2) <= rf * rf) & (yy < top)
    fr = (in_rect_f | in_arch_f) & ~win
    img[fr] = frame
    g = np.array(glass)
    # sky reflection gradient in the glass
    t = np.clip((yy - y0) / max(y1 - y0, 1), 0, 1)
    refl = g * (1.25 - 0.55 * t)[..., None]
    img[win] = refl[win]
    # mullion cross
    mul = win & ((np.abs(dx) < 2) | (np.abs(yy - (top + y1) / 2) < 2))
    img[mul] = frame
    sl = (dx <= rf + 4) & (yy > y1 + 2) & (yy < y1 + 9)
    img[sl] = sill
    return img


def oval_window(img, cx, cy, rx, ry, frame, glass):
    H, W, _ = img.shape
    yy, xx = np.mgrid[0:H, 0:W]
    dx = np.minimum(np.abs(xx - cx), W - np.abs(xx - cx))
    e = (dx / rx) ** 2 + ((yy - cy) / ry) ** 2
    ef = (dx / (rx + 6)) ** 2 + ((yy - cy) / (ry + 6)) ** 2
    img[(ef <= 1) & (e > 1)] = frame
    win = e <= 1
    t = np.clip((yy - (cy - ry)) / (2 * ry), 0, 1)
    img[win] = (np.array(glass) * (1.3 - 0.6 * t)[..., None])[win]
    # leaded-light hatch, as the elevation draws its two oval windows
    hatch = win & ((((xx + yy) % 22) < 2) | (((xx - yy) % 22) < 2))
    img[hatch] = frame
    return img


def school_wall(seed=4):
    """One tile = 4 m along the wall x 8 m up it (512 x 1024).

    Stone base course, lime plaster, a round-topped window at sill height,
    and -- above 4.4 m, so only the Main Hall's tall walls ever show it -- an
    oval clerestory window with leaded lights like the two in the elevation.
    A band of coloured tile runs at 3.1 m, the height of the ordinary walls'
    tops, so it reads as a cornice there and a string course on the hall."""
    H, W = 1024, 512
    px_m = H / 8.0                               # 128 px per metre
    plaster = tk.tint(tk.fbm(H, W, period=6, octaves=5, seed=seed),
                      (0.86, 0.80, 0.68), (0.97, 0.93, 0.84))
    img = plaster.copy()
    # weathering streaks and soft dirt toward the ground
    streak = tk.fbm(H, W * 4, period=20, octaves=4, seed=seed + 3)[:, ::4]
    img *= (0.94 + 0.08 * streak)[..., None]

    def row(m):            # metres above floor -> image row (v up = row down)
        return int(H - m * px_m)

    stone = fieldstone(256, 512, seed=seed + 9, stones=26)
    base_top = row(0.55)
    img[base_top:, :] = np.vstack([stone] * 2)[: H - base_top, :W]
    img[base_top - 3:base_top + 2, :] *= 0.75

    frame = np.array([0.42, 0.27, 0.16])         # redwood
    glass = np.array([0.30, 0.42, 0.50])
    sill = np.array([0.60, 0.56, 0.50])
    _arch_window(img, W // 2, row(2.55), row(0.95), int(0.55 * px_m),
                 frame, glass, sill)
    # tile string course
    rng = _rng(seed)
    band = slice(row(3.25), row(3.05))
    cols = np.array([[0.13, 0.42, 0.55], [0.80, 0.55, 0.20], [0.20, 0.50, 0.32],
                     [0.62, 0.20, 0.18], [0.90, 0.82, 0.55]])
    n = W // 16
    pick = cols[rng.integers(0, len(cols), n)]
    strip = np.repeat(pick, 16, axis=0)[None, :, :]
    img[band] = strip
    img[band][:, ::16] *= 0.5
    oval_window(img, W // 2, row(5.1), int(0.62 * px_m), int(0.72 * px_m),
                frame, glass)
    # baked light: darker at the base, a little lighter at the top
    v = np.linspace(1.0, 0.0, H)[:, None]
    img *= (0.80 + 0.22 * v)[..., None]
    return np.clip(img, 0, 1)


def cottage_wall(seed=8, tint=(0.95, 0.88, 0.74)):
    """One tile = 3 m x 3 m (384 x 384): plaster, stone plinth, one window."""
    H = W = 384
    px_m = H / 3.0
    base = np.array(tint)
    img = tk.tint(tk.fbm(H, W, period=5, octaves=5, seed=seed),
                  base * 0.88, np.minimum(base * 1.04, 1))
    plinth = int(H - 0.4 * px_m)
    img[plinth:] = fieldstone(H - plinth, W, seed=seed + 1, stones=10) \
        if False else fieldstone(64, 384, seed=seed + 1, stones=12)[: H - plinth]
    _arch_window(img, W // 2, int(H - 2.3 * px_m), int(H - 0.9 * px_m),
                 int(0.42 * px_m), np.array([0.36, 0.48, 0.30]),
                 np.array([0.32, 0.42, 0.48]), np.array([0.62, 0.58, 0.52]))
    v = np.linspace(1.0, 0.0, H)[:, None]
    img *= (0.82 + 0.2 * v)[..., None]
    return np.clip(img, 0, 1)


def roof_plaster(seed=12):
    """Sculpted lime-plaster roof, 4 m per repeat: soft trowel variation and
    rain streaks. Deliberately plain -- the roof is drawn translucent over
    the rooms, and any pattern on it is laid over every room below."""
    H = W = 512
    img = tk.tint(tk.fbm(H, W, period=5, octaves=5, seed=seed),
                  (0.84, 0.78, 0.66), (0.96, 0.92, 0.82))
    streak = tk.fbm(H, W * 4, period=24, octaves=4, seed=seed + 7)[:, ::4]
    img *= (0.90 + 0.12 * streak)[..., None]
    return np.clip(img, 0, 1)


def sod_roof(seed=21):
    """A living roof: meadow grass with wildflowers (4 m repeat)."""
    H = W = 256
    g = tk.fbm(H, W, period=12, octaves=5, seed=seed)
    img = tk.tint(g, (0.30, 0.38, 0.14), (0.58, 0.62, 0.26))
    rng = _rng(seed)
    flowers = rng.random((H, W)) > 0.993
    fl_col = np.array([[0.95, 0.80, 0.25], [0.85, 0.45, 0.70], [0.95, 0.95, 0.90]])
    pick = fl_col[rng.integers(0, 3, (H, W))]
    img = np.where(flowers[..., None], pick, img)
    return img


def wood_planks(h=256, w=256, seed=0, base=(0.55, 0.36, 0.20), rows=8):
    """Redwood decking / floorboards; v runs along the boards."""
    rng = _rng(seed)
    grain = tk.fbm(h * 6, w, period=8, octaves=4, seed=seed)[::6, :]
    yy, xx = np.mgrid[0:h, 0:w]
    bw = w / rows
    board = (xx / bw).astype(int)
    offs = rng.random(rows) * h
    joint = ((yy + offs[board]) % h) < 2
    shade = rng.uniform(0.82, 1.12, rows)[board]
    img = np.array(base) * (0.8 + 0.35 * grain)[..., None] * shade[..., None]
    img[(xx % bw) < 1.5] *= 0.55
    img[joint] *= 0.6
    return np.clip(img, 0, 1)


def cedar_shingle(seed=31):
    H = W = 256
    rng = _rng(seed)
    img = np.zeros((H, W, 3))
    rows = 10
    rh = H / rows
    for r in range(rows):
        y0, y1 = int(r * rh), int((r + 1) * rh)
        x = 0
        off = rng.integers(0, 20)
        while x < W + 30:
            sw = int(rng.integers(14, 30))
            c = np.array([0.55, 0.36, 0.22]) * rng.uniform(0.75, 1.15)
            xs = np.arange(x - off, x - off + sw) % W
            img[y0:y1, xs] = c
            img[y0:y1, xs[:1]] *= 0.5
            x += sw
        img[y1 - 3:y1] *= 0.55
    img *= (0.85 + 0.25 * tk.fbm(H, W, 8, 4, seed=seed))[..., None]
    return np.clip(img, 0, 1)


def water(seed=5, deep=(0.10, 0.28, 0.36), shallow=(0.30, 0.52, 0.55)):
    H = W = 512
    n = tk.fbm(H, W * 3, period=10, octaves=5, seed=seed)[:, ::3]
    img = tk.tint(n, deep, shallow)
    glint = tk.fbm(H, W, period=24, octaves=3, seed=seed + 2)
    img = tk.overlay(img, np.array([0.85, 0.92, 0.95]),
                     np.clip((glint - 0.72) * 4, 0, 1) * 0.5)
    return img


def pool_water(seed=6):
    """Pool: a light tiled bottom seen through clear water, with caustics."""
    H = W = 256
    yy, xx = np.mgrid[0:H, 0:W]
    img = np.full((H, W, 3), (0.42, 0.74, 0.82))
    img[((xx % 32) < 1) | ((yy % 32) < 1)] *= 0.85
    c = tk.fbm(H, W, period=8, octaves=3, seed=seed)
    caust = np.clip(1 - np.abs(c - 0.5) * 9, 0, 1)
    img = tk.overlay(img, np.array([0.9, 0.98, 1.0]), caust * 0.55)
    return img


def books(seed=3):
    """Bookcase front: shelves of coloured spines. One tile = one bay,
    1 m wide x 2 m tall (256 x 512), five shelves."""
    H, W = 512, 256
    rng = _rng(seed)
    img = np.full((H, W, 3), (0.36, 0.24, 0.14))
    shelves = 5
    sh = H / shelves
    spine = np.array([[0.55, 0.12, 0.10], [0.12, 0.25, 0.45], [0.18, 0.40, 0.22],
                      [0.80, 0.68, 0.40], [0.40, 0.18, 0.35], [0.85, 0.85, 0.80],
                      [0.15, 0.15, 0.18], [0.65, 0.35, 0.12]])
    for s in range(shelves):
        y1 = int((s + 1) * sh) - 8
        x = 6
        while x < W - 8:
            bw = int(rng.integers(6, 16))
            bh = int(sh * rng.uniform(0.62, 0.86))
            if rng.random() < 0.06:          # a gap, a leaning book
                x += bw
                continue
            c = spine[rng.integers(0, len(spine))] * rng.uniform(0.75, 1.1)
            img[y1 - bh:y1, x:x + bw] = c
            img[y1 - bh:y1, x:x + 1] *= 0.6
            band = y1 - int(bh * 0.75)
            img[band:band + 2, x:x + bw] = (0.85, 0.75, 0.40)
            x += bw
        img[y1:y1 + 8, :] = (0.30, 0.20, 0.12)
    img[:, :6] = img[:, -6:] = (0.30, 0.20, 0.12)
    return img


def solar(seed=0):
    """PV module: blue-black cells on a white backsheet grid, 2x6 per tile."""
    H, W = 512, 256
    yy, xx = np.mgrid[0:H, 0:W]
    img = np.full((H, W, 3), (0.08, 0.12, 0.25))
    img *= (0.85 + 0.3 * tk.fbm(H, W, period=6, octaves=3, seed=seed))[..., None]
    cell = 42
    grid = ((xx % cell) < 2) | ((yy % cell) < 2)
    img[grid] = (0.78, 0.80, 0.84)
    busbar = ((xx % cell) - cell / 2).__abs__() < 0.8
    img[busbar & ~grid] *= 1.6
    sheen = np.linspace(0.85, 1.25, W)[None, :]
    img *= sheen[..., None]
    return np.clip(img, 0, 1)


def cubbies(seed=2):
    """A wall of children's cubbies: coloured bins in a birch frame."""
    H, W = 256, 512
    rng = _rng(seed)
    img = np.full((H, W, 3), (0.80, 0.68, 0.48))
    cols, rows = 8, 3
    pal = np.array([[0.85, 0.30, 0.25], [0.95, 0.75, 0.25], [0.30, 0.60, 0.85],
                    [0.35, 0.70, 0.40], [0.65, 0.40, 0.75], [0.95, 0.55, 0.30]])
    cw, ch = W / cols, H / rows
    for r in range(rows):
        for c in range(cols):
            x0, y0 = int(c * cw + 6), int(r * ch + 6)
            x1, y1 = int((c + 1) * cw - 6), int((r + 1) * ch - 6)
            img[y0:y1, x0:x1] = (0.18, 0.13, 0.09)
            bx = pal[rng.integers(0, len(pal))]
            img[int(y0 + (y1 - y0) * 0.45):y1, x0 + 3:x1 - 3] = bx
    return img


def fig_bark(seed=17):
    """Moreton Bay fig: smooth grey bark, not the fissured oak kind."""
    H = W = 256
    n = tk.fbm(H, W * 3, period=6, octaves=5, seed=seed)[:, ::3]
    img = tk.tint(n, (0.40, 0.38, 0.34), (0.62, 0.60, 0.55))
    return img


# --------------------------------------------------------------------------
# the school's floors, painted room by room from the traced plan
# --------------------------------------------------------------------------

def _tiles(h, w, size, grout, base, var, seed):
    rng = _rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    ci, cj = (yy // size), (xx // size)
    shade = rng.uniform(1 - var, 1 + var, (ci.max() + 1, cj.max() + 1))
    img = np.array(base) * shade[ci, cj][..., None]
    g = ((yy % size) < grout) | ((xx % size) < grout)
    img[g] = np.array(base) * 0.55 + 0.25
    return img


def _planks(h, w, width, base, seed):
    rng = _rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    row = yy // width
    offs = rng.integers(0, 400, row.max() + 1)
    length = 90
    board = (xx + offs[row]) // length
    shade = rng.uniform(0.82, 1.12, (row.max() + 1, board.max() + 2))
    grain = tk.fbm(h, w * 4, period=16, octaves=4, seed=seed)[:, ::4]
    img = np.array(base) * shade[row, board][..., None] * (0.85 + 0.3 * grain)[..., None]
    img[(yy % width) < 1] *= 0.55
    img[((xx + offs[row]) % length) < 1] *= 0.6
    return img


def _checker(h, w, size, a, b):
    yy, xx = np.mgrid[0:h, 0:w]
    m = ((yy // size + xx // size) % 2).astype(bool)
    img = np.where(m[..., None], np.array(a), np.array(b)).astype(float)
    return img


def _flagstone(h, w, seed):
    lab, edge = voronoi_cells(h, w, max(40, h * w // 700), seed, wrap=False)
    rng = _rng(seed)
    n = lab.max() + 1
    t = rng.uniform(0, 1, n)
    base = np.stack([0.58 + 0.12 * t, 0.55 + 0.10 * t, 0.49 + 0.07 * t], 1)
    base *= rng.uniform(0.85, 1.08, n)[:, None]
    img = base[lab] * (0.85 + 0.2 * np.clip(edge / 5, 0, 1))[..., None]
    joint = edge < 1.6
    img[joint] = (0.40, 0.44, 0.30)                   # moss in the joints
    return img


def _mosaic_tree(h, w, seed):
    """Small tesserae in warm stone, with a stylised banyan inlaid: a trunk,
    branching limbs, and aerial roots dropping back to the ground -- the
    school's name, set in the floor where everyone walks in."""
    lab, edge = voronoi_cells(h, w, h * w // 60, seed, wrap=False)
    rng = _rng(seed)
    n = lab.max() + 1
    sand = np.stack([rng.uniform(0.78, 0.90, n), rng.uniform(0.70, 0.80, n),
                     rng.uniform(0.55, 0.64, n)], 1)
    img = sand[lab]
    motif = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(motif)
    cx, base_y = w * 0.5, h * 0.88
    S = min(w, h)

    def limb(x, y, ang, L, wdt, depth):
        x2 = x + math.cos(ang) * L
        y2 = y - math.sin(ang) * L
        d.line([(x, y), (x2, y2)], fill=255, width=max(int(wdt), 1))
        if depth == 0:
            d.ellipse([x2 - S * .035, y2 - S * .035, x2 + S * .035, y2 + S * .035], fill=128)
            return
        if depth <= 2 and rng.random() < 0.8:          # an aerial root
            d.line([(x2, y2), (x2 + rng.normal(0, 2), base_y)], fill=200, width=1)
        for da in (-0.5, 0.45):
            limb(x2, y2, ang + da + rng.normal(0, 0.12), L * 0.72, wdt * 0.68, depth - 1)

    limb(cx, base_y, math.pi / 2, S * 0.28, S * 0.06, 5)
    d.ellipse([cx - S * 0.46, h * 0.05, cx + S * 0.46, h * 0.95], outline=90, width=3)
    m = np.asarray(motif.filter(ImageFilter.MaxFilter(3))) / 255.0
    # quantise the motif onto whole tesserae, the way a mosaic really is
    per = ndi.mean(m, labels=lab, index=np.arange(n))
    mm = per[lab]
    trunk = np.array([0.36, 0.24, 0.14])
    leaf = np.array([0.18, 0.46, 0.30])
    ring = np.array([0.12, 0.38, 0.55])
    img = np.where((mm > 0.62)[..., None], trunk, img)
    img = np.where(((mm > 0.40) & (mm <= 0.62))[..., None], leaf, img)
    img = np.where(((mm > 0.25) & (mm <= 0.40))[..., None], ring, img)
    img *= (0.80 + 0.2 * np.clip(edge / 2.5, 0, 1))[..., None]
    return img


FLOOR_STYLE = {
    'main_hall':  ('terracotta', None),
    'indoor_rec': ('maple', None),
    'lab':        ('checker', None),
    'lobby':      ('mosaic', None),
    'courtyard':  ('flagstone', None),
    'admin':      ('carpet', (0.35, 0.42, 0.50)),
    'library':    ('oak', None),
    'rest_west':  ('smalltile', None),
    'rest_east':  ('smalltile', None),
    'underwater': ('bluetile', None),
    'storage':    ('concrete', None),
    'gallery':    ('terracotta', None),
}


def floor_plan_texture(plan, scale=2, seed=40):
    """Paint the whole school floor as one image, aligned to the plan.

    One floor mesh, one texture: each room's material is painted inside that
    room's traced region, and the floor darkens toward the walls (baked
    ambient occlusion), so the single headlight still reads depth."""
    H, W = plan.shape
    h, w = H * scale, W * scale
    up = lambda a: np.kron(a, np.ones((scale, scale), a.dtype))   # noqa: E731
    rooms = up(plan.rooms)
    out = np.full((h, w, 3), 0.80)
    painters = {
        'terracotta': lambda: _tiles(h, w, 18, 2, (0.70, 0.40, 0.26), 0.10, seed),
        'maple': lambda: _planks(h, w, 9, (0.84, 0.68, 0.46), seed + 1),
        'oak': lambda: _planks(h, w, 10, (0.52, 0.34, 0.20), seed + 2),
        'checker': lambda: _checker(h, w, 18, (0.86, 0.85, 0.80), (0.20, 0.22, 0.25)),
        'mosaic': None,
        'carpet': None,
        'smalltile': lambda: _tiles(h, w, 8, 1, (0.88, 0.88, 0.84), 0.05, seed + 4),
        'bluetile': lambda: _tiles(h, w, 10, 1, (0.30, 0.55, 0.68), 0.12, seed + 5),
        'concrete': lambda: tk.tint(tk.fbm(h, w, 24, 5, seed=seed + 6),
                                    (0.52, 0.52, 0.50), (0.66, 0.65, 0.62)),
    }
    cache = {}
    for k, name in enumerate(plan.room_names, 1):
        sel = rooms == k
        if not sel.any():
            continue
        style, arg = FLOOR_STYLE.get(name, ('concrete', None))
        if style in ('mosaic', 'flagstone'):
            # painted on the room's own bounding box: these patterns are
            # costly and the motif is composed for that room's shape
            rr, cc = np.nonzero(sel)
            r0, r1, c0, c1 = rr.min(), rr.max() + 1, cc.min(), cc.max() + 1
            maker = _mosaic_tree if style == 'mosaic' else _flagstone
            patch = maker(r1 - r0, c1 - c0, seed + 7)
            box = out[r0:r1, c0:c1]
            box[sel[r0:r1, c0:c1]] = patch[sel[r0:r1, c0:c1]]
            continue
        if style == 'carpet':
            img = tk.tint(tk.fbm(h, w, 64, 4, seed=seed + 8),
                          np.array(arg) * 0.85, np.array(arg) * 1.1)
        else:
            if style not in cache:
                cache[style] = painters[style]()
            img = cache[style]
        out[sel] = img[sel]

    # baked AO: darken within ~0.6 m of any wall
    d = ndi.distance_transform_edt(~up(plan.walls)) / scale * 0.06
    ao = 0.70 + 0.30 * np.clip(d / 0.6, 0, 1) ** 0.6
    out *= ao[..., None]
    return np.clip(out, 0, 1)


def load_drawing(path, pad=24, ink=(0.12, 0.10, 0.09), paper=(0.96, 0.93, 0.86)):
    """One of Jeff's drawings on warm paper, with a margin -- for the easels."""
    g = np.asarray(Image.open(path).convert('L')).astype(float) / 255.0
    g = np.pad(g, pad, constant_values=1.0)
    img = np.array(ink) + (np.array(paper) - np.array(ink)) * g[..., None]
    return img
