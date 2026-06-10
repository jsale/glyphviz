"""
Shared fixtures and helpers for golden-master matrix tests.

The workflow is:
1. Edit / add scene CSVs in tests/golden/scenes/
2. Run generate_expected.py to populate tests/golden/expected/ (Python baseline
   until the ANTz C oracle is wired up in Phase A).
3. Run pytest — tests compare node_world_matrix() against the stored expected values.
4. Phase A: rerun generate_expected.py --oracle <oracle_dir> to replace Python
   baseline with ANTz C reference matrices; tests then verify conformance.
"""

import json
from pathlib import Path

import numpy as np
import pytest

SCENE_DIR    = Path(__file__).parent / "scenes"
EXPECTED_DIR = Path(__file__).parent / "expected"


def load_oracle(scene_name: str) -> dict[int, np.ndarray]:
    """
    Load expected matrices for a scene.
    Returns {node_id: 4x4 float64 array}.
    Skips the test if no oracle file exists yet (run generate_expected.py first).
    """
    path = EXPECTED_DIR / f"{scene_name}.json"
    if not path.exists():
        pytest.skip(f"No oracle for '{scene_name}' — run tests/golden/generate_expected.py")
    raw = json.loads(path.read_text())
    return {int(k): np.array(v, dtype=np.float64) for k, v in raw.items()}


def assert_matrix_close(
    actual: np.ndarray,
    expected: np.ndarray,
    node_id: int,
    atol: float = 1e-5,
):
    """Compare two 4x4 world matrices with a tolerance appropriate for float32 GL math."""
    np.testing.assert_allclose(
        actual, expected, atol=atol,
        err_msg=f"\nNode {node_id} matrix mismatch\n"
                f"actual:\n{actual}\n"
                f"expected:\n{expected}\n",
    )


def all_scene_names() -> list[str]:
    return sorted(p.stem for p in SCENE_DIR.glob("*.csv"))
