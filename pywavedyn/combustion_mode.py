from __future__ import annotations

import copy

from core.engine_components import Engine


ADAPTIVE_COMBUSTION_MODES = {"as_is", "on", "off"}
ADAPTIVE_SUMMARY_KEYS = (
    "duration_scale",
    "ca50_offset_deg",
    "duration_min_deg",
    "duration_max_deg",
    "ca50_min_deg_atdc",
    "ca50_max_deg_atdc",
)


def normalize_adaptive_combustion_mode(mode: str | None) -> str:
    value = str(mode or "as_is").strip().lower()
    if value not in ADAPTIVE_COMBUSTION_MODES:
        raise ValueError(f"adaptive combustion mode must be one of {sorted(ADAPTIVE_COMBUSTION_MODES)}")
    return value


def summarize_combustion_mode(engine: Engine, *, requested_mode: str = "as_is") -> dict:
    adaptive_cfg = getattr(engine.combustion, "adaptive_model", {}) or {}
    summary = {
        "adaptive_mode_requested": normalize_adaptive_combustion_mode(requested_mode),
        "adaptive_enabled": bool(adaptive_cfg.get("enabled", False)),
        "adaptive_parameters": {},
        "adaptive_config_keys": sorted(adaptive_cfg.keys()),
    }
    for key in ADAPTIVE_SUMMARY_KEYS:
        if key in adaptive_cfg:
            summary["adaptive_parameters"][key] = float(adaptive_cfg[key])
    return summary


def apply_adaptive_combustion_mode(
    engine: Engine,
    engine_raw: dict,
    *,
    mode: str = "as_is",
) -> tuple[Engine, dict, dict]:
    requested_mode = normalize_adaptive_combustion_mode(mode)
    adjusted_engine = Engine.from_dict(engine.to_dict())
    adjusted_raw = copy.deepcopy(engine_raw)

    combustion_raw = adjusted_raw.setdefault("combustion", {})
    adaptive_cfg = dict(getattr(adjusted_engine.combustion, "adaptive_model", {}) or {})
    if "adaptive_model" in combustion_raw and isinstance(combustion_raw["adaptive_model"], dict):
        adaptive_cfg.update(combustion_raw["adaptive_model"])

    if requested_mode == "on":
        adaptive_cfg["enabled"] = True
    elif requested_mode == "off":
        adaptive_cfg["enabled"] = False

    adjusted_engine.combustion.adaptive_model = adaptive_cfg
    if adaptive_cfg:
        combustion_raw["adaptive_model"] = adaptive_cfg
    else:
        combustion_raw.pop("adaptive_model", None)

    summary = summarize_combustion_mode(adjusted_engine, requested_mode=requested_mode)
    return adjusted_engine, adjusted_raw, summary
