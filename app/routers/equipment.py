from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services import audit
from ..standards.baseline import Baseline

router = APIRouter(prefix="/equipment", tags=["equipment"])


@router.post("", response_model=schemas.EquipmentOut)
def create_equipment(payload: schemas.EquipmentCreate, db: Session = Depends(get_db)):
    try:
        Baseline.equipment_scope.validate(payload.equipment_type)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    eq = models.Equipment(**payload.model_dump())
    db.add(eq)
    db.flush()
    audit.log(db, eq, "create")
    db.commit()
    db.refresh(eq)
    return eq


@router.get("/types", response_model=list[str])
def list_equipment_types():
    return list(Baseline.equipment_scope.allowed_types)


@router.get("", response_model=list[schemas.EquipmentOut])
def list_equipment(db: Session = Depends(get_db)):
    return db.query(models.Equipment).order_by(models.Equipment.tag_number).all()


@router.get("/{equipment_id:int}", response_model=schemas.EquipmentDetail)
def get_equipment(equipment_id: int, db: Session = Depends(get_db)):
    eq = db.get(models.Equipment, equipment_id)
    if not eq:
        raise HTTPException(404, "Equipment not found")
    return eq


@router.post("/{equipment_id}/components", response_model=schemas.ComponentOut)
def add_component(equipment_id: int, payload: schemas.ComponentCreate, db: Session = Depends(get_db)):
    eq = db.get(models.Equipment, equipment_id)
    if not eq:
        raise HTTPException(404, "Equipment not found")
    comp = models.Component(
        equipment_id=equipment_id, name=payload.name,
        t_min_mm=payload.t_min_mm, t_nominal_mm=payload.t_nominal_mm,
        geometry_type=payload.geometry_type,
        insulated=payload.insulated,
        operating_temperature_c=payload.operating_temperature_c,
    )
    for cname in payload.cml_names:
        comp.cmls.append(models.CML(name=cname))
    db.add(comp)
    db.flush()
    audit.log(db, comp, "create")
    db.commit()
    db.refresh(comp)
    return comp
