"""Generate the Mood Background example — a scene whose *background* is the
animated element.

The World row (type=0) holds GlyphViz's scene-wide settings, and Channels can
now drive them: its own color_r/g/b is the background color, fog_enabled /
fog_start / fog_end pull atmospheric depth in and out, and render_mode
switches the whole scene's blend mode. One channel, six tracks, and every
glyph in the scene is affected at once.

The glyphs themselves are a static double helix — deliberately still, and
deliberately spread across a wide depth range so the fog has something to
bite on. Everything you see changing is the World row.

Mood arc (16 s at 30 fps, loops seamlessly):

    deep night -> pre-dawn -> dawn -> clear day -> dusk -> night -> ember glow

Fog switches OFF for the clear-day phase and back on either side of it, and
the final ember phase flips render_mode to Additive (1) so the glyphs
glow-stack against a near-black sky — Additive only reads well on a dark
background, which is why the arc puts it there.

Usage:
    python generate_mood_background.py [--out DIR]
"""
import argparse
import csv
import math
from pathlib import Path

import numpy as np

STEM = "mood_background"
FPS = 30
FRAMES = 480          # 16 seconds

# --- scene geometry -------------------------------------------------------
STRANDS = 2
PER_STRAND = 34
HELIX_RADIUS = 70.0
HELIX_TURNS = 2.4
Z_SPAN = 240.0        # -120 .. +120, the depth the fog works across
GLYPH_SCALE = 3.0     # raw scale; renderer floors at 0.2/axis, so stay well above

# --- mood keyframes -------------------------------------------------------
# (t, name, background rgb, fog_enabled, fog_start, fog_end, render_mode)
# t is normalized 0..1 through the loop; t=1.0 repeats t=0.0 so the loop is
# seamless. Colors and fog distances are interpolated between keys; the two
# integer flags are held as step functions (see build_tracks).
NORMAL, ADDITIVE = 0, 1
MOODS = [
    (0.00, "deep night",  (  8,  10,  26), 1, 120.0, 420.0, NORMAL),
    (0.16, "pre-dawn",    ( 38,  32,  66), 1,  90.0, 340.0, NORMAL),
    (0.32, "dawn",        (172,  94,  76), 1, 140.0, 520.0, NORMAL),
    (0.48, "clear day",   (206, 198, 176), 0, 200.0, 700.0, NORMAL),
    (0.64, "dusk",        (142,  66,  86), 1, 130.0, 460.0, NORMAL),
    (0.78, "night falls", ( 14,  12,  34), 1,  90.0, 320.0, NORMAL),
    # Fog OFF for the ember phase. Fog fades toward the background color, so
    # thick fog over a near-black sky cancels exactly what Additive blending
    # is trying to add — the glyphs go invisible instead of glowing.
    (0.88, "ember glow",  (  2,   2,   8), 0,  60.0, 260.0, ADDITIVE),
    (1.00, "deep night",  (  8,  10,  26), 1, 120.0, 420.0, NORMAL),
]

# Channel + track ids. One channel (the World row) feeding six tracks.
CH_WORLD = 1
TRACKS = [
    (1, 'color_r'),
    (2, 'color_g'),
    (3, 'color_b'),
    (4, 'fog_enabled'),
    (5, 'fog_start'),
    (6, 'fog_end'),
    (7, 'render_mode'),
]

NODE_COLS = [
    'id', 'type', 'parent_id', 'branch_level',
    'translate_x', 'translate_y', 'translate_z',
    'rotate_x', 'rotate_y', 'rotate_z',
    'scale_x', 'scale_y', 'scale_z',
    'color_r', 'color_g', 'color_b', 'color_a',
    'geometry', 'hide', 'topo', 'ratio',
    'ch_input_id', 'fog_enabled', 'fog_start', 'fog_end',
]


def _row(**kw):
    """A node row with the sane defaults every column has on load."""
    row = dict.fromkeys(NODE_COLS, 0)
    row.update(dict(
        branch_level=0, scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=255, color_g=255, color_b=255, color_a=255,
        geometry=11, topo=0, ratio=0.1,
    ))
    row.update(kw)
    return row


