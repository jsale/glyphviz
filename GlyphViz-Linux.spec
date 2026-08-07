# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for GlyphViz on Linux — produces a one-folder build,
# the same shape as the Windows dist/GlyphViz/GlyphViz.exe layout.
#
# Build:
#   ./build_linux.sh                     (recommended; creates the venv,
#                                          then also packages the .tar.gz
#                                          and the .AppImage)
#   or, in an env that already has the deps:
#   python -m PyInstaller GlyphViz-Linux.spec --clean -y
#
# Output: dist/GlyphViz/GlyphViz  (executable) + dist/GlyphViz/_internal/
#
# This is a SEPARATE spec from GlyphViz.spec (Windows) and GlyphViz-macOS.spec
# rather than a platform-branching one — same reasoning as the macOS spec's
# header: each platform's binary-collection quirks don't overlap enough to
# share a body behind `if sys.platform`.
#
# GLIBC FLOOR: unlike the Windows build (which links against whatever DLLs
# the build machine's conda env carries) and the macOS build (which pins
# numpy/scipy to hold the wheel floor down), the thing that sets a Linux
# build's minimum distro here is the manylinux tag on the PySide6/numpy/scipy
# wheels pip resolves at build time, together with the build machine's own
# glibc. build_linux.sh and build-linux.yml both build on an older Ubuntu LTS
# runner (22.04, glibc 2.35) rather than the newest available, to keep that
# floor as low as practical without pulling in a full manylinux container
# build. No specific older-glibc compatibility claim is made beyond that —
# if a report comes back that a specific older distro can't run the build,
# that's the point to pin wheel versions or move to a manylinux container.

import sys

# SPECPATH is injected by PyInstaller and is this file's directory. The spec is
# exec'd with a sys.path that doesn't necessarily include the repo root, so add
# it before reading the version off the package.
if SPECPATH not in sys.path:
    sys.path.insert(0, SPECPATH)

from glyphviz_core import __version__ as GLYPHVIZ_VERSION  # noqa: F401 (kept for parity with the other specs; read by build_linux.sh instead)

a = Analysis(
    ['main.py'],
    pathex=[],
    # Nothing here. Linux PySide6 wheels bundle their own Qt .so files and
    # locate them via an $ORIGIN rpath, so — like macOS — there's no
    # equivalent of the Windows spec's hand-listed conda DLLs. What is NOT
    # bundled, on any platform, is the actual GL driver: GlyphViz renders
    # through whatever libGL.so.1 / vendor driver the host already has
    # installed, same as it relies on the host's opengl32.dll on Windows.
    binaries=[],
    datas=[],
    hiddenimports=[
        # PyOpenGL picks its platform backend at runtime from sys.platform;
        # PyInstaller can't see that statically. GLX is the desktop-Linux/X11
        # backend (the counterpart of 'win32' and 'darwin' in the other two
        # specs); EGL is included too since it's what a Wayland-native or
        # otherwise-minimal windowing setup resolves to instead.
        'OpenGL.platform.glx',
        'OpenGL.platform.egl',
        'OpenGL.arrays.ctypesarrays',
        'OpenGL.arrays.numpymodule',
        'OpenGL.arrays.lists',
        'OpenGL.arrays.numbers',
        # Imported conditionally at runtime in video_manager.py / audio_player.py.
        'PySide6.QtMultimedia',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Same reasoning as the Windows and macOS specs: scipy (pdb_loader's
    # cKDTree) and PIL (basemap tile stitching) are NOT excluded — dropping
    # either makes the frozen build fail where `python main.py` works.
    excludes=['tkinter', 'matplotlib', 'IPython'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GlyphViz',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX is skipped here too — same Qt-corruption risk flagged in the
    # Windows spec, never verified safe on Linux's .so files either.
    upx=False,
    # console/windowed is a Windows-only distinction in PyInstaller; kept
    # False for parity with the other two specs, no functional effect here.
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='GlyphViz',
)
