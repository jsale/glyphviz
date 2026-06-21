"""Camera-facing text billboard for VR — renders a node's tag label to a
QImage/QPainter texture and draws it as a screen-facing quad, so the
selected node's text is visible in-headset without a 3D font-glyph pipeline.

Single-entry texture cache: re-renders only when the label text changes
(i.e. on selection change), since this is meant for one live label at a
time, not a per-frame-updating panel.
"""
import numpy as np

from .transforms import gl_col_major

_FONT_PX = 64
_PADDING = 10
_LABEL_HEIGHT_M = 0.6  # real-world quad height, independent of scene/diorama scale

_cache_text: str | None = None
_cache_gl_name: int = 0
_cache_aspect: float = 1.0


def _ensure_qt_app():
    from PySide6.QtGui import QGuiApplication
    if QGuiApplication.instance() is None:
        QGuiApplication([])


def _render_text_rgba(text: str):
    from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter

    _ensure_qt_app()
    font = QFont("Arial")
    font.setPixelSize(_FONT_PX)
    fm = QFontMetrics(font)
    text_w = max(1, fm.horizontalAdvance(text))
    text_h = fm.height()
    w, h = text_w + _PADDING * 2, text_h + _PADDING * 2

    img = QImage(w, h, QImage.Format.Format_RGBA8888)
    img.fill(QColor(0, 0, 0, 0))
    painter = QPainter(img)
    painter.setFont(font)
    baseline = _PADDING + fm.ascent()
    painter.setPen(QColor(0, 0, 0, 220))
    painter.drawText(_PADDING + 2, baseline + 2, text)
    painter.setPen(QColor(255, 255, 200, 255))
    painter.drawText(_PADDING, baseline, text)
    painter.end()

    img = img.mirrored(False, True)  # GL texture origin is bottom-left
    return img, w, h


def _qimage_to_bytes(img, size: int) -> bytes:
    """Mirrors glyphviz_gl.texture_manager.TextureManager._qimage_to_bytes —
    duplicated rather than imported so glyphviz_xr doesn't pick up a
    dependency on the Qt-widget-heavy desktop renderer module for this."""
    ptr = img.constBits()
    try:
        return bytes(ptr)
    except TypeError:
        pass
    try:
        ptr.setsize(size)
        return bytes(ptr)
    except (AttributeError, TypeError):
        pass
    return np.frombuffer(ptr, dtype=np.uint8, count=size).tobytes()


def _upload(text: str) -> tuple[int, float]:
    """Render *text* and upload it as a GL texture, returning (gl_name, aspect)."""
    from OpenGL.GL import (
        glBindTexture, glDeleteTextures, glGenTextures, glTexImage2D,
        glTexParameteri, GL_LINEAR, GL_REPEAT, GL_RGBA, GL_TEXTURE_2D,
        GL_TEXTURE_MAG_FILTER, GL_TEXTURE_MIN_FILTER, GL_TEXTURE_WRAP_S,
        GL_TEXTURE_WRAP_T, GL_UNSIGNED_BYTE,
    )
    global _cache_gl_name
    img, w, h = _render_text_rgba(text)
    img = img.convertToFormat(img.Format.Format_RGBA8888)
    data = _qimage_to_bytes(img, img.sizeInBytes())

    if _cache_gl_name:
        glDeleteTextures(1, [_cache_gl_name])
    gl_name = int(glGenTextures(1))
    glBindTexture(GL_TEXTURE_2D, gl_name)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
    glBindTexture(GL_TEXTURE_2D, 0)
    return gl_name, w / h


def draw_label(text: str, anchor_offset: tuple[float, float, float],
                height_m: float = _LABEL_HEIGHT_M):
    """Draw *text* as a camera-facing billboard, bottom-anchored at the
    current GL_MODELVIEW origin plus *anchor_offset*.

    Must be called with GL_MODELVIEW already translated to the node's world
    position (see render.draw_scene) — *anchor_offset* is applied on top of
    that, still in the pre-billboard (parent) frame, typically to lift the
    label clear of the node's own geometry.
    """
    global _cache_text, _cache_gl_name, _cache_aspect
    if not text:
        return
    from OpenGL.GL import (
        glBindTexture, glBegin, glColor4f, glDisable, glEnable, glEnd,
        glGetFloatv, glLoadMatrixf, glPopMatrix, glPushMatrix,
        glTexCoord2f, glTranslatef, glVertex3f, GL_LIGHTING,
        GL_MODELVIEW_MATRIX, GL_QUADS, GL_TEXTURE_2D,
    )

    if text != _cache_text:
        _cache_gl_name, _cache_aspect = _upload(text)
        _cache_text = text

    glPushMatrix()
    glTranslatef(*anchor_offset)
    # Cancel rotation/scale, keeping only the eye-space translation, so the
    # quad always faces the camera regardless of any parent rotation chain
    # — the standard "spherical billboard" trick. Same reshape(4,4).T
    # convention glyphviz_gl.viewport uses to read GL_MODELVIEW_MATRIX.
    m = np.array(glGetFloatv(GL_MODELVIEW_MATRIX), dtype=np.float32).reshape(4, 4).T
    m[:3, :3] = np.eye(3, dtype=np.float32)
    glLoadMatrixf(gl_col_major(m))

    w = height_m * _cache_aspect
    glDisable(GL_LIGHTING)
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, _cache_gl_name)
    glColor4f(1.0, 1.0, 1.0, 1.0)
    glBegin(GL_QUADS)
    glTexCoord2f(0.0, 0.0); glVertex3f(-w / 2, 0.0, 0.0)
    glTexCoord2f(1.0, 0.0); glVertex3f(w / 2, 0.0, 0.0)
    glTexCoord2f(1.0, 1.0); glVertex3f(w / 2, height_m, 0.0)
    glTexCoord2f(0.0, 1.0); glVertex3f(-w / 2, height_m, 0.0)
    glEnd()
    glBindTexture(GL_TEXTURE_2D, 0)
    glDisable(GL_TEXTURE_2D)
    glEnable(GL_LIGHTING)
    glPopMatrix()
