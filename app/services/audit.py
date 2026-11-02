import json
from contextvars import ContextVar
from datetime import date, datetime

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from .. import models

current_user_id: ContextVar[int] = ContextVar("current_user_id", default=0)


def _val(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def _serialize(obj) -> str:
    mapper = inspect(obj).mapper
    return json.dumps({c.name: _val(getattr(obj, c.name)) for c in mapper.columns})


def log(db: Session, entity, action: str, old: str = ""):
    if entity is None:
        return
    db.add(
        models.AuditLog(
            entity_type=type(entity).__name__,
            entity_id=getattr(entity, "id", 0) or 0,
            action=action,
            old_value=old,
            new_value=_serialize(entity),
            user_id=current_user_id.get(),
        )
    )
