#!/usr/bin/env python3
"""
generate_bird_song_surface_topology.py
=======================================
A GlyphViz TOPO_SURFACE showcase: a real field recording's spectrogram
rendered and animated as a deformable grid. (Not a synesthesia example --
no FFT-driven glyph swarm here, just what Surface topology alone can do with
real audio data. Earlier revisions of this example did try pairing a
video-textured screen with an FFT glyph bloom -- see git history -- but a
video texture's own playback clock can't be locked to anything else in the
scene, so that approach was dropped entirely.) The only "audio object" here
is a WAV played back through the existing Channels-sync mechanism
(gv_audio.txt -- see Cat_Scan_Synesthesia_Example), which locks Channels
frame advance to real audio playback position. No drift, no unsynchronizable
clock.

The scene: a real field recording's spectrogram (time x frequency, grayscale
= magnitude) rendered as a TOPO_SURFACE grid (glyphviz_core/topology.py --
same mechanism as the Cowles Mountain DEM in Surface_Example, translate_z is
just the height at each grid point), but ANIMATED rather than static. A
"wavefront" sweeps across the grid along X (time) in sync with the audio:
each time-column is flat/untouched until the wave reaches it, then snaps up
to its full spectrogram height (a hard leading edge -- Jeff's "wall"), and
over the TAIL_WIDTH columns after the wave has passed, decays smoothly back
down to flat (Jeff's "trailing wave"). Columns not yet reached never move;
columns fully decayed sit flat again -- only a TAIL_WIDTH-column-wide band
around the current wavefront position is ever in motion.

wave_pos(frame) advances linearly from 0 to (N_TIME - 1 + TAIL_WIDTH) across
the animation's frame range, so column 0 is fully lit at frame 0 and the last
column has fully decayed again by the final frame -- no abrupt cut at either
end. Per column c, per frame f:
    distance = wave_pos(f) - c
    factor   = 0                                  if distance < 0   (not yet reached)
             = 0.5 * (1 + cos(pi * distance / TAIL_WIDTH))   if 0 <= distance <= TAIL_WIDTH
             = 0                                  if distance > TAIL_WIDTH  (fully decayed)
    translate_z(f, c, r) = spectrogram[c, r] * factor * HEIGHT_SCALE

Resolution: the spectrogram is finer in time (N_TIME=50 columns -- the wave
travels along this axis, so it needs enough steps to read as a long sweep
rather than a short hop) and coarser in frequency (N_FREQ=20 rows). This is
NOT the same audio_analysis.analyze() call an FFT-driven glyph swarm would
use (many bands at the animation's native ~30 fps); here fps is set so
analyze() itself returns ~N_TIME frames, i.e. the "frame rate" of the
spectrogram IS the grid's time resolution, computed once from the real WAV
duration. The animation's actual playback frame rate (ANIM_FPS, ~30) is a
separate, independent clock driving how smoothly wave_pos sweeps across
those columns -- it does not change the underlying spectrogram data.

Color: each grid point's color is static (not animated -- only translate_z
moves) and comes from the same colormap the reference spectrogram PNG uses
-- matplotlib's "inferno", vmin=0/vmax=1 applied directly to that cell's own
normalized spectrogram magnitude (see Cat_Scan_Synesthesia_Example.ipynb's
imshow call). So the full data "shape" is visible as a heatmap across the
whole grid at all times; the traveling wave adds the 3D height reveal on
top of it, it doesn't gate the color.

Output files (written to --out, default: this folder)
------------------------------------------------------
  Bird_Song_Surface_Topology_Example_gv_node.csv    1 Surface root + N_TIME*N_FREQ children
  Bird_Song_Surface_Topology_Example_gv_tag.csv     1 label on the root
  Bird_Song_Surface_Topology_Example_gv_ch-map.csv  N_TIME*N_FREQ channel -> track -> translate_z
  Bird_Song_Surface_Topology_Example_gv_ch-tracks.csv
  Bird_Song_Surface_Topology_Example_gv_audio.txt   relative path to the WAV (Channels-synced playback)

Usage
-----
  python generate_bird_song_surface_topology.py
  python generate_bird_song_surface_topology.py --out scratch/

Load in GlyphViz: File > Open Node CSV -> Bird_Song_Surface_Topology_Example_gv_node.csv
Press Play in the Channels panel -- audio plays in sync automatically, and
the spectrogram wave sweeps across the surface as the call plays.
"""

import argparse
import csv
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Audio_Animation_Example" / "Cat_Scan_Synesthesia_Example"))
from audio_analysis import analyze, load_wav_mono   # vendored copy, see that file's docstring

# ===========================================================================
# Parameters
# ===========================================================================

OUTPUT_DIR = Path(__file__).parent
PREFIX     = "Bird_Song_Surface_Topology_Example"
MEDIA_DIR  = OUTPUT_DIR / "media"
SOURCE_WAV = MEDIA_DIR / "mockingbird_song_mono.wav"

