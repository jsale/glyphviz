"""
Shared scene plumbing for the tensor lab: the node/channel writer (adapted
from lorenz5d_feedback_lab/scene_kit.py), arrows built from two Link glyphs,
signed bars, act captions, and the rotation helpers every scene shares.

Frames of reference (every scene):

    turn    world, rotated to the default camera's azimuth (45 deg):
            +X toward the viewer, +Y screen right, +Z up
    stage   the 3-D stage, turned a further -20 deg so its x axis comes
            toward the viewer and a little LEFT -- the textbook view of
            x, y, z axes (y right, z up)
    wall    the turn frame leaned back to the camera's elevation (25 deg)
    board   flat panels on the wall: x = screen right, y = up, z = toward
            the viewer

Rotations are written in GlyphViz's Euler XYZ mode (rotation_mode 0), where a
node's world basis is Rx(rx) Ry(ry) Rz(rz) diag(scale) -- measured through
compute_world_transforms, see verify_tensor_lab.py.
"""
import csv
import math
import os

import numpy as np

GEO_CUBE, GEO_SPHERE_WIRE, GEO_SPHERE, GEO_CONE = 1, 2, 3, 5
GEO_CYLINDER, GEO_POINT, GEO_CIRCLE = 19, 22, 24
TYPE_GLYPH, TYPE_LINK = 5, 7
TOPO_NONE, TOPO_PLOT = 0, 16
CUBE_FACE = 0.57735                   # a unit-scale cube's faces sit this far out

NODE_COLS = ["id", "type", "parent_id", "branch_level",
             "translate_x", "translate_y", "translate_z",
             "rotate_x", "rotate_y", "rotate_z",
             "scale_x", "scale_y", "scale_z",
             "color_r", "color_g", "color_b", "color_a",
             "geometry", "hide", "topo", "ratio",
             "child_id", "ch_input_id", "show_text", "rotation_mode", "text"]

# The basis colours: e1, e2, e3 = red, green, blue (the ANTz x/y/z convention).
E_RGB = ((235, 60, 60), (60, 200, 80), (70, 120, 255))
E_LIGHT = ((255, 150, 140), (150, 240, 160), (150, 185, 255))
GOLD = (255, 200, 60)
WHITE = (235, 235, 245)
GREY = (120, 125, 145)
CAPTION = (215, 215, 230)
WARM, COOL = (255, 150, 60), (90, 160, 255)


def num(v, dp=4):
    """Compact float: dp decimals, trailing zeros trimmed, never '-0'."""
    s = f"{float(v):.{dp}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


# --------------------------------------------------------------------------
# Rotations
# --------------------------------------------------------------------------

def rot_x(a):
    a = math.radians(a)
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_y(a):
    a = math.radians(a)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_z(a):
    a = math.radians(a)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def euler_xyz(R):
    """Degrees (rx, ry, rz) with R = Rx(rx) Ry(ry) Rz(rz). R may be (3, 3) or
    (n, 3, 3). Near ry = +/-90 the split between rx and rz is arbitrary, but
    the composed matrix is still exact, and Channels never interpolate."""
    R = np.asarray(R, dtype=float)
    ry = np.degrees(np.arcsin(np.clip(R[..., 0, 2], -1.0, 1.0)))
    rx = np.degrees(np.arctan2(-R[..., 1, 2], R[..., 2, 2]))
    rz = np.degrees(np.arctan2(-R[..., 0, 1], R[..., 0, 0]))
    gimbal = np.abs(R[..., 0, 2]) > 1 - 1e-9
    if np.any(gimbal):
        # cos(ry) ~ 0: put the whole remaining turn into rx.
        rx = np.where(gimbal, np.degrees(np.arctan2(R[..., 2, 1], R[..., 1, 1])), rx)
        rz = np.where(gimbal, 0.0, rz)
    return np.stack([rx, ry, rz], axis=-1)


def from_euler_xyz(e):
    return rot_x(e[0]) @ rot_y(e[1]) @ rot_z(e[2])


def axis_angle(axis, deg):
    """Rodrigues: rotation by deg about the unit axis."""
    k = np.asarray(axis, float)
    k = k / np.linalg.norm(k)
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    a = math.radians(deg)
    return np.eye(3) + math.sin(a) * K + (1 - math.cos(a)) * K @ K


