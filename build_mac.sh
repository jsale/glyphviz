#!/usr/bin/env bash
#
# build_mac.sh — build GlyphViz.app on macOS.
#
# Unlike build.bat (which is gitignored because it bakes in a machine-local
# conda path), this script derives everything it needs, so it is tracked.
#
#   ./build_mac.sh              # build into a throwaway venv at .venv-build
#   ./build_mac.sh --latest     # use the newest PySide6 instead of the pinned one
#   ./build_mac.sh --keep-venv  # reuse .venv-build if it already exists
#
# Output:
#   dist/GlyphViz.app
#   dist/GlyphViz-<version>-macOS-<arch>.zip   (made with ditto, see below)

set -euo pipefail

cd "$(dirname "$0")"

# ---------------------------------------------------------------------------
# PySide6 pin
#
# Which PySide6 you build against IS the app's macOS floor, because the wheel's
# platform tag is the floor:
#
#   PySide6 6.7.x  -> macosx_11_0   (Big Sur and later)
#   PySide6 6.8-6.9 -> macosx_12_0  (Monterey and later)
#   PySide6 6.10+  -> macosx_13_0   (Ventura and later)
#
# Pinned to 6.7.x by default so the build reaches the oldest Macs Qt 6 has ever
# supported via wheels. Pass --latest to build against current PySide6 instead
# (newer Qt, but Ventura+ only). No PySide6 has EVER shipped a wheel that runs
# on macOS 10.13 High Sierra — 10.14 was the lowest tag, on Qt 6.0-6.2.
#
# numpy/scipy need pinning for the same goal, for a sneakier reason: recent
# releases publish TWO macOS wheels per arch (e.g. macosx_11_0_arm64 AND a
# macosx_14_0 Accelerate variant), and pip picks the newest one the *build*
# machine supports — so building on a new Mac silently raises the app's floor
# to 14. numpy<2 / scipy<1.14 are the last series with a single old-floor
# wheel per arch (Intel 10.9; arm64 11.0/12.0), making the floor deterministic:
#   Intel x86_64 build -> macOS 11 (set by PySide6)
#   arm64 build        -> macOS 12 (set by scipy; every Apple Silicon Mac can run 12)
# pandas/Pillow publish no such variants and float at 10.13/11.0 — left unpinned.
# ---------------------------------------------------------------------------
PYSIDE_SPEC='PySide6>=6.7,<6.8'
COMPAT_PINS='numpy<2 scipy<1.14'

VENV=.venv-build
KEEP_VENV=0
for arg in "$@"; do
  case "$arg" in
    --latest)    PYSIDE_SPEC='PySide6>=6.7'; COMPAT_PINS='' ;;
    --keep-venv) KEEP_VENV=1 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

PYTHON="${GLYPHVIZ_PYTHON:-python3}"
if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "error: need Python 3.10+ (found: $("$PYTHON" --version 2>&1))" >&2
  exit 1
fi

ARCH="$(uname -m)"
echo "==> Building GlyphViz for macOS/$ARCH with $("$PYTHON" --version 2>&1)"

if [ "$KEEP_VENV" -eq 0 ] || [ ! -d "$VENV" ]; then
  rm -rf "$VENV"
  "$PYTHON" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

python -m pip install --upgrade pip wheel >/dev/null
# Pins first so they win over pyproject's floors during resolution.
# shellcheck disable=SC2086  # COMPAT_PINS is intentionally word-split
python -m pip install "$PYSIDE_SPEC" $COMPAT_PINS
python -m pip install -e ".[build]"

echo "==> PySide6 $(python -c 'import PySide6; print(PySide6.__version__)')"

rm -rf build dist
python -m PyInstaller GlyphViz-macOS.spec --clean -y

VERSION="$(python -c 'from glyphviz_core import __version__; print(__version__)')"
ZIP="dist/GlyphViz-${VERSION}-macOS-${ARCH}.zip"

# ditto, not zip: `zip` mangles the symlinks inside Qt's .framework bundles and
# drops extended attributes, which invalidates the code signature — the app
# then dies with "damaged and can't be opened" after a round trip.
ditto -c -k --sequesterRsrc --keepParent dist/GlyphViz.app "$ZIP"

echo
echo "==> Built dist/GlyphViz.app  ->  $ZIP"
echo "    codesign check:"
codesign --verify --deep --verbose=2 dist/GlyphViz.app 2>&1 | sed 's/^/    /' || true
echo
echo "    This build is ad-hoc signed, not notarized. Anyone who downloads the"
echo "    zip must clear the quarantine flag before first launch:"
echo "        xattr -dr com.apple.quarantine /path/to/GlyphViz.app"
