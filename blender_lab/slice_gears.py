"""Vertical slice: two meshing gears -> bake.  Run inside Blender via bl.py."""
import importlib
import math
import sys

HERE = r"C:\Users\jsale\source\repos\glyphviz\blender_lab"
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import machine_lib as L
import export_for_glyphviz as X
importlib.reload(L)
importlib.reload(X)
import bpy

L.clear_scene()
N = 90                                   # frames in the loop
F = range(1, N + 1)
bpy.context.scene.frame_start, bpy.context.scene.frame_end = 1, N
bpy.context.scene.render.fps = 30

m = 0.1
Ta, Tb = 24, 12
ra, rb = m * Ta / 2, m * Tb / 2
phi = 0.0                                # B sits to the right of A
A = L.make_gear("gearA", Ta, m, 0.25, spokes=5)
B = L.make_gear("gearB", Tb, m, 0.25)
L.mark(A, (214, 168, 64), label="Gear A (24T)")
L.mark(B, (96, 170, 220), label="Gear B (12T)")

ta0 = phi
tb0 = L.meshing_phase(Ta, Tb, phi)
ang_a = lambda f: ta0 + math.tau * (f - 1) / N                      # 1 rev per loop
ang_b = lambda f: L.mesh_angle(ang_a(f), ta0, Ta, Tb, tb0)           # -2 revs
L.set_pose(A, 0, 0, 0)
L.set_pose(B, L.centre_distance(Ta, Tb, m), 0, 0)
L.key_rot_y(A, ang_a, F)
L.key_rot_y(B, ang_b, F)

print("interference:", L.interference([("gearA", "gearB")], F))
print(X.bake(r"C:\Users\jsale\source\repos\glyphviz\blender_lab\out\slice", 1, N))
