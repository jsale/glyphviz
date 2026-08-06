"""GlyphViz presentation-independent kernel.

Kept import-light on purpose: pyproject.toml reads ``__version__`` from here
via setuptools' ``attr:`` directive, which parses this file without importing
the heavy dependencies (numpy/pandas) the submodules pull in.

The version follows the dated release convention the Windows builds already
use (GlyphViz20260806 -> 2026.8.6), normalized to PEP 440.
"""

__version__ = "2026.8.6"
