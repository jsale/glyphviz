"""
organic — meshes from masks: curved walls, smooth-edged slabs, ribbon arches.

The Banyan Tree school has no straight walls worth the name; it was drawn in
the spirit of James Hubbell, whose buildings are poured, plastered and
stacked rather than framed. A footprint-and-prism toolkit (meshkit.prism)
would square every curve off, so this module works from RASTER masks instead:

* `walls_from_mask` smooths a wall mask and takes its iso-line as the wall's
  faces. A wall drawn as one stroke becomes a closed loop around that stroke,
  so both faces, the rounded ends and every door jamb come out of one contour.
* `slab_from_mask` tessellates a region as a height field -- floors, roofs,
  wall tops -- and SNAPS the cells that straddle its edge onto the same smooth
  iso-line, so a curved roof edge is a curve and not a staircase of cells.
* `ribbon` sweeps a vertical band along a path whose height varies, which is
  how the elevation's soaring walkway arches are built.

All of them take a `Grid`: the mask's pixel -> world transform. The plan is in
pixels with y pointing DOWN, the scene is in metres with y pointing NORTH, and
that one flip reverses every winding -- so each builder checks its normals
against the world rather than trusting the pixel-space order.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import contourpy
import numpy as np
from scipy import ndimage as ndi

import meshkit as mk


@dataclass
class Grid:
    """Pixel (col, row) -> world (x, y). `m` metres per pixel, `origin` the
    world position of pixel (0, 0), y flipped."""
    m: float
    origin: tuple

    def world(self, col, row):
        return (self.origin[0] + np.asarray(col, float) * self.m,
                self.origin[1] - np.asarray(row, float) * self.m)

    def pixel(self, x, y):
        return ((np.asarray(x, float) - self.origin[0]) / self.m,
                (self.origin[1] - np.asarray(y, float)) / self.m)


def smooth_field(mask: np.ndarray, sigma: float) -> np.ndarray:
    """A 0..1 field whose 0.5 iso-line is the mask's edge, rounded off."""
    return ndi.gaussian_filter(mask.astype(float), sigma)


def _sample(field, cols, rows):
    return ndi.map_coordinates(field, [np.atleast_1d(rows), np.atleast_1d(cols)],
                               order=1, mode='constant', cval=0.0)


