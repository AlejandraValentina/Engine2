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

# Defaults for legacy callers; the solver wires specific values from SimulationSettings.
DEFAULT_GAMMA = 1.4
DEFAULT_R = 287.0
GAMMA = DEFAULT_GAMMA
R = DEFAULT_R


@jit(nopython=True)
def flux_vector(U, gamma=DEFAULT_GAMMA):
    """Compute the flux vector F for a state U = [rho, rho*u, rho*E]."""
    rho = U[0]
    mom = U[1]
    energy = U[2]
    rho_safe = max(rho, 1e-12)
    u = mom / rho_safe
    kinetic = 0.5 * rho_safe * u * u
    # Ideal gas EOS: p = (gamma - 1) * (E - 0.5*rho*u^2)
    p = (gamma - 1.0) * (energy - kinetic)
    F = np.empty(3, dtype=np.float64)
    F[0] = mom
    F[1] = mom * u + p
    F[2] = (energy + p) * u
    return F


@jit(nopython=True)
def flux_vector_scalar(U, gamma=DEFAULT_GAMMA):
    """Compute flux vector for U = [rho, rho*u, rho*E, rho*Y]."""
    rho = U[0]
    mom = U[1]
    energy = U[2]
    rhoY = U[3]
    rho_safe = max(rho, 1e-12)
    u = mom / rho_safe
    kinetic = 0.5 * rho_safe * u * u
    p = (gamma - 1.0) * (energy - kinetic)
    F = np.empty(4, dtype=np.float64)
    F[0] = mom
    F[1] = mom * u + p
    F[2] = (energy + p) * u
    F[3] = rhoY * u
    return F


@jit(nopython=True)
def source_terms(U, dx, D, f, Tw, heat_transfer_enabled):
    """Compute wall friction and heat transfer source terms."""
    rho = U[0]
    mom = U[1]
    energy = U[2]
    rho_safe = max(rho, 1e-12)
    u = mom / rho_safe
    friction = -0.5 * rho_safe * u * np.abs(u) * f / D
    heat_transfer = 0.0
    if heat_transfer_enabled:
        # Placeholder: heat transfer is intentionally disabled in the current core.
        heat_transfer = 0.0
    S = np.zeros(3, dtype=np.float64)
    S[1] = friction
    S[2] = friction * u + heat_transfer
    return S


@jit(nopython=True)
def lax_wendroff_step(
    U_grid,
    dt,
    dx,
    areas,
    friction_coeffs,
    diameters,
    gamma,
    artificial_diffusion,
    clamp_rho_min,
    clamp_p_min,
    clamp_p_max,
    clamp_u_max,
    clamp_energy_max,
    heat_transfer_enabled,
):
    """Advance the conserved variables one time step with area variation handling."""
    n_cells = U_grid.shape[0]
    U_new = np.empty_like(U_grid)

    F_centers = np.empty_like(U_grid)
    for i in range(n_cells):
        F_centers[i] = flux_vector(U_grid[i], gamma)

    U_half = np.empty((n_cells - 1, 3), dtype=np.float64)
    F_half = np.empty_like(U_half)
    for i in range(n_cells - 1):
        U_half[i] = 0.5 * (U_grid[i + 1] + U_grid[i]) - 0.5 * dt / dx * (F_centers[i + 1] - F_centers[i])
        F_half[i] = flux_vector(U_half[i], gamma)

    for i in range(n_cells):
        if i == 0:
            dA_dx = (areas[i + 1] - areas[i]) / dx
        elif i == n_cells - 1:
            dA_dx = (areas[i] - areas[i - 1]) / dx
        else:
            dA_dx = (areas[i + 1] - areas[i - 1]) / (2.0 * dx)

        rho_i = U_grid[i, 0]
        mom_i = U_grid[i, 1]
        energy_i = U_grid[i, 2]
        rho_safe = max(rho_i, clamp_rho_min)
        u_i = mom_i / rho_safe
        p_i = (gamma - 1.0) * (energy_i - 0.5 * mom_i * u_i)
        if p_i < clamp_p_min:
            p_i = clamp_p_min

        geom_0 = -(rho_safe * u_i) * dA_dx / areas[i]
        geom_1 = -rho_safe * u_i * u_i * dA_dx / areas[i]
        geom_2 = -(u_i * (energy_i + p_i)) * dA_dx / areas[i]

        diameter = max(diameters[i], 1e-12)
        S = source_terms(U_grid[i], dx, diameter, friction_coeffs[i], 0.0, heat_transfer_enabled)
        S0 = S[0]
        S1 = S[1]
        S2 = S[2]

        if i == 0:
            flux_diff0 = F_half[i, 0]
            flux_diff1 = F_half[i, 1]
            flux_diff2 = F_half[i, 2]
        elif i == n_cells - 1:
            flux_diff0 = -F_half[i - 1, 0]
            flux_diff1 = -F_half[i - 1, 1]
            flux_diff2 = -F_half[i - 1, 2]
        else:
            flux_diff0 = F_half[i, 0] - F_half[i - 1, 0]
            flux_diff1 = F_half[i, 1] - F_half[i - 1, 1]
            flux_diff2 = F_half[i, 2] - F_half[i - 1, 2]

        coef = dt / dx
        U_new[i, 0] = U_grid[i, 0] - coef * flux_diff0 + dt * (S0 + geom_0)
        U_new[i, 1] = U_grid[i, 1] - coef * flux_diff1 + dt * (S1 + geom_1)
        U_new[i, 2] = U_grid[i, 2] - coef * flux_diff2 + dt * (S2 + geom_2)

    if artificial_diffusion > 0.0:
        for i in range(1, n_cells - 1):
            laplacian = U_grid[i + 1] - 2.0 * U_grid[i] + U_grid[i - 1]
            U_new[i] += artificial_diffusion * laplacian

    for i in range(n_cells):
        rho_i = max(U_new[i, 0], clamp_rho_min)
        mom_i = U_new[i, 1]
        u_i = mom_i / rho_i
        if u_i > clamp_u_max:
            u_i = clamp_u_max
        elif u_i < -clamp_u_max:
            u_i = -clamp_u_max
        mom_i = rho_i * u_i

        kinetic = 0.5 * rho_i * u_i * u_i
        pressure = (gamma - 1.0) * (U_new[i, 2] - kinetic)
        if pressure < clamp_p_min:
            energy_i = kinetic + clamp_p_min / (gamma - 1.0)
        elif pressure > clamp_p_max:
            energy_i = kinetic + clamp_p_max / (gamma - 1.0)
        else:
            energy_i = U_new[i, 2]
        energy_i = min(max(energy_i, kinetic), clamp_energy_max)

        U_new[i, 0] = rho_i
        U_new[i, 1] = mom_i
        U_new[i, 2] = energy_i

    return U_new


