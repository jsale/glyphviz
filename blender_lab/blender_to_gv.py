"""Turn a Blender bake (export_for_glyphviz.py) into a GlyphViz scene folder.

    python blender_to_gv.py <bake_dir> <scene_folder> <stem> [--scale 10]

Run with the glyphviz env's python.  One flat node per rigid part:

    node position = world position of the part's BOUNDING-BOX CENTRE
    node rotation = the part's world rotation, re-expressed as GlyphViz Euler
    node scale    = mesh radius * S          (the importer normalizes every mesh
                                              to unit radius about its own bbox
                                              centre, so this restores true size)

That is exact for a rigid part: M(v) = M(c) + R (v - c).  Only the attributes
that actually change over the loop become channel tracks; parts whose motion is
identical share a channel.  GlyphViz channels hard-set each frame with no
interpolation, so the bake IS the animation.
"""
import argparse
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "mesh_creation_lab"))
sys.path.insert(0, str(REPO))

from gvscene import SceneBuilder            # noqa: E402
from glyphviz_core.topology import local_rotation_matrix  # noqa: E402
from glyphviz_core.node import ROTATION_MODE_EULER_XYZ    # noqa: E402


def read_obj(path):
    v = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("v "):
            v.append([float(t) for t in line.split()[1:4]])
    return np.asarray(v)


def mesh_center_radius(verts):
    """Mirror of mesh_loader's normalization (bbox centre, max-norm radius)."""
    lo, hi = verts.min(axis=0), verts.max(axis=0)
    c = (lo + hi) / 2.0
    r = float(np.max(np.linalg.norm(verts - c, axis=1)))
    return c, (r if r > 1e-12 else 1.0)


def euler_xyz_deg(R):
    """Angles with Rx(rx) @ Ry(ry) @ Rz(rz) == R  (GlyphViz EULER_XYZ order)."""
    cy = math.hypot(R[0, 0], R[0, 1])
    ry = math.atan2(R[0, 2], cy)            # atan2, not asin: accurate right up to the pole
    if cy > 1e-9:
        rx = math.atan2(-R[1, 2], R[2, 2])
        rz = math.atan2(-R[0, 1], R[0, 0])
    else:                                   # gimbal lock: only x+z (or z-x) is defined; put it in rx
        rz = 0.0
        a = math.atan2(R[1, 0], R[1, 1])
        rx = a if R[0, 2] > 0 else -a
    return np.degrees([rx, ry, rz])


def _num(x):
    """Shortest 4-decimal form; never '-0' (it breaks round-trip idempotence)."""
    s = ("%.4f" % x).rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def euler_track(Rs):
    """Continuous GlyphViz Euler angles for a sequence of rotation matrices.

    Every rotation has two Rx.Ry.Rz solutions, (rx,ry,rz) and
    (rx+180, 180-ry, rz+180).  Picking per frame the one nearest the previous
    frame (after 360-degree unwrapping) keeps a plain spin about one axis on
    that axis alone -- otherwise past +-90 degrees it flips to the second branch
    and drags two extra, spurious, animated tracks along with it."""
    out = []
    for R in Rs:
        s1 = euler_xyz_deg(R)
        s2 = np.array([s1[0] + 180.0, 180.0 - s1[1], s1[2] + 180.0])
        if not out:
            out.append(s1 if abs(s1[0]) + abs(s1[2]) <= abs(s2[0]) + abs(s2[2]) + 1e-9
                       else s2 - 360.0 * np.round(s2 / 360.0))
            continue
        prev = out[-1]
        best = None
        for s in (s1, s2):
            u = s - 360.0 * np.round((s - prev) / 360.0)
            d = float(np.abs(u - prev).sum())
            if best is None or d < best[0]:
                best = (d, u)
        out.append(best[1])
    return np.array(out)


