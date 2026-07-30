"""
Drag-and-drop routing unit tests.

The contract (see glyphviz_core/drop_router.py): a drop is resolved into an
ordered plan of load actions WITHOUT touching Qt, so the interesting decisions
are testable headlessly. The decisions under test:

  * a node CSV is recognised by its COLUMNS, not its name — so an arbitrarily
    named scene file loads and gv_tag.csv / gv_ch-map.csv / gv_ch-tracks.csv
    are never mistaken for one;
  * a dropped folder or zip resolves to the node CSV inside it, which is all
    that's needed because every companion (tag, channels, media/) is
    discovered from that path by the existing loaders;
  * a zip extracts beside itself, refusing entries that would escape the
    destination ("zip slip");
  * several node CSVs in one drop open the first and merge the rest, and Shift
    (merge=True) makes even the first one merge.
"""
import csv
import io
import zipfile
from pathlib import Path

import pytest

from glyphviz_core.drop_router import (
    ACTION_MERGE_CSV, ACTION_MESH, ACTION_OPEN_CSV, ACTION_PDB, ACTION_TEXTURES,
    ZipExtractError, can_accept, extract_zip, find_node_csvs, looks_like_node_csv,
    resolve_drop,
)

# The columns load_node_csv indexes unconditionally.
_NODE_COLS = [
    'id', 'type', 'parent_id', 'branch_level',
    'translate_x', 'translate_y', 'translate_z',
    'rotate_x', 'rotate_y', 'rotate_z',
    'scale_x', 'scale_y', 'scale_z',
    'color_r', 'color_g', 'color_b', 'color_a',
    'geometry', 'hide', 'topo',
]


def _write_node_csv(path: Path, rows: int = 1):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(_NODE_COLS)
        for i in range(rows):
            w.writerow([i + 1, 5, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1,
                        255, 255, 255, 255, 3, 0, 0])
    return path


