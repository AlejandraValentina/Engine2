"""0D thermodynamic cycle simulator for indicated torque/power estimates."""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np

from core.engine_components import Engine
from core.units import bar_to_pa, cc_to_m3, mm_to_m

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Nasa7Coeffs:
    t_mid: float
    low: Tuple[float, float, float, float, float, float, float]
    high: Tuple[float, float, float, float, float, float, float]


_NASA7_SPECIES = {
    "air": _Nasa7Coeffs(
        t_mid=1000.0,
        low=(3.5, 1.0e-4, 0.0, 0.0, 0.0, 0.0, 0.0),
        high=(3.2, 2.0e-4, 0.0, 0.0, 0.0, 0.0, 0.0),
    ),
    "burned": _Nasa7Coeffs(
        t_mid=1000.0,
        low=(3.9, 1.5e-4, 0.0, 0.0, 0.0, 0.0, 0.0),
        high=(3.6, 2.5e-4, 0.0, 0.0, 0.0, 0.0, 0.0),
    ),
}


def _nasa7_coeffs(species: str, T: float) -> Tuple[float, float, float, float, float, float, float]:
    data = _NASA7_SPECIES[species]
    return data.low if T <= data.t_mid else data.high


def _nasa7_cp_R(species: str, T: float) -> float:
    a1, a2, a3, a4, a5, _a6, _a7 = _nasa7_coeffs(species, T)
    return a1 + a2 * T + a3 * T ** 2 + a4 * T ** 3 + a5 * T ** 4


def _nasa7_h_RT(species: str, T: float) -> float:
    a1, a2, a3, a4, a5, a6, _a7 = _nasa7_coeffs(species, T)
    return (
        a1
        + a2 * T / 2.0
        + a3 * T ** 2 / 3.0
        + a4 * T ** 3 / 4.0
        + a5 * T ** 4 / 5.0
        + a6 / T
    )


def _nasa7_cp(species: str, T: float, gas_constant: float) -> float:
    return _nasa7_cp_R(species, T) * gas_constant


def _nasa7_h(species: str, T: float, gas_constant: float) -> float:
    return _nasa7_h_RT(species, T) * gas_constant * T


def thermally_perfect_cp(T: float, Y_fresh: float, gas_constant: float) -> float:
    Y = min(max(Y_fresh, 0.0), 1.0)
    cp_air = _nasa7_cp("air", T, gas_constant)
    cp_burned = _nasa7_cp("burned", T, gas_constant)
    return Y * cp_air + (1.0 - Y) * cp_burned


def thermally_perfect_h(T: float, Y_fresh: float, gas_constant: float) -> float:
    Y = min(max(Y_fresh, 0.0), 1.0)
    h_air = _nasa7_h("air", T, gas_constant)
    h_burned = _nasa7_h("burned", T, gas_constant)
    return Y * h_air + (1.0 - Y) * h_burned


def thermally_perfect_e(T: float, Y_fresh: float, gas_constant: float) -> float:
    h = thermally_perfect_h(T, Y_fresh, gas_constant)
    return h - gas_constant * T


def thermally_perfect_gamma(T: float, Y_fresh: float, gas_constant: float) -> float:
    cp = thermally_perfect_cp(T, Y_fresh, gas_constant)
    cv = cp - gas_constant
    if cv <= 0.0:
        raise ValueError("Invalid cv for thermally perfect gas")
    return cp / cv


