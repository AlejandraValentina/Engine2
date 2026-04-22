from __future__ import annotations

import json
from pathlib import Path


def _offscreen_plugin_available() -> tuple[bool, str]:
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


def _make_window(monkeypatch):
    import os
    import pytest

    pytest.importorskip("PySide6")
    pytest.importorskip("pyqtgraph")
    pytest.importorskip("pyqtgraph")

    ok, reason = _offscreen_plugin_available()
    if not ok:
        pytest.skip(reason)

    if not os.environ.get("QT_QPA_PLATFORM"):
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication
    from gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    return app, window


def _bundle_artifact_filename(manifest: dict, artifact_type: str) -> str:
    for entry in manifest.get("artifacts", []):
        if entry.get("artifact_type") == artifact_type:
            return str(entry["filename"])
    raise AssertionError(f"Missing artifact type in manifest: {artifact_type}")


def test_gui_real_dyno_tab_smoke(monkeypatch) -> None:
    app, window = _make_window(monkeypatch)
    try:
        assert window.real_dyno_widget is not None
        assert window.tabs.indexOf(window.real_dyno_widget) >= 0
        assert "current editor engine" in window.real_dyno_widget.base_engine_label.text().lower()
        tab_labels = [window.real_dyno_widget.results_tabs.tabText(i).lower() for i in range(window.real_dyno_widget.results_tabs.count())]
        assert tab_labels == [
            "compare",
            "calibration",
            "validation",
            "a/b",
            "sensitivity",
            "optimize",
            "diagnostics / coverage",
            "dataset detail",
        ]
        assert "dataset" in window.real_dyno_widget.workflow_status_label.text().lower()
        assert window.real_dyno_widget.engine_toggle_button.isCheckable()
        assert window.real_dyno_widget.workflow_toggle_button.isCheckable()
        window.real_dyno_widget.engine_toggle_button.setChecked(False)
        window.real_dyno_widget.workflow_toggle_button.setChecked(False)
        app.processEvents()
        assert window.real_dyno_widget.engine_toggle_button.text().startswith("▸")
        assert window.real_dyno_widget.workflow_toggle_button.text().startswith("▸")
        assert "adaptive" in window.real_dyno_widget.engine_summary_label.text().lower()
        assert "dataset" in window.real_dyno_widget.workflow_summary_label.text().lower()
        assert window.real_dyno_widget.workflow_content.isHidden()
        assert window.real_dyno_widget.engine_content.isHidden()
        window.real_dyno_widget.engine_toggle_button.setChecked(True)
        window.real_dyno_widget.workflow_toggle_button.setChecked(True)
        app.processEvents()
        assert window.real_dyno_widget.engine_toggle_button.text().startswith("▾")
        assert window.real_dyno_widget.workflow_toggle_button.text().startswith("▾")
        assert not window.real_dyno_widget.engine_content.isHidden()
        assert not window.real_dyno_widget.workflow_content.isHidden()
    finally:
        window.close()
        app.processEvents()


def test_gui_real_dyno_import_dialog_autoselects_obvious_fields(monkeypatch, tmp_path: Path) -> None:
    import os
    import pytest

    pytest.importorskip("PySide6")

    ok, reason = _offscreen_plugin_available()
    if not ok:
        pytest.skip(reason)

    if not os.environ.get("QT_QPA_PLATFORM"):
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication
    from gui.real_dyno_workbench import DynoImportDialog

    source = tmp_path / "obvious.csv"
    source.write_text(
        "rpm,torque_nm,power_hp,map_kpa,lambda,boost_kpa\n"
        "2000,120.0,45.0,98.0,0.82,15.0\n",
        encoding="utf-8",
    )

    app = QApplication.instance() or QApplication([])
    dialog = DynoImportDialog(source, "presets/honda_k20.json")
    try:
        assert dialog.field_combos["rpm"].currentText() == "rpm"
        assert dialog.field_combos["torque_nm"].currentText() == "torque_nm"
        assert dialog.field_combos["power_hp"].currentText() == "power_hp"
        assert dialog.field_combos["map_kpa"].currentText() == "map_kpa"
        assert dialog.field_combos["lambda"].currentText() == "lambda"
        assert dialog.field_combos["boost_kpa"].currentText() == "boost_kpa"
        assert dialog.unit_combos["rpm"].currentText() == "rpm"
        assert dialog.unit_combos["torque_nm"].currentText() == "nm"
        assert dialog.unit_combos["power_hp"].currentText() == "hp"
        assert dialog.unit_combos["map_kpa"].currentText() == "kpa_abs"
        assert dialog.unit_combos["lambda"].currentText() == "lambda"
        assert dialog.unit_combos["boost_kpa"].currentText() == "kpa_g"
    finally:
        dialog.close()
        app.processEvents()


