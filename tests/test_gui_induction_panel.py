from __future__ import annotations

from pathlib import Path


def _offscreen_plugin_available() -> tuple[bool, str]:
    import sys

    from PySide6.QtCore import QLibraryInfo

    plugins_path = Path(QLibraryInfo.path(QLibraryInfo.PluginsPath))
    platforms_dir = plugins_path / "platforms"
    if not platforms_dir.exists():
        return False, f"Qt platforms dir not found: {platforms_dir}"

    if sys.platform.startswith("win"):
        candidates = ["qoffscreen.dll"]
    elif sys.platform == "darwin":
        candidates = ["libqoffscreen.dylib"]
    else:
        candidates = ["libqoffscreen.so"]

    for name in candidates:
        if (platforms_dir / name).exists():
            return True, ""
    return False, f"Qt platform plugin 'offscreen' not found in {platforms_dir}"


def _make_window(monkeypatch):
    import os
    import pytest

    pytest.importorskip("PySide6")
    pytest.importorskip("pyqtgraph")

    ok, reason = _offscreen_plugin_available()
    if not ok:
        pytest.skip(reason)

    if not os.environ.get("QT_QPA_PLATFORM"):
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication
    from gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    return app, window


def test_gui_turbo_induction_panel_uses_turbo_block(monkeypatch) -> None:
    from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QTextEdit

    from core.engine_components import Engine

    app, window = _make_window(monkeypatch)
    try:
        preset_path = Path(__file__).resolve().parents[1] / "presets" / "swift.json"
        window.engine = Engine.load_from_file(str(preset_path))
        window.refresh_tree()
        window.update_overview()
        app.processEvents()

        assert "Turbo" in window.induction_tree_item.text(0)
        assert "Turbo" in window.overview_subtitle_label.text()
        assert "Naturally Aspirated" not in window.overview_subtitle_label.text()
        assert "Turbo" in window._quick_dyno_engine_name()

        window.navigation_tree.setCurrentItem(window.induction_tree_item)
        window.update_properties_panel(window.induction_tree_item)
        app.processEvents()

        mode_combo = window.property_widget.findChild(QComboBox)
        assert mode_combo is not None
        assert mode_combo.currentText() == "Turbo"
        assert len(window.property_widget.findChildren(QTextEdit)) == 3

        mode_combo.setCurrentText("Roots")
        app.processEvents()
        assert window.engine.turbo.enabled is False
        assert window.engine.supercharger.type == "Roots"
        assert "Roots" in window.induction_tree_item.text(0)

        roots_boost_spin = window.property_widget.findChild(QDoubleSpinBox)
        assert roots_boost_spin is not None
        roots_boost_spin.setValue(0.85)
        roots_boost_spin.editingFinished.emit()
        app.processEvents()
        assert window.engine.supercharger.boost_pressure_bar == 0.85

        mode_combo = window.property_widget.findChild(QComboBox)
        assert mode_combo is not None
        mode_combo.setCurrentText("Turbo")
        app.processEvents()

        assert window.engine.turbo.enabled is True
        assert window.engine.supercharger.type == "NA"
        assert window.engine.supercharger.boost_pressure_bar == 0.0
        assert "Turbo" in window.overview_subtitle_label.text()
        assert len(window.property_widget.findChildren(QTextEdit)) == 3
    finally:
        window.close()
        app.processEvents()
