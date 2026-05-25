from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from conftest import load_example


example = load_example("fastapi_app_routers_example", "01-fastapi-app-routers/fastapi_example.py")


def setup_function() -> None:
    example._fake_db.clear()


def test_health_readiness_and_server_header_are_stable() -> None:
    client = TestClient(example.app)

    assert client.get("/healthz").json() == {"status": "ok"}
    ready = client.get("/readyz")

    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}
    assert ready.headers["server"] == example.SERVER_NAME


def test_item_crud_flow_preserves_created_at_and_supports_pagination() -> None:
    client = TestClient(example.app)

    first = client.post(
        "/v1/items/",
        json={"name": "Widget", "price": "9.99", "category": "hardware"},
    )
    second = client.post(
        "/v1/items/",
        json={"name": "Service Plan", "price": "19.50", "category": "service"},
    )
    assert first.status_code == 201
    assert second.status_code == 201

    item_id = first.json()["id"]
    created_at = first.json()["created_at"]

    listed = client.get("/v1/items/", params={"limit": 1, "offset": 1})
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["name"] == "Service Plan"

    patched = client.patch(f"/v1/items/{item_id}", json={"price": "12.34"})
    assert patched.status_code == 200
    assert patched.json()["name"] == "Widget"
    assert patched.json()["price"] == "12.34"
    assert patched.json()["created_at"] == created_at

    replaced = client.put(
        f"/v1/items/{item_id}",
        json={"name": "Widget Pro", "price": "29.99", "category": "software"},
    )
    assert replaced.status_code == 200
    assert replaced.json()["name"] == "Widget Pro"
    assert replaced.json()["created_at"] == created_at

    deleted = client.delete(f"/v1/items/{item_id}")
    assert deleted.status_code == 204
    assert client.get(f"/v1/items/{item_id}").status_code == 404


def test_item_validation_and_route_errors_use_structured_envelopes() -> None:
    client = TestClient(example.app)

    invalid = client.post("/v1/items/", json={"name": "", "price": "-1.00", "category": "bad"})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"

    missing = client.get(f"/v1/items/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["error"] == {"code": "NOT_FOUND", "message": "Item not found"}

    route_miss = client.get("/v1/nope")
    assert route_miss.status_code == 404
    assert route_miss.json()["error"]["code"] == "ROUTE_NOT_FOUND"


def test_item_models_validate_domain_constraints() -> None:
    item = example.ItemCreate(name="A", price=Decimal("1.23"), category="hardware")
    update = example.ItemUpdate(price=Decimal("2.34"))

    assert item.model_dump()["category"] == "hardware"
    assert update.model_dump(exclude_unset=True) == {"price": Decimal("2.34")}
