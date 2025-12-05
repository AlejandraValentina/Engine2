import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PRESET_DIRS = [ROOT / "presets", ROOT / "presets" / "legacy"]


def _cylinder_volume_cc(bore_mm: float, stroke_mm: float) -> float:
    """Compute swept volume per cylinder in cubic centimeters using mm inputs."""
    return math.pi * (bore_mm ** 2) * stroke_mm / 4.0 / 1000.0


def _iter_presets():
    for preset_dir in PRESET_DIRS:
        for path in preset_dir.glob("*.json"):
            yield path


def test_combustion_chamber_override_matches_compression_ratio():
    for path in _iter_presets():
        data = json.loads(path.read_text(encoding="utf-8"))

        block = data.get("block", {})
        head = data.get("head", {})
        bore = float(block.get("bore", 0.0))
        stroke = float(block.get("stroke", 0.0))
        compression_ratio = head.get("compression_ratio")
        chamber_override = head.get("combustion_chamber_vol")

        if chamber_override is None or compression_ratio is None:
            continue

        vd_cc = _cylinder_volume_cc(bore, stroke)
        vc_cc = float(chamber_override)
        cr_eff = (vd_cc + vc_cc) / vc_cc
        rel_error = abs(cr_eff - compression_ratio) / compression_ratio

        assert rel_error < 0.01, (
            f"{path.name}: CR effective {cr_eff:.3f} vs declared {compression_ratio:.3f} "
            f"(Vd={vd_cc:.2f} cc, Vc={vc_cc:.2f} cc, rel error={rel_error:.4f})"
        )

