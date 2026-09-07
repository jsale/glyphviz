"""
Point-cloud / LIDAR import — glyphviz_core.point_cloud_loader.

Qt-free and GL-free. Test LAS files are WRITTEN with laspy rather than
committed as fixtures, which keeps the repo small and, more usefully, lets
each test state the file property it is about — 16-bit colour, a huge
projected coordinate origin, an unclassified file, a stray outlier — right
where the assertion is.

The properties pinned here are the ones a real tile taught us. All four were
measured against the Autzen Stadium test cloud (PDAL's public
autzen-classified.copc.laz: 10,653,336 points, Oregon State Plane, 16-bit
RGB, fifteen classification codes including user-defined ones past 64):

  * coordinates in the hundreds of thousands must come back centred;
  * 16-bit colour must be detected from the data, not assumed;
  * classification filtering must happen BEFORE decimation, or a point budget
    is spent on points that are then thrown away;
  * classification codes are not limited to the ASPRS 0-18 table.
"""
import numpy as np
import pytest

from glyphviz_core import point_cloud_loader as pcl
from glyphviz_core.geometry_data import GEO_POINT
from glyphviz_core.topology import TOPO_POINTCLOUD

laspy = pytest.importorskip('laspy')


# --------------------------------------------------------------- fixtures

def _write_las(path, xyz, *, rgb=None, classification=None, intensity=None,
               scale=0.01):
    """Write a LAS file with the given per-point data.

    point_format 3 carries colour and classification, 2 carries classification
    without colour — chosen from what the caller supplies so a test asking for
    "a file with no RGB" gets a file that genuinely has no RGB fields, not one
    with zeroed ones.
    """
    fmt = 3 if rgb is not None else 2
    header = laspy.LasHeader(point_format=fmt, version="1.2")
    header.scales = np.array([scale, scale, scale])
    header.offsets = np.floor(np.min(xyz, axis=0))
    las = laspy.LasData(header)
    las.x, las.y, las.z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    if rgb is not None:
        las.red, las.green, las.blue = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    if classification is not None:
        las.classification = classification
    if intensity is not None:
        las.intensity = intensity
    las.write(str(path))
    return str(path)


@pytest.fixture
def utm_las(tmp_path):
    """A file shaped like real airborne LIDAR: projected coordinates with a
    huge origin, 16-bit colour, and ASPRS classification."""
    rng = np.random.default_rng(3)
    n = 5000
    xyz = np.stack([
        635_000.0 + rng.random(n) * 3000.0,      # easting
        851_000.0 + rng.random(n) * 4000.0,      # northing
        400.0 + rng.random(n) * 200.0,           # elevation
    ], axis=1)
    rgb = (rng.random((n, 3)) * 60000).astype(np.uint16)     # 16-bit
    cls = rng.choice([2, 5, 6, 9], size=n, p=[0.65, 0.25, 0.05, 0.05])
    inten = (rng.random(n) * 60000).astype(np.uint16)
    return _write_las(tmp_path / "utm.las", xyz, rgb=rgb,
                      classification=cls.astype(np.uint8), intensity=inten)


# ------------------------------------------------------------ reading ---

def test_reads_a_las_file(utm_las):
    data = pcl.load_point_cloud(utm_las, max_points=None)
    assert len(data) == 5000
    assert data.total_points == 5000
    assert data.points.shape == (5000, 3)
    assert data.classification is not None
    assert data.intensity is not None


def test_coordinates_survive_the_las_scale_offset_round_trip(utm_las):
    """LAS stores scaled integers plus a header offset; laspy reconstructs the
    doubles. Pin that what comes back really is in source units and not, say,
    the raw integers."""
    data = pcl.load_point_cloud(utm_las, max_points=None)
    assert 635_000 <= data.points[:, 0].min() <= 638_000
    assert 851_000 <= data.points[:, 1].min() <= 855_000


def test_sixteen_bit_color_is_detected_and_scaled(utm_las):
    """The file is written with values well past 255, so the >>8 must fire."""
    data = pcl.load_point_cloud(utm_las, max_points=None)
    assert data.colors is not None
    assert data.colors.dtype == np.uint8
    assert data.colors.max() > 150     # a real spread, not a black cloud


def test_eight_bit_color_is_left_alone(tmp_path):
    """Plenty of writers put 8-bit values straight into the 16-bit fields.
    Scaling those by >>8 turns the cloud black — the failure this heuristic
    exists to prevent."""
    xyz = np.random.default_rng(0).random((200, 3)) * 10
    rgb = np.full((200, 3), 200, dtype=np.uint16)      # 8-bit values
    p = _write_las(tmp_path / "eight.las", xyz, rgb=rgb)
    data = pcl.load_point_cloud(p, max_points=None)
    assert data.colors.max() == 200


