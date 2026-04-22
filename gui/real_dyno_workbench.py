from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path
from typing import Callable, Optional

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.optimize_runner import optimize_guided
from core.engine_components import Engine
from pywavedyn.analysis_contract import (
    REPORT_TYPE_AB_COMPARE,
    REPORT_TYPE_COMPARE,
    REPORT_TYPE_OPTIMIZE_GUIDED,
    REPORT_TYPE_SENSITIVITY_LOCAL,
    REPORT_TYPE_STAGED_CALIBRATION,
    REPORT_TYPE_VALIDATION_COMPARE,
    apply_analysis_envelope,
    build_report_context,
)
from pywavedyn.analysis_labels import (
    COMPARISON_OUTCOME_DEFAULT,
    COMPARISON_OUTCOMES,
    comparison_outcome_label,
    stage_status_from_entry,
    stage_status_label,
)
from pywavedyn.analysis_bundle import manifest_entry, write_manifest
from pywavedyn.ab_sensitivity import run_ab_compare, run_local_sensitivity
from pywavedyn.bench import evaluate_with_engine
from pywavedyn.combustion_mode import apply_adaptive_combustion_mode
from pywavedyn.dyno_data import import_dyno_file, write_dataset_package
from pywavedyn.staged_calibration import run_staged_calibration
from pywavedyn.validation_compare import apply_turbo_incremental_mode, run_validation_batch


CANONICAL_SIGNALS = ["rpm", "torque_nm", "power_hp", "boost_kpa", "map_kpa", "lambda", "afr", "egt_c"]
SIGNAL_LABELS = {
    "rpm": "RPM",
    "torque_nm": "Torque",
    "power_hp": "Power",
    "boost_kpa": "Boost",
    "map_kpa": "MAP",
    "lambda": "Lambda",
    "afr": "AFR",
    "egt_c": "EGT",
}
UNIT_OPTIONS = {
    "rpm": ["rpm"],
    "torque_nm": ["lbft", "nm"],
    "power_hp": ["hp", "kw"],
    "boost_kpa": ["kpa_g", "psi_g", "bar_g"],
    "map_kpa": ["kpa_abs", "psi_abs", "bar_abs"],
    "lambda": ["lambda"],
    "afr": ["afr"],
    "egt_c": ["c", "f", "k"],
}


def _infer_source_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".json":
        return "json"
    raise ValueError(f"Unsupported source file '{path.name}'. Choose CSV or JSON.")


def _collect_json_fields(value, prefix: str = "") -> list[str]:
    fields: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else key
            if isinstance(item, dict):
                fields.extend(_collect_json_fields(item, next_prefix))
            else:
                fields.append(next_prefix)
    return fields


def inspect_source_fields(path: Path) -> tuple[str, list[str]]:
    fmt = _infer_source_format(path)
    if fmt == "csv":
        with path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            return fmt, list(reader.fieldnames or [])
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        for key in ("points", "rows", "records", "data"):
            candidate = payload.get(key)
            if isinstance(candidate, list) and candidate:
                payload = candidate[0]
                break
    elif isinstance(payload, list) and payload:
        payload = payload[0]
    if not isinstance(payload, dict):
        return fmt, []
    return fmt, sorted(_collect_json_fields(payload))


def _normalize_field_name(field_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(field_name).strip().lower()).strip("_")


def _guess_mapping(fields: list[str]) -> dict[str, str]:
    lowered = {field: field.lower() for field in fields}
    normalized = {field: _normalize_field_name(field) for field in fields}
    guesses: dict[str, str] = {}
    exact_aliases = {
        "rpm": ("rpm", "speed_rpm", "engine_rpm"),
        "torque_nm": ("torque_nm", "tq_nm", "engine_torque_nm"),
        "power_hp": ("power_hp", "engine_power_hp"),
        "boost_kpa": ("boost_kpa", "boost", "boost_gauge_kpa"),
        "map_kpa": ("map_kpa", "map_abs_kpa", "manifold_abs_kpa", "manifold_kpa"),
        "lambda": ("lambda", "lambda_ch1", "lambda_1"),
        "afr": ("afr", "afr_ch1", "afr_1"),
        "egt_c": ("egt_c", "egt", "egt_ch1", "exhaust_temp_c"),
    }
    for signal, aliases in exact_aliases.items():
        for alias in aliases:
            for field, normalized_field in normalized.items():
                if normalized_field == alias:
                    guesses[signal] = field
                    break
            if signal in guesses:
                break
    patterns = {
        "rpm": ("rpm", "speed"),
        "torque_nm": ("torque", "tq"),
        "power_hp": ("power", "hp", "kw"),
        "boost_kpa": ("boost",),
        "map_kpa": ("map", "manifold"),
        "lambda": ("lambda", "lam"),
        "afr": ("afr", "airfuel"),
        "egt_c": ("egt", "exhausttemp", "temp"),
    }
    for signal, tokens in patterns.items():
        if signal in guesses:
            continue
        for field, lowered_field in lowered.items():
            if any(token in lowered_field for token in tokens):
                guesses[signal] = field
                break
    return guesses


def _guess_unit(signal: str, field_name: str) -> str:
    lowered = field_name.lower()
    normalized = _normalize_field_name(field_name)
    if signal == "torque_nm":
        return "lbft" if any(token in normalized for token in ("lbft", "lb_ft", "lb", "ftlb")) else "nm"
    if signal == "power_hp":
        return "kw" if "kw" in normalized else "hp"
    if signal == "boost_kpa":
        if "psi" in normalized:
            return "psi_g"
        if "bar" in normalized:
            return "bar_g"
        return "kpa_g"
    if signal == "map_kpa":
        if "psi" in normalized:
            return "psi_abs"
        if "bar" in normalized:
            return "bar_abs"
        return "kpa_abs"
    if signal == "egt_c":
        if "degf" in normalized or normalized.endswith("_f") or normalized.endswith("f"):
            return "f"
        if "degk" in normalized or normalized.endswith("_k") or normalized.endswith("k"):
            return "k"
        return "c"
    if signal == "lambda":
        return "lambda"
    if signal == "afr":
        return "afr"
    return "rpm"


def _format_metrics(metrics: dict) -> str:
    parts = [
        f"Torque MAPE: {metrics.get('torque_mape', 0.0):.3f}",
        f"Power MAPE: {metrics.get('power_mape', 0.0):.3f}",
        f"Total MAPE: {metrics.get('total_mape', 0.0):.3f}",
        f"Contract: {'pass' if metrics.get('contract_pass') else 'fail'}",
    ]
    optional = metrics.get("optional_signals", {})
    if optional:
        parts.append(
            "Optional signals: "
            + ", ".join(f"{signal} mape={data.get('mape', 0.0):.3f}" for signal, data in optional.items())
        )
    if "objective_filtered" in metrics:
        parts.append(f"Filtered objective: {metrics['objective_filtered']:.3f}")
    return " | ".join(parts)


def _format_diagnostics_html(diagnostics: list[dict]) -> str:
    if not diagnostics:
        return "<b>Diagnostics:</b><br>None"
    lines = ["<b>Diagnostics</b><br>"]
    for diag in diagnostics:
        lines.append(
            f"[{diag.get('severity', 'info').upper()} / {diag.get('confidence', 'low')}] "
            f"{diag.get('title', diag.get('id', 'diagnostic'))}<br>"
            f"Signals: {', '.join(diag.get('signals_used', [])) or 'none'}<br>"
            f"Rationale: {diag.get('rationale', '')}<br>"
            f"Interpretation: {diag.get('suggested_interpretation', '')}<br><br>"
        )
    return "".join(lines)


def _json_html(value: object) -> str:
    return json.dumps(value, indent=2).replace("\n", "<br>").replace(" ", "&nbsp;")


def _parse_param_list(text: str) -> list[str]:
    return [item.strip() for item in str(text).split(",") if item.strip()]


def _outcome_badge(outcome: str) -> str:
    return comparison_outcome_label(outcome)


def _real_dyno_state_path() -> Path:
    override = os.environ.get("PYWAVEDYN_GUI_STATE_PATH", "").strip()
    if override:
        return Path(override)
    local_app = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    return local_app / "PyWaveDyn" / "real_dyno_state.json"


