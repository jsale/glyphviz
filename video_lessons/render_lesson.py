#!/usr/bin/env python3
"""
render_lesson.py
================
Render one or more GlyphViz feature lessons to MP4 (+ .srt captions, + the
lesson's own scene CSV so a viewer can open exactly what they watched).

    python video_lessons/render_lesson.py tags
    python video_lessons/render_lesson.py tags camera_mode torus
    python video_lessons/render_lesson.py torus --draft          # 640x360 @15
    python video_lessons/render_lesson.py torus --stills-only    # PNGs, no MP4
    python video_lessons/render_lesson.py tags --voice "Microsoft David Desktop"
    python video_lessons/render_lesson.py tags --no-tts           # timing only

Each lesson is a module in video_lessons/lessons/ exposing build() -> Lesson.
Output lands in video_lessons/out/<lesson>/ (gitignored).

--stills-only is the look-before-you-ship step: it renders every frame (so
animation state is exact) but saves only a few sample PNGs, one per shot at
its midpoint, and skips encoding.
"""
from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lessonkit  # noqa: E402  (must precede any PySide6 import: DPI env)
import narrate  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Render GlyphViz lesson videos.")
    ap.add_argument("lessons", nargs="+", help="lesson module names")
    ap.add_argument("--out", default=str(HERE / "out"))
    # 720p by default: tag labels are drawn at the app's real point size, so
    # at 1080p they shrink to a third of the frame height they have in the app
    # window a viewer will compare them against.
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--draft", action="store_true",
                    help="640x360 at 15 fps, for checking camera moves fast")
    ap.add_argument("--stills-only", action="store_true",
                    help="save one PNG per shot (at its midpoint); no video")
    ap.add_argument("--engine", choices=("kokoro", "sapi"), default="kokoro",
                    help="kokoro (natural, default) or sapi (Windows built-in)")
    ap.add_argument("--voice", default=None,
                    help="override the lesson's voice: a Kokoro id such as "
                         "af_heart / am_michael / bf_emma, or with --engine "
                         "sapi a SAPI name (default Microsoft Zira Desktop)")
    ap.add_argument("--rate", type=float, default=None,
                    help="Kokoro speed multiplier (lesson default, usually "
                         "1.0) or SAPI rate -10..10 (default 1)")
    ap.add_argument("--no-tts", action="store_true",
                    help="silent; shots timed at a reading pace")
    ap.add_argument("--no-burn-captions", action="store_true",
                    help="leave captions to the .srt only")
    args = ap.parse_args()
    if args.draft:
        args.width, args.height, args.fps = 640, 360, 15

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841

    for name in args.lessons:
        t0 = time.time()
        lesson = importlib.import_module(f"lessons.{name}").build()
        out_dir = Path(args.out) / lesson.name
        if args.engine == "kokoro":
            voice = args.voice or lesson.voice
            rate = args.rate if args.rate is not None else lesson.speed
        else:
            voice = args.voice or "Microsoft Zira Desktop"
            rate = int(args.rate) if args.rate is not None else 1
        clips = narrate.synthesize(
            [s.say for s in lesson.shots], Path(args.out) / "_tts_cache",
            voice=voice, rate=rate,
            engine="none" if args.no_tts else args.engine)
        print(f"{lesson.name}: voice {args.engine}:{voice}")

        timing = lessonkit.plan_timing(lesson, clips)
        stills = [tm.start + tm.dur * 0.5 for tm in timing]
        if args.stills_only:
            stills += [tm.start + tm.dur * 0.9 for tm in timing]

        res = lessonkit.render(
            lesson, out_dir, clips, args.width, args.height, args.fps,
            stills=sorted(stills), video=not args.stills_only,
            burn_captions=not args.no_burn_captions)

        srt = narrate.write_srt(lesson.shots, res["timing"],
                                out_dir / f"{lesson.name}.srt")
        if not args.stills_only:
            wav = narrate.build_track(res["timing"], res["total"],
                                      out_dir / f"{lesson.name}.narration.wav")
            subprocess.run(
                [lessonkit.FFMPEG, "-y", "-loglevel", "error",
                 "-i", str(res["silent"]), "-i", str(wav),
                 "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                 "-movflags", "+faststart", str(res["mp4"])], check=True)
            res["silent"].unlink(missing_ok=True)
            print(f"{lesson.name}: {res['mp4']}  "
                  f"({res['total']:.1f} s, rendered in {time.time() - t0:.0f} s)")
        else:
            print(f"{lesson.name}: {len(res.get('stills', []))} stills in "
                  f"{out_dir} ({res['total']:.1f} s timeline)")
        print(f"  captions {srt}\n  scene    {res['csv']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
