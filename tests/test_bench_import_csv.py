from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from pywavedyn.bench_import import _LBFT_TO_NM

jsonschema = pytest.importorskip("jsonschema")


def test_bench_import_csv_parses_and_writes(tmp_path: Path) -> None:
    csv_path = tmp_path / "curve.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["rpm", "hp", "tq"])
        writer.writerow([2000, 50, 100])
        writer.writerow([4000, 80, 120])

    out_path = tmp_path / "targets.json"
    from pywavedyn.bench_import import import_csv, write_targets

    payload = import_csv(csv_path, torque_units="lbft", power_units="hp", engine_id="test_case")
    write_targets(payload, out_path)

    loaded = json.loads(out_path.read_text(encoding="utf-8"))
    schema = json.loads(Path("schemas/bench_targets.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=loaded, schema=schema)

    assert loaded["engine_id"] == "test_case"
    assert loaded["points"][0]["power_hp"] == 50
    assert loaded["points"][0]["torque_nm"] == pytest.approx(100 * _LBFT_TO_NM)
