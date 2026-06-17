# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for GlyphViz (Windows, one-folder output).
#
# Build:
#   build.bat   (or directly: C:\Users\jsale\anaconda3\envs\glyphviz\python.exe -m PyInstaller GlyphViz.spec --clean -y)
#
# Output: dist\GlyphViz\GlyphViz.exe
#
# To add a Windows icon, set:
#   exe = EXE(..., icon='path\\to\\glyphviz.ico', ...)

import shutil, os as _os

_CONDA = r'C:\Users\jsale\anaconda3\envs\glyphviz\Library\bin'

# pyexpat.pyd links against 'libexpat.dll' but conda ships 'expat.dll'.
# Create an alias so PyInstaller can bundle it under the expected name.
_expat_alias = _os.path.join(_CONDA, 'libexpat.dll')
if not _os.path.exists(_expat_alias):
    shutil.copy2(_os.path.join(_CONDA, 'expat.dll'), _expat_alias)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[
        # DLLs that live in conda's Library\bin — PyInstaller can't find them
        # automatically because they're not on PATH during analysis.
        (f'{_CONDA}\\ffi.dll',             '.'),
        (f'{_CONDA}\\ffi-8.dll',           '.'),
        (f'{_CONDA}\\libbz2.dll',          '.'),
        (f'{_CONDA}\\liblzma.dll',         '.'),
        (f'{_CONDA}\\libcrypto-3-x64.dll', '.'),
        (f'{_CONDA}\\libssl-3-x64.dll',    '.'),
        (f'{_CONDA}\\libexpat.dll',        '.'),
        (f'{_CONDA}\\sqlite3.dll',         '.'),
    ],
    datas=[],
    hiddenimports=[
        # PyOpenGL selects its platform backend at runtime via os.name;
        # PyInstaller cannot detect this statically.
        'OpenGL.platform.win32',
        'OpenGL.arrays.ctypesarrays',
        'OpenGL.arrays.numpymodule',
        'OpenGL.arrays.lists',
        'OpenGL.arrays.numbers',
        # Qt Multimedia — imported conditionally at runtime in video_manager.py
        'PySide6.QtMultimedia',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Exclude heavy packages that GlyphViz doesn't use
    excludes=['tkinter', 'matplotlib', 'scipy', 'PIL', 'IPython'],
    noarchive=False,
)

# PyInstaller's automatic dependency scan picks up icuuc.dll from wherever it
# finds a file with that name on PATH at build time -- on this machine that's
# the base Anaconda env's Library\bin, which ships a *C++* ICU library (mangled
# icu_73:: symbols) under that name. Qt6Core.dll's actual import is the plain
# C API (ucnv_open etc.), which that file does not export, so bundling it
# breaks the load with "specified procedure could not be found". The glyphviz
# env itself has no icu*.dll at all -- Qt6Core falls back to the small
# C-API shim Windows ships at System32\icuuc.dll, which does export the right
# symbols. Dropping the wrongly-matched copies (and their now-unneeded
# transitive icudt73.dll) lets that fallback happen, exactly as it already
# does for a normal (unfrozen) run of the app.
_BAD_BINARY_PREFIXES = ('icuuc', 'icudt', 'icuin')
a.binaries = [
    b for b in a.binaries
    if not _os.path.basename(b[0]).lower().startswith(_BAD_BINARY_PREFIXES)
]

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
    # UPX compression disabled — it can corrupt Qt DLLs
    upx=False,
    # console=False → no terminal window; a crash dialog will still appear
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
