"""Integrated laboratory checks for the TRL 5 screening loop."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base, get_db
from app.main import app
from app.routers.cmms import get_cmms_adapter
from app.services.cmms import MockMaximoClient
from app.services.incident_reference import IncidentReferenceError, load_incident_reference

RANK = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}


def _client() -> TestClient:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with session_factory() as db:
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
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    laboratory_cmms = MockMaximoClient()
    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_cmms_adapter] = lambda: laboratory_cmms
    return TestClient(app)


def _quality(client: TestClient, entity_type: str, entity_id: int, field_name: str) -> None:
    response = client.post(
        "/data-platform/quality-records",
        json={
            "entity_type": entity_type,
            "entity_id": entity_id,
            "field_name": field_name,
            "source": "Laboratory fixture",
            "source_date": datetime(2025, 1, 1).isoformat(),
            "actor": "laboratory-engineer",
            "quality": "verified",
        },
    )
    if response.status_code != 200:
        raise AssertionError(response.text)


def _criterion(code: str, name: str, passed: bool, detail: str) -> dict:
    return {"code": code, "name": name, "passed": passed, "detail": detail}


def _reference_criteria() -> list[dict]:
    try:
        summary = load_incident_reference()
    except IncidentReferenceError as error:
        return [_criterion("E6", "PHMSA accident extract", False, str(error))]

    span = summary["year_max"] - summary["year_min"]
    original = summary["source"]["original_url"]
    passed = (
        summary["accident_count"] >= 1000
        and span >= 10
        and 0 < summary["corrosion_share"] < 1
        and "phmsa.dot.gov" in original
        and summary["release_bbl"]["count"] > 0
        and summary["cost_current_usd"]["p50"] > 0
    )
    return [_criterion(
        "E6",
        "PHMSA accident extract",
        passed,
        (
            f"{summary['accident_count']} deduplicated accidents, "
            f"{summary['year_min']}–{summary['year_max']}, "
            f"corrosion share {summary['corrosion_share']:.3f}, "
            f"median release {summary['release_bbl']['p50']} bbl, "
            f"file as of {summary['source'].get('datafile_as_of')}."
        ),
    )]


def run_criteria() -> dict:
    criteria = _reference_criteria()
    client = _client()
    try:
        criteria.extend(_workflow(client))
    finally:
        app.dependency_overrides.clear()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "criteria": criteria,
        "passed": all(item["passed"] for item in criteria),
    }


def _workflow(client: TestClient) -> list[dict]:
    criteria = []
    equipment = client.post("/equipment", json={
        "tag_number": "PL-TRL5",
        "plant_unit": "Laboratory unit",
        "equipment_type": "piping",
    })
    component = client.post(
        f"/equipment/{equipment.json()['id']}/components",
        json={
            "name": "Line",
            "t_min_mm": 8.0,
            "t_nominal_mm": 14.0,
            "cml_names": ["CML-1"],
        },
    )
    equipment_id = equipment.json()["id"]
    component_id = component.json()["id"]
    cml_id = component.json()["cmls"][0]["id"]

    blocked = client.post(f"/equipment/{equipment_id}/analyze")
    criteria.append(_criterion(
        "E1",
        "Missing provenance blocks analysis",
        blocked.status_code == 409 and bool(blocked.json()["detail"]["missing_fields"]),
        f"HTTP {blocked.status_code}",
    ))
    if not criteria[-1]["passed"]:
        return criteria

    for field in ("material", "design_pressure_kpa", "inventory_m3", "fluid_type", "hazardous"):
        _quality(client, "equipment", equipment_id, field)
    for field in ("t_min_mm", "t_nominal_mm", "geometry_type", "damage_mechanism_review"):
        _quality(client, "component", component_id, field)
    _quality(client, "cml", cml_id, "inspection_history")

    first = client.post(f"/equipment/{equipment_id}/analyze")
    first_body = first.json()
    first_result = first_body["results"][0] if first.status_code == 200 else {}
    criteria.append(_criterion(
        "E2",
        "Complete provenance produces a screening result",
        (
            first.status_code == 200
            and first_result.get("risk_level") in {"High", "Critical"}
            and first_result.get("details", {}).get("engine", {}).get("compliance_status")
            == "internal_screening"
        ),
        f"HTTP {first.status_code}, risk {first_result.get('risk_level')}",
    ))
    if not criteria[-1]["passed"]:
        return criteria

    replay = client.get(f"/audit/runs/{first_body['run_id']}/replay")
    replay_body = replay.json()
    criteria.append(_criterion(
        "E3",
        "Independent replay matches the stored result",
        replay.status_code == 200 and replay_body.get("matched") is True,
        f"HTTP {replay.status_code}, differences "
        f"{[item.get('differences') for item in replay_body.get('results', [])]}",
    ))
    repeated = client.get(f"/audit/runs/{first_body['run_id']}/replay")
    criteria.append(_criterion(
        "E9",
        "Replay is repeatable",
        (
            repeated.status_code == 200
            and repeated.json().get("results") == replay_body.get("results")
        ),
        "Second replay compared with the first.",
    ))

    sync = client.post(f"/integrations/cmms/runs/{first_body['run_id']}/work-orders")
    sync_body = sync.json() if sync.status_code == 200 else {}
    work_order = (sync_body.get("work_orders") or [{}])[0]
    criteria.append(_criterion(
        "E4",
        "High screening result opens one laboratory work order",
        sync.status_code == 200 and sync_body.get("created_count") == 1,
        f"HTTP {sync.status_code}, created {sync_body.get('created_count')}",
    ))
    if not criteria[-1]["passed"]:
        return criteria

    completed = client.post(
        f"/integrations/cmms/work-orders/{work_order['external_reference']}/complete",
        json={
            "inspection_date": "2024-06-01",
            "thickness_mm": 12.4,
            "effectiveness": "B",
        },
    )
    still_blocked = client.post(f"/equipment/{equipment_id}/analyze")
    feedback_gate = (
        completed.status_code == 200
        and still_blocked.status_code == 409
        and any(
            "thickness_mm" in field
            for field in still_blocked.json()["detail"]["missing_fields"]
        )
    )
    criteria.append(_criterion(
        "E5",
        "Field reading is stored and stays blocked until quality evidence exists",
        feedback_gate,
        (
            f"completion HTTP {completed.status_code}, "
            f"reanalysis HTTP {still_blocked.status_code}"
        ),
    ))
    if not criteria[-1]["passed"]:
        return criteria

    inspection_id = completed.json()["inspection_id"]
    for field in ("inspection_date", "thickness_mm", "effectiveness"):
        _quality(client, "inspection_record", inspection_id, field)
    second = client.post(f"/equipment/{equipment_id}/analyze")
    second_body = second.json()
    second_result = second_body["results"][0]
    rank_dropped = RANK[second_result["risk_level"]] < RANK[first_result["risk_level"]]
    second_replay = client.get(f"/audit/runs/{second_body['run_id']}/replay")
    criteria.append(_criterion(
        "E5b",
        "Verified field reading changes the next screen and still replays",
        (
            second.status_code == 200
            and rank_dropped
            and second_result["details"]["pof"]["details"]["inspection_count"] == 1
            and second_replay.json().get("matched") is True
        ),
        (
            f"{first_result['risk_level']} -> {second_result['risk_level']}, "
            f"replay matched {second_replay.json().get('matched')}"
        ),
    ))

    dashboard = client.get("/reports/dashboard")
    page = dashboard.text
    criteria.append(_criterion(
        "E7",
        "Dashboard shows the laboratory asset and the PHMSA context",
        (
            dashboard.status_code == 200
            and "PL-TRL5" in page
            and 'data-reference="phmsa"' in page
            and "PHMSA hazardous-liquid accidents" in page
            and "Corrosion cause" in page
            and "do not change probability" in page
        ),
        f"HTTP {dashboard.status_code}",
    ))
    criteria.append(_criterion(
        "E8",
        "Screen remains an internal, nonconforming calculation",
        (
            first_result["details"]["engine"]["compliance_status"] == "internal_screening"
            and second_result["details"]["engine"]["compliance_status"] == "internal_screening"
            and "No API RP" in client.get(
                f"/audit/runs/{second_body['run_id']}/reconstruction"
            ).json()["compliance_claim"]
        ),
        "Both runs stay on internal_screening.",
    ))
    return criteria


def render_report(report: dict) -> str:
    lines = [
        "# TRL 5 validation report",
        "",
        f"Generated {report['generated_at']}.",
        "",
        "The integrated screening loop was exercised in a laboratory client with an "
        "in-memory database. The accident context is the committed PHMSA "
        "hazardous-liquid summary. A failing criterion fails this run.",
        "",
        "| Code | Criterion | Result | Detail |",
        "| --- | --- | --- | --- |",
    ]
    for item in report["criteria"]:
        result = "pass" if item["passed"] else "fail"
        detail = item["detail"].replace("|", "/")
        lines.append(f"| {item['code']} | {item['name']} | {result} | {detail} |")
    lines.extend([
        "",
        f"Overall: {'pass' if report['passed'] else 'fail'}.",
        "",
        "This run does not validate API RP 580 or API RP 581, and it does not use "
        "plant inspection history.",
        "",
    ])
    return "\n".join(lines)
