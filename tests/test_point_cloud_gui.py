"""
Point Cloud topology — rendering, picking and the loop exclusions, through
the real Viewport.

The batch math is pinned in tests/test_point_cloud.py. What's pinned here is
that the topology REPLACES its children's rendering rather than decorating
it, and that the three rules that follow from that hold:

  * a cloud's points draw as one glDrawArrays(GL_POINTS), and their glyphs
    do not draw at all;
  * a cloud counts as ONE unit against the backslash draw limit — its parent
    glyph — so the limit thins the glyphs around a cloud and never decimates
    the cloud itself;
  * in the unscoped all-tags mode a cloud's points are not labelled unless
    individually pinned or selected, so a 100k-point scan can't bury the
    scene in text.

Most tests need Qt but not a GL context — the GL entry points in viewport.py
are swapped for recorders, the arrangement tests/test_link_geometry_gui.py
uses.

The last two are different: picking goes through the real color-ID FBO, so
they need a real driver. Under QT_QPA_PLATFORM=offscreen (what this suite
runs as, and what CI has) glGenFramebuffers is not even a live entry point,
so they skip. Run the file with QT_QPA_PLATFORM unset on a machine with a GPU
to actually exercise them; both were verified that way on the RTX 3080 Ti
this feature was built on -- 216/216 exact hits on a sparse cloud, and every
click on a dense 20k-point one landing within 2.5 px.
"""
import os

import numpy as np
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

# Pin devicePixelRatio to 1, BEFORE Qt is imported (these are read once, when
# QApplication is constructed) -- the same pin tools/export_frame.py takes,
# for the same reason. The picking tests project a world position to a LOGICAL
# widget pixel themselves and click there; on a fractional-DPI display that
# integer is up to 0.6 DEVICE pixels off the true center, which a glyph
# several pixels wide absorbs and a 3-pixel cloud point does not. Measured on
# a 1.25 display: glyph picks landed exactly, cloud picks 1-2 px out. At DPR 1
# the two passes are pixel-identical (verified against a glyph control at the
# same nine world positions), which is the property these tests are for.
os.environ.setdefault('QT_ENABLE_HIGHDPI_SCALING', '0')
os.environ.setdefault('QT_SCALE_FACTOR', '1')

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtWidgets import QApplication                          # noqa: E402

from glyphviz_core import point_cloud as pc                         # noqa: E402
from glyphviz_core.geometry_data import GEO_POINT, GEO_SPHERE       # noqa: E402
from glyphviz_core.node import Node, NODE_TYPE_LINK                 # noqa: E402
from glyphviz_core.topology import (                                # noqa: E402
    TOPO_NONE, TOPO_POINTCLOUD,
)
from glyphviz_gl import viewport as vp                              # noqa: E402


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication([])
        except Exception as exc:                        # pragma: no cover
            pytest.skip(f'Qt unavailable: {exc}')
    return app


def _node(**kw):
    base = dict(
        id=1, type=5, parent_id=0, branch_level=0,
        translate_x=0.0, translate_y=0.0, translate_z=0.0,
        rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=200, color_g=200, color_b=200, color_a=255,
        geometry=GEO_SPHERE, hide=0, topo=TOPO_NONE,
    )
    base.update(kw)
    return Node(**base)


def _scene_nodes(n_points=8, parent_topo=TOPO_POINTCLOUD, ratio=0.15,
                 extra_glyphs=3):
    """A cloud parent with n_points children, plus a few unrelated glyphs so
    the exclusion tests can tell "skipped the points" from "skipped
    everything"."""
    parent = _node(id=1, topo=parent_topo, ratio=ratio)
    pts = [_node(id=10 + i, parent_id=1, branch_level=1, geometry=GEO_POINT,
                 translate_x=float(i), translate_z=float(i % 3),
                 text=f'p{i}')
           for i in range(n_points)]
    # 10_000 + i, not 100 + i: the points number from 10, so at more than
    # ~90 points the two ranges used to overlap and the fixture silently
    # handed out duplicate node ids.
    others = [_node(id=10_000 + i, translate_y=20.0 + i, text=f'g{i}')
              for i in range(extra_glyphs)]
    return [parent] + pts + others


