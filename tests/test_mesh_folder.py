"""
The meshes/ folder convention (2026-09-17).

A scene's `mesh_id` used to mean "the Nth file imported by hand this session",
which is not a property of the scene file at all — so a CSV using GEO_MESH
could not be reopened, let alone sent to anyone. It now means the same thing
`texture_id` has always meant: **the file's 1-based position in a folder
beside the node CSV, sorted by name**.

Positional ids are unforgiving and that is what these tests are about: one
stray file sorting early shifts every id after it, and the scene still opens,
wearing the wrong shapes. So the sort order, the numbering from 1, and the
treatment of a file that fails to parse are each pinned separately.

Qt is needed (Viewport is a QOpenGLWidget) but a GL context is not: the
display-list calls are stubbed, the same arrangement
tests/test_interior_geometry.py uses.
"""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')
trimesh = pytest.importorskip('trimesh')

from PySide6.QtWidgets import QApplication          # noqa: E402

from glyphviz_core.mesh_loader import SUPPORTED_EXTENSIONS   # noqa: E402


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication([])
        except Exception as exc:                     # pragma: no cover
            pytest.skip(f'Qt unavailable: {exc}')
    return app


@pytest.fixture
def vp(qapp, monkeypatch):
    """A Viewport with the GL-touching parts of mesh import stubbed out."""
    from glyphviz_gl.viewport import Viewport

    v = Viewport()
    monkeypatch.setattr(v, 'makeCurrent', lambda: None)
    monkeypatch.setattr(v, 'update', lambda: None)
    monkeypatch.setattr(v._geo, 'setup', lambda: None)
    registered: list[tuple[int, str]] = []
    monkeypatch.setattr(v._geo, 'register_mesh',
                        lambda mid, mesh: registered.append((mid, mesh.name)))
    v.registered = registered
    return v


def _write_box(path, size=1.0):
    trimesh.creation.box(extents=(size, size, size)).export(str(path))


# --- the numbering rule -----------------------------------------------------

def test_mesh_ids_are_sorted_positions(vp, tmp_path):
    folder = tmp_path / 'meshes'
    folder.mkdir()
    # written out of order on purpose
    for name in ('zulu.obj', 'alpha.obj', 'mike.obj'):
        _write_box(folder / name)

    ids = vp.load_mesh_folder(folder)
    assert ids == [1, 2, 3]
    assert vp.registered == [(1, 'alpha'), (2, 'mike'), (3, 'zulu')]
    assert vp.mesh_name(1) == 'alpha'
    assert vp.mesh_name(3) == 'zulu'


def test_ids_survive_a_reload(vp, tmp_path):
    """Reopening the same scene must hand out the same ids — that is the
    entire point of the feature."""
    folder = tmp_path / 'meshes'
    folder.mkdir()
    for name in ('b.obj', 'a.obj'):
        _write_box(folder / name)

    first = vp.load_mesh_folder(folder)
    names_first = {i: vp.mesh_name(i) for i in first}
    vp.registered.clear()
    second = vp.load_mesh_folder(folder)
    assert first == second
    assert {i: vp.mesh_name(i) for i in second} == names_first


def test_a_new_file_shifts_the_ids_after_it(vp, tmp_path):
    """Not a bug to fix — a documented consequence of positional ids, pinned
    here so nobody 'fixes' the sort into something order-dependent. It is why
    gvscene.SceneBuilder verifies the folder against the CSV at write time."""
    folder = tmp_path / 'meshes'
    folder.mkdir()
    _write_box(folder / 'b.obj')
    _write_box(folder / 'c.obj')
    assert vp.load_mesh_folder(folder) == [1, 2]
    assert vp.mesh_name(1) == 'b'

    _write_box(folder / 'a.obj')
    vp.load_mesh_folder(folder)
    assert vp.mesh_name(1) == 'a'
    assert vp.mesh_name(2) == 'b'


def test_non_mesh_files_are_ignored(vp, tmp_path):
    folder = tmp_path / 'meshes'
    folder.mkdir()
    _write_box(folder / 'model.obj')
    (folder / 'notes.txt').write_text('not a mesh')
    (folder / 'thumb.png').write_bytes(b'\x89PNG\r\n\x1a\n')

    assert vp.load_mesh_folder(folder) == [1]
    assert vp.mesh_name(1) == 'model'


def test_every_supported_extension_is_picked_up(vp, tmp_path):
    folder = tmp_path / 'meshes'
    folder.mkdir()
    box = trimesh.creation.box(extents=(1, 1, 1))
    written = []
    for ext in ('.obj', '.stl', '.ply'):
        assert ext in SUPPORTED_EXTENSIONS
        p = folder / f'm{ext}'
        box.export(str(p))
        written.append(p)
    assert len(vp.load_mesh_folder(folder)) == len(written)


def test_missing_folder_is_not_an_error(vp, tmp_path):
    assert vp.load_mesh_folder(tmp_path / 'nope') == []


def test_a_broken_file_is_skipped_but_still_counted(vp, tmp_path):
    """A file that will not parse must not cost the scene every mesh after
    it. It is skipped, but the NUMBERING still counts it — otherwise every
    later model would silently shift by one and the scene would open wearing
    the wrong shapes, which is far worse than one missing object."""
    folder = tmp_path / 'meshes'
    folder.mkdir()
    _write_box(folder / 'a.obj')
    (folder / 'b.obj').write_text('this is not an OBJ file at all\n')
    _write_box(folder / 'c.obj')

    ids = vp.load_mesh_folder(folder)
    assert ids == [1, 3], "the broken file must still consume id 2"
    assert vp.mesh_name(1) == 'a'
    assert vp.mesh_name(3) == 'c'


def test_hand_import_after_a_folder_gets_a_fresh_id(vp, tmp_path, monkeypatch):
    """Meshes/ claims 1..N; a later Meshes > Import Mesh File… must not
    collide with one of them."""
    folder = tmp_path / 'meshes'
    folder.mkdir()
    for name in ('a.obj', 'b.obj'):
        _write_box(folder / name)
    assert vp.load_mesh_folder(folder) == [1, 2]

    extra = tmp_path / 'extra.obj'
    _write_box(extra)
    assert vp.load_mesh_file(str(extra)) == 3


def test_reimporting_a_folder_mesh_by_hand_reuses_its_id(vp, tmp_path):
    """load_mesh_file dedupes on resolved path, and load_mesh_folder records
    those paths — so dragging in a file the scene folder already supplied
    refreshes it rather than making a second entry."""
    folder = tmp_path / 'meshes'
    folder.mkdir()
    _write_box(folder / 'a.obj')
    _write_box(folder / 'b.obj')
    vp.load_mesh_folder(folder)

    assert vp.load_mesh_file(str(folder / 'b.obj')) == 2


def test_sort_is_case_sensitive_and_platform_independent(vp, tmp_path):
    """mesh_id order must not depend on the OS.

    `sorted(folder.iterdir())` looks right and is a trap: pathlib compares
    paths case-INSENSITIVELY on Windows and case-sensitively everywhere else,
    so the same folder hands out different ids on different machines — and a
    scene's ids are supposed to travel. Sorting the NAME as a plain string
    pins the case-sensitive order, which is also what GlyphViz Web follows.
    """
    folder = tmp_path / 'meshes'
    folder.mkdir()
    for name in ('alpha.obj', 'Beta.obj', 'Zulu.obj'):
        _write_box(folder / name)

    vp.load_mesh_folder(folder)
    # ASCII order: uppercase before lowercase.
    assert [vp.mesh_name(i) for i in (1, 2, 3)] == ['Beta', 'Zulu', 'alpha']
