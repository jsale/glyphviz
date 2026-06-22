#!/usr/bin/env python3
"""
generate_doc_screenshots.py
============================
Batch-renders the golden-master test scenes to docs/assets/ for use in
tutorials/docs, via export_frame.render_frame() (no window ever shown).

Re-running this is the reproducible alternative to hand-grabbing screenshots
each time a topology or rendering change makes the old ones stale.

Usage:
    python tools/generate_doc_screenshots.py
    python tools/generate_doc_screenshots.py --width 1920 --height 1080
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from PySide6.QtWidgets import QApplication

from tools.export_frame import render_frame

GOLDEN_SCENES_DIR = REPO_ROOT / "tests" / "golden" / "scenes"
OUT_DIR = REPO_ROOT / "docs" / "assets"

# The plain (un-suffixed) golden-master scenes — one representative CSV per
# topology/hierarchy case.  The *_antz.csv / *_np_node.csv siblings exist
# only to test cross-format column aliasing and would render identically.
SCENES = [
    "deep_hierarchy",
    "rotation_cascade",
    "siblings_branching",
    "topo0_cartesian",
    "topo2_sphere",
    "topo6_rod",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args()

    app = QApplication.instance() or QApplication(sys.argv)

    for name in SCENES:
        csv_path = GOLDEN_SCENES_DIR / f"{name}.csv"
        if not csv_path.exists():
            print(f"Skipping {name}: {csv_path} not found")
            continue
        out_path = OUT_DIR / f"{name}.png"
        render_frame(str(csv_path), str(out_path), args.width, args.height)
        print(f"Wrote {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