@jit(nopython=True)
def lax_wendroff_step_scalar(
    U_grid,
    dt,
    dx,
    areas,
    friction_coeffs,
    diameters,
    gamma,
    artificial_diffusion,
    clamp_rho_min,
    clamp_p_min,
    clamp_p_max,
    clamp_u_max,
    clamp_energy_max,
    heat_transfer_enabled,
):
    """Advance conserved variables with a passive scalar rho*Y."""
    n_cells = U_grid.shape[0]
    U_new = np.empty_like(U_grid)

    F_centers = np.empty_like(U_grid)
    for i in range(n_cells):
        F_centers[i] = flux_vector_scalar(U_grid[i], gamma)

    U_half = np.empty((n_cells - 1, 4), dtype=np.float64)
    F_half = np.empty_like(U_half)
    for i in range(n_cells - 1):
        U_half[i] = 0.5 * (U_grid[i + 1] + U_grid[i]) - 0.5 * dt / dx * (F_centers[i + 1] - F_centers[i])
        F_half[i] = flux_vector_scalar(U_half[i], gamma)

    for i in range(n_cells):
        if i == 0:
            dA_dx = (areas[i + 1] - areas[i]) / dx
        elif i == n_cells - 1:
            dA_dx = (areas[i] - areas[i - 1]) / dx
        else:
            dA_dx = (areas[i + 1] - areas[i - 1]) / (2.0 * dx)

        rho_i = U_grid[i, 0]
        mom_i = U_grid[i, 1]
        energy_i = U_grid[i, 2]
        rhoY_i = U_grid[i, 3]
        rho_safe = max(rho_i, clamp_rho_min)
        u_i = mom_i / rho_safe
        p_i = (gamma - 1.0) * (energy_i - 0.5 * mom_i * u_i)
        if p_i < clamp_p_min:
            p_i = clamp_p_min

        geom_0 = -(rho_safe * u_i) * dA_dx / areas[i]
        geom_1 = -rho_safe * u_i * u_i * dA_dx / areas[i]
        geom_2 = -(u_i * (energy_i + p_i)) * dA_dx / areas[i]
        geom_3 = -(rhoY_i * u_i) * dA_dx / areas[i]

        diameter = max(diameters[i], 1e-12)
        S = source_terms(U_grid[i], dx, diameter, friction_coeffs[i], 0.0, heat_transfer_enabled)
        S0 = S[0]
        S1 = S[1]
        S2 = S[2]
        S3 = 0.0

        if i == 0:
            flux_diff0 = F_half[i, 0]
            flux_diff1 = F_half[i, 1]
            flux_diff2 = F_half[i, 2]
            flux_diff3 = F_half[i, 3]
        elif i == n_cells - 1:
            flux_diff0 = -F_half[i - 1, 0]
            flux_diff1 = -F_half[i - 1, 1]
            flux_diff2 = -F_half[i - 1, 2]
            flux_diff3 = -F_half[i - 1, 3]
        else:
            flux_diff0 = F_half[i, 0] - F_half[i - 1, 0]
            flux_diff1 = F_half[i, 1] - F_half[i - 1, 1]
            flux_diff2 = F_half[i, 2] - F_half[i - 1, 2]
            flux_diff3 = F_half[i, 3] - F_half[i - 1, 3]

        coef = dt / dx
        U_new[i, 0] = U_grid[i, 0] - coef * flux_diff0 + dt * (S0 + geom_0)
        U_new[i, 1] = U_grid[i, 1] - coef * flux_diff1 + dt * (S1 + geom_1)
        U_new[i, 2] = U_grid[i, 2] - coef * flux_diff2 + dt * (S2 + geom_2)
        U_new[i, 3] = U_grid[i, 3] - coef * flux_diff3 + dt * (S3 + geom_3)

    if artificial_diffusion > 0.0:
        for i in range(1, n_cells - 1):
            laplacian = U_grid[i + 1] - 2.0 * U_grid[i] + U_grid[i - 1]
            U_new[i] += artificial_diffusion * laplacian

    for i in range(n_cells):
        rho_i = max(U_new[i, 0], clamp_rho_min)
        mom_i = U_new[i, 1]
        u_i = mom_i / rho_i
        if u_i > clamp_u_max:
            u_i = clamp_u_max
        elif u_i < -clamp_u_max:
            u_i = -clamp_u_max
        mom_i = rho_i * u_i

        kinetic = 0.5 * rho_i * u_i * u_i
        pressure = (gamma - 1.0) * (U_new[i, 2] - kinetic)
        if pressure < clamp_p_min:
            energy_i = kinetic + clamp_p_min / (gamma - 1.0)
        elif pressure > clamp_p_max:
            energy_i = kinetic + clamp_p_max / (gamma - 1.0)
        else:
            energy_i = U_new[i, 2]
        energy_i = min(max(energy_i, kinetic), clamp_energy_max)

        rhoY_i = U_new[i, 3]
        Y_i = rhoY_i / max(rho_i, clamp_rho_min)
        if Y_i < 0.0:
            Y_i = 0.0
        elif Y_i > 1.0:
            Y_i = 1.0
        rhoY_i = rho_i * Y_i

        U_new[i, 0] = rho_i
        U_new[i, 1] = mom_i
        U_new[i, 2] = energy_i
        U_new[i, 3] = rhoY_i

    return U_new


