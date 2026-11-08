"""Recompute a stored analysis from its persisted input snapshot."""

from __future__ import annotations

import json
from math import isclose
from typing import Any

from sqlalchemy.orm import Session

from ..models import AnalysisRun
from .analysis_orchestrator import get_engine
from .engine.contract import EngineInputSnapshot

_ABSOLUTE = 1e-9
_FIELDS = (
    ("pof_value", "pof_value"),
    ("pof_category", "pof_category"),
    ("cof_value", "cof_value"),
    ("cof_category", "cof_category"),
    ("risk_score", "risk_score"),
    ("risk_level", "risk_level"),
    ("remaining_life_years", "remaining_life_years"),
    ("recommended_interval_years", "recommended_interval_years"),
)


def _same(stored: Any, recomputed: Any) -> bool:
    if isinstance(stored, (int, float)) and isinstance(recomputed, (int, float)):
        return isclose(float(stored), float(recomputed), rel_tol=0.0, abs_tol=_ABSOLUTE)
    return stored == recomputed


def replay_analysis(db: Session, run: AnalysisRun) -> dict[str, Any]:
    engine = get_engine()
    comparisons = []
    for result in run.results:
        details = json.loads(result.details_json or "{}")
        inputs = details.get("inputs")
        if not isinstance(inputs, dict) or "component" not in inputs:
            comparisons.append({
                "cml_id": result.cml_id,
                "matched": False,
                "reason": "stored inputs are incomplete",
                "differences": ["inputs"],
            })
            continue
        snapshot = EngineInputSnapshot(
            equipment_id=run.equipment_id,
            component_id=int(inputs["component"].get("id") or 0),
            cml_id=result.cml_id,
            inputs=inputs,
            assumptions=details.get("assumptions") or [],
            data_quality=details.get("data_quality") or {},
        )
        try:
            output = engine.compute(snapshot)
        except (TypeError, ValueError, KeyError, NotImplementedError) as error:
            comparisons.append({
                "cml_id": result.cml_id,
                "matched": False,
                "reason": str(error),
                "differences": ["compute"],
            })
            continue
        differences = [
            name
            for name, attribute in _FIELDS
            if not _same(getattr(result, attribute), getattr(output, name))
        ]
        comparisons.append({
            "cml_id": result.cml_id,
            "matched": not differences,
            "reason": "recomputed from the stored input snapshot",
            "differences": differences,
            "recomputed": {
                "pof_value": output.pof_value,
                "pof_category": output.pof_category,
                "cof_value": output.cof_value,
                "cof_category": output.cof_category,
                "risk_score": output.risk_score,
                "risk_level": output.risk_level,
                "remaining_life_years": output.remaining_life_years,
                "recommended_interval_years": output.recommended_interval_years,
                "compliance_status": output.compliance_status,
            },
        })

    return {
        "run_id": run.id,
        "engine": {
            "name": engine.name,
            "version": engine.version,
            "compliance_status": engine.compliance_status,
        },
        "matched": bool(comparisons) and all(item["matched"] for item in comparisons),
        "result_count": len(comparisons),
        "results": comparisons,
        "compliance_claim": (
            "No API RP 580/581 conformity claim. Replay checks whether the "
            "current internal engine reproduces the stored screening result."
        ),
    }
