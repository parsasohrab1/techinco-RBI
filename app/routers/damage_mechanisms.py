import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services import audit
from ..services.data_platform import DataPlatformService

router = APIRouter(prefix="/damage-mechanisms", tags=["damage-mechanisms"])


@router.get("", response_model=list[schemas.DamageMechanismOut])
def list_dm(db: Session = Depends(get_db)):
    return db.query(models.DamageMechanism).order_by(models.DamageMechanism.name).all()


@router.post("/components/{component_id}/assign")
def assign_dm(component_id: int, payload: schemas.ComponentDMCreate, db: Session = Depends(get_db)):
    comp = db.get(models.Component, component_id)
    if not comp:
        raise HTTPException(404, "Component not found")
    dm = db.get(models.DamageMechanism, payload.dm_id)
    if not dm:
        raise HTTPException(404, "Damage mechanism not found")
    if payload.status == "rejected" and not payload.justification:
        raise HTTPException(400, "Rejected mechanisms require justification")
    link = models.ComponentDamageMechanism(
        component_id=component_id, dm_id=payload.dm_id,
        status=payload.status, justification=payload.justification,
        assessment_data_json=json.dumps(payload.assessment_data),
    )
    db.add(link)
    db.flush()
    audit.log(db, link, "create")
    DataPlatformService(db).record_event(
        "damage_mechanism_assigned",
        "component_damage_mechanism",
        link.id,
        str(audit.current_user_id.get()),
        {
            "component_id": component_id,
            "damage_mechanism_id": dm.id,
            "name": dm.name,
            "status": link.status,
            "justification": link.justification,
            "assessment_data": payload.assessment_data,
        },
    )
    db.commit()
    db.refresh(link)
    return {"id": link.id, "status": link.status}
