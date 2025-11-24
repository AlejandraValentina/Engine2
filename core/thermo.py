"""0D thermodynamic cycle simulator for indicated torque/power estimates."""
from __future__ import annotations

import math
from typing import Dict

import numpy as np

from core.engine_components import Engine

GAMMA = 1.4
R_AIR = 287.0
LHV_DEFAULT = 44e6  # J/kg
AFR_STOICH = 14.7
P_ATM = 101325.0
T_INTAKE = 300.0


def piston_geometry(angle_array_deg: np.ndarray, bore: float, stroke: float, conrod: float):
    """Return (volume, dV/dtheta, lever arm) for given crank angles.

    All geometry inputs are in millimeters; outputs are meters-based volumes.
    angle_array_deg is expected in crank degrees.
    """
    theta = np.deg2rad(angle_array_deg)
    r = (stroke * 1e-3) / 2.0  # crank radius (m)
    l = conrod * 1e-3  # rod length (m)
    area = math.pi * (bore * 1e-3) ** 2 / 4.0

    sin_t = np.sin(theta)
    cos_t = np.cos(theta)
    under_sqrt = np.maximum(l ** 2 - (r * sin_t) ** 2, 1e-12)
    x = r * (1.0 - cos_t) + l - np.sqrt(under_sqrt)

    dx_dtheta = r * sin_t + (r ** 2 * sin_t * cos_t) / np.sqrt(under_sqrt)
    dV_dtheta = area * dx_dtheta  # derivative with respect to crank angle (radians)

    # Mechanical advantage proxy; crank effective lever arm
    lever_arm = r * sin_t + (r ** 2 * sin_t * cos_t) / np.sqrt(under_sqrt)

    # Swept contribution only; clearance volume handled in simulator
    V_swept = area * x
    return V_swept, dV_dtheta, lever_arm


def wiebe_function(angle_array_deg: np.ndarray, start_angle: float, duration: float, efficiency: float):
    """Return cumulative heat release fraction (0..1) using Wiebe."""
    a = 5.0
    m = 2.0
    theta = angle_array_deg
    x = np.zeros_like(theta)

    mask = (theta >= start_angle) & (theta <= start_angle + duration)
    theta_rel = (theta[mask] - start_angle) / duration
    expo = -a * theta_rel ** (m + 1)
    x_val = 1.0 - np.exp(expo)

    x[mask] = x_val * efficiency
    x[theta > start_angle + duration] = efficiency
    return x


class CylinderSimulator:
    """Simple 0D cylinder thermodynamics to estimate pressure and torque."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def run_cycle(self, rpm: float) -> Dict[str, np.ndarray]:
        # Crank angle grid (0-720 deg, 0.5 deg resolution)
        angle_arr = np.arange(0.0, 720.0 + 0.5, 0.5)

        # Geometry
        volume_swept, dV_dtheta, _ = piston_geometry(
            angle_arr,
            self.engine.block.bore,
            self.engine.block.stroke,
            self.engine.block.conrod_length,
        )

        bore_m = self.engine.block.bore * 1e-3
        stroke_m = self.engine.block.stroke * 1e-3
        area = math.pi * bore_m ** 2 / 4.0
        Vd = area * stroke_m  # swept volume per cylinder (m^3)
        Vc = Vd / (self.engine.head.compression_ratio - 1.0)
        volume = volume_swept + Vc

        # Motored baseline (adiabatic compression/expansion)
        V_max = np.max(volume)
        C_motored = P_ATM * (V_max ** GAMMA)
        pressure_motored = C_motored / (volume ** GAMMA)

        # Volumetric efficiency curve (simple interpolated VE)
        ve = np.interp(rpm, [1000.0, 5500.0, 8500.0], [0.85, 0.98, 0.80])
        m_air = ve * (P_ATM * Vd) / (R_AIR * T_INTAKE)
        fuel_mass = m_air / AFR_STOICH
        Q_total = fuel_mass * LHV_DEFAULT

        # Combustion around TDC
        start_angle = 360.0
        duration = 40.0
        efficiency = 0.95
        x = wiebe_function(angle_arr, start_angle, duration, efficiency)
        Q_rel = Q_total * x

        pressure_comb = pressure_motored + (GAMMA - 1.0) * Q_rel / volume

        # Work integral for indicated work per cylinder
        work_single = np.trapz(pressure_comb, volume)  # J per cycle per cylinder
        torque_mean_single = work_single / (4.0 * math.pi)  # 720 deg = 4*pi rad
        torque_mean = torque_mean_single * self.engine.block.num_cylinders

        # Torque trace (scaled to engine) for plotting
        torque_trace_single = (pressure_comb - P_ATM) * dV_dtheta
        torque_trace = torque_trace_single * self.engine.block.num_cylinders

        omega = rpm * 2.0 * math.pi / 60.0
        mean_power_w = torque_mean * omega
        mean_power_hp = mean_power_w / 745.7

        return {
            "angle": angle_arr,
            "pressure": pressure_comb,
            "volume": volume,
            "torque": torque_trace,
            "mean_torque_nm": torque_mean,
            "mean_power_hp": mean_power_hp,
        }
