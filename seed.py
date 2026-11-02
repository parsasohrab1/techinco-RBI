from datetime import date

from app import models
from app.database import (
    Base,
    SessionLocal,
    engine,
    migrate_component_cui_fields,
    migrate_damage_mechanism_assessment_data,
)

Base.metadata.create_all(bind=engine)
migrate_component_cui_fields(engine)
migrate_damage_mechanism_assessment_data(engine)
db = SessionLocal()

# Keep the mechanism catalog current even when demo equipment was seeded earlier.
catalog = [
    models.DamageMechanism(
        name="Thinning", api571_ref="API 571 §4.2.1", category="mechanical"
    ),
    models.DamageMechanism(
        name="CUI", api571_ref="API 571 §4.3.1", category="corrosion"
    ),
    models.DamageMechanism(
        name="Cracking", api571_ref="API 571 §4.5", category="mechanical"
    ),
    models.DamageMechanism(
        name="SCC", api571_ref="API 571 (general mechanism)", category="cracking"
    ),
]
existing_names = {
    name for (name,) in db.query(models.DamageMechanism.name).all()
}
db.add_all(mechanism for mechanism in catalog if mechanism.name not in existing_names)
db.commit()

if db.query(models.Equipment).count() > 0:
    print("ℹ️  Demo data already present — skipping seed.")
    db.close()
    raise SystemExit(0)

mechanisms = {
    mechanism.name: mechanism
    for mechanism in db.query(models.DamageMechanism).all()
}
thin = mechanisms["Thinning"]
cui = mechanisms["CUI"]

# Demo vessel
eq = models.Equipment(
    tag_number="V-101", equipment_type="vessel", material="Carbon Steel",
    design_pressure_kpa=1500.0, design_temperature_c=80.0,
    inventory_m3=20.0, fluid_type="liquid", hazardous=True,
)
comp = models.Component(
    name="Shell",
    t_min_mm=8.0,
    t_nominal_mm=14.0,
    geometry_type="shell",
    insulated=True,
    operating_temperature_c=80.0,
)
comp.damage_mechanisms.append(models.ComponentDamageMechanism(
    dm_id=thin.id, status="active", justification="Carbon steel in wet service",
))
comp.damage_mechanisms.append(models.ComponentDamageMechanism(
    dm_id=cui.id, status="active", justification="Insulated carbon steel in operating service",
))
cml = models.CML(name="CML-01-Shell")
cml.inspections.append(models.InspectionRecord(
    inspection_date=date(2020, 5, 1), thickness_mm=12.6, effectiveness="B", method="UT",
))
cml.inspections.append(models.InspectionRecord(
    inspection_date=date(2023, 6, 1), thickness_mm=11.9, effectiveness="B", method="UT",
))
comp.cmls.append(cml)
eq.components.append(comp)
db.add(eq)
db.commit()
print(f"✅ Seeded equipment {eq.tag_number} with component + CML + 2 inspections")
db.close()