TOPO_SURFACE = 17   # glyphviz_core/topology.py
GEO_POINT    = 22   # glyphviz_core/geometry_data.py

N_TIME  = 50     # spectrogram time columns (x-axis, wave travel direction --
                  # the long axis, so the sweep reads as a real traveling wave)
N_FREQ  = 20     # spectrogram frequency rows (y-axis)
F_LO    = 700.0   # Hz -- mockingbird call range, NOT a generic 20 Hz music floor
                   # (see this script's git history for the spectral scan that
                   # picked this: real content only showed up ~700 Hz-10 kHz)
F_HI    = 10000.0  # Hz

TAIL_WIDTH  = 5.0    # columns of trailing decay behind the wavefront
ANIM_FPS    = 30.0   # animation playback frame rate (independent of N_TIME)

HEIGHT_SCALE = 6.0    # world-unit height at a cell's peak (spectrogram value 1.0)
ROOT_SCALE_X = 1.0    # world units per time-column
ROOT_SCALE_Y = 1.0    # world units per frequency-row
CHILD_SCALE  = 0.15   # GEO_POINT glyph size per grid point


# ===========================================================================
# Wave shaping
# ===========================================================================

def wave_factor(frame_idx: np.ndarray, n_time: int, tail_width: float, n_frames: int) -> np.ndarray:
    """(n_frames, n_time) array: 0..1 multiplier per (frame, column). wave_pos
    sweeps linearly from 0 (column 0 fully lit at frame 0) to
    n_time - 1 + tail_width (last column fully decayed by the final frame)."""
    wave_pos = frame_idx / max(1, n_frames - 1) * (n_time - 1 + tail_width)
    cols = np.arange(n_time)
    distance = wave_pos[:, None] - cols[None, :]   # (n_frames, n_time)
    factor = np.where(
        (distance >= 0) & (distance <= tail_width),
        0.5 * (1.0 + np.cos(np.pi * distance / tail_width)),
        0.0,
    )
    return factor


# ===========================================================================
# File writers
# ===========================================================================

NODE_FIELDS = [
    "id", "type", "parent_id", "branch_level",
    "translate_x", "translate_y", "translate_z",
    "rotate_x", "rotate_y", "rotate_z",
    "scale_x", "scale_y", "scale_z",
    "color_r", "color_g", "color_b", "color_a",
    "geometry", "hide", "topo", "ratio", "ch_input_id",
]


from matplotlib import colormaps
_INFERNO = colormaps["inferno"]


def spectrogram_color(value: float) -> tuple[int, int, int]:
    """Same colormap + normalization as Cat_Scan_Synesthesia_Example.ipynb's
    reference spectrogram plot (cmap='inferno', vmin=0/vmax=1) applied to
    this cell's own normalized magnitude -- static per cell, not animated,
    so the full spectrogram's color pattern is visible across the whole grid
    even before the wave reaches it."""
    r, g, b, _a = _INFERNO(max(0.0, min(1.0, value)))
    return int(r * 255), int(g * 255), int(b * 255)


def build_nodes() -> tuple[list[dict], np.ndarray]:
    """Returns (node rows, spectrogram) where spectrogram is (N_TIME, N_FREQ),
    normalized 0..1 (audio_analysis.analyze()'s own per-band peak norm)."""
    print(f"Analyzing {SOURCE_WAV.name}: duration...")
    samples, sr = load_wav_mono(SOURCE_WAV)
    duration_s = len(samples) / sr
    grid_fps = N_TIME / duration_s
    print(f"  {duration_s:.2f}s -> spectrogram fps={grid_fps:.3f} for {N_TIME} time columns")

    spectrogram, band_freqs, _ = analyze(
        SOURCE_WAV, n_bands=N_FREQ, fps=grid_fps, f_lo=F_LO, f_hi=F_HI)
    n_time_actual = spectrogram.shape[0]
    if n_time_actual != N_TIME:
        print(f"  NOTE: analyze() returned {n_time_actual} time columns, not {N_TIME} "
              f"(rounding) -- using {n_time_actual}.")

    x_off = -(n_time_actual - 1) / 2.0
    y_off = -(N_FREQ - 1) / 2.0

    rows = [{
        "id": 1, "type": 5, "parent_id": 0, "branch_level": 0,
        "translate_x": 0.0, "translate_y": 0.0, "translate_z": 0.0,
        "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
        "scale_x": ROOT_SCALE_X, "scale_y": ROOT_SCALE_Y, "scale_z": 1.0,
        "color_r": 90, "color_g": 90, "color_b": 90, "color_a": 255,
        "geometry": GEO_POINT, "hide": 0, "topo": TOPO_SURFACE, "ratio": 0.1,
        "ch_input_id": 0,
    }]
    next_id = 2
    for c in range(n_time_actual):
        for r in range(N_FREQ):
            cr, cg, cb = spectrogram_color(spectrogram[c, r])
            ch = (c * N_FREQ + r) + 1   # 1-indexed channel id, row-major within column
            rows.append({
                "id": next_id, "type": 5, "parent_id": 1, "branch_level": 1,
                "translate_x": round(c + x_off, 4),
                "translate_y": round(r + y_off, 4),
                "translate_z": 0.0,
                "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
                "scale_x": CHILD_SCALE, "scale_y": CHILD_SCALE, "scale_z": CHILD_SCALE,
                "color_r": cr, "color_g": cg, "color_b": cb, "color_a": 255,
                "geometry": GEO_POINT, "hide": 0, "topo": 0, "ratio": 0.1,
                "ch_input_id": ch,
            })
            next_id += 1
    return rows, spectrogram, band_freqs, duration_s, n_time_actual