def thermally_perfect_T_from_e(
    e_target: float,
    Y_fresh: float,
    gas_constant: float,
    T_guess: float | None = None,
    T_min: float = 200.0,
    T_max: float = 3500.0,
    max_iters: int = 6,
    tol: float = 1e-6,
    return_iterations: bool = False,
) -> float | Tuple[float, int]:
    if not math.isfinite(e_target):
        raise ValueError("e_target must be finite")
    T = T_guess if T_guess is not None else 300.0
    T = min(max(T, T_min), T_max)
    iters = 0
    for iters in range(1, max_iters + 1):
        e = thermally_perfect_e(T, Y_fresh, gas_constant)
        f = e - e_target
        if abs(f) <= tol * max(1.0, abs(e_target)):
            break
        cv = thermally_perfect_cp(T, Y_fresh, gas_constant) - gas_constant
        if cv <= 0.0:
            break
        T = T - f / cv
        T = min(max(T, T_min), T_max)
    if return_iterations:
        return T, iters
    return T


def piston_geometry(angle_array_deg: np.ndarray, bore: float, stroke: float, conrod: float):
    """Return swept volume and dV/dtheta for given crank angles.

    All geometry inputs are in millimeters; outputs are meters-based volumes.
    angle_array_deg is expected in crank degrees.
    """
    theta = np.deg2rad(angle_array_deg)
    r = mm_to_m(stroke) / 2.0  # crank radius (m)
    l = mm_to_m(conrod)  # rod length (m)
    area = math.pi * (mm_to_m(bore) ** 2) / 4.0

    sin_t = np.sin(theta)
    cos_t = np.cos(theta)
    under_sqrt = np.maximum(l ** 2 - (r * sin_t) ** 2, 1e-12)
    x = r * (1.0 - cos_t) + l - np.sqrt(under_sqrt)

    dx_dtheta = r * sin_t + (r ** 2 * sin_t * cos_t) / np.sqrt(under_sqrt)
    dV_dtheta = area * dx_dtheta  # derivative with respect to crank angle (radians)

    V_swept = area * x
    return V_swept, dV_dtheta


def wiebe_function(
    angle_array_deg: np.ndarray,
    start_angle: float,
    duration: float,
    a: float,
    m: float,
):
    """Return cumulative heat release fraction (0..1) using Wiebe."""
    theta = angle_array_deg
    x = np.zeros_like(theta)

    mask = (theta >= start_angle) & (theta <= start_angle + duration)
    theta_rel = (theta[mask] - start_angle) / duration
    expo = -a * theta_rel ** (m + 1)
    x_val = 1.0 - np.exp(expo)

    x[mask] = x_val
    x[theta > start_angle + duration] = 1.0
    return x


