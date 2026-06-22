#!/usr/bin/env python3
"""
generate_audio_example.py
==========================
GlyphViz audio-driven Channels ("music synesthesia"): runs an FFT band-power
analysis on a WAV file (glyphviz_core/audio_analysis.py) and writes the result
into the existing gv_ch-map.csv/gv_ch-tracks.csv format, plus a one-line
gv_audio.txt manifest naming the source WAV. The desktop Channels player
auto-detects that manifest (glyphviz_core/channel_loader.find_audio_file) and
plays the audio in sync — see glyphviz_gl/audio_player.py and
MainWindow._ch_tick_audio_synced.

Scene layout
------------
N_BANDS independent sphere nodes spread along the X axis, one per log-spaced
frequency band (lowest frequency at -X, highest at +X). Each sphere's
translate_z is driven by that band's normalized power over time. Color is a
blue (low frequency) -> red (high frequency) gradient, purely so the bands
are easy to tell apart by eye; it does not animate.

Output files (written to OUTPUT_DIR)
-------------------------------------
  {PREFIX}_gv_node.csv       N_BANDS sphere nodes
  {PREFIX}_gv_tag.csv        per-node frequency label ("123 Hz")
  {PREFIX}_gv_ch-map.csv     channel -> attribute mappings (-> translate_z)
  {PREFIX}_gv_ch-tracks.csv  per-band power over time, from audio_analysis.analyze()
  {PREFIX}_gv_audio.txt      relative path to the analyzed WAV, for audio-sync playback

Usage
-----
  python generate_audio_example.py
  python generate_audio_example.py --wav media/4_instruments_c_major.wav

Load in GlyphViz: File > Open Node CSV -> {PREFIX}_gv_node.csv
The Channels panel appears automatically. Press the play button to animate —
the audio plays in sync automatically.
"""

import argparse
import colorsys
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from glyphviz_core.audio_analysis import analyze

# ===========================================================================
# Parameters — modify these freely, or override SOURCE_WAV with --wav
# ===========================================================================

OUTPUT_DIR = Path(__file__).parent
PREFIX     = "Audio_Animation_Example"
MEDIA_DIR  = OUTPUT_DIR / "media"

# Default source audio to analyze: a real major scale played by four
# instruments — a much better demo than the synthetic tone files below.
#
# For regression-testing the analysis pipeline itself, the tone files are
# better ground truth: 5tones_100_200_300_400_800.wav has five equal-amplitude
# tones (confirmed via FFT: each peaks within 0.01% of the others), so exactly
# five band clusters should light up and nothing else --wav media/5tones_100_200_300_400_800.wav.
SOURCE_WAV = MEDIA_DIR / "4_instruments_c_major.wav"

N_BANDS = 64
FPS     = 30.0
F_LO    = 20.0
F_HI    = 16000.0

# Peak translate_z displacement (scene units) at full band power.
AMPLITUDE = 8.0

# Spacing between adjacent band spheres along X (scene units).
SPACING = 1.5

SCALE  = 0.5
RATIO  = 0.1
GEO_SPHERE = 3   # glyphviz_core/geometry_data.py
TOPO_NONE  = 0   # glyphviz_core/topology.py


def _band_color(i: int, n: int) -> tuple[int, int, int]:
    """Blue (low frequency, i=0) -> red (high frequency, i=n-1), for eyeballing
    which sphere belongs to which band — purely cosmetic, not animated."""
    hue = 0.66 * (1.0 - i / max(n - 1, 1))   # 0.66 = blue, 0.0 = red
    r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 1.0)
    return int(r * 255), int(g * 255), int(b * 255)


def write_nodes(path: Path, band_freqs) -> int:
    fieldnames = [
        "id", "type", "parent_id", "branch_level",
        "translate_x", "translate_y", "translate_z",
        "rotate_x", "rotate_y", "rotate_z",
        "scale_x", "scale_y", "scale_z",
        "color_r", "color_g", "color_b", "color_a",
        "geometry", "hide", "topo", "ratio", "ch_input_id",
    ]
    n = len(band_freqs)
    x0 = -(n - 1) / 2.0 * SPACING
    rows = []
    for i in range(n):
        r, g, b = _band_color(i, n)
        rows.append({
            "id": i + 1, "type": 5, "parent_id": 0, "branch_level": 0,
            "translate_x": round(x0 + i * SPACING, 4),
            "translate_y": 0.0, "translate_z": 0.0,
            "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
            "scale_x": SCALE, "scale_y": SCALE, "scale_z": SCALE,
            "color_r": r, "color_g": g, "color_b": b, "color_a": 255,
            "geometry": GEO_SPHERE, "hide": 0, "topo": TOPO_NONE, "ratio": RATIO,
            "ch_input_id": i + 1,   # 1-indexed; matches channel_id in ch-map
        })
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"  {path.name}: {n} band-sphere nodes")
    return n


