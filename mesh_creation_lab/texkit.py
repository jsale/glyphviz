"""
texkit — procedural textures for GlyphViz example scenes.

Companion to meshkit.py: meshkit makes the shape and the UVs, texkit
makes the image those UVs sample. Everything is numpy + Pillow, and every
function returns an (H, W, 3) uint8 array so they can be layered before being
written into a scene's media/ folder.

Two conventions that matter for scenes built this way:

* **Tiling.** Anything meant to repeat (brick, plating, asphalt) must be
  seamless, because meshkit's `uv_world=True` mapping deliberately runs UVs
  past 1.0 so a texture keeps a constant real-world size. The noise here wraps
  by construction — it is generated on a torus — rather than being blurred at
  the edges afterwards.

* **Baked light.** GlyphViz lights a scene with one eye-space headlight, so a
  texture carrying its own soft shading reads as material where a flat one
  reads as plastic. `ao_gradient` and the dirt layers exist for that.

Textures are written at modest sizes (256-1024) on purpose: an example scene
should stay small enough to ship in a zip, and these are read at a distance.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image

# --------------------------------------------------------------------------
# noise
# --------------------------------------------------------------------------


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def value_noise(h: int, w: int, period: int, seed: int = 0) -> np.ndarray:
    """Seamlessly tiling value noise in 0..1.

    Built by sampling a `period`x`period` lattice that wraps with np.roll and
    interpolating smoothly, so the left edge meets the right by construction.
    """
    g = _rng(seed).random((period, period))
    ys = np.linspace(0, period, h, endpoint=False)
    xs = np.linspace(0, period, w, endpoint=False)
    y0, x0 = np.floor(ys).astype(int) % period, np.floor(xs).astype(int) % period
    fy, fx = ys - np.floor(ys), xs - np.floor(xs)
    sy = (fy * fy * (3 - 2 * fy))[:, None]
    sx = (fx * fx * (3 - 2 * fx))[None, :]
    y1, x1 = (y0 + 1) % period, (x0 + 1) % period
    a = g[np.ix_(y0, x0)]
    b = g[np.ix_(y0, x1)]
    c = g[np.ix_(y1, x0)]
    d = g[np.ix_(y1, x1)]
    return (a * (1 - sx) * (1 - sy) + b * sx * (1 - sy)
            + c * (1 - sx) * sy + d * sx * sy)


def fbm(h: int, w: int, period: int = 4, octaves: int = 5,
        gain: float = 0.5, seed: int = 0) -> np.ndarray:
    """Fractal sum of value noise, normalized to 0..1 — still seamless."""
    out = np.zeros((h, w))
    amp, total, p = 1.0, 0.0, period
    for o in range(octaves):
        out += amp * value_noise(h, w, max(p, 2), seed + o * 101)
        total += amp
        amp *= gain
        p *= 2
    out /= total
    lo, hi = out.min(), out.max()
    return (out - lo) / (hi - lo) if hi > lo else out


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def solid(h: int, w: int, rgb) -> np.ndarray:
    return np.tile(np.array(rgb, dtype=np.float64), (h, w, 1))


def tint(mask: np.ndarray, lo, hi) -> np.ndarray:
    """Map a 0..1 mask onto a colour ramp."""
    lo = np.array(lo, dtype=np.float64)
    hi = np.array(hi, dtype=np.float64)
    return lo + (hi - lo) * mask[..., None]


def overlay(base: np.ndarray, layer: np.ndarray, alpha) -> np.ndarray:
    """Composite *layer* over *base*; alpha may be scalar or an (H, W) mask."""
    a = alpha[..., None] if isinstance(alpha, np.ndarray) and alpha.ndim == 2 else alpha
    return base * (1 - a) + layer * a


def ao_gradient(h: int, w: int, strength: float = 0.35,
                axis: str = 'v') -> np.ndarray:
    """A soft darkening ramp, as baked ambient occlusion — the cheap trick
    that stops a flat-lit surface reading as plastic."""
    t = np.linspace(0, 1, h)[:, None] if axis == 'v' else np.linspace(0, 1, w)[None, :]
    return np.broadcast_to(1.0 - strength * (1.0 - t), (h, w))


def save(rgb: np.ndarray, path) -> Path:
    """Write an (H, W, 3) float 0..1 or uint8 array as PNG."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = rgb
    if arr.dtype != np.uint8:
        arr = np.clip(arr, 0, 1) if arr.max() <= 1.001 else np.clip(arr / 255.0, 0, 1)
        arr = (arr * 255).round().astype(np.uint8)
    Image.fromarray(arr, mode='RGB').save(path, optimize=True)
    return path


