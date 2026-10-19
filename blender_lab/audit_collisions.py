"""Run INSIDE Blender after the machine is built: does anything pass through anything?

Every animated part is tested against every other part (moving or static) with a
BVH triangle-overlap query, every STEP-th frame of the loop.  Pairs that are SUPPOSED
to touch are listed in EXPECTED and reported separately so a genuine hit stands out.
"""
import bpy
from mathutils.bvhtree import BVHTree

STEP = 1       # every frame; use 3 for a quick pass
# touching on purpose: pins seated in the wheel, the crank stud inside the rod's eye, etc.
EXPECTED = {
    frozenset(p) for p in [
        ("G2_gear15", "P1_conrod"),          # crank stud passes through the rod's eye
        ("C1_cam", "C2_follower"),           # the follower plate rides on the cam
        ("P1_conrod", "P2_piston"),          # the rod's eye is pinned into the piston
        ("W3_brackets", "W1_wall"),          # brackets are bolted to the wall
        ("W2_rails", "W1_wall"),
        ("K1_pendulum", "K3_anchor"),        # the anchor's axle is pinned through the pendulum hub
    ] + [("M%d_marble" % k, "R3_prism") for k in range(6)]     # marbles pass through the prism on purpose
      + [("B%d_stem" % k, "G3_wheel60") for k in range(6)]     # stem pin seated in the wheel
      + [("B%d_stem" % k, "B%d_cup" % k) for k in range(6)]    # stem lands on the cup's brace
}

scn = bpy.context.scene
parts = sorted((o for o in scn.objects if o.get("gv") and o.type == "MESH"), key=lambda o: o.name)
animated = {o.name for o in parts if o.animation_data and o.animation_data.action}


def tree(ob):
    me = ob.data
    return BVHTree.FromPolygons([ob.matrix_world @ v.co for v in me.vertices],
                                [tuple(p.vertices) for p in me.polygons])


static_trees = {}
scn.frame_set(1)
for ob in parts:
    if ob.name not in animated:
        static_trees[ob.name] = tree(ob)

hits = {}
for f in range(1, scn.frame_end + 1, STEP):
    scn.frame_set(f)
    bpy.context.view_layer.update()
    moving = {ob.name: tree(ob) for ob in parts if ob.name in animated}
    names = sorted(moving)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            n = len(moving[a].overlap(moving[b]))
            if n:
                hits.setdefault(frozenset((a, b)), []).append((f, n))
        for b, tb in static_trees.items():
            n = len(moving[a].overlap(tb))
            if n:
                hits.setdefault(frozenset((a, b)), []).append((f, n))

unexpected = {k: v for k, v in hits.items() if k not in EXPECTED}
expected = {k: v for k, v in hits.items() if k in EXPECTED}
print("frames tested: %d  (every %d)" % (len(range(1, scn.frame_end + 1, STEP)), STEP))
print("EXPECTED contacts seen:", sorted("/".join(sorted(k)) for k in expected))
print("UNEXPECTED overlaps: %d pairs" % len(unexpected))
for k, v in sorted(unexpected.items(), key=lambda kv: -len(kv[1])):
    frames = [f for f, _ in v]
    print("  %-34s in %3d frames, worst %3d tris, frames %s%s" % (
        " x ".join(sorted(k)), len(v), max(n for _, n in v), frames[:6], "..." if len(frames) > 6 else ""))
