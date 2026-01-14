import numpy as np

from core.advanced import solver_1d


def _build_state(n_phys: int, gamma: float, gas_constant: float) -> np.ndarray:
    x = np.linspace(0.0, 1.0, n_phys)
    rho = 1.2 + 0.05 * np.sin(2.0 * np.pi * x)
    u = 15.0 + 0.2 * np.cos(2.0 * np.pi * x)
    p = 101325.0 + 500.0 * np.sin(2.0 * np.pi * x)
    Y = 0.3 + 0.02 * np.cos(2.0 * np.pi * x)
    prim = np.stack([rho, u, p, Y], axis=1)
    U_phys = solver_1d._primitive_to_conserved(prim, gamma, gas_constant, "soa_test")
    U = np.zeros((n_phys + 2, 4))
    U[1:-1] = U_phys
    U[0] = U[1]
    U[-1] = U[-2]
    return U


def test_solver1d_soa_matches_aos_step() -> None:
    gamma = 1.35
    gas_constant = 287.0
    U = _build_state(6, gamma, gas_constant)
    dx = 0.1
    dt = 1e-5
    U_aos = solver_1d._muscl_hancock_step_aos(
        U.copy(),
        dx,
        dt,
        gamma,
        gas_constant,
        p_outlet=None,
        outlet_mode="copy",
    )
    U_soa = solver_1d._muscl_hancock_step_soa(
        U.copy(),
        dx,
        dt,
        gamma,
        gas_constant,
        p_outlet=None,
        outlet_mode="copy",
    )
    diff = np.max(np.abs(U_aos - U_soa))
    assert diff <= 1e-10
