"""
Generate expected-matrix JSON files for the golden-master test suite.

Usage (from the repo root):
    conda run -n glyphviz python tests/golden/generate_expected.py

Each scene CSV in tests/golden/scenes/ gets a companion JSON in
tests/golden/expected/ containing the 4x4 world matrix for every node,
as computed by glyphviz_core.scene.node_world_matrix with base_scale=3.0.

Initially this creates a Python-computed baseline (regression protection).
Phase A will replace these with matrices extracted from the ANTz C oracle.

To regenerate a single scene, pass its name without extension:
    python tests/golden/generate_expected.py topo0_cartesian
"""

import json
import sys
from pathlib import Path

# Allow running from repo root without installing the package.
sys.path.insert(0, str(Path(__file__).parents[2]))

from glyphviz_core.scene import Scene, node_world_matrix

BASE_SCALE   = 3.0
SCENE_DIR    = Path(__file__).parent / "scenes"
EXPECTED_DIR = Path(__file__).parent / "expected"

EXPECTED_DIR.mkdir(parents=True, exist_ok=True)


def generate_scene(csv_path: Path):
    scene = Scene.load(csv_path, base_scale=BASE_SCALE)
    matrices: dict[str, list] = {}
    for node in scene.nodes:
        M = node_world_matrix(node, scene)
        matrices[str(node.id)] = M.tolist()
    out = EXPECTED_DIR / f"{csv_path.stem}.json"
    out.write_text(json.dumps(matrices, indent=2))
    print(f"  wrote {out.relative_to(Path.cwd())}  ({len(matrices)} nodes)")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        targets = [SCENE_DIR / f"{name}.csv" for name in sys.argv[1:]]
    else:
        targets = sorted(SCENE_DIR.glob("*.csv"))

    print(f"Generating expected matrices (base_scale={BASE_SCALE}) …")
    for csv in targets:
        if not csv.exists():
            print(f"  SKIP {csv} — not found")
            continue
        generate_scene(csv)
    print("Done.")
