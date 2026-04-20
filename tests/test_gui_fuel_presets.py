from __future__ import annotations


def _offscreen_plugin_available() -> tuple[bool, str]:
    from pathlib import Path
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


def _fuel_form_widgets(window):
    from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QFormLayout, QLineEdit

    window._build_fuel_form(window.engine.fuel)

    preset_combo = window.property_form.itemAt(0, QFormLayout.FieldRole).widget()
    fuel_type_edit = window.property_form.itemAt(1, QFormLayout.FieldRole).widget()
    octane_spin = window.property_form.itemAt(2, QFormLayout.FieldRole).widget()
    energy_spin = window.property_form.itemAt(3, QFormLayout.FieldRole).widget()
    afr_spin = window.property_form.itemAt(4, QFormLayout.FieldRole).widget()

    assert isinstance(preset_combo, QComboBox)
    assert isinstance(fuel_type_edit, QLineEdit)
    assert isinstance(octane_spin, QDoubleSpinBox)
    assert isinstance(energy_spin, QDoubleSpinBox)
    assert isinstance(afr_spin, QDoubleSpinBox)
    return preset_combo, fuel_type_edit, octane_spin, energy_spin, afr_spin


def test_gui_fuel_presets_prioritize_uruguay_options(monkeypatch) -> None:
    app, window = _make_window(monkeypatch)
    try:
        preset_combo, _, _, _, _ = _fuel_form_widgets(window)
        visible_items = [preset_combo.itemText(i) for i in range(preset_combo.count()) if preset_combo.itemText(i)]

        assert visible_items[:2] == ["Súper 95", "Premium 97"]
        assert "Advanced / Special Fuels" in visible_items
        assert visible_items[-5:] == ["Race Gas (100)", "Race Gas (110)", "E85", "Methanol", "Custom"]

        header_index = preset_combo.findText("Advanced / Special Fuels")
        assert header_index >= 0
        assert not preset_combo.model().item(header_index).isEnabled()
    finally:
        window.close()
        app.processEvents()


def test_gui_fuel_preset_selection_updates_fields_and_model(monkeypatch) -> None:
    import pytest

    app, window = _make_window(monkeypatch)
    try:
        preset_combo, fuel_type_edit, octane_spin, energy_spin, afr_spin = _fuel_form_widgets(window)

        preset_combo.setCurrentText("Premium 97")
        app.processEvents()
        assert fuel_type_edit.text() == "Gasoline"
        assert octane_spin.value() == pytest.approx(97.0)
        assert energy_spin.value() == pytest.approx(44e6)
        assert afr_spin.value() == pytest.approx(14.7)
        assert window.engine.fuel.type_name == "Gasoline"
        assert window.engine.fuel.octane_rating == pytest.approx(97.0)
        assert window.engine.fuel.energy_density == pytest.approx(44e6)
        assert window.engine.fuel.stoich_afr == pytest.approx(14.7)

        preset_combo.setCurrentText("Race Gas (110)")
        app.processEvents()
        assert fuel_type_edit.text() == "Race Gas"
        assert octane_spin.value() == pytest.approx(110.0)
        assert energy_spin.value() == pytest.approx(46e6)
        assert afr_spin.value() == pytest.approx(14.2)
        assert window.engine.fuel.octane_rating == pytest.approx(110.0)

        octane_spin.setValue(111.0)
        octane_spin.editingFinished.emit()
        app.processEvents()
        assert window.engine.fuel.octane_rating == pytest.approx(111.0)
        assert preset_combo.currentText() == "Custom"
    finally:
        window.close()
        app.processEvents()
