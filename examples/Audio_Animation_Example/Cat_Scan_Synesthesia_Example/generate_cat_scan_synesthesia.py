#!/usr/bin/env python3
"""
generate_cat_scan_synesthesia.py
=================================
GlyphViz music synesthesia — Tangerine Dream, "Cat Scan".

Where Audio_Animation_Example was a spectral array (64 independent hyperglyphs,
one animated attribute), this is a *synesthesia instrument*: one master glyph
whose 64 children are the frequency bands, each band a 3-level hyperglyph with
a zone personality — geometry, palette, child count, and motion character all
change as frequency rises.

Scene structure
---------------
  branch 0   master root — a ghostly wire sphere ("the stage"). Its topology
             (Sphere) governs how the 64 band glyphs distribute: change the
             root's topo in the Properties panel and ALL 64 bands rearrange
             (torus ring, cylinder column, spiral, ...). The bands sit on a
             Fibonacci-sphere shell pushed out past the root's surface via
             structural translate_z — bass at the south pole, treble at the
             north, evenly spaced.
  branch 1   64 band roots (one per log-spaced frequency band, 20 Hz - 16 kHz)
  branch 2   N2 children per band root, arranged around it (Sphere topology)
  branch 3   N3 children per branch-2 node

Each band's hierarchy is 1 + N2 + N2*N3 = 55..91 objects (zone-dependent),
geometry constant per branch level within a band (hyperglyph-composer style).

Frequency zones (16 bands each)
--------------------------------
  DEEP   20-107 Hz     solid spheres + fat toruses, deep indigo->blue,
                       heavy slow scale-breathing, lazy spin, slow orbits
  FLOW   107-570 Hz    dodecahedra + cylinders + cubes, teal->emerald
  SHINE  570-3000 Hz   octahedra + cones, gold->orange, fast pinwheels,
                       POLAR orbits (translate_rate_y - latitude is periodic,
                       so children loop over the poles)
  SPARK  3-16 kHz      wire icosahedra + pins + tetras, magenta->near-white
                       sparks, snappiest envelopes, fastest equatorial orbits

Channel animation (5 signals per band + 1 master)
--------------------------------------------------
  band root   scale_x/y/z   <- envelope-followed band power (instant attack,
                               zone-tuned decay: bass booms linger, treble
                               snaps).  Scale cascades multiplicatively, so
                               the whole band hyperglyph breathes as one.
  branch 2    translate_z   <- altitude pop above the band root's surface
              rotate_rate_z <- pinwheel spin speed about the outward axis
  branch 3    translate_rate_x (or _y in SHINE) <- orbital speed around its
                               parent.  Longitude/latitude are periodic, so
                               orbiting children never fly off into space —
                               loud passages just orbit faster.
              translate_z   <- same altitude signal as branch 2 (smaller in
                               world units, cascaded by the parent's scale)
  master root scale_x/y/z   <- whole-scene breath, +/-5% from overall loudness

Rate attributes are set by the channels but integrated by the viewport
(60 cycles/s), so positions accumulate: on Stop the rates reset to 0 but the
orbits stay wherever the music left them — the glyph remembers the song.

Output files (written to --out, default: this folder)
------------------------------------------------------
  Cat_Scan_Synesthesia_Example_gv_node.csv       4,529 nodes
  Cat_Scan_Synesthesia_Example_gv_tag.csv        master + 64 band labels
  Cat_Scan_Synesthesia_Example_gv_ch-map.csv     channel -> attribute mappings
  Cat_Scan_Synesthesia_Example_gv_ch-tracks.csv  257 tracks x ~7,300 frames
  Cat_Scan_Synesthesia_Example_gv_audio.txt      relative path to the WAV

Usage
-----
  python generate_cat_scan_synesthesia.py
  python generate_cat_scan_synesthesia.py --wav path/to/other.wav --out scratch/

Load in GlyphViz: File > Open Node CSV -> Cat_Scan_Synesthesia_Example_gv_node.csv
Press Play in the Channels panel — audio plays in sync automatically.
"""

import argparse
import colorsys
import csv
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from glyphviz_core.audio_analysis import analyze

# ===========================================================================
# Parameters
# ===========================================================================

