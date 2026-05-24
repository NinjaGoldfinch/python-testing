# Auth / Permissions

This example demonstrates bearer-token authentication and resource-level authorization.

## Implementation Plan

1. Convert bearer tokens into typed principals.
2. Centralize permission checks in small helpers.
3. Cover unauthenticated, authorized, and admin access paths.

## Run

```bash
python3 auth_permissions_example.py
python3 -m uvicorn auth_permissions_example:app --reload --no-server-header
```

## Diagram

```mermaid
flowchart TD
    Request[HTTP request] --> Auth[Bearer token dependency]
    Auth --> Principal[Principal user_id + role]
    Principal --> Route[Document route]
    Route --> Permission{Can view or edit?}
    Permission -->|yes| Document[Document operation]
    Permission -->|no| Forbidden[403 Forbidden]
```

## Standards Demonstrated

- Authentication returns a typed principal.
- Authorization checks are explicit helper functions.
- Admins can access all documents; users can access their own.
- Missing or invalid credentials return `401`; denied actions return `403`.
