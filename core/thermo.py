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
THERMAL_EFFICIENCY = 0.62  # accounts for heat losses to coolant and walls
SPEED_OF_SOUND = 340.0  # m/s approximate at 300 K


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

        cam = self.engine.camshaft
        intake_centerline = cam.lobe_separation - cam.advance
        exhaust_centerline = cam.lobe_separation + cam.advance

        IVC = intake_centerline + (cam.intake_duration / 2.0) + 180.0
        EVO = 540.0 - (exhaust_centerline + (cam.exhaust_duration / 2.0))

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

        # Helper to fetch volume at a specific crank angle
        def volume_at(angle_deg: float) -> float:
            idx = int(np.argmin(np.abs(angle_arr - angle_deg)))
            return volume[idx]

        V_IVC = volume_at(IVC)

        boost_bar = getattr(self.engine.supercharger, "boost_pressure_bar", 0.0)
        boost_pa = float(boost_bar) * 100000.0
        is_boosted = (getattr(self.engine.supercharger, "type", "NA") or "NA") != "NA"
        P_manifold = P_ATM + boost_pa if is_boosted and boost_pa > 0.0 else P_ATM
        # Account for charge heating from compression with simple exponent (k-1)/k ~= 0.28
        T_boost = T_INTAKE * (P_manifold / P_ATM) ** 0.28
        intercooler_eff = 0.7
        T_charge = T_INTAKE + (T_boost - T_INTAKE) * (1.0 - intercooler_eff)

        # Volumetric efficiency driven by Taylor's Mach index (valve choke) with intake
        # runner acoustic tuning (Chrysler/Helmholtz-inspired).
        stroke_m = self.engine.block.stroke * 1e-3
        piston_speed = 2.0 * stroke_m * rpm / 60.0  # mean piston speed (m/s)

        valve_diameter_mm = getattr(
            self.engine.head, "intake_valve_diameter", self.engine.intake.runner_diameter
        )
        valve_diameter_m = valve_diameter_mm * 1e-3
        flow_coeff = 0.7
        Av = max(
            1e-9,
            self.engine.head.intake_valves * math.pi * (valve_diameter_m / 2.0) ** 2 * flow_coeff,
        )
        Ap = max(1e-9, math.pi * (bore_m / 2.0) ** 2)
        mach_index = (Ap / Av) * (piston_speed / SPEED_OF_SOUND)

        base_ve = 0.95
        if mach_index <= 0.5:
            ve_penalty = 1.0
        else:
            ve_penalty = max(0.0, 1.0 - 2.5 * (mach_index - 0.5) ** 2)

        # Intake runner tuning based on pulse reflections. Convert runner length to inches
        # for the classic 84k / L formula.
        runner_length_m = max(1e-6, self.engine.intake.runner_length * 1e-3)
        runner_length_in = runner_length_m / 0.0254
        rpm_tune = 84000.0 / runner_length_in

        harmonics = [1.0, 0.7, 0.5]  # 2nd, 3rd, 4th harmonic multipliers
        peak_boosts = [0.15, 0.1, 0.08]
        sigma_factors = [0.12, 0.12, 0.12]

        tuning_boost = 0.0
        for harmonic, boost, sigma_factor in zip(harmonics, peak_boosts, sigma_factors):
            peak_rpm = rpm_tune * harmonic
            sigma = max(200.0, peak_rpm * sigma_factor)
            tuning_boost += boost * math.exp(-0.5 * ((rpm - peak_rpm) / sigma) ** 2)

        tuning_factor = 1.0 + tuning_boost

        ivc_abdc = max(0.0, IVC - 180.0)
        rpm_ratio = min(max(rpm / 7000.0, 0.0), 1.0)
        reversion_factor = max(0.0, 1.0 - (ivc_abdc * 0.005 * (1.0 - rpm_ratio)))

        ve_base = np.clip(base_ve * ve_penalty * tuning_factor * reversion_factor, 0.0, 1.2)

        # Flowbench/throttle restriction using CFM limits
        disp_cid = self.engine.block.displacement_cc * 0.0610237  # cc to cubic inches
        required_cfm = (disp_cid * rpm) / 3456.0 * ve_base
        head_capacity = self.engine.head.port_flow_cfm * self.engine.head.intake_valves
        throttle_capacity = getattr(self.engine.intake, "throttle_cfm", 500.0)
        total_capacity = max(1e-6, min(head_capacity, throttle_capacity))
        if required_cfm <= total_capacity:
            restriction_penalty = 1.0
        else:
            restriction_penalty = (total_capacity / required_cfm) ** 0.5

        ve = np.clip(ve_base * restriction_penalty, 0.0, 1.2)

        m_air = ve * (P_manifold * Vd) / (R_AIR * T_charge)
        fuel_mass = m_air / AFR_STOICH
        Q_total = fuel_mass * LHV_DEFAULT
        Q_effective = Q_total * THERMAL_EFFICIENCY

        # Wiebe heat release during power stroke (advanced ignition)
        start_angle = 350.0
        duration = 60.0
        efficiency = 0.95
        x = wiebe_function(angle_arr, start_angle, duration, efficiency)
        Q_rel = Q_effective * x

        # Phase masks driven by cam events
        mask_intake = angle_arr < IVC
        mask_compression = (angle_arr >= IVC) & (angle_arr < 360.0)
        mask_power = (angle_arr >= 360.0) & (angle_arr < EVO)
        mask_exhaust = angle_arr >= EVO

        pressure = np.zeros_like(volume)

        # Intake: manifold pressure (atmospheric for NA, elevated for boost)
        pressure[mask_intake] = P_manifold

        # Exhaust: elevated backpressure
        pressure[mask_exhaust] = 1.05 * P_ATM

        # Compression: adiabatic from intake valve closing forward
        C_comp = P_manifold * (V_IVC**GAMMA)
        pressure[mask_compression] = C_comp / (volume[mask_compression] ** GAMMA)

        # Power: motored expansion plus heat release
        C_power = C_comp  # same constant continues across TDC
        pressure_mot_power = C_power / (volume[mask_power] ** GAMMA)
        pressure[mask_power] = pressure_mot_power + (GAMMA - 1.0) * Q_rel[mask_power] / volume[mask_power]

        # Torque trace scaled by cylinder count
        torque_trace_single = (pressure - P_ATM) * dV_dtheta
        torque_trace = torque_trace_single * self.engine.block.num_cylinders

        # Indicated mean torque via average of trace over full 720 deg
        indicated_torque = float(np.mean(torque_trace))

        # Mechanical friction/pumping losses (simple FMEP-derived torque estimate)
        friction_torque = 15.0 + (rpm * 0.005) + (rpm ** 2 * 1e-6)
        brake_torque = indicated_torque - friction_torque

        omega = rpm * 2.0 * math.pi / 60.0
        mean_power_w = brake_torque * omega
        mean_power_hp = mean_power_w / 745.7

        return {
            "angle": angle_arr,
            "pressure": pressure,
            "volume": volume,
            "torque": torque_trace,
            "mean_torque_nm": brake_torque,
            "mean_power_hp": mean_power_hp,
        }
