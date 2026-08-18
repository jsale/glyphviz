"""Cut a GlyphViz Windows release: build, archive, publish, and re-stamp the docs.

One command does the whole chain that used to be done by hand — which is how
the previous release shipped as ``GlyphViz20260729.zip`` on 2026-07-26:

  1. PyInstaller build           -> dist\\GlyphViz\\
  2. Zip it                      -> GlyphViz<YYYYMMDD>.zip  (contents at the
                                    archive's top level: GlyphViz.exe +
                                    _internal, which is what the Installation
                                    page tells people to expect)
  3. Publish into the local iluvdata mirror, next to the previous releases,
     ready to upload
  4. Re-stamp the docs           -> every GlyphViz<date>.zip name/URL on the
                                    Installation page, plus its size and
                                    build-date line
  5. Rebuild the docs site and publish it into that same mirror folder, so
     one folder holds both the new zip and the pages that link to it

Steps 4 and 5 are the default, not an opt-in: the 2026-07-28 release re-stamped
the Installation page but never rebuilt the site, so the published pages still
advertised the previous zip. Pass --no-docs to leave the docs alone entirely.

Run it with the glyphviz conda env's python (see CLAUDE.md):

    <glyphviz-env>\\python.exe tools\\release.py                 # full release
    <glyphviz-env>\\python.exe tools\\release.py --dry-run       # show the plan
    <glyphviz-env>\\python.exe tools\\release.py --skip-build    # re-zip dist/ as is

The examples archive is deliberately NOT rebuilt: the example scenes don't
change from one app build to the next, and re-cutting 200+ MB on every app
build buys nothing. Pass --examples on the release where they do change. It is
published under the fixed name GlyphViz_Examples.zip — see ARTIFACTS for why
it carries no date where the app zip does.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# --- what gets published, and where ------------------------------------
#
# Each artifact is a folder zipped CONTENTS-FIRST (the folder itself is not a
# level in the archive) and published into its own subfolder of the mirror,
# matching the https://iluvdata.org/glyphviz/<subfolder>/<name>.zip URLs the
# Installation page links to.
ARTIFACTS = {
    'app': {
        'source': REPO / 'dist' / 'GlyphViz',
        'prefix': 'GlyphViz',
        'subdir': 'versions',
        'label': 'Windows app',
    },
    'examples': {
        'source': REPO / 'examples',
        'prefix': 'GlyphViz_Examples',
        'subdir': 'examples',
        'label': 'example scenes',
        # Undated, deliberately. The app zip earns its date — users keep
        # several builds side by side and the build date is meaningful — but
        # the examples set does not: it changes rarely, the enclosed files
        # carry their own dates, and a stable URL removes a whole drift
        # surface from the re-stamping logic this script exists to protect.
        # (The docs and the live file went undated first; this caught up on
        # 2026-08-18, until which --examples aborted on a pattern that
        # matched nothing.)
        'dated': False,
    },
}


def archive_name(spec: dict, stamp: str) -> str:
    return f"{spec['prefix']}{stamp}.zip" if spec.get('dated', True) \
        else f"{spec['prefix']}.zip"

# Never worth shipping, in either archive.
EXCLUDE_DIRS = {'__pycache__', '.ipynb_checkpoints', '.git', '_notes'}
EXCLUDE_FILES = {'Thumbs.db', '.DS_Store'}
EXCLUDE_SUFFIXES = {'.pyc', '.pyo'}

# Docs files that carry a release stamp. Rewrites are applied to all of them;
# a pattern that matches nothing anywhere is reported as doc drift rather
# than silently skipped.
DOC_FILES = [
    REPO / 'glyphviz-docs' / 'docs' / 'getting-started' / 'installation.md',
    REPO / 'glyphviz-docs' / 'docs' / 'getting-started' / 'quickstart.md',
    REPO / 'glyphviz-docs' / 'docs' / 'examples' / 'index.md',
]

# "GlyphViz20260729", and only that: the examples archive is
# GlyphViz_Examples.zip, with no digits after the name, so it cannot be hit
# here. The lookahead is kept against the old GlyphVizExamples<date> spelling
# in case an archived page or a stale local mirror still carries it.
APP_STAMP_RE = re.compile(r'GlyphViz(?!Examples)(\d{8})')

# "*Windows 10/11, 64-bit · ~116 MB download, ~300 MB extracted · build 2026-07-29*"
#
# Anchored on the "Windows 10/11, 64-bit" prefix, and not merely on the
# "~N MB download, ~N MB extracted · build <date>" shape: the macOS line
# ("Apple Silicon (arm64): ~98 MB … · Intel (x86_64): ~117 MB download, ~382 MB
# extracted · build 2026-08-06") ends in exactly that shape too, so the
# unanchored pattern stamped the WINDOWS size and date onto the Intel Mac
# build — which this release does not even rebuild. Caught and reverted by
# hand on 2026-08-12; keep the anchor.
APP_SIZE_RE = re.compile(
    r'(\*Windows 10/11, 64-bit · ~)\d+( MB download, ~)\d+'
    r'( MB extracted · build )\d{4}-\d{2}-\d{2}')
# "*~212 MB download, ~340 MB extracted*"
EXAMPLES_SIZE_RE = re.compile(r'(~)\d+( MB download, ~)\d+( MB extracted\*)')


# ----------------------------------------------------------------- helpers

def log(msg=''):
    print(msg, flush=True)


def mib(n_bytes: int) -> int:
    """Bytes as whole mebibytes — the unit Windows' file properties shows,
    and what the docs' '~NNN MB' figures mean."""
    return round(n_bytes / (1024 * 1024))


