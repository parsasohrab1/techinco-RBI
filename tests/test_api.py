def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_risk_dashboard_empty_state(client):
    r = client.get("/reports/dashboard")

    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "No analysis results yet" in r.text


def test_full_workflow(client):
    # Create equipment
    r = client.post("/equipment", json={"tag_number": "V-900", "hazardous": True})
    assert r.status_code == 200
    eq_id = r.json()["id"]

    # Add component with CML
    r = client.post(f"/equipment/{eq_id}/components", json={
        "name": "Shell", "t_min_mm": 8.0, "t_nominal_mm": 14.0,
        "insulated": True, "operating_temperature_c": 80.0,
        "cml_names": ["CML-A"],
    })
    assert r.status_code == 200
    assert r.json()["insulated"] is True
    assert r.json()["operating_temperature_c"] == 80.0
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

    # Add inspections
    for d, t in [("2020-05-01", 12.6), ("2023-06-01", 11.9)]:
        r = client.post(f"/cml/{cml_id}/inspections", json={
            "inspection_date": d, "thickness_mm": t, "effectiveness": "B",
        })
        assert r.status_code == 200

    # Run analysis
    r = client.post(f"/equipment/{eq_id}/analyze")
    assert r.status_code == 200
    data = r.json()
    assert data["tag_number"] == "V-900"
    assert len(data["results"]) == 1
    assert data["results"][0]["risk_level"] in {"Low", "Medium", "High", "Critical"}
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
    assert "Latest CML assessments" in dashboard.text
    assert "V-900" in dashboard.text
    assert "CML-A" in dashboard.text
    assert f"/reports/run/{latest_run_id}/worklist.csv" in dashboard.text
    assert f"/reports/run/{run_id}/worklist.csv" not in dashboard.text
