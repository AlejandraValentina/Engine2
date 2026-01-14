import pytest

from core.advanced.orchestrator import _relax_downstream_totals


def test_coupling_under_relaxation_basic_and_ramp() -> None:
    prev = (100.0, 300.0, 0.2)
    current = (200.0, 400.0, 0.8)

    relaxed, alpha_eff = _relax_downstream_totals(prev, current, 1.0, 0, 0)
    assert relaxed == pytest.approx(current)
    assert alpha_eff == pytest.approx(1.0)

    relaxed, alpha_eff = _relax_downstream_totals(prev, current, 0.5, 0, 0)
    assert relaxed == pytest.approx((150.0, 350.0, 0.5))
    assert alpha_eff == pytest.approx(0.5)

    _, alpha0 = _relax_downstream_totals(prev, current, 0.2, 0, 3)
    _, alpha1 = _relax_downstream_totals(prev, current, 0.2, 1, 3)
    _, alpha2 = _relax_downstream_totals(prev, current, 0.2, 2, 3)
    assert alpha0 < alpha1 < alpha2
    assert alpha2 == pytest.approx(1.0)
