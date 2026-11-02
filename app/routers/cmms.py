from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services.cmms import CMMSAdapter, WorkOrderRequest, get_cmms_adapter

router = APIRouter(prefix="/integrations/cmms", tags=["integrations"])
WORK_ORDER_RISK_LEVELS = {"Critical", "High"}


@router.get("/status", response_model=schemas.CMMSStatusOut)
def cmms_status(adapter: CMMSAdapter = Depends(get_cmms_adapter)):
    return adapter.health()


@router.post("/runs/{run_id}/work-orders", response_model=schemas.CMMSRunSyncOut)
def create_run_work_orders(
    run_id: int,
    db: Session = Depends(get_db),
    adapter: CMMSAdapter = Depends(get_cmms_adapter),
):
    run = db.get(models.AnalysisRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    rows = (
        db.query(models.CMLAnalysisResult, models.CML, models.Component)
        .join(models.CML, models.CMLAnalysisResult.cml_id == models.CML.id)
        .join(models.Component, models.CML.component_id == models.Component.id)
        .filter(
            models.CMLAnalysisResult.run_id == run_id,
            models.CMLAnalysisResult.risk_level.in_(WORK_ORDER_RISK_LEVELS),
        )
        .order_by(models.CMLAnalysisResult.id)
        .all()
    )

    receipts = []
    for result, cml, component in rows:
        external_reference = f"rbi-run-{run_id}-cml-{cml.id}"
        receipts.append(adapter.create_work_order(WorkOrderRequest(
            external_reference=external_reference,
            asset_number=run.equipment.tag_number,
            location=f"{component.name} / {cml.name}",
            risk_level=result.risk_level,
            risk_score=result.risk_score,
            summary=(
                f"{result.risk_level} RBI finding for {cml.name}; "
                f"recommended inspection interval: "
                f"{result.recommended_interval_years:.1f} years."
            ),
            recommended_interval_years=result.recommended_interval_years,
        )))

    return schemas.CMMSRunSyncOut(
        adapter=adapter.adapter_name,
        run_id=run_id,
        eligible_count=len(rows),
        created_count=sum(receipt.created for receipt in receipts),
        work_orders=receipts,
    )
