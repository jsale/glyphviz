"""Helpers for lessons that film REAL app windows (the Glyph Composer, the
Hyperglyph Generator, the Properties panel) and drive them the way a user
would: a pointer that travels to a widget, a ring around it, and the widget's
own signal handlers firing when the click lands.

Nothing here fakes behaviour. Edits go through the dialog's actual widgets
(``spin.setValue``, ``combo.setCurrentIndex``, ``button.click``), file
choosers are answered with a path (so ``Load Template...`` runs the app's own
handler end to end), and painting sends real QMouseEvents to the Viewport.
"""
from __future__ import annotations

import contextlib
import math
from pathlib import Path

from lessonkit import AMBER, BG, CHALK, TEAL, Panel, Sec, as_u, ease, lerp


def _later(t, dt_s=0.04):
    """`t` (a fraction or a Sec) a hair later, so an action fires just after
    the pointer lands on its target."""
    return Sec(float(t) + dt_s) if isinstance(t, Sec) else float(t) + 0.003


# ------------------------------------------------------------------ placement

def place(L, widget, fx, fy, scale, title="", crop=None) -> Panel:
    """A Panel positioned in FRACTIONS of the frame, so a draft render at half
    size lines up exactly like the full one. (fx, fy) is where the window's
    content starts; `scale` is relative to a 1080-line frame."""
    h = L.vp.height()
    w = L.vp.width()
    return Panel(widget=widget, x=fx * w, y=fy * h, scale=scale * h / 1080.0,
                 title=title, crop=crop)


# ------------------------------------------------------------------ pointer

class Script:
    """A pointer script over one shot.

    steps: dicts with
        u      shot fraction at which the pointer ARRIVES and clicks
        w      callable(L) -> the widget being used   (with `pn`)
        pn     callable(L) -> the Panel the widget is shown in
        at     callable(L) -> (x, y) frame pixels, instead of w/pn
        rect   callable(L) -> (x0, y0, x1, y1) ring, instead of w/pn
        do     callable(L), fired as the click lands
        ring   draw a highlight ring around the widget (default True)
        click  draw the click ripple (default True)
    The pointer eases from the previous step's position, leaving no sooner
    than half a second after the previous click.
    """

    def __init__(self, steps, travel=0.75, ring_hold=1.6, start=None):
        self.steps = steps
        self.travel = travel
        self.ring_hold = ring_hold
        self.start = start               # callable(L) -> (x, y), or None
        self._pts = {}

    # -- events the shot must also carry
    def events(self):
        return [(_later(st["u"]), st["do"]) for st in self.steps if st.get("do")]

    # -- geometry
    def _target(self, L, st):
        if "at" in st:
            return st["at"](L)
        return st["pn"](L).point(st["w"](L))

    def _ring(self, L, st):
        if "rect" in st:
            return st["rect"](L)
        if "w" in st and st.get("ring", True):
            return st["pn"](L).rect(st["w"](L))
        return None

    def cursor(self, L, u):
        dur = max(L.cur_dur, 1e-3)
        tv = self.travel / dur
        steps = self.steps
        arrive = [as_u(st["u"], dur) for st in steps]
        departs = []
        for i in range(len(steps)):
            floor = (arrive[i - 1] + 0.5 / dur) if i else 0.0
            departs.append(max(arrive[i] - tv, floor))
        if u < departs[0]:
            return None
        i = max(k for k in range(len(steps)) if departs[k] <= u)
        st = steps[i]
        ua = arrive[i]
        try:
            tgt = self._target(L, st)
        except RuntimeError:             # the widget was rebuilt under us
            tgt = self._pts.get(i)
            if tgt is None:
                return None
        if u < ua:
            if i:
                a = self._pts.get(i - 1, tgt)
            else:
                a = self.start(L) if self.start else tgt
            t = ease((u - departs[i]) / max(ua - departs[i], 1e-6))
            pos = (lerp(a[0], tgt[0], t), lerp(a[1], tgt[1], t))
            return dict(x=pos[0], y=pos[1], alpha=min(1.0, 3 * (u - departs[0]) / tv + 0.2))
        self._pts[i] = tgt
        since = (u - ua) * dur
        out = dict(x=tgt[0], y=tgt[1])
        if st.get("click", True):
            out["click"] = since / 0.55
        if since < self.ring_hold:
            try:
                ring = self._ring(L, st)
            except RuntimeError:
                ring = None
            if ring:
                out["ring"] = ring
                out["alpha"] = min(1.0, (self.ring_hold - since) / 0.35)
        return out


