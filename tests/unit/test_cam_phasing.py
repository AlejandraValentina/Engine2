import math

import numpy as np

from core.engine_components import Camshaft


def _peak_angle(cam: Camshaft, intake: bool = True) -> float:
    angles = np.linspace(0.0, 720.0, 721)
    lifts = np.array([cam.get_lift(angle, intake=intake) for angle in angles])
    return float(angles[int(np.argmax(lifts))])


def _lift_integral(cam: Camshaft, intake: bool = True) -> float:
    angles = np.linspace(0.0, 720.0, 721)
    lifts = np.array([cam.get_lift(angle, intake=intake) for angle in angles])
    return float(np.trapezoid(lifts, angles))


def test_vvt_phase_zero_matches_baseline() -> None:
    base = Camshaft()
    phased = Camshaft(phase_deg_intake=0.0, phase_deg_exhaust=0.0)
    angles = np.linspace(0.0, 720.0, 181)
    lifts_base = np.array([base.get_lift(a, intake=True) for a in angles])
    lifts_phased = np.array([phased.get_lift(a, intake=True) for a in angles])
    assert np.allclose(lifts_base, lifts_phased, atol=1e-12)


def test_vvt_phase_shifts_lift_center() -> None:
    base = Camshaft()
    phase = 20.0
    phased = Camshaft(phase_deg_intake=phase)
    peak_base = _peak_angle(base, intake=True)
    peak_phased = _peak_angle(phased, intake=True)
    shift = (peak_phased - peak_base) % 720.0
    if shift > 360.0:
        shift -= 720.0
    assert math.isclose(shift, phase, abs_tol=1.0)


def test_vvt_phase_preserves_area_integral() -> None:
    base = Camshaft()
    phased = Camshaft(phase_deg_intake=35.0)
    area_base = _lift_integral(base, intake=True)
    area_phased = _lift_integral(phased, intake=True)
    assert math.isclose(area_base, area_phased, rel_tol=1e-3)
