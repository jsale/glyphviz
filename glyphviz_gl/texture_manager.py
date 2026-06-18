"""
TextureManager — loads image files from a directory into OpenGL texture objects,
assigning 1-based integer IDs that match the ANTz/GaiaViz texture_id convention.

Images are sorted alphanumerically; texture_id 1 is the first file, 2 the second,
etc.  Only the default folder (usr/images/ relative to the loaded CSV) is searched
automatically; an additional folder can be loaded via load_folder().
"""
from __future__ import annotations

from pathlib import Path

from OpenGL.GL import *
from PySide6.QtGui import QImage

_IMAGE_EXTS = frozenset({
    '.png', '.jpg', '.jpeg', '.bmp', '.tga', '.gif', '.tif', '.tiff', '.webp',
})


class TextureManager:
    def __init__(self):
        self._gl_names: dict[int, int] = {}   # 1-based texture_id → GL texture object name
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
            gl_name = self._upload(path)
            if gl_name:
                self._gl_names[idx + 1] = gl_name   # 1-based
        return len(self._gl_names)

    def get_gl_name(self, texture_id: int) -> int:
        """Return the GL texture object name for a 1-based texture_id, or 0."""
        return self._gl_names.get(texture_id, 0)

    def has(self, texture_id: int) -> bool:
        return texture_id in self._gl_names

    def count(self) -> int:
        return len(self._gl_names)

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

    def _upload(self, path: Path) -> int:
        """Upload one image to the GPU.  Returns the GL texture object name, or 0 on failure."""
        try:
            img = QImage(str(path))
            if img.isNull():
                print(f"[TextureManager] Could not load image: {path.name}")
                return 0

            img = img.convertToFormat(QImage.Format.Format_RGBA8888)
            img = img.mirrored(False, True)   # GL origin is bottom-left (positional: horizontal, vertical)
            w, h = img.width(), img.height()
            size = img.sizeInBytes()

            data = self._qimage_to_bytes(img, size)
            if data is None:
                print(f"[TextureManager] Could not extract pixel data from: {path.name}")
                return 0

            gl_name = int(glGenTextures(1))
            glBindTexture(GL_TEXTURE_2D, gl_name)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0,
                         GL_RGBA, GL_UNSIGNED_BYTE, data)
            try:
                glGenerateMipmap(GL_TEXTURE_2D)
            except Exception:
                # OpenGL < 3.0 without EXT_framebuffer_object: fall back to GL_LINEAR
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glBindTexture(GL_TEXTURE_2D, 0)
            return gl_name
        except Exception as exc:
            print(f"[TextureManager] Upload failed for {path.name}: {exc}")
            return 0

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
