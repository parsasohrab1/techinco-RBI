def test_cmms_mock_status(client):
    response = client.get("/integrations/cmms/status")

    assert response.status_code == 200
    assert response.json()["adapter"] == "sap-maximo-mock"
    assert response.json()["mode"] == "mock"
    assert response.json()["connected"] is True
    assert "no external CMMS" in response.json()["message"]


def test_high_risk_run_creates_idempotent_mock_work_order(client):
    equipment = client.post("/equipment", json={"tag_number": "V-CMMS"})
    assert equipment.status_code == 200

    component = client.post(
        f"/equipment/{equipment.json()['id']}/components",
        json={
            "name": "Shell",
            "t_min_mm": 8.0,
            "t_nominal_mm": 14.0,
            "cml_names": ["CML-HIGH"],
        },
    )
    assert component.status_code == 200

    analysis = client.post(f"/equipment/{equipment.json()['id']}/analyze")
    assert analysis.status_code == 200
    result = analysis.json()["results"][0]
    assert result["risk_level"] in {"High", "Critical"}

    url = f"/integrations/cmms/runs/{analysis.json()['run_id']}/work-orders"
    first_sync = client.post(url)
    assert first_sync.status_code == 200
    first_payload = first_sync.json()
    assert first_payload["eligible_count"] == 1
    assert first_payload["created_count"] == 1
    work_order = first_payload["work_orders"][0]
    assert work_order["asset_number"] == "V-CMMS"
    assert work_order["location"] == "Shell / CML-HIGH"
    assert work_order["risk_level"] == result["risk_level"]

    second_sync = client.post(url)
    assert second_sync.status_code == 200
    second_payload = second_sync.json()
    assert second_payload["eligible_count"] == 1
    assert second_payload["created_count"] == 0
    assert second_payload["work_orders"][0]["status"] == "already_exists"
    assert (
        second_payload["work_orders"][0]["work_order_id"]
        == first_payload["work_orders"][0]["work_order_id"]
    )


def test_cmms_rejects_unknown_analysis_run(client):
    response = client.post("/integrations/cmms/runs/999/work-orders")

    assert response.status_code == 404
    assert response.json()["detail"] == "Analysis run not found"