def site_dir() -> Path | None:
    """Where mkdocs build writes the site: mkdocs.yml's site_dir.

    Read from the config rather than hardcoded, which keeps this tracked file
    free of the machine-specific absolute paths that got build.bat gitignored.
    """
    cfg = REPO / 'glyphviz-docs' / 'mkdocs.yml'
    try:
        text = cfg.read_text(encoding='utf-8')
    except OSError:
        return None
    m = re.search(r'^site_dir:\s*(.+?)\s*$', text, re.MULTILINE)
    if not m:
        return None
    return Path(m.group(1).strip().strip('"\''))


def mirror_root() -> Path | None:
    """The local copy of the iluvdata web root that holds the published zips.

    site_dir points at <web root>/glyphviz-docs-site-preview, so its parent is
    the web root and the published site (and its versions/ and examples/
    folders) sits at <web root>/glyphviz. That folder is what gets uploaded.
    """
    site = site_dir()
    if site is None:
        return None
    candidate = site.parent / 'glyphviz'
    return candidate if candidate.is_dir() else None


def publish_site(site: Path, dest: Path) -> int:
    """Merge the built site into dest, overwriting pages but deleting nothing.

    dest also holds versions/ and examples/ with the release zips, which the
    site build knows nothing about — so this must never be a mirror-with-delete.
    Returns the number of files copied.
    """
    n = sum(1 for _ in site.rglob('*') if _.is_file())
    shutil.copytree(site, dest, dirs_exist_ok=True)
    return n


