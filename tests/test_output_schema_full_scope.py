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
def test_output_schema_full_scope(tmp_path: Path) -> None:
    out_path = tmp_path / "full_scope.json"
    preset = Path("presets/legacy/custom_twin_230cc.json").resolve()

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "full-scope",
            "--engine",
            str(preset),
            "--duration",
            "0.004",
            "--max-steps",
            "400",
            "--target-dx",
            "0.16",
            "--out",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    schema = _load_schema("full_scope.schema.json")
    jsonschema.validate(instance=payload, schema=schema)
