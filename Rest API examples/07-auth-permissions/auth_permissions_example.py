"""
auth_permissions_example.py
===========================
Reference implementation for authentication and permission checks in FastAPI.

Run the self-tests:
    python3 auth_permissions_example.py

Start the API server:
    python3 -m uvicorn auth_permissions_example:app --reload --no-server-header
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 1. AUTH MODEL
# ---------------------------------------------------------------------------

class Role(StrEnum):
    USER = "user"
    ADMIN = "admin"


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    role: Role


TOKENS: dict[str, Principal] = {
    "user-token": Principal(UUID("00000000-0000-0000-0000-000000000001"), Role.USER),
    "admin-token": Principal(UUID("00000000-0000-0000-0000-000000000002"), Role.ADMIN),
}


async def get_current_principal(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> Principal:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    principal = TOKENS.get(token)
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")
    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


# ---------------------------------------------------------------------------
# 2. DOMAIN + STORE
# ---------------------------------------------------------------------------

class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=5000)


class DocumentRead(BaseModel):
    id: UUID
    title: str
    body: str
    owner_id: UUID


_documents: dict[UUID, DocumentRead] = {}


# ---------------------------------------------------------------------------
# 3. PERMISSION HELPERS
# ---------------------------------------------------------------------------

def can_view(document: DocumentRead, principal: Principal) -> bool:
    return principal.role == Role.ADMIN or document.owner_id == principal.user_id


def can_edit(document: DocumentRead, principal: Principal) -> bool:
    return principal.role == Role.ADMIN or document.owner_id == principal.user_id


def require_can_view(document: DocumentRead, principal: Principal) -> None:
    if not can_view(document, principal):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")


def require_can_edit(document: DocumentRead, principal: Principal) -> None:
    if not can_edit(document, principal):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")


# ---------------------------------------------------------------------------
# 4. APP + ROUTES
# ---------------------------------------------------------------------------

app = FastAPI(title="Auth and Permissions API", version="1.0.0")


@app.post("/v1/documents/", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def create_document(payload: DocumentCreate, principal: CurrentPrincipal) -> DocumentRead:
    document = DocumentRead(id=uuid4(), owner_id=principal.user_id, **payload.model_dump())
    _documents[document.id] = document
    return document


@app.get("/v1/documents/", response_model=list[DocumentRead])
async def list_documents(principal: CurrentPrincipal) -> list[DocumentRead]:
    return [document for document in _documents.values() if can_view(document, principal)]


@app.get("/v1/documents/{document_id}", response_model=DocumentRead)
async def get_document(document_id: UUID, principal: CurrentPrincipal) -> DocumentRead:
    document = _documents.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    require_can_view(document, principal)
    return document


@app.delete("/v1/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: UUID, principal: CurrentPrincipal) -> None:
    document = _documents.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    require_can_edit(document, principal)
    del _documents[document_id]


# ---------------------------------------------------------------------------
# 5. SELF-TESTS
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    client = TestClient(app)
    user_headers = {"Authorization": "Bearer user-token"}
    admin_headers = {"Authorization": "Bearer admin-token"}

    assert client.get("/v1/documents/").status_code == 401

    created = client.post(
        "/v1/documents/",
        json={"title": "Runbook", "body": "Operational notes"},
        headers=user_headers,
    )
    assert created.status_code == 201, created.text
    document_id = created.json()["id"]

    assert client.get(f"/v1/documents/{document_id}", headers=user_headers).status_code == 200
    assert client.get(f"/v1/documents/{document_id}", headers=admin_headers).status_code == 200
    assert client.delete(f"/v1/documents/{document_id}", headers=admin_headers).status_code == 204
    assert client.get(f"/v1/documents/{document_id}", headers=user_headers).status_code == 404

    print("All auth and permissions tests passed.")


if __name__ == "__main__":
    _run_tests()
