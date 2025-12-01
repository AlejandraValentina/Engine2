"""Network-capable 1D gas solver tying engine data to numerics."""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np

from core import numerics
from core.junctions import Junction
from core.model import Pipe


def _init_pipe_state(pipe_data: Pipe, target_dx: float, p_atm: float, T_amb: float):
    L = float(pipe_data.length)
    estimated_N = int(np.ceil(L / target_dx))
    N = max(estimated_N, 50)
    dx = L / N

    diam_in = float(pipe_data.diameter_inlet)
    diam_out = float(pipe_data.diameter_outlet)
    diameters = np.linspace(diam_in, diam_out, N)
    areas = math.pi * (diameters * 0.5) ** 2
    friction_coeffs = np.full(N, pipe_data.friction_coeff, dtype=np.float64)

    rho0 = p_atm / (numerics.R * T_amb)
    u0 = 0.0
    e0 = p_atm / (numerics.GAMMA - 1.0) / rho0
    U = np.zeros((N, 3), dtype=np.float64)
    U[:, 0] = rho0
    U[:, 1] = rho0 * u0
    U[:, 2] = rho0 * (e0 + 0.5 * u0 * u0)

    return {
        "N": N,
        "dx": dx,
        "areas": areas,
        "friction": friction_coeffs,
        "U": U,
        "initial": U.copy(),
    }


def _pressure_from_state(U: np.ndarray) -> np.ndarray:
    rho = U[:, 0]
    mom = U[:, 1]
    energy = U[:, 2]
    u = mom / rho
    p = (numerics.GAMMA - 1.0) * (energy - 0.5 * rho * u * u)
    return np.maximum(p, 1e-6)


