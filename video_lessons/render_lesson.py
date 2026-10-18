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
    # None = the lesson's own size (Lesson.size), else 1280x720.
    ap.add_argument("--width", type=int, default=None)
    ap.add_argument("--height", type=int, default=None)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--draft", action="store_true",
                    help="a quarter-size frame at 15 fps (640x360 for a "
                         "1280x720 lesson), for checking camera moves fast")
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
    ap.add_argument("--at", default=None,
                    help="with --stills-only: comma-separated times (seconds) to "
                         "save PNGs at, instead of two per shot")
    ap.add_argument("--no-tts", action="store_true",
                    help="silent; shots timed at a reading pace")
    ap.add_argument("--no-burn-captions", action="store_true",
                    help="leave captions to the .srt only")
    args = ap.parse_args()
    if args.draft:
        args.fps = 15

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
        if args.at:
            stills = [float(t) for t in args.at.split(",")]

        w, h = lesson.size or (1280, 720)
        if args.draft:
            w, h = w // 2, h // 2
        w, h = args.width or w, args.height or h
        res = lessonkit.render(
            lesson, out_dir, clips, w, h, args.fps,
            stills=sorted(stills), video=not args.stills_only,
            burn_captions=not args.no_burn_captions)

        srt = narrate.write_srt(lesson.shots, res["timing"],
                                out_dir / f"{lesson.name}.srt")
        if not args.stills_only:
            wav = narrate.build_track(res["timing"], res["total"],
                                      out_dir / f"{lesson.name}.narration.wav")
            bed = narrate.build_bed(lesson.shots, res["timing"], res["total"],
                                    out_dir / f"{lesson.name}.soundtrack.wav",
                                    lessonkit.FFMPEG)
            if bed is None:
                inputs, mix = ["-i", str(wav)], []
            else:
                # Narration (mono, centred) over the scene's own stereo audio.
                # normalize=0: amix would otherwise halve both.
                inputs = ["-i", str(wav), "-i", str(bed)]
                mix = ["-filter_complex",
                       "[1:a]aresample=48000,pan=stereo|c0=c0|c1=c0[n];"
                       "[n][2:a]amix=inputs=2:duration=first:normalize=0[a]",
                       "-map", "0:v", "-map", "[a]"]
            subprocess.run(
                [lessonkit.FFMPEG, "-y", "-loglevel", "error",
                 "-i", str(res["silent"]), *inputs, *mix,
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
