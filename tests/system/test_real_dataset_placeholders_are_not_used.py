from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.mark.system
def test_real_dataset_placeholders_are_not_used() -> None:
    dataset_root = Path("benchmarks/datasets")
    real_dirs = sorted(p for p in dataset_root.iterdir() if p.is_dir() and p.name.endswith("_real"))
    assert real_dirs, "Expected at least one *_real dataset placeholder"

    for ds in real_dirs:
        meta_path = ds / "metadata.json"
        assert meta_path.exists(), f"Missing metadata.json for {ds.name}"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta.get("source") == "real_data"
        assert "PLACEHOLDER" in str(meta.get("notes", ""))

        targets_csv = ds / "targets.csv"
        assert targets_csv.exists(), f"Missing targets.csv for {ds.name}"
        lines = targets_csv.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1

    regression_dirs = sorted(
        p for p in dataset_root.iterdir() if p.is_dir() and "regression_golden" in p.name
    )
    assert all(not p.name.endswith("_real") for p in regression_dirs)
