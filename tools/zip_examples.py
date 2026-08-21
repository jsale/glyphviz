"""Cut one downloadable zip per example scene, for the docs' per-example links.

The full ``GlyphViz_Examples.zip`` (see tools/release.py) stays exactly as it
is — this is the *additional* per-example download users asked for, so someone
who only wants the wind rose doesn't pull 196 MB.

  examples/Wind_Rose_Example/Monsoon_Year/  ->  Wind_Rose_Example_Monsoon_Year.zip

The zips are published to ``<web root>/glyphviz/zips/`` and are **not** part of
the repo — nothing here is tracked, and the docs link them by URL. Adding a new
example needs no doc change for the existing ones: re-run this script (it only
rebuilds what changed) and add the one link to the new gallery page.

Run it with the glyphviz conda env's python (see CLAUDE.md):

    <glyphviz-env>\\python.exe tools\\zip_examples.py            # build/refresh all
    <glyphviz-env>\\python.exe tools\\zip_examples.py --list     # just show the plan
    <glyphviz-env>\\python.exe tools\\zip_examples.py --only Wind_Rose_Example_Monsoon_Year
    <glyphviz-env>\\python.exe tools\\zip_examples.py --dest D:\\somewhere

What counts as one downloadable example
---------------------------------------
A **unit** is any folder holding a ``*_gv_node.csv`` of its own, so a folder of
several scenes (Geomagnetic_Field_Example, Tropical_Cyclone_Example, the GTD
and Vehicle sets, ...) yields one zip per scene rather than one big one. A
top-level example that is itself a scene *and* has scene subfolders
(CalStateTesting_Example) gets a zip for its own level with the subfolders left
out — they have their own zips. Protein_Import_Example has no node CSV at all
(it ships a .pdb), so a top-level folder with no scene anywhere under it is
taken whole.

The one exception is ``WHOLE_FOLDER_UNITS`` below: an example that is a *series*
rather than a set of independent scenes ships as a single zip even though it
holds several scene folders.

Zip layout
----------
Contents-first, the same contract release.py states for the app and full
examples archives: the zip holds the scene folder's *contents* at its top
level, so Windows' Extract All (which makes a folder named after the zip) lands
them in one clean folder, and dropping the zip on the window extracts and loads
in one step. Preserving the full ``examples/`` path instead was tried and
dropped — it nests three folders that all say the same thing and pushes real
scenes toward Windows' 260-character path limit.

A zip holds exactly one folder: the scene's own. A sub-scene does **not** pick
up its parent's README, generator script or preview PNGs — some of those
collide by name with the scene's own files (Audio_Animation_Example and its
scenes both carry ``audio_analysis.py``), the gallery page is the write-up
anyway, and anyone who wants the generators has the full examples set.

The one cross-scene reference in the tree is handled: Cat_Scan_Synesthesia's
audio manifest points at ``../Cat_Scan_Example/media/cat_scan_all_mono.wav``,
which would leave its standalone zip silent, so the WAV is pulled into the
unit's own ``media/`` and the manifest rewritten to match *inside the zip only*.
"""

import argparse
import os
import re
import sys
import time
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EXAMPLES = REPO / 'examples'

# Same exclusions release.py applies to the full archive, plus nested *.zip:
# Global_Terrorism_Example and Tropical_Cyclone_Example each keep a zipped copy
# of their big scenes beside the working folder, and shipping both would double
# the download.
EXCLUDE_DIRS = {'__pycache__', '.ipynb_checkpoints', '.git', '_notes'}
EXCLUDE_FILES = {'Thumbs.db', '.DS_Store'}
EXCLUDE_SUFFIXES = {'.pyc', '.pyo', '.zip'}

NODE_CSV_RE = re.compile(r'_gv_node\.csv$', re.IGNORECASE)

# Examples that ship as ONE zip even though they hold several scene folders.
#
# Topology_Animation_Examples is an instructional *series*, not a set of
# independent scenes: each animation is built from the same visual grammar as
# the last one, the docs link the set as a whole, and the top level carries the
# README, the notebook and the generator that produced every folder. Splitting
# it per scene would hand out twelve downloads AND silently drop those three
# files, since the top level holds no node CSV of its own and so is not a unit.
WHOLE_FOLDER_UNITS = {'Topology_Animation_Examples'}


# ----------------------------------------------------------------- helpers

def log(msg=''):
    print(msg, flush=True)


def mib(n_bytes: int) -> int:
    return round(n_bytes / (1024 * 1024))


def size_label(n_bytes: int) -> str:
    """Human size for the docs' download buttons: '820 KB', '26 MB'."""
    if n_bytes < 1024 * 1024:
        return f"{max(1, round(n_bytes / 1024))} KB"
    return f"{mib(n_bytes)} MB"


