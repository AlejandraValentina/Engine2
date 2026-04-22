from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")
pytest.importorskip("numpy")


def _run_dyno(tmp_path: Path, engine: Path, rpm: str, turbo: Path | None) -> dict:
    out_path = tmp_path / ("dyno_turbo.json" if turbo else "dyno_na.json")
    cmd = [
        sys.executable,
        "-m",
        "pywavedyn.cli",
        "dyno",
        "--engine",
        str(engine),
        "--rpm",
        rpm,
        "--out",
        str(out_path),
    ]
    if turbo is not None:
        cmd.extend(["--turbo", str(turbo)])
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    schema = json.loads(Path("schemas/dyno.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=payload, schema=schema)
    return payload


@pytest.mark.system
def test_cli_dyno_turbo_trend(tmp_path: Path) -> None:
    engine = Path("presets/honda_k20.json").resolve()
    turbo = Path("presets/turbo_simple.json").resolve()

    rpm = "4000"
    na = _run_dyno(tmp_path, engine, rpm, None)
    boosted = _run_dyno(tmp_path, engine, rpm, turbo)

    na_hp = float(na["results"][0]["mean_power_hp"])
    boosted_hp = float(boosted["results"][0]["mean_power_hp"])
    assert boosted_hp > na_hp
