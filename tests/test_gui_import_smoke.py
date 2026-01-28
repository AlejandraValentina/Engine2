from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")


def test_gui_import_smoke() -> None:
    from gui.main_window import MainWindow

    assert MainWindow is not None
