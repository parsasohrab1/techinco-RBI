"""Create a deterministic, isolated synthetic RBI portfolio and analyze it."""

import argparse
import json
import os
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, insert, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, selectinload

from app import models
from app.database import Base
from app.models_data_platform import DataQualityStatus
from app.services.analysis_orchestrator import analyze_equipment
from app.services.engine.corrosion_calculator import (
    InternalCorrosionCalculator,
    build_circuit_input_snapshot,
    circuit_defaults,
    circuit_input_digest,
)

QUALITY_SOURCE = "Synthetic demonstration data"
QUALITY_ACTOR = "synthetic-dataset-generator"
QUALITY_SOURCE_DATE = datetime(2026, 1, 1, tzinfo=timezone.utc)
PLANT_UNITS = (
    ("GSP", "Gas separation plant"),
    ("ETH", "Ethylene production plant"),
    ("PE", "Polyethylene production plant"),
    ("PP", "Polypropylene production plant"),
    ("ES", "Energy supply plant"),
)
EQUIPMENT_TYPES = (
    "vessel",
    "vessel",
    "pressure_vessel",
    "column",
    "heat_exchanger",
    "piping",
    "pipeline",
    "atmospheric_tank",
    "storage_tank",
    "pump",
    "turbine",
    "compressor",
    "boiler",
    "fired_heater",
    "reactor",
    "valve",
    "pressure_relief_device",
)
INSPECTION_METHODS = ("UT", "PAUT", "RT", "Profile RT")
COMPONENT_PROFILES = {
    "vessel": (("Shell", "shell"), ("Head", "head"), ("Nozzle", "nozzle")),
    "pressure_vessel": (
        ("Shell", "shell"),
        ("Head", "head"),
        ("Nozzle", "nozzle"),
    ),
    "column": (
        ("Column shell", "shell"),
        ("Tray section", "shell"),
        ("Nozzle", "nozzle"),
    ),
    "heat_exchanger": (
        ("Shell side", "shell"),
        ("Channel head", "head"),
        ("Tube bundle", "tube"),
    ),
    "piping": (("Pipe segment", "pipe"), ("Elbow", "pipe"), ("Nozzle", "nozzle")),
    "pipeline": (
        ("Pipeline segment", "pipe"),
        ("Elbow", "pipe"),
        ("Nozzle", "nozzle"),
    ),
    "atmospheric_tank": (
        ("Tank shell course", "shell"),
        ("Tank bottom", "shell"),
        ("Roof plate", "shell"),
    ),
    "storage_tank": (
        ("Tank shell course", "shell"),
        ("Tank bottom", "shell"),
        ("Roof plate", "shell"),
    ),
    "pump": (
        ("Casing", "shell"),
        ("Impeller", "rotor"),
        ("Nozzle", "nozzle"),
    ),
    "turbine": (
        ("Casing", "shell"),
        ("Rotor", "rotor"),
        ("Steam chest", "shell"),
    ),
    "compressor": (
        ("Casing", "shell"),
        ("Rotor", "rotor"),
        ("Nozzle", "nozzle"),
    ),
    "boiler": (("Steam drum", "shell"), ("Header", "pipe"), ("Water wall", "shell")),
    "fired_heater": (
        ("Radiant coil", "tube"),
        ("Convection coil", "tube"),
        ("Header", "pipe"),
    ),
    "reactor": (
        ("Reactor shell", "shell"),
        ("Head", "head"),
        ("Nozzle", "nozzle"),
    ),
    "valve": (("Body", "shell"), ("Bonnet", "shell"), ("Nozzle", "nozzle")),
    "pressure_relief_device": (("Inlet nozzle", "nozzle"), ("Outlet nozzle", "nozzle")),
}
MECHANISM_CATALOG = (
    ("Thinning", "API 571 §4.2.1", "mechanical"),
    ("CUI", "API 571 §4.3.1", "corrosion"),
    ("SCC", "API 571 (general mechanism)", "cracking"),
)
COMPONENT_BATCH_SIZE = 100


