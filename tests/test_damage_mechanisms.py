from types import SimpleNamespace

import pytest

from app.services.engine.damage_mechanisms import (
    CUIDamageMechanismEvaluator,
    SCCChecklistEvaluator,
)


def _equipment(material="Carbon Steel"):
    return SimpleNamespace(material=material)


def _component(insulated=True, temperature=80.0):
    return SimpleNamespace(
        insulated=insulated,
        operating_temperature_c=temperature,
    )


def test_cui_screen_marks_insulated_carbon_steel_in_range_susceptible():
    result = CUIDamageMechanismEvaluator().assess(_equipment(), _component())

    assert result.status == "susceptible"
    assert result.details["screening_range_c"] == {"minimum": -12.0, "maximum": 175.0}


def test_cui_screen_is_indeterminate_without_operating_temperature():
    result = CUIDamageMechanismEvaluator().assess(
        _equipment(), _component(temperature=None)
    )

    assert result.status == "indeterminate"
    assert result.details["reason"] == "operating_temperature_missing"


def test_cui_screen_does_not_apply_to_uninsulated_component():
    result = CUIDamageMechanismEvaluator().assess(
        _equipment(), _component(insulated=False)
    )

    assert result.status == "not_susceptible"
    assert result.details["reason"] == "component_not_insulated"


def test_cui_screen_is_indeterminate_for_unsupported_material():
    result = CUIDamageMechanismEvaluator().assess(
        _equipment("Stainless Steel"), _component()
    )

    assert result.status == "indeterminate"
    assert result.details["reason"] == "material_outside_supported_screen"


@pytest.mark.parametrize(
    ("temperature", "expected_status"),
    [
        (-12.0, "susceptible"),
        (175.0, "susceptible"),
        (-12.1, "not_susceptible"),
        (175.1, "not_susceptible"),
    ],
)
def test_cui_screen_temperature_boundaries(temperature, expected_status):
    result = CUIDamageMechanismEvaluator().assess(
        _equipment(), _component(temperature=temperature)
    )

    assert result.status == expected_status


def test_scc_checklist_is_indeterminate_when_inputs_are_incomplete():
    result = SCCChecklistEvaluator().assess(
        _equipment(), _component(), {"susceptible_material": True}
    )

    assert result.status == "indeterminate"
    assert result.details["missing_inputs"] == [
        "environment_present",
        "tensile_stress_present",
    ]


def test_scc_checklist_marks_all_reported_conditions_present():
    result = SCCChecklistEvaluator().assess(
        _equipment(),
        _component(),
        {
            "susceptible_material": True,
            "environment_present": True,
            "tensile_stress_present": True,
        },
    )

    assert result.status == "susceptible"
    assert result.details["assessment_type"] == "generic_user_input_checklist_only"
    assert "not API-conforming" in result.details["limitations"]


def test_scc_checklist_marks_absent_condition_not_susceptible():
    result = SCCChecklistEvaluator().assess(
        _equipment(),
        _component(),
        {
            "susceptible_material": True,
            "environment_present": False,
            "tensile_stress_present": True,
        },
    )

    assert result.status == "not_susceptible"
