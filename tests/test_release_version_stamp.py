"""tools/release.py step 0: stamp glyphviz_core.__version__ from --date.

The constant names the macOS and Linux CI artifacts, and it sat at 2026.8.30
through five Windows releases because nothing ever updated it. These pin the
stamp: the PEP 440 form, a real rewrite, and a refusal when the line is gone.
"""
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))

import release  # noqa: E402


def _version_file(tmp_path, value='2026.8.30'):
    p = tmp_path / '__init__.py'
    p.write_text('"""Docstring mentioning __version__ in prose."""\n\n'
                 f'__version__ = "{value}"\n', encoding='utf-8')
    return p


def test_the_version_is_the_date_without_leading_zeros():
    assert release.pep440_version(date(2026, 8, 6)) == '2026.8.6'
    assert release.pep440_version(date(2026, 12, 25)) == '2026.12.25'


def test_stamping_rewrites_only_the_version_line(tmp_path):
    p = _version_file(tmp_path)
    before = p.read_text(encoding='utf-8')
    assert release.stamp_version(date(2026, 9, 27), False, p) == ('2026.8.30', '2026.9.27')
    after = p.read_text(encoding='utf-8')
    assert after == before.replace('2026.8.30', '2026.9.27')


def test_a_dry_run_reports_but_writes_nothing(tmp_path):
    p = _version_file(tmp_path)
    before = p.read_text(encoding='utf-8')
    assert release.stamp_version(date(2026, 9, 27), True, p) == ('2026.8.30', '2026.9.27')
    assert p.read_text(encoding='utf-8') == before


def test_a_missing_version_line_stops_the_release(tmp_path):
    p = tmp_path / '__init__.py'
    p.write_text('VERSION = "2026.8.30"\n', encoding='utf-8')
    assert release.stamp_version(date(2026, 9, 27), False, p) is None


def test_the_real_file_is_in_the_shape_the_stamp_expects():
    old, new = release.stamp_version(date(2026, 9, 27), True)
    import glyphviz_core
    assert old == glyphviz_core.__version__