def create_synthetic_portfolio(
    db: Session,
    component_count: int = 10_000,
    equipment_count: int = 100,
    seed: int = 5812026,
    tag_prefix: str = "SYN-RBI",
    inspections_per_component: int = 50,
) -> list[int]:
    if component_count < 1:
        raise ValueError("component_count must be positive.")
    if equipment_count < 1 or equipment_count > component_count:
        raise ValueError("equipment_count must be between 1 and component_count.")
    if inspections_per_component < 2:
        raise ValueError("inspections_per_component must be at least 2.")
    if not tag_prefix.strip():
        raise ValueError("tag_prefix must not be empty.")

    existing_tag = db.scalar(
        select(models.Equipment.id).where(
            models.Equipment.tag_number.like(f"{tag_prefix}-%")
        ).limit(1)
    )
    if existing_tag is not None:
        raise ValueError(
            f"Equipment with tag prefix '{tag_prefix}-' already exists; "
            "choose another prefix or database."
        )

    equipment_start = (db.scalar(select(func.max(models.Equipment.id))) or 0) + 1
    component_start = (db.scalar(select(func.max(models.Component.id))) or 0) + 1
    cml_start = (db.scalar(select(func.max(models.CML.id))) or 0) + 1
    inspection_start = (
        db.scalar(select(func.max(models.InspectionRecord.id))) or 0
    ) + 1
    circuit_start = (
        db.scalar(select(func.max(models.CorrosionCircuit.id))) or 0
    ) + 1
    measurement_set_start = (
        db.scalar(select(func.max(models.MeasurementSet.id))) or 0
    ) + 1
    mechanism_link_start = (
        db.scalar(select(func.max(models.ComponentDamageMechanism.id))) or 0
    ) + 1
    now = datetime.now(timezone.utc)
    rng = random.Random(seed)
    components_per_equipment = [
        component_count // equipment_count
        + (1 if index < component_count % equipment_count else 0)
        for index in range(equipment_count)
    ]

    equipment_rows = []
    equipment_quality = []
    for equipment_offset in range(equipment_count):
        equipment_id = equipment_start + equipment_offset
        plant_code, plant_unit = PLANT_UNITS[equipment_offset % len(PLANT_UNITS)]
        equipment_type = EQUIPMENT_TYPES[equipment_offset % len(EQUIPMENT_TYPES)]
        risk_profile = equipment_offset % 5
        if risk_profile == 0:
            pressure = float(rng.randrange(700, 1_101, 50))
            inventory = float(rng.randrange(10, 31, 5))
            fluid_type, hazardous = "liquid", False
        elif risk_profile == 1:
            pressure = float(rng.randrange(800, 1_801, 50))
            inventory = float(rng.randrange(30, 101, 5))
            fluid_type, hazardous = "liquid", rng.choice((False, True))
        elif risk_profile == 2:
            pressure = float(rng.randrange(1_500, 2_801, 50))
            inventory = float(rng.randrange(100, 401, 10))
            fluid_type, hazardous = "gas", rng.choice((False, True))
        elif risk_profile == 3:
            pressure = float(rng.randrange(2_500, 3_601, 50))
            inventory = float(rng.randrange(300, 701, 10))
            fluid_type, hazardous = "gas", True
        else:
            pressure = float(rng.randrange(3_500, 4_001, 50))
            inventory = float(rng.randrange(700, 1_001, 10))
            fluid_type, hazardous = "gas", True
        equipment_rows.append({
            "id": equipment_id,
            "tag_number": (
                f"{tag_prefix}-{plant_code}-{equipment_offset + 1:04d}"
            ),
            "plant_unit": plant_unit,
            "equipment_type": equipment_type,
            "material": rng.choice(("Carbon Steel", "Cr-Mo Steel", "Stainless Steel")),
            "design_pressure_kpa": pressure,
            "design_temperature_c": float(rng.randrange(40, 301, 5)),
            "inventory_m3": inventory,
            "fluid_type": fluid_type,
            "hazardous": hazardous,
        })
        equipment_quality.extend(
            {
                "entity_type": "equipment",
                "entity_id": equipment_id,
                "field_name": field_name,
                "source": QUALITY_SOURCE,
                "source_date": QUALITY_SOURCE_DATE,
                "recorded_by": QUALITY_ACTOR,
                "recorded_at": now,
                "quality": "verified",
                "note": "Synthetic value; demonstration only, not verified plant data.",
            }
            for field_name in (
                "material",
                "design_pressure_kpa",
                "design_temperature_c",
                "inventory_m3",
                "fluid_type",
                "hazardous",
            )
        )

    db.execute(insert(models.Equipment), equipment_rows)
    db.execute(insert(DataQualityStatus), equipment_quality)
    recent_date = datetime.now(timezone.utc).date() - timedelta(days=120)
    circuit_rows = []
    measurement_set_rows = []
    measurement_set_ids: list[list[int]] = []
    for equipment_offset, equipment in enumerate(equipment_rows):
        circuit_id = circuit_start + equipment_offset
        defaults = circuit_defaults(equipment["equipment_type"])
        circuit_rows.append({
            "id": circuit_id,
            "equipment_id": equipment["id"],
            "circuit_code": "A",
            "description": "Synthetic corrosion-rate grouping for demonstration.",
            **defaults,
        })
        set_ids = []
        for inspection_offset in range(inspections_per_component):
            set_id = measurement_set_start + (
                equipment_offset * inspections_per_component + inspection_offset
            )
            fraction = inspection_offset / (inspections_per_component - 1)
            elapsed_days = round(15 * 365.25 * fraction)
            set_date = recent_date - timedelta(
                days=round(15 * 365.25) - elapsed_days
            )
            measurement_set_rows.append({
                "id": set_id,
                "circuit_id": circuit_id,
                "name": f"SYN-{inspection_offset + 1:03d}",
                "description": "Synthetic historical inspection campaign.",
                "measurement_date": set_date,
                "status": "completed",
                "technician": QUALITY_ACTOR,
                "created_at": now.replace(tzinfo=None),
            })
            set_ids.append(set_id)
        measurement_set_ids.append(set_ids)
    db.execute(insert(models.CorrosionCircuit), circuit_rows)
    db.execute(insert(models.MeasurementSet), measurement_set_rows)
    existing_mechanisms = {
        mechanism.name: mechanism
        for mechanism in db.scalars(select(models.DamageMechanism))
    }
    db.add_all(
        models.DamageMechanism(name=name, api571_ref=reference, category=category)
        for name, reference, category in MECHANISM_CATALOG
        if name not in existing_mechanisms
    )
    db.flush()
    mechanisms = {
        mechanism.name: mechanism.id
        for mechanism in db.scalars(select(models.DamageMechanism))
        if mechanism.name in {item[0] for item in MECHANISM_CATALOG}
    }

    component_index = 0
    mechanism_link_index = 0
    equipment_offset = 0
    equipment_component_end = components_per_equipment[0]
    while component_index < component_count:
        component_rows = []
        cml_rows = []
        inspection_rows = []
        mechanism_rows = []
        quality_rows = []

        for _ in range(min(COMPONENT_BATCH_SIZE, component_count - component_index)):
            while component_index >= equipment_component_end:
                equipment_offset += 1
                equipment_component_end += components_per_equipment[equipment_offset]
            equipment_id = equipment_start + equipment_offset
            equipment_type = equipment_rows[equipment_offset]["equipment_type"]
            component_id = component_start + component_index
            cml_id = cml_start + component_index
            first_inspection_id = (
                inspection_start + component_index * inspections_per_component
            )
            nominal = round(rng.uniform(10.0, 28.0), 2)
            minimum = round(rng.uniform(4.0, min(9.0, nominal - 2)), 2)
            initial_thickness = round(rng.uniform(minimum + 2, nominal), 2)
            maximum_loss = max(initial_thickness - minimum - 0.1, 0.1)
            total_loss = min(rng.uniform(0.35, 6.0), maximum_loss)
            deterioration_profile = component_index % 5
            if deterioration_profile == 0:
                total_loss = min(rng.uniform(0.25, 1.0), maximum_loss)
            elif deterioration_profile == 1:
                total_loss = min(rng.uniform(1.0, 2.5), maximum_loss)
            elif deterioration_profile >= 3:
                total_loss = min(rng.uniform(3.0, 6.0), maximum_loss)
            is_insulated = rng.random() < 0.35
            component_name, geometry_type = rng.choice(
                COMPONENT_PROFILES[equipment_type]
            )
            component_name = f"{component_name} {component_index + 1:05d}"
            component_rows.append({
                "id": component_id,
                "equipment_id": equipment_id,
                "circuit_id": circuit_start + equipment_offset,
                "name": component_name,
                "t_min_mm": minimum,
                "t_nominal_mm": nominal,
                "geometry_type": geometry_type,
                "insulated": is_insulated,
                "operating_temperature_c": float(rng.randrange(20, 251, 5)),
            })
            cml_rows.append({
                "id": cml_id,
                "component_id": component_id,
                "name": f"CML-{component_index + 1:05d}",
                "surface_condition": rng.choice(("normal", "coated", "weathered")),
            })
            previous_date = None
            for inspection_offset in range(inspections_per_component):
                fraction = inspection_offset / (inspections_per_component - 1)
                elapsed_days = round(15 * 365.25 * fraction)
                inspection_date = recent_date - timedelta(
                    days=round(15 * 365.25) - elapsed_days
                )
                if 0 < inspection_offset < inspections_per_component - 1:
                    inspection_date += timedelta(days=rng.randint(-18, 18))
                if previous_date is not None and inspection_date <= previous_date:
                    inspection_date = previous_date + timedelta(days=30)
                previous_date = inspection_date
                true_thickness = initial_thickness - total_loss * fraction
                thickness = round(
                    min(nominal, max(minimum - 0.05, true_thickness + rng.gauss(0, 0.12))),
                    2,
                )
                inspection_id = first_inspection_id + inspection_offset
                inspection_rows.append({
                    "id": inspection_id,
                    "cml_id": cml_id,
                    "measurement_set_id": measurement_set_ids[equipment_offset][
                        inspection_offset
                    ],
                    "inspection_date": inspection_date,
                    "thickness_mm": thickness,
                    "method": rng.choice(INSPECTION_METHODS),
                    "effectiveness": rng.choice(("A", "B", "C", "D", "E")),
                    "quality_indicator": "good",
                    "reading_type": "measured",
                    "inspector_id": 0,
                })
                for field_name in (
                    "inspection_date",
                    "thickness_mm",
                    "effectiveness",
                ):
                    quality_rows.append({
                        "entity_type": "inspection_record",
                        "entity_id": inspection_id,
                        "field_name": field_name,
                        "source": QUALITY_SOURCE,
                        "source_date": QUALITY_SOURCE_DATE,
                        "recorded_by": QUALITY_ACTOR,
                        "recorded_at": now,
                        "quality": "verified",
                        "note": "Synthetic value; demonstration only, not verified plant data.",
                    })

            assigned_mechanisms = [("Thinning", {})]
            if is_insulated:
                assigned_mechanisms.append(("CUI", {}))
            if rng.random() < 0.08:
                assigned_mechanisms.append((
                    "SCC",
                    {
                        "susceptible_material": True,
                        "environment_present": rng.choice((True, False)),
                        "tensile_stress_present": True,
                    },
                ))
            for mechanism_name, assessment_data in assigned_mechanisms:
                link_id = mechanism_link_start + mechanism_link_index
                mechanism_rows.append({
                    "id": link_id,
                    "component_id": component_id,
                    "dm_id": mechanisms[mechanism_name],
                    "status": "active",
                    "justification": (
                        "Synthetic screening assignment for demonstration only."
                    ),
                    "assessment_data_json": json.dumps(assessment_data),
                })
                for field_name in ("status", "assessment_data"):
                    quality_rows.append({
                        "entity_type": "component_damage_mechanism",
                        "entity_id": link_id,
                        "field_name": field_name,
                        "source": QUALITY_SOURCE,
                        "source_date": QUALITY_SOURCE_DATE,
                        "recorded_by": QUALITY_ACTOR,
                        "recorded_at": now,
                        "quality": "verified",
                        "note": "Synthetic mechanism screen; demonstration only.",
                    })
                mechanism_link_index += 1

            for field_name in (
                "t_min_mm",
                "t_nominal_mm",
                "geometry_type",
                "damage_mechanism_review",
                "insulated",
                "operating_temperature_c",
            ):
                quality_rows.append({
                    "entity_type": "component",
                    "entity_id": component_id,
                    "field_name": field_name,
                    "source": QUALITY_SOURCE,
                    "source_date": QUALITY_SOURCE_DATE,
                    "recorded_by": QUALITY_ACTOR,
                    "recorded_at": now,
                    "quality": "verified",
                    "note": "Synthetic value; demonstration only, not verified plant data.",
                })
            quality_rows.append({
                "entity_type": "cml",
                "entity_id": cml_id,
                "field_name": "inspection_history",
                "source": QUALITY_SOURCE,
                "source_date": QUALITY_SOURCE_DATE,
                "recorded_by": QUALITY_ACTOR,
                "recorded_at": now,
                "quality": "verified",
                "note": "Synthetic inspection history; demonstration only.",
            })
            component_index += 1

        db.execute(insert(models.Component), component_rows)
        db.execute(insert(models.CML), cml_rows)
        db.execute(insert(models.InspectionRecord), inspection_rows)
        db.execute(insert(models.ComponentDamageMechanism), mechanism_rows)
        db.execute(insert(DataQualityStatus), quality_rows)

    db.commit()
    return list(range(equipment_start, equipment_start + equipment_count))


