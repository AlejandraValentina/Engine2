from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from core.advanced.orchestrator import Orchestrator
from core.pro_dyno_v2 import ProDynoV2Runner
from core.simulator import Engine1DSolver
from pywavedyn.cli import run_dyno


PRESET = Path("presets/legacy/custom_twin_230cc.json")


def _boom(label: str):
    def _raise(*_args, **_kwargs):
        raise AssertionError(f"Unexpected call to {label} in v1 default path")

    return _raise


def test_coupling_disabled_noop_does_not_call_advanced(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(ProDynoV2Runner, "run_sweep", _boom("ProDynoV2Runner.run_sweep"))
    monkeypatch.setattr(Engine1DSolver, "run_full_simulation", _boom("Engine1DSolver.run_full_simulation"))
    monkeypatch.setattr(Orchestrator, "run", _boom("Orchestrator.run"))

    out_path = tmp_path / "dyno.json"
    run_dyno(PRESET, "2000", out_path, mode="v1")

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    coupling_mode = payload.get("metadata", {}).get("coupling_mode")
    assert coupling_mode == "none", f"Expected coupling_mode='none', got {coupling_mode!r}"

    results = payload.get("results", [])
    assert len(results) == 1, f"Expected 1 result, got {len(results)}"
    entry = results[0]

    for key in ("rpm", "mean_power_hp", "mean_torque_nm", "bmep_bar", "ve_actual"):
        assert key in entry, f"Missing key '{key}' in result"
        value = float(entry[key])
        assert math.isfinite(value), f"Non-finite {key}={value}"

    assert float(entry["rpm"]) > 0.0, f"rpm must be positive, got {entry['rpm']}"
