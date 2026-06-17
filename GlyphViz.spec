# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for GlyphViz (Windows, one-folder output).
#
# Build:
#   conda run -n glyphviz python -m PyInstaller GlyphViz.spec --clean
#
# Output: dist\GlyphViz\GlyphViz.exe
#
# To add a Windows icon, set:
#   exe = EXE(..., icon='path\\to\\glyphviz.ico', ...)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
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
