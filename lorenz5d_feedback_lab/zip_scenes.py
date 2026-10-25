"""
Zip this lab's four scenes for the docs site's per-example downloads, then
check every zip the way a user's drop would read it.

The lab lives outside examples/, so tools/zip_examples.py does not see it;
this writes the same kind of zip: one per scene, contents-first (the scene's
files at the zip root, no wrapper folder), deflated.

    python zip_scenes.py [--dest DIR]

Default destination: the live mirror's zips/ folder,
$GLYPHVIZ_WEB_ROOT/glyphviz/zips. Regenerate the scenes first (the
generate_*.py scripts); the scene folders are gitignored.
"""
import argparse
import os
import shutil
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from glyphviz_core.csv_reader import load_node_csv  # noqa: E402
from glyphviz_core.drop_router import resolve_drop  # noqa: E402
from glyphviz_core.channel_loader import find_channel_files  # noqa: E402

SCENES = ("Convection_Cells", "R_Sweep_Tower", "Feedback_Loop", "Stability_Landscape")
PREFIX = "Lorenz5D_"


def build(scene: str, dest: Path) -> Path:
    folder = HERE / scene
    files = sorted(p for p in folder.iterdir() if p.is_file())
    if not any(p.name.endswith("_gv_node.csv") for p in files):
        raise SystemExit(f"{folder} has no node CSV: run its generator first")
    out = dest / f"{PREFIX}{scene}.zip"
    tmp = out.with_suffix(".zip.part")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in files:
            zf.write(p, p.name)
    tmp.replace(out)
    return out


def check(zip_path: Path) -> str:
    """Resolve the zip as a drop, load its node CSV, find its channel files.
    A dropped zip extracts BESIDE itself when that folder is writable, so the
    check drops a copy in a scratch folder, never the published zip."""
    import tempfile
    scratch = Path(tempfile.mkdtemp(prefix="l5d_zipcheck_"))
    try:
        return _check(shutil.copy2(zip_path, scratch / zip_path.name))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _check(zip_path) -> str:
    plan = resolve_drop([Path(zip_path)])
    try:
        assert not plan.errors, plan.errors
        loads = [a for a in plan.actions if a.kind != "merge"]
        assert len(loads) == 1, plan.actions
        node_csv = loads[0].path
        nodes = load_node_csv(str(node_csv))
        ch_map, _tracks = find_channel_files(str(node_csv))
        return f"{len(nodes)} nodes" + (", channels found" if ch_map else ", static")
    finally:
        for d in plan.temp_dirs:
            shutil.rmtree(d, ignore_errors=True)


def main():
    root = os.environ.get("GLYPHVIZ_WEB_ROOT", r"C:\Jeff\iluvdata\public_html")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", type=Path, default=Path(root) / "glyphviz" / "zips")
    args = ap.parse_args()
    args.dest.mkdir(parents=True, exist_ok=True)
    for scene in SCENES:
        out = build(scene, args.dest)
        mb = out.stat().st_size / 2 ** 20
        print(f"  {out.name:<42} {mb:5.1f} MB  {check(out)}")


if __name__ == "__main__":
    main()
