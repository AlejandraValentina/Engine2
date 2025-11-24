"""Numerical routines for 1D Euler equations using Lax-Wendroff scheme."""

import importlib.util
import numpy as np

if importlib.util.find_spec("numba") is not None:
    from numba import jit
else:  # pragma: no cover - fallback when numba is not installed
    def jit(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

GAMMA = 1.4
R = 287.0


@jit(nopython=True)
def flux_vector(U):
    """Compute the flux vector F for a state U = [rho, rho*u, rho*E]."""
    rho = U[0]
    mom = U[1]
    energy = U[2]
    u = mom / rho
    kinetic = 0.5 * rho * u * u
    p = (GAMMA - 1.0) * (energy - kinetic)
    F = np.empty(3, dtype=np.float64)
    F[0] = mom
    F[1] = mom * u + p
    F[2] = (energy + p) * u
    return F


@jit(nopython=True)
def source_terms(U, dx, D, f, Tw):
    """Compute wall friction and heat transfer source terms."""
    rho = U[0]
    mom = U[1]
    energy = U[2]
    u = mom / rho
    # Friction (Darcy-Weisbach-like), applied to momentum and energy.
    friction = -0.5 * rho * u * np.abs(u) * f / D
    # Simple heat transfer placeholder (Tw not yet used explicitly)
    heat_transfer = 0.0
    S = np.zeros(3, dtype=np.float64)
    S[1] = friction
    S[2] = friction * u + heat_transfer
    return S


@jit(nopython=True)
def lax_wendroff_step(U_grid, dt, dx, areas, friction_coeffs):
    """Advance the conserved variables one time step with area variation handling."""
    n_cells = U_grid.shape[0]
    U_new = np.empty_like(U_grid)

    # Precompute fluxes at cell centers
    F_centers = np.empty_like(U_grid)
    for i in range(n_cells):
        F_centers[i] = flux_vector(U_grid[i])

    # Predictor: interface states
    U_half = np.empty((n_cells - 1, 3), dtype=np.float64)
    F_half = np.empty_like(U_half)
    for i in range(n_cells - 1):
        U_half[i] = 0.5 * (U_grid[i + 1] + U_grid[i]) - 0.5 * dt / dx * (F_centers[i + 1] - F_centers[i])
        F_half[i] = flux_vector(U_half[i])

    # Corrector: update cell averages
    for i in range(n_cells):
        # Geometric source term for area variation
        if i == 0:
            dA_dx = (areas[i + 1] - areas[i]) / dx
        elif i == n_cells - 1:
            dA_dx = (areas[i] - areas[i - 1]) / dx
        else:
            dA_dx = (areas[i + 1] - areas[i - 1]) / (2.0 * dx)

        rho = U_grid[i, 0]
        u = U_grid[i, 1] / rho
        geom_source = np.zeros(3, dtype=np.float64)
        geom_source[1] = -rho * u * u * dA_dx / areas[i]
        geom_source[2] = -U_grid[i, 2] * u * dA_dx / areas[i]

        # Friction source term
        D = 1.0
        S = source_terms(U_grid[i], dx, D, friction_coeffs[i], 0.0)

        flux_diff = np.zeros(3, dtype=np.float64)
        if i == 0:
            flux_diff = F_half[i]
        elif i == n_cells - 1:
            flux_diff = -F_half[i - 1]
        else:
            flux_diff = F_half[i] - F_half[i - 1]

        U_new[i] = U_grid[i] - dt / dx * flux_diff + dt * (S + geom_source)

    return U_new