# --------------------------------------------------------------- recorders

class _GLRecorder:
    """Stands in for viewport.py's GL entry points, logging calls in order."""

    def __init__(self):
        self.calls: list[tuple] = []
        self._next_list = 1

    def install(self, monkeypatch):
        for name in dir(vp):
            if not name.startswith('gl') or name.startswith('GL'):
                continue
            if not callable(getattr(vp, name)):
                continue
            monkeypatch.setattr(vp, name, self._stub(name), raising=False)

    def _stub(self, name):
        def fn(*args):
            self.calls.append((name,) + args)
            if name == 'glGenLists':
                self._next_list += 1
                return self._next_list
            if name == 'glIsEnabled':
                return False
            return None
        return fn

    def names(self):
        return [c[0] for c in self.calls]

    def of(self, name):
        return [c for c in self.calls if c[0] == name]

    def lighting_events(self):
        return [c[0] == 'glEnable' for c in self.calls
                if c[0] in ('glEnable', 'glDisable')
                and c[1:] == (vp.GL_LIGHTING,)]


class _GeoSpy:
    """Stands in for GeoRenderer, recording which glyphs actually drew."""

    def __init__(self):
        self.drawn: list[int] = []

    def draw(self, geo_id, rx, ry, rz, ratio=0.1, gl_tex_name=0, mesh_id=0):
        self.drawn.append(geo_id)

    def ensure_ratio_list(self, *a, **kw):
        pass


def _bare_viewport(nodes, show_hidden=False, draw_limit=None):
    """A Viewport with just enough state wired for the draw/pick loops, with
    no GL context and no widget — the same __new__ trick the link-geometry
    render tests use."""
    view = vp.Viewport.__new__(vp.Viewport)
    view._scene = vp.Scene(nodes, base_scale=1.0)
    view._scan_cache = None
    view._scan_cache_rev = -1
    view.show_hidden = show_hidden
    view._draw_limit = draw_limit
    view._cloud_dls = {}
    view._assets_rev = 0
    view._ch_dynamic_ids = set()
    view._ch_transform_ids = set()
    view._ch_dynamic_nodes = []
    view.selected_node_ids = set()
    view.show_tags = True
    view.show_tags_selected_only = False
    view._tex_mgr = type('T', (), {'get_gl_name': lambda self, i: 0})()
    view._video_mgr = type('V', (), {'get_gl_name': lambda self, i: 0})()
    view._geo = _GeoSpy()
    return view


# ------------------------------------------------------- batched rendering

def test_cloud_draws_one_point_array_not_per_point_glyphs(qapp, monkeypatch):
    rec = _GLRecorder()
    rec.install(monkeypatch)
    view = _bare_viewport(_scene_nodes(n_points=8))
    view._draw_point_clouds()

    draws = rec.of('glDrawArrays')
    assert len(draws) == 1, rec.names()
    assert draws[0][1] == vp.GL_POINTS
    assert draws[0][3] == 8              # every point, one call
    assert view._geo.drawn == []         # no per-point glyph drawing


def test_cloud_children_are_excluded_from_the_glyph_loop(qapp, monkeypatch):
    rec = _GLRecorder()
    rec.install(monkeypatch)
    view = _bare_viewport(_scene_nodes(n_points=8, extra_glyphs=3))
    view._draw_nodes_immediate(planes=None)
    # The cloud parent and the three unrelated glyphs draw; the 8 points
    # do not. This is the "replaces, not decorates" contract.
    assert len(view._geo.drawn) == 4


