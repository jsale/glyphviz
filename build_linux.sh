#!/usr/bin/env bash
#
# build_linux.sh — build GlyphViz for Linux: a one-folder PyInstaller build,
# packaged both as a .tar.gz (extract-and-run) and a .AppImage
# (download-chmod-run, no extraction needed).
#
# Unlike build.bat (gitignored — it bakes in a machine-local conda path),
# this script derives everything it needs, so it's tracked, same as
# build_mac.sh.
#
#   ./build_linux.sh              # build into a throwaway venv at .venv-build
#   ./build_linux.sh --keep-venv  # reuse .venv-build if it already exists
#   ./build_linux.sh --no-appimage  # skip the AppImage step (tar.gz only)
#
# Output:
#   dist/GlyphViz/                                   (raw onedir build)
#   dist/GlyphViz-<version>-Linux-<arch>.tar.gz
#   dist/GlyphViz-<version>-Linux-<arch>.AppImage

set -euo pipefail

cd "$(dirname "$0")"

VENV=.venv-build
KEEP_VENV=0
BUILD_APPIMAGE=1
for arg in "$@"; do
  case "$arg" in
    --keep-venv)   KEEP_VENV=1 ;;
    --no-appimage) BUILD_APPIMAGE=0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

PYTHON="${GLYPHVIZ_PYTHON:-python3}"
if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "error: need Python 3.10+ (found: $("$PYTHON" --version 2>&1))" >&2
  exit 1
fi

ARCH="$(uname -m)"
echo "==> Building GlyphViz for Linux/$ARCH with $("$PYTHON" --version 2>&1)"

if [ "$KEEP_VENV" -eq 0 ] || [ ! -d "$VENV" ]; then
  rm -rf "$VENV"
  "$PYTHON" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

python -m pip install --upgrade pip wheel >/dev/null
python -m pip install -e ".[build]"

echo "==> PySide6 $(python -c 'import PySide6; print(PySide6.__version__)')"

rm -rf build dist
python -m PyInstaller GlyphViz-Linux.spec --clean -y

VERSION="$(python -c 'from glyphviz_core import __version__; print(__version__)')"
BASE="GlyphViz-${VERSION}-Linux-${ARCH}"

echo "==> Smoke test"
dist/GlyphViz/GlyphViz --version
dist/GlyphViz/GlyphViz --check || echo "    (--check failed; expected on a machine with no GL driver)"

echo "==> Packaging tar.gz"
# Contains a top-level GlyphViz/ folder (unlike the Windows zip's
# contents-first layout — that convention is release.py's, driven by its own
# tooling, and not worth replicating here) so extracting into a shared
# directory like ~/Downloads can't scatter GlyphViz/_internal loose.
tar -czf "dist/${BASE}.tar.gz" -C dist GlyphViz
echo "    dist/${BASE}.tar.gz"

if [ "$BUILD_APPIMAGE" -eq 1 ]; then
  echo "==> Building AppImage"

  APPIMAGETOOL="dist/appimagetool-${ARCH}.AppImage"
  if [ ! -x "$APPIMAGETOOL" ]; then
    curl -fL -o "$APPIMAGETOOL" \
      "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${ARCH}.AppImage"
    chmod +x "$APPIMAGETOOL"
  fi

  APPDIR="dist/AppDir"
  rm -rf "$APPDIR"
  mkdir -p "$APPDIR/usr/bin"
  cp -a dist/GlyphViz "$APPDIR/usr/bin/GlyphViz"

  cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "${0}")")"
exec "$HERE/usr/bin/GlyphViz/GlyphViz" "$@"
EOF
  chmod +x "$APPDIR/AppRun"

  cat > "$APPDIR/glyphviz.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=GlyphViz
Comment=3D node-graph visualizer for ANTz/GaiaViz-style CSV scene data
Exec=GlyphViz
Icon=glyphviz
Categories=Graphics;Science;Viewer;
Terminal=false
EOF

  cp glyphviz-docs/docs/assets/brand/favicon-180.png "$APPDIR/glyphviz.png"

  # FUSE is frequently unavailable in CI/container environments; this env var
  # tells appimagetool's own AppImage runtime (not the build step below,
  # which always extracts-and-runs regardless) to fall back the same way at
  # launch time if the *user's* machine also lacks FUSE.
  export APPIMAGE_EXTRACT_AND_RUN=1
  "$APPIMAGETOOL" --appimage-extract-and-run "$APPDIR" "dist/${BASE}.AppImage" 2>/dev/null \
    || "$APPIMAGETOOL" "$APPDIR" "dist/${BASE}.AppImage"
  chmod +x "dist/${BASE}.AppImage"
  echo "    dist/${BASE}.AppImage"
fi

echo
echo "==> Done."
echo "    Raw build : dist/GlyphViz/"
echo "    tar.gz    : dist/${BASE}.tar.gz"
if [ "$BUILD_APPIMAGE" -eq 1 ]; then
  echo "    AppImage  : dist/${BASE}.AppImage"
fi
