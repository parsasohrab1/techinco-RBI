def test_corrosion_calculation_quality_snapshot_and_dashboard(client):
    equipment_response = client.post(
        "/equipment",
        json={
            "tag_number": "V-COR-1",
            "plant_unit": "Gas separation plant",
            "hazardous": True,
        },
    )
    assert equipment_response.status_code == 200, equipment_response.text
    equipment_id = equipment_response.json()["id"]

    component_response = client.post(
        f"/equipment/{equipment_id}/components",
        json={
            "name": "Shell",
            "t_min_mm": 5.0,
            "t_nominal_mm": 12.0,
            "insulated": False,
            "cml_names": ["CML-A"],
        },
    )
    assert component_response.status_code == 200, component_response.text
    component = component_response.json()
    component_id = component["id"]
    cml_id = component["cmls"][0]["id"]

    circuit_response = client.post(
        f"/equipment/{equipment_id}/circuits",
        json={"circuit_code": "C-01"},
    )
    assert circuit_response.status_code == 201, circuit_response.text
    circuit = circuit_response.json()
    assert circuit["calculation_method"] == 2
    circuit_id = circuit["id"]

    assignment_response = client.post(
        f"/circuits/{circuit_id}/components/{component_id}"
    )
    assert assignment_response.status_code == 200, assignment_response.text

    measurement_set_response = client.post(
        f"/circuits/{circuit_id}/measurement-sets",
        json={
            "name": "2024 annual survey",
            "measurement_date": "2024-01-01",
            "technician": "Inspector A",
        },
    )
    assert measurement_set_response.status_code == 201, measurement_set_response.text
    measurement_set_id = measurement_set_response.json()["id"]
    pending_dashboard = client.get("/reports/dashboard")
    assert pending_dashboard.status_code == 200, pending_dashboard.text
    assert "Not calculated" in pending_dashboard.text

    for measurement in [
        {"inspection_date": "2020-01-01", "thickness_mm": 10.0},
        {"inspection_date": "2022-01-01", "thickness_mm": 9.0},
    ]:
        response = client.post(
            f"/cml/{cml_id}/inspections",
            json={**measurement, "quality_indicator": "verified"},
        )
        assert response.status_code == 200, response.text

    latest_measurement = client.post(
        f"/cml/{cml_id}/inspections",
        json={
            "inspection_date": "2024-01-01",
            "thickness_mm": 8.0,
            "quality_indicator": "verified",
            "measurement_set_id": measurement_set_id,
        },
    )
    assert latest_measurement.status_code == 200, latest_measurement.text

    calculation_response = client.post(
        f"/circuits/{circuit_id}/calculate",
        json={"measurement_set_id": measurement_set_id, "actor": "engineer"},
    )
    assert calculation_response.status_code == 201, calculation_response.text
    calculation = calculation_response.json()
    result = calculation["results"]["cml_results"][0]
    assert result["long_rate_mm_yr"] == 0.5
    assert result["governing_rate_basis"] == "short"
    assert result["remaining_corrosion_allowance_mm"] == 3.0
    assert 5.9 < result["remaining_life_years"] < 6.1
    assert calculation["results"]["circuit"]["driving_cml"] == "CML-A"
    assert calculation["results"]["circuit"]["tif_source"] == "reference_interval_factor"
    summary_id = calculation["id"]

    late_reading = client.post(
        f"/cml/{cml_id}/inspections",
        json={
            "inspection_date": "2025-01-01",
            "thickness_mm": 7.5,
            "quality_indicator": "good",
        },
    )
    assert late_reading.status_code == 200, late_reading.text
    stale_approval = client.post(
        f"/circuits/calculations/{summary_id}/approve",
        json={"actor": "reviewer", "comment": "Reviewed"},
    )
    assert stale_approval.status_code == 409
    assert "inputs changed" in stale_approval.json()["detail"]

    outlier = client.post(
        f"/cml/{cml_id}/inspections",
        json={
            "inspection_date": "2026-01-01",
            "thickness_mm": 10.0,
            "quality_indicator": "good",
        },
    )
    assert outlier.status_code == 200, outlier.text
    recalculation = client.post(
        f"/circuits/{circuit_id}/calculate",
        json={"actor": "engineer"},
    )
    assert recalculation.status_code == 201, recalculation.text
    cml_result = recalculation.json()["results"]["cml_results"][0]
    assert cml_result["latest_date"] == "2025-01-01"
    assert 0.45 < cml_result["linear_regression_rate_mm_yr"] < 0.55
    assert "growth_error" in cml_result["quality_flags"][-1]["codes"]
    approval = client.post(
        f"/circuits/calculations/{recalculation.json()['id']}/approve",
        json={"actor": "reviewer", "comment": "Reviewed"},
    )
    assert approval.status_code == 200, approval.text
    assert approval.json()["status"] == "approved"
    assert approval.json()["approved_by"] == "reviewer"

    dashboard = client.get("/reports/dashboard")
    assert dashboard.status_code == 200, dashboard.text
    assert 'data-workspace="corrosion-circuits"' in dashboard.text
    assert "Latest circuit calculation register" in dashboard.text
    assert "V-COR-1" in dashboard.text
    assert "C-01" in dashboard.text