def test_a_file_with_no_color_reports_none(tmp_path):
    xyz = np.random.default_rng(0).random((200, 3)) * 10
    p = _write_las(tmp_path / "nocolor.las", xyz,
                   classification=np.full(200, 2, dtype=np.uint8))
    data = pcl.load_point_cloud(p, max_points=None)
    assert data.colors is None


def test_reads_ascii_xyz(tmp_path):
    p = tmp_path / "scan.xyz"
    p.write_text("# a comment\n1 2 3\n4 5 6\n7 8 9\n")
    data = pcl.load_point_cloud(str(p), max_points=None)
    assert len(data) == 3
    np.testing.assert_allclose(data.points[1], [4, 5, 6])


def test_reads_ascii_xyz_with_color(tmp_path):
    p = tmp_path / "scan.pts"
    p.write_text("1 2 3 255 0 0\n4 5 6 0 255 0\n")
    data = pcl.load_point_cloud(str(p), max_points=None)
    assert data.colors is not None
    assert list(data.colors[0]) == [255, 0, 0]


def test_an_unsupported_extension_says_so(tmp_path):
    p = tmp_path / "nope.docx"
    p.write_text("x")
    with pytest.raises(ValueError, match="Unsupported"):
        pcl.load_point_cloud(str(p))


# --------------------------------------------------------- decimation ---

@pytest.mark.parametrize('method', pcl.DECIMATE_METHODS)
def test_decimation_hits_the_target(utm_las, method):
    data = pcl.load_point_cloud(utm_las, max_points=500, method=method)
    assert len(data) <= 500
    assert len(data) >= 350          # voxel lands near, not exactly, on target
    assert data.total_points == 5000


def test_decimation_is_reproducible(utm_las):
    """Same seed, same scene — so re-importing a file reproduces the cloud
    rather than reshuffling it."""
    a = pcl.load_point_cloud(utm_las, max_points=500, seed=7)
    b = pcl.load_point_cloud(utm_las, max_points=500, seed=7)
    np.testing.assert_array_equal(a.points, b.points)
    c = pcl.load_point_cloud(utm_las, max_points=500, seed=8)
    assert not np.array_equal(a.points, c.points)


def test_decimation_keeps_every_parallel_array_aligned(utm_las):
    """Positions, colours, classification and intensity are gathered
    separately; a mismatch between them would put one point's colour on
    another's position, which no assertion downstream would catch."""
    full = pcl.load_point_cloud(utm_las, max_points=None)
    part = pcl.load_point_cloud(utm_las, max_points=400, method='stride')
    step = int(np.ceil(5000 / 400))
    idx = np.arange(0, 5000, step)[:400]
    np.testing.assert_array_equal(part.points, full.points[idx])
    np.testing.assert_array_equal(part.colors, full.colors[idx])
    np.testing.assert_array_equal(part.classification, full.classification[idx])


def test_nothing_is_dropped_when_the_file_is_already_small(utm_las):
    data = pcl.load_point_cloud(utm_las, max_points=999_999)
    assert len(data) == 5000


def test_voxel_sampling_spreads_more_evenly_than_random(tmp_path):
    """The reason voxel is offered at all: a scan with a dense patch (a
    flight-line overlap) should not import as mostly that patch."""
    rng = np.random.default_rng(1)
    sparse = rng.random((2000, 3)) * np.array([100.0, 100.0, 5.0])
    dense = rng.random((18000, 3)) * np.array([10.0, 100.0, 5.0])
    p = _write_las(tmp_path / "uneven.las", np.vstack([sparse, dense]))

    def dense_fraction(method):
        d = pcl.load_point_cloud(p, max_points=1000, method=method)
        return float((d.points[:, 0] < 10.0).mean())

    assert dense_fraction('voxel') < dense_fraction('random')


# ------------------------------------------------------ world fitting ---

def test_fit_recenters_and_scales(utm_las):
    data = pcl.load_point_cloud(utm_las, max_points=None)
    fitted, scale, center = pcl.fit_to_world(data.points, span=360.0)
    assert abs(center[0] - 636_500) < 500      # near the source centre
    # centred on the origin, and the wider horizontal axis spans ~360
    assert np.abs(fitted.mean(axis=0)[:2]).max() < 20.0
    wide = max(np.ptp(fitted[:, 0]), np.ptp(fitted[:, 1]))
    assert 340.0 < wide < 380.0


def test_fit_is_uniform_across_axes(utm_las):
    """A per-axis fit would silently stretch terrain — the one thing a LIDAR
    viewer must never do by default. Aspect ratios must survive."""
    data = pcl.load_point_cloud(utm_las, max_points=None)
    src = np.ptp(data.points, axis=0)
    fitted, _, _ = pcl.fit_to_world(data.points)
    got = np.ptp(fitted, axis=0)
    np.testing.assert_allclose(got / got[0], src / src[0], rtol=0.02)


