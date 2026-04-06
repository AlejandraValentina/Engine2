from __future__ import annotations

import re
from pathlib import Path

import pytest


@pytest.mark.system
def test_docs_consistency() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    documentation = Path("docs/internal/DOCUMENTATION.md").read_text(encoding="utf-8")

    assert "docs/internal/FEATURES.md" in readme
    assert "docs/internal/VALIDATION_GUIDE.md" in readme

    forbidden_tokens = ["not implemented", "no implementado", "not-implemented"]
    lowered = readme.lower()
    for token in forbidden_tokens:
        assert token not in lowered

    assert re.search(r"Como comparar fidelidad", documentation)
    assert "bench-import" in documentation
