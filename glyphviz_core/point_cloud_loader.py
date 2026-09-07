"""
Importer for external point-cloud files — LIDAR and friends — into a
GlyphViz Point Cloud scene (TOPO_POINTCLOUD, see point_cloud.py).

Pure data/numpy: no OpenGL, no Qt, so this module is safe to import from
anything, including a future non-GL presentation layer. Same shape as
mesh_loader.py and pdb_loader.py.

FORMATS, AND WHY THEY ARE ALL OPEN
----------------------------------
LAS is binary but it is not proprietary: it is a published ASPRS
specification (1.0 through 1.4, the spec itself at github.com/ASPRSorg/LAS),
and LAZ — its lossless compressed form — became an OGC Community Standard in
September 2026. We read both through `laspy` (BSD-2-Clause, pure Python) with
the `lazrs` LAZ codec (MIT, Rust). Neither carries the LGPL that the original
LASzip library does, which is what makes them safe to bundle.

  .las .laz   laspy            — the LIDAR interchange formats
  .ply        trimesh          — already a dependency; point-only PLY is fine
  .xyz .pts .txt .csv          — whitespace/comma ASCII, parsed here

E57 is deliberately absent: it is an open ASTM standard, but reading it needs
libE57Format via pye57, which is a native dependency this project does not
have. Convert to LAS or PLY first.

WHAT AN IMPORT HAS TO GET RIGHT
-------------------------------
Three things, none of them the file parsing:

1. **Coordinates.** A georeferenced scan arrives in CRS units with enormous
   offsets — the Autzen Stadium test file this was built against runs
   635,577..639,003 easting in Oregon State Plane feet. Dropped into a scene
   as-is it is a speck 800,000 units from the origin. `fit_to_world` recenters
   it and scales it to a sane span.

2. **Colour.** Most public LIDAR has no RGB at all. Classification codes and
   elevation are what make such a file readable, so both are first-class
   colour modes rather than fallbacks.

3. **Count.** GlyphViz gives every point a real Node -- clickable, taggable,
   animatable. That is the feature, and it is also the ceiling: about 2 KB
   resident each, and about 550 bytes on disk once save_node_csv writes its
   94-column ANTz-compatible row. Measured: 100,000 points is a 55 MB scene
   that saves in 3.4 s and reopens in 1.8 s; 442,767 points is 244 MB, 15 s
   and 9 s. Importing is far cheaper than saving -- 442k points come out of a
   compressed LAZ in 4 s and render at ~400 fps -- so it is the SAVED scene
   that sets the budget. A 10M-point tile must be decimated, and the
   decimation has to be honest about it.
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .geometry_data import GEO_POINT, GEO_SPHERE
from .node import Node, ROTATION_MODE_EULER_XYZ
from .topology import TOPO_POINTCLOUD

LAS_EXTENSIONS = ('.las', '.laz')
ASCII_EXTENSIONS = ('.xyz', '.pts', '.txt')
SUPPORTED_EXTENSIONS = LAS_EXTENSIONS + ('.ply',) + ASCII_EXTENSIONS

# How many points a scene can carry comfortably. Not a renderer limit --
# measured, the renderer replays 1M points in 0.63 ms/frame and a 442,767-point
# import runs at ~400 fps -- but a Node limit, and mostly a DISK one, because
# save_node_csv writes the full 94-column ANTz row for every point: at 100k the
# saved scene is 55 MB (3.4 s to save, 1.8 s to reopen, ~200 MB resident); at
# 442k it is 244 MB (15 s / 9 s). Importing is far cheaper than saving.
# See point_cloud.py's module docstring.
DEFAULT_MAX_POINTS = 100_000

# Default world-space span for the LARGER horizontal axis of an imported
# scan. 360 is GlyphViz's own 1:1 reference frame -- the width of a default
# World Grid, and of a full sweep of longitude -- so an imported scan lands
# at the same scale as everything else in the app and can be dropped onto a
# grid without retuning.
DEFAULT_WORLD_SPAN = 360.0

# Center and scale are measured from this percentile box rather than the raw
# min/max. Airborne LIDAR reliably contains a handful of gross outliers
# (birds, cloud returns, multipath), and one point a kilometre up would
# otherwise shrink the entire scan toward invisibility. At these percentiles
# the box IS the bounding box for clean data, so nothing is distorted when
# there is nothing to reject.
FIT_PERCENTILES = (0.1, 99.9)

# ASPRS standard classification codes (LAS 1.4, table 17) and the colours
# GlyphViz gives them. Ground brown, vegetation greens by height, buildings
# red, water blue -- the convention every LIDAR tool draws, so a classified
# scan reads immediately. Codes outside this table (LAS 1.4 allows 0-255 and
# reserves 64+ for user definition -- the test file uses 64, 65, 66, 68, 73,
# 76, 77) are coloured by hashing the code into a spread of hues, so distinct
# user classes stay visually distinct without pretending to know their names.
ASPRS_CLASSES: dict[int, tuple[str, tuple[int, int, int]]] = {
    0:  ("Created, never classified", (150, 150, 150)),
    1:  ("Unclassified",              (170, 170, 175)),
    2:  ("Ground",                    (166, 124,  82)),
    3:  ("Low Vegetation",            (120, 170,  90)),
    4:  ("Medium Vegetation",         ( 70, 150,  70)),
    5:  ("High Vegetation",           ( 34, 110,  50)),
    6:  ("Building",                  (200,  80,  70)),
    7:  ("Low Point (noise)",         (110,  60, 120)),
    8:  ("Reserved",                  (140, 140, 140)),
    9:  ("Water",                     ( 60, 130, 210)),
    10: ("Rail",                      (180, 140,  60)),
    11: ("Road Surface",              (110, 110, 120)),
    12: ("Reserved",                  (140, 140, 140)),
    13: ("Wire - Guard",              (230, 200,  90)),
    14: ("Wire - Conductor",          (240, 220, 120)),
    15: ("Transmission Tower",        (220, 160,  60)),
    16: ("Wire-structure Connector",  (230, 190, 110)),
    17: ("Bridge Deck",               (190, 120, 160)),
    18: ("High Noise",                (140,  70, 140)),
}

# How many class names the cloud parent's provenance label spells out before
# it summarizes. Four fits a readable label; a real classified tile routinely
# carries a dozen or more.
_LABEL_CLASS_LIMIT = 4

COLOR_MODES = ('auto', 'rgb', 'classification', 'elevation', 'intensity')
DECIMATE_METHODS = ('random', 'stride', 'voxel')


@dataclass
class PointCloudData:
    """One imported cloud, still in its SOURCE coordinate system.

    Keeping source coordinates until `fit_to_world` runs is deliberate: the
    caller needs the real extents to show the user what they are about to
    import ("3426 x 4656 x 209 units"), and a scale chosen before the user
    has seen that number is a guess.
    """
    name: str
    points: np.ndarray                    # (N, 3) float64, source units
    colors: np.ndarray | None = None      # (N, 3) uint8, if the file had RGB
    classification: np.ndarray | None = None   # (N,) uint8
    intensity: np.ndarray | None = None        # (N,) uint16
    source_path: str = ""
    total_points: int = 0                 # how many were in the FILE
    # How many survived the classification filter, before decimation. Equal
    # to total_points when no filter was applied. Kept separate so an import
    # can report "50,000 of 3.7M matching points (10.6M in the file)" --
    # collapsing the two would make a filtered import look like it lost data.
    available_points: int = 0
    crs: str = ""                         # only when it could be read cheaply

    def __len__(self) -> int:
        return int(self.points.shape[0])

    def extents(self) -> tuple[np.ndarray, np.ndarray]:
        return self.points.min(axis=0), self.points.max(axis=0)

    def span(self) -> np.ndarray:
        lo, hi = self.extents()
        return hi - lo

    def class_counts(self) -> dict[int, int]:
        if self.classification is None:
            return {}
        codes, counts = np.unique(self.classification, return_counts=True)
        return {int(c): int(n) for c, n in zip(codes, counts)}


# --------------------------------------------------------------- readers ---

def _read_las(path: str, max_points: int | None, method: str, seed: int,
              keep_classes=None) -> PointCloudData:
    """LAS/LAZ via laspy.

    Decimation happens HERE rather than after loading, because a 10M-point
    tile is ~250 MB of float64 xyz alone and the caller only ever wants ~100k
    of it. laspy still has to decompress every point (LAZ is a sequential
    codec), but it does not have to hand us 10M rows of every attribute.

    The classification filter is applied BEFORE the decimation, and the
    ordering is the whole reason it lives down here rather than in
    build_nodes. Ask for 100k points and then drop ground -- which is most of
    an aerial tile -- and filtering second would quietly hand back 35k. The
    user asked for 100k points OF THE CLASSES THEY CHOSE, so the sample is
    drawn from the filtered set.
    """
    try:
        import laspy
    except ImportError as exc:                          # pragma: no cover
        raise ImportError(
            "Reading LAS/LAZ needs laspy. Install it with:\n"
            "    pip install laspy[lazrs]\n"
            f"(original error: {exc})"
        ) from exc

    las = laspy.read(path)
    total = len(las.points)
    dims_all = {d.name.lower() for d in las.point_format.dimensions}

    subset = None
    if keep_classes is not None and 'classification' in dims_all:
        wanted = np.asarray(sorted(int(c) for c in keep_classes))
        subset = np.flatnonzero(np.isin(np.asarray(las.classification), wanted))
    available = total if subset is None else int(subset.size)

    # Voxel sampling needs the coordinates to bucket, so gather them up
    # front for that method only. It costs a transient (available x 3)
    # float64 -- 255 MB on the 10.6M-point test tile, on top of the point
    # record laspy is already holding -- which is why the other two methods,
    # which need only a count, do not pay it.
    coords = None
    if method == 'voxel':
        coords = np.stack([np.asarray(las.x), np.asarray(las.y),
                           np.asarray(las.z)], axis=1)
        if subset is not None:
            coords = coords[subset]

    picked = _decimation_index(available, max_points, method, seed,
                               coords=coords)
    del coords
    keep = picked if subset is None else subset[picked]

    xyz = np.stack([np.asarray(las.x)[keep],
                    np.asarray(las.y)[keep],
                    np.asarray(las.z)[keep]], axis=1).astype(np.float64)

    dims = dims_all

    colors = None
    if {'red', 'green', 'blue'} <= dims:
        rgb = np.stack([np.asarray(las.red)[keep],
                        np.asarray(las.green)[keep],
                        np.asarray(las.blue)[keep]], axis=1)
        if rgb.max(initial=0) > 0:
            # LAS stores colour as 16-bit, but plenty of writers put 8-bit
            # values straight into those fields. Scaling a genuinely 8-bit
            # file by >>8 turns it black, and NOT scaling a 16-bit one turns
            # it white -- so decide from the data, which is the standard
            # heuristic every LAS reader uses.
            colors = ((rgb >> 8) if rgb.max() > 255 else rgb).astype(np.uint8)

    classification = None
    if 'classification' in dims:
        classification = np.asarray(las.classification)[keep].astype(np.uint8)

    intensity = None
    if 'intensity' in dims:
        intensity = np.asarray(las.intensity)[keep].astype(np.uint16)

    # parse_crs() needs pyproj, an OPTIONAL laspy extra this project does not
    # depend on -- so it must never be the thing that fails an import. The CRS
    # is a display nicety; the geometry is already in hand.
    crs = ""
    try:
        parsed = las.header.parse_crs()
        if parsed is not None:
            crs = str(getattr(parsed, 'name', parsed))
    except Exception:                                   # noqa: BLE001
        pass

    return PointCloudData(
        name=Path(path).stem, points=xyz, colors=colors,
        classification=classification, intensity=intensity,
        source_path=str(path), total_points=total,
        available_points=available, crs=crs,
    )


def _read_ply(path: str, max_points: int | None,
              method: str, seed: int) -> PointCloudData:
    """PLY via trimesh, which handles both the point-cloud and the mesh form
    (a mesh's vertices are a perfectly good cloud)."""
    import trimesh

    obj = trimesh.load(path, process=False)
    verts = getattr(obj, 'vertices', None)
    if verts is None or len(verts) == 0:
        raise ValueError(f"No points found in {path!r}")
    verts = np.asarray(verts, dtype=np.float64)

    rgb = None
    for holder in ('colors', 'vertex_colors'):
        vc = getattr(getattr(obj, 'visual', None), holder, None)
        if vc is not None and len(vc) == len(verts):
            rgb = np.asarray(vc)[:, :3].astype(np.uint8)
            break

    total = len(verts)
    keep = _decimation_index(total, max_points, method, seed, coords=verts)
    return PointCloudData(
        name=Path(path).stem, points=verts[keep],
        colors=None if rgb is None else rgb[keep],
        source_path=str(path), total_points=total, available_points=total,
    )


def _read_ascii(path: str, max_points: int | None,
                method: str, seed: int) -> PointCloudData:
    """Whitespace- or comma-separated x y z [r g b] / x y z [intensity].

    Deliberately forgiving: scanners and photogrammetry tools emit this
    format with every combination of delimiter, header line and trailing
    column. Any leading line that does not parse as numbers is treated as a
    header and skipped.
    """
    rows = np.genfromtxt(path, delimiter=None, comments='#',
                         invalid_raise=False, dtype=np.float64)
    if rows.ndim == 1:
        rows = rows.reshape(1, -1)
    if rows.size and np.isnan(rows).all(axis=1).any():
        # a header line (or a comma-delimited file) -- retry on commas
        rows2 = np.genfromtxt(path, delimiter=',', comments='#',
                              invalid_raise=False, dtype=np.float64)
        if rows2.ndim == 1:
            rows2 = rows2.reshape(1, -1)
        if rows2.shape[1] >= 3:
            rows = rows2
        rows = rows[~np.isnan(rows[:, :3]).any(axis=1)]
    if rows.size == 0 or rows.shape[1] < 3:
        raise ValueError(f"No x y z columns found in {path!r}")

    verts = rows[:, :3]
    rgb = None
    if rows.shape[1] >= 6:
        cand = rows[:, 3:6]
        if np.nanmax(cand) <= 1.0 + 1e-9 and np.nanmin(cand) >= 0.0:
            rgb = (cand * 255.0).astype(np.uint8)      # 0..1 floats
        elif np.nanmax(cand) <= 255.0 and np.nanmin(cand) >= 0.0:
            rgb = cand.astype(np.uint8)

    total = len(verts)
    keep = _decimation_index(total, max_points, method, seed, coords=verts)
    return PointCloudData(
        name=Path(path).stem, points=verts[keep],
        colors=None if rgb is None else rgb[keep],
        source_path=str(path), total_points=total, available_points=total,
    )


def load_point_cloud(path: str, max_points: int | None = DEFAULT_MAX_POINTS,
                     method: str = 'random', seed: int = 0,
                     keep_classes=None) -> PointCloudData:
    """Read any supported point-cloud file, decimated to *max_points*.

    `max_points=None` loads everything, which is what a script converting a
    file wants and never what the GUI wants.

    `keep_classes` restricts the import to those ASPRS classification codes,
    and is applied before the decimation so the point budget is spent on the
    classes asked for. Only LAS/LAZ carry classification; it is ignored for
    the other formats.
    """
    ext = Path(path).suffix.lower()
    if ext in LAS_EXTENSIONS:
        return _read_las(path, max_points, method, seed, keep_classes)
    if ext == '.ply':
        return _read_ply(path, max_points, method, seed)
    if ext in ASCII_EXTENSIONS or ext == '.csv':
        return _read_ascii(path, max_points, method, seed)
    raise ValueError(
        f"Unsupported point-cloud format {ext!r}. "
        f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}")


# ------------------------------------------------------------ decimation ---

def _decimation_index(total: int, max_points: int | None, method: str,
                      seed: int, coords: np.ndarray | None) -> np.ndarray:
    """Row indices to keep. Always sorted ascending, so the kept points stay
    in file order and a re-import with the same seed reproduces the scene."""
    if max_points is None or total <= max_points:
        return np.arange(total)

    if method == 'stride':
        # Cheapest, and the one to be careful with: a file written in
        # acquisition order has its rows grouped by flight line, so a stride
        # can beat against the scan pattern and sample stripes rather than
        # the scene. Offered because it is exactly reproducible and needs no
        # RNG; not the default for that reason.
        step = int(np.ceil(total / max_points))
        return np.arange(0, total, step)[:max_points]

    if method == 'voxel':
        if coords is None:
            # Defensive only: every reader now hands coordinates in for this
            # method (_read_las gathers them specially, and the PLY/ASCII
            # readers have them already). It used to fall through here for
            # LAS, which meant the dialog's "Voxel grid" option silently did
            # a random sample on the one format it matters most for -- if a
            # new reader is ever added, give it coords rather than restoring
            # that.
            method = 'random'
        else:
            return _voxel_index(coords, max_points)

    rng = np.random.default_rng(seed)
    return np.sort(rng.choice(total, size=max_points, replace=False))


def _voxel_keys(coords: np.ndarray, lo: np.ndarray, span: np.ndarray,
                size: float) -> np.ndarray | None:
    """One int64 cell id per point, or None when *size* would need more cells
    than an int64 key can hold.

    Flattening (i, j, k) into a single integer is what keeps this affordable:
    np.unique over a 1-D int64 array is a plain sort, while np.unique(...,
    axis=0) over an (N, 3) array sorts structured records and is several times
    slower — the difference between a second and most of a minute on a
    ten-million-point tile.
    """
    cells = (np.ceil(span / max(size, 1e-12)) + 1).astype(np.int64)
    cells = np.maximum(cells, 1)
    if int(cells[0]) * int(cells[1]) * int(cells[2]) > (1 << 62):
        return None
    k = np.floor((coords - lo) / max(size, 1e-12)).astype(np.int64)
    np.clip(k, 0, cells - 1, out=k)
    return (k[:, 0] * cells[1] + k[:, 1]) * cells[2] + k[:, 2]


# Voxel-size search happens on at most this multiple of the target count.
# A uniform random pre-sample scales every local density by the SAME factor,
# so the voxel step still equalizes density afterwards -- but the search runs
# over 1.2M points instead of 10.6M, which is the difference between about a
# second and most of a minute. Only the search is affected; the chosen voxel
# size is then applied to the pre-sampled set, which is already far larger
# than the target.
_VOXEL_SEARCH_FACTOR = 12


def _voxel_index(coords: np.ndarray, max_points: int) -> np.ndarray:
    """One point per occupied voxel, the voxel size solved for so the result
    lands near *max_points*.

    Gives even VOLUMETRIC density: random and stride sampling both preserve
    the scanner's own density bias, so a dense patch under the flight path
    stays dense and a sparse edge stays sparse. Measured on the 10.6M-point
    Autzen tile decimated to 100k, against a 32-cube occupancy grid — voxel
    reaches 85.5% of the cells the full cloud occupies where random reaches
    73.6%, with a density spread (p95/median) of 8.2 against 18.3.

    "Volumetric" is the part worth knowing: the grid is 3-D, so a tall column
    of trees or a building contributes many cells and a patch of bare ground
    contributes one. Relative to a random sample this moves points OFF flat
    ground and ONTO structure, which is usually what you want to look at but
    is not the same as even ground coverage. Costs a sort per search step —
    about 2x a random decimation on that tile — so it is opt-in.

    The search is a geometric bisection on the cube size, keeping the best
    result that does not overshoot. Occupancy is not uniform -- that is the
    entire point of the method -- so the size cannot be solved for directly
    and the first guess (cells spread over the bounding volume) is usually
    several factors out.
    """
    n = len(coords)
    if n <= max_points:
        return np.arange(n)

    # Pre-sample for the search (see _VOXEL_SEARCH_FACTOR). Indices are
    # carried through so the result still points into the caller's array.
    budget = max_points * _VOXEL_SEARCH_FACTOR
    if n > budget:
        rng = np.random.default_rng(0)
        base = np.sort(rng.choice(n, size=budget, replace=False))
        work = coords[base]
    else:
        base, work = None, coords

    lo = work.min(axis=0)
    span = np.maximum(work.max(axis=0) - lo, 1e-9)
    size = float((float(span.prod()) / max(1, max_points)) ** (1.0 / 3.0))
    if not np.isfinite(size) or size <= 0:
        size = float(span.max()) / 64.0

    small, large = size / 1024.0, size * 1024.0   # brackets, in cube size
    best: np.ndarray | None = None
    for _ in range(24):
        keys = _voxel_keys(work, lo, span, size)
        if keys is None:                      # too fine to key -- go coarser
            small = size
            size = float(np.sqrt(size * large))
            continue
        _, first = np.unique(keys, return_index=True)
        count = len(first)
        if count <= max_points:
            if best is None or count > len(best):
                best = np.sort(first)
            if count >= max_points * 0.95:
                break
            large = size                      # too few -- finer voxels
            size = float(np.sqrt(small * size))
        else:
            small = size                      # too many -- coarser voxels
            size = float(np.sqrt(size * large))

    if best is None:                          # pragma: no cover
        # The bisection never found a size that fit. Rather than return a
        # cloud larger than asked for, thin the finest attempt evenly.
        best = np.linspace(0, len(work) - 1, max_points).astype(np.int64)
    return best if base is None else base[best]

# -------------------------------------------------------- world fitting ---

def fit_to_world(points: np.ndarray, span: float = DEFAULT_WORLD_SPAN,
                 exaggeration: float = 1.0,
                 ) -> tuple[np.ndarray, float, np.ndarray]:
    """Recenter and uniformly scale a scan into GlyphViz world units.

    Returns (fitted_points, scale, center) so the caller can report and, if
    it wants, invert the transform — a scan whose real-world scale matters
    should be able to say what one world unit is worth.

    The scale is UNIFORM across all three axes and derived from the larger
    HORIZONTAL extent only. Deriving it from the 3-D extent instead would
    make a tall narrow scan and a flat wide one of the same footprint import
    at different sizes; deriving per-axis would silently stretch the terrain,
    which is the one thing a LIDAR viewer must never do by default.

    `exaggeration` then multiplies Z alone. Vertical exaggeration is standard
    in terrain work — 2-3x is how a 200 m relief over 4 km reads as relief at
    all — but it IS a distortion, so it is an explicit argument with a
    truthful default of 1.0.
    """
    pts = np.asarray(points, dtype=np.float64)
    if pts.size == 0:
        return pts.copy(), 1.0, np.zeros(3)

    lo = np.percentile(pts, FIT_PERCENTILES[0], axis=0)
    hi = np.percentile(pts, FIT_PERCENTILES[1], axis=0)
    center = (lo + hi) / 2.0
    horizontal = float(max(hi[0] - lo[0], hi[1] - lo[1]))
    scale = (span / horizontal) if horizontal > 1e-12 else 1.0

    out = (pts - center) * scale
    if exaggeration != 1.0:
        out[:, 2] *= exaggeration
    return out, scale, center


# ------------------------------------------------------------- colouring ---

def _ramp(values: np.ndarray, lo_rgb, hi_rgb, mid_rgb=None) -> np.ndarray:
    """Normalize *values* to 0..1 over their 2nd..98th percentile and map
    through a two- or three-stop ramp.

    Percentiles rather than min/max because both elevation and intensity have
    long thin tails in real LIDAR — a handful of noise returns at the top of
    the range would compress every real value into the bottom of the ramp and
    the cloud would come out one flat colour.
    """
    v = np.asarray(values, dtype=np.float64)
    lo, hi = np.percentile(v, 2.0), np.percentile(v, 98.0)
    t = np.clip((v - lo) / (hi - lo), 0.0, 1.0) if hi > lo else np.zeros(len(v))
    lo_rgb = np.asarray(lo_rgb, dtype=np.float64)
    hi_rgb = np.asarray(hi_rgb, dtype=np.float64)
    if mid_rgb is None:
        out = lo_rgb + (hi_rgb - lo_rgb) * t[:, None]
    else:
        mid_rgb = np.asarray(mid_rgb, dtype=np.float64)
        a = np.clip(t * 2.0, 0.0, 1.0)[:, None]
        b = np.clip(t * 2.0 - 1.0, 0.0, 1.0)[:, None]
        out = lo_rgb + (mid_rgb - lo_rgb) * a + (hi_rgb - mid_rgb) * b
    return np.clip(out, 0, 255).astype(np.uint8)


def class_color(code: int) -> tuple[int, int, int]:
    """Colour for one ASPRS classification code.

    Codes past the standard table (LAS 1.4 permits 0-255, reserving 64+ for
    user definition) get a hue spread off the code itself: distinct classes
    stay distinct without inventing names for them.
    """
    known = ASPRS_CLASSES.get(int(code))
    if known is not None:
        return known[1]
    h = (int(code) * 47) % 360
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(h / 360.0, 0.55, 0.85)
    return (int(r * 255), int(g * 255), int(b * 255))


def class_name(code: int) -> str:
    known = ASPRS_CLASSES.get(int(code))
    return known[0] if known else f"User class {int(code)}"


def resolve_colors(data: PointCloudData, mode: str = 'auto',
                   fitted_z: np.ndarray | None = None) -> tuple[np.ndarray, str]:
    """(N, 3) uint8 colours for a cloud, plus the mode actually used.

    'auto' is the important one, because it decides what a file that carries
    no colour should look like: RGB when the file has it, else classification
    when the file is genuinely classified, else an elevation ramp. Most public
    LIDAR lands on one of the latter two.

    `fitted_z` lets the elevation ramp run over the post-fit heights; without
    it the source z is used, which gives the same ramp (the fit is affine).
    """
    n = len(data)
    chosen = mode

    if mode == 'auto':
        if data.colors is not None:
            chosen = 'rgb'
        elif data.classification is not None and _is_really_classified(data):
            chosen = 'classification'
        else:
            chosen = 'elevation'

    if chosen == 'rgb':
        if data.colors is None:
            return resolve_colors(data, 'auto', fitted_z)
        return data.colors.astype(np.uint8), 'rgb'

    if chosen == 'classification':
        if data.classification is None:
            return resolve_colors(data, 'elevation', fitted_z)
        out = np.empty((n, 3), dtype=np.uint8)
        for code in np.unique(data.classification):
            out[data.classification == code] = class_color(int(code))
        return out, 'classification'

    if chosen == 'intensity':
        if data.intensity is None:
            return resolve_colors(data, 'elevation', fitted_z)
        return _ramp(data.intensity, (20, 20, 30), (255, 255, 240)), 'intensity'

    z = data.points[:, 2] if fitted_z is None else fitted_z
    # blue -> green -> warm white: the terrain ramp, low to high
    return _ramp(z, (40, 70, 160), (245, 240, 220), (90, 170, 110)), 'elevation'


def _is_really_classified(data: PointCloudData) -> bool:
    """True when classification carries information worth colouring by.

    A file where every point is 0 ("created, never classified") or 1
    ("unclassified") is not classified — it just has the column, which nearly
    every LAS file does. Colouring such a file by class would produce one
    uniform grey cloud and look like a bug.
    """
    codes = set(data.class_counts())
    return bool(codes - {0, 1})


# ---------------------------------------------------------- node building ---

def build_nodes(data: PointCloudData, *, color_mode: str = 'auto',
                span: float = DEFAULT_WORLD_SPAN, exaggeration: float = 1.0,
                point_size: float = 2.0, keep_classes=None,
                start_id: int = 1, parent_translate=(0.0, 0.0, 0.0),
                label_points: bool = False) -> tuple[list[Node], dict]:
    """Turn an imported cloud into a TOPO_POINTCLOUD parent plus one Node per
    point, and report what was done.

    ids run start_id (the parent) then start_id+1.. for the points, so the
    result drops straight into an empty scene or merges into a loaded one.

    `point_size` is in PIXELS and is stored on the PARENT as
    `ratio = size / 20` — the conversion point_cloud.point_size inverts. It
    lives on the parent because fixed-function GL has one point size per draw
    call, and the whole cloud is one call.

    Points get no text by default. GlyphViz's usual rule is that every node
    should carry a label explaining its encoding, and a point cloud is the
    one place that rule inverts: 100k labels is 8 MB of text nobody will ever
    read, and the viewport declines to draw them anyway (see
    Viewport._project_tagged_nodes). The PARENT carries the label instead,
    and it says what the cloud is and how it was made.
    """
    if keep_classes is not None and data.classification is not None:
        mask = np.isin(data.classification, np.asarray(list(keep_classes)))
        data = _subset(data, mask)

    fitted, scale, center = fit_to_world(data.points, span, exaggeration)
    colors, used_mode = resolve_colors(data, color_mode, fitted_z=fitted[:, 2])

    src_span = data.span() if len(data) else np.zeros(3)
    # The parent's label is the cloud's provenance, and it is the ONLY place
    # that record survives: the points carry no text (see the docstring), and
    # a saved scene has no other memory of how it was made. So it names every
    # choice that changed what got imported -- the count, the colouring, the
    # class filter and the exaggeration -- not just the count.
    bits = [f"{len(data):,} points", f"coloured by {used_mode}"]
    if data.total_points > len(data):
        bits.append(f"sampled from {data.total_points:,} in the file")
    if keep_classes:
        # Name the classes that actually SURVIVED, biggest first, capped --
        # a tick list can easily hold fifteen entries (the Autzen test tile
        # has fifteen) and spelling them all out buries the rest of the
        # label. The classes with points in them are the ones that describe
        # the cloud; a ticked class the filter found nothing for does not.
        counts = data.class_counts()
        ranked = sorted(counts.items(), key=lambda kv: -kv[1])
        names = [class_name(c) for c, _ in ranked[:_LABEL_CLASS_LIMIT]]
        more = len(ranked) - len(names)
        bits.append("classes: " + ", ".join(names)
                    + (f" +{more} more" if more > 0 else ""))
    if exaggeration != 1.0:
        bits.append(f"{exaggeration:g}x vertical exaggeration")
    label = f"{data.name} — " + "; ".join(bits)

    parent = Node(
        id=start_id, type=5, parent_id=0, branch_level=0,
        translate_x=float(parent_translate[0]),
        translate_y=float(parent_translate[1]),
        translate_z=float(parent_translate[2]),
        rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=255, color_g=220, color_b=120, color_a=255,
        geometry=GEO_SPHERE, hide=0, topo=TOPO_POINTCLOUD,
        ratio=float(point_size) / 20.0,
        rotation_mode=ROTATION_MODE_EULER_XYZ,
        text=label, show_text=0,
    )

    nodes = [parent]
    nid = start_id + 1
    for i in range(len(data)):
        nodes.append(Node(
            id=nid, type=5, parent_id=start_id, branch_level=1,
            translate_x=float(fitted[i, 0]),
            translate_y=float(fitted[i, 1]),
            translate_z=float(fitted[i, 2]),
            rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
            scale_x=0.1, scale_y=0.1, scale_z=0.1,
            color_r=int(colors[i, 0]), color_g=int(colors[i, 1]),
            color_b=int(colors[i, 2]), color_a=255,
            geometry=GEO_POINT, hide=0, topo=0, ratio=0.1,
            rotation_mode=ROTATION_MODE_EULER_XYZ,
            text=(f"{data.name} point {i}" if label_points else ""),
        ))
        nid += 1

    report = {
        'name': data.name,
        'source': data.source_path,
        'points': len(data),
        'total_points': data.total_points,
        'available_points': data.available_points or data.total_points,
        'color_mode': used_mode,
        'world_scale': scale,
        'source_center': center.tolist(),
        'source_span': src_span.tolist(),
        'world_span': (fitted.max(axis=0) - fitted.min(axis=0)).tolist()
                      if len(data) else [0.0, 0.0, 0.0],
        'exaggeration': exaggeration,
        'kept_classes': None if not keep_classes else sorted(int(c) for c in keep_classes),
        'crs': data.crs,
        'classes': {int(c): (class_name(c), n)
                    for c, n in data.class_counts().items()},
    }
    return nodes, report


def _subset(data: PointCloudData, mask: np.ndarray) -> PointCloudData:
    """A PointCloudData holding only the masked points. total_points is
    deliberately preserved: it means "how many were in the file", which is
    what the import report needs to be honest about what was dropped."""
    return PointCloudData(
        name=data.name,
        points=data.points[mask],
        colors=None if data.colors is None else data.colors[mask],
        classification=(None if data.classification is None
                        else data.classification[mask]),
        intensity=None if data.intensity is None else data.intensity[mask],
        source_path=data.source_path,
        total_points=data.total_points,
        available_points=data.available_points,
        crs=data.crs,
    )


def import_to_nodes(path: str, *, max_points: int | None = DEFAULT_MAX_POINTS,
                    method: str = 'random', seed: int = 0,
                    keep_classes=None,
                    **build_kwargs) -> tuple[list[Node], dict]:
    """Read a point-cloud file and return scene-ready nodes. The one call the
    GUI and any script both go through.

    keep_classes goes to the READER, not just to build_nodes, so the class
    filter narrows the population the decimation samples from rather than
    thinning an already-decimated sample.
    """
    data = load_point_cloud(path, max_points=max_points, method=method,
                            seed=seed, keep_classes=keep_classes)
    nodes, report = build_nodes(data, keep_classes=keep_classes, **build_kwargs)
    report['decimation'] = (method if report['available_points'] > report['points']
                            else 'none')
    return nodes, report