# --------------------------------------------------------------------------
# materials
# --------------------------------------------------------------------------

def facade(h=512, w=512, cols=8, rows=12, seed=0,
           wall=(0.42, 0.44, 0.48), frame=(0.20, 0.21, 0.24),
           lit=(1.0, 0.86, 0.55), dark=(0.06, 0.08, 0.12),
           lit_fraction=0.35, mullions=True) -> np.ndarray:
    """A night-time office facade: a grid of windows, a random scatter of them
    lit. Tiles seamlessly in both directions, so `uv_world` mapping can run a
    single image up a 60-storey tower without a visible repeat line."""
    rng = _rng(seed)
    img = solid(h, w, wall)
    grime = fbm(h, w, period=3, octaves=4, seed=seed + 7)
    img *= (0.82 + 0.28 * grime)[..., None]

    ch, cw = h / rows, w / cols
    ys, xs = np.mgrid[0:h, 0:w]
    # per-cell coordinates and per-cell index
    cy, cx = (ys / ch).astype(int), (xs / cw).astype(int)
    fy, fx = (ys % ch) / ch, (xs % cw) / cw

    # window opening: a margin inside each cell
    mx, my = 0.18, 0.22
    inside = (fx > mx) & (fx < 1 - mx) & (fy > my) & (fy < 1 - my)

    state = rng.random((rows, cols))
    bright = rng.random((rows, cols)) * 0.5 + 0.5
    is_lit = state[cy, cx] < lit_fraction
    glow = bright[cy, cx]

    glass = np.where(is_lit[..., None],
                     np.array(lit) * glow[..., None],
                     np.array(dark) * (0.7 + 0.6 * grime)[..., None])
    img = np.where(inside[..., None], glass, img)

    if mullions:
        bar = ((np.abs(fx - 0.5) < 0.012) | (np.abs(fy - 0.5) < 0.010)) & inside
        img = np.where(bar[..., None], np.array(frame), img)

    # floor slab shadow under each band of windows
    slab = (fy < my * 0.55)
    img = np.where(slab[..., None], img * 0.72, img)
    return img


def brick(h=256, w=256, rows=16, seed=0,
          mortar=(0.78, 0.76, 0.72), base=(0.55, 0.26, 0.20)) -> np.ndarray:
    """Running-bond brick, each brick tinted slightly differently."""
    rng = _rng(seed)
    cols = rows // 2
    ys, xs = np.mgrid[0:h, 0:w]
    rh, bw = h / rows, w / cols
    ry = (ys / rh).astype(int)
    offset = np.where(ry % 2 == 0, 0.0, bw / 2)
    xo = (xs + offset) % w
    rx = (xo / bw).astype(int)
    fy, fx = (ys % rh) / rh, (xo % bw) / bw

    shade = rng.random((rows, cols)) * 0.34 + 0.83
    img = np.array(base) * shade[ry, rx][..., None]
    img *= (0.85 + 0.3 * fbm(h, w, period=8, octaves=4, seed=seed + 3))[..., None]
    joint = (fy < 0.10) | (fx < 0.055)
    img = np.where(joint[..., None], np.array(mortar) * 0.92, img)
    return img


def asphalt(h=256, w=256, seed=0, stripe=None) -> np.ndarray:
    """Road surface. `stripe` draws a dashed centre line down the v axis."""
    grain = fbm(h, w, period=16, octaves=5, seed=seed)
    img = tint(grain, (0.16, 0.16, 0.17), (0.30, 0.30, 0.32))
    patch = fbm(h, w, period=3, octaves=3, seed=seed + 11)
    img = overlay(img, img * 0.75, (patch > 0.68).astype(float) * 0.5)
    if stripe:
        ys, xs = np.mgrid[0:h, 0:w]
        on_line = np.abs(xs - w / 2) < w * 0.018
        dash = ((ys / (h / 8)).astype(int) % 2) == 0
        img = np.where((on_line & dash)[..., None], np.array(stripe), img)
    return img


