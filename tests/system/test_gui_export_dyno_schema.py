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
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    from gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.engine.block.redline_rpm = 1500.0

    out_path = tmp_path / "dyno.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(out_path), "json"))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.Ok)

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
    result_count = len(list(window.last_dyno_payload.get("results", []))) if window.last_dyno_payload is not None else 0
    assert window.dyno_status_value_label.text() == "Status: Ready"
    assert window.dyno_result_state_label.text() == "Last run: Completed"
    assert window.dyno_result_value_label.text() == f"Result: {result_count} points available"
    assert window.dyno_cancel_btn.isHidden()
    assert window.dyno_summary_peak_power_value.text() != "-"
    assert window.dyno_summary_peak_torque_value.text() != "-"
    assert window.invalid_power_curve is not None
    assert window.invalid_power_curve.opts.get("name") is None
    assert window.invalid_torque_curve is not None
    assert window.invalid_torque_curve.opts.get("name") is None
    window.export_dyno_json()
    window.close()
    app.processEvents()

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    schema = json.loads(Path("schemas/dyno.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=payload, schema=schema)
    assert payload["observable_semantics"]["ve_actual"]["cross_mode_relation"] == "comparable_not_identical"
