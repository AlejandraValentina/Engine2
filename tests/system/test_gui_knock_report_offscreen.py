from __future__ import annotations

import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")
pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")


@pytest.mark.system
def test_gui_knock_report_offscreen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication, QFileDialog
    from gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.engine.block.redline_rpm = 1500.0
    window.engine.combustion.residual_coupling = {"enabled": True, "k": 0.8, "min_factor": 0.4}

    dyno_path = tmp_path / "dyno.json"
    knock_path = tmp_path / "knock_report.json"
    paths = [str(knock_path), str(dyno_path)]

    def _get_save_file_name(*_args, **_kwargs):
        if paths:
            return (paths.pop(0), "json")
        return ("", "")

    monkeypatch.setattr(QFileDialog, "getSaveFileName", _get_save_file_name)

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

    window.dyno_knock_export_checkbox.setChecked(True)
    window.export_dyno_json()
    window.close()
    app.processEvents()

    payload = json.loads(knock_path.read_text(encoding="utf-8"))
    schema = json.loads(Path("schemas/knock_report.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=payload, schema=schema)
