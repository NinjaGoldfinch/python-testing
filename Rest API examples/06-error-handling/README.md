# Error Handling

This example shows consistent HTTP error envelopes for domain errors, route misses, validation errors, and unhandled exceptions.

## Implementation Plan

1. Define one error envelope shape for clients.
2. Register handlers for domain, HTTP, validation, and unknown errors.
3. Test each error path so clients can rely on stable codes.

## Run

```bash
python3 error_handling_example.py
python3 -m uvicorn error_handling_example:app --reload --no-server-header
```

## Diagram

```mermaid
flowchart TD
    Error[Exception raised] --> Kind{Exception type}
    Kind --> Domain[AppError handler]
    Kind --> HTTP[HTTPException handler]
    Kind --> Validation[RequestValidationError handler]
    Kind --> Unknown[Unhandled exception handler]
    Domain --> Envelope[Standard error envelope]
    HTTP --> Envelope
    Validation --> Envelope
    Unknown --> Envelope
```

## Standards Demonstrated

- Domain exceptions map to stable machine-readable codes.
- Validation errors include per-field details.
- Routing 404s are distinguishable from missing resources.
- Server logs keep traceback details out of client responses.
