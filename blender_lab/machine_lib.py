"""Helpers that run INSIDE Blender (bpy) to build and animate a rigid-part machine.

Conventions (shared with export_for_glyphviz.py):
  * The machine lives in the XZ plane, viewed from -Y (Blender's "front"):
    x is right, z is up, shafts run along Y.  Z-up matches GlyphViz.
  * Angles passed around are screen angles, CCW as seen from -Y.  Blender's
    rotation about +Y is clockwise on that screen, hence rotation_euler.y = -a.
  * Every exported part is a rigid mesh object with NO object scale (scale is
    baked into the vertices), because a GlyphViz node applies one uniform scale.
  * An object is exported iff it has the custom property "gv" (see mark()).
"""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

TAU = 2.0 * math.pi


# ---------------------------------------------------------------- materials

def material(name, rgb, alpha=1.0, metallic=0.0, roughness=0.45, emission=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*[c / 255.0 for c in rgb], 1.0)
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = roughness
    b.inputs["Alpha"].default_value = alpha
    if emission:
        b.inputs["Emission"].default_value = (*[c / 255.0 for c in rgb], 1.0)
        b.inputs["Emission Strength"].default_value = emission
    m.diffuse_color = (*[c / 255.0 for c in rgb], alpha)
    return m


def mark(obj, rgb, alpha=255, label=""):
    """Flag an object for export and record the flat colour GlyphViz will paint it."""
    obj["gv"] = 1
    obj["gv_r"], obj["gv_g"], obj["gv_b"] = float(rgb[0]), float(rgb[1]), float(rgb[2])
    obj["gv_a"] = float(alpha)
    obj["gv_hide"] = 0.0
    if label:
        obj["gv_label"] = label
    m = material("mat_%s" % obj.name, rgb, alpha / 255.0, metallic=0.5, roughness=0.35)
    obj.data.materials.clear()
    obj.data.materials.append(m)
    return obj


# ------------------------------------------------------------------ meshing