def quat_from_matrix(R):
    w = math.sqrt(max(0.0, 1 + R[0, 0] + R[1, 1] + R[2, 2])) / 2
    x = math.copysign(math.sqrt(max(0.0, 1 + R[0, 0] - R[1, 1] - R[2, 2])) / 2, R[2, 1] - R[1, 2])
    y = math.copysign(math.sqrt(max(0.0, 1 - R[0, 0] + R[1, 1] - R[2, 2])) / 2, R[0, 2] - R[2, 0])
    z = math.copysign(math.sqrt(max(0.0, 1 - R[0, 0] - R[1, 1] + R[2, 2])) / 2, R[1, 0] - R[0, 1])
    q = np.array([w, x, y, z])
    return q / np.linalg.norm(q)


def matrix_from_quat(q):
    w, x, y, z = q / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def slerp(R0, R1, u):
    """Shortest-path rotation from R0 (u = 0) to R1 (u = 1)."""
    q0, q1 = quat_from_matrix(R0), quat_from_matrix(R1)
    if np.dot(q0, q1) < 0:
        q1 = -q1
    d = min(1.0, float(np.dot(q0, q1)))
    th = math.acos(d)
    if th < 1e-9:
        return R0.copy()
    q = (math.sin((1 - u) * th) * q0 + math.sin(u * th) * q1) / math.sin(th)
    return matrix_from_quat(q)


def ease(u):
    """Smoothstep 0..1 with zero slope at both ends."""
    u = np.clip(u, 0.0, 1.0)
    return u * u * (3 - 2 * u)


def tour(s):
    """The basis tour both of the first two scenes use: a closed loop in
    rotation space, identity at s = 0 and s = 1. A full twist about z,
    while the twist axis itself tips up to 70 deg and swings around twice.
    Every component of a generic vector or tensor moves."""
    s = float(s)
    beta = 70.0 * math.sin(math.pi * s) ** 2
    alpha = 720.0 * s
    gamma = 360.0 * s
    return rot_z(gamma) @ rot_z(alpha) @ rot_y(beta) @ rot_z(-alpha)


# --------------------------------------------------------------------------
# The writer
# --------------------------------------------------------------------------

