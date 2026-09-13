"""Terrain for a lon/lat window: fetch a DEM, build the lattice a TOPO_SURFACE
draws, and drape lines onto that lattice so they sit ON the rendered relief.

Qt-free, like basemap.py beside it, and for the same reason: everything here is
testable headlessly with an injected tile fetcher. Heights are metres and
positions are lon/lat throughout. Mapping to world units is the caller's
business, and it is affine per axis (x from lon, y from lat, z from height),
so a fraction computed here is the same fraction in the scene.

THE ONE THING TO KNOW: drape onto the lattice, never onto the DEM
-----------------------------------------------------------------
A Surface mesh is far coarser than its DEM, so each vertex has to carry the
MEAN height of its cell (point-sampling aliases single crags into spikes and
loses the landform). Averaging fills valleys in. A river sampled straight from
the DEM therefore runs UNDER the surface you can see: measured on the San Diego
River's 1,256-vertex mainstem, 94% of vertices were buried at a 300-column
lattice (worst 73 m of true height), and 87% even at 600 columns.

So a draped line is placed against `Lattice.surface_height`, the height of the
quad actually drawn. GL_QUADS may be split along either diagonal by the driver,
so that height is the max of both triangulations. Then `drape_polyline` inserts
a vertex wherever a segment crosses a lattice line or either diagonal. Between
two such breakpoints each triangulation is a single plane, so max(A, B) is
convex along the segment and the straight chord between two draped points can
never pass beneath it.

DEM SOURCE
----------
AWS Terrain Tiles in the Terrarium encoding (Mapzen, hosted as AWS Open Data):
free, no key, no registration. Height = (R*256 + G + B/256) - 32768 metres.
US coverage at high zoom comes from USGS 3DEP. Each tile is decoded to float
BEFORE anything is resampled: interpolating raw RGB mixes the high and low
bytes of neighbouring heights and produces nonsense.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from glyphviz_core.basemap import (
    TILE_SIZE, BBox, Provider, _default_fetch, _get_tile_bytes, _lon_x_norm,
    _merc_y_norm, default_cache_dir,
)

TERRARIUM = Provider(
    key="terrarium",
    label="AWS Terrain Tiles (Terrarium)",
    url_template=("https://s3.amazonaws.com/elevation-tiles-prod/"
                  "terrarium/{z}/{x}/{y}.png"),
    attribution="Terrain Tiles: Mapzen / AWS Open Data (USGS 3DEP, SRTM, GMTED)",
    max_zoom=15,
)

DEFAULT_DEM_ZOOM = 12            # ~32 m/px at 33°N
DEFAULT_DEM_TILE_CAP = 150


class TerrainError(Exception):
    """Anything that should surface as a message, not a traceback."""


# --- DEM -----------------------------------------------------------------------

def decode_terrarium(rgb: np.ndarray) -> np.ndarray:
    """(H, W, 3) Terrarium pixels -> (H, W) float32 metres."""
    rgb = rgb.astype(np.float64)
    return ((rgb[..., 0] * 256.0 + rgb[..., 1] + rgb[..., 2] / 256.0)
            - 32768.0).astype(np.float32)


@dataclass
class Dem:
    """A stitched block of Web Mercator tiles, in metres, north-up.

    Kept in Mercator rather than reprojected: every lookup converts lon/lat to
    tile space exactly, so the projection costs no resampling error.
    Pixel (i, j) covers [i, i+1) x [j, j+1) and its value sits at the centre.
    """
    heights: np.ndarray          # (rows, cols) float32 metres
    zoom: int
    tx0: int                     # tile column of heights[:, 0]
    ty0: int                     # tile row of heights[0, :]

    def pixel_xy(self, lon, lat):
        """Continuous pixel coordinates (edge-based) of lon/lat; vectorised."""
        n = float(1 << self.zoom)
        lon = np.asarray(lon, dtype=np.float64)
        lat = np.radians(np.asarray(lat, dtype=np.float64))
        px = ((lon + 180.0) / 360.0 * n - self.tx0) * TILE_SIZE
        py = ((1.0 - np.arcsinh(np.tan(lat)) / math.pi) / 2.0 * n
              - self.ty0) * TILE_SIZE
        return px, py

    def sample(self, lon, lat):
        """Bilinear height in metres at lon/lat (clamped to the block edge)."""
        px, py = self.pixel_xy(lon, lat)
        h, w = self.heights.shape
        x = np.clip(px - 0.5, 0.0, w - 1.0)
        y = np.clip(py - 0.5, 0.0, h - 1.0)
        ix = np.minimum(np.floor(x).astype(np.int64), w - 2)
        iy = np.minimum(np.floor(y).astype(np.int64), h - 2)
        fx, fy = x - ix, y - iy
        H = self.heights
        top = H[iy, ix] * (1 - fx) + H[iy, ix + 1] * fx
        bot = H[iy + 1, ix] * (1 - fx) + H[iy + 1, ix + 1] * fx
        out = top * (1 - fy) + bot * fy
        return float(out) if np.ndim(out) == 0 else out


def plan_dem_tiles(bbox: BBox, zoom: int) -> tuple[int, int, int, int]:
    """(tx_min, tx_max, ty_min, ty_max) covering bbox at zoom."""
    bbox = bbox.clamped()
    bbox.validate()
    n = 1 << zoom
    tx_min = min(int(_lon_x_norm(bbox.lon_min) * n), n - 1)
    tx_max = min(int(_lon_x_norm(bbox.lon_max) * n), n - 1)
    ty_min = min(int(_merc_y_norm(bbox.lat_max) * n), n - 1)   # north edge
    ty_max = min(int(_merc_y_norm(bbox.lat_min) * n), n - 1)
    return tx_min, tx_max, ty_min, ty_max


def fetch_dem(bbox: BBox, zoom: int = DEFAULT_DEM_ZOOM, *, fetch=None,
              cache_dir: Path | None = None, progress=None,
              tile_cap: int = DEFAULT_DEM_TILE_CAP,
              clamp_sea: bool = True) -> Dem:
    """Stitch Terrarium tiles over bbox into a Dem.

    *fetch* is url -> bytes (tests inject one; default uses requests), and
    tiles share Fetch Basemap's on-disk cache, so a rebuild re-fetches
    nothing. *clamp_sea* flattens everything below 0 m to 0 BEFORE any
    averaging: an offshore trench averaged against a coastal cell otherwise
    punches a hole through the shoreline (the Pacific reaches -6,700 m within
    sixty miles of San Diego).
    """
    from PIL import Image

    if not 0 <= zoom <= TERRARIUM.max_zoom:
        raise TerrainError(f"DEM zoom must be 0..{TERRARIUM.max_zoom}, got {zoom}")
    tx_min, tx_max, ty_min, ty_max = plan_dem_tiles(bbox, zoom)
    nx, ny = tx_max - tx_min + 1, ty_max - ty_min + 1
    if nx * ny > tile_cap:
        raise TerrainError(
            f"{nx * ny} DEM tiles at zoom {zoom} exceeds the cap of {tile_cap}; "
            f"lower the zoom or raise tile_cap")
    fetch = fetch or _default_fetch
    cache_dir = cache_dir or default_cache_dir()

    canvas = np.zeros((ny * TILE_SIZE, nx * TILE_SIZE), dtype=np.float32)
    done = 0
    for ty in range(ty_min, ty_max + 1):
        for tx in range(tx_min, tx_max + 1):
            try:
                data = _get_tile_bytes(TERRARIUM, zoom, tx, ty, cache_dir, fetch)
            except Exception as exc:
                raise TerrainError(str(exc)) from exc
            rgb = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
            if rgb.shape[:2] != (TILE_SIZE, TILE_SIZE):
                raise TerrainError(f"DEM tile {zoom}/{tx}/{ty} is not "
                                   f"{TILE_SIZE}x{TILE_SIZE}")
            r0, c0 = (ty - ty_min) * TILE_SIZE, (tx - tx_min) * TILE_SIZE
            canvas[r0:r0 + TILE_SIZE, c0:c0 + TILE_SIZE] = decode_terrarium(rgb)
            done += 1
            if progress:
                progress(done, nx * ny)
    if clamp_sea:
        np.maximum(canvas, 0.0, out=canvas)
    return Dem(canvas, zoom, tx_min, ty_min)


# --- the lattice a Surface draws ---------------------------------------------------

@dataclass
class Lattice:
    """Evenly spaced lon/lat axes and the height at every vertex, in metres.

    `heights[j, i]` is the vertex at (lons[i], lats[j]); lats ascend south to
    north. This is exactly the grid of children a TOPO_SURFACE parent is given,
    so its geometry IS the rendered mesh.
    """
    lons: np.ndarray             # (cols,)
    lats: np.ndarray             # (rows,)
    heights: np.ndarray          # (rows, cols)

    @property
    def cols(self) -> int:
        return len(self.lons)

    @property
    def rows(self) -> int:
        return len(self.lats)

    def fractional(self, lon, lat):
        """Lattice index coordinates (u along lons, v along lats); vectorised
        and NOT clamped."""
        u = (np.asarray(lon, dtype=np.float64) - self.lons[0]) \
            / ((self.lons[-1] - self.lons[0]) / (self.cols - 1))
        v = (np.asarray(lat, dtype=np.float64) - self.lats[0]) \
            / ((self.lats[-1] - self.lats[0]) / (self.rows - 1))
        return u, v

    def surface_height(self, lon, lat):
        """Height of the rendered surface at lon/lat, in metres.

        The quad under the point is drawn as two triangles along a diagonal the
        driver chooses, so this is the max of both triangulations — the top of
        whichever surface is on screen. Points outside the lattice clamp to its
        edge.
        """
        u, v = self.fractional(lon, lat)
        u = np.clip(u, 0.0, self.cols - 1.0)
        v = np.clip(v, 0.0, self.rows - 1.0)
        i = np.minimum(np.floor(u).astype(np.int64), self.cols - 2)
        j = np.minimum(np.floor(v).astype(np.int64), self.rows - 2)
        fu, fv = u - i, v - j
        H = self.heights
        h00, h10 = H[j, i], H[j, i + 1]
        h01, h11 = H[j + 1, i], H[j + 1, i + 1]
        # Diagonal 00-11.
        a = np.where(fu >= fv,
                     h00 + fu * (h10 - h00) + fv * (h11 - h10),
                     h00 + fv * (h01 - h00) + fu * (h11 - h01))
        # Diagonal 10-01.
        b = np.where(fu + fv <= 1.0,
                     h00 + fu * (h10 - h00) + fv * (h01 - h00),
                     h11 + (1.0 - fu) * (h01 - h11) + (1.0 - fv) * (h10 - h11))
        out = np.maximum(a, b)
        return float(out) if np.ndim(out) == 0 else out


def lattice_rows_for(bbox: BBox, cols: int) -> int:
    """Rows that give square ground cells for *cols* columns over bbox."""
    lat_c = math.radians((bbox.lat_min + bbox.lat_max) / 2.0)
    ground_w = (bbox.lon_max - bbox.lon_min) * math.cos(lat_c)
    ground_h = bbox.lat_max - bbox.lat_min
    return max(2, int(round(cols * ground_h / ground_w)))


def build_lattice(dem: Dem, bbox: BBox, cols: int,
                  rows: int | None = None) -> Lattice:
    """Area-averaged vertex heights over bbox.

    Each vertex takes the mean of every DEM pixel overlapping its cell (the
    cell being the vertex +/- half a lattice step), computed with a
    summed-area table so a 600-column terrain costs one pass over the DEM, not
    one slice per vertex. A cell narrower than a pixel falls back to the one
    pixel it lies in.
    """
    if cols < 2:
        raise TerrainError("a lattice needs at least 2 columns")
    rows = rows if rows is not None else lattice_rows_for(bbox, cols)
    if rows < 2:
        raise TerrainError("a lattice needs at least 2 rows")
    lons = np.linspace(bbox.lon_min, bbox.lon_max, cols)
    lats = np.linspace(bbox.lat_min, bbox.lat_max, rows)
    dlon = (bbox.lon_max - bbox.lon_min) / (cols - 1) / 2.0
    dlat = (bbox.lat_max - bbox.lat_min) / (rows - 1) / 2.0

    H = dem.heights.astype(np.float64)
    h, w = H.shape
    sat = np.zeros((h + 1, w + 1), dtype=np.float64)
    sat[1:, 1:] = H.cumsum(axis=0).cumsum(axis=1)

    # Pixel spans of each column's and each row's cell, as half-open integer
    # ranges [a, b) that always hold at least one pixel.
    x0, _ = dem.pixel_xy(lons - dlon, lats[0])
    x1, _ = dem.pixel_xy(lons + dlon, lats[0])
    _, y0 = dem.pixel_xy(lons[0], lats + dlat)          # north edge -> smaller y
    _, y1 = dem.pixel_xy(lons[0], lats - dlat)

    def spans(a, b, limit):
        lo = np.clip(np.floor(a).astype(np.int64), 0, limit - 1)
        hi = np.clip(np.ceil(b).astype(np.int64), 1, limit)
        return lo, np.maximum(hi, lo + 1)

    ca, cb = spans(x0, x1, w)
    ra, rb = spans(y0, y1, h)
    total = (sat[rb[:, None], cb[None, :]] - sat[ra[:, None], cb[None, :]]
             - sat[rb[:, None], ca[None, :]] + sat[ra[:, None], ca[None, :]])
    count = (rb - ra)[:, None] * (cb - ca)[None, :]
    return Lattice(lons, lats, (total / count).astype(np.float64))


# --- draping --------------------------------------------------------------------------

def _crossings(f0: float, f1: float) -> list[float]:
    """Segment parameters t in (0, 1) where a linear f crosses an integer."""
    if f1 == f0:
        return []
    lo, hi = min(f0, f1), max(f0, f1)
    return [(k - f0) / (f1 - f0)
            for k in range(math.floor(lo) + 1, math.ceil(hi))]


def simplify_polyline(lons, lats, tolerance_m: float
                      ) -> tuple[np.ndarray, np.ndarray]:
    """Douglas-Peucker in local metres: drop vertices that move the line by
    less than tolerance_m. Endpoints are always kept (so a ring stays closed).

    Survey lines arrive far denser than any lattice can use — NHDPlus
    flowlines carry a vertex every ~50 m and WBD divides are denser still —
    and every surplus vertex becomes a node.
    """
    lons = np.asarray(lons, dtype=np.float64)
    lats = np.asarray(lats, dtype=np.float64)
    n = len(lons)
    if n <= 2 or tolerance_m <= 0:
        return lons.copy(), lats.copy()
    k = 111_320.0
    x = lons * k * math.cos(math.radians(float(lats.mean())))
    y = lats * k
    keep = np.zeros(n, dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        dx, dy = x[b] - x[a], y[b] - y[a]
        seg = math.hypot(dx, dy)
        px, py = x[a + 1:b] - x[a], y[a + 1:b] - y[a]
        if seg == 0.0:
            d = np.hypot(px, py)
        else:
            d = np.abs(px * dy - py * dx) / seg
        i = int(np.argmax(d))
        if d[i] > tolerance_m:
            m = a + 1 + i
            keep[m] = True
            stack.append((a, m))
            stack.append((m, b))
    return lons[keep], lats[keep]


def drape_polyline(lattice: Lattice, lons, lats, clearance: float = 0.0,
                   thin: bool = True
                   ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Lay a lon/lat polyline onto the rendered lattice surface.

    Returns (lons, lats, heights) with a vertex added wherever a segment
    crosses a lattice line or either quad diagonal, and every height set to
    `surface_height + clearance` (metres). Original vertices are kept, in
    order, so a closed ring stays closed.

    Why those breakpoints are sufficient: within the intervals they cut, each
    of the two possible triangulations is one plane, so the surface's max is
    convex along the segment and a straight chord between draped points lies
    on or above it. Nothing finer is needed, and nothing coarser is safe.

    `thin` (default) then drops every inserted breakpoint the line does not
    actually need — which is most of them wherever the surface along the line
    is concave, i.e. along every valley floor a river follows. A breakpoint
    goes only if the longer chord still clears it; since the surface is convex
    between consecutive breakpoints, clearing each skipped breakpoint means
    clearing everything between them, so the guarantee above still holds
    exactly. It matters for more than node count: a thin GL line with a
    round-join point every fraction of a pixel renders dark and hatched.
    Original vertices are never thinned (that would change the line's plan
    shape) — use simplify_polyline for those.
    """
    lons = np.asarray(lons, dtype=np.float64)
    lats = np.asarray(lats, dtype=np.float64)
    if lons.shape != lats.shape or lons.ndim != 1:
        raise TerrainError("lons and lats must be 1-D and the same length")
    if len(lons) == 0:
        return lons.copy(), lats.copy(), np.zeros(0)
    u, v = lattice.fractional(lons, lats)
    out_lon, out_lat = [float(lons[0])], [float(lats[0])]
    for k in range(len(lons) - 1):
        ts = {0.0, 1.0}
        for f0, f1 in ((u[k], u[k + 1]), (v[k], v[k + 1]),
                       (u[k] - v[k], u[k + 1] - v[k + 1]),
                       (u[k] + v[k], u[k + 1] + v[k + 1])):
            ts.update(t for t in _crossings(float(f0), float(f1))
                      if 1e-9 < t < 1.0 - 1e-9)
        t = np.array(sorted(ts))
        sl = lons[k] + t * (lons[k + 1] - lons[k])
        st = lats[k] + t * (lats[k + 1] - lats[k])
        if thin and len(t) > 2:
            z = np.asarray(lattice.surface_height(sl, st), dtype=np.float64)
            kept = [0]
            a = 0
            while a < len(t) - 1:
                # Extend the chord from a as far as it still clears every
                # breakpoint it would skip.
                b = a + 1
                while b + 1 < len(t):
                    c = b + 1
                    mid = slice(a + 1, c)
                    frac = (t[mid] - t[a]) / (t[c] - t[a])
                    if np.all(z[a] + frac * (z[c] - z[a]) >= z[mid] - 1e-9):
                        b = c
                    else:
                        break
                kept.append(b)
                a = b
            sl, st = sl[kept], st[kept]
        out_lon.extend(float(x) for x in sl[1:])
        out_lat.extend(float(y) for y in st[1:])
    out_lon_a = np.array(out_lon)
    out_lat_a = np.array(out_lat)
    heights = np.asarray(lattice.surface_height(out_lon_a, out_lat_a),
                         dtype=np.float64) + clearance
    return out_lon_a, out_lat_a, np.atleast_1d(heights)
