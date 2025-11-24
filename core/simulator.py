"""Simulation scaffolding to couple engine data with numerical solver."""

from __future__ import annotations

import math

import numpy as np

from core import numerics
from core.model import Pipe


class PipeSolver:
    """Numerical wrapper to evolve a single pipe using the Lax-Wendroff scheme."""

    def __init__(self, pipe_data: Pipe, dx_target: float = 0.01, p_atm: float = 101325.0, T_amb: float = 300.0):
        """
        Initialize the solver state for a pipe.

        Args:
            pipe_data: Configuration describing geometry and friction.
            dx_target: Desired spatial resolution in meters (default 10 mm).
            p_atm: Ambient/initial pressure (Pa).
            T_amb: Ambient/initial temperature (K).
        """

        self.pipe_data = pipe_data
        self.time: float = 0.0

        length_m = pipe_data.length / 1000.0
        self.n_cells = max(3, int(math.ceil(length_m / dx_target)))
        self.dx = length_m / self.n_cells

        # Linearly varying diameter to support conical pipes later.
        diam_in = pipe_data.diameter_inlet / 1000.0
        diam_out = pipe_data.diameter_outlet / 1000.0
        diameters = np.linspace(diam_in, diam_out, self.n_cells)
        self.areas = math.pi * (diameters * 0.5) ** 2

        self.friction_coeffs = np.full(self.n_cells, pipe_data.friction_coeff, dtype=np.float64)

        # Conserved variables: [rho, rho*u, rho*E]
        self.U = np.zeros((self.n_cells, 3), dtype=np.float64)
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

    def step(self, dt: float):
        """Advance the pipe solution by one timestep."""
        self.apply_inlet_boundary()
        self.apply_outlet_boundary()
        self.U = numerics.lax_wendroff_step(self.U, dt, self.dx, self.areas, self.friction_coeffs)
        self.time += dt