OUTPUT_DIR = Path(__file__).parent
PREFIX     = "Cat_Scan_Synesthesia_Example"
SOURCE_WAV = OUTPUT_DIR.parent / "Cat_Scan_Example" / "media" / "cat_scan_all_mono.wav"

N_BANDS = 64
FPS     = 30.0
F_LO    = 20.0
F_HI    = 16000.0

TOPO_SPHERE = 2
BASE_SCALE  = 1.0     # the desktop app's default Global Scale slider value

# Global motion multiplier applied to every animated signal's amplitude
# (scale swell gain, altitude pop, spin rate, orbit rate, master breath) —
# NOT to the rest sizes, which the scale tracks carry as absolute values.
# 1.0 = the original tuning; raised to 4.0 at Jeff's request after live
# testing ("not exaggerated enough").
EXAGGERATION = 4.0

# glyphviz_core/geometry_data.py ids
GEO_CUBE, GEO_SPHERE_WIRE, GEO_SPHERE = 1, 2, 3
GEO_CONE, GEO_TORUS, GEO_DODECA      = 5, 7, 9
GEO_OCTA, GEO_TETRA, GEO_ICOSA_WIRE  = 11, 13, 14
GEO_PIN, GEO_CYLINDER                = 16, 19

# --- world-space layout -----------------------------------------------------
# Sphere-topology child distance from parent center = (1 + translate_z) x
# parent world scale (topology.py _batched_kml with base_scale=1).  The master
# root's own radius is MASTER_SCALE; structural translate_z pushes the band
# glyphs out to a shell of radius SHELL_RADIUS.
MASTER_SCALE  = 2.5
SHELL_RADIUS  = 6.5
BAND_SHELL_Z  = SHELL_RADIUS / MASTER_SCALE - 1.0   # structural, not animated

# Band-root world radius shrinks from bass to treble ("low = bulky").
# The viewport floors *world* scale at 0.2/axis (viewport.py), so every
# level's world size below is chosen to stay >= 0.2 at rest.
ROOT_WORLD_LO = 0.68   # band 0 (deepest bass)
ROOT_WORLD_HI = 0.44   # band 63 (highest treble)


@dataclass(frozen=True)
class Zone:
    """One frequency zone's complete personality (16 consecutive bands)."""
    name: str
    geo_l1: int; geo_l2: int; geo_l3: int
    n2: int; n3: int              # children per band root / per L2 node
    l2_world: float               # L2 world radius (uniform scale)
    l3_world: float               # L3 world radius
    hue_lo: float; hue_hi: float  # palette hue range across the zone's bands
    sat: float; val: float        # base saturation/value (L2 level)
    l2_lat: float                 # |latitude| of alternating L2 rings (0 = equator)
    scale_gain: float             # band-root scale swells by (1 + gain*env)
    tau_scale: float              # envelope decay (s) for the scale swell
    alt_peak: float               # branch-2 translate_z at full band power
    spin_peak: float              # rotate_rate_z deg/cycle (60 cyc/s) at full power
    orbit_peak: float             # translate_rate deg/cycle at full power
    orbit_axis: str               # 'translate_rate_x' (equatorial) or '_y' (polar)
    ratio: float                  # geometry ratio (torus tube fatness etc.)


ZONES = [
    Zone("DEEP",  GEO_SPHERE, GEO_TORUS,    GEO_SPHERE,  6, 8, 0.40, 0.26,
         0.72, 0.60, 0.85, 0.62, 0.0,
         0.90, 0.50, 0.70, 0.6, 0.30, 'translate_rate_x', 0.32),
    Zone("FLOW",  GEO_DODECA, GEO_CYLINDER, GEO_CUBE,    7, 8, 0.37, 0.25,
         0.55, 0.40, 0.80, 0.72, 18.0,
         0.75, 0.32, 0.85, 1.2, 0.70, 'translate_rate_x', 0.22),
    Zone("SHINE", GEO_OCTA,   GEO_CONE,     GEO_OCTA,    8, 8, 0.33, 0.23,
         0.13, 0.04, 0.92, 0.88, 32.0,
         0.62, 0.20, 1.00, 2.2, 1.30, 'translate_rate_y', 0.18),
    Zone("SPARK", GEO_ICOSA_WIRE, GEO_PIN,  GEO_TETRA,  10, 8, 0.29, 0.21,
         0.90, 0.99, 0.88, 1.00, 48.0,
         0.50, 0.12, 1.20, 3.5, 2.40, 'translate_rate_x', 0.14),
]
BANDS_PER_ZONE = N_BANDS // len(ZONES)

