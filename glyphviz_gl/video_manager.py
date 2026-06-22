"""
VideoManager — plays video files as animated OpenGL textures.

Videos found in the texture folder alongside static images are each assigned a
texture_id continuing from where the image textures left off.  Qt Multimedia's
QMediaPlayer / QVideoSink decodes each video; frames are uploaded to the GPU on
every render tick via glTexSubImage2D.

Each video's audio track plays through its own QAudioOutput, so by default all
loaded videos are heard at once (mixed by the OS, same as multiple browser tabs
playing video).  Call set_solo() to mute every track but one, or pass None to
return to the "play all" default.

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
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink, QVideoFrame
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
        self.name: str = path.name
        self.gl_name: int = int(glGenTextures(1))
        self._initialized: bool = False
        self._active: bool = False
        self._pending_frame: QVideoFrame | None = None

        glBindTexture(GL_TEXTURE_2D, self.gl_name)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glBindTexture(GL_TEXTURE_2D, 0)

        self._sink = QVideoSink()
        self._sink.videoFrameChanged.connect(self._on_frame)

        self._audio_output = QAudioOutput()

        self._player = QMediaPlayer()
        self._player.setVideoSink(self._sink)
        self._player.setAudioOutput(self._audio_output)
        self._player.setSource(QUrl.fromLocalFile(str(path.resolve())))
        # Loop indefinitely: setLoops(-1) == QMediaPlayer::Infinite (Qt 6.1+).
        # Fall back to manual loop via mediaStatusChanged on older builds.
        try:
            self._player.setLoops(-1)
        except (AttributeError, TypeError):
            self._player.mediaStatusChanged.connect(self._on_media_status)
        # Playback (and its audio) doesn't start on load — only once a node
        # actually draws this texture, via ensure_playing().  It pauses again
        # via ensure_stopped() once no node draws it anymore (e.g. the node
        # was switched to a different texture).

    # ------------------------------------------------------------------
    # Slots (all called on the main thread by Qt's event loop)

    def _on_frame(self, frame: QVideoFrame):
        self._pending_frame = frame

    def ensure_playing(self):
        """Start (or resume) playback because a node is drawing this texture
        this frame."""
        if not self._active:
            self._active = True
            self._player.play()

    def ensure_stopped(self):
        """Pause playback because no node drew this texture this frame.
        Keeps position so it resumes where it left off if reassigned later."""
        if self._active:
            self._active = False
            self._player.pause()

    def _on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._player.setPosition(0)
            self._player.play()

    # ------------------------------------------------------------------

    def set_muted(self, muted: bool):
        self._audio_output.setMuted(muted)

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
        self._solo_id: int | None = None   # None == all audio tracks play
        self._active_ids: set[int] = set()   # texture_ids drawn on a node this frame

    def load_folder(self, folder: Path, first_id: int) -> int:
        """Scan *folder* for video files and start playing each one.

        Assigns texture IDs starting at *first_id* (should be one past the last
        image texture ID so the two ID spaces don't collide).  Returns the number
        of videos loaded.  Must be called while the OpenGL context is current."""
        self._release()
        self._solo_id = None
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
                print(f"[VideoManager] Loaded '{path.name}' as texture_id {first_id + idx}")
            except Exception as exc:
                print(f"[VideoManager] Failed to load '{path.name}': {exc}")
        return len(self._entries)

    def tick(self):
        """Upload any pending decoded frames to their GL textures, and reset
        the per-frame draw-tracking used by finalize_frame().  Must be called
        from the GL thread (inside paintGL), before nodes are drawn."""
        self._active_ids = set()
        for entry in self._entries.values():
            entry.tick()

    def get_gl_name(self, texture_id: int) -> int:
        """Return the GL texture object name for a video texture_id, or 0.

        Called once per frame for each node actually drawn with this texture,
        so it doubles as the "this video is now visible" signal that starts
        playback (see _VideoEntry.ensure_playing)."""
        entry = self._entries.get(texture_id)
        if entry is None:
            return 0
        self._active_ids.add(texture_id)
        entry.ensure_playing()
        return entry.gl_name

    def finalize_frame(self):
        """Pause any video no node drew this frame (e.g. its node was switched
        to a different texture).  Call once per frame after all nodes are drawn."""
        for texture_id, entry in self._entries.items():
            if texture_id not in self._active_ids:
                entry.ensure_stopped()

    def count(self) -> int:
        return len(self._entries)

    def has_videos(self) -> bool:
        return bool(self._entries)

    def list_tracks(self) -> list[tuple[int, str]]:
        """Return (texture_id, filename) for each loaded video, in load order."""
        return [(tid, entry.name) for tid, entry in sorted(self._entries.items())]

    def set_solo(self, texture_id: int | None):
        """Mute every video's audio except *texture_id*.  Pass None to unmute
        all of them (the default "play every track" behavior)."""
        self._solo_id = texture_id
        for tid, entry in self._entries.items():
            entry.set_muted(texture_id is not None and tid != texture_id)

    def release(self):
        """Stop all players and release all GL textures."""
        self._release()

    def _release(self):
        for entry in self._entries.values():
            entry.release()
        self._entries.clear()
