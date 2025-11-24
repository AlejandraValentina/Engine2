from __future__ import annotations

import math
from typing import Any, Optional

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QStyle,
    QSpinBox,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.engine_components import (
    Block,
    Camshaft,
    CylinderHead,
    Engine,
    ExhaustSystem,
    IntakeSystem,
    Supercharger,
)
from core.thermo import CylinderSimulator


class MainWindow(QMainWindow):
    """Main GUI window binding engine data, editing, and dyno plotting."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PyWaveDyn - Virtual Dyno")
        self.resize(1280, 800)

        self.engine = Engine()

        self.navigation_tree = QTreeWidget()
        self.navigation_tree.setHeaderHidden(True)
        self.navigation_tree.currentItemChanged.connect(self.update_properties_panel)

        self.property_widget = QWidget()
        self.property_form = QFormLayout()
        self.property_widget.setLayout(self.property_form)

        self.tab_widget = QTabWidget()
        self.dyno_plot = pg.PlotWidget()
        self.power_curve = None
        self.torque_curve = None
        self.optimizer_plot = pg.PlotWidget()
        self.optimizer_param_combo = QComboBox()
        self.optimizer_start_spin = QDoubleSpinBox()
        self.optimizer_end_spin = QDoubleSpinBox()
        self.optimizer_step_spin = QDoubleSpinBox()
        self.optimizer_progress = QProgressBar()
        self._setup_tabs()

        self.toolbar = self.addToolBar("Main Toolbar")
        self._create_toolbar()
        self._create_menu()
        self._create_left_panel()

        self.refresh_tree()
        self._show_placeholder("Select a component to edit its properties")

    # -------------------------- UI Construction ---------------------------
    def _create_menu(self) -> None:
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")

        save_action = QAction("Save", self)
        save_action.triggered.connect(self.save_engine)
        file_menu.addAction(save_action)

        load_action = QAction("Load", self)
        load_action.triggered.connect(self.load_engine)
        file_menu.addAction(load_action)

    def _create_toolbar(self) -> None:
        save_icon = self.style().standardIcon(QStyle.SP_DialogSaveButton)
        save_action = QAction(save_icon, "Save", self)
        save_action.triggered.connect(self.save_engine)
        self.toolbar.addAction(save_action)

    def _create_left_panel(self) -> None:
        left_dock = QDockWidget("Project Explorer", self)
        left_dock.setWidget(self.navigation_tree)
        left_dock.setAllowedAreas(Qt.LeftDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, left_dock)

    def _setup_tabs(self) -> None:
        overview_tab = QWidget()
        overview_layout = QVBoxLayout()
        overview_layout.addWidget(QLabel("Engine Overview"))
        overview_layout.addStretch()
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

        optimizer_tab = QWidget()
        optimizer_layout = QVBoxLayout()

        target_layout = QFormLayout()
        self.optimizer_param_combo.addItems(
            [
                "Camshaft: Intake Duration (deg)",
                "Camshaft: Max Lift (mm)",
                "Intake: Runner Length (mm)",
                "Intake: Runner Diameter (mm)",
                "Exhaust: Primary Length (mm)",
                "Exhaust: Primary Diameter (mm)",
                "Block: Compression Ratio",
            ]
        )
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

        self.tab_widget.addTab(overview_tab, "Overview")
        self.tab_widget.addTab(self.properties_tab, "Properties")
        self.tab_widget.addTab(dyno_tab, "Dyno Graph")
        self.tab_widget.addTab(optimizer_tab, "Optimizer")
        self.setCentralWidget(self.tab_widget)

    # -------------------------- Tree Handling -----------------------------
    def refresh_tree(self) -> None:
        self.navigation_tree.clear()
        root_item = QTreeWidgetItem(["Engine"])
        root_item.setData(0, Qt.UserRole, self.engine)
        self.navigation_tree.addTopLevelItem(root_item)

        block_item = QTreeWidgetItem(["Block"])
        block_item.setData(0, Qt.UserRole, self.engine.block)
        root_item.addChild(block_item)

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

        self.navigation_tree.expandAll()
        self.navigation_tree.setCurrentItem(block_item)

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

        self.tab_widget.setCurrentWidget(self.properties_tab)

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
        else:
            self._show_placeholder("No editable properties for this selection")

    def _build_block_form(self, block: Block) -> None:
        self._clear_property_form()
        self.property_form.addRow(self._label_value("Displacement (cc)", f"{block.displacement_cc:.1f}"))

        bore_spin = self._double_spin(block.bore, 50.0, 110.0, 0.1)
        bore_spin.valueChanged.connect(lambda val: self._update_value(block, "bore", val))
        self.property_form.addRow("Bore (mm)", bore_spin)

        stroke_spin = self._double_spin(block.stroke, 40.0, 120.0, 0.1)
        stroke_spin.valueChanged.connect(lambda val: self._update_value(block, "stroke", val))
        self.property_form.addRow("Stroke (mm)", stroke_spin)

        rod_spin = self._double_spin(block.conrod_length, 80.0, 200.0, 0.5)
        rod_spin.valueChanged.connect(lambda val: self._update_value(block, "conrod_length", val))
        self.property_form.addRow("Conrod Length (mm)", rod_spin)

        cyl_spin = QSpinBox()
        cyl_spin.setRange(1, 16)
        cyl_spin.setValue(block.num_cylinders)
        cyl_spin.valueChanged.connect(lambda val: self._update_value(block, "num_cylinders", val))
        self.property_form.addRow("Cylinders", cyl_spin)

        config_combo = QComboBox()
        config_combo.addItems(["L", "V", "Boxer"])
        config_combo.setCurrentText(block.config)
        config_combo.currentTextChanged.connect(lambda text: self._update_value(block, "config", text))
        self.property_form.addRow("Configuration", config_combo)

        bank_spin = self._double_spin(block.bank_angle, 0.0, 120.0, 0.5)
        bank_spin.valueChanged.connect(lambda val: self._update_value(block, "bank_angle", val))
        self.property_form.addRow("Bank Angle (deg)", bank_spin)

        firing_edit = QLineEdit(",".join(str(x) for x in block.firing_order))
        firing_edit.editingFinished.connect(lambda: self._update_firing_order(block, firing_edit.text()))
        self.property_form.addRow("Firing Order", firing_edit)

    def _build_head_form(self, head: CylinderHead) -> None:
        self._clear_property_form()

        cr_spin = self._double_spin(head.compression_ratio, 5.0, 18.0, 0.1)
        cr_spin.valueChanged.connect(lambda val: self._update_value(head, "compression_ratio", val))
        self.property_form.addRow("Compression Ratio", cr_spin)

        intake_valves_spin = QSpinBox()
        intake_valves_spin.setRange(1, 5)
        intake_valves_spin.setValue(head.intake_valves)
        intake_valves_spin.valueChanged.connect(lambda val: self._update_value(head, "intake_valves", val))
        self.property_form.addRow("Intake Valves", intake_valves_spin)

        exhaust_valves_spin = QSpinBox()
        exhaust_valves_spin.setRange(1, 5)
        exhaust_valves_spin.setValue(head.exhaust_valves)
        exhaust_valves_spin.valueChanged.connect(lambda val: self._update_value(head, "exhaust_valves", val))
        self.property_form.addRow("Exhaust Valves", exhaust_valves_spin)

        chamber_spin = self._double_spin(head.combustion_chamber_vol or 40.0, 20.0, 80.0, 0.1)
        chamber_spin.valueChanged.connect(lambda val: self._update_value(head, "combustion_chamber_vol", val))
        self.property_form.addRow("Chamber Volume (cc)", chamber_spin)

    def _build_cam_form(self, cam: Camshaft) -> None:
        self._clear_property_form()

        int_lift = self._double_spin(cam.intake_lift, 1.0, 20.0, 0.1)
        int_lift.valueChanged.connect(lambda val: self._update_value(cam, "intake_lift", val))
        self.property_form.addRow("Intake Lift (mm)", int_lift)

        exh_lift = self._double_spin(cam.exhaust_lift, 1.0, 20.0, 0.1)
        exh_lift.valueChanged.connect(lambda val: self._update_value(cam, "exhaust_lift", val))
        self.property_form.addRow("Exhaust Lift (mm)", exh_lift)

        int_dur = self._double_spin(cam.intake_duration, 180.0, 320.0, 0.5)
        int_dur.valueChanged.connect(lambda val: self._update_value(cam, "intake_duration", val))
        self.property_form.addRow("Intake Duration (deg)", int_dur)

        exh_dur = self._double_spin(cam.exhaust_duration, 180.0, 320.0, 0.5)
        exh_dur.valueChanged.connect(lambda val: self._update_value(cam, "exhaust_duration", val))
        self.property_form.addRow("Exhaust Duration (deg)", exh_dur)

        lsa_spin = self._double_spin(cam.lobe_separation, 90.0, 125.0, 0.5)
        lsa_spin.valueChanged.connect(lambda val: self._update_value(cam, "lobe_separation", val))
        self.property_form.addRow("Lobe Separation (deg)", lsa_spin)

        adv_spin = self._double_spin(cam.advance, -20.0, 20.0, 0.5)
        adv_spin.valueChanged.connect(lambda val: self._update_value(cam, "advance", val))
        self.property_form.addRow("Advance (deg)", adv_spin)

    def _build_intake_form(self, intake: IntakeSystem) -> None:
        self._clear_property_form()

        runner_len = self._double_spin(intake.runner_length, 50.0, 800.0, 1.0)
        runner_len.valueChanged.connect(lambda val: self._update_value(intake, "runner_length", val))
        self.property_form.addRow("Runner Length (mm)", runner_len)

        runner_dia = self._double_spin(intake.runner_diameter, 20.0, 120.0, 0.5)
        runner_dia.valueChanged.connect(lambda val: self._update_value(intake, "runner_diameter", val))
        self.property_form.addRow("Runner Diameter (mm)", runner_dia)

        plenum_vol = self._double_spin(intake.plenum_volume, 0.5, 10.0, 0.1)
        plenum_vol.valueChanged.connect(lambda val: self._update_value(intake, "plenum_volume", val))
        self.property_form.addRow("Plenum Volume (L)", plenum_vol)

        throttle_dia = self._double_spin(intake.throttle_body_dia, 30.0, 90.0, 0.5)
        throttle_dia.valueChanged.connect(lambda val: self._update_value(intake, "throttle_body_dia", val))
        self.property_form.addRow("Throttle Body Dia (mm)", throttle_dia)

    def _build_exhaust_form(self, exhaust: ExhaustSystem) -> None:
        self._clear_property_form()

        primary_len = self._double_spin(exhaust.header_primary_length, 100.0, 1200.0, 1.0)
        primary_len.valueChanged.connect(lambda val: self._update_value(exhaust, "header_primary_length", val))
        self.property_form.addRow("Primary Length (mm)", primary_len)

        primary_dia = self._double_spin(exhaust.header_primary_diameter, 20.0, 100.0, 0.5)
        primary_dia.valueChanged.connect(lambda val: self._update_value(exhaust, "header_primary_diameter", val))
        self.property_form.addRow("Primary Diameter (mm)", primary_dia)

        collector_len = self._double_spin(exhaust.collector_length, 100.0, 1200.0, 1.0)
        collector_len.valueChanged.connect(lambda val: self._update_value(exhaust, "collector_length", val))
        self.property_form.addRow("Collector Length (mm)", collector_len)

    def _build_supercharger_form(self, supercharger: Supercharger) -> None:
        self._clear_property_form()

        type_combo = QComboBox()
        type_combo.addItems(["NA", "Turbo", "Roots"])
        type_combo.setCurrentText(supercharger.type)
        type_combo.currentTextChanged.connect(lambda text: self._update_value(supercharger, "type", text))
        self.property_form.addRow("Type", type_combo)

        boost_spin = self._double_spin(supercharger.boost_pressure_bar, 0.0, 3.0, 0.05)
        boost_spin.valueChanged.connect(lambda val: self._update_value(supercharger, "boost_pressure_bar", val))
        self.property_form.addRow("Boost (bar)", boost_spin)

    # -------------------------- Helpers -----------------------------------
    def _double_spin(self, value: float, minimum: float, maximum: float, step: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(3)
        spin.setSingleStep(step)
        spin.setValue(value)
        return spin

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

    def _update_firing_order(self, block: Block, text: str) -> None:
        try:
            order = [int(x.strip()) for x in text.split(",") if x.strip()]
            if order:
                block.firing_order = order
        except ValueError:
            pass

    # -------------------------- File IO -----------------------------------
    def save_engine(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(self, "Save Engine", "engine.json", "JSON Files (*.json)")
        if filename:
            self.engine.save_to_file(filename)

    def load_engine(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Load Engine", "", "JSON Files (*.json)")
        if filename:
            self.engine = Engine.load_from_file(filename)
            self.refresh_tree()

    # -------------------------- Dyno Sweep --------------------------------
    def run_dyno_sweep(self) -> None:
        simulator = CylinderSimulator(self.engine)
        rpm_values = list(range(3000, 12001, 500))
        power_hp: list[float] = []
        torque_nm: list[float] = []

        for rpm in rpm_values:
            result = simulator.run_cycle(rpm)
            power_hp.append(result["mean_power_hp"])
            power_w = result["mean_power_hp"] * 745.7
            torque = power_w * 60.0 / (2.0 * math.pi * rpm)
            torque_nm.append(torque)

        self.dyno_plot.clear()
        self.dyno_plot.addLegend(clear=True)
        self.power_curve = self.dyno_plot.plot(rpm_values, power_hp, pen=pg.mkPen("r", width=2), name="Power (HP)")
        self.torque_curve = self.dyno_plot.plot(rpm_values, torque_nm, pen=pg.mkPen("b", width=2), name="Torque (Nm)")
        self.dyno_plot.setLabel("bottom", "RPM")
        self.dyno_plot.setLabel("left", "Power (HP) / Torque (Nm)")

    # -------------------------- Optimization -----------------------------
    def _parameter_mapping(self) -> dict[str, tuple[Any, str]]:
        return {
            "Camshaft: Intake Duration (deg)": (self.engine.camshaft, "intake_duration"),
            "Camshaft: Max Lift (mm)": (self.engine.camshaft, "intake_lift"),
            "Intake: Runner Length (mm)": (self.engine.intake, "runner_length"),
            "Intake: Runner Diameter (mm)": (self.engine.intake, "runner_diameter"),
            "Exhaust: Primary Length (mm)": (self.engine.exhaust, "header_primary_length"),
            "Exhaust: Primary Diameter (mm)": (self.engine.exhaust, "header_primary_diameter"),
            "Block: Compression Ratio": (self.engine.head, "compression_ratio"),
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
        if not hasattr(obj, attr):
            return

        start = self.optimizer_start_spin.value()
        end = self.optimizer_end_spin.value()
        step = self.optimizer_step_spin.value()
        if step <= 0:
            return

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
            setattr(obj, attr, val)
            peak_hp = self._compute_peak_hp()
            results.append(peak_hp)
            progress = int((idx + 1) / total * 100)
            self.optimizer_progress.setValue(progress)
            QApplication.processEvents()

        setattr(obj, attr, original_value)
        self.optimizer_progress.setValue(100)

        self.optimizer_plot.clear()
        self.optimizer_plot.plot(values, results, pen=pg.mkPen("m", width=2), symbol="o", name="Peak HP")
        self.optimizer_plot.setLabel("bottom", target)
        self.optimizer_plot.setLabel("left", "Peak HP")


def main() -> None:
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
