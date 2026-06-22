"""
TextureManager — loads image files from a directory into OpenGL texture objects,
assigning 1-based integer IDs that match the ANTz/GaiaViz texture_id convention.

Images are sorted alphanumerically; texture_id 1 is the first file, 2 the second,
etc.  Only the default folder (media/ next to the loaded CSV) is searched
automatically; an additional folder can be loaded via load_folder().

Multi-frame GIFs are detected automatically and played back using their own
embedded per-frame delays (see tick()), independent of the channel/track
animation system that drives texture_id switching between separate files.
"""
from __future__ import annotations

from pathlib import Path

from OpenGL.GL import *
from PySide6.QtGui import QImage, QImageReader

_IMAGE_EXTS = frozenset({
    '.png', '.jpg', '.jpeg', '.bmp', '.tga', '.gif', '.tif', '.tiff', '.webp',
})

# Guard against a malformed/zero frame delay spinning the loop too fast.
_MIN_GIF_FRAME_DELAY_MS = 20.0


class _AnimatedGifEntry:
    """One looping multi-frame GIF mapped to one GL texture object, advanced
    by its own embedded per-frame delays (independent of the channel/track
    animation system)."""

    def __init__(self, path: Path, gl_name: int, first_delay: float):
        self.gl_name = gl_name
        self._path = path
        self._reader = QImageReader(str(path))
        self._elapsed_ms = 0.0
        self._frame_delay_ms = max(first_delay, _MIN_GIF_FRAME_DELAY_MS)

    def advance(self, dt_ms: float) -> QImage | None:
        """Step playback forward by dt_ms.  Returns the new frame to upload,
        or None if no frame boundary was crossed this tick."""
        self._elapsed_ms += dt_ms
        frame: QImage | None = None
        # Catch up multiple frames if a paint was delayed (loop, don't recurse).
        while self._elapsed_ms >= self._frame_delay_ms:
            self._elapsed_ms -= self._frame_delay_ms
            img = self._reader.read()
            if img.isNull():
                # QImageReader can't rewind once it hits its end-of-sequence
                # error state (jumpToImage(0) fails there) — reopen instead.
                self._reader = QImageReader(str(self._path))
                img = self._reader.read()
                if img.isNull():
                    break
            frame = img
            self._frame_delay_ms = max(self._reader.nextImageDelay(), _MIN_GIF_FRAME_DELAY_MS)
        return frame


