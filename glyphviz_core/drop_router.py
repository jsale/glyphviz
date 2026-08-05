"""Resolve dropped file-system paths into a plan of load actions.

This module is deliberately Qt-free: MainWindow's dropEvent hands it a plain
list of paths and gets back a DropPlan describing what to load, in what order.
All the interesting decisions (which CSV in a folder is the node file, where a
zip extracts, what to do when several things are dropped at once) live here so
they can be tested headlessly, without a GL context or an event loop.

The routing leans on the fact that everything else in a GlyphViz scene is
discovered *from* the node CSV's path — the companion tag file
(csv_reader._tag_file_path), the ch-map/ch-tracks pair
(channel_loader.find_channel_files), the audio manifest, and the media/ texture
folder next to it. So "load this folder" reduces to "find its node CSV"; the
rest comes along on its own.
"""

from __future__ import annotations

import csv
import os
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

# --- what we recognise -------------------------------------------------------

MESH_EXTS = frozenset({'.obj', '.stl', '.ply', '.glb', '.gltf'})
PDB_EXTS = frozenset({'.pdb'})
ZIP_EXTS = frozenset({'.zip'})

# Kept in step with texture_manager._IMAGE_EXTS / video_manager._VIDEO_EXTS.
# Only used to recognise a dropped folder as a texture folder, so a near-miss
# costs an informational note, not a wrong load.
IMAGE_EXTS = frozenset({
    '.png', '.jpg', '.jpeg', '.jfif', '.bmp', '.tga', '.gif', '.tif', '.tiff',
})
VIDEO_EXTS = frozenset({'.mp4', '.avi', '.mov', '.mkv', '.webm', '.m4v', '.wmv', '.flv'})
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS

# Columns load_node_csv indexes unconditionally. A CSV missing any of these
# would raise there, so requiring a core subset up front lets us tell a node
# CSV from its tag/channel companions by content rather than by filename.
NODE_CSV_REQUIRED = frozenset({
    'id', 'type', 'parent_id', 'translate_x', 'translate_y', 'translate_z',
})
# GaiaViz np_ dialect: csv_reader renames these once it sees np_node_id first.
NODE_CSV_REQUIRED_GAIAVIZ = frozenset({
    'np_node_id', 'type', 'parent_id', 'translate_x', 'translate_y', 'translate_z',
})

# --- action kinds ------------------------------------------------------------

ACTION_OPEN_CSV = 'open_csv'
ACTION_MERGE_CSV = 'merge_csv'
ACTION_PDB = 'pdb'
ACTION_MESH = 'mesh'
ACTION_TEXTURES = 'textures'


@dataclass(frozen=True)
class DropAction:
    kind: str
    path: Path


@dataclass
class DropPlan:
    """What a drop resolved to. `actions` are applied in order."""
    actions: list[DropAction] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)     # shown in the status bar
    errors: list[str] = field(default_factory=list)    # nothing loadable / failed
    temp_dirs: list[Path] = field(default_factory=list)  # zips extracted to temp

    @property
    def is_empty(self) -> bool:
        return not self.actions


# --- node-CSV detection ------------------------------------------------------

def _header_fields(path: Path) -> list[str]:
    """First row of a CSV as a list of column names, or [] if unreadable.

    Reads one line rather than handing the file to pandas: a folder drop may
    sniff a dozen CSVs, and some of them (ch-tracks on a long animation) are
    large enough that parsing them just to reject them would stall the drop.
    """
    try:
        with open(path, 'r', encoding='utf-8-sig', newline='', errors='replace') as fh:
            for row in csv.reader(fh):
                return [c.strip() for c in row]
    except OSError:
        return []
    return []


