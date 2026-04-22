from __future__ import annotations

from pathlib import Path

from pywavedyn.dyno_data import parse_mapping_text, parse_units_text, write_dataset_package as write_flexible_dataset_package


def import_csv(path: Path, torque_units: str = "lbft", power_units: str = "hp", engine_id: str | None = None) -> dict:
    from pywavedyn.dyno_data import import_dyno_file

    payload, _trace = import_dyno_file(
        path,
        source_format="csv",
        mapping={"rpm": "rpm", "power_hp": "hp", "torque_nm": "tq"},
        units={"torque_nm": torque_units, "power_hp": power_units},
        engine_id=engine_id,
    )
    return payload


def write_targets(payload: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(__import__("json").dumps(payload, indent=2), encoding="utf-8")


def write_dataset_package(
    csv_path: Path,
    dataset_dir: Path,
    *,
    dataset_id: str,
    engine_id: str,
    preset_path: str,
    torque_units: str,
    power_units: str,
    notes: str,
    error_contract: dict,
) -> None:
    write_flexible_dataset_package(
        csv_path,
        dataset_dir,
        dataset_id=dataset_id,
        engine_id=engine_id,
        preset_path=preset_path,
        notes=notes,
        error_contract=error_contract,
        source_format="csv",
        mapping={"rpm": "rpm", "power_hp": "hp", "torque_nm": "tq"},
        units={"torque_nm": torque_units, "power_hp": power_units},
    )


__all__ = [
    "import_csv",
    "write_targets",
    "write_dataset_package",
    "parse_mapping_text",
    "parse_units_text",
]
