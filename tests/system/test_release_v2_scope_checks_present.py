from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.system
def test_release_v2_scope_docs_and_features_present() -> None:
    scope_doc = Path("docs/RELEASE_V2_SCOPE.md")
    checks_doc = Path("docs/RELEASE_V2_0_CHECKS.md")
    features = Path("FEATURES.md")

    assert scope_doc.exists()
    assert checks_doc.exists()
    assert features.exists()

    text = features.read_text(encoding="utf-8")
    required = [
        "Acople 0D↔1D bidireccional",
        "Síntesis multi-cilindro",
        "Barridos automáticos sin GUI",
        "Reporte/cut-list reproducible",
        "presets legacy",
    ]
    for needle in required:
        lines = [line for line in text.splitlines() if needle in line]
        assert lines, f"Missing FEATURES entry for: {needle}"
        assert any("[x]" in line for line in lines), f"Entry not marked complete: {needle}"