GOLDEN_ANGLE = 137.50776405   # degrees — Fibonacci sphere / vogel spiral

# Channel/track id scheme (all 1-indexed):
#   band i:  channels 3i+1 (root scale), 3i+2 (L2), 3i+3 (L3)   -> 1..192
#            tracks   4i+1 (scale), 4i+2 (alt), 4i+3 (spin), 4i+4 (orbit)
#   master:  channel 193, track 257
CH_MASTER    = 3 * N_BANDS + 1
TRACK_MASTER = 4 * N_BANDS + 1
MASTER_BREATH_GAIN = 0.05
MASTER_TAU         = 0.6


# ===========================================================================
# Signal shaping
# ===========================================================================

def envelope(p: np.ndarray, fps: float, tau: float) -> np.ndarray:
    """Peak-follower: instant attack, exponential decay with time constant tau.
    Turns spiky per-frame FFT power into musical swells — a drum hit blooms
    instantly then relaxes over tau seconds instead of strobing."""
    decay = math.exp(-1.0 / (fps * tau))
    env = np.empty_like(p)
    e = 0.0
    for t in range(len(p)):
        e = max(float(p[t]), e * decay)
        env[t] = e
    return env


def zone_of_band(i: int) -> Zone:
    return ZONES[min(i // BANDS_PER_ZONE, len(ZONES) - 1)]


def band_root_world(i: int) -> float:
    f = i / (N_BANDS - 1)
    return ROOT_WORLD_LO + (ROOT_WORLD_HI - ROOT_WORLD_LO) * f


def band_colors(i: int) -> tuple[tuple[int, int, int], ...]:
    """(L1, L2, L3) colors for band i: hue slides across the zone, value
    deepens toward the core (L1) and brightens/desaturates at the tips (L3) —
    SPARK's branch-3 tetras wash out to near-white."""
    z = zone_of_band(i)
    f = (i % BANDS_PER_ZONE) / max(BANDS_PER_ZONE - 1, 1)
    hue = (z.hue_lo + (z.hue_hi - z.hue_lo) * f) % 1.0
    lvl = [
        (hue, z.sat,        min(1.0, z.val * 0.78)),
        (hue, z.sat,        z.val),
        (hue, z.sat * 0.45, min(1.0, z.val + 0.22)),
    ]
    out = []
    for h, s, v in lvl:
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        out.append((int(r * 255), int(g * 255), int(b * 255)))
    return tuple(out)


def fibonacci_shell(n: int) -> list[tuple[float, float]]:
    """(longitude, latitude) degrees for n evenly-spaced points on a sphere,
    monotonic in latitude: index 0 (deepest bass) at the south pole rising to
    index n-1 (treble) at the north — an even scatter that still reads
    low-to-high."""
    pts = []
    for i in range(n):
        lat = math.degrees(math.asin(2.0 * (i + 0.5) / n - 1.0))
        lon = (i * GOLDEN_ANGLE) % 360.0
        pts.append((lon, lat))
    return pts


def l2_placement(z: Zone) -> list[tuple[float, float]]:
    """(lon, lat) for a band's branch-2 children: even longitudes, latitude
    alternating +/- z.l2_lat (DEEP keeps a flat equatorial ring at lat 0)."""
    pts = []
    for j in range(z.n2):
        lon = j * 360.0 / z.n2
        lat = z.l2_lat * (1 if j % 2 == 0 else -1)
        pts.append((lon, lat))
    return pts


def l3_placement(z: Zone) -> list[tuple[float, float]]:
    pts = []
    for k in range(z.n3):
        lon = k * 360.0 / z.n3
        lat = 12.0 * (1 if k % 2 == 0 else -1) if z.l2_lat > 20 else 0.0
        pts.append((lon, lat))
    return pts


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


def _node_row(node_id, parent_id, level, tx, ty, tz, scale, color, alpha,
              geometry, ratio, ch_input_id):
    r, g, b = color
    return {
        "id": node_id, "type": 5, "parent_id": parent_id, "branch_level": level,
        "translate_x": round(tx, 4), "translate_y": round(ty, 4), "translate_z": round(tz, 4),
        "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
        "scale_x": round(scale, 5), "scale_y": round(scale, 5), "scale_z": round(scale, 5),
        "color_r": r, "color_g": g, "color_b": b, "color_a": alpha,
        "geometry": geometry, "hide": 0, "topo": TOPO_SPHERE, "ratio": ratio,
        "ch_input_id": ch_input_id,
    }


def build_nodes() -> tuple[list[dict], list[int]]:
    """Returns (node rows, band-root node ids)."""
    rows = []
    rows.append(_node_row(1, 0, 0, 0.0, 0.0, 0.0, MASTER_SCALE,
                          (58, 58, 92), 60, GEO_SPHERE_WIRE, 0.1, CH_MASTER))
    shell = fibonacci_shell(N_BANDS)
    band_root_ids = []
    next_id = 2
    for i in range(N_BANDS):
        z = zone_of_band(i)
        c1, c2, c3 = band_colors(i)
        w_root = band_root_world(i)
        s_root = w_root / MASTER_SCALE
        s_l2   = z.l2_world / w_root
        s_l3   = z.l3_world / z.l2_world
        lon, lat = shell[i]
        ch_root, ch_l2, ch_l3 = 3 * i + 1, 3 * i + 2, 3 * i + 3

        root_id = next_id
        next_id += 1
        band_root_ids.append(root_id)
        rows.append(_node_row(root_id, 1, 1, lon, lat, BAND_SHELL_Z,
                              s_root, c1, 255, z.geo_l1, z.ratio, ch_root))
        for lon2, lat2 in l2_placement(z):
            l2_id = next_id
            next_id += 1
            rows.append(_node_row(l2_id, root_id, 2, lon2, lat2, 0.0,
                                  s_l2, c2, 255, z.geo_l2, z.ratio, ch_l2))
            for lon3, lat3 in l3_placement(z):
                l3_id = next_id
                next_id += 1
                rows.append(_node_row(l3_id, l2_id, 3, lon3, lat3, 0.0,
                                      s_l3, c3, 255, z.geo_l3, z.ratio, ch_l3))
    return rows, band_root_ids


def build_ch_map() -> list[dict]:
    rows = []
    rid = 0

    def add(ch, track, attr):
        nonlocal rid
        rows.append({"id": rid, "channel_id": ch, "track_id": track,
                     "attribute": attr, "track_table_id": 0,
                     "ch_map_table_id": 0, "record_id": 0})
        rid += 1

    for i in range(N_BANDS):
        z = zone_of_band(i)
        t_scale, t_alt, t_spin, t_orbit = 4 * i + 1, 4 * i + 2, 4 * i + 3, 4 * i + 4
        for attr in ("scale_x", "scale_y", "scale_z"):
            add(3 * i + 1, t_scale, attr)
        add(3 * i + 2, t_alt, "translate_z")
        add(3 * i + 2, t_spin, "rotate_rate_z")
        add(3 * i + 3, t_orbit, z.orbit_axis)
        add(3 * i + 3, t_alt, "translate_z")
    for attr in ("scale_x", "scale_y", "scale_z"):
        add(CH_MASTER, TRACK_MASTER, attr)
    return rows


def build_tracks(tracks: np.ndarray) -> np.ndarray:
    """(n_frames, 257) absolute channel-track values from normalized band power."""
    n_frames = tracks.shape[0]
    out = np.zeros((n_frames, TRACK_MASTER), dtype=np.float64)
    for i in range(N_BANDS):
        z = zone_of_band(i)
        p = tracks[:, i]
        env_scale = envelope(p, FPS, z.tau_scale)
        env_alt   = envelope(p, FPS, max(0.08, z.tau_scale * 0.5))
        s_root = band_root_world(i) / MASTER_SCALE
        out[:, 4 * i + 0] = s_root * (1.0 + EXAGGERATION * z.scale_gain * env_scale)
        out[:, 4 * i + 1] = EXAGGERATION * z.alt_peak * env_alt
        out[:, 4 * i + 2] = EXAGGERATION * z.spin_peak * p
        out[:, 4 * i + 3] = EXAGGERATION * z.orbit_peak * p
    loudness = tracks.mean(axis=1)
    peak = loudness.max()
    if peak > 0:
        loudness = loudness / peak
    env_master = envelope(loudness, FPS, MASTER_TAU)
    out[:, TRACK_MASTER - 1] = MASTER_SCALE * (
        1.0 + EXAGGERATION * MASTER_BREATH_GAIN * env_master)
    return out


def write_nodes(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=NODE_FIELDS)
        w.writeheader()
        w.writerows(rows)
    per_band = [(1 + z.n2 + z.n2 * z.n3) for z in ZONES]
    print(f"  {path.name}: {len(rows)} nodes "
          f"(1 master + 64 band glyphs of {'/'.join(map(str, per_band))} objects per zone)")


def write_tags(path: Path, band_freqs, band_root_ids) -> None:
    rows = [{"id": 0, "table_id": 0, "record_id": 1,
             "title": "Cat Scan — Tangerine Dream"}]
    for i, (freq, rid) in enumerate(zip(band_freqs, band_root_ids)):
        z = zone_of_band(i)
        rows.append({"id": i + 1, "table_id": 0, "record_id": rid,
                     "title": f"{z.name} {freq:.0f} Hz"})
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "table_id", "record_id", "title"])
        w.writeheader()
        w.writerows(rows)
    print(f"  {path.name}: {len(rows)} labels")


