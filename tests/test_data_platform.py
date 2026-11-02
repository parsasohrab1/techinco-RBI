def test_assumed_quality_requires_an_approved_assumption(client):
    equipment = client.post("/equipment", json={"tag_number": "V-ASSUMED"})
    assert equipment.status_code == 200
    equipment_id = equipment.json()["id"]

    assumption = client.post(
        "/data-platform/assumptions",
        json={
            "entity_type": "equipment",
            "entity_id": equipment_id,
            "field_name": "inventory_m3",
            "assumed_value": "12",
            "basis": "Approved engineering estimate",
            "actor": "engineer",
        },
    )
    assert assumption.status_code == 200
    assumption_id = assumption.json()["id"]
    quality_payload = {
        "entity_type": "equipment",
        "entity_id": equipment_id,
        "field_name": "inventory_m3",
        "source": "Engineering assumption",
        "source_date": "2025-01-01T00:00:00",
        "actor": "engineer",
        "quality": "assumed",
    }

    blocked = client.post("/data-platform/quality-records", json=quality_payload)
    assert blocked.status_code == 409

    approved = client.post(
        f"/data-platform/assumptions/{assumption_id}/approve",
        json={"actor": "approver"},
    )
    assert approved.status_code == 200
    assert approved.json()["approved_by"] == "approver"
    accepted = client.post("/data-platform/quality-records", json=quality_payload)
    assert accepted.status_code == 200
    assert accepted.json()["recorded_by"] == "engineer"
    deactivated = client.post(
        f"/data-platform/assumptions/{assumption_id}/deactivate",
        json={"actor": "approver"},
    )
    assert deactivated.status_code == 200
    rejected = client.post("/data-platform/quality-records", json=quality_payload)
    assert rejected.status_code == 409


def test_workflow_records_events_and_prevents_final_decision_changes(client):
    equipment = client.post("/equipment", json={"tag_number": "V-WORKFLOW"})
    equipment_id = equipment.json()["id"]
    submitted = client.post(
        "/data-platform/workflows",
        json={
            "entity_type": "equipment",
            "entity_id": equipment_id,
            "actor": "engineer",
        },
    )
    assert submitted.status_code == 200
    workflow_id = submitted.json()["id"]
    assert submitted.json()["stage"] == "pending"

    approved = client.post(
        f"/data-platform/workflows/{workflow_id}/decision",
        json={"decision": "approved", "actor": "approver", "comment": "Reviewed"},
    )
    assert approved.status_code == 200
    rejected_change = client.post(
        f"/data-platform/workflows/{workflow_id}/decision",
        json={"decision": "rejected", "actor": "approver"},
    )
    assert rejected_change.status_code == 409

    events = client.get(
        "/data-platform/events",
        params={"entity_type": "equipment", "entity_id": equipment_id},
    )
    assert events.status_code == 200
    assert [event["event_type"] for event in events.json()] == [
        "workflow_approved",
        "workflow_submitted",
    ]


def test_equipment_scope_rejects_unsupported_types(client):
    response = client.post(
        "/equipment",
        json={"tag_number": "X-OUT-OF-SCOPE", "equipment_type": "turbine"},
    )
    assert response.status_code == 422