def test_a_non_cloud_parent_still_draws_every_child_as_a_glyph(qapp,
                                                               monkeypatch):
    """Control: the same scene with the parent's topo left at None."""
    rec = _GLRecorder()
    rec.install(monkeypatch)
    view = _bare_viewport(_scene_nodes(n_points=8, parent_topo=TOPO_NONE))
    view._draw_nodes_immediate(planes=None)
    assert len(view._geo.drawn) == 12          # 1 parent + 8 points + 3 others
    assert not rec.of('glDrawArrays')
    assert view._cloud_dls == {}


def test_point_size_comes_from_the_parent_ratio(qapp, monkeypatch):
    rec = _GLRecorder()
    rec.install(monkeypatch)
    view = _bare_viewport(_scene_nodes(ratio=0.4))
    view._draw_point_clouds()
    sizes = [c[1] for c in rec.of('glPointSize')]
    assert sizes[0] == pytest.approx(8.0)      # 0.4 * POINT_SIZE_SCALE
    assert sizes[-1] == pytest.approx(1.0)     # restored afterwards


def test_lighting_is_left_the_way_the_pass_found_it(qapp, monkeypatch):
    """Points carry flat color, so the pass disables lighting — and must put
    it back, or every lit glyph drawn after it renders unshaded (the bug the
    link-geometry pass had to be pinned against)."""
    rec = _GLRecorder()
    rec.install(monkeypatch)
    view = _bare_viewport(_scene_nodes())
    view._draw_point_clouds()
    assert rec.lighting_events() == [False, True]


def test_hidden_points_are_dropped_from_the_batch(qapp, monkeypatch):
    rec = _GLRecorder()
    rec.install(monkeypatch)
    nodes = _scene_nodes(n_points=6)
    nodes[2].hide = 1
    nodes[4].hide = 1
    view = _bare_viewport(nodes)
    view._draw_point_clouds()
    assert rec.of('glDrawArrays')[0][3] == 4


def test_show_hidden_puts_them_back(qapp, monkeypatch):
    rec = _GLRecorder()
    rec.install(monkeypatch)
    nodes = _scene_nodes(n_points=6)
    nodes[2].hide = 1
    view = _bare_viewport(nodes, show_hidden=True)
    view._draw_point_clouds()
    assert rec.of('glDrawArrays')[0][3] == 6


def test_a_hidden_cloud_parent_draws_no_points(qapp, monkeypatch):
    rec = _GLRecorder()
    rec.install(monkeypatch)
    nodes = _scene_nodes(n_points=6)
    nodes[0].hide = 1
    view = _bare_viewport(nodes)
    view._draw_point_clouds()
    assert not rec.of('glDrawArrays')


def test_an_empty_cloud_draws_nothing_and_caches_nothing(qapp, monkeypatch):
    rec = _GLRecorder()
    rec.install(monkeypatch)
    view = _bare_viewport([_node(id=1, topo=TOPO_POINTCLOUD)])
    view._draw_point_clouds()
    assert not rec.of('glDrawArrays')
    assert view._cloud_dls == {}


def test_a_link_child_of_a_cloud_is_not_swallowed_into_it(qapp, monkeypatch):
    """A Link parented to a cloud is still an edge, drawn by the overlay
    pass — it must not become a point, and it must not be silently dropped."""
    rec = _GLRecorder()
    rec.install(monkeypatch)
    nodes = _scene_nodes(n_points=4)
    nodes.append(_node(id=77, type=NODE_TYPE_LINK, parent_id=1,
                       branch_level=1, extras={'child_id': 11}))
    view = _bare_viewport(nodes)
    view._draw_point_clouds()
    assert rec.of('glDrawArrays')[0][3] == 4


# ----------------------------------------------------------- batch caching

