from __future__ import annotations

import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")
pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")


@pytest.mark.system
def test_gui_export_dyno_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication, QFileDialog
    from gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.engine.block.redline_rpm = 1500.0

    out_path = tmp_path / "dyno.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(out_path), "json"))

    window.run_dyno_sweep()

    loop = QEventLoop()

    def poll() -> None:
        if window.dyno_thread is None or not window.dyno_thread.isRunning():
            loop.quit()

    timer = QTimer()
    timer.timeout.connect(poll)
    timer.start(50)
    loop.exec()
    timer.stop()
    assert window.dyno_thread is None or not window.dyno_thread.isRunning()
    window.export_dyno_json()
    window.close()
    app.processEvents()

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    schema = json.loads(Path("schemas/dyno.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=payload, schema=schema)
