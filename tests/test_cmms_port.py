import pytest

from app.integrations.cmms_port import (
    CmmsIntegrationService,
    InspectionWorkPackage,
    MaximoAdapter,
    SapPmAdapter,
)


@pytest.mark.parametrize(
    "adapter",
    [SapPmAdapter("https://example.invalid", "secret"), MaximoAdapter("https://example.invalid", "secret")],
)
def test_unvalidated_enterprise_adapters_cannot_push(adapter):
    package = InspectionWorkPackage(
        equipment_tag="V-1",
        cml_id=1,
        method="UT",
        target_date="2027-01-01",
        priority="High",
        damage_mechanisms=["thinning"],
        risk_level="High",
        standard_refs=[],
    )
    with pytest.raises(PermissionError, match="not validated"):
        CmmsIntegrationService(adapter).push_plan([package])
    assert adapter.health()["validated"] is False