def test_exaggeration_touches_only_z(utm_las):
    data = pcl.load_point_cloud(utm_las, max_points=None)
    flat, _, _ = pcl.fit_to_world(data.points, exaggeration=1.0)
    tall, _, _ = pcl.fit_to_world(data.points, exaggeration=3.0)
    np.testing.assert_allclose(flat[:, :2], tall[:, :2])
    np.testing.assert_allclose(flat[:, 2] * 3.0, tall[:, 2])


def test_one_wild_outlier_does_not_shrink_the_scan(tmp_path):
    """Airborne LIDAR reliably contains a few gross outliers (birds, cloud
    returns). Fitting off raw min/max would let one of them collapse the
    whole cloud toward invisibility."""
    rng = np.random.default_rng(2)
    xyz = rng.random((5000, 3)) * np.array([1000.0, 1000.0, 50.0])
    xyz[0] = [500_000.0, 500_000.0, 90_000.0]          # one absurd return
    p = _write_las(tmp_path / "outlier.las", xyz, scale=0.1)
    data = pcl.load_point_cloud(p, max_points=None)
    fitted, _, _ = pcl.fit_to_world(data.points, span=360.0)
    body = fitted[1:]      # everything but the outlier
    wide = max(np.ptp(body[:, 0]), np.ptp(body[:, 1]))
    assert wide > 300.0, wide     # the real cloud still fills the span


def test_fit_of_an_empty_cloud_does_not_explode():
    fitted, scale, center = pcl.fit_to_world(np.zeros((0, 3)))
    assert fitted.shape == (0, 3) and scale == 1.0


# ---------------------------------------------------------- colouring ---

def test_auto_prefers_file_rgb(utm_las):
    data = pcl.load_point_cloud(utm_las, max_points=None)
    _, mode = pcl.resolve_colors(data, 'auto')
    assert mode == 'rgb'


def test_auto_falls_back_to_classification_when_there_is_no_rgb(tmp_path):
    xyz = np.random.default_rng(0).random((500, 3)) * 100
    cls = np.random.default_rng(0).choice([2, 5, 6], 500).astype(np.uint8)
    p = _write_las(tmp_path / "cls.las", xyz, classification=cls)
    data = pcl.load_point_cloud(p, max_points=None)
    colors, mode = pcl.resolve_colors(data, 'auto')
    assert mode == 'classification'
    # ground and vegetation must not come out the same colour
    ground = colors[data.classification == 2][0]
    veg = colors[data.classification == 5][0]
    assert not np.array_equal(ground, veg)


def test_auto_falls_back_to_elevation_for_an_unclassified_file(tmp_path):
    """Nearly every LAS file HAS a classification column; most public ones
    leave it all 0 or all 1. Colouring by class there gives one flat grey
    cloud, which looks like a bug."""
    xyz = np.random.default_rng(0).random((500, 3)) * 100
    p = _write_las(tmp_path / "unclass.las", xyz,
                   classification=np.zeros(500, dtype=np.uint8))
    data = pcl.load_point_cloud(p, max_points=None)
    _, mode = pcl.resolve_colors(data, 'auto')
    assert mode == 'elevation'


def test_elevation_ramp_actually_ramps(tmp_path):
    xyz = np.zeros((300, 3))
    xyz[:, 2] = np.linspace(0, 100, 300)
    p = _write_las(tmp_path / "ramp.las", xyz)
    data = pcl.load_point_cloud(p, max_points=None)
    colors, mode = pcl.resolve_colors(data, 'elevation')
    assert mode == 'elevation'
    assert not np.array_equal(colors[0], colors[-1])


def test_asking_for_a_mode_the_file_cannot_serve_falls_back(tmp_path):
    """Requesting RGB on a file with none must produce a usable cloud, not
    a crash and not a black one."""
    xyz = np.random.default_rng(0).random((200, 3)) * 10
    p = _write_las(tmp_path / "norgb.las", xyz)
    data = pcl.load_point_cloud(p, max_points=None)
    colors, mode = pcl.resolve_colors(data, 'rgb')
    assert mode != 'rgb'
    assert colors.shape == (200, 3)


def test_user_defined_class_codes_get_distinct_colors():
    """LAS 1.4 allows 0-255 and reserves 64+ for user definition; the real
    test tile uses 64, 65, 66, 68, 73, 76 and 77."""
    assert pcl.class_color(2) == pcl.ASPRS_CLASSES[2][1]
    a, b = pcl.class_color(64), pcl.class_color(65)
    assert a != b
    assert pcl.class_name(64).startswith("User class")
    assert pcl.class_name(2) == "Ground"


