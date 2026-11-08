import csv
import io
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from itertools import pairwise
from math import ceil, log10
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..services.incident_reference import (
    IncidentReferenceError,
    load_incident_reference,
    present_incident_reference,
)

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


@router.get("/incident-reference")
def incident_reference():
    try:
        return load_incident_reference()
    except IncidentReferenceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/dashboard", response_class=HTMLResponse)
def risk_dashboard(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 100,
    equipment_id: Annotated[int | None, Query(gt=0)] = None,
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
    active_dm_component_ids = (
        db.query(
            models.ComponentDamageMechanism.component_id.label("component_id")
        )
        .filter(models.ComponentDamageMechanism.status == "active")
        .distinct()
        .subquery()
    )
    assessed_component_ids = (
        portfolio_query.with_entities(
            models.Component.id.label("component_id")
        )
        .distinct()
        .subquery()
    )
    components_with_active_dm = (
        db.query(func.count())
        .select_from(active_dm_component_ids)
        .scalar()
        or 0
    )
    components_with_latest_assessment = (
        db.query(func.count())
        .select_from(assessed_component_ids)
        .scalar()
        or 0
    )
    components_with_dm_and_assessment = (
        db.query(func.count())
        .select_from(active_dm_component_ids)
        .join(
            assessed_component_ids,
            active_dm_component_ids.c.component_id
            == assessed_component_ids.c.component_id,
        )
        .scalar()
        or 0
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
            func.count(func.distinct(models.Component.id)),
        )
        .group_by(models.Equipment.plant_unit)
        .all()
    ):
        plant_units[plant_unit]["assessed_count"] = assessed_count
    for plant_unit, inventory_total, inventory_mean in (
        db.query(
            models.Equipment.plant_unit,
            func.sum(models.Equipment.inventory_m3),
            func.avg(models.Equipment.inventory_m3),
        )
        .group_by(models.Equipment.plant_unit)
        .all()
    ):
        plant_units[plant_unit]["inventory_total"] = inventory_total
        plant_units[plant_unit]["inventory_mean"] = inventory_mean
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
    material_distribution = [
        {"label": label, "count": count}
        for label, count in (
            db.query(models.Equipment.material, func.count(models.Equipment.id))
            .group_by(models.Equipment.material)
            .order_by(func.count(models.Equipment.id).desc())
            .all()
        )
    ]
    fluid_distribution = [
        {"label": label.title(), "count": count}
        for label, count in (
            db.query(models.Equipment.fluid_type, func.count(models.Equipment.id))
            .group_by(models.Equipment.fluid_type)
            .order_by(func.count(models.Equipment.id).desc())
            .all()
        )
    ]
    equipment_ranges = db.query(
        func.min(models.Equipment.design_pressure_kpa),
        func.max(models.Equipment.design_pressure_kpa),
        func.avg(models.Equipment.design_pressure_kpa),
        func.min(models.Equipment.design_temperature_c),
        func.max(models.Equipment.design_temperature_c),
        func.avg(models.Equipment.design_temperature_c),
        func.min(models.Equipment.inventory_m3),
        func.max(models.Equipment.inventory_m3),
        func.avg(models.Equipment.inventory_m3),
    ).one()
    component_ranges = db.query(
        func.min(models.Component.t_min_mm),
        func.max(models.Component.t_min_mm),
        func.min(models.Component.t_nominal_mm),
        func.max(models.Component.t_nominal_mm),
        func.min(models.Component.operating_temperature_c),
        func.max(models.Component.operating_temperature_c),
    ).one()
    inspection_ranges = db.query(
        func.min(models.InspectionRecord.thickness_mm),
        func.max(models.InspectionRecord.thickness_mm),
        func.avg(models.InspectionRecord.thickness_mm),
        func.min(models.InspectionRecord.inspection_date),
        func.max(models.InspectionRecord.inspection_date),
    ).one()
    inspection_method_distribution = [
        {"label": label, "count": count}
        for label, count in (
            db.query(
                models.InspectionRecord.method,
                func.count(models.InspectionRecord.id),
            )
            .group_by(models.InspectionRecord.method)
            .order_by(func.count(models.InspectionRecord.id).desc())
            .all()
        )
    ]
    effectiveness_distribution = [
        {"label": label, "count": count}
        for label, count in (
            db.query(
                models.InspectionRecord.effectiveness,
                func.count(models.InspectionRecord.id),
            )
            .group_by(models.InspectionRecord.effectiveness)
            .order_by(models.InspectionRecord.effectiveness)
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
    cof_distribution = [
        {"category": category, "count": matrix_cof_count}
        for category, matrix_cof_count in (
            portfolio_query.with_entities(
                models.CMLAnalysisResult.cof_category,
                func.count(models.CMLAnalysisResult.id),
            )
            .group_by(models.CMLAnalysisResult.cof_category)
            .order_by(models.CMLAnalysisResult.cof_category)
            .all()
        )
    ]
    risk_plot_rows = (
        portfolio_query.with_entities(
            models.CMLAnalysisResult.pof_value,
            models.CMLAnalysisResult.cof_value,
            models.CMLAnalysisResult.risk_level,
        )
        .order_by(models.CMLAnalysisResult.id)
        .all()
    )
    risk_plot_stride = max(ceil(len(risk_plot_rows) / 650), 1)
    risk_plot_points = [
        {
            "pof": row.pof_value,
            "cof": row.cof_value,
            "level": row.risk_level.lower(),
            "x": round(
                84 + (log10(max(row.pof_value, 0.000001)) + 6) * 130,
                1,
            ),
            "y": round(230 - (row.cof_value - 1) * 45, 1),
        }
        for row in risk_plot_rows[::risk_plot_stride]
    ]

    priority_order = case(
        (models.CMLAnalysisResult.risk_level == "Critical", 0),
        (models.CMLAnalysisResult.risk_level == "High", 1),
        (models.CMLAnalysisResult.risk_level == "Medium", 2),
        (models.CMLAnalysisResult.risk_level == "Low", 3),
        else_=4,
    )
    equipment_choices = (
        db.query(models.Equipment)
        .order_by(models.Equipment.plant_unit, models.Equipment.tag_number)
        .all()
    )
    selected_equipment = next(
        (item for item in equipment_choices if item.id == equipment_id),
        equipment_choices[0] if equipment_choices else None,
    )
    focused = None
    focus_inspections = []
    focus_analysis = {}
    thickness_chart = {"points": "", "minimum_y": 0, "nominal_y": 0, "ticks": []}
    rate_chart = {"bars": [], "minimum": 0, "maximum": 0}
    focus_rates = []
    if selected_equipment:
        focused = (
            portfolio_query.filter(models.Equipment.id == selected_equipment.id)
            .order_by(
                priority_order,
                models.CMLAnalysisResult.recommended_interval_years,
                models.Component.name,
            )
            .first()
        )
    if focused:
        _, _, focus_result, focus_cml, focus_component = focused
        focus_inspections = (
            db.query(models.InspectionRecord)
            .filter(models.InspectionRecord.cml_id == focus_cml.id)
            .order_by(models.InspectionRecord.inspection_date, models.InspectionRecord.id)
            .all()
        )
        focus_analysis = json.loads(focus_result.details_json or "{}")
        observed = [record.thickness_mm for record in focus_inspections]
        chart_low = min(min(observed), focus_component.t_min_mm) - 0.5
        chart_high = max(max(observed), focus_component.t_nominal_mm) + 0.5
        chart_span = max(chart_high - chart_low, 0.1)
        chart_left, chart_width = 70, 850
        chart_top, chart_height = 24, 205
        thickness_points = []
        thickness_markers = []
        for index, record in enumerate(focus_inspections):
            x = chart_left + index * chart_width / max(len(focus_inspections) - 1, 1)
            y = chart_top + (chart_high - record.thickness_mm) * chart_height / chart_span
            thickness_points.append(f"{x:.1f},{y:.1f}")
            if index in {0, len(focus_inspections) // 2, len(focus_inspections) - 1}:
                thickness_markers.append({
                    "x": round(x, 1),
                    "y": round(y, 1),
                    "date": record.inspection_date,
                    "thickness": record.thickness_mm,
                })
        thickness_chart = {
            "points": " ".join(thickness_points),
            "markers": thickness_markers,
            "minimum_y": round(
                chart_top + (chart_high - focus_component.t_min_mm) * chart_height / chart_span,
                1,
            ),
            "nominal_y": round(
                chart_top + (chart_high - focus_component.t_nominal_mm) * chart_height / chart_span,
                1,
            ),
            "ticks": [
                {
                    "y": round(chart_top + index * chart_height / 4, 1),
                    "value": round(chart_high - index * chart_span / 4, 1),
                }
                for index in range(5)
            ],
        }
        for earlier, later in pairwise(focus_inspections):
            elapsed_years = (
                later.inspection_date - earlier.inspection_date
            ).days / 365.25
            if elapsed_years <= 0:
                continue
            focus_rates.append({
                "date": later.inspection_date,
                "rate": round(
                    (earlier.thickness_mm - later.thickness_mm) / elapsed_years,
                    4,
                ),
                "effectiveness": later.effectiveness,
            })
        if focus_rates:
            rate_min = min(min(item["rate"] for item in focus_rates), 0)
            rate_max = max(max(item["rate"] for item in focus_rates), 0)
            rate_span = max(rate_max - rate_min, 0.001)
            zero_y = 24 + rate_max * 155 / rate_span
            rate_chart = {
                "minimum": rate_min,
                "maximum": rate_max,
                "zero_y": round(zero_y, 1),
                "bars": [
                    {
                        "x": round(70 + index * 850 / len(focus_rates), 1),
                        "y": round(min(
                            zero_y,
                            24 + (rate_max - item["rate"]) * 155 / rate_span,
                        ), 1),
                        "height": round(
                            max(2, abs(item["rate"]) * 155 / rate_span),
                            1,
                        ),
                        "rate": item["rate"],
                        "date": item["date"],
                    }
                    for index, item in enumerate(focus_rates)
                ],
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

    priority_rows = (
        portfolio_query.order_by(
            priority_order,
            models.CMLAnalysisResult.recommended_interval_years,
            models.Equipment.tag_number,
        )
        .limit(50)
        .all()
    )
    plan_rows = [
        {
            "run": run,
            "equipment": equipment,
            "result": result,
            "cml": cml,
            "component": component,
            "screening_target_date": datetime.now(timezone.utc).date()
            + timedelta(days=round(result.recommended_interval_years * 365.25)),
        }
        for run, equipment, result, cml, component in priority_rows
    ]
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

    latest_corrosion_summary_ids = (
        db.query(
            models.CorrosionCalcSummary.circuit_id.label("circuit_id"),
            func.max(models.CorrosionCalcSummary.id).label("summary_id")
        )
        .group_by(models.CorrosionCalcSummary.circuit_id)
        .subquery()
    )
    corrosion_records = (
        db.query(
            models.CorrosionCircuit,
            models.Equipment,
            models.CorrosionCalcSummary,
        )
        .join(
            models.Equipment,
            models.Equipment.id == models.CorrosionCircuit.equipment_id,
        )
        .outerjoin(
            latest_corrosion_summary_ids,
            latest_corrosion_summary_ids.c.circuit_id
            == models.CorrosionCircuit.id,
        )
        .outerjoin(
            models.CorrosionCalcSummary,
            models.CorrosionCalcSummary.id
            == latest_corrosion_summary_ids.c.summary_id,
        )
        .order_by(models.Equipment.tag_number, models.CorrosionCircuit.circuit_code)
        .limit(100)
        .all()
    )
    corrosion_circuit_rows = []
    for circuit, equipment, summary in corrosion_records:
        results = json.loads(summary.results_json) if summary else None
        circuit_results = results["circuit"] if results else {}
        corrosion_circuit_rows.append({
            "circuit": circuit,
            "equipment": equipment,
            "summary": summary,
            "results": circuit_results,
        })
    corrosion_circuit_count = (
        db.query(func.count(models.CorrosionCircuit.id)).scalar() or 0
    )
    corrosion_calculation_count = (
        db.query(func.count(models.CorrosionCalcSummary.id)).scalar() or 0
    )
    corrosion_approved_count = (
        db.query(func.count(models.CorrosionCalcSummary.id))
        .filter(models.CorrosionCalcSummary.status == "approved")
        .scalar()
        or 0
    )
    corrosion_quality_issue_count = sum(
        row["results"].get("data_quality_issue_count", 0)
        for row in corrosion_circuit_rows
    )

    return templates.TemplateResponse(
        request=request,
        name="risk_dashboard.html",
        context={
            "rows": rows,
            "priority_rows": priority_rows,
            "risk_levels": RISK_LEVELS,
            "risk_counts": risk_counts,
            "risk_distribution": risk_distribution,
            "corrosion_circuit_rows": corrosion_circuit_rows,
            "corrosion_circuit_count": corrosion_circuit_count,
            "corrosion_calculation_count": corrosion_calculation_count,
            "corrosion_approved_count": corrosion_approved_count,
            "corrosion_quality_issue_count": corrosion_quality_issue_count,
            "equipment_count": equipment_count,
            "total_equipment_count": total_equipment_count,
            "component_count": component_count,
            "components_with_active_dm": components_with_active_dm,
            "components_without_active_dm": (
                component_count - components_with_active_dm
            ),
            "components_with_latest_assessment": (
                components_with_latest_assessment
            ),
            "components_with_dm_and_assessment": (
                components_with_dm_and_assessment
            ),
            "components_with_dm_without_assessment": (
                components_with_active_dm - components_with_dm_and_assessment
            ),
            "inspection_count": inspection_count,
            "cml_count": cml_count,
            "plant_units": list(plant_units.values()),
            "equipment_type_distribution": equipment_type_distribution,
            "material_distribution": material_distribution,
            "fluid_distribution": fluid_distribution,
            "equipment_ranges": equipment_ranges,
            "component_ranges": component_ranges,
            "inspection_ranges": inspection_ranges,
            "inspection_method_distribution": inspection_method_distribution,
            "effectiveness_distribution": effectiveness_distribution,
            "mechanism_distribution": mechanism_distribution,
            "interval_distribution": interval_distribution,
            "risk_matrix": risk_matrix,
            "cof_distribution": cof_distribution,
            "risk_plot_points": risk_plot_points,
            "equipment_choices": equipment_choices,
            "selected_equipment": selected_equipment,
            "focused": focused,
            "focus_inspections": focus_inspections,
            "focus_analysis": focus_analysis,
            "thickness_chart": thickness_chart,
            "rate_chart": rate_chart,
            "focus_rates": focus_rates,
            "plan_rows": plan_rows,
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
            "incident_reference": present_incident_reference(),
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
