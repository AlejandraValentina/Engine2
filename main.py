import numpy as np
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QSlider,
    QStyle,
    QTabWidget,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core import numerics
from core.model import CylinderGeometry, CylinderNode, EngineProject, Pipe
from core.simulator import PipeSolver
from gui.widgets.scope_widget import ScopeWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyWaveDyn")
        self.resize(1200, 800)

        self.engine_project = self._create_default_project()
        self.solver: PipeSolver | None = None
        self.sim_timer = QTimer(self)
        self.sim_timer.setInterval(16)
        self.sim_timer.timeout.connect(self.run_simulation_step)

        self._create_menu()
        self._create_toolbar()
        self._create_left_panel()
        self._create_center_tabs()
        self._create_right_panel()

    def _create_menu(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")
        new_engine_wizard = QAction("New Engine Wizard...", self)
        new_engine_wizard.setStatusTip(
            "Launches the engine configuration wizard (e.g., choose Inline, V, Boxer)."
        )
        # TODO: Implement wizard to guide selection of engine topology and parameters
        file_menu.addAction(new_engine_wizard)

    def _create_toolbar(self) -> None:
        self.toolbar = QToolBar("Simulation Controls", self)
        self.toolbar.setMovable(False)

        init_action = QAction(self.style().standardIcon(QStyle.SP_BrowserReload), "Initialize Solver", self)
        init_action.triggered.connect(self.initialize_solver)
        self.toolbar.addAction(init_action)

        self.toggle_action = QAction(self.style().standardIcon(QStyle.SP_MediaPlay), "Start/Stop Simulation", self)
        self.toggle_action.setCheckable(True)
        self.toggle_action.toggled.connect(self.toggle_simulation)
        self.toolbar.addAction(self.toggle_action)

        self.toolbar.addSeparator()
        speed_label = QLabel("Sim Speed", self)
        self.toolbar.addWidget(speed_label)
        self.speed_slider = QSlider(Qt.Horizontal, self)
        self.speed_slider.setRange(1, 50)
        self.speed_slider.setValue(5)
        self.speed_slider.setToolTip("Simulation steps per frame")
        self.toolbar.addWidget(self.speed_slider)

        self.addToolBar(self.toolbar)

    def _create_left_panel(self) -> None:
        self.navigation_tree = QTreeWidget()
        self.navigation_tree.setHeaderHidden(True)
        self.navigation_tree.currentItemChanged.connect(self.update_properties_panel)

        self._populate_tree()

        left_dock = QDockWidget("Project Explorer", self)
        left_dock.setWidget(self.navigation_tree)
        left_dock.setAllowedAreas(Qt.LeftDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, left_dock)

    def _create_center_tabs(self) -> None:
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self._create_placeholder_tab("Dashboard / Overview"), "Overview")
        self.scope_widget = ScopeWidget()
        self.tab_widget.addTab(self.scope_widget, "Simulation Monitor")
        self.setCentralWidget(self.tab_widget)

    def _create_placeholder_tab(self, title: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(QLabel(title))
        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def _create_right_panel(self) -> None:
        self.property_widget = QWidget()
        self.property_form = QFormLayout()
        self.property_widget.setLayout(self.property_form)
        self._show_placeholder("Select an item to edit properties")

        right_dock = QDockWidget("Properties", self)
        right_dock.setWidget(self.property_widget)
        right_dock.setAllowedAreas(Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.RightDockWidgetArea, right_dock)

    def _populate_tree(self) -> None:
        root = QTreeWidgetItem([f"Project: {self.engine_project.name}"])
        root.setData(0, Qt.UserRole, self.engine_project)
        self.navigation_tree.addTopLevelItem(root)

        global_settings = QTreeWidgetItem(["Global Settings"])
        global_settings.setData(0, Qt.UserRole, self.engine_project.simulation_settings)
        global_settings.addChild(QTreeWidgetItem(["Environment"]))
        global_settings.addChild(QTreeWidgetItem(["Simulation Time"]))
        root.addChild(global_settings)

        engine_block = QTreeWidgetItem(["Engine Block"])
        engine_block.setData(0, Qt.UserRole, self.engine_project)

        cylinder_index = 1
        for bank_name, cylinders in self.engine_project.banks.items():
            bank_item = QTreeWidgetItem([bank_name])
            bank_item.setData(0, Qt.UserRole, cylinders)
            for cylinder in cylinders:
                cylinder_item = QTreeWidgetItem([f"Cylinder {cylinder_index}"])
                cylinder_item.setData(0, Qt.UserRole, cylinder.geometry)
                bank_item.addChild(cylinder_item)
                cylinder_index += 1
            engine_block.addChild(bank_item)
        root.addChild(engine_block)

        cylinder_head = QTreeWidgetItem(["Cylinder Head"])
        cylinder_head.addChild(QTreeWidgetItem(["Camshaft Profiles"]))
        cylinder_head.addChild(QTreeWidgetItem(["Valves Geometry"]))
        root.addChild(cylinder_head)

        gas_exchange = QTreeWidgetItem(["Gas Exchange Network"])
        intake_system = QTreeWidgetItem(["Intake System"])
        intake_system.addChild(QTreeWidgetItem(["Plenum"]))
        for runner_key in self.intake_runners:
            runner_item = QTreeWidgetItem([runner_key])
            runner_item.setData(0, Qt.UserRole, self.engine_project.pipes[runner_key])
            intake_system.addChild(runner_item)

        exhaust_system = QTreeWidgetItem(["Exhaust System"])
        for pipe_key in self.exhaust_pipes:
            pipe_item = QTreeWidgetItem([pipe_key])
            pipe_item.setData(0, Qt.UserRole, self.engine_project.pipes[pipe_key])
            exhaust_system.addChild(pipe_item)
        collector_item = QTreeWidgetItem(["Collector A (Merge)"])
        collector_item.setData(0, Qt.UserRole, None)
        exhaust_system.addChild(collector_item)

        gas_exchange.addChild(intake_system)
        gas_exchange.addChild(exhaust_system)
        root.addChild(gas_exchange)

        self.navigation_tree.expandAll()

    def _create_default_project(self) -> EngineProject:
        project = EngineProject(name="MyRaceEngine")
        project.banks = {
            "Bank 1": [
                CylinderNode(firing_angle=0.0),
                CylinderNode(firing_angle=180.0),
            ],
            "Bank 2": [
                CylinderNode(firing_angle=360.0),
                CylinderNode(firing_angle=540.0),
            ],
        }

        project.pipes = {
            "Intake Runner 1 -> Connects to Cyl 1": Pipe(length=280.0, diameter_inlet=38.0),
            "Intake Runner 2 -> Connects to Cyl 2": Pipe(length=280.0, diameter_inlet=38.0),
            "Exhaust Primary 1 -> From Cyl 1": Pipe(length=600.0, diameter_inlet=38.0),
            "Exhaust Primary 2 -> From Cyl 2": Pipe(length=600.0, diameter_inlet=38.0),
            "Tailpipe": Pipe(length=900.0, diameter_inlet=55.0, diameter_outlet=55.0),
        }

        self.intake_runners = [
            "Intake Runner 1 -> Connects to Cyl 1",
            "Intake Runner 2 -> Connects to Cyl 2",
        ]
        self.exhaust_pipes = [
            "Exhaust Primary 1 -> From Cyl 1",
            "Exhaust Primary 2 -> From Cyl 2",
            "Tailpipe",
        ]
        return project

    def _clear_property_form(self) -> None:
        while self.property_form.rowCount():
            self.property_form.removeRow(0)

    def _show_placeholder(self, message: str) -> None:
        self._clear_property_form()
        placeholder = QLabel(message)
        placeholder.setWordWrap(True)
        self.property_form.addRow(placeholder)

    def update_properties_panel(self, current: QTreeWidgetItem | None, previous: QTreeWidgetItem | None = None) -> None:
        if current is None:
            self._show_placeholder("Select an item to edit properties")
            return

        obj = current.data(0, Qt.UserRole)
        if isinstance(obj, CylinderGeometry):
            self._build_cylinder_geometry_form(obj)
        elif isinstance(obj, Pipe):
            self._build_pipe_form(obj)
        else:
            self._show_placeholder("No editable properties for this selection")

    def _build_cylinder_geometry_form(self, geometry: CylinderGeometry) -> None:
        self._clear_property_form()

        bore_spin = self._create_double_spinbox(geometry.bore, 20.0, 150.0, 0.1)
        bore_spin.valueChanged.connect(lambda value: setattr(geometry, "bore", value))
        self.property_form.addRow("Bore (mm)", bore_spin)

        stroke_spin = self._create_double_spinbox(geometry.stroke, 20.0, 150.0, 0.1)
        stroke_spin.valueChanged.connect(lambda value: setattr(geometry, "stroke", value))
        self.property_form.addRow("Stroke (mm)", stroke_spin)

        cr_spin = self._create_double_spinbox(geometry.compression_ratio, 5.0, 20.0, 0.1)
        cr_spin.valueChanged.connect(
            lambda value: setattr(geometry, "compression_ratio", value)
        )
        self.property_form.addRow("Compression Ratio", cr_spin)

    def _build_pipe_form(self, pipe: Pipe) -> None:
        self._clear_property_form()

        length_spin = self._create_double_spinbox(pipe.length, 50.0, 2000.0, 1.0)
        length_spin.valueChanged.connect(lambda value: setattr(pipe, "length", value))
        self.property_form.addRow("Length (mm)", length_spin)

        diameter_inlet_spin = self._create_double_spinbox(
            pipe.diameter_inlet, 10.0, 200.0, 0.5
        )
        diameter_inlet_spin.valueChanged.connect(
            lambda value: setattr(pipe, "diameter_inlet", value)
        )
        self.property_form.addRow("Diameter Inlet (mm)", diameter_inlet_spin)

        diameter_outlet_spin = self._create_double_spinbox(
            pipe.diameter_outlet, 10.0, 200.0, 0.5
        )
        diameter_outlet_spin.valueChanged.connect(
            lambda value: setattr(pipe, "diameter_outlet", value)
        )
        self.property_form.addRow("Diameter Outlet (mm)", diameter_outlet_spin)

    def _create_double_spinbox(
        self, value: float, minimum: float, maximum: float, step: float
    ) -> QDoubleSpinBox:
        spinbox = QDoubleSpinBox()
        spinbox.setRange(minimum, maximum)
        spinbox.setDecimals(2)
        spinbox.setSingleStep(step)
        spinbox.setValue(value)
        return spinbox

    # --- Simulation wiring ---
    def initialize_solver(self) -> None:
        pipe_obj = None
        if self.engine_project.pipes:
            first_key = next(iter(self.engine_project.pipes))
            pipe_obj = self.engine_project.pipes[first_key]

        if pipe_obj is None:
            pipe_obj = Pipe(length=1.0, diameter_inlet=0.04, diameter_outlet=0.04, friction_coeff=0.02)

        length_m = pipe_obj.length / 1000.0
        diameter_inlet_m = pipe_obj.diameter_inlet / 1000.0
        diameter_outlet_m = pipe_obj.diameter_outlet / 1000.0
        pipe_si = Pipe(
            length=length_m,
            diameter_inlet=diameter_inlet_m,
            diameter_outlet=diameter_outlet_m,
            wall_temperature=pipe_obj.wall_temperature,
            friction_coeff=pipe_obj.friction_coeff,
        )

        self.solver = PipeSolver(pipe_si, target_dx=0.01)

        center_idx = self.solver.N // 2
        self.solver.U[center_idx, 2] *= 1.2

        x_axis = np.linspace(0, self.solver.L, self.solver.N)
        p = self.compute_pressure(self.solver.U)
        self.scope_widget.update_data(x_axis, p)

    def toggle_simulation(self, running: bool) -> None:
        if self.solver is None:
            self.toggle_action.setChecked(False)
            return

        if running:
            self.toggle_action.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
            self.sim_timer.start()
        else:
            self.toggle_action.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
            self.sim_timer.stop()

    def run_simulation_step(self) -> None:
        if self.solver is None:
            return

        steps_per_frame = self.speed_slider.value()
        rpm = 12_000.0
        p_high = 15.0 * 100_000.0
        p_low = 1.0 * 100_000.0
        t_cyl = 1200.0
        max_area = 0.0007

        for _ in range(steps_per_frame):
            crank_angle = (self.solver.time * rpm * 360.0 / 60.0) % 720.0
            if 140.0 < crank_angle < 360.0:
                lift_factor = np.sin(np.pi * (crank_angle - 140.0) / (360.0 - 140.0))
                current_area = max_area * lift_factor
                current_p_cyl = p_high
            else:
                current_area = 0.0
                current_p_cyl = p_low

            dt = self.solver.get_time_step()
            self.solver.step_valve_boundary(dt, current_p_cyl, t_cyl, current_area)
            self.solver.step(dt)

        x_axis = np.linspace(0, self.solver.L, self.solver.N)
        p = self.compute_pressure(self.solver.U)
        self.scope_widget.update_data(x_axis, p)

    @staticmethod
    def compute_pressure(state: np.ndarray) -> np.ndarray:
        rho = state[:, 0]
        mom = state[:, 1]
        energy = state[:, 2]
        u = mom / rho
        return (numerics.GAMMA - 1.0) * (energy - 0.5 * rho * u * u)


def main() -> None:
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
