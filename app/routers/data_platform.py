from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..models_data_platform import (
    ApprovalWorkflow,
    DataQualityStatus,
    EngineeringAssumption,
    TraceableEvent,
)
from ..services.data_platform import DataPlatformError, DataPlatformService

router = APIRouter(prefix="/data-platform", tags=["data-platform"])


def _raise_platform_error(error: DataPlatformError) -> None:
    detail = {"message": str(error)}
    if error.missing_fields:
        detail["missing_fields"] = error.missing_fields
    raise HTTPException(status_code=error.status_code, detail=detail) from error


@router.post("/quality-records", response_model=schemas.DataQualityOut)
def create_quality_record(
    payload: schemas.DataQualityCreate,
    db: Session = Depends(get_db),
):
    service = DataPlatformService(db)
    try:
        record = service.record_quality(
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            field_name=payload.field_name,
            source=payload.source,
            source_date=payload.source_date,
            quality=payload.quality,
            actor=payload.actor,
            note=payload.note,
        )
        db.commit()
        db.refresh(record)
        return record
    except DataPlatformError as error:
        db.rollback()
        _raise_platform_error(error)


@router.get("/quality-records", response_model=list[schemas.DataQualityOut])
def list_quality_records(
    entity_type: schemas.DataEntityType | None = None,
    entity_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(DataQualityStatus)
    if entity_type is not None:
        query = query.filter(DataQualityStatus.entity_type == entity_type)
    if entity_id is not None:
        query = query.filter(DataQualityStatus.entity_id == entity_id)
    return query.order_by(DataQualityStatus.id.desc()).limit(limit).all()


@router.post("/assumptions", response_model=schemas.EngineeringAssumptionOut)
def create_assumption(
    payload: schemas.EngineeringAssumptionCreate,
    db: Session = Depends(get_db),
):
    service = DataPlatformService(db)
    try:
        assumption = service.create_assumption(
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            field_name=payload.field_name,
            value=payload.assumed_value,
            basis=payload.basis,
            actor=payload.actor,
        )
        db.commit()
        db.refresh(assumption)
        return assumption
    except DataPlatformError as error:
        db.rollback()
        _raise_platform_error(error)


@router.post(
    "/assumptions/{assumption_id}/approve",
    response_model=schemas.EngineeringAssumptionOut,
)
def approve_assumption(
    assumption_id: int,
    payload: schemas.ActorAction,
    db: Session = Depends(get_db),
):
    service = DataPlatformService(db)
    try:
        assumption = service.approve_assumption(assumption_id, payload.actor)
        db.commit()
        db.refresh(assumption)
        return assumption
    except DataPlatformError as error:
        db.rollback()
        _raise_platform_error(error)


@router.post(
    "/assumptions/{assumption_id}/deactivate",
    response_model=schemas.EngineeringAssumptionOut,
)
def deactivate_assumption(
    assumption_id: int,
    payload: schemas.ActorAction,
    db: Session = Depends(get_db),
):
    service = DataPlatformService(db)
    try:
        assumption = service.deactivate_assumption(assumption_id, payload.actor)
        db.commit()
        db.refresh(assumption)
        return assumption
    except DataPlatformError as error:
        db.rollback()
        _raise_platform_error(error)


@router.post("/workflows", response_model=schemas.ApprovalWorkflowOut)
def submit_workflow(
    payload: schemas.ApprovalWorkflowCreate,
    db: Session = Depends(get_db),
):
    service = DataPlatformService(db)
    try:
        workflow = service.submit_for_approval(
            payload.entity_type,
            payload.entity_id,
            payload.actor,
        )
        db.commit()
        db.refresh(workflow)
        return workflow
    except DataPlatformError as error:
        db.rollback()
        _raise_platform_error(error)


@router.post(
    "/workflows/{workflow_id}/decision",
    response_model=schemas.ApprovalWorkflowOut,
)
def decide_workflow(
    workflow_id: int,
    payload: schemas.ApprovalWorkflowDecision,
    db: Session = Depends(get_db),
):
    service = DataPlatformService(db)
    try:
        workflow = service.decide(
            workflow_id,
            payload.decision,
            payload.actor,
            payload.comment,
        )
        db.commit()
        db.refresh(workflow)
        return workflow
    except DataPlatformError as error:
        db.rollback()
        _raise_platform_error(error)


@router.get("/events", response_model=list[schemas.TraceableEventOut])
def list_traceable_events(
    entity_type: schemas.DataEntityType | None = None,
    entity_id: int | None = Query(default=None, gt=0),
    since: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(TraceableEvent)
    if entity_type is not None:
        query = query.filter(TraceableEvent.entity_type == entity_type)
    if entity_id is not None:
        query = query.filter(TraceableEvent.entity_id == entity_id)
    if since is not None:
        query = query.filter(TraceableEvent.occurred_at >= since)
    return query.order_by(TraceableEvent.id.desc()).limit(limit).all()


@router.get("/workflows", response_model=list[schemas.ApprovalWorkflowOut])
def list_workflows(
    entity_type: schemas.DataEntityType | None = None,
    entity_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(ApprovalWorkflow)
    if entity_type is not None:
        query = query.filter(ApprovalWorkflow.entity_type == entity_type)
    if entity_id is not None:
        query = query.filter(ApprovalWorkflow.entity_id == entity_id)
    return query.order_by(ApprovalWorkflow.id.desc()).limit(limit).all()


@router.get("/assumptions", response_model=list[schemas.EngineeringAssumptionOut])
def list_assumptions(
    entity_type: schemas.DataEntityType | None = None,
    entity_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(EngineeringAssumption)
    if entity_type is not None:
        query = query.filter(EngineeringAssumption.entity_type == entity_type)
    if entity_id is not None:
        query = query.filter(EngineeringAssumption.entity_id == entity_id)
    return query.order_by(EngineeringAssumption.id.desc()).limit(limit).all()