def test_gui_real_dyno_import_and_compare(monkeypatch, tmp_path: Path) -> None:
    app, window = _make_window(monkeypatch)
    try:
        source = tmp_path / "dyno.csv"
        source.write_text(
            "speed_rpm,power_kw,torque_lbft,map_abs_kpa,lambda_ch1,afr_ch1,egt_f\n"
            "2000,20.20,71.11,95,0.80,13.0,1350\n"
            "3000,30.80,72.30,96,0.80,13.0,1380\n",
            encoding="utf-8",
        )
        dataset_dir = tmp_path / "dataset"
        widget = window.real_dyno_widget
        assert widget is not None
        window.tabs.setCurrentWidget(widget)
        widget.import_dataset_from_config(
            {
                "source_path": source,
                "source_format": "csv",
                "dataset_id": "gui_k20",
                "engine_id": "gui_k20",
                "preset_path": "presets/honda_k20.json",
                "dataset_dir": dataset_dir,
                "mapping": {
                    "rpm": "speed_rpm",
                    "power_hp": "power_kw",
                    "torque_nm": "torque_lbft",
                    "map_kpa": "map_abs_kpa",
                    "lambda": "lambda_ch1",
                    "afr": "afr_ch1",
                    "egt_c": "egt_f",
                },
                "units": {
                    "rpm": "rpm",
                    "power_hp": "kw",
                    "torque_nm": "lbft",
                    "map_kpa": "kpa_abs",
                    "lambda": "lambda",
                    "afr": "afr",
                    "egt_c": "f",
                },
                "afr_stoich": 14.7,
                "notes": "GUI import test",
                "error_contract": {"torque_mape_max": 1.0, "power_mape_max": 1.0},
            }
        )
        app.processEvents()
        window.resize(1500, 900)
        app.processEvents()
        assert widget.dataset_payload is not None
        assert widget.dataset_panel.isHidden()
        assert "dataset id" in widget.compare_dataset_browser.toPlainText().lower()
        assert "import warnings" in widget.compare_dataset_browser.toPlainText().lower()
        assert "differ by more than 0.05 lambda" in widget.compare_dataset_browser.toPlainText().lower()

        widget.run_compare()
        app.processEvents()
        assert widget.compare_report is not None
        tab_labels = [widget.results_tabs.tabText(i).lower() for i in range(widget.results_tabs.count())]
        assert tab_labels == [
            "compare",
            "calibration",
            "validation",
            "a/b",
            "sensitivity",
            "optimize",
            "diagnostics / coverage",
            "dataset detail",
        ]
        assert "contract" in widget.compare_summary_label.text().lower()
        assert "adaptive combustion" not in widget.compare_summary_label.text().lower()
        assert "coverage rationale" in widget.compare_browser.toPlainText().lower()
        assert "diagnostics" in widget.compare_browser.toPlainText().lower()
        assert widget.dataset_panel.isHidden()
        assert widget.results_tabs.tabText(widget.results_tabs.count() - 1).lower() == "dataset detail"
        assert widget.results_tabs.tabText(widget.results_tabs.count() - 2).lower() == "diagnostics / coverage"
        assert widget.results_tabs.widget(0) is widget.compare_tab
        assert widget.results_tabs.widget(6) is widget.diagnostics_tab
        assert widget.results_tabs.widget(7) is widget.compare_dataset_tab
        assert widget.compare_tab.layout().count() == 2
        assert widget.compare_tab.layout().itemAt(0).widget() is widget.compare_summary_label
        assert widget.compare_tab.layout().itemAt(1).widget() is widget.compare_plot
        assert widget.compare_diagnostics_group.parentWidget() is widget.diagnostics_tab
        assert widget.compare_dataset_browser.parentWidget() is widget.compare_dataset_tab
        assert widget.compare_preview_table.parentWidget() is widget.compare_dataset_tab
        assert "dataset id" in widget.compare_dataset_browser.toPlainText().lower()
        assert widget.compare_preview_table.rowCount() == 2
        assert not widget.compare_plot.isHidden()
        assert not widget.compare_diagnostics_group.isHidden()
        assert widget.compare_plot.width() >= 560
        assert widget.compare_tab.layout().contentsMargins().bottom() >= 18
        assert 320 <= widget.compare_plot.minimumHeight() <= 380
        assert widget.compare_plot.height() >= 500
        assert widget.compare_plot.height() > widget.compare_summary_label.height() * 4
        assert 30 <= widget.compare_plot.getAxis("bottom").height() <= 60
        assert widget.export_compare_button.isEnabled()
    finally:
        window.close()
        app.processEvents()


