"""Command-line entry point for GlyphViz (``glyphviz`` on PATH after
``pip install -e .``).

Deliberately argparse-first: ``--version`` and ``--help`` answer before Qt or
OpenGL are imported, so they still work on a machine where the GUI stack is
the thing that's broken. ``--check`` is the diagnostic for exactly that case —
it brings up an offscreen GL context and prints what the driver reports, which
is the fastest way to find out whether a given Mac or Linux box can render
GlyphViz's fixed-function pipeline at all.
"""
from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path

from glyphviz_core import __version__

# A minimal scene in the native 20-column authoring dialect: one Sphere-topology
# parent with children placed on its surface by longitude/latitude. Small enough
# to read at a glance, but it exercises the loader, the topology placement math,
# and the renderer together — which is the point of a smoke-test scene.
_DEMO_ROWS = [
    # id type parent branch  tx    ty   tz   rx ry rz  sx  sy  sz    r    g    b   a  geo hide topo
    (1, 5, 0, 0, 0.0, 0.0, 0.0, 0, 0, 0, 6.0, 6.0, 6.0, 40, 60, 90, 255, 3, 0, 2),
    (2, 5, 1, 1, 0.0, 0.0, 0.0, 0, 0, 0, 1.0, 1.0, 1.0, 220, 70, 70, 255, 7, 0, 0),
    (3, 5, 1, 1, 60.0, 0.0, 0.0, 0, 0, 0, 1.0, 1.0, 1.0, 240, 150, 50, 255, 7, 0, 0),
    (4, 5, 1, 1, 120.0, 0.0, 0.0, 0, 0, 0, 1.0, 1.0, 1.0, 240, 220, 60, 255, 7, 0, 0),
    (5, 5, 1, 1, 180.0, 0.0, 0.0, 0, 0, 0, 1.0, 1.0, 1.0, 110, 210, 90, 255, 7, 0, 0),
    (6, 5, 1, 1, 240.0, 0.0, 0.0, 0, 0, 0, 1.0, 1.0, 1.0, 70, 190, 200, 255, 7, 0, 0),
    (7, 5, 1, 1, 300.0, 0.0, 0.0, 0, 0, 0, 1.0, 1.0, 1.0, 120, 120, 230, 255, 7, 0, 0),
    (8, 5, 1, 1, 30.0, 45.0, 0.0, 0, 0, 0, 0.8, 0.8, 0.8, 200, 200, 220, 255, 2, 0, 0),
    (9, 5, 1, 1, 150.0, 45.0, 0.0, 0, 0, 0, 0.8, 0.8, 0.8, 200, 200, 220, 255, 2, 0, 0),
    (10, 5, 1, 1, 270.0, 45.0, 0.0, 0, 0, 0, 0.8, 0.8, 0.8, 200, 200, 220, 255, 2, 0, 0),
    (11, 5, 1, 1, 90.0, -45.0, 0.0, 0, 0, 0, 0.8, 0.8, 0.8, 200, 200, 220, 255, 2, 0, 0),
    (12, 5, 1, 1, 210.0, -45.0, 0.0, 0, 0, 0, 0.8, 0.8, 0.8, 200, 200, 220, 255, 2, 0, 0),
    (13, 5, 1, 1, 330.0, -45.0, 0.0, 0, 0, 0, 0.8, 0.8, 0.8, 200, 200, 220, 255, 2, 0, 0),
]

_DEMO_HEADER = (
    "id,type,parent_id,branch_level,translate_x,translate_y,translate_z,"
    "rotate_x,rotate_y,rotate_z,scale_x,scale_y,scale_z,"
    "color_r,color_g,color_b,color_a,geometry,hide,topo"
)


def _write_demo_scene() -> Path:
    """Write the built-in demo scene to a temp CSV and return its path.

    Routed through a real file rather than constructed as Node objects so
    ``--demo`` exercises the same load path File > Open does.
    """
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="glyphviz-demo-")) / "demo_gv_node.csv"
    lines = [_DEMO_HEADER]
    lines += [",".join(str(v) for v in row) for row in _DEMO_ROWS]
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmp


def _run_check() -> int:
    """Print an environment report, including what the OpenGL driver says.

    Returns a process exit code: 0 if a usable GL context came up, 1 if not.
    """
    print(f"GlyphViz          {__version__}")
    print(f"Python            {sys.version.split()[0]} ({sys.executable})")
    print(f"Platform          {platform.platform()}")
    print(f"Machine           {platform.machine()}")
    if sys.platform == "darwin":
        print(f"macOS release     {platform.mac_ver()[0]}")

    try:
        import PySide6
        from PySide6.QtCore import qVersion
        print(f"PySide6           {PySide6.__version__} (Qt {qVersion()})")
    except Exception as exc:                      # noqa: BLE001 - report, don't raise
        print(f"PySide6           NOT AVAILABLE: {exc}")
        return 1

    try:
        import OpenGL
        print(f"PyOpenGL          {OpenGL.__version__}")
    except Exception as exc:                      # noqa: BLE001
        print(f"PyOpenGL          NOT AVAILABLE: {exc}")
        return 1

    # An offscreen surface is enough to interrogate the driver and avoids
    # flashing a window up just to run a check.
    from PySide6.QtGui import QOffscreenSurface, QOpenGLContext, QSurfaceFormat
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])
    surface = QOffscreenSurface()
    surface.setFormat(QSurfaceFormat.defaultFormat())
    surface.create()
    ctx = QOpenGLContext()
    ctx.setFormat(surface.format())
    if not ctx.create() or not ctx.makeCurrent(surface):
        print("OpenGL            FAILED to create a context")
        print("\nGlyphViz needs a working OpenGL 2.1-era (fixed-function) context.")
        return 1

    from OpenGL.GL import (GL_RENDERER, GL_SHADING_LANGUAGE_VERSION, GL_VENDOR,
                           GL_VERSION, glGetString)

    def _s(enum) -> str:
        raw = glGetString(enum)
        return raw.decode("utf-8", "replace") if raw else "(unavailable)"

    print(f"GL vendor         {_s(GL_VENDOR)}")
    print(f"GL renderer       {_s(GL_RENDERER)}")
    print(f"GL version        {_s(GL_VERSION)}")
    print(f"GLSL version      {_s(GL_SHADING_LANGUAGE_VERSION)}")
    fmt = ctx.format()
    print(f"Context profile   {fmt.profile().name} {fmt.majorVersion()}.{fmt.minorVersion()}")

    # GlyphViz draws with display lists and glBegin/glEnd, so a core profile
    # would compile fine and then render nothing -- worth calling out loudly.
    if fmt.profile() == QSurfaceFormat.OpenGLContextProfile.CoreProfile:
        print("\nWARNING: this is a CORE profile context. GlyphViz's renderer uses the\n"
              "fixed-function pipeline, which core profiles remove. Rendering will\n"
              "likely be blank. A legacy/compatibility 2.1 context is what's wanted.")
        ctx.doneCurrent()
        return 1

    print("\nOpenGL context OK - GlyphViz's fixed-function renderer should work here.")
    ctx.doneCurrent()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="glyphviz",
        description="GlyphViz - 3D node-graph visualizer for ANTz/GaiaViz-style CSV scenes.",
    )
    p.add_argument("csv", nargs="?", help="node CSV to open on launch")
    p.add_argument("--version", action="version", version=f"GlyphViz {__version__}")
    p.add_argument("--demo", action="store_true",
                   help="launch with a small built-in scene instead of an empty window")
    p.add_argument("--check", action="store_true",
                   help="print an environment/OpenGL report and exit (no window)")
    return p


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        # Finder can hand a bundled app a "-psn_0_12345" process-serial-number
        # argument; argparse would exit(2) on it before the window ever opens.
        argv = [a for a in sys.argv[1:] if not a.startswith("-psn_")]
    args = build_parser().parse_args(argv)

    if args.check:
        return _run_check()

    # Deferred so --version/--help/--check stay usable when the GUI stack isn't.
    from glyphviz_gl.main_window import MainWindow

    app = _build_application()

    win = MainWindow()
    win.show()
    app.set_window(win)

    path = args.csv
    if args.demo:
        if path:
            print("--demo overrides the CSV argument", file=sys.stderr)
        path = str(_write_demo_scene())

    if path:
        target = Path(path).expanduser()
        if not target.is_file():
            print(f"glyphviz: no such file: {target}", file=sys.stderr)
            return 2
        win._load_csv_path(str(target.resolve()))

    return app.exec()


def _build_application():
    """Construct the QApplication.

    Subclassed rather than monkey-patched: Qt dispatches ``event()`` through
    the C++ virtual, and PySide6 only routes that back into Python for methods
    defined on a subclass — assigning ``app.event = ...`` on an instance would
    silently never be called.
    """
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    class GlyphVizApplication(QApplication):
        """QApplication that honors macOS "open with GlyphViz" file events.

        macOS delivers a Finder double-click or a drop on the Dock icon as a
        QFileOpenEvent rather than an argv entry, and it can arrive before the
        main window exists — hence the queue.
        """

        def __init__(self, argv):
            super().__init__(argv)
            self._win = None
            self._pending: list[str] = []

        def set_window(self, win) -> None:
            self._win = win
            for local in self._pending:
                win._load_csv_path(local)
            self._pending.clear()

        def event(self, ev):
            if ev.type() == QEvent.Type.FileOpen:
                local = ev.file() or ev.url().toLocalFile()
                if local:
                    if self._win is None:
                        self._pending.append(local)
                    else:
                        self._win._load_csv_path(local)
                    return True
            return super().event(ev)

    app = GlyphVizApplication(sys.argv)
    app.setApplicationName("GlyphViz")
    app.setOrganizationName("GlyphViz")
    app.setApplicationVersion(__version__)
    return app


if __name__ == "__main__":
    sys.exit(main())