def looks_like_node_csv(path: Path) -> bool:
    """True when this CSV has the columns load_node_csv requires.

    Content-based on purpose: it accepts an arbitrarily named node file and
    rejects gv_tag.csv / gv_ch-map.csv / gv_ch-tracks.csv without relying on
    the naming convention, which third-party files don't always follow.
    """
    if path.suffix.lower() != '.csv':
        return False
    cols = set(_header_fields(path))
    if not cols:
        return False
    return NODE_CSV_REQUIRED <= cols or NODE_CSV_REQUIRED_GAIAVIZ <= cols


def _node_name_rank(path: Path) -> int:
    """Preference order among several node CSVs in one folder (lower is better).

    Convention names win over arbitrary ones, so a folder holding both
    gv_node.csv and some unrelated export opens the one the author intended.
    """
    stem = path.stem.lower()
    base = stem[:-14] if len(stem) > 14 and stem[-14:].isdigit() else stem
    if base in ('gv_node', 'np_node'):
        return 0
    if base.endswith('node'):
        return 1
    return 2


def find_node_csvs(folder: Path) -> list[Path]:
    """Every node CSV directly inside *folder*, best candidate first.

    Non-recursive by design — a nested search through an examples/ tree would
    turn one drop into an arbitrary scene choice. _effective_folder already
    steps through a zip's single wrapper directory, which is the case that
    actually comes up.
    """
    try:
        entries = sorted(p for p in folder.iterdir() if p.is_file())
    except OSError:
        return []
    found = [p for p in entries if looks_like_node_csv(p)]
    # Newest timestamp first within a rank: a folder of stamped saves should
    # open the most recent one.
    found.sort(key=lambda p: (_node_name_rank(p), _stamp_sort_key(p)))
    return found


def _stamp_sort_key(path: Path) -> tuple[int, str]:
    """Sort helper putting the newest YYYYMMDDHHMMSS-stamped file first."""
    stem = path.stem
    if len(stem) > 14 and stem[-14:].isdigit():
        # Negate lexicographically by inverting: later stamps sort earlier.
        return (0, ''.join(chr(ord('9') - (ord(c) - ord('0'))) for c in stem[-14:]))
    return (1, stem.lower())


def folder_has_media(folder: Path) -> bool:
    try:
        return any(
            p.is_file() and p.suffix.lower() in MEDIA_EXTS
            for p in folder.iterdir()
        )
    except OSError:
        return False


def find_pdbs(folder: Path) -> list[Path]:
    """Every PDB directly inside *folder*, name-sorted.

    Only zips consult this: the per-example downloads include one whose whole
    payload is a PDB (Protein_Import_Example), and refusing it for having no
    node CSV would be a surprising way to greet a scene that imports fine when
    the .pdb itself is dropped.
    """
    try:
        return sorted(p for p in folder.iterdir()
                      if p.is_file() and p.suffix.lower() in PDB_EXTS)
    except OSError:
        return []


# --- zip handling ------------------------------------------------------------

MAX_ZIP_ENTRIES = 20_000
MAX_ZIP_BYTES = 2 * 1024 ** 3   # 2 GiB uncompressed


class ZipExtractError(Exception):
    pass


