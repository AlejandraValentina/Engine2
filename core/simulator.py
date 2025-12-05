"""Network-capable 1D gas solver tying engine data to numerics."""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np

from core import numerics
from core.engine_components import Pipe, SimulationSettings
from core.junctions import Junction


def _init_pipe_state(
    pipe_data: Pipe,
    target_dx: float,
    p_atm: float,
    T_amb: float,
    gamma: float,
    gas_constant: float,
):
    L_m = float(pipe_data.length) * 1e-3
    estimated_N = int(np.ceil(L_m / target_dx))
    N = max(estimated_N, 50)
    dx = L_m / N

    diam_in_m = float(pipe_data.diameter_inlet) * 1e-3
    diam_out_m = float(pipe_data.diameter_outlet) * 1e-3
    diameters = np.linspace(diam_in_m, diam_out_m, N)
    areas = math.pi * (diameters * 0.5) ** 2
    friction_coeffs = np.full(N, pipe_data.friction_coeff, dtype=np.float64)

    rho0 = p_atm / (gas_constant * T_amb)
    u0 = 0.0
    e0 = p_atm / (gamma - 1.0) / rho0
    U = np.zeros((N, 3), dtype=np.float64)
    U[:, 0] = rho0
    U[:, 1] = rho0 * u0
    U[:, 2] = rho0 * (e0 + 0.5 * u0 * u0)

    return {
        "N": N,
        "dx": dx,
        "diameters": diameters,
        "areas": areas,
        "friction": friction_coeffs,
        "U": U,
        "initial": U.copy(),
    }


def _pressure_from_state(
    U: np.ndarray, p_min: float, p_max: float, gamma: float
) -> np.ndarray:
    rho = U[:, 0]
    mom = U[:, 1]
    energy = U[:, 2]
    u = mom / rho
    p = (gamma - 1.0) * (energy - 0.5 * rho * u * u)
    return np.clip(p, p_min, p_max)


def compute_placeholder_valve_area(
    cyl_angle: float,
    exhaust_open_start: float,
    exhaust_open_end: float,
    base_area: float,
) -> float:
    """Sinusoidal valve curtain placeholder pending real valve geometry.

    Returns ``base_area * sin(pi * phase)`` while the crank angle is inside the
    open window and ``0`` otherwise. The window may wrap 720°; ``base_area``
    typically comes from the first pipe cell area. This helper isolates the
    placeholder for future replacement with true port/curtain geometry.
    """

    if base_area <= 0.0:
        return 0.0

    angle = cyl_angle % 720.0
    start = exhaust_open_start % 720.0
    end = exhaust_open_end % 720.0

    if start <= end:
        if not (start <= angle <= end):
            return 0.0
        span = max(end - start, 1e-6)
        phase = (angle - start) / span
    else:
        if not (angle >= start or angle <= end):
            return 0.0
        span = (720.0 - start) + end
        phase = ((angle - start) % 720.0) / span

    lift = max(math.sin(math.pi * phase), 0.0)
    return base_area * lift


def rusanov_flux(U_L: np.ndarray, U_R: np.ndarray, gamma: float) -> np.ndarray:
    """Local Lax-Friedrichs flux for 1D Euler equations."""

    def _primitive(U: np.ndarray) -> Tuple[float, float, float]:
        rho = float(U[0])
        u = float(U[1]) / max(rho, 1e-12)
        p = max((gamma - 1.0) * (float(U[2]) - 0.5 * rho * u * u), 1e-9)
        return rho, u, p

    rho_L, u_L, p_L = _primitive(U_L)
    rho_R, u_R, p_R = _primitive(U_R)

    F_L = np.array([
        rho_L * u_L,
        rho_L * u_L * u_L + p_L,
        u_L * (float(U_L[2]) + p_L),
    ])
    F_R = np.array([
        rho_R * u_R,
        rho_R * u_R * u_R + p_R,
        u_R * (float(U_R[2]) + p_R),
    ])

    c_L = math.sqrt(gamma * p_L / max(rho_L, 1e-12))
    c_R = math.sqrt(gamma * p_R / max(rho_R, 1e-12))
    smax = max(abs(u_L) + c_L, abs(u_R) + c_R)

    return 0.5 * (F_L + F_R) - 0.5 * smax * (U_R - U_L)


