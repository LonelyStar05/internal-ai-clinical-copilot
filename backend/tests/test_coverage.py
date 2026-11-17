from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
AN = {"Authorization": "Bearer demo-bs-an"}
BINH = {"Authorization": "Bearer demo-bs-binh"}


def test_coverage_catalog_and_grounded_result():
    catalog = client.get("/api/coverage/services", headers=AN)
    assert catalog.status_code == 200
    assert {item["code"] for item in catalog.json()} >= {"CRP", "HBA1C", "CREAT", "CXR"}

    response = client.post(
        "/api/patients/p001/coverage/check",
        headers=AN,
        json={"service_codes": ["CRP", "HBA1C"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["patient_id"] == "p001" and len(body["results"]) == 2
    assert sum(body["counts"].values()) == 2
    assert all(result["criteria"] and result["basis"] for result in body["results"])
    assert "không quyết định" in body["disclaimer"].lower()


def test_coverage_access_control_and_unknown_service():
    assert client.post(
        "/api/patients/p001/coverage/check",
        json={"service_codes": ["CRP"]},
    ).status_code == 401
    assert client.post(
        "/api/patients/p001/coverage/check",
        headers=BINH,
        json={"service_codes": ["CRP"]},
    ).status_code == 403
    response = client.post(
        "/api/patients/p001/coverage/check",
        headers=AN,
        json={"service_codes": ["NOT-A-SERVICE"]},
    )
    assert response.status_code == 422 and "chưa có luật" in response.json()["detail"].lower()
