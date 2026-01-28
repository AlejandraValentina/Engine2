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
    expectations = Path("validation_cases/expectations.json").resolve()

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
