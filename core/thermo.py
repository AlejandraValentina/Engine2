"""0D thermodynamic cycle simulator for indicated torque/power estimates."""
from __future__ import annotations

import logging
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
SPEED_OF_SOUND = 340.0  # m/s approximate at 300 K

logger = logging.getLogger(__name__)


def piston_geometry(angle_array_deg: np.ndarray, bore: float, stroke: float, conrod: float):
    """Return swept volume and dV/dtheta for given crank angles.

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

    V_swept = area * x
    return V_swept, dV_dtheta


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

    def _calculate_dynamic_ve(self, rpm: float, piston_speed: float, bore_m: float, duration: float):
        """Estimate volumetric efficiency and Mach index with configurable choking."""
        cam_peak = max(getattr(self.engine.camshaft, "peak_rpm", 5500.0), 1500.0)
        rpm_points = [1000.0, cam_peak, cam_peak + 1500.0]

        cam_duration = duration
        peak_ve = np.interp(cam_duration, [200.0, 230.0, 260.0, 300.0], [1.0, 1.0, 1.1, 1.15])
        shape = [0.85 * peak_ve, 1.0 * peak_ve, 0.85 * peak_ve]
        base_curve = np.interp(rpm, rpm_points, shape)

        head = self.engine.head
        valve_mm = getattr(head, "intake_valve_diameter_mm", None)
        if valve_mm is None:
            valve_mm = getattr(head, "intake_valve_diameter", 35.0)
        valve_diameter_m = valve_mm * 1e-3

        eff = min(max(getattr(head, "port_flow_efficiency", 0.7), 0.1), 1.0)
        Av_geom = max(1e-9, head.intake_valves * math.pi * (valve_diameter_m / 2.0) ** 2)
        Av = Av_geom * eff
        Ap = max(1e-9, math.pi * (bore_m / 2.0) ** 2)
        V_gas = piston_speed * (Ap / Av)
        mach_index = V_gas / SPEED_OF_SOUND

        mach_limit = getattr(head, "mach_tolerance", 0.75) or 0.75
        if mach_index < mach_limit:
            choke_factor = 1.0
        else:
            choke_factor = 1.0 - 1.2 * (mach_index - mach_limit) ** 2
            choke_factor = max(0.4, choke_factor)

        print(
            f"[DEBUG VE] RPM={rpm:.0f} PistonSpd={piston_speed:.1f} GasVel={V_gas:.1f} Mach={mach_index:.2f} ChokeFactor={choke_factor:.2f}"
        )

        ve = max(0.2, base_curve * choke_factor)

        flow_loss = getattr(self.engine.intake, "flow_loss_coefficient", 0.0)
        ve *= max(0.0, 1.0 - flow_loss)

        return ve, mach_index

    def run_cycle(self, rpm: float) -> Dict[str, np.ndarray]:
        """Run a 720° four-stroke cycle and return pressure/torque traces."""
        angle_arr = np.arange(0.0, 720.0 + 0.5, 0.5)

        cam = self.engine.camshaft
        comb = getattr(self.engine, "combustion", None)
        ignition = getattr(comb, "ignition_advance", 30.0)
        burn_duration = getattr(comb, "burn_duration", 50.0)
        thermal_eff = getattr(comb, "thermal_efficiency", 0.5)
        afr_user = getattr(comb, "afr", AFR_STOICH)

        fuel_cfg = getattr(self.engine, "fuel", None)
        fuel_lhv = getattr(fuel_cfg, "energy_density", LHV_DEFAULT) or LHV_DEFAULT
        fuel_stoich = afr_user
        fuel_octane = getattr(fuel_cfg, "octane_rating", 93.0)

        icl = cam.lobe_separation - cam.advance
        ecl = 720.0 - (cam.lobe_separation + cam.advance)
        IVC = float(np.clip(icl + (cam.intake_duration / 2.0), 180.0, 360.0))
        EVO = float(np.clip(ecl - (cam.exhaust_duration / 2.0), 480.0, 720.0))

        volume_swept, dV_dtheta = piston_geometry(
            angle_arr, self.engine.block.bore, self.engine.block.stroke, self.engine.block.conrod_length
        )

        bore_m = self.engine.block.bore * 1e-3
        stroke_m = self.engine.block.stroke * 1e-3
        area = math.pi * bore_m ** 2 / 4.0
        Vd = area * stroke_m

        head = self.engine.head
        compression_ratio = max(head.compression_ratio, 1.01)
        if head.combustion_chamber_vol is not None and head.combustion_chamber_vol > 0.0:
            Vc = head.combustion_chamber_vol * 1e-6
        else:
            Vc = Vd / (compression_ratio - 1.0)

        volume = np.maximum(volume_swept + Vc, 1e-9)

        def volume_at(angle_deg: float) -> float:
            idx = int(np.argmin(np.abs(angle_arr - angle_deg)))
            return max(volume[idx], 1e-9)

        V_IVC = max(volume_at(IVC), 1e-9)

        boost_bar = getattr(self.engine.supercharger, "boost_pressure_bar", 0.0)
        boost_pa = float(boost_bar) * 100000.0
        is_boosted = (getattr(self.engine.supercharger, "type", "NA") or "NA") != "NA"
        P_manifold = P_ATM + boost_pa if is_boosted and boost_pa > 0.0 else P_ATM
        T_boost = T_INTAKE * (P_manifold / P_ATM) ** 0.28
        intercooler_eff = 0.7
        T_charge = T_INTAKE + (T_boost - T_INTAKE) * (1.0 - intercooler_eff)

        piston_speed = 2.0 * stroke_m * rpm / 60.0
        base_ve, mach_index = self._calculate_dynamic_ve(rpm, piston_speed, bore_m, cam.intake_duration)

        runner_length_m = max(self.engine.intake.runner_length * 1e-3, 1e-6)
        runner_dia_m = max(self.engine.intake.runner_diameter * 1e-3, 1e-6)

        runner_length_in = runner_length_m / 0.0254
        rpm_tune = 84000.0 / runner_length_in
        harmonics = [1.0, 0.7, 0.5]
        boosts = [0.15, 0.1, 0.08]
        tuning_boost = 0.0
        for h, b in zip(harmonics, boosts):
            peak = rpm_tune * h
            sigma = max(200.0, peak * 0.12)
            tuning_boost += b * math.exp(-0.5 * ((rpm - peak) / sigma) ** 2)
        tuning_factor = 1.0 + tuning_boost

        exhaust_length_m = max(self.engine.exhaust.header_primary_length * 1e-3, 1e-6)
        exhaust_dia_m = max(self.engine.exhaust.header_primary_diameter * 1e-3, 1e-6)

        exhaust_length_in = exhaust_length_m / 0.0254
        exhaust_peak = 115000.0 / exhaust_length_in
        exhaust_sigma = max(300.0, exhaust_peak * 0.15)
        exhaust_boost = 0.15 * math.exp(-0.5 * ((rpm - exhaust_peak) / exhaust_sigma) ** 2)
        tuning_factor *= 1.0 + exhaust_boost

        ivc_abdc = max(0.0, IVC - 180.0)
        rpm_ratio = min(max(rpm / 7000.0, 0.0), 1.0)
        reversion_factor = max(0.0, 1.0 - (ivc_abdc * 0.002 * (1.0 - rpm_ratio)))

        ve_prelim = np.clip(base_ve * tuning_factor * reversion_factor, 0.0, 1.5)

        disp_cid = self.engine.block.displacement_cc * 0.0610237
        required_cfm = (disp_cid * rpm) / 3456.0 * ve_prelim
        head_capacity_total = (
            self.engine.head.port_flow_cfm
            * self.engine.head.intake_valves
            * self.engine.block.num_cylinders
            * 0.9
        )
        throttle_capacity = getattr(self.engine.intake, "throttle_cfm", 500.0)
        total_capacity = max(1e-6, min(head_capacity_total, throttle_capacity))
        restriction_penalty = 1.0 if required_cfm <= total_capacity else (total_capacity / required_cfm) ** 0.5

        intake_loss_factor = (runner_length_m / max(runner_dia_m, 1e-9)) * 0.002
        exhaust_loss_factor = (exhaust_length_m / max(exhaust_dia_m, 1e-9)) * 0.002
        total_loss = max(0.0, intake_loss_factor + exhaust_loss_factor)

        ve = np.clip(ve_prelim * restriction_penalty * max(0.0, 1.0 - total_loss), 0.0, 1.2)

        m_air = ve * (P_manifold * V_IVC) / (R_AIR * T_charge)
        fuel_mass = m_air / fuel_stoich
        Q_total = fuel_mass * fuel_lhv
        Q_effective = Q_total * thermal_eff

        start_angle = 360.0 - float(ignition)
        x = wiebe_function(angle_arr, start_angle, burn_duration, efficiency=1.0)
        Q_rel = Q_effective * x

        mask_intake = angle_arr < IVC
        mask_compression = (angle_arr >= IVC) & (angle_arr < 360.0)
        mask_power = (angle_arr >= 360.0) & (angle_arr < EVO)
        mask_exhaust = angle_arr >= EVO

        pressure = np.zeros_like(volume)
        pressure[mask_intake] = P_manifold
        pressure[mask_exhaust] = 1.05 * P_ATM

        vol_comp = np.maximum(volume[mask_compression], 1e-9)
        vol_pow = np.maximum(volume[mask_power], 1e-9)

        C_comp = P_manifold * (V_IVC ** GAMMA)
        pressure[mask_compression] = C_comp / (vol_comp ** GAMMA)

        C_power = C_comp
        pressure_mot_power = C_power / (vol_pow ** GAMMA)
        pressure_combustion_rise = (GAMMA - 1.0) * Q_rel[mask_power] / vol_pow
        pressure[mask_power] = pressure_mot_power + pressure_combustion_rise

        if (not np.isfinite(pressure).all()) or (not np.isfinite(volume).all()):
            raise ValueError(
                f"Non-finite thermo state (rpm={rpm:.1f}, IVC={IVC:.2f}, EVO={EVO:.2f}, minV={float(np.min(volume)):.3e})"
            )

        torque_trace_single = (pressure - P_ATM) * dV_dtheta
        torque_trace = torque_trace_single * self.engine.block.num_cylinders
        indicated_torque = float(np.mean(torque_trace))

        f_cfg = getattr(self.engine, "friction", None)
        f_base = getattr(f_cfg, "friction_base_kpa", 35.0) + 5.0  # bump base by 5 kPa
        f_lin = getattr(f_cfg, "friction_linear_factor", 0.02)
        f_quad = getattr(f_cfg, "friction_quadratic_factor", 1.8e-6)

        fmep_kpa = f_base + f_lin * rpm + f_quad * rpm * rpm

        be_type = (getattr(f_cfg, "bottom_end_type", "Standard") or "Standard").lower()
        if be_type == "performance":
            fmep_kpa *= 0.9
        elif be_type == "race":
            fmep_kpa *= 0.72
        fmep_pa = fmep_kpa * 1000.0

        displacement_m3 = max(self.engine.block.displacement_cc * 1e-6, 1e-9)
        friction_torque = fmep_pa * displacement_m3 / (4.0 * math.pi)

        accessories = 0.0
        if getattr(f_cfg, "water_pump", True):
            accessories += 0.5 + (rpm / 10000.0) ** 2 * 2.0
        if getattr(f_cfg, "alternator", True):
            accessories += 2.0
        if getattr(f_cfg, "power_steering", True):
            accessories += 3.0
        if getattr(f_cfg, "mechanical_fan", False):
            accessories += 0.1 + (rpm / 5000.0) ** 3 * 5.0

        total_friction_torque = friction_torque + accessories
        brake_torque = max(0.0, indicated_torque - total_friction_torque)

        dynamic_cr = max(V_IVC, 1e-9) / max(Vc, 1e-9)
        req_octane = dynamic_cr * 12.0 - 20.0
        knock_warning = False
        if req_octane > fuel_octane:
            knock_warning = True
            knock_gap = req_octane - fuel_octane
            penalty = max(0.3, 1.0 - 0.05 * knock_gap)
            brake_torque *= penalty

        omega = rpm * 2.0 * math.pi / 60.0
        mean_power_w = brake_torque * omega
        mean_power_hp = mean_power_w / 745.7
        friction_power_hp = total_friction_torque * omega / 745.7

        bmep_bar = brake_torque * 4.0 * math.pi / displacement_m3 / 100000.0

        actual_cfm = (disp_cid * rpm) / 3456.0 * ve

        logger.debug(
            "rpm=%.1f IVC=%.2f EVO=%.2f Vc=%.3e minV=%.3e V_IVC=%.3e ve=%.3f Ti=%.3f Tf=%.3f Tb=%.3f",
            rpm,
            IVC,
            EVO,
            Vc,
            float(np.min(volume)),
            V_IVC,
            ve,
            indicated_torque,
            total_friction_torque,
            brake_torque,
        )

        return {
            "angle": angle_arr,
            "pressure": pressure,
            "volume": volume,
            "torque": torque_trace,
            "mean_torque_nm": brake_torque,
            "mean_power_hp": mean_power_hp,
            "mean_piston_speed": piston_speed,
            "ve": ve * 100.0,
            "ve_actual": ve,
            "mach_index": mach_index,
            "friction_hp": friction_power_hp,
            "bmep_bar": bmep_bar,
            "airflow_cfm": actual_cfm,
            "knock_warning": knock_warning,
        }

    def run_pro_cycle(self, rpm: float) -> Dict[str, np.ndarray]:
        """Pro dyno path currently reuses the calibrated quick cycle."""
        return self.run_cycle(rpm)
