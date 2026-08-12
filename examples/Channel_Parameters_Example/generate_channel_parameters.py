"""Generate the Channel Parameters example — a test bench with one labeled
station per newly-bindable Channels attribute, all animating at once.

Seven stations in a row, each driven by its own channel and single track, so
the ch-map reads as a legend:

    ratio        a torus swells; its children ride the placement radius out
    topo         a parent's children re-lay-out as the topology steps
    geometry     one glyph cycles through solid shapes
    color_index  one track sweeps a gradient palette
    palette_id   one glyph steps through all 26 built-in palettes
    hide         a glyph strobes on the beat
    show_text    a tag label pops on and off

Stations 1 and 2 are the ones worth watching closely: `ratio`, `topo` and
`geometry` re-place a node's CHILDREN, not just its own appearance, so those
two stations show the whole subtree rearranging.

`mesh_id` is bindable too but can't be demonstrated from a CSV alone — it
selects among meshes imported at runtime via File > Import Mesh.

Usage:
    python generate_channel_parameters.py [--out DIR]
"""
import argparse
import csv
import math
from pathlib import Path

import numpy as np

STEM = "channel_parameters"
FPS = 30
FRAMES = 240          # 8 seconds, loops

STATION_SPACING = 46.0
LABEL_Y = -38.0
DEMO_SCALE = 9.0

# Topologies station 2 steps through, and how children arrange under each.
TOPO_CYCLE = [2, 3, 4, 1, 14]          # Sphere, Torus, Cylinder, Cube, Spiral
# Solid geometries station 3 steps through.
GEO_CYCLE = [1, 3, 5, 9, 11, 13, 15, 19]   # cube sphere cone dodeca octa tetra icosa cylinder

NODE_COLS = [
    'id', 'type', 'parent_id', 'branch_level',
    'translate_x', 'translate_y', 'translate_z',
    'rotate_x', 'rotate_y', 'rotate_z',
    'scale_x', 'scale_y', 'scale_z',
    'color_r', 'color_g', 'color_b', 'color_a',
    'geometry', 'hide', 'topo', 'ratio', 'topo_scale',
    'palette_id', 'color_index', 'ch_input_id', 'text', 'show_text',
]

# Station 2's parent (see below) carries ANTz's topology-coordinate scale,
# 1/180: a linear topology's translate axis then spans the parent's own
# extent, exactly as 180 degrees of longitude spans a sphere. Its 12 children
# are placed in DEGREES (0..330), which every angular topology in TOPO_CYCLE
# reads correctly but Cube reads as world units — at the default topo_scale
# of 1.0 that throws them ~3000 units out, off screen and past every other
# station, which is precisely the confusion this field exists to fix. Left as
# a literal here rather than imported so the generator stays dependency-free.
TOPO_SCALE_ANTZ = 1.0 / 180.0

# (channel_id, track_id, attribute) — one station each.
CH_MAP = [
    (1, 1, 'ratio'),
    (2, 2, 'topo'),
    (3, 3, 'geometry'),
    (4, 4, 'color_index'),
    (5, 5, 'palette_id'),
    (6, 6, 'hide'),
    (7, 7, 'show_text'),
]

STATION_LABELS = [
    'ratio', 'topo', 'geometry', 'color_index', 'palette_id', 'hide', 'show_text',
]


def _row(**kw):
    row = dict.fromkeys(NODE_COLS, 0)
    row.update(dict(
        branch_level=0, scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=210, color_g=210, color_b=210, color_a=255,
        geometry=11, topo=0, ratio=0.1, topo_scale=1.0, text='',
    ))
    row.update(kw)
    return row


def station_x(i):
    return (i - (len(STATION_LABELS) - 1) / 2.0) * STATION_SPACING


