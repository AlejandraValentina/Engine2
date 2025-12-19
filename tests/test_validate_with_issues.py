from core.engine_components import Engine


def test_validate_with_issues_empty_for_valid_engine() -> None:
    engine = Engine()
    assert engine.validate_with_issues() == []


def test_validate_with_issues_order_stable() -> None:
    engine = Engine()
    engine.block.bore = 0.0
    engine.block.num_cylinders = 0
    engine.head.compression_ratio = 1.0

    issues = engine.validate_with_issues()
    assert issues == [
        "Block geometry must be positive (bore/stroke/conrod)",
        "Engine must have at least one cylinder",
        "Compression ratio must exceed 1.0",
    ]


def test_validate_non_strict_matches_issues() -> None:
    engine = Engine()
    engine.block.stroke = 0.0
    assert engine.validate(strict=False) is False
    assert engine.validate_with_issues()
