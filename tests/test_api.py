def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_full_workflow(client):
    # Create equipment
    r = client.post("/equipment", json={"tag_number": "V-900", "hazardous": True})
    assert r.status_code == 200
    eq_id = r.json()["id"]

    # Add component with CML
    r = client.post(f"/equipment/{eq_id}/components", json={
        "name": "Shell", "t_min_mm": 8.0, "t_nominal_mm": 14.0,
        "cml_names": ["CML-A"],
    })
    assert r.status_code == 200
    cml_id = r.json()["cmls"][0]["id"]

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

    # CSV worklist
    run_id = data["run_id"]
    r = client.get(f"/reports/run/{run_id}/worklist.csv")
    assert r.status_code == 200
    assert "Tag" in r.text and "V-900" in r.text