def run_portfolio_analysis(db: Session, equipment_ids: list[int]) -> int:
    result_count = 0
    for equipment_id in equipment_ids:
        equipment = db.get(models.Equipment, equipment_id)
        if equipment is None:
            raise RuntimeError(f"Synthetic equipment {equipment_id} disappeared.")
        run = analyze_equipment(db, equipment)
        result_count += len(run.results)
    return result_count


def run_corrosion_circuit_calculations(
    db: Session,
    equipment_ids: list[int],
) -> int:
    circuit_ids = db.scalars(
        select(models.CorrosionCircuit.id).where(
            models.CorrosionCircuit.equipment_id.in_(equipment_ids)
        )
    ).all()
    calculator = InternalCorrosionCalculator()
    for circuit_id in circuit_ids:
        circuit = (
            db.query(models.CorrosionCircuit)
            .options(
                selectinload(models.CorrosionCircuit.components)
                .selectinload(models.Component.cmls)
                .selectinload(models.CML.inspections)
            )
            .filter(models.CorrosionCircuit.id == circuit_id)
            .one()
        )
        snapshot = build_circuit_input_snapshot(circuit)
        results = calculator.calculate_circuit(circuit, circuit.components)
        db.add(models.CorrosionCalcSummary(
            circuit_id=circuit.id,
            status="calculated",
            input_snapshot_json=json.dumps({
                "digest": circuit_input_digest(snapshot),
                "inputs": snapshot,
            }, sort_keys=True),
            results_json=json.dumps(results, sort_keys=True),
            calculated_by=QUALITY_ACTOR,
        ))
    db.commit()
    return len(circuit_ids)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("RBI_SYNTHETIC_DATABASE_URL", "sqlite:///./rbi-synthetic.db"),
        help="Target database URL. Defaults to a separate local SQLite database.",
    )
    parser.add_argument("--components", type=int, default=10_000)
    parser.add_argument("--equipment", type=int, default=100)
    parser.add_argument("--inspections-per-component", type=int, default=50)
    parser.add_argument("--seed", type=int, default=5812026)
    parser.add_argument("--tag-prefix", default="SYN-RBI")
    parser.add_argument(
        "--seed-only",
        action="store_true",
        help="Create synthetic records without running the calculation engine.",
    )
    args = parser.parse_args()

    if make_url(args.database_url).get_backend_name() != "sqlite":
        parser.error("Use a dedicated SQLite URL for this demonstration generator.")

    from sqlalchemy import create_engine

    database_engine = create_engine(
        args.database_url,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=database_engine)
    with Session(database_engine, autoflush=False, expire_on_commit=False) as db:
        equipment_ids = create_synthetic_portfolio(
            db,
            component_count=args.components,
            equipment_count=args.equipment,
            seed=args.seed,
            tag_prefix=args.tag_prefix,
            inspections_per_component=args.inspections_per_component,
        )
        print(
            f"Created {args.components:,} synthetic components across "
            f"{len(equipment_ids):,} equipment items, with "
            f"{args.inspections_per_component:,} inspections per component."
        )
        if not args.seed_only:
            count = run_portfolio_analysis(db, equipment_ids)
            print(f"Saved {count:,} internal-screening CML results.")
            circuit_count = run_corrosion_circuit_calculations(db, equipment_ids)
            print(f"Saved {circuit_count:,} deterministic corrosion summaries.")
    database_engine.dispose()


if __name__ == "__main__":
    main()
