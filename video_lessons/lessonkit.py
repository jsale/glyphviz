"""
lessonkit.py
============
Render a short GlyphViz feature lesson straight from the engine: no screen
recording, no editing timeline. A lesson is a scene (a list of Nodes) plus a
list of Shots; each Shot carries its narration line, camera keyframes, and the
overlays drawn on top (callouts, key caps, a mouse-gesture glyph, a live
readout). The narration is synthesized first and each clip's length sets its
shot's length, so picture and voice cannot drift.

Pipeline, per lesson:

    scene Nodes --save--> <out>/scene/<name>_gv_node.csv  (the lesson ships
                                                          with its own scene)
    Shot.say ----TTS---->  one WAV per shot  --> shot durations
    per frame:  animate nodes -> ease camera -> grab the real Viewport
                -> draw overlays (PIL) -> pipe raw RGB into ffmpeg
    ffmpeg:     frames + narration.wav -> <name>.mp4, plus <name>.srt

Everything visible in the 3D view is the app's own renderer (tools/
export_frame.py's _build_viewport), so a lesson can never show a feature
behaving differently from how the app behaves. Overlays are the only thing
drawn outside the engine.
"""
from __future__ import annotations

import math
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))

# export_frame pins devicePixelRatio to 1 at import, BEFORE Qt loads. That
# matters here for the same reason it matters there: the tag overlay is drawn
# in logical pixels and would land in the wrong place on a scaled display.
import export_frame  # noqa: E402  (side effect: Qt DPI env vars)

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

FFMPEG = r"C:\ffmpeg\bin\ffmpeg.exe"

# Brand palette, shared with examples/Topology_Animation_Examples.
BG = (14, 14, 26)
INDIGO = (63, 81, 181)
TEAL = (38, 198, 181)
CORAL = (255, 111, 97)
VIOLET = (167, 139, 250)
AMBER = (255, 193, 7)
CHALK = (236, 240, 255)


# ------------------------------------------------------------------ script

@dataclass
class Key:
    """One camera keyframe, at fraction `u` (0..1) of its shot.

    Two ways to say where the camera is, matching the two ways GlyphViz
    moves it:

    * orbit (default): `target` + azimuth/elevation/distance — the rig the
      app's orbit camera uses. `target` may be a node id, resolved to that
      node's world position on the frame it is used (so it tracks a moving
      node).
    * eye: an eye position plus the heading/pitch it looks along — how
      Camera Mode flight is naturally described. When BOTH ends of a
      segment give `eye`, the eye is interpolated (a straight flight path)
      instead of the target, which would otherwise swing the eye in an arc.

    Any field left None inherits from the previous key, so a key can change
    one thing.
    """
    u: float = 0.0
    az: float | None = None
    el: float | None = None
    dist: float | None = None
    target: tuple | int | None = None
    eye: tuple | None = None


@dataclass
class Callout:
    """A label with a leader line to a node, drawn where the engine projects
    that node. `start`/`end` are shot fractions; it fades in and out."""
    node: int
    text: str
    start: float = 0.0
    end: float = 1.0
    offset: tuple = (90, -70)        # label box position relative to node, px
    ring: bool = True
    color: tuple = AMBER


@dataclass
class Shot:
    say: str
    keys: Sequence[Key] = ()
    heading: str | None = None        # small lower-third heading
    title: str | None = None          # big centred title card (fades out)
    keycap: str | Callable | None = None   # "T", "Ctrl + Click", or f(u)
    keycap_note: str | None = None    # text beside the key cap
    callouts: Sequence[Callout] = ()
    select: set | None = None         # selection at shot start (None = keep)
    state: dict = field(default_factory=dict)   # Viewport attrs at start
    events: Sequence[tuple] = ()      # (u, {attr: value}) or (u, f(lesson))
    animate: Callable | None = None   # f(lesson, u) mutates nodes
    readout: Callable | None = None   # f(lesson, u) -> str | None
    gesture: Callable | None = None   # f(u) -> dict (see _draw_gesture)
    summary: Sequence[str] = ()       # bullet card (end of lesson)
    scene: str | None = None          # cut to this node CSV at shot start
    # Channels playback speed from this shot on, in animation frames per
    # second of video (0 pauses; None keeps the previous shot's). Needs a
    # use_window lesson, whose MainWindow loaded the channel files.
    ch_rate: float | None = None
    ch_frame: float | None = None     # jump the animation here at shot start
    # Play the animation from frame A to frame B across this shot (linear in
    # shot time). Chain shots A->B, B->C so playback never skips. Or give
    # ((u, frame), ...) pairs to play piecewise, e.g. arrive and then hold.
    ch_span: tuple | None = None
    card: Callable | None = None      # f(overlay, draw, u): a custom full-frame card
    # Play a stretch of the scene's OWN soundtrack, in sync with its Channels
    # animation, once the narration line has finished:
    #   dict(path=<audio file>, frames=(f0, f1), fps=30, gain=1.0)
    # The animation holds on f0 while the line is spoken, then plays f0 -> f1
    # at the scene's frame rate while the audio from f0/fps to f1/fps plays
    # under it, exactly as the app pairs them through an audio manifest. The
    # shot is lengthened to fit.
    soundtrack: dict | None = None
    min_dur: float = 0.0
    tail: float = 0.45                # silence after the narration, seconds


