from datetime import date
from types import SimpleNamespace

import pytest

from app.services.engine.contract import (
    EngineConfig,
    EngineInputSnapshot,
    EngineOutput,
    EngineRegistry,
)
from app.services.engine.impl_internal import InternalEngine
from app.services.engine.mechanism_gate import MechanismGate


def test_internal_engine_implements_contract_and_reports_screening_status():
    engine = InternalEngine()
    snapshot = EngineInputSnapshot(
        equipment_id=1,
        component_id=2,
        cml_id=3,
        inputs={
            "equipment": {
                "material": "Carbon Steel",
                "hazardous": True,
                "fluid_type": "liquid",
                "inventory_m3": 20.0,
                "design_pressure_kpa": 1500.0,
            },
            "component": {"t_min_mm": 8.0, "insulated": False},
            "cml": {},
            "inspections": [
                {
                    "inspection_date": date(2020, 5, 1).isoformat(),
                    "thickness_mm": 12.6,
                    "effectiveness": "B",
                },
                {
                    "inspection_date": date(2023, 6, 1).isoformat(),
                    "thickness_mm": 11.9,
                    "effectiveness": "B",
                },
            ],
            "damage_mechanisms": [],
        },
        data_quality={"component.2.t_min_mm": "verified"},
    )

    output = engine.compute(snapshot)

    assert isinstance(output, EngineOutput)
    assert output.engine_name == "internal"
    assert output.compliance_status == "internal_screening"
    assert output.pof_value > 0
    assert output.intermediate_details["pof"]["details"]["inspection_count"] == 2
    assert output.standard_references


def test_engine_output_rejects_invalid_probability():
    with pytest.raises(ValueError, match="POF"):
        EngineOutput(
            pof_value=float("nan"),
            pof_category=1,
            cof_value=1,
            cof_category="A",
            risk_score=1,
            risk_level="Low",
            remaining_life_years=1,
            recommended_interval_years=1,
        )


def test_engine_config_validates_weights_and_strict_compliance():
    with pytest.raises(ValueError, match="positive"):
        EngineConfig("internal", {"safety": 0, "environmental": 0, "economic": 0})

    EngineRegistry.register(InternalEngine())
    with pytest.raises(PermissionError, match="not validated"):
        EngineConfig(
            "internal",
            {"safety": 0.4, "environmental": 0.3, "economic": 0.3},
            strict_compliance=True,
        ).resolve_engine()


def test_mechanism_gate_blocks_unverified_reference_cases():
    admission = MechanismGate.check("CUI")
    assert not admission.validated
    assert "status=internal_screening" in admission.blockers
    with pytest.raises(PermissionError, match="blocked"):
        MechanismGate.assert_admitted("CUI")
