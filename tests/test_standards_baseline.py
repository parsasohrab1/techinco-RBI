import pytest

from app.standards.baseline import Baseline, ComplianceStatus


def test_baseline_does_not_claim_unverified_compliance():
    assert Baseline.compliance_label() == ("INTERNAL SCREENING ONLY — no API conformity claim")
    assert all(
        status == ComplianceStatus.INTERNAL_SCREENING
        for status in Baseline.mechanism_scope.approved.values()
    )
    with pytest.raises(PermissionError):
        Baseline.require_compliance_ready("thinning")


@pytest.mark.parametrize(
    "equipment_type",
    ["vessel", "pressure_vessel", "heat exchanger", "pressure-relief-device"],
)
def test_baseline_accepts_supported_equipment_aliases(equipment_type):
    Baseline.equipment_scope.validate(equipment_type)
