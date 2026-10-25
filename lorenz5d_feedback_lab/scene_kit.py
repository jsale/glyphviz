"""
Shared scene plumbing for this lab's generators: the node/channel writer and
the comet trail, adapted from lorenz_sync_lab/generate_lorenz_sync.py (where
the performance reasoning behind the trail design is measured).

Frames of reference used by both scenes:

    turn   world, rotated to the default camera's azimuth (45 deg)
    wall   leaned back to the default camera's elevation (25 deg);
           wall-local +X toward the viewer, +Y screen right, +Z up
    board  wall rotated so board-local +x = screen right, +y = up,
           +z = toward the viewer -- the frame the scenes are drawn in
"""
import csv
import math
import os

import numpy as np

GEO_CUBE, GEO_SPHERE, GEO_CONE, GEO_POINT, GEO_CIRCLE = 1, 3, 5, 22, 24
TOPO_NONE, TOPO_PLOT, TOPO_SURFACE = 0, 16, 17
CUBE_FACE = 0.57735                   # a unit-scale cube's faces sit this far out

NODE_COLS = ["id", "type", "parent_id", "branch_level",
             "translate_x", "translate_y", "translate_z",
             "rotate_x", "rotate_y", "rotate_z",
             "scale_x", "scale_y", "scale_z",
             "color_r", "color_g", "color_b", "color_a",
             "geometry", "hide", "topo", "ratio",
             "child_id", "ch_input_id", "show_text", "rotation_mode", "text"]


def num(v, dp=4):
    """Compact float: dp decimals, trailing zeros trimmed, never '-0'."""
    s = f"{float(v):.{dp}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


class Scene:
    def __init__(self, frames):
        self.frames = frames
        self.rows = []
        self.level = {0: -1}
        self.tracks = []          # (values, decimals); track id = index + 1
        self.chmap = []           # (channel_id, track_id, attribute)
        self.next_ch = 1

    def node(self, parent=0, *, type=5, pos=(0, 0, 0), rot=(0, 0, 0), scale=1.0,
             color=(255, 255, 255, 255), geometry=GEO_SPHERE, hide=0, topo=TOPO_NONE,
             ratio=0.1, child_id=0, ch=0, show_text=0, text=""):
        nid = len(self.rows) + 1
        lvl = self.level[parent] + 1
        self.level[nid] = lvl
        sc = scale if isinstance(scale, (tuple, list)) else (scale,) * 3
        c = tuple(int(round(v)) for v in color) + (255,) * (4 - len(color))
        self.rows.append([nid, type, parent, lvl, *(float(v) for v in pos),
                          *(float(v) for v in rot), *(float(v) for v in sc), *c,
                          geometry, hide, topo, float(ratio), child_id, ch, show_text, 0, text])
        return nid

    def track(self, values, dp=4):
        values = np.asarray(values, dtype=float)
        assert len(values) == self.frames, (len(values), self.frames)
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


def frames_of_reference(sc, background, lift):
    """World background + turn + wall + board. -> board node id."""
    sc.node(0, type=0, color=(*background, 255), geometry=GEO_POINT, hide=1,
            text="World - background")
    turn = sc.node(0, pos=(0, 0, lift), rot=(0, 0, 45), hide=1, geometry=GEO_POINT,
                   text="wall frame - turned to the default camera's azimuth (45)")
    wall = sc.node(turn, rot=(0, -25, 0), hide=1, geometry=GEO_POINT,
                   text="wall - leaned back to the default camera's elevation (25)")
    return wall


def board(sc, wall, origin, scale=1.0):
    """A frame on the wall with x = screen right, y = up, z = toward the viewer.
    Rz(90) then Rx(90) maps board x -> wall +Y, y -> wall +Z, z -> wall +X.
    `origin` is in wall coords (toward viewer, right, up); `scale` sizes the
    whole board (labels keep their pixel size, so it also spreads them out)."""
    outer = sc.node(wall, pos=origin, rot=(0, 0, 90), scale=scale, hide=1, geometry=GEO_POINT,
                    text="board frame, step 1 of 2 (Rz 90)")
    return sc.node(outer, rot=(90, 0, 0), hide=1, geometry=GEO_POINT,
                   text="board frame: x = right, y = up, z = toward the viewer")


def bar(sc, parent, x, y0, y1, width, color, *, z=0.0, depth=None, text="", ch=0):
    """A Cube spanning y0..y1 at x (scale 0 if the span is empty)."""
    h = abs(y1 - y0)
    d = width if depth is None else depth
    s = (width / (2 * CUBE_FACE), h / (2 * CUBE_FACE), d / (2 * CUBE_FACE)) if h > 0 else 0.0
    return sc.node(parent, pos=(x, 0.5 * (y0 + y1), z), scale=s, color=color,
                   geometry=GEO_CUBE, text=text, ch=ch)


