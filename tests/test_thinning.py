from datetime import date
from types import SimpleNamespace

from app.services.engine.impl_internal import InternalPofCalculator


def _make_cml_component():
    comp = SimpleNamespace(t_min_mm=8.0, t_nominal_mm=14.0)
    return comp


def _ins(date_str, thickness, eff="B"):
    return SimpleNamespace(
        inspection_date=date.fromisoformat(date_str),
        thickness_mm=thickness,
        effectiveness=eff,
    )


def test_thinning_pof_calculates_rate_and_life():
    calc = InternalPofCalculator()
    comp = _make_cml_component()
    inspections = [_ins("2020-05-01", 12.6), _ins("2023-06-01", 11.9)]
    result = calc.calculate(comp, None, inspections, [])
    assert 0.20 < result.details["corrosion_rate_mm_yr"] < 0.25
    assert 15 < result.details["remaining_life_years"] < 20
    assert 1 <= result.category <= 5
    assert result.details["model_scope"] == "illustrative_not_standard_conforming"
    assert result.details["inspection_count"] == 2
    assert result.details["observed_thickness_range_mm"] == {
        "minimum": 11.9,
        "maximum": 12.6,
    }


def test_thinning_pof_no_inspections_is_worst_case():
    calc = InternalPofCalculator()
    result = calc.calculate(_make_cml_component(), None, [], [])
    assert result.category == 5
