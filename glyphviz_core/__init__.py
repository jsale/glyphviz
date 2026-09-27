"""GlyphViz presentation-independent kernel.

Kept import-light on purpose: pyproject.toml reads ``__version__`` from here
via setuptools' ``attr:`` directive, which parses this file without importing
the heavy dependencies (numpy/pandas) the submodules pull in.

The version follows the dated release convention the Windows builds already
use (GlyphViz20260806 -> 2026.8.6), normalized to PEP 440. tools/release.py
stamps it from its --date on every app release, so don't hand-edit it for a
Windows build; the macOS and Linux CI builds name their artifacts from it.
"""

__version__ = "2026.9.27"