# ----------------------------------------------- classification filter ---

def test_class_filter_narrows_the_import(utm_las):
    nodes, report = pcl.import_to_nodes(utm_las, max_points=None,
                                        keep_classes=[6])
    assert set(report['classes']) == {6}
    assert len(nodes) - 1 == report['points']


def test_class_filter_runs_BEFORE_decimation(utm_las):
    """The bug this pins: filtering after sampling spends the point budget on
    points that are then discarded. The file is 65% ground; asking for 1000
    non-ground points must give ~1000, not ~350."""
    _, report = pcl.import_to_nodes(utm_las, max_points=1000,
                                    keep_classes=[5, 6, 9])
    assert report['points'] == 1000
    assert set(report['classes']) <= {5, 6, 9}
    # and the report stays honest about all three counts
    assert report['total_points'] == 5000
    assert report['points'] < report['available_points'] < report['total_points']


def test_no_filter_leaves_available_equal_to_total(utm_las):
    _, report = pcl.import_to_nodes(utm_las, max_points=1000)
    assert report['available_points'] == report['total_points'] == 5000


# -------------------------------------------------------- node building ---

def test_build_nodes_makes_a_cloud_parent_and_one_node_per_point(utm_las):
    nodes, report = pcl.import_to_nodes(utm_las, max_points=300)
    parent, points = nodes[0], nodes[1:]
    assert parent.topo == TOPO_POINTCLOUD
    assert len(points) == 300 == report['points']
    assert all(p.parent_id == parent.id for p in points)
    assert all(p.branch_level == 1 for p in points)
    assert all(p.geometry == GEO_POINT for p in points)


def test_node_ids_are_unique_and_contiguous(utm_las):
    nodes, _ = pcl.import_to_nodes(utm_las, max_points=300, start_id=50)
    ids = [n.id for n in nodes]
    assert ids == list(range(50, 50 + len(nodes)))


def test_point_size_lands_on_the_parents_ratio(utm_las):
    from glyphviz_core import point_cloud as pc
    nodes, _ = pcl.import_to_nodes(utm_las, max_points=50, point_size=6.0)
    assert pc.point_size(nodes[0]) == pytest.approx(6.0)


def test_points_carry_no_labels_but_the_parent_does(utm_las):
    """GlyphViz's usual rule is that every node carries a label. A cloud is
    where that inverts — 100k labels is megabytes nobody reads — so the
    provenance lives on the parent instead."""
    nodes, _ = pcl.import_to_nodes(utm_las, max_points=50)
    assert nodes[0].text
    assert all(not p.text for p in nodes[1:])


def test_the_parent_label_records_how_the_cloud_was_made(utm_las):
    """A saved scene has no other memory of the import settings."""
    nodes, _ = pcl.import_to_nodes(utm_las, max_points=300,
                                   color_mode='classification',
                                   exaggeration=2.5, keep_classes=[5, 6])
    label = nodes[0].text
    assert '300' in label
    assert 'classification' in label
    assert '2.5x' in label
    assert '5,000' in label            # what it was sampled from


def test_imported_points_land_in_world_units(utm_las):
    """The point of the fit: coordinates in the hundreds of thousands must
    not reach the scene."""
    nodes, _ = pcl.import_to_nodes(utm_las, max_points=500, span=360.0)
    xs = [n.translate_x for n in nodes[1:]]
    ys = [n.translate_y for n in nodes[1:]]
    assert max(map(abs, xs)) < 200.0
    assert max(map(abs, ys)) < 200.0


def test_import_round_trips_through_a_node_csv(utm_las, tmp_path):
    """The whole delivery: an imported cloud is an ordinary GlyphViz scene."""
    from glyphviz_core.csv_reader import load_node_csv, save_node_csv
    from glyphviz_core.scene import Scene

    nodes, _ = pcl.import_to_nodes(utm_las, max_points=400)
    out = tmp_path / "cloud_gv_node.csv"
    save_node_csv(nodes, str(out))
    reloaded = load_node_csv(str(out))

    assert len(reloaded) == len(nodes)
    assert reloaded[0].topo == TOPO_POINTCLOUD
    assert reloaded[0].ratio == pytest.approx(nodes[0].ratio)
    scene = Scene(reloaded, base_scale=1.0)
    for original, back in zip(nodes[1:6], reloaded[1:6]):
        # a cloud parent adds no offset, so a point's world position IS its
        # translate -- the placement claim, checked through the real engine
        assert scene.world_pos(back.id) == pytest.approx(
            (original.translate_x, original.translate_y, original.translate_z),
            abs=1e-3)
