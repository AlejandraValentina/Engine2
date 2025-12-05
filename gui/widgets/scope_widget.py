from PySide6.QtWidgets import QWidget, QVBoxLayout
import pyqtgraph as pg


class ScopeWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        pg.setConfigOptions(antialias=True)

        self.plot_widget = pg.PlotWidget(background="k")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.15)
        self.plot_widget.setLabel("bottom", "Position (m)")
        self.plot_widget.setLabel("left", "Pressure (Pa)")
        # Let the vertical axis auto-scale to keep signals visible regardless of
        # operating pressure.
        self.plot_widget.getViewBox().enableAutoRange(axis="y")

        neon_pen = pg.mkPen(color=(0, 255, 255), width=3)
        self.curve = self.plot_widget.plot(pen=neon_pen)

        self.status_item = pg.TextItem(color="w", anchor=(0.0, 1.0))
        self.status_item.setText("Time: 0.00 ms | Crank: 0.0 deg | Valve: CLOSED")
        self.plot_widget.addItem(self.status_item)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plot_widget)

    def update_data(self, x_axis, pressure_pa):
        self.curve.setData(x_axis, pressure_pa)

    def update_status(self, angle_deg: float, valve_state: str, sim_time: float) -> None:
        text = f"Time: {sim_time * 1000.0:.2f} ms | Crank: {angle_deg:6.1f} deg | Valve: {valve_state}"
        self.status_item.setText(text)
        view_range = self.plot_widget.getViewBox().viewRange()
        if not view_range:
            return
        (x_min, x_max), (y_min, y_max) = view_range
        x_span = max(x_max - x_min, 1e-6)
        y_span = max(y_max - y_min, 1e-6)
        margin_x = 0.02 * x_span
        margin_y = 0.05 * y_span
        self.status_item.setPos(x_min + margin_x, y_max - margin_y)
