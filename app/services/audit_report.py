"""Reconstruction report assembled from persisted analysis inputs and outputs."""

import json
from datetime import datetime, timezone
from typing import Any

from ..models import AnalysisRun, CMLAnalysisResult
from ..standards.knowledge_base import StandardsKnowledgeBase


class AuditReconstructionReport:
    def __init__(
        self,
        run: AnalysisRun,
        results: list[CMLAnalysisResult],
    ):
        self.run = run
        self.results = results

    def build(self) -> dict[str, Any]:
        chains = []
        traces = []
        engines = []
        for result in self.results:
            details = json.loads(result.details_json)
            engine = details.get("engine", {})
            if engine and engine not in engines:
                engines.append(engine)
            chains.append({
                "step": "input_snapshot",
                "cml_id": result.cml_id,
                "inputs": details.get("inputs", {}),
                "assumptions": details.get("assumptions", []),
                "data_quality": details.get("data_quality", {}),
            })
            traces.append({
                "cml_id": result.cml_id,
                "pof": {
                    "value": result.pof_value,
                    "category": result.pof_category,
                    "reference": details.get("pof", {}).get("reference"),
                    "details": details.get("pof", {}).get("details", {}),
                },
                "cof": {
                    "value": result.cof_value,
                    "category": result.cof_category,
                    "reference": details.get("cof", {}).get("reference"),
                    "details": details.get("cof", {}).get("details", {}),
                },
                "risk": {
                    "score": result.risk_score,
                    "level": result.risk_level,
                },
                "remaining_life_years": result.remaining_life_years,
                "recommended_interval_years": result.recommended_interval_years,
                "standard_references": details.get("standard_references", []),
                "damage_mechanisms": details.get("damage_mechanisms", []),
            })

        compliance_status = (
            engines[0].get("compliance_status", "internal_screening")
            if engines
            else "internal_screening"
        )
        limitations = [
            (
                "This reconstruction reflects stored inputs and outputs; it does not "
                "independently recalculate the analysis."
            ),
            (
                "Independent recalculation of the stored input snapshot is a separate "
                "request, GET /audit/runs/{run_id}/replay."
            ),
            "The event and audit records are not cryptographically immutable.",
            "Actor identifiers are caller-supplied until authentication is implemented.",
        ]
        if compliance_status != "validated":
            limitations.append(
                "The calculation engine is not validated against approved "
                "independent reference cases."
            )

        return {
            "report_type": "RBI_AUDIT_RECONSTRUCTION",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run.id,
            "equipment_tag": self.run.equipment.tag_number,
            "engine": engines[0] if engines else {
                "name": self.run.engine_version.rsplit("-", 1)[0],
                "version": self.run.engine_version.rsplit("-", 1)[-1],
                "standard_reference": self.run.standard_ref,
                "compliance_status": compliance_status,
            },
            "baseline": {
                "api580": self._baseline_label("API RP 580"),
                "api581": self._baseline_label("API RP 581"),
            },
            "chain_of_custody": chains,
            "calculation_trace": traces,
            "traceability_appendix": {
                "scope": (
                    "Partial product traceability only; entries do not establish "
                    "standard conformity."
                ),
                "entries": StandardsKnowledgeBase.traceability_matrix(),
            },
            "limitations": limitations,
            "compliance_claim": (
                "No API RP 580/581 conformity claim. Internal screening output "
                "requires qualified engineering review."
            ),
        }

    @staticmethod
    def _baseline_label(code: str) -> str:
        from ..standards.baseline import Baseline

        version = {
            "API RP 580": Baseline.api580,
            "API RP 581": Baseline.api581,
        }[code]
        return version.label()
