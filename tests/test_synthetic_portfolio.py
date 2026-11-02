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
            component_count=4,
            equipment_count=2,
            seed=10,
        )

        assert run_portfolio_analysis(db, equipment_ids) == 4
        assert db.scalar(select(func.count()).select_from(models.Component)) == 4
        assert db.scalar(select(func.count()).select_from(models.CMLAnalysisResult)) == 4
        assert db.scalar(select(func.count()).select_from(models.AnalysisRun)) == 2
        assert db.scalar(
            select(func.count())
            .select_from(DataQualityStatus)
            .where(DataQualityStatus.quality == "verified")
        ) == 54
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