def _rdp(pts: np.ndarray, tol: float) -> np.ndarray:
    """Ramer-Douglas-Peucker on an open polyline (iterative)."""
    if len(pts) < 3:
        return pts
    keep = np.zeros(len(pts), bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        seg = pts[b] - pts[a]
        L = np.hypot(*seg)
        rel = pts[a + 1:b] - pts[a]
        if L < 1e-12:
            d = np.hypot(rel[:, 0], rel[:, 1])
        else:
            d = np.abs(rel[:, 0] * seg[1] - rel[:, 1] * seg[0]) / L
        i = int(np.argmax(d))
        if d[i] > tol:
            k = a + 1 + i
            keep[k] = True
            stack += [(a, k), (k, b)]
    return pts[keep]


def contours(field: np.ndarray, level=0.5, simplify=0.35):
    """Closed iso-lines of *field*, in pixel coords (col, row), simplified."""
    gen = contourpy.contour_generator(z=field, line_type='Separate')
    out = []
    for line in gen.lines(level):
        line = np.asarray(line, float)            # (N, 2) as (col, row)
        if len(line) < 4:
            continue
        closed = np.allclose(line[0], line[-1])
        body = line[:-1] if closed else line
        if simplify:
            # RDP needs an open run; split the loop at its far point
            k = int(np.argmax(np.hypot(*(body - body[0]).T)))
            a = _rdp(body[:k + 1], simplify)
            b = _rdp(np.vstack([body[k:], body[:1]]), simplify)
            body = np.vstack([a[:-1], b[:-1]])
        if len(body) >= 3:
            out.append(body)
    return out


def walls_from_mask(mask, grid: Grid, z_bottom, z_top, *, sigma=1.2,
                    uv_scale=0.25, name="walls", field=None):
    """Vertical wall faces around every connected blob of *mask*.

    `z_bottom`/`z_top` are callables f(x, y) -> z in world metres (or
    numbers), evaluated per vertex, so a wall top can undulate. UVs run u along
    the wall (world metres x uv_scale) and v up it, so a texture keeps one
    real-world size on every wall, curved or not.
    """
    f = smooth_field(mask, sigma) if field is None else field
    zb = z_bottom if callable(z_bottom) else (lambda x, y, c=z_bottom: np.full(np.shape(x), c))
    zt = z_top if callable(z_top) else (lambda x, y, c=z_top: np.full(np.shape(x), c))
    m = mk.Mesh(name)
    for loop in contours(f):
        cols, rows = loop[:, 0], loop[:, 1]
        # Orientation: the wall's solid side is where the field is high. Walk
        # so that the OUTSIDE is to the right of travel in world space (the
        # right-hand side is where a quad (a0,b0,b1,a1) faces).
        x, y = grid.world(cols, rows)
        nxt = np.roll(np.arange(len(x)), -1)
        tx, ty = x[nxt] - x, y[nxt] - y
        L = np.hypot(tx, ty) + 1e-12
        rx, ry = ty / L, -tx / L                     # right-hand normal
        pc, pr = grid.pixel(x + (tx * 0.5) + rx * grid.m * 1.5,
                            y + (ty * 0.5) + ry * grid.m * 1.5)
        if np.mean(_sample(f, pc, pr) > 0.5) > 0.5:  # right side is solid
            x, y = x[::-1], y[::-1]
        zb_v, zt_v = zb(x, y), zt(x, y)
        run = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))])
        n = len(x)
        total = run[-1] + math.hypot(x[0] - x[-1], y[0] - y[-1])
        for i in range(n):
            j = (i + 1) % n
            u0 = run[i] * uv_scale
            u1 = (run[j] if j else total) * uv_scale
            m.add_quad((x[i], y[i], zb_v[i]), (x[j], y[j], zb_v[j]),
                       (x[j], y[j], zt_v[j]), (x[i], y[i], zt_v[i]),
                       uvs=[(u0, zb_v[i] * uv_scale), (u1, zb_v[j] * uv_scale),
                            (u1, zt_v[j] * uv_scale), (u0, zt_v[i] * uv_scale)])
    return m


def slab_from_mask(mask, grid: Grid, z_fn, *, cell=3, sigma=1.2, field=None,
                   uv_fn=None, up=True, name="slab"):
    """A height-field surface over *mask*, with its edge snapped smooth.

    `cell` is in pixels. Cells with at least one corner inside are kept, and
    every corner that falls outside is walked along the field gradient onto
    the 0.5 iso-line -- the same line `walls_from_mask` builds faces on, so a
    roof edge sits on its wall instead of stepping past it.

    `z_fn(x, y)` gives height; `uv_fn(x, y) -> (u, v)` texture coordinates
    (default: world metres / 4). `up=False` faces the surface downward.
    """
    f = smooth_field(mask, sigma) if field is None else field
    H, W = f.shape
    rows = np.arange(0, H + cell, cell, dtype=float)
    cols = np.arange(0, W + cell, cell, dtype=float)
    R, C = np.meshgrid(rows, cols, indexing='ij')
    fv = _sample(f, C.ravel(), R.ravel()).reshape(R.shape)
    inside = fv >= 0.5
    cell_in = (inside[:-1, :-1] | inside[1:, :-1] | inside[:-1, 1:] | inside[1:, 1:])
    used = np.zeros_like(inside)
    used[:-1, :-1] |= cell_in
    used[1:, :-1] |= cell_in
    used[:-1, 1:] |= cell_in
    used[1:, 1:] |= cell_in

    # Snap outside corners onto the edge with a signed distance field: unlike
    # the blurred mask, its gradient is defined everywhere, so a corner a
    # whole cell outside still knows which way the edge is.
    pc, pr = C.copy(), R.copy()
    snap = used & ~inside
    solid = f >= 0.5
    sdf = (ndi.distance_transform_edt(~solid) - ndi.distance_transform_edt(solid))
    sdf = ndi.gaussian_filter(sdf, 1.0)
    gy, gx = np.gradient(sdf)
    sc, sr = pc[snap], pr[snap]
    for _ in range(3):
        val = _sample(sdf, sc, sr)
        gxx, gyy = _sample(gx, sc, sr), _sample(gy, sc, sr)
        gn = np.hypot(gxx, gyy) + 1e-9
        step = np.clip(val, 0, cell * 1.5)
        sc = sc - step * gxx / gn
        sr = sr - step * gyy / gn
    pc[snap], pr[snap] = sc, sr

    x, y = grid.world(pc, pr)
    z = z_fn(x, y)
    if uv_fn is None:
        uv_fn = lambda xx, yy: (xx / 4.0, yy / 4.0)   # noqa: E731
    u, v = uv_fn(x, y)
    u = np.broadcast_to(np.asarray(u, float), x.shape)
    v = np.broadcast_to(np.asarray(v, float), x.shape)

    m = mk.Mesh(name)
    idx = -np.ones(R.shape, int)
    for (i, j) in zip(*np.nonzero(used)):
        idx[i, j] = m.vert((x[i, j], y[i, j], z[i, j]), (u[i, j], v[i, j]))
    for (i, j) in zip(*np.nonzero(cell_in)):
        a, b, c, d = idx[i, j], idx[i, j + 1], idx[i + 1, j + 1], idx[i + 1, j]
        # pixel order a,b,c,d is clockwise in world (y flipped) -> faces down
        if up:
            m.quad(a, d, c, b)
        else:
            m.quad(a, b, c, d)
    return m


