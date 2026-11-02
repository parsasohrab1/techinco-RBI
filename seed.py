from datetime import date

from app import models
from app.database import Base, SessionLocal, engine, migrate_component_cui_fields

Base.metadata.create_all(bind=engine)
migrate_component_cui_fields(engine)
db = SessionLocal()

if db.query(models.Equipment).count() > 0:
    print("ℹ️  Demo data already present — skipping seed.")
    raise SystemExit(0)

# Damage mechanism catalog
thin = models.DamageMechanism(name="Thinning", api571_ref="API 571 §4.2.1", category="mechanical")
cui = models.DamageMechanism(name="CUI", api571_ref="API 571 §4.3.1", category="corrosion")
crack = models.DamageMechanism(name="Cracking", api571_ref="API 571 §4.5", category="mechanical")
db.add_all([thin, cui, crack])
db.flush()

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
