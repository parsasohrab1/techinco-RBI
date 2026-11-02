import json

from app.models import AnalysisRun, CMLAnalysisResult, Equipment
from app.services.audit_report import AuditReconstructionReport


def test_audit_reconstruction_reports_snapshot_and_limitations():
    equipment = Equipment(tag_number="V-AUDIT")
    run = AnalysisRun(
        id=17,
        equipment=equipment,
        engine_version="internal-0.2.0",
        standard_ref="internal screening",
        overall_risk_level="Low",
    )
    result = CMLAnalysisResult(
        run_id=17,
        cml_id=23,
        pof_value=0.01,
        pof_category=2,
        cof_value=1.5,
        cof_category="B",
        risk_score=2,
        risk_level="Low",
        recommended_interval_years=5,
        remaining_life_years=10,
        details_json=json.dumps({
            "inputs": {"component": {"t_min_mm": 8}},
            "assumptions": [],
            "data_quality": {"component.2.t_min_mm": "verified"},
            "pof": {"reference": "illustrative", "details": {"rate": 0.1}},
            "cof": {"reference": "illustrative", "details": {"safety": 2}},
            "engine": {
                "name": "internal",
                "version": "0.2.0",
                "compliance_status": "internal_screening",
            },
        }),
    )

    report = AuditReconstructionReport(run, [result]).build()

    assert report["run_id"] == 17
    assert report["compliance_claim"].startswith("No API RP")
    assert report["chain_of_custody"][0]["inputs"]["component"]["t_min_mm"] == 8
    assert report["calculation_trace"][0]["pof"]["details"]["rate"] == 0.1
    assert report["limitations"]