def site_dir() -> Path | None:
    """mkdocs.yml's site_dir — same read release.py does, so this file keeps
    no machine-specific absolute path of its own."""
    cfg = REPO / 'glyphviz-docs' / 'mkdocs.yml'
    try:
        text = cfg.read_text(encoding='utf-8')
    except OSError:
        return None
    m = re.search(r'^site_dir:\s*(.+?)\s*$', text, re.MULTILINE)
    return Path(m.group(1).strip().strip('"\'')) if m else None


def default_dest() -> Path | None:
    """<web root>/glyphviz/zips — beside the versions/ and examples/ folders
    release.py publishes into."""
    site = site_dir()
    if site is None:
        return None
    published = site.parent / 'glyphviz'
    return published / 'zips' if published.is_dir() else None


def is_scene(folder: Path) -> bool:
    """True if a node CSV sits directly in *folder*."""
    try:
        return any(NODE_CSV_RE.search(p.name) for p in folder.iterdir() if p.is_file())
    except OSError:
        return False


def shippable_dirs(folder: Path) -> list[Path]:
    try:
        return sorted(p for p in folder.iterdir()
                      if p.is_dir() and p.name not in EXCLUDE_DIRS)
    except OSError:
        return []


def shippable_files(folder: Path) -> list[Path]:
    try:
        return sorted(p for p in folder.iterdir()
                      if p.is_file()
                      and p.name not in EXCLUDE_FILES
                      and p.suffix.lower() not in EXCLUDE_SUFFIXES)
    except OSError:
        return []


def walk_files(root: Path, skip_dirs=()):
    """Every shippable file under *root*, skipping the named subdirectories."""
    skip = {Path(d).name for d in skip_dirs}
    for dirpath, dirnames, filenames in os.walk(root):
        if Path(dirpath) == root:
            dirnames[:] = sorted(d for d in dirnames
                                 if d not in EXCLUDE_DIRS and d not in skip)
        else:
            dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS)
        for name in sorted(filenames):
            if name in EXCLUDE_FILES or Path(name).suffix.lower() in EXCLUDE_SUFFIXES:
                continue
            yield Path(dirpath) / name


# ------------------------------------------------------------------- units

class Unit:
    """One downloadable example: a name, the files in it, and their arcnames."""

    def __init__(self, name: str, folder: Path, entries: list[tuple[Path, str]],
                 rewrites: dict[str, bytes] | None = None):
        self.name = name
        self.folder = folder
        self.entries = entries              # (source path, arcname)
        self.rewrites = rewrites or {}      # arcname -> replacement bytes
        self.raw_bytes = sum(p.stat().st_size for p, _ in entries)

    @property
    def zip_name(self) -> str:
        return f"{self.name}.zip"

    def newest_mtime(self) -> float:
        return max((p.stat().st_mtime for p, _ in self.entries), default=0.0)


def unit_name(folder: Path) -> str:
    """Zip stem for a unit folder.

    A top-level example keeps its own name. A scene subfolder is prefixed with
    its example so the file still says what it is once it is sitting in a
    Downloads folder — except when the subfolder already carries the
    ``_Example`` suffix (the audio scenes), where the prefix would only stutter.
    """
    rel = folder.relative_to(EXAMPLES).parts
    if len(rel) == 1:
        return rel[0]
    parent, child = rel[0], rel[-1]
    return child if child.endswith('_Example') else f"{parent}_{child}"


def arcname(path: Path, root: Path) -> str:
    """Archive name for *path*, relative to the unit folder (contents-first)."""
    return str(path.relative_to(root)).replace('\\', '/')


def rel_to_examples(folder: Path) -> str:
    return str(folder.relative_to(EXAMPLES)).replace('\\', '/')


def external_audio_fix(folder: Path) -> tuple[list[tuple[Path, str]], dict[str, bytes]]:
    """Pull in an audio file the unit's manifest points at from outside it.

    channel_loader.find_audio_file() resolves the one-line ``*_gv_audio.txt``
    relative to the node CSV's folder. Cat_Scan_Synesthesia_Example reuses the
    WAV sitting in Cat_Scan_Example/media/, which is fine inside the full
    examples tree and silent in a standalone zip. Returns the extra entries and
    the rewritten manifest keyed by arcname; both empty for every other scene.
    """
    manifests = [p for p in shippable_files(folder) if p.name.endswith('_gv_audio.txt')]
    if len(manifests) != 1:
        return [], {}
    manifest = manifests[0]
    rel = manifest.read_text(encoding='utf-8').strip()
    if not rel:
        return [], {}
    source = (folder / rel).resolve()
    try:
        source.relative_to(folder.resolve())
        return [], {}          # already inside the unit — nothing to do
    except ValueError:
        pass
    if not source.is_file():
        log(f"    WARNING: {manifest.name} points at a missing file: {rel}")
        return [], {}
    inner = f"media/{source.name}"
    return [(source, inner)], {arcname(manifest, folder): (inner + '\n').encode('utf-8')}


