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


def test_gui_offscreen_window_smoke(monkeypatch) -> None:
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

    app = QApplication.instance() or QApplication([])
    from gui.main_window import MainWindow

    window = MainWindow()
    window.show()
    app.processEvents()
    app.processEvents()
    assert window.workspace_combo.currentText() == "Standard View"
    assert window.overview_run_dyno_btn.text() == "Run Dyno"
    assert "Mode: Standard View / Overview" == window.toolbar_context_label.text()
    assert not hasattr(window, "overview_mode_label")
    assert "Project state:" in window.overview_status_label.text()
    assert "Dataset" in window.overview_status_label.text()
    assert "None" in window.overview_status_label.text()
    assert "Technical baseline:" in window.overview_context_label.text()
    assert "Technical overview" in window.overview_browser.toPlainText()
    assert "Short Block" in window.overview_browser.toPlainText()
    assert "Camshaft" in window.overview_browser.toPlainText()
    assert window.left_dock is not None and window.left_dock.minimumWidth() >= 240
    quick_dyno_index = window.tabs.indexOf(window.quick_dyno_tab)
    assert quick_dyno_index >= 0
    window.tabs.setCurrentIndex(quick_dyno_index)
    window.resize(1440, 900)
    app.processEvents()
    app.processEvents()
    assert "ve_actual" in window.dyno_mode_note_label.text()
    assert "strict parity" in window.dyno_mode_note_label.text().lower()
    assert "Project" in window.dyno_context_label.text()
    assert "Solver" in window.dyno_context_label.text()
    assert "Sweep" in window.dyno_context_label.text()
    assert window.dyno_settings_quality_value.text() == "Fast"
    assert "rpm" in window.dyno_settings_sweep_value.text().lower()
    assert window.dyno_status_value_label.text() == "Status: Ready"
    assert window.dyno_result_state_label.text() == "Last run: Not run yet"
    assert window.dyno_result_value_label.text() == "Result: No result available"
    assert window.dyno_cancel_btn.isHidden()
    assert "Plot context:" in window.dyno_plot_caption_label.text()
    assert "Solver" not in window.dyno_plot_caption_label.text()
    assert "populate peak values" in window.dyno_summary_detail_label.text().lower()
    assert window.dyno_plot_notice_label.isHidden()
    assert window.dyno_top_panel.height() < window.dyno_plot.height()
    assert window.dyno_plot.height() >= 360
    analysis_index = window.tabs.indexOf(window.analysis_table.parentWidget())
    assert analysis_index >= 0
    window.tabs.setCurrentIndex(analysis_index)
    app.processEvents()
    app.processEvents()
    assert "Project" in window.analysis_context_label.text()
    assert "Solver" in window.analysis_context_label.text()
    assert "Run status" in window.analysis_summary_label.text()
    assert "populate the analysis view" in window.analysis_detail_label.text().lower()
    assert window.analysis_knock_notice_label.isHidden()
    assert window.analysis_table.columnCount() == 10
    window.close()
    app.processEvents()
