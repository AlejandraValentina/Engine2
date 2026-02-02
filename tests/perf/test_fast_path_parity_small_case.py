import numpy as np
import pytest

pytest.importorskip("numpy")

from core.engine_components import Engine
from core.full_network import run_full_scope


@pytest.mark.perf
def test_fast_path_parity_small_case() -> None:
    engine = Engine()
    engine.exhaust.header_primary_diameter = max(engine.exhaust.header_primary_diameter, 80.0)
    baseline = run_full_scope(engine, duration_s=0.005, max_steps=8000, target_dx=0.1, use_numba=False, rpm=1500.0)
    fast = run_full_scope(engine, duration_s=0.005, max_steps=8000, target_dx=0.1, use_numba=True, rpm=1500.0)

    base_plenum = np.asarray(baseline.intake_plenum_pa, dtype=float)
    fast_plenum = np.asarray(fast.intake_plenum_pa, dtype=float)

    assert baseline.status == fast.status
    assert np.isfinite(base_plenum).all()
    assert np.isfinite(fast_plenum).all()
    assert float(fast_plenum[-1]) == pytest.approx(float(base_plenum[-1]), rel=1e-3, abs=5.0)
