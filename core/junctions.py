"""Junction model for multi-branch gas networks.

This module provides a compact zero-dimensional junction that conserves mass
and energy when multiple pipes merge (e.g., exhaust collectors).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np

from core import numerics


@dataclass
class Junction:
    """0D volume where multiple branches merge."""

    volume: float
    pressure: float
    temperature: float

    def __post_init__(self) -> None:
        self.mass = self._mass_from_state(self.pressure, self.temperature)

    def _mass_from_state(self, p: float, T: float) -> float:
        T_safe = max(T, 1e-3)
        return p * self.volume / (numerics.R * T_safe)

    def update(self, dt: float, inflows_mass: float, inflows_energy: float) -> None:
        """Apply conservation of mass and energy over ``dt``.

        Parameters
        ----------
        dt : float
            Timestep in seconds.
        inflows_mass : float
            Net mass flow into the junction (kg/s). Negative removes mass.
        inflows_energy : float
            Net energy flow into the junction (J/s). Negative removes energy.
        """

        self.mass = max(self.mass + inflows_mass * dt, 1e-8)

        total_energy = (self.pressure / (numerics.GAMMA - 1.0)) * self.volume
        total_energy += inflows_energy * dt
        # Prevent negative internal energy
        total_energy = max(total_energy, 1e-6)

        # Update thermodynamic state via ideal gas law
        self.temperature = total_energy * (numerics.GAMMA - 1.0) / (
            self.mass * numerics.R
        )
        self.temperature = max(self.temperature, 1.0)
        self.pressure = self.mass * numerics.R * self.temperature / self.volume

    def get_state(self) -> Tuple[float, float, float]:
        """Return (pressure, temperature, density)."""

        rho = self.mass / self.volume
        return self.pressure, self.temperature, rho

