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
N_BANDS independent 3-level hyperglyphs spread along the X axis, one per
log-spaced frequency band (lowest frequency at -X, highest at +X): a root
sphere with N_L1_CHILDREN children evenly spaced around its equator, each
of those with N_L2_CHILDREN children evenly spaced around its own equator.
Every level uses Sphere topology, so translate_z means "altitude above the
parent's surface" rather than a Cartesian offset — Channels drives that
altitude every frame for every node in a band's hierarchy (all bound to the
same ch_input_id/channel, so the whole hyperglyph reacts together), without
disturbing each child's structural placement around its parent. Child
geometry is randomized from CHILD_GEOMETRIES (fixed seed, reproducible);
color is a blue (low frequency) -> red (high frequency) gradient shared by
a band's whole hierarchy, purely so bands are easy to tell apart by eye —
it does not animate.

Output files (written to OUTPUT_DIR)
-------------------------------------
  {PREFIX}_gv_node.csv       hyperglyph nodes (root + L1 + L2 per band)
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
import random
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

# Peak translate_z displacement (scene units) at full band power. Note this is
# a *local* offset, so L1/L2 children (whose translate_z is carried by their
# parent's cumulative world_scale, same cascading as the placement math above)
# move less in world space than the root does for the same track value — e.g.
# at SCALE-derived cascaded scales of ~0.12/0.10, a child's visible bounce is
# roughly 1/8-1/10th of the root's. Bumped 4x (2.0 -> 8.0) since the prior
# value was too small to see the children move at all.
AMPLITUDE = 8.0

# Spacing between adjacent band roots along X (scene units).
SPACING = 3.0

RATIO  = 0.1
GEO_SPHERE  = 3   # glyphviz_core/geometry_data.py
TOPO_SPHERE = 2   # glyphviz_core/topology.py
BASE_SCALE  = 3.0   # the desktop app's default Global Scale slider value

# Hyperglyph validation pass: give each band root a couple of child levels,
# all bound to the same channel (ch_input_id) as their parent, so the whole
# 3-level hierarchy animates and colors together as one glyph.
#
# Every level uses Sphere topology (per Jeff, after the first TOPO_NONE
# attempt: with topo=NONE, parent and children only had Channels' shared
# translate_z to move by, so they all translated together as one rigid
# block — nothing moved *relative* to its parent). Under Sphere topology,
# a child's translate_x/y are longitude/latitude (structural placement,
# evenly distributed around the parent's surface) while translate_z is
# *altitude above that surface* — a completely separate axis from
# placement, so Channels can drive altitude every frame without disturbing
# where around the parent each child sits. At altitude=0 a child rests
# exactly on its parent's surface; the channel pushes it outward from there.
#
# This also remains clear of the *other* known issue — multi-level Sphere/
# Point/Rod/Cube nesting distorts grandchildren's shape under a non-uniform
# ancestor scale (see memory: project_topology_nested_scaling_bug) — because
# that bug specifically requires a non-uniform per-axis parent scale to
# compound through the rotation cascade, and every scale below is uniform
# (scale_x == scale_y == scale_z at every level).
N_L1_CHILDREN = 4
N_L2_CHILDREN = 2

ROOT_RADIUS_WORLD = 0.36   # -> SCALE = 0.12, same as the original flat build
L1_RADIUS_WORLD   = 0.30
L2_RADIUS_WORLD   = 0.24

# glyphviz_core/topology.py's compute_world_scales() cascades scale_x
# multiplicatively down the hierarchy (world_scale = parent's *cumulative*
# world_scale * own scale_x), so the local scale_x a child needs depends on
# its parent's world size, not just on what that child "looks like" alone.
SCALE    = ROOT_RADIUS_WORLD / BASE_SCALE
L1_SCALE = L1_RADIUS_WORLD / ROOT_RADIUS_WORLD
L2_SCALE = L2_RADIUS_WORLD / L1_RADIUS_WORLD

# Grab-bag of solid geometries to randomize child shape from (GEO_SPHERE stays
# reserved for the band roots) — glyphviz_core/geometry_data.py ids.
CHILD_GEOMETRIES = [1, 5, 7, 9, 11, 13, 15, 16, 19]   # Cube,Cone,Torus,Dodeca,Octa,Tetra,Icosa,Pin,Cylinder
_rng = random.Random(42)   # fixed seed: regenerating reproduces the same shapes


def _band_color(i: int, n: int) -> tuple[int, int, int]:
    """Blue (low frequency, i=0) -> red (high frequency, i=n-1), for eyeballing
    which sphere belongs to which band — purely cosmetic, not animated."""
    hue = 0.66 * (1.0 - i / max(n - 1, 1))   # 0.66 = blue, 0.0 = red
    r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 1.0)
    return int(r * 255), int(g * 255), int(b * 255)


def _node_row(node_id, parent_id, branch_level, tx, ty, tz, scale, color, geometry, ch_input_id):
    r, g, b = color
    return {
        "id": node_id, "type": 5, "parent_id": parent_id, "branch_level": branch_level,
        "translate_x": round(tx, 4), "translate_y": round(ty, 4), "translate_z": round(tz, 4),
        "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
        "scale_x": scale, "scale_y": scale, "scale_z": scale,
        "color_r": r, "color_g": g, "color_b": b, "color_a": 255,
        "geometry": geometry, "hide": 0, "topo": TOPO_SPHERE, "ratio": RATIO,
        "ch_input_id": ch_input_id,
    }


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
    next_id = n + 1   # band roots reserve ids 1..n (== their ch_input_id/tag record_id)

    for i in range(n):
        color = _band_color(i, n)
        ch_id = i + 1   # 1-indexed; matches channel_id in ch-map. Every L1/L2
                         # descendant below reuses this same value, so the
                         # whole band's hierarchy animates as one glyph.
        root_id = i + 1
        rows.append(_node_row(
            root_id, 0, 0,
            x0 + i * SPACING, 0.0, 0.0,
            SCALE, color, GEO_SPHERE, ch_id,
        ))

        for j in range(N_L1_CHILDREN):
            # Sphere-topology placement: translate_x/y = longitude/latitude
            # (degrees), translate_z = altitude above the surface (left at 0 —
            # Channels drives this every frame). Evenly distributed = equally
            # spaced longitudes around the root's equator.
            longitude = j * 360.0 / N_L1_CHILDREN
            l1_id = next_id
            next_id += 1
            rows.append(_node_row(
                l1_id, root_id, 1,
                longitude, 0.0, 0.0,
                L1_SCALE, color, _rng.choice(CHILD_GEOMETRIES), ch_id,
            ))

            for k in range(N_L2_CHILDREN):
                longitude2 = k * 360.0 / N_L2_CHILDREN
                l2_id = next_id
                next_id += 1
                rows.append(_node_row(
                    l2_id, l1_id, 2,
                    longitude2, 0.0, 0.0,
                    L2_SCALE, color, _rng.choice(CHILD_GEOMETRIES), ch_id,
                ))

    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    total_children = n * N_L1_CHILDREN * (1 + N_L2_CHILDREN)
    print(f"  {path.name}: {len(rows)} nodes ({n} band roots + {total_children} hyperglyph children)")
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
