"""
Scene-writing helpers shared by the two qudit-synthesis scenes: a node table
with Channels tracks (the same writer as lsa_transition_lab and
conformal_fluid_lab), polylines, captions and point clouds.
"""
import csv
import os

import numpy as np

GEO_CUBE, GEO_SPHERE, GEO_OCTA, GEO_POINT, GEO_CIRCLE, GEO_STAR = 1, 3, 11, 22, 24, 26
GEO_CUBE_WIRE, GEO_SPHERE_WIRE = 0, 2
TOPO_NONE, TOPO_PLOT, TOPO_POINTCLOUD = 0, 16, 18
CUBE_HALF = 0.57735           # a cube's face is 1/sqrt(3) out at scale 1

NODE_COLS = ["id", "type", "parent_id", "branch_level",
             "translate_x", "translate_y", "translate_z",
             "rotate_x", "rotate_y", "rotate_z",
             "scale_x", "scale_y", "scale_z",
             "color_r", "color_g", "color_b", "color_a",
             "geometry", "hide", "topo", "ratio",
             "ch_input_id", "show_text", "rotation_mode", "text"]

# Gate-count palette shared by both scenes and their plots: level / layer k
# gets LAYER_COLORS[k]. A warm-to-cool ramp, so "newer" reads as "cooler".
LAYER_COLORS = ((255, 90, 80), (255, 150, 60), (250, 205, 60), (190, 225, 70),
                (110, 215, 110), (60, 205, 170), (60, 185, 235), (90, 140, 255),
                (150, 115, 255), (205, 105, 240), (240, 110, 200))


def num(v):
    """Compact float: 4 dp, trailing zeros trimmed, never '-0'."""
    s = f"{float(v):.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


class Scene:
    def __init__(self, frames):
        self.frames = frames
        self.rows = []
        self.level = {0: -1}
        self.tracks = []          # formatted columns, track id = index + 1
        self.track_ids = {}       # formatted column -> track id (identical tracks shared)
        self.chmap = []           # (channel_id, track_id, attribute)
        self.next_ch = 1

    def node(self, parent=0, *, type=5, pos=(0, 0, 0), rot=(0, 0, 0), scale=1.0,
             color=(255, 255, 255, 255), geometry=GEO_SPHERE, hide=0, topo=TOPO_NONE,
             ratio=0.1, ch=0, show_text=0, text=""):
        nid = len(self.rows) + 1
        self.level[nid] = self.level[parent] + 1
        sc = scale if isinstance(scale, (tuple, list)) else (scale,) * 3
        c = tuple(color) + (255,) * (4 - len(color))
        self.rows.append([nid, type, parent, self.level[nid],
                          *(float(v) for v in pos), *rot, *sc, *c,
                          geometry, hide, topo, ratio, ch, show_text, 0, text])
        return nid

    def track(self, values):
        col = tuple(num(v) for v in values)
        assert len(col) == self.frames
        if col not in self.track_ids:
            self.tracks.append(col)
            self.track_ids[col] = len(self.tracks)
        return self.track_ids[col]

    def channel(self, bindings):
        """bindings: [(values, attribute), ...] -> new channel id."""
        ch = self.next_ch
        self.next_ch += 1
        for values, attr in bindings:
            self.chmap.append((ch, self.track(values), attr))
        return ch

    def _bake_frame0(self):
        """Write every channel-bound field as its frame-0 track value. The
        app opens a scene on the node CSV's static values and applies no
        frame until playback starts, so a layer that should appear later
        must already be hidden in the file itself."""
        first = {}
        for ch, tid, attr in self.chmap:
            first.setdefault(ch, []).append((NODE_COLS.index(attr),
                                             float(self.tracks[tid - 1][0])))
        ch_col = NODE_COLS.index("ch_input_id")
        for row in self.rows:
            for col, v in first.get(row[ch_col], ()):
                row[col] = int(v) if isinstance(row[col], int) else v

    def write(self, out_dir, stem):
        self._bake_frame0()
        os.makedirs(out_dir, exist_ok=True)
        # Companions first, node CSV last (Watch-and-Reload safe).
        with open(os.path.join(out_dir, f"{stem}_gv_ch-map.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\r\n")
            w.writerow(["channel_id", "track_id", "attribute"])
            w.writerows(self.chmap)
        with open(os.path.join(out_dir, f"{stem}_gv_ch-tracks.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            fh.write(",".join(["cyclecount"] + [f"ch{i + 1}" for i in range(len(self.tracks))])
                     + "\r\n")
            for f in range(self.frames):
                fh.write(str(f) + "," + ",".join(c[f] for c in self.tracks) + "\r\n")
        with open(os.path.join(out_dir, f"{stem}_gv_node.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\r\n")
            w.writerow(NODE_COLS)
            for row in self.rows:
                w.writerow([num(v) if isinstance(v, float) else v for v in row])


def line(sc, parent, pts, color, label, ratio=0.06, ch=0):
    """A fixed polyline; zero-scale vertices, each labelled."""
    plot = sc.node(parent, geometry=GEO_POINT, topo=TOPO_PLOT, ratio=ratio,
                   color=(255, 255, 255, 0), text=label, ch=ch)
    for i, p in enumerate(pts):
        sc.node(plot, pos=tuple(float(v) for v in p), scale=0.0, color=color,
                text=f"{label} (vertex {i + 1})")
    return plot


def circle_pts(center, radius, n=96, axes=(1, 2), a0=0.0, a1=2 * np.pi):
    """Points on a circle (or arc) in the plane of the two given local axes."""
    out = []
    for a in np.linspace(a0, a1, n):
        p = list(center)
        p[axes[0]] += radius * np.cos(a)
        p[axes[1]] += radius * np.sin(a)
        out.append(tuple(p))
    return out


def caption(sc, parent, pos, text, show=1, ch=0):
    return sc.node(parent, pos=pos, scale=0.06, geometry=GEO_CIRCLE,
                   color=(200, 200, 220), show_text=show, text=text, ch=ch)


def cloud(sc, parent, positions, colors, labels, ratio, title, ch=0):
    """A point-cloud parent (one batched draw) holding one point per row.
    ratio * 20 = the point size in pixels. The parent itself is a GEO_POINT
    sprite at its frame's origin, so it is fully transparent; the cloud draws
    from the children's colours alone."""
    p = sc.node(parent, geometry=GEO_POINT, topo=TOPO_POINTCLOUD, ratio=ratio,
                color=(255, 255, 255, 0), text=title, ch=ch)
    for xyz, c, t in zip(positions, colors, labels):
        sc.node(p, pos=tuple(float(v) for v in xyz), scale=1.0, geometry=GEO_POINT,
                color=c, text=t)
    return p


def stage_track(frames, start, end=None):
    """1 inside [start, end), else 0 -- for show_text / visibility switches."""
    v = np.zeros(frames)
    v[start:end] = 1
    return v