class CylinderSimulator:
    """Simple 0D cylinder thermodynamics to estimate pressure and torque."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self.engine.validate(strict=True)

    def _calculate_dynamic_ve(
        self,
        rpm: float,
        piston_speed: float,
        bore_m: float,
        duration: float,
        gamma_air: float,
        gas_constant: float,
        ambient_temp_k: float,
        return_debug: bool = False,
    ):
        """Estimate volumetric efficiency and Mach index with configurable choking."""
        cam_peak = max(getattr(self.engine.camshaft, "peak_rpm", 5500.0), 1500.0)
        rpm_points = [1000.0, cam_peak, cam_peak + 1500.0]

        cam_duration = duration
        peak_ve = np.interp(cam_duration, [200.0, 230.0, 260.0, 300.0], [1.0, 1.0, 1.1, 1.15])
        shape = [0.85 * peak_ve, 1.0 * peak_ve, 0.85 * peak_ve]
        base_curve = np.interp(rpm, rpm_points, shape)

        head = self.engine.head
        valve_mm = getattr(head, "intake_valve_diameter_mm", None)
        legacy_mm = getattr(head, "intake_valve_diameter", None)
        if legacy_mm is not None:
            if valve_mm is None or not math.isclose(float(valve_mm), float(legacy_mm), abs_tol=1e-6):
                valve_mm = legacy_mm
        if valve_mm is None:
            valve_mm = 35.0
        valve_diameter_m = float(valve_mm) * 1e-3

        eff = min(max(getattr(head, "port_flow_efficiency", 0.7), 0.1), 1.0)
        Av_geom = max(1e-9, head.intake_valves * math.pi * (valve_diameter_m / 2.0) ** 2)
        Av = Av_geom * eff
        Ap = max(1e-9, math.pi * (bore_m / 2.0) ** 2)
        area_ratio = Av / Ap
        area_threshold = float(getattr(head, "valve_area_ratio_threshold", 0.15))
        if area_threshold <= 0.0:
            area_threshold = 0.15
        area_penalty = 1.0
        if area_ratio < area_threshold:
            area_penalty = max(0.3, area_ratio / area_threshold)
        V_gas = piston_speed * (Ap / Av)
        c_sound = math.sqrt(max(gamma_air * gas_constant * ambient_temp_k, 1e-9))
        mach_index = V_gas / max(c_sound, 1e-9)

        mach_limit = getattr(head, "mach_tolerance", 0.75) or 0.75
        if mach_index < mach_limit:
            choke_factor = 1.0
        else:
            choke_factor = 1.0 - 1.2 * (mach_index - mach_limit) ** 2
            choke_factor = max(0.4, choke_factor)

        ve = max(0.2, base_curve * choke_factor * area_penalty)

        flow_loss = getattr(self.engine.intake, "flow_loss_coefficient", 0.0)
        flow_loss_factor = max(0.0, 1.0 - flow_loss)
        ve *= flow_loss_factor

        if return_debug:
            return ve, mach_index, base_curve, choke_factor, flow_loss_factor
        return ve, mach_index

    def run_cycle(
        self,
        rpm: float,
        exhaust_backpressure_trace: dict[str, np.ndarray] | None = None,
    ) -> Dict[str, np.ndarray]:
        """Run a 720° four-stroke cycle and return pressure/torque traces."""
        # Explicit phasing: 0-180 intake, 180-360 compression, 360-540 power,
        # 540-720 exhaust (angles always within one 720° four-stroke cycle).
        angle_arr = np.arange(0.0, 720.0 + 0.5, 0.5)

        settings = getattr(self.engine, "simulation_settings", None)
        heat_loss_factor = getattr(settings, "heat_loss_factor", 1.0)
        tuning_sensitivity = getattr(settings, "tuning_sensitivity", 1.0)
        ambient_temp_k = (getattr(settings, "air_temperature_c", 25.0) + 273.15)
        gas_constant = getattr(settings, "gas_constant_R", 287.0)
        cp_model = getattr(settings, "cp_model", "constant")
        gamma_air = getattr(settings, "gamma_air", 1.4)
        gamma_exh = getattr(settings, "gamma_exhaust", 1.35)
        if cp_model == "nasa7":
            gamma_air = thermally_perfect_gamma(ambient_temp_k, 1.0, gas_constant)
            gamma_exh = thermally_perfect_gamma(ambient_temp_k, 0.0, gas_constant)
        # Absolute ambient pressure (Pa)
        ambient_pressure_pa = bar_to_pa(getattr(settings, "air_pressure_bar", 1.013))

        cam = self.engine.camshaft
        comb = getattr(self.engine, "combustion", None)
        ignition = getattr(comb, "ignition_advance", 30.0)
        afr_user = getattr(comb, "afr", getattr(self.engine.fuel, "stoich_afr", 14.7))
        wiebe_a = getattr(comb, "wiebe_a", 5.0)
        wiebe_m = getattr(comb, "wiebe_m", 2.0)
        target_ca50 = getattr(comb, "target_ca50_deg_atdc", None)

        fuel_cfg = getattr(self.engine, "fuel", None)
        fuel_lhv = getattr(fuel_cfg, "energy_density", 44e6)
        fuel_stoich = afr_user
        fuel_octane = getattr(fuel_cfg, "octane_rating", 93.0)

        icl = cam.lobe_separation - cam.advance
        ecl = 720.0 - (cam.lobe_separation + cam.advance)
        IVC = float(np.clip(icl + (cam.intake_duration / 2.0), 180.0, 360.0))
        EVO = float(np.clip(ecl - (cam.exhaust_duration / 2.0), 480.0, 720.0))

        volume_swept, dV_dtheta = piston_geometry(
            angle_arr, self.engine.block.bore, self.engine.block.stroke, self.engine.block.conrod_length
        )

        bore_m = mm_to_m(self.engine.block.bore)
        stroke_m = mm_to_m(self.engine.block.stroke)
        area = math.pi * bore_m ** 2 / 4.0
        Vd = area * stroke_m

        # Port efficiency used across VE/tuning logic
        eff = min(max(getattr(self.engine.head, "port_flow_efficiency", 0.7), 0.1), 1.0)

        head = self.engine.head
        compression_ratio = max(head.compression_ratio, 1.01)
        if head.combustion_chamber_vol is not None and head.combustion_chamber_vol > 0.0:
            Vc = cc_to_m3(head.combustion_chamber_vol)
        else:
            Vc = Vd / (compression_ratio - 1.0)

        volume = np.maximum(volume_swept + Vc, 1e-9)

        def volume_at(angle_deg: float) -> float:
            idx = int(np.argmin(np.abs(angle_arr - angle_deg)))
            return max(volume[idx], 1e-9)

        V_IVC = max(volume_at(IVC), 1e-9)

        boost_bar = getattr(self.engine.supercharger, "boost_pressure_bar", 0.0)
        boost_pa = bar_to_pa(float(boost_bar))
        # Manifold pressure is always absolute: ambient + boost (boost may be zero for NA).
        P_manifold = ambient_pressure_pa + boost_pa
        T_boost = ambient_temp_k * (P_manifold / ambient_pressure_pa) ** 0.28
        intercooler_eff = getattr(self.engine.supercharger, "intercooler_efficiency", 0.70)
        T_charge = ambient_temp_k + (T_boost - ambient_temp_k) * (1.0 - intercooler_eff)

        piston_speed = 2.0 * stroke_m * rpm / 60.0
        base_ve, mach_index, ve_cam_factor, ve_mach_factor, ve_flow_loss_factor = self._calculate_dynamic_ve(
            rpm,
            piston_speed,
            bore_m,
            cam.intake_duration,
            gamma_air,
            gas_constant,
            ambient_temp_k,
            return_debug=True,
        )

        runner_length_m = max(mm_to_m(self.engine.intake.runner_length), 1e-6)
        runner_dia_m = max(mm_to_m(self.engine.intake.runner_diameter), 1e-6)

        runner_length_in = runner_length_m / 0.0254
        rpm_tune = 84000.0 / runner_length_in
        harmonics = [1.0, 0.7, 0.5]
        boosts = [0.15, 0.1, 0.08]
        tuning_boost = 0.0
        for h, b in zip(harmonics, boosts):
            peak = rpm_tune * h
            sigma = max(200.0, peak * 0.12)
            tuning_boost += b * math.exp(-0.5 * ((rpm - peak) / sigma) ** 2)
        exhaust_length_m = max(mm_to_m(self.engine.exhaust.header_primary_length), 1e-6)
        exhaust_dia_m = max(mm_to_m(self.engine.exhaust.header_primary_diameter), 1e-6)

        exhaust_length_in = exhaust_length_m / 0.0254
        exhaust_peak = 115000.0 / exhaust_length_in
        exhaust_sigma = max(300.0, exhaust_peak * 0.15)
        exhaust_boost = 0.15 * math.exp(-0.5 * ((rpm - exhaust_peak) / exhaust_sigma) ** 2)

        total_boost = (tuning_boost + exhaust_boost) * tuning_sensitivity
        tuning_factor = 1.0 + total_boost

        ivc_abdc = max(0.0, IVC - 180.0)
        rpm_ratio = min(max(rpm / 7000.0, 0.0), 1.0)
        reversion_factor = max(0.85, 1.0 - (ivc_abdc * 0.002 * (1.0 - rpm_ratio)))

        ve_prelim = np.clip(base_ve * tuning_factor * reversion_factor, 0.0, 1.5)
        ve_cam_factor = float(ve_cam_factor)
        ve_mach_factor = float(ve_mach_factor)
        ve_flow_loss_factor = float(ve_flow_loss_factor)

        bmep_est_bar = (P_manifold / 1e5) * ve_prelim * 10.0
        burn_duration = getattr(comb, "burn_duration", 50.0)
        if getattr(comb, "use_dynamic_burn_duration", False):
            base = getattr(comb, "burn_duration_base", burn_duration)
            k_rpm = getattr(comb, "burn_duration_rpm_factor", 0.0)
            k_load = getattr(comb, "burn_duration_load_factor", 0.0)
            burn_duration = base + k_rpm * (rpm / 1000.0) + k_load * bmep_est_bar
        burn_duration = max(burn_duration, 1.0)

        if target_ca50 is None and getattr(comb, "use_dynamic_ca50", False):
            base_ca50 = getattr(comb, "ca50_base_deg_atdc", 8.0)
            k_rpm = getattr(comb, "ca50_rpm_factor", 0.0)
            k_load = getattr(comb, "ca50_load_factor", 0.0)
            target_ca50 = base_ca50 + k_rpm * (rpm / 1000.0) + k_load * bmep_est_bar

        disp_cid = self.engine.block.displacement_cc * 0.0610237
        required_cfm = (disp_cid * rpm) / 3456.0 * ve_prelim
        head_supply_cfm = self.engine.head.port_flow_cfm * self.engine.head.intake_valves * self.engine.block.num_cylinders
        throttle_capacity = getattr(self.engine.intake, "throttle_cfm", None)
        if throttle_capacity is None:
            throttle_capacity = getattr(self.engine.intake, "throttle_flow_cfm", 500.0)
        throttle_capacity = 500.0 if throttle_capacity is None else throttle_capacity
        head_supply_cfm = max(head_supply_cfm, 0.0)
        throttle_capacity = max(throttle_capacity, 0.0)
        throttle_cfg = getattr(self.engine, "throttle", None)
        if throttle_cfg is not None and getattr(throttle_cfg, "enabled", False):
            pos = float(getattr(throttle_cfg, "position", 1.0))
            exp = float(getattr(throttle_cfg, "area_exponent", 2.0))
            pos = min(max(pos, 0.0), 1.0)
            exp = max(exp, 0.0)
            throttle_capacity *= pos ** exp
        supply_cfm = min(head_supply_cfm, throttle_capacity)
        eps = 1e-9
        flow_cap_factor = float(np.clip(supply_cfm / max(required_cfm, eps), 0.0, 1.0))

        ve_limited = np.clip(ve_prelim * flow_cap_factor, 0.0, 1.5)
        ve = ve_limited
        ve_flow_cap_factor = float(flow_cap_factor)

        m_air = ve * (P_manifold * V_IVC) / (gas_constant * T_charge)
        fuel_mass = m_air / fuel_stoich
        working_mass_kg = max(m_air + fuel_mass, 1e-12)
        eta_combustion = float(np.clip(getattr(self.engine.combustion, "thermal_efficiency", 0.95), 0.0, 1.0))
        Q_total = fuel_mass * fuel_lhv

        if target_ca50 is not None:
            safe_a = max(wiebe_a, 1e-6)
            phi50 = (math.log(2.0) / safe_a) ** (1.0 / (wiebe_m + 1.0))
            ca50_abs = 360.0 + float(target_ca50)
            start_angle = ca50_abs - burn_duration * phi50
        else:
            start_angle = 360.0 - float(ignition)
        x = wiebe_function(angle_arr, start_angle, burn_duration, a=wiebe_a, m=wiebe_m)
        Q_rel = Q_total * x
        dQ_chem = np.diff(Q_rel, prepend=0.0)

        mask_intake = angle_arr < IVC
        mask_exhaust = angle_arr >= EVO

        pressure = np.zeros_like(volume)
        pressure[mask_intake] = P_manifold
        backpressure_factor = getattr(settings, "exhaust_backpressure_factor", 1.05)
        default_backpressure = backpressure_factor * ambient_pressure_pa

        backpressure_trace = None
        if exhaust_backpressure_trace is not None:
            angle_bp = np.asarray(exhaust_backpressure_trace.get("angle", []), dtype=float)
            pressure_bp = np.asarray(exhaust_backpressure_trace.get("pressure", []), dtype=float)
            finite = np.isfinite(angle_bp) & np.isfinite(pressure_bp)
            if np.any(finite):
                angle_bp = angle_bp[finite]
                pressure_bp = pressure_bp[finite]
                order = np.argsort(angle_bp)
                angle_bp = angle_bp[order]
                pressure_bp = pressure_bp[order]
                if angle_bp.size >= 2:
                    backpressure_trace = np.interp(angle_arr, angle_bp, pressure_bp)
                else:
                    backpressure_trace = np.full_like(angle_arr, float(pressure_bp[0]))
                bp_min = getattr(settings, "clamp_p_min", 1e-6)
                bp_max = getattr(settings, "clamp_p_max", 1e9)
                backpressure_trace = np.clip(backpressure_trace, bp_min, bp_max)

        if backpressure_trace is None:
            backpressure_trace = np.full_like(angle_arr, default_backpressure)

        pressure[mask_exhaust] = backpressure_trace[mask_exhaust]

        deg_step = angle_arr[1] - angle_arr[0]
        dt = deg_step / 360.0 * 60.0 / max(rpm, 1e-3)
        piston_speed_mean = piston_speed
        head_area = area
        piston_area = area

        bore_mm = max(self.engine.block.bore, 1e-6)
        scale_factor = (85.0 / max(bore_mm, 20.0)) ** 0.5
        heat_loss_multiplier = scale_factor
        woschni_k = 0.006 * heat_loss_multiplier * (rpm ** 0.6) * heat_loss_factor

        idx_ivc = int(np.argmin(np.abs(angle_arr - IVC)))
        idx_evo = int(np.argmin(np.abs(angle_arr - EVO)))
        if idx_evo <= idx_ivc:
            idx_evo = max(idx_ivc + 1, idx_evo)

        p_current = P_manifold * (V_IVC / max(volume[idx_ivc], 1e-9)) ** gamma_air
        for idx in range(idx_ivc, idx_evo + 1):
            V_curr = max(volume[idx], 1e-9)
            x_disp = max((V_curr - Vc) / max(area, 1e-12), 0.0)
            area_wall = head_area + piston_area + (math.pi * bore_m * x_disp)

            T_gas = p_current * V_curr / max(working_mass_kg * gas_constant, 1e-9)
            w_mean = 2.28 * piston_speed_mean
            h_c = (
                woschni_k
                * (max(p_current, 1e-6) / 1000.0) ** 0.8
                * max(T_gas, 1e-3) ** -0.55
                * max(w_mean, 1e-6) ** 0.8
            )
            Q_loss = h_c * area_wall * max(T_gas - getattr(settings, "wall_temperature_k", 450.0), 0.0) * dt

            if cp_model == "nasa7":
                Y_fresh = 1.0 if angle_arr[idx] < 360.0 else 0.0
                gamma_curr = thermally_perfect_gamma(T_gas, Y_fresh, gas_constant)
            else:
                gamma_curr = gamma_air if angle_arr[idx] < 360.0 else gamma_exh
            dQ_net = eta_combustion * dQ_chem[idx] - Q_loss
            p_with_heat = p_current + (gamma_curr - 1.0) * dQ_net / max(V_curr, 1e-9)
            pressure[idx] = p_with_heat

            if idx < idx_evo:
                V_next = max(volume[idx + 1], 1e-9)
                p_current = p_with_heat * (V_curr / V_next) ** gamma_curr

        temperature = pressure * volume / max(working_mass_kg * gas_constant, 1e-9)
        exhaust_p_stag = pressure.copy()
        exhaust_t_stag = temperature.copy()

        if (not np.isfinite(pressure).all()) or (not np.isfinite(volume).all()):
            raise ValueError(
                f"Non-finite thermo state (rpm={rpm:.1f}, IVC={IVC:.2f}, EVO={EVO:.2f}, minV={float(np.min(volume)):.3e})"
            )

        torque_trace_single = (pressure - ambient_pressure_pa) * dV_dtheta
        torque_trace = torque_trace_single * self.engine.block.num_cylinders
        indicated_torque = float(np.mean(torque_trace))

        f_cfg = getattr(self.engine, "friction", None)
        f_base = getattr(f_cfg, "friction_base_kpa", 35.0) + 5.0
        f_lin = getattr(f_cfg, "friction_linear_factor", 0.02)
        f_quad = getattr(f_cfg, "friction_quadratic_factor", 1.8e-6)

        fmep_kpa = f_base + f_lin * rpm + f_quad * rpm * rpm

        be_type = (getattr(f_cfg, "bottom_end_type", "Standard") or "Standard").lower()
        if be_type == "performance":
            fmep_kpa *= 0.85
        elif be_type == "race":
            fmep_kpa *= 0.65
        else:
            fmep_kpa *= 1.05
        fmep_pa = fmep_kpa * 1000.0
        fmep_pa *= getattr(f_cfg, "global_scaling_factor", 1.0)

        displacement_m3 = max(cc_to_m3(self.engine.block.displacement_cc), 1e-9)
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

        # BMEP expressed in bar (absolute, derived from brake torque and displacement)
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

        trace = {
            "ve_prelim": float(ve_prelim),
            "ve_cam_factor": float(ve_cam_factor),
            "ve_mach_factor": float(ve_mach_factor),
            "ve_flow_cap_factor": float(ve_flow_cap_factor),
            "ve_final": float(ve),
            "eta_combustion_used": float(eta_combustion),
            "start_angle_used": float(start_angle),
            "burn_duration_used": float(burn_duration),
            "ca50_target_used": None if target_ca50 is None else float(target_ca50),
        }

        return {
            "angle": angle_arr,
            "pressure": pressure,
            "volume": volume,
            "temperature": temperature,
            "exhaust_p_stag": exhaust_p_stag,
            "exhaust_t_stag": exhaust_t_stag,
            "torque": torque_trace,
            "mean_torque_nm": brake_torque,
            "mean_power_hp": mean_power_hp,
            "mean_piston_speed": piston_speed,
            "ve": ve * 100.0,
            "ve_actual": ve,
            "ve_cam_factor": ve_cam_factor,
            "ve_mach_factor": ve_mach_factor,
            "ve_flow_loss_factor": ve_flow_loss_factor,
            "ve_flow_cap_factor": ve_flow_cap_factor,
            "ve_final": ve,
            "mach_index": mach_index,
            "friction_hp": friction_power_hp,
            "fmep_kpa": fmep_kpa,
            "friction_torque_nm": friction_torque,
            "accessory_torque_nm": accessories,
            "total_friction_torque_nm": total_friction_torque,
            "bmep_bar": bmep_bar,
            "airflow_cfm": actual_cfm,
            "knock_warning": knock_warning,
            "burn_duration_deg": burn_duration,
            "target_ca50_deg_atdc": target_ca50,
            "trace": trace,
        }
    def run_pro_cycle(self, rpm: float) -> Dict[str, np.ndarray]:
        """Pro dyno path currently reuses the calibrated quick cycle."""
        return self.run_cycle(rpm)

