import pytest

from core.engine_components import Engine


def test_validate_with_issues_reports_invalid_block_geometry() -> None:
    engine = Engine()
    engine.block.bore = 0.0
    issues = engine.validate_with_issues()
    assert issues
    assert any("Block geometry" in issue for issue in issues)
    assert engine.validate(strict=False) is False


def test_validate_strict_raises() -> None:
    engine = Engine()
    engine.block.stroke = 0.0
    with pytest.raises(ValueError):
        engine.validate(strict=True)