def _write_csv(path: Path, header: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        csv.writer(fh).writerow(header)
    return path


def _kinds(plan):
    return [a.kind for a in plan.actions]


# --- node-CSV detection ------------------------------------------------------

def test_node_csv_recognised_by_columns_not_name(tmp_path):
    """An arbitrarily named file with the right columns is a node CSV."""
    odd = _write_node_csv(tmp_path / 'some_export.csv')
    assert looks_like_node_csv(odd)


def test_companion_files_are_not_node_csvs(tmp_path):
    """The three companions share a folder with the node file and must never
    be mistaken for it — each lacks the required transform columns."""
    tag = _write_csv(tmp_path / 'gv_tag.csv', ['table_id', 'record_id', 'title'])
    ch_map = _write_csv(tmp_path / 'gv_ch-map.csv', ['channel_id', 'track_id', 'attribute'])
    tracks = _write_csv(tmp_path / 'gv_ch-tracks.csv', ['frame', 'ch1', 'ch2'])
    for p in (tag, ch_map, tracks):
        assert not looks_like_node_csv(p), p.name


def test_gaiaviz_np_dialect_recognised(tmp_path):
    """csv_reader renames the np_ dialect on load, so the sniff has to accept
    np_node_id in place of id."""
    p = _write_csv(tmp_path / 'np_node.csv', [
        'np_node_id', 'type', 'parent_id', 'translate_x', 'translate_y', 'translate_z',
    ])
    assert looks_like_node_csv(p)


def test_convention_named_file_wins_over_arbitrary_one(tmp_path):
    _write_node_csv(tmp_path / 'unrelated_export.csv')
    _write_node_csv(tmp_path / 'gv_node.csv')
    assert find_node_csvs(tmp_path)[0].name == 'gv_node.csv'


def test_newest_stamped_save_wins(tmp_path):
    """A folder of timestamped saves opens the most recent."""
    _write_node_csv(tmp_path / 'gv_node20260625182432.csv')
    _write_node_csv(tmp_path / 'gv_node20260730090000.csv')
    _write_node_csv(tmp_path / 'gv_node20260101000000.csv')
    assert find_node_csvs(tmp_path)[0].name == 'gv_node20260730090000.csv'


def test_find_node_csvs_is_not_recursive(tmp_path):
    """A nested search would turn one drop into an arbitrary scene choice."""
    _write_node_csv(tmp_path / 'sub' / 'gv_node.csv')
    assert find_node_csvs(tmp_path) == []


# --- single-file drops -------------------------------------------------------

def test_drop_node_csv_opens_it(tmp_path):
    p = _write_node_csv(tmp_path / 'gv_node.csv')
    plan = resolve_drop([str(p)])
    assert _kinds(plan) == [ACTION_OPEN_CSV]
    assert plan.actions[0].path == p


def test_drop_companion_csv_redirects_to_its_node_file(tmp_path):
    """Grabbing gv_tag.csv by mistake should still open the scene."""
    node = _write_node_csv(tmp_path / 'gv_node.csv')
    tag = _write_csv(tmp_path / 'gv_tag.csv', ['table_id', 'record_id', 'title'])
    plan = resolve_drop([str(tag)])
    assert _kinds(plan) == [ACTION_OPEN_CSV]
    assert plan.actions[0].path == node
    assert any('companion' in n for n in plan.notes)


def test_drop_lone_companion_csv_errors(tmp_path):
    """No node file to redirect to — say so rather than trying to load it."""
    tag = _write_csv(tmp_path / 'gv_tag.csv', ['table_id', 'record_id', 'title'])
    plan = resolve_drop([str(tag)])
    assert plan.is_empty
    assert plan.errors


def test_drop_pdb_and_mesh(tmp_path):
    pdb = tmp_path / 'protein.pdb'
    pdb.write_text('ATOM\n', encoding='utf-8')
    mesh = tmp_path / 'thing.obj'
    mesh.write_text('v 0 0 0\n', encoding='utf-8')
    assert _kinds(resolve_drop([str(pdb)])) == [ACTION_PDB]
    assert _kinds(resolve_drop([str(mesh)])) == [ACTION_MESH]


def test_dropped_image_loads_its_whole_folder(tmp_path):
    """texture_id indexes the folder's sorted contents, so a single image
    still means 'load this folder'."""
    media = tmp_path / 'media'
    media.mkdir()
    img = media / 'a.png'
    img.write_bytes(b'\x89PNG\r\n\x1a\n')
    plan = resolve_drop([str(img)])
    assert _kinds(plan) == [ACTION_TEXTURES]
    assert plan.actions[0].path == media


def test_missing_path_reports_error(tmp_path):
    plan = resolve_drop([str(tmp_path / 'nope.csv')])
    assert plan.is_empty
    assert 'not found' in plan.errors[0]


def test_unsupported_file_reports_error(tmp_path):
    p = tmp_path / 'notes.docx'
    p.write_text('x', encoding='utf-8')
    plan = resolve_drop([str(p)])
    assert plan.is_empty
    assert 'unsupported' in plan.errors[0]


# --- folder drops ------------------------------------------------------------

def test_drop_folder_finds_its_node_csv(tmp_path):
    folder = tmp_path / 'My_Example'
    node = _write_node_csv(folder / 'gv_node.csv')
    _write_csv(folder / 'gv_tag.csv', ['table_id', 'record_id', 'title'])
    _write_csv(folder / 'gv_ch-map.csv', ['channel_id', 'track_id', 'attribute'])
    plan = resolve_drop([str(folder)])
    # Only the node CSV is actioned — the loader picks up the rest itself.
    assert _kinds(plan) == [ACTION_OPEN_CSV]
    assert plan.actions[0].path == node


def test_drop_media_only_folder_loads_textures(tmp_path):
    folder = tmp_path / 'media'
    folder.mkdir()
    (folder / 'a.png').write_bytes(b'\x89PNG\r\n\x1a\n')
    plan = resolve_drop([str(folder)])
    assert _kinds(plan) == [ACTION_TEXTURES]


def test_drop_empty_folder_errors(tmp_path):
    folder = tmp_path / 'empty'
    folder.mkdir()
    plan = resolve_drop([str(folder)])
    assert plan.is_empty
    assert plan.errors


def test_multiple_node_csvs_in_a_folder_note_the_choice(tmp_path):
    folder = tmp_path / 'Scene'
    _write_node_csv(folder / 'gv_node.csv')
    _write_node_csv(folder / 'other.csv')
    plan = resolve_drop([str(folder)])
    assert _kinds(plan) == [ACTION_OPEN_CSV]
    assert any('2 node CSVs' in n for n in plan.notes)


# --- zip drops ---------------------------------------------------------------

def _make_zip(path: Path, entries: dict[str, str]):
    with zipfile.ZipFile(path, 'w') as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return path


def _node_csv_text(rows: int = 1) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator='\n')
    w.writerow(_NODE_COLS)
    for i in range(rows):
        w.writerow([i + 1, 5, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1,
                    255, 255, 255, 255, 3, 0, 0])
    return buf.getvalue()