def build_ch_map_and_tracks(n_time: int, n_freq: int, spectrogram: np.ndarray,
                             duration_s: float) -> tuple[list[dict], np.ndarray]:
    n_channels = n_time * n_freq
    ch_rows = [
        {"id": i, "channel_id": i + 1, "track_id": i + 1, "attribute": "translate_z",
         "track_table_id": 0, "ch_map_table_id": 0, "record_id": 0}
        for i in range(n_channels)
    ]

    n_frames = max(2, round(duration_s * ANIM_FPS))
    frame_idx = np.arange(n_frames)
    factor = wave_factor(frame_idx, n_time, TAIL_WIDTH, n_frames)   # (n_frames, n_time)

    # out[:, c*n_freq + r] = spectrogram[c, r] * factor[:, c] * HEIGHT_SCALE
    out = (factor[:, :, None] * spectrogram[None, :, :]) * HEIGHT_SCALE   # (n_frames, n_time, n_freq)
    out = out.reshape(n_frames, n_time * n_freq)
    return ch_rows, out


def write_nodes(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=NODE_FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"  {path.name}: {len(rows)} nodes")


def write_tags(path: Path, n_time: int, n_freq: int) -> None:
    rows = [{"id": 0, "table_id": 0, "record_id": 1,
             "title": f"Northern Mockingbird spectrogram ({n_time}x{n_freq}) -- Press Play"}]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "table_id", "record_id", "title"])
        w.writeheader()
        w.writerows(rows)
    print(f"  {path.name}: 1 label")


def write_ch_map(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "channel_id", "track_id", "attribute",
                                          "track_table_id", "ch_map_table_id", "record_id"])
        w.writeheader()
        w.writerows(rows)
    print(f"  {path.name}: {len(rows)} mappings")


def write_ch_tracks(path: Path, out: np.ndarray) -> None:
    n_frames, n_tracks = out.shape
    cols = [f"ch{i + 1}" for i in range(n_tracks)]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["cyclecount"] + cols)
        for j in range(n_frames):
            w.writerow([j] + [f"{v:.4f}" for v in out[j]])
    print(f"  {path.name}: {n_frames} frames x {n_tracks} tracks")


def write_audio_manifest(path: Path, wav_path: Path, out_dir: Path) -> None:
    import os
    rel = os.path.relpath(wav_path.resolve(), out_dir.resolve())
    path.write_text(rel.replace("\\", "/") + "\n", encoding="utf-8")
    print(f"  {path.name}: -> {rel}")


def generate(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Writing {PREFIX} to {out_dir}/\n")

    node_rows, spectrogram, band_freqs, duration_s, n_time_actual = build_nodes()
    ch_map_rows, ch_tracks = build_ch_map_and_tracks(n_time_actual, N_FREQ, spectrogram, duration_s)

    write_nodes(out_dir / f"{PREFIX}_gv_node.csv", node_rows)
    write_tags(out_dir / f"{PREFIX}_gv_tag.csv", n_time_actual, N_FREQ)
    write_ch_map(out_dir / f"{PREFIX}_gv_ch-map.csv", ch_map_rows)
    write_ch_tracks(out_dir / f"{PREFIX}_gv_ch-tracks.csv", ch_tracks)
    write_audio_manifest(out_dir / f"{PREFIX}_gv_audio.txt", SOURCE_WAV, out_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GlyphViz Surface-topology spectrogram waterfall generator")
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR,
                         help="output directory (default: this example's folder)")
    args = parser.parse_args()
    out = args.out if args.out.is_absolute() else OUTPUT_DIR / args.out

    generate(out)

    print(f"\nDone.  Open GlyphViz, then:")
    print(f"  File > Open Node CSV -> {PREFIX}_gv_node.csv")
    print(f"  Press Play in the Channels panel -- audio plays in sync, and the")
    print(f"  spectrogram wave sweeps across the surface as the call plays.")
