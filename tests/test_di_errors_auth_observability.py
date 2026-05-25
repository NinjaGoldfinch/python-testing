from __future__ import annotations

import logging
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from conftest import load_example


di_example = load_example("dependency_injection_example", "05-dependency-injection/dependency_injection_example.py")
error_example = load_example("error_handling_example", "06-error-handling/error_handling_example.py")
auth_example = load_example("auth_permissions_example", "07-auth-permissions/auth_permissions_example.py")
tests_example = load_example("tests_reference_example", "08-tests/tests_example.py")
observability_example = load_example(
    "observability_deployment_example",
    "09-observability-deployment/observability_deployment_example.py",
)


def test_dependency_overrides_isolate_settings_and_repository() -> None:
    repo = di_example.InMemoryNoteRepository()

    async def override_settings() -> di_example.Settings:
        return di_example.Settings(app_name="Test API", api_key="test-key", allow_debug_routes=False)

    async def override_repo() -> di_example.InMemoryNoteRepository:
        return repo

    di_example.app.dependency_overrides[di_example.get_settings] = override_settings
    di_example.app.dependency_overrides[di_example.get_note_repository] = override_repo
    try:
        client = TestClient(di_example.app)
        assert client.get("/healthz").json()["app"] == "Test API"
        assert client.get("/v1/notes/").status_code == 401

        headers = {"X-API-Key": "test-key"}
        created = client.post("/v1/notes/", json={"text": "Injected"}, headers=headers)
        assert created.status_code == 201
        assert client.get("/v1/notes/", headers=headers).json()[0]["text"] == "Injected"
    finally:
        di_example.app.dependency_overrides.clear()


def test_error_handlers_cover_validation_domain_http_route_and_unhandled_errors() -> None:
    error_example._widgets.clear()
    client = TestClient(error_example.app, raise_server_exceptions=False)

    invalid = client.post("/v1/widgets/", json={"name": ""})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["details"][0]["field"] == "body -> name"

    created = client.post("/v1/widgets/", json={"name": "alpha"})
    assert created.status_code == 201
    widget_id = created.json()["id"]

    duplicate = client.post("/v1/widgets/", json={"name": "alpha"})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DUPLICATE_WIDGET"

    assert client.get(f"/v1/widgets/{widget_id}").status_code == 200
    assert client.get(f"/v1/widgets/{uuid4()}").json()["error"]["code"] == "WIDGET_NOT_FOUND"
    assert client.get("/v1/http-error").json()["error"]["code"] == "BAD_REQUEST"
    assert client.get("/missing").json()["error"]["code"] == "ROUTE_NOT_FOUND"


def test_error_body_omits_empty_details() -> None:
    assert error_example.error_body("X", "Message") == {"error": {"code": "X", "message": "Message"}}
    assert error_example.error_body("X", "Message", [{"field": "body"}])["error"]["details"]


def test_auth_permissions_allow_owner_and_admin_but_block_others() -> None:
    auth_example._documents.clear()
    client = TestClient(auth_example.app)
    user_headers = {"Authorization": "Bearer user-token"}
    admin_headers = {"Authorization": "Bearer admin-token"}
    outsider = auth_example.Principal(uuid4(), auth_example.Role.USER)

    unauthorized = client.get("/v1/documents/")
    assert unauthorized.status_code == 401

    created = client.post(
        "/v1/documents/",
        json={"title": "Runbook", "body": "Ops notes"},
        headers=user_headers,
    )
    assert created.status_code == 201
    document = auth_example.DocumentRead(**created.json())

    assert auth_example.can_view(document, auth_example.TOKENS["user-token"]) is True
    assert auth_example.can_edit(document, auth_example.TOKENS["admin-token"]) is True
    assert auth_example.can_view(document, outsider) is False

    with pytest.raises(Exception):
        auth_example.require_can_view(document, outsider)

    assert client.get(f"/v1/documents/{document.id}", headers=admin_headers).status_code == 200
    assert client.delete(f"/v1/documents/{document.id}", headers=admin_headers).status_code == 204
    assert client.get(f"/v1/documents/{document.id}", headers=user_headers).status_code == 404


def test_testing_example_service_and_api_reference_tests_are_runnable() -> None:
    tests_example.test_service_create_and_complete()
    tests_example.test_api_create_get_complete()
    tests_example.test_api_validation_and_not_found()


def test_observability_metrics_logging_and_deployment_snippets(caplog: pytest.LogCaptureFixture) -> None:
    observability_example.metrics.requests_total = 0
    observability_example.metrics.errors_total = 0
    observability_example.metrics.last_request_ms = 0.0
    client = TestClient(observability_example.app)

    with caplog.at_level(logging.INFO, logger="api"):
        ping = client.get("/v1/ping", headers={"X-Request-ID": "test-request"})
        metrics_response = client.get("/metrics")

    assert ping.status_code == 200
    assert ping.json() == {"message": "pong"}
    assert metrics_response.json()["requests_total"] >= 1
    assert observability_example.metrics.requests_total >= 2
    assert observability_example.metrics.last_request_ms >= 0
    assert "--no-server-header" in observability_example.DOCKERFILE
    assert "/readyz" in observability_example.KUBERNETES_PROBES

    assert any(getattr(record, "request_id", None) == "test-request" for record in caplog.records)
