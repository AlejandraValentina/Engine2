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
    window.close()
    app.processEvents()
