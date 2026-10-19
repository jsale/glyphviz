"""Does GlyphViz put every part where Blender put it?  (glyphviz env python)

    python verify_scene.py <bake_dir> <scene_dir> [frame ...]

For each frame: pose the scene with the app's OWN ChannelEngine + Scene math,
transform each part's imported (normalized) mesh to world space, and compare
with Blender's world-space vertices (baked matrix @ OBJ-local vertex, times the
export scale).  Reports the worst symmetric nearest-neighbour distance per frame.
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from glyphviz_core.channel_engine import ChannelEngine            # noqa: E402
from glyphviz_core.channel_loader import (                        # noqa: E402
    find_channel_files, load_ch_map, load_ch_tracks)
from glyphviz_core.csv_reader import load_node_csv                # noqa: E402
from glyphviz_core.mesh_loader import load_mesh_file              # noqa: E402
from glyphviz_core.scene import Scene, node_world_matrix          # noqa: E402


def read_obj(path):
    return np.array([[float(t) for t in l.split()[1:4]]
                     for l in Path(path).read_text(encoding="utf-8").splitlines()
                     if l.startswith("v ")])


def main(bake_dir, scene_dir, frames, S=10.0):
    bake_dir, scene_dir = Path(bake_dir), Path(scene_dir)
    data = json.loads((bake_dir / "bake.json").read_text(encoding="utf-8"))
    csv = next(scene_dir.glob("*_gv_node.csv"))
    nodes = load_node_csv(str(csv))
    mp, tp = find_channel_files(str(csv))
    ch_map = load_ch_map(mp)
    tracks, id_to_col = load_ch_tracks(tp)
    eng = ChannelEngine()
    eng.load(ch_map, tracks, id_to_col, nodes)
    names = sorted(data["objects"])
    mesh_files = sorted((scene_dir / "meshes").glob("*.obj"))
    unit = {}
    for i, p in enumerate(mesh_files, 1):
        md = load_mesh_file(str(p))
        unit[i] = np.asarray(md.vertices, dtype=float)
    by_mesh = {n.mesh_id: n for n in nodes if n.type == 5}
    sc = Scene(nodes, 1.0)
    worst_all = 0.0
    frames = frames or [0, len(tracks) // 4, len(tracks) // 2, len(tracks) - 1]
    for f in frames:
        eng.apply_frame(f)
        sc.invalidate()
        worst = 0.0
        for i, p in enumerate(mesh_files, 1):
            node = by_mesh[i]
            W = node_world_matrix(node, sc)
            v = unit[i]
            gv = (W @ np.c_[v, np.ones(len(v))].T).T[:, :3]
            M = np.asarray(data["objects"][p.stem]["m"][f], dtype=float).reshape(3, 4)
            lv = read_obj(p)
            bl = (lv @ M[:, :3].T + M[:, 3]) * S
            d1 = cKDTree(gv).query(bl)[0].max()
            d2 = cKDTree(bl).query(gv)[0].max()
            worst = max(worst, d1, d2)
            if max(d1, d2) > 0.05:
                print("  frame %d  %-12s  MISMATCH  %.4f / %.4f" % (f, p.stem, d1, d2))
        print("frame %3d: worst vertex distance %.5f world units" % (f, worst))
        worst_all = max(worst_all, worst)
    print("OK" if worst_all < 0.05 else "FAIL", " worst overall %.5f" % worst_all)
    return worst_all


if __name__ == "__main__":
    fr = [int(a) for a in sys.argv[3:]]
    main(sys.argv[1], sys.argv[2], fr)
