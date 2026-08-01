#!/usr/bin/env python3
"""
capture_example_shots.py
========================
Generate one screenshot per shipped example for the docs Examples Gallery
(glyphviz-docs/docs/examples/), by loading each scene through the real
MainWindow loader (File > Open / Import PDB code paths — companion tag,
channel, and media files come along exactly as they do for a user) and
grabbing the auto-framed viewport.

Shares the Capture window helper with capture_tour_shots.py. Like that
script, running this briefly opens a real window on the desktop; it drives
no input.

Usage:
    python tools/capture_example_shots.py                 # everything
    python tools/capture_example_shots.py --only rss-news topology
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from PySide6.QtWidgets import QApplication

from capture_tour_shots import Capture, pump   # noqa: E402  (same folder)

OUT_DIR = REPO_ROOT / "glyphviz-docs" / "docs" / "assets" / "examples"
EX = REPO_ROOT / "examples"

# (slug, scene folder, explicit file or None). None -> the folder's single
# *node*.csv. A .pdb file goes through the PDB import path instead.
MANIFEST = [
    ("topology", EX / "Topology_Example", None),
    ("channel-parameters", EX / "Channel_Parameters_Example", None),
    ("palette", EX / "Palette_Example", None),
    ("sine-wave", EX / "SineWave_Example", None),
    ("rotation-convention", EX / "Rotation_Convention_Example", None),
    ("texture-animation", EX / "Texture_Animation_Example", None),
    ("mood-background", EX / "Mood_Background_Example", None),
    ("bird-song-surface", EX / "Bird_Song_Surface_Topology_Example", None),
    ("audio-cat-scan", EX / "Audio_Animation_Example" / "Cat_Scan_Example", None),
    ("audio-cat-scan-synesthesia",
     EX / "Audio_Animation_Example" / "Cat_Scan_Synesthesia_Example", None),
    ("audio-four-instruments",
     EX / "Audio_Animation_Example" / "Four_Instruments_C_Major_Example", None),
    ("audio-moby-go", EX / "Audio_Animation_Example" / "Moby_Go_Example", None),
    ("audio-violin-a-major",
     EX / "Audio_Animation_Example" / "Violin_A_Major_Example", None),
    ("surface-cowles", EX / "Surface_Example", None),
    ("multi-hike-race", EX / "Multi_Hike_Race_Example", None),
    ("sd-seismicity", EX / "SD_Seismicity_Example", None),
    ("rss-news", EX / "RSS_News_Example", None),
    ("calstate-testing", EX / "CalStateTesting_Example", None),
    ("ses-achievement-gap-terrain", EX / "SES_Achievement_Gap_Terrain_Example", None),
    ("district-heatmap", EX / "District_Heatmap_Example", None),
    ("gtdb-organization-profiles",
     EX / "Global_Terrorism_Example" / "Organization_Profiles", None),
    ("gtdb-event-cloud", EX / "Global_Terrorism_Example" / "Event_Cloud", None),
    ("gtdb-org-event-network",
     EX / "Global_Terrorism_Example" / "Org_Event_Network", None),
    ("gtdb-time-replay", EX / "Global_Terrorism_Example" / "Time_Replay", None),
    ("gtdb-campaign-pulse", EX / "Global_Terrorism_Example" / "Campaign_Pulse", None),
    ("vehicle-market-galaxy", EX / "Vehicle_Sales_Example" / "Market_Galaxy", None),
    ("vehicle-depreciation-grid",
     EX / "Vehicle_Sales_Example" / "Depreciation_Grid", None),
    ("vehicle-raw-auction-field",
     EX / "Vehicle_Sales_Example" / "Raw_Auction_Field", None),
    ("breathing-century", EX / "Breathing_Century_Example", None),
    ("century-swarm", EX / "Century_Swarm_Example", None),
    ("duel-of-dynasties", EX / "Duel_Of_Dynasties_Example", None),
    ("ybco-superconductor", EX / "YBCO_Superconductor_Example", None),
    ("protein-import", EX / "Protein_Import_Example", "alpha_helix_example.pdb"),
    ("flocking", EX / "Flocking_Example", None),
    ("autosleep-2025", EX / "AutoSleep_2025_Example", None),
    ("hacking-creativity-glyph", EX / "Hacking_Creativity_Glyph_Example",
     "Hacking_Creativity_Glyph_Example_gv_node.csv"),
]


# Auto-framing fits a bounding box; for a few scenes that reads too distant.
# Values multiply the fitted camera distance after load.
ZOOM = {
    "protein-import": 0.35,
}


def scene_file(folder: Path, explicit: str | None) -> Path | None:
    if explicit:
        return folder / explicit
    csvs = sorted(folder.glob("*node*.csv"), key=lambda p: len(p.name))
    return csvs[0] if csvs else None


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
        for slug, folder, explicit in MANIFEST:
            if wanted is not None and slug not in wanted:
                continue
            path = scene_file(folder, explicit)
            if path is None or not path.exists():
                print(f"  !! {slug}: no scene file in {folder}")
                failed.append(slug)
                continue
            if path.suffix.lower() == ".pdb":
                ok = cap.win._load_pdb_path(str(path))
            else:
                ok = cap.win._load_csv_path(str(path))
            if not ok:
                print(f"  !! {slug}: load failed for {path.name}")
                failed.append(slug)
                continue
            pump(0.4)   # texture uploads / first frame of a big scene
            if slug in ZOOM:
                cap.vp._cam_distance *= ZOOM[slug]
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