def discover_units() -> list[Unit]:
    units: list[Unit] = []
    for top in sorted(p for p in EXAMPLES.iterdir()
                      if p.is_dir() and p.name not in EXCLUDE_DIRS):
        scenes = [d for d in shippable_dirs(top) if is_scene(d)]
        if not scenes or top.name in WHOLE_FOLDER_UNITS:
            # Whole folder, scene or not (Protein_Import_Example ships a .pdb).
            entries = [(p, arcname(p, top)) for p in walk_files(top)]
            units.append(Unit(unit_name(top), top, entries))
            continue

        for scene in scenes:
            entries = [(p, arcname(p, scene)) for p in walk_files(scene)]
            extra, rewrites = external_audio_fix(scene)
            units.append(Unit(unit_name(scene), scene, entries + extra, rewrites))
        if is_scene(top):
            # The example is a scene in its own right as well (CalStateTesting):
            # its zip is its own level, minus the scenes that have their own.
            entries = [(p, arcname(p, top)) for p in walk_files(top, skip_dirs=scenes)]
            units.append(Unit(unit_name(top), top, entries))
    return sorted(units, key=lambda u: u.name.lower())


# ------------------------------------------------------------------ zipping

def build(unit: Unit, dest_dir: Path) -> int:
    seen: set[str] = set()
    for _, name in unit.entries:
        if name in seen:
            raise SystemExit(f"{unit.zip_name}: two files would both be {name!r}")
        seen.add(name)
    dest = dest_dir / unit.zip_name
    tmp = dest.with_suffix('.zip.part')
    started = time.time()
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path, name in unit.entries:
            if name in unit.rewrites:
                zf.writestr(name, unit.rewrites[name])
            else:
                zf.write(path, name)
    tmp.replace(dest)
    size = dest.stat().st_size
    log(f"  {unit.zip_name:<52} {size_label(size):>7}  "
        f"({len(unit.entries)} files, {time.time() - started:.0f}s)")
    return size


def is_current(unit: Unit, dest_dir: Path) -> bool:
    dest = dest_dir / unit.zip_name
    return dest.is_file() and dest.stat().st_mtime >= unit.newest_mtime()


# --------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--dest', type=Path, default=None,
                    help='folder to write the zips into '
                         '(default: <web root>/glyphviz/zips)')
    ap.add_argument('--only', action='append', default=[],
                    help='build just this zip name (repeatable, no .zip needed)')
    ap.add_argument('--list', action='store_true',
                    help='show the units and their sizes; write nothing')
    ap.add_argument('--force', action='store_true',
                    help='rebuild even when the zip is newer than its sources')
    args = ap.parse_args()

    if not EXAMPLES.is_dir():
        log(f"no examples folder at {EXAMPLES}")
        return 1

    units = discover_units()
    if args.only:
        wanted = {n[:-4] if n.lower().endswith('.zip') else n for n in args.only}
        missing = wanted - {u.name for u in units}
        if missing:
            log(f"unknown example(s): {', '.join(sorted(missing))}")
            return 1
        units = [u for u in units if u.name in wanted]

    if args.list:
        log(f"{len(units)} downloadable examples:\n")
        for u in units:
            log(f"  {u.zip_name:<52} {size_label(u.raw_bytes):>7} uncompressed  "
                f"({len(u.entries)} files)  <- examples/{rel_to_examples(u.folder)}")
        return 0

    dest_dir = args.dest or default_dest()
    if dest_dir is None:
        log("could not locate the publish folder; pass --dest")
        return 1
    dest_dir.mkdir(parents=True, exist_ok=True)
    log(f"writing {len(units)} zips to {dest_dir}\n")

    built = skipped = 0
    total = 0
    for u in units:
        if not args.force and is_current(u, dest_dir):
            size = (dest_dir / u.zip_name).stat().st_size
            total += size
            skipped += 1
            log(f"  {u.zip_name:<52} {size_label(size):>7}  (up to date)")
            continue
        total += build(u, dest_dir)
        built += 1

    log(f"\n{built} built, {skipped} up to date, {mib(total)} MB total")
    return 0


if __name__ == '__main__':
    sys.exit(main())
