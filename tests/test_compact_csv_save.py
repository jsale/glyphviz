"""GlyphViz saves the MINIMAL native dialect, not the 94-column ANTz layout.

`save_node_csv` used to write all 94 ANTz/GaiaViz columns whether a scene used
them or not, which cost ~550 bytes a row: the 442,767-point LIDAR example
saved as a 243 MB scene file. It now writes the 22 base columns plus only the
columns the scene's data actually needs -- 40.7 MB for that same scan, and 4x
faster to write.

The rule under test throughout: **a column is written only when omitting it
would make some node reload as a different value.** A column whose values are
all covered by load_node_csv's documented default carries no information, so
it is left out; that is what makes a save/reload cycle column-stable instead
of column-accreting, and it is the same discipline the old writer already
applied to its extension columns.

The expectations here are written out longhand rather than imported from
csv_reader, so they cross-check the writer instead of restating it.
"""

from pathlib import Path

import pandas as pd
import pytest

from glyphviz_core.csv_reader import _COL_ORDER, load_node_csv, save_node_csv
from glyphviz_core.node import (
    DEFAULT_TOPO_SCALE, NODE_TYPE_GRID, NODE_TYPE_LINK, NODE_TYPE_WORLD, Node,
    REF_GRID_DEFAULT_RGB, ROTATION_MODE_EULER_XYZ,
    ROTATION_MODE_HEADING_TILT_ROLL, TAG_DEFAULT_FONT_SIZE,
    TAG_DEFAULT_TEXT_RGB, TAG_COLOR_MODE_UNIFORM, TOPO_SCALE_ANTZ,
)
from glyphviz_core import topology as topo

# The 20 columns load_node_csv requires, plus ratio and facet. Written for
# every scene, in this order -- the same 22 GlyphViz Web's writer emits.
BASE_COLUMNS = [
    'id', 'type', 'parent_id', 'branch_level',
    'translate_x', 'translate_y', 'translate_z',
    'rotate_x', 'rotate_y', 'rotate_z',
    'scale_x', 'scale_y', 'scale_z',
    'color_r', 'color_g', 'color_b', 'color_a',
    'geometry', 'hide', 'topo', 'ratio', 'facet',
]


def _node(id=1, **kw):
    """A node at every load default, so any column that appears is one the
    test asked for. Note rotation_mode: a fresh Node() is EULER_XYZ, which the
    load fallback would MISREAD as Heading/Tilt/Roll, so a node that means
    'default' on disk has to say so."""
    fields = dict(
        id=id, type=5, parent_id=0, branch_level=0,
        translate_x=0.0, translate_y=0.0, translate_z=0.0,
        rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=200, color_g=200, color_b=210, color_a=255,
        geometry=2, hide=0, topo=topo.TOPO_NONE,
        rotation_mode=ROTATION_MODE_HEADING_TILT_ROLL,
    )
    fields.update(kw)
    return Node(**fields)


def _header(path) -> list[str]:
    return path.read_text(encoding='utf-8').splitlines()[0].split(',')


def _save(nodes, tmp_path, name='out_gv_node.csv', **kw):
    path = tmp_path / name
    save_node_csv(nodes, str(path), **kw)
    return path


# ---------------------------------------------------------------------------
# The base set
# ---------------------------------------------------------------------------

def test_a_default_scene_writes_only_the_base_columns(tmp_path):
    path = _save([_node(1), _node(2, parent_id=1, branch_level=1)], tmp_path)
    assert _header(path) == BASE_COLUMNS


def test_the_base_columns_are_the_ones_the_loader_requires(tmp_path):
    """Nothing in BASE_COLUMNS is optional: dropping any one of the 20 the
    loader reads directly makes the file unloadable, which is why they are
    written unconditionally."""
    path = _save([_node(1)], tmp_path)
    df = pd.read_csv(path)
    for col in BASE_COLUMNS:
        if col in ('ratio', 'facet'):
            continue                     # conventional, not required
        thinned = tmp_path / f'without_{col}.csv'
        df.drop(columns=[col]).to_csv(thinned, index=False)
        with pytest.raises(KeyError):
            load_node_csv(str(thinned))


def test_a_new_nodes_euler_rotation_mode_is_written(tmp_path):
    """The one asymmetric default: a missing column reloads as ANTz's
    Heading/Tilt/Roll, so a node at the dataclass default (Euler XYZ) MUST
    write the column or it would silently change convention on reload."""
    fresh = _node(1)
    fresh.rotation_mode = ROTATION_MODE_EULER_XYZ   # the dataclass default
    path = _save([fresh], tmp_path)
    assert 'rotation_mode' in _header(path)
    assert load_node_csv(str(path))[0].rotation_mode == ROTATION_MODE_EULER_XYZ