def test_gui_real_dyno_import_and_staged_calibration(monkeypatch, tmp_path: Path) -> None:
    app, window = _make_window(monkeypatch)
    try:
        source = tmp_path / "dyno.csv"
        source.write_text(
            "speed_rpm,power_hp,torque_lbft\n"
            "2000,27.0,71.1\n"
            "3000,41.0,72.3\n"
            "4000,56.0,74.5\n",
            encoding="utf-8",
        )
        dataset_dir = tmp_path / "dataset"
        widget = window.real_dyno_widget
        assert widget is not None
        widget.import_dataset_from_config(
            {
                "source_path": source,
                "source_format": "csv",
                "dataset_id": "gui_stage_k20",
                "engine_id": "gui_stage_k20",
                "preset_path": "presets/honda_k20.json",
                "dataset_dir": dataset_dir,
                "mapping": {"rpm": "speed_rpm", "power_hp": "power_hp", "torque_nm": "torque_lbft"},
                "units": {"rpm": "rpm", "power_hp": "hp", "torque_nm": "lbft"},
                "afr_stoich": 14.7,
                "notes": "GUI staged test",
                "error_contract": {"torque_mape_max": 1.0, "power_mape_max": 1.0},
            }
        )
        widget.adaptive_mode_combo.setCurrentIndex(1)
        widget.max_evals_spin.setValue(3)
        app.processEvents()
        widget.run_staged_calibration()
        app.processEvents()
        assert widget.staged_report is not None
        assert widget.stage_table.rowCount() == 6
        assert widget.export_stage_button.isEnabled()
        assert "final params" in widget.stage_browser.toPlainText().lower()
        assert "adaptive combustion" in widget.stage_browser.toPlainText().lower()
        assert "diagnostics" in widget.stage_browser.toPlainText().lower()
    finally:
        window.close()
        app.processEvents()


