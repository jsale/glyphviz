"""Multi-material model import: MTL parsing, the material split, and the
node hierarchy a split becomes.

The load-bearing claim is the last one: parts that are re-assembled by the
REAL transform code land exactly where the un-split model would have. That is
checked against glyphviz_core.scene rather than against a restatement of the
composition rule, so a change to how GlyphViz composes transforms fails here
rather than silently relocating every imported model.
"""
import numpy as np
import pytest

from glyphviz_core import mesh_loader, model_import
from glyphviz_core.csv_reader import load_node_csv, save_node_csv
from glyphviz_core.geometry_data import GEO_MESH
from glyphviz_core.mesh_loader import (
    MaterialSpec, MeshPart, find_mtl, load_mesh_file, load_mesh_parts, parse_mtl,
)
from glyphviz_core.model_import import (
    IMAGE_EXTS, build_nodes, folder_ids, index_textures, match_by_name,
    plan_model, remap_ids, safe_name, write_assets,
)
from glyphviz_core.scene import Scene, node_world_matrix


# --- fixtures --------------------------------------------------------------

def _write_two_material_obj(folder, mtl_name='box.mtl', mtllib=None):
    """Two unit cubes, each its own material, 3 units apart along X."""
    lines = [f"mtllib {mtllib or mtl_name}"]
    verts = []
    faces = []

    def cube(cx, tag):
        base = len(verts)
        for dx in (-0.5, 0.5):
            for dy in (-0.5, 0.5):
                for dz in (-0.5, 0.5):
                    verts.append((cx + dx, dy, dz))
        quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1),
                 (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
        out = []
        for q in quads:
            a, b, c, d = (base + i + 1 for i in q)
            out.append(f"f {a} {b} {c}")
            out.append(f"f {a} {c} {d}")
        return tag, out

    for cx, tag in ((-1.5, 'left'), (1.5, 'right')):
        t, fs = cube(cx, tag)
        faces.append((t, fs))

    for v in verts:
        lines.append(f"v {v[0]} {v[1]} {v[2]}")
    for tag, fs in faces:
        lines.append(f"usemtl {tag}")
        lines.extend(fs)

    obj = folder / 'box.obj'
    obj.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return obj


MTL_TEXT = """\
# a comment
newmtl left
Kd 1.0 0.0 0.0
d 0.5
map_Kd left_diffuse.png

newmtl right
Kd 0.0 0.0 0.0
map_Kd -s 1 1 1 -o 0 0 0 C:\\authors\\drive\\right_diffuse.png
"""


# --- parse_mtl -------------------------------------------------------------

def test_parse_mtl_reads_colour_alpha_and_map():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / 'a.mtl'
        p.write_text(MTL_TEXT, encoding='utf-8')
        mats = parse_mtl(p)

    assert set(mats) == {'left', 'right'}
    assert mats['left'].diffuse == (255, 0, 0)
    assert mats['left'].alpha == 128
    assert mats['left'].texture == 'left_diffuse.png'
    # Options are skipped and only the BASE NAME of an absolute path survives:
    # the author's drive letter is never useful to us.
    assert mats['right'].texture == 'right_diffuse.png'


def test_parse_mtl_tr_is_inverted_d():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / 'a.mtl'
        p.write_text("newmtl x\nTr 0.25\n", encoding='utf-8')
        assert parse_mtl(p)['x'].alpha == 191   # 1 - 0.25


def test_black_kd_is_reported_as_unusable():
    assert MaterialSpec('a', diffuse=(0, 0, 0)).is_black
    assert MaterialSpec('a', diffuse=None).is_black
    assert not MaterialSpec('a', diffuse=(1, 0, 0)).is_black


# --- find_mtl --------------------------------------------------------------

def test_find_mtl_exact(tmp_path):
    obj = _write_two_material_obj(tmp_path)
    (tmp_path / 'box.mtl').write_text(MTL_TEXT, encoding='utf-8')
    assert find_mtl(obj).name == 'box.mtl'


def test_find_mtl_tolerates_space_underscore_drift(tmp_path):
    """The real failure this exists for: an exporter recorded 'Cargo
    Spaceship.mtl' beside a file shipped as Cargo_Spaceship.mtl, so a strict
    lookup produced a silently untextured, uncoloured import."""
    obj = _write_two_material_obj(tmp_path, mtllib='My Model.mtl')
    (tmp_path / 'My_Model.mtl').write_text(MTL_TEXT, encoding='utf-8')
    assert find_mtl(obj).name == 'My_Model.mtl'


def test_find_mtl_falls_back_to_sole_sibling(tmp_path):
    obj = _write_two_material_obj(tmp_path, mtllib='nothing-like-it.mtl')
    (tmp_path / 'renamed.mtl').write_text(MTL_TEXT, encoding='utf-8')
    assert find_mtl(obj).name == 'renamed.mtl'


def test_find_mtl_gives_up_when_ambiguous(tmp_path):
    obj = _write_two_material_obj(tmp_path, mtllib='nothing-like-it.mtl')
    (tmp_path / 'a.mtl').write_text(MTL_TEXT, encoding='utf-8')
    (tmp_path / 'b.mtl').write_text(MTL_TEXT, encoding='utf-8')
    assert find_mtl(obj) is None


# --- load_mesh_parts -------------------------------------------------------

def test_single_material_model_reports_no_split(tmp_path):
    """A caller can then fall back to load_mesh_file without special-casing."""
    obj = tmp_path / 'one.obj'
    obj.write_text(
        "v 0 0 0\nv 1 0 0\nv 0 1 0\nusemtl only\nf 1 2 3\n", encoding='utf-8')
    assert load_mesh_parts(obj) == []


def test_split_keeps_every_face_and_finds_materials(tmp_path):
    obj = _write_two_material_obj(tmp_path)
    (tmp_path / 'box.mtl').write_text(MTL_TEXT, encoding='utf-8')
    parts = load_mesh_parts(obj)

    assert {p.material for p in parts} == {'left', 'right'}
    assert sum(p.face_count for p in parts) == len(load_mesh_file(obj).faces)
    left = next(p for p in parts if p.material == 'left')
    assert left.spec is not None and left.spec.diffuse == (255, 0, 0)


def test_parts_are_ordered_largest_first(tmp_path):
    """Part order is node order, and a model reads far better when its hull is
    the first row rather than its running lights."""
    obj = tmp_path / 'uneven.obj'
    obj.write_text(
        "mtllib uneven.mtl\n"
        "v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\n"
        "usemtl small\nf 1 2 3\n"
        "usemtl big\nf 1 2 4\nf 1 3 4\nf 2 3 4\n", encoding='utf-8')
    (tmp_path / 'uneven.mtl').write_text(
        "newmtl small\nKd 1 1 1\nnewmtl big\nKd 1 1 1\n", encoding='utf-8')
    parts = load_mesh_parts(obj)
    assert [p.material for p in parts] == ['big', 'small']


def test_mesh_with_inconsistent_winding_still_imports(tmp_path):
    """Regression: trimesh's validate pass repairs face winding, and that one
    repair needs networkx -- an optional dependency this project does not
    carry. A mesh whose winding is already inconsistent reaches it, and the
    whole import used to die on ModuleNotFoundError rather than open."""
    obj = tmp_path / 'wound.obj'
    obj.write_text(
        "v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\n"
        "f 1 2 3\nf 1 2 4\nf 1 3 4\nf 2 3 4\n", encoding='utf-8')
    mesh = load_mesh_file(obj)
    assert len(mesh.faces) == 4
    assert len(mesh.vertices) == 4


# --- overlapping copies ----------------------------------------------------
#
# Found on a real purchased model: a Maya scene carrying both an object-level
# material and per-face-set materials exports BOTH assignments, so the OBJ
# ships several overlapping copies of the whole model. Rendered, they z-fight
# into a dense rib pattern and the catch-all copy hides the correctly-textured
# one under a single wrong image.

def _overlapping_obj(folder):
    """One triangle drawn under two materials, plus one the broad material
    holds alone -- the shape of the real failure in miniature."""
    obj = folder / 'dupe.obj'
    obj.write_text(
        "mtllib dupe.mtl\n"
        # shared surface, written twice with its OWN vertices each time
        "v 0 0 0\nv 1 0 0\nv 0 1 0\n"
        "v 0 0 0\nv 1 0 0\nv 0 1 0\n"
        # a surface only the broad material covers (the 'engines')
        "v 5 0 0\nv 6 0 0\nv 5 1 0\n"
        "usemtl detail\nf 1 2 3\n"
        "usemtl catchall\nf 4 5 6\nf 7 8 9\n",
        encoding='utf-8')
    (folder / 'dupe.mtl').write_text(
        "newmtl detail\nKd 1 0 0\nnewmtl catchall\nKd 0 1 0\n", encoding='utf-8')
    return obj


def test_coincident_copies_are_drawn_once(tmp_path):
    obj = _overlapping_obj(tmp_path)
    parts = load_mesh_parts(obj)
    assert sum(p.face_count for p in parts) == 2      # not 3


def test_the_specific_material_keeps_the_shared_surface(tmp_path):
    """The narrow assignment is the intent; the catch-all is the leftover."""
    obj = _overlapping_obj(tmp_path)
    by_mat = {p.material: p for p in load_mesh_parts(obj)}
    assert by_mat['detail'].face_count == 1
    assert by_mat['detail'].dropped_faces == 0


def test_the_broad_material_keeps_what_it_covers_alone(tmp_path):
    """The engines case: dedupe must not cost the model geometry no other
    material claims. On the real ship this was 3,340 triangles -- the whole
    engine assembly, which is what went missing when only the per-material
    copy was kept."""
    obj = _overlapping_obj(tmp_path)
    by_mat = {p.material: p for p in load_mesh_parts(obj)}
    assert by_mat['catchall'].face_count == 1
    assert by_mat['catchall'].dropped_faces == 1


def test_dedupe_loses_no_geometry(tmp_path):
    """The deduped parts still span exactly the model's own bounding box."""
    obj = _overlapping_obj(tmp_path)
    parts = load_mesh_parts(obj)
    reasm = np.vstack([p.mesh.vertices + np.asarray(p.translate, dtype=np.float32)
                       for p in parts])
    whole = load_mesh_file(obj).vertices
    assert np.allclose(reasm.min(axis=0), whole.min(axis=0), atol=1e-6)
    assert np.allclose(reasm.max(axis=0), whole.max(axis=0), atol=1e-6)


def test_dedupe_can_be_turned_off(tmp_path):
    obj = _overlapping_obj(tmp_path)
    parts = load_mesh_parts(obj, dedupe=False)
    assert sum(p.face_count for p in parts) == 3
    assert all(p.dropped_faces == 0 for p in parts)


def test_a_clean_model_is_not_touched(tmp_path):
    """No false positives: a model whose materials do not overlap keeps every
    face, so the guard can be on by default."""
    obj = _write_two_material_obj(tmp_path)
    (tmp_path / 'box.mtl').write_text(MTL_TEXT, encoding='utf-8')
    parts = load_mesh_parts(obj)
    assert sum(p.face_count for p in parts) == len(load_mesh_file(obj).faces)
    assert all(p.dropped_faces == 0 for p in parts)


def test_parts_without_a_findable_mtl_still_split(tmp_path):
    """The geometry split survives a missing .mtl -- only the NAMES are lost,
    because trimesh has nothing to read them from and falls back to the file
    name. Worth knowing: such an import is correct but poorly labelled."""
    obj = tmp_path / 'nomtl.obj'
    obj.write_text(
        "v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\n"
        "usemtl a\nf 1 2 3\n"
        "usemtl b\nf 1 2 4\nf 1 3 4\n", encoding='utf-8')
    parts = load_mesh_parts(obj)
    assert len(parts) == 2
    assert all(p.spec is None for p in parts)
    assert {'a', 'b'}.isdisjoint({p.material for p in parts})


def test_parts_reassemble_into_the_whole_model(tmp_path):
    """Part vertices plus their translate reproduce the un-split model exactly.

    This is the invariant the whole feature rests on: the split changes how a
    model is ADDRESSED, never where it is.
    """
    obj = _write_two_material_obj(tmp_path)
    (tmp_path / 'box.mtl').write_text(MTL_TEXT, encoding='utf-8')

    parts = load_mesh_parts(obj)
    reasm = np.vstack([p.mesh.vertices + np.asarray(p.translate, dtype=np.float32)
                       for p in parts])
    whole = load_mesh_file(obj).vertices

    assert np.allclose(reasm.min(axis=0), whole.min(axis=0), atol=1e-6)
    assert np.allclose(reasm.max(axis=0), whole.max(axis=0), atol=1e-6)


def test_part_radius_undoes_a_round_trip_through_a_file(tmp_path):
    """A part written out and reloaded is re-normalized onto its OWN bounding
    box. Its recorded radius is exactly what cancels that -- which is what
    stops every part arriving the same size."""
    obj = _write_two_material_obj(tmp_path)
    parts = load_mesh_parts(obj)

    for p in parts:
        f = tmp_path / f"{p.material}.obj"
        model_import.write_part_obj(p.mesh, f)
        back = load_mesh_file(f).vertices * p.radius
        assert np.allclose(back.min(axis=0), p.mesh.vertices.min(axis=0), atol=1e-5)
        assert np.allclose(back.max(axis=0), p.mesh.vertices.max(axis=0), atol=1e-5)


# --- texture matching ------------------------------------------------------

def test_match_by_name_prefers_a_colour_map(tmp_path):
    for n in ('Hull_Normal.png', 'Hull_Diffuse.png', 'Hull_Glossiness.png'):
        (tmp_path / n).touch()
    pool = index_textures(tmp_path)
    assert match_by_name(['Hull'], pool).name == 'Hull_Diffuse.png'


def test_match_by_name_prefers_the_shader_name_over_the_material(tmp_path):
    (tmp_path / 'ShipMain_Diffuse.png').touch()
    (tmp_path / 'lambert13SG_Diffuse.png').touch()
    pool = index_textures(tmp_path)
    assert match_by_name(['ShipMain', 'lambert13SG'], pool).name == 'ShipMain_Diffuse.png'


def test_index_textures_skips_tool_cache_folders(tmp_path):
    """Maya's .mayaSwatches and V-Ray's .vrayThumbs hold same-named
    thumbnails that would otherwise win a name match."""
    (tmp_path / '.vrayThumbs').mkdir()
    (tmp_path / '.vrayThumbs' / 'Hull_Diffuse.png').touch()
    (tmp_path / 'Hull_Diffuse.png').touch()
    pool = index_textures(tmp_path)
    assert [p.name for p in pool] == ['Hull_Diffuse.png']
    assert pool[0].parent == tmp_path


def test_plan_uses_map_kd_before_a_name_guess(tmp_path):
    obj = _write_two_material_obj(tmp_path)
    (tmp_path / 'box.mtl').write_text(MTL_TEXT, encoding='utf-8')
    (tmp_path / 'left_diffuse.png').touch()
    (tmp_path / 'left_Diffuse_other.png').touch()

    plan = plan_model(load_mesh_parts(obj), obj, index_textures(tmp_path))
    left = next(p for p in plan.parts if p.part.material == 'left')
    assert left.via == 'map_Kd'
    assert left.texture.name == 'left_diffuse.png'


def test_override_beats_a_name_guess_but_not_map_kd(tmp_path):
    obj = _write_two_material_obj(tmp_path)
    (tmp_path / 'box.mtl').write_text(MTL_TEXT, encoding='utf-8')
    # left's map_Kd is on disk; right's (right_diffuse.png) deliberately is not.
    for n in ('left_diffuse.png', 'chosen.png'):
        (tmp_path / n).touch()
    pool = index_textures(tmp_path)

    plan = plan_model(load_mesh_parts(obj), obj, pool,
                      overrides={'left': {'diffuse': 'chosen.png'},
                                 'right': {'diffuse': 'chosen.png'}})
    by_mat = {p.part.material: p for p in plan.parts}
    # left's own map_Kd resolves, so the file's own word wins over the override.
    assert by_mat['left'].via == 'map_Kd'
    assert by_mat['left'].texture.name == 'left_diffuse.png'
    # right's map_Kd names a file that is not there, so the override applies.
    assert by_mat['right'].via == 'override'
    assert by_mat['right'].texture.name == 'chosen.png'


def test_textured_parts_take_a_white_tint(tmp_path):
    """A textured node MULTIPLIES its colour into the texture, so anything
    but white darkens the image -- the bug that rendered a bark-textured
    grove black."""
    obj = _write_two_material_obj(tmp_path)
    (tmp_path / 'box.mtl').write_text(MTL_TEXT, encoding='utf-8')
    (tmp_path / 'left_diffuse.png').touch()

    plan = plan_model(load_mesh_parts(obj), obj, index_textures(tmp_path))
    left = next(p for p in plan.parts if p.part.material == 'left')
    assert left.color == model_import.TEXTURED_TINT


def test_black_kd_falls_back_to_grey_not_black(tmp_path):
    """Kd 0 0 0 across every material is what V-Ray/Arnold exporters write
    when the real shading lived in a node graph. Believing it imports a
    silhouette."""
    obj = _write_two_material_obj(tmp_path)
    (tmp_path / 'box.mtl').write_text(MTL_TEXT, encoding='utf-8')

    plan = plan_model(load_mesh_parts(obj), obj, [])
    right = next(p for p in plan.parts if p.part.material == 'right')
    assert right.texture is None
    assert right.color == model_import.NEUTRAL_GREY


def test_emissive_override_is_lifted_to_full_brightness(tmp_path):
    """A light material is an emitter GlyphViz cannot reproduce; its hue at
    full brightness at least reads as glowing colour. A non-emissive colour is
    taken at face value, however dim."""
    obj = _write_two_material_obj(tmp_path)
    (tmp_path / 'box.mtl').write_text(MTL_TEXT, encoding='utf-8')
    dim_blue = (0.0, 0.0518, 0.5)
    plan = plan_model(load_mesh_parts(obj), obj, [], overrides={
        'left': {'color': dim_blue, 'emissive': True},
        'right': {'color': dim_blue, 'emissive': False},
    })
    by_mat = {p.part.material: p for p in plan.parts}
    assert by_mat['left'].color == (0, 26, 255)     # hue kept, peak lifted to 255
    assert by_mat['right'].color == (0, 13, 128)    # unchanged, and dim


# --- folder ids and remapping ---------------------------------------------

def test_folder_ids_are_one_based_sorted_positions(tmp_path):
    for n in ('b.obj', 'a.obj', 'c.obj'):
        (tmp_path / n).touch()
    assert folder_ids(tmp_path) == {'a.obj': 1, 'b.obj': 2, 'c.obj': 3}


def test_remap_ids_carries_nodes_across_an_insertion():
    """Inserting a file shifts every id after it. Without the remap the scene
    silently wears the wrong images."""
    before = {'a.png': 1, 'c.png': 2}
    after = {'a.png': 1, 'b.png': 2, 'c.png': 3}
    nodes = [_node(1, texture_id=1), _node(2, texture_id=2), _node(3, texture_id=0)]

    moved = remap_ids(nodes, before, after, 'texture_id')
    assert moved == 1
    assert [n.texture_id for n in nodes] == [1, 3, 0]


def _node(nid, **kw):
    from glyphviz_core.node import Node
    base = dict(id=nid, type=5, parent_id=0, branch_level=0,
                translate_x=0.0, translate_y=0.0, translate_z=0.0,
                rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
                scale_x=1.0, scale_y=1.0, scale_z=1.0,
                color_r=1, color_g=1, color_b=1, color_a=255,
                geometry=1, hide=0, topo=0)
    base.update(kw)
    return Node(**base)


def test_safe_name_survives_awkward_material_names():
    assert safe_name('Ship/Main:1') == 'Ship_Main_1'
    assert safe_name('///') == 'part'


# --- the hierarchy ---------------------------------------------------------

def test_build_nodes_shape(tmp_path):
    obj = _write_two_material_obj(tmp_path)
    (tmp_path / 'box.mtl').write_text(MTL_TEXT, encoding='utf-8')
    plan = plan_model(load_mesh_parts(obj), obj, [])
    write_assets(plan, tmp_path / 'meshes', tmp_path / 'media')

    nodes = build_nodes(plan, first_id=7,
                        mesh_ids=folder_ids(tmp_path / 'meshes'),
                        texture_ids={}, label='box')

    rig, *parts = nodes
    assert rig.id == 7 and rig.hide == 1 and rig.parent_id == 0
    assert all(p.parent_id == rig.id for p in parts)
    assert all(p.geometry == GEO_MESH and p.mesh_id > 0 for p in parts)
    # The rig is hidden and the tag pass only labels what it DRAWS, so the
    # model's name has to ride on the first visible part instead.
    assert rig.text == ''
    assert parts[0].text == 'box'


def test_y_up_model_is_stood_up_by_the_rig_alone(tmp_path):
    obj = _write_two_material_obj(tmp_path)
    plan = plan_model(load_mesh_parts(obj), obj, [])
    y_up = build_nodes(plan, 1, {}, {}, up_axis='y')
    z_up = build_nodes(plan, 1, {}, {}, up_axis='z')

    assert y_up[0].rotate_x == model_import.Y_UP_RIG_ROTATION
    assert z_up[0].rotate_x == 0.0
    # Only the rig differs -- no vertex and no child is touched.
    assert [(n.translate_x, n.scale_x) for n in y_up[1:]] == \
           [(n.translate_x, n.scale_x) for n in z_up[1:]]


def test_assembled_nodes_reproduce_the_model_through_the_real_transform(tmp_path):
    """End to end, and the reason the feature is trustworthy: run the written
    parts back through glyphviz_core.scene and the assembled bounding box is
    the un-split model's, scaled by the rig. Checked against the real
    transform code, not against a restatement of it.
    """
    obj = _write_two_material_obj(tmp_path)
    (tmp_path / 'box.mtl').write_text(MTL_TEXT, encoding='utf-8')

    parts = load_mesh_parts(obj)
    plan = plan_model(parts, obj, [])
    mesh_dir, media_dir = tmp_path / 'meshes', tmp_path / 'media'
    write_assets(plan, mesh_dir, media_dir)

    rig_scale = 4.0
    nodes = build_nodes(plan, first_id=1, mesh_ids=folder_ids(mesh_dir),
                        texture_ids={}, rig_scale=rig_scale, up_axis='z')

    scene = Scene(nodes, base_scale=1.0)
    names = sorted(q.name for q in mesh_dir.iterdir())

    lo = np.full(3, np.inf)
    hi = np.full(3, -np.inf)
    for n in nodes:
        if n.mesh_id == 0:
            continue
        v = load_mesh_file(mesh_dir / names[n.mesh_id - 1]).vertices
        M = np.asarray(node_world_matrix(n, scene), dtype=np.float64)
        w = (np.hstack([v, np.ones((len(v), 1))]) @ M.T)[:, :3]
        lo = np.minimum(lo, w.min(axis=0))
        hi = np.maximum(hi, w.max(axis=0))

    whole = load_mesh_file(obj).vertices
    assert np.allclose(lo, whole.min(axis=0) * rig_scale, atol=1e-4)
    assert np.allclose(hi, whole.max(axis=0) * rig_scale, atol=1e-4)


def test_imported_hierarchy_survives_a_csv_round_trip(tmp_path):
    obj = _write_two_material_obj(tmp_path)
    plan = plan_model(load_mesh_parts(obj), obj, [])
    write_assets(plan, tmp_path / 'meshes', tmp_path / 'media')
    nodes = build_nodes(plan, 1, folder_ids(tmp_path / 'meshes'), {},
                        rig_scale=3.0, label='box')

    csv = tmp_path / 'gv_node.csv'
    save_node_csv(nodes, str(csv))
    back = load_node_csv(str(csv))

    assert len(back) == len(nodes)
    for a, b in zip(nodes, back):
        assert a.id == b.id and a.parent_id == b.parent_id
        assert a.mesh_id == b.mesh_id and a.hide == b.hide
        assert a.scale_x == pytest.approx(b.scale_x, abs=1e-6)
        assert a.translate_z == pytest.approx(b.translate_z, abs=1e-6)
        assert a.rotate_x == pytest.approx(b.rotate_x, abs=1e-6)
