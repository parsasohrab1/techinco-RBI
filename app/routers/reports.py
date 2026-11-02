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
PLANT_UNIT_ORDER = (
    "Gas separation plant",
    "Ethylene production plant",
    "Polyethylene production plant",
    "Polypropylene production plant",
    "Energy supply plant",
)


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

    cml_count = (
        portfolio_query.with_entities(func.count(models.CMLAnalysisResult.id)).scalar()
        or 0
    )
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
    component_count = db.query(func.count(models.Component.id)).scalar() or 0
    total_equipment_count = (
        db.query(func.count(models.Equipment.id)).scalar() or 0
    )
    inspection_count = (
        db.query(func.count(models.InspectionRecord.id)).scalar() or 0
    )
    plant_units = {
        row[0]: {
            "plant_unit": row[0],
            "equipment_count": row[1],
            "component_count": row[2],
            "assessed_count": 0,
        }
        for row in (
            db.query(
                models.Equipment.plant_unit,
                func.count(func.distinct(models.Equipment.id)),
                func.count(func.distinct(models.Component.id)),
            )
            .outerjoin(models.Component, models.Component.equipment_id == models.Equipment.id)
            .group_by(models.Equipment.plant_unit)
            .order_by(models.Equipment.plant_unit)
            .all()
        )
    }
    for plant_unit, assessed_count in (
        portfolio_query.with_entities(
            models.Equipment.plant_unit,
            func.count(models.CMLAnalysisResult.id),
        )
        .group_by(models.Equipment.plant_unit)
        .all()
    ):
        plant_units[plant_unit]["assessed_count"] = assessed_count
    plant_units = dict(sorted(
        plant_units.items(),
        key=lambda item: (
            PLANT_UNIT_ORDER.index(item[0])
            if item[0] in PLANT_UNIT_ORDER
            else len(PLANT_UNIT_ORDER)
        ),
    ))

    equipment_type_distribution = [
        {
            "equipment_type": equipment_type,
            "count": count,
            "percent": (
                count * 100 / total_equipment_count
                if total_equipment_count
                else 0
            ),
        }
        for equipment_type, count in (
            db.query(
                models.Equipment.equipment_type,
                func.count(models.Equipment.id),
            )
            .group_by(models.Equipment.equipment_type)
            .order_by(func.count(models.Equipment.id).desc())
            .all()
        )
    ]
    mechanism_distribution = [
        {
            "name": name,
            "count": count,
            "percent": min(count * 100 / component_count, 100) if component_count else 0,
        }
        for name, count in (
            db.query(
                models.DamageMechanism.name,
                func.count(models.ComponentDamageMechanism.id),
            )
            .join(
                models.ComponentDamageMechanism,
                models.ComponentDamageMechanism.dm_id == models.DamageMechanism.id,
            )
            .filter(models.ComponentDamageMechanism.status == "active")
            .group_by(models.DamageMechanism.name)
            .order_by(func.count(models.ComponentDamageMechanism.id).desc())
            .all()
        )
    ]
    interval_group = case(
        (models.CMLAnalysisResult.recommended_interval_years <= 1, "≤ 1 year"),
        (models.CMLAnalysisResult.recommended_interval_years <= 2, "1–2 years"),
        (models.CMLAnalysisResult.recommended_interval_years <= 5, "2–5 years"),
        (models.CMLAnalysisResult.recommended_interval_years <= 10, "5–10 years"),
        else_="> 10 years",
    )
    interval_counts = dict(
        portfolio_query.with_entities(
            interval_group,
            func.count(models.CMLAnalysisResult.id),
        )
        .group_by(interval_group)
        .all()
    )
    interval_distribution = [
        {
            "label": label,
            "count": interval_counts.get(label, 0),
            "percent": (
                interval_counts.get(label, 0) * 100 / cml_count
                if cml_count
                else 0
            ),
        }
        for label in ("≤ 1 year", "1–2 years", "2–5 years", "5–10 years", "> 10 years")
    ]
    matrix_counts = {
        (pof_category, cof_category): count
        for pof_category, cof_category, count in (
            portfolio_query.with_entities(
                models.CMLAnalysisResult.pof_category,
                models.CMLAnalysisResult.cof_category,
                func.count(models.CMLAnalysisResult.id),
            )
            .group_by(
                models.CMLAnalysisResult.pof_category,
                models.CMLAnalysisResult.cof_category,
            )
            .all()
        )
    }
    risk_matrix = []
    for pof_category in range(1, 6):
        matrix_row = []
        for cof_category in "ABCDE":
            score = pof_category * (ord(cof_category) - ord("A") + 1)
            risk_level = (
                "Low" if score <= 3 else
                "Medium" if score <= 8 else
                "High" if score <= 14 else "Critical"
            )
            matrix_row.append({
                "pof": pof_category,
                "cof": cof_category,
                "count": matrix_counts.get((pof_category, cof_category), 0),
                "level": risk_level,
            })
        risk_matrix.append(matrix_row)

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
            "total_equipment_count": total_equipment_count,
            "component_count": component_count,
            "inspection_count": inspection_count,
            "cml_count": cml_count,
            "plant_units": list(plant_units.values()),
            "equipment_type_distribution": equipment_type_distribution,
            "mechanism_distribution": mechanism_distribution,
            "interval_distribution": interval_distribution,
            "risk_matrix": risk_matrix,
            "page_result_count": len(rows),
            "high_priority_count": (
                risk_counts.get("Critical", 0) + risk_counts.get("High", 0)
            ),
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
