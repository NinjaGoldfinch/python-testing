# FastAPI App + Routers

This example shows the HTTP surface of a REST API: app creation, lifespan, middleware, routers, path/query parameters, health checks, and structured error envelopes.

## Implementation Plan

1. Create the `FastAPI` app with lifespan and middleware.
2. Group resource endpoints under `APIRouter`.
3. Add health/readiness routes and smoke-test the HTTP surface.

## Run

```bash
python3 -m uvicorn fastapi_example:app --reload --no-server-header
```

Open `http://127.0.0.1:8000/docs`.

## Diagram

```mermaid
flowchart TD
    Client[HTTP client] --> App[FastAPI app]
    App --> Middleware[Server header middleware]
    Middleware --> Router[APIRouter /v1/items]
    Router --> Handler[Route handler]
    Handler --> Store[In-memory item store]
    Handler --> Response[Pydantic response model]
```

## Standards Demonstrated

- One `FastAPI` app with a lifespan context manager.
- Resource routes grouped under `APIRouter`.
- Explicit status codes such as `201` and `204`.
- Health and readiness endpoints for deployment platforms.
- Structured errors instead of raw `{"detail": ...}` responses.
