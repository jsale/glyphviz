"""
Generate ANTz-compatible 94-column np_node.csv files for each golden-master
test scene.  Each file follows the mandatory ANTz opening structure:

  row 1  world (type 0)   parent_id=0  branch_level=0
  row 2  camera (type 1)  parent_id=0  branch_level=0  (root camera)
  rows 3-5  cameras       parent_id=2  branch_level=1  (sub-cameras)
  row 6  grid (type 6)    parent_id=0  branch_level=0
  rows 7+  glyph nodes (type 5)

Glyph node branch_level convention (ANTz legacy):
  branch_level=0  when parent_id=0  (direct child of world/root)
  branch_level=1  when parent is another glyph one level deep
  branch_level=N  for N levels deep

Usage (from the repo root):
  conda run -n glyphviz python tests/golden/generate_antz_scenes.py
"""

import csv
from pathlib import Path

OUT_DIR = Path(__file__).parent / "scenes"

# ---------------------------------------------------------------------------
# 94-column header
# ---------------------------------------------------------------------------
HEADER = [
    'id','type','data','selected','parent_id','branch_level',
    'child_id','child_index','child_count',
    'ch_input_id','ch_output_id','ch_last_updated','average','samples',
    'aux_a_x','aux_a_y','aux_a_z','aux_b_x','aux_b_y','aux_b_z','color_shift',
    'rotate_vec_x','rotate_vec_y','rotate_vec_z','rotate_vec_s',
    'scale_x','scale_y','scale_z',
    'translate_x','translate_y','translate_z',
    'tag_offset_x','tag_offset_y','tag_offset_z',
    'rotate_rate_x','rotate_rate_y','rotate_rate_z',
    'rotate_x','rotate_y','rotate_z',
    'scale_rate_x','scale_rate_y','scale_rate_z',
    'translate_rate_x','translate_rate_y','translate_rate_z',
    'translate_vec_x','translate_vec_y','translate_vec_z',
    'shader','geometry','line_width','point_size','ratio','color_index',
    'color_r','color_g','color_b','color_a','color_fade','texture_id',
    'hide','freeze','topo','facet',
    'auto_zoom_x','auto_zoom_y','auto_zoom_z',
    'trigger_hi_x','trigger_hi_y','trigger_hi_z',
    'trigger_lo_x','trigger_lo_y','trigger_lo_z',
    'set_hi_x','set_hi_y','set_hi_z',
    'set_lo_x','set_lo_y','set_lo_z',
    'proximity_x','proximity_y','proximity_z',
    'proximity_mode_x','proximity_mode_y','proximity_mode_z',
    'segments_x','segments_y','segments_z',
    'tag_mode','format_id','table_id','record_id','size',
]
assert len(HEADER) == 94


# ---------------------------------------------------------------------------
# Row builder: start from all-zeros then apply overrides
# ---------------------------------------------------------------------------

def make_row(overrides: dict) -> list:
    row = {h: 0 for h in HEADER}
    row['data']       = overrides.get('id', 0)
    row['samples']    = 1
    row['scale_x']    = row['scale_y'] = row['scale_z'] = 1.0
    row['line_width'] = 1.0
    row['ratio']      = 0.1
    row['color_a']    = 255
    row['segments_x'] = row['segments_y'] = 16
    row['size']       = 420
    row.update(overrides)
    return [row[h] for h in HEADER]


# ---------------------------------------------------------------------------
# Fixed infrastructure rows (identical for every scene file)
# ---------------------------------------------------------------------------

INFRA = [
    # world
    make_row(dict(id=1, type=0,
                  rotate_vec_y=1.0,
                  color_r=50, color_g=101, color_b=101,
                  trigger_lo_z=1, record_id=0)),
    # root camera
    make_row(dict(id=2, type=1, parent_id=0, branch_level=0,
                  child_index=2, child_count=3,
                  rotate_vec_y=0.667548, rotate_vec_z=0.380760, rotate_vec_s=-0.639844,
                  translate_x=-27.871548, translate_y=-16.805004, translate_z=16.488552,
                  rotate_x=50.219776, rotate_y=60.300198,
                  color_r=50, color_g=101, color_b=101, record_id=2)),
    # sub-camera 1
    make_row(dict(id=3, type=1, parent_id=2, branch_level=1,
                  rotate_vec_s=-1.0,
                  translate_x=-0.5, translate_z=571.75,
                  color_r=50, color_g=101, color_b=101)),
    # sub-camera 2
    make_row(dict(id=4, type=1, parent_id=2, branch_level=1,
                  rotate_vec_z=1.0,
                  translate_y=-90.0, translate_z=7.0, rotate_x=90.0,
                  color_r=50, color_g=101, color_b=101)),
    # sub-camera 3
    make_row(dict(id=5, type=1, parent_id=2, branch_level=1,
                  rotate_vec_y=-1.0,
                  translate_x=85.0, translate_z=7.0, rotate_x=90.0, rotate_y=270.0,
                  color_r=50, color_g=101, color_b=101)),
    # grid
    make_row(dict(id=6, type=6, parent_id=0, branch_level=0,
                  aux_a_x=15.5, aux_a_y=10.5, aux_a_z=30.0,
                  color_r=0, color_g=0, color_b=255, color_a=150,
                  segments_x=12, segments_y=6)),
]


# ---------------------------------------------------------------------------
# Glyph-node helper (type=5, ANTz "pin" glyph)
# ---------------------------------------------------------------------------

