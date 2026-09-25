"""
narrate.py
==========
Text-to-speech for lesson shots, plus the audio/caption assembly.

The default voice is Windows' built-in SAPI (System.Speech), reached through
PowerShell: nothing to install, works offline, and every machine this repo
runs on already has it. Its voices are serviceable rather than natural; the
engine is one function (`synthesize`), so a better one (edge-tts, Kokoro,
Piper, ElevenLabs) drops in without touching the renderer.

Clips are cached by a hash of (engine, voice, rate, text), so re-rendering a
lesson after changing only the camera or overlays re-uses every clip.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import wave
from pathlib import Path

RATE_HZ = 22050

_PS_SAPI = r"""
param([string]$JobFile)
Add-Type -AssemblyName System.Speech
$jobs = Get-Content -Raw -Encoding UTF8 $JobFile | ConvertFrom-Json
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice($jobs.voice)
$s.Rate = [int]$jobs.rate
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(22050,
    [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
    [System.Speech.AudioFormat.AudioChannel]::Mono)
foreach ($j in $jobs.items) {
    $s.SetOutputToWaveFile($j.path, $fmt)
    $s.Speak($j.text)
}
$s.SetOutputToNull()
$s.Dispose()
"""


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


KOKORO_HOME = Path(os.environ.get("LOCALAPPDATA", "")) / "GlyphViz" / "kokoro"
KOKORO_PY = KOKORO_HOME / "venv" / "Scripts" / "python.exe"


def _kokoro(todo, voice, speed):
    """Kokoro runs in its own venv (see kokoro_worker.py for why)."""
    if not KOKORO_PY.exists():
        raise RuntimeError(
            f"Kokoro is not set up: expected {KOKORO_PY}. See "
            "video_lessons/README.md > Voices.")
    with tempfile.TemporaryDirectory() as td:
        job = Path(td) / "job.json"
        job.write_text(json.dumps({
            "model": str(KOKORO_HOME / "kokoro-v1.0.onnx"),
            "voices": str(KOKORO_HOME / "voices-v1.0.bin"),
            "voice": voice, "speed": speed,
            "lang": "en-gb" if voice[:1] == "b" else "en-us",
            "items": todo}), encoding="utf-8")
        subprocess.run([str(KOKORO_PY), str(Path(__file__).with_name(
            "kokoro_worker.py")), str(job)], check=True)


def synthesize(lines: list[str], cache_dir: Path, voice="Microsoft Zira Desktop",
               rate=0, engine="sapi") -> list[tuple[Path | None, float]]:
    """One WAV per line -> [(path, seconds)]. engine='none' returns silent
    placeholders timed at a comfortable reading pace, for fast camera
    drafts. For engine='kokoro', `voice` is a Kokoro voice id (af_heart,
    am_michael, bf_emma, ...) and `rate` is its speed multiplier."""
    if engine == "none":
        return [(None, max(1.5, len(l.split()) / 2.6)) for l in lines]
    if engine not in ("sapi", "kokoro"):
        raise ValueError(f"unknown TTS engine {engine!r}")

    cache_dir.mkdir(parents=True, exist_ok=True)
    paths, todo = [], []
    for line in lines:
        key = hashlib.sha1(f"{engine}|{voice}|{rate}|{line}".encode()).hexdigest()[:16]
        p = cache_dir / f"{key}.wav"
        paths.append(p)
        if not p.exists():
            todo.append({"text": line, "path": str(p)})
    if todo and engine == "kokoro":
        _kokoro(todo, voice, rate)
    elif todo:
        with tempfile.TemporaryDirectory() as td:
            job = Path(td) / "job.json"
            script = Path(td) / "sapi.ps1"
            job.write_text(json.dumps({"voice": voice, "rate": rate,
                                       "items": todo}), encoding="utf-8")
            script.write_text(_PS_SAPI, encoding="utf-8")
            subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy",
                            "Bypass", "-File", str(script), str(job)],
                           check=True)
    return [(p, wav_seconds(p)) for p in paths]


def build_track(timing, total: float, out_path: Path, lead_in=0.35) -> Path:
    """Lay each shot's clip at (shot start + lead_in) on one mono WAV, at the
    clips' own sample rate (SAPI 22.05 kHz, Kokoro 24 kHz)."""
    rate = RATE_HZ
    for tm in timing:
        if tm.audio is not None:
            with wave.open(str(tm.audio), "rb") as w:
                rate = w.getframerate()
            break
    n = int(round(total * rate))
    buf = bytearray(n * 2)
    for tm in timing:
        if tm.audio is None:
            continue
        with wave.open(str(tm.audio), "rb") as w:
            if w.getframerate() != rate or w.getsampwidth() != 2 or w.getnchannels() != 1:
                raise ValueError(f"{tm.audio}: expected {rate} Hz 16-bit mono")
            data = w.readframes(w.getnframes())
        at = int(round((tm.start + lead_in) * rate)) * 2
        end = min(len(buf), at + len(data))
        buf[at:end] = data[: end - at]
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(buf))
    return out_path


def _ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def write_srt(shots, timing, out_path: Path, lead_in=0.35) -> Path:
    rows = []
    for i, (shot, tm) in enumerate(zip(shots, timing), 1):
        a = tm.start + lead_in
        b = a + tm.speech + 0.2
        rows.append(f"{i}\n{_ts(a)} --> {_ts(b)}\n{shot.say}\n")
    out_path.write_text("\n".join(rows), encoding="utf-8")
    return out_path
