"""GlyphViz OpenGL presentation layer.

PyOpenGL configuration must happen here, before any submodule (or the XR
package, which imports glyphviz_gl.geometry) executes `from OpenGL.GL
import *` — PyOpenGL builds its call wrappers at import time, so flags set
after that point are silently ignored.

ERROR_CHECKING: by default PyOpenGL wraps every single GL call with a
glGetError() round-trip. Profiling on a real 8320-node scene showed this
was 51% of CPU frame time (glGetError can force a CPU-GPU pipeline sync,
so it compounds as GPU load grows) and disabling it alone took the scene
from 830 ms/frame to 252 ms/frame. We turn it off for normal runs and
keep a debug escape hatch: set GLYPHVIZ_GL_DEBUG=1 to restore full
per-call error checking when hunting a rendering bug.
"""
import os

import OpenGL

if not os.environ.get("GLYPHVIZ_GL_DEBUG"):
    OpenGL.ERROR_CHECKING = False
