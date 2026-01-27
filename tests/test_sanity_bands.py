import copy

import pytest

np = pytest.importorskip("numpy")

from core.engine_components import Engine
from core.thermo import CylinderSimulator
try:  # Prefer relative import to avoid clashes with site-level `tests` packages
    from ._assertions import assert_sanity_bounds
except ImportError:  # Fallback for environments that resolve absolute first
    from tests._assertions import assert_sanity_bounds

pytestmark = [pytest.mark.slow]


@pytest.mark.integration
@pytest.mark.parametrize(
    "label,rpm,bmep_band,ve_band",
    [
        ("Eco_1600", 6000.0, (5.0, 9.0), (85.0, 110.0)),
        ("K20", 8000.0, (9.0, 13.5), (110.0, 135.0)),
        ("V8_350", 6000.0, (7.5, 11.5), (100.0, 130.0)),
        ("V10", 8500.0, (11.0, 16.5), (120.0, 150.0)),
        ("F1_V12", 17000.0, (6.0, 9.5), (100.0, 130.0)),
        ("Kart_125", 10500.0, (2.5, 5.0), (115.0, 150.0)),
    ],
)
def test_sanity_bands(
    label,
    rpm,
    bmep_band,
    ve_band,
    k20_config,
    v8_config,
    eco_config,
    v10_config,
    f1_v12_config,
    kart_125_config,
):
    cfg_map = {
        "Eco_1600": eco_config,
        "K20": k20_config,
        "V8_350": v8_config,
        "V10": v10_config,
        "F1_V12": f1_v12_config,
        "Kart_125": kart_125_config,
    }
    cfg = copy.deepcopy(cfg_map[label])
    engine = Engine.from_dict(cfg)
    results = CylinderSimulator(engine).run_cycle(rpm)

    print(
        f"[{label}] rpm={rpm:.0f} hp={results['mean_power_hp']:.2f} tq={results['mean_torque_nm']:.2f} bmep={results.get('bmep_bar'):.3f} ve={results.get('ve'):.2f}"
    )
    assert_sanity_bounds(results, bmep_band, ve_band)