# ---------------------------------------------------------------------------
# Optional columns: present exactly when used
# ---------------------------------------------------------------------------

# (columns the setting adds, the non-default value that should add them)
OPTIONAL_CASES = [
    (['topo_scale'], dict(topo_scale=TOPO_SCALE_ANTZ)),
    (['texture_id'], dict(texture_id=3)),
    (['mesh_id'], dict(mesh_id=2)),
    (['rotation_mode'], dict(rotation_mode=ROTATION_MODE_EULER_XYZ)),
    (['color_index'], dict(color_index=7)),
    (['palette_id'], dict(palette_id=4)),
    (['translate_rate_x', 'translate_rate_y', 'translate_rate_z'],
     dict(translate_rate_y=0.5)),
    (['rotate_rate_x', 'rotate_rate_y', 'rotate_rate_z'], dict(rotate_rate_z=2.0)),
    (['scale_rate_x', 'scale_rate_y', 'scale_rate_z'], dict(scale_rate_x=0.01)),
    (['text'], dict(text='Station 4')),
    (['link'], dict(link='https://example.org')),
    (['show_text'], dict(show_text=1)),
    (['render_mode'], dict(render_mode=1)),
    (['fog_enabled', 'fog_start', 'fog_end'], dict(fog_enabled=1, fog_end=400.0)),
    (['tag_color_mode'], dict(tag_color_mode=1)),
    (['tag_color_r', 'tag_color_g', 'tag_color_b'], dict(tag_color_g=128)),
    (['tag_font_size'], dict(tag_font_size=22)),
    (['ref_grid_color_r', 'ref_grid_color_g', 'ref_grid_color_b'],
     dict(ref_grid_color_b=200)),
]


@pytest.mark.parametrize('cols,setting', OPTIONAL_CASES,
                         ids=[c[0] for c, _ in OPTIONAL_CASES])
def test_an_optional_column_appears_only_when_a_node_uses_it(cols, setting, tmp_path):
    plain = _save([_node(1), _node(2)], tmp_path, 'plain.csv')
    assert not set(cols) & set(_header(plain)), 'written without being used'

    used = _save([_node(1), _node(2, **setting)], tmp_path, 'used.csv')
    header = _header(used)
    # All-or-nothing: a rate triple, the fog settings and a color triple are
    # each ONE setting, and writing only the component that differs would
    # reload as a mix of authored and default values.
    assert [c for c in header if c in cols] == cols

    back = load_node_csv(str(used))[1]
    for field, value in setting.items():
        assert getattr(back, field) == pytest.approx(value)


def test_one_node_out_of_many_is_enough_to_earn_a_column(tmp_path):
    """The World row carries the scene settings, so the check has to be over
    the whole scene, not per node -- and the other rows then write the
    default, not a blank."""
    nodes = [_node(1, type=NODE_TYPE_WORLD, tag_font_size=20)]
    nodes += [_node(i) for i in range(2, 60)]
    path = _save(nodes, tmp_path)
    assert 'tag_font_size' in _header(path)
    back = load_node_csv(str(path))
    assert back[0].tag_font_size == 20
    assert all(n.tag_font_size == TAG_DEFAULT_FONT_SIZE for n in back[1:])


# ---------------------------------------------------------------------------
# extras: informationless columns dropped, meaningful ones kept
# ---------------------------------------------------------------------------

def _legacy_94_column_file(tmp_path, **overrides):
    """A file in the old canonical layout -- what every scene saved by a
    previous GlyphViz release looks like."""
    row = {c: 0 for c in _COL_ORDER}
    row.update(id=1, type=5, parent_id=0, branch_level=0,
               scale_x=1, scale_y=1, scale_z=1, color_a=255,
               geometry=2, ratio=0.1, facet=1, samples=1, size=420,
               line_width=1,
               segments_x=16, segments_y=16, record_id=1, data=1)
    row.update(overrides)
    path = tmp_path / 'legacy_gv_node.csv'
    pd.DataFrame([row])[_COL_ORDER].to_csv(path, index=False)
    return path


