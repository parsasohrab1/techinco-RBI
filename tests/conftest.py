import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.database import Base, get_db
from app.routers.cmms import get_cmms_adapter
from app.main import app
from app.services.cmms import MockMaximoClient


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with TestSession() as db:
        db.add_all([
            models.DamageMechanism(
                name="CUI",
                api571_ref="API 571 §4.3.1",
                category="corrosion",
            ),
            models.DamageMechanism(
                name="SCC",
                api571_ref="API 571 (general mechanism)",
                category="cracking",
            ),
        ])
        db.commit()

    def _get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    cmms_client = MockMaximoClient()
    app.dependency_overrides[get_cmms_adapter] = lambda: cmms_client
    yield TestClient(app)
    app.dependency_overrides.clear()