@jit(nopython=True)
def calculate_mass_flow_rate(
    p_up: float,
    p_down: float,
    T_up: float,
    area: float,
    Cd: float,
    gamma: float = DEFAULT_GAMMA,
    gas_constant: float = DEFAULT_R,
) -> float:
    """Compute isentropic mass flow rate from an upstream reservoir to a downstream region.

    Parameters
    ----------
    p_up : float
        Upstream (stagnation) pressure [Pa].
    p_down : float
        Downstream pressure [Pa].
    T_up : float
        Upstream (stagnation) temperature [K].
    area : float
        Effective throat/valve area [m^2].
    Cd : float
        Discharge coefficient (0-1).

    Returns
    -------
    float
        Mass flow rate [kg/s], always positive in the direction from upstream
        to downstream.
    """

    if area <= 0.0 or p_up <= 0.0 or T_up <= 0.0:
        return 0.0

    sign = 1.0
    p_up_eff = p_up
    p_down_eff = p_down
    if p_down > p_up:
        sign = -1.0
        p_up_eff = p_down
        p_down_eff = p_up

    pressure_ratio = p_down_eff / p_up_eff
    if pressure_ratio < 0.0:
        pressure_ratio = 0.0

    pcrit = (2.0 / (gamma + 1.0)) ** (gamma / (gamma - 1.0))
    coeff = Cd * area * p_up_eff * np.sqrt(gamma / (gas_constant * T_up))

    if pressure_ratio <= pcrit:
        exponent = (gamma + 1.0) / (2.0 * (gamma - 1.0))
        mdot = coeff * (2.0 / (gamma + 1.0)) ** exponent
    else:
        term1 = pressure_ratio ** (2.0 / gamma)
        term2 = pressure_ratio ** ((gamma + 1.0) / gamma)
        delta = term1 - term2
        if delta < 0.0:
            delta = 0.0
        mdot = coeff * np.sqrt((2.0 / (gamma - 1.0)) * delta)

    return sign * mdot
