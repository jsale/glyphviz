"""
kokoro_worker.py
================
Runs INSIDE the isolated Kokoro venv (%LOCALAPPDATA%\\GlyphViz\\kokoro\\venv),
never in the glyphviz env: kokoro-onnx pins onnxruntime/numpy versions the app
env must not be exposed to. narrate.py launches it as a subprocess, exactly as
it launches PowerShell for SAPI.

    <venv python> kokoro_worker.py job.json

job.json: {"model": ..., "voices": ..., "voice": "af_heart", "speed": 1.0,
           "lang": "en-us", "items": [{"text": ..., "path": ...}, ...]}
Writes each item as 16-bit mono WAV at Kokoro's native 24 kHz.
"""
import json
import sys

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro


def main():
    job = json.load(open(sys.argv[1], encoding="utf-8"))
    tts = Kokoro(job["model"], job["voices"])
    for item in job["items"]:
        samples, rate = tts.create(item["text"], voice=job["voice"],
                                   speed=float(job.get("speed", 1.0)),
                                   lang=job.get("lang", "en-us"))
        # Trim Kokoro's leading/trailing near-silence so shot timing measures
        # speech, not padding.
        loud = np.nonzero(np.abs(samples) > 0.01)[0]
        if len(loud):
            a = max(0, loud[0] - int(0.05 * rate))
            b = min(len(samples), loud[-1] + int(0.12 * rate))
            samples = samples[a:b]
        sf.write(item["path"], samples, rate, subtype="PCM_16")


if __name__ == "__main__":
    main()
