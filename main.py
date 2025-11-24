from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDockWidget,
    QFormLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyWaveDyn")
        self.resize(1200, 800)

        self.engine_model = {
            "project_name": "MyRaceEngine",
            "banks": [
                {"name": "Bank 1", "cylinders": 2},
                {"name": "Bank 2", "cylinders": 2},
            ],
            "intake_runners": [
                "Runner 1 -> Connects to Cyl 1",
                "Runner 2 -> Connects to Cyl 2",
            ],
            "exhaust_primaries": [
                "Primary Pipe 1 -> From Cyl 1",
                "Primary Pipe 2 -> From Cyl 2",
            ],
        }

        self._create_menu()
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

    def _create_left_panel(self) -> None:
        self.navigation_tree = QTreeWidget()
        self.navigation_tree.setHeaderHidden(True)
        self.navigation_tree.itemSelectionChanged.connect(self._on_tree_selection_changed)

        self._populate_tree()

        left_dock = QDockWidget("Project Explorer", self)
        left_dock.setWidget(self.navigation_tree)
        left_dock.setAllowedAreas(Qt.LeftDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, left_dock)

    def _create_center_tabs(self) -> None:
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self._create_placeholder_tab("Dashboard / Overview"), "Overview")
        self.tab_widget.addTab(self._create_placeholder_tab("Simulation Plots"), "Plots")
        self.setCentralWidget(self.tab_widget)

    def _create_placeholder_tab(self, title: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(QLabel(title))
        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def _create_right_panel(self) -> None:
        self.property_stack = QStackedWidget()
        self.property_stack.addWidget(self._create_placeholder_panel("Select an item to edit properties"))
        self.engine_block_panel_index = self.property_stack.addWidget(self._create_engine_block_panel())

        right_dock = QDockWidget("Properties", self)
        right_dock.setWidget(self.property_stack)
        right_dock.setAllowedAreas(Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.RightDockWidgetArea, right_dock)

    def _create_placeholder_panel(self, message: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(QLabel(message))
        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def _create_engine_block_panel(self) -> QWidget:
        widget = QWidget()
        form_layout = QFormLayout()

        configuration_combo = QComboBox()
        configuration_combo.addItems(["Single", "Inline", "V-Type", "Boxer"])
        form_layout.addRow("Configuration Type", configuration_combo)

        cylinder_count_spin = QSpinBox()
        cylinder_count_spin.setRange(1, 24)
        cylinder_count_spin.setValue(4)
        form_layout.addRow("Number of Cylinders", cylinder_count_spin)

        widget.setLayout(form_layout)
        return widget

    def _populate_tree(self) -> None:
        root = QTreeWidgetItem([f"Project: {self.engine_model['project_name']}"])
        self.navigation_tree.addTopLevelItem(root)

        global_settings = QTreeWidgetItem(["Global Settings"])
        global_settings.addChild(QTreeWidgetItem(["Environment"]))
        global_settings.addChild(QTreeWidgetItem(["Simulation Time"]))
        root.addChild(global_settings)

        engine_block = QTreeWidgetItem(["Engine Block"])
        properties = QTreeWidgetItem(["Properties"])
        properties.addChild(QTreeWidgetItem(["Type: Inline/V"]))
        properties.addChild(QTreeWidgetItem(["Bore"]))
        properties.addChild(QTreeWidgetItem(["Stroke"]))
        properties.addChild(QTreeWidgetItem(["Firing Order"]))
        engine_block.addChild(properties)

        cylinder_index = 1
        for bank in self.engine_model["banks"]:
            bank_item = QTreeWidgetItem([bank["name"]])
            for _ in range(bank["cylinders"]):
                bank_item.addChild(QTreeWidgetItem([f"Cylinder {cylinder_index}"]))
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
        intake_system.addChildren(
            [QTreeWidgetItem([runner]) for runner in self.engine_model["intake_runners"]]
        )

        exhaust_system = QTreeWidgetItem(["Exhaust System"])
        exhaust_system.addChildren(
            [QTreeWidgetItem([pipe]) for pipe in self.engine_model["exhaust_primaries"]]
        )
        exhaust_system.addChild(QTreeWidgetItem(["Collector A (Merge)"]))
        exhaust_system.addChild(QTreeWidgetItem(["Tailpipe"]))

        gas_exchange.addChild(intake_system)
        gas_exchange.addChild(exhaust_system)
        root.addChild(gas_exchange)

        self.navigation_tree.expandAll()

    def _on_tree_selection_changed(self) -> None:
        selected_items = self.navigation_tree.selectedItems()
        if not selected_items:
            self.property_stack.setCurrentIndex(0)
            return

        selected_text = selected_items[0].text(0)
        if selected_text == "Engine Block":
            self.property_stack.setCurrentIndex(self.engine_block_panel_index)
        else:
            self.property_stack.setCurrentIndex(0)


def main() -> None:
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