def chain(*cursors):
    """Combine pointer sources: the first one with something to show wins."""
    def f(L, u):
        for c in cursors:
            r = c(L, u)
            if r:
                return r
        return None
    return f


# ------------------------------------------------------------------ painting

def _mouse(L, kind, fx, fy):
    """A real mouse event into the filmed Viewport, at a frame fraction."""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    vp = L.vp
    pos = QPointF(fx * vp.width(), fy * vp.height())
    if kind == "press":
        ev = QMouseEvent(QEvent.Type.MouseButtonPress, pos, Qt.MouseButton.LeftButton,
                         Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        vp.mousePressEvent(ev)
    elif kind == "move":
        ev = QMouseEvent(QEvent.Type.MouseMove, pos, Qt.MouseButton.NoButton,
                         Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        vp.mouseMoveEvent(ev)
    else:
        ev = QMouseEvent(QEvent.Type.MouseButtonRelease, pos, Qt.MouseButton.LeftButton,
                         Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        vp.mouseReleaseEvent(ev)


class Stroke:
    """One press-drag-release across the 3D view, between shot fractions
    u0..u1, along `pts` (frame fractions). Press and release are real mouse
    events; the moves in between are what Draw Mode turns into stamps."""

    def __init__(self, pts, u0, u1, moves=48):
        # pts: [(fx, fy), ...] or a callable(L) -> that list (see `ground`).
        self.pts, self.u0, self.u1, self.moves = pts, u0, u1, moves
        self._L = None

    def _path(self):
        return self.pts(self._L) if callable(self.pts) else self.pts

    def at(self, t):
        """Position at path fraction t (0..1), by arc length."""
        pts = self._path()
        seg = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
        total = sum(seg) or 1.0
        d = min(max(t, 0.0), 1.0) * total
        for i, s in enumerate(seg):
            if d <= s or i == len(seg) - 1:
                a, b = pts[i], pts[i + 1]
                k = min(d / s, 1.0) if s else 0.0
                return (lerp(a[0], b[0], k), lerp(a[1], b[1], k))
            d -= s
        return pts[-1]

    def _at(self, L, t):
        self._L = L
        return self.at(t)

    def events(self):
        ev = [(self.u0, lambda L: _mouse(L, "press", *self._at(L, 0.0)))]
        a, b = float(self.u0), float(self.u1)
        sec = isinstance(self.u0, Sec)
        for i in range(1, self.moves + 1):
            t = i / self.moves
            u = lerp(a, b, t)
            ev.append((Sec(u) if sec else u,
                       lambda L, t=t: _mouse(L, "move", *self._at(L, t))))
        ev.append((_later(self.u1), lambda L: _mouse(L, "release", *self._at(L, 1.0))))
        return ev

    def cursor(self, L, u):
        self._L = L
        dur = max(L.cur_dur, 1e-3)
        u0, u1 = as_u(self.u0, dur), as_u(self.u1, dur)
        if not (u0 - 0.5 / dur <= u <= u1 + 0.8 / dur):
            return None
        t = (u - u0) / max(u1 - u0, 1e-6)
        x, y = self.at(t)
        w, h = L.vp.width(), L.vp.height()
        out = dict(x=x * w, y=y * h)
        if 0 <= u - u0 <= 0.5 / dur:
            out["click"] = (u - u0) * dur / 0.5
        return out


def ground(points, z=0.0):
    """A Stroke path given in WORLD (x, y) on the ground plane z, projected
    through the camera the viewport last drew with. Lets a stroke be authored
    where the glyphs should land (and kept on the World Grid) instead of by
    screen guesses."""
    def f(L):
        import numpy as np
        from glyphviz_core import gizmo
        vp = L.vp
        mvp = vp._proj_matrix @ vp._mv_matrix
        pts = np.array([(x, y, z) for x, y in points], float)
        scr, _ok = gizmo.project(mvp, pts, vp.width(), vp.height())
        return [(float(s[0]) / vp.width(), float(s[1]) / vp.height()) for s in scr]
    return f


def clicks(*pts, gap=0.06):
    """Single clicks (press + release) at frame fractions, from shot fraction
    `at` onward: [(u, (fx, fy)), ...] -> events."""
    ev = []
    for u, p in pts:
        ev.append((u, lambda L, p=p: _mouse(L, "press", *p)))
        ev.append((u + gap / 2, lambda L, p=p: _mouse(L, "release", *p)))
    return ev


# ------------------------------------------------------------------ dialogs

@contextlib.contextmanager
def answering(open_path=None, save_path=None, color=None):
    """While active, file/colour choosers answer immediately, so the app's own
    ``Load Template...`` / ``Save Recipe...`` / colour-swatch handler runs end
    to end without a modal window nobody can click."""
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QColorDialog, QFileDialog
    saved = (QFileDialog.getOpenFileName, QFileDialog.getSaveFileName,
             QColorDialog.getColor)
    if open_path is not None:
        QFileDialog.getOpenFileName = staticmethod(
            lambda *a, **k: (str(open_path), ""))
    if save_path is not None:
        QFileDialog.getSaveFileName = staticmethod(
            lambda *a, **k: (str(save_path), ""))
    if color is not None:
        QColorDialog.getColor = staticmethod(lambda *a, **k: QColor(*color))
    try:
        yield
    finally:
        (QFileDialog.getOpenFileName, QFileDialog.getSaveFileName,
         QColorDialog.getColor) = saved


def set_combo(combo, data):
    combo.setCurrentIndex(combo.findData(data))


# ------------------------------------------------------------------ cards

def file_card(title, folder, files, picked, t0=0.0, t1=1.0):
    """A pictured file chooser for Shot.card: `files` listed, `picked` marked.
    Stands in for the OS dialog, which a headless render never shows."""
    def draw(ov, d, u):
        a = min(1.0, (u - t0) / 0.05, (t1 - u) / 0.05)
        if a <= 0:
            return
        s = ov.s
        w, h = 760 * s, (150 + 40 * len(files)) * s
        x0, y0 = (ov.w - w) / 2 - 120 * s, ov.h * 0.30
        d.rectangle((0, 0, ov.w, ov.h), fill=(*BG, int(110 * a)))
        ov._box(d, (x0, y0, x0 + w, y0 + h), fill=(246, 247, 251, int(255 * a)),
                outline=(120, 124, 150, int(255 * a)))
        d.rounded_rectangle((x0, y0, x0 + w, y0 + 40 * s), radius=int(10 * s),
                            fill=(36, 38, 54, int(255 * a)))
        d.text((x0 + 16 * s, y0 + 7 * s), title, font=ov.f_note,
               fill=(*CHALK, int(255 * a)))
        d.text((x0 + 18 * s, y0 + 52 * s), folder, font=ov.f_note,
               fill=(70, 74, 100, int(255 * a)))
        for i, f in enumerate(files):
            y = y0 + (88 + 40 * i) * s
            if f == picked:
                d.rectangle((x0 + 10 * s, y - 4 * s, x0 + w - 10 * s, y + 32 * s),
                            fill=(190, 215, 255, int(255 * a)))
            d.text((x0 + 22 * s, y), f, font=ov.f_cap,
                   fill=(20, 22, 40, int(255 * a)))
    return draw


def image_card(path, title, caption, t0=0.0, t1=1.0, width=0.62):
    """A screenshot on a dark card (Shot.card), e.g. the Tree Designer."""
    from PIL import Image
    cache = {}

    def draw(ov, d, u):
        a = min(1.0, (u - t0) / 0.05, (t1 - u) / 0.05)
        if a <= 0:
            return
        s = ov.s
        if "im" not in cache:
            cache["im"] = Image.open(path).convert("RGB")
        im = cache["im"]
        tw = int(ov.w * width)
        th = int(im.height * tw / im.width)
        rs = im.resize((tw, th), Image.LANCZOS)
        d.rectangle((0, 0, ov.w, ov.h), fill=(*BG, int(225 * a)))
        x0, y0 = (ov.w - tw) // 2, int(ov.h * 0.17)
        d.text((x0, y0 - 52 * s), title, font=ov.f_head, fill=(*TEAL, int(255 * a)))
        d.text((x0, y0 - 28 * s), caption, font=ov.f_note,
               fill=(180, 186, 210, int(235 * a)))
        layer = rs.convert("RGBA")
        layer.putalpha(int(255 * a))
        d.pil_image.paste(layer, (x0, y0), layer)     # set by lessonkit.render
        d.rectangle((x0, y0, x0 + tw, y0 + th), outline=(*AMBER, int(255 * a)), width=2)
    return draw