def test_the_batch_is_baked_once_and_replayed(qapp, monkeypatch):
    rec = _GLRecorder()
    rec.install(monkeypatch)
    view = _bare_viewport(_scene_nodes())
    view._draw_point_clouds()
    view._draw_point_clouds()
    view._draw_point_clouds()
    # One bake -- one glNewList holding the single glDrawArrays -- and then
    # every frame, that first one included, is a glCallList replay.
    assert len(rec.of('glNewList')) == 1
    assert len(rec.of('glDrawArrays')) == 1
    assert len(rec.of('glCallList')) == 3


def test_a_scene_edit_rebakes_the_batch(qapp, monkeypatch):
    rec = _GLRecorder()
    rec.install(monkeypatch)
    view = _bare_viewport(_scene_nodes())
    view._draw_point_clouds()
    view._scene.invalidate()          # what any node edit does
    view._scan_cache_rev = -1
    view._draw_point_clouds()
    assert len(rec.of('glNewList')) == 2
    # the superseded list is freed, not leaked
    assert len(rec.of('glDeleteLists')) == 1


def test_a_channel_animated_cloud_is_never_baked(qapp, monkeypatch):
    """Channels playback moves nodes WITHOUT bumping Scene._revision, so a
    retained list would freeze the cloud mid-animation. Those redraw from the
    arrays every frame instead."""
    rec = _GLRecorder()
    rec.install(monkeypatch)
    view = _bare_viewport(_scene_nodes(n_points=6))
    view._ch_transform_ids = {12}         # one point is transform-bound
    view._draw_point_clouds()
    view._draw_point_clouds()
    assert not rec.of('glNewList')
    assert not rec.of('glCallList')
    assert len(rec.of('glDrawArrays')) == 2


def test_client_array_state_is_always_turned_back_off(qapp, monkeypatch):
    """A dangling glVertexPointer into a numpy buffer Python may free is a
    crash waiting for the next glDrawArrays anywhere in the renderer."""
    rec = _GLRecorder()
    rec.install(monkeypatch)
    view = _bare_viewport(_scene_nodes())
    view._draw_point_clouds()
    enabled = [c[1] for c in rec.of('glEnableClientState')]
    disabled = [c[1] for c in rec.of('glDisableClientState')]
    assert sorted(enabled) == sorted(disabled)
    assert vp.GL_VERTEX_ARRAY in enabled and vp.GL_COLOR_ARRAY in enabled


# ------------------------------------------------------------- draw limit

def test_a_cloud_costs_one_unit_of_the_draw_limit(qapp, monkeypatch):
    """The backslash limit counts the cloud's PARENT glyph and nothing else,
    so the cap thins the glyphs around a cloud rather than the cloud."""
    rec = _GLRecorder()
    rec.install(monkeypatch)
    # 8 points + 3 unrelated glyphs + the parent. A limit of 2 should draw
    # the parent and exactly one other glyph.
    view = _bare_viewport(_scene_nodes(n_points=8, extra_glyphs=3),
                          draw_limit=2)
    view._draw_nodes_immediate(planes=None)
    assert len(view._geo.drawn) == 2


def test_the_draw_limit_never_decimates_the_cloud_itself(qapp, monkeypatch):
    rec = _GLRecorder()
    rec.install(monkeypatch)
    view = _bare_viewport(_scene_nodes(n_points=8), draw_limit=1)
    view._draw_point_clouds()
    assert rec.of('glDrawArrays')[0][3] == 8


# ------------------------------------------------------------------- tags

def _tag_ids(view):
    """Label texts the tag pass would draw.

    The projection culls anything outside NDC, so a plain identity matrix
    would drop the whole scene and every one of these tests would pass
    vacuously. A uniform 0.02 shrink brings the fixture's coordinates
    (points along x=0..7, glyphs at y=20..22) inside the cube instead.
    """
    mvp = np.diag([0.02, 0.02, 0.02, 1.0])
    view._mv_matrix = mvp
    view._proj_matrix = np.eye(4)
    texts = view._project_tagged_nodes(mvp, np.eye(4), 0, 0, 400, 400)
    return {t[0] for t in texts}


