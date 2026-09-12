"""
Texture mapping on a TOPO_SURFACE mesh (2026-09-12).

A Surface parent carrying a `texture_id` now drapes that image across its own
lattice instead of interpolating its children's vertex colours. Both routes
stay available and that is the point: a texture is what imagery wants — and it
decouples map resolution from mesh density, which otherwise caps the picture
at one pixel per vertex — while vertex colour is what *data* painted on the
terrain wants (burn severity, land cover, slope).

What's pinned here:

  * the mode is chosen by texture_id alone, and an unresolvable id falls back
    to vertex colour rather than drawing an untextured white sheet;
  * UVs match GEO_GRID's convention (u with +x, v with +y), so one
    georeferenced image registers identically on a flat grid and on relief —
    this is the assertion that would catch a vertically flipped map;
  * the corners of the lattice land on the corners of the image, and interior
    vertices sit at their true fractional position, so the picture is not
    stretched or offset;
  * the textured path leaves GL_TEXTURE_2D off again afterwards, so it cannot
    leak into later passes;
  * texturing is MODULATE, not REPLACE — this mesh is drawn lit, and the
    relief only reads as relief because lighting shades it.

Qt is needed but a GL context is not: viewport.py pulls its GL entry points in
via `from OpenGL.GL import *`, so swapping the callables for recorders
captures the exact call stream — the same arrangement
tests/test_link_geometry_gui.py uses on the very same function.
"""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtWidgets import QApplication                          # noqa: E402

from glyphviz_core.node import Node                                 # noqa: E402
from glyphviz_core.topology import TOPO_SURFACE                     # noqa: E402
from glyphviz_gl import viewport as vp                              # noqa: E402

TEX_NAME = 77          # a non-zero GL texture name means "resolved"


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication([])
        except Exception as exc:                        # pragma: no cover
            pytest.skip(f'Qt unavailable: {exc}')
    return app


class _GLRecorder:
    """Stands in for viewport.py's GL entry points, logging calls in order."""

    def __init__(self):
        self.calls: list[tuple] = []

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
                return 1
            if name == 'glIsEnabled':
                return False
            return None
        return fn

    def names(self):
        return [c[0] for c in self.calls]

    def texcoords(self):
        return [c[1:] for c in self.calls if c[0] == 'glTexCoord2f']

    def vertex_colors(self):
        return [c[1:] for c in self.calls if c[0] == 'glColor4f']

    def quads(self):
        """Emitted vertices grouped four at a time, each paired with the
        texcoord latched when it was sent (None if untextured)."""
        pairs, uv = [], None
        for call in self.calls:
            if call[0] == 'glTexCoord2f':
                uv = call[1:]
            elif call[0] == 'glVertex3f':
                pairs.append((uv, call[1:]))
        return [pairs[i:i + 4] for i in range(0, len(pairs), 4)]

    def texture_events(self):
        """(enabled: bool) in order, for GL_TEXTURE_2D only."""
        return [c[0] == 'glEnable' for c in self.calls
                if c[0] in ('glEnable', 'glDisable')
                and c[1:] == (vp.GL_TEXTURE_2D,)]


def _node(**overrides):
    base = dict(
        id=1, type=5, parent_id=0, branch_level=0,
        translate_x=0.0, translate_y=0.0, translate_z=0.0,
        rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=200, color_g=200, color_b=200, color_a=255,
        geometry=1, hide=0, topo=0,
    )
    base.update(overrides)
    return Node(**base)


def _surface_scene(cols=3, rows=3, texture_id=0, span=10.0):
    """A Surface parent at the origin with a cols x rows lattice under it.

    Vertex colours are made distinct per child so a fallback to vertex colour
    is visible in the recorder rather than indistinguishable from a default.
    """
    parent = _node(id=1, topo=TOPO_SURFACE, texture_id=texture_id)
    nodes = [parent]
    nid = 2
    for j in range(rows):
        for i in range(cols):
            nodes.append(_node(
                id=nid, parent_id=1, branch_level=1,
                translate_x=span * i / (cols - 1),
                translate_y=span * j / (rows - 1),
                translate_z=0.0,
                color_r=10 * i, color_g=10 * j, color_b=7, color_a=255,
            ))
            nid += 1
    return nodes


