from core.advanced.junctions import estimate_K_from_geometry


def test_estimate_K_from_geometry_monotonic() -> None:
    k_small_angle = estimate_K_from_geometry(angle_deg=20.0, area_ratio=1.0, quality=0.5)
    k_large_angle = estimate_K_from_geometry(angle_deg=60.0, area_ratio=1.0, quality=0.5)
    assert k_large_angle > k_small_angle

    k_poor = estimate_K_from_geometry(angle_deg=45.0, area_ratio=1.0, quality=0.2)
    k_good = estimate_K_from_geometry(angle_deg=45.0, area_ratio=1.0, quality=0.8)
    assert k_poor > k_good
