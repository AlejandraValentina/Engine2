from __future__ import annotations

import html
import json
import logging
import math
import traceback
from pathlib import Path
from typing import Any, Optional

import numpy as np

import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer, QRectF, QThread, QElapsedTimer
from PySide6.QtGui import QAction, QColor, QBrush, QFont
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QCheckBox,
    QProgressBar,
    QTextBrowser,
    QTextEdit,
    QPushButton,
    QSplitter,
    QSlider,
    QStyle,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from acoustics.audio_generator import AudioSynthesizer, generate_full_engine_sound
from core import numerics
from core.engine_components import (
    Block,
    Camshaft,
    Combustion,
    CylinderHead,
    Engine,
    ExhaustSystem,
    Fuel,
    Friction,
    IntakeSystem,
    SimulationSettings,
    Supercharger,
    Turbo,
)
from core.engine_wizard import (
    COMPLEXITY_FIELDS,
    WizardSpec,
    build_engine_from_wizard,
    review_wizard_spec,
    summarize_engine_for_wizard,
)
from core.junctions import Junction
from core.model import Pipe
from core.pro_dyno_v2 import ProDynoV2Runner
from gui.workers.dyno_worker import DynoWorker
from core.simulator import Engine1DSolver
from core.thermo import CylinderSimulator
from core.units import cc_to_m3
from core.wave_utils import compute_image_levels, compute_pressure_matrix
from pywavedyn.analysis_contract import OBSERVABLE_VE_ACTUAL, apply_observable_semantics
from pywavedyn.cli import _metadata as cli_metadata
from core.knock import KnockConfig, compute_knock_index
from gui.real_dyno_workbench import RealDynoWorkbench
from gui.widgets.scope_widget import ScopeWidget

FUEL_PRESET_DEFINITIONS = {
    "Súper 95": {
        "type_name": "Gasoline",
        "octane_rating": 95.0,
        "energy_density": 44e6,
        "stoich_afr": 14.7,
        "match_names": {"super 95", "súper 95", "pump_95"},
    },
    "Premium 97": {
        "type_name": "Gasoline",
        "octane_rating": 97.0,
        "energy_density": 44e6,
        "stoich_afr": 14.7,
        "match_names": {"premium 97", "premium", "premium_97"},
    },
    "Race Gas (100)": {
        "type_name": "Race Gas",
        "octane_rating": 100.0,
        "energy_density": 44e6,
        "stoich_afr": 14.7,
        "match_names": {"race gas 100"},
    },
    "Race Gas (110)": {
        "type_name": "Race Gas",
        "octane_rating": 110.0,
        "energy_density": 46e6,
        "stoich_afr": 14.2,
        "match_names": {"race gas 110", "race gas"},
    },
    "E85": {
        "type_name": "E85",
        "octane_rating": 105.0,
        "energy_density": 29e6,
        "stoich_afr": 9.8,
        "match_names": {"e85"},
    },
    "Methanol": {
        "type_name": "Methanol",
        "octane_rating": 110.0,
        "energy_density": 20e6,
        "stoich_afr": 6.4,
        "match_names": {"methanol"},
    },
    "Custom": {
        "type_name": "Custom",
        "match_names": {"custom"},
    },
}

FUEL_PRESET_GROUPS = (
    ("primary", ("Súper 95", "Premium 97")),
    ("advanced", ("Race Gas (100)", "Race Gas (110)", "E85", "Methanol", "Custom")),
)

FUEL_PRESET_LEGACY_ALIASES = {
    "Regular (87)": {
        "type_name": "Regular",
        "octane_rating": 87.0,
        "energy_density": 44e6,
        "stoich_afr": 14.7,
    },
    "Premium (93)": {
        "type_name": "Premium",
        "octane_rating": 93.0,
        "energy_density": 44e6,
        "stoich_afr": 14.7,
    },
}


class GuidedEngineWizardDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Guided Engine")
        self.resize(760, 620)
        self.generated_engine: Optional[Engine] = None

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.complexity_combo = QComboBox()
        self.complexity_combo.addItems(["Basic", "Advanced", "Expert"])
        self.use_case_combo = QComboBox()
        self.use_case_combo.addItems(["Street", "Track", "Tow", "Prototype"])
        self.architecture_combo = QComboBox()
        self.architecture_combo.addItems(["Inline-4", "V6", "V8", "Single Cylinder"])
        self.aspiration_combo = QComboBox()
        self.aspiration_combo.addItems(["Naturally Aspirated", "Turbo"])
        self.objective_combo = QComboBox()
        self.objective_combo.addItem("Torque Mean", "torque_mean")
        self.objective_combo.addItem("Peak Power", "peak_power")
        self.objective_combo.addItem("Spool", "spool")
        self.objective_combo.addItem("Efficiency", "efficiency")
        self.objective_combo.addItem("Sound", "sound")
        self.rpm_start_spin = QSpinBox()
        self.rpm_start_spin.setRange(1000, 20000)
        self.rpm_start_spin.setSingleStep(250)
        self.rpm_start_spin.setValue(2000)
        self.rpm_end_spin = QSpinBox()
        self.rpm_end_spin.setRange(1500, 22000)
        self.rpm_end_spin.setSingleStep(250)
        self.rpm_end_spin.setValue(8000)

        form.addRow("Complexity", self.complexity_combo)
        form.addRow("Use case", self.use_case_combo)
        form.addRow("Architecture", self.architecture_combo)
        form.addRow("Aspiration", self.aspiration_combo)
        form.addRow("Primary objective", self.objective_combo)
        form.addRow("Target RPM start", self.rpm_start_spin)
        form.addRow("Target RPM end", self.rpm_end_spin)
        layout.addLayout(form)

        self.advanced_group = QGroupBox("Advanced")
        advanced_form = QFormLayout(self.advanced_group)
        self.displacement_spin = self._make_spin(2000.0, 100.0, 12000.0, 10.0, " cc")
        self.compression_spin = self._make_spin(11.0, 5.0, 18.0, 0.1, ":1")
        self.runner_length_spin = self._make_spin(320.0, 50.0, 1000.0, 5.0, " mm")
        self.header_length_spin = self._make_spin(650.0, 50.0, 2000.0, 10.0, " mm")
        advanced_form.addRow("Displacement", self.displacement_spin)
        advanced_form.addRow("Compression ratio", self.compression_spin)
        advanced_form.addRow("Runner length", self.runner_length_spin)
        advanced_form.addRow("Header length", self.header_length_spin)
        layout.addWidget(self.advanced_group)

        self.expert_group = QGroupBox("Expert")
        expert_form = QFormLayout(self.expert_group)
        self.runner_diameter_spin = self._make_spin(45.0, 10.0, 120.0, 1.0, " mm")
        self.header_diameter_spin = self._make_spin(38.0, 10.0, 120.0, 1.0, " mm")
        self.port_flow_eff_spin = self._make_spin(0.70, 0.2, 1.0, 0.01)
        self.thermal_eff_spin = self._make_spin(0.50, 0.2, 0.8, 0.01)
        self.peak_rpm_spin = self._make_spin(5500.0, 500.0, 22000.0, 100.0, " rpm")
        self.redline_spin = self._make_spin(8000.0, 1000.0, 22000.0, 100.0, " rpm")
        self.intake_duration_spin = self._make_spin(260.0, 180.0, 360.0, 1.0, " deg")
        self.exhaust_duration_spin = self._make_spin(264.0, 180.0, 360.0, 1.0, " deg")
        self.intake_lift_spin = self._make_spin(10.5, 4.0, 20.0, 0.1, " mm")
        self.exhaust_lift_spin = self._make_spin(10.0, 4.0, 20.0, 0.1, " mm")
        self.lsa_spin = self._make_spin(110.0, 90.0, 130.0, 0.5, " deg")
        self.ignition_spin = self._make_spin(28.0, 0.0, 60.0, 0.5, " deg BTDC")
        self.boost_spin = self._make_spin(70.0, 5.0, 200.0, 1.0, " kPa")
        expert_form.addRow("Runner diameter", self.runner_diameter_spin)
        expert_form.addRow("Header diameter", self.header_diameter_spin)
        expert_form.addRow("Port flow efficiency", self.port_flow_eff_spin)
        expert_form.addRow("Thermal efficiency", self.thermal_eff_spin)
        expert_form.addRow("Cam peak RPM", self.peak_rpm_spin)
        expert_form.addRow("Redline RPM", self.redline_spin)
        expert_form.addRow("Intake duration", self.intake_duration_spin)
        expert_form.addRow("Exhaust duration", self.exhaust_duration_spin)
        expert_form.addRow("Intake lift", self.intake_lift_spin)
        expert_form.addRow("Exhaust lift", self.exhaust_lift_spin)
        expert_form.addRow("Lobe separation", self.lsa_spin)
        expert_form.addRow("Ignition advance", self.ignition_spin)
        expert_form.addRow("Target boost", self.boost_spin)
        layout.addWidget(self.expert_group)

        layout.addWidget(QLabel("Generated preset summary"))
        self.summary_browser = QTextBrowser()
        self.summary_browser.setReadOnly(True)
        layout.addWidget(self.summary_browser, 1)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.export_button = self.button_box.addButton("Export JSON...", QDialogButtonBox.ActionRole)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.export_button.clicked.connect(self.export_json)
        layout.addWidget(self.button_box)

        widgets = [
            self.complexity_combo,
            self.use_case_combo,
            self.architecture_combo,
            self.aspiration_combo,
            self.objective_combo,
            self.rpm_start_spin,
            self.rpm_end_spin,
            self.displacement_spin,
            self.compression_spin,
            self.runner_length_spin,
            self.header_length_spin,
            self.runner_diameter_spin,
            self.header_diameter_spin,
            self.port_flow_eff_spin,
            self.thermal_eff_spin,
            self.peak_rpm_spin,
            self.redline_spin,
            self.intake_duration_spin,
            self.exhaust_duration_spin,
            self.intake_lift_spin,
            self.exhaust_lift_spin,
            self.lsa_spin,
            self.ignition_spin,
            self.boost_spin,
        ]
        for widget in widgets:
            if hasattr(widget, "currentIndexChanged"):
                widget.currentIndexChanged.connect(lambda *_: self._refresh_preview())
            elif hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(lambda *_: self._refresh_preview())
        self.complexity_combo.currentIndexChanged.connect(lambda *_: self._update_complexity_visibility())
        self.aspiration_combo.currentIndexChanged.connect(lambda *_: self._update_complexity_visibility())

        self._update_complexity_visibility()
        self._refresh_preview()

    def _make_spin(
        self,
        value: float,
        minimum: float,
        maximum: float,
        step: float,
        suffix: str = "",
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setDecimals(2 if step < 1.0 else 1)
        spin.setValue(value)
        spin.setSuffix(suffix)
        return spin

    def _update_complexity_visibility(self) -> None:
        complexity = self.complexity_combo.currentText()
        self.advanced_group.setVisible(complexity in {"Advanced", "Expert"})
        self.expert_group.setVisible(complexity == "Expert")
        self.boost_spin.setEnabled(self.aspiration_combo.currentText() == "Turbo")

    def _build_spec(self) -> WizardSpec:
        complexity = self.complexity_combo.currentText()
        advanced = complexity in {"Advanced", "Expert"}
        expert = complexity == "Expert"
        return WizardSpec(
            complexity=complexity,
            use_case=self.use_case_combo.currentText(),
            architecture=self.architecture_combo.currentText(),
            aspiration=self.aspiration_combo.currentText(),
            rpm_start=self.rpm_start_spin.value(),
            rpm_end=self.rpm_end_spin.value(),
            objective=str(self.objective_combo.currentData()),
            displacement_cc=self.displacement_spin.value() if advanced else None,
            compression_ratio=self.compression_spin.value() if advanced else None,
            runner_length_mm=self.runner_length_spin.value() if advanced else None,
            header_length_mm=self.header_length_spin.value() if advanced else None,
            runner_diameter_mm=self.runner_diameter_spin.value() if expert else None,
            header_diameter_mm=self.header_diameter_spin.value() if expert else None,
            peak_rpm=self.peak_rpm_spin.value() if expert else None,
            redline_rpm=self.redline_spin.value() if expert else None,
            thermal_efficiency=self.thermal_eff_spin.value() if expert else None,
            port_flow_efficiency=self.port_flow_eff_spin.value() if expert else None,
            intake_duration_deg=self.intake_duration_spin.value() if expert else None,
            exhaust_duration_deg=self.exhaust_duration_spin.value() if expert else None,
            intake_lift_mm=self.intake_lift_spin.value() if expert else None,
            exhaust_lift_mm=self.exhaust_lift_spin.value() if expert else None,
            lobe_separation_deg=self.lsa_spin.value() if expert else None,
            ignition_advance_deg=self.ignition_spin.value() if expert else None,
            target_boost_kpa=self.boost_spin.value()
            if expert and self.aspiration_combo.currentText() == "Turbo"
            else None,
        )

    def _refresh_preview(self) -> None:
        spec = self._build_spec()
        spec_review = review_wizard_spec(spec)
        lines = [
            "<h3>Level behavior</h3>",
            f"<p><b>{spec.complexity}</b> exposes: {', '.join(COMPLEXITY_FIELDS.get(spec.complexity, []))}</p>",
        ]
        if spec_review["errors"]:
            lines.append("<p><b>Wizard input errors</b></p><ul>")
            for issue in spec_review["errors"]:
                lines.append(f"<li>{issue}</li>")
            lines.append("</ul>")
            self.summary_browser.setHtml("".join(lines))
            self.generated_engine = None
            ok_button = self.button_box.button(QDialogButtonBox.Ok)
            if ok_button is not None:
                ok_button.setEnabled(False)
            self.export_button.setEnabled(False)
            return

        engine = build_engine_from_wizard(spec)
        preflight = engine.preflight_review(operation="dyno", mode="v1")
        summary = summarize_engine_for_wizard(engine, spec)
        lines.append("<h3>Engineering summary</h3><ul>")
        for key, value in summary.items():
            lines.append(f"<li><b>{key}:</b> {value}</li>")
        lines.append("</ul>")
        if spec_review["warnings"]:
            lines.append("<p><b>Wizard guidance</b></p><ul>")
            for issue in spec_review["warnings"]:
                lines.append(f"<li>{issue}</li>")
            lines.append("</ul>")
        if preflight["errors"]:
            lines.append("<p><b>Preflight blockers</b></p><ul>")
            for issue in preflight["errors"]:
                lines.append(f"<li>{issue}</li>")
            lines.append("</ul>")
        if preflight["warnings"]:
            lines.append("<p><b>Preflight warnings</b></p><ul>")
            for issue in preflight["warnings"]:
                lines.append(f"<li>{issue}</li>")
            lines.append("</ul>")
        if not preflight["errors"] and not preflight["warnings"]:
            lines.append("<p><b>Preflight:</b> ready to export or apply.</p>")
        self.summary_browser.setHtml("".join(lines))
        self.generated_engine = engine
        ok_button = self.button_box.button(QDialogButtonBox.Ok)
        if ok_button is not None:
            ok_button.setEnabled(not preflight["errors"])
        self.export_button.setEnabled(not preflight["errors"])

    def export_json(self) -> None:
        if self.generated_engine is None:
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Export Generated Engine", "guided_engine.json", "JSON Files (*.json)")
        if not filename:
            return
        self.generated_engine.save_to_file(filename)


class MainWindow(QMainWindow):
    """Main GUI window binding engine data, editing, and dyno plotting."""

    def __init__(self) -> None:
        super().__init__()
        self.resize(1280, 800)

        self.engine = Engine()
        self.audio_synth = AudioSynthesizer()
        self.current_project_path: Optional[str] = None
        self.real_dyno_widget: Optional[RealDynoWorkbench] = None
        self._try_load_default_preset()
        self.block_displacement_label: Optional[QLabel] = None
        self.block_piston_speed_label: Optional[QLabel] = None
        self._update_window_title()

        self.navigation_tree = QTreeWidget()
        self.navigation_tree.setHeaderHidden(True)
        self.navigation_tree.setIndentation(18)
        self.navigation_tree.setUniformRowHeights(True)
        self.navigation_tree.setStyleSheet(
            """
            QTreeWidget {
                background: #fbfcfe;
                border: none;
                padding: 8px 6px;
            }
            QTreeWidget::item {
                padding: 6px 8px;
                margin: 1px 0;
            }
            QTreeWidget::item:selected {
                background: #dce9f7;
                color: #102030;
                border-radius: 6px;
            }
            """
        )
        self.navigation_tree.currentItemChanged.connect(self.update_properties_panel)
        self.left_dock: Optional[QDockWidget] = None

        self.property_widget = QWidget()
        self.property_form = QFormLayout()
        self.property_widget.setLayout(self.property_form)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setStyleSheet(
            """
            QTabWidget::pane {
                border: 1px solid #d6dde8;
                border-radius: 10px;
                background: white;
                top: -1px;
            }
            QTabBar::tab {
                background: #eef2f7;
                border: 1px solid #d6dde8;
                border-bottom: none;
                padding: 8px 14px;
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
        self.main_stack = QStackedWidget()
        self.wave_plot = pg.PlotWidget()
        self.wave_image = pg.ImageItem()
        self.wave_rpm_spin = QDoubleSpinBox()
        self.wave_scrub_slider = QSlider(Qt.Horizontal)
        self.wave_record_btn = QPushButton("Record")
        self.wave_record_btn.setCheckable(True)
        self.wave_save_btn = QPushButton("Save Audio")
        self.wave_save_btn.setEnabled(False)
        self.wave_frame_indicator: Optional[pg.InfiniteLine] = None
        self.wave_scope = ScopeWidget()
        self.fabrication_table = QTableWidget()
        self.collector_type_combo = QComboBox()
        self.collector_inlet_label = QLabel("-")
        self.tailpipe_length_label = QLabel("-")
        self.dyno_plot = pg.PlotWidget()
        self.power_curve = None
        self.torque_curve = None
        self.invalid_power_curve = None
        self.invalid_torque_curve = None
        self.dyno_mode_combo = QComboBox()
        self.dyno_quality_combo = QComboBox()
        self.dyno_run_btn = QPushButton("Run Dyno")
        self.dyno_cancel_btn = QPushButton("Cancel")
        self.dyno_progress = QProgressBar()
        self.dyno_status_label = QLabel("")
        self.dyno_export_btn = QPushButton("Export Dyno JSON...")
        self.dyno_knock_export_checkbox = QCheckBox("Knock report (opt-in)")
        self.dyno_advanced_group = QGroupBox("Advanced Dyno Options (optional)")
        self.dyno_context_label = QLabel("")
        self.dyno_plot_caption_label = QLabel("")
        self.dyno_plot_notice_label = QLabel("")
        self.dyno_settings_sweep_value = QLabel("")
        self.dyno_settings_quality_value = QLabel("")
        self.dyno_status_value_label = QLabel("Status: Ready")
        self.dyno_result_state_label = QLabel("Last run: Not run yet")
        self.dyno_result_value_label = QLabel("Result: No result available")
        self.dyno_summary_peak_power_value = QLabel("-")
        self.dyno_summary_peak_power_rpm_value = QLabel("-")
        self.dyno_summary_peak_torque_value = QLabel("-")
        self.dyno_summary_peak_torque_rpm_value = QLabel("-")
        self.dyno_summary_sweep_value = QLabel("-")
        self.dyno_summary_detail_label = QLabel("Run a dyno sweep to populate peak values and exportable results.")
        self.analysis_context_label = QLabel("")
        self._dyno_run_state = "Idle"
        self.analysis_detail_label = QLabel("Run a dyno sweep to populate the analysis view.")
        self.analysis_peak_power_value_label = QLabel("-")
        self.analysis_peak_power_rpm_label = QLabel("-")
        self.analysis_peak_torque_value_label = QLabel("-")
        self.analysis_peak_torque_rpm_label = QLabel("-")
        self.analysis_knock_notice_label = QLabel("")
        self.last_dyno_payload: Optional[dict[str, Any]] = None
        self.dyno_thread: Optional[QThread] = None
        self.dyno_worker: Optional[DynoWorker] = None
        self.dyno_elapsed = QElapsedTimer()
        self._dyno_progress_count = 0
        self._dyno_point_count = 0
        self._dyno_mode_running: Optional[str] = None
        self._dyno_rpm_values: list[int] = []
        self._dyno_power_hp: list[float] = []
        self._dyno_torque_nm: list[float] = []
        self._dyno_plot_rpms: list[int] = []
        self._dyno_plot_power_hp: list[float] = []
        self._dyno_plot_torque_nm: list[float] = []
        self._dyno_invalid_rpms: list[int] = []
        self._dyno_invalid_power_hp: list[float] = []
        self._dyno_invalid_torque_nm: list[float] = []
        self._dyno_results: list[dict[str, float]] = []
        self._dyno_max_hp_value = -float("inf")
        self._dyno_max_hp_rpm = 0
        self._dyno_max_tq_value = -float("inf")
        self._dyno_max_tq_rpm = 0
        self._dyno_knock_detected = False
        self.pro_dyno_plot = pg.PlotWidget()
        self.pro_power_curve = None
        self.pro_torque_curve = None
        self.convergence_plot = pg.PlotWidget()
        self.optimizer_plot = pg.PlotWidget()
        self.optimizer_param_combo = QComboBox()
        self.optimizer_start_spin = QDoubleSpinBox()
        self.optimizer_end_spin = QDoubleSpinBox()
        self.optimizer_step_spin = QDoubleSpinBox()
        self.opt_rpm_spin = QDoubleSpinBox()
        self.optimizer_progress = QProgressBar()
        self.wave_solver: Optional[Engine1DSolver] = None
        self.wave_matrix: Optional[np.ndarray] = None
        self.wave_history: list[np.ndarray] = []
        self.wave_time_vector: list[float] = []
        self.wave_x_axis: Optional[np.ndarray] = None
        self.timer = QTimer(self)
        self._setup_views()

        self.toolbar = self.addToolBar("Main Toolbar")
        self._create_toolbar()
        self._create_menu()
        self._create_left_panel()
        self.main_stack.currentChanged.connect(lambda _index: self._sync_navigation_state())
        self.tabs.currentChanged.connect(lambda _index: self._sync_navigation_state())

        self.refresh_tree()
        self._show_placeholder("Select a component to edit its properties")
        self.update_overview()
        self.tabs.setCurrentIndex(0)
        self._sync_navigation_state()

    # -------------------------- UI Construction ---------------------------
    def _create_menu(self) -> None:
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")

        guided_action = QAction("New Guided Engine...", self)
        guided_action.triggered.connect(self.launch_guided_engine_wizard)
        file_menu.addAction(guided_action)

        file_menu.addSeparator()

        save_action = QAction("Save", self)
        save_action.triggered.connect(self.save_engine)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save As...", self)
        save_as_action.triggered.connect(self.save_engine_as)
        file_menu.addAction(save_as_action)

        load_action = QAction("Load", self)
        load_action.triggered.connect(self.load_project)
        file_menu.addAction(load_action)

    def _create_toolbar(self) -> None:
        save_icon = self.style().standardIcon(QStyle.SP_DialogSaveButton)
        save_action = QAction(save_icon, "Save", self)
        save_action.triggered.connect(self.save_engine)
        self.toolbar.addAction(save_action)
        self.toolbar.setMovable(False)

        self.toolbar.addSeparator()

        workspace_label = QLabel("View")
        workspace_label.setStyleSheet("color: #506072;")
        self.toolbar.addWidget(workspace_label)
        self.workspace_combo = QComboBox()
        self.workspace_combo.addItems(["Standard View", "Pro Dyno", "Wave Sim", "Fabrication"])
        self.workspace_combo.setMinimumWidth(150)
        self.workspace_combo.setToolTip("Switch the active workspace")
        self.workspace_combo.currentIndexChanged.connect(self._set_workspace_index)
        self.toolbar.addWidget(self.workspace_combo)

        self.toolbar.addSeparator()
        self.toolbar_context_label = QLabel()
        self.toolbar_context_label.setStyleSheet("color: #5f6b7a; padding-left: 2px;")
        self.toolbar.addWidget(self.toolbar_context_label)

    def _create_left_panel(self) -> None:
        self.left_dock = QDockWidget("Engine Explorer", self)
        self.left_dock.setWidget(self.navigation_tree)
        self.left_dock.setAllowedAreas(Qt.LeftDockWidgetArea)
        self.left_dock.setMinimumWidth(240)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.left_dock)
        self.resizeDocks([self.left_dock], [280], Qt.Horizontal)

    def _setup_views(self) -> None:
        overview_tab = QWidget()
        overview_layout = QVBoxLayout()
        overview_layout.setContentsMargins(18, 18, 18, 18)
        overview_layout.setSpacing(12)

        overview_header = QWidget()
        overview_header.setObjectName("overviewHeader")
        overview_header.setStyleSheet(
            """
            QWidget#overviewHeader {
                background: #f7f9fc;
                border: 1px solid #d6dde8;
                border-radius: 10px;
            }
            """
        )
        overview_header_layout = QHBoxLayout()
        overview_header_layout.setContentsMargins(14, 14, 14, 14)
        overview_header_layout.setSpacing(14)

        overview_text_layout = QVBoxLayout()
        overview_text_layout.setSpacing(4)
        self.overview_title_label = QLabel("Project")
        self.overview_title_label.setStyleSheet("font-size: 20px; font-weight: 700; color: #18212f;")
        self.overview_title_label.setWordWrap(True)
        self.overview_subtitle_label = QLabel("")
        self.overview_subtitle_label.setStyleSheet("font-size: 12px; color: #314154; font-weight: 600;")
        self.overview_subtitle_label.setWordWrap(True)
        self.overview_context_label = QLabel("")
        self.overview_context_label.setStyleSheet("font-size: 11px; color: #506072;")
        self.overview_context_label.setTextFormat(Qt.RichText)
        self.overview_context_label.setWordWrap(True)
        self.overview_status_label = QLabel("")
        self.overview_status_label.setStyleSheet("font-size: 11px; color: #506072;")
        self.overview_status_label.setTextFormat(Qt.RichText)
        self.overview_status_label.setWordWrap(True)
        self.overview_guidance_label = QLabel("")
        self.overview_guidance_label.setStyleSheet("font-size: 11px; color: #18212f; font-weight: 600;")
        self.overview_guidance_label.setWordWrap(True)
        overview_text_layout.addWidget(self.overview_title_label)
        overview_text_layout.addWidget(self.overview_subtitle_label)
        overview_text_layout.addWidget(self.overview_context_label)
        overview_text_layout.addWidget(self.overview_status_label)
        overview_text_layout.addWidget(self.overview_guidance_label)

        overview_actions_layout = QVBoxLayout()
        overview_actions_layout.setSpacing(6)
        self.overview_run_dyno_btn = QPushButton("Run Dyno")
        self.overview_run_dyno_btn.setMinimumWidth(150)
        self.overview_run_dyno_btn.setStyleSheet(
            "QPushButton { background: #1f5ea8; color: white; border: none; border-radius: 8px; padding: 9px 16px; font-weight: 700; }"
            "QPushButton:hover { background: #184b85; }"
        )
        self.overview_run_dyno_btn.clicked.connect(self._run_dyno_from_overview)
        self.overview_edit_btn = QPushButton("Edit Properties")
        self.overview_edit_btn.clicked.connect(self._open_properties_from_overview)
        self.overview_real_dyno_btn = QPushButton("Open Real Dyno")
        self.overview_real_dyno_btn.clicked.connect(self._open_real_dyno_from_overview)
        overview_actions_layout.addWidget(self.overview_run_dyno_btn)
        overview_secondary_actions = QHBoxLayout()
        overview_secondary_actions.setSpacing(6)
        overview_secondary_actions.addWidget(self.overview_edit_btn)
        overview_secondary_actions.addWidget(self.overview_real_dyno_btn)
        overview_actions_layout.addLayout(overview_secondary_actions)
        overview_actions_layout.addStretch()

        overview_header_layout.addLayout(overview_text_layout, 1)
        overview_header_layout.addLayout(overview_actions_layout)
        overview_header.setLayout(overview_header_layout)
        overview_layout.addWidget(overview_header)

        self.overview_browser = QTextBrowser()
        self.overview_browser.setOpenExternalLinks(False)
        self.overview_browser.setReadOnly(True)
        self.overview_browser.setStyleSheet(
            """
            QTextBrowser {
                background: white;
                border: 1px solid #d6dde8;
                border-radius: 12px;
                padding: 8px;
            }
            """
        )
        overview_layout.addWidget(self.overview_browser)
        overview_tab.setLayout(overview_layout)

        self.properties_tab = QWidget()
        properties_layout = QVBoxLayout()
        properties_layout.addWidget(self.property_widget)
        properties_layout.addStretch()
        self.properties_tab.setLayout(properties_layout)

        dyno_tab = QWidget()
        dyno_layout = QVBoxLayout()
        dyno_layout.setContentsMargins(18, 18, 18, 18)
        dyno_layout.setSpacing(10)
        self.dyno_run_btn.clicked.connect(self.run_dyno_sweep)
        self.dyno_cancel_btn.clicked.connect(self.cancel_dyno_sweep)
        self.dyno_cancel_btn.setEnabled(False)
        self.dyno_cancel_btn.setVisible(False)
        self.dyno_run_btn.setMinimumWidth(150)
        self.dyno_run_btn.setStyleSheet(
            "QPushButton { background: #1f5ea8; color: white; border: none; border-radius: 8px; padding: 9px 16px; font-weight: 700; }"
            "QPushButton:hover { background: #184b85; }"
            "QPushButton:disabled { background: #a7bbd4; color: #eef3f9; }"
        )
        self.dyno_cancel_btn.setMinimumWidth(96)
        self.dyno_cancel_btn.setStyleSheet(
            "QPushButton { background: #eef2f7; color: #415164; border: 1px solid #d6dde8; border-radius: 8px; padding: 9px 14px; font-weight: 600; }"
            "QPushButton:hover { background: #e4ebf4; }"
            "QPushButton:disabled { color: #8d99a8; background: #f6f8fb; border-color: #e0e7f0; }"
        )
        self.dyno_progress.setRange(0, 100)
        self.dyno_progress.setMinimumWidth(220)
        self.dyno_progress.setFixedHeight(12)
        self.dyno_progress.setTextVisible(True)
        self.dyno_progress.setFormat("%p%")
        self.dyno_progress.setStyleSheet(
            "QProgressBar {"
            " background: #edf2f8;"
            " border: 1px solid #d6dde8;"
            " border-radius: 6px;"
            " color: #17385d;"
            " font-size: 9px;"
            " font-weight: 700;"
            " text-align: center;"
            "}"
            "QProgressBar::chunk {"
            " background: #2d6eb5;"
            " border-radius: 5px;"
            "}"
        )
        self.dyno_progress.setVisible(False)
        self.dyno_mode_combo.addItem("v1 (Quick 0D)", "v1")
        self.dyno_mode_combo.addItem("v2 (Pro Coupled)", "v2")
        self.dyno_quality_combo.addItem("Fast", "fast")
        self.dyno_quality_combo.addItem("Stable", "stable")
        self.dyno_export_btn.clicked.connect(self.export_dyno_json)
        self.dyno_status_label.setWordWrap(False)
        self.dyno_status_label.setMinimumWidth(360)
        self.dyno_status_label.setStyleSheet("color: #314154; font-size: 11px; font-weight: 600;")
        self.dyno_mode_note_label = QLabel(
            "Cross-mode note: `ve_actual` is a modeled estimate in v1 and a trapped-mass result in v2. "
            "Use it for trend/plausibility checks rather than strict parity."
        )
        self.dyno_mode_note_label.setWordWrap(True)
        self.dyno_mode_note_label.setStyleSheet(
            "color: #506072; font-size: 10px; background: #f6f8fb; border: 1px solid #d6dde8; border-radius: 7px; padding: 4px 8px;"
        )

        section_kicker_style = "font-size: 10px; font-weight: 700; color: #5b6b7c;"
        section_divider_style = "background: #d6dde8; border-radius: 1px;"

        self.dyno_top_panel = QWidget()
        self.dyno_top_panel.setObjectName("quickDynoTopBand")
        self.dyno_top_panel.setStyleSheet(
            """
            QWidget#quickDynoTopBand {
                background: #f8fafc;
                border: 1px solid #d6dde8;
                border-radius: 10px;
            }
            """
        )
        dyno_top_panel_layout = QVBoxLayout()
        dyno_top_panel_layout.setContentsMargins(12, 10, 12, 10)
        dyno_top_panel_layout.setSpacing(8)

        dyno_context_row = QHBoxLayout()
        dyno_context_row.setSpacing(8)
        dyno_context_title = QLabel("Run Context")
        dyno_context_title.setStyleSheet(section_kicker_style)
        self.dyno_context_label.setTextFormat(Qt.RichText)
        self.dyno_context_label.setWordWrap(True)
        self.dyno_context_label.setStyleSheet("font-size: 10px; color: #314154;")
        dyno_context_row.addWidget(dyno_context_title)
        dyno_context_row.addWidget(self.dyno_context_label, 1)
        dyno_top_panel_layout.addLayout(dyno_context_row)

        dyno_context_controls_divider = QWidget()
        dyno_context_controls_divider.setFixedHeight(1)
        dyno_context_controls_divider.setStyleSheet(section_divider_style)
        dyno_top_panel_layout.addWidget(dyno_context_controls_divider)

        dyno_controls_summary_row = QHBoxLayout()
        dyno_controls_summary_row.setSpacing(10)

        dyno_controls_panel = QWidget()
        dyno_controls_layout = QVBoxLayout()
        dyno_controls_layout.setContentsMargins(0, 0, 0, 0)
        dyno_controls_layout.setSpacing(6)

        dyno_controls_header = QLabel("Run Controls")
        dyno_controls_header.setStyleSheet(section_kicker_style)

        dyno_mode_row = QHBoxLayout()
        dyno_mode_row.setSpacing(6)
        dyno_mode_label = QLabel("Mode")
        dyno_mode_label.setStyleSheet("font-size: 10px; color: #6b7888;")
        dyno_mode_row.addWidget(dyno_mode_label)
        dyno_mode_row.addWidget(self.dyno_mode_combo)
        dyno_mode_row.addStretch(1)

        dyno_controls_meta_row = QHBoxLayout()
        dyno_controls_meta_row.setSpacing(4)
        dyno_settings_quality_title = QLabel("Quality")
        dyno_settings_quality_title.setStyleSheet("font-size: 10px; color: #6b7888;")
        self.dyno_settings_quality_value.setStyleSheet("font-size: 10px; font-weight: 700; color: #18212f;")
        dyno_settings_sweep_title = QLabel("Sweep")
        dyno_settings_sweep_title.setStyleSheet("font-size: 10px; color: #6b7888;")
        self.dyno_settings_sweep_value.setStyleSheet("font-size: 10px; font-weight: 700; color: #18212f;")
        dyno_controls_sep = QLabel("|")
        dyno_controls_sep.setStyleSheet("font-size: 10px; color: #90a0b3;")
        dyno_controls_meta_row.addWidget(dyno_settings_quality_title)
        dyno_controls_meta_row.addWidget(self.dyno_settings_quality_value)
        dyno_controls_meta_row.addWidget(dyno_controls_sep)
        dyno_controls_meta_row.addWidget(dyno_settings_sweep_title)
        dyno_controls_meta_row.addWidget(self.dyno_settings_sweep_value)
        dyno_controls_meta_row.addStretch(1)

        dyno_actions_row = QHBoxLayout()
        dyno_actions_row.setSpacing(6)
        dyno_action_buttons = QHBoxLayout()
        dyno_action_buttons.setSpacing(6)
        dyno_action_buttons.addWidget(self.dyno_run_btn)
        dyno_action_buttons.addWidget(self.dyno_cancel_btn)
        dyno_action_status = QVBoxLayout()
        dyno_action_status.setSpacing(2)
        dyno_action_status.addWidget(self.dyno_progress)
        dyno_action_status.addWidget(self.dyno_status_label)
        dyno_actions_row.addLayout(dyno_action_buttons)
        dyno_actions_row.addLayout(dyno_action_status)
        dyno_actions_row.addStretch(1)

        dyno_controls_layout.addWidget(dyno_controls_header)
        dyno_controls_layout.addLayout(dyno_mode_row)
        dyno_controls_layout.addLayout(dyno_controls_meta_row)
        dyno_controls_layout.addLayout(dyno_actions_row)
        dyno_controls_panel.setLayout(dyno_controls_layout)
        dyno_controls_summary_row.addWidget(dyno_controls_panel, 3)

        dyno_controls_summary_divider = QWidget()
        dyno_controls_summary_divider.setFixedWidth(1)
        dyno_controls_summary_divider.setStyleSheet(section_divider_style)
        dyno_controls_summary_row.addWidget(dyno_controls_summary_divider)

        dyno_summary_panel = QWidget()
        dyno_summary_layout = QVBoxLayout()
        dyno_summary_layout.setContentsMargins(0, 0, 0, 0)
        dyno_summary_layout.setSpacing(4)
        dyno_summary_header = QLabel("Result Summary")
        dyno_summary_header.setStyleSheet(section_kicker_style)
        for label in (
            self.dyno_status_value_label,
            self.dyno_result_state_label,
            self.dyno_result_value_label,
        ):
            label.setWordWrap(False)
            label.setStyleSheet("font-size: 10px; font-weight: 700; color: #18212f;")
        self.dyno_summary_detail_label.setWordWrap(False)
        self.dyno_summary_detail_label.setStyleSheet("font-size: 10px; color: #506072;")

        self.dyno_summary_peak_power_value.setStyleSheet("font-size: 11px; font-weight: 700; color: #18212f;")
        self.dyno_summary_peak_power_value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.dyno_summary_peak_torque_value.setStyleSheet("font-size: 11px; font-weight: 700; color: #18212f;")
        self.dyno_summary_peak_torque_value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        dyno_summary_status_row = QHBoxLayout()
        dyno_summary_status_row.setSpacing(8)
        dyno_summary_status_row.addWidget(self.dyno_status_value_label)
        dyno_summary_status_row.addWidget(self.dyno_result_state_label)
        dyno_summary_status_row.addWidget(self.dyno_result_value_label, 1)
        dyno_summary_metrics_row = QHBoxLayout()
        dyno_summary_metrics_row.setSpacing(10)
        dyno_summary_power_title = QLabel("Peak power")
        dyno_summary_power_title.setStyleSheet("font-size: 10px; color: #6b7888;")
        dyno_summary_torque_title = QLabel("Peak torque")
        dyno_summary_torque_title.setStyleSheet("font-size: 10px; color: #6b7888;")
        dyno_summary_metrics_row.addWidget(dyno_summary_power_title)
        dyno_summary_metrics_row.addWidget(self.dyno_summary_peak_power_value)
        dyno_summary_metrics_row.addWidget(dyno_summary_torque_title)
        dyno_summary_metrics_row.addWidget(self.dyno_summary_peak_torque_value, 1)
        dyno_summary_layout.addWidget(dyno_summary_header)
        dyno_summary_layout.addLayout(dyno_summary_status_row)
        dyno_summary_layout.addLayout(dyno_summary_metrics_row)
        dyno_summary_layout.addWidget(self.dyno_summary_detail_label)
        dyno_summary_panel.setLayout(dyno_summary_layout)
        dyno_controls_summary_row.addWidget(dyno_summary_panel, 2)

        dyno_top_panel_layout.addLayout(dyno_controls_summary_row)
        self.dyno_top_panel.setLayout(dyno_top_panel_layout)
        dyno_layout.addWidget(self.dyno_top_panel)

        self.dyno_advanced_group.setCheckable(True)
        self.dyno_advanced_group.setChecked(False)
        self.dyno_advanced_group.setStyleSheet(
            """
            QGroupBox {
                color: #5f6b7a;
                font-size: 11px;
                font-weight: 600;
                border: 1px solid #d6dde8;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 6px;
                background: #fbfcfe;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            """
        )
        self.dyno_advanced_group.toggled.connect(self._set_dyno_advanced_visible)
        dyno_advanced_layout = QFormLayout()
        dyno_advanced_layout.setSpacing(8)
        dyno_advanced_layout.addRow("Quality", self.dyno_quality_combo)
        dyno_export_row = QWidget()
        dyno_export_layout = QHBoxLayout()
        dyno_export_layout.setContentsMargins(0, 0, 0, 0)
        dyno_export_layout.setSpacing(8)
        dyno_export_layout.addWidget(self.dyno_export_btn)
        dyno_export_layout.addWidget(self.dyno_knock_export_checkbox)
        dyno_export_layout.addStretch()
        dyno_export_row.setLayout(dyno_export_layout)
        dyno_advanced_layout.addRow("Export", dyno_export_row)
        self.dyno_advanced_group.setLayout(dyno_advanced_layout)
        dyno_layout.addWidget(self.dyno_advanced_group)
        self._set_dyno_advanced_visible(False)

        self.dyno_mode_combo.currentIndexChanged.connect(lambda _index: self._refresh_quick_dyno_panel())
        self.dyno_quality_combo.currentIndexChanged.connect(lambda _index: self._refresh_quick_dyno_panel())

        dyno_plot_meta_panel = QWidget()
        dyno_plot_meta_layout = QVBoxLayout()
        dyno_plot_meta_layout.setContentsMargins(0, 0, 0, 0)
        dyno_plot_meta_layout.setSpacing(4)
        dyno_plot_meta_top_row = QHBoxLayout()
        dyno_plot_meta_top_row.setContentsMargins(0, 0, 0, 0)
        dyno_plot_meta_top_row.setSpacing(8)
        self.dyno_plot_notice_label.setVisible(False)
        self.dyno_plot_notice_label.setWordWrap(False)
        self.dyno_plot_notice_label.setStyleSheet(
            "font-size: 10px; font-weight: 700; color: #a53b2f; background: #fff2ef; border: 1px solid #f1c5bd; border-radius: 7px; padding: 3px 8px;"
        )
        dyno_plot_meta_top_row.addWidget(self.dyno_plot_notice_label)
        dyno_plot_meta_top_row.addWidget(self.dyno_mode_note_label, 1)
        self.dyno_plot_caption_label.setWordWrap(False)
        self.dyno_plot_caption_label.setStyleSheet("font-size: 10px; color: #5f6b7a;")
        dyno_plot_meta_layout.addLayout(dyno_plot_meta_top_row)
        dyno_plot_meta_layout.addWidget(self.dyno_plot_caption_label)
        dyno_plot_meta_panel.setLayout(dyno_plot_meta_layout)

        self.dyno_plot.showGrid(x=True, y=True, alpha=0.15)
        self.dyno_plot.addLegend()
        self.dyno_plot.setLabel("bottom", "RPM")
        self.dyno_plot.setLabel("left", "Output")
        self.dyno_plot.setMinimumHeight(360)
        dyno_layout.addWidget(dyno_plot_meta_panel)
        dyno_layout.addWidget(self.dyno_plot, 1)
        dyno_tab.setLayout(dyno_layout)
        self.quick_dyno_tab = dyno_tab

        analysis_tab = QWidget()
        analysis_layout = QVBoxLayout()
        analysis_layout.setContentsMargins(16, 16, 16, 14)
        analysis_layout.setSpacing(8)

        analysis_top_panel = QWidget()
        analysis_top_panel.setObjectName("analysisTopPanel")
        analysis_top_panel.setStyleSheet(
            """
            QWidget#analysisTopPanel {
                background: #f8fafc;
                border: 1px solid #d6dde8;
                border-radius: 10px;
            }
            """
        )
        analysis_top_layout = QVBoxLayout()
        analysis_top_layout.setContentsMargins(12, 7, 12, 7)
        analysis_top_layout.setSpacing(5)

        analysis_context_title = QLabel("Analysis Context")
        analysis_context_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #5b6b7c;")
        self.analysis_context_label.setTextFormat(Qt.RichText)
        self.analysis_context_label.setWordWrap(True)
        self.analysis_context_label.setStyleSheet("font-size: 10px; color: #314154;")
        analysis_top_layout.addWidget(analysis_context_title)
        analysis_top_layout.addWidget(self.analysis_context_label)

        analysis_summary_panel = QWidget()
        analysis_summary_layout = QVBoxLayout()
        analysis_summary_layout.setContentsMargins(0, 0, 0, 0)
        analysis_summary_layout.setSpacing(4)

        self.analysis_summary_label = QLabel("No dyno data yet")
        self.analysis_summary_label.setTextFormat(Qt.RichText)
        self.analysis_summary_label.setWordWrap(True)
        self.analysis_summary_label.setStyleSheet(
            "font-size: 10px; color: #314154; background: #eef3f8; border: 1px solid #d6dde8; border-radius: 7px; padding: 3px 7px;"
        )
        analysis_summary_layout.addWidget(self.analysis_summary_label)

        analysis_peak_row = QHBoxLayout()
        analysis_peak_row.setSpacing(0)

        analysis_peak_power_panel = QWidget()
        analysis_peak_power_layout = QVBoxLayout()
        analysis_peak_power_layout.setContentsMargins(0, 0, 10, 0)
        analysis_peak_power_layout.setSpacing(1)
        analysis_peak_power_title = QLabel("Peak power")
        analysis_peak_power_title.setStyleSheet("font-size: 9px; color: #6b7888;")
        self.analysis_peak_power_value_label.setStyleSheet("font-size: 15px; font-weight: 700; color: #18212f;")
        self.analysis_peak_power_rpm_label.setStyleSheet("font-size: 10px; color: #506072;")
        analysis_peak_power_layout.addWidget(analysis_peak_power_title)
        analysis_peak_power_layout.addWidget(self.analysis_peak_power_value_label)
        analysis_peak_power_layout.addWidget(self.analysis_peak_power_rpm_label)
        analysis_peak_power_panel.setLayout(analysis_peak_power_layout)
        analysis_peak_row.addWidget(analysis_peak_power_panel)

        analysis_peak_divider = QWidget()
        analysis_peak_divider.setFixedWidth(1)
        analysis_peak_divider.setStyleSheet("background: #d6dde8;")
        analysis_peak_row.addWidget(analysis_peak_divider)

        analysis_peak_torque_panel = QWidget()
        analysis_peak_torque_layout = QVBoxLayout()
        analysis_peak_torque_layout.setContentsMargins(10, 0, 0, 0)
        analysis_peak_torque_layout.setSpacing(1)
        analysis_peak_torque_title = QLabel("Peak torque")
        analysis_peak_torque_title.setStyleSheet("font-size: 9px; color: #6b7888;")
        self.analysis_peak_torque_value_label.setStyleSheet("font-size: 15px; font-weight: 700; color: #18212f;")
        self.analysis_peak_torque_rpm_label.setStyleSheet("font-size: 10px; color: #506072;")
        analysis_peak_torque_layout.addWidget(analysis_peak_torque_title)
        analysis_peak_torque_layout.addWidget(self.analysis_peak_torque_value_label)
        analysis_peak_torque_layout.addWidget(self.analysis_peak_torque_rpm_label)
        analysis_peak_torque_panel.setLayout(analysis_peak_torque_layout)
        analysis_peak_row.addWidget(analysis_peak_torque_panel)

        analysis_summary_layout.addLayout(analysis_peak_row)
        self.analysis_detail_label.setWordWrap(True)
        self.analysis_detail_label.setStyleSheet("font-size: 10px; color: #506072;")
        analysis_summary_layout.addWidget(self.analysis_detail_label)
        analysis_summary_panel.setLayout(analysis_summary_layout)
        analysis_top_layout.addWidget(analysis_summary_panel)
        analysis_top_panel.setLayout(analysis_top_layout)
        analysis_layout.addWidget(analysis_top_panel)

        self.analysis_knock_notice_label.setWordWrap(True)
        self.analysis_knock_notice_label.setVisible(False)
        self.analysis_knock_notice_label.setStyleSheet(
            "font-size: 10px; font-weight: 700; color: #a53b2f; background: #fff2ef; border: 1px solid #f1c5bd; border-radius: 7px; padding: 4px 8px;"
        )
        analysis_layout.addWidget(self.analysis_knock_notice_label)

        analysis_table_title = QLabel("Detailed Sweep Metrics")
        analysis_table_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #5b6b7c;")
        analysis_layout.addWidget(analysis_table_title)

        self.analysis_table = QTableWidget()
        self.analysis_table.setColumnCount(10)
        self.analysis_table.setHorizontalHeaderLabels(
            [
                "RPM",
                "Torque (Nm)",
                "Power (HP)",
                "BMEP (bar)",
                "VE (%)",
                "Piston Spd (m/s)",
                "Mach Z",
                "Friction (HP)",
                "Airflow (CFM)",
                "Knock?",
            ]
        )
        self.analysis_table.setAlternatingRowColors(True)
        self.analysis_table.setShowGrid(False)
        self.analysis_table.verticalHeader().setVisible(False)
        self.analysis_table.setStyleSheet(
            """
            QTableWidget {
                background: #ffffff;
                alternate-background-color: #f8fafc;
                border: 1px solid #d6dde8;
                border-radius: 10px;
                color: #243243;
                gridline-color: #e5ebf2;
                padding-top: 0px;
            }
            QHeaderView::section {
                background: #eef3f8;
                color: #506072;
                border: none;
                border-bottom: 1px solid #d6dde8;
                padding: 7px 8px;
                font-size: 10px;
                font-weight: 600;
            }
            """
        )
        analysis_header = self.analysis_table.horizontalHeader()
        analysis_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        analysis_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        analysis_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        analysis_header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        analysis_header.setSectionResizeMode(9, QHeaderView.ResizeToContents)
        for idx, width in ((3, 96), (5, 116), (6, 86), (7, 98), (8, 108)):
            self.analysis_table.setColumnWidth(idx, width)
        for idx in range(self.analysis_table.columnCount()):
            header_item = self.analysis_table.horizontalHeaderItem(idx)
            if header_item is None:
                continue
            header_font = header_item.font()
            header_font.setBold(idx in {0, 1, 2, 4})
            header_item.setFont(header_font)
            if idx in {0, 1, 2, 4}:
                header_item.setForeground(QBrush(QColor("#18212f")))
        analysis_layout.addWidget(self.analysis_table, 1)
        analysis_tab.setLayout(analysis_layout)

        optimizer_tab = QWidget()
        optimizer_layout = QVBoxLayout()

        target_layout = QFormLayout()
        optimizer_params = list(self._parameter_mapping().keys())
        self.optimizer_param_combo.addItems(optimizer_params)
        target_layout.addRow("Target Parameter", self.optimizer_param_combo)

        self.optimizer_start_spin.setRange(0.0, 10000.0)
        self.optimizer_start_spin.setDecimals(3)
        self.optimizer_start_spin.setSingleStep(1.0)
        self.optimizer_start_spin.setValue(100.0)
        target_layout.addRow("Start", self.optimizer_start_spin)

        self.optimizer_end_spin.setRange(0.0, 10000.0)
        self.optimizer_end_spin.setDecimals(3)
        self.optimizer_end_spin.setSingleStep(1.0)
        self.optimizer_end_spin.setValue(400.0)
        target_layout.addRow("End", self.optimizer_end_spin)

        self.optimizer_step_spin.setRange(0.001, 1000.0)
        self.optimizer_step_spin.setDecimals(3)
        self.optimizer_step_spin.setSingleStep(1.0)
        self.optimizer_step_spin.setValue(25.0)
        target_layout.addRow("Step", self.optimizer_step_spin)

        self.opt_rpm_spin.setRange(1000.0, 20000.0)
        self.opt_rpm_spin.setDecimals(0)
        self.opt_rpm_spin.setSingleStep(100.0)
        self.opt_rpm_spin.setValue(6000.0)
        target_layout.addRow("Target RPM", self.opt_rpm_spin)

        optimizer_layout.addLayout(target_layout)

        sweep_button = QPushButton("Run Optimization Sweep")
        sweep_button.clicked.connect(self.run_optimization_sweep)
        optimizer_layout.addWidget(sweep_button)

        self.optimizer_progress.setRange(0, 100)
        self.optimizer_progress.setValue(0)
        optimizer_layout.addWidget(self.optimizer_progress)

        self.optimizer_plot.showGrid(x=True, y=True, alpha=0.2)
        self.optimizer_plot.setLabel("bottom", "Parameter Value")
        self.optimizer_plot.setLabel("left", "Peak HP")
        optimizer_layout.addWidget(self.optimizer_plot)
        optimizer_tab.setLayout(optimizer_layout)

        self.tabs.addTab(overview_tab, "Overview")
        self.tabs.addTab(self.properties_tab, "Properties")
        self.tabs.addTab(dyno_tab, "Quick Dyno")
        self.tabs.addTab(analysis_tab, "Analysis")
        self.real_dyno_widget = RealDynoWorkbench(
            engine_provider=lambda: self.engine,
            engine_path_provider=lambda: self.current_project_path,
            status_message=self.statusBar().showMessage,
            parent=self,
        )
        self.tabs.addTab(self.real_dyno_widget, "Real Dyno")
        self.tabs.addTab(optimizer_tab, "Optimizer")

        standard_container = QWidget()
        standard_layout = QVBoxLayout()
        standard_layout.setContentsMargins(0, 0, 0, 0)
        standard_layout.addWidget(self.tabs)
        standard_container.setLayout(standard_layout)

        pro_dyno_tab = QWidget()
        pro_dyno_layout = QVBoxLayout()
        pro_run_button = QPushButton("Run Pro Dyno")
        pro_run_button.clicked.connect(self.run_pro_dyno_sweep)
        pro_dyno_layout.addWidget(pro_run_button)

        self.pro_dyno_plot.showGrid(x=True, y=True, alpha=0.2)
        self.pro_dyno_plot.addLegend()
        self.pro_dyno_plot.setLabel("bottom", "RPM")
        self.pro_dyno_plot.setLabel("left", "Output")
        pro_dyno_layout.addWidget(self.pro_dyno_plot)
        self.convergence_plot.showGrid(x=True, y=True, alpha=0.2)
        self.convergence_plot.addLegend()
        self.convergence_plot.setLabel("bottom", "Iteration")
        self.convergence_plot.setLabel("left", "Relative Error")
        pro_dyno_layout.addWidget(self.convergence_plot)
        pro_dyno_tab.setLayout(pro_dyno_layout)

        fabrication_tab = QWidget()
        fabrication_layout = QVBoxLayout()
        self.fabrication_table.setColumnCount(5)
        self.fabrication_table.setHorizontalHeaderLabels(
            ["Cylinder #", "Target Length (mm)", "Actual Length (mm)", "Diameter (mm)", "Bend Angle Est."]
        )
        self.fabrication_table.itemChanged.connect(self._on_fabrication_cell_changed)
        fabrication_layout.addWidget(self.fabrication_table)

        collector_layout = QFormLayout()
        self.collector_type_combo.addItems(["4-into-1", "4-2-1", "6-into-1", "Custom"])
        self.collector_type_combo.currentTextChanged.connect(lambda _text: self.update_fabrication_data())
        collector_layout.addRow("Collector Type", self.collector_type_combo)
        collector_layout.addRow("Collector Inlet Diameter", self.collector_inlet_label)
        collector_layout.addRow("Tailpipe Length", self.tailpipe_length_label)
        fabrication_layout.addLayout(collector_layout)

        report_btn = QPushButton("Generate Fabrication Report")
        report_btn.clicked.connect(self._generate_fabrication_report)
        fabrication_layout.addWidget(report_btn)
        fabrication_tab.setLayout(fabrication_layout)

        self.main_stack.addWidget(standard_container)
        self.main_stack.addWidget(pro_dyno_tab)
        self.main_stack.addWidget(self._init_wave_scope_ui())
        self.main_stack.addWidget(fabrication_tab)
        self.setCentralWidget(self.main_stack)
        self.main_stack.setCurrentIndex(0)
        self._refresh_quick_dyno_panel()

    def _set_dyno_advanced_visible(self, visible: bool) -> None:
        self.dyno_advanced_group.setFlat(not visible)
        for idx in range(self.dyno_advanced_group.layout().count()):
            item = self.dyno_advanced_group.layout().itemAt(idx)
            widget = item.widget()
            if widget is not None:
                widget.setVisible(visible)

    def _workspace_name(self, index: int) -> str:
        workspaces = ["Standard View", "Pro Dyno", "Wave Sim", "Fabrication"]
        if 0 <= index < len(workspaces):
            return workspaces[index]
        return workspaces[0]

    def _current_mode_summary(self) -> str:
        workspace = self._workspace_name(self.main_stack.currentIndex())
        if self.main_stack.currentIndex() == 0 and self.tabs.count():
            tab_index = self.tabs.currentIndex()
            if tab_index >= 0:
                return f"{workspace} / {self.tabs.tabText(tab_index)}"
        return workspace

    def _set_workspace_index(self, index: int) -> None:
        self.main_stack.setCurrentIndex(index)
        if index == 0 and self.tabs.currentIndex() < 0 and self.tabs.count():
            self.tabs.setCurrentIndex(0)
        self._sync_navigation_state()

    def _open_standard_tab(self, tab_index: int) -> None:
        self.main_stack.setCurrentIndex(0)
        if 0 <= tab_index < self.tabs.count():
            self.tabs.setCurrentIndex(tab_index)
        self._sync_navigation_state()

    def _open_properties_from_overview(self) -> None:
        self._open_standard_tab(self.tabs.indexOf(self.properties_tab))
        current_item = self.navigation_tree.currentItem()
        if current_item is not None:
            self.update_properties_panel(current_item)

    def _open_real_dyno_from_overview(self) -> None:
        if self.real_dyno_widget is not None:
            self._open_standard_tab(self.tabs.indexOf(self.real_dyno_widget))

    def _run_dyno_from_overview(self) -> None:
        self._open_standard_tab(self.tabs.indexOf(self.quick_dyno_tab))
        QTimer.singleShot(0, self.run_dyno_sweep)

    def _sync_navigation_state(self) -> None:
        current_mode = self._current_mode_summary()
        if hasattr(self, "workspace_combo"):
            self.workspace_combo.blockSignals(True)
            self.workspace_combo.setCurrentIndex(self.main_stack.currentIndex())
            self.workspace_combo.blockSignals(False)
        if hasattr(self, "toolbar_context_label"):
            self.toolbar_context_label.setText(f"Mode: {current_mode}")
        if self.main_stack.currentIndex() == 0 and self.tabs.currentIndex() == 0:
            self.update_overview()

    def _init_wave_scope_ui(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout()

        controls = QHBoxLayout()
        rpm_label = QLabel("Simulation RPM")
        self.wave_rpm_spin.setRange(1000.0, 25000.0)
        self.wave_rpm_spin.setDecimals(0)
        self.wave_rpm_spin.setSingleStep(100.0)
        self.wave_rpm_spin.setValue(max(self.engine.camshaft.peak_rpm, 1000.0))

        calc_btn = QPushButton("Calculate Waves")
        calc_btn.clicked.connect(self.run_wave_calculation)
        self.wave_save_btn.clicked.connect(self.save_wave_audio)

        self.wave_scrub_slider.setRange(0, 0)
        self.wave_scrub_slider.setEnabled(False)
        self.wave_scrub_slider.valueChanged.connect(self.update_wave_plot)

        controls.addWidget(rpm_label)
        controls.addWidget(self.wave_rpm_spin)
        controls.addWidget(calc_btn)
        controls.addWidget(QLabel("Crank Angle Scrub"))
        controls.addWidget(self.wave_scrub_slider)
        controls.addWidget(self.wave_record_btn)
        controls.addWidget(self.wave_save_btn)
        controls.addStretch()

        layout.addLayout(controls)

        # Heatmap-style wave visualization with frame indicator
        self.wave_plot = pg.PlotWidget(background="k")
        self.wave_plot.addItem(self.wave_image)
        self.wave_frame_indicator = pg.InfiniteLine(
            angle=0,
            pos=0.0,
            pen=pg.mkPen(color=QColor(255, 255, 0), width=2, style=Qt.DashLine),
            movable=False,
        )
        self.wave_plot.addItem(self.wave_frame_indicator)
        pos = np.array([0.0, 0.5, 1.0])
        color = np.array(
            [[0, 0, 255, 255], [0, 0, 0, 255], [255, 255, 0, 255]], dtype=np.ubyte
        )
        cmap = pg.ColorMap(pos, color)
        self.wave_image.setLookupTable(cmap.getLookupTable(0.0, 1.0, 256))
        self.wave_plot.setLabel("bottom", "Pipe Length (m)")
        self.wave_plot.setLabel("left", "Crank Angle (deg)")

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.wave_plot)
        splitter.addWidget(self.wave_scope)
        splitter.setSizes([300, 200])

        layout.addWidget(splitter)
        container.setLayout(layout)
        return container

    # -------------------------- Tree Handling -----------------------------
    def refresh_tree(self) -> None:
        self.wave_solver = None
        self.navigation_tree.clear()

        root_item = QTreeWidgetItem(["Engine"])
        root_item.setData(0, Qt.UserRole, self.engine)
        self.navigation_tree.addTopLevelItem(root_item)

        block_item = QTreeWidgetItem(["Block"])
        block_item.setData(0, Qt.UserRole, self.engine.block)
        root_item.addChild(block_item)

        settings_item = QTreeWidgetItem(["Simulation Settings"])
        settings_item.setData(0, Qt.UserRole, self.engine.simulation_settings)
        root_item.addChild(settings_item)

        head_item = QTreeWidgetItem(["Cylinder Head"])
        head_item.setData(0, Qt.UserRole, self.engine.head)
        root_item.addChild(head_item)

        cam_item = QTreeWidgetItem(["Camshaft"])
        cam_item.setData(0, Qt.UserRole, self.engine.camshaft)
        root_item.addChild(cam_item)

        intake_item = QTreeWidgetItem(["Intake System"])
        intake_item.setData(0, Qt.UserRole, self.engine.intake)
        root_item.addChild(intake_item)

        exhaust_item = QTreeWidgetItem(["Exhaust System"])
        exhaust_item.setData(0, Qt.UserRole, self.engine.exhaust)
        root_item.addChild(exhaust_item)

        induction_item = QTreeWidgetItem([self.engine.induction_tree_label()])
        induction_item.setData(0, Qt.UserRole, self.engine.turbo)
        root_item.addChild(induction_item)
        self.induction_tree_item = induction_item

        fuel_item = QTreeWidgetItem(["Fuel"])
        fuel_item.setData(0, Qt.UserRole, self.engine.fuel)
        root_item.addChild(fuel_item)

        combustion_item = QTreeWidgetItem(["Combustion"])
        combustion_item.setData(0, Qt.UserRole, self.engine.combustion)
        root_item.addChild(combustion_item)

        friction_item = QTreeWidgetItem(["Mechanical Losses"])
        friction_item.setData(0, Qt.UserRole, self.engine.friction)
        root_item.addChild(friction_item)

        self.navigation_tree.expandAll()
        self.navigation_tree.setCurrentItem(block_item)
        self.update_fabrication_data()
        if self.wave_rpm_spin is not None:
            try:
                self.wave_rpm_spin.setValue(max(self.engine.camshaft.peak_rpm, 1000.0))
            except Exception:
                pass

    # -------------------------- Properties Panel --------------------------
    def _clear_property_form(self) -> None:
        while self.property_form.rowCount():
            self.property_form.removeRow(0)
        self.block_displacement_label = None
        self.block_piston_speed_label = None

    def _show_placeholder(self, message: str) -> None:
        self._clear_property_form()
        label = QLabel(message)
        label.setWordWrap(True)
        self.property_form.addRow(label)

    def update_properties_panel(
        self, current: Optional[QTreeWidgetItem], previous: Optional[QTreeWidgetItem] = None
    ) -> None:
        if current is None:
            self._show_placeholder("Select a component to edit its properties")
            return

        self.main_stack.setCurrentIndex(0)
        self.tabs.setCurrentWidget(self.properties_tab)

        component = current.data(0, Qt.UserRole)
        if isinstance(component, Block):
            self._build_block_form(component)
        elif isinstance(component, CylinderHead):
            self._build_head_form(component)
        elif isinstance(component, Camshaft):
            self._build_cam_form(component)
        elif isinstance(component, IntakeSystem):
            self._build_intake_form(component)
        elif isinstance(component, ExhaustSystem):
            self._build_exhaust_form(component)
        elif isinstance(component, Turbo):
            self._build_induction_form()
        elif isinstance(component, Supercharger):
            self._build_induction_form()
        elif isinstance(component, Fuel):
            self._build_fuel_form(component)
        elif isinstance(component, SimulationSettings):
            self._build_sim_settings_form(component)
        elif isinstance(component, Combustion):
            self._build_combustion_form(component)
        elif isinstance(component, Friction):
            self._build_friction_form(component)
        else:
            self._show_placeholder("No editable properties for this selection")

    def _build_block_form(self, block: Block) -> None:
        self._clear_property_form()
        self.block_displacement_label = QLabel(f"{block.displacement_cc:.1f}")
        displacement_row = self._label_value("Displacement (cc)", self.block_displacement_label)
        self.property_form.addRow(displacement_row)
        mean_piston_speed = 2.0 * (block.stroke * 1e-3) * block.redline_rpm / 60.0
        self.block_piston_speed_label = QLabel(f"{mean_piston_speed:.2f}")
        piston_row = self._label_value("Mean Piston Speed @ Redline (m/s)", self.block_piston_speed_label)
        self.property_form.addRow(piston_row)

        bore_spin = self._double_spin(block.bore, 50.0, 110.0, 0.1)
        self._bind_spin(bore_spin, lambda val: self._update_value(block, "bore", val), "bore")
        self.property_form.addRow("Bore (mm)", bore_spin)

        stroke_spin = self._double_spin(block.stroke, 10.0, 120.0, 0.1)
        self._bind_spin(stroke_spin, lambda val: self._update_value(block, "stroke", val), "stroke")
        self.property_form.addRow("Stroke (mm)", stroke_spin)

        rod_spin = self._double_spin(block.conrod_length, 80.0, 200.0, 0.5)
        self._bind_spin(rod_spin, lambda val: self._update_value(block, "conrod_length", val), "conrod_length")
        self.property_form.addRow("Conrod Length (mm)", rod_spin)

        cyl_spin = QSpinBox()
        cyl_spin.setRange(1, 16)
        cyl_spin.setValue(block.num_cylinders)
        self._bind_spin(cyl_spin, lambda val: self._update_value(block, "num_cylinders", val), "num_cylinders")
        self.property_form.addRow("Cylinders", cyl_spin)

        config_combo = QComboBox()
        config_combo.addItems(["L", "V", "Boxer"])
        config_combo.setCurrentText(block.config)
        config_combo.currentTextChanged.connect(lambda text: self._update_value(block, "config", text))
        self.property_form.addRow("Configuration", config_combo)

        bank_spin = self._double_spin(block.bank_angle, 0.0, 120.0, 0.5)
        self._bind_spin(bank_spin, lambda val: self._update_value(block, "bank_angle", val), "bank_angle")
        self.property_form.addRow("Bank Angle (deg)", bank_spin)

        redline_spin = QSpinBox()
        redline_spin.setRange(1000, 20000)
        redline_spin.setSingleStep(100)
        redline_spin.setSuffix(" rpm")
        redline_spin.setValue(int(block.redline_rpm))
        self._bind_spin(redline_spin, lambda val: self._update_value(block, "redline_rpm", float(val)), "redline_rpm")
        self.property_form.addRow("Redline RPM", redline_spin)

        firing_edit = QLineEdit(",".join(str(x) for x in block.firing_order))
        firing_edit.editingFinished.connect(lambda: self._update_firing_order(block, firing_edit.text()))
        self.property_form.addRow("Firing Order", firing_edit)

    def _build_head_form(self, head: CylinderHead) -> None:
        self._clear_property_form()

        chamber_spin = self._double_spin(head.combustion_chamber_vol or 40.0, 20.0, 80.0, 0.1)

        def update_cr(val: float) -> None:
            try:
                self._update_value(head, "compression_ratio", val)
                v_swept = self.calculate_swept_volume()
                if val > 1.0:
                    v_c = v_swept / max(val - 1.0, 1e-6)
                    head.combustion_chamber_vol = v_c
                    chamber_spin.blockSignals(True)
                    chamber_spin.setValue(v_c)
                    chamber_spin.blockSignals(False)
                    self.statusBar().showMessage(
                        f"Mode: Calculated from Compression Ratio (Vc={v_c:.2f} cc)", 2000
                    )
                self.update_overview()
            except Exception:
                pass

        cr_spin = self._double_spin(head.compression_ratio, 5.0, 18.0, 0.1)
        self._bind_spin(cr_spin, update_cr, "compression_ratio")
        cr_row = QWidget()
        cr_layout = QHBoxLayout()
        cr_layout.setContentsMargins(0, 0, 0, 0)
        cr_layout.addWidget(cr_spin)
        calc_btn = QPushButton("Calculator...")
        calc_btn.clicked.connect(lambda: self._open_compression_dialog(head, cr_spin))
        cr_layout.addWidget(calc_btn)
        cr_row.setLayout(cr_layout)
        self.property_form.addRow("Compression Ratio", cr_row)

        intake_valves_spin = QSpinBox()
        intake_valves_spin.setRange(1, 5)
        intake_valves_spin.setValue(head.intake_valves)
        self._bind_spin(intake_valves_spin, lambda val: self._update_value(head, "intake_valves", val), "intake_valves")
        self.property_form.addRow("Intake Valves", intake_valves_spin)

        exhaust_valves_spin = QSpinBox()
        exhaust_valves_spin.setRange(1, 5)
        exhaust_valves_spin.setValue(head.exhaust_valves)
        self._bind_spin(exhaust_valves_spin, lambda val: self._update_value(head, "exhaust_valves", val), "exhaust_valves")
        self.property_form.addRow("Exhaust Valves", exhaust_valves_spin)

        intake_dia_val = getattr(head, "intake_valve_diameter_mm", head.intake_valve_diameter)
        intake_dia = self._double_spin(intake_dia_val, 15.0, 60.0, 0.1)
        intake_dia.setSuffix(" mm")
        self._bind_spin(intake_dia, lambda val: self._update_valve_size(head, "intake", val), "intake_valve_diameter")
        self.property_form.addRow("Intake Valve Dia", intake_dia)

        exhaust_dia_val = getattr(head, "exhaust_valve_diameter_mm", head.exhaust_valve_diameter)
        exhaust_dia = self._double_spin(exhaust_dia_val, 15.0, 60.0, 0.1)
        exhaust_dia.setSuffix(" mm")
        self._bind_spin(exhaust_dia, lambda val: self._update_valve_size(head, "exhaust", val), "exhaust_valve_diameter")
        self.property_form.addRow("Exhaust Valve Dia", exhaust_dia)

        self._bind_spin(
            chamber_spin,
            lambda val: self._update_value(head, "combustion_chamber_vol", val),
            "combustion_chamber_vol",
        )
        self.property_form.addRow("Chamber Volume (cc)", chamber_spin)

        gasket_thickness = self._double_spin(head.gasket_thickness_mm, 0.1, 5.0, 0.05)
        gasket_thickness.setSuffix(" mm")
        self._bind_spin(gasket_thickness, lambda val: self._update_value(head, "gasket_thickness_mm", val), "gasket_thickness_mm")
        self.property_form.addRow("Gasket Thickness", gasket_thickness)

        gasket_bore = self._double_spin(head.gasket_bore_mm, 50.0, 120.0, 0.1)
        gasket_bore.setSuffix(" mm")
        self._bind_spin(gasket_bore, lambda val: self._update_value(head, "gasket_bore_mm", val), "gasket_bore_mm")
        self.property_form.addRow("Gasket Bore", gasket_bore)

        deck_clearance = self._double_spin(head.deck_clearance_mm, -2.0, 5.0, 0.05)
        deck_clearance.setSuffix(" mm")
        self._bind_spin(deck_clearance, lambda val: self._update_value(head, "deck_clearance_mm", val), "deck_clearance_mm")
        self.property_form.addRow("Deck Clearance", deck_clearance)

        piston_dome = self._double_spin(head.piston_dome_cc, -30.0, 30.0, 0.1)
        piston_dome.setSuffix(" cc")
        self._bind_spin(piston_dome, lambda val: self._update_value(head, "piston_dome_cc", val), "piston_dome_cc")
        self.property_form.addRow("Piston Dome Volume", piston_dome)

        port_flow_spin = self._double_spin(head.port_flow_cfm, 50.0, 500.0, 1.0)
        port_flow_spin.setSuffix(" cfm")
        self._bind_spin(port_flow_spin, lambda val: self._update_value(head, "port_flow_cfm", val), "port_flow_cfm")
        self.property_form.addRow("Port Flow @28\" (cfm)", port_flow_spin)

        port_cd_spin = self._double_spin(head.port_flow_efficiency, 0.1, 1.0, 0.01)
        self._bind_spin(port_cd_spin, lambda val: self._update_value(head, "port_flow_efficiency", val), "port_flow_efficiency")
        self.property_form.addRow("Port Flow Efficiency", port_cd_spin)

        mach_tol = self._double_spin(head.mach_tolerance, 0.5, 1.0, 0.05)
        self._bind_spin(mach_tol, lambda val: self._update_value(head, "mach_tolerance", val), "mach_tolerance")
        self.property_form.addRow("Mach Tolerance", mach_tol)

    def _build_cam_form(self, cam: Camshaft) -> None:
        self._clear_property_form()

        int_lift = self._double_spin(cam.intake_lift, 1.0, 20.0, 0.1)
        self._bind_spin(int_lift, lambda val: self._update_value(cam, "intake_lift", val), "intake_lift")
        self.property_form.addRow("Intake Lift (mm)", int_lift)

        exh_lift = self._double_spin(cam.exhaust_lift, 1.0, 20.0, 0.1)
        self._bind_spin(exh_lift, lambda val: self._update_value(cam, "exhaust_lift", val), "exhaust_lift")
        self.property_form.addRow("Exhaust Lift (mm)", exh_lift)

        int_dur = self._double_spin(cam.intake_duration, 180.0, 320.0, 0.5)
        self._bind_spin(int_dur, lambda val: self._update_value(cam, "intake_duration", val), "intake_duration")
        self.property_form.addRow("Intake Duration (deg)", int_dur)

        exh_dur = self._double_spin(cam.exhaust_duration, 180.0, 320.0, 0.5)
        self._bind_spin(exh_dur, lambda val: self._update_value(cam, "exhaust_duration", val), "exhaust_duration")
        self.property_form.addRow("Exhaust Duration (deg)", exh_dur)

        lsa_spin = self._double_spin(cam.lobe_separation, 80.0, 120.0, 0.5)
        self._bind_spin(lsa_spin, lambda val: self._update_value(cam, "lobe_separation", val), "lobe_separation")
        self.property_form.addRow("Lobe Separation (deg)", lsa_spin)

        adv_spin = self._double_spin(cam.advance, -50.0, 50.0, 0.5)
        self._bind_spin(adv_spin, lambda val: self._update_value(cam, "advance", val), "advance")
        self.property_form.addRow("Advance (deg)", adv_spin)

        phase_int = self._double_spin(cam.phase_deg_intake, -60.0, 60.0, 0.5)
        self._bind_spin(
            phase_int, lambda val: self._update_value(cam, "phase_deg_intake", val), "phase_deg_intake"
        )
        self.property_form.addRow("Intake Phase (deg)", phase_int)

        phase_exh = self._double_spin(cam.phase_deg_exhaust, -60.0, 60.0, 0.5)
        self._bind_spin(
            phase_exh, lambda val: self._update_value(cam, "phase_deg_exhaust", val), "phase_deg_exhaust"
        )
        self.property_form.addRow("Exhaust Phase (deg)", phase_exh)

        peak_spin = self._double_spin(cam.peak_rpm, 1000.0, 20000.0, 50.0)
        peak_spin.setSuffix(" rpm")
        self._bind_spin(peak_spin, lambda val: self._update_value(cam, "peak_rpm", val), "peak_rpm")
        self.property_form.addRow("Peak RPM", peak_spin)

    def _build_combustion_form(self, combustion: Combustion) -> None:
        self._clear_property_form()
        presets = {
            "Old Wedge": {"thermal_efficiency": 0.45, "burn_duration": 65.0, "ignition_advance": 25.0},
            "Modern Pentroof": {"thermal_efficiency": 0.54, "burn_duration": 45.0, "ignition_advance": 30.0},
            "Race / Hemi": {"thermal_efficiency": 0.60, "burn_duration": 35.0, "ignition_advance": 35.0},
            "Custom": {},
        }

        chamber_combo = QComboBox()
        chamber_combo.addItems(list(presets.keys()))
        chamber_combo.setCurrentText(
            combustion.chamber_type if combustion.chamber_type in presets else "Custom"
        )

        eff_spin = self._double_spin(combustion.thermal_efficiency, 0.3, 0.7, 0.01)
        burn_spin = self._double_spin(combustion.burn_duration, 20.0, 90.0, 0.5)
        burn_spin.setSuffix(" deg")
        advance_spin = self._double_spin(combustion.ignition_advance, 0.0, 60.0, 0.5)
        advance_spin.setSuffix(" deg")
        afr_spin = self._double_spin(combustion.afr, 10.0, 18.0, 0.05)
        wiebe_a_spin = self._double_spin(combustion.wiebe_a, 0.1, 10.0, 0.1)
        wiebe_m_spin = self._double_spin(combustion.wiebe_m, 0.1, 10.0, 0.1)

        def set_custom() -> None:
            if chamber_combo.currentText() != "Custom":
                chamber_combo.blockSignals(True)
                chamber_combo.setCurrentText("Custom")
                chamber_combo.blockSignals(False)

        self._bind_spin(
            eff_spin,
            lambda val: (self._update_value(combustion, "thermal_efficiency", val), set_custom()),
            "thermal_efficiency",
        )
        self._bind_spin(
            burn_spin,
            lambda val: (self._update_value(combustion, "burn_duration", val), set_custom()),
            "burn_duration",
        )
        self._bind_spin(
            advance_spin,
            lambda val: (self._update_value(combustion, "ignition_advance", val), set_custom()),
            "ignition_advance",
        )
        self._bind_spin(
            afr_spin,
            lambda val: (self._update_value(combustion, "afr", val), set_custom()),
            "afr",
        )
        self._bind_spin(
            wiebe_a_spin,
            lambda val: (self._update_value(combustion, "wiebe_a", val), set_custom()),
            "wiebe_a",
        )
        self._bind_spin(
            wiebe_m_spin,
            lambda val: (self._update_value(combustion, "wiebe_m", val), set_custom()),
            "wiebe_m",
        )

        def apply_preset(name: str) -> None:
            preset = presets.get(name, {})
            if not preset:
                self._update_value(combustion, "chamber_type", name)
                return
            combustion.chamber_type = name
            for attr, val in preset.items():
                self._update_value(combustion, attr, val)
            for spin, attr in (
                (eff_spin, "thermal_efficiency"),
                (burn_spin, "burn_duration"),
                (advance_spin, "ignition_advance"),
            ):
                spin.blockSignals(True)
                spin.setValue(getattr(combustion, attr))
                spin.blockSignals(False)

        chamber_combo.currentTextChanged.connect(apply_preset)

        self.property_form.addRow("Chamber Type", chamber_combo)
        self.property_form.addRow("Thermal Efficiency", eff_spin)
        self.property_form.addRow("Burn Duration", burn_spin)
        self.property_form.addRow("Ignition Advance", advance_spin)
        self.property_form.addRow("AFR", afr_spin)
        self.property_form.addRow("Wiebe a", wiebe_a_spin)
        self.property_form.addRow("Wiebe m", wiebe_m_spin)

    def _build_intake_form(self, intake: IntakeSystem) -> None:
        self._clear_property_form()

        runner_len = self._double_spin(intake.runner_length, 50.0, 800.0, 1.0)
        self._bind_spin(runner_len, lambda val: self._update_value(intake, "runner_length", val), "runner_length")
        self.property_form.addRow("Runner Length (mm)", runner_len)

        runner_dia = self._double_spin(intake.runner_diameter, 20.0, 120.0, 0.5)
        self._bind_spin(runner_dia, lambda val: self._update_value(intake, "runner_diameter", val), "runner_diameter")
        self.property_form.addRow("Runner Diameter (mm)", runner_dia)

        plenum_vol = self._double_spin(intake.plenum_volume, 0.5, 10.0, 0.1)
        self._bind_spin(plenum_vol, lambda val: self._update_value(intake, "plenum_volume", val), "plenum_volume")
        self.property_form.addRow("Plenum Volume (L)", plenum_vol)

        throttle_dia = self._double_spin(intake.throttle_body_dia, 30.0, 90.0, 0.5)
        self._bind_spin(throttle_dia, lambda val: self._update_value(intake, "throttle_body_dia", val), "throttle_body_dia")
        self.property_form.addRow("Throttle Body Dia (mm)", throttle_dia)

        throttle_cfm = self._double_spin(intake.throttle_cfm, 100.0, 1500.0, 10.0)
        throttle_cfm.setSuffix(" cfm")
        self._bind_spin(throttle_cfm, lambda val: self._update_value(intake, "throttle_cfm", val), "throttle_cfm")
        self.property_form.addRow("Throttle/Carb Rating (cfm)", throttle_cfm)

    def _build_exhaust_form(self, exhaust: ExhaustSystem) -> None:
        self._clear_property_form()

        primary_len = self._double_spin(exhaust.header_primary_length, 100.0, 1200.0, 1.0)
        self._bind_spin(primary_len, lambda val: self._update_value(exhaust, "header_primary_length", val), "header_primary_length")
        self.property_form.addRow("Primary Length (mm)", primary_len)

        primary_dia = self._double_spin(exhaust.header_primary_diameter, 20.0, 100.0, 0.5)
        self._bind_spin(primary_dia, lambda val: self._update_value(exhaust, "header_primary_diameter", val), "header_primary_diameter")
        self.property_form.addRow("Primary Diameter (mm)", primary_dia)

        collector_len = self._double_spin(exhaust.collector_length, 100.0, 1200.0, 1.0)
        self._bind_spin(collector_len, lambda val: self._update_value(exhaust, "collector_length", val), "collector_length")
        self.property_form.addRow("Collector Length (mm)", collector_len)

    def _build_induction_form(self) -> None:
        self._clear_property_form()

        induction_state = self.engine.induction_classification()
        induction_name = self.engine.induction_mode_name()

        title = QLabel(f"Induction System: {induction_name}")
        title.setStyleSheet("font-size: 15px; font-weight: 700; color: #18212f;")
        title.setWordWrap(True)
        self.property_form.addRow(title)

        note = QLabel()
        note.setWordWrap(True)
        note.setStyleSheet("font-size: 11px; color: #506072;")
        if induction_state == "Turbo":
            note.setText(
                "Turbo mode is driven by `turbo.enabled=true`. This panel edits `turbo.*` directly and keeps the legacy "
                "`supercharger` block neutral so preflight stays valid."
            )
        elif induction_state == "Supercharger":
            note.setText(
                "Mechanical boost mode edits the legacy `supercharger` block and forces `turbo.enabled=false` so the "
                "engine cannot end up with two active boost systems."
            )
        else:
            note.setText(
                "Naturally aspirated mode keeps both boost systems disabled. Stored `turbo.*` data is preserved until "
                "you switch back to Turbo."
            )
        self.property_form.addRow(note)

        type_combo = QComboBox()
        available_modes = ["NA", "Turbo", "Roots"]
        supercharger_type = str(self.engine.supercharger.type or "NA").strip()
        if supercharger_type and supercharger_type not in {"NA", "Turbo", "Roots"}:
            available_modes.append(supercharger_type)
        type_combo.addItems(available_modes)
        if induction_state == "Turbo":
            current_mode = "Turbo"
        elif induction_state == "Supercharger":
            current_mode = supercharger_type if supercharger_type != "NA" else "Roots"
        else:
            current_mode = "NA"
        type_combo.setCurrentText(current_mode)
        type_combo.currentTextChanged.connect(self._apply_induction_mode_change)
        self.property_form.addRow("Mode", type_combo)

        if induction_state == "Turbo":
            target_boost_spin = self._double_spin(float(self.engine.turbo.target_boost_kpa or 0.0), 0.0, 400.0, 1.0)
            target_boost_spin.setSuffix(" kPa")
            target_boost_spin.setSpecialValueText("None")
            self._bind_spin(
                target_boost_spin,
                lambda val: self._update_value(
                    self.engine.turbo,
                    "target_boost_kpa",
                    float(val) if float(val) > 0.0 else None,
                ),
                "turbo.target_boost_kpa",
            )
            self.property_form.addRow("Target Boost", target_boost_spin)

            target_pr_spin = self._double_spin(float(self.engine.turbo.target_pr or 0.0), 0.0, 5.0, 0.01)
            target_pr_spin.setSpecialValueText("None")
            self._bind_spin(
                target_pr_spin,
                lambda val: self._update_value(
                    self.engine.turbo,
                    "target_pr",
                    float(val) if float(val) > 0.0 else None,
                ),
                "turbo.target_pr",
            )
            self.property_form.addRow("Target PR", target_pr_spin)

            wastegate_box = QCheckBox("Enable wastegate target control")
            wastegate_box.setChecked(bool(self.engine.turbo.wastegate_enabled))
            wastegate_box.stateChanged.connect(
                lambda state: self._update_value(self.engine.turbo, "wastegate_enabled", bool(state))
            )
            self.property_form.addRow("Wastegate", wastegate_box)

            wastegate_gain = self._double_spin(self.engine.turbo.wastegate_gain, 0.01, 5.0, 0.01)
            self._bind_spin(
                wastegate_gain,
                lambda val: self._update_value(self.engine.turbo, "wastegate_gain", val),
                "turbo.wastegate_gain",
            )
            self.property_form.addRow("Wastegate Gain", wastegate_gain)

            max_iters = QSpinBox()
            max_iters.setRange(1, 50)
            max_iters.setValue(int(self.engine.turbo.max_iters))
            self._bind_spin(
                max_iters,
                lambda val: self._update_value(self.engine.turbo, "max_iters", int(val)),
                "turbo.max_iters",
            )
            self.property_form.addRow("Solver Iterations", max_iters)

            comp_eff = self._double_spin(self.engine.turbo.compressor_efficiency, 0.0, 1.0, 0.01)
            self._bind_spin(
                comp_eff,
                lambda val: self._update_value(self.engine.turbo, "compressor_efficiency", val),
                "turbo.compressor_efficiency",
            )
            self.property_form.addRow("Compressor Eff", comp_eff)

            turbine_eff = self._double_spin(self.engine.turbo.turbine_efficiency, 0.0, 1.0, 0.01)
            self._bind_spin(
                turbine_eff,
                lambda val: self._update_value(self.engine.turbo, "turbine_efficiency", val),
                "turbo.turbine_efficiency",
            )
            self.property_form.addRow("Turbine Eff", turbine_eff)

            ic_spin = self._double_spin(self.engine.turbo.intercooler_efficiency, 0.0, 1.0, 0.01)
            self._bind_spin(
                ic_spin,
                lambda val: self._update_value(self.engine.turbo, "intercooler_efficiency", val),
                "turbo.intercooler_efficiency",
            )
            self.property_form.addRow("Intercooler Eff", ic_spin)

            compressor_row = self._build_json_editor_row(
                self.engine.turbo.compressor_map,
                expected_type=list,
                setter=lambda payload: self._update_value(self.engine.turbo, "compressor_map", payload),
                label="turbo.compressor_map",
                placeholder='[{"pr": 1.6, "flow": 0.18, "eff": 0.72}]',
            )
            self.property_form.addRow("Compressor Map", compressor_row)

            turbine_row = self._build_json_editor_row(
                self.engine.turbo.turbine_map,
                expected_type=list,
                setter=lambda payload: self._update_value(self.engine.turbo, "turbine_map", payload),
                label="turbo.turbine_map",
                placeholder='[{"pr": 1.8, "flow": 0.16, "eff": 0.70}]',
            )
            self.property_form.addRow("Turbine Map", turbine_row)

            response_row = self._build_json_editor_row(
                self.engine.turbo.response_model,
                expected_type=dict,
                setter=lambda payload: self._update_value(self.engine.turbo, "response_model", payload),
                label="turbo.response_model",
                placeholder='{"enabled": true, "spool_width_rpm": 900.0}',
            )
            self.property_form.addRow("Response Model", response_row)
            return

        if induction_state == "Supercharger":
            boost_spin = self._double_spin(self.engine.supercharger.boost_pressure_bar, 0.0, 3.0, 0.05)
            self._bind_spin(
                boost_spin,
                lambda val: self._update_value(self.engine.supercharger, "boost_pressure_bar", val),
                "supercharger.boost_pressure_bar",
            )
            self.property_form.addRow("Boost (bar)", boost_spin)

            ic_spin = self._double_spin(self.engine.supercharger.intercooler_efficiency, 0.0, 1.0, 0.01)
            self._bind_spin(
                ic_spin,
                lambda val: self._update_value(self.engine.supercharger, "intercooler_efficiency", val),
                "supercharger.intercooler_efficiency",
            )
            self.property_form.addRow("Intercooler Eff", ic_spin)
            return

        idle_note = QLabel(
            "No boost hardware is active. Select `Turbo` to edit `turbo.*`, or `Roots` to edit the mechanical supercharger block."
        )
        idle_note.setWordWrap(True)
        idle_note.setStyleSheet("font-size: 11px; color: #506072;")
        self.property_form.addRow(idle_note)

    def _build_supercharger_form(self, supercharger: Supercharger) -> None:
        self._build_induction_form()

    def _build_friction_form(self, friction: Friction) -> None:
        self._clear_property_form()

        bottom_combo = QComboBox()
        bottom_combo.addItems(["Standard", "Performance", "Race"])
        bottom_combo.setCurrentText(friction.bottom_end_type)
        self.property_form.addRow("Bottom End Type", bottom_combo)

        base_spin = self._double_spin(friction.friction_base_kpa, 0.0, 150.0, 0.5)
        base_spin.setSuffix(" kPa")
        lin_spin = self._double_spin(friction.friction_linear_factor, 0.0, 0.2, 0.001)
        lin_spin.setDecimals(5)
        quad_spin = self._double_spin(friction.friction_quadratic_factor, 0.0, 1e-4, 1e-7)
        quad_spin.setDecimals(8)
        scale_spin = self._double_spin(friction.global_scaling_factor, 0.1, 5.0, 0.05)

        self._bind_spin(base_spin, lambda val: self._update_value(friction, "friction_base_kpa", val), "friction_base_kpa")
        self._bind_spin(
            lin_spin, lambda val: self._update_value(friction, "friction_linear_factor", val), "friction_linear_factor"
        )
        self._bind_spin(
            quad_spin,
            lambda val: self._update_value(friction, "friction_quadratic_factor", val),
            "friction_quadratic_factor",
        )
        self._bind_spin(
            scale_spin,
            lambda val: self._update_value(friction, "global_scaling_factor", val),
            "global_scaling_factor",
        )

        self.property_form.addRow("Base FMEP (kPa)", base_spin)
        self.property_form.addRow("Linear Coeff", lin_spin)
        self.property_form.addRow("Quadratic Coeff", quad_spin)
        self.property_form.addRow("Global Scaling Factor", scale_spin)

        presets = {
            "Standard": (45.0, 0.03, 2.5e-6),
            "Performance": (35.0, 0.02, 1.8e-6),
            "Race": (25.0, 0.015, 0.9e-6),
        }

        def apply_preset(text: str) -> None:
            self._update_value(friction, "bottom_end_type", text)
            preset = presets.get(text)
            if not preset:
                return
            base, lin, quad = preset
            for spin, val, attr in (
                (base_spin, base, "friction_base_kpa"),
                (lin_spin, lin, "friction_linear_factor"),
                (quad_spin, quad, "friction_quadratic_factor"),
            ):
                spin.blockSignals(True)
                spin.setValue(val)
                spin.blockSignals(False)
                setattr(friction, attr, val)
            self.update_overview()

        bottom_combo.currentTextChanged.connect(apply_preset)

        def _checkbox_row(label: str, attr: str) -> None:
            box = QCheckBox(label)
            box.setChecked(getattr(friction, attr))
            box.stateChanged.connect(lambda state, a=attr: self._update_value(friction, a, bool(state)))
            self.property_form.addRow(label, box)

        _checkbox_row("Water Pump", "water_pump")
        _checkbox_row("Alternator", "alternator")
        _checkbox_row("Power Steering", "power_steering")
        _checkbox_row("Mechanical Fan", "mechanical_fan")

    def _resolve_fuel_preset_definition(self, preset: str) -> Optional[dict[str, Any]]:
        if preset in FUEL_PRESET_DEFINITIONS:
            return FUEL_PRESET_DEFINITIONS[preset]
        if preset in FUEL_PRESET_LEGACY_ALIASES:
            return FUEL_PRESET_LEGACY_ALIASES[preset]
        return None

    def _apply_fuel_preset(self, fuel: Fuel, preset: str) -> None:
        definition = self._resolve_fuel_preset_definition(preset)
        if definition is None:
            return
        fuel.type_name = str(definition["type_name"])
        if preset == "Custom":
            return
        fuel.octane_rating = float(definition["octane_rating"])
        fuel.energy_density = float(definition["energy_density"])
        fuel.stoich_afr = float(definition["stoich_afr"])

    def _populate_fuel_preset_combo(self, combo: QComboBox) -> None:
        primary_items = FUEL_PRESET_GROUPS[0][1]
        advanced_items = FUEL_PRESET_GROUPS[1][1]
        combo.addItems(primary_items)
        combo.insertSeparator(combo.count())
        combo.addItem("Advanced / Special Fuels")
        advanced_header = combo.model().item(combo.count() - 1)
        if advanced_header is not None:
            advanced_header.setEnabled(False)
        combo.addItems(advanced_items)

    def _matches_fuel_preset(self, fuel: Fuel, preset: str) -> bool:
        definition = FUEL_PRESET_DEFINITIONS[preset]
        if preset == "Custom":
            return False
        current_name = (fuel.type_name or "").strip().lower()
        match_names = {name.lower() for name in definition.get("match_names", set())}
        name_matches = current_name in match_names or current_name == str(definition["type_name"]).strip().lower()
        octane_matches = abs(fuel.octane_rating - float(definition["octane_rating"])) <= 0.6
        energy_matches = abs(fuel.energy_density - float(definition["energy_density"])) <= 0.25e6
        afr_matches = abs(fuel.stoich_afr - float(definition["stoich_afr"])) <= 0.15
        return (name_matches and octane_matches) or (octane_matches and energy_matches and afr_matches)

    def _matching_fuel_preset_label(self, fuel: Fuel) -> str:
        for _, preset_names in FUEL_PRESET_GROUPS:
            for preset in preset_names:
                if preset == "Custom":
                    continue
                if self._matches_fuel_preset(fuel, preset):
                    return preset
        return "Custom"

    def _sync_fuel_preset_combo(self, combo: QComboBox, fuel: Fuel) -> None:
        match = self._matching_fuel_preset_label(fuel)
        index = combo.findText(match)
        if index >= 0 and combo.currentIndex() != index:
            combo.blockSignals(True)
            combo.setCurrentIndex(index)
            combo.blockSignals(False)

    def _build_fuel_form(self, fuel: Fuel) -> None:
        self._clear_property_form()

        preset_combo = QComboBox()
        self._populate_fuel_preset_combo(preset_combo)
        self._sync_fuel_preset_combo(preset_combo, fuel)

        name_edit = QLineEdit(fuel.type_name)
        octane_spin = self._double_spin(fuel.octane_rating, 70.0, 130.0, 0.5)
        energy_spin = self._double_spin(fuel.energy_density, 10e6, 50e6, 1e5)
        energy_spin.setSuffix(" J/kg")
        energy_spin.setDecimals(1)
        afr_spin = self._double_spin(fuel.stoich_afr, 5.0, 18.0, 0.05)

        def apply_and_refresh(text: str) -> None:
            self._apply_fuel_preset(fuel, text)
            name_edit.setText(fuel.type_name)
            octane_spin.setValue(fuel.octane_rating)
            energy_spin.setValue(fuel.energy_density)
            afr_spin.setValue(fuel.stoich_afr)
            self.update_overview()

        preset_combo.currentTextChanged.connect(apply_and_refresh)
        self.property_form.addRow("Presets", preset_combo)

        def update_fuel_name() -> None:
            self._update_value(fuel, "type_name", name_edit.text())
            self._sync_fuel_preset_combo(preset_combo, fuel)

        name_edit.editingFinished.connect(update_fuel_name)
        self.property_form.addRow("Fuel Type", name_edit)

        self._bind_spin(
            octane_spin,
            lambda val: (self._update_value(fuel, "octane_rating", val), self._sync_fuel_preset_combo(preset_combo, fuel)),
            "octane_rating",
        )
        self.property_form.addRow("Octane Rating", octane_spin)

        self._bind_spin(
            energy_spin,
            lambda val: (self._update_value(fuel, "energy_density", val), self._sync_fuel_preset_combo(preset_combo, fuel)),
            "energy_density",
        )
        self.property_form.addRow("Energy Density", energy_spin)

        self._bind_spin(
            afr_spin,
            lambda val: (self._update_value(fuel, "stoich_afr", val), self._sync_fuel_preset_combo(preset_combo, fuel)),
            "stoich_afr",
        )
        self.property_form.addRow("Stoich AFR", afr_spin)

    def _build_sim_settings_form(self, settings: SimulationSettings) -> None:
        self._clear_property_form()

        ign_spin = self._double_spin(settings.ignition_timing_btdc, -10.0, 60.0, 0.5)
        ign_spin.setSuffix(" deg BTDC")
        self._bind_spin(ign_spin, lambda val: self._update_value(settings, "ignition_timing_btdc", val), "ignition_timing_btdc")
        self.property_form.addRow("Ignition Timing", ign_spin)

        heat_spin = self._double_spin(settings.heat_loss_factor, 0.0, 5.0, 0.1)
        self._bind_spin(heat_spin, lambda val: self._update_value(settings, "heat_loss_factor", val), "heat_loss_factor")
        self.property_form.addRow("Calibration: Heat Loss", heat_spin)

        pipe_spin = self._double_spin(settings.pipe_friction_factor, 0.0, 5.0, 0.1)
        self._bind_spin(pipe_spin, lambda val: self._update_value(settings, "pipe_friction_factor", val), "pipe_friction_factor")
        self.property_form.addRow("Calibration: Pipe Friction", pipe_spin)

        tune_spin = self._double_spin(settings.tuning_sensitivity, 0.0, 5.0, 0.1)
        self._bind_spin(tune_spin, lambda val: self._update_value(settings, "tuning_sensitivity", val), "tuning_sensitivity")
        self.property_form.addRow("Calibration: Tuning Sensitivity", tune_spin)

        air_temp = self._double_spin(settings.air_temperature_c, -50.0, 80.0, 0.5)
        air_temp.setSuffix(" C")
        self._bind_spin(air_temp, lambda val: self._update_value(settings, "air_temperature_c", val), "air_temperature_c")
        self.property_form.addRow("Air Temp (C)", air_temp)

        air_press = self._double_spin(settings.air_pressure_bar, 0.5, 2.0, 0.01)
        air_press.setSuffix(" bar")
        self._bind_spin(air_press, lambda val: self._update_value(settings, "air_pressure_bar", val), "air_pressure_bar")
        self.property_form.addRow("Air Pressure (bar)", air_press)

    # -------------------------- Helpers -----------------------------------
    def _double_spin(self, value: float, minimum: float, maximum: float, step: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(3)
        spin.setSingleStep(step)
        spin.setValue(value)
        return spin

    def _update_window_title(self) -> None:
        title = "PyWaveDyn - Virtual Dyno"
        if self.current_project_path:
            title = f"{title} — {Path(self.current_project_path).name}"
        self.setWindowTitle(title)

    def _bind_spin(self, spin: Any, setter: Any, attr_name: Optional[str] = None) -> None:
        def handler() -> None:
            label = attr_name or "value"
            try:
                val = spin.value()
                setter(val)
                self.statusBar().showMessage(f"Updated {label} to {val}", 2000)
            except Exception as exc:
                logger = logging.getLogger(__name__)
                trace = traceback.format_exc()
                logger.error("Failed to update %s: %s\n%s", label, exc, trace)
                message = f"Failed to update {label}: {exc}"
                self.statusBar().showMessage(message, 4000)
                QMessageBox.critical(self, "Update Error", message)

        spin.editingFinished.connect(handler)

    def _label_value(self, label: str, value: str | QLabel) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(label))
        layout.addStretch()
        if isinstance(value, QLabel):
            layout.addWidget(value)
        else:
            layout.addWidget(QLabel(value))
        container.setLayout(layout)
        return container

    def _build_json_editor_row(
        self,
        value: Any,
        *,
        expected_type: type,
        setter: Any,
        label: str,
        placeholder: str,
    ) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        editor = QTextEdit()
        editor.setAcceptRichText(False)
        editor.setPlaceholderText(placeholder)
        editor.setMinimumHeight(90)
        editor.setPlainText(json.dumps(value, indent=2))

        apply_button = QPushButton("Apply JSON")
        apply_button.setMaximumWidth(120)

        def apply_json() -> None:
            try:
                raw_text = editor.toPlainText().strip()
                payload = json.loads(raw_text) if raw_text else expected_type()
                if not isinstance(payload, expected_type):
                    raise ValueError(f"Expected {expected_type.__name__} JSON payload")
                setter(payload)
                editor.setPlainText(json.dumps(payload, indent=2))
                self.statusBar().showMessage(f"Updated {label}", 2000)
            except Exception as exc:
                message = f"Failed to update {label}: {exc}"
                self.statusBar().showMessage(message, 4000)
                QMessageBox.critical(self, "JSON Update Error", message)

        apply_button.clicked.connect(apply_json)
        layout.addWidget(editor)
        layout.addWidget(apply_button, 0, Qt.AlignLeft)
        container.setLayout(layout)
        return container

    def _refresh_induction_tree_item(self) -> None:
        item = getattr(self, "induction_tree_item", None)
        if item is not None:
            item.setText(0, self.engine.induction_tree_label())

    def _apply_induction_mode_change(self, mode: str) -> None:
        self.engine.set_induction_mode(mode)
        self._refresh_induction_tree_item()
        self.update_overview()
        if self.navigation_tree.currentItem() is getattr(self, "induction_tree_item", None):
            QTimer.singleShot(0, self._build_induction_form)

    def _update_value(self, obj: Any, attr: str, value: Any) -> None:
        setattr(obj, attr, value)
        current_item = self.navigation_tree.currentItem()
        if current_item and isinstance(obj, Block):
            self._update_block_derived_labels(obj)
            if attr in {"config"}:
                self._schedule_block_form_rebuild(obj)
        if obj is self.engine.supercharger or obj is self.engine.turbo:
            self._refresh_induction_tree_item()
        self.update_overview()

    def _update_block_derived_labels(self, block: Block) -> None:
        if self.block_displacement_label is not None:
            self.block_displacement_label.setText(f"{block.displacement_cc:.1f}")
        if self.block_piston_speed_label is not None:
            mean_piston_speed = 2.0 * (block.stroke * 1e-3) * block.redline_rpm / 60.0
            self.block_piston_speed_label.setText(f"{mean_piston_speed:.2f}")

    def _schedule_block_form_rebuild(self, block: Block) -> None:
        QTimer.singleShot(0, lambda b=block: self._build_block_form(b))

    def _clear_head_chamber_override(self, head: CylinderHead) -> None:
        head.combustion_chamber_vol = 0.0
        self.statusBar().showMessage("Mode: Calculated from Compression Ratio", 2000)
        self.update_overview()

    def _update_valve_size(self, head: CylinderHead, attr_base: str, value: float) -> None:
        setattr(head, f"{attr_base}_valve_diameter", value)
        setattr(head, f"{attr_base}_valve_diameter_mm", value)
        self.update_overview()

    def calculate_swept_volume(self) -> float:
        """Return per-cylinder swept volume in cc using current block geometry."""
        bore = self.engine.block.bore
        stroke = self.engine.block.stroke
        return math.pi * (bore / 20.0) ** 2 * (stroke / 10.0)

    def _update_firing_order(self, block: Block, text: str) -> None:
        try:
            order = [int(x.strip()) for x in text.split(",") if x.strip()]
            if order:
                block.firing_order = order
        except ValueError:
            pass
        self.update_overview()

    def _engine_architecture_label(self, block: Block) -> str:
        config = str(block.config).strip().upper()
        count = int(block.num_cylinders)
        if config == "L":
            return f"L{count}"
        if config == "V":
            return f"V{count}"
        if config == "BOXER":
            return f"Boxer {count}"
        return f"{block.config} {count}"

    def _overview_card_html(self, title: str, rows: list[tuple[str, str]]) -> str:
        row_html = "".join(
            "<tr>"
            f"<td class='label'>{html.escape(label)}</td>"
            f"<td class='value'>{html.escape(str(value))}</td>"
            "</tr>"
            for label, value in rows
        )
        return (
            "<table class='card' width='100%' cellspacing='0' cellpadding='0'>"
            "<tr><td>"
            f"<div class='card-title'>{html.escape(title)}</div>"
            "<table class='kv' width='100%' cellspacing='0' cellpadding='0'>"
            f"{row_html}"
            "</table>"
            "</td></tr>"
            "</table>"
        )

    def _overview_inline_summary_html(self, title: str, items: list[tuple[str, str]]) -> str:
        separator = " <span style='color: #90a0b3;'>&bull;</span> "
        content = separator.join(
            "<span style='color: #506072;'>"
            f"{html.escape(label)}</span> "
            "<span style='color: #18212f; font-weight: 600;'>"
            f"{html.escape(str(value))}</span>"
            for label, value in items
        )
        return (
            "<span style='color: #314154; font-weight: 700;'>"
            f"{html.escape(title)}:</span> "
            f"{content}"
        )

    def _overview_dataset_status(self) -> str:
        if self.real_dyno_widget is None or self.real_dyno_widget.dataset_dir is None:
            return "None"
        dataset_meta = self.real_dyno_widget.dataset_meta or {}
        dataset_id = str(dataset_meta.get("dataset_id", "")).strip()
        if dataset_id:
            return dataset_id
        return self.real_dyno_widget.dataset_dir.name

    def _overview_last_dyno_status(self) -> str:
        if not self.last_dyno_payload:
            return "None"
        metadata = self.last_dyno_payload.get("metadata", {})
        coupling_mode = str(metadata.get("coupling_mode", "")).strip().lower()
        mode_label = "v2" if coupling_mode == "v2_orchestrator" else (self._dyno_mode_running or self._dyno_mode())
        point_count = len(list(self.last_dyno_payload.get("results", [])))
        if math.isfinite(self._dyno_max_hp_value) and self._dyno_max_hp_value > 0.0 and self._dyno_max_hp_rpm > 0:
            dyno_summary = f"{mode_label} | {self._dyno_max_hp_value:.1f} hp @ {self._dyno_max_hp_rpm:.0f} rpm"
            if point_count:
                dyno_summary += f" | {point_count} pts"
            return dyno_summary
        if point_count:
            return f"{mode_label} | {point_count} pts"
        return f"{mode_label} ready"

    def _overview_report_status(self) -> str:
        if self.real_dyno_widget is None:
            return "None"
        report_names = [
            label
            for label, payload in (
                ("compare", self.real_dyno_widget.compare_report),
                ("staged", self.real_dyno_widget.staged_report),
                ("validation", self.real_dyno_widget.validation_report),
                ("A/B", self.real_dyno_widget.ab_report),
                ("sensitivity", self.real_dyno_widget.sensitivity_report),
                ("optimize", self.real_dyno_widget.optimize_report),
            )
            if payload is not None
        ]
        if not report_names:
            return "None"
        if len(report_names) <= 3:
            return ", ".join(report_names)
        return f"{len(report_names)} available"

    def _overview_calibration_status(self) -> str:
        if self.real_dyno_widget is None or self.real_dyno_widget.staged_report is None:
            return "Not run"
        stages = list(self.real_dyno_widget.staged_report.get("stages", []))
        if not stages:
            return "Report ready"
        counts: dict[str, int] = {}
        for stage in stages:
            status = str(stage.get("status", "unknown")).strip().lower()
            counts[status] = counts.get(status, 0) + 1
        parts = [f"{counts[key]} {key}" for key in ("accepted", "rejected", "omitted") if counts.get(key)]
        return ", ".join(parts) if parts else "Report ready"

    def _quick_dyno_project_name(self) -> str:
        if self.current_project_path:
            return Path(self.current_project_path).name
        return "Unsaved Project"

    def _quick_dyno_engine_name(self) -> str:
        architecture = self._engine_architecture_label(self.engine.block)
        displacement_l = self.engine.block.displacement_cc / 1000.0
        return f"{architecture} | {displacement_l:.2f} L | {self.engine.induction_summary()}"

    def _quick_dyno_mode_label(self) -> str:
        return "v2 (Pro Coupled)" if self._dyno_mode() == "v2" else "v1 (Quick 0D)"

    def _quick_dyno_quality_label(self) -> str:
        return "Stable" if self._dyno_quality() == "stable" else "Fast"

    def _analysis_mode_label(self) -> str:
        if self.last_dyno_payload is not None:
            metadata = self.last_dyno_payload.get("metadata", {})
            coupling_mode = str(metadata.get("coupling_mode", "")).strip().lower()
            if coupling_mode == "v2_orchestrator":
                return "v2 (Pro Coupled)"
            return "v1 (Quick 0D)"
        mode = self._dyno_mode_running or self._dyno_mode()
        return "v2 (Pro Coupled)" if mode == "v2" else "v1 (Quick 0D)"

    def _quick_dyno_requested_rpm_values(self) -> list[int]:
        max_rpm = int(self.engine.block.redline_rpm)
        return list(range(1000, max_rpm + 500, 500))

    def _quick_dyno_sweep_text(self) -> str:
        rpm_values = self._dyno_rpm_values or self._quick_dyno_requested_rpm_values()
        if not rpm_values:
            return "No sweep range"
        return f"{min(rpm_values)}-{max(rpm_values)} rpm ({len(rpm_values)} pts)"

    def _quick_dyno_result_count(self) -> int:
        if self.last_dyno_payload is not None:
            return len(list(self.last_dyno_payload.get("results", [])))
        return len(self._dyno_results)

    def _quick_dyno_point_label(self, count: int) -> str:
        return "point" if count == 1 else "points"

    def _quick_dyno_status_value(self) -> str:
        if self._dyno_run_state == "Cancelling":
            return "Cancelling"
        if self._dyno_run_state == "Running":
            return "Running"
        return "Ready"

    def _quick_dyno_last_run_value(self) -> str:
        if self._dyno_run_state in {"Running", "Cancelling"}:
            return "In progress"
        if self.last_dyno_payload is not None:
            return "Completed"
        if self._dyno_run_state == "Cancelled":
            return "Cancelled"
        if self._dyno_run_state == "Error":
            return "Failed"
        return "Not run yet"

    def _quick_dyno_result_status_value(self) -> str:
        result_count = self._quick_dyno_result_count()
        requested = len(self._dyno_rpm_values or self._quick_dyno_requested_rpm_values())
        if self._dyno_run_state in {"Running", "Cancelling"}:
            return f"{result_count}/{requested} points collected"
        if self.last_dyno_payload is not None:
            if result_count:
                return f"{result_count} {self._quick_dyno_point_label(result_count)} available"
            return "No valid points saved"
        return "No result available"

    def _quick_dyno_result_availability(self) -> str:
        result_count = self._quick_dyno_result_count()
        requested = len(self._dyno_rpm_values or self._quick_dyno_requested_rpm_values())
        if self.dyno_thread and self.dyno_thread.isRunning():
            return f"In progress ({result_count}/{requested} pts)"
        if self.last_dyno_payload is not None:
            if result_count:
                return f"Available ({result_count} pts)"
            return "No valid points saved"
        if self._dyno_run_state == "Cancelled":
            return "Cancelled"
        if self._dyno_run_state == "Error":
            return "Failed"
        return "None yet"

    def _refresh_quick_dyno_panel(self) -> None:
        if not hasattr(self, "dyno_context_label"):
            return

        self.dyno_settings_quality_value.setText(self._quick_dyno_quality_label())
        self.dyno_settings_sweep_value.setText(self._quick_dyno_sweep_text())
        project_name = self._quick_dyno_project_name()
        engine_name = self._quick_dyno_engine_name()
        mode_label = self._quick_dyno_mode_label()
        quality_label = self._quick_dyno_quality_label()
        sweep_text = self._quick_dyno_sweep_text()
        status_value = self._quick_dyno_status_value()

        def _context_line(items: list[tuple[str, str]]) -> str:
            return " <span style='color: #90a0b3;'>&bull;</span> ".join(
                (
                    "<span style='color: #5f6b7a; font-weight: 700;'>"
                    f"{html.escape(label)}:</span> "
                    f"<span style='color: #18212f;'>{html.escape(value)}</span>"
                )
                for label, value in items
            )

        context_html = (
            _context_line([("Project", project_name), ("Engine", engine_name)])
            + "<br>"
            + _context_line([("Solver", mode_label), ("Quality", quality_label), ("Sweep", sweep_text)])
        )
        self.dyno_context_label.setText(context_html)
        self.dyno_status_value_label.setText(f"Status: {status_value}")
        self.dyno_result_state_label.setText(f"Last run: {self._quick_dyno_last_run_value()}")
        self.dyno_result_value_label.setText(f"Result: {self._quick_dyno_result_status_value()}")
        self.dyno_plot_caption_label.setText(
            f"Plot context: {project_name} / {engine_name} | {mode_label} | {sweep_text} | {status_value}"
        )
        if self._dyno_knock_detected:
            self.dyno_plot_notice_label.setText("Knock warning: low octane for this compression")
            self.dyno_plot_notice_label.setVisible(True)
        else:
            self.dyno_plot_notice_label.clear()
            self.dyno_plot_notice_label.setVisible(False)

        peak_power_ready = math.isfinite(self._dyno_max_hp_value) and self._dyno_max_hp_value > 0.0 and self._dyno_max_hp_rpm > 0
        peak_torque_ready = math.isfinite(self._dyno_max_tq_value) and self._dyno_max_tq_value > 0.0 and self._dyno_max_tq_rpm > 0
        self.dyno_summary_peak_power_value.setText(
            f"{self._dyno_max_hp_value:.1f} hp @ {self._dyno_max_hp_rpm:.0f} rpm" if peak_power_ready else "-"
        )
        self.dyno_summary_peak_power_rpm_value.setText(f"{self._dyno_max_hp_rpm:.0f} rpm" if peak_power_ready else "-")
        self.dyno_summary_peak_torque_value.setText(
            f"{self._dyno_max_tq_value:.1f} Nm @ {self._dyno_max_tq_rpm:.0f} rpm" if peak_torque_ready else "-"
        )
        self.dyno_summary_peak_torque_rpm_value.setText(f"{self._dyno_max_tq_rpm:.0f} rpm" if peak_torque_ready else "-")
        self.dyno_summary_sweep_value.setText(self._quick_dyno_sweep_text())

        if self.dyno_thread and self.dyno_thread.isRunning():
            self.dyno_summary_detail_label.setText(
                f"Collecting points in {self._quick_dyno_mode_label()}: {self._quick_dyno_result_count()} so far."
            )
            self._refresh_analysis_panel()
            return

        if self.last_dyno_payload is not None:
            result_count = self._quick_dyno_result_count()
            invalid_count = len(self._dyno_invalid_rpms)
            if result_count:
                detail = f"{result_count} point(s) ready in {self._quick_dyno_mode_label()}."
            else:
                detail = f"Sweep completed in {self._quick_dyno_mode_label()}, but no exportable points were kept."
            if invalid_count:
                detail += f" {invalid_count} invalid point(s) stayed out of the main legend."
            self.dyno_summary_detail_label.setText(detail)
            self._refresh_analysis_panel()
            return

        if self._dyno_run_state == "Cancelled":
            self.dyno_summary_detail_label.setText("No exportable dyno result is currently stored.")
            self._refresh_analysis_panel()
            return

        if self._dyno_run_state == "Error":
            self.dyno_summary_detail_label.setText("Check the error dialog, then retry once the engine setup is valid.")
            self._refresh_analysis_panel()
            return

        self.dyno_summary_detail_label.setText("Run a dyno sweep to populate peak values and exportable results.")
        self._refresh_analysis_panel()

    def _refresh_analysis_panel(self) -> None:
        if not hasattr(self, "analysis_context_label"):
            return

        project_name = self._quick_dyno_project_name()
        engine_name = self._quick_dyno_engine_name()
        mode_label = self._analysis_mode_label()
        sweep_text = self._quick_dyno_sweep_text()
        row_count = self.analysis_table.rowCount()

        def _context_line(items: list[tuple[str, str]]) -> str:
            return " <span style='color: #90a0b3;'>&bull;</span> ".join(
                (
                    "<span style='color: #5f6b7a; font-weight: 700;'>"
                    f"{html.escape(label)}:</span> "
                    f"<span style='color: #18212f;'>{html.escape(value)}</span>"
                )
                for label, value in items
            )

        if self.dyno_thread and self.dyno_thread.isRunning():
            result_context = "Current quick dyno run"
        elif self.last_dyno_payload is not None and mode_label.startswith("v1"):
            result_context = "Current analysis result"
        elif self.last_dyno_payload is not None:
            result_context = "Analysis table is not tied to the current v2 result"
        elif self._dyno_run_state == "Cancelled":
            result_context = "No stored analysis result"
        elif self._dyno_run_state == "Error":
            result_context = "Analysis unavailable after failed run"
        else:
            result_context = "Awaiting a quick dyno result"

        context_html = (
            _context_line([("Project", project_name), ("Engine", engine_name), ("Solver", mode_label)])
            + "<br>"
            + _context_line([("Sweep", sweep_text), ("Points", str(row_count)), ("Result", result_context)])
        )
        self.analysis_context_label.setText(context_html)

        self.analysis_summary_label.setText(
            self._overview_inline_summary_html(
                "Run status",
                [
                    ("Status", self._quick_dyno_status_value()),
                    ("Last run", self._quick_dyno_last_run_value()),
                    ("Result", self._quick_dyno_result_status_value()),
                ],
            )
        )

        peak_power_ready = math.isfinite(self._dyno_max_hp_value) and self._dyno_max_hp_value > 0.0 and self._dyno_max_hp_rpm > 0
        peak_torque_ready = math.isfinite(self._dyno_max_tq_value) and self._dyno_max_tq_value > 0.0 and self._dyno_max_tq_rpm > 0
        self.analysis_peak_power_value_label.setText(f"{self._dyno_max_hp_value:.1f} hp" if peak_power_ready else "-")
        self.analysis_peak_power_rpm_label.setText(f"at {self._dyno_max_hp_rpm:.0f} rpm" if peak_power_ready else "No peak recorded yet")
        self.analysis_peak_torque_value_label.setText(f"{self._dyno_max_tq_value:.1f} Nm" if peak_torque_ready else "-")
        self.analysis_peak_torque_rpm_label.setText(f"at {self._dyno_max_tq_rpm:.0f} rpm" if peak_torque_ready else "No peak recorded yet")

        if self.dyno_thread and self.dyno_thread.isRunning():
            self.analysis_detail_label.setText(
                f"{row_count} point(s) collected so far."
            )
        elif self.last_dyno_payload is not None and mode_label.startswith("v2"):
            self.analysis_detail_label.setText(
                "v2 result active. This table remains a v1-oriented cycle-detail view."
            )
        elif self.last_dyno_payload is not None and row_count:
            self.analysis_detail_label.setText(
                f"{row_count} point(s) ready for detailed review."
            )
        elif self._dyno_run_state == "Cancelled":
            self.analysis_detail_label.setText("Dyno cancelled. No current analysis result is stored.")
        elif self._dyno_run_state == "Error":
            self.analysis_detail_label.setText("Dyno failed. Rerun to populate the analysis view.")
        else:
            self.analysis_detail_label.setText("Run a dyno sweep to populate the analysis view.")

        if self._dyno_knock_detected:
            self.analysis_knock_notice_label.setText(
                "Knock warning detected in the current analysis result. Review octane, compression, or timing before trusting the upper-load trend."
            )
            self.analysis_knock_notice_label.setVisible(True)
        else:
            self.analysis_knock_notice_label.clear()
            self.analysis_knock_notice_label.setVisible(False)

    def update_overview(self) -> None:
        if not hasattr(self, "overview_browser"):
            return

        self._refresh_quick_dyno_panel()

        project_name = "Unsaved Project"
        if self.current_project_path:
            project_name = Path(self.current_project_path).name

        block = self.engine.block
        head = self.engine.head
        cam = self.engine.camshaft
        intake = self.engine.intake
        exhaust = self.engine.exhaust
        fuel = getattr(self.engine, "fuel", None)
        combustion = getattr(self.engine, "combustion", None)
        friction = getattr(self.engine, "friction", None)

        displacement_cc = block.displacement_cc
        displacement_l = displacement_cc / 1000.0
        bore = block.bore
        stroke = block.stroke
        rod = block.conrod_length
        redline = block.redline_rpm
        mean_piston_speed = 2.0 * (stroke * 1e-3) * redline / 60.0

        try:
            geo_cr = self.engine.calculate_geometric_cr()
        except Exception:
            geo_cr = head.compression_ratio

        architecture = self._engine_architecture_label(block)
        induction = self.engine.induction_summary()
        self.overview_title_label.setText(project_name)
        self.overview_subtitle_label.setText(f"{architecture}  |  {displacement_l:.2f} L  |  {induction}")
        self.overview_context_label.setText(
            self._overview_inline_summary_html(
                "Technical baseline",
                [
                    ("Redline", f"{redline:.0f} rpm"),
                    ("CR", f"{geo_cr:.2f}:1"),
                    ("Cam peak", f"{cam.peak_rpm:.0f} rpm"),
                    ("Port flow", f"{head.port_flow_cfm:.1f} cfm"),
                ],
            )
        )
        self.overview_status_label.setText(
            self._overview_inline_summary_html(
                "Project state",
                [
                    ("Dataset", self._overview_dataset_status()),
                    ("Last dyno", self._overview_last_dyno_status()),
                    ("Reports", self._overview_report_status()),
                    ("Calibration", self._overview_calibration_status()),
                ],
            )
        )
        self.overview_guidance_label.setText(
            "Next: run a dyno baseline, then adjust properties or move into Real Dyno when measured data is available."
        )

        cards = [
            (
                "Short Block",
                [
                    ("Architecture", architecture),
                    ("Displacement", f"{displacement_cc:.1f} cc ({displacement_l:.2f} L)"),
                    ("Bore x Stroke", f"{bore:.1f} x {stroke:.1f} mm"),
                    ("Rod Length", f"{rod:.1f} mm"),
                    ("Redline", f"{redline:.0f} rpm"),
                    ("Mean Piston Speed", f"{mean_piston_speed:.2f} m/s"),
                ],
            ),
            (
                "Cylinder Head",
                [
                    ("Geometric CR", f"{geo_cr:.2f}:1"),
                    ("Intake Valve", f"{head.intake_valve_diameter:.1f} mm"),
                    ("Exhaust Valve", f"{head.exhaust_valve_diameter:.1f} mm"),
                    ("Port Flow", f"{head.port_flow_cfm:.1f} cfm"),
                    ("Flow Efficiency", f"{head.port_flow_efficiency:.2f}"),
                    ("Mach Tolerance", f"{head.mach_tolerance:.2f}"),
                ],
            ),
            (
                "Camshaft",
                [
                    ("Intake Duration", f"{cam.intake_duration:.1f} deg"),
                    ("Exhaust Duration", f"{cam.exhaust_duration:.1f} deg"),
                    ("Lifts", f"{cam.intake_lift:.2f} / {cam.exhaust_lift:.2f} mm"),
                    ("LSA", f"{cam.lobe_separation:.1f} deg"),
                    ("Advance", f"{cam.advance:.1f} deg"),
                    ("Peak RPM", f"{cam.peak_rpm:.0f} rpm"),
                ],
            ),
            (
                "Induction",
                [
                    ("Mode", induction),
                    ("Runner", f"{intake.runner_length:.1f} mm x {intake.runner_diameter:.1f} mm"),
                    ("Plenum", f"{intake.plenum_volume:.2f} L"),
                    ("Throttle", f"{intake.throttle_body_dia:.1f} mm"),
                    ("Throttle Flow", f"{intake.throttle_cfm:.1f} cfm"),
                ],
            ),
            (
                "Exhaust",
                [
                    ("Primary", f"{exhaust.header_primary_length:.1f} mm x {exhaust.header_primary_diameter:.1f} mm"),
                    ("Collector Length", f"{exhaust.collector_length:.1f} mm"),
                ],
            ),
        ]

        if fuel:
            cards.append(
                (
                    "Fuel",
                    [
                        ("Type", fuel.type_name),
                        ("Octane", f"{fuel.octane_rating:.1f}"),
                        ("Energy Density", f"{fuel.energy_density / 1e6:.2f} MJ/kg"),
                        ("Stoich AFR", f"{fuel.stoich_afr:.2f}"),
                    ],
                )
            )

        if combustion:
            cards.append(
                (
                    "Combustion",
                    [
                        ("Thermal Efficiency", f"{combustion.thermal_efficiency:.2f}"),
                        ("Burn Duration", f"{combustion.burn_duration:.1f} deg"),
                        ("Ignition Advance", f"{combustion.ignition_advance:.1f} deg BTDC"),
                        ("AFR", f"{combustion.afr:.2f}"),
                    ],
                )
            )

        if friction:
            cards.append(
                (
                    "Mechanical Losses",
                    [
                        ("Base FMEP", f"{friction.friction_base_kpa:.1f} kPa"),
                    ],
                )
            )

        grid_rows = []
        for idx in range(0, len(cards), 2):
            left_card = self._overview_card_html(*cards[idx])
            right_card = ""
            if idx + 1 < len(cards):
                right_card = self._overview_card_html(*cards[idx + 1])
            grid_rows.append(
                "<tr>"
                f"<td width='50%' valign='top'>{left_card}</td>"
                f"<td width='50%' valign='top'>{right_card}</td>"
                "</tr>"
            )

        overview_html = f"""
        <html>
        <head>
        <style>
            body {{
                font-family: 'Segoe UI';
                color: #1a2433;
                background: #f7f9fc;
                margin: 0;
            }}
            .summary-shell {{
                background: #ffffff;
                border: 1px solid #d6dde8;
                border-radius: 12px;
                padding: 14px;
            }}
            .summary-header {{
                margin: 0 0 10px 0;
            }}
            .summary-kicker {{
                color: #1f5ea8;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.08em;
                text-transform: uppercase;
            }}
            .summary-note {{
                color: #506072;
                font-size: 12px;
                margin-top: 4px;
            }}
            table.grid {{
                border-collapse: separate;
                border-spacing: 10px;
            }}
            table.card {{
                background: #fbfcfe;
                border: 1px solid #d6dde8;
                border-radius: 10px;
            }}
            .card-title {{
                font-size: 15px;
                font-weight: 700;
                color: #18212f;
                padding: 12px 14px 4px 14px;
            }}
            table.kv {{
                padding: 2px 14px 12px 14px;
            }}
            td.label {{
                width: 42%;
                color: #506072;
                font-size: 12px;
                padding: 3px 0;
            }}
            td.value {{
                color: #18212f;
                font-size: 12px;
                font-weight: 600;
                padding: 3px 0 3px 12px;
            }}
            .summary-title {{
                color: #314154;
                font-weight: 700;
            }}
            .summary-label {{
                color: #506072;
            }}
            .summary-value {{
                color: #18212f;
                font-weight: 600;
            }}
            .summary-sep {{
                color: #90a0b3;
            }}
        </style>
        </head>
        <body>
            <div class="summary-shell">
                <div class="summary-header">
                    <div class="summary-kicker">Technical overview</div>
                    <div class="summary-note">Grouped by subsystem for a faster read before dyno, calibration, or fabrication work.</div>
                </div>
                <table class="grid" width="100%" cellspacing="0" cellpadding="0">
                    {"".join(grid_rows)}
                </table>
            </div>
        </body>
        </html>
        """
        self.overview_browser.setHtml(overview_html)

    def _open_compression_dialog(self, head: CylinderHead, cr_spin: QDoubleSpinBox) -> None:
        dialog = CompressionDialog(self.engine, head, cr_spin, self)
        dialog.exec()

    # -------------------------- File IO -----------------------------------
    def save_engine(self) -> None:
        if self.current_project_path:
            self._save_engine_to_path(self.current_project_path)
            return
        self.save_engine_as()

    def save_engine_as(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(self, "Save Engine As", "engine.json", "JSON Files (*.json)")
        if filename:
            self._save_engine_to_path(filename)

    def _save_engine_to_path(self, filename: str) -> None:
        try:
            self.engine.validate(strict=True)
        except ValueError as exc:
            message = f"Cannot save engine: {exc}"
            self.statusBar().showMessage(message, 4000)
            QMessageBox.critical(self, "Validation Error", message)
            return
        self.engine.save_to_file(filename)
        self.current_project_path = filename
        self._update_window_title()
        self.update_overview()
        if self.real_dyno_widget is not None:
            self.real_dyno_widget.refresh_base_engine_label()
        self.statusBar().showMessage("Engine saved.", 2000)

    def launch_guided_engine_wizard(self) -> None:
        dialog = GuidedEngineWizardDialog(self)
        if dialog.exec() != QDialog.Accepted or dialog.generated_engine is None:
            return
        self.engine = dialog.generated_engine
        self.current_project_path = None
        self.audio_synth = AudioSynthesizer()
        self.timer.stop()
        self.refresh_tree()
        self.update_properties_panel(self.navigation_tree.currentItem())
        self._update_window_title()
        self.update_overview()
        if self.real_dyno_widget is not None:
            self.real_dyno_widget.refresh_base_engine_label()
        self.main_stack.setCurrentIndex(0)
        self.tabs.setCurrentIndex(0)
        self.statusBar().showMessage("Guided engine preset generated.", 3000)

    def _show_preflight_issues(self, operation: str, mode: str = "v1") -> bool:
        review = self.engine.preflight_review(operation=operation, mode=mode)
        if review["errors"]:
            issue_text = "\n".join(f"- {issue}" for issue in review["errors"])
            QMessageBox.critical(
                self,
                "Preflight validation failed",
                f"Cannot run {operation} until the configuration is corrected:\n{issue_text}",
            )
            self.statusBar().showMessage(f"{operation} blocked by preflight validation.", 4000)
            return False
        if review["warnings"]:
            warning_text = "\n".join(f"- {issue}" for issue in review["warnings"])
            QMessageBox.warning(
                self,
                "Preflight warnings",
                f"{operation} can run, but the configuration should be reviewed:\n{warning_text}",
            )
            self.statusBar().showMessage(f"{operation} started with preflight warnings.", 4000)
            return True
        return True

    def _try_load_default_preset(self) -> None:
        """Attempt to load honda_k20.json as default engine on startup."""
        default = Path(__file__).resolve().parent.parent / "presets" / "honda_k20.json"
        if not default.exists():
            return
        try:
            with open(default, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.engine = Engine.from_dict(data)
            self.current_project_path = str(default)
            if self.real_dyno_widget is not None:
                self.real_dyno_widget.refresh_base_engine_label()
        except Exception:
            logging.getLogger(__name__).debug(
                "Failed to load default preset, using empty engine", exc_info=True
            )

    def load_project(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Load Engine", "", "JSON Files (*.json)")
        if filename:
            with open(filename, "r") as f:
                data = json.load(f)

            self.engine = Engine.from_dict(data)
            issues = self.engine.validate_with_issues()
            self.wave_solver = None
            self.audio_synth = AudioSynthesizer()
            self.timer.stop()
            self.refresh_tree()
            self.update_properties_panel(None)
            self.current_project_path = filename
            self._update_window_title()
            self.update_overview()
            if self.real_dyno_widget is not None:
                self.real_dyno_widget.refresh_base_engine_label()
            self.main_stack.setCurrentIndex(0)
            self.tabs.setCurrentIndex(0)
            if issues:
                issue_text = "\n".join(f"- {issue}" for issue in issues)
                QMessageBox.warning(
                    self,
                    "Validation Warnings",
                    f"Engine loaded with validation warnings:\n{issue_text}",
                )
                self.statusBar().showMessage("Loaded engine with validation warnings.", 4000)

    # Backwards compatibility with older action wiring
    def load_engine(self) -> None:  # pragma: no cover - retained for older menu hookups
        self.load_project()

    def save_wav_audio(self) -> None:
        waveform = self.audio_synth.render_waveform()
        if waveform is None:
            return

        firing_order = self.engine.block.firing_order or list(
            range(1, self.engine.block.num_cylinders + 1)
        )
        target_rpm = max(float(self.wave_rpm_spin.value()), 1000.0)
        mixed = generate_full_engine_sound(
            waveform,
            target_rpm,
            firing_order,
            self.audio_synth.sample_rate,
        )
        if mixed.size == 0:
            return

        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Exhaust Audio", "engine.wav", "WAV Files (*.wav)"
        )
        if filename:
            self.audio_synth.save_waveform(mixed, filename)
            self.statusBar().showMessage("Audio saved!", 2000)

    # Retained for wiring compatibility with wave scope controls
    def save_wave_audio(self) -> None:  # pragma: no cover - thin wrapper
        self.save_wav_audio()

    # -------------------------- Wave Simulation --------------------------
    def _init_wave_solver(self) -> None:
        exhaust = self.engine.exhaust
        block = self.engine.block

        n_cyl = max(block.num_cylinders, 1)
        primary_length = max(exhaust.header_primary_length * 0.001, 0.1)
        primary_dia = max(exhaust.header_primary_diameter * 0.001, 0.005)

        primaries: list[Pipe] = []
        for _ in range(n_cyl):
            primaries.append(
                Pipe(
                    length=primary_length,
                    diameter_inlet=primary_dia,
                    diameter_outlet=primary_dia,
                    wall_temperature=600.0,
                    friction_coeff=0.02,
                )
            )

        collector_area = math.pi * (primary_dia * 0.5) ** 2
        collector_volume = max(collector_area * 0.1 * n_cyl, 1e-4)
        collector = Junction(collector_volume, 101325.0, 600.0)

        tail_length = max(exhaust.collector_length * 0.001, 0.2)
        tail_dia = max(primary_dia * max(math.sqrt(n_cyl) * 0.6, 1.2), primary_dia * 1.2)
        tailpipe = Pipe(
            length=tail_length,
            diameter_inlet=tail_dia,
            diameter_outlet=tail_dia,
            wall_temperature=600.0,
            friction_coeff=0.02,
        )

        self.wave_solver = Engine1DSolver(
            primaries,
            tailpipe,
            block.firing_order,
            collector_volume=collector.volume,
            settings=self.engine.simulation_settings,
            camshaft=self.engine.camshaft,
            head=self.engine.head,
        )
        self.audio_synth = AudioSynthesizer()
        self.wave_history = []
        self.wave_time_vector = []

    def run_wave_calculation(self) -> None:
        if not self._show_preflight_issues("scope", mode="v1"):
            return
        if self.wave_solver is None:
            self._init_wave_solver()
        if self.wave_solver is None:
            return

        rpm = float(self.wave_rpm_spin.value())
        record_audio = self.wave_record_btn.isChecked()
        self.audio_synth = AudioSynthesizer()
        history, audio_pressures, time_vector = self.wave_solver.run_full_simulation(
            rpm, cycles=2
        )
        self.wave_history = history
        self.wave_time_vector = time_vector
        self.wave_matrix = None
        self.wave_x_axis = None

        if record_audio:
            for t, p in zip(time_vector, audio_pressures):
                self.audio_synth.add_sample(t, p)
            self.wave_save_btn.setEnabled(len(audio_pressures) > 0)
        else:
            self.wave_save_btn.setEnabled(False)

        if self.wave_history:
            self.wave_matrix = compute_pressure_matrix(
                self.wave_history, self.wave_solver.gamma
            )

            levels = compute_image_levels(self.wave_matrix)
            self.wave_image.setImage(self.wave_matrix.T, levels=levels)
            total_degrees = float(self.wave_matrix.shape[0])

            primary_length = (
                self.wave_solver.primary_states[0]["dx"]
                * self.wave_solver.primary_states[0]["U"].shape[0]
            )
            self.wave_x_axis = np.arange(self.wave_matrix.shape[1]) * (
                self.wave_solver.primary_states[0]["dx"]
            )
            self.wave_image.setRect(QRectF(0.0, 0.0, primary_length, total_degrees))
            self.wave_plot.setYRange(0.0, total_degrees)
            self.wave_plot.setXRange(0.0, primary_length)

            self.wave_scrub_slider.setEnabled(True)
            self.wave_scrub_slider.setRange(0, self.wave_matrix.shape[0] - 1)
            self.wave_scrub_slider.setValue(0)
            self.update_wave_plot(0)
            self.statusBar().showMessage("Wave simulation calculated", 2000)
        else:
            self.wave_scrub_slider.setEnabled(False)
            self.wave_image.clear()
            self.wave_scope.update_data([], [])
            self.wave_scope.update_status(0.0, "N/A", 0.0)

    def update_wave_plot(self, index: int) -> None:
        if self.wave_matrix is None or self.wave_matrix.size == 0:
            return
        idx = max(0, min(int(index), self.wave_matrix.shape[0] - 1))
        rpm = float(self.wave_rpm_spin.value())
        angle = (self.wave_time_vector[idx] * rpm * 6.0) % 720.0
        if self.wave_frame_indicator is not None:
            self.wave_frame_indicator.setPos(float(idx))
        if self.wave_x_axis is not None:
            self.wave_scope.update_data(self.wave_x_axis, self.wave_matrix[idx])
            sim_time = self.wave_time_vector[idx] if idx < len(self.wave_time_vector) else 0.0
            self.wave_scope.update_status(angle, "N/A", sim_time)
        self.statusBar().showMessage(
            f"Angle {angle:5.1f} deg | Frame {idx+1}/{self.wave_matrix.shape[0]}", 1500
        )

    # -------------------------- Dyno Sweep --------------------------------
    def _dyno_mode(self) -> str:
        mode = self.dyno_mode_combo.currentData()
        return str(mode) if mode in ("v1", "v2") else "v1"

    def _dyno_quality(self) -> str:
        quality = self.dyno_quality_combo.currentData()
        return str(quality) if quality in ("fast", "stable") else "fast"

    def _dyno_v2_settings(self) -> dict[str, Any]:
        if self._dyno_quality() == "stable":
            return {
                "settle_cycles": 1,
                "min_periodicity": 0.35,
                "drop_invalid": True,
                "rpm_start_safe": True,
                "report_status": True,
            }
        return {}

    def _dyno_results_from_cycles(self, rpm_values: list[int], cycles: list[dict[str, Any]]) -> list[dict[str, float]]:
        results: list[dict[str, float]] = []
        for rpm, cycle in zip(rpm_values, cycles):
            entry = {
                "rpm": float(rpm),
                "mean_power_hp": float(cycle["mean_power_hp"]),
                "mean_torque_nm": float(cycle["mean_torque_nm"]),
                "bmep_bar": float(cycle["bmep_bar"]),
                "ve_actual": float(cycle["ve_actual"]),
            }
            for key in (
                "map_est_kpa",
                "overlap_flow_kg",
                "residual_fraction_est",
                "scavenging_index",
                "boost_kpa",
                "pr_comp",
                "pr_turb",
                "wg_duty",
            ):
                if key in cycle:
                    entry[key] = float(cycle[key])
            results.append(entry)
        return results

    def _dyno_results_from_sweep(self, rpm_values: list[int], sweep: dict[str, list[float]]) -> list[dict[str, float]]:
        displacement_m3 = max(cc_to_m3(self.engine.block.displacement_cc), 1e-9)
        results: list[dict[str, float]] = []
        status_series = sweep.get("status")
        periodicity_series = sweep.get("periodicity_error")
        reason_series = sweep.get("reason")
        for idx, rpm in enumerate(rpm_values):
            mean_power_hp = float(sweep["mean_power_hp"][idx])
            mean_torque_nm = float(sweep["mean_torque_nm"][idx])
            bmep_bar = mean_torque_nm * 4.0 * math.pi / displacement_m3 / 100000.0
            ve_actual = float(sweep["ve_real"][idx])
            entry: dict[str, Any] = {
                "rpm": float(rpm),
                "mean_power_hp": mean_power_hp,
                "mean_torque_nm": mean_torque_nm,
                "bmep_bar": float(bmep_bar),
                "ve_actual": ve_actual,
            }
            if status_series is not None and idx < len(status_series):
                entry["status"] = status_series[idx]
            if periodicity_series is not None and idx < len(periodicity_series):
                entry["periodicity_error"] = periodicity_series[idx]
            if reason_series is not None and idx < len(reason_series):
                entry["reason"] = reason_series[idx]
            results.append(entry)
        return results

    def _build_dyno_payload(self, mode: str, results: list[dict[str, float]]) -> dict[str, Any]:
        raw = self.engine.to_dict()
        coupling_mode = "v2_orchestrator" if mode == "v2" else "none"
        payload = {
            "metadata": cli_metadata(self.engine, raw, coupling_mode=coupling_mode),
            "results": results,
        }
        return apply_observable_semantics(payload, OBSERVABLE_VE_ACTUAL)

    def _build_knock_report_payload(self, rpm_values: list[int], mode: str) -> dict[str, Any]:
        residual_cfg = getattr(self.engine.combustion, "residual_coupling", {}) or {}
        if not bool(residual_cfg.get("enabled", False)):
            raise ValueError("combustion.residual_coupling.enabled must be true for knock reports")

        knock_cfg = residual_cfg.get("knock", {})
        if not isinstance(knock_cfg, dict):
            knock_cfg = {}

        simulator = CylinderSimulator(self.engine)
        results: list[dict[str, Any]] = []
        for rpm in rpm_values:
            cycle = simulator.run_cycle(float(rpm))
            trace = cycle.get("trace", {})
            residual_fraction = float(trace.get("residual_fraction_est", 0.0))
            start_angle = float(trace.get("start_angle_used", 360.0 - self.engine.combustion.ignition_advance))
            entry = compute_knock_index(
                cycle["angle"],
                cycle["temperature"],
                float(rpm),
                start_angle,
                residual_fraction,
                config=knock_cfg,
            )
            entry["rpm"] = float(rpm)
            results.append(entry)

        coupling_mode = "v2_orchestrator" if mode == "v2" else "none"
        metadata = cli_metadata(self.engine, self.engine.to_dict(), coupling_mode=coupling_mode)
        knock_model = KnockConfig.from_dict(knock_cfg)
        metadata["knock_model"] = {
            "A": knock_model.A,
            "B": knock_model.B,
            "threshold": knock_model.threshold,
            "window_deg": knock_model.window_deg,
            "residual_hot_k": knock_model.residual_hot_k,
        }
        return {"metadata": metadata, "results": results}

    def run_dyno_sweep(self) -> None:
        if self.dyno_thread and self.dyno_thread.isRunning():
            return
        mode = self._dyno_mode()
        if not self._show_preflight_issues("dyno", mode=mode):
            return
        v2_settings = self._dyno_v2_settings() if mode == "v2" else {}
        max_rpm = int(self.engine.block.redline_rpm)
        rpm_values = list(range(1000, max_rpm + 500, 500))
        if not rpm_values:
            QMessageBox.information(self, "Dyno", "No RPM values available.")
            return

        self._dyno_mode_running = mode
        self._dyno_rpm_values = rpm_values
        self._dyno_power_hp = []
        self._dyno_torque_nm = []
        self._dyno_plot_rpms = []
        self._dyno_plot_power_hp = []
        self._dyno_plot_torque_nm = []
        self._dyno_invalid_rpms = []
        self._dyno_invalid_power_hp = []
        self._dyno_invalid_torque_nm = []
        self._dyno_results = []
        self._dyno_progress_count = 0
        self._dyno_point_count = 0
        self._dyno_max_hp_value = -float("inf")
        self._dyno_max_hp_rpm = 0
        self._dyno_max_tq_value = -float("inf")
        self._dyno_max_tq_rpm = 0
        self._dyno_knock_detected = False
        self._dyno_run_state = "Running"

        self.analysis_table.setRowCount(0)
        self.analysis_summary_label.setText("Running dyno...")
        self.dyno_plot.clear()
        self.dyno_plot.addLegend(clear=True)
        self.power_curve = self.dyno_plot.plot([], [], pen=pg.mkPen("r", width=2), name="Power (HP)", symbol="o")
        self.torque_curve = self.dyno_plot.plot([], [], pen=pg.mkPen("b", width=2), name="Torque (Nm)", symbol="o")
        self.invalid_power_curve = self.dyno_plot.plot(
            [],
            [],
            pen=None,
            symbol="x",
            symbolBrush=pg.mkBrush(150, 150, 150),
        )
        self.invalid_torque_curve = self.dyno_plot.plot(
            [],
            [],
            pen=None,
            symbol="x",
            symbolBrush=pg.mkBrush(120, 120, 120),
        )
        self.dyno_plot.setLabel("bottom", "RPM")
        self.dyno_plot.setLabel("left", "Power (HP) / Torque (Nm)")
        self.dyno_plot.setTitle("")

        self.last_dyno_payload = None
        self._set_dyno_ui_running(True)
        self._refresh_quick_dyno_panel()
        self.dyno_elapsed.restart()

        engine_data = self.engine.to_dict()
        self.dyno_worker = DynoWorker(engine_data, mode, rpm_values, v2_settings=v2_settings)
        self.dyno_thread = QThread(self)
        self.dyno_worker.moveToThread(self.dyno_thread)
        self.dyno_thread.started.connect(self.dyno_worker.run)
        self.dyno_worker.progress.connect(self._on_dyno_progress)
        self.dyno_worker.point.connect(self._on_dyno_point)
        self.dyno_worker.finished.connect(self._on_dyno_finished)
        self.dyno_worker.cancelled.connect(self._on_dyno_cancelled)
        self.dyno_worker.error.connect(self._on_dyno_error)
        self.dyno_thread.start()

    def cancel_dyno_sweep(self) -> None:
        if self.dyno_worker:
            self._dyno_run_state = "Cancelling"
            self.dyno_status_label.setText("Cancellation requested...")
            self._refresh_quick_dyno_panel()
            self.dyno_worker.request_cancel()

    def _set_dyno_ui_running(self, running: bool) -> None:
        self.dyno_run_btn.setEnabled(not running)
        self.dyno_export_btn.setEnabled(not running)
        self.dyno_knock_export_checkbox.setEnabled(not running)
        self.dyno_mode_combo.setEnabled(not running)
        self.dyno_quality_combo.setEnabled(not running)
        self.dyno_cancel_btn.setEnabled(running)
        self.dyno_cancel_btn.setVisible(running)
        self.dyno_progress.setVisible(running)
        if not running:
            self.dyno_progress.setValue(0)
            self.dyno_status_label.setText("")
        self._refresh_quick_dyno_panel()

    def _update_dyno_plot(self) -> None:
        if not self._dyno_rpm_values:
            return
        self.power_curve.setData(self._dyno_rpm_values[: len(self._dyno_power_hp)], self._dyno_power_hp)
        self.torque_curve.setData(self._dyno_rpm_values[: len(self._dyno_torque_nm)], self._dyno_torque_nm)
        if self.invalid_power_curve is not None:
            self.invalid_power_curve.setData(self._dyno_invalid_rpms, self._dyno_invalid_power_hp)
        if self.invalid_torque_curve is not None:
            self.invalid_torque_curve.setData(self._dyno_invalid_rpms, self._dyno_invalid_torque_nm)
        if len(self._dyno_rpm_values) >= 2:
            self.dyno_plot.setXRange(min(self._dyno_rpm_values), max(self._dyno_rpm_values), padding=0.05)

    def _on_dyno_progress(self, percent: int, msg: str) -> None:
        self._dyno_progress_count += 1
        elapsed_ms = self.dyno_elapsed.elapsed()
        self.dyno_progress.setValue(percent)
        compact_msg = msg.replace(": RPM ", " RPM ").replace(" | ", " · ")
        self.dyno_status_label.setText(f"{compact_msg} · {elapsed_ms / 1000.0:.1f} s")
        self._refresh_quick_dyno_panel()

    def _on_dyno_point(self, payload: dict[str, Any]) -> None:
        self._dyno_point_count += 1
        entry: dict[str, Any] = {}
        for key, value in payload.items():
            if isinstance(value, (int, float)):
                entry[key] = float(value)
            elif isinstance(value, str):
                entry[key] = value
        dropped = bool(payload.get("dropped", False))
        status = str(payload.get("status", "ok"))
        if not dropped:
            self._dyno_results.append(entry)

        rpm_val = float(payload.get("rpm", 0.0))
        power_val = float(payload.get("mean_power_hp", 0.0))
        torque_val = float(payload.get("mean_torque_nm", 0.0))
        if status != "ok":
            self._dyno_power_hp.append(float("nan"))
            self._dyno_torque_nm.append(float("nan"))
            self._dyno_invalid_rpms.append(int(rpm_val))
            self._dyno_invalid_power_hp.append(power_val)
            self._dyno_invalid_torque_nm.append(torque_val)
        else:
            self._dyno_power_hp.append(power_val)
            self._dyno_torque_nm.append(torque_val)
        self._update_dyno_plot()

        cycle = payload.get("cycle")
        if cycle is not None:
            rpm = float(payload.get("rpm", 0.0))
            hp_val = float(cycle.get("mean_power_hp", 0.0))
            torque_val = float(cycle.get("mean_torque_nm", 0.0))
            if hp_val > self._dyno_max_hp_value:
                self._dyno_max_hp_value = hp_val
                self._dyno_max_hp_rpm = int(rpm)
            if torque_val > self._dyno_max_tq_value:
                self._dyno_max_tq_value = torque_val
                self._dyno_max_tq_rpm = int(rpm)
            knock_present = self.update_analysis_table(rpm, cycle)
            self._dyno_knock_detected = self._dyno_knock_detected or knock_present
        elif status == "ok":
            if power_val > self._dyno_max_hp_value:
                self._dyno_max_hp_value = power_val
                self._dyno_max_hp_rpm = int(rpm_val)
            if torque_val > self._dyno_max_tq_value:
                self._dyno_max_tq_value = torque_val
                self._dyno_max_tq_rpm = int(rpm_val)
        self._refresh_quick_dyno_panel()

    def _on_dyno_finished(self, payload: dict[str, Any]) -> None:
        mode = payload.get("mode", "v1")
        results = payload.get("results", [])
        self.last_dyno_payload = self._build_dyno_payload(mode, results)
        self._dyno_run_state = "Completed"

        if mode == "v1" and results:
            summary = (
                f"🏆 Max Power: {self._dyno_max_hp_value:.1f} HP @ {self._dyno_max_hp_rpm} RPM | "
                f"🚀 Max Torque: {self._dyno_max_tq_value:.1f} Nm @ {self._dyno_max_tq_rpm} RPM"
            )
            warning_html = ""
            if self._dyno_knock_detected:
                warning_html = (
                    "<br><span style='color:red; font-weight:bold;'>WARNING: ENGINE KNOCK DETECTED - Low Octane for this Compression</span>"
                )
                self.statusBar().showMessage(
                    "WARNING: ENGINE KNOCK DETECTED - Low Octane for this Compression", 5000
                )
            else:
                self.statusBar().clearMessage()
            self.analysis_summary_label.setText(summary + warning_html)
        else:
            self.analysis_summary_label.setText("Pro Dyno mode selected (analysis table uses v1 data).")

        self._set_dyno_ui_running(False)
        self._cleanup_dyno_thread()
        self._refresh_quick_dyno_panel()

    def _on_dyno_cancelled(self) -> None:
        self.last_dyno_payload = None
        self._dyno_run_state = "Cancelled"
        self.analysis_summary_label.setText("Dyno cancelled.")
        self._set_dyno_ui_running(False)
        self._cleanup_dyno_thread()
        self._refresh_quick_dyno_panel()

    def _on_dyno_error(self, message: str) -> None:
        self.last_dyno_payload = None
        self._dyno_run_state = "Error"
        self._set_dyno_ui_running(False)
        self._cleanup_dyno_thread()
        self._refresh_quick_dyno_panel()
        QMessageBox.critical(self, "Dyno error", message)

    def _cleanup_dyno_thread(self) -> None:
        if self.dyno_thread:
            self.dyno_thread.quit()
            self.dyno_thread.wait()
        if self.dyno_worker:
            self.dyno_worker.deleteLater()
        if self.dyno_thread:
            self.dyno_thread.deleteLater()
        self.dyno_worker = None
        self.dyno_thread = None

    def export_dyno_json(self) -> None:
        if not self.last_dyno_payload:
            QMessageBox.information(self, "Export Dyno JSON", "Run a dyno sweep first.")
            return

        knock_path = None
        if self.dyno_knock_export_checkbox.isChecked():
            residual_cfg = getattr(self.engine.combustion, "residual_coupling", {}) or {}
            if not bool(residual_cfg.get("enabled", False)):
                QMessageBox.critical(
                    self,
                    "Knock report unavailable",
                    "Enable combustion.residual_coupling before exporting a knock report.",
                )
                return
            knock_path, _ = QFileDialog.getSaveFileName(
                self, "Export Knock Report", "knock_report.json", "JSON Files (*.json)"
            )
            if not knock_path:
                return

        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Dyno JSON", "dyno.json", "JSON Files (*.json)"
        )
        if not filename:
            return

        payload = self.last_dyno_payload
        try:
            try:
                import jsonschema
            except Exception:
                jsonschema = None
            if jsonschema is not None:
                schema_path = Path("schemas/dyno.schema.json")
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
                jsonschema.validate(instance=payload, schema=schema)
        except Exception as exc:
            QMessageBox.critical(self, "Schema validation failed", str(exc))
            return

        Path(filename).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.statusBar().showMessage(f"Dyno JSON exported to {filename}", 3000)

        if knock_path:
            try:
                report = self._build_knock_report_payload(self._dyno_rpm_values, self._dyno_mode_running or "v1")
                try:
                    import jsonschema
                except Exception:
                    jsonschema = None
                if jsonschema is not None:
                    schema_path = Path("schemas/knock_report.schema.json")
                    schema = json.loads(schema_path.read_text(encoding="utf-8"))
                    jsonschema.validate(instance=report, schema=schema)
            except Exception as exc:
                QMessageBox.critical(self, "Knock report failed", str(exc))
                return
            Path(knock_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
            self.statusBar().showMessage(f"Knock report exported to {knock_path}", 3000)

    def update_analysis_table(self, rpm: float, result: dict[str, float]) -> bool:
        row = self.analysis_table.rowCount()
        self.analysis_table.insertRow(row)

        knock = bool(result.get("knock_warning", False))
        row_data = [
            rpm,
            result.get("mean_torque_nm", 0.0),
            result.get("mean_power_hp", 0.0),
            result.get("bmep_bar", 0.0),
            result.get("ve_actual", 0.0) * 100.0,
            result.get("mean_piston_speed", 0.0),
            result.get("mach_index", 0.0),
            result.get("friction_hp", 0.0),
            result.get("airflow_cfm", 0.0),
            knock,
        ]

        for col, val in enumerate(row_data):
            if col == 9:
                text = "Warn" if knock else "Clear"
                item = QTableWidgetItem(text)
                color = QColor(184, 47, 47) if knock else QColor(95, 107, 122)
                item.setForeground(QBrush(color))
                if knock:
                    font = QFont(item.font())
                    font.setBold(True)
                    item.setFont(font)
            else:
                if isinstance(val, (int, float)):
                    if col == 0:
                        text = f"{val:.0f}"
                    elif col in {1, 2, 3, 4, 5, 7, 8}:
                        text = f"{val:.1f}"
                    else:
                        text = f"{val:.2f}"
                else:
                    text = str(val)
                item = QTableWidgetItem(text)
                if col in {0, 1, 2, 4}:
                    font = QFont(item.font())
                    font.setBold(True)
                    item.setFont(font)
                    item.setForeground(QBrush(QColor("#18212f")))
                else:
                    item.setForeground(QBrush(QColor("#5f6b7a")))
            item.setTextAlignment(Qt.AlignCenter)
            self.analysis_table.setItem(row, col, item)

        return knock

    # -------------------------- Fabrication Tab ---------------------------
    def update_fabrication_data(self) -> None:
        """Populate the fabrication table based on the current engine."""
        n_cyl = max(1, int(self.engine.block.num_cylinders))
        target_len = float(self.engine.exhaust.header_primary_length)
        diameter = float(self.engine.exhaust.header_primary_diameter)

        self.fabrication_table.blockSignals(True)
        self.fabrication_table.setRowCount(n_cyl)
        for i in range(n_cyl):
            cyl_item = QTableWidgetItem(str(i + 1))
            cyl_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.fabrication_table.setItem(i, 0, cyl_item)

            tgt_item = QTableWidgetItem(f"{target_len:.1f}")
            tgt_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.fabrication_table.setItem(i, 1, tgt_item)

            actual_item = QTableWidgetItem(f"{target_len:.1f}")
            self.fabrication_table.setItem(i, 2, actual_item)

            dia_item = QTableWidgetItem(f"{diameter:.1f}")
            dia_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.fabrication_table.setItem(i, 3, dia_item)

            bend_item = QTableWidgetItem("0°")
            self.fabrication_table.setItem(i, 4, bend_item)

            self._evaluate_fabrication_row(i)

        self.fabrication_table.blockSignals(False)

        inlet = diameter * math.sqrt(max(1, n_cyl))
        self.collector_inlet_label.setText(f"~{inlet:.1f} mm")
        self.tailpipe_length_label.setText(f"{self.engine.exhaust.collector_length:.1f} mm")

    def _on_fabrication_cell_changed(self, item: QTableWidgetItem) -> None:
        if item.column() in (1, 2):
            self._evaluate_fabrication_row(item.row())

    def _evaluate_fabrication_row(self, row: int) -> None:
        try:
            tgt = float(self.fabrication_table.item(row, 1).text())
            act = float(self.fabrication_table.item(row, 2).text())
        except Exception:
            return

        deviation = abs(act - tgt) / max(tgt, 1e-6)
        item = self.fabrication_table.item(row, 2)
        if deviation > 0.05:
            item.setBackground(QBrush(QColor(255, 200, 200)))
        else:
            item.setBackground(QBrush(Qt.white))

    def _generate_fabrication_report(self) -> None:
        rows = self.fabrication_table.rowCount()
        total_length_mm = 0.0
        diameter = self.engine.exhaust.header_primary_diameter
        for i in range(rows):
            try:
                total_length_mm += float(self.fabrication_table.item(i, 2).text())
            except Exception:
                continue

        total_m = total_length_mm / 1000.0
        report_lines = [
            f"You need approximately {total_m:.2f} meters of {diameter:.1f} mm tubing.",
            "Cut list:",
        ]
        for i in range(rows):
            try:
                act = float(self.fabrication_table.item(i, 2).text())
            except Exception:
                act = 0.0
            report_lines.append(f"- Cylinder {i+1}: {act:.1f} mm")

        QMessageBox.information(self, "Fabrication Report", "\n".join(report_lines))

    def run_pro_dyno_sweep(self) -> None:
        if not self._show_preflight_issues("dyno", mode="v2"):
            return
        max_rpm = int(self.engine.block.redline_rpm)
        rpm_values = list(range(1000, max_rpm + 500, 500))
        runner = ProDynoV2Runner(self.engine)
        results = runner.run_sweep(rpm_values)
        rpm_values = results.get("rpm", rpm_values)
        power_hp = results.get("mean_power_hp", [])
        torque_nm = results.get("mean_torque_nm", [])
        convergence_history = results.get("convergence_history", [])
        convergence_tol = results.get("convergence_tol")
        payload_results = self._dyno_results_from_sweep([int(v) for v in rpm_values], results)
        self.last_dyno_payload = self._build_dyno_payload("v2", payload_results)

        self.pro_dyno_plot.clear()
        self.pro_dyno_plot.addLegend(clear=True)
        self.pro_power_curve = self.pro_dyno_plot.plot(
            rpm_values, power_hp, pen=pg.mkPen("r", width=2), name="Power (HP)"
        )
        self.pro_torque_curve = self.pro_dyno_plot.plot(
            rpm_values, torque_nm, pen=pg.mkPen("b", width=2), name="Torque (Nm)"
        )
        self.pro_dyno_plot.setLabel("bottom", "RPM")
        self.pro_dyno_plot.setLabel("left", "Power (HP) / Torque (Nm)")
        if rpm_values:
            self.pro_dyno_plot.setXRange(min(rpm_values), max(rpm_values), padding=0.05)

        self.convergence_plot.clear()
        self.convergence_plot.addLegend(clear=True)
        if convergence_history:
            ks = [entry.get("k", idx) for idx, entry in enumerate(convergence_history)]
            err_mass = [entry.get("err_trapped_mass", 0.0) for entry in convergence_history]
            err_imep = [entry.get("err_imep", 0.0) for entry in convergence_history]
            err_period = [entry.get("err_periodicity_1d", 0.0) for entry in convergence_history]
            self.convergence_plot.plot(
                ks, err_mass, pen=pg.mkPen("c", width=2), name="Trapped Mass"
            )
            self.convergence_plot.plot(
                ks, err_imep, pen=pg.mkPen("m", width=2), name="IMEP"
            )
            self.convergence_plot.plot(
                ks, err_period, pen=pg.mkPen("y", width=2), name="1D Periodicity"
            )
            if convergence_tol is not None:
                tol_line = pg.InfiniteLine(
                    pos=float(convergence_tol),
                    angle=0,
                    pen=pg.mkPen(QColor(180, 180, 180), width=1, style=Qt.DashLine),
                )
                self.convergence_plot.addItem(tol_line)

    # -------------------------- Optimization -----------------------------
    def _parameter_mapping(self) -> dict[str, tuple[Any, str]]:
        return {
            "Camshaft: Intake Duration (deg)": (self.engine.camshaft, "intake_duration"),
            "Camshaft: Max Lift (mm)": (self.engine.camshaft, "both_lifts"),
            "Camshaft: Lobe Separation (deg)": (self.engine.camshaft, "lobe_separation"),
            "Camshaft: Advance (deg)": (self.engine.camshaft, "advance"),
            "Tuning: Ignition Timing (deg BTDC)": (
                self.engine.simulation_settings,
                "ignition_timing_btdc",
            ),
            "Intake: Runner Length (mm)": (self.engine.intake, "runner_length"),
            "Intake: Runner Diameter (mm)": (self.engine.intake, "runner_diameter"),
            "Intake: Throttle Flow (CFM)": (self.engine.intake, "throttle_cfm"),
            "Exhaust: Primary Length (mm)": (self.engine.exhaust, "header_primary_length"),
            "Exhaust: Primary Diameter (mm)": (self.engine.exhaust, "header_primary_diameter"),
            "Head: Compression Ratio": (self.engine.head, "compression_ratio"),
            "Head: Port Flow (CFM)": (self.engine.head, "port_flow_cfm"),
            "Turbo: Target Boost (kPa)": (
                self.engine.turbo,
                "target_boost_kpa",
            ),
            "Supercharger: Boost Pressure (Bar)": (
                self.engine.supercharger,
                "boost_pressure_bar",
            ),
        }

    def _compute_peak_hp(self) -> float:
        simulator = CylinderSimulator(self.engine)
        rpm_values = list(range(3000, 12001, 500))
        peak_hp = 0.0
        for rpm in rpm_values:
            result = simulator.run_cycle(rpm)
            peak_hp = max(peak_hp, result.get("mean_power_hp", 0.0))
        return peak_hp

    def run_optimization_sweep(self) -> None:
        if not self._show_preflight_issues("sweep", mode="v1"):
            return
        mapping = self._parameter_mapping()
        target = self.optimizer_param_combo.currentText()
        if target not in mapping:
            return

        obj, attr = mapping[target]
        if attr != "both_lifts" and not hasattr(obj, attr):
            return

        start = self.optimizer_start_spin.value()
        end = self.optimizer_end_spin.value()
        step = self.optimizer_step_spin.value()
        target_rpm = self.opt_rpm_spin.value()
        if step <= 0:
            return
        if attr == "both_lifts":
            original_value = (obj.intake_lift, obj.exhaust_lift)
        else:
            original_value = getattr(obj, attr)
        self.optimizer_progress.setValue(0)
        values: list[float] = []
        current = start
        while current <= end + 1e-9:
            values.append(current)
            current += step

        results: list[float] = []
        total = max(len(values), 1)
        for idx, val in enumerate(values):
            if attr == "both_lifts":
                obj.intake_lift = val
                obj.exhaust_lift = val
            else:
                setattr(obj, attr, val)
            simulator = CylinderSimulator(self.engine)
            result = simulator.run_cycle(target_rpm)
            results.append(result.get("mean_power_hp", 0.0))
            progress = int((idx + 1) / total * 100)
            self.optimizer_progress.setValue(progress)
            QApplication.processEvents()

        if attr == "both_lifts":
            obj.intake_lift, obj.exhaust_lift = original_value
        else:
            setattr(obj, attr, original_value)
        self.optimizer_progress.setValue(100)

        self.optimizer_plot.clear()
        unit_map = {
            "Camshaft: Intake Duration (deg)": "Degrees",
            "Camshaft: Max Lift (mm)": "mm",
            "Camshaft: Lobe Separation (deg)": "Degrees",
            "Camshaft: Advance (deg)": "Degrees",
            "Tuning: Ignition Timing (deg BTDC)": "Degrees",
            "Head: Compression Ratio": "Ratio",
            "Head: Port Flow (CFM)": "CFM",
            "Intake: Runner Length (mm)": "mm",
            "Intake: Runner Diameter (mm)": "mm",
            "Intake: Throttle Flow (CFM)": "CFM",
            "Exhaust: Primary Length (mm)": "mm",
            "Exhaust: Primary Diameter (mm)": "mm",
            "Turbo: Target Boost (kPa)": "kPa",
            "Supercharger: Boost Pressure (Bar)": "Bar",
        }
        x_label = unit_map.get(target, "Parameter Value")

        self.optimizer_plot.plot(values, results, pen=pg.mkPen("m", width=2), symbol="o", name="Peak HP")
        self.optimizer_plot.setLabel("bottom", f"{target} [{x_label}]")
        self.optimizer_plot.setLabel("left", "Peak HP")


class CompressionDialog(QDialog):
    """Compression ratio helper dialog using build measurements."""

    def __init__(
        self,
        engine: Engine,
        head: CylinderHead,
        cr_spin: QDoubleSpinBox,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.engine = engine
        self.head = head
        self.cr_spin = cr_spin
        self.setWindowTitle("Compression Calculator")

        form = QFormLayout()

        self.bore_spin = self._make_spin(engine.block.bore, 30.0, 150.0, 0.01, suffix=" mm")
        self.bore_spin.setEnabled(False)
        form.addRow("Bore", self.bore_spin)

        self.stroke_spin = self._make_spin(engine.block.stroke, 30.0, 150.0, 0.01, suffix=" mm")
        self.stroke_spin.setEnabled(False)
        form.addRow("Stroke", self.stroke_spin)

        chamber_init = head.combustion_chamber_vol if head.combustion_chamber_vol is not None else 40.0
        self.chamber_spin = self._make_spin(chamber_init, 10.0, 150.0, 0.01, suffix=" cc")
        form.addRow("Chamber Volume", self.chamber_spin)

        self.gasket_thickness_spin = self._make_spin(head.gasket_thickness_mm, 0.1, 5.0, 0.01, suffix=" mm")
        form.addRow("Gasket Thickness", self.gasket_thickness_spin)

        self.gasket_bore_spin = self._make_spin(head.gasket_bore_mm, 30.0, 150.0, 0.01, suffix=" mm")
        form.addRow("Gasket Bore", self.gasket_bore_spin)

        self.deck_clearance_spin = self._make_spin(head.deck_clearance_mm, -5.0, 5.0, 0.01, suffix=" mm")
        form.addRow("Deck Clearance", self.deck_clearance_spin)

        self.piston_dome_spin = self._make_spin(head.piston_dome_cc, -50.0, 50.0, 0.01, suffix=" cc")
        form.addRow("Piston Dome Volume", self.piston_dome_spin)

        self.result_label = QLabel()
        form.addRow("Result", self.result_label)

        btns = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Close)
        btns.accepted.connect(self._apply)
        btns.rejected.connect(self.reject)

        container = QVBoxLayout()
        container.addLayout(form)
        container.addWidget(btns)
        self.setLayout(container)

        for spin in (
            self.chamber_spin,
            self.gasket_thickness_spin,
            self.gasket_bore_spin,
            self.deck_clearance_spin,
            self.piston_dome_spin,
        ):
            spin.editingFinished.connect(self._update_result)

        self._update_result()

    def _make_spin(
        self, value: float, minimum: float, maximum: float, step: float, suffix: str = ""
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(3)
        spin.setSingleStep(step)
        spin.setValue(value)
        if suffix:
            spin.setSuffix(suffix)
        return spin

    def _compute_cr(self) -> float:
        bore_m = self.bore_spin.value() * 1e-3
        stroke_m = self.stroke_spin.value() * 1e-3
        area_bore = math.pi * bore_m * bore_m / 4.0
        swept_cc = area_bore * stroke_m * 1e6

        gasket_bore_m = self.gasket_bore_spin.value() * 1e-3
        gasket_thick_m = self.gasket_thickness_spin.value() * 1e-3
        deck_clear_m = self.deck_clearance_spin.value() * 1e-3

        gasket_cc = math.pi * gasket_bore_m * gasket_bore_m / 4.0 * gasket_thick_m * 1e6
        deck_cc = math.pi * bore_m * bore_m / 4.0 * deck_clear_m * 1e6
        chamber_cc = self.chamber_spin.value()
        dome_cc = self.piston_dome_spin.value()

        total_clearance_cc = chamber_cc + gasket_cc + deck_cc - dome_cc
        if total_clearance_cc <= 1e-6:
            total_clearance_cc = 1e-6

        cr = (swept_cc + total_clearance_cc) / total_clearance_cc
        return cr

    def _update_result(self) -> None:
        cr = self._compute_cr()
        self.result_label.setText(f"{cr:.2f} : 1")

    def _apply(self) -> None:
        cr = self._compute_cr()
        self.head.compression_ratio = cr
        self.head.combustion_chamber_vol = self.chamber_spin.value()
        self.head.gasket_thickness_mm = self.gasket_thickness_spin.value()
        self.head.gasket_bore_mm = self.gasket_bore_spin.value()
        self.head.deck_clearance_mm = self.deck_clearance_spin.value()
        self.head.piston_dome_cc = self.piston_dome_spin.value()
        self.cr_spin.setValue(cr)
        if isinstance(self.parent(), MainWindow):
            self.parent().update_overview()
        self.accept()


def main() -> None:
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
