"""Zip each AI Observatory scene for download from the website.

The scenes in ai_observatory/scenes/ are large (a Gemma node CSV is ~70 MB) and
regenerable, so they are not in the repository. They are published one zip per
scene instead, and the gallery pages link to them. The two scenes that ship
inside the examples set (examples/AI_Observatory_*_Example) are not here; those
go through tools/zip_examples.py with every other example.

    <glyphviz-env>\\python.exe ai_observatory\\zip_scenes.py            # all
    ...\\python.exe ai_observatory\\zip_scenes.py --only AI_Observatory_Gemma_IOI
    ...\\python.exe ai_observatory\\zip_scenes.py --dest D:\\somewhere --force

Default destination is <web root>/glyphviz/ai_observatory/scenes, found the way
tools/zip_examples.py finds its own: from mkdocs.yml's site_dir, so this file
carries no machine-specific path. Contents-first, like every other GlyphViz
zip: extracting gives you the scene's files, not a folder inside a folder.
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SCENES = HERE / "scenes"
# Screenshots are documentation of a scene, not part of it; the zip is what
# you drag into GlyphViz.
EXCLUDE_DIRS = {"screenshots", "__pycache__"}
EXCLUDE_FILES = {"Thumbs.db", ".DS_Store"}


def size_label(n: int) -> str:
    return f"{max(1, round(n / 1024))} KB" if n < 1024 * 1024 else f"{round(n / (1024 * 1024))} MB"


def site_dir() -> Path | None:
    cfg = REPO / "glyphviz-docs" / "mkdocs.yml"
    try:
        text = cfg.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"^site_dir:\s*(.+?)\s*$", text, re.MULTILINE)
    return Path(m.group(1).strip().strip("\"'")) if m else None


def default_dest() -> Path | None:
    site = site_dir()
    if site is None:
        return None
    published = site.parent / "glyphviz"
    return published / "ai_observatory" / "scenes" if published.is_dir() else None


def scene_files(folder: Path):
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.name in EXCLUDE_FILES:
            continue
        if set(path.relative_to(folder).parts[:-1]) & EXCLUDE_DIRS:
            continue
        yield path


def build(folder: Path, dest_dir: Path) -> int:
    dest = dest_dir / f"{folder.name}.zip"
    tmp = dest.with_suffix(".zip.part")
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for path in scene_files(folder):
            z.write(path, str(path.relative_to(folder)).replace("\\", "/"))
    tmp.replace(dest)
    return dest.stat().st_size


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dest", type=Path, default=None)
    ap.add_argument("--only", nargs="*", default=None, help="scene folder names")
    ap.add_argument("--force", action="store_true",
                    help="rebuild even when the zip is newer than the scene")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    folders = [p for p in sorted(SCENES.glob("*")) if p.is_dir()]
    if args.only:
        wanted = set(args.only)
        folders = [p for p in folders if p.name in wanted]
        missing = wanted - {p.name for p in folders}
        if missing:
            print(f"no such scene: {', '.join(sorted(missing))}")
            return 1
    if not folders:
        print(f"no scenes in {SCENES}")
        return 1
    if args.list:
        for f in folders:
            print(f"  {f.name}  ({size_label(sum(p.stat().st_size for p in scene_files(f)))} raw)")
        return 0

    dest_dir = args.dest or default_dest()
    if dest_dir is None:
        print("could not find the publish folder; pass --dest")
        return 1
    print(f"destination: {dest_dir}")
    total = 0
    for folder in folders:
        dest = dest_dir / f"{folder.name}.zip"
        newest = max((p.stat().st_mtime for p in scene_files(folder)), default=0.0)
        if not args.force and dest.is_file() and dest.stat().st_mtime >= newest:
            print(f"  = {dest.name} (current)")
            total += dest.stat().st_size
            continue
        size = build(folder, dest_dir)
        total += size
        print(f"  + {dest.name}  {size_label(size)}")
    print(f"{len(folders)} zips, {size_label(total)} total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