class Engine1DSolver:
    """Network solver handling multiple primaries, collector, and tailpipe."""

    def __init__(
        self,
        primary_pipes: List[Pipe],
        tailpipe: Pipe,
        firing_order: List[int],
        target_dx: float = 0.01,
        collector_volume: float = 0.005,
        p_atm: float = 101325.0,
        T_amb: float = 300.0,
    ):
        self.time: float = 0.0
        self.p_atm = p_atm
        self.T_amb = T_amb

        self.primary_states = [
            _init_pipe_state(pipe, target_dx, p_atm, T_amb) for pipe in primary_pipes
        ]
        self.tail_state = _init_pipe_state(tailpipe, target_dx, p_atm, T_amb)

        self.collector = Junction(collector_volume, p_atm, T_amb)

        self.firing_order = firing_order
        self.n_cyl = len(primary_pipes)
        self.phase_map: Dict[int, float] = {}
        for idx, cyl in enumerate(firing_order):
            self.phase_map[cyl] = 720.0 * idx / max(self.n_cyl, 1)

    def _apply_inlet(self, state: Dict, p_cyl: float, T_cyl: float) -> None:
        gamma = numerics.GAMMA
        T_ref = max(T_cyl, 1.0)
        rho = max(p_cyl / (numerics.R * T_ref), 0.1)
        energy_inlet = p_cyl / (gamma - 1.0)
        energy_inlet = min(energy_inlet, 5.0e6)

        state["U"][0, 0] = rho
        state["U"][0, 1] = 0.0
        state["U"][0, 2] = energy_inlet

    def _apply_collector_boundaries(self) -> None:
        p_col, T_col, rho_col = self.collector.get_state()
        energy_col = p_col / (numerics.GAMMA - 1.0) / rho_col

        for state in self.primary_states:
            state["U"][-1, 0] = rho_col
            state["U"][-1, 1] = 0.0
            state["U"][-1, 2] = rho_col * energy_col

        tail = self.tail_state
        tail["U"][0, 0] = rho_col
        tail["U"][0, 1] = 0.0
        tail["U"][0, 2] = rho_col * energy_col

    def _tail_atmosphere(self) -> None:
        tail = self.tail_state
        rho = self.p_atm / (numerics.R * self.T_amb)
        energy = self.p_atm / (numerics.GAMMA - 1.0) / rho
        tail["U"][-1, 0] = rho
        tail["U"][-1, 1] = 0.0
        tail["U"][-1, 2] = rho * energy

    def _pipe_dt(self, state: Dict) -> float:
        rho = state["U"][:, 0]
        u = state["U"][:, 1] / rho
        p = _pressure_from_state(state["U"])
        a = np.sqrt(numerics.GAMMA * p / rho)
        max_wave_speed = np.max(np.abs(u) + a) + 1e-5
        return 0.4 * state["dx"] / max_wave_speed

    def get_time_step(self) -> float:
        dts = [self._pipe_dt(s) for s in self.primary_states]
        dts.append(self._pipe_dt(self.tail_state))
        return float(np.min(dts))

    def _interface_flux(self, state: Dict, idx: int, area: float) -> Tuple[float, float]:
        rho = state["U"][idx, 0]
        mom = state["U"][idx, 1]
        energy = state["U"][idx, 2]
        u = mom / rho
        p = (numerics.GAMMA - 1.0) * (energy - 0.5 * rho * u * u)
        mdot = rho * u * area
        edot = (energy + p) * u * area
        return mdot, edot

    def step(
        self,
        rpm: float,
        dt: Optional[float] = None,
        exhaust_open_start: float = 140.0,
        exhaust_open_end: float = 360.0,
        p_exhaust: float = 15.0 * 100000.0,
        T_exhaust: float = 1200.0,
    ) -> float:
        base_angle = (self.time * rpm * 6.0) % 720.0

        # Apply cylinder-driven inlet boundaries for each primary
        for i, state in enumerate(self.primary_states):
            cyl_id = i + 1
            phase_shift = self.phase_map.get(cyl_id, 0.0)
            cyl_angle = (base_angle + phase_shift) % 720.0
            if exhaust_open_start <= cyl_angle <= exhaust_open_end:
                span = max(exhaust_open_end - exhaust_open_start, 1e-6)
                phase = (cyl_angle - exhaust_open_start) / span
                lift = max(math.sin(math.pi * phase), 0.0)
                diameter = math.sqrt(state["areas"][0] / math.pi) * 2.0
                max_area = math.pi * (diameter * 0.5) ** 2
                valve_area = max_area * lift
                p_cyl = p_exhaust
                T_cyl = T_exhaust
            else:
                valve_area = 0.0
                p_cyl = self.p_atm
                T_cyl = self.T_amb

            if valve_area > 0.0:
                self._apply_inlet(state, p_cyl, T_cyl)
            else:
                # reflective inlet when closed
                state["U"][0, 0] = state["U"][1, 0]
                state["U"][0, 1] = -state["U"][1, 1]
                state["U"][0, 2] = state["U"][1, 2]

        # Apply collector state to primaries/tailpipe boundaries
        self._apply_collector_boundaries()

        if dt is None:
            dt = self.get_time_step()

        # Compute net flows into collector
        mdot_sum = 0.0
        edot_sum = 0.0
        for state in self.primary_states:
            m, e = self._interface_flux(state, -1, state["areas"][-1])
            mdot_sum += m
            edot_sum += e

        # Tailpipe flow leaves the collector (opposite sign)
        m_tail, e_tail = self._interface_flux(self.tail_state, 0, self.tail_state["areas"][0])
        mdot_sum -= m_tail
        edot_sum -= e_tail

        self.collector.update(dt, mdot_sum, edot_sum)

        # Re-apply collector BC with updated pressure
        self._apply_collector_boundaries()

        # Advance all pipes
        for state in self.primary_states:
            U_new = numerics.lax_wendroff_step(
                state["U"], dt, state["dx"], state["areas"], state["friction"]
            )
            U_new[:, 0] = np.maximum(U_new[:, 0], 0.1)
            U_new[:, 2] = np.clip(U_new[:, 2], 0.0, 1.0e7)
            state["U"] = U_new

        tail = self.tail_state
        U_tail = numerics.lax_wendroff_step(
            tail["U"], dt, tail["dx"], tail["areas"], tail["friction"]
        )
        U_tail[:, 0] = np.maximum(U_tail[:, 0], 0.1)
        U_tail[:, 2] = np.clip(U_tail[:, 2], 0.0, 1.0e7)
        tail["U"] = U_tail

        # Atmospheric outlet
        self._tail_atmosphere()

        self.time += dt
        return dt

    def run_full_simulation(self, rpm: float, cycles: int = 2):
        """Simulate several cycles and record state history for visualization."""

        # Reset states
        for state in self.primary_states:
            state["U"] = state["initial"].copy()
        self.tail_state["U"] = self.tail_state["initial"].copy()
        self.time = 0.0

        total_time = cycles * 120.0 / max(rpm, 1.0)
        sample_interval = 1.0 / (rpm * 6.0)
        next_sample = 0.0

        history: List[np.ndarray] = []
        audio: List[float] = []
        time_vector: List[float] = []

        while self.time < total_time:
            dt = self.get_time_step()
            self.step(rpm=rpm, dt=dt)
            while self.time >= next_sample and next_sample <= total_time:
                # record first primary for visualization
                history.append(self.primary_states[0]["U"].copy())
                p_grid = (numerics.GAMMA - 1.0) * (
                    self.tail_state["U"][:, 2]
                    - 0.5 * (self.tail_state["U"][:, 1] ** 2)
                    / self.tail_state["U"][:, 0]
                )
                audio.append(float(p_grid[-1]))
                time_vector.append(self.time)
                next_sample += sample_interval

        return history, audio, time_vector


# Backwards compatibility for existing imports
PipeSolver = Engine1DSolver

