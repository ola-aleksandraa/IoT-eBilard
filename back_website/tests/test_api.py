import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as client:
        yield client


def assert_numerical(body):
    forbidden = {"image", "images", "overlay", "rectified", "mask", "color", "pattern"}
    def visit(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value), value.keys()
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, str):
            assert not value.startswith("data:image/")
    visit(body)


def test_docs_and_contract_expose_only_website_routes(client):
    assert client.get("/", follow_redirects=False).headers["location"] == "/docs"
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert client.get("/health").json() == {"status": "ok", "service": "website", "version": "1.0.0"}
    schema = client.get("/openapi.json").json()
    assert set(schema["paths"]) == {"/health", "/api/v1/settings", "/api/v1/categories",
                                    "/api/v1/shots", "/api/v1/shots/predict", "/api/v1/shots/simulate"}
    for path, operations in schema["paths"].items():
        for operation in operations.values():
            assert set(operation["responses"]["200"]["content"]) == {"application/json"}, path


@pytest.mark.parametrize("path", ["images/detect", "images/calibrate", "camera", "camera/detect", "camera/calibrate"])
def test_recognition_routes_are_served_by_the_pi_not_the_website(client, path):
    assert client.get(f"/api/v1/{path}").status_code == 404
    assert client.post(f"/api/v1/{path}").status_code == 404


def test_categories_and_defaults_have_no_presentation_dependency(client):
    assert client.get("/api/v1/settings").json() == {
        "table_ratio": 2, "ball_radius_ratio": 0.026, "cloth_hue": None,
        "hue_tolerance": 16, "saturation_min": 55, "split_touching": True,
    }
    response = client.get("/api/v1/categories")
    assert {item["kind"] for item in response.json()} == {"cue", "eight", "solid", "striped", "unknown"}
    assert_numerical(response.json())
