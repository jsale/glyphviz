"""Multi-material model import through the real window.

The planning and node math are pinned in tests/test_model_import.py. What is
pinned here is the wiring: that the menu path writes the scene's asset folders,
adds the hierarchy to the live scene, and -- the part most likely to go wrong
silently -- re-points every node that was already in the scene when inserting
files renumbers the folders underneath it.

Qt is needed but a GL context is not, so these run headless (same arrangement
as tests/test_placement_gui.py).
"""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtWidgets import QApplication                # noqa: E402

from glyphviz_core.geometry_data import GEO_MESH          # noqa: E402
from glyphviz_core.node import Node                       # noqa: E402
from glyphviz_gl import main_window as mw                 # noqa: E402


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication([])
        except Exception as exc:                          # pragma: no cover
            pytest.skip(f'Qt unavailable: {exc}')
    return app


def _node(**overrides):
    base = dict(
        id=1, type=5, parent_id=0, branch_level=0,
        translate_x=0.0, translate_y=0.0, translate_z=0.0,
        rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=200, color_g=200, color_b=200, color_a=255,
        geometry=3, hide=0, topo=0,
    )
    base.update(overrides)
    return Node(**base)


def _model(folder, stem='ship'):
    """A two-material OBJ with a matching MTL and one real texture file."""
    verts, faces = [], []
    for cx, tag in ((-1.5, 'hull'), (1.5, 'pod')):
        base = len(verts)
        for dx in (-0.5, 0.5):
            for dy in (-0.5, 0.5):
                for dz in (-0.5, 0.5):
                    verts.append((cx + dx, dy, dz))
        quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1),
                 (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
        tris = []
        for q in quads:
            a, b, c, d = (base + i + 1 for i in q)
            tris += [f"f {a} {b} {c}", f"f {a} {c} {d}"]
        faces.append((tag, tris))

    lines = [f"mtllib {stem}.mtl"]
    lines += [f"v {v[0]} {v[1]} {v[2]}" for v in verts]
    for tag, tris in faces:
        lines.append(f"usemtl {tag}")
        lines += tris

    obj = folder / f'{stem}.obj'
    obj.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (folder / f'{stem}.mtl').write_text(
        "newmtl hull\nKd 0.8 0.2 0.2\nmap_Kd hull_diffuse.png\n"
        "newmtl pod\nKd 0.2 0.2 0.8\n", encoding='utf-8')
    _png(folder / 'hull_diffuse.png')
    return obj


def _png(path):
    """A real 1x1 PNG -- the importer copies files, and media/ ids count only
    files that are actually there."""
    import base64
    path.write_bytes(base64.b64decode(
        b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8'
        b'z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='))


def _win(nodes=None, current_path=None):
    win = mw.MainWindow()
    win.nodes = list(nodes or [])
    win._viewport.set_nodes(win.nodes)
    win._table.set_nodes(win.nodes)
    win._current_path = current_path
    return win


# --- the import ------------------------------------------------------------

def test_import_builds_a_rig_and_one_node_per_material(qapp, tmp_path):
    obj = _model(tmp_path)
    win = _win(current_path=str(tmp_path / 'scene_gv_node.csv'))

    assert win._load_model_parts(str(obj)) is True

    assert len(win.nodes) == 3                       # rig + hull + pod
    rig, *parts = win.nodes
    assert rig.hide == 1 and rig.parent_id == 0
    assert {p.parent_id for p in parts} == {rig.id}
    assert all(p.geometry == GEO_MESH and p.mesh_id > 0 for p in parts)


def test_import_writes_the_scene_asset_folders(qapp, tmp_path):
    obj = _model(tmp_path)
    win = _win(current_path=str(tmp_path / 'scene_gv_node.csv'))
    win._load_model_parts(str(obj))

    meshes = sorted(q.name for q in (tmp_path / 'meshes').iterdir())
    media = sorted(q.name for q in (tmp_path / 'media').iterdir())
    assert len(meshes) == 2
    assert all(n.endswith('.obj') and n.startswith('ship_') for n in meshes)
    # Only the material that actually named a map_Kd brings an image across.
    assert media == ['hull_diffuse.png']


def test_the_textured_part_points_at_the_copied_image(qapp, tmp_path):
    obj = _model(tmp_path)
    win = _win(current_path=str(tmp_path / 'scene_gv_node.csv'))
    win._load_model_parts(str(obj))

    by_text = {n.text: n for n in win.nodes if n.mesh_id}
    hull = next(n for n in win.nodes if n.mesh_id and n.texture_id)
    assert hull.texture_id == 1
    # A textured node multiplies its colour into the image, so it must be white.
    assert (hull.color_r, hull.color_g, hull.color_b) == (255, 255, 255)
    # The untextured one keeps its own Kd rather than going grey.
    pod = next(n for n in win.nodes if n.mesh_id and not n.texture_id)
    assert (pod.color_r, pod.color_g, pod.color_b) == (51, 51, 204)


def test_import_repoints_existing_nodes_when_media_renumbers(qapp, tmp_path):
    """The silent-corruption case. texture_id and mesh_id are POSITIONS in a
    sorted folder, so inserting a file that sorts first shifts everything
    after it -- and the scene already open would quietly wear the wrong
    images and the wrong shapes."""
    media = tmp_path / 'media'
    media.mkdir()
    _png(media / 'zebra.png')                # sorts AFTER hull_diffuse.png
    meshes = tmp_path / 'meshes'
    meshes.mkdir()
    (meshes / 'zz_existing.obj').write_text(
        "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding='utf-8')

    existing = _node(id=1, texture_id=1, mesh_id=1, geometry=GEO_MESH)
    obj = _model(tmp_path)
    win = _win([existing], current_path=str(tmp_path / 'scene_gv_node.csv'))
    win._load_model_parts(str(obj))

    # hull_diffuse.png now sorts first, so zebra.png moved 1 -> 2; likewise
    # ship_00/ship_01 sort before zz_existing.obj, which moved 1 -> 3.
    assert existing.texture_id == 2
    assert existing.mesh_id == 3


def test_single_material_model_falls_back_to_the_plain_import(qapp, tmp_path):
    obj = tmp_path / 'one.obj'
    obj.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding='utf-8')
    win = _win(current_path=str(tmp_path / 'scene_gv_node.csv'))

    win._load_model_parts(str(obj))

    # One ordinary node, not a rig-and-parts hierarchy.
    assert len(win.nodes) == 1
    assert win.nodes[0].geometry == GEO_MESH
    assert win.nodes[0].hide == 0


def test_import_does_not_disturb_an_unrelated_node(qapp, tmp_path):
    obj = _model(tmp_path)
    other = _node(id=1, texture_id=0, mesh_id=0)
    win = _win([other], current_path=str(tmp_path / 'scene_gv_node.csv'))
    win._load_model_parts(str(obj))

    assert other.texture_id == 0 and other.mesh_id == 0
    assert win.nodes[0] is other
    # New ids start past whatever was already loaded.
    assert min(n.id for n in win.nodes[1:]) == 2
