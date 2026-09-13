"""
Terrain (glyphviz_core/terrain.py) unit tests — no network, no Qt.

What's pinned here:

  * Terrarium decoding is exact, and the sea is flattened before averaging;
  * the DEM stitches tiles in the right places and samples lon/lat through
    the Mercator math exactly (a height field that encodes each pixel's own
    position is read back at known points);
  * tiles share the basemap cache — a rebuild fetches nothing — and an
    oversized request is refused rather than hammering the tile server;
  * a lattice vertex is the MEAN of its cell, not a point sample (a single
    spike must not survive as a spike);
  * `surface_height` is the top of whichever triangulation GL draws;
  * the draping guarantee itself: sampled finely along every draped segment,
    the line never dips below either triangulation of the rendered surface —
    and the undensified line demonstrably does, which is why this exists.
"""
import io
import math

import numpy as np
import pytest
from PIL import Image

from glyphviz_core.basemap import TILE_SIZE, BBox
from glyphviz_core.terrain import (
    Dem, Lattice, TerrainError, build_lattice, decode_terrarium,
    drape_polyline, fetch_dem, lattice_rows_for, plan_dem_tiles,
)


def _encode(metres: np.ndarray) -> np.ndarray:
    """Inverse of decode_terrarium, to 1/256 m."""
    v = np.round((metres.astype(np.float64) + 32768.0) * 256.0).astype(np.int64)
    r = (v >> 16) & 0xFF
    g = (v >> 8) & 0xFF
    b = v & 0xFF
    return np.stack([r, g, b], axis=-1).astype(np.uint8)