def build_nodes():
    """World row + a static double helix of glyphs spanning the depth range."""
    start_rgb = MOODS[0][2]
    nodes = [_row(
        id=1, type=0,                       # type 0 = World: scene-wide settings
        color_r=start_rgb[0], color_g=start_rgb[1], color_b=start_rgb[2],
        fog_enabled=MOODS[0][3], fog_start=MOODS[0][4], fog_end=MOODS[0][5],
        ch_input_id=CH_WORLD,               # <- the whole point of this example
    )]

    node_id = 2
    for strand in range(STRANDS):
        phase = strand * math.pi
        for i in range(PER_STRAND):
            f = i / (PER_STRAND - 1)
            angle = phase + f * HELIX_TURNS * 2 * math.pi
            # Muted cool->warm ramp along the helix: present enough to catch
            # the light, quiet enough that the background sets the mood.
            warm = 0.5 + 0.5 * math.sin(angle)
            nodes.append(_row(
                id=node_id, type=5,
                translate_x=HELIX_RADIUS * math.cos(angle),
                translate_y=HELIX_RADIUS * math.sin(angle),
                translate_z=-Z_SPAN / 2 + f * Z_SPAN,
                scale_x=GLYPH_SCALE, scale_y=GLYPH_SCALE, scale_z=GLYPH_SCALE,
                color_r=int(120 + 110 * warm),
                color_g=int(130 + 60 * warm),
                color_b=int(170 - 60 * warm),
                color_a=255,
                geometry=3,                 # solid sphere
            ))
            node_id += 1
    return nodes


def build_tracks():
    """One row per frame, one column per track. Values are ABSOLUTE — the
    engine does no interpolation between frames, so the smooth fades are
    precomputed here."""
    t = np.linspace(0.0, 1.0, FRAMES, endpoint=False)
    keys = np.array([m[0] for m in MOODS])

    def ramp(idx, sub=None):
        vals = np.array([(m[idx][sub] if sub is not None else m[idx])
                         for m in MOODS], dtype=float)
        return np.interp(t, keys, vals)

    def step(idx):
        """Integer fields (fog_enabled, render_mode) hold their keyframe value
        until the next key rather than being interpolated through meaningless
        in-between values."""
        vals = [m[idx] for m in MOODS]
        out = np.empty(FRAMES)
        for i, ti in enumerate(t):
            k = max(j for j in range(len(keys)) if keys[j] <= ti)
            out[i] = vals[k]
        return out

    return {
        1: ramp(2, 0), 2: ramp(2, 1), 3: ramp(2, 2),
        4: step(3),
        5: ramp(4), 6: ramp(5),
        7: step(6),
    }


def write(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / f"{STEM}_gv_node.csv", 'w', newline='',
              encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=NODE_COLS)
        w.writeheader()
        w.writerows(build_nodes())

    # GlyphViz reads exactly three columns from a ch-map: channel_id,
    # track_id, attribute. Nothing else is needed for a native gv_ file.
    with open(out_dir / f"{STEM}_gv_ch-map.csv", 'w', newline='',
              encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['channel_id', 'track_id', 'attribute'])
        for tid, attr in TRACKS:
            w.writerow([CH_WORLD, tid, attr])

    tracks = build_tracks()
    with open(out_dir / f"{STEM}_gv_ch-tracks.csv", 'w', newline='',
              encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['cyclecount'] + [f'ch{tid}' for tid, _a in TRACKS])
        for i in range(FRAMES):
            w.writerow([i] + [round(float(tracks[tid][i]), 4)
                              for tid, _a in TRACKS])

    print(f"wrote {STEM}_gv_node.csv / _gv_ch-map.csv / _gv_ch-tracks.csv "
          f"to {out_dir}  ({FRAMES} frames @ {FPS} fps)")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(Path(__file__).parent),
                    help="output folder (defaults to this script's folder)")
    write(Path(ap.parse_args().out))