class DynoImportDialog(QDialog):
    def __init__(
        self,
        source_path: Path,
        default_preset_path: str,
        *,
        initial_config: Optional[dict] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.source_path = source_path
        self.setWindowTitle("Import Real Dyno Dataset")
        self.resize(880, 640)
        self.source_format, self.fields = inspect_source_fields(source_path)
        guessed_mapping = _guess_mapping(self.fields)
        initial_config = dict(initial_config or {})

        layout = QVBoxLayout(self)
        intro = QTextBrowser()
        intro.setReadOnly(True)
        intro.setHtml(
            "<b>Source</b>: "
            f"{source_path.name}<br><b>Format</b>: {self.source_format.upper()}<br>"
            "Define explicit field mapping and source units. RPM is mandatory and torque or power is required."
        )
        layout.addWidget(intro)

        form = QFormLayout()
        self.dataset_id_edit = QLineEdit(str(initial_config.get("dataset_id", f"{source_path.stem}_dataset")))
        self.engine_id_edit = QLineEdit(str(initial_config.get("engine_id", source_path.stem)))
        self.preset_path_edit = QLineEdit(str(initial_config.get("preset_path", default_preset_path or "<current_gui_engine>")))
        out_default = Path(str(initial_config.get("dataset_dir", source_path.parent / f"{source_path.stem}_dataset")))
        self.output_dir_edit = QLineEdit(str(out_default))
        out_button = QPushButton("Browse…")
        out_button.clicked.connect(self._browse_output_dir)
        out_row = QWidget()
        out_layout = QHBoxLayout(out_row)
        out_layout.setContentsMargins(0, 0, 0, 0)
        out_layout.addWidget(self.output_dir_edit, 1)
        out_layout.addWidget(out_button)
        self.notes_edit = QLineEdit(str(initial_config.get("notes", "Imported from GUI real-dyno workflow")))
        self.afr_stoich_spin = QDoubleSpinBox()
        self.afr_stoich_spin.setRange(5.0, 25.0)
        self.afr_stoich_spin.setValue(float(initial_config.get("afr_stoich", 14.7)))
        self.afr_stoich_spin.setDecimals(3)
        self.torque_limit_spin = QDoubleSpinBox()
        self.torque_limit_spin.setRange(0.0, 2.0)
        self.torque_limit_spin.setValue(float(initial_config.get("error_contract", {}).get("torque_mape_max", 0.15)))
        self.torque_limit_spin.setDecimals(3)
        self.power_limit_spin = QDoubleSpinBox()
        self.power_limit_spin.setRange(0.0, 2.0)
        self.power_limit_spin.setValue(float(initial_config.get("error_contract", {}).get("power_mape_max", 0.15)))
        self.power_limit_spin.setDecimals(3)

        form.addRow("Dataset id", self.dataset_id_edit)
        form.addRow("Engine id", self.engine_id_edit)
        form.addRow("Preset path", self.preset_path_edit)
        form.addRow("Output dataset dir", out_row)
        form.addRow("Notes", self.notes_edit)
        form.addRow("AFR stoich", self.afr_stoich_spin)
        form.addRow("Torque MAPE max", self.torque_limit_spin)
        form.addRow("Power MAPE max", self.power_limit_spin)
        layout.addLayout(form)

        mapping_group = QGroupBox("Field mapping and units")
        grid = QGridLayout(mapping_group)
        grid.addWidget(QLabel("Canonical signal"), 0, 0)
        grid.addWidget(QLabel("Source field"), 0, 1)
        grid.addWidget(QLabel("Source unit"), 0, 2)
        self.field_combos: dict[str, QComboBox] = {}
        self.unit_combos: dict[str, QComboBox] = {}
        stored_mapping = dict(initial_config.get("mapping", {}))
        stored_units = dict(initial_config.get("units", {}))
        selectable_fields = [""] + self.fields
        for row, signal in enumerate(CANONICAL_SIGNALS, start=1):
            grid.addWidget(QLabel(SIGNAL_LABELS[signal]), row, 0)
            field_combo = QComboBox()
            field_combo.addItems(selectable_fields)
            field_combo.setEditable(False)
            guessed_field = str(stored_mapping.get(signal, guessed_mapping.get(signal, "")))
            if guessed_field:
                field_combo.setCurrentText(guessed_field)
            unit_combo = QComboBox()
            unit_combo.addItems(UNIT_OPTIONS[signal])
            chosen_unit = str(stored_units.get(signal, _guess_unit(signal, guessed_field) if guessed_field else UNIT_OPTIONS[signal][0]))
            if chosen_unit:
                unit_combo.setCurrentText(chosen_unit)
            field_combo.currentTextChanged.connect(
                lambda value, s=signal, combo=unit_combo: self._sync_unit_guess(s, value, combo)
            )
            self.field_combos[signal] = field_combo
            self.unit_combos[signal] = unit_combo
            grid.addWidget(field_combo, row, 1)
            grid.addWidget(unit_combo, row, 2)
        layout.addWidget(mapping_group, 1)

        self.preview_browser = QTextBrowser()
        self.preview_browser.setReadOnly(True)
        self.preview_browser.setHtml(
            "<b>Detected fields</b><br>" + "<br>".join(self.fields) if self.fields else "No source fields detected."
        )
        layout.addWidget(self.preview_browser)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Choose Dataset Output Directory", self.output_dir_edit.text())
        if directory:
            self.output_dir_edit.setText(directory)

    def _sync_unit_guess(self, signal: str, field_name: str, combo: QComboBox) -> None:
        if not field_name:
            return
        guess = _guess_unit(signal, field_name)
        index = combo.findText(guess)
        if index >= 0:
            combo.setCurrentIndex(index)

    def config(self) -> dict:
        mapping = {}
        units = {}
        for signal in CANONICAL_SIGNALS:
            field_name = self.field_combos[signal].currentText().strip()
            if not field_name:
                continue
            mapping[signal] = field_name
            units[signal] = self.unit_combos[signal].currentText().strip()
        if "rpm" not in mapping:
            raise ValueError("RPM mapping is required.")
        if "torque_nm" not in mapping and "power_hp" not in mapping:
            raise ValueError("Map at least torque or power before importing.")
        if not self.dataset_id_edit.text().strip():
            raise ValueError("Dataset id is required.")
        if not self.engine_id_edit.text().strip():
            raise ValueError("Engine id is required.")
        if not self.output_dir_edit.text().strip():
            raise ValueError("Output dataset directory is required.")
        return {
            "source_path": self.source_path,
            "source_format": self.source_format,
            "dataset_id": self.dataset_id_edit.text().strip(),
            "engine_id": self.engine_id_edit.text().strip(),
            "preset_path": self.preset_path_edit.text().strip(),
            "dataset_dir": Path(self.output_dir_edit.text().strip()),
            "mapping": mapping,
            "units": units,
            "afr_stoich": float(self.afr_stoich_spin.value()),
            "notes": self.notes_edit.text().strip(),
            "error_contract": {
                "torque_mape_max": float(self.torque_limit_spin.value()),
                "power_mape_max": float(self.power_limit_spin.value()),
            },
        }


class RealDynoWorkbench(QWidget):
    def __init__(
        self,
        *,
        engine_provider: Callable[[], Engine],
        engine_path_provider: Callable[[], Optional[str]],
        status_message: Callable[[str, int], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._engine_provider = engine_provider
        self._engine_path_provider = engine_path_provider
        self._status_message = status_message
        self._state = self._load_ui_state()
        self._busy_message = ""

        self.selected_engine_path: Optional[str] = self._state.get("selected_engine_path")
        self.dataset_dir: Optional[Path] = None
        self.dataset_meta: Optional[dict] = None
        self.dataset_payload: Optional[dict] = None
        self.compare_report: Optional[dict] = None
        self.staged_report: Optional[dict] = None
        self.validation_report: Optional[dict] = None
        self.ab_report: Optional[dict] = None
        self.sensitivity_report: Optional[dict] = None
        self.optimize_report: Optional[dict] = None
        self.calibrated_engine_raw: Optional[dict] = None
        self.benchmark_before_report: Optional[dict] = None
        self.benchmark_after_report: Optional[dict] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)

        group_style = (
            "QGroupBox {"
            " font-size: 10px; font-weight: 600; color: #304052;"
            " border: 1px solid #dbe2ec; border-radius: 8px;"
            " margin-top: 7px; padding-top: 3px; background: #fbfcfe;"
            "}"
            "QGroupBox::title {"
            " subcontrol-origin: margin; left: 10px; padding: 0 4px;"
            "}"
        )
        section_style = (
            "QWidget#realDynoDisclosureSection {"
            " background: #fbfcfe; border: 1px solid #dbe2ec; border-radius: 8px;"
            "}"
        )

        context_strip = QWidget()
        context_strip.setObjectName("realDynoContextStrip")
        context_strip.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        context_strip.setStyleSheet(
            """
            QWidget#realDynoContextStrip {
                background: #f9fbfd;
                border: 1px solid #dbe2ec;
                border-radius: 9px;
            }
            """
        )
        context_layout = QVBoxLayout()
        context_layout.setContentsMargins(8, 6, 8, 6)
        context_layout.setSpacing(3)
        context_title = QLabel("Real Dyno Workbench")
        context_title.setStyleSheet("font-size: 9px; font-weight: 700; color: #6a7888;")
        self.context_summary_label = QLabel()
        self.context_summary_label.setTextFormat(Qt.RichText)
        self.context_summary_label.setWordWrap(True)
        self.context_summary_label.setStyleSheet("font-size: 9px; color: #415164;")
        self.workflow_status_label = QLabel()
        self.workflow_status_label.setWordWrap(True)
        self.workflow_status_label.setStyleSheet(
            "font-size: 9px; font-weight: 600; color: #4a5a6c; background: #f3f6fa; border: 1px solid #dbe2ec; border-radius: 7px; padding: 2px 6px;"
        )
        context_layout.addWidget(context_title)
        context_strip.setLayout(context_layout)
        layout.addWidget(context_strip)

        engine_group = QWidget()
        engine_group.setObjectName("realDynoDisclosureSection")
        engine_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        engine_group.setStyleSheet(section_style)
        engine_group_layout = QVBoxLayout(engine_group)
        engine_group_layout.setContentsMargins(0, 0, 0, 0)
        engine_group_layout.setSpacing(0)
        engine_header = QWidget()
        engine_header_layout = QHBoxLayout(engine_header)
        engine_header_layout.setContentsMargins(8, 6, 8, 4)
        engine_header_layout.setSpacing(6)
        self.engine_toggle_button = QToolButton()
        self.engine_toggle_button.setCheckable(True)
        self.engine_toggle_button.setChecked(True)
        self.engine_toggle_button.setAutoRaise(True)
        self.engine_toggle_button.setStyleSheet(
            "QToolButton { border: none; color: #304052; font-size: 10px; font-weight: 700; padding: 0px; }"
            "QToolButton:hover { color: #18212f; }"
        )
        self.engine_summary_label = QLabel()
        self.engine_summary_label.setStyleSheet("font-size: 9px; color: #516174; font-weight: 600;")
        self.engine_summary_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        engine_header_layout.addWidget(self.engine_toggle_button)
        engine_header_layout.addStretch()
        engine_header_layout.addWidget(self.engine_summary_label)
        engine_group_layout.addWidget(engine_header)
        self.engine_content = QWidget()
        engine_layout = QHBoxLayout(self.engine_content)
        self.base_engine_label = QLabel()
        self.base_engine_label.setTextFormat(Qt.RichText)
        self.base_engine_label.setWordWrap(True)
        self.base_engine_label.setStyleSheet("font-size: 10px; color: #18212f;")
        context_layout.addWidget(self.base_engine_label)
        context_layout.addWidget(self.context_summary_label)
        context_layout.addWidget(self.workflow_status_label)
        self.adaptive_mode_combo = QComboBox()
        self.adaptive_mode_combo.addItem("Adaptive combustion: as configured", "as_is")
        self.adaptive_mode_combo.addItem("Adaptive combustion: force on", "on")
        self.adaptive_mode_combo.addItem("Adaptive combustion: force off", "off")
        self.adaptive_mode_combo.currentIndexChanged.connect(
            lambda _index: (self._refresh_engine_header(), self._refresh_context_strip())
        )
        self.current_engine_button = QPushButton("Use current editor engine")
        self.current_engine_button.clicked.connect(self.use_current_engine)
        self.browse_engine_button = QPushButton("Browse engine JSON…")
        self.browse_engine_button.clicked.connect(self.browse_base_engine)
        secondary_button_style = (
            "QPushButton { background: #f8fafd; color: #405064; border: 1px solid #dbe2ec; border-radius: 7px; padding: 4px 8px; }"
            "QPushButton:hover { background: #f1f5fa; border-color: #c8d3e0; }"
            "QPushButton:disabled { background: #f7f9fb; color: #9aa8b8; border-color: #e4eaf1; }"
        )
        self.current_engine_button.setStyleSheet(secondary_button_style)
        self.browse_engine_button.setStyleSheet(secondary_button_style)
        engine_layout.setContentsMargins(8, 8, 8, 6)
        engine_layout.setSpacing(4)
        engine_layout.addWidget(self.base_engine_label, 1)
        engine_layout.addWidget(self.adaptive_mode_combo)
        engine_layout.addWidget(self.current_engine_button)
        engine_layout.addWidget(self.browse_engine_button)
        engine_group_layout.addWidget(self.engine_content)
        layout.addWidget(engine_group)

        actions_group = QWidget()
        actions_group.setObjectName("realDynoDisclosureSection")
        actions_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        actions_group.setStyleSheet(section_style)
        actions_group_layout = QVBoxLayout(actions_group)
        actions_group_layout.setContentsMargins(0, 0, 0, 0)
        actions_group_layout.setSpacing(0)
        workflow_header = QWidget()
        workflow_header_layout = QHBoxLayout(workflow_header)
        workflow_header_layout.setContentsMargins(8, 6, 8, 4)
        workflow_header_layout.setSpacing(6)
        self.workflow_toggle_button = QToolButton()
        self.workflow_toggle_button.setCheckable(True)
        self.workflow_toggle_button.setChecked(True)
        self.workflow_toggle_button.setAutoRaise(True)
        self.workflow_toggle_button.setStyleSheet(
            "QToolButton { border: none; color: #304052; font-size: 10px; font-weight: 700; padding: 0px; }"
            "QToolButton:hover { color: #18212f; }"
        )
        self.workflow_summary_label = QLabel()
        self.workflow_summary_label.setStyleSheet("font-size: 9px; color: #516174; font-weight: 600;")
        self.workflow_summary_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        workflow_header_layout.addWidget(self.workflow_toggle_button)
        workflow_header_layout.addStretch()
        workflow_header_layout.addWidget(self.workflow_summary_label)
        actions_group_layout.addWidget(workflow_header)
        self.workflow_group = actions_group
        self.workflow_content = QWidget()
        actions_layout = QVBoxLayout(self.workflow_content)
        self.import_button = QPushButton("Import dyno data…")
        self.import_button.clicked.connect(self.launch_import_dialog)
        self.load_dataset_button = QPushButton("Load dataset package…")
        self.load_dataset_button.clicked.connect(self.load_dataset_package_dialog)
        self.compare_button = QPushButton("Compare simulation vs real")
        self.compare_button.clicked.connect(self.run_compare)
        self.compare_button.setEnabled(False)
        self.stage_button = QPushButton("Run staged calibration")
        self.stage_button.clicked.connect(self.run_staged_calibration)
        self.stage_button.setEnabled(False)
        self.export_compare_button = QPushButton("Export compare report…")
        self.export_compare_button.clicked.connect(self.export_compare_report)
        self.export_compare_button.setEnabled(False)
        self.export_stage_button = QPushButton("Export calibration artifacts…")
        self.export_stage_button.clicked.connect(self.export_staged_artifacts)
        self.export_stage_button.setEnabled(False)
        self.open_report_button = QPushButton("Open analysis report…")
        self.open_report_button.clicked.connect(self.open_analysis_report_dialog)
        self.export_bundle_button = QPushButton("Export analysis bundle…")
        self.export_bundle_button.clicked.connect(self.export_analysis_bundle_dialog)
        self.reload_last_dataset_button = QPushButton("Reload last dataset")
        self.reload_last_dataset_button.clicked.connect(self.reload_last_dataset)
        self.max_evals_spin = QSpinBox()
        self.max_evals_spin.setRange(1, 200)
        self.max_evals_spin.setValue(int(self._state.get("max_evals_per_stage", 10)))
        self.import_button.setStyleSheet(
            "QPushButton { background: #1f5ea8; color: white; border: none; border-radius: 8px; padding: 7px 14px; font-weight: 700; }"
            "QPushButton:hover { background: #184b85; }"
            "QPushButton:disabled { background: #a7bbd4; color: #eef3f9; }"
        )
        self.compare_button.setStyleSheet(
            "QPushButton { background: #1f5ea8; color: white; border: none; border-radius: 8px; padding: 7px 14px; font-weight: 700; }"
            "QPushButton:hover { background: #184b85; }"
            "QPushButton:disabled { background: #a7bbd4; color: #eef3f9; }"
        )
        self.stage_button.setStyleSheet(secondary_button_style)
        self.load_dataset_button.setStyleSheet(secondary_button_style)
        self.reload_last_dataset_button.setStyleSheet(secondary_button_style)
        self.export_compare_button.setStyleSheet(secondary_button_style)
        self.export_stage_button.setStyleSheet(secondary_button_style)
        self.open_report_button.setStyleSheet(secondary_button_style)
        self.export_bundle_button.setStyleSheet(secondary_button_style)
        actions_layout.setContentsMargins(8, 8, 8, 6)
        actions_layout.setSpacing(4)
        workflow_source_label = QLabel("1 Load or import dataset")
        workflow_source_label.setStyleSheet("font-size: 9px; font-weight: 700; color: #5b6b7c;")
        actions_layout.addWidget(workflow_source_label)
        workflow_source_row = QHBoxLayout()
        workflow_source_row.setSpacing(4)
        workflow_source_row.addWidget(self.import_button)
        workflow_source_row.addWidget(self.load_dataset_button)
        workflow_source_row.addWidget(self.reload_last_dataset_button)
        workflow_source_row.addStretch()
        actions_layout.addLayout(workflow_source_row)
        workflow_compare_label = QLabel("2 Compare")
        workflow_compare_label.setStyleSheet("font-size: 9px; font-weight: 700; color: #5b6b7c;")
        actions_layout.addWidget(workflow_compare_label)
        workflow_compare_row = QHBoxLayout()
        workflow_compare_row.setSpacing(4)
        workflow_compare_row.addWidget(self.compare_button)
        workflow_compare_row.addStretch()
        actions_layout.addLayout(workflow_compare_row)
        workflow_run_label = QLabel("3 Calibrate")
        workflow_run_label.setStyleSheet("font-size: 9px; font-weight: 700; color: #5b6b7c;")
        actions_layout.addWidget(workflow_run_label)
        workflow_run_row = QHBoxLayout()
        workflow_run_row.setSpacing(4)
        workflow_run_row.addWidget(self.stage_button)
        workflow_max_evals_label = QLabel("Max evals/stage")
        workflow_run_row.addWidget(workflow_max_evals_label)
        workflow_run_row.addWidget(self.max_evals_spin)
        workflow_run_row.addStretch()
        actions_layout.addLayout(workflow_run_row)
        self.workflow_artifacts_label = QLabel("Reports")
        self.workflow_artifacts_label.setStyleSheet("font-size: 9px; color: #7b8795;")
        actions_layout.addWidget(self.workflow_artifacts_label)
        workflow_artifacts_row = QHBoxLayout()
        workflow_artifacts_row.setSpacing(4)
        workflow_artifacts_row.addWidget(self.export_compare_button)
        workflow_artifacts_row.addWidget(self.export_stage_button)
        workflow_artifacts_row.addWidget(self.open_report_button)
        workflow_artifacts_row.addWidget(self.export_bundle_button)
        workflow_artifacts_row.addStretch()
        self.workflow_artifacts_row = workflow_artifacts_row
        actions_layout.addLayout(workflow_artifacts_row)
        actions_group_layout.addWidget(self.workflow_content)
        layout.addWidget(actions_group)

        analysis_group = QGroupBox("Advanced analysis views")
        analysis_group.setCheckable(True)
        analysis_group.setChecked(False)
        analysis_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        analysis_group.setStyleSheet(group_style)
        analysis_layout = QGridLayout(analysis_group)
        analysis_layout.setContentsMargins(10, 12, 10, 10)
        analysis_layout.setHorizontalSpacing(8)
        analysis_layout.setVerticalSpacing(8)
        self.advanced_group = analysis_group
        self.validation_adaptive_check = QCheckBox("Adaptive on/off")
        self.validation_adaptive_check.setChecked(True)
        self.validation_turbo_check = QCheckBox("Turbo on/off")
        self.validation_turbo_check.setChecked(True)
        self.validation_stage_check = QCheckBox("Before/after staged")
        self.validation_stage_check.setChecked(True)
        self.validation_button = QPushButton("Run feature validation")
        self.validation_button.clicked.connect(self.run_feature_validation)
        self.validation_button.setEnabled(False)

        self.ab_mode_a_combo = QComboBox()
        self.ab_mode_a_combo.addItem("Baseline", "baseline")
        self.ab_mode_a_combo.addItem("Adaptive ON", "adaptive_on")
        self.ab_mode_a_combo.addItem("Adaptive OFF", "adaptive_off")
        self.ab_mode_a_combo.addItem("Turbo incremental ON", "turbo_on")
        self.ab_mode_a_combo.addItem("Turbo incremental OFF", "turbo_off")
        self.ab_mode_b_combo = QComboBox()
        self.ab_mode_b_combo.addItem("Baseline", "baseline")
        self.ab_mode_b_combo.addItem("Adaptive ON", "adaptive_on")
        self.ab_mode_b_combo.addItem("Adaptive OFF", "adaptive_off")
        self.ab_mode_b_combo.addItem("Turbo incremental ON", "turbo_on")
        self.ab_mode_b_combo.addItem("Turbo incremental OFF", "turbo_off")
        self.ab_mode_b_combo.setCurrentIndex(1)
        self.ab_button = QPushButton("Run A/B compare")
        self.ab_button.clicked.connect(self.run_ab_analysis)
        self.ab_button.setEnabled(False)

        self.sensitivity_params_edit = QLineEdit(str(self._state.get("sensitivity_params", "ve_scale, friction_scale, burn_scale")))
        self.sensitivity_button = QPushButton("Run local sensitivity")
        self.sensitivity_button.clicked.connect(self.run_sensitivity_analysis)
        self.sensitivity_button.setEnabled(False)

        self.optimize_params_edit = QLineEdit(str(self._state.get("optimize_params", "burn_scale, friction_scale")))
        self.optimize_max_evals_spin = QSpinBox()
        self.optimize_max_evals_spin.setRange(2, 50)
        self.optimize_max_evals_spin.setValue(int(self._state.get("optimize_max_evals", 12)))
        self.optimize_button = QPushButton("Run optimize-guided")
        self.optimize_button.clicked.connect(self.run_optimize_analysis)
        self.optimize_button.setEnabled(False)
        self.validation_button.setStyleSheet(secondary_button_style)
        self.ab_button.setStyleSheet(secondary_button_style)
        self.sensitivity_button.setStyleSheet(secondary_button_style)
        self.optimize_button.setStyleSheet(secondary_button_style)

        analysis_layout.addWidget(self.validation_adaptive_check, 0, 0)
        analysis_layout.addWidget(self.validation_turbo_check, 0, 1)
        analysis_layout.addWidget(self.validation_stage_check, 0, 2)
        analysis_layout.addWidget(self.validation_button, 0, 3)
        analysis_layout.addWidget(QLabel("A"), 1, 0)
        analysis_layout.addWidget(self.ab_mode_a_combo, 1, 1)
        analysis_layout.addWidget(QLabel("B"), 1, 2)
        analysis_layout.addWidget(self.ab_mode_b_combo, 1, 3)
        analysis_layout.addWidget(self.ab_button, 1, 4)
        analysis_layout.addWidget(QLabel("Sensitivity params"), 2, 0)
        analysis_layout.addWidget(self.sensitivity_params_edit, 2, 1, 1, 3)
        analysis_layout.addWidget(self.sensitivity_button, 2, 4)
        analysis_layout.addWidget(QLabel("Optimize params"), 3, 0)
        analysis_layout.addWidget(self.optimize_params_edit, 3, 1, 1, 2)
        analysis_layout.addWidget(QLabel("Max evals"), 3, 3)
        analysis_layout.addWidget(self.optimize_max_evals_spin, 3, 4)
        analysis_layout.addWidget(self.optimize_button, 3, 5)
        layout.addWidget(analysis_group)

        dataset_browser_style = (
            "QTextBrowser { background: #fbfcfe; border: 1px solid #dbe2ec; border-radius: 8px; padding: 8px; color: #314154; }"
        )
        self.dataset_browser = QTextBrowser()
        self.dataset_browser.setReadOnly(True)
        self.dataset_browser.setStyleSheet(dataset_browser_style)
        self.dataset_browser.setMinimumHeight(96)
        self.dataset_browser.setMaximumHeight(220)

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)
        self.content_layout = content_layout

        self.dataset_panel = QWidget()
        self.dataset_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        left_col = QVBoxLayout(self.dataset_panel)
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(4)
        self.dataset_title_label = QLabel("Dataset preview")
        self.dataset_title_label.setStyleSheet("font-size: 10px; font-weight: 700; color: #5b6b7c;")
        left_col.addWidget(self.dataset_title_label)
        left_col.addWidget(self.dataset_browser)
        self.preview_table = QTableWidget()
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.setMinimumHeight(150)
        self.preview_table.setMaximumHeight(360)
        left_col.addWidget(self.preview_table, 2)
        # Dataset detail now lives in the result tabs; keep this legacy side panel off-layout.
        self.dataset_panel.setVisible(False)

        self.results_panel = QWidget()
        self.results_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_col = QVBoxLayout(self.results_panel)
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(4)
        self.results_title_label = QLabel("Results")
        self.results_title_label.setStyleSheet("font-size: 10px; font-weight: 700; color: #5b6b7c;")
        right_col.addWidget(self.results_title_label)
        self.results_tabs = QTabWidget()
        self.results_tabs.setDocumentMode(True)
        self.results_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.results_tabs.setStyleSheet(
            """
            QTabWidget::pane {
                border: 1px solid #d6dde8;
                border-radius: 10px;
                background: white;
            }
            QTabBar::tab {
                background: #eef2f7;
                border: 1px solid #d6dde8;
                border-bottom: none;
                padding: 8px 12px;
                margin-right: 4px;
                color: #415164;
            }
            QTabBar::tab:selected {
                background: white;
                color: #18212f;
                font-weight: 600;
            }
            """
        )

        compare_tab = QWidget()
        self.compare_tab = compare_tab
        compare_layout = QVBoxLayout(compare_tab)
        compare_layout.setContentsMargins(6, 6, 6, 18)
        compare_layout.setSpacing(10)
        self.compare_summary_label = QLabel()
        self.compare_summary_label.setTextFormat(Qt.RichText)
        self.compare_summary_label.setWordWrap(True)
        self.compare_summary_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.compare_summary_label.setStyleSheet(
            "background: #f8fafc; border: 1px solid #dbe2ec; border-radius: 8px; padding: 8px; color: #18212f;"
        )
        compare_layout.addWidget(self.compare_summary_label)
        self.compare_plot = pg.PlotWidget()
        self.compare_plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.compare_plot.showGrid(x=True, y=True, alpha=0.2)
        self.compare_plot.setLabel("bottom", "RPM")
        self.compare_plot.setLabel("left", "Torque / Power")
        self.compare_plot.setMinimumHeight(360)
        compare_layout.addWidget(self.compare_plot, 1)

        diagnostics_tab = QWidget()
        self.diagnostics_tab = diagnostics_tab
        diagnostics_layout = QVBoxLayout(diagnostics_tab)
        diagnostics_layout.setContentsMargins(8, 8, 8, 8)
        diagnostics_layout.setSpacing(6)

        # Keep secondary diagnostics content out of the main compare plot tab.
        self.compare_diagnostics_group = QGroupBox("Diagnostics / Coverage")
        self.compare_diagnostics_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.compare_diagnostics_group.setStyleSheet(
            "QGroupBox { font-size: 10px; font-weight: 600; color: #304052; "
            "border: 1px solid #dbe2ec; border-radius: 8px; margin-top: 6px; padding-top: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }"
        )
        compare_diagnostics_layout = QVBoxLayout(self.compare_diagnostics_group)
        compare_diagnostics_layout.setContentsMargins(8, 10, 8, 8)
        compare_diagnostics_layout.setSpacing(4)
        self.compare_browser = QTextBrowser()
        self.compare_browser.setReadOnly(True)
        self.compare_browser.setStyleSheet(
            "QTextBrowser { background: #fbfcfe; border: 1px solid #dbe2ec; border-radius: 8px; padding: 5px; color: #314154; font-size: 9px; }"
        )
        self.compare_browser.setMinimumHeight(220)
        compare_diagnostics_layout.addWidget(self.compare_browser)
        diagnostics_layout.addWidget(self.compare_diagnostics_group, 1)

        compare_dataset_tab = QWidget()
        self.compare_dataset_tab = compare_dataset_tab
        compare_dataset_layout = QVBoxLayout(compare_dataset_tab)
        compare_dataset_layout.setContentsMargins(8, 8, 8, 8)
        compare_dataset_layout.setSpacing(6)
        self.compare_dataset_browser = QTextBrowser()
        self.compare_dataset_browser.setReadOnly(True)
        self.compare_dataset_browser.setStyleSheet(dataset_browser_style)
        self.compare_dataset_browser.setMinimumHeight(120)
        self.compare_dataset_browser.setMaximumHeight(220)
        compare_dataset_layout.addWidget(self.compare_dataset_browser)
        self.compare_preview_table = QTableWidget()
        self.compare_preview_table.setAlternatingRowColors(True)
        self.compare_preview_table.setMinimumHeight(260)
        compare_dataset_layout.addWidget(self.compare_preview_table, 1)
        self.results_tabs.addTab(compare_tab, "Compare")

        stage_tab = QWidget()
        stage_layout = QVBoxLayout(stage_tab)
        self.stage_table = QTableWidget()
        self.stage_table.setColumnCount(7)
        self.stage_table.setHorizontalHeaderLabels(
            ["Stage", "Status", "Params", "Signals", "Before", "After", "Notes"]
        )
        stage_layout.addWidget(self.stage_table, 1)
        self.stage_browser = QTextBrowser()
        self.stage_browser.setReadOnly(True)
        stage_layout.addWidget(self.stage_browser, 1)
        self.stage_plot = pg.PlotWidget()
        self.stage_plot.showGrid(x=True, y=True, alpha=0.2)
        self.stage_plot.setLabel("bottom", "RPM")
        self.stage_plot.setLabel("left", "Torque / Power")
        stage_layout.addWidget(self.stage_plot, 2)
        self.results_tabs.addTab(stage_tab, "Calibration")

        validation_tab = QWidget()
        validation_layout = QVBoxLayout(validation_tab)
        self.validation_browser = QTextBrowser()
        self.validation_browser.setReadOnly(True)
        validation_layout.addWidget(self.validation_browser, 1)
        self.validation_table = QTableWidget()
        self.validation_table.setColumnCount(7)
        self.validation_table.setHorizontalHeaderLabels(
            ["Feature", "Outcome", "Supported", "Signals", "Improved", "Worsened", "Note"]
        )
        validation_layout.addWidget(self.validation_table, 2)
        self.results_tabs.addTab(validation_tab, "Validation")

        ab_tab = QWidget()
        ab_layout = QVBoxLayout(ab_tab)
        self.ab_browser = QTextBrowser()
        self.ab_browser.setReadOnly(True)
        ab_layout.addWidget(self.ab_browser, 1)
        self.ab_table = QTableWidget()
        self.ab_table.setColumnCount(4)
        self.ab_table.setHorizontalHeaderLabels(["Signal", "A MAPE", "B MAPE", "Delta"])
        ab_layout.addWidget(self.ab_table, 1)
        self.ab_plot = pg.PlotWidget()
        self.ab_plot.showGrid(x=True, y=True, alpha=0.2)
        self.ab_plot.setLabel("bottom", "RPM")
        self.ab_plot.setLabel("left", "Torque / Power")
        ab_layout.addWidget(self.ab_plot, 2)
        self.results_tabs.addTab(ab_tab, "A/B")

        sensitivity_tab = QWidget()
        sensitivity_layout = QVBoxLayout(sensitivity_tab)
        self.sensitivity_browser = QTextBrowser()
        self.sensitivity_browser.setReadOnly(True)
        sensitivity_layout.addWidget(self.sensitivity_browser, 1)
        self.sensitivity_rank_table = QTableWidget()
        self.sensitivity_rank_table.setColumnCount(4)
        self.sensitivity_rank_table.setHorizontalHeaderLabels(
            ["Signal", "Top param", "Max abs delta", "Robustness"]
        )
        sensitivity_layout.addWidget(self.sensitivity_rank_table, 1)
        self.sensitivity_param_table = QTableWidget()
        self.sensitivity_param_table.setColumnCount(5)
        self.sensitivity_param_table.setHorizontalHeaderLabels(
            ["Param", "Supported", "Overall influence", "Tradeoff", "Interpretation / note"]
        )
        sensitivity_layout.addWidget(self.sensitivity_param_table, 2)
        self.results_tabs.addTab(sensitivity_tab, "Sensitivity")

        optimize_tab = QWidget()
        optimize_layout = QVBoxLayout(optimize_tab)
        self.optimize_browser = QTextBrowser()
        self.optimize_browser.setReadOnly(True)
        optimize_layout.addWidget(self.optimize_browser, 1)
        self.optimize_candidate_table = QTableWidget()
        self.optimize_candidate_table.setColumnCount(6)
        self.optimize_candidate_table.setHorizontalHeaderLabels(
            ["Rank", "Params", "Score", "Feasible", "Objective metrics", "Tradeoffs / robustness"]
        )
        optimize_layout.addWidget(self.optimize_candidate_table, 2)
        self.results_tabs.addTab(optimize_tab, "Optimize")
        self.results_tabs.addTab(diagnostics_tab, "Diagnostics / Coverage")
        self.results_tabs.addTab(compare_dataset_tab, "Dataset detail")

        right_col.addWidget(self.results_tabs, 1)
        content_layout.addWidget(self.results_panel, 1)

        layout.addLayout(content_layout, 1)

        self.refresh_base_engine_label()
        self._render_idle_state()
        adaptive_index = self.adaptive_mode_combo.findData(self._state.get("adaptive_mode", "as_is"))
        if adaptive_index >= 0:
            self.adaptive_mode_combo.setCurrentIndex(adaptive_index)
        self.engine_toggle_button.toggled.connect(self._set_engine_visible)
        self._set_engine_visible(True)
        self.workflow_toggle_button.toggled.connect(self._set_workflow_visible)
        self._set_workflow_visible(True)
        self.advanced_group.toggled.connect(self._set_advanced_visible)
        self._set_advanced_visible(False)
        self._update_recent_state_banner()

    def refresh_base_engine_label(self) -> None:
        if self.selected_engine_path:
            engine_path = Path(self.selected_engine_path)
            self.base_engine_label.setText(
                "<div>"
                "<span style='color: #5f6b7a; font-size: 9px; font-weight: 700;'>Base engine</span> "
                f"<span style='color: #18212f; font-size: 11px; font-weight: 700;'>{engine_path.name}</span> "
                "<span style='color: #6a7888;'>external JSON</span>"
                f"<br><span style='color: #7b8795; font-size: 9px;'>{self.selected_engine_path}</span>"
                "</div>"
            )
            self._refresh_engine_header()
            self._refresh_context_strip()
            return
        current = self._engine_path_provider()
        if current:
            current_path = Path(current)
            self.base_engine_label.setText(
                "<div>"
                "<span style='color: #5f6b7a; font-size: 9px; font-weight: 700;'>Base engine</span> "
                f"<span style='color: #18212f; font-size: 11px; font-weight: 700;'>{current_path.name}</span> "
                "<span style='color: #6a7888;'>current editor engine</span>"
                f"<br><span style='color: #7b8795; font-size: 9px;'>{current}</span>"
                "</div>"
            )
        else:
            self.base_engine_label.setText(
                "<div>"
                "<span style='color: #5f6b7a; font-size: 9px; font-weight: 700;'>Base engine</span> "
                "<span style='color: #18212f; font-size: 11px; font-weight: 700;'>Unsaved configuration</span> "
                "<span style='color: #6a7888;'>current editor engine</span>"
                "</div>"
            )
        self._refresh_engine_header()
        self._refresh_context_strip()

    def use_current_engine(self) -> None:
        self.selected_engine_path = None
        self.refresh_base_engine_label()
        self._persist_ui_state()

    def browse_base_engine(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Choose Base Engine", "", "JSON Files (*.json)")
        if filename:
            self.selected_engine_path = filename
            self.refresh_base_engine_label()
            self._persist_ui_state()

    def _set_advanced_visible(self, visible: bool) -> None:
        self.advanced_group.setFlat(not visible)
        for idx in range(self.advanced_group.layout().count()):
            item = self.advanced_group.layout().itemAt(idx)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setVisible(visible)

    def _set_layout_widgets_visible(self, layout, visible: bool) -> None:
        for idx in range(layout.count()):
            item = layout.itemAt(idx)
            if item is None:
                continue
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.setVisible(visible)
            elif child_layout is not None:
                self._set_layout_widgets_visible(child_layout, visible)

    def _set_disclosure_button_label(self, button: QToolButton, title: str, visible: bool) -> None:
        chevron = "▾" if visible else "▸"
        button.setText(f"{chevron} {title}")

    def _compact_results_mode(self) -> bool:
        engine_collapsed = hasattr(self, "engine_toggle_button") and not self.engine_toggle_button.isChecked()
        workflow_collapsed = hasattr(self, "workflow_toggle_button") and not self.workflow_toggle_button.isChecked()
        return engine_collapsed or workflow_collapsed

    def _short_engine_name(self) -> str:
        if self.selected_engine_path:
            return Path(self.selected_engine_path).stem
        current = self._engine_path_provider()
        return Path(current).stem if current else "unsaved configuration"

    def _base_engine_summary(self) -> str:
        adaptive_value = str(self.adaptive_mode_combo.currentText()).replace("Adaptive combustion: ", "")
        adaptive_value = adaptive_value.replace("force ", "")
        return f"{self._short_engine_name()} | adaptive {adaptive_value}"

    def _refresh_engine_header(self) -> None:
        if not hasattr(self, "engine_summary_label"):
            return
        self.engine_summary_label.setText(self._base_engine_summary())

    def _set_engine_visible(self, visible: bool) -> None:
        self._set_disclosure_button_label(self.engine_toggle_button, "Base engine", visible)
        self.engine_content.setVisible(visible)
        self._refresh_engine_header()
        self._update_results_presentation()

    def _workflow_state_summary(self) -> str:
        dataset_state = "dataset loaded" if self.dataset_dir is not None else "no dataset"
        if self._busy_message:
            if self.staged_report is not None:
                calibration_state = "calibration done"
            elif self.dataset_dir is not None:
                calibration_state = "calibration pending"
            else:
                calibration_state = ""
            if self.compare_report is not None:
                compare_state = "compare done"
            elif self.dataset_dir is not None:
                compare_state = "compare pending"
            else:
                compare_state = ""
        else:
            compare_state = "compare done" if self.compare_report is not None else ("compare pending" if self.dataset_dir is not None else "")
            calibration_state = (
                "calibration done" if self.staged_report is not None else ("calibration pending" if self.dataset_dir is not None else "")
            )
        parts = [dataset_state]
        if compare_state:
            parts.append(compare_state)
        if calibration_state:
            parts.append(calibration_state)
        return " · ".join(parts)

    def _refresh_workflow_header(self) -> None:
        if not hasattr(self, "workflow_group"):
            return
        self.workflow_group.setTitle(f"Real dyno workflow · {self._workflow_state_summary()}")

    def _set_workflow_visible(self, visible: bool) -> None:
        self.workflow_group.setFlat(not visible)
        for widget in getattr(self, "workflow_content_widgets", []):
            widget.setVisible(visible)
        if visible:
            self._update_buttons_for_current_state()
        self._refresh_workflow_header()

    def _workflow_state_summary(self) -> str:
        if self._busy_message:
            return self._busy_message
        dataset_loaded = self.dataset_dir is not None
        dataset_state = "dataset loaded" if dataset_loaded else "dataset not loaded"
        compare_state = "compare done" if self.compare_report is not None else ("compare ready" if dataset_loaded else "compare not ready")
        calibration_state = (
            "calibration done" if self.staged_report is not None else ("calibration not run" if dataset_loaded else "calibration not ready")
        )
        parts = [dataset_state, compare_state]
        if dataset_loaded or self.staged_report is not None:
            parts.append(calibration_state)
        return " | ".join(parts)

    def _refresh_workflow_header(self) -> None:
        if not hasattr(self, "workflow_summary_label"):
            return
        self.workflow_summary_label.setText(self._workflow_state_summary())

    def _set_workflow_visible(self, visible: bool) -> None:
        self._set_disclosure_button_label(self.workflow_toggle_button, "Real dyno workflow", visible)
        self.workflow_content.setVisible(visible)
        if visible:
            self._update_buttons_for_current_state()
        else:
            self._refresh_workflow_header()
            self._refresh_context_strip()
        self._update_results_presentation()
        self._refresh_workflow_header()

    def _set_placeholder_panel(self, browser: QTextBrowser, message_html: str, *widgets: QWidget) -> None:
        browser.setHtml(message_html)
        for widget in widgets:
            widget.setVisible(False)

    def _show_panel_widgets(self, *widgets: QWidget) -> None:
        for widget in widgets:
            widget.setVisible(True)

    def _set_dataset_preview_visible(self, visible: bool) -> None:
        self.preview_table.setVisible(visible)
        self.dataset_browser.setMinimumHeight(84 if visible else 136)
        if hasattr(self, "compare_preview_table"):
            self.compare_preview_table.setVisible(visible)
        if hasattr(self, "compare_dataset_browser"):
            self.compare_dataset_browser.setMinimumHeight(120 if visible else 160)

    def _set_preview_table_content(self, table: QTableWidget, points: list[dict]) -> None:
        columns = [signal for signal in CANONICAL_SIGNALS if any(signal in point for point in points)]
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels([SIGNAL_LABELS[col] for col in columns])
        table.setRowCount(len(points))
        for row, point in enumerate(points):
            for col, signal in enumerate(columns):
                value = point.get(signal, "")
                if isinstance(value, float):
                    text = f"{value:.4f}" if signal in {"lambda", "afr"} else f"{value:.2f}"
                else:
                    text = str(value)
                table.setItem(row, col, QTableWidgetItem(text))

    def _update_results_presentation(self) -> None:
        compare_ready = self.compare_report is not None
        compact_results = self._compact_results_mode()
        if hasattr(self, "dataset_panel"):
            self.dataset_panel.setVisible(False)
        if hasattr(self, "dataset_title_label"):
            self.dataset_title_label.setText("Dataset detail" if compare_ready else "Dataset preview")
        if hasattr(self, "results_title_label"):
            self.results_title_label.setText("Comparison result" if self.dataset_dir is not None else "Results")
        if hasattr(self, "dataset_browser"):
            self.dataset_browser.setMaximumHeight(72 if compact_results and compare_ready else (92 if compare_ready else 220))
        if hasattr(self, "preview_table"):
            self.preview_table.setMaximumHeight(108 if compact_results and compare_ready else (132 if compare_ready else 360))
        if hasattr(self, "compare_plot"):
            self.compare_plot.setMinimumHeight(320 if compact_results and compare_ready else (380 if compare_ready else 320))
        if hasattr(self, "compare_browser"):
            self.compare_browser.setMinimumHeight(220 if compact_results and compare_ready else 260)
        if hasattr(self, "compare_diagnostics_group"):
            self.compare_diagnostics_group.setVisible(True)
        if hasattr(self, "compare_dataset_browser"):
            self.compare_dataset_browser.setMaximumHeight(200 if compact_results and compare_ready else 240)
        if hasattr(self, "compare_preview_table"):
            self.compare_preview_table.setMinimumHeight(260 if compact_results and compare_ready else 320)

    def _signals_present_summary(self) -> str:
        if not self.dataset_meta:
            return "none"
        signals = list(self.dataset_meta.get("signals_present", []))
        if not signals:
            return "none"
        if len(signals) <= 5:
            return ", ".join(signals)
        return ", ".join(signals[:5]) + f" +{len(signals) - 5} more"

    def _workflow_phase_summary(self) -> str:
        if self._busy_message:
            return self._busy_message
        if self.dataset_dir is None:
            return "Dataset not loaded"
        if self.compare_report is None and self.staged_report is None:
            return "Dataset loaded / compare not run"
        if self.compare_report is not None and self.staged_report is None:
            return "Compare ready / calibration not run"
        if self.staged_report is not None:
            return "Calibration ready"
        return "Workflow ready"

    def _results_ready_summary(self) -> str:
        ready = [
            label
            for label, payload in (
                ("compare", self.compare_report),
                ("calibration", self.staged_report),
                ("validation", self.validation_report),
                ("A/B", self.ab_report),
                ("sensitivity", self.sensitivity_report),
                ("optimize", self.optimize_report),
            )
            if payload is not None
        ]
        if not ready:
            return "none yet"
        if len(ready) <= 3:
            return ", ".join(ready)
        return f"{len(ready)} ready"

    def _refresh_context_strip(self) -> None:
        if not hasattr(self, "context_summary_label"):
            return
        dataset_value = "None"
        if self.dataset_dir is not None:
            dataset_value = str((self.dataset_meta or {}).get("dataset_id") or self.dataset_dir.name)
        adaptive_value = str(self.adaptive_mode_combo.currentText()).replace("Adaptive combustion: ", "")
        flow_value = self._workflow_phase_summary()
        signals_value = self._signals_present_summary()
        results_value = self._results_ready_summary()
        separator = " <span style='color: #90a0b3;'>&bull;</span> "
        top_line = separator.join(
            [
                f"<span style='color: #5f6b7a; font-weight: 700;'>Dataset:</span> <span style='color: #18212f;'>{dataset_value}</span>",
                f"<span style='color: #5f6b7a; font-weight: 700;'>Signals:</span> <span style='color: #18212f;'>{signals_value}</span>",
            ]
        )
        bottom_line = separator.join(
            [
                f"<span style='color: #5f6b7a; font-weight: 700;'>Adaptive:</span> <span style='color: #18212f;'>{adaptive_value}</span>",
                f"<span style='color: #5f6b7a; font-weight: 700;'>Flow:</span> <span style='color: #18212f;'>{flow_value}</span>",
                f"<span style='color: #5f6b7a; font-weight: 700;'>Results:</span> <span style='color: #18212f;'>{results_value}</span>",
            ]
        )
        self.context_summary_label.setText(top_line + "<br>" + bottom_line)

    def _render_idle_state(self) -> None:
        self._update_results_presentation()
        self._set_dataset_preview_visible(False)
        self.compare_summary_label.setText(
            "<div style='font-size: 11px; font-weight: 700; color: #18212f;'>Comparison summary</div>"
            "<div style='margin-top: 4px; color: #506072;'>Load a dataset to unlock compare and produce a verdict against the current base engine.</div>"
        )
        self.dataset_browser.setHtml(
            "<div style='padding: 4px 0;'>"
            "<div style='font-size: 12px; font-weight: 700; color: #18212f;'>No dataset loaded</div>"
            "<div style='margin-top: 4px; color: #506072;'>Import a CSV/JSON dyno source or load a canonical dataset package to unlock compare, calibration, and advanced analysis.</div>"
            "</div>"
        )
        self._set_placeholder_panel(
            self.compare_browser,
            "<div style='padding: 6px 0;'><b>No comparison yet.</b><br><span style='color: #506072;'>Load a dataset, then run compare to populate metrics, diagnostics, and overlay curves.</span></div>",
            self.compare_plot,
        )
        self.compare_dataset_browser.setHtml(
            "<div style='padding: 4px 0;'>"
            "<div style='font-size: 12px; font-weight: 700; color: #18212f;'>No dataset detail</div>"
            "<div style='margin-top: 4px; color: #506072;'>Load or import a dataset to inspect mapping, source units, and canonical points here.</div>"
            "</div>"
        )
        self._set_placeholder_panel(
            self.stage_browser,
            "<div style='padding: 6px 0;'><b>No calibration yet.</b><br><span style='color: #506072;'>Run staged calibration after a dataset is loaded to review stage-by-stage changes.</span></div>",
            self.stage_table,
            self.stage_plot,
        )
        self._set_placeholder_panel(
            self.validation_browser,
            "<div style='padding: 6px 0;'><b>No validation yet.</b><br><span style='color: #506072;'>Feature validation will summarize supported toggles and before/after deltas here.</span></div>",
            self.validation_table,
        )
        self._set_placeholder_panel(
            self.ab_browser,
            "<div style='padding: 6px 0;'><b>No A/B comparison yet.</b><br><span style='color: #506072;'>Run A/B compare to inspect two configurations side by side.</span></div>",
            self.ab_table,
            self.ab_plot,
        )
        self._set_placeholder_panel(
            self.sensitivity_browser,
            "<div style='padding: 6px 0;'><b>No sensitivity study yet.</b><br><span style='color: #506072;'>Run local sensitivity to rank parameter influence and robustness.</span></div>",
            self.sensitivity_rank_table,
            self.sensitivity_param_table,
        )
        self._set_placeholder_panel(
            self.optimize_browser,
            "<div style='padding: 6px 0;'><b>No optimize-guided study yet.</b><br><span style='color: #506072;'>Run optimize-guided to inspect candidate tradeoffs and scores.</span></div>",
            self.optimize_candidate_table,
        )
        self.preview_table.setRowCount(0)
        self.preview_table.setColumnCount(0)
        self.compare_preview_table.setRowCount(0)
        self.compare_preview_table.setColumnCount(0)
        self.stage_table.setRowCount(0)
        self.validation_table.setRowCount(0)
        self.ab_table.setRowCount(0)
        self.sensitivity_rank_table.setRowCount(0)
        self.sensitivity_param_table.setRowCount(0)
        self.optimize_candidate_table.setRowCount(0)
        self.compare_plot.clear()
        self.stage_plot.clear()
        self.ab_plot.clear()
        self._update_buttons_for_current_state()
        self._refresh_context_strip()

    def _engine_context(self) -> tuple[Engine, dict, Path, dict]:
        if self.selected_engine_path:
            path = Path(self.selected_engine_path)
            raw = json.loads(path.read_text(encoding="utf-8"))
            engine = Engine.from_dict(raw)
            engine, raw, summary = apply_adaptive_combustion_mode(
                engine,
                raw,
                mode=str(self.adaptive_mode_combo.currentData() or "as_is"),
            )
            return engine, raw, path, summary
        engine = self._engine_provider()
        raw = engine.to_dict()
        base_path = Path(self._engine_path_provider() or "<current_gui_engine>")
        engine, raw, summary = apply_adaptive_combustion_mode(
            Engine.from_dict(raw),
            raw,
            mode=str(self.adaptive_mode_combo.currentData() or "as_is"),
        )
        return engine, raw, base_path, summary

    def _variant_engine_context(self, mode: str) -> tuple[Engine, dict, str]:
        engine, raw, _, _ = self._engine_context()
        normalized = str(mode or "baseline")
        if normalized == "baseline":
            return engine, raw, "baseline"
        if normalized == "adaptive_on":
            adjusted_engine, adjusted_raw, _ = apply_adaptive_combustion_mode(engine, raw, mode="on")
            return adjusted_engine, adjusted_raw, "adaptive_on"
        if normalized == "adaptive_off":
            adjusted_engine, adjusted_raw, _ = apply_adaptive_combustion_mode(engine, raw, mode="off")
            return adjusted_engine, adjusted_raw, "adaptive_off"
        if normalized == "turbo_on":
            adjusted_engine, adjusted_raw, _ = apply_turbo_incremental_mode(engine, raw, mode="on")
            return adjusted_engine, adjusted_raw, "turbo_incremental_on"
        if normalized == "turbo_off":
            adjusted_engine, adjusted_raw, _ = apply_turbo_incremental_mode(engine, raw, mode="off")
            return adjusted_engine, adjusted_raw, "turbo_incremental_off"
        raise ValueError(f"Unsupported A/B mode '{mode}'")

    def _load_ui_state(self) -> dict:
        path = _real_dyno_state_path()
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _persist_ui_state(self) -> None:
        state = {
            "selected_engine_path": self.selected_engine_path,
            "adaptive_mode": str(self.adaptive_mode_combo.currentData() or "as_is"),
            "max_evals_per_stage": int(self.max_evals_spin.value()),
            "sensitivity_params": self.sensitivity_params_edit.text().strip(),
            "optimize_params": self.optimize_params_edit.text().strip(),
            "optimize_max_evals": int(self.optimize_max_evals_spin.value()),
            "last_dataset_dir": str(self.dataset_dir) if self.dataset_dir is not None else self._state.get("last_dataset_dir"),
            "last_import_config": self._state.get("last_import_config", {}),
            "last_export_dir": self._state.get("last_export_dir"),
            "last_report_dir": self._state.get("last_report_dir"),
        }
        self._state.update(state)
        path = _real_dyno_state_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _update_recent_state_banner(self) -> None:
        last_dataset = self._state.get("last_dataset_dir")
        if self.dataset_dir is not None:
            self.workflow_status_label.setText("Dataset loaded")
            self._refresh_workflow_header()
            self._refresh_context_strip()
            return
        if last_dataset:
            self.workflow_status_label.setText("Recent dataset available")
        else:
            self.workflow_status_label.setText("No dataset loaded yet.")
        self.reload_last_dataset_button.setEnabled(bool(last_dataset))
        self._refresh_workflow_header()
        self._refresh_context_strip()

    def _set_busy(self, running: bool, message: str = "") -> None:
        self._busy_message = message if running else ""
        widgets = [
            self.import_button,
            self.load_dataset_button,
            self.reload_last_dataset_button,
            self.compare_button,
            self.stage_button,
            self.validation_button,
            self.ab_button,
            self.sensitivity_button,
            self.optimize_button,
            self.export_compare_button,
            self.export_stage_button,
            self.open_report_button,
            self.export_bundle_button,
            self.current_engine_button,
            self.browse_engine_button,
        ]
        for widget in widgets:
            if running:
                widget.setEnabled(False)
            else:
                pass
        if running:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.workflow_status_label.setText(message)
            self._status_message(message, 0)
            self._refresh_workflow_header()
            self._refresh_context_strip()
        else:
            QApplication.restoreOverrideCursor()
            self._update_buttons_for_current_state()
            self._update_recent_state_banner()
            self._status_message(message or "Ready.", 3000)
        QApplication.processEvents()

    def _update_buttons_for_current_state(self) -> None:
        dataset_ready = self.dataset_dir is not None
        workflow_expanded = not hasattr(self, "workflow_toggle_button") or self.workflow_toggle_button.isChecked()
        any_results_ready = any(
            payload is not None
            for payload in (
                self.compare_report,
                self.staged_report,
                self.validation_report,
                self.ab_report,
                self.sensitivity_report,
                self.optimize_report,
            )
        )
        self.import_button.setEnabled(True)
        self.load_dataset_button.setEnabled(True)
        self.open_report_button.setEnabled(True)
        self.export_bundle_button.setEnabled(any_results_ready)
        self.current_engine_button.setEnabled(True)
        self.browse_engine_button.setEnabled(True)
        self.compare_button.setEnabled(dataset_ready)
        self.stage_button.setEnabled(dataset_ready)
        self.validation_button.setEnabled(dataset_ready)
        self.ab_button.setEnabled(dataset_ready)
        self.sensitivity_button.setEnabled(dataset_ready)
        self.optimize_button.setEnabled(dataset_ready and self.dataset_payload is not None)
        self.export_compare_button.setEnabled(self.compare_report is not None)
        self.export_stage_button.setEnabled(self.staged_report is not None and self.calibrated_engine_raw is not None)
        self.reload_last_dataset_button.setEnabled(bool(self._state.get("last_dataset_dir")))
        self.export_compare_button.setVisible(workflow_expanded and self.compare_report is not None)
        self.export_stage_button.setVisible(
            workflow_expanded and self.staged_report is not None and self.calibrated_engine_raw is not None
        )
        self.export_bundle_button.setVisible(workflow_expanded and any_results_ready)
        self.reload_last_dataset_button.setVisible(workflow_expanded and bool(self._state.get("last_dataset_dir")))
        self.open_report_button.setVisible(workflow_expanded and (not dataset_ready or any_results_ready))
        self.workflow_artifacts_label.setVisible(
            workflow_expanded and (any_results_ready or self.open_report_button.isVisible())
        )
        self._refresh_workflow_header()
        self._refresh_context_strip()

    def _render_dual_overlay(
        self,
        plot: pg.PlotWidget,
        *,
        points: list[dict],
        series_specs: list[tuple[str, list[float], str, object]],
    ) -> None:
        plot.clear()
        plot.addLegend(clear=True)
        rpm = [float(point["rpm"]) for point in points]
        for name, values, color, style in series_specs:
            plot.plot(rpm, values, pen=pg.mkPen(color, width=2, style=style), name=name)

    def _signal_series(self, points: list[dict], branch: str, signal: str) -> list[float]:
        return [float(point.get(branch, {}).get(signal, float("nan"))) for point in points]

    def launch_import_dialog(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Import Dyno Source", "", "Dyno Files (*.csv *.json)")
        if not filename:
            return
        default_preset = self.selected_engine_path or self._engine_path_provider() or "<current_gui_engine>"
        dialog = DynoImportDialog(
            Path(filename),
            default_preset,
            initial_config=self._state.get("last_import_config", {}),
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.import_dataset_from_config(dialog.config())
        except Exception as exc:
            self._show_error("Dyno import failed", str(exc))

    def reload_last_dataset(self) -> None:
        last_dataset = self._state.get("last_dataset_dir")
        if not last_dataset:
            self._show_error("Reload failed", "No recent dataset package is recorded yet.")
            return
        self.load_dataset_package(Path(last_dataset))

    def load_dataset_package_dialog(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Open Canonical Dataset Package", "")
        if not directory:
            return
        try:
            self.load_dataset_package(Path(directory))
        except Exception as exc:
            self._show_error("Dataset load failed", str(exc))

    def import_dataset_from_config(self, config: dict) -> None:
        self._set_busy(True, "Importing dyno source and canonicalizing dataset…")
        try:
            write_dataset_package(
                Path(config["source_path"]),
                Path(config["dataset_dir"]),
                dataset_id=str(config["dataset_id"]),
                engine_id=str(config["engine_id"]),
                preset_path=str(config["preset_path"]),
                notes=str(config["notes"]),
                error_contract=dict(config["error_contract"]),
                source_format=str(config["source_format"]),
                mapping=dict(config["mapping"]),
                units=dict(config["units"]),
                afr_stoich=float(config["afr_stoich"]),
            )
            self._state["last_import_config"] = {
                "dataset_id": str(config["dataset_id"]),
                "engine_id": str(config["engine_id"]),
                "preset_path": str(config["preset_path"]),
                "dataset_dir": str(config["dataset_dir"]),
                "mapping": dict(config["mapping"]),
                "units": dict(config["units"]),
                "afr_stoich": float(config["afr_stoich"]),
                "notes": str(config["notes"]),
                "error_contract": dict(config["error_contract"]),
            }
            self.load_dataset_package(Path(config["dataset_dir"]))
        finally:
            self._persist_ui_state()
            self._set_busy(False, "Dyno dataset imported and canonicalized.")

    def load_dataset_package(self, dataset_dir: Path) -> None:
        metadata_path = dataset_dir / "metadata.json"
        targets_path = dataset_dir / "target_curve.json"
        if not metadata_path.exists() or not targets_path.exists():
            raise ValueError("Dataset package must contain metadata.json and target_curve.json.")
        self.dataset_dir = dataset_dir
        self.dataset_meta = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.dataset_payload = json.loads(targets_path.read_text(encoding="utf-8"))
        self.compare_report = None
        self.staged_report = None
        self.validation_report = None
        self.ab_report = None
        self.sensitivity_report = None
        self.optimize_report = None
        self.calibrated_engine_raw = None
        self.benchmark_before_report = None
        self.benchmark_after_report = None
        self._state["last_dataset_dir"] = str(dataset_dir)
        self._persist_ui_state()
        self._render_dataset_preview()

    def _render_dataset_preview(self) -> None:
        if self.dataset_meta is None or self.dataset_payload is None:
            return
        self._update_results_presentation()
        self._set_dataset_preview_visible(True)
        warnings = self.dataset_meta.get("import_warnings", [])
        warning_html = "<br>".join(f"- {warning}" for warning in warnings) if warnings else "None"
        dataset_html = (
            "<div style='font-size: 12px; font-weight: 700; color: #18212f;'>Dataset package</div>"
            f"<b>Dataset id:</b> {self.dataset_meta.get('dataset_id', '')}<br>"
            f"<b>Engine id:</b> {self.dataset_meta.get('engine_id', '')}<br>"
            f"<b>Directory:</b> {self.dataset_dir}<br>"
            f"<b>Points:</b> {len(self.dataset_payload.get('points', []))}<br>"
            f"<b>Source file:</b> {self.dataset_meta.get('source_file', '')}<br>"
            f"<b>Source format:</b> {self.dataset_meta.get('source_format', '')}<br>"
            f"<b>Signals present:</b> {', '.join(self.dataset_meta.get('signals_present', [])) or 'none'}<br>"
            f"<b>Mapping:</b> {json.dumps(self.dataset_meta.get('mapping_applied', {}), indent=2)}<br>"
            f"<b>Original units:</b> {json.dumps(self.dataset_meta.get('original_units', {}), indent=2)}<br>"
            f"<b>Import warning count:</b> {len(warnings)}<br>"
            f"<b>Import warnings:</b><br>{warning_html}"
        )
        self.dataset_browser.setHtml(dataset_html)
        self.compare_dataset_browser.setHtml(dataset_html)
        points = list(self.dataset_payload.get("points", []))
        self._set_preview_table_content(self.preview_table, points)
        self._set_preview_table_content(self.compare_preview_table, points)
        self.compare_summary_label.setText(
            "<div style='font-size: 11px; font-weight: 700; color: #18212f;'>Comparison summary</div>"
            "<div style='margin-top: 4px; color: #506072;'>Dataset ready. Run compare to get the contract verdict, key error metrics, and overlay plot.</div>"
        )
        self._set_placeholder_panel(
            self.compare_browser,
            "<div style='padding: 6px 0;'><b>Dataset ready for compare.</b><br><span style='color: #506072;'>Run compare to populate metrics, diagnostics, and overlay curves.</span></div>",
            self.compare_plot,
        )
        self._set_placeholder_panel(
            self.stage_browser,
            "<div style='padding: 6px 0;'><b>Dataset ready for calibration.</b><br><span style='color: #506072;'>Run staged calibration to review stage results and before/after curves.</span></div>",
            self.stage_table,
            self.stage_plot,
        )
        self._set_placeholder_panel(
            self.validation_browser,
            "<div style='padding: 6px 0;'><b>Validation is available.</b><br><span style='color: #506072;'>Run feature validation to compare baseline, toggles, and staged results.</span></div>",
            self.validation_table,
        )
        self._set_placeholder_panel(
            self.ab_browser,
            "<div style='padding: 6px 0;'><b>A/B compare is available.</b><br><span style='color: #506072;'>Run A/B compare to inspect two configurations side by side.</span></div>",
            self.ab_table,
            self.ab_plot,
        )
        self._set_placeholder_panel(
            self.sensitivity_browser,
            "<div style='padding: 6px 0;'><b>Sensitivity is available.</b><br><span style='color: #506072;'>Run local sensitivity to rank parameter influence.</span></div>",
            self.sensitivity_rank_table,
            self.sensitivity_param_table,
        )
        self._set_placeholder_panel(
            self.optimize_browser,
            "<div style='padding: 6px 0;'><b>Optimize-guided is available.</b><br><span style='color: #506072;'>Run optimize-guided to inspect candidate tradeoffs.</span></div>",
            self.optimize_candidate_table,
        )
        self.compare_plot.clear()
        self.stage_plot.clear()
        self.ab_plot.clear()
        self.stage_table.setRowCount(0)
        self.validation_table.setRowCount(0)
        self.ab_table.setRowCount(0)
        self.sensitivity_rank_table.setRowCount(0)
        self.sensitivity_param_table.setRowCount(0)
        self.optimize_candidate_table.setRowCount(0)
        self._update_buttons_for_current_state()
        self._update_recent_state_banner()

    def _show_error(self, title: str, message: str) -> None:
        self.dataset_browser.setHtml(f"<b>Error</b><br>{message}")
        self.workflow_status_label.setText(f"{title}: {message}")
        self._status_message(f"{title}: {message}", 5000)
        QMessageBox.critical(self, title, message)

    def run_compare(self) -> None:
        if self.dataset_dir is None:
            self._show_error("Compare failed", "Import or load a dataset package first.")
            return
        self._set_busy(True, "Running simulator vs real-data comparison…")
        try:
            engine, raw, base_path, combustion_summary = self._engine_context()
            report = evaluate_with_engine(engine, raw, self.dataset_dir).to_dict()
            report.setdefault("metadata", {})["combustion"] = combustion_summary
            apply_analysis_envelope(
                report,
                report_type=REPORT_TYPE_COMPARE,
                context=build_report_context(engine_path=base_path),
            )
            self.compare_report = report
            self._render_compare_report()
            self._persist_ui_state()
        finally:
            self._set_busy(False, "Real dyno comparison completed.")

    def _render_compare_report(self) -> None:
        if self.compare_report is None:
            return
        self._update_results_presentation()
        self._show_panel_widgets(self.compare_plot)
        errors = self.compare_report["errors"]
        coverage = self.compare_report.get("signal_coverage", {})
        optional = errors.get("optional_signals", {})
        contract_pass = bool(self.compare_report.get("contract", {}).get("pass"))
        verdict_color = "#1f7a45" if contract_pass else "#b42318"
        verdict_label = "PASS" if contract_pass else "FAIL"
        optional_html = (
            "<br>".join(
                f"<b>{signal} MAPE:</b> {payload.get('mape', 0.0):.3f}"
                for signal, payload in sorted(optional.items())
            )
            if optional
            else "None"
        )
        combustion = self.compare_report.get("metadata", {}).get("combustion", {})
        self.compare_summary_label.setText(
            "<div style='font-size: 10px; font-weight: 700; color: #5f6b7a;'>Comparison result</div>"
            f"<div style='margin-top: 2px; font-size: 18px; font-weight: 800; color: {verdict_color};'>Contract {verdict_label}</div>"
            f"<div style='margin-top: 4px; color: #314154;'><b>Torque MAPE:</b> {errors['torque_nm']['mape']:.3f} &nbsp;&nbsp; "
            f"<b>Power MAPE:</b> {errors['power_hp']['mape']:.3f} &nbsp;&nbsp; "
            f"<b>Total MAPE:</b> {errors['total_mape']:.3f}</div>"
        )
        self.compare_browser.setHtml(
            f"<b>Coverage rationale:</b> Adaptive combustion = {combustion.get('adaptive_enabled')} "
            f"({combustion.get('adaptive_mode_requested', 'as_is')})<br><br>"
            f"<b>Dataset signals:</b> {', '.join(coverage.get('dataset_signals', [])) or 'none'}<br>"
            f"<b>Compared:</b> {', '.join(coverage.get('compared_signals', [])) or 'none'} &nbsp;&nbsp; "
            f"<b>Skipped:</b> {', '.join(coverage.get('skipped_signals', [])) or 'none'}<br>"
            f"<b>Optional metrics:</b><br>{optional_html}<br><br>"
            f"{_format_diagnostics_html(self.compare_report.get('diagnostics', []))}"
        )
        points = self.compare_report.get("points", [])
        self._render_dual_overlay(
            self.compare_plot,
            points=points,
            series_specs=[
                ("Torque real", self._signal_series(points, "target", "torque_nm"), "#1f77b4", Qt.SolidLine),
                ("Torque sim", self._signal_series(points, "predicted", "torque_nm"), "#1f77b4", Qt.DashLine),
                ("Power real", self._signal_series(points, "target", "power_hp"), "#d62728", Qt.SolidLine),
                ("Power sim", self._signal_series(points, "predicted", "power_hp"), "#d62728", Qt.DashLine),
            ],
        )
        self.results_tabs.setCurrentIndex(0)

    def run_feature_validation(self) -> None:
        if self.dataset_dir is None:
            self._show_error("Feature validation failed", "Import or load a dataset package first.")
            return
        self._set_busy(True, "Running comparative feature validation…")
        try:
            engine, raw, base_path, _ = self._engine_context()
            report = run_validation_batch(
                engine,
                raw,
                base_engine_path=base_path,
                dataset_dirs=[self.dataset_dir],
                include_adaptive_toggle=bool(self.validation_adaptive_check.isChecked()),
                include_turbo_toggle=bool(self.validation_turbo_check.isChecked()),
                include_staged_calibration=bool(self.validation_stage_check.isChecked()),
                max_evals_per_stage=int(self.max_evals_spin.value()),
            )
            self.validation_report = report
            self._render_validation_report()
            self._persist_ui_state()
        finally:
            self._set_busy(False, "Feature validation completed.")

    def _render_validation_report(self) -> None:
        if self.validation_report is None:
            return
        self._show_panel_widgets(self.validation_table)
        cases = list(self.validation_report.get("cases", []))
        if not cases:
            self.validation_browser.setHtml("No validation cases were produced.")
            self.validation_table.setRowCount(0)
            return
        case = cases[0]
        features = case.get("features", {})
        self.validation_table.setRowCount(len(features))
        for row, (feature_name, payload) in enumerate(features.items()):
            delta = payload.get("delta_vs_baseline", {})
            self.validation_table.setItem(row, 0, QTableWidgetItem(feature_name))
            self.validation_table.setItem(row, 1, QTableWidgetItem(_outcome_badge(payload.get("outcome", ""))))
            self.validation_table.setItem(row, 2, QTableWidgetItem("yes" if payload.get("supported") else "no"))
            self.validation_table.setItem(
                row,
                3,
                QTableWidgetItem(", ".join(payload.get("signal_coverage", {}).get("compared_signals", []))),
            )
            self.validation_table.setItem(row, 4, QTableWidgetItem(", ".join(delta.get("improved_signals", [])) or "-"))
            self.validation_table.setItem(row, 5, QTableWidgetItem(", ".join(delta.get("worsened_signals", [])) or "-"))
            self.validation_table.setItem(row, 6, QTableWidgetItem(str(payload.get("note", ""))))
        summary = self.validation_report.get("summary", {}).get("feature_summary", {})
        summary_html = "<br>".join(
            "<b>"
            + str(name)
            + "</b>: "
            + ", ".join(
                f"{comparison_outcome_label(outcome)}={item.get(f'{outcome}_cases', 0)}"
                for outcome in COMPARISON_OUTCOMES
            )
            for name, item in sorted(summary.items())
        ) or "None"
        coverage = case.get("signal_coverage", {})
        self.validation_browser.setHtml(
            "<h3>Feature validation</h3>"
            f"<b>Dataset:</b> {case.get('dataset', {}).get('dataset_id', '')}<br>"
            f"<b>Compared signals:</b> {', '.join(coverage.get('compared_signals', [])) or 'none'}<br>"
            f"<b>Skipped signals:</b> {', '.join(coverage.get('skipped_signals', [])) or 'none'}<br>"
            f"<b>Feature summary:</b><br>{summary_html}"
        )
        self.results_tabs.setCurrentIndex(2)

    def run_ab_analysis(self) -> None:
        if self.dataset_dir is None:
            self._show_error("A/B compare failed", "Import or load a dataset package first.")
            return
        self._set_busy(True, "Running explicit A/B comparison…")
        try:
            mode_a = str(self.ab_mode_a_combo.currentData() or "baseline")
            mode_b = str(self.ab_mode_b_combo.currentData() or "adaptive_on")
            engine_a, raw_a, label_a = self._variant_engine_context(mode_a)
            engine_b, raw_b, label_b = self._variant_engine_context(mode_b)
            base_path = self.selected_engine_path or self._engine_path_provider()
            report_a = evaluate_with_engine(engine_a, raw_a, self.dataset_dir).to_dict()
            report_b = evaluate_with_engine(engine_b, raw_b, self.dataset_dir).to_dict()
            report = run_ab_compare(
                engine_a,
                raw_a,
                engine_b,
                raw_b,
                dataset_dir=self.dataset_dir,
                label_a=label_a,
                label_b=label_b,
            )
            report["curve_points"] = {
                "a": list(report_a.get("points", [])),
                "b": list(report_b.get("points", [])),
            }
            apply_analysis_envelope(
                report,
                report_type=REPORT_TYPE_AB_COMPARE,
                context=build_report_context(engine_path=base_path),
            )
            self.ab_report = report
            self._render_ab_report()
            self._persist_ui_state()
        finally:
            self._set_busy(False, "A/B compare completed.")

    def _render_ab_report(self) -> None:
        if self.ab_report is None:
            return
        self._show_panel_widgets(self.ab_table, self.ab_plot)
        comparison = self.ab_report.get("comparison", {})
        delta = comparison.get("delta_a_to_b", {})
        by_signal = delta.get("by_signal", {})
        self.ab_table.setRowCount(len(by_signal))
        for row, (signal, values) in enumerate(sorted(by_signal.items())):
            self.ab_table.setItem(row, 0, QTableWidgetItem(signal))
            self.ab_table.setItem(row, 1, QTableWidgetItem(f"{float(values.get('baseline_mape', 0.0)):.3f}"))
            self.ab_table.setItem(row, 2, QTableWidgetItem(f"{float(values.get('candidate_mape', 0.0)):.3f}"))
            self.ab_table.setItem(row, 3, QTableWidgetItem(f"{float(values.get('delta_mape', 0.0)):+.3f}"))
        coverage = self.ab_report.get("signal_coverage", {})
        self.ab_browser.setHtml(
            "<h3>A/B comparison</h3>"
            f"<b>Outcome:</b> {_outcome_badge(comparison.get('outcome', COMPARISON_OUTCOME_DEFAULT))}<br>"
            f"<b>Compared signals:</b> {', '.join(coverage.get('compared_signals_union', [])) or 'none'}<br>"
            f"<b>Skipped signals:</b> {', '.join(coverage.get('skipped_signals_union', [])) or 'none'}<br>"
            f"<b>Improved:</b> {', '.join(delta.get('improved_signals', [])) or 'none'}<br>"
            f"<b>Worsened:</b> {', '.join(delta.get('worsened_signals', [])) or 'none'}<br>"
            f"<b>Note:</b> {comparison.get('note', '')}"
        )
        curve_points = self.ab_report.get("curve_points", {})
        points_a = list(curve_points.get("a", []))
        points_b = list(curve_points.get("b", []))
        points = points_a or points_b
        if points:
            labels = comparison.get("labels", {})
            self._render_dual_overlay(
                self.ab_plot,
                points=points,
                series_specs=[
                    ("Real torque", self._signal_series(points, "target", "torque_nm"), "#444444", Qt.SolidLine),
                    (f"{labels.get('a', 'A')} torque", self._signal_series(points, "predicted", "torque_nm"), "#1f77b4", Qt.SolidLine),
                    (f"{labels.get('b', 'B')} torque", self._signal_series(points_b or points, "predicted", "torque_nm"), "#1f77b4", Qt.DashLine),
                    ("Real power", self._signal_series(points, "target", "power_hp"), "#666666", Qt.SolidLine),
                    (f"{labels.get('a', 'A')} power", self._signal_series(points, "predicted", "power_hp"), "#d62728", Qt.SolidLine),
                    (f"{labels.get('b', 'B')} power", self._signal_series(points_b or points, "predicted", "power_hp"), "#d62728", Qt.DashLine),
                ],
            )
        else:
            self.ab_plot.clear()
        self.results_tabs.setCurrentIndex(3)

    def run_sensitivity_analysis(self) -> None:
        if self.dataset_dir is None:
            self._show_error("Sensitivity failed", "Import or load a dataset package first.")
            return
        params = _parse_param_list(self.sensitivity_params_edit.text())
        if not params:
            self._show_error("Sensitivity failed", "Enter at least one supported sensitivity parameter.")
            return
        self._set_busy(True, "Running local sensitivity study…")
        try:
            engine, raw, base_path, _ = self._engine_context()
            report = run_local_sensitivity(engine, raw, dataset_dir=self.dataset_dir, params=params)
            apply_analysis_envelope(
                report,
                report_type=REPORT_TYPE_SENSITIVITY_LOCAL,
                context=build_report_context(engine_path=base_path),
            )
            self.sensitivity_report = report
            self._render_sensitivity_report()
            self._persist_ui_state()
        finally:
            self._set_busy(False, "Local sensitivity completed.")

    def _render_sensitivity_report(self) -> None:
        if self.sensitivity_report is None:
            return
        self._show_panel_widgets(self.sensitivity_rank_table, self.sensitivity_param_table)
        summary = self.sensitivity_report.get("summary", {})
        robustness = summary.get("robustness_by_signal", {})
        self.sensitivity_rank_table.setRowCount(len(robustness))
        for row, (signal, payload) in enumerate(sorted(robustness.items())):
            self.sensitivity_rank_table.setItem(row, 0, QTableWidgetItem(signal))
            self.sensitivity_rank_table.setItem(row, 1, QTableWidgetItem(str(payload.get("top_param", ""))))
            self.sensitivity_rank_table.setItem(row, 2, QTableWidgetItem(f"{float(payload.get('max_abs_delta_mape', 0.0)):.3f}"))
            self.sensitivity_rank_table.setItem(row, 3, QTableWidgetItem(str(payload.get("level", ""))))
        params = list(self.sensitivity_report.get("params", []))
        self.sensitivity_param_table.setRowCount(len(params))
        for row, payload in enumerate(params):
            self.sensitivity_param_table.setItem(row, 0, QTableWidgetItem(str(payload.get("param", ""))))
            self.sensitivity_param_table.setItem(row, 1, QTableWidgetItem("yes" if payload.get("supported") else "no"))
            score = payload.get("overall_influence_score")
            self.sensitivity_param_table.setItem(row, 2, QTableWidgetItem("" if score is None else f"{float(score):.3f}"))
            self.sensitivity_param_table.setItem(row, 3, QTableWidgetItem("yes" if payload.get("tradeoff_detected") else "no"))
            note = f"{payload.get('interpretation', '')} {payload.get('note', '')}".strip()
            self.sensitivity_param_table.setItem(row, 4, QTableWidgetItem(note))
        ranking_html = "<br>".join(
            f"<b>{signal}</b>: top={payload.get('top_param', '')}, level={payload.get('level', '')}, "
            f"max_abs_delta_mape={float(payload.get('max_abs_delta_mape', 0.0)):.3f}"
            for signal, payload in sorted(robustness.items())
        ) or "No robustness conclusion could be made from the scored signals."
        self.sensitivity_browser.setHtml(
            "<h3>Local sensitivity</h3>"
            "<b>Interpretation:</b> local perturbation only, not global uncertainty quantification.<br>"
            f"<b>Robustness by signal:</b><br>{ranking_html}"
        )
        self.results_tabs.setCurrentIndex(4)

    def run_optimize_analysis(self) -> None:
        if self.dataset_dir is None or self.dataset_payload is None:
            self._show_error("Optimize-guided failed", "Import or load a dataset package first.")
            return
        params = _parse_param_list(self.optimize_params_edit.text())
        if not params:
            self._show_error("Optimize-guided failed", "Enter at least one supported optimization parameter.")
            return
        self._set_busy(True, "Running bounded optimize-guided search…")
        try:
            engine, _, base_path, _ = self._engine_context()
            constraints = {}
            error_contract = dict((self.dataset_meta or {}).get("error_contract", {}))
            max_signal_mape = {}
            for signal in ("torque_nm", "power_hp"):
                limit = error_contract.get(f"{signal.split('_')[0]}_mape_max")
                if limit is not None:
                    max_signal_mape[signal] = float(limit)
            if max_signal_mape:
                constraints["max_signal_mape"] = max_signal_mape
            optimize_points = []
            for point in list(self.dataset_payload.get("points", [])):
                filtered = {"rpm": point["rpm"]}
                for signal in ("torque_nm", "power_hp"):
                    if signal in point:
                        filtered[signal] = point[signal]
                optimize_points.append(filtered)
            report = optimize_guided(
                engine,
                objective="dataset_error",
                params=params,
                seed=0,
                max_evals=int(self.optimize_max_evals_spin.value()),
                target_points=optimize_points,
                constraints=constraints,
            ).to_dict()
            apply_analysis_envelope(
                report,
                report_type=REPORT_TYPE_OPTIMIZE_GUIDED,
                context=build_report_context(dataset=self.dataset_meta, engine_path=base_path),
            )
            self.optimize_report = report
            self._render_optimize_report()
            self._persist_ui_state()
        finally:
            self._set_busy(False, "Optimize-guided completed.")

    def _render_optimize_report(self) -> None:
        if self.optimize_report is None:
            return
        self._show_panel_widgets(self.optimize_candidate_table)
        candidates = list(self.optimize_report.get("candidates", []))
        self.optimize_candidate_table.setRowCount(len(candidates))
        for row, candidate in enumerate(candidates):
            self.optimize_candidate_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self.optimize_candidate_table.setItem(row, 1, QTableWidgetItem(json.dumps(candidate.get("params", {}), sort_keys=True)))
            self.optimize_candidate_table.setItem(row, 2, QTableWidgetItem(f"{float(candidate.get('score', 0.0)):.6f}"))
            self.optimize_candidate_table.setItem(row, 3, QTableWidgetItem("yes" if candidate.get("feasible") else "no"))
            self.optimize_candidate_table.setItem(row, 4, QTableWidgetItem(json.dumps(candidate.get("objective_metrics", {}), sort_keys=True)))
            notes = list(candidate.get("tradeoff_notes", []))
            robustness = candidate.get("robustness", {})
            if robustness:
                notes.append(f"fragility={robustness.get('fragility', '')}, spread={float(robustness.get('top_score_spread', 0.0)):.6f}")
            self.optimize_candidate_table.setItem(row, 5, QTableWidgetItem(" | ".join(notes) or "-"))
        best = dict(self.optimize_report.get("best_candidate", {}))
        warnings = list(self.optimize_report.get("warnings", []))
        self.optimize_browser.setHtml(
            "<h3>Optimize-guided</h3>"
            f"<b>Objective:</b> {self.optimize_report.get('optimization_problem', {}).get('objective', '')}<br>"
            f"<b>Params:</b> {', '.join(self.optimize_report.get('optimization_problem', {}).get('params', []))}<br>"
            f"<b>Signals scored:</b> {', '.join(self.optimize_report.get('optimization_problem', {}).get('signals_scored', [])) or 'none'}<br>"
            f"<b>Baseline score:</b> {float(self.optimize_report.get('baseline', {}).get('score', 0.0)):.6f}<br>"
            f"<b>Best candidate score:</b> {float(best.get('score', 0.0)):.6f}<br>"
            f"<b>Best params:</b><br>{_json_html(best.get('params', {}))}<br>"
            f"<b>Best objective metrics:</b><br>{_json_html(best.get('objective_metrics', {}))}<br>"
            f"<b>Tradeoffs / robustness:</b><br>{'<br>'.join(best.get('tradeoff_notes', [])) or 'None'}<br>"
            f"<b>Warnings:</b><br>{'<br>'.join(warnings) or 'None'}"
        )
        self.results_tabs.setCurrentIndex(5)

    def _load_report_payload(self, payload: dict) -> None:
        report_type = str(payload.get("report_type", "")).strip()
        if report_type == REPORT_TYPE_OPTIMIZE_GUIDED:
            self.optimize_report = payload
            self._render_optimize_report()
            return
        if report_type == REPORT_TYPE_AB_COMPARE:
            self.ab_report = payload
            self._render_ab_report()
            return
        if report_type == REPORT_TYPE_SENSITIVITY_LOCAL:
            self.sensitivity_report = payload
            self._render_sensitivity_report()
            return
        if report_type == REPORT_TYPE_VALIDATION_COMPARE:
            self.validation_report = payload
            self._render_validation_report()
            return
        if report_type == REPORT_TYPE_STAGED_CALIBRATION:
            self.staged_report = payload
            self._render_staged_report()
            return
        if report_type == REPORT_TYPE_COMPARE:
            self.compare_report = payload
            self._render_compare_report()
            return
        if "optimization_problem" in payload and "best_candidate" in payload and "candidates" in payload:
            self.optimize_report = payload
            self._render_optimize_report()
            return
        if "comparison" in payload and "signal_coverage" in payload and "dataset" in payload:
            self.ab_report = payload
            self._render_ab_report()
            return
        if "params" in payload and "summary" in payload and "baseline" in payload:
            self.sensitivity_report = payload
            self._render_sensitivity_report()
            return
        if "cases" in payload and "summary" in payload and "metadata" in payload:
            self.validation_report = payload
            self._render_validation_report()
            return
        if "stages" in payload and "final_params" in payload:
            self.staged_report = payload
            self._render_staged_report()
            return
        if "errors" in payload and "points" in payload and "dataset" in payload:
            self.compare_report = payload
            self._render_compare_report()
            return
        raise ValueError("This JSON file is not a supported Real Dyno analysis artifact.")

    def open_analysis_report_dialog(self) -> None:
        start_dir = self._state.get("last_report_dir") or self._state.get("last_export_dir") or ""
        filename, _ = QFileDialog.getOpenFileName(self, "Open Analysis Report", str(start_dir), "JSON Files (*.json)")
        if not filename:
            return
        payload = json.loads(Path(filename).read_text(encoding="utf-8"))
        self._load_report_payload(payload)
        self._state["last_report_dir"] = str(Path(filename).parent)
        self._persist_ui_state()
        self._update_buttons_for_current_state()
        self._status_message(f"Loaded analysis report from {filename}", 3000)

    def export_analysis_bundle_to_dir(self, out_dir: Path) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        manifest_entries: list[dict] = []
        payloads = [
            ("compare_report", "compare.json", self.compare_report),
            ("staged_calibration_report", "staged_calibration.json", self.staged_report),
            ("benchmark_before_report", "benchmark_before.json", self.benchmark_before_report),
            ("benchmark_after_report", "benchmark_after.json", self.benchmark_after_report),
            ("calibrated_engine", "calibrated_engine.json", self.calibrated_engine_raw),
            ("validation_compare_report", "validation_compare.json", self.validation_report),
            ("ab_compare_report", "ab_compare.json", self.ab_report),
            ("sensitivity_local_report", "sensitivity_local.json", self.sensitivity_report),
            ("optimize_guided_report", "optimize_guided.json", self.optimize_report),
        ]
        for artifact_type, filename, payload in payloads:
            if payload is None:
                continue
            path = out_dir / filename
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            written.append(path)
            manifest_entries.append(manifest_entry(artifact_type=artifact_type, filename=filename, payload=payload))
        if manifest_entries:
            written.append(write_manifest(out_dir, manifest_entries))
        self._state["last_export_dir"] = str(out_dir)
        self._persist_ui_state()
        return written

    def export_analysis_bundle_dialog(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "Export Analysis Bundle",
            str(self._state.get("last_export_dir") or self._state.get("last_dataset_dir") or ""),
        )
        if not directory:
            return
        written = self.export_analysis_bundle_to_dir(Path(directory))
        self._status_message(f"Exported {len(written)} analysis artifact(s) to {directory}", 4000)

    def run_staged_calibration(self) -> None:
        if self.dataset_dir is None:
            self._show_error("Staged calibration failed", "Import or load a dataset package first.")
            return
        self._set_busy(True, "Running staged calibration across supported stages…")
        try:
            engine, raw, base_path, combustion_summary = self._engine_context()
            self.stage_browser.setHtml("<b>Running staged calibration…</b>")
            report, calibrated_raw, bench_before, bench_after = run_staged_calibration(
                engine,
                raw,
                base_engine_path=base_path,
                dataset_dir=self.dataset_dir,
                max_evals_per_stage=int(self.max_evals_spin.value()),
            )
            report["combustion_requested"] = combustion_summary
            self.staged_report = report
            self.calibrated_engine_raw = calibrated_raw
            self.benchmark_before_report = bench_before
            self.benchmark_after_report = bench_after
            self._render_staged_report()
            self._persist_ui_state()
        finally:
            self._set_busy(False, "Staged calibration completed.")

    def _stage_status(self, stage: dict) -> str:
        return stage_status_label(stage_status_from_entry(stage))

    def _render_staged_report(self) -> None:
        if self.staged_report is None:
            return
        self._show_panel_widgets(self.stage_table, self.stage_plot)
        stages = self.staged_report.get("stages", [])
        self.stage_table.setRowCount(len(stages))
        for row, stage in enumerate(stages):
            self.stage_table.setItem(row, 0, QTableWidgetItem(str(stage.get("stage_name", ""))))
            self.stage_table.setItem(row, 1, QTableWidgetItem(self._stage_status(stage)))
            self.stage_table.setItem(row, 2, QTableWidgetItem(", ".join(stage.get("params_touched", []))))
            self.stage_table.setItem(row, 3, QTableWidgetItem(", ".join(stage.get("signals_used", []))))
            self.stage_table.setItem(row, 4, QTableWidgetItem(_format_metrics(stage.get("before_metrics", {}))))
            self.stage_table.setItem(row, 5, QTableWidgetItem(_format_metrics(stage.get("after_metrics", {}))))
            self.stage_table.setItem(row, 6, QTableWidgetItem(str(stage.get("notes", ""))))
        final_params = self.staged_report.get("final_params", {})
        artifacts = self.staged_report.get("artifacts", {})
        combustion_after = self.staged_report.get("combustion_after", {})
        before_errors = (self.benchmark_before_report or {}).get("errors", {})
        after_errors = (self.benchmark_after_report or {}).get("errors", {})
        self.stage_browser.setHtml(
            "<h3>Staged calibration result</h3>"
            f"<b>Adaptive combustion:</b> {combustion_after.get('adaptive_enabled')} "
            f"({combustion_after.get('adaptive_mode_requested', 'as_is')})<br>"
            f"<b>Before total MAPE:</b> {float(before_errors.get('total_mape', 0.0)):.3f}<br>"
            f"<b>After total MAPE:</b> {float(after_errors.get('total_mape', 0.0)):.3f}<br>"
            f"<b>Final params:</b> {json.dumps(final_params, indent=2)}<br>"
            f"<b>Artifacts:</b> {json.dumps(artifacts, indent=2)}<br><br>"
            f"{_format_diagnostics_html(self.staged_report.get('diagnostics', []))}"
        )
        before_points = list((self.benchmark_before_report or {}).get("points", []))
        after_points = list((self.benchmark_after_report or {}).get("points", []))
        points = after_points or before_points
        if points:
            self._render_dual_overlay(
                self.stage_plot,
                points=points,
                series_specs=[
                    ("Real torque", self._signal_series(points, "target", "torque_nm"), "#444444", Qt.SolidLine),
                    ("Before torque", self._signal_series(before_points or points, "predicted", "torque_nm"), "#1f77b4", Qt.SolidLine),
                    ("After torque", self._signal_series(after_points or points, "predicted", "torque_nm"), "#1f77b4", Qt.DashLine),
                    ("Real power", self._signal_series(points, "target", "power_hp"), "#666666", Qt.SolidLine),
                    ("Before power", self._signal_series(before_points or points, "predicted", "power_hp"), "#d62728", Qt.SolidLine),
                    ("After power", self._signal_series(after_points or points, "predicted", "power_hp"), "#d62728", Qt.DashLine),
                ],
            )
        else:
            self.stage_plot.clear()
        self.results_tabs.setCurrentIndex(1)

    def export_compare_report(self) -> None:
        if self.compare_report is None:
            return
        start_dir = self._state.get("last_export_dir") or self._state.get("last_dataset_dir") or ""
        filename, _ = QFileDialog.getSaveFileName(self, "Export Compare Report", str(Path(start_dir) / "compare.json" if start_dir else "compare.json"), "JSON Files (*.json)")
        if not filename:
            return
        Path(filename).write_text(json.dumps(self.compare_report, indent=2), encoding="utf-8")
        self._state["last_export_dir"] = str(Path(filename).parent)
        self._persist_ui_state()
        self._status_message(f"Compare report exported to {filename}", 3000)

    def export_staged_artifacts(self) -> None:
        if self.staged_report is None or self.calibrated_engine_raw is None:
            return
        directory = QFileDialog.getExistingDirectory(
            self,
            "Export Staged Calibration Artifacts",
            str(self._state.get("last_export_dir") or self._state.get("last_dataset_dir") or ""),
        )
        if not directory:
            return
        out_dir = Path(directory)
        out_dir.mkdir(parents=True, exist_ok=True)
        staged_path = out_dir / "staged_calibration.json"
        bench_before_path = out_dir / "benchmark_before.json"
        bench_after_path = out_dir / "benchmark_after.json"
        calibrated_path = out_dir / "calibrated_engine.json"
        staged_payload = dict(self.staged_report)
        staged_payload["artifacts"] = {
            "calibrated_engine": str(calibrated_path),
            "benchmark_before": str(bench_before_path),
            "benchmark_after": str(bench_after_path),
        }
        staged_path.write_text(json.dumps(staged_payload, indent=2), encoding="utf-8")
        bench_before_path.write_text(json.dumps(self.benchmark_before_report, indent=2), encoding="utf-8")
        bench_after_path.write_text(json.dumps(self.benchmark_after_report, indent=2), encoding="utf-8")
        calibrated_path.write_text(json.dumps(self.calibrated_engine_raw, indent=2), encoding="utf-8")
        self._state["last_export_dir"] = str(out_dir)
        self._persist_ui_state()
        self._status_message(f"Staged calibration artifacts exported to {directory}", 3000)
