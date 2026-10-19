"""Run INSIDE Blender: search for an escapement timing that never collides.

The pendulum swings p(u) = A sin(2*pi*K*u); the anchor rides it.  The escape wheel is
driven by a scripted stepper: half a tooth-pitch at each zero crossing of the pendulum
(when both pallets are momentarily lifted clear), smoothed over `width` of a half-swing.

Analytic design (so the search is narrow, not blind): a real anchor straddles a half-integer
number of pitches (2.5 -> +-37.5 deg at the dip) so that one pallet rests in a gap while the
other is lifted.  The free parameters that matter are the wheel's rest angle `theta0`, the
step direction, and the pallet geometry; this prints every zero-collision combination.
"""
import importlib
import itertools
import math
import sys

HERE = r"C:\Users\jsale\source\repos\glyphviz\blender_lab"
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import machine_lib as L
importlib.reload(L)
import bpy
from mathutils import Matrix
from mathutils.bvhtree import BVHTree

TAU = math.tau
K, A = 6, math.radians(15.0)
PIV = (-5.5, 2.45)
TEETH, M_ESC = 12, 0.14
PITCH = TAU / TEETH


def smooth(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def steps_done(u, phase, width):
    """Half-swings completed (continuous): a step centred `phase` after each zero crossing."""
    t = u * 2.0 * K - phase                         # in half-swings
    n = math.floor(t)
    f = t - n
    # step n completes around f = 0.5: smooth ramp over [0.5-w/2, 0.5+w/2]
    return n + smooth((f - (0.5 - width / 2.0)) / width)


def tree(ob):
    me = ob.data
    return BVHTree.FromPolygons([ob.matrix_world @ v.co for v in me.vertices],
                                [tuple(p.vertices) for p in me.polygons])


good = []
tested = 0
AZ = 0.5
PAL_H = 0.17
LOW_Z = -AZ - 0.85 * PAL_H                      # pallet's lowest edge, relative to the pivot
for ez, ax in itertools.product((0.94, 0.96, 0.98, 1.0), (0.70, 0.72, 0.74, 0.76)):
    wheel = L.make_gear("scan_wheel", TEETH, M_ESC, 0.12)
    anchor = L.make_anchor("scan_anchor", ax=ax, az=AZ)
    for amp, direction, theta0, phase, width in itertools.product(
            (6.0, 8.0, 9.0, 10.0), (-1,), [math.radians(d * 1.5) for d in range(20)],
            (-0.05, 0.0, 0.05), (0.3, 0.45)):
        tested += 1
        worst, r_min = 0, 9.0
        for f in range(0, 720):                 # twice per frame: nothing slips between samples
            u = f / 720.0
            p = math.radians(amp) * math.sin(TAU * K * u)
            anchor.matrix_world = Matrix.Translation((PIV[0], 0.0, PIV[1])) @ Matrix.Rotation(-p, 4, "Y")
            ang = theta0 + direction * 0.5 * PITCH * steps_done(u, phase, width)
            wheel.matrix_world = Matrix.Translation((PIV[0], 0.0, ez)) @ Matrix.Rotation(-ang, 4, "Y")
            bpy.context.view_layer.update()
            n = len(tree(anchor).overlap(tree(wheel)))
            if n:
                worst = n
                break
            for sx in (-1, 1):                  # how deep do the pallets reach into the teeth?
                for ox in (-0.07, 0.07):
                    q = anchor.matrix_world @ Matrix.Translation((0, 0, 0)).to_translation().__class__(
                        (sx * ax + ox, 0.0, LOW_Z))
                    r_min = min(r_min, math.hypot(q.x - PIV[0], q.z - ez))
        if worst == 0 and r_min < 0.96:         # tip radius is 0.98: must really enter the teeth
            good.append((round(r_min, 3), ez, ax, amp, direction, round(math.degrees(theta0), 1), phase, width))
    for ob in (wheel, anchor):
        bpy.data.objects.remove(ob, do_unlink=True)

print("tested %d combinations; collision-free AND engaged: %d" % (tested, len(good)))
good.sort(key=lambda g: (-g[3], g[0]))
for g in good[:30]:
    print("  r_min=%.3f wheel_z=%.2f pallet_ax=%.2f amp=%.0f dir=%+d theta0=%.1f phase=%+.2f width=%.2f" % g)
