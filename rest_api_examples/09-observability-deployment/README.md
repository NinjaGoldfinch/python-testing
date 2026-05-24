# Observability + Deployment

This example shows production hooks: structured JSON logs, request IDs, simple metrics, health/readiness endpoints, and deployment snippets.

## When To Use It

Use this pattern when an API is moving beyond local-only development and needs enough operational structure to be monitored and deployed confidently.

## Implementation Plan

1. Add request middleware for timing, request IDs, logs, and counters.
2. Expose health, readiness, and metrics endpoints.
3. Include deployment snippets that match the runtime behavior.

## Run

```bash
python3 observability_deployment_example.py
python3 -m uvicorn observability_deployment_example:app --reload --no-server-header
```

## Diagram

```mermaid
flowchart TD
    Request[HTTP request] --> Middleware[Observability middleware]
    Middleware --> RequestID[Request ID]
    Middleware --> Timer[Duration timer]
    Middleware --> Route[Route handler]
    Middleware --> Logs[Structured JSON logs]
    Middleware --> Metrics[Metrics counters]
    Platform[Load balancer or Kubernetes] --> Health[/healthz]
    Platform --> Ready[/readyz]
```

## Standards Demonstrated

- Logs are machine-readable JSON.
- Requests carry or receive a request ID.
- Health and readiness endpoints are deployment-facing.
- Metrics are exposed through a small `/metrics` endpoint.
- Docker and Kubernetes probe snippets show deployment expectations.

## Demo vs Production

- The demo uses a tiny in-process metrics store so the behavior stays visible.
- In production, these hooks often connect to external logging, metrics, and orchestration platforms.

## Best Paired With

- [`../01-fastapi-app-routers/README.md`](../01-fastapi-app-routers/README.md)
- [`../06-error-handling/README.md`](../06-error-handling/README.md)
- [`../04-database-models-repositories/README.md`](../04-database-models-repositories/README.md)
