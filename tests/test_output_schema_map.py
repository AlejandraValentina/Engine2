from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")


def _load_schema(name: str) -> dict:
    path = Path("schemas") / name
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.integration
def test_output_schema_map(tmp_path: Path) -> None:
    out_path = tmp_path / "map.json"
    preset = Path("presets/legacy/custom_twin_230cc.json").resolve()

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "map",
            "--engine",
            str(preset),
            "--rpm-grid",
            "2000,3000",
            "--throttle-grid",
            "0.5,1.0",
            "--out",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    schema = _load_schema("map.schema.json")
    jsonschema.validate(instance=payload, schema=schema)
