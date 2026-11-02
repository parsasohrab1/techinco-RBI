"""Create a deterministic, isolated synthetic RBI portfolio and analyze it."""

import argparse
import os
import random
from datetime import date, datetime, timedelta

from sqlalchemy import func, insert, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app import models
from app.database import Base
from app.models_data_platform import DataQualityStatus
from app.services.analysis_orchestrator import analyze_equipment

QUALITY_SOURCE = "Synthetic demonstration data"
QUALITY_ACTOR = "synthetic-dataset-generator"
QUALITY_SOURCE_DATE = datetime(2026, 1, 1)


def create_synthetic_portfolio(
    db: Session,
    component_count: int = 10_000,
    equipment_count: int = 100,
    seed: int = 5812026,
    tag_prefix: str = "SYN-RBI",
) -> list[int]:
    if component_count < 1:
        raise ValueError("component_count must be positive.")
    if equipment_count < 1 or equipment_count > component_count:
        raise ValueError("equipment_count must be between 1 and component_count.")
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
    now = datetime.now()
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
        equipment_rows.append({
            "id": equipment_id,
            "tag_number": f"{tag_prefix}-{equipment_offset + 1:04d}",
            "equipment_type": "vessel",
            "material": rng.choice(("Carbon Steel", "Cr-Mo Steel", "Stainless Steel")),
            "design_pressure_kpa": float(rng.randrange(700, 4_001, 50)),
            "design_temperature_c": float(rng.randrange(40, 301, 5)),
            "inventory_m3": float(rng.randrange(10, 1_001, 10)),
            "fluid_type": rng.choice(("liquid", "gas")),
            "hazardous": rng.choice((True, True, False)),
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
                "inventory_m3",
                "fluid_type",
                "hazardous",
            )
        )

    db.execute(insert(models.Equipment), equipment_rows)
    component_rows = []
    cml_rows = []
    inspection_rows = []
    quality_rows = list(equipment_quality)
    component_index = 0
    recent_date = date.today() - timedelta(days=120)
    for equipment_offset, equipment_component_count in enumerate(
        components_per_equipment
    ):
        equipment_id = equipment_start + equipment_offset
        for _ in range(equipment_component_count):
            component_id = component_start + component_index
            cml_id = cml_start + component_index
            first_inspection_id = inspection_start + component_index * 2
            nominal = round(rng.uniform(10.0, 28.0), 2)
            minimum = round(rng.uniform(4.0, min(9.0, nominal - 2)), 2)
            initial_thickness = round(rng.uniform(minimum + 2, nominal), 2)
            remaining_thickness = round(
                rng.uniform(minimum + 0.05, initial_thickness - 0.2), 2
            )
            elapsed_years = rng.randint(2, 15)
            first_date = recent_date - timedelta(days=elapsed_years * 365)
            component_rows.append({
                "id": component_id,
                "equipment_id": equipment_id,
                "name": f"Component-{component_index + 1:05d}",
                "t_min_mm": minimum,
                "t_nominal_mm": nominal,
                "geometry_type": rng.choice(("shell", "head", "nozzle", "pipe")),
                "insulated": False,
                "operating_temperature_c": float(rng.randrange(20, 251, 5)),
            })
            cml_rows.append({
                "id": cml_id,
                "component_id": component_id,
                "name": f"CML-{component_index + 1:05d}",
                "surface_condition": rng.choice(("normal", "coated", "weathered")),
            })
            inspection_rows.extend((
                {
                    "id": first_inspection_id,
                    "cml_id": cml_id,
                    "inspection_date": first_date,
                    "thickness_mm": initial_thickness,
                    "method": "UT",
                    "effectiveness": rng.choice(("B", "C", "D")),
                    "inspector_id": 0,
                },
                {
                    "id": first_inspection_id + 1,
                    "cml_id": cml_id,
                    "inspection_date": recent_date,
                    "thickness_mm": remaining_thickness,
                    "method": "UT",
                    "effectiveness": rng.choice(("B", "C", "D")),
                    "inspector_id": 0,
                },
            ))
            for field_name in (
                "t_min_mm",
                "t_nominal_mm",
                "geometry_type",
                "damage_mechanism_review",
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
            for inspection_id in (first_inspection_id, first_inspection_id + 1):
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
            component_index += 1

    db.execute(insert(models.Component), component_rows)
    db.execute(insert(models.CML), cml_rows)
    db.execute(insert(models.InspectionRecord), inspection_rows)
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("RBI_SYNTHETIC_DATABASE_URL", "sqlite:///./rbi-synthetic.db"),
        help="Target database URL. Defaults to a separate local SQLite database.",
    )
    parser.add_argument("--components", type=int, default=10_000)
    parser.add_argument("--equipment", type=int, default=100)
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
        )
        print(
            f"Created {args.components:,} synthetic components across "
            f"{len(equipment_ids):,} equipment items."
        )
        if not args.seed_only:
            count = run_portfolio_analysis(db, equipment_ids)
            print(f"Saved {count:,} internal-screening CML results.")
    database_engine.dispose()


if __name__ == "__main__":
    main()
