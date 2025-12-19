from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def main() -> None:
    try:
        import numpy  # noqa: F401
    except Exception:
        print("NumPy is required to run the v2 toy demo. Install requirements-dev.txt.")
        return

    from core.advanced.coupling import ValveTiming
    from core.advanced.orchestrator import Orchestrator, OrchestratorConfig
    cfg = OrchestratorConfig()
    solver = Orchestrator(cfg)

    bore = 0.086
    stroke = 0.086
    conrod = 0.139
    clearance = 5e-5

    valve = ValveTiming(
        open_start_deg=360.0,
        open_end_deg=540.0,
        max_lift_m=0.008,
        seat_diameter_m=0.03,
        cd=0.9,
    )

    result = solver.run(
        rpm=3000.0,
        pipe_cells=30,
        pipe_length_m=0.6,
        pipe_diameter_m=0.04,
        bore_m=bore,
        stroke_m=stroke,
        conrod_m=conrod,
        clearance_m3=clearance,
        valve=valve,
    )

    ve_real = max(result["ve"], default=0.0)
    trapped = result["trapped_mass"][-1] if result["trapped_mass"] else 0.0
    work = result["indicated_work"][-1] if result["indicated_work"] else 0.0

    print("=== PyWaveDyn v2.0 Toy Case ===")
    print(f"VE_real (peak): {ve_real:.3f}")
    print(f"Trapped mass @ IVC: {trapped:.6f} kg")
    print(f"Indicated work: {work:.2f} J")


if __name__ == "__main__":
    main()