def _viewport(nodes, resolves=True, bound=()):
    view = vp.Viewport.__new__(vp.Viewport)
    view._scene = vp.Scene(nodes)
    view._scan_cache = None
    view._scan_cache_rev = -1
    view.show_hidden = False
    view._ch_dynamic_ids = set(bound)
    view._ch_transform_ids = set()
    # A non-empty dynamic set sends _draw_topology_overlays through the
    # playback branch, which rebuilds these from the scene on demand.
    view._ch_dynamic_rev = 0
    view._ch_cache_rev = None
    view._ch_dynamic_nodes = []
    view._ch_transform_rows = []
    view._assets_rev = 0
    view._surface_dls = {}
    name = TEX_NAME if resolves else 0
    view._tex_mgr = type('T', (), {'get_gl_name': lambda self, i: name})()
    view._video_mgr = type('V', (), {'get_gl_name': lambda self, i: 0})()
    view._geo = type('G', (), {'draw': lambda self, *a, **k: None})()
    return view


def _run(monkeypatch, nodes, resolves=True, bound=()):
    rec = _GLRecorder()
    rec.install(monkeypatch)
    _viewport(nodes, resolves, bound)._draw_topology_overlays()
    return rec


# --- mode selection --------------------------------------------------------

def test_no_texture_id_keeps_vertex_colour(qapp, monkeypatch):
    """The pre-existing behaviour, unchanged: no texture_id, no texturing."""
    rec = _run(monkeypatch, _surface_scene(texture_id=0))
    assert not rec.texcoords()
    assert vp.GL_TEXTURE_2D not in [c[1] for c in rec.calls
                                    if c[0] == 'glEnable' and len(c) > 1]
    # 4 quads x 4 corners, each corner carrying its own colour.
    assert len(rec.vertex_colors()) == 16


def test_texture_id_switches_to_texturing(qapp, monkeypatch):
    rec = _run(monkeypatch, _surface_scene(texture_id=3))
    assert len(rec.texcoords()) == 16          # one per emitted corner
    assert ('glBindTexture', vp.GL_TEXTURE_2D, TEX_NAME) in rec.calls
    # A single white colour for the whole mesh, not one per corner: tinting
    # the image by each vertex's colour is exactly what we are replacing.
    assert rec.vertex_colors() == [(1.0, 1.0, 1.0, 1.0)]


def test_unresolvable_texture_falls_back_to_vertex_colour(qapp, monkeypatch):
    """A texture_id pointing at nothing must not leave a blank white sheet —
    it renders the way it did before the id was set."""
    rec = _run(monkeypatch, _surface_scene(texture_id=3), resolves=False)
    assert not rec.texcoords()
    assert len(rec.vertex_colors()) == 16


# --- UV correctness --------------------------------------------------------

def test_uv_matches_grid_convention(qapp, monkeypatch):
    """u grows with +x and v grows with +y, exactly as _grid_plate does.

    This is the assertion that catches a vertically flipped map: the same
    georeferenced image has to land the same way up on a flat World Grid and
    on a relief surface.
    """
    rec = _run(monkeypatch, _surface_scene(cols=3, rows=3, texture_id=3))
    for quad in rec.quads():
        for (u, v), (x, y, _z) in quad:
            assert u == pytest.approx(x / 10.0), f'u should track +x at {x},{y}'
            assert v == pytest.approx(y / 10.0), f'v should track +y at {x},{y}'


def test_lattice_corners_reach_the_image_corners(qapp, monkeypatch):
    """The picture spans the mesh's bounding box: no crop, no inset."""
    rec = _run(monkeypatch, _surface_scene(cols=4, rows=5, texture_id=3))
    uvs = rec.texcoords()
    us = [u for u, _ in uvs]
    vs = [v for _, v in uvs]
    assert min(us) == pytest.approx(0.0)
    assert max(us) == pytest.approx(1.0)
    assert min(vs) == pytest.approx(0.0)
    assert max(vs) == pytest.approx(1.0)


def test_interior_vertices_sit_at_their_true_fraction(qapp, monkeypatch):
    """A 5-column lattice puts its middle column at u = 0.5, not 0.4 or 0.6 —
    an off-by-one in the span would still pass the corner test above."""
    rec = _run(monkeypatch, _surface_scene(cols=5, rows=2, texture_id=3))
    seen = sorted({round(u, 6) for u, _ in rec.texcoords()})
    assert seen == [0.0, 0.25, 0.5, 0.75, 1.0]


