import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..database import get_db
from ..services.analysis_orchestrator import get_corrosion_calculator
from ..services.audit import current_user_id
from ..services.data_platform import DataPlatformService
from ..services.engine.corrosion_calculator import (
    build_circuit_input_snapshot,
    circuit_defaults,
    circuit_input_digest,
)

router = APIRouter(tags=["corrosion circuits"])


def _load_circuit(db: Session, circuit_id: int) -> models.CorrosionCircuit:
    circuit = (
        db.query(models.CorrosionCircuit)
        .options(
            selectinload(models.CorrosionCircuit.components)
            .selectinload(models.Component.cmls)
            .selectinload(models.CML.inspections)
        )
        .filter(models.CorrosionCircuit.id == circuit_id)
        .one_or_none()
    )
    if circuit is None:
        raise HTTPException(404, "Corrosion circuit not found")
    return circuit


def _summary_response(
    summary: models.CorrosionCalcSummary,
) -> schemas.CorrosionCalcSummaryOut:
    return schemas.CorrosionCalcSummaryOut(
        id=summary.id,
        circuit_id=summary.circuit_id,
        measurement_set_id=summary.measurement_set_id,
        status=summary.status,
        input_snapshot=json.loads(summary.input_snapshot_json),
        results=json.loads(summary.results_json),
        calculated_by=summary.calculated_by,
        calculated_at=summary.calculated_at,
        approved_by=summary.approved_by,
        approved_at=summary.approved_at,
        approval_comment=summary.approval_comment,
    )


@router.get("/circuits", response_model=list[schemas.CorrosionCircuitOut])
def list_circuits(db: Annotated[Session, Depends(get_db)]):
    return (
        db.query(models.CorrosionCircuit)
        .order_by(models.CorrosionCircuit.equipment_id, models.CorrosionCircuit.circuit_code)
        .all()
    )


@router.post(
    "/equipment/{equipment_id}/circuits",
    response_model=schemas.CorrosionCircuitOut,
    status_code=201,
)
def create_circuit(
    equipment_id: int,
    payload: schemas.CorrosionCircuitCreate,
    db: Annotated[Session, Depends(get_db)],
):
    equipment = db.get(models.Equipment, equipment_id)
    if equipment is None:
        raise HTTPException(404, "Equipment not found")
    if (
        db.query(models.CorrosionCircuit.id)
        .filter_by(equipment_id=equipment_id, circuit_code=payload.circuit_code)
        .first()
    ):
        raise HTTPException(409, "Circuit code already exists for this equipment")

    defaults = circuit_defaults(equipment.equipment_type)
    provided = payload.model_dump(exclude_unset=True)
    for key in ("calculation_method", "suggested_corrosion_rate_mm_yr"):
        if provided.get(key) is not None:
            defaults[key] = provided[key]
    defaults_source = (
        "user_configured"
        if any(
            provided.get(key) is not None
            for key in ("calculation_method", "suggested_corrosion_rate_mm_yr")
        )
        else defaults["defaults_source"]
    )
    circuit = models.CorrosionCircuit(
        equipment_id=equipment_id,
        circuit_code=payload.circuit_code,
        description=payload.description,
        calculation_method=defaults["calculation_method"],
        suggested_corrosion_rate_mm_yr=defaults[
            "suggested_corrosion_rate_mm_yr"
        ],
        interval_factor=payload.interval_factor,
        tif_override=payload.tif_override,
        time_based_interval_years=payload.time_based_interval_years,
        max_inspection_interval_years=payload.max_inspection_interval_years,
        ignore_calculated_interval=payload.ignore_calculated_interval,
        defaults_source=defaults_source,
    )
    db.add(circuit)
    db.flush()
    DataPlatformService(db).record_event(
        "corrosion_circuit_created",
        "corrosion_circuit",
        circuit.id,
        str(current_user_id.get()),
        {
            "equipment_id": equipment_id,
            "circuit_code": circuit.circuit_code,
            "calculation_method": circuit.calculation_method,
            "defaults_source": circuit.defaults_source,
        },
    )
    db.commit()
    db.refresh(circuit)
    return circuit


@router.post(
    "/circuits/{circuit_id}/components/{component_id}",
    response_model=schemas.ComponentOut,
)
def assign_component(
    circuit_id: int,
    component_id: int,
    db: Annotated[Session, Depends(get_db)],
):
    circuit = db.get(models.CorrosionCircuit, circuit_id)
    component = db.get(models.Component, component_id)
    if circuit is None:
        raise HTTPException(404, "Corrosion circuit not found")
    if component is None:
        raise HTTPException(404, "Component not found")
    if circuit.equipment_id != component.equipment_id:
        raise HTTPException(
            422, "A component can only be assigned to a circuit on its equipment"
        )
    if component.circuit_id not in {None, circuit_id}:
        raise HTTPException(409, "Component is already assigned to another circuit")
    component.circuit_id = circuit_id
    DataPlatformService(db).record_event(
        "component_assigned_to_corrosion_circuit",
        "component",
        component.id,
        str(current_user_id.get()),
        {"circuit_id": circuit_id},
    )
    db.commit()
    db.refresh(component)
    return component


@router.get(
    "/circuits/{circuit_id}/measurement-sets",
    response_model=list[schemas.MeasurementSetOut],
)
def list_measurement_sets(
    circuit_id: int,
    db: Annotated[Session, Depends(get_db)],
):
    if db.get(models.CorrosionCircuit, circuit_id) is None:
        raise HTTPException(404, "Corrosion circuit not found")
    return (
        db.query(models.MeasurementSet)
        .filter(models.MeasurementSet.circuit_id == circuit_id)
        .order_by(models.MeasurementSet.measurement_date.desc())
        .all()
    )