def glyph(id, parent_id=0, branch_level=None,
          tx=0.0, ty=0.0, tz=0.0,
          rx=0.0, ry=0.0, rz=0.0,
          sx=1.0, sy=1.0, sz=1.0,
          geometry=3, topo=0, ratio=0.1,
          color_r=180, color_g=180, color_b=180, color_a=255,
          hide=0):
    bl = branch_level if branch_level is not None else (0 if parent_id == 0 else 1)
    return make_row(dict(
        id=id, type=5, parent_id=parent_id, branch_level=bl,
        rotate_vec_z=1.0,           # ANTz glyph default orientation
        translate_x=tx, translate_y=ty, translate_z=tz,
        rotate_x=rx, rotate_y=ry, rotate_z=rz,
        scale_x=sx, scale_y=sy, scale_z=sz,
        tag_offset_z=1,             # ANTz glyph default
        geometry=geometry, ratio=ratio, topo=topo,
        color_r=color_r, color_g=color_g, color_b=color_b, color_a=color_a,
        hide=hide,
        record_id=id,
    ))


# ---------------------------------------------------------------------------
# Scene definitions
# ---------------------------------------------------------------------------

SCENES = {

    'topo0_cartesian_antz': [
        glyph(7,  tx=0,  ty=0,  tz=0,  sx=1, sy=1, sz=1, rx=0,  geometry=3,  color_r=200,color_g=100,color_b=50,  topo=0),
        glyph(8,  tx=10, ty=0,  tz=0,  sx=2, sy=2, sz=2,         geometry=1,  color_r=100,color_g=200,color_b=50,  topo=0),
        glyph(9,  tx=0,  ty=0,  tz=20, sx=1, sy=1, sz=1, rx=45,  geometry=3,  color_r=50, color_g=100,color_b=200, topo=0),
    ],

    'topo6_rod_antz': [
        glyph(7,  tx=0, ty=0, tz=0,  geometry=19, color_r=200,color_g=100,color_b=50,  topo=6),
        glyph(8,  tx=5, ty=5, tz=5,  geometry=19, color_r=200,color_g=100,color_b=50,  topo=6),
        glyph(9,  tx=0, ty=0, tz=0, rx=90,        geometry=19, color_r=200,color_g=100,color_b=50,  topo=6),
    ],

    'topo2_sphere_antz': [
        glyph(7,  tx=0,  ty=0,  tz=0,  geometry=3, color_r=200,color_g=100,color_b=50,  topo=2),
        glyph(8,  parent_id=7, branch_level=1, tx=0,  ty=0,  tz=0,  geometry=3, color_r=100,color_g=200,color_b=50,  topo=0),
        glyph(9,  parent_id=7, branch_level=1, tx=90, ty=0,  tz=0,  geometry=3, color_r=50, color_g=100,color_b=200, topo=0),
        glyph(10, parent_id=7, branch_level=1, tx=0,  ty=90, tz=0,  geometry=3, color_r=200,color_g=50, color_b=100, topo=0),
    ],

    'deep_hierarchy_antz': [
        glyph(7,  tx=10, ty=0, tz=0, geometry=3, color_r=200,color_g=100,color_b=50,  topo=0),
        glyph(8,  parent_id=7, branch_level=1, tx=5, ty=0, tz=0, geometry=3, color_r=100,color_g=200,color_b=50,  topo=0),
        glyph(9,  parent_id=8, branch_level=2, tx=3, ty=0, tz=0, geometry=3, color_r=50, color_g=100,color_b=200, topo=0),
    ],

    'siblings_branching_antz': [
        glyph(7,  tx=0,  ty=0, tz=0, sx=2, sy=2, sz=2, geometry=3, color_r=200,color_g=100,color_b=50,  topo=0),
        glyph(8,  parent_id=7, branch_level=1, tx=5,  ty=0, tz=0, geometry=3, color_r=255,color_g=50, color_b=50,  topo=0),
        glyph(9,  parent_id=7, branch_level=1, tx=0,  ty=5, tz=0, geometry=3, color_r=50, color_g=255,color_b=50,  topo=0),
        glyph(10, parent_id=7, branch_level=1, tx=0,  ty=0, tz=5, geometry=3, color_r=50, color_g=50, color_b=255, topo=0),
        glyph(11, parent_id=7, branch_level=1, tx=-5, ty=0, tz=0, sx=0.5,sy=0.5,sz=0.5, geometry=3, color_r=255,color_g=255,color_b=50, topo=0),
    ],

    'rotation_cascade_antz': [
        glyph(7,  tx=0,  ty=0, tz=0, rz=90, geometry=3, color_r=200,color_g=100,color_b=50,  topo=0),
        glyph(8,  parent_id=7, branch_level=1, tx=10, ty=0, tz=0, geometry=3, color_r=100,color_g=200,color_b=50,  topo=0),
        glyph(9,  tx=0,  ty=0, tz=0, rx=90, geometry=3, color_r=50, color_g=100,color_b=200, topo=0),
        glyph(10, parent_id=9, branch_level=1, tx=10, ty=0, tz=0, geometry=3, color_r=200,color_g=50, color_b=100, topo=0),
    ],

}


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print(f"Writing ANTz 94-column scene files to {OUT_DIR} …")
    for scene_name, glyph_rows in SCENES.items():
        path = OUT_DIR / f"{scene_name}.csv"
        with open(path, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(HEADER)
            for row in INFRA:
                w.writerow(row)
            for row in glyph_rows:
                w.writerow(row)
        print(f"  {path.name}  ({len(glyph_rows)} glyph nodes)")
    print("Done.")