def walk_files(root: Path):
    """Every shippable file under root, as (absolute path, archive name)."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS)
        for name in sorted(filenames):
            if name in EXCLUDE_FILES or Path(name).suffix.lower() in EXCLUDE_SUFFIXES:
                continue
            path = Path(dirpath) / name
            yield path, str(path.relative_to(root)).replace('\\', '/')


def make_zip(source: Path, dest: Path) -> tuple[int, int]:
    """Zip source's CONTENTS to dest. Returns (zip bytes, extracted bytes).

    Contents-first is the contract the Installation page states: the app
    archive holds GlyphViz.exe and _internal at its top level, and the
    examples archive holds each example at its top level.
    """
    entries = list(walk_files(source))
    total = sum(p.stat().st_size for p, _ in entries)
    log(f"    {len(entries)} files, {mib(total)} MB uncompressed")
    tmp = dest.with_suffix('.zip.part')
    done = 0
    last_pct = -10
    started = time.time()
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path, arcname in entries:
            zf.write(path, arcname)
            done += path.stat().st_size
            pct = int(done * 100 / total) if total else 100
            if pct >= last_pct + 10:
                log(f"    ... {pct}%")
                last_pct = pct
    tmp.replace(dest)
    log(f"    zipped in {time.time() - started:.0f}s")
    return dest.stat().st_size, total


def run_build() -> None:
    """PyInstaller, via the same spec build.bat uses.

    sys.executable is the glyphviz env's python (this script is run with it),
    so the env is already correct — no conda-path probing needed here, and
    never `conda run`, which hangs on Jeff's Windows setup.
    """
    log(f"  using {sys.executable}")
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet',
                    '--upgrade', 'pyinstaller'], cwd=REPO, check=True)
    subprocess.run([sys.executable, '-m', 'PyInstaller', 'GlyphViz.spec',
                    '--clean', '-y'], cwd=REPO, check=True)


# -------------------------------------------------------------- doc rewrite

def rewrite_docs(edits, dry_run: bool) -> bool:
    """Apply (label, compiled pattern, replacement) edits across DOC_FILES.

    Returns False if any edit matched nothing anywhere — that means the docs
    drifted away from the shape this script expects, and the release should
    stop rather than publish a zip the download links don't point at.
    """
    hits = {label: 0 for label, _, _ in edits}
    changes: dict[Path, str] = {}
    for path in DOC_FILES:
        if not path.exists():
            log(f"  !! missing doc file: {path}")
            return False
        original = path.read_text(encoding='utf-8')
        text = original
        for label, pattern, repl in edits:
            text, n = pattern.subn(repl, text)
            hits[label] += n
        if text != original:
            changes[path] = text
            log(f"  {path.relative_to(REPO)}: updated")

    missed = [label for label, n in hits.items() if n == 0]
    if missed:
        log(f"  !! no match for: {', '.join(missed)}")
        log("     The docs no longer look the way this script expects — "
            "fix the pattern in tools/release.py (or the page) and re-run.")
        return False
    for label, n in hits.items():
        log(f"  {label}: {n} occurrence(s)")
    if dry_run:
        log("  (dry run — nothing written)")
        return True
    for path, text in changes.items():
        path.write_text(text, encoding='utf-8', newline='\n')
    return True


# --------------------------------------------------------------------- main

def main() -> int:
    today = date.today().strftime('%Y%m%d')
    ap = argparse.ArgumentParser(
        description="Build, archive, publish and re-stamp a GlyphViz release.")
    ap.add_argument('--date', default=today, metavar='YYYYMMDD',
                    help=f'release stamp (default: today, {today})')
    ap.add_argument('--skip-build', action='store_true',
                    help='re-zip the existing dist/GlyphViz instead of rebuilding')
    ap.add_argument('--examples', action='store_true',
                    help='also rebuild + re-stamp the examples archive '
                         '(only when the example scenes themselves changed)')
    ap.add_argument('--examples-only', action='store_true',
                    help='re-cut only the examples archive; leave the app alone')
    ap.add_argument('--out-root', type=Path, default=None, metavar='PATH',
                    help='web-root folder holding versions/ and examples/ '
                         '(default: the local iluvdata mirror, derived from '
                         "mkdocs.yml's site_dir)")
    ap.add_argument('--no-docs', action='store_true',
                    help='publish the archive but leave the docs alone: no '
                         're-stamp, no site build, no site publish')
    ap.add_argument('--no-docs-build', action='store_true',
                    help='re-stamp the docs but skip rebuilding and publishing '
                         'the site (you will have to run mkdocs build yourself)')
    ap.add_argument('--force', action='store_true',
                    help='overwrite an archive that already exists under that name')
    ap.add_argument('--dry-run', action='store_true',
                    help='show the plan; build nothing, write nothing')
    args = ap.parse_args()

    if not re.fullmatch(r'\d{8}', args.date):
        log(f"ERROR: --date must be YYYYMMDD, got {args.date!r}")
        return 2
    try:
        stamp_date = datetime.strptime(args.date, '%Y%m%d').date()
    except ValueError:
        log(f"ERROR: {args.date} is not a real date.")
        return 2
    if stamp_date > date.today():
        log(f"ERROR: {args.date} is in the future (today is {today}).")
        log("       Refusing to post-date a release — that is what put "
            "GlyphViz20260729.zip on the server three days early.")
        return 2

    wanted = []
    if not args.examples_only:
        wanted.append('app')
    if args.examples or args.examples_only:
        wanted.append('examples')

    out_root = args.out_root or mirror_root()
    if out_root is None:
        out_root = REPO / 'release'
        log(f"NOTE: no iluvdata mirror found; publishing to {out_root} instead.")

    log('=' * 62)
    log(f" GlyphViz release {args.date}")
    log('=' * 62)
    log(f"  artifacts : {', '.join(ARTIFACTS[k]['label'] for k in wanted)}")
    log(f"  publish to: {out_root}")
    log(f"  docs      : {'skipped' if args.no_docs else 'will be re-stamped'}")
    if args.dry_run:
        log("  DRY RUN — nothing will be built, written, or published.")
    log()

    # --- 1. build -------------------------------------------------------
    if 'app' in wanted and not args.skip_build:
        log("[1] Building the Windows app (PyInstaller)...")
        if args.dry_run:
            log("    (dry run — skipped)")
        else:
            try:
                run_build()
            except subprocess.CalledProcessError as exc:
                log(f"BUILD FAILED (exit {exc.returncode}). Nothing published.")
                return 1
        log()
    elif 'app' in wanted:
        log("[1] Build skipped (--skip-build); re-using dist/GlyphViz as is.")
        log()

    # --- 2. archive + publish -------------------------------------------
    sizes = {}
    for key in wanted:
        spec = ARTIFACTS[key]
        source = spec['source']
        if not source.is_dir():
            log(f"ERROR: {source} does not exist — nothing to archive.")
            return 1
        dest_dir = out_root / spec['subdir']
        dest = dest_dir / archive_name(spec, args.date)
        log(f"[2] Archiving the {spec['label']}: {source.name}/ -> {dest.name}")
        # Only a DATED archive is guarded: its name identifies one published
        # release, so overwriting it is a mistake worth blocking. An undated
        # one has a single stable URL and overwriting in place is the point.
        if (spec.get('dated', True) and dest.exists()
                and not args.force and not args.dry_run):
            log(f"ERROR: {dest} already exists. Re-run with --force to overwrite,")
            log("       or pass a different --date.")
            return 1
        if args.dry_run:
            entries = list(walk_files(source))
            total = sum(p.stat().st_size for p, _ in entries)
            log(f"    would zip {len(entries)} files ({mib(total)} MB) -> {dest}")
            sizes[key] = (0, total)
        else:
            dest_dir.mkdir(parents=True, exist_ok=True)
            sizes[key] = make_zip(source, dest)
            zip_bytes, raw_bytes = sizes[key]
            log(f"    {dest}")
            log(f"    {mib(zip_bytes)} MB download, {mib(raw_bytes)} MB extracted")
        log()

    # --- 3. docs --------------------------------------------------------
    if not args.no_docs:
        log("[3] Re-stamping the docs...")
        edits = []
        if 'app' in wanted:
            edits.append(('app archive name/URL', APP_STAMP_RE,
                          f'GlyphViz{args.date}'))
            if not args.dry_run:
                zip_bytes, raw_bytes = sizes['app']
                edits.append((
                    'app size + build date', APP_SIZE_RE,
                    rf'\g<1>{mib(zip_bytes)}\g<2>{mib(raw_bytes)}'
                    rf'\g<3>{stamp_date.isoformat()}'))
        if 'examples' in wanted:
            # No name/URL edit: GlyphViz_Examples.zip is a fixed name, so the
            # links never move and only the size line needs restating.
            if not args.dry_run:
                zip_bytes, raw_bytes = sizes['examples']
                edits.append((
                    'examples size', EXAMPLES_SIZE_RE,
                    rf'\g<1>{mib(zip_bytes)}\g<2>{mib(raw_bytes)}\g<3>'))
        if not rewrite_docs(edits, args.dry_run):
            log("Docs NOT updated. The archive is published but the download "
                "links still point at the previous release — fix and re-run "
                "with --skip-build.")
            return 1
        log()

    # --- 4. docs site ---------------------------------------------------
    site_published = False
    if not args.no_docs and not args.no_docs_build:
        log("[4] Building the docs site (mkdocs build)...")
        # MkDocs lives in glyphviz-docs/.venv, NOT the glyphviz conda env, and
        # must run from the folder holding mkdocs.yml. Using sys.executable
        # here would fail with "No module named mkdocs".
        docs_dir = REPO / 'glyphviz-docs'
        docs_python = docs_dir / '.venv' / 'Scripts' / 'python.exe'
        site = site_dir()
        if not docs_python.exists():
            log(f"    ERROR: no docs venv at {docs_python}")
            log("    Create it, or re-run with --no-docs-build and build by hand.")
            return 1
        if site is None:
            log("    ERROR: no site_dir in glyphviz-docs/mkdocs.yml.")
            return 1
        if args.dry_run:
            log(f"    (dry run — would run {docs_python} -m mkdocs build)")
            log(f"    (dry run — would publish {site} -> {out_root})")
        else:
            try:
                subprocess.run([str(docs_python), '-m', 'mkdocs', 'build'],
                               cwd=docs_dir, check=True)
            except subprocess.CalledProcessError as exc:
                log(f"    mkdocs build failed (exit {exc.returncode}).")
                return 1
            log(f"    built into {site}")
            log()
            # The zips published in step 2 live under out_root, so the site has
            # to land there too — one folder to upload, pages and downloads in
            # agreement. Merge-copy, never mirror-with-delete: the build output
            # does not contain versions/ or examples/*.zip.
            log(f"[5] Publishing the site into {out_root}...")
            n = publish_site(site, out_root)
            log(f"    {n} files copied (release zips left in place)")
            site_published = True
        log()

    # --- what's left for a human ----------------------------------------
    log('=' * 62)
    if site_published:
        log(" Done. Everything to upload is in one folder:")
        log(f"   {out_root}")
        log("       -> https://iluvdata.org/glyphviz/")
        log("   (then commit the docs change)")
    else:
        log(" Done. To publish:")
        for key in wanted:
            spec = ARTIFACTS[key]
            log(f"   upload {out_root / spec['subdir'] / archive_name(spec, args.date)}")
            log(f"       -> https://iluvdata.org/glyphviz/{spec['subdir']}/")
        if not args.no_docs:
            log("   commit the docs change, rebuild the site, upload it")
    log('=' * 62)
    return 0


if __name__ == '__main__':
    sys.exit(main())
