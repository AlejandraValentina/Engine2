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
        """Initialize solver state using the provided pipe configuration."""

        self.pipe_data = pipe_data
        self.time: float = 0.0

        length_m = pipe_data.length / 1000.0
        self.N = max(3, int(math.ceil(length_m / target_dx)))
        self.dx = length_m / self.N

        diam_in = pipe_data.diameter_inlet / 1000.0
        diam_out = pipe_data.diameter_outlet / 1000.0
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

    def apply_inlet_boundary(self):
        """Placeholder for inlet boundary conditions."""
        # TODO: connect to cylinder or upstream component
        return

    def apply_outlet_boundary(self):
        """Placeholder for outlet boundary conditions."""
        # TODO: connect to atmosphere or downstream component
        return

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

    def step(self, dt: Optional[float] = None) -> float:
        """Advance the pipe solution by one timestep and return the dt used."""

        if dt is None:
            dt = self.get_time_step()

        self.apply_inlet_boundary()
        self.apply_outlet_boundary()
        self.U = numerics.lax_wendroff_step(self.U, dt, self.dx, self.areas, self.friction_coeffs)
        self.time += dt
        return dt
