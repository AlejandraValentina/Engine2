from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.system
def test_real_dataset_transition_policy() -> None:
    dataset_root = Path("benchmarks/datasets")
    target_schema = _load_json(Path("schemas/bench_targets.schema.json"))
    real_dirs = sorted(p for p in dataset_root.iterdir() if p.is_dir() and p.name.endswith("_real"))
    assert real_dirs, "Expected at least one *_real dataset"

    canonical = {"k20_like_real", "v8_like_real"}
    placeholders = {"f1_like_real"}

    assert {p.name for p in real_dirs} == canonical | placeholders

    for name in sorted(canonical):
        ds = dataset_root / name
        meta = _load_json(ds / "metadata.json")
        target_path = ds / "target_curve.json"
        source_path = ds / "source.csv"
        target = _load_json(target_path)

        assert source_path.exists(), f"Canonical real dataset must commit source.csv: {name}"
        assert not (ds / "targets.csv").exists(), f"Canonical real dataset must not keep legacy targets.csv: {name}"
        assert target_path.exists(), f"Canonical real dataset must provide target_curve.json: {name}"
        assert meta["dataset_id"] == name
        assert meta["engine_id"] == name
        assert meta["source_type"] == "real_data"
        assert meta["source_file"] == "source.csv"
        assert meta["source_sha256"] == _sha256(source_path), f"Canonical real dataset hash must match committed source.csv: {name}"
        assert meta["signals_present"] == ["power_hp", "torque_nm"]
        assert meta["signal_evidence"]["groups"]["contract_baseline"]["status"] == "available"
        assert meta["signal_evidence"]["groups"]["turbo"]["status"] == "not_available"
        assert meta["signal_evidence"]["groups"]["fueling"]["status"] == "not_available"
        assert meta["signal_evidence"]["groups"]["thermal"]["status"] == "not_available"

        jsonschema.validate(target, target_schema)
        assert target.get("engine_id") == name, f"Canonical target_curve.json must stay aligned with engine_id: {name}"
        assert isinstance(target.get("points"), list) and target["points"], f"Canonical real dataset must have points: {name}"
        for idx, point in enumerate(target["points"]):
            assert point["rpm"] > 0.0, f"Canonical point RPM must be positive: {name}#{idx}"
            assert "torque_nm" in point or "power_hp" in point, (
                f"Canonical point must keep at least torque or power for scoring: {name}#{idx}"
            )

    for name in sorted(placeholders):
        ds = dataset_root / name
        meta = _load_json(ds / "metadata.json")
        targets_csv = ds / "targets.csv"

        assert not (ds / "target_curve.json").exists(), f"Placeholder dataset must not masquerade as canonical: {name}"
        assert not (ds / "source.csv").exists(), f"Placeholder dataset must not claim committed measured source: {name}"
        assert targets_csv.exists(), f"Placeholder dataset must keep legacy reminder file: {name}"
        assert meta.get("dataset_id") == name
        assert meta.get("source_type") == "real_data"
        assert meta.get("placeholder") is True
        assert "legacy" in str(meta.get("notes", "")).lower()
        assert "PLACEHOLDER" in str(meta.get("notes", ""))

        lines = targets_csv.read_text(encoding="utf-8").strip().splitlines()
        assert lines == ["rpm,torque_nm,power_hp"]
