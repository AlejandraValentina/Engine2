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

        self.status_item = pg.TextItem(color="w", anchor=(0, 0))
        self.status_item.setText("Time: 0.00 ms | Crank: 0.0 deg | Valve: CLOSED")
        self.status_item.setPos(0.0, 0.0)
        self.plot_widget.addItem(self.status_item)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plot_widget)

    def update_data(self, x_axis, pressure_data):
        self.curve.setData(x_axis, pressure_data)

    def update_status(self, angle_deg: float, valve_state: str, sim_time: float) -> None:
        text = f"Time: {sim_time * 1000.0:.2f} ms | Crank: {angle_deg:6.1f} deg | Valve: {valve_state}"
        self.status_item.setText(text)