def test_gui_real_dyno_advanced_analysis_views(monkeypatch, tmp_path: Path) -> None:
    app, window = _make_window(monkeypatch)
    try:
        source = tmp_path / "dyno.csv"
        source.write_text(
            "speed_rpm,power_hp,torque_lbft,map_abs_kpa\n"
            "2000,27.0,71.1,95\n"
            "3000,41.0,72.3,97\n"
            "4000,56.0,74.5,99\n",
            encoding="utf-8",
        )
        dataset_dir = tmp_path / "dataset"
        widget = window.real_dyno_widget
        assert widget is not None
        widget.import_dataset_from_config(
            {
                "source_path": source,
                "source_format": "csv",
                "dataset_id": "gui_analysis_k20",
                "engine_id": "gui_analysis_k20",
                "preset_path": "presets/honda_k20.json",
                "dataset_dir": dataset_dir,
                "mapping": {
                    "rpm": "speed_rpm",
                    "power_hp": "power_hp",
                    "torque_nm": "torque_lbft",
                    "map_kpa": "map_abs_kpa",
                },
                "units": {
                    "rpm": "rpm",
                    "power_hp": "hp",
                    "torque_nm": "lbft",
                    "map_kpa": "kpa_abs",
                },
                "afr_stoich": 14.7,
                "notes": "GUI advanced analysis test",
                "error_contract": {"torque_mape_max": 1.0, "power_mape_max": 1.0},
            }
        )
        widget.max_evals_spin.setValue(3)
        widget.run_feature_validation()
        app.processEvents()
        assert widget.validation_report is not None
        assert widget.validation_table.rowCount() >= 3
        assert "feature validation" in widget.validation_browser.toPlainText().lower()

        widget.ab_mode_a_combo.setCurrentIndex(0)
        widget.ab_mode_b_combo.setCurrentIndex(1)
        widget.run_ab_analysis()
        app.processEvents()
        assert widget.ab_report is not None
        assert widget.ab_table.rowCount() >= 2
        assert "outcome" in widget.ab_browser.toPlainText().lower()

        widget.sensitivity_params_edit.setText("ve_scale, friction_scale, burn_scale")
        widget.run_sensitivity_analysis()
        app.processEvents()
        assert widget.sensitivity_report is not None
        assert widget.sensitivity_rank_table.rowCount() >= 1
        assert "local perturbation only" in widget.sensitivity_browser.toPlainText().lower()

        widget.optimize_params_edit.setText("burn_scale, friction_scale")
        widget.optimize_max_evals_spin.setValue(6)
        widget.run_optimize_analysis()
        app.processEvents()
        assert widget.optimize_report is not None
        assert widget.optimize_candidate_table.rowCount() >= 1
        assert "best candidate score" in widget.optimize_browser.toPlainText().lower()
    finally:
        window.close()
        app.processEvents()