class TextureManager:
    def __init__(self):
        self._gl_names: dict[int, int] = {}   # 1-based texture_id → GL texture object name
        self._animated: dict[int, _AnimatedGifEntry] = {}   # texture_id → entry, subset of _gl_names
        self._folder: Path | None = None

    @property
    def folder(self) -> Path | None:
        return self._folder

    def load_folder(self, folder: Path) -> int:
        """Replace current textures with all images found in *folder*, sorted
        alphanumerically.  Returns the number of textures successfully loaded."""
        self._release()
        self._folder = Path(folder)
        if not self._folder.is_dir():
            return 0
        files = sorted(
            p for p in self._folder.iterdir()
            if p.is_file() and p.suffix.lower() in _IMAGE_EXTS
        )
        for idx, path in enumerate(files):
            texture_id = idx + 1   # 1-based
            gl_name, entry = self._upload(path)
            if gl_name:
                self._gl_names[texture_id] = gl_name
                if entry:
                    self._animated[texture_id] = entry
        return len(self._gl_names)

    def get_gl_name(self, texture_id: int) -> int:
        """Return the GL texture object name for a 1-based texture_id, or 0."""
        return self._gl_names.get(texture_id, 0)

    def has(self, texture_id: int) -> bool:
        return texture_id in self._gl_names

    def has_animated(self) -> bool:
        return bool(self._animated)

    def count(self) -> int:
        return len(self._gl_names)

    def tick(self, dt_ms: float):
        """Advance any playing animated GIFs and upload due frames.  Must be
        called from the GL thread (inside paintGL) while the context is current."""
        for entry in self._animated.values():
            frame = entry.advance(dt_ms)
            if frame is not None:
                self._upload_frame(entry.gl_name, frame, mipmapped=False)

    def release(self):
        """Delete all GL texture objects and reset state."""
        self._release()
        self._folder = None

    # --- private ----------------------------------------------------------

    def _release(self):
        if self._gl_names:
            names = list(self._gl_names.values())
            glDeleteTextures(len(names), names)
            self._gl_names.clear()
        self._animated.clear()

    def _upload(self, path: Path) -> tuple[int, _AnimatedGifEntry | None]:
        """Upload one image to the GPU.  Returns (gl_name, animated_entry);
        gl_name is 0 on failure, animated_entry is non-None only for
        multi-frame GIFs (the caller must keep ticking those)."""
        if path.suffix.lower() == '.gif':
            reader = QImageReader(str(path))
            if reader.imageCount() > 1:
                return self._upload_animated_gif(path, reader)

        try:
            img = QImage(str(path))
            if img.isNull():
                print(f"[TextureManager] Could not load image: {path.name}")
                return 0, None

            gl_name = self._create_texture(mipmapped=True)
            if not gl_name:
                return 0, None
            if not self._upload_frame(gl_name, img, mipmapped=True):
                glDeleteTextures(1, [gl_name])
                return 0, None
            return gl_name, None
        except Exception as exc:
            print(f"[TextureManager] Upload failed for {path.name}: {exc}")
            return 0, None

    def _upload_animated_gif(self, path: Path, reader: QImageReader) -> tuple[int, _AnimatedGifEntry | None]:
        """Read the first frame of an animated GIF and set up looping playback."""
        try:
            first = reader.read()
            if first.isNull():
                print(f"[TextureManager] Could not load image: {path.name}")
                return 0, None
            first_delay = reader.nextImageDelay()

            gl_name = self._create_texture(mipmapped=False)
            if not gl_name:
                return 0, None
            if not self._upload_frame(gl_name, first, mipmapped=False):
                glDeleteTextures(1, [gl_name])
                return 0, None
            return gl_name, _AnimatedGifEntry(path, gl_name, first_delay)
        except Exception as exc:
            print(f"[TextureManager] Animated GIF upload failed for {path.name}: {exc}")
            return 0, None

    @staticmethod
    def _create_texture(mipmapped: bool) -> int:
        """Allocate a GL texture object and set its sampling parameters.
        Caller still owns uploading pixel data via _upload_frame()."""
        gl_name = int(glGenTextures(1))
        glBindTexture(GL_TEXTURE_2D, gl_name)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
        if mipmapped:
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
        else:
            # Animated entries re-upload every due frame; skip mipmap regen cost.
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glBindTexture(GL_TEXTURE_2D, 0)
        return gl_name

    def _upload_frame(self, gl_name: int, img: QImage, mipmapped: bool) -> bool:
        """Upload one already-decoded frame's pixels into an existing GL
        texture object (full reallocation via glTexImage2D each call — frames
        are typically small enough that this is cheaper than the bookkeeping
        needed for glTexSubImage2D).  Returns True on success."""
        img = img.convertToFormat(QImage.Format.Format_RGBA8888)
        img = img.mirrored(False, True)   # GL origin is bottom-left
        w, h = img.width(), img.height()
        data = self._qimage_to_bytes(img, img.sizeInBytes())
        if data is None:
            print("[TextureManager] Could not extract pixel data from frame")
            return False

        glBindTexture(GL_TEXTURE_2D, gl_name)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
        if mipmapped:
            try:
                glGenerateMipmap(GL_TEXTURE_2D)
            except Exception:
                # OpenGL < 3.0 without EXT_framebuffer_object: fall back to GL_LINEAR
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glBindTexture(GL_TEXTURE_2D, 0)
        return True

    @staticmethod
    def _qimage_to_bytes(img: QImage, size: int) -> bytes | None:
        """Extract raw pixel bytes from a QImage.

        PySide6 >= 6.7 returns a memoryview from constBits(); older versions
        return a sip.voidptr.  Both support the buffer protocol so bytes() works
        on them directly.  Fall back to numpy if neither converts cleanly."""
        ptr = img.constBits()

        # memoryview (PySide6 >= 6.7) and sip.voidptr both implement the buffer
        # protocol, so bytes() should work on both.
        try:
            return bytes(ptr)
        except TypeError:
            pass

        # sip.voidptr with known size (older PySide6)
        try:
            ptr.setsize(size)
            return bytes(ptr)
        except (AttributeError, TypeError):
            pass

        # numpy frombuffer as final fallback
        try:
            import numpy as np
            return np.frombuffer(ptr, dtype=np.uint8, count=size).tobytes()
        except Exception:
            pass

        return None