def convert(bake_dir, scene_dir, stem, S, rot_tol=1e-4):
    bake_dir, scene_dir = Path(bake_dir), Path(scene_dir)
    data = json.loads((bake_dir / "bake.json").read_text(encoding="utf-8"))
    names = sorted(data["objects"])
    (scene_dir / "meshes").mkdir(parents=True, exist_ok=True)
    for old in (scene_dir / "meshes").glob("*.obj"):
        old.unlink()
    sb = SceneBuilder(scene_dir, stem, background=(10, 12, 20))
    for nm in names:
        shutil.copyfile(bake_dir / "meshes" / (nm + ".obj"), scene_dir / "meshes" / (nm + ".obj"))
        sb.register_mesh(nm + ".obj")

    channels = {}            # key(tuple of (attr, track-key)) -> channel id
    chan_rows = []           # (channel_id, track_id, attribute)
    tracks = {}              # track-key -> (track_id, values)
    stats = {"parts": 0, "moving": 0, "tracks": 0, "channels": 0}

    def track_id(values):
        key = tuple(np.round(values, 4))
        if key not in tracks:
            tracks[key] = (len(tracks) + 1, np.asarray(key))
        return tracks[key][0]

    for nm in names:
        rec = data["objects"][nm]
        M = np.asarray(rec["m"], dtype=float).reshape(-1, 3, 4)
        P = np.asarray(rec["p"], dtype=float)            # gv_r,g,b,a,hide
        verts = read_obj(bake_dir / "meshes" / (nm + ".obj"))
        c, radius = mesh_center_radius(verts)
        R = M[:, :, :3]
        det = np.linalg.det(R)
        if np.abs(det - 1.0).max() > 1e-3:
            raise ValueError("%s: world matrix is not a pure rotation (det %.4f) -- "
                             "object scale/mirror must be baked into the mesh" % (nm, det.min()))
        pos = (np.einsum("fij,j->fi", R, c) + M[:, :, 3]) * S
        # Blender stores float32 matrices: snap each to the nearest true rotation first, or the
        # asin in the decomposition amplifies that noise near the +-90 degree pole.
        u_, _, vt_ = np.linalg.svd(R)
        Rn = u_ @ vt_
        rot = euler_track(Rn)

        # self-check every frame against the app's own rotation function
        for f in range(len(R)):
            got = np.array(local_rotation_matrix(*rot[f], ROTATION_MODE_EULER_XYZ))
            if np.abs(got - Rn[f]).max() > 1e-9 or np.abs(got - R[f]).max() > 1e-5:
                raise AssertionError("%s frame %d: Euler decomposition mismatch" % (nm, f))

        cols = {"translate_x": pos[:, 0], "translate_y": pos[:, 1], "translate_z": pos[:, 2],
                "rotate_x": rot[:, 0], "rotate_y": rot[:, 1], "rotate_z": rot[:, 2],
                "color_r": P[:, 0], "color_g": P[:, 1], "color_b": P[:, 2],
                "color_a": P[:, 3], "hide": P[:, 4]}
        dyn = {}
        for k, v in cols.items():
            if k.startswith("color") or k == "hide":
                tol = 0.5
            elif k.startswith("rotate"):
                tol = rot_tol
            else:
                tol = 1e-5 * max(1.0, S)
            if v.max() - v.min() > tol:
                dyn[k] = v
        first = {k: float(v[0]) for k, v in cols.items()}
        node = sb.add(mesh=nm + ".obj",
                      pos=(first["translate_x"], first["translate_y"], first["translate_z"]),
                      rot=(first["rotate_x"], first["rotate_y"], first["rotate_z"]),
                      scale=radius * S,
                      color=(round(first["color_r"]), round(first["color_g"]), round(first["color_b"])),
                      alpha=round(first["color_a"]), hide=int(first["hide"] > 0.5),
                      text=rec.get("label", ""))
        stats["parts"] += 1
        if dyn:
            stats["moving"] += 1
            rows = tuple(sorted((attr, track_id(v)) for attr, v in dyn.items()))
            if rows not in channels:
                cid = len(channels) + 1
                channels[rows] = cid
                chan_rows.extend((cid, tid, attr) for attr, tid in rows)
            node.extras["ch_input_id"] = channels[rows]

    sb.finish()
    frames = data["frames"]
    stem_path = scene_dir / stem
    with open(str(stem_path) + "_gv_ch-map.csv", "w", encoding="utf-8", newline="") as fh:
        fh.write("id,channel_id,track_id,attribute\r\n")
        for i, (cid, tid, attr) in enumerate(chan_rows, 1):
            fh.write("%d,%d,%d,%s\r\n" % (i, cid, tid, attr))
    ordered = sorted(tracks.values())
    with open(str(stem_path) + "_gv_ch-tracks.csv", "w", encoding="utf-8", newline="") as fh:
        fh.write("cyclecount," + ",".join("ch%d" % t for t, _ in ordered) + "\r\n")
        for f in range(frames):
            fh.write(str(f) + "," + ",".join(_num(v[f]) for _, v in ordered) + "\r\n")
    stats.update(tracks=len(ordered), channels=len(channels), frames=frames)
    print("  ", stats)
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("bake_dir")
    ap.add_argument("scene_dir")
    ap.add_argument("stem")
    ap.add_argument("--scale", type=float, default=10.0)
    a = ap.parse_args()
    convert(a.bake_dir, a.scene_dir, a.stem, a.scale)
