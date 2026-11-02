def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_risk_dashboard_empty_state(client):
    r = client.get("/reports/dashboard")

    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "No assessments have been recorded" in r.text
    assert "synthetic demonstration portfolio" in r.text
    assert "Risk matrix" in r.text
    assert 'id="assessment-search"' not in r.text


def test_full_workflow(client, record_quality):
    # Create equipment
    r = client.post("/equipment", json={
        "tag_number": "V-900",
        "plant_unit": "Gas separation plant",
        "hazardous": True,
    })
    assert r.status_code == 200
    assert r.json()["plant_unit"] == "Gas separation plant"
    eq_id = r.json()["id"]

    # Add component with CML
    r = client.post(f"/equipment/{eq_id}/components", json={
        "name": "Shell", "t_min_mm": 8.0, "t_nominal_mm": 14.0,
        "insulated": True, "operating_temperature_c": None,
        "cml_names": ["CML-A"],
    })
    assert r.status_code == 200
    assert r.json()["insulated"] is True
    assert r.json()["operating_temperature_c"] is None
    component_id = r.json()["id"]
    cml_id = r.json()["cmls"][0]["id"]

    cui = next(
        mechanism for mechanism in client.get("/damage-mechanisms").json()
        if mechanism["name"] == "CUI"
    )
    r = client.post(
        f"/damage-mechanisms/components/{component_id}/assign",
        json={"dm_id": cui["id"], "status": "active"},
    )
    assert r.status_code == 200
    cui_link_id = r.json()["id"]
    mechanism_event = client.get(
        "/data-platform/events",
        params={
            "entity_type": "component_damage_mechanism",
            "entity_id": cui_link_id,
        },
    )
    assert mechanism_event.status_code == 200
    assert mechanism_event.json()[0]["event_type"] == "damage_mechanism_assigned"
    scc = next(
        mechanism for mechanism in client.get("/damage-mechanisms").json()
        if mechanism["name"] == "SCC"
    )
    r = client.post(
        f"/damage-mechanisms/components/{component_id}/assign",
        json={
            "dm_id": scc["id"],
            "status": "active",
            "assessment_data": {
                "susceptible_material": True,
                "environment_present": True,
                "tensile_stress_present": True,
            },
        },
    )
    assert r.status_code == 200
    scc_link_id = r.json()["id"]

    # Add inspections
    inspection_ids = []
    for d, t in [("2020-05-01", 12.6), ("2023-06-01", 11.9)]:
        r = client.post(f"/cml/{cml_id}/inspections", json={
            "inspection_date": d, "thickness_mm": t, "effectiveness": "B",
        })
        assert r.status_code == 200
        inspection_ids.append(r.json()["id"])
        events = client.get(
            "/data-platform/events",
            params={
                "entity_type": "inspection_record",
                "entity_id": r.json()["id"],
            },
        )
        assert events.status_code == 200
        assert events.json()[0]["event_type"] == "inspection_recorded"

    # Missing provenance blocks calculation instead of silently using unverified inputs.
    r = client.post(f"/equipment/{eq_id}/analyze")
    assert r.status_code == 409
    assert r.json()["detail"]["missing_fields"]

    for field in ("material", "design_pressure_kpa", "fluid_type", "hazardous"):
        record_quality(client, "equipment", eq_id, field)
    assumption = client.post(
        "/data-platform/assumptions",
        json={
            "entity_type": "equipment",
            "entity_id": eq_id,
            "field_name": "inventory_m3",
            "assumed_value": "200",
            "basis": "Approved test assumption",
            "actor": "engineer",
        },
    )
    assert assumption.status_code == 200
    approved = client.post(
        f"/data-platform/assumptions/{assumption.json()['id']}/approve",
        json={"actor": "approver"},
    )
    assert approved.status_code == 200
    record_quality(client, "equipment", eq_id, "inventory_m3", quality="assumed")
    temperature_assumption = client.post(
        "/data-platform/assumptions",
        json={
            "entity_type": "component",
            "entity_id": component_id,
            "field_name": "operating_temperature_c",
            "assumed_value": "80",
            "basis": "Approved test assumption",
            "actor": "engineer",
        },
    )
    assert temperature_assumption.status_code == 200
    approved_temperature = client.post(
        f"/data-platform/assumptions/{temperature_assumption.json()['id']}/approve",
        json={"actor": "approver"},
    )
    assert approved_temperature.status_code == 200
    for field in (
        "t_min_mm", "t_nominal_mm", "geometry_type", "insulated",
        "damage_mechanism_review",
    ):
        record_quality(client, "component", component_id, field)
    record_quality(
        client,
        "component",
        component_id,
        "operating_temperature_c",
        quality="assumed",
    )
    record_quality(client, "cml", cml_id, "inspection_history")
    for inspection_id in inspection_ids:
        for field in ("inspection_date", "thickness_mm", "effectiveness"):
            record_quality(client, "inspection_record", inspection_id, field)
    for link_id in (cui_link_id, scc_link_id):
        record_quality(
            client,
            "component_damage_mechanism",
            link_id,
            "status",
        )
        record_quality(
            client,
            "component_damage_mechanism",
            link_id,
            "assessment_data",
        )

    # Run analysis with complete provenance.
    r = client.post(f"/equipment/{eq_id}/analyze")
    assert r.status_code == 200
    data = r.json()
    assert data["tag_number"] == "V-900"
    assert len(data["results"]) == 1
    assert data["results"][0]["risk_level"] in {"Low", "Medium", "High", "Critical"}
    assert data["results"][0]["details"]["cof"]["details"]["environmental"] == 3
    assert data["results"][0]["details"]["engine"]["compliance_status"] == "internal_screening"
    assert data["results"][0]["details"]["inputs"]["equipment"]["inventory_m3"] == 200.0
    reconstruction = client.get(
        f"/audit/runs/{data['run_id']}/reconstruction"
    )
    assert reconstruction.status_code == 200
    assert reconstruction.json()["compliance_claim"].startswith("No API RP")
    assert reconstruction.json()["chain_of_custody"][0]["assumptions"][0]["assumed_value"] == "200"
    dashboard = client.get("/reports/dashboard")
    assert dashboard.status_code == 200
    assert "V-900" in dashboard.text
    assert "Asset assessment register" in dashboard.text
    assert 'data-risk="' in dashboard.text
    assert "Portfolio snapshot" in dashboard.text
    assert "1 shown · 1 total" in dashboard.text
    assert "Gas separation plant" in dashboard.text
    assert "Risk matrix" in dashboard.text
    assert client.get("/reports/dashboard?page=0").status_code == 422
    assert client.get("/reports/dashboard?page_size=101").status_code == 422
    mechanism_assessments = data["results"][0]["details"]["damage_mechanisms"]
    cui_assessment = next(
        item for item in mechanism_assessments if item["mechanism"] == "CUI"
    )
    assert cui_assessment["mechanism"] == "CUI"
    assert cui_assessment["status"] == "susceptible"
    assert cui_assessment["details"]["assessment_type"] == "susceptibility_screen_only"
    scc_assessment = next(
        item for item in mechanism_assessments if item["mechanism"] == "SCC"
    )
    assert scc_assessment["status"] == "susceptible"
    assert scc_assessment["details"]["assessment_type"] == "generic_user_input_checklist_only"
    events = client.get(
        "/data-platform/events",
        params={"entity_type": "equipment", "entity_id": eq_id},
    ).json()
    analysis_event = next(
        event for event in events if event["event_type"] == "analysis_run_created"
    )
    assert analysis_event["payload"]["input_snapshot"]["equipment"]["inventory_m3"] == 200.0
    assert analysis_event["payload"]["compliance_status"] == (
        "INTERNAL SCREENING ONLY — no API conformity claim"
    )

    # CSV worklist
    run_id = data["run_id"]
    r = client.get(f"/reports/run/{run_id}/worklist.csv")
    assert r.status_code == 200
    assert "Tag" in r.text and "V-900" in r.text

    latest_run_response = client.post(f"/equipment/{eq_id}/analyze")
    assert latest_run_response.status_code == 200
    latest_run_id = latest_run_response.json()["run_id"]

    dashboard = client.get("/reports/dashboard")
    assert dashboard.status_code == 200
    assert "Asset assessment register" in dashboard.text
    assert "V-900" in dashboard.text
    assert "CML-A" in dashboard.text
    assert f"/reports/run/{latest_run_id}/worklist.csv" in dashboard.text
    assert f"/reports/run/{run_id}/worklist.csv" not in dashboard.text

    record_quality(client, "equipment", eq_id, "inventory_m3", quality="unverified")
    blocked = client.post(f"/equipment/{eq_id}/analyze")
    assert blocked.status_code == 409
    assert f"equipment.{eq_id}.inventory_m3" in blocked.json()["detail"]["missing_fields"]