def write_ch_map(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "channel_id", "track_id", "attribute",
                                          "track_table_id", "ch_map_table_id", "record_id"])
        w.writeheader()
        w.writerows(rows)
    print(f"  {path.name}: {len(rows)} mappings across {CH_MASTER} channels")


def write_ch_tracks(path: Path, out: np.ndarray) -> None:
    n_frames, n_tracks = out.shape
    cols = [f"ch{i + 1}" for i in range(n_tracks)]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["cyclecount"] + cols)
        for j in range(n_frames):
            w.writerow([j] + [f"{v:.5f}" for v in out[j]])
    print(f"  {path.name}: {n_frames} frames x {n_tracks} tracks")


def write_audio_manifest(path: Path, wav_path: Path, out_dir: Path) -> None:
    rel = os.path.relpath(wav_path.resolve(), out_dir.resolve())
    path.write_text(rel.replace("\\", "/") + "\n", encoding="utf-8")
    print(f"  {path.name}: -> {rel}")


def generate(source_wav: Path, out_dir: Path):
    """Full pipeline; returns (tracks, band_freqs, duration_s) for notebooks."""
    print(f"Analyzing {source_wav.name} ({N_BANDS} bands, {FPS} fps, {F_LO}-{F_HI} Hz)...")
    tracks, band_freqs, duration_s = analyze(
        source_wav, n_bands=N_BANDS, fps=FPS, f_lo=F_LO, f_hi=F_HI)
    print(f"  {duration_s:.1f}s of audio -> {tracks.shape[0]} frames")

    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nWriting {PREFIX} to {out_dir}/\n")
    node_rows, band_root_ids = build_nodes()
    write_nodes         (out_dir / f"{PREFIX}_gv_node.csv", node_rows)
    write_tags          (out_dir / f"{PREFIX}_gv_tag.csv", band_freqs, band_root_ids)
    write_ch_map        (out_dir / f"{PREFIX}_gv_ch-map.csv", build_ch_map())
    write_ch_tracks     (out_dir / f"{PREFIX}_gv_ch-tracks.csv", build_tracks(tracks))
    write_audio_manifest(out_dir / f"{PREFIX}_gv_audio.txt", source_wav, out_dir)
    return tracks, band_freqs, duration_s


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GlyphViz music synesthesia generator")
    parser.add_argument("--wav", type=Path, default=SOURCE_WAV)
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR,
                        help="output directory (default: this example's folder)")
    args = parser.parse_args()
    wav = args.wav if args.wav.is_absolute() else OUTPUT_DIR / args.wav
    out = args.out if args.out.is_absolute() else OUTPUT_DIR / args.out

    generate(wav, out)

    print(f"\nDone.  Open GlyphViz, then:")
    print(f"  File > Open Node CSV -> {PREFIX}_gv_node.csv")
    print(f"  Press Play — audio plays in sync.  Try changing the master root's")
    print(f"  topology (Torus, Cylinder, Spiral...) to rearrange all 64 bands.")