@dataclass
class Lesson:
    name: str                         # file stem, e.g. "tags"
    title: str
    nodes: list
    shots: list
    show_grid: bool = True
    show_axes: bool = False
    # Drive a real (never shown) MainWindow instead of a bare Viewport, so a
    # lesson can perform the app's own actions -- N, Shift+N, the New Object
    # Defaults, the Topology list -- through the very handlers a user's
    # keypress reaches. `nodes` is then the STARTING scene.
    use_window: bool = False
    # Film an existing scene file (e.g. a gallery example) instead of
    # `nodes`: loaded exactly as the app opens it, media/ and meshes/ included.
    scene_csv: str | None = None
    voice: str = "af_heart"           # Kokoro voice id (render_lesson --voice overrides)
    speed: float = 1.0                # Kokoro speaking speed
    # Called once before rendering, e.g. to write a lesson's own copy of a
    # scene. Returns nothing; may set scene_csv.
    prepare: Callable | None = None
    ch_loop: bool = True              # wrap the Channels clock at the end
    # Filled in at render time:
    vp: object = None
    win: object = None
    ch_rate: float = 0.0
    ch_frame: float = 0.0

    def node(self, node_id):
        return self.vp._scene.node_by_id(node_id)

    def show_ch_frame(self, frame: float):
        """Put the Channels animation on `frame`, through the same method the
        app's play timer and frame slider call."""
        w = self.win
        if w is None or w._ch_engine is None:
            return
        n = w._ch_engine.frame_count
        f = int(frame) % n if self.ch_loop else min(int(frame), n - 1)
        self.ch_frame = float(frame)
        w._ch_frame = f
        w._ch_apply_and_show_frame(f)


# ------------------------------------------------------------------ easing

def ease(u: float) -> float:
    """Smoothstep-quintic: zero velocity AND acceleration at both ends, so a
    camera move starts and lands without the jolt a cubic still has."""
    u = min(max(u, 0.0), 1.0)
    return u * u * u * (u * (6 * u - 15) + 10)


def lerp(a, b, t):
    return a + (b - a) * t


def _dir(az, el):
    a, e = math.radians(az), math.radians(el)
    return np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a),
                     math.sin(e)])