def _png(rgb: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(rgb, "RGB").save(buf, format="PNG")
    return buf.getvalue()


class _TileServer:
    """Serves tiles whose heights come from field(zoom, tx, ty) -> (256,256)."""

    def __init__(self, field):
        self.field = field
        self.urls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        z, x, y = (int(p) for p in url.rstrip(".png").split("/")[-3:])
        return _png(_encode(self.field(z, x, y)))


SD = BBox(-117.25, -116.50, 32.73, 33.14)


# --- decoding and fetching ---------------------------------------------------------

def test_terrarium_decode_round_trips():
    m = np.array([[-32768.0, -10.5, 0.0], [1.0, 1986.25, 8848.0]])
    assert np.allclose(decode_terrarium(_encode(m)), m, atol=1 / 256)


def test_sea_is_flattened_before_anything_else(tmp_path):
    server = _TileServer(lambda z, x, y: np.full((256, 256), -6700.0))
    dem = fetch_dem(SD, zoom=9, fetch=server, cache_dir=tmp_path)
    assert dem.heights.min() == 0.0
    raw = fetch_dem(SD, zoom=9, fetch=server, cache_dir=tmp_path, clamp_sea=False)
    assert raw.heights.min() == pytest.approx(-6700.0)


def test_tiles_are_stitched_in_place(tmp_path):
    """Each tile carries its own (x, y) as height, so a tile placed in the
    wrong slot reads back as the wrong number."""
    tx0, tx1, ty0, ty1 = plan_dem_tiles(SD, 10)
    # Terrarium holds 24 bits (under 32,768 m), so encode tile OFFSETS.
    server = _TileServer(lambda z, x, y: np.full((256, 256),
                                                  float((x - tx0) * 100 + (y - ty0))))
    dem = fetch_dem(SD, zoom=10, fetch=server, cache_dir=tmp_path)
    assert (tx1 - tx0 + 1) * (ty1 - ty0 + 1) > 1, "need more than one tile"
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            r, c = (ty - ty0) * TILE_SIZE + 100, (tx - tx0) * TILE_SIZE + 100
            assert dem.heights[r, c] == pytest.approx((tx - tx0) * 100 + (ty - ty0))


def test_sampling_goes_through_the_mercator_math(tmp_path):
    """Heights encode each pixel centre's own GLOBAL pixel coordinate (x in one
    test, y in the other), so a sample at lon/lat must return the coordinate
    the slippy-tile formulas predict for that point. The y case is the one
    that catches a linear-in-latitude mistake: Mercator y is not."""
    base = 91000.0                  # keep heights inside Terrarium's range
    lon, lat = -116.9, 32.9
    n = 1 << 11

    def along_x(z, x, y):
        return np.tile(np.arange(256) + x * 256 + 0.5 - base, (256, 1))
    dem = fetch_dem(SD, zoom=11, fetch=_TileServer(along_x), cache_dir=tmp_path / "x")
    expected_px = (lon + 180.0) / 360.0 * n * 256
    assert dem.sample(lon, lat) + base == pytest.approx(expected_px, abs=1e-3)

    base_y = 211000.0

    def along_y(z, x, y):
        return np.tile((np.arange(256) + y * 256 + 0.5 - base_y)[:, None], (1, 256))
    dem = fetch_dem(SD, zoom=11, fetch=_TileServer(along_y), cache_dir=tmp_path / "y")
    merc = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2
    assert dem.sample(lon, lat) + base_y == pytest.approx(merc * n * 256, abs=1e-3)


def test_rebuild_fetches_nothing(tmp_path):
    server = _TileServer(lambda z, x, y: np.zeros((256, 256)))
    fetch_dem(SD, zoom=10, fetch=server, cache_dir=tmp_path)
    first = len(server.urls)
    assert first > 0
    fetch_dem(SD, zoom=10, fetch=server, cache_dir=tmp_path)
    assert len(server.urls) == first


def test_oversized_request_is_refused_before_fetching(tmp_path):
    server = _TileServer(lambda z, x, y: np.zeros((256, 256)))
    with pytest.raises(TerrainError, match="cap"):
        fetch_dem(SD, zoom=15, fetch=server, cache_dir=tmp_path, tile_cap=10)
    assert server.urls == []


def test_fetch_failure_is_a_terrain_error(tmp_path):
    def broken(url):
        raise OSError("offline")
    with pytest.raises(TerrainError):
        fetch_dem(SD, zoom=9, fetch=broken, cache_dir=tmp_path)


# --- lattice ---------------------------------------------------------------------------

def _dem_from(heights: np.ndarray, zoom=12) -> tuple[Dem, BBox]:
    """A Dem over exactly one tile's worth of pixels, and a bbox inside it."""
    tx0, _, ty0, _ = plan_dem_tiles(SD, zoom)
    dem = Dem(heights.astype(np.float32), zoom, tx0, ty0)
    n = 1 << zoom
    lon0 = tx0 / n * 360.0 - 180.0
    lon1 = (tx0 + heights.shape[1] / 256) / n * 360.0 - 180.0

    def lat_of(ty):
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * ty / n))))
    lat1 = lat_of(ty0)
    lat0 = lat_of(ty0 + heights.shape[0] / 256)
    return dem, BBox(lon0, lon1, lat0, lat1)


def test_lattice_vertex_is_the_cell_mean_not_a_point_sample():
    """One 1-pixel spike of 10,000 m: a point sample landing on it keeps a
    10 km needle, the cell mean spreads it to its true volume."""
    H = np.zeros((256, 256))
    dem, box = _dem_from(H)
    lat = build_lattice(dem, box, cols=9, rows=9)
    # Put the spike exactly under an interior vertex.
    px, py = dem.pixel_xy(lat.lons[4], lat.lats[4])
    H[int(py), int(px)] = 10_000.0
    dem = Dem(H.astype(np.float32), dem.zoom, dem.tx0, dem.ty0)
    lat = build_lattice(dem, box, cols=9, rows=9)
    peak = lat.heights.max()
    assert 0 < peak < 500.0, f"spike survived as {peak:.0f} m"


def test_flat_dem_gives_a_flat_lattice():
    dem, box = _dem_from(np.full((256, 256), 321.0))
    lat = build_lattice(dem, box, cols=17)
    assert np.allclose(lat.heights, 321.0)
    assert lat.heights.shape == (lat.rows, 17)


def test_lattice_follows_a_gradient_in_the_right_direction():
    """North is up in the DEM (row 0) and lats ascend in the lattice, so a
    field that rises to the north must rise with j."""
    rows = np.linspace(1000.0, 0.0, 256)[:, None] * np.ones((1, 256))
    dem, box = _dem_from(rows)
    lat = build_lattice(dem, box, cols=6, rows=6)
    col = lat.heights[:, 3]
    assert np.all(np.diff(col) > 0)