def write_tags(path: Path, band_freqs) -> None:
    fieldnames = ["id", "table_id", "record_id", "title"]
    rows = []
    for i, freq in enumerate(band_freqs):
        rows.append({
            "id": i, "table_id": 0, "record_id": i + 1,
            "title": f"{freq:.0f} Hz",
        })
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"  {path.name}: {len(rows)} frequency labels")


def write_ch_map(path: Path, n_bands: int) -> None:
    # channel i drives track i, animating translate_z; node ch_input_id == i
    # binds that node to this channel (see write_nodes above).
    fieldnames = ["id", "channel_id", "track_id", "attribute",
                  "track_table_id", "ch_map_table_id", "record_id"]
    rows = []
    for i in range(n_bands):
        rows.append({
            "id": i, "channel_id": i + 1, "track_id": i + 1,
            "attribute": "translate_z",
            "track_table_id": 0, "ch_map_table_id": 0, "record_id": 0,
        })
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"  {path.name}: {len(rows)} channel mappings (ch_input_id 1-{n_bands} -> translate_z)")


def write_ch_tracks(path: Path, tracks) -> None:
    n_frames, n_bands = tracks.shape
    track_cols = [f"ch{i + 1}" for i in range(n_bands)]
    fieldnames = ["cyclecount"] + track_cols
    rows = []
    for j in range(n_frames):
        row: dict = {"cyclecount": j}
        for i in range(n_bands):
            row[track_cols[i]] = round(float(tracks[j, i]) * AMPLITUDE, 6)
        rows.append(row)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"  {path.name}: {n_frames} frames x {n_bands} tracks (translate_z, peak +/-{AMPLITUDE})")


def write_audio_manifest(path: Path, wav_path: Path) -> None:
    # Relative to OUTPUT_DIR, so the example folder stays portable.
    rel = wav_path.resolve().relative_to(OUTPUT_DIR.resolve())
    path.write_text(str(rel).replace("\\", "/") + "\n", encoding="utf-8")
    print(f"  {path.name}: -> {rel}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wav", type=Path, default=SOURCE_WAV,
        help=f"WAV file to analyze (default: {SOURCE_WAV.relative_to(OUTPUT_DIR)})",
    )
    args = parser.parse_args()
    source_wav = args.wav if args.wav.is_absolute() else OUTPUT_DIR / args.wav

    print(f"Analyzing {source_wav.name} ({N_BANDS} bands, {FPS} fps, {F_LO}-{F_HI} Hz)...")
    tracks, band_freqs, duration_s = analyze(source_wav, n_bands=N_BANDS, fps=FPS, f_lo=F_LO, f_hi=F_HI)
    print(f"  {duration_s:.2f}s of audio -> {tracks.shape[0]} frames")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\nWriting Audio_Animation_Example to {OUTPUT_DIR}/\n")
    write_nodes         (OUTPUT_DIR / f"{PREFIX}_gv_node.csv", band_freqs)
    write_tags          (OUTPUT_DIR / f"{PREFIX}_gv_tag.csv", band_freqs)
    write_ch_map        (OUTPUT_DIR / f"{PREFIX}_gv_ch-map.csv", N_BANDS)
    write_ch_tracks     (OUTPUT_DIR / f"{PREFIX}_gv_ch-tracks.csv", tracks)
    write_audio_manifest(OUTPUT_DIR / f"{PREFIX}_gv_audio.txt", source_wav)

    print(f"\nDone.  Open GlyphViz, then:")
    print(f"  File > Open Node CSV -> {PREFIX}_gv_node.csv")
    print(f"  The Channels panel appears automatically.  Press Play to animate; audio plays in sync automatically.")