def test_all_tags_mode_does_not_label_a_clouds_points(qapp):
    """Item 5-2: 100k labels over a scan is unreadable, and which 500 the
    per-frame cap kept would be scene order, not a user choice."""
    view = _bare_viewport(_scene_nodes(n_points=8, extra_glyphs=3))
    labels = _tag_ids(view)
    assert not any(t.startswith('p') for t in labels), labels
    # the cloud parent and the unrelated glyphs still label normally
    assert {'g0', 'g1', 'g2'} <= labels


def test_a_selected_point_is_labelled(qapp):
    view = _bare_viewport(_scene_nodes(n_points=8))
    view.selected_node_ids = {13}
    assert 'p3' in _tag_ids(view)


def test_a_pinned_point_is_labelled(qapp):
    """show_text is an explicit per-node act and outranks every scene-wide
    tag setting — for a cloud point exactly as for any other node."""
    nodes = _scene_nodes(n_points=8)
    nodes[5].show_text = 1
    view = _bare_viewport(nodes)
    assert 'p4' in _tag_ids(view)


def test_cloud_points_do_not_consume_the_tag_pass_draw_limit(qapp):
    """The tag loop's limit counter has to agree with the draw loop's, or
    labels start vanishing off glyphs that are plainly on screen."""
    view = _bare_viewport(_scene_nodes(n_points=8, extra_glyphs=3),
                          draw_limit=4)
    labels = _tag_ids(view)
    assert {'g0', 'g1', 'g2'} <= labels


def test_the_tag_pass_does_not_walk_the_cloud(qapp):
    """The frame-rate fix, stated as a count rather than a stopwatch.

    The tag overlay runs every frame over the whole node list. On a real
    442,767-point import that was 109 ms of a 111 ms frame — 97% of it — for
    a loop that skipped every node it looked at. Jeff saw it as 10 fps.
    Filtering the cloud out BEFORE the loop took the same scene to 2.4 ms.

    Counting visits rather than timing keeps this honest on any machine: the
    pass must not touch a cloud's points at all.
    """
    nodes = _scene_nodes(n_points=200, extra_glyphs=3)
    view = _bare_viewport(nodes)
    cloud_ids = {n.id for n in nodes if n.parent_id == 1}

    visited = []
    scan = view._scene_scan()
    for node in scan.taggable_nodes(view._scene.nodes):
        visited.append(node.id)

    assert not (set(visited) & cloud_ids), "the tag pass walked cloud points"
    assert len(visited) == 4          # cloud parent + 3 unrelated glyphs


def test_a_scene_with_no_cloud_pays_nothing_for_the_filter(qapp):
    """taggable_nodes must hand back the caller's own list — same object, no
    copy — so every existing scene behaves and performs identically."""
    nodes = _scene_nodes(n_points=5, parent_topo=TOPO_NONE)
    view = _bare_viewport(nodes)
    scan = view._scene_scan()
    assert scan.taggable_nodes(view._scene.nodes) is view._scene.nodes


def test_a_pinned_cloud_point_stays_in_the_tag_pass(qapp):
    """show_text outranks every scene-wide setting, so the filter has to keep
    pinned points. Safe to bake into the per-revision cache because changing
    show_text bumps the revision — unlike selection."""
    nodes = _scene_nodes(n_points=50)
    nodes[7].show_text = 1
    view = _bare_viewport(nodes)
    kept = {n.id for n in view._scene_scan().taggable_nodes(view._scene.nodes)}
    assert nodes[7].id in kept