def test_rows_default_to_square_ground_cells():
    rows = lattice_rows_for(SD, 300)
    lat_c = math.radians((SD.lat_min + SD.lat_max) / 2)
    w = (SD.lon_max - SD.lon_min) * math.cos(lat_c) / 299
    h = (SD.lat_max - SD.lat_min) / (rows - 1)
    assert h == pytest.approx(w, rel=0.01)


# --- the rendered surface --------------------------------------------------------

def _lattice(H):
    H = np.asarray(H, dtype=np.float64)
    return Lattice(np.linspace(0.0, H.shape[1] - 1.0, H.shape[1]),
                   np.linspace(0.0, H.shape[0] - 1.0, H.shape[0]), H)


def test_surface_height_hits_the_vertices():
    rng = np.random.default_rng(3)
    lat = _lattice(rng.uniform(0, 100, (5, 7)))
    for j in range(5):
        for i in range(7):
            assert lat.surface_height(float(i), float(j)) == pytest.approx(lat.heights[j, i])


def test_saddle_takes_the_higher_triangulation():
    """A saddle quad: one diagonal runs along the ridge (both high corners),
    the other along the valley. At the centre the two triangulations give 10
    and 0 — the surface on screen could be either, so the answer is 10."""
    lat = _lattice([[10.0, 0.0], [0.0, 10.0]])      # h00=10 h10=0 h01=0 h11=10
    assert lat.surface_height(0.5, 0.5) == pytest.approx(10.0)


# --- draping ------------------------------------------------------------------------------

def _triangulations(lat: Lattice, x, y):
    """Both GL splits evaluated independently (a reference implementation)."""
    i = min(int(math.floor(x)), lat.cols - 2)
    j = min(int(math.floor(y)), lat.rows - 2)
    fu, fv = x - i, y - j
    H = lat.heights
    h00, h10, h01, h11 = H[j, i], H[j, i + 1], H[j + 1, i], H[j + 1, i + 1]
    if fu >= fv:
        a = h00 + fu * (h10 - h00) + fv * (h11 - h10)
    else:
        a = h00 + fv * (h01 - h00) + fu * (h11 - h01)
    if fu + fv <= 1:
        b = h00 + fu * (h10 - h00) + fv * (h01 - h00)
    else:
        b = h11 + (1 - fu) * (h01 - h11) + (1 - fv) * (h10 - h11)
    return a, b


def _worst_dip(lat, lons, lats, heights, steps=40):
    """Largest amount any finely sampled point of the polyline sits BELOW
    either triangulation."""
    worst = 0.0
    for k in range(len(lons) - 1):
        for s in np.linspace(0, 1, steps):
            x = lons[k] + s * (lons[k + 1] - lons[k])
            y = lats[k] + s * (lats[k + 1] - lats[k])
            z = heights[k] + s * (heights[k + 1] - heights[k])
            worst = max(worst, max(_triangulations(lat, x, y)) - z)
    return worst


def test_draped_line_never_dips_below_the_rendered_surface():
    rng = np.random.default_rng(11)
    lat = _lattice(rng.uniform(0, 500, (12, 15)))
    for trial in range(25):
        n = rng.integers(2, 8)
        xs = rng.uniform(0, 14, n)
        ys = rng.uniform(0, 11, n)
        dl, dt, dh = drape_polyline(lat, xs, ys)
        assert _worst_dip(lat, dl, dt, dh) < 1e-6, f"trial {trial}"


def test_undensified_line_does_dip_which_is_why_densifying_exists():
    """Control for the test above: the same line with heights only at its own
    vertices goes underground over this terrain."""
    rng = np.random.default_rng(11)
    lat = _lattice(rng.uniform(0, 500, (12, 15)))
    xs = np.array([0.3, 13.7])
    ys = np.array([0.4, 10.6])
    hs = lat.surface_height(xs, ys)
    assert _worst_dip(lat, xs, ys, hs) > 50.0


