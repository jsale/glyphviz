#!/usr/bin/env python3
"""
capture_home_shots.py
======================
Generate a handful of extra, tighter-framed screenshots for the docs home
page carousel (glyphviz-docs/docs/index.md) — reuses the same Capture
helper as capture_example_shots.py, but with per-shot zoom/orbit/channel-
frame overrides so a couple of scenes read better as small hero images than
their Examples Gallery auto-framed shot does (most gallery shots are reused
as-is for the carousel; this script only covers the ones that needed a
different framing).

Usage:
    python tools/capture_home_shots.py
    python tools/capture_home_shots.py --only vehicle-raw-auction-field-close
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from PySide6.QtWidgets import QApplication

from capture_tour_shots import Capture, pump   # noqa: E402  (same folder)

OUT_DIR = REPO_ROOT / "glyphviz-docs" / "docs" / "assets" / "home"
EX = REPO_ROOT / "examples"

# Each entry: slug, scene folder, explicit file or None, zoom multiplier
# (applied to the auto-fit camera distance), channel frame or None, and an
# optional (azimuth_delta, elevation, target_offset_xyz) orbit override —
# None means keep the auto-fit orbit.
MANIFEST = [
    # The auction field's glyph legend stands well clear of the data (out at
    # x = -395), so the auto-fit bbox is nearly twice the size of the field
    # and centres on empty space between the two. Both numbers below are
    # corrections for that: the zoom is the old 0.12 rescaled to the larger
    # fitted distance, and the target offset walks the aim from the bbox
    # centre (19.5, 93, 77) back onto the field itself. Re-derive both if the
    # scene's extents change again — tools/export_frame.py --report prints them.
    ("vehicle-raw-auction-field-close",
     EX / "Vehicle_Sales_Example" / "Raw_Auction_Field", None, 0.068, None,
     (90.0, 18.0, (185.0, 10.0, -45.0))),
    ("audio-cat-scan-synesthesia-close",
     EX / "Audio_Animation_Example" / "Cat_Scan_Synesthesia_Example", None, 0.6, None, None),
    ("century-swarm-close", EX / "Century_Swarm_Example", None, 0.7, None, None),
    # SD_Seismicity_Example's hypocenters are born invisible and light up as
    # Channels plays through 66 years — frame 0 (the gallery shot) is mostly
    # empty. The final second of the loop relights the whole catalog at once
    # (see examples/SD_Seismicity_Example/README.md), which is the one frame
    # that actually shows the full color-ramped seismicity cloud. The orbit
    # override frames the amber zoom-callout frustum rising into the glowing
    # earthquake cloud, with the SD aerial plate still visible for context —
    # picked over a tighter crop (loses the map) and the plain auto-fit
    # (frustum reads as clutter, dots too small).
    ("sd-seismicity", EX / "SD_Seismicity_Example", None, 0.6, 9999, (20.0, 5.0, (0, -40, 0))),
]


def scene_file(folder: Path, explicit: str | None) -> Path | None:
    if explicit:
        return folder / explicit
    csvs = sorted(folder.glob("*node*.csv"), key=lambda p: len(p.name))
    return csvs[0] if csvs else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", default=None, help="Slugs to (re)capture.")
    args = parser.parse_args()
    wanted = set(args.only) if args.only else None

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841

    cap = Capture()
    failed = []
    try:
        for slug, folder, explicit, zoom, ch_frame, orbit in MANIFEST:
            if wanted is not None and slug not in wanted:
                continue
            path = scene_file(folder, explicit)
            if path is None or not path.exists():
                print(f"  !! {slug}: no scene file in {folder}")
                failed.append(slug)
                continue
            ok = cap.win._load_csv_path(str(path))
            if not ok:
                print(f"  !! {slug}: load failed for {path.name}")
                failed.append(slug)
                continue
            pump(0.4)
            if ch_frame is not None and cap.win._ch_engine is not None:
                cap.win._ch_apply_and_show_frame(ch_frame)
                pump(0.1)
            cap.vp._cam_distance *= zoom
            if orbit is not None:
                az_delta, elevation, target_off = orbit
                cap.vp._cam_azimuth += az_delta
                cap.vp._cam_elevation = elevation
                for i in range(3):
                    cap.vp._cam_target[i] += target_off[i]
            cap.vp.update()
            pump(0.1)
            cap.viewport_png(OUT_DIR / f"{slug}.png")
            print(f"  ok {slug}  ({path.name})")
    finally:
        cap.close()

    if failed:
        print(f"{len(failed)} failed: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
