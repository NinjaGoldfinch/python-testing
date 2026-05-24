"""
observability_deployment_example.py
===================================
Reference implementation for production observability and deployment hooks.

Run the self-tests:
    python3 observability_deployment_example.py

Start the API server:
    python3 -m uvicorn observability_deployment_example:app --reload --no-server-header
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Awaitable, Callable
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware


# ---------------------------------------------------------------------------
# 1. STRUCTURED LOGGING
# ---------------------------------------------------------------------------

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "method", "path", "status_code", "duration_ms"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, separators=(",", ":"))


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
logger = logging.getLogger("api")


# ---------------------------------------------------------------------------
# 2. METRICS STORE
# ---------------------------------------------------------------------------

@dataclass
class Metrics:
    requests_total: int = 0
    errors_total: int = 0
    last_request_ms: float = 0.0


metrics = Metrics()


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            metrics.requests_total += 1
            metrics.last_request_ms = duration_ms
            if status_code >= 500:
                metrics.errors_total += 1
            logger.info(
                "request completed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )


# ---------------------------------------------------------------------------
# 3. LIFESPAN + APP
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("application startup")
    yield
    logger.info("application shutdown")


app = FastAPI(
    title="Observability and Deployment API",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(ObservabilityMiddleware)


@app.get("/healthz", tags=["ops"])
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz", tags=["ops"])
async def readyz() -> dict[str, str]:
    return {"status": "ready"}


@app.get("/metrics", tags=["ops"])
async def get_metrics() -> dict[str, float | int]:
    return {
        "requests_total": metrics.requests_total,
        "errors_total": metrics.errors_total,
        "last_request_ms": metrics.last_request_ms,
    }


@app.get("/v1/ping", tags=["example"])
async def ping() -> dict[str, str]:
    return {"message": "pong"}


# ---------------------------------------------------------------------------
# 4. DEPLOYMENT REFERENCE
# ---------------------------------------------------------------------------

DOCKERFILE = """
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "observability_deployment_example:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
""".strip()


KUBERNETES_PROBES = """
livenessProbe:
  httpGet:
    path: /healthz
    port: 8000
readinessProbe:
  httpGet:
    path: /readyz
    port: 8000
""".strip()


# ---------------------------------------------------------------------------
# 5. SELF-TESTS
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    client = TestClient(app)

    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    ping_response = client.get("/v1/ping", headers={"X-Request-ID": "test-request"})
    assert ping_response.status_code == 200
    assert ping_response.json()["message"] == "pong"

    metrics_response = client.get("/metrics")
    assert metrics_response.status_code == 200
    body = metrics_response.json()
    assert body["requests_total"] >= 2
    assert "last_request_ms" in body

    assert "/healthz" in KUBERNETES_PROBES
    assert "--no-server-header" in DOCKERFILE

    print("All observability and deployment tests passed.")


if __name__ == "__main__":
    _run_tests()