def test_a_legacy_94_column_file_shrinks_to_the_base_set(tmp_path):
    """The whole point of the change: 94 columns of mostly-zeros reload as a
    scene that needs 22, and re-saving it writes 22."""
    nodes = load_node_csv(str(_legacy_94_column_file(tmp_path)))
    assert _header(_save(nodes, tmp_path)) == BASE_COLUMNS


@pytest.mark.parametrize('col,value', [
    ('child_id', 9),         # a link's B-end -- the graph would be lost
    ('ch_input_id', 4),      # the channel binding -- the animation would be lost
    ('freeze', 1),           # suspends this node's rate animation
    ('segments_x', 40),      # a World Grid's lattice
    ('trigger_hi_x', -116),  # a World Grid's extents window
])
def test_a_legacy_column_that_carries_meaning_survives(col, value, tmp_path):
    nodes = load_node_csv(str(_legacy_94_column_file(tmp_path, **{col: value})))
    path = _save(nodes, tmp_path)
    assert col in _header(path)
    assert int(float(load_node_csv(str(path))[0].extras[col])) == value


@pytest.mark.parametrize('col', [
    'child_id', 'ch_input_id', 'freeze', 'segments_x', 'trigger_hi_x',
    'selected', 'shader', 'size', 'samples', 'data', 'record_id',
    'proximity_x', 'aux_a_x', 'set_lo_z', 'tag_offset_y', 'line_width',
])
def test_a_legacy_column_at_its_default_is_dropped(col, tmp_path):
    """Each of these reloads to the same value whether the column is there or
    not, so keeping it would cost bytes and say nothing. record_id and data
    are the id-mirroring pair: absent, both fall back to the node's own id."""
    nodes = load_node_csv(str(_legacy_94_column_file(tmp_path)))
    assert col in nodes[0].extras            # the source file really had it
    assert col not in _header(_save(nodes, tmp_path))


def test_a_record_id_that_is_not_the_node_id_is_kept(tmp_path):
    """It is the tag file's join key; only its equality with the node id makes
    it droppable."""
    nodes = load_node_csv(str(_legacy_94_column_file(tmp_path, record_id=77)))
    path = _save(nodes, tmp_path)
    assert 'record_id' in _header(path)
    assert int(float(load_node_csv(str(path))[0].extras['record_id'])) == 77


def test_an_unknown_third_party_column_is_carried_verbatim(tmp_path):
    """A column with no documented default could mean anything, so there is no
    basis for dropping it. (The 94-column writer used to discard these
    outright -- it only ever wrote columns with a slot in its own layout.)"""
    path = tmp_path / 'foreign_gv_node.csv'
    path.write_text(
        'id,type,parent_id,branch_level,translate_x,translate_y,translate_z,'
        'rotate_x,rotate_y,rotate_z,scale_x,scale_y,scale_z,'
        'color_r,color_g,color_b,color_a,geometry,hide,topo,np_ch_in_id,site\n'
        '1,5,0,0,0,0,0,0,0,0,1,1,1,255,0,0,255,3,0,1,12,Mauna Loa\n',
        encoding='utf-8')
    out = _save(load_node_csv(str(path)), tmp_path)
    assert _header(out) == BASE_COLUMNS + ['np_ch_in_id', 'site']
    back = load_node_csv(str(out))[0]
    assert int(float(back.extras['np_ch_in_id'])) == 12
    assert back.extras['site'] == 'Mauna Loa'


def test_a_node_missing_an_extras_column_writes_its_default_not_a_blank(tmp_path):
    """Merging or creating nodes leaves a scene whose rows disagree about
    which extras they carry. The column is written once the scene needs it,
    and the rows that never had it take the documented default."""
    legacy = load_node_csv(str(_legacy_94_column_file(tmp_path, child_id=9)))
    fresh = _node(2)                          # no extras at all
    path = _save(legacy + [fresh], tmp_path)
    assert 'child_id' in _header(path)
    assert int(float(load_node_csv(str(path))[1].extras['child_id'])) == 0


# ---------------------------------------------------------------------------
# Number formatting
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('value,written', [
    (0.0, '0'),
    (-0.0, '0'),          # a value that rounds to zero has no meaningful sign
    (-1.2e-17, '0'),      # ... which is what a generator's cos(90 deg) lands on
    (1.0, '1'),
    (-195.0, '-195'),
    (0.5, '0.5'),
    (33.698407, '33.698407'),
    (-117.25, '-117.25'),
    (1e-7, '0'),          # below 6 dp, as it always was
    (0.1234567, '0.123457'),
])
def test_float_columns_are_written_without_padding(value, written, tmp_path):
    """6 decimal places as always, minus the trailing zeros -- '0.000000' is
    eight bytes to say '0', and that padding was most of the file."""
    path = _save([_node(1, translate_x=value)], tmp_path)
    assert path.read_text(encoding='utf-8').splitlines()[1].split(',')[4] == written
    assert load_node_csv(str(path))[0].translate_x == pytest.approx(value, abs=5e-7)


