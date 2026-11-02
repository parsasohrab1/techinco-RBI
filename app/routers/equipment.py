from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services import audit

router = APIRouter(prefix="/equipment", tags=["equipment"])


@router.post("", response_model=schemas.EquipmentOut)
def create_equipment(payload: schemas.EquipmentCreate, db: Session = Depends(get_db)):
    eq = models.Equipment(**payload.model_dump())
    db.add(eq)
    db.flush()
    audit.log(db, eq, "create")
    db.commit()
    db.refresh(eq)
    return eq


@router.get("", response_model=list[schemas.EquipmentOut])
def list_equipment(db: Session = Depends(get_db)):
    return db.query(models.Equipment).order_by(models.Equipment.tag_number).all()


@router.get("/{equipment_id}", response_model=schemas.EquipmentDetail)
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
    )
    for cname in payload.cml_names:
        comp.cmls.append(models.CML(name=cname))
    db.add(comp)
    db.flush()
    audit.log(db, comp, "create")
    db.commit()
    db.refresh(comp)
    return comp