def bark(h=256, w=256, seed=0, base=(0.30, 0.22, 0.15)) -> np.ndarray:
    """Vertical fissured bark — stretched noise plus dark grooves."""
    n = fbm(h, w * 4, period=6, octaves=5, seed=seed)[:, ::4]
    ridge = fbm(h, w, period=10, octaves=3, seed=seed + 5)
    fissure = np.abs(ridge - 0.5) * 2
    img = tint(n, np.array(base) * 0.55, np.array(base) * 1.5)
    img *= (0.45 + 0.75 * fissure)[..., None]
    return img


def hull_plating(h=512, w=512, seed=0, cells=10,
                 base=(0.60, 0.61, 0.64)) -> np.ndarray:
    """Panelled starship hull: rectangular plates, recessed seams, rivets,
    scorch and streaked weathering.

    Plates are RECTANGULAR, laid as rows of varying height each split into
    plates of varying width. An earlier version used a jittered Voronoi, which
    tiles just as well but reads as stone paving — hull plate is cut and
    welded, so the eye wants straight seams and consistent runs. The row and
    column splits are integer partitions of the image, so the pattern still
    wraps exactly in both directions.

    Plate *size* is what the eye reads as ship size, so `cells` is the single
    most load-bearing parameter in the fleet scene: fewer, larger plates make
    a hull look bigger."""
    rng = _rng(seed)

    def partition(total: int, n: int) -> np.ndarray:
        """n integers summing exactly to total, uneven but none tiny.

        A plain random-cut partition happily emits 1-pixel slivers, which read
        as glitches rather than as narrow plates. Each piece gets a floor of
        `total / (2n)` and the remainder is distributed randomly on top."""
        n = max(int(n), 1)
        floor = max(total // (2 * n), 1)
        spare = total - floor * n
        if spare <= 0:
            return np.full(n, total // n) + np.array(
                [1] * (total % n) + [0] * (n - total % n))
        extra = rng.multinomial(spare, np.ones(n) / n)
        return floor + extra

    row_h = partition(h, max(cells // 2, 2))
    row_of = np.repeat(np.arange(len(row_h)), row_h)          # (h,)
    row_v = np.concatenate([[0], np.cumsum(row_h)])

    plate = np.zeros((h, w), dtype=int)
    seam = np.zeros((h, w))
    next_id = 0
    for r, hh in enumerate(row_h):
        widths = partition(w, max(int(rng.integers(cells - 2, cells + 3)), 2))
        edges = np.concatenate([[0], np.cumsum(widths)])
        col_of = np.repeat(np.arange(len(widths)), widths)
        plate[row_v[r]:row_v[r + 1], :] = next_id + col_of
        next_id += len(widths)
        # vertical seams inside the row
        for e in edges[:-1]:
            seam[row_v[r]:row_v[r + 1], (e - 1) % w:(e + 1) % w or w] = 1.0
            seam[row_v[r]:row_v[r + 1], e % w] = 1.0
    # horizontal seams between rows
    for e in row_v[:-1]:
        seam[e % h, :] = 1.0
        seam[(e - 1) % h, :] = np.maximum(seam[(e - 1) % h, :], 0.6)

    shade = rng.random(next_id) * 0.20 + 0.88
    img = np.array(base) * shade[plate][..., None]
    img *= (0.90 + 0.18 * fbm(h, w, period=8, octaves=5, seed=seed + 2))[..., None]

    # seams are recessed, so they read dark with a bright lip above
    img = overlay(img, img * 0.30, seam * 0.85)

    # rivet runs just inside the plate edges
    near = np.zeros((h, w))
    for e in row_v[:-1]:
        near[(e + 3) % h, :] = 1.0
        near[(e - 4) % h, :] = 1.0
    dots = ((np.arange(w) % 9) == 0)[None, :]
    img = overlay(img, img * 1.45, (near * dots).astype(float) * 0.7)

    # streaked weathering running down the hull, plus scorch blotches
    streak = fbm(h, w * 6, period=24, octaves=4, seed=seed + 13)[:, ::6]
    img = overlay(img, img * 0.62, np.clip((streak - 0.60) * 2.6, 0, 1) * 0.55)
    scorch = fbm(h, w, period=3, octaves=4, seed=seed + 17)
    img = overlay(img, img * np.array([0.38, 0.35, 0.34]),
                  np.clip((scorch - 0.66) * 3.2, 0, 1) * 0.7)
    return np.clip(img, 0, 1)


def greeble_panel(h=512, w=512, seed=0, base=(0.55, 0.56, 0.60),
                  boxes=220) -> np.ndarray:
    """Machined surface clutter — the flat-shaded "greebling" that reads as
    industrial detail at a distance without costing any triangles."""
    rng = _rng(seed)
    img = solid(h, w, base)
    img *= (0.85 + 0.3 * fbm(h, w, period=6, octaves=4, seed=seed + 1))[..., None]
    for _ in range(boxes):
        bw = int(rng.integers(4, max(5, w // 12)))
        bh = int(rng.integers(3, max(4, h // 16)))
        x = int(rng.integers(0, w))
        y = int(rng.integers(0, h))
        shade = float(rng.random() * 0.7 + 0.5)
        xs = (np.arange(x, x + bw)) % w
        ys = (np.arange(y, y + bh)) % h
        img[np.ix_(ys, xs)] *= shade
        # a highlight lip on one side, which is what makes it read as 3-D
        img[np.ix_(ys[:1], xs)] *= 1.6
    return np.clip(img, 0, 1)


def scales(h=256, w=256, seed=0, base=(0.22, 0.30, 0.36), rows=22) -> np.ndarray:
    """Overlapping rounded scales/skin, for the whale and other creatures."""
    cols = rows
    ys, xs = np.mgrid[0:h, 0:w]
    rh, cw = h / rows, w / cols
    ry = (ys / rh).astype(int)
    xo = (xs + np.where(ry % 2 == 0, 0.0, cw / 2)) % w
    fy, fx = (ys % rh) / rh, (xo % cw) / cw
    d = np.sqrt(((fx - 0.5) * 2) ** 2 + ((fy - 0.5) * 1.7) ** 2)
    lobe = np.clip(1.0 - d, 0, 1) ** 0.6
    img = tint(lobe, np.array(base) * 0.55, np.array(base) * 1.35)
    img *= (0.88 + 0.24 * fbm(h, w, period=6, octaves=4, seed=seed))[..., None]
    return img


def foliage(h=256, w=256, seed=0, base=(0.20, 0.42, 0.16)) -> np.ndarray:
    """Clumped leaf canopy — mottled greens with baked depth shading."""
    clump = fbm(h, w, period=6, octaves=5, seed=seed)
    fine = fbm(h, w, period=24, octaves=3, seed=seed + 9)
    img = tint(clump, np.array(base) * 0.45, np.array(base) * 1.6)
    img *= (0.80 + 0.4 * fine)[..., None]
    img = overlay(img, img * np.array([1.25, 1.15, 0.7]),
                  np.clip((clump - 0.7) * 3, 0, 1) * 0.5)   # sunlit tips
    return img


def metal_panel(h=256, w=256, seed=0, base=(0.72, 0.74, 0.78),
                bands=6) -> np.ndarray:
    """Brushed aircraft skin: fine directional grain plus panel seams."""
    grain = fbm(h * 1, w * 8, period=64, octaves=3, seed=seed)[:, ::8]
    img = tint(grain, np.array(base) * 0.9, np.array(base) * 1.08)
    ys, xs = np.mgrid[0:h, 0:w]
    seam = (np.abs((ys % (h / bands)) - 0) < 1.2)
    img = overlay(img, img * 0.6, seam.astype(float) * 0.8)
    rivet = (fbm(h, w, period=bands * 8, octaves=2, seed=seed + 4) > 0.70)
    img = overlay(img, img * 0.75, (rivet & seam).astype(float))
    return img
