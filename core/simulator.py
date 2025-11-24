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

    def apply_boundary_conditions(
        self, p_cyl: float, T_cyl: float, valve_area: float
    ) -> None:
        """Apply inlet valve condition and transmissive outlet."""

        gamma = numerics.GAMMA

        if valve_area > 0.0:
            # High-energy blowdown imposed at the inlet. Keep density tied to the
            # neighboring cell (or ideal-gas estimate) while injecting energy.
            if self.N > 1:
                rho_base = self.U[1, 0]
            else:
                rho_base = p_cyl / (numerics.R * max(T_cyl, 1e-6))

            self.U[0, 0] = rho_base
            self.U[0, 1] = 0.0
            self.U[0, 2] = p_cyl / (gamma - 1.0)

            # Nudge the adjacent cell to kick off wave propagation when the valve
            # opens so the energy isn't trapped at the boundary cell.
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

    def get_time_step(self, cfl: float = 0.5) -> float:
        """Compute a stable time-step using the CFL condition."""

        rho = self.U[:, 0]
        u = self.U[:, 1] / rho
        energy = self.U[:, 2]
        p = (numerics.GAMMA - 1.0) * (energy - 0.5 * rho * u * u)
        p = np.maximum(p, 1e-6)
        a = np.sqrt(numerics.GAMMA * p / rho)
        max_wave_speed = np.max(np.abs(u) + a)
        if max_wave_speed <= 0.0:
            max_wave_speed = 1e-8
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
            dt = self.get_time_step()

        # Apply boundary conditions before the numerical update.
        self.apply_boundary_conditions(p_cyl, T_cyl, valve_area)

        U_new = numerics.lax_wendroff_step(
            self.U, dt, self.dx, self.areas, self.friction_coeffs
        )

        self.U = U_new

        # Re-apply boundaries so ghost cells persist for plotting and the next step.
        self.apply_boundary_conditions(p_cyl, T_cyl, valve_area)

        # Numerical safety clamps to prevent negative densities or energies.
        self.U[:, 0] = np.maximum(self.U[:, 0], 1e-4)
        self.U[:, 2] = np.maximum(self.U[:, 2], 1e-4)

        self.time += dt
        return dt
