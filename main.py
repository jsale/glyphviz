"""GlyphViz entry point.

Thin delegate to glyphviz_gl.cli so that `python main.py`, the frozen
executable (which runs this file), and the `glyphviz` console script installed
by `pip install -e .` all take exactly the same startup path — including the
macOS "open with GlyphViz" file-event handling.
"""
import sys

from glyphviz_gl.cli import main

if __name__ == "__main__":
    sys.exit(main())
