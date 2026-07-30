"""
Basemap (Fetch Basemap) unit tests — no network, no Qt.

The contract (see glyphviz_core/basemap.py): a lon/lat bounding box plans and
builds a plate-carrée PNG whose coverage exactly matches the grid extents it
will be paired with. Under test, with an injected fake tile fetcher:

  * bbox derivation from a grid's DIRECT children (descendants place relative
    to their parents, so they must not contribute), with padding and the
    Mercator ±85.05° latitude clamp;
  * zoom selection: resolution targets ~target_px width, then backs off until
    the tile count fits the cap (politeness toward public tile servers);
  * the Web Mercator → equirectangular reprojection, verified numerically by
    encoding each tile pixel's global position in its color channels;
  * the on-disk tile cache: a rebuilt map re-fetches nothing;
  * failures surface as BasemapError, and no partial output file is written.
"""
import io
import math

import numpy as np
import pytest
from PIL import Image

from glyphviz_core.basemap import (
    DEFAULT_PROVIDER, MERCATOR_LAT_LIMIT, PROVIDERS, TILE_SIZE, BasemapError,
    BBox, bbox_from_nodes, build_basemap, plan_basemap,
)
from glyphviz_core.node import NODE_TYPE_GRID, Node


def _node(id, parent_id=0, tx=0.0, ty=0.0, type=5):
    return Node(id=id, type=type, parent_id=parent_id, branch_level=1,
                translate_x=tx, translate_y=ty, translate_z=0.0,
                rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
                scale_x=1.0, scale_y=1.0, scale_z=1.0,
                color_r=0, color_g=0, color_b=0, color_a=255,
                geometry=7, hide=0, topo=0)


# --- BBox / bbox_from_nodes --------------------------------------------------

def test_bbox_validate_rejects_inverted_and_antimeridian():
    with pytest.raises(BasemapError):
        BBox(10, 10, 0, 5).validate()
    with pytest.raises(BasemapError):
        BBox(0, 10, 8, 3).validate()
    with pytest.raises(BasemapError):
        BBox(170, 190, 0, 10).validate()   # dateline crossing unsupported in V1


def test_bbox_clamped_to_mercator_limits():
    b = BBox(-200, 200, -90, 90).clamped()
    assert (b.lon_min, b.lon_max) == (-180, 180)
    assert b.lat_min == -MERCATOR_LAT_LIMIT and b.lat_max == MERCATOR_LAT_LIMIT


def test_bbox_from_nodes_direct_children_only_with_padding():
    grid = _node(1, type=NODE_TYPE_GRID)
    kids = [_node(2, parent_id=1, tx=-120, ty=30),
            _node(3, parent_id=1, tx=-110, ty=40)]
    grandkid = _node(4, parent_id=2, tx=999, ty=999)   # relative — must not count
    stranger = _node(5, parent_id=0, tx=50, ty=50)
    b = bbox_from_nodes([grid, *kids, grandkid, stranger], grid_id=1)
    assert -120.5 <= b.lon_min < -120 and -110 < b.lon_max <= -109.5
    assert 29.5 <= b.lat_min < 30 and 40 < b.lat_max <= 40.5


def test_bbox_from_nodes_single_point_gets_a_real_window():
    grid = _node(1, type=NODE_TYPE_GRID)
    kid = _node(2, parent_id=1, tx=-117.16, ty=32.72)
    b = bbox_from_nodes([grid, kid], grid_id=1)
    b.validate()   # non-degenerate despite a zero-span dataset
    assert b.lon_max - b.lon_min >= 1.0 and b.lat_max - b.lat_min >= 1.0


def test_bbox_from_nodes_no_children_is_none():
    assert bbox_from_nodes([_node(1, type=NODE_TYPE_GRID)], grid_id=1) is None


# --- plan_basemap ------------------------------------------------------------

def test_plan_whole_earth_backs_off_to_tile_cap():
    plan = plan_basemap(BBox(-180, 180, -90, 90), target_px=1536, tile_cap=48)
    # Resolution alone wants zoom 3 (8x8 = 64 tiles); the cap forces zoom 2.
    assert plan.zoom == 2
    assert plan.tile_count <= 48
    assert plan.out_w == 4 * TILE_SIZE


def test_plan_small_region_balances_resolution_against_cap():
    plan = plan_basemap(BBox(-118, -116, 32, 34), target_px=1536)
    # Resolution alone wants zoom 11 (~160 tiles); the default cap backs off
    # to zoom 10 — 7x8 = 56 tiles, 1456 px wide. The cap always wins.
    assert plan.zoom == 10
    assert plan.tile_count <= 60
    assert plan.out_w >= 1024
    # Square pixels in degree space: 2° x 2° window → square output.
    assert abs(plan.out_h - plan.out_w) <= 1


def test_plan_output_aspect_matches_degree_aspect():
    plan = plan_basemap(BBox(-125, -66, 24, 49))
    assert plan.out_h / plan.out_w == pytest.approx(25 / 59, abs=0.01)


def test_plan_unknown_provider_raises():
    with pytest.raises(BasemapError):
        plan_basemap(BBox(0, 10, 0, 10), provider_key="nope")


def test_plan_max_zoom_respected_for_tiny_bbox():
    plan = plan_basemap(BBox(0, 0.001, 0, 0.001))
    assert plan.zoom <= PROVIDERS[DEFAULT_PROVIDER].max_zoom


