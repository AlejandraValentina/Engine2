from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

import logging

from core.advanced.combustion import CombustionConfig
from core.advanced.coupling import ValveTiming
from core.advanced.orchestrator import (
    Orchestrator,
    OrchestratorConfig,
    _build_valve_timing,
    _fmep_from_engine,
)
from core.engine_components import Engine


@dataclass
class ProDynoV2Result:
    rpm: int
    mean_power_hp: float
    mean_torque_nm: float
    ve_real: float
    residual_frac: float


class ProDynoV2Runner:
    """Run the v2 Advanced Core for Pro Dyno sweeps."""

    def __init__(self, engine: Engine, settings: Optional[dict[str, Any]] = None) -> None:
        self.engine = engine
        self.settings = settings or {}
        self._last_state: Optional[dict[str, Any]] = None

    def _build_orchestrator(self, warm_start: bool) -> Orchestrator:
        max_cycles = int(self.settings.get("max_cycles", 4))
        if warm_start:
            max_cycles = max(2, min(max_cycles, 3))
        cp_value = self.settings.get("cp") if "cp" in self.settings else None
        pipe_role = str(self.settings.get("pipe_role", "intake"))
        if pipe_role not in ("intake", "exhaust"):
            raise ValueError("pipe_role must be 'intake' or 'exhaust'")
        combustion_cfg = self._combustion_from_engine()
        gamma_default = (
            self.engine.simulation_settings.gamma_exhaust
            if pipe_role == "exhaust"
            else self.engine.simulation_settings.gamma_air
        )
        cfg = OrchestratorConfig(
            gamma=float(self.settings.get("gamma", gamma_default)),
            gas_constant=float(self.settings.get("gas_constant", self.engine.simulation_settings.gas_constant_R)),
            cp=float(cp_value) if cp_value is not None else None,
            cp_model=str(self.engine.simulation_settings.cp_model),
            cfl=float(self.settings.get("cfl", 0.5)),
            dt_max=float(self.settings.get("dt_max", 5e-5)),
            max_cycles=max_cycles,
            combustion=combustion_cfg,
            pipe_role=pipe_role,
        )
        return Orchestrator(cfg)

    def _default_pipe(self) -> tuple[int, float, float]:
        cells = int(self.settings.get("pipe_cells", 40))
        length_m = float(self.settings.get("pipe_length_m", 0.6))
        diameter_m = float(self.settings.get("pipe_diameter_m", 0.04))
        return cells, length_m, diameter_m

    def _default_valve(self) -> ValveTiming:
        pipe_role = str(self.settings.get("pipe_role", "intake"))
        valve = _build_valve_timing(self.engine, pipe_role)
        if "valve_cd" in self.settings:
            valve.cd = float(self.settings["valve_cd"])
        return valve

    def _combustion_from_engine(self) -> CombustionConfig:
        comb = self.engine.combustion
        fuel_cfg = self.engine.simulation_settings.fuel
        cfg = CombustionConfig(
            enabled=True,
            afr_stoich=float(comb.afr) if comb.afr > 0.0 else 14.7,
            fuel_lhv=float(fuel_cfg.lhv_j_per_kg) if fuel_cfg.lhv_j_per_kg > 0.0 else 43e6,
            eta_comb_base=float(min(max(comb.thermal_efficiency, 0.0), 1.0)),
            wiebe_a=float(comb.wiebe_a),
            wiebe_m=float(comb.wiebe_m),
            start_angle_deg_atdc=-float(comb.ignition_advance),
            duration_deg=float(comb.burn_duration),
        )
        residual = comb.residual_coupling or {}
        if "eta_comb_residual_k" in residual:
            cfg.eta_comb_residual_k = float(residual["eta_comb_residual_k"])
        if "duration_residual_k" in residual:
            cfg.duration_residual_k = float(residual["duration_residual_k"])
        if "clamp_X_res" in residual and isinstance(residual["clamp_X_res"], (list, tuple)):
            vals = residual["clamp_X_res"]
            if len(vals) == 2:
                cfg.clamp_X_res = (float(vals[0]), float(vals[1]))
        return cfg

    def run_point(self, rpm: int, warm_start_state: Optional[dict[str, Any]] = None) -> tuple[dict[str, Any], dict[str, Any]]:
        warm_start = warm_start_state is not None
        settle_cycles = int(self.settings.get("settle_cycles", 0))
        if settle_cycles < 0:
            raise ValueError("settle_cycles must be non-negative")
        extra_cycles = settle_cycles if not warm_start else 0
        orchestrator = self._build_orchestrator(warm_start)
        if extra_cycles > 0:
            orchestrator.cfg.max_cycles = int(orchestrator.cfg.max_cycles + extra_cycles)
        cells, length_m, diameter_m = self._default_pipe()
        block = self.engine.block
        bore_m = float(block.bore) * 1e-3
        stroke_m = float(block.stroke) * 1e-3
        conrod_m = float(block.conrod_length) * 1e-3
        area = math.pi * (bore_m * 0.5) ** 2
        clearance_m3 = area * stroke_m / max(self.engine.head.compression_ratio - 1.0, 1e-6)

        valve = self._default_valve()
        result = orchestrator.run(
            rpm=float(rpm),
            pipe_cells=cells,
            pipe_length_m=length_m,
            pipe_diameter_m=diameter_m,
            bore_m=bore_m,
            stroke_m=stroke_m,
            conrod_m=conrod_m,
            clearance_m3=clearance_m3,
            valve=valve,
        )

        work_history = result.get("indicated_work", [])
        ve_cycle_history = result.get("ve_cycle", [])
        if extra_cycles > 0 and len(work_history) > extra_cycles:
            work_eval = work_history[extra_cycles:]
            ve_eval = ve_cycle_history[extra_cycles:] if ve_cycle_history else []
        else:
            work_eval = work_history
            ve_eval = ve_cycle_history if ve_cycle_history else []
        chosen_index = max(len(work_eval) - 1, 0)
        indicated_work = work_eval[chosen_index] if work_eval else 0.0
        if orchestrator.cfg.combustion.enabled and indicated_work < 0.0:
            nonneg_idxs = [idx for idx, work in enumerate(work_eval) if work >= 0.0]
            if nonneg_idxs:
                chosen_index = max(nonneg_idxs, key=lambda idx: work_eval[idx])
                indicated_work = work_eval[chosen_index]
        disp_per_cyl_m3 = area * stroke_m
        disp_total_m3 = disp_per_cyl_m3 * self.engine.block.num_cylinders
        indicated_work_total = indicated_work * self.engine.block.num_cylinders
        indicated_torque_nm = indicated_work_total / (2.0 * math.pi)
        omega = float(rpm) * 2.0 * math.pi / 60.0
        fmep_pa = _fmep_from_engine(self.engine, float(rpm))
        friction_torque_nm = fmep_pa * disp_total_m3 / (4.0 * math.pi)
        mean_torque_nm = indicated_torque_nm - friction_torque_nm
        mean_power_hp = mean_torque_nm * omega / 745.7

        ve_real = max(result["ve"], default=0.0)
        if ve_eval and chosen_index < len(ve_eval):
            ve_real = float(ve_eval[chosen_index])
        p_ref = float(self.engine.simulation_settings.air_pressure_bar) * 100000.0
        t_ref = float(self.engine.simulation_settings.air_temperature_c) + 273.15
        rho_ref = p_ref / max(self.engine.simulation_settings.gas_constant_R * t_ref, 1e-9)
        rho_base = 1.2
        if rho_ref > 0.0:
            ve_real = ve_real * (rho_base / rho_ref)
        trapped = result["trapped_mass"][-1] if result["trapped_mass"] else 0.0
        residual = 1.0 - min(trapped / max(result["trapped_mass"][0], 1e-9), 1.0) if result["trapped_mass"] else 0.0

        out = {
            "mean_power_hp": mean_power_hp,
            "mean_torque_nm": mean_torque_nm,
            "ve_real": ve_real,
            "residual_frac": residual,
        }
        min_periodicity = self.settings.get("min_periodicity")
        report_status = bool(self.settings.get("report_status")) or min_periodicity is not None
        periodicity_error = None
        if report_status or min_periodicity is not None:
            history = result.get("convergence_history", [])
            if history:
                periodicity_error = history[-1].get("err_periodicity_1d")
        if report_status or min_periodicity is not None:
            status = "ok"
            reason = ""
            if min_periodicity is not None and periodicity_error is not None:
                if periodicity_error > float(min_periodicity):
                    status = "failed"
                    reason = "not_converged"
            if status == "ok" and orchestrator.cfg.combustion.enabled:
                if indicated_work < 0.0 or mean_torque_nm < 0.0:
                    status = "failed"
                    reason = "motoring"
            out["periodicity_error"] = float(periodicity_error) if periodicity_error is not None else None
            out["status"] = status
            if reason:
                out["reason"] = reason
        if bool(self.settings.get("debug_dyno_v2")) and rpm == 7000:
            logger = logging.getLogger(__name__)
            m_fresh_peak = ve_real * rho_ref * disp_per_cyl_m3
            logger.info(
                "v2 dyno VE debug rpm=%d ve=%.4f m_fresh=%.6e rho_ref=%.3f disp=%.6e",
                rpm,
                ve_real,
                m_fresh_peak,
                rho_ref,
                disp_per_cyl_m3,
            )
        state_out = {
            "last_result": result,
            "convergence_history": result.get("convergence_history", []),
            "convergence_tol": orchestrator.cfg.convergence_tol,
        }
        return out, state_out

    def run_sweep(self, rpm_values: list[int]) -> dict[str, list[float]]:
        results = {
            "rpm": [],
            "mean_power_hp": [],
            "mean_torque_nm": [],
            "ve_real": [],
            "residual_frac": [],
        }
        min_periodicity = self.settings.get("min_periodicity")
        drop_invalid = bool(self.settings.get("drop_invalid", False))
        report_status = bool(self.settings.get("report_status")) or min_periodicity is not None or drop_invalid
        rpm_start_safe = bool(self.settings.get("rpm_start_safe", False))
        warm_state: Optional[dict[str, Any]] = None
        if rpm_start_safe and rpm_values:
            safe_floor = int(self.settings.get("rpm_safe_floor", 2000))
            if rpm_values[0] < safe_floor:
                _, warm_state = self.run_point(safe_floor, warm_state)
        if report_status:
            results["status"] = []
            results["periodicity_error"] = []
            results["reason"] = []
        for rpm in rpm_values:
            try:
                result, warm_state = self.run_point(int(rpm), warm_state)
            except (RuntimeError, ValueError) as exc:
                if not (report_status or drop_invalid or min_periodicity is not None):
                    raise
                status = "failed"
                reason = "solver_error"
                if drop_invalid:
                    warm_state = None
                    continue
                result = {
                    "mean_power_hp": 0.0,
                    "mean_torque_nm": 0.0,
                    "ve_real": 0.0,
                    "residual_frac": 0.0,
                    "status": status,
                    "reason": reason,
                    "periodicity_error": None,
                }
            status = str(result.get("status", "ok"))
            if drop_invalid and status != "ok":
                warm_state = None
                continue
            results["rpm"].append(int(rpm))
            results["mean_power_hp"].append(float(result["mean_power_hp"]))
            results["mean_torque_nm"].append(float(result["mean_torque_nm"]))
            results["ve_real"].append(float(result["ve_real"]))
            results["residual_frac"].append(float(result["residual_frac"]))
            if report_status:
                results["status"].append(status)
                results["periodicity_error"].append(result.get("periodicity_error"))
                results["reason"].append(result.get("reason", ""))
        self._last_state = warm_state
        if warm_state:
            results["convergence_history"] = warm_state.get("convergence_history", [])
            results["convergence_tol"] = warm_state.get("convergence_tol")
        return results
