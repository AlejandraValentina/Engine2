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
        self.plot_widget.setYRange(0, 250000)

        neon_pen = pg.mkPen(color=(0, 255, 255), width=2)
        self.curve = self.plot_widget.plot(pen=neon_pen)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plot_widget)

    def update_data(self, x_axis, pressure_data):
        self.curve.setData(x_axis, pressure_data)
