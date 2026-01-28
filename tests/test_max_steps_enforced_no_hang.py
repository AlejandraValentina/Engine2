import pytest

pytest.importorskip("numpy")

from core.engine_components import Engine
from core.full_network import run_full_scope


def test_max_steps_enforced_no_hang() -> None:
    engine = Engine()
    with pytest.raises(RuntimeError):
        run_full_scope(engine, duration_s=0.01, max_steps=1, target_dx=0.1)
