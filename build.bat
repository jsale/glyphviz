@echo off
setlocal
echo ============================================================
echo  GlyphViz Windows build  (conda env: glyphviz)
echo ============================================================

set PYTHON=C:\Users\jsale\anaconda3\envs\glyphviz\python.exe

echo.
echo [1/2] Installing / updating PyInstaller...
"%PYTHON%" -m pip install --quiet --upgrade pyinstaller
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: pip install failed.
    exit /b 1
)

echo.
echo [2/2] Building...
"%PYTHON%" -m PyInstaller GlyphViz.spec --clean -y
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo BUILD FAILED.  Check the output above.
    exit /b 1
)

echo.
echo ============================================================
echo  Done.
echo  Executable : dist\GlyphViz\GlyphViz.exe
echo  Distribute : copy the entire dist\GlyphViz\ folder
echo ============================================================
endlocal
