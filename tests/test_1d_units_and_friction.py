import math

import math

import pytest

np = pytest.importorskip("numpy")

from core import numerics
from core.engine_components import Pipe, SimulationSettings
from core.simulator import _init_pipe_state


def test_pipe_units_conversion():
    pipe = Pipe(length=500.0, diameter_inlet=50.0, diameter_outlet=50.0)
    target_dx = 0.01
    settings = SimulationSettings()
    state = _init_pipe_state(
        pipe,
        target_dx,
        p_atm=101325.0,
        T_amb=300.0,
        gamma=settings.gamma_exhaust,
        gas_constant=settings.gas_constant_R,
    )

    assert state["dx"] == pytest.approx(0.5 / 50.0)

    expected_area = math.pi * (0.05 * 0.5) ** 2
    assert state["areas"][0] == pytest.approx(expected_area)


def test_darcy_uses_real_diameter():
    settings = SimulationSettings()
    gamma = settings.gamma_exhaust
    n_cells = 5
    dx = 0.1
    dt = 1e-4

    rho = 1.0
    u = 20.0
    pressure = 101325.0
    energy = pressure / (gamma - 1.0) / rho + 0.5 * u * u

    base_state = np.zeros((n_cells, 3), dtype=np.float64)
    base_state[:, 0] = rho
    base_state[:, 1] = rho * u
    base_state[:, 2] = rho * energy

    friction = np.full(n_cells, 0.02)

    d_small = np.full(n_cells, 0.02)
    d_large = np.full(n_cells, 0.10)
    areas_small = math.pi * (d_small * 0.5) ** 2
    areas_large = math.pi * (d_large * 0.5) ** 2

    U_small = numerics.lax_wendroff_step(
        base_state,
        dt,
        dx,
        areas_small,
        friction,
        d_small,
        gamma,
        settings.artificial_diffusion,
        settings.clamp_rho_min,
        settings.clamp_p_min,
        settings.clamp_p_max,
        settings.clamp_u_max,
        settings.clamp_energy_max,
        settings.enable_heat_transfer_1d,
    )

    U_large = numerics.lax_wendroff_step(
        base_state,
        dt,
        dx,
        areas_large,
        friction,
        d_large,
        gamma,
        settings.artificial_diffusion,
        settings.clamp_rho_min,
        settings.clamp_p_min,
        settings.clamp_p_max,
        settings.clamp_u_max,
        settings.clamp_energy_max,
        settings.enable_heat_transfer_1d,
    )

    mom_small = U_small[:, 1].sum()
    mom_large = U_large[:, 1].sum()

    assert mom_small < mom_large
    assert (mom_large - mom_small) > 0.01
