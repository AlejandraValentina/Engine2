import math

from core.engine_components import Camshaft, Engine


K20_CONFIG = {
    "block": {
        "bore": 86.0,
        "stroke": 86.0,
        "conrod_length": 139.0,
        "num_cylinders": 4,
        "config": "L",
        "bank_angle": 0.0,
        "firing_order": [1, 3, 4, 2],
    },
    "head": {
        "compression_ratio": 11.5,
        "intake_valves": 2,
        "exhaust_valves": 2,
        "combustion_chamber_vol": 47.6,
    },
    "cam": {
        "intake_lift": 11.5,
        "exhaust_lift": 10.5,
        "intake_duration": 265.0,
        "exhaust_duration": 260.0,
        "lobe_separation": 107.0,
        "advance": 0.0,
    },
}


def test_engine_from_dict_accepts_cam_alias():
    engine = Engine.from_dict(K20_CONFIG)
    assert math.isclose(engine.camshaft.intake_lift, 11.5)
    assert math.isclose(engine.camshaft.exhaust_duration, 260.0)


def test_displacement_reasonable_for_k20():
    engine = Engine.from_dict(K20_CONFIG)
    disp = engine.block.displacement_cc
    assert 1900.0 < disp < 2100.0


def test_camshaft_lift_non_negative():
    cam = Camshaft(intake_lift=12.0, exhaust_lift=11.0, lobe_separation=110.0, advance=0.0)
    angles = [0.0, 180.0, 360.0, 540.0, 720.0]
    for angle in angles:
        assert cam.get_lift(angle, intake=True) >= 0.0
        assert cam.get_lift(angle, intake=False) >= 0.0
