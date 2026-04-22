from __future__ import annotations

import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")
pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")


@pytest.mark.system
def test_gui_export_dyno_schema_v2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    from gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.engine.block.redline_rpm = 1000.0

    idx = window.dyno_mode_combo.findData("v2")
    if idx >= 0:
        window.dyno_mode_combo.setCurrentIndex(idx)
    qidx = window.dyno_quality_combo.findData("fast")
    if qidx >= 0:
        window.dyno_quality_combo.setCurrentIndex(qidx)

    out_path = tmp_path / "dyno_v2.json"
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
    assert window.dyno_status_value_label.text() == "Status: Ready"
    assert window.dyno_result_state_label.text() == "Last run: Completed"
    assert "v2 (Pro Coupled)" in window.dyno_plot_caption_label.text()
    window.export_dyno_json()
    window.close()
    app.processEvents()

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    schema = json.loads(Path("schemas/dyno.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=payload, schema=schema)
    assert payload["metadata"]["coupling_mode"] == "v2_orchestrator"
    assert payload["observable_semantics"]["ve_actual"]["cross_mode_relation"] == "comparable_not_identical"
    assert payload["results"]
    assert all("mean_torque_nm" in result for result in payload["results"])
    assert all("mean_power_hp" in result for result in payload["results"])
