"""Audit preset compression-ratio consistency.

By default the script prints effective compression ratios and suggested
combustion chamber volumes for each preset. Use `--fix` to rewrite
`combustion_chamber_vol` values to match the declared compression ratio.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRESET_DIRS = [ROOT / "presets", ROOT / "presets" / "legacy"]


def cylinder_volume_cc(bore_mm: float, stroke_mm: float) -> float:
    return math.pi * (bore_mm ** 2) * stroke_mm / 4.0 / 1000.0


def iter_presets():
    for preset_dir in PRESET_DIRS:
        yield from preset_dir.glob("*.json")


def audit_preset(path: Path, fix: bool = False, tolerance: float = 0.01) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    block = data.get("block", {})
    head = data.get("head", {})
    bore = float(block.get("bore", 0.0))
    stroke = float(block.get("stroke", 0.0))
    compression_ratio = head.get("compression_ratio")
    chamber_override = head.get("combustion_chamber_vol")

    if compression_ratio is None:
        print(f"{path.name}: missing compression_ratio; skipping")
        return

    vd_cc = cylinder_volume_cc(bore, stroke)
    suggested_vc = vd_cc / (compression_ratio - 1.0) if compression_ratio > 1.0 else float("nan")

    if chamber_override is None:
        print(
            f"{path.name}: Vd={vd_cc:.2f} cc, declared CR={compression_ratio:.3f}, "
            f"no override (suggested Vc={suggested_vc:.2f} cc)"
        )
        return

    vc_cc = float(chamber_override)
    cr_eff = (vd_cc + vc_cc) / vc_cc
    rel_error = abs(cr_eff - compression_ratio) / compression_ratio
    msg = (
        f"{path.name}: Vd={vd_cc:.2f} cc, Vc={vc_cc:.2f} cc, declared CR={compression_ratio:.3f}, "
        f"effective CR={cr_eff:.3f}, mismatch={rel_error*100:.2f}%"
    )
    if rel_error >= tolerance:
        msg += f" (suggested Vc={suggested_vc:.2f} cc)"
    print(msg)

    if fix and rel_error >= tolerance and math.isfinite(suggested_vc):
        head["combustion_chamber_vol"] = round(suggested_vc, 2)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"  -> updated combustion_chamber_vol to {head['combustion_chamber_vol']} cc")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", action="store_true", help="rewrite combustion_chamber_vol to match declared CR")
    parser.add_argument("--tolerance", type=float, default=0.01, help="allowed relative CR mismatch (default 1%)")
    args = parser.parse_args()

    for path in iter_presets():
        audit_preset(path, fix=args.fix, tolerance=args.tolerance)


if __name__ == "__main__":
    main()

