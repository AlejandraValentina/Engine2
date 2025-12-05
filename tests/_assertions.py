import math


def assert_hp_tq_consistency(hp: float, tq_nm: float, rpm: float, rel_tol: float = 0.03) -> None:
    hp_from_tq = tq_nm * rpm * 2.0 * math.pi / 60.0 / 745.7
    if hp_from_tq == 0:
        assert hp == 0
        return
    diff = abs(hp - hp_from_tq) / max(abs(hp_from_tq), 1e-9)
    assert diff <= rel_tol, f"HP/TQ mismatch at {rpm} rpm: hp={hp:.3f} hp_from_tq={hp_from_tq:.3f}"  # noqa: E501


def bmep_from_torque_bar(tq_nm: float, displacement_cc: float) -> float:
    disp_m3 = max(displacement_cc * 1e-6, 1e-12)
    return tq_nm * 4.0 * math.pi / disp_m3 / 100000.0


def assert_bmep_consistency(bmep_bar: float, tq_nm: float, displacement_cc: float, abs_tol_bar: float = 0.5) -> None:
    expected = bmep_from_torque_bar(tq_nm, displacement_cc)
    assert abs(bmep_bar - expected) <= abs_tol_bar, (
        f"BMEP mismatch: got {bmep_bar:.3f} bar expected {expected:.3f} bar"
    )


def assert_sanity_bounds(results: dict, bmep_band: tuple, ve_band: tuple) -> None:
    bmep = results.get("bmep_bar")
    ve_value = results.get("ve") if results.get("ve") is not None else results.get("ve_percent")
    assert bmep is not None, "bmep_bar not present in results"
    assert ve_value is not None, "ve/ve_percent not present in results"
    assert bmep_band[0] <= bmep <= bmep_band[1], f"BMEP {bmep:.3f} outside band {bmep_band}"
    assert ve_band[0] <= ve_value <= ve_band[1], f"VE {ve_value:.2f} outside band {ve_band}"