def test_topo_scale_keeps_significant_figures_not_decimal_places(tmp_path):
    """A multiplier, not a coordinate: 6 dp would round the ANTz preset
    (1/180) to four significant figures."""
    path = _save([_node(1, topo_scale=TOPO_SCALE_ANTZ)], tmp_path)
    assert load_node_csv(str(path))[0].topo_scale == pytest.approx(
        TOPO_SCALE_ANTZ, rel=1e-9)


def test_a_label_with_a_comma_survives(tmp_path):
    path = _save([_node(1, text='La Jolla, CA "north"')], tmp_path)
    assert load_node_csv(str(path))[0].text == 'La Jolla, CA "north"'


# ---------------------------------------------------------------------------
# The ANTz dialect is still reachable
# ---------------------------------------------------------------------------

def test_the_94_column_dialect_is_still_available(tmp_path):
    path = _save([_node(1)], tmp_path, compact=False)
    header = _header(path)
    assert header[:len(_COL_ORDER)] == _COL_ORDER
    assert load_node_csv(str(path))[0].id == 1


# ---------------------------------------------------------------------------
# Every scene in the repository
#
# Replaces the old single-file guard in test_tag_font_size.py, which only ever
# audited sorted(examples)[0] -- any new scene sorting earlier silently took
# over the slot and the previous file stopped being checked.
#
# mesh_creation_lab/ is swept alongside examples/ even though it is not part of
# the shipped collection: the property being guarded (a save/reload cycle is
# column-stable) is a property of the WRITER, and a lab scene exercises it just
# as well as a gallery one. It is included only when present, so deleting or
# restructuring the lab cannot fail the suite.
# ---------------------------------------------------------------------------

SCENE_ROOTS = [Path('examples'), Path('mesh_creation_lab')]
EXAMPLE_SCENES = sorted(
    p for root in SCENE_ROOTS if root.is_dir()
    for p in root.rglob('*gv_node*.csv')
)

# Scenes chosen to cover the features that add columns: World Grid extents,
# links, channel bindings, labels, rate animation and topo_scale. These get
# the full byte-for-byte round trip; the rest get the column check, which is
# what the sweep is actually guarding and is half the cost.
ROUND_TRIP_SAMPLE = [
    p for p in EXAMPLE_SCENES
    if p.parent.name in {
        'Topology_Example', 'Rotation_Convention_Example',
        'Wind_Rose_Example', 'Decay_Chain_Example',
        'Tropical_Cyclone_Example', 'LIDAR_Import_Example',
    }
]