class CameraTrack:
    """Resolves a lesson's keyframes into a camera per frame. Keys are
    completed forward (missing fields inherit), and each shot's keys start
    from wherever the previous shot left the camera."""

    def __init__(self, lesson: Lesson, start: dict):
        self.lesson = lesson
        self.cam = dict(start)   # az, el, dist, target(np), eye(np|None)

    def _resolve_target(self, t):
        if isinstance(t, int):
            p = self.lesson.vp.world_position(t)
            return np.array(p if p is not None else (0, 0, 0), float)
        return np.array(t, float)

    def _complete(self, key: Key, prev: dict) -> dict:
        c = dict(prev)
        for f in ("az", "el", "dist"):
            v = getattr(key, f)
            if v is not None:
                c[f] = float(v)
        if key.eye is not None:
            c["eye"] = np.array(key.eye, float)
            c["target"] = c["eye"] - c["dist"] * _dir(c["az"], c["el"])
            # A later orbit key that names no target orbits where flight
            # left off, not where the camera was before it took off.
            c["target_src"] = c["target"].tolist()
        else:
            c["eye"] = None
            if key.target is not None:
                c["target_src"] = key.target
            c["target"] = self._resolve_target(c.get("target_src",
                                                     c["target"].tolist()))
        return c

    def shot_keys(self, shot: Shot):
        keys = list(shot.keys)
        out = []
        prev = dict(self.cam)
        if not keys or keys[0].u > 0:
            out.append((0.0, dict(prev)))
        for k in keys:
            prev = self._complete(k, prev)
            out.append((k.u, dict(prev)))
        if out[-1][0] < 1.0:
            out.append((1.0, dict(out[-1][1])))
        return out

    def at(self, keys, u: float) -> dict:
        # Ease ONCE over the whole shot, then walk the keys piecewise-linearly
        # in eased time: the camera starts and lands softly but passes
        # through interior keys without stopping (per-segment easing made a
        # curving flight path halt at every waypoint).
        ue = ease(u)
        for (u0, a), (u1, b) in zip(keys, keys[1:]):
            if ue <= u1 or (u1 == keys[-1][0]):
                t = min(max((ue - u0) / (u1 - u0), 0.0), 1.0) if u1 > u0 else 1.0
                break
        # Re-resolve node-id targets every frame so they track motion.
        ta = self._resolve_target(a["target_src"]) if (
            a["eye"] is None and isinstance(a.get("target_src"), int)) else a["target"]
        tb = self._resolve_target(b["target_src"]) if (
            b["eye"] is None and isinstance(b.get("target_src"), int)) else b["target"]
        az, el = lerp(a["az"], b["az"], t), lerp(a["el"], b["el"], t)
        dist = lerp(a["dist"], b["dist"], t)
        if a["eye"] is not None and b["eye"] is not None:
            eye = lerp(a["eye"], b["eye"], t)
            target = eye - dist * _dir(az, el)
        else:
            target = lerp(ta, tb, t)
        cam = dict(az=az, el=el, dist=dist, target=target, eye=None)
        self.cam = dict(b)
        return cam


def span_frame(span, u: float) -> float:
    """The animation frame at shot fraction u for a Shot.ch_span."""
    if not isinstance(span[0], (tuple, list)):
        span = ((0.0, span[0]), (1.0, span[1]))
    if u <= span[0][0]:
        return float(span[0][1])
    for (u0, f0), (u1, f1) in zip(span, span[1:]):
        if u <= u1:
            return f0 + (f1 - f0) * ((u - u0) / (u1 - u0) if u1 > u0 else 1.0)
    return float(span[-1][1])


# ------------------------------------------------------------------ overlays

def _font(size, bold=False, mono=False):
    names = (["consola.ttf"] if mono else
             (["segoeuib.ttf"] if bold else ["segoeui.ttf"]))
    for n in names:
        try:
            return ImageFont.truetype(f"C:/Windows/Fonts/{n}", size)
        except OSError:
            pass
    return ImageFont.load_default()


