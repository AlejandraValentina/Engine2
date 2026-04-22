from __future__ import annotations

from pywavedyn.analysis_evidence import build_signal_evidence


def test_signal_evidence_marks_missing_optional_groups_honestly() -> None:
    evidence = build_signal_evidence(dataset_signals=["power_hp", "torque_nm"])

    assert evidence["groups"]["contract_baseline"]["status"] == "available"
    assert evidence["groups"]["turbo"]["status"] == "not_available"
    assert evidence["groups"]["fueling"]["status"] == "not_available"
    assert evidence["groups"]["thermal"]["status"] == "not_available"
    assert "No committed turbo evidence" in evidence["groups"]["turbo"]["note"]


def test_signal_evidence_distinguishes_compared_from_present_not_compared() -> None:
    evidence = build_signal_evidence(
        dataset_signals=["power_hp", "torque_nm", "boost_kpa", "egt_c"],
        compared_signals=["power_hp", "torque_nm", "boost_kpa"],
        skipped_signals=["egt_c"],
    )

    assert evidence["groups"]["contract_baseline"]["status"] == "compared"
    assert evidence["groups"]["turbo"]["status"] == "compared"
    assert evidence["groups"]["thermal"]["status"] == "present_not_compared"
    assert evidence["groups"]["thermal"]["signals_skipped"] == ["egt_c"]
