from types import SimpleNamespace

from app.services.engine.impl_internal import InternalCofCalculator, StandardRiskMatrix


def test_risk_matrix_basic():
    matrix = StandardRiskMatrix()
    score, level = matrix.evaluate(
        SimpleNamespace(category=1), SimpleNamespace(category="A")
    )
    assert score == 1 and level == "Low"

    score, level = matrix.evaluate(
        SimpleNamespace(category=5), SimpleNamespace(category="E")
    )
    assert score == 25 and level == "Critical"


def test_cof_returns_valid_category():
    calc = InternalCofCalculator()
    eq = SimpleNamespace(
        hazardous=True, fluid_type="liquid",
        inventory_m3=20.0, design_pressure_kpa=1500.0,
    )
    result = calc.calculate(eq, None)
    assert result.category in {"A", "B", "C", "D", "E"}
