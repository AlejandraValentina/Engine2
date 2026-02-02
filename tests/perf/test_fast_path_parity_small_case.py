import numpy as np
import pytest

pytest.importorskip("numpy")

from core.engine_components import Engine
from core.full_network import run_full_scope


@pytest.mark.perf
def test_fast_path_parity_small_case() -> None:
    engine = Engine()
    baseline = run_full_scope(engine, duration_s=0.01, max_steps=800, target_dx=0.05, use_numba=False)
    fast = run_full_scope(engine, duration_s=0.01, max_steps=800, target_dx=0.05, use_numba=True)

    base_plenum = np.asarray(baseline.intake_plenum_pa, dtype=float)
    fast_plenum = np.asarray(fast.intake_plenum_pa, dtype=float)

    assert baseline.status == fast.status
    assert np.isfinite(base_plenum).all()
    assert np.isfinite(fast_plenum).all()
    assert float(fast_plenum[-1]) == pytest.approx(float(base_plenum[-1]), rel=1e-3, abs=5.0)
