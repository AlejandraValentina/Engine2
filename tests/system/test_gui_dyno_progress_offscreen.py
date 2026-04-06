from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")
pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")


@pytest.mark.system
def test_gui_dyno_progress_offscreen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    from gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.engine.block.redline_rpm = 1000.0

    idx = window.dyno_mode_combo.findData("v2")
    if idx >= 0:
        window.dyno_mode_combo.setCurrentIndex(idx)

    window.run_dyno_sweep()

    loop = QEventLoop()
    start = time.time()

    def poll() -> None:
        if window.dyno_thread is None or not window.dyno_thread.isRunning():
            loop.quit()
            return
        if time.time() - start > 120.0:
            loop.quit()

    timer = QTimer()
    timer.timeout.connect(poll)
    timer.start(50)
    loop.exec()
    timer.stop()

    assert window.dyno_thread is None or not window.dyno_thread.isRunning()
    assert window._dyno_progress_count >= 1
    assert window._dyno_point_count >= 1
    assert window.last_dyno_payload is not None

    out_path = tmp_path / "dyno_gui.json"
    out_path.write_text(json.dumps(window.last_dyno_payload), encoding="utf-8")
    schema = json.loads(Path("schemas/dyno.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=window.last_dyno_payload, schema=schema)

    window.close()
    app.processEvents()
