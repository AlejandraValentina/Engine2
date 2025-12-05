from __future__ import annotations

import json
import math
from typing import Any, Optional

import numpy as np

import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer, QRectF
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
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QCheckBox,
    QProgressBar,
    QTextBrowser,
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
)
from core.junctions import Junction
from core.model import Pipe
from core.simulator import Engine1DSolver
from core.thermo import CylinderSimulator
from core.wave_utils import compute_image_levels, compute_pressure_matrix
from gui.widgets.scope_widget import ScopeWidget


class MainWindow(QMainWindow):
    """Main GUI window binding engine data, editing, and dyno plotting."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PyWaveDyn - Virtual Dyno")
        self.resize(1280, 800)

        self.engine = Engine()
        self.audio_synth = AudioSynthesizer()

        self.navigation_tree = QTreeWidget()
        self.navigation_tree.setHeaderHidden(True)
        self.navigation_tree.currentItemChanged.connect(self.update_properties_panel)

        self.property_widget = QWidget()
        self.property_form = QFormLayout()
        self.property_widget.setLayout(self.property_form)

        self.tabs = QTabWidget()
        self.main_stack = QStackedWidget()
        self.wave_plot = pg.PlotWidget()
        self.wave_image = pg.ImageItem()
        self.wave_rpm_spin = QDoubleSpinBox()
        self.wave_scrub_slider = QSlider(Qt.Horizontal)
        self.wave_record_btn = QPushButton("🔴 Record")
        self.wave_record_btn.setCheckable(True)
        self.wave_save_btn = QPushButton("💾 Save Audio")
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
        self.pro_dyno_plot = pg.PlotWidget()
        self.pro_power_curve = None
        self.pro_torque_curve = None
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
        self.wave_audio_samples: list[float] = []
        self.wave_x_axis: Optional[np.ndarray] = None
        self.timer = QTimer(self)
        self._setup_views()

        self.toolbar = self.addToolBar("Main Toolbar")
        self._create_toolbar()
        self._create_menu()
        self._create_left_panel()

        self.refresh_tree()
        self._show_placeholder("Select a component to edit its properties")
        self.update_overview()
        self.tabs.setCurrentIndex(0)

    # -------------------------- UI Construction ---------------------------
    def _create_menu(self) -> None:
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")

        save_action = QAction("Save", self)
        save_action.triggered.connect(self.save_engine)
        file_menu.addAction(save_action)

        load_action = QAction("Load", self)
        load_action.triggered.connect(self.load_project)
        file_menu.addAction(load_action)

    def _create_toolbar(self) -> None:
        save_icon = self.style().standardIcon(QStyle.SP_DialogSaveButton)
        save_action = QAction(save_icon, "Save", self)
        save_action.triggered.connect(self.save_engine)
        self.toolbar.addAction(save_action)

        self.toolbar.addSeparator()

        nav_container = QWidget()
        nav_layout = QHBoxLayout()
        nav_layout.setContentsMargins(6, 0, 6, 0)
        nav_layout.setSpacing(8)
        nav_container.setLayout(nav_layout)

        btn_standard = QPushButton("🏠 Standard View")
        btn_standard.clicked.connect(lambda: self.main_stack.setCurrentIndex(0))
        nav_layout.addWidget(btn_standard)

        btn_pro = QPushButton("🧠 Pro Dyno")
        btn_pro.clicked.connect(lambda: self.main_stack.setCurrentIndex(1))
        nav_layout.addWidget(btn_pro)

        btn_wave = QPushButton("🌊 Wave Sim")
        btn_wave.clicked.connect(lambda: self.main_stack.setCurrentIndex(2))
        nav_layout.addWidget(btn_wave)

        btn_fabrication = QPushButton("🛠️ Fabrication")
        btn_fabrication.clicked.connect(lambda: self.main_stack.setCurrentIndex(3))
        nav_layout.addWidget(btn_fabrication)

        self.toolbar.addWidget(nav_container)

    def _create_left_panel(self) -> None:
        left_dock = QDockWidget("Project Explorer", self)
        left_dock.setWidget(self.navigation_tree)
        left_dock.setAllowedAreas(Qt.LeftDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, left_dock)

    def _setup_views(self) -> None:
        overview_tab = QWidget()
        overview_layout = QVBoxLayout()
        self.overview_browser = QTextBrowser()
        self.overview_browser.setOpenExternalLinks(False)
        self.overview_browser.setReadOnly(True)
        overview_layout.addWidget(self.overview_browser)
        overview_tab.setLayout(overview_layout)

        self.properties_tab = QWidget()
        properties_layout = QVBoxLayout()
        properties_layout.addWidget(self.property_widget)
        properties_layout.addStretch()
        self.properties_tab.setLayout(properties_layout)

        dyno_tab = QWidget()
        dyno_layout = QVBoxLayout()
        run_button = QPushButton("Run Power Sweep")
        run_button.clicked.connect(self.run_dyno_sweep)
        dyno_layout.addWidget(run_button)

        self.dyno_plot.showGrid(x=True, y=True, alpha=0.2)
        self.dyno_plot.addLegend()
        self.dyno_plot.setLabel("bottom", "RPM")
        self.dyno_plot.setLabel("left", "Output")
        dyno_layout.addWidget(self.dyno_plot)
        dyno_tab.setLayout(dyno_layout)

        analysis_tab = QWidget()
        analysis_layout = QVBoxLayout()
        self.analysis_summary_label = QLabel("No dyno data yet")
        self.analysis_summary_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        analysis_layout.addWidget(self.analysis_summary_label)
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
        analysis_layout.addWidget(self.analysis_table)
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
        self.tabs.addTab(optimizer_tab, "Optimizer")

        standard_container = QWidget()
        standard_layout = QVBoxLayout()
        standard_layout.setContentsMargins(0, 0, 0, 0)
        standard_layout.addWidget(self.tabs)
        standard_container.setLayout(standard_layout)

        pro_dyno_tab = QWidget()
        pro_dyno_layout = QVBoxLayout()
        pro_run_button = QPushButton("Run Pro Simulation (Slower)")
        pro_run_button.clicked.connect(self.run_pro_dyno_sweep)
        pro_dyno_layout.addWidget(pro_run_button)

        self.pro_dyno_plot.showGrid(x=True, y=True, alpha=0.2)
        self.pro_dyno_plot.addLegend()
        self.pro_dyno_plot.setLabel("bottom", "RPM")
        self.pro_dyno_plot.setLabel("left", "Output")
        pro_dyno_layout.addWidget(self.pro_dyno_plot)
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

        report_btn = QPushButton("📄 Generate Fabrication Report")
        report_btn.clicked.connect(self._generate_fabrication_report)
        fabrication_layout.addWidget(report_btn)
        fabrication_tab.setLayout(fabrication_layout)

        self.main_stack.addWidget(standard_container)
        self.main_stack.addWidget(pro_dyno_tab)
        self.main_stack.addWidget(self._init_wave_scope_ui())
        self.main_stack.addWidget(fabrication_tab)
        self.setCentralWidget(self.main_stack)
        self.main_stack.setCurrentIndex(0)

    def _init_wave_scope_ui(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout()

        controls = QHBoxLayout()
        rpm_label = QLabel("Simulation RPM")
        self.wave_rpm_spin.setRange(1000.0, 25000.0)
        self.wave_rpm_spin.setDecimals(0)
        self.wave_rpm_spin.setSingleStep(100.0)
        self.wave_rpm_spin.setValue(max(self.engine.camshaft.peak_rpm, 1000.0))

        calc_btn = QPushButton("⚡ Calculate Waves")
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

        sc_item = QTreeWidgetItem(["Supercharger"])
        sc_item.setData(0, Qt.UserRole, self.engine.supercharger)
        root_item.addChild(sc_item)

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
        elif isinstance(component, Supercharger):
            self._build_supercharger_form(component)
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
        self.property_form.addRow(self._label_value("Displacement (cc)", f"{block.displacement_cc:.1f}"))

        bore_spin = self._double_spin(block.bore, 50.0, 110.0, 0.1)
        self._bind_spin(bore_spin, lambda val: self._update_value(block, "bore", val), "bore")
        self.property_form.addRow("Bore (mm)", bore_spin)

        stroke_spin = self._double_spin(block.stroke, 40.0, 120.0, 0.1)
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

    def _build_supercharger_form(self, supercharger: Supercharger) -> None:
        self._clear_property_form()

        type_combo = QComboBox()
        type_combo.addItems(["NA", "Turbo", "Roots"])
        type_combo.setCurrentText(supercharger.type)
        type_combo.currentTextChanged.connect(lambda text: self._update_value(supercharger, "type", text))
        self.property_form.addRow("Type", type_combo)

        boost_spin = self._double_spin(supercharger.boost_pressure_bar, 0.0, 3.0, 0.05)
        self._bind_spin(boost_spin, lambda val: self._update_value(supercharger, "boost_pressure_bar", val), "boost_pressure_bar")
        self.property_form.addRow("Boost (bar)", boost_spin)

        ic_spin = self._double_spin(supercharger.intercooler_efficiency, 0.0, 1.0, 0.01)
        self._bind_spin(ic_spin, lambda val: self._update_value(supercharger, "intercooler_efficiency", val), "intercooler_efficiency")
        self.property_form.addRow("Intercooler Eff", ic_spin)

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

    def _apply_fuel_preset(self, fuel: Fuel, preset: str) -> None:
        presets = {
            "Regular (87)": ("Regular", 87.0, 44e6, 14.7),
            "Premium (93)": ("Premium", 93.0, 44e6, 14.7),
            "Race Gas (110)": ("Race Gas", 110.0, 46e6, 14.2),
            "E85": ("E85", 105.0, 29e6, 9.8),
            "Methanol": ("Methanol", 110.0, 20e6, 6.4),
        }
        if preset in presets:
            name, octane, energy, afr = presets[preset]
            fuel.type_name = name
            fuel.octane_rating = octane
            fuel.energy_density = energy
            fuel.stoich_afr = afr

    def _build_fuel_form(self, fuel: Fuel) -> None:
        self._clear_property_form()

        preset_combo = QComboBox()
        presets = ["Regular (87)", "Premium (93)", "Race Gas (110)", "E85", "Methanol"]
        preset_combo.addItems(presets)

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

        name_edit.editingFinished.connect(lambda: self._update_value(fuel, "type_name", name_edit.text()))
        self.property_form.addRow("Fuel Type", name_edit)

        self._bind_spin(octane_spin, lambda val: self._update_value(fuel, "octane_rating", val), "octane_rating")
        self.property_form.addRow("Octane Rating", octane_spin)

        self._bind_spin(energy_spin, lambda val: self._update_value(fuel, "energy_density", val), "energy_density")
        self.property_form.addRow("Energy Density", energy_spin)

        self._bind_spin(afr_spin, lambda val: self._update_value(fuel, "stoich_afr", val), "stoich_afr")
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

    def _bind_spin(self, spin: Any, setter: Any, attr_name: Optional[str] = None) -> None:
        def handler() -> None:
            try:
                val = spin.value()
                setter(val)
                label = attr_name or "value"
                self.statusBar().showMessage(f"Updated {label} to {val}", 2000)
            except Exception:
                pass

        spin.editingFinished.connect(handler)

    def _label_value(self, label: str, value: str) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(label))
        layout.addStretch()
        layout.addWidget(QLabel(value))
        container.setLayout(layout)
        return container

    def _update_value(self, obj: Any, attr: str, value: Any) -> None:
        setattr(obj, attr, value)
        current_item = self.navigation_tree.currentItem()
        if current_item and isinstance(obj, Block):
            self._build_block_form(obj)
        self.update_overview()

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

    def update_overview(self) -> None:
        if not hasattr(self, "overview_browser"):
            return

        block = self.engine.block
        head = self.engine.head
        cam = self.engine.camshaft
        intake = self.engine.intake
        exhaust = self.engine.exhaust
        sc = self.engine.supercharger
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

        induction = "Naturally Aspirated"
        if sc.type != "NA" or sc.boost_pressure_bar > 0.0:
            induction = f"{sc.type} @ {sc.boost_pressure_bar:.2f} bar"

        fuel_html = []
        if fuel:
            fuel_html = [
                "<h3>Fuel</h3>",
                "<ul>",
                f"<li><b>Type:</b> {fuel.type_name}</li>",
                f"<li><b>Octane:</b> {fuel.octane_rating:.1f}</li>",
                f"<li><b>Energy Density:</b> {fuel.energy_density/1e6:.2f} MJ/kg</li>",
                f"<li><b>Stoich AFR:</b> {fuel.stoich_afr:.2f}</li>",
                "</ul>",
            ]

        html_parts = [
            "<h2>Project: PyWaveDyn Engine</h2>",
            "<h3>Short Block</h3>",
            "<ul>",
            f"<li><b>Config:</b> {block.config} {block.num_cylinders}</li>",
            f"<li><b>Bore:</b> {bore:.1f} mm</li>",
            f"<li><b>Stroke:</b> {stroke:.1f} mm</li>",
            f"<li><b>Displacement:</b> {displacement_cc:.1f} cc ({displacement_l:.2f} L)</li>",
            f"<li><b>Rod Length:</b> {rod:.1f} mm</li>",
            f"<li><b>Redline:</b> {redline:.0f} rpm</li>",
            f"<li><b>Mean Piston Speed @ Redline:</b> {mean_piston_speed:.2f} m/s</li>",
            "</ul>",
            "<h3>Cylinder Head</h3>",
            "<ul>",
            f"<li><b>Compression Ratio (geom):</b> {geo_cr:.2f}:1</li>",
            f"<li><b>Intake Valve Dia:</b> {head.intake_valve_diameter:.1f} mm</li>",
            f"<li><b>Exhaust Valve Dia:</b> {head.exhaust_valve_diameter:.1f} mm</li>",
            f"<li><b>Port Flow:</b> {head.port_flow_cfm:.1f} cfm</li>",
            f"<li><b>Port Flow Efficiency:</b> {head.port_flow_efficiency:.2f}</li>",
            f"<li><b>Mach Tolerance:</b> {head.mach_tolerance:.2f}</li>",
            "</ul>",
            "<h3>Camshaft</h3>",
            "<ul>",
            f"<li><b>Durations (I/E):</b> {cam.intake_duration:.1f} / {cam.exhaust_duration:.1f} deg</li>",
            f"<li><b>Lifts (I/E):</b> {cam.intake_lift:.2f} / {cam.exhaust_lift:.2f} mm</li>",
            f"<li><b>LSA:</b> {cam.lobe_separation:.1f} deg</li>",
            f"<li><b>Advance:</b> {cam.advance:.1f} deg</li>",
            f"<li><b>Peak RPM:</b> {cam.peak_rpm:.0f}</li>",
            "</ul>",
            "<h3>Induction</h3>",
            "<ul>",
            f"<li><b>Runner:</b> {intake.runner_length:.1f} mm x {intake.runner_diameter:.1f} mm</li>",
            f"<li><b>Plenum:</b> {intake.plenum_volume:.2f} L</li>",
            f"<li><b>Throttle:</b> {intake.throttle_body_dia:.1f} mm ({intake.throttle_cfm:.1f} cfm)</li>",
            f"<li><b>Induction:</b> {induction}</li>",
            "</ul>",
            "<h3>Exhaust</h3>",
            "<ul>",
            f"<li><b>Primary:</b> {exhaust.header_primary_length:.1f} mm x {exhaust.header_primary_diameter:.1f} mm</li>",
            f"<li><b>Collector Length:</b> {exhaust.collector_length:.1f} mm</li>",
            "</ul>",
        ]

        html_parts.extend(fuel_html)

        if combustion:
            html_parts.extend(
                [
                    "<h3>Combustion</h3>",
                    "<ul>",
                    f"<li><b>Thermal Efficiency:</b> {combustion.thermal_efficiency:.2f}</li>",
                    f"<li><b>Burn Duration:</b> {combustion.burn_duration:.1f} deg</li>",
                    f"<li><b>Ignition Advance:</b> {combustion.ignition_advance:.1f} deg BTDC</li>",
                    f"<li><b>AFR:</b> {combustion.afr:.2f}</li>",
                    "</ul>",
                ]
            )

        if friction:
            html_parts.extend(
                [
                    "<h3>Friction</h3>",
                    "<ul>",
                    f"<li><b>Base FMEP:</b> {friction.friction_base_kpa:.1f} kPa</li>",
                    "</ul>",
                ]
            )

        self.overview_browser.setHtml("\n".join(html_parts))

    def _open_compression_dialog(self, head: CylinderHead, cr_spin: QDoubleSpinBox) -> None:
        dialog = CompressionDialog(self.engine, head, cr_spin, self)
        dialog.exec()

    # -------------------------- File IO -----------------------------------
    def save_engine(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(self, "Save Engine", "engine.json", "JSON Files (*.json)")
        if filename:
            self.engine.save_to_file(filename)

    def load_project(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Load Engine", "", "JSON Files (*.json)")
        if filename:
            with open(filename, "r") as f:
                data = json.load(f)

            self.engine = Engine.from_dict(data)
            self.wave_solver = None
            self.audio_synth = AudioSynthesizer()
            self.timer.stop()
            self.refresh_tree()
            self.update_properties_panel(None)
            self.update_overview()
            self.main_stack.setCurrentIndex(0)
            self.tabs.setCurrentIndex(0)

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
        )
        self.audio_synth = AudioSynthesizer()
        self.wave_history = []
        self.wave_time_vector = []
        self.wave_audio_samples = []

    def run_wave_calculation(self) -> None:
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
        self.wave_audio_samples = audio_pressures
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
    def run_dyno_sweep(self) -> None:
        simulator = CylinderSimulator(self.engine)
        max_rpm = int(self.engine.block.redline_rpm)
        rpm_values = list(range(1000, max_rpm + 500, 500))
        power_hp: list[float] = []
        torque_nm: list[float] = []
        max_hp_value = -float("inf")
        max_hp_rpm = 0
        max_hp_row = -1
        max_tq_value = -float("inf")
        max_tq_rpm = 0
        max_tq_row = -1
        knock_detected = False

        self.analysis_table.setRowCount(0)
        self.dyno_plot.setTitle("")

        for rpm in rpm_values:
            result = simulator.run_cycle(rpm)
            hp_val = result["mean_power_hp"]
            power_hp.append(hp_val)
            torque = result.get("mean_torque_nm", 0.0)
            torque_nm.append(torque)

            if hp_val > max_hp_value:
                max_hp_value = hp_val
                max_hp_rpm = rpm
                max_hp_row = self.analysis_table.rowCount()

            if torque > max_tq_value:
                max_tq_value = torque
                max_tq_rpm = rpm
                max_tq_row = self.analysis_table.rowCount()

            knock_present = self.update_analysis_table(rpm, result)
            knock_detected = knock_detected or knock_present

        warning_html = ""
        if rpm_values and max_hp_row >= 0 and max_tq_row >= 0:
            summary = (
                f"🏆 Max Power: {max_hp_value:.1f} HP @ {max_hp_rpm} RPM | 🚀 Max Torque: {max_tq_value:.1f} Nm @ {max_tq_rpm} RPM"
            )
            if knock_detected:
                warning_html = (
                    "<br><span style='color:red; font-weight:bold;'>WARNING: ENGINE KNOCK DETECTED - Low Octane for this Compression</span>"
                )
                self.dyno_plot.setTitle(
                    "<span style='color:red; font-weight:bold;'>WARNING: ENGINE KNOCK DETECTED - Low Octane for this Compression</span>"
                )
                self.statusBar().showMessage(
                    "WARNING: ENGINE KNOCK DETECTED - Low Octane for this Compression", 5000
                )
            else:
                self.statusBar().clearMessage()

            self.analysis_summary_label.setText(summary + warning_html)
            hp_item = self.analysis_table.item(max_hp_row, 2)
            if hp_item:
                hp_item.setBackground(QBrush(QColor(255, 200, 200)))
                font = QFont(hp_item.font())
                font.setBold(True)
                hp_item.setFont(font)

            tq_item = self.analysis_table.item(max_tq_row, 1)
            if tq_item:
                tq_item.setBackground(QBrush(QColor(200, 200, 255)))
                font = QFont(tq_item.font())
                font.setBold(True)
                tq_item.setFont(font)
        else:
            self.analysis_summary_label.setText("No dyno data yet")
            self.statusBar().clearMessage()

        self.dyno_plot.clear()
        self.dyno_plot.addLegend(clear=True)
        self.power_curve = self.dyno_plot.plot(rpm_values, power_hp, pen=pg.mkPen("r", width=2), name="Power (HP)")
        self.torque_curve = self.dyno_plot.plot(rpm_values, torque_nm, pen=pg.mkPen("b", width=2), name="Torque (Nm)")
        self.dyno_plot.setLabel("bottom", "RPM")
        self.dyno_plot.setLabel("left", "Power (HP) / Torque (Nm)")
        if rpm_values:
            self.dyno_plot.setXRange(min(rpm_values), max(rpm_values), padding=0.05)
        if not knock_detected:
            self.dyno_plot.setTitle("")

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
                text = "YES" if knock else "No"
                item = QTableWidgetItem(text)
                color = QColor(200, 0, 0) if knock else QColor(0, 150, 0)
                item.setForeground(QBrush(color))
                if knock:
                    font = QFont(item.font())
                    font.setBold(True)
                    item.setFont(font)
            else:
                item = QTableWidgetItem(f"{val:.2f}" if isinstance(val, (int, float)) else str(val))
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
        simulator = CylinderSimulator(self.engine)
        max_rpm = int(self.engine.block.redline_rpm)
        rpm_values = list(range(1000, max_rpm + 500, 500))
        power_hp: list[float] = []
        torque_nm: list[float] = []

        for rpm in rpm_values:
            result = simulator.run_pro_cycle(rpm)
            power_hp.append(result.get("mean_power_hp", 0.0))
            torque_nm.append(result.get("mean_torque_nm", 0.0))

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
            "Turbo: Boost Pressure (Bar)": (
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
            "Turbo: Boost Pressure (Bar)": "Bar",
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
