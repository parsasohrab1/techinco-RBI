import csv
import io
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db

router = APIRouter(prefix="/reports", tags=["reports"])
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")
RISK_LEVELS = ("Critical", "High", "Medium", "Low")


@router.get("/dashboard", response_class=HTMLResponse)
def risk_dashboard(request: Request, db: Session = Depends(get_db)):
    latest_run_ids = (
        db.query(func.max(models.AnalysisRun.id).label("run_id"))
        .group_by(models.AnalysisRun.equipment_id)
        .subquery()
    )
    rows = (
        db.query(
            models.AnalysisRun,
            models.Equipment,
            models.CMLAnalysisResult,
            models.CML,
            models.Component,
        )
        .join(latest_run_ids, models.AnalysisRun.id == latest_run_ids.c.run_id)
        .join(models.Equipment, models.AnalysisRun.equipment_id == models.Equipment.id)
        .join(models.CMLAnalysisResult, models.CMLAnalysisResult.run_id == models.AnalysisRun.id)
        .join(models.CML, models.CMLAnalysisResult.cml_id == models.CML.id)
        .join(models.Component, models.CML.component_id == models.Component.id)
        .order_by(models.Equipment.tag_number, models.Component.name, models.CML.name)
        .all()
    )

    risk_counts = Counter(result.risk_level for _, _, result, _, _ in rows)
    latest_runs = {}
    for run, equipment, _, _, _ in rows:
        latest_runs[run.id] = (run, equipment)

    return templates.TemplateResponse(
        request=request,
        name="risk_dashboard.html",
        context={
            "rows": rows,
            "risk_levels": RISK_LEVELS,
            "risk_counts": risk_counts,
            "equipment_count": len(latest_runs),
            "cml_count": len(rows),
        },
    )


@router.get("/run/{run_id}/worklist.csv")
def worklist_csv(run_id: int, db: Session = Depends(get_db)):
    run = db.get(models.AnalysisRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "Tag", "CML", "Component", "POF_Cat", "COF_Cat",
        "Risk_Score", "Risk_Level", "Remaining_Life_yr", "Recommended_Interval_yr",
    ])
    for r in run.results:
        cml = db.get(models.CML, r.cml_id)
        comp = cml.component
        w.writerow([
            run.equipment.tag_number, cml.name, comp.name,
            r.pof_category, r.cof_category, r.risk_score, r.risk_level,
            r.remaining_life_years, r.recommended_interval_years,
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="worklist-{run_id}.csv"'},
    )
