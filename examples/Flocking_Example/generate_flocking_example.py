#!/usr/bin/env python3
"""
generate_flocking_example.py
============================
A classic Reynolds "boids" flocking simulation, precomputed and baked into
GlyphViz Channels files: every boid is one node whose translate_x/y/z are
driven by 3 tracks, so N boids means 3*N tracks (100 boids = 300 tracks --
well within what Channels playback already handles).

The three steering rules (each a clamped Reynolds steering force,
desired_velocity - current_velocity):
  separation -- steer away from neighbors closer than R_SEPARATION,
                weighted 1/distance^2 so near-collisions dominate
  alignment  -- steer toward the mean heading of neighbors within R_PERCEPTION
  cohesion   -- steer toward the centroid of neighbors within R_PERCEPTION
plus a soft spherical containment: outside R_BOUND, a pull back toward the
origin that grows with the overshoot (no hard wall, so turns stay smooth).

Speed is clamped to [MIN_SPEED, MAX_SPEED] each step -- the floor keeps
boids from stalling mid-air, the ceiling keeps the flock coherent. The sim
runs WARMUP_STEPS before recording so frame 0 already shows a formed flock
rather than the random initial scatter (also softens the jump when Channels
playback loops -- the loop seam itself can't be continuous, since flocking
is chaotic).

Boids are colored by a hue wheel over their index, which makes the mixing/
splitting of sub-flocks easy to track by eye.

Simulation is O(N^2) per frame via a dense pairwise-offset array; fine for
the default 100 boids, and still tractable (a minute or two, ~GB-scale
temporaries) at Jeff's 1000+ channel scale.

Output files (written to --output-dir, default: this script's folder)
---------------------------------------------------------------------
  {PREFIX}_gv_node.csv       N boid nodes (GEO_OCTA darts, hue-wheel colors)
  {PREFIX}_gv_tag.csv        one "Boid N" label per node
  {PREFIX}_gv_ch-map.csv     channel i+1 -> tracks 3i/3i+1/3i+2 -> translate_x/y/z
  {PREFIX}_gv_ch-tracks.csv  N_FRAMES frames x 3*N tracks

Usage
-----
  python generate_flocking_example.py                 # 100 boids, 1800 frames
  python generate_flocking_example.py --n-boids 250 --frames 900 --seed 7

Load in GlyphViz: File > Open Node CSV -> {PREFIX}_gv_node.csv, then start
Channels playback (60s loop at the default 30fps for the default 1800 frames).
"""

import argparse
import colorsys
import csv
from pathlib import Path

import numpy as np

PREFIX = "Flocking_Example"

GEO_OCTA = 11   # solid octahedron -- reads as a bird-ish dart at flock scale

# --- simulation parameters (world units; one sim step = one playback frame,
# i.e. 1/30 s at the app's default Channels rate) ---
INIT_RADIUS = 50.0       # initial random scatter
R_BOUND = 90.0           # soft containment sphere -- flock lives in ~±100
R_PERCEPTION = 18.0      # neighbor radius for alignment + cohesion
R_SEPARATION = 6.0       # personal-space radius
MAX_SPEED = 1.0          # units/frame = 30 units/s
MIN_SPEED = 0.4
MAX_FORCE = 0.04         # steering clamp -- turn rate, effectively
W_SEPARATION = 1.6
W_ALIGNMENT = 1.0
W_COHESION = 0.8
BOUND_GAIN = 0.02        # containment acceleration per unit of overshoot
WARMUP_STEPS = 300       # sim steps discarded before recording starts

BOID_SCALE = 2.0         # tuned for the base_scale=1.0 default


def _limit(vec: np.ndarray, max_norm: float) -> np.ndarray:
    """Clamp each row of (N,3) vec to max_norm."""
    norms = np.linalg.norm(vec, axis=1, keepdims=True)
    factor = np.minimum(1.0, max_norm / np.maximum(norms, 1e-12))
    return vec * factor


def _steer(desired: np.ndarray, vel: np.ndarray) -> np.ndarray:
    """Reynolds steering: (desired direction at MAX_SPEED) - velocity,
    clamped to MAX_FORCE. Rows with a zero desired vector steer nowhere."""
    norms = np.linalg.norm(desired, axis=1, keepdims=True)
    has = norms[:, 0] > 1e-9
    out = np.zeros_like(desired)
    out[has] = desired[has] / norms[has] * MAX_SPEED - vel[has]
    return _limit(out, MAX_FORCE)


