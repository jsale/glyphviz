#!/usr/bin/env python3
"""
capture_tutorial_shots.py
==========================
Generate the screenshot set for the hand-authored-CSV tutorials
(glyphviz-docs/docs/tutorials/01-first-scene.md, 02-tags-hierarchy.md,
03-topology-geometry.md) by
writing the exact scratch CSVs those pages walk the reader through, loading
each through the real MainWindow open path (`_load_csv_path`, the same code
File > Open runs), and grabbing the viewport.

Shares the Capture window helper with capture_tour_shots.py. Like that
script, running this briefly opens a real window on the desktop; it drives
no mouse/keyboard input.

Usage:
    python tools/capture_tutorial_shots.py                # all shots
    python tools/capture_tutorial_shots.py --only tut02-04-full-tree
"""
import argparse
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from PySide6.QtWidgets import QApplication

from capture_tour_shots import Capture, pump   # noqa: E402  (same folder)

OUT_DIR = REPO_ROOT / "glyphviz-docs" / "docs" / "assets" / "tutorials"
SCRATCH = Path(tempfile.gettempdir()) / "glyphviz_tutorial_shot_scenes"

TWO_NODE = """id,type,parent_id,branch_level,translate_x,translate_y,translate_z,rotate_x,rotate_y,rotate_z,scale_x,scale_y,scale_z,color_r,color_g,color_b,color_a,geometry,hide,topo
1,5,0,0,0,0,0,0,0,0,1,1,1,242,121,61,255,11,0,0
2,5,1,1,3,0,0,0,0,0,0.6,0.6,0.6,90,200,255,255,3,0,0
"""

TWO_NODE_LABELED = """id,type,parent_id,branch_level,translate_x,translate_y,translate_z,rotate_x,rotate_y,rotate_z,scale_x,scale_y,scale_z,color_r,color_g,color_b,color_a,geometry,hide,topo,text,link
1,5,0,0,0,0,0,0,0,0,1,1,1,242,121,61,255,11,0,0,Root,https://www.iluvdata.org/glyphviz/
2,5,1,1,3,0,0,0,0,0,0.6,0.6,0.6,90,200,255,255,3,0,0,Child A,
"""

FOUR_NODE_LABELED = """id,type,parent_id,branch_level,translate_x,translate_y,translate_z,rotate_x,rotate_y,rotate_z,scale_x,scale_y,scale_z,color_r,color_g,color_b,color_a,geometry,hide,topo,text,link
1,5,0,0,0,0,0,0,0,0,1,1,1,242,121,61,255,11,0,0,Root,https://www.iluvdata.org/glyphviz/
2,5,1,1,3,0,0,0,0,0,0.6,0.6,0.6,90,200,255,255,3,0,0,Child A,
3,5,2,2,2,0,0,0,0,0,0.4,0.4,0.4,255,210,80,255,13,0,0,Grandchild,
4,5,1,1,-3,0,0,0,0,0,0.6,0.6,0.6,200,120,255,255,9,0,0,Child B,
"""

FOUR_NODE_PINNED = """id,type,parent_id,branch_level,translate_x,translate_y,translate_z,rotate_x,rotate_y,rotate_z,scale_x,scale_y,scale_z,color_r,color_g,color_b,color_a,geometry,hide,topo,text,link,show_text
1,5,0,0,0,0,0,0,0,0,1,1,1,242,121,61,255,11,0,0,Root,https://www.iluvdata.org/glyphviz/,1
2,5,1,1,3,0,0,0,0,0,0.6,0.6,0.6,90,200,255,255,3,0,0,Child A,,0
3,5,2,2,2,0,0,0,0,0,0.4,0.4,0.4,255,210,80,255,13,0,0,Grandchild,,0
4,5,1,1,-3,0,0,0,0,0,0.6,0.6,0.6,200,120,255,255,9,0,0,Child B,,0
"""

# Tutorial 3: same 4-node hierarchy, Root's topo changed and (sometimes) the
# children's translate values rewritten to match what that topology expects.
TORUS_COMPRESSED = """id,type,parent_id,branch_level,translate_x,translate_y,translate_z,rotate_x,rotate_y,rotate_z,scale_x,scale_y,scale_z,color_r,color_g,color_b,color_a,geometry,hide,topo,text,link,show_text
1,5,0,0,0,0,0,0,0,0,1,1,1,242,121,61,255,11,0,3,Root,https://www.iluvdata.org/glyphviz/,1
2,5,1,1,3,0,0,0,0,0,0.6,0.6,0.6,90,200,255,255,3,0,0,Child A,,0
3,5,2,2,2,0,0,0,0,0,0.4,0.4,0.4,255,210,80,255,13,0,0,Grandchild,,0
4,5,1,1,-3,0,0,0,0,0,0.6,0.6,0.6,200,120,255,255,9,0,0,Child B,,0
"""

TORUS_SPREAD = """id,type,parent_id,branch_level,translate_x,translate_y,translate_z,rotate_x,rotate_y,rotate_z,scale_x,scale_y,scale_z,color_r,color_g,color_b,color_a,geometry,hide,topo,text,link,show_text
1,5,0,0,0,0,0,0,0,0,1,1,1,242,121,61,255,11,0,3,Root,https://www.iluvdata.org/glyphviz/,1
2,5,1,1,0,0,0,0,0,0,0.6,0.6,0.6,90,200,255,255,3,0,0,Child A,,0
3,5,2,2,2,0,0,0,0,0,0.4,0.4,0.4,255,210,80,255,13,0,0,Grandchild,,0
4,5,1,1,180,0,0,0,0,0,0.6,0.6,0.6,200,120,255,255,9,0,0,Child B,,0
"""

