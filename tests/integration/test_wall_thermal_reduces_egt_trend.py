from __future__ import annotations

import numpy as np
import pytest

from core.advanced.orchestrator import _apply_pipe_wall_thermal
from core.advanced.state import Primitive1D, primitive_to_conserved
from core.advanced.solver_1d import conserved_to_primitive
from core.engine_components import WallThermalConfig


@pytest.mark.integration
def test_wall_thermal_reduces_egt_trend() -> None:
    gamma = 1.35
    gas_constant = 287.0
    p0 = 120000.0
    T0 = 900.0
    rho = p0 / (gas_constant * T0)
    prim = Primitive1D(rho=rho, u=0.0, p=p0, T=T0, Y=0.0)
    cons = primitive_to_conserved(prim, gamma, gas_constant)

    n_cells = 6
    U = np.zeros((n_cells + 2, 4), dtype=float)
    U[1:-1, 0] = cons.rho
    U[1:-1, 1] = cons.rhou
    U[1:-1, 2] = cons.rhoE
    U[1:-1, 3] = cons.rhoY
    U[0] = U[1]
    U[-1] = U[-2]

    cfg = WallThermalConfig(
        enabled=True,
        h_model="constant",
        h_w_per_m2k=250.0,
        area_m2=0.05,
        m_wall_kg=1.0,
        cp_wall_j_per_kgk=500.0,
        twall_init_k=400.0,
    )

    prim_before = conserved_to_primitive(U[1:-1], gamma, gas_constant)
    T_before = float(np.mean(prim_before[:, 3]))

    _apply_pipe_wall_thermal(
        U,
        dt=1e-3,
        cfg=cfg,
        twall_k=cfg.twall_init_k,
        pipe_volume=0.002,
        gamma=gamma,
        gas_constant=gas_constant,
    )

    prim_after = conserved_to_primitive(U[1:-1], gamma, gas_constant)
    T_after = float(np.mean(prim_after[:, 3]))

    assert T_after <= T_before


@pytest.mark.integration
def test_wall_thermal_dittus_boelter_reduces_temp() -> None:
    gamma = 1.35
    gas_constant = 287.0
    p0 = 120000.0
    T0 = 900.0
    rho = p0 / (gas_constant * T0)
    prim = Primitive1D(rho=rho, u=80.0, p=p0, T=T0, Y=0.0)
    cons = primitive_to_conserved(prim, gamma, gas_constant)

    n_cells = 6
    U = np.zeros((n_cells + 2, 4), dtype=float)
    U[1:-1, 0] = cons.rho
    U[1:-1, 1] = cons.rhou
    U[1:-1, 2] = cons.rhoE
    U[1:-1, 3] = cons.rhoY
    U[0] = U[1]
    U[-1] = U[-2]

    cfg = WallThermalConfig(
        enabled=True,
        h_model="dittus_boelter",
        mu_model="sutherland",
        h_w_per_m2k=250.0,
        area_m2=0.05,
        m_wall_kg=1.0,
        cp_wall_j_per_kgk=500.0,
        twall_init_k=400.0,
    )

    prim_before = conserved_to_primitive(U[1:-1], gamma, gas_constant)
    T_before = float(np.mean(prim_before[:, 3]))

    _apply_pipe_wall_thermal(
        U,
        dt=1e-3,
        cfg=cfg,
        twall_k=cfg.twall_init_k,
        pipe_volume=0.002,
        gamma=gamma,
        gas_constant=gas_constant,
    )

    prim_after = conserved_to_primitive(U[1:-1], gamma, gas_constant)
    T_after = float(np.mean(prim_after[:, 3]))

    assert T_after <= T_before
