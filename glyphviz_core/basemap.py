"""Fetch web-map imagery for a lon/lat bounding box as a World Grid texture.

This module is deliberately Qt-free: the Fetch Basemap dialog hands it a
bounding box and gets back a plate-carrée PNG whose coverage exactly matches
the grid extents it should be paired with. All the interesting work — zoom
selection under a tile-count cap, slippy-tile math, the Web Mercator →
equirectangular reprojection, attribution stamping, on-disk tile caching —
lives here so it can be tested headlessly with an injected fetcher, no
network and no GL context.

Why reprojection is mandatory: tile servers serve Web Mercator (EPSG:3857),
but a World Grid maps its texture *linearly* in latitude across the extents
window (plate carrée). Skipping the resample would visibly misplace glyphs
at mid/high latitudes — tens of pixels for a region like the contiguous US.
Longitude is linear in both projections, so only rows are resampled.

Provider etiquette is designed in, not bolted on: an identifying User-Agent,
a hard cap on tiles per request, and a per-tile disk cache so bbox tweaks
and refetches never re-hit the server. Attribution is baked into the image
corner so it travels with the saved scene.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

TILE_SIZE = 256
# Web Mercator's latitude of validity; also the pole of tile y = 0 / y = n-1.
MERCATOR_LAT_LIMIT = 85.0511287798066

USER_AGENT = "GlyphViz/1.0 (desktop data-visualization app; basemap fetch)"
FETCH_TIMEOUT_S = 20

# Defaults for plan_basemap. ~1536 px across reads crisply on a fullscreen
# plate; 60 tiles (a worst-case fetch around 1.5 MB, well inside the OSM tile
# usage policy's idea of polite) is the smallest cap that lets a square
# regional bbox reach that width — ~6 full tiles across plus partial-tile
# overhang on both axes.
DEFAULT_TARGET_PX = 1536
DEFAULT_TILE_CAP = 60


class BasemapError(Exception):
    """Anything that should surface to the user as a message, not a traceback."""


@dataclass(frozen=True)
class Provider:
    key: str
    label: str
    url_template: str          # {z}/{x}/{y} placeholders
    attribution: str
    max_zoom: int


# Key-free providers only; adding a key-requiring one (Mapbox etc.) is a new
# entry plus whatever auth its template needs.
PROVIDERS: dict[str, Provider] = {
    "osm": Provider(
        key="osm",
        label="OpenStreetMap (streets)",
        url_template="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        attribution="© OpenStreetMap contributors",
        max_zoom=19,
    ),
    "esri_imagery": Provider(
        key="esri_imagery",
        label="Esri World Imagery (satellite)",
        url_template=("https://server.arcgisonline.com/ArcGIS/rest/services/"
                      "World_Imagery/MapServer/tile/{z}/{y}/{x}"),
        attribution="Imagery © Esri, Maxar, Earthstar Geographics",
        max_zoom=19,
    ),
    "opentopomap": Provider(
        key="opentopomap",
        label="OpenTopoMap (terrain)",
        url_template="https://tile.opentopomap.org/{z}/{x}/{y}.png",
        attribution="© OpenStreetMap contributors, SRTM | © OpenTopoMap (CC-BY-SA)",
        max_zoom=17,
    ),
}
DEFAULT_PROVIDER = "osm"


@dataclass(frozen=True)
class BBox:
    lon_min: float
    lon_max: float
    lat_min: float
    lat_max: float

    def padded(self, frac: float) -> "BBox":
        """Grow each axis by *frac* of its span (degenerate spans get a
        half-degree cushion so a single-point dataset still yields a map)."""
        lon_pad = max((self.lon_max - self.lon_min) * frac, 0.5)
        lat_pad = max((self.lat_max - self.lat_min) * frac, 0.5)
        return BBox(self.lon_min - lon_pad, self.lon_max + lon_pad,
                    self.lat_min - lat_pad, self.lat_max + lat_pad)

    def clamped(self) -> "BBox":
        return BBox(max(self.lon_min, -180.0), min(self.lon_max, 180.0),
                    max(self.lat_min, -MERCATOR_LAT_LIMIT),
                    min(self.lat_max, MERCATOR_LAT_LIMIT))

    def validate(self):
        if not all(map(math.isfinite,
                       (self.lon_min, self.lon_max, self.lat_min, self.lat_max))):
            raise BasemapError("Bounding box has non-finite values.")
        if self.lon_max <= self.lon_min or self.lat_max <= self.lat_min:
            raise BasemapError("Bounding box max must exceed min on each axis.")
        if self.lon_min < -180.0 or self.lon_max > 180.0:
            raise BasemapError(
                "Longitude window must lie within -180..180 "
                "(antimeridian-crossing regions aren't supported yet).")


def bbox_from_nodes(nodes, grid_id: int, pad_frac: float = 0.05) -> BBox | None:
    """Bounding box of a grid's direct children's lon/lat (translate_x/y),
    padded — the numbers the Fetch Basemap dialog prefills. Descendants
    deeper than the direct children place relative to them, so they don't
    contribute. Returns None when the grid has no children."""
    lons = [n.translate_x for n in nodes if n.parent_id == grid_id]
    lats = [n.translate_y for n in nodes if n.parent_id == grid_id]
    if not lons:
        return None
    return BBox(min(lons), max(lons), min(lats), max(lats)).padded(pad_frac).clamped()


# --- slippy-tile math --------------------------------------------------------

def _merc_y_norm(lat_deg: float) -> float:
    """Latitude → normalized Web Mercator y in 0..1 (0 = north edge)."""
    lat = math.radians(lat_deg)
    return (1.0 - math.asinh(math.tan(lat)) / math.pi) / 2.0


def _lon_x_norm(lon_deg: float) -> float:
    """Longitude → normalized x in 0..1 (0 = -180)."""
    return (lon_deg + 180.0) / 360.0


@dataclass(frozen=True)
class BasemapPlan:
    """Everything a fetch will do, computable without touching the network —
    the dialog previews these numbers live as the bbox is edited."""
    provider: Provider
    bbox: BBox                 # exact coverage; pair the grid extents with THIS
    zoom: int
    tx_min: int
    tx_max: int
    ty_min: int
    ty_max: int
    out_w: int
    out_h: int

    @property
    def tile_count(self) -> int:
        return (self.tx_max - self.tx_min + 1) * (self.ty_max - self.ty_min + 1)


def plan_basemap(bbox: BBox, provider_key: str = DEFAULT_PROVIDER,
                 target_px: int = DEFAULT_TARGET_PX,
                 tile_cap: int = DEFAULT_TILE_CAP) -> BasemapPlan:
    """Pick the zoom level and tile range for *bbox*: the smallest zoom whose
    output is at least ~target_px wide, backed off until the tile count fits
    under *tile_cap* (zoom 0 is a single tile, so a plan always exists)."""
    provider = PROVIDERS.get(provider_key)
    if provider is None:
        raise BasemapError(f"Unknown basemap provider: {provider_key!r}")
    bbox = bbox.clamped()
    bbox.validate()

    def tiles_at(z: int) -> tuple[int, int, int, int]:
        n = 1 << z
        tx_min = min(int(_lon_x_norm(bbox.lon_min) * n), n - 1)
        tx_max = min(int(_lon_x_norm(bbox.lon_max) * n), n - 1)
        ty_min = min(int(_merc_y_norm(bbox.lat_max) * n), n - 1)  # north edge
        ty_max = min(int(_merc_y_norm(bbox.lat_min) * n), n - 1)
        return tx_min, tx_max, ty_min, ty_max

    def width_px(z: int) -> float:
        return (bbox.lon_max - bbox.lon_min) / 360.0 * (1 << z) * TILE_SIZE

    zoom = provider.max_zoom
    for z in range(provider.max_zoom + 1):
        if width_px(z) >= target_px:
            zoom = z
            break
    while zoom > 0:
        tx_min, tx_max, ty_min, ty_max = tiles_at(zoom)
        if (tx_max - tx_min + 1) * (ty_max - ty_min + 1) <= tile_cap:
            break
        zoom -= 1
    tx_min, tx_max, ty_min, ty_max = tiles_at(zoom)

    out_w = max(int(round(width_px(zoom))), 1)
    # Square pixels in degree space: the grid drapes the texture linearly in
    # lon and lat, so matching the window's degree aspect keeps it undistorted.
    out_h = max(int(round(out_w * (bbox.lat_max - bbox.lat_min)
                          / (bbox.lon_max - bbox.lon_min))), 1)
    return BasemapPlan(provider=provider, bbox=bbox, zoom=zoom,
                       tx_min=tx_min, tx_max=tx_max,
                       ty_min=ty_min, ty_max=ty_max,
                       out_w=out_w, out_h=out_h)


# --- fetching ----------------------------------------------------------------

def default_cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".cache")
    return Path(base) / "GlyphViz" / "tile_cache"


def _default_fetch(url: str) -> bytes:
    import requests
    resp = requests.get(url, headers={"User-Agent": USER_AGENT},
                        timeout=FETCH_TIMEOUT_S)
    resp.raise_for_status()
    return resp.content


def _get_tile_bytes(provider: Provider, z: int, x: int, y: int,
                    cache_dir: Path, fetch) -> bytes:
    cached = cache_dir / provider.key / str(z) / str(x) / f"{y}.png"
    if cached.is_file():
        return cached.read_bytes()
    url = provider.url_template.format(z=z, x=x, y=y)
    try:
        data = fetch(url)
    except Exception as exc:
        raise BasemapError(f"Tile fetch failed ({url}): {exc}") from exc
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(data)
    return data


# --- stitch + reproject ------------------------------------------------------

def build_basemap(plan: BasemapPlan, out_path: Path,
                  fetch=None, cache_dir: Path | None = None,
                  progress=None) -> Path:
    """Fetch the plan's tiles, stitch, reproject Mercator → plate carrée,
    stamp attribution, and write a PNG to *out_path*. *fetch* is
    url → bytes (tests inject a fake; default uses requests); *progress* is
    an optional callable(done_tiles, total_tiles)."""
    import io

    from PIL import Image

    if fetch is None:
        fetch = _default_fetch
    if cache_dir is None:
        cache_dir = default_cache_dir()

    n_x = plan.tx_max - plan.tx_min + 1
    n_y = plan.ty_max - plan.ty_min + 1
    canvas = np.zeros((n_y * TILE_SIZE, n_x * TILE_SIZE, 3), dtype=np.uint8)
    done = 0
    for ty in range(plan.ty_min, plan.ty_max + 1):
        for tx in range(plan.tx_min, plan.tx_max + 1):
            data = _get_tile_bytes(plan.provider, plan.zoom, tx, ty,
                                   cache_dir, fetch)
            try:
                tile = Image.open(io.BytesIO(data)).convert("RGB")
            except Exception as exc:
                raise BasemapError(
                    f"Tile {plan.zoom}/{tx}/{ty} is not a readable image: {exc}"
                ) from exc
            if tile.size != (TILE_SIZE, TILE_SIZE):
                tile = tile.resize((TILE_SIZE, TILE_SIZE))
            row = (ty - plan.ty_min) * TILE_SIZE
            col = (tx - plan.tx_min) * TILE_SIZE
            canvas[row:row + TILE_SIZE, col:col + TILE_SIZE] = np.asarray(tile)
            done += 1
            if progress is not None:
                progress(done, plan.tile_count)

    out = _reproject_to_equirect(canvas, plan)
    img = Image.fromarray(out)
    _stamp_attribution(img, plan.provider.attribution)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG")
    return out_path


def _reproject_to_equirect(canvas: np.ndarray, plan: BasemapPlan) -> np.ndarray:
    """Crop the stitched Mercator canvas to the bbox and resample its rows so
    latitude becomes linear (columns are already linear in longitude)."""
    n_px = (1 << plan.zoom) * TILE_SIZE     # world size in pixels at this zoom
    x0 = plan.tx_min * TILE_SIZE            # canvas origin in world pixels
    y0 = plan.ty_min * TILE_SIZE
    bbox = plan.bbox

    left = int(round(_lon_x_norm(bbox.lon_min) * n_px)) - x0
    left = min(max(left, 0), canvas.shape[1] - 1)
    right = min(left + plan.out_w, canvas.shape[1])

    # Output row i sits at a linearly spaced latitude (north → south, matching
    # image row order); gather its nearest Mercator source row in one take.
    lats = np.linspace(bbox.lat_max, bbox.lat_min, plan.out_h)
    merc = (1.0 - np.arcsinh(np.tan(np.radians(lats))) / np.pi) / 2.0
    rows = np.rint(merc * n_px - y0).astype(np.int64)
    rows = np.clip(rows, 0, canvas.shape[0] - 1)
    return np.ascontiguousarray(canvas[rows][:, left:right])


def _stamp_attribution(img, text: str):
    """Bake the provider's required attribution into the bottom-right corner
    (a translucent strip keeps it legible on any map style)."""
    from PIL import Image, ImageDraw, ImageFont

    try:
        font = ImageFont.load_default(size=max(11, img.height // 90))
    except TypeError:   # older Pillow: fixed-size bitmap font
        font = ImageFont.load_default()
    draw = ImageDraw.Draw(img, "RGBA")
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    pad = 4
    w, h = (r - l) + 2 * pad, (b - t) + 2 * pad
    x, y = img.width - w, img.height - h
    draw.rectangle((x, y, img.width, img.height), fill=(0, 0, 0, 140))
    draw.text((x + pad - l, y + pad - t), text, font=font, fill=(255, 255, 255, 230))
