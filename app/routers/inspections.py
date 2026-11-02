from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services import audit

router = APIRouter(tags=["inspections"])


@router.post("/cml/{cml_id}/inspections", response_model=schemas.InspectionOut)
def add_inspection(cml_id: int, payload: schemas.InspectionCreate, db: Session = Depends(get_db)):
    cml = db.get(models.CML, cml_id)
    if not cml:
        raise HTTPException(404, "CML not found")
    rec = models.InspectionRecord(cml_id=cml_id, **payload.model_dump())
    db.add(rec)
    db.flush()
    audit.log(db, rec, "create")
    db.commit()
    db.refresh(rec)
    return rec


@router.get("/cml/{cml_id}/inspections", response_model=list[schemas.InspectionOut])
def list_inspections(cml_id: int, db: Session = Depends(get_db)):
    cml = db.get(models.CML, cml_id)
    if not cml:
        raise HTTPException(404, "CML not found")
    return cml.inspections