def ribbon(path_xy, z_lo, z_hi, thickness=0.3, name="ribbon") -> mk.Mesh:
    """A vertical band of *thickness* swept along a 2-D path, its bottom and
    top heights given per path point -- an arch, a swooping wall, a bench."""
    p = np.asarray(path_xy, float)
    z_lo = np.broadcast_to(np.asarray(z_lo, float), (len(p),))
    z_hi = np.broadcast_to(np.asarray(z_hi, float), (len(p),))
    t = np.gradient(p, axis=0)
    t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-12
    nrm = np.stack([-t[:, 1], t[:, 0]], axis=1) * (thickness / 2)
    secs = []
    for k in range(len(p)):
        a, b = p[k] - nrm[k], p[k] + nrm[k]
        secs.append([(a[0], a[1], z_lo[k]), (b[0], b[1], z_lo[k]),
                     (b[0], b[1], z_hi[k]), (a[0], a[1], z_hi[k])])
    return mk.loft(secs, closed=True, cap_start=True, cap_end=True, name=name)


def centerline(mask: np.ndarray, step=4.0):
    """Order the pixels of a thin, curve-like blob into a polyline (col, row).

    No skeletonization library is available here, so: geodesic distance from
    one end (found by a double breadth-first sweep), then bin pixels by that
    distance and average each bin."""
    pts = np.argwhere(mask)
    if len(pts) < 3:
        return None
    index = {tuple(p): k for k, p in enumerate(pts)}
    nbrs = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

    def bfs(start):
        dist = np.full(len(pts), -1.0)
        dist[start] = 0
        q = [start]
        h = 0
        while h < len(q):
            k = q[h]
            h += 1
            r, c = pts[k]
            for dr, dc in nbrs:
                j = index.get((r + dr, c + dc))
                if j is not None and dist[j] < 0:
                    dist[j] = dist[k] + math.hypot(dr, dc)
                    q.append(j)
        return dist

    d0 = bfs(0)
    a = int(np.argmax(d0))
    d = bfs(a)
    bins = np.floor(d / step).astype(int)
    out = []
    for b in range(bins.max() + 1):
        sel = bins == b
        if sel.any():
            r, c = pts[sel].mean(axis=0)
            out.append((c, r))
    return np.array(out)


def resample(path, spacing):
    """Even spacing along a polyline."""
    p = np.asarray(path, float)
    seg = np.hypot(*np.diff(p, axis=0).T)
    run = np.concatenate([[0.0], np.cumsum(seg)])
    n = max(int(run[-1] / spacing), 2)
    s = np.linspace(0, run[-1], n + 1)
    return np.stack([np.interp(s, run, p[:, 0]), np.interp(s, run, p[:, 1])], axis=1)


def smooth_path(path, passes=3):
    p = np.asarray(path, float).copy()
    for _ in range(passes):
        p[1:-1] = 0.25 * p[:-2] + 0.5 * p[1:-1] + 0.25 * p[2:]
    return p