@router.post(
    "/circuits/{circuit_id}/measurement-sets",
    response_model=schemas.MeasurementSetOut,
    status_code=201,
)
def create_measurement_set(
    circuit_id: int,
    payload: schemas.MeasurementSetCreate,
    db: Annotated[Session, Depends(get_db)],
):
    circuit = db.get(models.CorrosionCircuit, circuit_id)
    if circuit is None:
        raise HTTPException(404, "Corrosion circuit not found")
    measurement_set = models.MeasurementSet(
        circuit_id=circuit_id,
        name=payload.name,
        description=payload.description,
        measurement_date=payload.measurement_date,
        technician=payload.technician,
    )
    db.add(measurement_set)
    db.flush()
    DataPlatformService(db).record_event(
        "measurement_set_created",
        "measurement_set",
        measurement_set.id,
        str(current_user_id.get()),
        {"circuit_id": circuit_id, "name": measurement_set.name},
    )
    db.commit()
    db.refresh(measurement_set)
    return measurement_set


@router.post(
    "/circuits/{circuit_id}/calculate",
    response_model=schemas.CorrosionCalcSummaryOut,
    status_code=201,
)
def calculate_circuit(
    circuit_id: int,
    payload: schemas.CorrosionCalculateRequest,
    db: Annotated[Session, Depends(get_db)],
):
    circuit = _load_circuit(db, circuit_id)
    if not circuit.components:
        raise HTTPException(409, "Assign at least one component before calculation")
    measurement_set = None
    if payload.measurement_set_id is not None:
        measurement_set = db.get(models.MeasurementSet, payload.measurement_set_id)
        if measurement_set is None or measurement_set.circuit_id != circuit_id:
            raise HTTPException(404, "Measurement set not found on this circuit")
    try:
        calculator = get_corrosion_calculator()
    except NotImplementedError as error:
        raise HTTPException(503, str(error)) from error
    snapshot = build_circuit_input_snapshot(circuit)
    results = calculator.calculate_circuit(circuit, circuit.components)
    stored_snapshot = {"digest": circuit_input_digest(snapshot), "inputs": snapshot}
    summary = models.CorrosionCalcSummary(
        circuit_id=circuit_id,
        measurement_set_id=measurement_set.id if measurement_set else None,
        status="calculated",
        input_snapshot_json=json.dumps(stored_snapshot, sort_keys=True),
        results_json=json.dumps(results, sort_keys=True),
        calculated_by=payload.actor,
    )
    db.add(summary)
    db.flush()
    DataPlatformService(db).record_event(
        "corrosion_calculation_completed",
        "corrosion_calc_summary",
        summary.id,
        payload.actor,
        {
            "circuit_id": circuit_id,
            "measurement_set_id": summary.measurement_set_id,
            "model": calculator.name,
            "version": calculator.version,
            "compliance_status": calculator.compliance_status,
            "driving_cml": results["circuit"]["driving_cml"],
            "driving_nid": results["circuit"]["driving_nid"],
        },
    )
    db.commit()
    db.refresh(summary)
    return _summary_response(summary)


@router.get(
    "/circuits/{circuit_id}/calculations/latest",
    response_model=schemas.CorrosionCalcSummaryOut,
)
def latest_circuit_calculation(
    circuit_id: int,
    db: Annotated[Session, Depends(get_db)],
):
    if db.get(models.CorrosionCircuit, circuit_id) is None:
        raise HTTPException(404, "Corrosion circuit not found")
    summary = (
        db.query(models.CorrosionCalcSummary)
        .filter(models.CorrosionCalcSummary.circuit_id == circuit_id)
        .order_by(models.CorrosionCalcSummary.id.desc())
        .first()
    )
    if summary is None:
        raise HTTPException(404, "No corrosion calculation exists for this circuit")
    return _summary_response(summary)


@router.post(
    "/circuits/calculations/{summary_id}/approve",
    response_model=schemas.CorrosionCalcSummaryOut,
)
def approve_circuit_calculation(
    summary_id: int,
    payload: schemas.CorrosionApproveRequest,
    db: Annotated[Session, Depends(get_db)],
):
    summary = db.get(models.CorrosionCalcSummary, summary_id)
    if summary is None:
        raise HTTPException(404, "Calculation summary not found")
    if summary.status != "calculated":
        raise HTTPException(409, "Only a calculated summary can be approved")
    circuit = _load_circuit(db, summary.circuit_id)
    saved_snapshot = json.loads(summary.input_snapshot_json)
    current_snapshot = build_circuit_input_snapshot(circuit)
    if saved_snapshot["digest"] != circuit_input_digest(current_snapshot):
        raise HTTPException(
            409, "Circuit inputs changed after calculation; recalculate before approval"
        )
    summary.status = "approved"
    summary.approved_by = payload.actor
    summary.approved_at = datetime.now(UTC).replace(tzinfo=None)
    summary.approval_comment = payload.comment
    if summary.measurement_set_id is not None:
        measurement_set = db.get(models.MeasurementSet, summary.measurement_set_id)
        if measurement_set is not None:
            measurement_set.status = "completed"
    DataPlatformService(db).record_event(
        "corrosion_calculation_approved",
        "corrosion_calc_summary",
        summary.id,
        payload.actor,
        {
            "circuit_id": summary.circuit_id,
            "measurement_set_id": summary.measurement_set_id,
            "comment": payload.comment,
            "input_digest": saved_snapshot["digest"],
        },
    )
    db.commit()
    db.refresh(summary)
    return _summary_response(summary)
