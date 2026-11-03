import pytest

from app.services.engine.mechanism_gate import check_api581_coverage
from app.standards.baseline import Baseline, ComplianceStatus


def test_baseline_does_not_claim_unverified_compliance():
    assert Baseline.compliance_label() == ("INTERNAL SCREENING ONLY — no API conformity claim")
    assert all(
        status == ComplianceStatus.INTERNAL_SCREENING
        for status in Baseline.mechanism_scope.approved.values()
    )
    with pytest.raises(PermissionError):
        Baseline.require_compliance_ready("thinning")


def test_baseline_returns_only_tracked_standard_mappings():
    assert Baseline.api580_requirements()
    assert Baseline.api581_requirements()
    assert all(
        entry.standard == Baseline.api580.code
        for entry in Baseline.api580_requirements()
    )
    assert all(
        entry.standard == Baseline.api581.code
        for entry in Baseline.api581_requirements()
    )


def test_api581_coverage_uses_exact_mechanism_tags():
    assert check_api581_coverage("THINNING")
    assert check_api581_coverage("cui")
    assert not check_api581_coverage("scc")
    assert not check_api581_coverage("unknown_damage")


@pytest.mark.parametrize(
    "equipment_type",
    [
        "vessel",
        "pressure_vessel",
        "column",
        "piping",
        "pipeline",
        "heat exchanger",
        "atmospheric tank",
        "storage tank",
        "pump",
        "turbine",
        "compressor",
        "boiler",
        "fired heater",
        "reactor",
        "valve",
        "pressure-relief-device",
    ],
)
def test_baseline_accepts_supported_equipment_aliases(equipment_type):
    Baseline.equipment_scope.validate(equipment_type)


@pytest.mark.parametrize(
    ("equipment_type", "canonical_type"),
    [
        ("tank", "storage_tank"),
        ("piping-system", "piping"),
        ("distillation column", "column"),
        ("furnace", "fired_heater"),
        ("relief-valve", "pressure_relief_device"),
    ],
)
def test_baseline_accepts_common_equipment_aliases(equipment_type, canonical_type):
    normalized = equipment_type.strip().casefold().replace("-", "_").replace(" ", "_")
    assert dict(Baseline.equipment_scope.aliases)[normalized] == canonical_type
    Baseline.equipment_scope.validate(equipment_type)