def test_a_selected_cloud_point_is_added_back_per_frame(qapp):
    """Selection deliberately does not bump the scene revision, so a selected
    point cannot be baked into the cached list — the tag pass gathers those
    itself. Pinning and selecting the same point must not label it twice."""
    nodes = _scene_nodes(n_points=50)
    view = _bare_viewport(nodes)
    view.selected_node_ids = {17, 18}
    nodes[8].show_text = 1                     # id 18, both pinned AND selected
    view._scan_cache_rev = -1                  # show_text changed
    labels = [t[0] for t in view._project_tagged_nodes(
        np.diag([0.02, 0.02, 0.02, 1.0]), np.eye(4), 0, 0, 400, 400)]
    assert 'p7' in labels and 'p8' in labels
    assert labels.count('p8') == 1, labels      # not drawn twice


# ------------------------------------------------- picking (needs real GL)

def _real_viewport(nodes, w=400, h=400):
    """A Viewport backed by a real driver, or a skip.

    PyOpenGL resolves entry points lazily against the CURRENT context, so the
    framebuffer probe below only means anything after one exists and is made
    current -- checked before any context, bool(glGenFramebuffers) is False on
    a perfectly good GPU. Qt's offscreen platform hands out a context whose
    pointers stay null, which otherwise surfaces as a NullFunctionError deep
    inside the first pick instead of an obvious "no GL here".
    """
    view = vp.Viewport()
    view.base_scale = 1.0
    view.resize(w, h)
    try:
        view.grabFramebuffer()            # forces context creation
        view.makeCurrent()
        ok = bool(vp.glGenFramebuffers)
    except Exception as exc:              # pragma: no cover
        pytest.skip(f'no GL context: {exc}')
    if not ok:
        pytest.skip('no framebuffer support (offscreen platform)')
    view.set_nodes(nodes)
    return view


def _sparse_cloud(k=3, step=12.0):
    parent = _node(id=1, topo=TOPO_POINTCLOUD, ratio=0.15)
    pts, nid = [], 10
    for i in range(k):
        for j in range(k):
            pts.append(_node(id=nid, parent_id=1, branch_level=1,
                             geometry=GEO_POINT,
                             translate_x=(i - k / 2) * step,
                             translate_z=(j - k / 2) * step))
            nid += 1
    return [parent] + pts


def test_a_click_on_a_point_selects_that_point(qapp):
    """Per-point color-IDs, through the real pick FBO. Points are spaced so
    no two share a pixel — on a dense cloud the nearest of the overlapping
    points correctly wins instead, which is a depth test doing its job."""
    view = _real_viewport(_sparse_cloud())
    view.set_camera(azimuth=90.0, elevation=0.0, distance=120.0,
                    target=(0.0, 0.0, 0.0))
    view.grabFramebuffer()
    if view._mv_matrix is None:                       # pragma: no cover
        pytest.skip('no camera matrices — GL context is not really rendering')
    entry = view._cloud_dls.get(1)
    assert entry is not None and len(entry.batch) == 9

    w, h = view.width(), view.height()
    checked = 0
    for i in range(len(entry.batch)):
        p = np.append(entry.batch.positions[i].astype(np.float64), 1.0)
        clip = view._proj_matrix @ (view._mv_matrix @ p)
        if clip[3] <= 0:
            continue
        ndc = clip[:3] / clip[3]
        sx = int(round((ndc[0] * 0.5 + 0.5) * w))
        sy = int(round((1.0 - (ndc[1] * 0.5 + 0.5)) * h))
        if not (4 <= sx < w - 4 and 4 <= sy < h - 4):
            continue
        got = view._pick_node(sx, sy)
        assert got is not None, (sx, sy)
        assert got.id == int(entry.batch.ids[i]), (got.id, entry.batch.ids[i])
        checked += 1
    assert checked >= 6, checked


def test_empty_space_next_to_a_cloud_still_picks_nothing(qapp):
    """The cloud pick pass must not paint anything the visible pass didn't —
    the invariant the link picking bug came down to."""
    view = _real_viewport(_sparse_cloud())
    view.set_camera(azimuth=90.0, elevation=0.0, distance=120.0,
                    target=(0.0, 0.0, 0.0))
    view.grabFramebuffer()
    assert view._pick_node(3, 3) is None