def test_gui_real_dyno_state_and_bundle_export(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PYWAVEDYN_GUI_STATE_PATH", str(tmp_path / "ui_state.json"))
    app, window = _make_window(monkeypatch)
    try:
        source = tmp_path / "dyno.csv"
        source.write_text(
            "speed_rpm,power_hp,torque_lbft\n"
            "2000,27.0,71.1\n"
            "3000,41.0,72.3\n"
            "4000,56.0,74.5\n",
            encoding="utf-8",
        )
        dataset_dir = tmp_path / "dataset"
        widget = window.real_dyno_widget
        assert widget is not None
        widget.import_dataset_from_config(
            {
                "source_path": source,
                "source_format": "csv",
                "dataset_id": "gui_bundle_k20",
                "engine_id": "gui_bundle_k20",
                "preset_path": "presets/honda_k20.json",
                "dataset_dir": dataset_dir,
                "mapping": {"rpm": "speed_rpm", "power_hp": "power_hp", "torque_nm": "torque_lbft"},
                "units": {"rpm": "rpm", "power_hp": "hp", "torque_nm": "lbft"},
                "afr_stoich": 14.7,
                "notes": "GUI bundle test",
                "error_contract": {"torque_mape_max": 1.0, "power_mape_max": 1.0},
            }
        )
        widget.max_evals_spin.setValue(4)
        widget.sensitivity_params_edit.setText("ve_scale, burn_scale")
        widget.optimize_params_edit.setText("burn_scale")
        widget.optimize_max_evals_spin.setValue(5)
        widget.run_compare()
        widget.run_sensitivity_analysis()
        bundle_dir = tmp_path / "bundle"
        written = widget.export_analysis_bundle_to_dir(bundle_dir)
        assert any(path.name == "compare.json" for path in written)
        assert any(path.name == "sensitivity_local.json" for path in written)
        assert any(path.name == "manifest.json" for path in written)
        manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["bundle_type"] == "real_dyno_analysis_bundle"
        assert manifest["bundle_version"] == 1
        assert manifest["artifact_count"] == 2
        artifact_types = {entry["artifact_type"] for entry in manifest["artifacts"]}
        assert artifact_types == {"compare_report", "sensitivity_local_report"}
        filenames = {entry["filename"] for entry in manifest["artifacts"]}
        assert filenames == {"compare.json", "sensitivity_local.json"}
        for entry in manifest["artifacts"]:
            assert entry.get("context", {}).get("dataset_id") == "gui_bundle_k20"
            assert entry.get("context", {}).get("engine_id") == "gui_bundle_k20"
    finally:
        window.close()
        app.processEvents()

    app2, window2 = _make_window(monkeypatch)
    try:
        widget2 = window2.real_dyno_widget
        assert widget2 is not None
        assert widget2.max_evals_spin.value() == 4
        assert widget2.sensitivity_params_edit.text() == "ve_scale, burn_scale"
        assert widget2.optimize_params_edit.text() == "burn_scale"
        assert widget2.optimize_max_evals_spin.value() == 5
        assert widget2.reload_last_dataset_button.isEnabled()
        widget2.reload_last_dataset()
        app2.processEvents()
        assert widget2.dataset_dir == dataset_dir
        manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
        compare_payload = json.loads(
            (bundle_dir / _bundle_artifact_filename(manifest, "compare_report")).read_text(encoding="utf-8")
        )
        widget2._load_report_payload(compare_payload)
        assert widget2.compare_report is not None
        assert widget2.compare_report.get("report_type") == "compare_report"
        assert "contract" in widget2.compare_summary_label.text().lower()
        assert "diagnostics" in widget2.compare_browser.toPlainText().lower()
        legacy_compare_payload = {
            key: value
            for key, value in compare_payload.items()
            if key not in {"report_type", "report_format_version", "report_family", "generated_at_utc", "context"}
        }
        widget2._load_report_payload(legacy_compare_payload)
        assert widget2.compare_report is not None
        sensitivity_payload = json.loads(
            (bundle_dir / _bundle_artifact_filename(manifest, "sensitivity_local_report")).read_text(encoding="utf-8")
        )
        widget2._load_report_payload(sensitivity_payload)
        assert widget2.sensitivity_report is not None
        assert widget2.sensitivity_report.get("report_type") == "sensitivity_local_report"
        assert "local perturbation only" in widget2.sensitivity_browser.toPlainText().lower()
        legacy_sensitivity_payload = {
            key: value
            for key, value in sensitivity_payload.items()
            if key not in {"report_type", "report_format_version", "report_family", "generated_at_utc", "context"}
        }
        widget2._load_report_payload(legacy_sensitivity_payload)
        assert widget2.sensitivity_report is not None
    finally:
        window2.close()
        app2.processEvents()


def test_gui_real_dyno_busy_state(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PYWAVEDYN_GUI_STATE_PATH", str(tmp_path / "busy_state.json"))
    app, window = _make_window(monkeypatch)
    try:
        widget = window.real_dyno_widget
        assert widget is not None
        widget._set_busy(True, "Running UX test…")
        app.processEvents()
        assert not widget.import_button.isEnabled()
        assert not widget.compare_button.isEnabled()
        assert "running ux test" in widget.workflow_status_label.text().lower()
        widget._set_busy(False, "Ready.")
        app.processEvents()
        assert widget.import_button.isEnabled()
    finally:
        window.close()
        app.processEvents()
