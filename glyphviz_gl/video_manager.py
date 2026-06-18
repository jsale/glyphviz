"""
VideoManager — plays video files as animated OpenGL textures.

Videos found in the texture folder alongside static images are each assigned a
texture_id continuing from where the image textures left off.  Qt Multimedia's
QMediaPlayer / QVideoSink decodes each video; frames are uploaded to the GPU on
every render tick via glTexSubImage2D.

Requires PySide6-QtMultimedia (bundled with standard PySide6 wheels on Windows).
If the module is absent, VideoManager.load_folder() returns 0 and prints a notice.
"""
from __future__ import annotations

from pathlib import Path

from OpenGL.GL import (
    glGenTextures, glDeleteTextures, glBindTexture, glTexImage2D, glTexSubImage2D,
    glTexParameteri,
    GL_TEXTURE_2D, GL_RGBA, GL_UNSIGNED_BYTE,
    GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE,
    GL_TEXTURE_MIN_FILTER, GL_TEXTURE_MAG_FILTER, GL_LINEAR,
)
from PySide6.QtGui import QImage

try:
    from PySide6.QtMultimedia import QMediaPlayer, QVideoSink, QVideoFrame
    from PySide6.QtCore import QUrl
    _QT_MULTIMEDIA_AVAILABLE = True
except ImportError:
    _QT_MULTIMEDIA_AVAILABLE = False

_VIDEO_EXTS = frozenset({'.mp4', '.avi', '.mov', '.mkv', '.webm', '.m4v', '.wmv', '.flv'})


def _qimage_to_bytes(img: QImage, size: int) -> bytes | None:
    """Same pixel-extraction logic as TextureManager, duplicated here to avoid
    a circular import."""
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
    try:
        import numpy as np
        return np.frombuffer(ptr, dtype=np.uint8, count=size).tobytes()
    except Exception:
        pass
    return None


class _VideoEntry:
    """One looping video mapped to one GL texture object."""

    def __init__(self, path: Path):
        self.gl_name: int = int(glGenTextures(1))
        self._initialized: bool = False
        self._pending_frame: QVideoFrame | None = None

        glBindTexture(GL_TEXTURE_2D, self.gl_name)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glBindTexture(GL_TEXTURE_2D, 0)

        self._sink = QVideoSink()
        self._sink.videoFrameChanged.connect(self._on_frame)

        self._player = QMediaPlayer()
        self._player.setVideoSink(self._sink)
        self._player.setSource(QUrl.fromLocalFile(str(path.resolve())))
        # Loop indefinitely: setLoops(-1) == QMediaPlayer::Infinite (Qt 6.1+).
        # Fall back to manual loop via mediaStatusChanged on older builds.
        try:
            self._player.setLoops(-1)
        except (AttributeError, TypeError):
            self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.play()

    # ------------------------------------------------------------------
    # Slots (all called on the main thread by Qt's event loop)

    def _on_frame(self, frame: QVideoFrame):
        self._pending_frame = frame

    def _on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._player.setPosition(0)
            self._player.play()

    # ------------------------------------------------------------------

    def tick(self):
        """Upload the pending frame to the GL texture.  Must be called from
        the GL thread (i.e. inside paintGL) while the context is current."""
        frame = self._pending_frame
        self._pending_frame = None
        if frame is None or not frame.isValid():
            return

        img = frame.toImage()
        if img.isNull():
            return
        img = img.convertToFormat(QImage.Format.Format_RGBA8888)
        img = img.mirrored(False, True)   # GL origin is bottom-left
        w, h = img.width(), img.height()
        data = _qimage_to_bytes(img, img.sizeInBytes())
        if data is None:
            return

        glBindTexture(GL_TEXTURE_2D, self.gl_name)
        if not self._initialized:
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
            self._initialized = True
        else:
            glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, w, h, GL_RGBA, GL_UNSIGNED_BYTE, data)
        glBindTexture(GL_TEXTURE_2D, 0)

    def release(self):
        """Stop playback and free the GL texture.  GL context must be current."""
        try:
            self._sink.videoFrameChanged.disconnect(self._on_frame)
        except RuntimeError:
            pass
        self._player.stop()
        if self.gl_name:
            glDeleteTextures(1, [self.gl_name])
            self.gl_name = 0


class VideoManager:
    """Loads video files from a folder, assigns sequential texture IDs continuing
    from the last static-image texture ID, and updates GL textures each tick."""

    def __init__(self):
        self._entries: dict[int, _VideoEntry] = {}   # texture_id → entry

    def load_folder(self, folder: Path, first_id: int) -> int:
        """Scan *folder* for video files and start playing each one.

        Assigns texture IDs starting at *first_id* (should be one past the last
        image texture ID so the two ID spaces don't collide).  Returns the number
        of videos loaded.  Must be called while the OpenGL context is current."""
        self._release()
        if not _QT_MULTIMEDIA_AVAILABLE:
            print("[VideoManager] PySide6.QtMultimedia not available — video textures disabled.")
            return 0
        if not folder.is_dir():
            return 0
        files = sorted(
            p for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in _VIDEO_EXTS
        )
        for idx, path in enumerate(files):
            try:
                entry = _VideoEntry(path)
                self._entries[first_id + idx] = entry
                print(f"[VideoManager] Playing '{path.name}' as texture_id {first_id + idx}")
            except Exception as exc:
                print(f"[VideoManager] Failed to load '{path.name}': {exc}")
        return len(self._entries)

    def tick(self):
        """Upload any pending decoded frames to their GL textures.
        Must be called from the GL thread (inside paintGL)."""
        for entry in self._entries.values():
            entry.tick()

    def get_gl_name(self, texture_id: int) -> int:
        """Return the GL texture object name for a video texture_id, or 0."""
        entry = self._entries.get(texture_id)
        return entry.gl_name if entry else 0

    def count(self) -> int:
        return len(self._entries)

    def has_videos(self) -> bool:
        return bool(self._entries)

    def release(self):
        """Stop all players and release all GL textures."""
        self._release()

    def _release(self):
        for entry in self._entries.values():
            entry.release()
        self._entries.clear()