@pytest.mark.skipif(not EXAMPLE_SCENES, reason='example scenes not present')
@pytest.mark.parametrize('scene', EXAMPLE_SCENES, ids=lambda p: p.parent.name)
def test_every_example_scene_stays_column_stable(scene, tmp_path):
    """No shipped scene grows a column when re-saved.

    Every optional column is checked at once, by asserting the written header
    is exactly the base set plus the columns this scene's own data justifies
    -- derived here from the loaded nodes, independently of the writer.
    """
    nodes = load_node_csv(str(scene))
    header = _header(_save(nodes, tmp_path))

    assert header[:len(BASE_COLUMNS)] == BASE_COLUMNS
    written = set(header[len(BASE_COLUMNS):])

    def used(pred):
        return any(pred(n) for n in nodes)

    for cols, needed in (
        (['topo_scale'], used(lambda n: n.topo_scale != DEFAULT_TOPO_SCALE)),
        (['texture_id'], used(lambda n: n.texture_id != 0)),
        (['mesh_id'], used(lambda n: n.mesh_id != 0)),
        (['rotation_mode'],
         used(lambda n: n.rotation_mode != ROTATION_MODE_HEADING_TILT_ROLL)),
        (['color_index'], used(lambda n: n.color_index != 0)),
        (['palette_id'], used(lambda n: n.palette_id != 0)),
        (['text'], used(lambda n: bool(n.text))),
        (['link'], used(lambda n: bool(n.link))),
        (['show_text'], used(lambda n: n.show_text != 0)),
        (['render_mode'], used(lambda n: n.render_mode != 0)),
        (['tag_color_mode'],
         used(lambda n: n.tag_color_mode != TAG_COLOR_MODE_UNIFORM)),
        (['tag_font_size'],
         used(lambda n: n.tag_font_size != TAG_DEFAULT_FONT_SIZE)),
        (['tag_color_r', 'tag_color_g', 'tag_color_b'],
         used(lambda n: (n.tag_color_r, n.tag_color_g, n.tag_color_b)
              != TAG_DEFAULT_TEXT_RGB)),
        (['ref_grid_color_r', 'ref_grid_color_g', 'ref_grid_color_b'],
         used(lambda n: (n.ref_grid_color_r, n.ref_grid_color_g,
                         n.ref_grid_color_b) != REF_GRID_DEFAULT_RGB)),
        (['fog_enabled', 'fog_start', 'fog_end'],
         used(lambda n: n.fog_enabled or n.fog_start or n.fog_end)),
        (['translate_rate_x', 'translate_rate_y', 'translate_rate_z'],
         used(lambda n: n.translate_rate_x or n.translate_rate_y
              or n.translate_rate_z)),
        (['rotate_rate_x', 'rotate_rate_y', 'rotate_rate_z'],
         used(lambda n: n.rotate_rate_x or n.rotate_rate_y or n.rotate_rate_z)),
        (['scale_rate_x', 'scale_rate_y', 'scale_rate_z'],
         used(lambda n: n.scale_rate_x or n.scale_rate_y or n.scale_rate_z)),
    ):
        for col in cols:
            assert (col in written) == bool(needed), \
                f'{scene.parent.name}: {col} {"missing" if needed else "written"}'
        written -= set(cols)

    # Whatever is left is an untracked column, and it is only allowed to stay
    # if some node holds something other than the value its absence would mean.
    for col in written:
        assert any(str(n.extras.get(col, '')).strip() not in ('', '0', '0.0')
                   for n in nodes) or col in ('record_id', 'data'), \
            f'{scene.parent.name}: kept an all-default column {col}'


@pytest.mark.skipif(not ROUND_TRIP_SAMPLE, reason='example scenes not present')
@pytest.mark.parametrize('scene', ROUND_TRIP_SAMPLE, ids=lambda p: p.parent.name)
def test_an_example_scene_re_saves_byte_for_byte(scene, tmp_path):
    """Saving twice must produce the same bytes. A writer that is not
    idempotent is one that changes a scene every time it is opened and saved
    -- this is what caught '-0', which reloaded as a positive zero."""
    once = _save(load_node_csv(str(scene)), tmp_path, 'once.csv')
    twice = _save(load_node_csv(str(once)), tmp_path, 'twice.csv')
    assert once.read_bytes() == twice.read_bytes()


@pytest.mark.skipif(not ROUND_TRIP_SAMPLE, reason='example scenes not present')
@pytest.mark.parametrize('scene', ROUND_TRIP_SAMPLE, ids=lambda p: p.parent.name)
def test_an_example_scene_keeps_its_values(scene, tmp_path):
    src = load_node_csv(str(scene))
    back = load_node_csv(str(_save(src, tmp_path)))
    assert len(back) == len(src)
    for a, b in zip(src, back):
        assert (a.id, a.type, a.parent_id, a.geometry, a.topo, a.hide) == \
               (b.id, b.type, b.parent_id, b.geometry, b.topo, b.hide)
        assert (b.translate_x, b.translate_y, b.translate_z) == pytest.approx(
            (a.translate_x, a.translate_y, a.translate_z), abs=1e-6)
        assert (b.scale_x, b.scale_y, b.scale_z) == pytest.approx(
            (a.scale_x, a.scale_y, a.scale_z), abs=1e-6)
        assert (b.color_r, b.color_g, b.color_b, b.color_a) == \
               (a.color_r, a.color_g, a.color_b, a.color_a)
        assert b.text == a.text and b.link == a.link
        assert b.rotation_mode == a.rotation_mode
        assert b.topo_scale == pytest.approx(a.topo_scale, rel=1e-9)
        if a.type == NODE_TYPE_GRID:
            assert b.grid_extents() == pytest.approx(a.grid_extents())
            assert b.grid_segments() == a.grid_segments()
        if a.type == NODE_TYPE_LINK:
            assert int(float(b.extras.get('child_id', 0))) == \
                   int(float(a.extras.get('child_id', 0)))
