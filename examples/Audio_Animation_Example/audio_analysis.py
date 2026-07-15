"""
audio_analysis.py — standalone copy for the Audio Animation Examples
======================================================================
Vendored from glyphviz_core/audio_analysis.py so this example folder can be
copied anywhere and run on its own, without a full GlyphViz repo checkout —
only numpy (+ Python's stdlib `wave` module) is required. Turns a WAV file
into a per-frame array of frequency-band energies in the exact shape the
GlyphViz Channels format (gv_ch-tracks.csv) expects.

If glyphviz_core/audio_analysis.py changes (bug fixes, new features), copy
the update here too — this file is not imported from the real package.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np


def load_wav_mono(path: str | Path) -> tuple[np.ndarray, int]:
    """Read a WAV file as float64 mono samples in [-1, 1].  Returns (samples, sample_rate)."""
    with wave.open(str(path), 'rb') as w:
        sr = w.getframerate()
        n = w.getnframes()
        channels = w.getnchannels()
        sample_width = w.getsampwidth()
        raw = w.readframes(n)
    if sample_width == 3:
        # 24-bit PCM — NumPy has no int24 dtype; sign-extend each 3-byte
        # little-endian sample to int32 by appending a sign byte (0x00 or 0xFF).
        n_samples = len(raw) // 3
        b = np.frombuffer(raw, dtype=np.uint8).reshape(n_samples, 3)
        sign = np.where(b[:, 2] & 0x80, np.uint8(0xFF), np.uint8(0x00)).reshape(-1, 1)
        x = np.hstack([b, sign]).view('<i4').flatten().astype(np.float64)
        x /= 2 ** 23
    else:
        dtype = {1: np.uint8, 2: np.int16, 4: np.int32}[sample_width]
        x = np.frombuffer(raw, dtype=dtype).astype(np.float64)
        if sample_width == 1:
            x = (x - 128.0) / 128.0   # uint8 is unsigned: 0..255 → -1..1
        else:
            x /= float(2 ** (sample_width * 8 - 1))
    if channels > 1:
        x = x.reshape(-1, channels).mean(axis=1)
    return x, sr


def band_edges(n_bands: int, f_lo: float, f_hi: float) -> np.ndarray:
    """n_bands + 1 log-spaced frequency edges from f_lo to f_hi."""
    return np.logspace(np.log10(f_lo), np.log10(f_hi), n_bands + 1)


def analyze(
    path: str | Path,
    n_bands: int = 64,
    fps: float = 30.0,
    f_lo: float = 20.0,
    f_hi: float = 16000.0,
    gate: float = 0.1,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Run a sliding-window FFT over the audio at *path* and bucket power into
    *n_bands* log-spaced frequency bands, one row per animation frame at *fps*.

    Each band is normalized toward its own peak across the whole clip (so
    quiet high-frequency bands are still visually legible, rather than always
    reading near-zero next to a much louder bass band) — but no band's
    normalizing reference is allowed to drop below *gate* fraction of the
    single loudest band in the whole clip.  Without this, a band whose only
    content is constant low-level FFT leakage from a neighboring tone (rather
    than a real signal) would get amplified up to a full-scale 1.0 right along
    with the genuinely dominant bands, since "normalize to own peak" can't
    distinguish "quiet but real" from "negligible but constant."

    Returns:
        tracks      — float64 array, shape (n_frames, n_bands), each column in [0, 1]
        band_freqs  — center frequency (Hz, geometric mean of each band's edges)
        duration_s  — clip length in seconds
    """
    samples, sr = load_wav_mono(path)
    f_hi = min(f_hi, sr / 2.0)

    hop = max(1, int(round(sr / fps)))
    win = max(hop * 2, 256)   # overlapping window: more frequency resolution than a bare hop would give
    n_frames = max(1, (len(samples) - win) // hop + 1)

    edges = band_edges(n_bands, f_lo, f_hi)
    band_freqs = np.sqrt(edges[:-1] * edges[1:])

    window = np.hanning(win)
    freqs = np.fft.rfftfreq(win, d=1.0 / sr)
    bin_band = np.clip(np.searchsorted(edges, freqs) - 1, 0, n_bands - 1)
    # Bins-per-band grows with frequency (log-spaced bands widen at the top),
    # so a band's *peak* bin — not its mean — is what tracks a single tone's
    # loudness independent of how many empty neighboring bins share its band;
    # averaging would dilute a high band's one real bin against several
    # near-zero ones, making identical tones read quieter the higher they are.
    band_bins = [np.where(bin_band == b)[0] for b in range(n_bands)]

    tracks = np.zeros((n_frames, n_bands), dtype=np.float64)
    for i in range(n_frames):
        start = i * hop
        chunk = samples[start:start + win]
        if len(chunk) < win:
            chunk = np.pad(chunk, (0, win - len(chunk)))
        spec = np.abs(np.fft.rfft(chunk * window))
        for b, bins in enumerate(band_bins):
            if len(bins):
                tracks[i, b] = spec[bins].max()

    peak = tracks.max(axis=0)
    floor = peak.max() * gate
    peak = np.maximum(peak, floor)
    peak[peak == 0] = 1.0
    tracks /= peak
    np.clip(tracks, 0.0, 1.0, out=tracks)

    duration_s = len(samples) / sr
    return tracks, band_freqs, duration_s
