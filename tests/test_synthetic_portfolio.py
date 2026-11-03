import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base
from app.models_data_platform import DataQualityStatus
from scripts.generate_synthetic_portfolio import (
    create_synthetic_portfolio,
    run_portfolio_analysis,
)


def test_synthetic_portfolio_is_traceable_and_runs_through_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine, autoflush=False, expire_on_commit=False) as db:
        equipment_ids = create_synthetic_portfolio(
            db,
            component_count=10,
            equipment_count=5,
            seed=10,
        )

        assert run_portfolio_analysis(db, equipment_ids) == 10
        assert db.scalar(select(func.count()).select_from(models.Component)) == 10
        assert db.scalar(select(func.count()).select_from(models.InspectionRecord)) == 500
        inspection_counts = db.execute(
            select(
                models.InspectionRecord.cml_id,
                func.count(models.InspectionRecord.id),
            ).group_by(models.InspectionRecord.cml_id)
        ).all()
        assert len(inspection_counts) == 10
        assert {count for _, count in inspection_counts} == {50}
        assert db.scalar(select(func.count()).select_from(models.CMLAnalysisResult)) == 10
        assert db.scalar(select(func.count()).select_from(models.AnalysisRun)) == 5
        assert db.scalar(
            select(func.count(func.distinct(models.Equipment.equipment_type)))
        ) >= 4
        assert db.scalar(
            select(func.count(func.distinct(models.Equipment.fluid_type)))
        ) == 2
        assert db.scalar(
            select(func.count(func.distinct(models.InspectionRecord.method)))
        ) >= 3
        assert {
            effectiveness
            for (effectiveness,) in db.execute(
                select(models.InspectionRecord.effectiveness).distinct()
            )
        } == {"A", "B", "C", "D", "E"}
        assert db.scalar(select(func.min(models.Equipment.design_pressure_kpa))) < db.scalar(
            select(func.max(models.Equipment.design_pressure_kpa))
        )
        mechanism_link_count = db.scalar(
            select(func.count()).select_from(models.ComponentDamageMechanism)
        )
        assert db.scalar(
            select(func.count())
            .select_from(DataQualityStatus)
            .where(DataQualityStatus.quality == "verified")
        ) == 6 * 5 + (7 + 3 * 50) * 10 + 2 * mechanism_link_count
        assert db.scalar(
            select(func.count())
            .select_from(models.Equipment)
            .where(models.Equipment.plant_unit != "Unassigned")
        ) == 5
        assert db.scalar(
            select(func.count())
            .select_from(DataQualityStatus)
            .where(
                DataQualityStatus.note.contains(
                    "not verified plant data"
                )
            )
        ) > 0

        with pytest.raises(ValueError, match="already exists"):
            create_synthetic_portfolio(
                db,
                component_count=1,
                equipment_count=1,
                seed=10,
            )

    engine.dispose()
