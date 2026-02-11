import pytest

np = pytest.importorskip("numpy")

from core import numerics


def test_species_conservation_closed_tube() -> None:
    n_cells = 60
    dx = 0.02
    gamma = 1.4
    rho = 1.2
    u = 0.0
    p = 101325.0
    energy = p / (gamma - 1.0) + 0.5 * rho * u * u

    U = np.zeros((n_cells + 2, 4), dtype=np.float64)
    U[1:-1, 0] = rho
    U[1:-1, 1] = rho * u
    U[1:-1, 2] = energy
    y_init = np.linspace(0.05, 0.95, n_cells)
    U[1:-1, 3] = rho * y_init

    total_rhoY_initial = float(np.sum(U[1:-1, 3]) * dx)

    areas = np.full(n_cells + 2, 1.0, dtype=np.float64)
    friction = np.zeros(n_cells + 2, dtype=np.float64)
    diameters = np.full(n_cells + 2, 0.05, dtype=np.float64)

    dt = 1e-4
    for _ in range(25):
        U[0] = U[1]
        U[-1] = U[-2]
        U[0, 1] = -U[1, 1]
        U[-1, 1] = -U[-2, 1]
        U = numerics.lax_wendroff_step_scalar(
            U,
            dt,
            dx,
            areas,
            friction,
            diameters,
            gamma,
            artificial_diffusion=0.0,
            clamp_rho_min=0.1,
            clamp_p_min=1e-6,
            clamp_p_max=1e9,
            clamp_u_max=1500.0,
            clamp_energy_max=1.0e7,
            heat_transfer_enabled=False,
        )

    total_rhoY_final = float(np.sum(U[1:-1, 3]) * dx)
    assert total_rhoY_final == pytest.approx(total_rhoY_initial, rel=1e-6, abs=1e-9)

    Y = U[1:-1, 3] / np.maximum(U[1:-1, 0], 1e-12)
    assert np.all((Y >= 0.0) & (Y <= 1.0))
    assert np.isfinite(U).all()
