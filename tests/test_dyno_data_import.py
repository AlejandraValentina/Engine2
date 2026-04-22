from __future__ import annotations

import json
from pathlib import Path

from pywavedyn.dyno_data import import_dyno_file


def test_import_dyno_csv_with_explicit_mapping_and_units(tmp_path: Path) -> None:
    source = tmp_path / "dyno.csv"
    source.write_text(
        "speed,torque,power,boost,map_abs,lam,egt\n"
        "3000,150,120,8,110,0.92,1450\n",
        encoding="utf-8",
    )

    payload, trace = import_dyno_file(
        source,
        source_format="csv",
        mapping={
            "rpm": "speed",
            "torque_nm": "torque",
            "power_hp": "power",
            "boost_kpa": "boost",
            "map_kpa": "map_abs",
            "lambda": "lam",
            "egt_c": "egt",
        },
        units={
            "torque_nm": "lbft",
            "power_hp": "kw",
            "boost_kpa": "psi_g",
            "map_kpa": "kpa_abs",
            "lambda": "lambda",
            "egt_c": "f",
        },
        engine_id="test_engine",
    )

    point = payload["points"][0]
    assert payload["engine_id"] == "test_engine"
    assert point["rpm"] == 3000.0
    assert point["torque_nm"] > 200.0
    assert point["power_hp"] > 150.0
    assert point["boost_kpa"] > 50.0
    assert point["map_kpa"] == 110.0
    assert point["lambda"] == 0.92
    assert point["egt_c"] > 700.0
    assert "boost_kpa" in trace["signals_present"]
    assert trace["signal_evidence"]["groups"]["turbo"]["status"] == "available"
    assert trace["signal_evidence"]["groups"]["fueling"]["status"] == "available"
    assert trace["signal_evidence"]["groups"]["thermal"]["status"] == "available"


def test_import_dyno_json_with_nested_mapping(tmp_path: Path) -> None:
    source = tmp_path / "dyno.json"
    source.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "channels": {
                            "rpm": 4000,
                            "hp": 150,
                            "afr": 13.5,
                            "lambda": 0.80,
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    payload, trace = import_dyno_file(
        source,
        source_format="json",
        mapping={
            "rpm": "channels.rpm",
            "power_hp": "channels.hp",
            "afr": "channels.afr",
            "lambda": "channels.lambda",
        },
        units={
            "power_hp": "hp",
            "afr": "afr",
            "lambda": "lambda",
        },
        engine_id="json_engine",
        afr_stoich=14.7,
    )

    assert payload["points"][0]["rpm"] == 4000.0
    assert payload["points"][0]["power_hp"] == 150.0
    assert payload["points"][0]["afr"] == 13.5
    assert payload["points"][0]["lambda"] == 0.80
    assert trace["import_warnings"]
    assert trace["signal_evidence"]["groups"]["fueling"]["status"] == "available"


def test_import_requires_torque_or_power(tmp_path: Path) -> None:
    source = tmp_path / "bad.csv"
    source.write_text("rpm,map\n3000,90\n", encoding="utf-8")

    try:
        import_dyno_file(
            source,
            source_format="csv",
            mapping={"rpm": "rpm", "map_kpa": "map"},
            units={"map_kpa": "kpa_abs"},
        )
    except ValueError as exc:
        assert "at least one of torque_nm or power_hp" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing torque/power mapping")
