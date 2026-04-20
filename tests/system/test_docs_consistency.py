from __future__ import annotations

import re
from pathlib import Path

import pytest


@pytest.mark.system
def test_docs_consistency() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    benchmarks_readme = Path("benchmarks/README.md").read_text(encoding="utf-8")
    benchmarks_method = Path("docs/BENCHMARKS_METHOD.md").read_text(encoding="utf-8")
    gui_overview = Path("docs/GUI_OVERVIEW.md").read_text(encoding="utf-8")
    runbook = Path("docs/RUNBOOK.md").read_text(encoding="utf-8")
    documentation = Path("docs/internal/DOCUMENTATION.md").read_text(encoding="utf-8")

    assert "docs/internal/FEATURES.md" in readme
    assert "docs/internal/VALIDATION_GUIDE.md" in readme

    forbidden_tokens = ["not implemented", "no implementado", "not-implemented"]
    lowered = readme.lower()
    for token in forbidden_tokens:
        assert token not in lowered

    assert re.search(r"Como comparar fidelidad", documentation)
    assert "bench-import" in documentation

    shared_policy_tokens = [
        "k20_like_real",
        "v8_like_real",
        "f1_like_real",
        "source_sha256",
        "target_curve.json",
        "source.csv",
        "targets.csv",
    ]
    placeholder_policy_tokens = [
        "placeholder legacy dataset",
    ]

    for text in (readme, benchmarks_readme, benchmarks_method, runbook):
        for token in shared_policy_tokens:
            assert token in text
        for token in placeholder_policy_tokens:
            assert token in text

    assert "canonical" in readme and "real-data package" in readme
    assert "canonical" in benchmarks_readme and "real-data package" in benchmarks_readme
    assert "canonical" in benchmarks_method and "real-data package" in benchmarks_method
    assert "canonical" in runbook and "real-data package" in runbook
    assert "not a canonical committed real-data package" in readme
    assert "not part of the canonical package format" in benchmarks_readme
    assert "not yet migrated to the canonical package format" in benchmarks_method
    assert "do not treat `f1_like_real` as a canonical committed real-data package" in runbook

    official_outcomes = [
        "improved",
        "partial_improvement",
        "tradeoff",
        "no_clear_benefit",
        "no_conclusion",
    ]
    official_robustness_levels = [
        "low_sensitivity",
        "moderate_sensitivity",
        "high_sensitivity",
    ]
    official_stage_statuses = [
        "accepted",
        "rejected",
        "omitted",
    ]

    for text in (readme, runbook, gui_overview):
        for token in official_outcomes:
            assert f"`{token}`" in text

    for text in (readme, runbook, gui_overview):
        for token in official_robustness_levels:
            assert f"`{token}`" in text

    for text in (runbook, gui_overview):
        for token in official_stage_statuses:
            assert f"`{token}`" in text

    common_envelope_tokens = [
        "report_type",
        "report_format_version",
        "report_family",
        "generated_at_utc",
        "context",
    ]
    for text in (readme, runbook, gui_overview):
        for token in common_envelope_tokens:
            assert f"`{token}`" in text

    ve_semantics_tokens = [
        "`ve_actual`",
        "`observable_semantics.ve_actual`",
    ]
    for text in (readme, runbook, gui_overview):
        for token in ve_semantics_tokens:
            assert token in text

    signal_evidence_tokens = [
        "`signal_evidence`",
        "`contract_baseline`",
        "`turbo`",
        "`fueling`",
        "`thermal`",
    ]
    for text in (readme, benchmarks_readme, benchmarks_method, runbook):
        for token in signal_evidence_tokens:
            assert token in text
