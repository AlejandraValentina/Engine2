from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")


@pytest.mark.system
def test_calibrate_bmep_cli_schema(tmp_path: Path) -> None:
    engine = Path("presets/v12_1710cc_15k_superbike_target.json").resolve()
    out_path = tmp_path / "calibrate_bmep.json"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "calibrate-bmep",
            "--engine",
            str(engine),
            "--rpm",
            "10000",
            "--target-bmep",
            "12.5",
            "--ca50-range",
            "6:12:2",
            "--duration-range",
            "14:26:4",
            "--out",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    schema = json.loads(Path("schemas/calibrate_bmep.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=payload, schema=schema)
