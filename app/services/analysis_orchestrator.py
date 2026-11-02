import json

from sqlalchemy.orm import Session

from .. import models
from . import audit
from .engine.base import ICalculationEngine
from .engine.impl_internal import InternalEngine

RANK = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}


def get_engine() -> ICalculationEngine:
    return InternalEngine()


def recommended_interval(remaining_life: float, risk_level: str) -> float:
    base = 10.0 if remaining_life >= 999 else remaining_life / 2.0
    cap = {"Critical": 2.0, "High": 4.0, "Medium": 6.0, "Low": 10.0}[risk_level]
    return round(max(min(base, cap), 1.0), 1)


def analyze_equipment(db: Session, equipment: models.Equipment) -> models.AnalysisRun:
    engine = get_engine()
    run = models.AnalysisRun(
        equipment_id=equipment.id,
        engine_version=f"{engine.metadata.name}-{engine.metadata.version}",
        standard_ref=engine.metadata.standard_ref,
        overall_risk_level="Low",
    )
    db.add(run)
    db.flush()

    worst_rank, worst_level = 0, "Low"
    for comp in equipment.components:
        for cml in comp.cmls:
            inspections = sorted(cml.inspections, key=lambda i: i.inspection_date)
            active_dms = [dm for dm in comp.damage_mechanisms if dm.status == "active"]

            pof = engine.pof_calculator.calculate(comp, cml, inspections, active_dms)
            cof = engine.cof_calculator.calculate(equipment, comp)
            score, level = engine.risk_matrix.evaluate(pof, cof)
            remaining = pof.details.get("remaining_life_years", 999.0)
            interval = recommended_interval(remaining, level)

            db.add(models.CMLAnalysisResult(
                run_id=run.id, cml_id=cml.id,
                pof_value=pof.value, pof_category=pof.category,
                cof_value=cof.value, cof_category=cof.category,
                risk_score=score, risk_level=level,
                recommended_interval_years=interval, remaining_life_years=remaining,
                details_json=json.dumps({
                    "pof": {"reference": pof.reference, "details": pof.details},
                    "cof": {"reference": cof.reference, "details": cof.details},
                }),
            ))
            if RANK[level] > worst_rank:
                worst_rank, worst_level = RANK[level], level

    run.overall_risk_level = worst_level
    audit.log(db, run, "create")
    db.commit()
    db.refresh(run)
    return run
