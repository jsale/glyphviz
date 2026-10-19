"""Runs INSIDE Blender: bake every part flagged with the "gv" custom property.

Writes, into OUT_DIR:
    meshes/<name>.obj   triangulated, in the object's LOCAL space (no scale)
    bake.json           per-frame world matrices + animated colour/hide props

Frames are sampled with scene.frame_set(), so anything Blender evaluates
(constraints, drivers, parenting, keyframes) lands in the bake -- only the final
rigid pose is exported, which is all a GlyphViz channel can represent.

Call:  bake(out_dir, frame_start, frame_end)   (end is EXCLUSIVE of the loop
wrap: a 360-frame loop is frames 1..360 and frame 361 must equal frame 1.)
"""
import json
import os

import bmesh
import bpy

PROPS = ("gv_r", "gv_g", "gv_b", "gv_a", "gv_hide")


def _write_obj(ob, path):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    lines = ["# %s exported by export_for_glyphviz.py" % ob.name]
    for v in bm.verts:
        lines.append("v %.6g %.6g %.6g" % tuple(v.co))
    for f in bm.faces:
        i = [v.index + 1 for v in f.verts]
        lines.append("f %d %d %d" % tuple(i))
    bm.free()
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")


def bake(out_dir, frame_start, frame_end):
    scn = bpy.context.scene
    os.makedirs(os.path.join(out_dir, "meshes"), exist_ok=True)
    parts = sorted((o for o in scn.objects if o.get("gv") and o.type == "MESH"),
                   key=lambda o: o.name)
    rec = {}
    for ob in parts:
        _write_obj(ob, os.path.join(out_dir, "meshes", ob.name + ".obj"))
        rec[ob.name] = {"label": ob.get("gv_label", ""), "m": [], "p": []}
    n = 0
    for f in range(frame_start, frame_end + 1):
        scn.frame_set(f)
        bpy.context.view_layer.update()
        for ob in parts:
            m = ob.matrix_world
            rec[ob.name]["m"].append([m[r][c] for r in range(3) for c in range(4)])
            rec[ob.name]["p"].append([float(ob.get(k, 0.0)) for k in PROPS])
        n += 1
    out = {"fps": scn.render.fps, "frame_start": frame_start, "frames": n,
           "props": list(PROPS), "objects": rec}
    with open(os.path.join(out_dir, "bake.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"))
    return {"parts": len(parts), "frames": n}