def _safe_zip_members(zf: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    """Validate a zip's entries before extracting anything.

    Guards the usual archive hazards, since a dropped zip may have come from
    anywhere: absolute paths and '..' segments that would escape the target
    directory ("zip slip"), and entry-count/size blowups.
    """
    infos = zf.infolist()
    if len(infos) > MAX_ZIP_ENTRIES:
        raise ZipExtractError(
            f"archive has {len(infos)} entries (limit {MAX_ZIP_ENTRIES})")
    total = 0
    members = []
    for info in infos:
        name = info.filename.replace('\\', '/')
        if name.endswith('/'):
            continue
        pure = Path(name)
        if not pure.parts:
            continue
        # ':' catches a Windows drive prefix, which PurePosixPath would
        # otherwise treat as an ordinary relative segment.
        if pure.is_absolute() or name.startswith('/') or ':' in pure.parts[0]:
            raise ZipExtractError(f"archive contains an absolute path: {info.filename}")
        if '..' in pure.parts:
            raise ZipExtractError(f"archive contains a parent-directory path: {info.filename}")
        total += info.file_size
        if total > MAX_ZIP_BYTES:
            raise ZipExtractError("archive expands to more than 2 GiB")
        members.append(info)
    if not members:
        raise ZipExtractError("archive is empty")
    return members


def _unique_dir(parent: Path, stem: str) -> Path:
    """A not-yet-existing directory `parent/stem`, suffixed if that's taken."""
    candidate = parent / stem
    n = 2
    while candidate.exists():
        candidate = parent / f'{stem}_{n}'
        n += 1
    return candidate


def _writable(folder: Path) -> bool:
    return os.access(folder, os.W_OK)


def extract_zip(zip_path: Path) -> tuple[Path, bool]:
    """Extract *zip_path* and return (destination, used_temp).

    Extracts into a new folder beside the zip so a later Save lands somewhere
    durable next to the data it came from. Falls back to a temp directory when
    that location isn't writable (a read-only share, a zip opened straight out
    of a download quarantine); used_temp says which happened, so the caller can
    tell the user their edits would go somewhere disposable.
    """
    zip_path = Path(zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        members = _safe_zip_members(zf)
        parent = zip_path.parent
        used_temp = not _writable(parent)
        if used_temp:
            dest = Path(tempfile.mkdtemp(prefix='glyphviz_drop_'))
        else:
            dest = _unique_dir(parent, zip_path.stem)
        dest.mkdir(parents=True, exist_ok=True)
        # Extract member-by-member: extractall() would also recreate the
        # directory entries we skipped above, and we want only vetted names.
        for info in members:
            zf.extract(info, dest)
    return dest, used_temp


def _effective_folder(folder: Path) -> Path:
    """Step through a lone wrapper directory.

    Archives are usually zipped from the parent, so Example.zip extracts to
    <dest>/Example_Example/ with everything one level down. Descend while the
    folder holds exactly one subdirectory and no files of its own.
    """
    current = folder
    for _ in range(8):   # bounded: never chase a pathological nest forever
        try:
            entries = list(current.iterdir())
        except OSError:
            return current
        subdirs = [p for p in entries if p.is_dir()]
        files = [p for p in entries if p.is_file()]
        if len(subdirs) == 1 and not files:
            current = subdirs[0]
        else:
            return current
    return current


# --- the plan ----------------------------------------------------------------

def resolve_drop(paths, *, merge: bool = False) -> DropPlan:
    """Turn dropped paths into an ordered DropPlan.

    *merge* (Shift held during the drop) makes the first node CSV merge into
    the current scene instead of replacing it, mirroring File > Merge (Ctrl+M).

    Multiple node CSVs in one drop open the first and merge the rest, so
    dragging in a handful of scenes composes them the way repeated Ctrl+M
    would. Meshes and texture folders are additive and always applied; a PDB
    is a whole-scene replace, so it's skipped (with a note) when the same drop
    also carries a node CSV.
    """
    plan = DropPlan()
    node_csvs: list[Path] = []
    pdbs: list[Path] = []
    meshes: list[Path] = []
    tex_folders: list[Path] = []
    unknown: list[Path] = []

    for raw in paths:
        p = Path(raw)
        if not p.exists():
            plan.errors.append(f"{p.name}: not found")
            continue
        suffix = p.suffix.lower()

        if p.is_file() and suffix in ZIP_EXTS:
            try:
                dest, used_temp = extract_zip(p)
            except (ZipExtractError, zipfile.BadZipFile, OSError) as exc:
                plan.errors.append(f"{p.name}: {exc}")
                continue
            if used_temp:
                plan.temp_dirs.append(dest)
            folder = _effective_folder(dest)
            found = find_node_csvs(folder)
            if found:
                node_csvs.append(found[0])
                where = "a temporary folder" if used_temp else f"{dest.name}/"
                plan.notes.append(f"extracted {p.name} to {where}")
                if used_temp:
                    plan.notes.append("saves from this scene would go to temp — use Save As")
            elif (inner_pdbs := find_pdbs(folder)):
                pdbs.append(inner_pdbs[0])
                plan.notes.append(f"extracted {p.name} — imported {inner_pdbs[0].name}")
            elif folder_has_media(folder):
                tex_folders.append(folder)
                plan.notes.append(f"extracted {p.name} — no node CSV, loaded as textures")
            else:
                plan.errors.append(f"{p.name}: no node CSV inside")
            continue

        if p.is_dir():
            folder = _effective_folder(p)
            found = find_node_csvs(folder)
            if found:
                node_csvs.append(found[0])
                if len(found) > 1:
                    plan.notes.append(
                        f"{folder.name}/ has {len(found)} node CSVs — opened {found[0].name}")
            elif folder_has_media(folder):
                tex_folders.append(folder)
            else:
                plan.errors.append(f"{p.name}: no node CSV or media files inside")
            continue

        if suffix == '.csv':
            if looks_like_node_csv(p):
                node_csvs.append(p)
            else:
                # A companion (tag / ch-map / ch-tracks) is a natural thing to
                # grab by mistake — redirect to the node file it belongs with
                # rather than failing on a file that can't be a scene.
                sibling = find_node_csvs(p.parent)
                if sibling:
                    node_csvs.append(sibling[0])
                    plan.notes.append(f"{p.name} is a companion file — opened {sibling[0].name}")
                else:
                    plan.errors.append(f"{p.name}: not a node CSV")
            continue

        if suffix in PDB_EXTS:
            pdbs.append(p)
        elif suffix in MESH_EXTS:
            meshes.append(p)
        elif suffix in MEDIA_EXTS:
            # Loading textures is a whole-folder operation (texture_id indexes
            # the folder's sorted contents), so a dropped image means its folder.
            if p.parent not in tex_folders:
                tex_folders.append(p.parent)
            plan.notes.append(f"loaded textures from {p.parent.name}/")
        else:
            unknown.append(p)

    # de-dupe, preserving order
    node_csvs = _dedupe(node_csvs)
    tex_folders = _dedupe(tex_folders)
    meshes = _dedupe(meshes)

    for i, csv_path in enumerate(node_csvs):
        first = i == 0
        kind = ACTION_MERGE_CSV if (merge or not first) else ACTION_OPEN_CSV
        plan.actions.append(DropAction(kind, csv_path))

    if pdbs:
        if node_csvs:
            plan.notes.append(f"ignored {len(pdbs)} PDB file(s) — a node CSV was dropped too")
        else:
            plan.actions.append(DropAction(ACTION_PDB, pdbs[0]))
            if len(pdbs) > 1:
                plan.notes.append(f"opened {pdbs[0].name} — one PDB at a time")

    for folder in tex_folders:
        plan.actions.append(DropAction(ACTION_TEXTURES, folder))
    for mesh in meshes:
        plan.actions.append(DropAction(ACTION_MESH, mesh))

    if unknown:
        names = ', '.join(p.name for p in unknown[:3])
        more = f" (+{len(unknown) - 3} more)" if len(unknown) > 3 else ''
        plan.errors.append(f"unsupported: {names}{more}")

    return plan


def _dedupe(items: list[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for p in items:
        key = str(p.resolve()).lower() if os.name == 'nt' else str(p.resolve())
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def can_accept(paths) -> bool:
    """Cheap yes/no for dragEnterEvent — does this drop have anything we take?

    Extension-level only: dragEnterEvent fires continuously as the cursor
    moves, so this must not read file contents or open archives.
    """
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            return True
        suffix = p.suffix.lower()
        if suffix in ZIP_EXTS or suffix in PDB_EXTS or suffix in MESH_EXTS:
            return True
        if suffix == '.csv' or suffix in MEDIA_EXTS:
            return True
    return False
