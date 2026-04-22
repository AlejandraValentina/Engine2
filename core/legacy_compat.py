from __future__ import annotations

from typing import Any

from core.engine_components import Engine


LEGACY_PROFILE_V1 = "v1"


def apply_legacy_compat(engine_raw: dict[str, Any], engine: Engine, profile: str = LEGACY_PROFILE_V1) -> dict[str, Any]:
    if profile != LEGACY_PROFILE_V1:
        raise ValueError(f"Unsupported legacy compatibility profile '{profile}'")

    overrides: dict[str, Any] = {}
    settings = engine.simulation_settings

    def _set(path: str, setter, value: Any) -> None:
        setter(value)
        overrides[path] = value

    _set("simulation_settings.cp_model", lambda v: setattr(settings, "cp_model", v), "constant")
    _set("simulation_settings.enable_heat_transfer_1d", lambda v: setattr(settings, "enable_heat_transfer_1d", v), False)
    _set("simulation_settings.enable_0d_to_1d_exhaust_coupling", lambda v: setattr(settings, "enable_0d_to_1d_exhaust_coupling", v), False)
    _set("simulation_settings.tuning_sensitivity", lambda v: setattr(settings, "tuning_sensitivity", v), 1.0)

    if settings.wall_thermal is not None:
        _set("simulation_settings.wall_thermal.enabled", lambda v: setattr(settings.wall_thermal, "enabled", v), False)

    settings.shock_cfl = {"enabled": False}
    overrides["simulation_settings.shock_cfl.enabled"] = False

    settings.intake_coupling = {"enabled": False}
    overrides["simulation_settings.intake_coupling.enabled"] = False

    engine.combustion.residual_coupling = {"enabled": False}
    overrides["combustion.residual_coupling.enabled"] = False

    engine_raw.setdefault("meta", {})["legacy_compat"] = profile

    return overrides
