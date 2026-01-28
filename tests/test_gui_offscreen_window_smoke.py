from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")


def test_gui_offscreen_window_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from gui.main_window import MainWindow

    window = MainWindow()
    window.show()
    app.processEvents()
    app.processEvents()
    window.close()
    app.processEvents()
