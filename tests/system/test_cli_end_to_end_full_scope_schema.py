from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")
pytest.importorskip("numpy")


@pytest.mark.system
def test_cli_end_to_end_full_scope_schema(tmp_path: Path) -> None:
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
            "0.01",
            "--target-dx",
            "0.05",
            "--max-steps",
            "120",
            "--out",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    schema = json.loads(Path("schemas/full_scope.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=payload, schema=schema)