def test_drape_keeps_original_vertices_in_order_and_closes_rings():
    lat = _lattice(np.zeros((6, 6)))
    ring_x = [0.5, 4.5, 4.5, 0.5, 0.5]
    ring_y = [0.5, 0.5, 4.5, 4.5, 0.5]
    dl, dt, dh = drape_polyline(lat, ring_x, ring_y, clearance=2.0)
    pts = list(zip(dl, dt))
    idx = [pts.index((x, y)) for x, y in zip(ring_x[:-1], ring_y[:-1])]
    assert idx == sorted(idx)
    assert pts[0] == pts[-1]
    assert np.allclose(dh, 2.0)                       # flat ground + clearance


def test_drape_adds_breakpoints_at_lines_and_diagonals():
    """A horizontal segment across three cells crosses 2 interior vertical
    lattice lines plus both diagonals in each cell (u-v and u+v integer
    crossings) — and nothing else."""
    lat = _lattice(np.zeros((3, 4)))
    dl, dt, _ = drape_polyline(lat, [0.0, 3.0], [0.25, 0.25], thin=False)
    assert len(dl) == 2 + 2 + 3 + 3
    assert np.all(np.diff(dl) > 0)


def test_unthinned_drape_never_dips_either():
    rng = np.random.default_rng(5)
    lat = _lattice(rng.uniform(0, 500, (9, 9)))
    for _ in range(10):
        xs, ys = rng.uniform(0, 8, 4), rng.uniform(0, 8, 4)
        dl, dt, dh = drape_polyline(lat, xs, ys, thin=False)
        assert _worst_dip(lat, dl, dt, dh) < 1e-6


def test_thinning_drops_every_breakpoint_on_flat_or_valley_ground():
    """Along a flat or concave profile no breakpoint is needed — which is the
    whole river network, since rivers run along valley floors."""
    lat = _lattice(np.zeros((6, 6)))
    dl, _, _ = drape_polyline(lat, [0.2, 4.8], [0.3, 4.1])
    assert len(dl) == 2
    valley = _lattice([[abs(i - 3) * 100.0 for i in range(7)] for _ in range(5)])
    dl, _, _ = drape_polyline(valley, [3.0, 3.0], [0.0, 4.0])   # along the floor
    assert len(dl) == 2


def test_thinning_keeps_the_breakpoint_on_a_ridge():
    """Crossing a ridge the chord would tunnel through it, so the crest stays."""
    ridge = _lattice([[500.0 if i == 3 else 0.0 for i in range(7)] for _ in range(3)])
    dl, dt, dh = drape_polyline(ridge, [0.5, 5.5], [1.0, 1.0])
    assert any(abs(x - 3.0) < 1e-9 for x in dl)
    assert _worst_dip(ridge, dl, dt, dh) < 1e-6
    assert len(dl) < len(drape_polyline(ridge, [0.5, 5.5], [1.0, 1.0], thin=False)[0])


def test_simplify_keeps_endpoints_and_real_corners():
    from glyphviz_core.terrain import simplify_polyline
    lon0, lat0 = -117.0, 33.0
    deg = 1 / 111_320.0                         # ~1 m of latitude
    lons = [lon0, lon0, lon0, lon0 + 500 * deg / math.cos(math.radians(33))]
    lats = [lat0, lat0 + 100 * deg, lat0 + 200 * deg + 3 * deg * 0, lat0 + 200 * deg]
    # insert a 3 m wiggle on a straight run, and a genuine 500 m corner
    lats[1] += 0.0
    lons[1] += 3 * deg / math.cos(math.radians(33))
    sl, st = simplify_polyline(lons, lats, tolerance_m=10.0)
    assert (sl[0], st[0]) == (lons[0], lats[0])
    assert (sl[-1], st[-1]) == (lons[-1], lats[-1])
    assert len(sl) == 3                          # wiggle gone, corner kept
    ring_l, ring_t = simplify_polyline([0, 1, 1, 0, 0], [0, 0, 1, 1, 0], 1.0)
    assert (ring_l[0], ring_t[0]) == (ring_l[-1], ring_t[-1])


def test_empty_polyline():
    lat = _lattice(np.zeros((3, 3)))
    dl, dt, dh = drape_polyline(lat, [], [])
    assert len(dl) == len(dt) == len(dh) == 0