PIN_BROKEN = """id,type,parent_id,branch_level,translate_x,translate_y,translate_z,rotate_x,rotate_y,rotate_z,scale_x,scale_y,scale_z,color_r,color_g,color_b,color_a,geometry,hide,topo,text,link,show_text
1,5,0,0,0,0,0,0,0,0,1,1,1,242,121,61,255,11,0,5,Root,https://www.iluvdata.org/glyphviz/,1
2,5,1,1,0,0,0,0,0,0,0.6,0.6,0.6,90,200,255,255,3,0,0,Child A,,0
3,5,2,2,2,0,0,0,0,0,0.4,0.4,0.4,255,210,80,255,13,0,0,Grandchild,,0
4,5,1,1,180,0,0,0,0,0,0.6,0.6,0.6,200,120,255,255,9,0,0,Child B,,0
"""

PIN_FIXED = """id,type,parent_id,branch_level,translate_x,translate_y,translate_z,rotate_x,rotate_y,rotate_z,scale_x,scale_y,scale_z,color_r,color_g,color_b,color_a,geometry,hide,topo,text,link,show_text
1,5,0,0,0,0,0,0,0,0,1,1,1,242,121,61,255,11,0,5,Root,https://www.iluvdata.org/glyphviz/,1
2,5,1,1,0.5,0,0,0,0,0,0.6,0.6,0.6,90,200,255,255,3,0,0,Child A,,0
3,5,2,2,2,0,0,0,0,0,0.4,0.4,0.4,255,210,80,255,13,0,0,Grandchild,,0
4,5,1,1,1.5,0,0,0,0,0,0.6,0.6,0.6,200,120,255,255,9,0,0,Child B,,0
"""

# (slug, csv text, show_tags, show_tags_selected_only, camera distance, camera target)
# set_nodes()'s auto-frame floors _cam_distance at 50 units regardless of
# scene span, which is much too far for these deliberately tiny hand-typed
# scenes (span ~3-7 units) — override it explicitly per shot instead. A
# target override is only needed when one node's position is a wild outlier
# (PIN_BROKEN's Child B at height 183) that would otherwise drag the
# default bounding-box-center target away from the interesting part of frame.
MANIFEST = [
    ("tut01-03-two-nodes", TWO_NODE, False, False, 9.0, None),
    ("tut02-02-labels-on", TWO_NODE_LABELED, True, False, 9.0, None),
    ("tut02-04-full-tree", FOUR_NODE_LABELED, True, False, 14.0, None),
    ("tut02-05-pinned-only", FOUR_NODE_PINNED, False, False, 14.0, None),
    # Torus/Sphere/Pin's base radius (~1 unit at base_scale=1.0, this repo's
    # actual default) is 1/3 what Scene.load()'s own stale base_scale=3.0
    # default would suggest -- these distances are tuned against the real
    # base_scale=1.0 positions (confirmed via Viewport.world_position),
    # not the geometry-not-yet-checked-by-eye guess.
    ("tut03-02-torus-compressed", TORUS_COMPRESSED, True, False, 4.5, None),
    ("tut03-03-torus-spread", TORUS_SPREAD, True, False, 5.5, None),
    ("tut03-05-pin-broken", PIN_BROKEN, True, False, 4.5, (0.0, 0.0, 0.6)),
    ("tut03-05-pin-fixed", PIN_FIXED, True, False, 5.0, (0.0, 0.0, 1.25)),
]


def write_scene(slug: str, csv_text: str) -> Path:
    folder = SCRATCH / slug
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "gv_node.csv"
    path.write_text(csv_text, encoding="utf-8", newline="\r\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", default=None,
                         help="Slugs to (re)capture.")
    args = parser.parse_args()
    wanted = set(args.only) if args.only else None

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841

    cap = Capture()
    failed = []
    try:
        for slug, csv_text, show_tags, show_tags_selected_only, distance, target in MANIFEST:
            if wanted is not None and slug not in wanted:
                continue
            path = write_scene(slug, csv_text)
            ok = cap.win._load_csv_path(str(path))
            if not ok:
                print(f"  !! {slug}: load failed for {path}")
                failed.append(slug)
                continue
            # Force a consistent 3/4 view on every shot rather than trusting
            # whatever azimuth/elevation the viewport happens to carry over
            # from the previous load in this same Capture() session.
            if target is not None:
                cap.vp.set_camera(azimuth=45.0, elevation=25.0,
                                   distance=distance, target=target)
            else:
                cap.vp.set_camera(azimuth=45.0, elevation=25.0,
                                   distance=distance)
            cap.vp.show_tags = show_tags
            cap.vp.show_tags_selected_only = show_tags_selected_only
            cap.vp.update()
            pump(0.3)
            cap.viewport_png(OUT_DIR / f"{slug}.png")
            print(f"  ok {slug}")
    finally:
        cap.close()

    if failed:
        print(f"{len(failed)} failed: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