def simulate(n_boids: int, n_frames: int, rng: np.random.Generator) -> np.ndarray:
    """Run the boids sim; returns positions of shape (n_frames, n_boids, 3)."""
    pos = rng.uniform(-INIT_RADIUS, INIT_RADIUS, (n_boids, 3))
    vel = rng.normal(size=(n_boids, 3))
    vel = vel / np.linalg.norm(vel, axis=1, keepdims=True) * (0.5 * (MIN_SPEED + MAX_SPEED))

    frames = np.empty((n_frames, n_boids, 3))
    for step in range(WARMUP_STEPS + n_frames):
        # offsets[i, j] = pos[j] - pos[i]
        offsets = pos[None, :, :] - pos[:, None, :]
        d2 = np.einsum('ijk,ijk->ij', offsets, offsets)
        np.fill_diagonal(d2, np.inf)

        near = d2 < R_PERCEPTION ** 2
        count = near.sum(axis=1)
        safe = np.maximum(count, 1)[:, None]

        # cohesion: toward the neighbor centroid (mean offset IS centroid - self)
        coh_desired = (offsets * near[:, :, None]).sum(axis=1) / safe
        # alignment: toward the neighbors' mean velocity
        ali_desired = (near.astype(float) @ vel) / safe
        # separation: away from close neighbors, 1/d^2-weighted
        close = d2 < R_SEPARATION ** 2
        sep_desired = -(offsets / d2[:, :, None] * close[:, :, None]).sum(axis=1)

        accel = (W_SEPARATION * _steer(sep_desired, vel)
                 + W_ALIGNMENT * _steer(ali_desired, vel)
                 + W_COHESION * _steer(coh_desired, vel))

        # soft containment: pull toward origin, growing with overshoot
        r = np.linalg.norm(pos, axis=1, keepdims=True)
        overshoot = np.maximum(r - R_BOUND, 0.0)
        accel += -pos / np.maximum(r, 1e-9) * overshoot * BOUND_GAIN

        vel = vel + accel
        speed = np.linalg.norm(vel, axis=1, keepdims=True)
        speed_clamped = np.clip(speed, MIN_SPEED, MAX_SPEED)
        vel = vel / np.maximum(speed, 1e-12) * speed_clamped
        pos = pos + vel

        if step >= WARMUP_STEPS:
            frames[step - WARMUP_STEPS] = pos
    return frames


# ===========================================================================
# Writers (same file contracts as Multi_Hike_Race_Example)
# ===========================================================================

NODE_FIELDS = [
    "id", "type", "parent_id", "branch_level",
    "translate_x", "translate_y", "translate_z",
    "rotate_x", "rotate_y", "rotate_z",
    "scale_x", "scale_y", "scale_z",
    "color_r", "color_g", "color_b", "color_a",
    "geometry", "hide", "topo", "ratio", "ch_input_id",
]


def boid_color(i: int, n: int) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(i / max(n, 1), 0.75, 1.0)
    return int(r * 255), int(g * 255), int(b * 255)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-boids", type=int, default=100)
    parser.add_argument("--frames", type=int, default=1800,
                        help="playback frames (1800 = 60s at the default 30fps)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    n = args.n_boids

    print(f"Simulating {n} boids x {WARMUP_STEPS} warmup + {args.frames} recorded steps...")
    rng = np.random.default_rng(args.seed)
    frames = simulate(n, args.frames, rng)

    # quick health readout: flock polarization (1.0 = perfectly aligned)
    final_vel = frames[-1] - frames[-2]
    polarization = np.linalg.norm(
        (final_vel / np.linalg.norm(final_vel, axis=1, keepdims=True)).mean(axis=0))
    r_final = np.linalg.norm(frames[-1], axis=1)
    print(f"  final-frame polarization {polarization:.2f}, "
          f"radius {r_final.min():.0f}-{r_final.max():.0f} (soft bound {R_BOUND:.0f})")

    nodes, tags, ch_map_rows = [], [], []
    for i in range(n):
        node_id = i + 1
        ch_id = i + 1          # 1-indexed: channel_id 0 means "not animated"
        x0, y0, z0 = frames[0, i]
        nodes.append({
            "id": node_id, "type": 5, "parent_id": 0, "branch_level": 0,
            "translate_x": round(float(x0), 4), "translate_y": round(float(y0), 4),
            "translate_z": round(float(z0), 4),
            "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
            "scale_x": BOID_SCALE, "scale_y": BOID_SCALE, "scale_z": BOID_SCALE,
            "color_r": boid_color(i, n)[0], "color_g": boid_color(i, n)[1],
            "color_b": boid_color(i, n)[2], "color_a": 255,
            "geometry": GEO_OCTA, "hide": 0, "topo": 0, "ratio": 0.1,
            "ch_input_id": ch_id,
        })
        tags.append({"id": i, "table_id": 0, "record_id": node_id,
                     "title": f"Boid {node_id}"})
        for axis_idx, attr in enumerate(("translate_x", "translate_y", "translate_z")):
            ch_map_rows.append({
                "id": len(ch_map_rows), "channel_id": ch_id,
                "track_id": 3 * i + axis_idx, "attribute": attr,
                "track_table_id": 0, "ch_map_table_id": 0, "record_id": 0,
            })

    node_path = out_dir / f"{PREFIX}_gv_node.csv"
    with open(node_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=NODE_FIELDS)
        w.writeheader()
        w.writerows(nodes)
    print(f"\n{node_path.name}: {len(nodes)} nodes")

    tag_path = out_dir / f"{PREFIX}_gv_tag.csv"
    with open(tag_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "table_id", "record_id", "title"])
        w.writeheader()
        w.writerows(tags)
    print(f"{tag_path.name}: {len(tags)} labels")

    ch_map_path = out_dir / f"{PREFIX}_gv_ch-map.csv"
    with open(ch_map_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "channel_id", "track_id", "attribute",
                                          "track_table_id", "ch_map_table_id", "record_id"])
        w.writeheader()
        w.writerows(ch_map_rows)
    print(f"{ch_map_path.name}: {len(ch_map_rows)} channel mappings")

    ch_tracks_path = out_dir / f"{PREFIX}_gv_ch-tracks.csv"
    with open(ch_tracks_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cyclecount"] + [f"ch{t}" for t in range(3 * n)])
        flat = frames.reshape(args.frames, 3 * n)   # boid-major: tracks 3i..3i+2
        for frame_idx in range(args.frames):
            w.writerow([frame_idx] + [round(float(v), 4) for v in flat[frame_idx]])
    print(f"{ch_tracks_path.name}: {args.frames} frames x {3 * n} tracks")

    print(f"\nDone. Open GlyphViz, then: File > Open Node CSV -> {node_path.name}")


if __name__ == "__main__":
    main()
