"""Simulation scaffolding to couple engine data with the numerical solver."""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from core import numerics
from core.model import Pipe


class PipeSolver:
    """Numerical wrapper to evolve a single pipe using the Lax-Wendroff scheme."""

    def __init__(
        self,
        pipe_data: Pipe,
        target_dx: float = 0.01,
        p_atm: float = 101325.0,
        T_amb: float = 300.0,
    ):
        """Initialize solver state using the provided pipe configuration.

        The spatial discretization uses `target_dx` (meters) as a guideline. The final
        cell count is clamped to a minimum of 50 for stability, and `dx` is recomputed
        so that the total pipe length remains consistent with `pipe_data.length`.
        """

        self.pipe_data = pipe_data
        self.time: float = 0.0

        # Strict SI units: assume pipe_data.length is already in meters.
        self.L = float(pipe_data.length)
        print(f"[PipeSolver] SI Units Check: Input L={self.L}m, target_dx={target_dx}")

        # Cell count based on requested spacing, with a hard minimum for stability.
        estimated_N = int(np.ceil(self.L / target_dx))
        if estimated_N < 50:
            print(
                "[PipeSolver] Warning: cell count too low for stability. "
                f"Requested {estimated_N}, enforcing minimum of 50."
            )
            self.N = 50
        else:
            self.N = estimated_N

        # Recompute dx so the discretized pipe length matches the original length.
        self.dx = self.L / self.N

        diam_in = float(pipe_data.diameter_inlet)
        diam_out = float(pipe_data.diameter_outlet)
        diameters = np.linspace(diam_in, diam_out, self.N)
        self.areas = math.pi * (diameters * 0.5) ** 2

        self.friction_coeffs = np.full(self.N, pipe_data.friction_coeff, dtype=np.float64)

        # Conserved variables: [rho, rho*u, rho*E]
        self.U = np.zeros((self.N, 3), dtype=np.float64)
        rho0 = p_atm / (numerics.R * T_amb)
        u0 = 0.0
        e0 = p_atm / (numerics.GAMMA - 1.0) / rho0
        self.U[:, 0] = rho0
        self.U[:, 1] = rho0 * u0
        self.U[:, 2] = rho0 * (e0 + 0.5 * u0 * u0)
        self._initial_U = self.U.copy()

    def apply_boundary_conditions(
        self, p_cyl: float, T_cyl: float, valve_area: float
    ) -> None:
        """Apply inlet valve condition and transmissive outlet."""

        gamma = numerics.GAMMA

        if valve_area > 0.0:
            T_ref = max(T_cyl, 1.0)
            rho_inlet = max(p_cyl / (numerics.R * T_ref), 0.1)
            energy_inlet = p_cyl / (gamma - 1.0)
            energy_inlet = min(energy_inlet, 5.0e6)

            self.U[0, 0] = rho_inlet
            self.U[0, 1] = 0.0
            self.U[0, 2] = energy_inlet

            # Nudge the adjacent cell to help launch the wavefront when the valve opens.
            if self.N > 1:
                self.U[1, 2] = 0.9 * self.U[1, 2] + 0.1 * self.U[0, 2]
        else:
            # Reflective ghost cell: mirror density/energy and invert momentum to
            # impose zero velocity at the wall while allowing pressure to relax.
            if self.N > 1:
                self.U[0, 0] = self.U[1, 0]
                self.U[0, 1] = -self.U[1, 1]
                self.U[0, 2] = self.U[1, 2]

        # Transmissive outlet lets waves exit without reflection.
        if self.N > 1:
            self.U[-1] = self.U[-2]

    def get_time_step(self, cfl: float = 0.4) -> float:
        """Compute a stable time-step using the CFL condition."""

        rho = self.U[:, 0]
        u = self.U[:, 1] / rho
        energy = self.U[:, 2]
        p = (numerics.GAMMA - 1.0) * (energy - 0.5 * rho * u * u)
        p = np.maximum(p, 1e-6)
        a = np.sqrt(numerics.GAMMA * p / rho)
        max_wave_speed = np.max(np.abs(u) + a) + 1e-5
        return cfl * self.dx / max_wave_speed

    def step(
        self,
        dt: Optional[float] = None,
        p_cyl: float = 101325.0,
        T_cyl: float = 300.0,
        valve_area: float = 0.0,
    ) -> float:
        """Advance the pipe solution by one timestep and return the dt used."""

        if dt is None:
            self.apply_boundary_conditions(p_cyl, T_cyl, valve_area)
            dt = self.get_time_step()
        else:
            self.apply_boundary_conditions(p_cyl, T_cyl, valve_area)

        U_prev = self.U.copy()
        U_new = numerics.lax_wendroff_step(
            self.U, dt, self.dx, self.areas, self.friction_coeffs
        )

        # Stability guard: detect non-finite values from the solver.
        if not np.isfinite(U_new).all():
            print("[PipeSolver] Warning: non-finite state detected; reverting step.")
            self.U = U_prev
            return 0.0

        # Apply density/energy limiters to reduce CFL blowups.
        U_new[:, 0] = np.maximum(U_new[:, 0], 0.1)
        U_new[:, 2] = np.clip(U_new[:, 2], 0.0, 1.0e7)

        self.U = U_new

        # Re-apply boundaries so ghost cells persist for plotting and the next step.
        self.apply_boundary_conditions(p_cyl, T_cyl, valve_area)

        # Keep boundary-refreshed state within sane physical limits.
        self.U[:, 0] = np.maximum(self.U[:, 0], 0.1)
        self.U[:, 2] = np.clip(self.U[:, 2], 0.0, 1.0e7)

        self.time += dt
        return dt

    def run_full_simulation(self, rpm: float, cycles: int = 2):
        """Simulate a full engine cycle (or several) and record state history.

        The simulation uses a simple exhaust-open/closed schedule to drive the
        boundary conditions, sampling the entire pipe state roughly every
        crank-degree for later visualization or audio synthesis.

        Returns
        -------
        Tuple[list[np.ndarray], list[float], list[float]]
            history of U snapshots, exhaust pressure samples, and time vector
            aligned to the history entries.
        """

        # Reset state to the initialized ambient condition for repeatability.
        self.U = self._initial_U.copy()
        self.time = 0.0

        rpm = max(float(rpm), 1.0)
        total_time = cycles * 120.0 / rpm  # seconds for requested cycles
        sample_interval = 1.0 / (rpm * 6.0)  # 1 crank-degree in seconds
        next_sample_time = 0.0

        exhaust_open_start = 140.0
        exhaust_open_end = 360.0
        exhaust_pressure = 15.0 * 100000.0
        ambient_pressure = 101325.0
        T_hot = 1200.0
        T_cold = 300.0

        history: list[np.ndarray] = []
        audio_pressures: list[float] = []
        time_vector: list[float] = []

        while self.time < total_time:
            angle = (self.time * rpm * 6.0) % 720.0
            if exhaust_open_start <= angle <= exhaust_open_end:
                phase = (angle - exhaust_open_start) / max(
                    exhaust_open_end - exhaust_open_start, 1e-6
                )
                lift = max(math.sin(math.pi * phase), 0.0)
                diameter = math.sqrt(self.areas[0] / math.pi) * 2.0
                max_area = math.pi * (diameter * 0.5) ** 2
                valve_area = max_area * lift
                p_cyl = exhaust_pressure
                T_cyl = T_hot
            else:
                valve_area = 0.0
                p_cyl = ambient_pressure
                T_cyl = T_cold

            dt = self.get_time_step()
            self.step(dt=dt, p_cyl=p_cyl, T_cyl=T_cyl, valve_area=valve_area)

            while self.time >= next_sample_time and next_sample_time <= total_time:
                history.append(self.U.copy())
                time_vector.append(self.time)
                p_grid = (numerics.GAMMA - 1.0) * (
                    self.U[:, 2] - 0.5 * (self.U[:, 1] ** 2) / self.U[:, 0]
                )
                audio_pressures.append(float(p_grid[-1]))
                next_sample_time += sample_interval

        return history, audio_pressures, time_vector
