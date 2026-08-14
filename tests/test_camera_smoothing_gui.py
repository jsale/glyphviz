"""
Camera smoothing — Properties panel wiring.

The filter math is pinned in tests/test_camera_smoothing.py and the viewport
contract in tests/test_camera_smoothing_viewport.py; what's pinned here is
that the panel actually reaches them — the slider carries the right units, the
Off/ANTz presets land on the exact constants, and the scope combo passes a
real scope value rather than an index.

Qt is needed but a GL context is not — same arrangement as
tests/test_topo_scale_gui.py, so these keep running on a box with no
framebuffer.
"""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtWidgets import QApplication              # noqa: E402

from glyphviz_core import camera_smoothing as cs        # noqa: E402
from glyphviz_gl import main_window as mw               # noqa: E402


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication([])
        except Exception as exc:                        # pragma: no cover
            pytest.skip(f'Qt unavailable: {exc}')
    return app


@pytest.fixture
def win(qapp):
    return mw.MainWindow()


def test_starts_off(win):
    """The default has to be off — that is the whole compatibility argument."""
    assert win._cam_smooth_slider.value() == 0
    assert win._viewport.camera_smoothing_tau == cs.TAU_OFF
    assert win._cam_smooth_label.text() == 'Smoothing: Off'


def test_scope_combo_is_disabled_while_off(win):
    """Nothing to scope when there is no smoothing."""
    assert not win._cam_smooth_scope.isEnabled()


def test_slider_units_are_hundredths_of_a_second(win):
    win._cam_smooth_slider.setValue(25)
    assert win._viewport.camera_smoothing_tau == pytest.approx(0.25)
    assert win._cam_smooth_label.text() == 'Smoothing: 0.25 s'


def test_slider_range_covers_off_to_tau_max(win):
    assert win._cam_smooth_slider.minimum() == 0
    assert win._cam_smooth_slider.maximum() == int(round(cs.TAU_MAX * 100))


def test_antz_preset_lands_on_the_constant(win):
    """The preset must mean ANTz's actual time constant, not whatever the
    slider's integer resolution rounds it to."""
    win._set_camera_smoothing_tau(cs.TAU_ANTZ)
    assert win._viewport.camera_smoothing_tau == pytest.approx(cs.TAU_ANTZ, abs=0.005)
    assert '(ANTz)' in win._cam_smooth_label.text()


def test_off_preset_turns_it_off(win):
    win._set_camera_smoothing_tau(cs.TAU_ANTZ)
    win._set_camera_smoothing_tau(cs.TAU_OFF)
    assert win._viewport.camera_smoothing_tau == cs.TAU_OFF
    assert win._cam_smooth_slider.value() == 0


def test_off_preset_is_idempotent(win):
    """Pressing Off when already off must still be a valid no-op — setValue
    does not fire when the slider is already there."""
    win._set_camera_smoothing_tau(cs.TAU_OFF)
    assert win._viewport.camera_smoothing_tau == cs.TAU_OFF


def test_scope_combo_enables_with_the_slider(win):
    win._cam_smooth_slider.setValue(25)
    assert win._cam_smooth_scope.isEnabled()
    win._cam_smooth_slider.setValue(0)
    assert not win._cam_smooth_scope.isEnabled()


def test_scope_combo_carries_real_scope_values(win):
    """The combo stores scope constants as item data — an index would silently
    become an invalid scope and get ignored by set_camera_smoothing."""
    assert win._cam_smooth_scope.itemData(0) == cs.SCOPE_COMBO
    assert win._cam_smooth_scope.itemData(1) == cs.SCOPE_ALL


def test_scope_combo_reaches_the_viewport(win):
    win._cam_smooth_slider.setValue(25)
    win._cam_smooth_scope.setCurrentIndex(1)
    assert win._viewport.camera_smoothing_scope == cs.SCOPE_ALL
    win._cam_smooth_scope.setCurrentIndex(0)
    assert win._viewport.camera_smoothing_scope == cs.SCOPE_COMBO


def test_scope_survives_an_amount_change(win):
    """Changing the slider must not reset the scope back to the default."""
    win._cam_smooth_slider.setValue(25)
    win._cam_smooth_scope.setCurrentIndex(1)
    win._cam_smooth_slider.setValue(40)
    assert win._viewport.camera_smoothing_scope == cs.SCOPE_ALL