def test_degenerate_lattice_does_not_divide_by_zero(qapp, monkeypatch):
    """All columns at one x would make the span zero. Guarded, and the mesh
    needs two distinct values per axis anyway, so it simply draws nothing."""
    nodes = _surface_scene(cols=3, rows=3, texture_id=3)
    for n in nodes[1:]:
        n.translate_x = 0.0
    rec = _run(monkeypatch, nodes)
    assert 'glVertex3f' not in rec.names()


# --- state hygiene ---------------------------------------------------------

def test_texturing_is_turned_back_off(qapp, monkeypatch):
    """Left enabled, it would tint every pass that follows in the same frame."""
    rec = _run(monkeypatch, _surface_scene(texture_id=3))
    assert rec.texture_events() == [True, False]


def test_texturing_modulates_so_lighting_still_shades_the_relief(qapp, monkeypatch):
    """REPLACE would paste a flat image over the mesh and throw away the
    shading that makes the terrain read as terrain."""
    rec = _run(monkeypatch, _surface_scene(texture_id=3))
    assert ('glTexEnvf', vp.GL_TEXTURE_ENV, vp.GL_TEXTURE_ENV_MODE,
            vp.GL_MODULATE) in rec.calls


# --- the mesh is retained, not re-emitted ---------------------------------
#
# Emitting an 11,400-vertex terrain per frame measured 404 ms of a 412 ms
# frame — 2.4 fps — because the whole quad stream is built in Python. These
# pin the display-list cache that fixed it, and the one case that must NOT be
# cached.

def test_static_mesh_is_emitted_once_and_replayed(qapp, monkeypatch):
    rec = _GLRecorder()
    rec.install(monkeypatch)
    view = _viewport(_surface_scene(cols=4, rows=4, texture_id=3))

    view._draw_topology_overlays()
    first = rec.names().count('glVertex3f')
    assert first == 36                       # 3x3 cells x 4 corners
    assert rec.names().count('glNewList') == 1

    before = len(rec.calls)
    view._draw_topology_overlays()
    later = [c[0] for c in rec.calls[before:]]
    assert 'glVertex3f' not in later, 'second frame re-emitted the mesh'
    assert 'glNewList' not in later
    assert later.count('glCallList') == 1


def test_channel_bound_surface_is_never_cached(qapp, monkeypatch):
    """Playback moves and recolours bound nodes WITHOUT bumping the scene
    revision, so a retained list would freeze the animation."""
    nodes = _surface_scene(cols=4, rows=4, texture_id=3)
    rec = _GLRecorder()
    rec.install(monkeypatch)
    view = _viewport(nodes, bound={nodes[3].id})     # one child is animated

    view._draw_topology_overlays()
    before = len(rec.calls)
    view._draw_topology_overlays()
    later = [c[0] for c in rec.calls[before:]]
    assert later.count('glVertex3f') == 36, 'animated mesh must re-emit'
    assert 'glNewList' not in later
    assert 'glCallList' not in later


def test_editing_the_scene_rebuilds_the_mesh(qapp, monkeypatch):
    """A cache that never invalidates is worse than no cache."""
    nodes = _surface_scene(cols=4, rows=4, texture_id=3)
    rec = _GLRecorder()
    rec.install(monkeypatch)
    view = _viewport(nodes)

    view._draw_topology_overlays()
    view._scene._revision += 1                # what a node edit does
    before = len(rec.calls)
    view._draw_topology_overlays()
    later = [c[0] for c in rec.calls[before:]]
    assert later.count('glVertex3f') == 36
    assert later.count('glNewList') == 1
    assert later.count('glDeleteLists') == 1, 'stale list must be freed'


def test_two_surfaces_do_not_leak_texturing_into_each_other(qapp, monkeypatch):
    """A textured surface followed by an untextured one: the second must draw
    with vertex colour, not with the first one's image still bound."""
    a = _surface_scene(cols=3, rows=3, texture_id=3)
    b = _surface_scene(cols=3, rows=3, texture_id=0)
    offset = 100
    for n in b:
        n.id += offset
        if n.parent_id:
            n.parent_id += offset
        n.translate_y += 50.0
    rec = _run(monkeypatch, a + b)
    # 32 corners in total; only the first surface's 16 carry texcoords.
    assert len(rec.texcoords()) == 16
    assert rec.texture_events() == [True, False]
    # White once for the textured mesh, then a real colour per corner.
    assert len(rec.vertex_colors()) == 1 + 16
