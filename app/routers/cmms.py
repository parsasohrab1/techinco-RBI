import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services import audit
from ..services.cmms import CMMSAdapter, WorkOrderRequest, get_cmms_adapter
from ..services.data_platform import DataPlatformService

_WORK_ORDER_REFERENCE = re.compile(r"^rbi-run-(\d+)-cml-(\d+)$")

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


@router.post(
    "/work-orders/{external_reference}/complete",
    response_model=schemas.CMMSCompletionOut,
)
def complete_work_order(
    external_reference: str,
    payload: schemas.CMMSWorkOrderComplete,
    db: Session = Depends(get_db),
    adapter: CMMSAdapter = Depends(get_cmms_adapter),
):
    """Record a laboratory field reading and close the mock work order.

    The reading stays unverified until data-quality evidence is recorded.
    The next analysis remains blocked until that evidence exists.
    """
    receipt = adapter.get_work_order(external_reference)
    if receipt is None:
        raise HTTPException(status_code=404, detail="Work order not found")
    if receipt.status == "completed":
        raise HTTPException(status_code=409, detail="Work order is already completed")
    match = _WORK_ORDER_REFERENCE.fullmatch(external_reference)
    if match is None:
        raise HTTPException(status_code=422, detail="Work order reference is not recognizable")
    cml_id = int(match.group(2))
    cml = db.get(models.CML, cml_id)
    if cml is None:
        raise HTTPException(status_code=404, detail="CML not found")

    inspection = models.InspectionRecord(
        cml_id=cml_id,
        inspection_date=payload.inspection_date,
        thickness_mm=payload.thickness_mm,
        method=payload.method,
        effectiveness=payload.effectiveness,
        quality_indicator="unreviewed",
        reading_type="measured",
        inspector_id=0,
    )
    db.add(inspection)
    db.flush()
    audit.log(db, inspection, "create")
    DataPlatformService(db).record_event(
        "cmms_field_reading_recorded",
        "inspection_record",
        inspection.id,
        payload.actor,
        {
            "external_reference": external_reference,
            "work_order_id": receipt.work_order_id,
            "cml_id": cml_id,
            "inspection_date": payload.inspection_date.isoformat(),
            "thickness_mm": payload.thickness_mm,
            "method": payload.method,
            "effectiveness": payload.effectiveness,
            "quality_indicator": "unreviewed",
        },
    )
    db.commit()
    completed = adapter.mark_completed(external_reference)
    return schemas.CMMSCompletionOut(
        work_order_id=completed.work_order_id,
        external_reference=external_reference,
        status=completed.status,
        cml_id=cml_id,
        inspection_id=inspection.id,
        thickness_mm=payload.thickness_mm,
        note=(
            "Field reading stored as unreviewed. Record data-quality evidence "
            "before the next analysis; this laboratory adapter is not SAP or Maximo."
        ),
    )