class Overlay:
    def __init__(self, w, h):
        self.w, self.h = w, h
        s = h / 720.0
        self.s = s
        self.f_title = _font(int(54 * s), bold=True)
        self.f_sub = _font(int(24 * s))
        self.f_head = _font(int(20 * s), bold=True)
        self.f_cap = _font(int(24 * s))
        self.f_key = _font(int(26 * s), bold=True)
        self.f_note = _font(int(20 * s))
        self.f_call = _font(int(19 * s), bold=True)
        self.f_mono = _font(int(22 * s), mono=True)
        self.f_bullet = _font(int(28 * s))

    # -- helpers
    def _box(self, d, xy, fill, radius=10, outline=None):
        d.rounded_rectangle(xy, radius=int(radius * self.s), fill=fill,
                            outline=outline, width=max(1, int(2 * self.s)))

    @staticmethod
    def _a(rgb, alpha):
        return (*rgb, int(max(0, min(1, alpha)) * 255))

    def _wrap(self, d, text, font, max_w):
        lines, cur = [], ""
        for word in text.split():
            trial = f"{cur} {word}".strip()
            if d.textlength(trial, font=font) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines

    # -- elements
    def title(self, d, title, sub, alpha):
        if alpha <= 0:
            return
        d.rectangle((0, 0, self.w, self.h), fill=(*BG, int(170 * alpha)))
        tw = d.textlength(title, font=self.f_title)
        y = self.h * 0.40
        d.text(((self.w - tw) / 2, y), title, font=self.f_title,
               fill=self._a(CHALK, alpha))
        bar_w = 120 * self.s
        d.rectangle(((self.w - bar_w) / 2, y + 78 * self.s,
                     (self.w + bar_w) / 2, y + 83 * self.s),
                    fill=self._a(TEAL, alpha))
        sw = d.textlength(sub, font=self.f_sub)
        d.text(((self.w - sw) / 2, y + 98 * self.s), sub, font=self.f_sub,
               fill=self._a((180, 186, 210), alpha))

    def brand(self, d, lesson_title, heading):
        m = 22 * self.s
        # Backing plate: the brand must stay legible over a bright glyph.
        w = d.textlength(f"GlyphViz  ·  {lesson_title}", font=self.f_head) + 30 * self.s
        if heading:
            w = max(w, d.textlength(heading, font=self.f_note) + 20 * self.s)
        self._box(d, (m - 10 * self.s, m - 6 * self.s, m + w,
                      m + (58 if heading else 32) * self.s), fill=(8, 8, 16, 150))
        d.text((m, m), "GlyphViz", font=self.f_head, fill=(*TEAL, 230))
        x = m + d.textlength("GlyphViz", font=self.f_head) + 10 * self.s
        d.text((x, m), f"·  {lesson_title}", font=self.f_head,
               fill=(*CHALK, 200))
        if heading:
            d.text((m, m + 28 * self.s), heading, font=self.f_note,
                   fill=(180, 186, 210, 210))

    def caption(self, d, text):
        if not text:
            return
        lines = self._wrap(d, text, self.f_cap, self.w * 0.72)
        lh = 32 * self.s
        total = lh * len(lines)
        y0 = self.h - 36 * self.s - total
        widest = max(d.textlength(l, font=self.f_cap) for l in lines)
        pad = 14 * self.s
        self._box(d, ((self.w - widest) / 2 - pad, y0 - pad * 0.6,
                      (self.w + widest) / 2 + pad, y0 + total + pad * 0.4),
                  fill=(8, 8, 16, 185))
        for i, l in enumerate(lines):
            lw = d.textlength(l, font=self.f_cap)
            d.text(((self.w - lw) / 2, y0 + i * lh), l, font=self.f_cap,
                   fill=(*CHALK, 245))

    def keycap(self, d, key, note, alpha, y_above):
        if alpha <= 0 or not key:
            return
        m = 26 * self.s
        parts = [p.strip() for p in key.split("+")]
        x = m
        kh = 46 * self.s
        y = y_above - kh - 22 * self.s
        for i, p in enumerate(parts):
            if i:
                d.text((x + 4 * self.s, y + 8 * self.s), "+", font=self.f_key,
                       fill=self._a(CHALK, alpha))
                x += 28 * self.s
            kw = max(kh, d.textlength(p, font=self.f_key) + 28 * self.s)
            self._box(d, (x, y + 4 * self.s, x + kw, y + kh + 4 * self.s),
                      fill=self._a((0, 0, 0), alpha * 0.6), radius=9)
            self._box(d, (x, y, x + kw, y + kh),
                      fill=self._a((238, 240, 248), alpha), radius=9,
                      outline=self._a((150, 155, 175), alpha))
            tw = d.textlength(p, font=self.f_key)
            d.text((x + (kw - tw) / 2, y + 6 * self.s), p, font=self.f_key,
                   fill=self._a((30, 32, 48), alpha))
            x += kw
        if note:
            d.text((x + 16 * self.s, y + 10 * self.s), note,
                   font=self.f_note, fill=self._a(CHALK, alpha))

    def callout(self, d, sx, sy, radius_px, c: Callout, alpha):
        if alpha <= 0 or not np.isfinite(sx):
            return
        s = self.s
        r = max(radius_px * 1.15, 16 * s)
        col = self._a(c.color, alpha)
        if c.ring:
            d.ellipse((sx - r, sy - r, sx + r, sy + r), outline=col,
                      width=max(2, int(3 * s)))
        dx, dy = c.offset
        lx, ly = sx + dx * s, sy + dy * s
        # Leader starts on the ring, not at the centre.
        vx, vy = lx - sx, ly - sy
        n = math.hypot(vx, vy) or 1.0
        x0, y0 = sx + vx / n * r, sy + vy / n * r
        d.line((x0, y0, lx, ly), fill=col, width=max(2, int(2 * s)))
        tw = d.textlength(c.text, font=self.f_call)
        pad = 9 * s
        bx0 = lx if dx >= 0 else lx - tw - 2 * pad
        by0 = ly - 16 * s
        self._box(d, (bx0, by0, bx0 + tw + 2 * pad, by0 + 32 * s),
                  fill=self._a((10, 10, 20), alpha * 0.85), radius=7,
                  outline=col)
        d.text((bx0 + pad, by0 + 3 * s), c.text, font=self.f_call,
               fill=self._a(CHALK, alpha))

    def readout(self, d, text):
        if not text:
            return
        lines = text.split("\n")
        s = self.s
        lh = 30 * s
        w = max(d.textlength(l, font=self.f_mono) for l in lines) + 30 * s
        x0 = self.w - w - 24 * s
        y0 = 24 * s
        self._box(d, (x0, y0, x0 + w, y0 + lh * len(lines) + 18 * s),
                  fill=(8, 8, 16, 200), outline=(*INDIGO, 255))
        for i, l in enumerate(lines):
            d.text((x0 + 15 * s, y0 + 9 * s + i * lh), l, font=self.f_mono,
                   fill=(*CHALK, 245))

    def gesture(self, d, g: dict, alpha):
        """Mouse-drag glyph: where the button went down (the anchor) and where
        the cursor is now, with an arrow between. Camera Mode's rate flight
        is steered by exactly that offset, so drawing it IS the instruction."""
        if alpha <= 0 or not g:
            return
        s = self.s
        cx, cy = g.get("pos", (self.w * 0.80, self.h * 0.60))
        ax, ay = cx, cy
        ox, oy = g.get("offset", (0, 0))
        px, py = ax + ox * s, ay + oy * s
        col = self._a(AMBER, alpha)
        d.ellipse((ax - 9 * s, ay - 9 * s, ax + 9 * s, ay + 9 * s),
                  outline=col, width=max(2, int(3 * s)))
        if math.hypot(ox, oy) > 4:
            d.line((ax, ay, px, py), fill=col, width=max(2, int(3 * s)))
            ang = math.atan2(py - ay, px - ax)
            hl = 16 * s
            for da in (2.6, -2.6):
                d.line((px, py, px + hl * math.cos(ang + da),
                        py + hl * math.sin(ang + da)),
                       fill=col, width=max(2, int(3 * s)))
        # A little mouse with the held button lit.
        mx, my = ax - 70 * s, ay - 26 * s
        mw, mh = 40 * s, 58 * s
        self._box(d, (mx, my, mx + mw, my + mh), fill=self._a((30, 32, 48), alpha),
                  radius=18, outline=self._a(CHALK, alpha))
        d.line((mx + mw / 2, my, mx + mw / 2, my + mh * 0.42),
               fill=self._a(CHALK, alpha), width=max(1, int(2 * s)))
        d.line((mx, my + mh * 0.42, mx + mw, my + mh * 0.42),
               fill=self._a(CHALK, alpha), width=max(1, int(2 * s)))
        btn = g.get("button")
        if btn in ("left", "right"):
            x0 = mx + 3 * s if btn == "left" else mx + mw / 2 + 2 * s
            d.rounded_rectangle((x0, my + 3 * s, x0 + mw / 2 - 5 * s,
                                 my + mh * 0.42 - 2 * s),
                                radius=int(6 * s), fill=col)
        elif btn == "wheel":
            d.rounded_rectangle((mx + mw / 2 - 4 * s, my + 8 * s,
                                 mx + mw / 2 + 4 * s, my + 22 * s),
                                radius=int(4 * s), fill=col)
        if g.get("label"):
            tw = d.textlength(g["label"], font=self.f_note)
            d.text((ax - tw / 2, ay + 40 * s), g["label"], font=self.f_note,
                   fill=self._a(CHALK, alpha))

    def summary(self, d, title, bullets, alpha):
        if alpha <= 0 or not bullets:
            return
        s = self.s
        d.rectangle((0, 0, self.w, self.h), fill=(*BG, int(228 * alpha)))
        x0, y = self.w * 0.18, self.h * 0.26
        d.text((x0, y), title, font=self.f_title, fill=self._a(CHALK, alpha))
        y += 90 * s
        for b in bullets:
            d.ellipse((x0, y + 13 * s, x0 + 12 * s, y + 25 * s),
                      fill=self._a(TEAL, alpha))
            d.text((x0 + 28 * s, y), b, font=self.f_bullet,
                   fill=self._a(CHALK, alpha))
            y += 50 * s