def _mesh_object(name, verts, faces, collection=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    me.update()
    ob = bpy.data.objects.new(name, me)
    (collection or bpy.context.scene.collection).objects.link(ob)
    return ob


def _fix_winding(ob):
    """Make every closed shell wind outward: the GlyphViz importer reads face
    normals from winding (crease pass), so an inside-out shell shades as a hole."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()


def _box(verts, faces, cx, cy, cz, hx, hy, hz, rot=0.0):
    """Axis box about (cx,cy,cz), rotated by `rot` (screen angle) in the XZ plane."""
    base = len(verts)
    c, s = math.cos(rot), math.sin(rot)
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                lx, lz = sx * hx, sz * hz
                verts.append((cx + lx * c - lz * s, cy + sy * hy, cz + lx * s + lz * c))
    # index = sx*4 + sy*2 + sz with sx,sy,sz in {0,1}
    def i(sx, sy, sz):
        return base + sx * 4 + sy * 2 + sz
    faces += [(i(0, 0, 0), i(0, 0, 1), i(0, 1, 1), i(0, 1, 0)),
              (i(1, 0, 0), i(1, 1, 0), i(1, 1, 1), i(1, 0, 1)),
              (i(0, 0, 0), i(1, 0, 0), i(1, 0, 1), i(0, 0, 1)),
              (i(0, 1, 0), i(0, 1, 1), i(1, 1, 1), i(1, 1, 0)),
              (i(0, 0, 0), i(0, 1, 0), i(1, 1, 0), i(1, 0, 0)),
              (i(0, 0, 1), i(1, 0, 1), i(1, 1, 1), i(0, 1, 1))]


def _cyl(verts, faces, r, y0, y1, n=24, cx=0.0, cz=0.0):
    base = len(verts)
    for k in range(n):
        a = TAU * k / n
        verts.append((cx + r * math.cos(a), y0, cz + r * math.sin(a)))
    for k in range(n):
        a = TAU * k / n
        verts.append((cx + r * math.cos(a), y1, cz + r * math.sin(a)))
    for k in range(n):
        j = (k + 1) % n
        faces.append((base + k, base + j, base + n + j, base + n + k))
    faces.append(tuple(base + k for k in range(n)))
    faces.append(tuple(base + n + k for k in reversed(range(n))))


def tooth_outline(teeth, module):
    """Trapezoid-tooth outline as (radius, angle) pairs, tooth 0 centred on +X.

    Tooth is 0.46 of the pitch at the pitch circle (0.54 gap = backlash), so a
    gear meshing at exact centre distance has clearance both sides."""
    r = module * teeth / 2.0
    r_root, r_tip = r - 1.25 * module, r + module
    p = TAU / teeth
    pts = []
    for k in range(teeth):
        c = k * p
        for dr, half in ((r_root, -0.30), (r, -0.23), (r_tip, -0.13),
                         (r_tip, 0.13), (r, 0.23), (r_root, 0.30)):
            pts.append((dr, c + half * p))
        pts.append((r_root, c + 0.5 * p))
    return pts, r_root


def make_gear(name, teeth, module, width, spokes=0, hub=None, y=0.0, stud=None):
    """A spur gear in the XZ plane, axis along Y, centred on the origin.

    spokes=0 -> solid disc.  spokes>0 -> toothed rim ring + hub + spokes (one
    joined mesh).  Rim/spokes are thinner than the rim in Y so nothing is
    coplanar (z-fighting in a flat-shaded GlyphViz render)."""
    pts, r_root = tooth_outline(teeth, module)
    verts, faces = [], []
    n = len(pts)
    yf, yb = y + width / 2.0, y - width / 2.0
    for (rr, a) in pts:
        verts.append((rr * math.cos(a), yf, rr * math.sin(a)))
    for (rr, a) in pts:
        verts.append((rr * math.cos(a), yb, rr * math.sin(a)))
    for k in range(n):                                     # outer wall
        j = (k + 1) % n
        faces.append((k, j, n + j, n + k))
    if spokes <= 0:
        faces.append(tuple(range(n)))
        faces.append(tuple(n + k for k in reversed(range(n))))
    else:
        r_in = r_root - max(0.9 * module * 1.0, 0.16 * module * teeth / 2.0)
        for (rr, a) in pts:
            verts.append((r_in * math.cos(a), yf, r_in * math.sin(a)))
        for (rr, a) in pts:
            verts.append((r_in * math.cos(a), yb, r_in * math.sin(a)))
        for k in range(n):
            j = (k + 1) % n
            faces.append((k, 2 * n + k, 2 * n + j, j))                 # front annulus
            faces.append((n + k, n + j, 3 * n + j, 3 * n + k))         # back annulus
            faces.append((2 * n + k, 3 * n + k, 3 * n + j, 2 * n + j)) # bore wall
        r_hub = hub if hub else max(0.22 * r_in, 1.6 * module)
        _cyl(verts, faces, r_hub, y - width * 0.75, y + width * 0.75, n=20)
        sp_t = width * 0.30
        for s in range(spokes):
            a = TAU * s / spokes + math.pi / spokes
            rm = 0.5 * (r_hub * 0.8 + r_in * 1.02)
            _box(verts, faces, rm * math.cos(a), y, rm * math.sin(a),
                 0.5 * (r_in * 1.02 - r_hub * 0.8), sp_t, 0.22 * r_hub + 0.2 * module, rot=a)
    if stud:                       # (distance from axis, stud radius, front y), at local angle 0
        d, sr, y_out = stud
        _cyl(verts, faces, sr, y_out, yb + width * 0.5, n=14, cx=d, cz=0.0)   # -Y is toward the camera
    ob = _mesh_object(name, verts, faces)
    _fix_winding(ob)
    return ob


def make_cylinder(name, r, length, n=24, along="Y"):
    verts, faces = [], []
    _cyl(verts, faces, r, -length / 2.0, length / 2.0, n=n)
    ob = _mesh_object(name, verts, faces)
    _fix_winding(ob)
    return ob


# --------------------------------------------------------------- animation

def set_pose(ob, x, y, z, screen_angle=0.0):
    ob.location = (x, y, z)
    ob.rotation_mode = "XYZ"
    ob.rotation_euler = (0.0, -screen_angle, 0.0)


def key_rot_y(ob, frame_to_angle, frames):
    """Keyframe the screen angle on every frame (linear, so sampling is exact)."""
    ob.rotation_mode = "XYZ"
    for f in frames:
        ob.rotation_euler = (0.0, -frame_to_angle(f), 0.0)
        ob.keyframe_insert("rotation_euler", frame=f, index=1)
    _linear(ob)


def key_loc(ob, frame_to_xyz, frames):
    for f in frames:
        ob.location = frame_to_xyz(f)
        ob.keyframe_insert("location", frame=f)
    _linear(ob)


def _linear(ob):
    ad = ob.animation_data
    if ad and ad.action:
        for fc in ad.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"


def interference(pairs, frames):
    """Count intersecting triangle pairs between named object pairs, per frame.

    `pairs` is [(name_a, name_b), ...]; returns {pair: worst_count_over_frames,
    ...} plus the frames it happened on.  Zero everywhere means the parts
    never touch -- the check that makes 'true tooth meshing' a measurement."""
    from mathutils.bvhtree import BVHTree
    scn = bpy.context.scene
    worst = {p: (0, None) for p in pairs}
    for f in frames:
        scn.frame_set(f)
        bpy.context.view_layer.update()
        trees = {}
        for a, b in pairs:
            for nm in (a, b):
                if nm not in trees:
                    ob = bpy.data.objects[nm]
                    me = ob.data
                    trees[nm] = BVHTree.FromPolygons(
                        [ob.matrix_world @ v.co for v in me.vertices],
                        [tuple(p.vertices) for p in me.polygons])
            n = len(trees[a].overlap(trees[b]))
            if n > worst[(a, b)][0]:
                worst[(a, b)] = (n, f)
    return worst


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.actions):
        for b in list(coll):
            coll.remove(b)


MESH_GAP = 0.015   # extra centre distance: trapezoid teeth are not conjugate, so
                   # exact pitch spacing bites at some phases (measured by interference())


def centre_distance(teeth_a, teeth_b, module, gap=MESH_GAP):
    return module * (teeth_a + teeth_b) / 2.0 + gap


def meshing_phase(teeth_a, teeth_b, phi):
    """Rest angle for gear B (screen angle) so its gap faces gear A's tooth at
    centre-line direction `phi` (A is placed with a tooth on +X: angle 0 + phi
    handled by the caller).  Returns theta_b0 for theta_a0 = phi."""
    return phi + math.pi - math.pi / teeth_b


def mesh_angle(theta_a, theta_a0, teeth_a, teeth_b, theta_b0):
    """Gear B's angle as A turns: B counter-rotates at the tooth ratio."""
    return theta_b0 - (theta_a - theta_a0) * teeth_a / teeth_b


# ------------------------------------------------------------- more shapes

def _sector(verts, faces, r_in, r_out, a0, a1, y0, y1, n=18, cx=0.0, cz=0.0):
    """Extruded annular sector, angles in radians CCW from +X in the XZ plane."""
    base = len(verts)
    ring = []
    for k in range(n + 1):
        a = a0 + (a1 - a0) * k / n
        ca, sa = math.cos(a), math.sin(a)
        ring.append((ca, sa))
    for (ca, sa) in ring:                       # 4 rings: out-front, out-back, in-front, in-back
        verts.append((cx + r_out * ca, y0, cz + r_out * sa))
        verts.append((cx + r_out * ca, y1, cz + r_out * sa))
        verts.append((cx + r_in * ca, y0, cz + r_in * sa))
        verts.append((cx + r_in * ca, y1, cz + r_in * sa))
    for k in range(n):
        o, p = base + 4 * k, base + 4 * (k + 1)
        faces += [(o + 0, p + 0, p + 1, o + 1),        # outer wall
                  (o + 2, o + 3, p + 3, p + 2),        # inner wall
                  (o + 0, o + 2, p + 2, p + 0),        # y0 face
                  (o + 1, p + 1, p + 3, o + 3)]        # y1 face
    e0, e1 = base, base + 4 * n                         # end caps
    faces += [(e0 + 0, e0 + 1, e0 + 3, e0 + 2), (e1 + 0, e1 + 2, e1 + 3, e1 + 1)]


def make_sphere(name, r, seg=16, rings=10):
    verts, faces = [], []
    for j in range(rings + 1):
        phi = math.pi * j / rings
        for i in range(seg):
            th = TAU * i / seg
            verts.append((r * math.sin(phi) * math.cos(th), r * math.cos(phi), r * math.sin(phi) * math.sin(th)))
    for j in range(rings):
        for i in range(seg):
            a, b = j * seg + i, j * seg + (i + 1) % seg
            c, d = (j + 1) * seg + (i + 1) % seg, (j + 1) * seg + i
            if j == 0:                       # pole: ring 0 is all one point
                faces.append((a, c, d))
            elif j == rings - 1:
                faces.append((a, b, d))
            else:
                faces.append((a, b, c, d))
    ob = _mesh_object(name, verts, faces)
    _fix_winding(ob)
    return ob


def make_torus_x(name, R, r, nu=40, nv=12):
    """Ring with its axis along local +X (a hoop a marble rolls through)."""
    verts, faces = [], []
    for i in range(nu):
        u = TAU * i / nu
        for j in range(nv):
            v = TAU * j / nv
            rr = R + r * math.cos(v)
            verts.append((r * math.sin(v), rr * math.cos(u), rr * math.sin(u)))
    for i in range(nu):
        for j in range(nv):
            a, b = i * nv + j, i * nv + (j + 1) % nv
            c, d = ((i + 1) % nu) * nv + (j + 1) % nv, ((i + 1) % nu) * nv + j
            faces.append((a, b, c, d))
    ob = _mesh_object(name, verts, faces)
    _fix_winding(ob)
    return ob


def make_cup(name, r_in=0.2, r_out=0.26, a0=200.0, a1=338.0, half_w=0.12):   # a0/a1: degrees CCW from +X
    """A U-shaped bucket: the lower arc of a ring plus a thin backplate, centred
    on the arc's centre so rotating the object tilts it about its own middle."""
    verts, faces = [], []
    _sector(verts, faces, r_in, r_out, math.radians(a0), math.radians(a1), -half_w, half_w)
    # a narrow brace across the chord, behind the marble: it joins the two rim ends and is
    # what the gondola's stem lands on (a full backplate hid the U when seen from the front)
    xl, zl = r_out * math.cos(math.radians(a0)), r_out * math.sin(math.radians(a0))
    xr = r_out * math.cos(math.radians(a1))
    _box(verts, faces, (xl + xr) / 2.0, half_w + 0.03, zl + 0.02, (xr - xl) / 2.0, 0.03, 0.03)
    ob = _mesh_object(name, verts, faces)
    _fix_winding(ob)
    return ob


def make_stem(name, length, pin_r=0.07, pin_len=0.14, bar_w=0.06, bar_t=0.05):
    """Pivot pin + hanger bar hanging from the origin (a gondola's stem)."""
    verts, faces = [], []
    _cyl(verts, faces, pin_r, -pin_len, pin_len * 0.2, n=12)
    _box(verts, faces, 0.0, -pin_len * 0.5, -length / 2.0, bar_w / 2.0, bar_t / 2.0, length / 2.0)
    ob = _mesh_object(name, verts, faces)
    _fix_winding(ob)
    return ob


def make_bell(name, r=0.55, h=0.7, n=24, rings=7):
    """A bell hanging with its rim at the bottom, axis along Z, origin on the rim."""
    verts, faces = [], []
    prof = []
    for k in range(rings + 1):
        t = k / rings
        prof.append((r * (1.0 - 0.18 * t * t - 0.62 * t ** 3 if t < 1 else 0.05), h * t))
    prof[-1] = (0.05, h)
    prof[0] = (r, 0.0)
    for (rr, z) in prof:
        for i in range(n):
            a = TAU * i / n
            verts.append((rr * math.cos(a), rr * math.sin(a), z))
    for k in range(rings):
        for i in range(n):
            a, b = k * n + i, k * n + (i + 1) % n
            faces.append((a, (k + 1) * n + i, (k + 1) * n + (i + 1) % n, b))
    faces.append(tuple(range(n - 1, -1, -1)))
    faces.append(tuple(rings * n + i for i in range(n)))
    ob = _mesh_object(name, verts, faces)
    _fix_winding(ob)
    return ob


class Static:
    """Collects boxes/cylinders in WORLD space into one mesh (an unmoving part)."""

    def __init__(self):
        self.v, self.f = [], []

    def box(self, cx, cy, cz, hx, hy, hz, rot=0.0):
        _box(self.v, self.f, cx, cy, cz, hx, hy, hz, rot)
        return self

    def plank(self, p0, p1, thick, width, y):
        """A bar from p0 to p1 (x,z), `thick` tall, `width` deep in Y, at depth y."""
        dx, dz = p1[0] - p0[0], p1[1] - p0[1]
        ln = math.hypot(dx, dz)
        self.box((p0[0] + p1[0]) / 2, y, (p0[1] + p1[1]) / 2, ln / 2, width / 2, thick / 2,
                 rot=math.atan2(dz, dx))
        return self

    def cyl(self, cx, cz, r, y0, y1, n=20):
        _cyl(self.v, self.f, r, y0, y1, n=n, cx=cx, cz=cz)
        return self

    def prism_x(self, x0, x1, tri_yz):
        """Triangular prism along X; tri_yz = three (y,z) points."""
        b = len(self.v)
        for x in (x0, x1):
            for (yy, zz) in tri_yz:
                self.v.append((x, yy, zz))
        self.f += [(b + 0, b + 1, b + 2), (b + 3, b + 5, b + 4),
                   (b + 0, b + 3, b + 4, b + 1), (b + 1, b + 4, b + 5, b + 2), (b + 2, b + 5, b + 3, b + 0)]
        return self

    def build(self, name):
        ob = _mesh_object(name, self.v, self.f)
        _fix_winding(ob)
        return ob


def make_bar(name, length, bar_h, bar_t, eye_r, along=+1):
    """Connecting rod: origin at one eye, bar along +X to the other eye."""
    verts, faces = [], []
    _box(verts, faces, length / 2.0, 0.0, 0.0, length / 2.0, bar_t / 2.0, bar_h / 2.0)
    for ex in (0.0, length):
        _cyl(verts, faces, eye_r, -bar_t * 0.9, bar_t * 0.9, n=16, cx=ex, cz=0.0)
    ob = _mesh_object(name, verts, faces)
    _fix_winding(ob)
    return ob


def make_block(name, sx, sy, sz):
    verts, faces = [], []
    _box(verts, faces, 0.0, 0.0, 0.0, sx / 2.0, sy / 2.0, sz / 2.0)
    ob = _mesh_object(name, verts, faces)
    _fix_winding(ob)
    return ob


def follow(theta_a, ta, tb, phi):
    """Absolute meshing law: gear B's angle given gear A's, B sitting at screen
    direction `phi` from A (see meshing_phase).  Needs no initial-state bookkeeping."""
    return phi + math.pi - math.pi / tb - (theta_a - phi) * ta / tb


def make_anchor(name, ax=0.6, az=0.5, arm_t=0.07, pallet=(0.14, 0.17), axle_y=(-0.3, 0.06)):
    """A clock's escapement anchor: origin on its pivot, two arms reaching down and out to
    pallets that straddle the top of the escape wheel; a short axle (along Y) ties it to the
    pendulum's plane.  `ax`/`az` = pallet offset from the pivot."""
    verts, faces = [], []
    for sgn in (-1, 1):
        dx, dz = sgn * ax, -az
        ln = math.hypot(dx, dz)
        _box(verts, faces, dx / 2.0, 0.0, dz / 2.0, ln / 2.0, 0.05, arm_t / 2.0, rot=math.atan2(dz, dx))
        _box(verts, faces, dx, 0.0, dz - pallet[1] * 0.35, pallet[0] / 2.0, 0.05, pallet[1] / 2.0)
    _cyl(verts, faces, 0.09, axle_y[0], axle_y[1], n=14)
    ob = _mesh_object(name, verts, faces)
    _fix_winding(ob)
    return ob
