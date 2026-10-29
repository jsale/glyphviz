"""
Shared scene plumbing for the string labs (bosonic_string_lab/ and
10d_superstring_lab/): the node/channel writer, frames of reference, board
captions and polylines (adapted from tensor_lab/tensor_kit.py), plus the
Hyperdimensional Coordinate System (HCS) itself.

Frames of reference:

    turn    world, rotated to the default camera's azimuth (45 deg):
            +X toward the viewer, +Y screen right, +Z up
    wall    the turn frame leaned back to the camera's elevation (25 deg)
    board   flat panels on the wall: x = screen right, y = up, z = toward
            the viewer

The HCS (Jeff Sale, on Dr. Art Springer's subsegment-ratio construction):
every dimension is the real line folded onto a circle,
theta = 180 u / (1 + |u|) with u = value / scale, so the scale lands at 90
deg and +/- infinity meet at 180 deg; dimension k+1 is a smaller circle
centred on the point chosen on circle k, in the plane of circle k's outward
radial and its normal (hyperdims' childFrame). Ported from
lorenz5d_feedback_lab/hcs.py.
"""
import csv
import math
import os

import numpy as np

GEO_CUBE, GEO_SPHERE_WIRE, GEO_SPHERE, GEO_CONE = 1, 2, 3, 5
GEO_TORUS_WIRE, GEO_TORUS = 6, 7
GEO_CYLINDER, GEO_POINT, GEO_CIRCLE = 19, 22, 24
TYPE_GLYPH, TYPE_LINK = 5, 7
TOPO_NONE, TOPO_TORUS, TOPO_PLOT = 0, 3, 16
CUBE_FACE = 0.57735                   # a unit-scale cube's faces sit this far out

NODE_COLS = ["id", "type", "parent_id", "branch_level",
             "translate_x", "translate_y", "translate_z",
             "rotate_x", "rotate_y", "rotate_z",
             "scale_x", "scale_y", "scale_z",
             "color_r", "color_g", "color_b", "color_a",
             "geometry", "hide", "topo", "ratio",
             "child_id", "ch_input_id", "show_text", "rotation_mode", "text"]

CAPTION = (215, 215, 230)
TITLE = (255, 220, 120)


def num(v, dp=4):
    """Compact float: dp decimals, trailing zeros trimmed, never '-0'."""
    s = f"{float(v):.{dp}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def ease(u):
    """Smoothstep 0..1 with zero slope at both ends."""
    u = np.clip(u, 0.0, 1.0)
    return u * u * (3 - 2 * u)


# --------------------------------------------------------------------------
# The HCS
# --------------------------------------------------------------------------

def hcs_angle(v, s):
    """HCS angle in degrees of value v at scale s (hyperdims' valueToAngle)."""
    u = np.asarray(v, dtype=float) / s
    return 180.0 * u / (1.0 + np.abs(u))


def hcs_chain(angles, r1, ratio):
    """Leaf of the nested-circle HCS for rows of angles (deg), shape (N, D) ->
    (N, 3). Circle 1 lies in the frame's XY plane with radius r1; circle k+1
    is centred on circle k's chosen point, in the plane of circle k's
    outward radial and its normal, radius scaled by ratio."""
    angles = np.atleast_2d(angles)
    n = len(angles)
    c = np.zeros((n, 3))
    u = np.tile([1.0, 0.0, 0.0], (n, 1))
    v = np.tile([0.0, 1.0, 0.0], (n, 1))
    w = np.tile([0.0, 0.0, 1.0], (n, 1))
    radius = r1
    for d in range(angles.shape[1]):
        t = np.radians(angles[:, d])[:, None]
        radial = np.cos(t) * u + np.sin(t) * v
        point = c + radius * radial
        if d == angles.shape[1] - 1:
            return point
        c, u, v, w = point, radial, w, np.cross(radial, w)
        radius *= ratio


def hcs_ts_leaf(angles_deg, r1, ratio):
    """Literal one-row port of hyperdims/src/hcs/geometry.ts (baseFrame /
    childFrame / circlePoint) -- deliberately NOT hcs_chain(), so the two
    can check each other."""
    c, u, v, w = (np.zeros(3), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]),
                  np.array([0, 0, 1.0]))
    radius = r1

    def circle_point(theta):
        t = np.radians(theta)
        return c + np.cos(t) * radius * u + np.sin(t) * radius * v

    for theta in angles_deg[:-1]:
        t = np.radians(theta)
        n = np.cos(t) * u + np.sin(t) * v
        c = circle_point(theta)
        u, v, w = n, w, np.cross(n, w)
        radius *= ratio
    return circle_point(angles_deg[-1])


