"""
error_handling_example.py
=========================
Reference implementation for consistent FastAPI error handling.

Run the self-tests:
    python3 error_handling_example.py

Start the API server:
    python3 -m uvicorn error_handling_example:app --reload --no-server-header
"""

from __future__ import annotations

import logging
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. ERROR SHAPE
# ---------------------------------------------------------------------------

def error_body(code: str, message: str, details: list[dict] | None = None) -> dict:
    error: dict = {"code": code, "message": message}
    if details:
        error["details"] = details
    return {"error": error}


HTTP_CODE_MAP = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    500: "INTERNAL_SERVER_ERROR",
}


# ---------------------------------------------------------------------------
# 2. DOMAIN EXCEPTIONS
# ---------------------------------------------------------------------------

class AppError(Exception):
    code = "APP_ERROR"
    status_code = 500
    message = "Application error"


class WidgetNotFoundError(AppError):
    code = "WIDGET_NOT_FOUND"
    status_code = 404
    message = "Widget not found"


class DuplicateWidgetError(AppError):
    code = "DUPLICATE_WIDGET"
    status_code = 409
    message = "Widget name already exists"


# ---------------------------------------------------------------------------
# 3. APP + HANDLERS
# ---------------------------------------------------------------------------

app = FastAPI(title="Error Handling API", version="1.0.0")


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message))


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = HTTP_CODE_MAP.get(exc.status_code, "HTTP_ERROR")
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    if exc.status_code == 404 and message == "Not Found":
        code = "ROUTE_NOT_FOUND"
        message = f"{request.method} {request.url.path} is not a valid API path"
    return JSONResponse(status_code=exc.status_code, content=error_body(code, message))


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"field": " -> ".join(str(part) for part in err["loc"]), "message": err["msg"], "type": err["type"]}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_body("VALIDATION_ERROR", f"{len(details)} validation error(s) in request", details),
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception for %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=error_body("INTERNAL_SERVER_ERROR", "An unexpected error occurred."),
    )


# ---------------------------------------------------------------------------
# 4. ROUTES
# ---------------------------------------------------------------------------

class WidgetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class WidgetRead(BaseModel):
    id: UUID
    name: str


_widgets: dict[UUID, WidgetRead] = {}


@app.post("/v1/widgets/", response_model=WidgetRead, status_code=status.HTTP_201_CREATED)
async def create_widget(payload: WidgetCreate) -> WidgetRead:
    if any(widget.name == payload.name for widget in _widgets.values()):
        raise DuplicateWidgetError
    widget = WidgetRead(id=uuid4(), name=payload.name)
    _widgets[widget.id] = widget
    return widget


@app.get("/v1/widgets/{widget_id}", response_model=WidgetRead)
async def get_widget(widget_id: UUID) -> WidgetRead:
    widget = _widgets.get(widget_id)
    if widget is None:
        raise WidgetNotFoundError
    return widget


@app.get("/v1/http-error")
async def explicit_http_error() -> None:
    raise HTTPException(status_code=400, detail="Explicit bad request")


# ---------------------------------------------------------------------------
# 5. SELF-TESTS
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    client = TestClient(app, raise_server_exceptions=False)

    invalid = client.post("/v1/widgets/", json={"name": ""})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"

    created = client.post("/v1/widgets/", json={"name": "alpha"})
    assert created.status_code == 201

    duplicate = client.post("/v1/widgets/", json={"name": "alpha"})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DUPLICATE_WIDGET"

    missing = client.get(f"/v1/widgets/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "WIDGET_NOT_FOUND"

    route_miss = client.get("/v1/nope")
    assert route_miss.status_code == 404
    assert route_miss.json()["error"]["code"] == "ROUTE_NOT_FOUND"

    print("All error handling tests passed.")


if __name__ == "__main__":
    _run_tests()
