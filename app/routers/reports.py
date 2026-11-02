import csv
import io
from collections import Counter
from math import ceil
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db

router = APIRouter(prefix="/reports", tags=["reports"])
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")
RISK_LEVELS = ("Critical", "High", "Medium", "Low")


@router.get("/dashboard", response_class=HTMLResponse)
def risk_dashboard(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 100,
):
    latest_run_ids = (
        db.query(func.max(models.AnalysisRun.id).label("run_id"))
        .group_by(models.AnalysisRun.equipment_id)
        .subquery()
    )
    portfolio_query = (
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
    )

    cml_count, short_interval_count, average_interval = (
        portfolio_query.with_entities(
            func.count(models.CMLAnalysisResult.id),
            func.sum(
                case(
                    (models.CMLAnalysisResult.recommended_interval_years <= 2, 1),
                    else_=0,
                )
            ),
            func.avg(models.CMLAnalysisResult.recommended_interval_years),
        ).one()
    )
    cml_count = cml_count or 0
    short_interval_count = short_interval_count or 0
    average_interval = average_interval or 0
    risk_counts = Counter(
        dict(
            portfolio_query.with_entities(
                models.CMLAnalysisResult.risk_level,
                func.count(models.CMLAnalysisResult.id),
            )
            .group_by(models.CMLAnalysisResult.risk_level)
            .all()
        )
    )

    priority_order = case(
        (models.CMLAnalysisResult.risk_level == "Critical", 0),
        (models.CMLAnalysisResult.risk_level == "High", 1),
        (models.CMLAnalysisResult.risk_level == "Medium", 2),
        (models.CMLAnalysisResult.risk_level == "Low", 3),
        else_=4,
    )
    priority_rows = (
        portfolio_query.order_by(
            priority_order,
            models.CMLAnalysisResult.recommended_interval_years,
            models.Equipment.tag_number,
        )
        .limit(8)
        .all()
    )
    page_count = max(ceil(cml_count / page_size), 1)
    page = min(page, page_count)
    rows = (
        portfolio_query.order_by(
            models.Equipment.tag_number,
            models.Component.name,
            models.CML.name,
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    equipment_count = (
        portfolio_query.with_entities(
            func.count(func.distinct(models.AnalysisRun.id))
        ).scalar()
        or 0
    )

    risk_distribution = [
        {
            "level": level,
            "count": risk_counts.get(level, 0),
            "percent": (
                risk_counts.get(level, 0) * 100 / cml_count
                if cml_count
                else 0
            ),
        }
        for level in RISK_LEVELS
    ]

    return templates.TemplateResponse(
        request=request,
        name="risk_dashboard.html",
        context={
            "rows": rows,
            "priority_rows": priority_rows,
            "risk_levels": RISK_LEVELS,
            "risk_counts": risk_counts,
            "risk_distribution": risk_distribution,
            "equipment_count": equipment_count,
            "cml_count": cml_count,
            "page_result_count": len(rows),
            "high_priority_count": (
                risk_counts.get("Critical", 0) + risk_counts.get("High", 0)
            ),
            "short_interval_count": short_interval_count,
            "average_interval": average_interval,
            "latest_run_count": equipment_count,
            "page": page,
            "page_size": page_size,
            "page_count": page_count,
            "previous_page": page - 1 if page > 1 else None,
            "next_page": page + 1 if page < page_count else None,
        },
    )


@router.get("/run/{run_id}/worklist.csv")
def worklist_csv(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
):
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