# --------------------------------------------------------------------------
# The writer
# --------------------------------------------------------------------------

class Scene:
    def __init__(self, frames=1, dedupe=True, extra_cols=()):
        """frames: Channels length (1 = a static scene, no Channels files).
        dedupe: identical tracks (after rounding) share one column.
        extra_cols: further node columns (e.g. palette_id), written only for
        scenes that use them -- omit a column rather than write zeros."""
        self.frames = frames
        self.dedupe = dedupe
        self.extra_cols = tuple(extra_cols)
        self._seen = {}
        self.rows = []
        self.level = {0: -1}
        self.tracks = []          # (values, decimals); track id = index + 1
        self.chmap = []           # (channel_id, track_id, attribute)
        self.next_ch = 1

    def node(self, parent=0, *, type=TYPE_GLYPH, pos=(0, 0, 0), rot=(0, 0, 0), scale=1.0,
             color=(255, 255, 255, 255), geometry=GEO_SPHERE, hide=0, topo=TOPO_NONE,
             ratio=0.1, child_id=0, ch=0, show_text=0, text="", **extra):
        assert text, "every node gets a label"
        assert set(extra) <= set(self.extra_cols), extra
        nid = len(self.rows) + 1
        lvl = self.level[parent] + 1
        self.level[nid] = lvl
        sc = scale if isinstance(scale, (tuple, list, np.ndarray)) else (scale,) * 3
        c = tuple(int(round(v)) for v in color) + (255,) * (4 - len(color))
        self.rows.append([nid, type, parent, lvl, *(float(v) for v in pos),
                          *(float(v) for v in rot), *(float(v) for v in sc), *c,
                          geometry, int(hide), topo, float(ratio), child_id, ch,
                          int(show_text), 0, text,
                          *(extra.get(k, 0) for k in self.extra_cols)])
        return nid

    def track(self, values, dp=4):
        values = np.asarray(values, dtype=float)
        assert values.shape == (self.frames,), (values.shape, self.frames)
        if self.dedupe:
            key = (dp, np.round(values, dp).tobytes())
            if key not in self._seen:
                self.tracks.append((values, dp))
                self._seen[key] = len(self.tracks)
            return self._seen[key]
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
        if self.chmap:
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
                fh.write(",".join(["cyclecount"] + [f"ch{i + 1}" for i in range(len(cols))])
                         + "\r\n")
                for f in range(self.frames):
                    fh.write(str(f) + "," + ",".join(c[f] for c in cols) + "\r\n")
        with open(os.path.join(out_dir, f"{stem}_gv_node.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\r\n")
            w.writerow(NODE_COLS + list(self.extra_cols))
            for row in self.rows:
                w.writerow([num(v) if isinstance(v, float) else v for v in row])


# --------------------------------------------------------------------------
# Frames
# --------------------------------------------------------------------------

def frames_of_reference(sc, background, lift):
    """World background + turn + wall. -> (turn id, wall id)."""
    sc.node(0, type=0, color=(*background, 255), geometry=GEO_POINT, hide=1,
            text="World - background")
    turn = sc.node(0, pos=(0, 0, lift), rot=(0, 0, 45), hide=1, geometry=GEO_POINT,
                   text="turn frame - the default camera's azimuth (45): x toward you, y right")
    wall = sc.node(turn, rot=(0, -25, 0), hide=1, geometry=GEO_POINT,
                   text="wall - leaned back to the default camera's elevation (25)")
    return turn, wall


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

def window(frames, f0, f1):
    """1 on [f0, f1), else 0."""
    f = np.arange(frames)
    return ((f >= f0) & (f < f1)).astype(float)


def hide_channel(sc, visible):
    """A channel hiding a node whenever `visible` is 0."""
    return sc.channel([(sc.track(np.where(np.asarray(visible) > 0, 0, 1)), "hide")])


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


def polyline(sc, parent, pts, color, label, ratio=0.04, ch=0, hide=0):
    """A fixed TOPO_PLOT polyline; the label lives on the parent."""
    plot = sc.node(parent, geometry=GEO_POINT, topo=TOPO_PLOT, ratio=ratio,
                   color=(255, 255, 255, 0), ch=ch, hide=hide, text=label)
    for i, p in enumerate(pts):
        sc.node(plot, pos=tuple(float(v) for v in p), scale=0.0, color=color, geometry=GEO_CUBE,
                text=f"{label}: vertex {i}")
    return plot


def unit_circle(n=61):
    a = np.radians(np.linspace(-180.0, 180.0, n))
    return np.stack([np.cos(a), np.sin(a), np.zeros(n)], axis=1)