def build_nodes():
    # A static dark World row so the stations read clearly. (Animating this
    # row's color_r/g/b is what the Mood Background example does.)
    nodes = [_row(id=1, type=0, color_r=16, color_g=17, color_b=24)]
    nid = 2

    # Always-pinned label under each station. show_text=1 draws the tag
    # regardless of the scene-wide "Show Tag Labels" setting.
    for i, label in enumerate(STATION_LABELS):
        nodes.append(_row(
            id=nid, type=5, translate_x=station_x(i), translate_y=LABEL_Y,
            scale_x=0.4, scale_y=0.4, scale_z=0.4,
            color_r=90, color_g=95, color_b=110,
            geometry=22, ratio=0.12,          # Point marker
            text=label, show_text=1,
        ))
        nid += 1

    # -- station 1: ratio. A torus with children ON its surface, so the
    #    swelling tube carries them outward with it.
    torus_id = nid
    nodes.append(_row(
        id=torus_id, type=5, translate_x=station_x(0),
        scale_x=DEMO_SCALE * 1.4, scale_y=DEMO_SCALE * 1.4, scale_z=DEMO_SCALE * 1.4,
        color_r=90, color_g=170, color_b=230, color_a=200,
        geometry=7, topo=3, ratio=0.10,       # solid torus, Torus topology
        ch_input_id=1,
    ))
    nid += 1
    # Note the tube angle (translate_y): a child at tube angle 0 sits on the
    # tube's outer equator, which is ratio-INVARIANT — torus_radii keeps
    # major+minor equal to the overall radius, so the outer edge never moves.
    # Putting these on the top (90) and bottom (270) of the tube is what makes
    # the swell visible: they lift apart and draw inward as the tube fattens.
    for k in range(8):
        nodes.append(_row(
            id=nid, type=5, parent_id=torus_id, branch_level=1,
            translate_x=(k // 2) * 90.0,      # orbital angle around the ring
            translate_y=90.0 if k % 2 == 0 else 270.0,   # tube angle
            scale_x=0.22, scale_y=0.22, scale_z=0.22,
            color_r=250, color_g=220, color_b=120,
            geometry=3,
        ))
        nid += 1

    # -- station 2: topo. Children re-arrange as the parent's topology steps.
    #    topo_scale (see the constant above) is what keeps them on this
    #    station through the linear topologies in the cycle instead of
    #    scattering them across the whole scene on the frame Cube comes up.
    topo_id = nid
    nodes.append(_row(
        id=topo_id, type=5, translate_x=station_x(1),
        scale_x=DEMO_SCALE, scale_y=DEMO_SCALE, scale_z=DEMO_SCALE,
        color_r=120, color_g=120, color_b=140, color_a=70,
        geometry=2, topo=2,                   # sphere wire shell
        topo_scale=TOPO_SCALE_ANTZ,
        ch_input_id=2,
    ))
    nid += 1
    for k in range(12):
        nodes.append(_row(
            id=nid, type=5, parent_id=topo_id, branch_level=1,
            translate_x=k * 30.0, translate_y=(k % 4) * 25.0 - 30.0,
            scale_x=0.28, scale_y=0.28, scale_z=0.28,
            color_r=255, color_g=140, color_b=90,
            geometry=3,
        ))
        nid += 1

    # -- station 3: geometry. One glyph, cycling shapes.
    nodes.append(_row(
        id=nid, type=5, translate_x=station_x(2),
        scale_x=DEMO_SCALE, scale_y=DEMO_SCALE, scale_z=DEMO_SCALE,
        color_r=160, color_g=230, color_b=160,
        geometry=1, ch_input_id=3,
    ))
    nid += 1

    # -- station 4: color_index sweeping the Rainbow Heatmap gradient (128
    #    indices). palette_id is set once here and never animated.
    nodes.append(_row(
        id=nid, type=5, translate_x=station_x(3),
        scale_x=DEMO_SCALE, scale_y=DEMO_SCALE, scale_z=DEMO_SCALE,
        geometry=3, palette_id=2, color_index=0, ch_input_id=4,
    ))
    nid += 1

    # -- station 5: palette_id stepping all 26 palettes at a fixed index.
    nodes.append(_row(
        id=nid, type=5, translate_x=station_x(4),
        scale_x=DEMO_SCALE, scale_y=DEMO_SCALE, scale_z=DEMO_SCALE,
        geometry=3, palette_id=0, color_index=8, ch_input_id=5,
    ))
    nid += 1

    # -- station 6: hide, strobing.
    nodes.append(_row(
        id=nid, type=5, translate_x=station_x(5),
        scale_x=DEMO_SCALE, scale_y=DEMO_SCALE, scale_z=DEMO_SCALE,
        color_r=255, color_g=90, color_b=90,
        geometry=9, ch_input_id=6,
    ))
    nid += 1

    # -- station 7: show_text, popping a label on and off. Note show_text
    #    starts at 0 — the label only exists while the channel says so.
    nodes.append(_row(
        id=nid, type=5, translate_x=station_x(6),
        scale_x=DEMO_SCALE, scale_y=DEMO_SCALE, scale_z=DEMO_SCALE,
        color_r=220, color_g=170, color_b=255,
        geometry=15, ch_input_id=7,
        text='now you see me', show_text=0,
    ))
    nid += 1
    return nodes


def build_tracks():
    f = np.arange(FRAMES)
    t = f / FRAMES                      # 0..1 through the loop

    # ratio: smooth swell and return (sine, so the loop closes seamlessly).
    ratio = 0.10 + 0.17 * (1 - np.cos(2 * np.pi * t))

    # topo / geometry: integer flip-books. Hold each value for a beat rather
    # than stepping every frame, or it reads as noise.
    topo = np.array([TOPO_CYCLE[int(i // (FRAMES / len(TOPO_CYCLE)))
                                % len(TOPO_CYCLE)] for i in f], dtype=float)
    geo = np.array([GEO_CYCLE[int(i // (FRAMES / len(GEO_CYCLE)))
                              % len(GEO_CYCLE)] for i in f], dtype=float)

    # color_index: full sweep of a 128-entry gradient palette.
    color_index = np.round(127 * t)

    # palette_id: step through all 26, ~9 frames each.
    palette_id = np.floor(t * 26) % 26

    # hide: strobe, 4 frames on / 4 off.
    hide = ((f // 4) % 2).astype(float)

    # show_text: on for 12 frames once per second.
    show_text = ((f % FPS) < 12).astype(float)

    return {1: ratio, 2: topo, 3: geo, 4: color_index,
            5: palette_id, 6: hide, 7: show_text}


def write(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / f"{STEM}_gv_node.csv", 'w', newline='',
              encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=NODE_COLS)
        w.writeheader()
        w.writerows(build_nodes())

    with open(out_dir / f"{STEM}_gv_ch-map.csv", 'w', newline='',
              encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['channel_id', 'track_id', 'attribute'])
        w.writerows(CH_MAP)

    tracks = build_tracks()
    tids = [tid for _c, tid, _a in CH_MAP]
    with open(out_dir / f"{STEM}_gv_ch-tracks.csv", 'w', newline='',
              encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['cyclecount'] + [f'ch{t}' for t in tids])
        for i in range(FRAMES):
            w.writerow([i] + [round(float(tracks[t][i]), 4) for t in tids])

    print(f"wrote {STEM}_gv_node.csv / _gv_ch-map.csv / _gv_ch-tracks.csv "
          f"to {out_dir}  ({FRAMES} frames @ {FPS} fps)")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(Path(__file__).parent),
                    help="output folder (defaults to this script's folder)")
    write(Path(ap.parse_args().out))
