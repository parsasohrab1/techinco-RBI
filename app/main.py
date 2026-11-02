from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import models  # noqa: F401 - ensure models are registered
from .database import (
    Base,
    engine,
    migrate_component_cui_fields,
    migrate_damage_mechanism_assessment_data,
    migrate_equipment_plant_unit,
)
from .routers import (
    analysis,
    audit_router,
    cmms,
    damage_mechanisms,
    data_platform,
    equipment,
    inspections,
    reports,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    migrate_component_cui_fields(engine)
    migrate_damage_mechanism_assessment_data(engine)
    migrate_equipment_plant_unit(engine)
    yield


app = FastAPI(
    title="RBI Enterprise API",
    description=(
        "RBI screening prototype referencing API RP 580 / API RP 581; "
        "internal calculations are not standards-conforming."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(equipment.router)
app.include_router(inspections.router)
app.include_router(damage_mechanisms.router)
app.include_router(analysis.router)
app.include_router(reports.router)
app.include_router(audit_router.router)
app.include_router(cmms.router)
app.include_router(data_platform.router)


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}
