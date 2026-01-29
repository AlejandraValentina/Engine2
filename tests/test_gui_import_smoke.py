from __future__ import annotations

def test_gui_import_smoke() -> None:
    import pytest

    pytest.importorskip("PySide6")
    pytest.importorskip("pyqtgraph")
    from gui.main_window import MainWindow

    assert MainWindow is not None
