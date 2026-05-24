"""
dependency_injection_example.py
===============================
Reference implementation for FastAPI dependency injection.

Run the self-tests:
    python3 dependency_injection_example.py

Start the API server:
    python3 -m uvicorn dependency_injection_example:app --reload --no-server-header
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Protocol
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 1. SETTINGS
# ---------------------------------------------------------------------------
# Keep settings injectable. Tests can override get_settings() without changing
# route code or mutating global module state.

@dataclass(frozen=True)
class Settings:
    app_name: str = "Dependency Injection API"
    api_key: str = "dev-api-key"
    allow_debug_routes: bool = True


def get_settings() -> Settings:
    return Settings()


SettingsDep = Annotated[Settings, Depends(get_settings)]


# ---------------------------------------------------------------------------
# 2. SCHEMAS
# ---------------------------------------------------------------------------

class NoteCreate(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class NoteRead(BaseModel):
    id: UUID
    text: str
    owner_id: UUID


# ---------------------------------------------------------------------------
# 3. REPOSITORY PROTOCOL + IMPLEMENTATION
# ---------------------------------------------------------------------------

class NoteRepository(Protocol):
    async def create(self, payload: NoteCreate, *, owner_id: UUID) -> NoteRead: ...
    async def list_for_owner(self, owner_id: UUID) -> list[NoteRead]: ...


class InMemoryNoteRepository:
    def __init__(self) -> None:
        self._notes: dict[UUID, NoteRead] = {}

    async def create(self, payload: NoteCreate, *, owner_id: UUID) -> NoteRead:
        note = NoteRead(id=uuid4(), text=payload.text, owner_id=owner_id)
        self._notes[note.id] = note
        return note

    async def list_for_owner(self, owner_id: UUID) -> list[NoteRead]:
        return [note for note in self._notes.values() if note.owner_id == owner_id]


_repository = InMemoryNoteRepository()


async def get_note_repository() -> InMemoryNoteRepository:
    return _repository


RepositoryDep = Annotated[InMemoryNoteRepository, Depends(get_note_repository)]


# ---------------------------------------------------------------------------
# 4. AUTH DEPENDENCY
# ---------------------------------------------------------------------------

async def require_api_key(
    settings: SettingsDep,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> UUID:
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return UUID("00000000-0000-0000-0000-000000000001")


CurrentUserId = Annotated[UUID, Depends(require_api_key)]


# ---------------------------------------------------------------------------
# 5. SERVICE DEPENDENCY
# ---------------------------------------------------------------------------

class NoteService:
    def __init__(self, repository: NoteRepository) -> None:
        self.repository = repository

    async def create_note(self, payload: NoteCreate, *, owner_id: UUID) -> NoteRead:
        return await self.repository.create(payload, owner_id=owner_id)

    async def list_notes(self, *, owner_id: UUID) -> list[NoteRead]:
        return await self.repository.list_for_owner(owner_id)


async def get_note_service(repository: RepositoryDep) -> NoteService:
    return NoteService(repository)


ServiceDep = Annotated[NoteService, Depends(get_note_service)]


# ---------------------------------------------------------------------------
# 6. APP + ROUTES
# ---------------------------------------------------------------------------

app = FastAPI(title="Dependency Injection API", version="1.0.0")


@app.get("/healthz", tags=["ops"])
async def healthz(settings: SettingsDep) -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


@app.post("/v1/notes/", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
async def create_note(
    payload: NoteCreate,
    service: ServiceDep,
    current_user_id: CurrentUserId,
) -> NoteRead:
    return await service.create_note(payload, owner_id=current_user_id)


@app.get("/v1/notes/", response_model=list[NoteRead])
async def list_notes(service: ServiceDep, current_user_id: CurrentUserId) -> list[NoteRead]:
    return await service.list_notes(owner_id=current_user_id)


# ---------------------------------------------------------------------------
# 7. SELF-TESTS
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    client = TestClient(app)

    assert client.get("/healthz").status_code == 200
    assert client.get("/v1/notes/").status_code == 401

    headers = {"X-API-Key": "dev-api-key"}
    created = client.post("/v1/notes/", json={"text": "Wire dependencies"}, headers=headers)
    assert created.status_code == 201, created.text
    assert created.json()["text"] == "Wire dependencies"

    listed = client.get("/v1/notes/", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    print("All dependency injection tests passed.")


if __name__ == "__main__":
    _run_tests()