def text_card(title, lines, color=TEAL, mono=True, sub=None, footer=None):
    """A full-frame text card for Shot.card: a heading, an optional
    subheading, a boxed block of lines, and an optional footer."""
    def draw(ov, d, u):
        a = min(1.0, u / 0.06, (1 - u) / 0.06)
        if a <= 0:
            return
        s = ov.s
        d.rectangle((0, 0, ov.w, ov.h), fill=(*BG, int(215 * a)))
        x, y = ov.w * 0.09, ov.h * 0.14
        d.text((x, y), title, font=ov.f_head, fill=(*color, int(255 * a)))
        if sub:
            d.text((x, y + 30 * s), sub, font=ov.f_note, fill=(180, 186, 210, int(230 * a)))
        y += 76 * s
        font = ov.f_mono if mono else ov.f_bullet
        lh = (29 if mono else 40) * s
        w = max(d.textlength(l, font=font) for l in lines) + 34 * s
        ov._box(d, (x - 16 * s, y - 12 * s, x - 16 * s + w, y + lh * len(lines) + 8 * s),
                fill=(8, 8, 16, int(225 * a)), outline=(*color, int(255 * a)))
        for i, l in enumerate(lines):
            d.text((x, y + i * lh), l, font=font, fill=(*CHALK, int(245 * a)))
        if footer:
            d.text((x, y + lh * len(lines) + 26 * s), footer, font=ov.f_note,
                   fill=(180, 186, 210, int(230 * a)))
    return draw