def test_zip_extracts_beside_itself_and_opens_the_scene(tmp_path):
    z = _make_zip(tmp_path / 'Example.zip', {
        'gv_node.csv': _node_csv_text(),
        'gv_tag.csv': 'table_id,record_id,title\n',
    })
    plan = resolve_drop([str(z)])
    assert _kinds(plan) == [ACTION_OPEN_CSV]
    opened = plan.actions[0].path
    assert opened.name == 'gv_node.csv'
    # Beside the zip, not in temp — so a later Save lands somewhere durable.
    assert opened.parent.parent == tmp_path
    assert not plan.temp_dirs
    # The companion came out too, next to the node file where the loader looks.
    assert (opened.parent / 'gv_tag.csv').exists()


def test_zip_with_single_wrapper_folder_is_stepped_through(tmp_path):
    """Archives are usually zipped from the parent, putting everything one
    level down."""
    z = _make_zip(tmp_path / 'Example.zip', {
        'Example/gv_node.csv': _node_csv_text(),
    })
    plan = resolve_drop([str(z)])
    assert _kinds(plan) == [ACTION_OPEN_CSV]
    assert plan.actions[0].path.name == 'gv_node.csv'


def test_zip_extraction_does_not_overwrite_an_existing_folder(tmp_path):
    (tmp_path / 'Example').mkdir()
    (tmp_path / 'Example' / 'precious.txt').write_text('keep me', encoding='utf-8')
    z = _make_zip(tmp_path / 'Example.zip', {'gv_node.csv': _node_csv_text()})
    plan = resolve_drop([str(z)])
    assert (tmp_path / 'Example' / 'precious.txt').read_text(encoding='utf-8') == 'keep me'
    assert plan.actions[0].path.parent != (tmp_path / 'Example')


def test_zip_slip_parent_path_is_refused(tmp_path):
    z = tmp_path / 'evil.zip'
    with zipfile.ZipFile(z, 'w') as zf:
        zf.writestr('../escaped.csv', _node_csv_text())
    plan = resolve_drop([str(z)])
    assert plan.is_empty
    assert not (tmp_path.parent / 'escaped.csv').exists()
    with pytest.raises(ZipExtractError):
        extract_zip(z)


def test_zip_slip_absolute_path_is_refused(tmp_path):
    z = tmp_path / 'evil2.zip'
    with zipfile.ZipFile(z, 'w') as zf:
        zf.writestr('/tmp/escaped.csv', _node_csv_text())
    with pytest.raises(ZipExtractError):
        extract_zip(z)


def test_empty_zip_is_refused(tmp_path):
    z = tmp_path / 'empty.zip'
    with zipfile.ZipFile(z, 'w'):
        pass
    with pytest.raises(ZipExtractError):
        extract_zip(z)


def test_zip_without_a_node_csv_errors(tmp_path):
    z = _make_zip(tmp_path / 'docs.zip', {'readme.txt': 'hello'})
    plan = resolve_drop([str(z)])
    assert plan.is_empty
    assert 'no node CSV' in plan.errors[0]


def test_corrupt_zip_reports_an_error(tmp_path):
    z = tmp_path / 'broken.zip'
    z.write_bytes(b'not a zip at all')
    plan = resolve_drop([str(z)])
    assert plan.is_empty
    assert plan.errors


