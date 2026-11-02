import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services.analysis_orchestrator import analyze_equipment

router = APIRouter(tags=["analysis"])


@router.post("/equipment/{equipment_id}/analyze", response_model=schemas.EquipmentAnalysisOut)
def analyze(equipment_id: int, db: Session = Depends(get_db)):
    eq = db.get(models.Equipment, equipment_id)
    if not eq:
        raise HTTPException(404, "Equipment not found")
    if not any(c.cmls for c in eq.components):
        raise HTTPException(400, "Equipment has no CMLs to analyze")
    run = analyze_equipment(db, eq)

    results = []
    for r in run.results:
        cml = db.get(models.CML, r.cml_id)
        comp = cml.component
        results.append(schemas.CMLAnalysisOut(
            cml_id=r.cml_id, cml_name=cml.name, component=comp.name,
            pof_value=r.pof_value, pof_category=r.pof_category,
            cof_value=r.cof_value, cof_category=r.cof_category,
            risk_score=r.risk_score, risk_level=r.risk_level,
            remaining_life_years=r.remaining_life_years,
            recommended_interval_years=r.recommended_interval_years,
            details=json.loads(r.details_json),
        ))

    return schemas.EquipmentAnalysisOut(
        run_id=run.id, equipment_id=run.equipment_id, tag_number=eq.tag_number,
        engine_version=run.engine_version, standard_ref=run.standard_ref,
        overall_risk_level=run.overall_risk_level, results=results,
    )


@router.get("/analysis-runs")
def list_runs(equipment_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(models.AnalysisRun)
    if equipment_id:
        q = q.filter(models.AnalysisRun.equipment_id == equipment_id)
    return [
        {
            "id": r.id, "equipment_id": r.equipment_id, "timestamp": r.run_timestamp,
            "engine_version": r.engine_version, "overall_risk_level": r.overall_risk_level,
        }
        for r in q.order_by(models.AnalysisRun.run_timestamp.desc()).all()
    ]
