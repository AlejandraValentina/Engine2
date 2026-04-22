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
def test_selfcheck_schema_validates(tmp_path: Path) -> None:
    out_path = tmp_path / "selfcheck.json"
    preset = Path("presets/legacy/custom_twin_230cc.json").resolve()
    expectations = tmp_path / "expectations.json"
    expectations.write_text(
        json.dumps({"cases": [{"file": str(preset), "rpm": [2000]}]}, indent=2),
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "selfcheck",
            "--expectations",
            str(expectations),
            "--out",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    schema = _load_schema("selfcheck.schema.json")
    jsonschema.validate(instance=payload, schema=schema)