def test_zip_falling_back_to_temp_warns_about_saves(tmp_path, monkeypatch):
    """A read-only location forces temp extraction; the user needs to know
    their edits would go somewhere disposable."""
    monkeypatch.setattr('glyphviz_core.drop_router._writable', lambda folder: False)
    z = _make_zip(tmp_path / 'Example.zip', {'gv_node.csv': _node_csv_text()})
    plan = resolve_drop([str(z)])
    assert _kinds(plan) == [ACTION_OPEN_CSV]
    assert plan.temp_dirs
    assert any('Save As' in n for n in plan.notes)


# --- multi-item drops and merge ---------------------------------------------

def test_two_node_csvs_open_the_first_and_merge_the_rest(tmp_path):
    a = _write_node_csv(tmp_path / 'a' / 'gv_node.csv')
    b = _write_node_csv(tmp_path / 'b' / 'gv_node.csv')
    plan = resolve_drop([str(a), str(b)])
    assert _kinds(plan) == [ACTION_OPEN_CSV, ACTION_MERGE_CSV]
    assert [x.path for x in plan.actions] == [a, b]


def test_shift_drop_merges_the_first_file_too(tmp_path):
    a = _write_node_csv(tmp_path / 'a' / 'gv_node.csv')
    b = _write_node_csv(tmp_path / 'b' / 'gv_node.csv')
    plan = resolve_drop([str(a), str(b)], merge=True)
    assert _kinds(plan) == [ACTION_MERGE_CSV, ACTION_MERGE_CSV]


def test_pdb_is_skipped_when_a_node_csv_is_dropped_too(tmp_path):
    """Both are whole-scene replacements; the CSV wins and the PDB is noted."""
    node = _write_node_csv(tmp_path / 'gv_node.csv')
    pdb = tmp_path / 'protein.pdb'
    pdb.write_text('ATOM\n', encoding='utf-8')
    plan = resolve_drop([str(node), str(pdb)])
    assert _kinds(plan) == [ACTION_OPEN_CSV]
    assert any('PDB' in n for n in plan.notes)


def test_meshes_are_additive_and_come_after_the_scene(tmp_path):
    """A mesh attaches to the selection, so the scene has to load first."""
    node = _write_node_csv(tmp_path / 'gv_node.csv')
    m1 = tmp_path / 'a.obj'
    m1.write_text('v 0 0 0\n', encoding='utf-8')
    m2 = tmp_path / 'b.stl'
    m2.write_text('solid\n', encoding='utf-8')
    plan = resolve_drop([str(m1), str(node), str(m2)])
    assert _kinds(plan) == [ACTION_OPEN_CSV, ACTION_MESH, ACTION_MESH]


def test_duplicate_paths_are_collapsed(tmp_path):
    p = _write_node_csv(tmp_path / 'gv_node.csv')
    plan = resolve_drop([str(p), str(p)])
    assert _kinds(plan) == [ACTION_OPEN_CSV]


def test_partial_drop_loads_what_it_can(tmp_path):
    """One bad item shouldn't sink the whole drop."""
    node = _write_node_csv(tmp_path / 'gv_node.csv')
    junk = tmp_path / 'notes.docx'
    junk.write_text('x', encoding='utf-8')
    plan = resolve_drop([str(node), str(junk)])
    assert _kinds(plan) == [ACTION_OPEN_CSV]
    assert plan.errors


# --- dragEnterEvent gate -----------------------------------------------------

def test_can_accept_is_extension_only(tmp_path):
    """dragEnterEvent fires continuously, so this must not read files."""
    assert can_accept([str(tmp_path / 'anything.csv')])
    assert can_accept([str(tmp_path / 'a.zip')])
    assert can_accept([str(tmp_path / 'a.obj')])
    assert not can_accept([str(tmp_path / 'a.docx')])
    assert not can_accept([])


def test_can_accept_takes_folders(tmp_path):
    folder = tmp_path / 'Scene'
    folder.mkdir()
    assert can_accept([str(folder)])