def _fade(u, start, end, dur_s, shot_len):
    """0..1 envelope that fades over ~0.35 s at each end of [start, end]."""
    if u < start or u > end:
        return 0.0
    k = 0.35 / max(shot_len, 1e-6)
    return min(1.0, (u - start) / k if k else 1, (end - u) / k if k else 1)


# ------------------------------------------------------------------ render

@dataclass
class ShotTiming:
    start: float
    dur: float
    audio: Path | None
    speech: float
    sound_at: float | None = None     # absolute start of the shot's soundtrack


SOUND_GAP = 0.5      # seconds between the narration ending and a soundtrack


def plan_timing(lesson: Lesson, clips: list, lead_in=0.35) -> list[ShotTiming]:
    t = 0.0
    out = []
    for shot, (path, speech) in zip(lesson.shots, clips):
        dur = max(lead_in + speech + shot.tail, shot.min_dur)
        sound_at = None
        if shot.soundtrack:
            st = shot.soundtrack
            f0, f1 = st["frames"]
            at = lead_in + speech + SOUND_GAP
            sound_at = t + at
            dur = max(dur, at + (f1 - f0) / st.get("fps", 30) + 1.2)
        out.append(ShotTiming(t, dur, path, speech, sound_at))
        t += dur
    return out


def soundtrack_frame(shot: Shot, tm: ShotTiming, t: float) -> float:
    """The animation frame at video time t in a soundtrack shot."""
    st = shot.soundtrack
    f0, f1 = st["frames"]
    if t <= tm.sound_at:
        return float(f0)
    return min(float(f1), f0 + (t - tm.sound_at) * st.get("fps", 30))


def grab_rgb(vp, w, h) -> np.ndarray:
    from PySide6.QtGui import QImage
    img = vp.grabFramebuffer()
    if img.width() != w or img.height() != h:
        from PySide6.QtCore import Qt
        img = img.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    img = img.convertToFormat(QImage.Format.Format_RGB888)
    arr = np.frombuffer(img.constBits(), np.uint8,
                        count=img.bytesPerLine() * h).reshape(h, img.bytesPerLine())
    return arr[:, : w * 3].reshape(h, w, 3).copy()


def _node_screen(vp, node_id, w, h):
    """(x, y, radius_px) of a node as the engine last drew it."""
    from glyphviz_core import gizmo
    from glyphviz_core import scene as scene_mod
    if vp._mv_matrix is None:
        return float("nan"), float("nan"), 0.0
    pos = vp.world_position(node_id)
    if pos is None:
        return float("nan"), float("nan"), 0.0
    node = vp._scene.node_by_id(node_id)
    m = np.asarray(scene_mod.node_world_matrix(node, vp._scene))[:3, :3]
    r = float(np.linalg.norm(m, axis=0).max())
    mvp = vp._proj_matrix @ vp._mv_matrix
    # Radius: project a point offset along the camera's own right vector.
    right = np.linalg.inv(vp._mv_matrix)[:3, 0]
    pts = np.array([pos, np.asarray(pos) + right * r])
    scr, ok = gizmo.project(mvp, pts, w, h)
    if not ok[0]:
        return float("nan"), float("nan"), 0.0
    rad = float(np.hypot(*(scr[1] - scr[0]))) if ok[1] else 20.0
    return float(scr[0][0]), float(scr[0][1]), rad


