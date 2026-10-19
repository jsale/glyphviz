import math, sys
HERE = r"C:\Users\jsale\source\repos\glyphviz\blender_lab"
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import importlib, machine_lib as L
importlib.reload(L)
import bpy
from mathutils.bvhtree import BVHTree

A, B = bpy.data.objects["gearA"], bpy.data.objects["gearB"]
for ob in (A, B):
    ob.animation_data_clear()
Ta, Tb, m = 24, 12, 0.1
ra, rb = m * Ta / 2, m * Tb / 2


def count(dist, tb):
    L.set_pose(A, 0, 0, 0, 0.0)
    L.set_pose(B, dist, 0, 0, tb)
    bpy.context.view_layer.update()
    t = []
    for ob in (A, B):
        me = ob.data
        t.append(BVHTree.FromPolygons([ob.matrix_world @ v.co for v in me.vertices],
                                      [tuple(p.vertices) for p in me.polygons]))
    return len(t[0].overlap(t[1]))

pitch_b = math.tau / Tb
out = []
for k in range(0, 24):
    off = k / 24.0 * pitch_b
    out.append((round(off / pitch_b, 3), count(ra + rb, off)))
print("phase sweep (fraction of B pitch -> overlaps):", out)
print("analytic phase", (math.pi - math.pi / Tb) % pitch_b / pitch_b)
for d in (ra + rb, ra + rb + 0.01, ra + rb + 0.02, ra + rb + 0.03):
    best = min((count(d, k / 48 * pitch_b), k / 48) for k in range(48))
    print("centre distance +%.2f: best overlaps %d at phase %.3f" % (d - ra - rb, best[0], best[1]))