class Engine1DSolver:
    """Network solver handling multiple primaries, collector, and tailpipe.

    State vectors ``U`` for each pipe have shape (N, 3) and store:
    ``[rho (kg/m^3), rho*u (kg/m^2/s), rho*E (J/m^3)]``.
    """

    def __init__(
        self,
        primary_pipes: List[Pipe],
        tailpipe: Pipe,
        firing_order: List[int],
        target_dx: float = 0.01,
        collector_volume: float = 0.005,
        p_atm: float = 101325.0,
        T_amb: float = 300.0,
        settings: Optional[SimulationSettings] = None,
    ):
        self.time: float = 0.0
        self.p_atm = p_atm
        self.T_amb = T_amb
        self.settings = settings or SimulationSettings()
        self.gamma = float(getattr(self.settings, "gamma_exhaust", numerics.DEFAULT_GAMMA))
        self.gas_constant = float(
            getattr(self.settings, "gas_constant_R", numerics.DEFAULT_R)
        )

        self.primary_states = [
            _init_pipe_state(
                pipe, target_dx, p_atm, T_amb, self.gamma, self.gas_constant
            )
            for pipe in primary_pipes
        ]
        self.tail_state = _init_pipe_state(
            tailpipe, target_dx, p_atm, T_amb, self.gamma, self.gas_constant
        )

        self.collector = Junction(
            collector_volume, p_atm, T_amb, gamma=self.gamma, gas_constant=self.gas_constant
        )

        self.firing_order = firing_order
        self.n_cyl = len(primary_pipes)
        self.phase_map: Dict[int, float] = {}
        for idx, cyl in enumerate(firing_order):
            self.phase_map[cyl] = 720.0 * idx / max(self.n_cyl, 1)

    def _apply_inlet(
        self,
        state: Dict,
        p_stag: float,
        T_stag: float,
        valve_area: float,
        dt: float,
        Cd: float = 0.9,
    ) -> None:
        if valve_area <= 0.0 or dt <= 0.0:
            return

        p_down = float(
            _pressure_from_state(
                state["U"][1:2],
                self.settings.clamp_p_min,
                self.settings.clamp_p_max,
                self.gamma,
            )[0]
        )
        mdot = float(
            numerics.calculate_mass_flow_rate(
                float(p_stag),
                float(p_down),
                float(max(T_stag, 1.0)),
                float(valve_area),
                float(Cd),
                float(self.gamma),
                float(self.gas_constant),
            )
        )

        A_pipe = float(state["areas"][0])
        if A_pipe <= 0.0:
            A_pipe = float(valve_area)
        mflux = mdot / max(A_pipe, 1e-12)

        rho_res = max(
            float(p_stag) / (self.gas_constant * float(max(T_stag, 1.0))),
            self.settings.clamp_rho_min,
        )
        u_res = float(
            np.clip(mflux / rho_res, -self.settings.clamp_u_max, self.settings.clamp_u_max)
        )
        cp = self.gamma * self.gas_constant / max(self.gamma - 1.0, 1e-9)
        h0 = cp * float(max(T_stag, 1.0)) + 0.5 * u_res * u_res

        cell_vol = float(state["dx"] * state["areas"][0])
        mass_delta = mdot * dt
        energy_delta = mass_delta * h0
        momentum_delta = mass_delta * u_res

        state["U"][0, 0] = max(
            state["U"][0, 0] + mass_delta / max(cell_vol, 1e-12),
            self.settings.clamp_rho_min,
        )
        state["U"][0, 1] += momentum_delta / max(cell_vol, 1e-12)
        state["U"][0, 2] = float(
            np.clip(
                state["U"][0, 2] + energy_delta / max(cell_vol, 1e-12),
                0.0,
                self.settings.clamp_energy_max,
            )
        )

    def _apply_collector_boundaries(self, mdot_primary: List[float], mdot_tail: float) -> None:
        p_col, T_col, rho_col = self.collector.get_state()
        rho_col = max(rho_col, self.settings.clamp_rho_min)

        for mdot, state in zip(mdot_primary, self.primary_states):
            area = float(max(state["areas"][-1], 1e-12))
            u_ghost = float(
                np.clip(mdot / (rho_col * area), -self.settings.clamp_u_max, self.settings.clamp_u_max)
            )
            e_int = p_col / max((self.gamma - 1.0) * rho_col, 1e-12)
            E_tot = e_int + 0.5 * u_ghost * u_ghost
            state["U"][-1, 0] = rho_col
            state["U"][-1, 1] = rho_col * u_ghost
            state["U"][-1, 2] = float(np.clip(rho_col * E_tot, 0.0, self.settings.clamp_energy_max))

        tail = self.tail_state
        area_tail = float(max(tail["areas"][0], 1e-12))
        u_tail = float(
            np.clip(mdot_tail / (rho_col * area_tail), -self.settings.clamp_u_max, self.settings.clamp_u_max)
        )
        e_int_tail = p_col / max((self.gamma - 1.0) * rho_col, 1e-12)
        E_tail = e_int_tail + 0.5 * u_tail * u_tail
        tail["U"][0, 0] = rho_col
        tail["U"][0, 1] = rho_col * u_tail
        tail["U"][0, 2] = float(np.clip(rho_col * E_tail, 0.0, self.settings.clamp_energy_max))

    def _tail_atmosphere(self) -> None:
        tail = self.tail_state
        U_i = tail["U"][-2]
        rho_i = float(U_i[0])
        mom_i = float(U_i[1])
        u_i = mom_i / rho_i

        p_ghost = float(self.p_atm)
        if u_i > 0.0:
            p_i = float(
                _pressure_from_state(
                    tail["U"][-2:-1],
                    self.settings.clamp_p_min,
                    self.settings.clamp_p_max,
                    self.gamma,
                )[0]
            )
            T_ghost = max(p_i / (self.gas_constant * rho_i), 1.0)
        else:
            T_ghost = float(self.T_amb)

        rho_g = max(p_ghost / (self.gas_constant * T_ghost), self.settings.clamp_rho_min)
        u_g = float(u_i)
        e_g = p_ghost / (self.gamma - 1.0) + 0.5 * rho_g * u_g * u_g

        tail["U"][-1, 0] = rho_g
        tail["U"][-1, 1] = rho_g * u_g
        tail["U"][-1, 2] = float(np.clip(e_g, 0.0, self.settings.clamp_energy_max))

    def apply_boundary_conditions(
        self,
        rpm: float,
        exhaust_open_start: float,
        exhaust_open_end: float,
        p_exhaust: float,
        T_exhaust: float,
        dt: float,
        p_stag_by_cyl: Optional[Dict[int, float]] = None,
        T_stag_by_cyl: Optional[Dict[int, float]] = None,
    ) -> None:
        """Apply inlet valve states (with reflective closure)."""

        base_angle = (self.time * rpm * 6.0) % 720.0

        for i, state in enumerate(self.primary_states):
            cyl_id = i + 1
            phase_shift = self.phase_map.get(cyl_id, 0.0)
            cyl_angle = (base_angle + phase_shift) % 720.0
            valve_area = compute_placeholder_valve_area(
                cyl_angle, exhaust_open_start, exhaust_open_end, state["areas"][0]
            )
            if valve_area > 0.0:
                p_cyl = p_stag_by_cyl.get(cyl_id, p_exhaust) if p_stag_by_cyl else p_exhaust
                T_cyl = T_stag_by_cyl.get(cyl_id, T_exhaust) if T_stag_by_cyl else T_exhaust
            else:
                p_cyl = self.p_atm
                T_cyl = self.T_amb

            if valve_area > 0.0:
                self._apply_inlet(state, p_cyl, T_cyl, valve_area, dt, Cd=0.9)
            else:
                # Reflective ghost cell when valve is closed
                state["U"][0, 0] = state["U"][1, 0]
                state["U"][0, 1] = -state["U"][1, 1]
                state["U"][0, 2] = state["U"][1, 2]

        self._tail_atmosphere()

    def _pipe_dt(self, state: Dict) -> float:
        rho = state["U"][:, 0]
        u = state["U"][:, 1] / rho
        p = _pressure_from_state(
            state["U"], self.settings.clamp_p_min, self.settings.clamp_p_max, self.gamma
        )
        a = np.sqrt(self.gamma * p / rho)
        max_wave_speed = np.max(np.abs(u) + a) + 1e-5
        return 0.4 * state["dx"] / max_wave_speed

    def get_time_step(self) -> float:
        dts = [self._pipe_dt(s) for s in self.primary_states]
        dts.append(self._pipe_dt(self.tail_state))
        return float(np.min(dts))

    def step(
        self,
        rpm: float,
        dt: Optional[float] = None,
        exhaust_open_start: float = 140.0,
        exhaust_open_end: float = 360.0,
        p_exhaust: float = 15.0 * 100000.0,
        T_exhaust: float = 1200.0,
        p_stag_by_cyl: Optional[Dict[int, float]] = None,
        T_stag_by_cyl: Optional[Dict[int, float]] = None,
    ) -> float:
        if dt is None:
            dt = self.get_time_step()

        self.apply_boundary_conditions(
            rpm,
            exhaust_open_start,
            exhaust_open_end,
            p_exhaust,
            T_exhaust,
            dt,
            p_stag_by_cyl=p_stag_by_cyl,
            T_stag_by_cyl=T_stag_by_cyl,
        )

        p_col, T_col, rho_col = self.collector.get_state()
        rho_col = max(rho_col, self.settings.clamp_rho_min)
        E_col = p_col / max((self.gamma - 1.0) * rho_col, 1e-12)
        U_col = np.array([rho_col, 0.0, rho_col * E_col], dtype=np.float64)

        mdot_primary: List[float] = []
        mdot_sum = 0.0
        edot_sum = 0.0

        for state in self.primary_states:
            U_int = state["U"][-2]
            flux = rusanov_flux(U_int, U_col, self.gamma)
            area_end = float(state["areas"][-1])
            mdot_i = float(flux[0] * area_end)
            edot_i = float(flux[2] * area_end)
            mdot_primary.append(mdot_i)
            mdot_sum += mdot_i
            edot_sum += edot_i

        tail = self.tail_state
        flux_tail = rusanov_flux(U_col, tail["U"][1], self.gamma)
        area_tail = float(tail["areas"][0])
        mdot_tail = float(flux_tail[0] * area_tail)
        edot_tail = float(flux_tail[2] * area_tail)
        mdot_sum -= mdot_tail
        edot_sum -= edot_tail

        self.collector.update(dt, mdot_sum, edot_sum)

        # Re-apply collector BC with updated pressure using interface fluxes
        self._apply_collector_boundaries(mdot_primary, mdot_tail)

        # Advance all pipes
        for state in self.primary_states:
            U_new = numerics.lax_wendroff_step(
                state["U"],
                dt,
                state["dx"],
                state["areas"],
                state["friction"],
                state["diameters"],
                self.gamma,
                self.settings.artificial_diffusion,
                self.settings.clamp_rho_min,
                self.settings.clamp_p_min,
                self.settings.clamp_p_max,
                self.settings.clamp_u_max,
                self.settings.clamp_energy_max,
                self.settings.enable_heat_transfer_1d,
            )
            state["U"] = U_new

        U_tail = numerics.lax_wendroff_step(
            tail["U"],
            dt,
            tail["dx"],
            tail["areas"],
            tail["friction"],
            tail["diameters"],
            self.gamma,
            self.settings.artificial_diffusion,
            self.settings.clamp_rho_min,
            self.settings.clamp_p_min,
            self.settings.clamp_p_max,
            self.settings.clamp_u_max,
            self.settings.clamp_energy_max,
            self.settings.enable_heat_transfer_1d,
        )
        tail["U"] = U_tail

        # Atmospheric outlet (already set in apply_boundary_conditions, repeated for safety)
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
                p_grid = (self.gamma - 1.0) * (
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

