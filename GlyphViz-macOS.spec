# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for GlyphViz on macOS — produces a real .app bundle.
#
# Build:
#   ./build_mac.sh                       (recommended; creates the venv too)
#   or, in an env that already has the deps:
#   python -m PyInstaller GlyphViz-macOS.spec --clean -y
#
# Output: dist/GlyphViz.app
#
# This is a SEPARATE spec from GlyphViz.spec (Windows) rather than a
# platform-branching one. The Windows spec is almost entirely conda-DLL
# surgery — the libexpat alias, the eight Library\bin binaries, the ICU
# blacklist — none of which has a macOS analogue. Folding both into one file
# would mean two disjoint bodies behind an `if sys.platform` with nothing
# shared but the entry-script name.
#
# ARCHITECTURE: builds for whatever Mac runs it (arm64 on Apple Silicon,
# x86_64 on Intel). target_arch='universal2' is deliberately NOT set: numpy,
# pandas, and scipy publish separate arm64 and x86_64 wheels rather than
# universal2 ones, so PyInstaller cannot assemble a universal binary from
# them. Ship one .app per architecture (see .github/workflows/build-macos.yml).

import sys

# SPECPATH is injected by PyInstaller and is this file's directory. The spec is
# exec'd with a sys.path that doesn't necessarily include the repo root, so add
# it before reading the version off the package.
if SPECPATH not in sys.path:
    sys.path.insert(0, SPECPATH)

from glyphviz_core import __version__ as GLYPHVIZ_VERSION

# The wheel's platform tag sets the real floor (PySide6 6.7.x is
# macosx_11_0_universal2); this only tells Finder/Gatekeeper the same thing.
MIN_MACOS = '11.0'

a = Analysis(
    ['main.py'],
    pathex=[],
    # Nothing here. macOS resolves Qt's frameworks and the Python shared
    # library through the wheels' own rpaths, so there's no equivalent of the
    # Windows spec's hand-listed conda DLLs.
    binaries=[],
    datas=[],
    hiddenimports=[
        # PyOpenGL picks its platform backend at runtime from os.name/sys.platform;
        # PyInstaller can't see that statically. 'darwin' is the macOS backend —
        # the counterpart of 'win32' in the Windows spec.
        'OpenGL.platform.darwin',
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
    # Same reasoning as the Windows spec: scipy (pdb_loader's cKDTree) and PIL
    # (basemap tile stitching) are NOT excluded — dropping either makes the
    # frozen app fail where `python main.py` works.
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
    # UPX is not used on macOS at all — it breaks code signing outright.
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    # Ad-hoc signature (PyInstaller's default when no identity is given).
    # NOT optional on Apple Silicon: arm64 refuses to execute an unsigned
    # binary, so an unsigned build would fail to launch rather than merely
    # warn. Set a Developer ID here to produce a notarizable build.
    codesign_identity=None,
    entitlements_file=None,
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

app = BUNDLE(
    coll,
    name='GlyphViz.app',
    icon=None,
    bundle_identifier='org.iluvdata.glyphviz',
    version=GLYPHVIZ_VERSION,
    info_plist={
        'CFBundleName': 'GlyphViz',
        'CFBundleDisplayName': 'GlyphViz',
        'CFBundleShortVersionString': GLYPHVIZ_VERSION,
        'CFBundleVersion': GLYPHVIZ_VERSION,
        'LSMinimumSystemVersion': MIN_MACOS,
        # Without this, macOS runs the app through the 2x upscaler and the
        # whole viewport looks soft on any Retina display.
        'NSHighResolutionCapable': True,
        # Qt Multimedia asks for the microphone the first time it initializes
        # an audio device; macOS kills the process outright if the plist has
        # no usage string to show.
        'NSMicrophoneUsageDescription':
            'GlyphViz uses audio playback for Channels animation and audio-driven scenes.',
        # Makes "Open With > GlyphViz" and Finder double-click work on node
        # CSVs. Handled by the QFileOpenEvent path in glyphviz_gl/cli.py —
        # macOS delivers these as events, never as argv.
        'CFBundleDocumentTypes': [{
            'CFBundleTypeName': 'GlyphViz Node CSV',
            'CFBundleTypeRole': 'Viewer',
            'LSHandlerRank': 'Alternate',
            'LSItemContentTypes': ['public.comma-separated-values-text'],
        }],
    },
)