class Scene:
    def __init__(self, frames):
        self.frames = frames
        self.rows = []
        self.level = {0: -1}
        self.tracks = []          # (values, decimals); track id = index + 1
        self.chmap = []           # (channel_id, track_id, attribute)
        self.next_ch = 1

    def node(self, parent=0, *, type=TYPE_GLYPH, pos=(0, 0, 0), rot=(0, 0, 0), scale=1.0,
             color=(255, 255, 255, 255), geometry=GEO_SPHERE, hide=0, topo=TOPO_NONE,
             ratio=0.1, child_id=0, ch=0, show_text=0, text=""):
        assert text, "every node gets a label"
        nid = len(self.rows) + 1
        lvl = self.level[parent] + 1
        self.level[nid] = lvl
        sc = scale if isinstance(scale, (tuple, list, np.ndarray)) else (scale,) * 3
        c = tuple(int(round(v)) for v in color) + (255,) * (4 - len(color))
        self.rows.append([nid, type, parent, lvl, *(float(v) for v in pos),
                          *(float(v) for v in rot), *(float(v) for v in sc), *c,
                          geometry, int(hide), topo, float(ratio), child_id, ch,
                          int(show_text), 0, text])
        return nid

    def track(self, values, dp=4):
        values = np.asarray(values, dtype=float)
        assert values.shape == (self.frames,), (values.shape, self.frames)
        self.tracks.append((values, dp))
        return len(self.tracks)

    def channel(self, bindings):
        """bindings: [(track_id, attribute), ...] -> new channel id."""
        ch = self.next_ch
        self.next_ch += 1
        for tid, attr in bindings:
            self.chmap.append((ch, tid, attr))
        return ch

    def write(self, out_dir, stem):
        os.makedirs(out_dir, exist_ok=True)
        # Companions first, node CSV last (Watch-and-Reload safe).
        with open(os.path.join(out_dir, f"{stem}_gv_ch-map.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\r\n")
            w.writerow(["channel_id", "track_id", "attribute"])
            w.writerows(self.chmap)
        cols = []
        for values, dp in self.tracks:
            if np.all(values == np.round(values)):
                cols.append([str(int(v)) for v in values])
            else:
                cols.append([num(v, dp) for v in values])
        with open(os.path.join(out_dir, f"{stem}_gv_ch-tracks.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            fh.write(",".join(["cyclecount"] + [f"ch{i + 1}" for i in range(len(cols))]) + "\r\n")
            for f in range(self.frames):
                fh.write(str(f) + "," + ",".join(c[f] for c in cols) + "\r\n")
        with open(os.path.join(out_dir, f"{stem}_gv_node.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\r\n")
            w.writerow(NODE_COLS)
            for row in self.rows:
                w.writerow([num(v) if isinstance(v, float) else v for v in row])


# --------------------------------------------------------------------------
# Frames
# --------------------------------------------------------------------------

STAGE_TURN = -20.0


def frames_of_reference(sc, background, lift):
    """World background + turn + wall. -> (turn id, wall id)."""
    sc.node(0, type=0, color=(*background, 255), geometry=GEO_POINT, hide=1,
            text="World - background")
    turn = sc.node(0, pos=(0, 0, lift), rot=(0, 0, 45), hide=1, geometry=GEO_POINT,
                   text="turn frame - the default camera's azimuth (45): x toward you, y right")
    wall = sc.node(turn, rot=(0, -25, 0), hide=1, geometry=GEO_POINT,
                   text="wall - leaned back to the default camera's elevation (25)")
    return turn, wall


def stage(sc, turn, origin, label="stage"):
    """The 3-D stage at turn-frame `origin` (toward viewer, right, up)."""
    return sc.node(turn, pos=origin, rot=(0, 0, STAGE_TURN), hide=1, geometry=GEO_POINT,
                   text=f"{label}: x toward you and a little left, y right, z up")


def stage_world_rotation():
    """The stage frame's world rotation (both frames above it)."""
    return rot_z(45.0) @ rot_z(STAGE_TURN)


def board(sc, wall, origin, scale=1.0, label="board"):
    """A frame on the wall with x = screen right, y = up, z = toward the viewer.
    Rz(90) then Rx(90) maps board x -> wall +Y, y -> wall +Z, z -> wall +X.
    `origin` is in wall coords (toward viewer, right, up)."""
    outer = sc.node(wall, pos=origin, rot=(0, 0, 90), scale=scale, hide=1, geometry=GEO_POINT,
                    text=f"{label} frame, step 1 of 2 (Rz 90)")
    return sc.node(outer, rot=(90, 0, 0), hide=1, geometry=GEO_POINT,
                   text=f"{label}: x = right, y = up, z = toward the viewer")


# --------------------------------------------------------------------------
# Channels helpers
# --------------------------------------------------------------------------

def pos_channel(sc, xyz, dp=4, extra=()):
    """A channel driving translate_x/y/z from an (frames, 3) array."""
    xyz = np.asarray(xyz, float)
    return sc.channel([(sc.track(xyz[:, i], dp), a)
                       for i, a in enumerate(("translate_x", "translate_y", "translate_z"))]
                      + list(extra))


def rot_channel(sc, Rs, dp=3):
    """A channel driving rotate_x/y/z (Euler XYZ) from (frames, 3, 3)."""
    e = euler_xyz(Rs)
    return sc.channel([(sc.track(e[:, i], dp), a)
                       for i, a in enumerate(("rotate_x", "rotate_y", "rotate_z"))])


def window(frames, f0, f1):
    """1 on [f0, f1), else 0."""
    f = np.arange(frames)
    return ((f >= f0) & (f < f1)).astype(float)


def hide_channel(sc, visible):
    """A channel hiding a node whenever `visible` is 0."""
    return sc.channel([(sc.track(np.where(np.asarray(visible) > 0, 0, 1)), "hide")])


# --------------------------------------------------------------------------
# Arrows: a Cylinder link for the shaft and a Cone link for the head. Links
# read their ends' world positions every frame, so a channel-driven tip drags
# the arrow along. The head shrinks with a short arrow so it never pokes out
# behind the tail.
# --------------------------------------------------------------------------

def head_length(length, head):
    return np.minimum(head, 0.45 * np.asarray(length))


def arrow(sc, parent, tail, tip, color, label, *, radius=0.06, head=0.45, head_radius=None,
          tail_node=None, ch_visible=None, show_text=0, tail_label=None):
    """A static or animated arrow under `parent`, in that frame's coords.

    tail, tip: (3,) or (frames, 3). Returns (tail id, tip id, shaft link id).
    ch_visible: optional (frames,) 0/1 array -- hides the whole arrow.
    show_text pins the label at the TIP (a small visible bead there): a link
    labels at its midpoint, and arrows sharing a tail crowd their midpoints."""
    tail = np.asarray(tail, float)
    tip = np.asarray(tip, float)
    animated = tail.ndim == 2 or tip.ndim == 2
    hr = 2.4 * radius if head_radius is None else head_radius
    vis_ch = hide_channel(sc, ch_visible) if ch_visible is not None else 0
    hidden0 = int(ch_visible is not None and not ch_visible[0])
    if animated:
        F = sc.frames
        tl = np.broadcast_to(tail, (F, 3)) if tail.ndim == 1 else tail
        tp = np.broadcast_to(tip, (F, 3)) if tip.ndim == 1 else tip
        d = tp - tl
        L = np.linalg.norm(d, axis=1)
        u = np.where(L[:, None] > 1e-12, d / np.maximum(L, 1e-12)[:, None], 0.0)
        neck = tp - u * head_length(L, head)[:, None]
        if tail_node is None:
            if tail.ndim == 1:
                t_id = sc.node(parent, pos=tail, hide=1, geometry=GEO_POINT,
                               text=tail_label or f"{label}: tail")
            else:
                t_id = sc.node(parent, pos=tl[0], hide=1, geometry=GEO_POINT,
                               ch=pos_channel(sc, tl), text=tail_label or f"{label}: tail")
        else:
            t_id = tail_node
        n_id = sc.node(parent, pos=neck[0], hide=1, geometry=GEO_POINT,
                       ch=pos_channel(sc, neck), text=f"{label}: base of the head")
        if show_text:
            extra = [(sc.track(np.where(ch_visible > 0, 0, 1)), "hide")]                 if ch_visible is not None else []
            tip_ch = pos_channel(sc, tp, extra=extra) if tip.ndim == 2 else vis_ch
            p_id = sc.node(parent, pos=tp[0], scale=radius, color=color, hide=hidden0,
                           ch=tip_ch, show_text=1, text=label)
        else:
            p_id = sc.node(parent, pos=tp[0], hide=1, geometry=GEO_POINT,
                           ch=pos_channel(sc, tp) if tip.ndim == 2 else 0,
                           text=f"{label}: tip")
    else:
        d = tip - tail
        L = float(np.linalg.norm(d))
        neck = tip - d / L * float(head_length(L, head))
        t_id = tail_node or sc.node(parent, pos=tail, hide=1, geometry=GEO_POINT,
                                    text=tail_label or f"{label}: tail")
        n_id = sc.node(parent, pos=neck, hide=1, geometry=GEO_POINT,
                       text=f"{label}: base of the head")
        if show_text:
            p_id = sc.node(parent, pos=tip, scale=radius, color=color, hide=hidden0,
                           ch=vis_ch, show_text=1, text=label)
        else:
            p_id = sc.node(parent, pos=tip, hide=1, geometry=GEO_POINT, text=f"{label}: tip")
    shaft = sc.node(t_id, type=TYPE_LINK, child_id=n_id, ratio=radius, color=color,
                    geometry=GEO_CYLINDER, hide=hidden0, ch=vis_ch, text=label)
    sc.node(n_id, type=TYPE_LINK, child_id=p_id, ratio=hr, color=color, geometry=GEO_CONE,
            hide=hidden0, ch=vis_ch, text=f"{label} (head)")
    return t_id, p_id, shaft


def rod(sc, a_id, b_id, color, label, radius=0.03, ch=0, hide=0, geometry=GEO_CYLINDER,
        show_text=0):
    """A plain link between two existing nodes."""
    return sc.node(a_id, type=TYPE_LINK, child_id=b_id, ratio=radius, color=color,
                   geometry=geometry, ch=ch, hide=hide, show_text=show_text, text=label)


def polyline(sc, parent, pts, color, label, ratio=0.04, colors=None, ch=0, hide=0):
    """A fixed TOPO_PLOT polyline; the label lives on the parent."""
    plot = sc.node(parent, geometry=GEO_POINT, topo=TOPO_PLOT, ratio=ratio,
                   color=(255, 255, 255, 0), ch=ch, hide=hide, text=label)
    for i, p in enumerate(pts):
        c = colors[i] if colors is not None else color
        sc.node(plot, pos=tuple(float(v) for v in p), scale=0.0, color=c, geometry=GEO_CUBE,
                text=f"{label}: vertex {i}")
    return plot


def reveal(sc, parent, pts, color, label, f_on, f_off, ratio=0.05, seg=8):
    """A path painted progressively: point k of `pts` belongs to frame
    f_on[k]; each segment of `seg` points switches on when its last point is
    reached and off at f_off. pts: (n, 3); f_on: (n,) frame numbers."""
    holder = sc.node(parent, hide=1, geometry=GEO_POINT, text=label)
    n = len(pts)
    for k0 in range(0, n - 1, seg):
        k1 = min(k0 + seg, n - 1)
        vis = window(sc.frames, int(f_on[k1]), f_off)
        ch = hide_channel(sc, vis)
        polyline(sc, holder, pts[k0:k1 + 1], color, f"{label} (points {k0}-{k1})",
                 ratio=ratio, ch=ch, hide=int(not vis[0]))
    return holder


# --------------------------------------------------------------------------
# Board pieces
# --------------------------------------------------------------------------

def caption(sc, bd, pos, text, color=CAPTION, visible=None, size=0.05):
    """A pinned label with a small dot. `visible` (frames,) switches it."""
    ch = 0
    hide = 0
    if visible is not None:
        ch = hide_channel(sc, visible)
        hide = int(not visible[0])
    return sc.node(bd, pos=(pos[0], pos[1], 0.05), scale=size, geometry=GEO_CIRCLE,
                   color=(*color, 255), show_text=1, ch=ch, hide=hide, text=text)


def signed_bar(sc, bd, x, y, values, color, label, *, unit=1.0, width=0.35, depth=0.12,
               colors=None, visible=None):
    """A vertical bar standing on (x, y), height = unit * value (down when
    negative). values: float or (frames,). colors: optional (frames, 3).
    visible: optional (frames,) 0/1 -- the bar is hidden where it is 0."""
    v = np.asarray(values, float)
    h = unit * v
    s = width / (2 * CUBE_FACE)
    sd = depth / (2 * CUBE_FACE)
    if v.ndim == 0:
        on = abs(float(h)) > 1e-9
        return sc.node(bd, pos=(x, y + float(h) / 2, 0.0),
                       scale=(s, abs(float(h)) / (2 * CUBE_FACE), sd) if on else 0.0,
                       color=(*color, 255), geometry=GEO_CUBE, text=label)
    on = np.abs(h) > 1e-9
    binds = [(sc.track(y + h / 2), "translate_y"),
             (sc.track(np.abs(h) / (2 * CUBE_FACE)), "scale_y"),
             (sc.track(np.where(on, s, 0.0)), "scale_x"),
             (sc.track(np.where(on, sd, 0.0)), "scale_z")]
    if colors is not None:
        colors = np.asarray(colors)
        binds += [(sc.track(colors[:, c]), a) for c, a in
                  enumerate(("color_r", "color_g", "color_b"))]
    hide = 0
    if visible is not None:
        binds.append((sc.track(np.where(np.asarray(visible) > 0, 0, 1)), "hide"))
        hide = int(not visible[0])
    c0 = colors[0] if colors is not None else color
    return sc.node(bd, pos=(x, y + h[0] / 2, 0.0),
                   scale=(s, abs(h[0]) / (2 * CUBE_FACE), sd) if on[0] else 0.0,
                   color=(*c0, 255), geometry=GEO_CUBE, ch=sc.channel(binds), hide=hide,
                   text=label)


def sign_colors(values, pos=WARM, neg=COOL):
    v = np.asarray(values)
    return np.where(v[:, None] >= 0, np.array(pos), np.array(neg))


def hline(sc, bd, x0, x1, y, color, label, ratio=0.02, z=0.0):
    return polyline(sc, bd, [(x0, y, z), (x1, y, z)], (*color, 200), label, ratio=ratio)


def marker(sc, parent, pos, color, label, scale=0.08, ch=0, hide=0, show_text=0,
           geometry=GEO_SPHERE):
    return sc.node(parent, pos=pos, scale=scale, color=color, geometry=geometry, ch=ch,
                   hide=hide, show_text=show_text, text=label)