# --- build_basemap: fake tile server ----------------------------------------

def _tile_png(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


def _parse_tile_url(url: str) -> tuple[int, int, int]:
    z, x, y = url.rstrip(".png").split("/")[-3:]
    return int(z), int(x), int(y)


def _row_encoding_fetch(calls: list):
    """Each pixel encodes its GLOBAL Mercator y: red = tile y index,
    green = row within the tile. Valid for zooms <= 8 (ty <= 255)."""
    def fetch(url: str) -> bytes:
        calls.append(url)
        _z, _x, y = _parse_tile_url(url)
        arr = np.zeros((TILE_SIZE, TILE_SIZE, 3), dtype=np.uint8)
        arr[:, :, 0] = y
        arr[:, :, 1] = np.arange(TILE_SIZE, dtype=np.uint8)[:, None]
        return _tile_png(arr)
    return fetch


def _col_encoding_fetch():
    """Each pixel encodes its GLOBAL x: red = tile x index, green = column."""
    def fetch(url: str) -> bytes:
        _z, x, _y = _parse_tile_url(url)
        arr = np.zeros((TILE_SIZE, TILE_SIZE, 3), dtype=np.uint8)
        arr[:, :, 0] = x
        arr[:, :, 1] = np.arange(TILE_SIZE, dtype=np.uint8)[None, :]
        return _tile_png(arr)
    return fetch


def _merc_y_px(lat_deg: float, zoom: int) -> float:
    n_px = (1 << zoom) * TILE_SIZE
    return (1.0 - math.asinh(math.tan(math.radians(lat_deg))) / math.pi) / 2.0 * n_px


def test_reprojection_rows_are_mercator_correct(tmp_path):
    """The core correctness test: output row i (linear in latitude) must have
    been sampled from the Mercator source row for that latitude, within 1 px.
    A plain crop (no reprojection) would be off by ~40 rows mid-image here."""
    bbox = BBox(-125, -66, 24, 49)   # contiguous US: strong Mercator stretch
    plan = plan_basemap(bbox, target_px=512, tile_cap=48)
    out = build_basemap(plan, tmp_path / "map.png",
                        fetch=_row_encoding_fetch([]), cache_dir=tmp_path / "cache")
    arr = np.asarray(Image.open(out).convert("RGB"))
    assert arr.shape == (plan.out_h, plan.out_w, 3)
    lats = np.linspace(bbox.lat_max, bbox.lat_min, plan.out_h)
    # Column 0 stays clear of the bottom-right attribution stamp.
    got = arr[:, 0, 0].astype(np.int64) * TILE_SIZE + arr[:, 0, 1]
    expect = np.array([_merc_y_px(lat, plan.zoom) for lat in lats])
    assert np.max(np.abs(got - expect)) <= 1.0
    # And it must NOT be a plain linear crop: nonlinearity visible mid-image.
    linear = np.linspace(expect[0], expect[-1], plan.out_h)
    assert np.max(np.abs(expect - linear)) > 10


def test_reprojection_columns_are_linear_lon_crop(tmp_path):
    bbox = BBox(-125, -66, 24, 49)
    plan = plan_basemap(bbox, target_px=512, tile_cap=48)
    out = build_basemap(plan, tmp_path / "map.png",
                        fetch=_col_encoding_fetch(), cache_dir=tmp_path / "cache")
    arr = np.asarray(Image.open(out).convert("RGB"))
    n_px = (1 << plan.zoom) * TILE_SIZE
    left = round((bbox.lon_min + 180.0) / 360.0 * n_px)
    got = arr[0, :, 0].astype(np.int64) * TILE_SIZE + arr[0, :, 1]   # top row: no stamp
    expect = left + np.arange(plan.out_w)
    assert np.array_equal(got, expect)


def test_tile_cache_prevents_refetch(tmp_path):
    plan = plan_basemap(BBox(-118, -116, 32, 34), target_px=512, tile_cap=48)
    calls = []
    fetch = _row_encoding_fetch(calls)
    build_basemap(plan, tmp_path / "a.png", fetch=fetch, cache_dir=tmp_path / "cache")
    first = len(calls)
    assert first == plan.tile_count
    build_basemap(plan, tmp_path / "b.png", fetch=fetch, cache_dir=tmp_path / "cache")
    assert len(calls) == first   # every tile served from disk


def test_fetch_failure_raises_and_writes_nothing(tmp_path):
    plan = plan_basemap(BBox(-118, -116, 32, 34), target_px=512, tile_cap=48)

    def broken(url):
        raise OSError("offline")

    out = tmp_path / "map.png"
    with pytest.raises(BasemapError):
        build_basemap(plan, out, fetch=broken, cache_dir=tmp_path / "cache")
    assert not out.exists()


def test_progress_callback_counts_every_tile(tmp_path):
    plan = plan_basemap(BBox(-118, -116, 32, 34), target_px=512, tile_cap=48)
    seen = []
    build_basemap(plan, tmp_path / "map.png", fetch=_row_encoding_fetch([]),
                  cache_dir=tmp_path / "cache",
                  progress=lambda done, total: seen.append((done, total)))
    assert seen == [(i + 1, plan.tile_count) for i in range(plan.tile_count)]
