import math

from core.advanced.orchestrator import _throttle_area_eff, _throttle_is_active, _update_throttle_position
from core.engine_components import Throttle


def test_throttle_rate_limit_no_overshoot() -> None:
    pos = 0.0
    rate_limit = 2.0
    dt = 0.1
    positions = []
    for _ in range(10):
        pos = _update_throttle_position(pos, 1.0, dt, rate_limit)
        positions.append(pos)

    assert all(0.0 <= p <= 1.0 for p in positions)
    assert all(positions[i] <= positions[i + 1] for i in range(len(positions) - 1))
    assert positions[-1] <= 1.0


def test_throttle_wot_parity_with_rate_limit() -> None:
    throttle = Throttle(
        enabled=True,
        position=1.0,
        body_diam_m=0.07,
        cd=1.0,
        area_exponent=2.0,
        rate_limit_per_s=5.0,
    )
    pos = _update_throttle_position(1.0, throttle.position, 0.1, throttle.rate_limit_per_s)

    assert _throttle_is_active(throttle, pos) is False
    area_eff = _throttle_area_eff(throttle, pos)
    area_max = math.pi * (0.07 * 0.5) ** 2
    assert abs(area_eff - area_max) < 1e-12


def test_throttle_safety_clamps_exponent() -> None:
    throttle = Throttle(
        enabled=True,
        position=0.5,
        body_diam_m=0.07,
        cd=1.0,
        area_exponent=0.3,
        safety_clamps=True,
    )
    area_eff = _throttle_area_eff(throttle)
    area_max = math.pi * (0.07 * 0.5) ** 2
    assert abs(area_eff - area_max * 0.5) < 1e-12