def _window_viewport(lesson: Lesson, width, height):
    """A real MainWindow, never shown, whose Viewport is detached so it can be
    grabbed at an exact size. The window's handlers still hold the same
    Viewport object, so every action they take lands in what we render."""
    from glyphviz_gl import main_window as mw
    win = mw.MainWindow()
    vp = win._viewport
    vp.setParent(None)
    vp.show_grid = lesson.show_grid
    vp.show_axes = lesson.show_axes
    vp.resize(width, height)
    vp.grabFramebuffer()            # create the GL context (see export_frame)
    lesson.win = win
    if lesson.scene_csv:
        # File > Open's own path: tags, media/, meshes/ and the Channels
        # companion files all load exactly as they do for a user.
        if not win._load_csv_path(str(lesson.scene_csv)):
            raise RuntimeError(win.statusBar().currentMessage())
        return vp
    win.nodes = list(lesson.nodes)
    vp.set_nodes(win.nodes)
    win._table.set_nodes(win.nodes)
    return vp


def render(lesson: Lesson, out_dir: Path, clips: list, width=1280, height=720,
           fps=30, stills: Sequence[float] = (), video=True,
           burn_captions=True) -> dict:
    """Render every frame, piping to ffmpeg. Returns paths written."""
    from glyphviz_core.csv_reader import save_node_csv

    out_dir.mkdir(parents=True, exist_ok=True)
    scene_dir = out_dir / "scene"
    scene_dir.mkdir(exist_ok=True)
    if lesson.prepare:
        lesson.prepare(lesson, scene_dir)
    if lesson.scene_csv:
        csv_path = Path(lesson.scene_csv)
    else:
        csv_path = scene_dir / f"{lesson.name}_gv_node.csv"
        save_node_csv(lesson.nodes, str(csv_path))

    if lesson.use_window:
        vp = _window_viewport(lesson, width, height)
    else:
        vp, _nodes, _t, _m = export_frame._build_viewport(
            str(csv_path), 1.0, lesson.show_grid, lesson.show_axes, True,
            None, width, height)
    vp.set_camera_smoothing(0.0)
    lesson.vp = vp
    # Keep the real grab size fixed for the whole render.
    vp.resize(width, height)

    timing = plan_timing(lesson, clips)
    total = timing[-1].start + timing[-1].dur
    n_frames = int(round(total * fps))

    track = CameraTrack(lesson, dict(
        az=vp._cam_azimuth, el=vp._cam_elevation, dist=vp._cam_distance,
        target=np.array(vp._cam_target, float), eye=None,
        target_src=list(vp._cam_target)))

    ov = Overlay(width, height)
    written = {"csv": csv_path}
    ff = None
    mp4 = out_dir / f"{lesson.name}.mp4"
    silent = out_dir / f"{lesson.name}.video.mp4"
    if video:
        ff = subprocess.Popen(
            [FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo",
             "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps),
             "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-pix_fmt", "yuv420p", str(silent)],
            stdin=subprocess.PIPE)

    still_frames = {int(round(t * fps)): t for t in stills}
    shot_i = -1
    keys = None
    current_scene = str(csv_path)
    fired = set()
    for f in range(n_frames):
        t = f / fps
        while shot_i + 1 < len(timing) and t >= timing[shot_i + 1].start:
            shot_i += 1
            shot = lesson.shots[shot_i]
            if shot.scene and shot.scene != current_scene:
                # A cut to another scene file, loaded as the app opens one.
                if lesson.win is not None:
                    lesson.win._load_csv_path(str(shot.scene))
                    lesson.ch_frame = 0.0
                else:
                    from glyphviz_core.csv_reader import load_node_csv
                    vp.set_nodes(load_node_csv(shot.scene))
                vp.selected_node_ids = set()
                current_scene = shot.scene
            if shot.select is not None:
                if lesson.win is not None:
                    lesson.win._table.select_by_ids(set(shot.select))
                else:
                    vp.selected_node_ids = set(shot.select)
            for k, v in shot.state.items():
                setattr(vp, k, v)
            if shot.ch_rate is not None:
                lesson.ch_rate = shot.ch_rate
            if shot.ch_frame is not None:
                lesson.show_ch_frame(shot.ch_frame)
            keys = track.shot_keys(shot)
            fired = set()
            vp.tags_touch()
        shot = lesson.shots[shot_i]
        tm = timing[shot_i]
        u = (t - tm.start) / tm.dur

        for i, (eu, changes) in enumerate(shot.events):
            if u >= eu and i not in fired:
                fired.add(i)
                if callable(changes):
                    changes(lesson)
                    continue
                for k, v in changes.items():
                    if k == "select":
                        vp.selected_node_ids = set(v)
                    else:
                        setattr(vp, k, v)
                vp.tags_touch()
        if shot.soundtrack and lesson.win is not None:
            lesson.show_ch_frame(soundtrack_frame(shot, tm, t))
        elif shot.ch_span and lesson.win is not None:
            lesson.show_ch_frame(span_frame(shot.ch_span, u))
        elif lesson.ch_rate and lesson.win is not None:
            # The animation clock runs on VIDEO time, not the app's QTimer, so
            # a frame that is slow to render can't make the playback stutter.
            lesson.show_ch_frame(lesson.ch_frame + lesson.ch_rate / fps)
        if shot.animate:
            shot.animate(lesson, u)
            vp.scene_invalidate()
            vp.tags_touch()

        cam = track.at(keys, u)
        vp.set_camera(azimuth=cam["az"], elevation=cam["el"],
                      distance=cam["dist"], target=tuple(cam["target"]))
        frame = grab_rgb(vp, width, height)

        img = Image.fromarray(frame).convert("RGBA")
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer, "RGBA")   # blend shapes; plain Draw replaces pixels
        for c in shot.callouts:
            a = _fade(u, c.start, c.end, 0, tm.dur)
            if a > 0:
                sx, sy, rp = _node_screen(vp, c.node, width, height)
                ov.callout(d, sx, sy, rp, c, a)
        if shot.gesture:
            ov.gesture(d, shot.gesture(u), _fade(u, 0.03, 0.97, 0, tm.dur))
        if shot.readout:
            ov.readout(d, shot.readout(lesson, u))
        ov.brand(d, lesson.title, shot.heading)
        cap_top = height - 36 * ov.s - 32 * ov.s * 3
        if shot.keycap:
            # A callable keycap changes key mid-shot: f(u) -> (key, note).
            key, note = (shot.keycap(u) if callable(shot.keycap)
                         else (shot.keycap, shot.keycap_note))
            ov.keycap(d, key, note, _fade(u, 0.02, 0.98, 0, tm.dur), cap_top)
        img = Image.alpha_composite(img, layer)

        # Full-screen cards, then captions, each on its own layer: PIL draws
        # REPLACE alpha within one layer, so a fading full-screen card drawn
        # into the same layer erased everything under it.
        if shot.title or shot.summary or shot.card:
            card = Image.new("RGBA", img.size, (0, 0, 0, 0))
            dc = ImageDraw.Draw(card, "RGBA")
            if shot.card:
                shot.card(ov, dc, u)
            if shot.title:
                # Title holds for the first ~35% then fades.
                a = 1.0 if u < 0.35 else max(0.0, 1 - (u - 0.35) / 0.15)
                ov.title(dc, shot.title, shot.heading or "", a)
            if shot.summary:
                ov.summary(dc, lesson.title, shot.summary, min(1.0, u / 0.12))
            img = Image.alpha_composite(img, card)
        # A soundtrack plays after the line is spoken; its caption clears
        # then, so the picture is unobstructed while the scene is heard.
        spoken = not (shot.soundtrack and t >= tm.sound_at)
        if burn_captions and spoken and not (shot.title and u < 0.5):
            cap = Image.new("RGBA", img.size, (0, 0, 0, 0))
            ov.caption(ImageDraw.Draw(cap, "RGBA"), shot.say)
            img = Image.alpha_composite(img, cap)
        img = img.convert("RGB")

        if f in still_frames:
            p = out_dir / f"{lesson.name}_t{still_frames[f]:05.1f}s.png"
            img.save(p)
            written.setdefault("stills", []).append(p)
        if ff:
            ff.stdin.write(img.tobytes())

    if ff:
        ff.stdin.close()
        if ff.wait() != 0:
            raise RuntimeError("ffmpeg failed encoding frames")

    if lesson.use_window and not lesson.scene_csv:
        # The scene the viewer should open is the one the lesson BUILT. (Never
        # for a filmed scene_csv: that path is a shipped example, and the
        # channel engine has left the last frame's values in its nodes.)
        save_node_csv(lesson.win.nodes, str(csv_path))
    written["timing"] = timing
    written["total"] = total
    written["silent"] = silent if video else None
    written["mp4"] = mp4
    return written