def bar_channel(sc, y0, y1, width, depth=None):
    """Channel animating a bar's centre and height from per-frame y0, y1 arrays."""
    y0, y1 = np.asarray(y0, float), np.asarray(y1, float)
    h = np.abs(y1 - y0)
    d = width if depth is None else depth
    sy = np.where(h > 0, h / (2 * CUBE_FACE), 0.0)
    sxz = np.where(h > 0, 1.0, 0.0)
    return sc.channel([(sc.track(0.5 * (y0 + y1)), "translate_y"),
                       (sc.track(sy), "scale_y"),
                       (sc.track(sxz * width / (2 * CUBE_FACE)), "scale_x"),
                       (sc.track(sxz * d / (2 * CUBE_FACE)), "scale_z")])


def pos_channel(sc, xyz, dp=4):
    """A channel driving translate_x/y/z from an (frames, 3) array."""
    return sc.channel([(sc.track(xyz[:, i], dp), a)
                       for i, a in enumerate(("translate_x", "translate_y", "translate_z"))])


def static_plot(sc, parent, pts, color, label, ratio=0.06, colors=None, closed=False):
    """A fixed polyline. The label goes on the parent only (vertices are
    zero-scale and unclickable; labelling thousands of them costs paint time)."""
    plot = sc.node(parent, geometry=GEO_POINT, topo=TOPO_PLOT, ratio=ratio,
                   color=(255, 255, 255, 0), text=label)
    pts = list(pts)
    if closed:
        pts.append(pts[0])
        if colors is not None:
            colors = list(colors) + [colors[0]]
    for i, p in enumerate(pts):
        c = colors[i] if colors is not None else color
        sc.node(plot, pos=tuple(float(v) for v in p), scale=0.0, color=c,
                geometry=GEO_CUBE)
    return plot


# --------------------------------------------------------------------------
# Comet trails (see lorenz_sync_lab: one hide channel per segment, shared by
# every trail in the scene, is what keeps playback cheap)
# --------------------------------------------------------------------------

class Comets:
    """A comet is two consecutive copies of its path: a bright thick head that
    hands over to a dim thin tail. bands: (from age, to age in frames, vertex
    alpha, Plot ratio)."""

    def __init__(self, sc, frames, trail_step=2, seg=10,
                 bands=((0, 40, 255, 0.13), (40, 160, 105, 0.07))):
        self.sc, self.frames, self.step, self.seg, self.bands = sc, frames, trail_step, seg, bands
        self.n_verts = (frames - 1) // trail_step + 1
        self.n_segs = (self.n_verts - 1 + seg - 1) // seg
        f = np.arange(frames)
        self.channels = []
        for age0, age1, _alpha, _ratio in bands:
            chans = []
            for k in range(self.n_segs):
                i0, i1 = self.span(k)
                start = i0 * trail_step
                on = max(start + age0, (i0 + i1) * trail_step // 2)
                live = (f >= on) & (f < start + age1)
                chans.append(sc.channel([(sc.track(np.where(live, 0, 1)), "hide")]))
            self.channels.append(chans)

    def span(self, k):
        return k * self.seg, min((k + 1) * self.seg, self.n_verts - 1)

    def trail(self, parent, fine, sub, colors, label, max_step):
        """fine: the path at integrator resolution, frame f = row f * sub.
        colors: one RGB per frame, or a single RGB tuple."""
        sc = self.sc
        holder = sc.node(parent, hide=1, geometry=GEO_POINT, text=label)
        extra = {}
        for (_a0, _a1, alpha, ratio), chans in zip(self.bands, self.channels):
            for k, ch in enumerate(chans):
                i0, i1 = self.span(k)
                seg = sc.node(holder, geometry=GEO_POINT, topo=TOPO_PLOT, ratio=ratio,
                              color=(255, 255, 255, 0), hide=1, ch=ch)
                for i in range(i0, i1 + 1):
                    b = i * self.step
                    c = colors if isinstance(colors, tuple) else colors[b]
                    j0 = b * sub
                    sc.node(seg, pos=tuple(float(v) for v in fine[j0]), scale=0.0,
                            color=(*c[:3], alpha), geometry=GEO_CUBE)
                    if i == i1:
                        continue
                    j1 = (b + self.step) * sub
                    if j0 not in extra:
                        extra[j0] = densify(fine, j0, j1, max_step)
                    for j in extra[j0]:
                        sc.node(seg, pos=tuple(float(v) for v in fine[j]), scale=0.0,
                                color=(*c[:3], alpha), geometry=GEO_CUBE)
        return holder


def densify(fine, j0, j1, max_step):
    """Fine-row indices strictly between j0 and j1 so no chord exceeds max_step."""
    seg = fine[j0:j1 + 1]
    length = np.linalg.norm(np.diff(seg, axis=0), axis=1).sum()
    n = int(math.ceil(length / max_step)) - 1
    if n <= 0:
        return []
    return sorted(set(int(round(j)) for j in np.linspace(j0, j1, n + 2)[1:-1]) - {j0, j1})


def lerp_color(stops, u):
    """Piecewise-linear colour ramp; stops = [(u, (r, g, b)), ...] sorted."""
    u = float(np.clip(u, stops[0][0], stops[-1][0]))
    for (u0, c0), (u1, c1) in zip(stops, stops[1:]):
        if u <= u1:
            w = 0.0 if u1 == u0 else (u - u0) / (u1 - u0)
            return tuple(int(round(c0[i] + (c1[i] - c0[i]) * w)) for i in range(3))
    return stops[-1][1]
