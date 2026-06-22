"""
AudioPlayer — plays a single audio file (no video) for Channels/synesthesia
playback, e.g. the WAV a Channels animation's FFT data was analyzed from.

Exists separately from VideoManager's per-video QAudioOutput because this one
drives the Channels frame index from real playback position (see
MainWindow._ch_tick), rather than just being heard alongside a texture.
"""
from __future__ import annotations

from pathlib import Path

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtCore import QUrl
    _QT_MULTIMEDIA_AVAILABLE = True
except ImportError:
    _QT_MULTIMEDIA_AVAILABLE = False


class AudioPlayer:
    """Thin QMediaPlayer/QAudioOutput wrapper for a single audio-only file."""

    def __init__(self):
        self._player = None
        self._audio_output = None
        if _QT_MULTIMEDIA_AVAILABLE:
            self._audio_output = QAudioOutput()
            self._player = QMediaPlayer()
            self._player.setAudioOutput(self._audio_output)

    @property
    def is_loaded(self) -> bool:
        return self._player is not None and bool(self._player.source().toString())

    def load(self, path: Path) -> bool:
        if self._player is None:
            return False
        self._player.setSource(QUrl.fromLocalFile(str(Path(path).resolve())))
        return True

    def unload(self):
        if self._player is not None:
            self._player.stop()
            self._player.setSource(QUrl())

    def play(self, loop: bool):
        if self._player is None:
            return
        try:
            self._player.setLoops(-1 if loop else 1)
        except (AttributeError, TypeError):
            pass
        self._player.play()

    def pause(self):
        if self._player is not None:
            self._player.pause()

    def stop(self):
        if self._player is not None:
            self._player.stop()
            self._player.setPosition(0)

    def has_ended(self) -> bool:
        if self._player is None:
            return True
        return self._player.playbackState() == QMediaPlayer.PlaybackState.StoppedState

    def position_ms(self) -> int:
        return self._player.position() if self._player is not None else 0

    def seek_ms(self, ms: int):
        if self._player is not None:
            self._player.setPosition(ms)

    def duration_ms(self) -> int:
        return self._player.duration() if self._player is not None else 0
