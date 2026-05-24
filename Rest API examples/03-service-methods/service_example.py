"""
service_example.py
==================
A documented reference implementation for the service-method layer of a
Python REST API, using a Project Task API as the example domain.

This file demonstrates the full layered pattern:

    FastAPI route
      -> Pydantic request/response schema
        -> Service method
          -> Repository / database method

The service layer is intentionally framework-independent: it raises domain
exceptions, not HTTPException. The route layer converts domain errors to HTTP.

Run the self-tests (no server required):
    python3 service_example.py

Implementation order (for a full service):
    1. FastAPI app + routers
    2. Pydantic schemas
    3. Service methods          ← this file
    4. Repository / database
    5. Dependency injection
    6. Error handling
    7. Auth / permissions
    8. Tests
    9. Observability + deployment
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 1. IMPORTS
# ---------------------------------------------------------------------------
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Protocol
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, status
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 2. DOMAIN — ENUMS
# ---------------------------------------------------------------------------
# StrEnum gives clean string values in JSON and type-safe comparisons in Python.
# Use Enum for domain-level concepts; do not import FastAPI or Pydantic here.

class TaskStatus(StrEnum):
    """
    Valid task lifecycle states.

    Allowed transitions:
        TODO → IN_PROGRESS → DONE
        TODO → DONE          (skip directly)
        any  → ARCHIVED      (terminal — no further changes allowed)
    """
    TODO        = "todo"
    IN_PROGRESS = "in_progress"
    DONE        = "done"
    ARCHIVED    = "archived"


# ---------------------------------------------------------------------------
# 3. DOMAIN — EXCEPTIONS
# ---------------------------------------------------------------------------
# Services raise domain exceptions — NOT HTTPException.
# The route layer is responsible for translating these into HTTP responses.
# This keeps business logic portable across FastAPI, CLI tools, workers, tests.

class AppError(Exception):
    """Base application exception."""

class TaskNotFoundError(AppError):
    """Task does not exist (or is not visible to the current user)."""

class TaskAlreadyCompletedError(AppError):
    """Cannot complete a task that is already done."""

class TaskArchivedError(AppError):
    """Cannot modify a task that has been archived."""

class InvalidTaskTransitionError(AppError):
    """The requested status transition is not permitted."""

class PermissionDeniedError(AppError):
    """Current user is not allowed to perform this action."""


# ---------------------------------------------------------------------------
# 4. PYDANTIC SCHEMAS  (API contract layer)
# ---------------------------------------------------------------------------
# Separate Create / Update / Read schemas — never merge them.
#   Create  → all required fields
#   Update  → all optional fields (PATCH — only changed fields sent)
#   Read    → output shape shown to clients
#   Filters → typed query-parameter object

class TaskCreate(BaseModel):
    """Request body for POST /tasks/."""
    title:       str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2_000)
    project_id:  UUID
    assignee_id: UUID | None = None


class TaskUpdate(BaseModel):
    """
    Request body for PATCH /tasks/{id}.

    All fields are optional. Use model_dump(exclude_unset=True) in the
    service/repository to touch only the fields the caller sent.
    """
    title:       str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2_000)
    assignee_id: UUID | None = None


class TaskRead(BaseModel):
    """Response schema for a single task."""
    model_config = ConfigDict(from_attributes=True)

    id:          UUID
    title:       str
    description: str | None
    project_id:  UUID
    assignee_id: UUID | None
    status:      TaskStatus
    created_by:  UUID
    created_at:  datetime
    updated_at:  datetime


class TaskListFilters(BaseModel):
    """Typed query-parameter object for GET /tasks/."""
    project_id:  UUID | None = None
    assignee_id: UUID | None = None
    status:      TaskStatus | None = None
    limit:  int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0,  ge=0)


# ---------------------------------------------------------------------------
# 5. REPOSITORY — DATA OBJECT
# ---------------------------------------------------------------------------
# TaskRecord is a plain Python object simulating what a database ORM returns.
# In production, replace with a SQLAlchemy model, asyncpg dataclass, etc.

class TaskRecord:
    """
    Persistence object — the shape returned by the database layer.

    In a real service this would be:
      - A SQLAlchemy mapped class
      - An asyncpg Row cast to a dataclass
      - A Piccolo or Tortoise model
    """
    def __init__(
        self,
        *,
        id:          UUID,
        title:       str,
        description: str | None,
        project_id:  UUID,
        assignee_id: UUID | None,
        status:      TaskStatus,
        created_by:  UUID,
        created_at:  datetime,
        updated_at:  datetime,
    ) -> None:
        self.id          = id
        self.title       = title
        self.description = description
        self.project_id  = project_id
        self.assignee_id = assignee_id
        self.status      = status
        self.created_by  = created_by
        self.created_at  = created_at
        self.updated_at  = updated_at


# ---------------------------------------------------------------------------
# 6. REPOSITORY — PROTOCOL (interface)
# ---------------------------------------------------------------------------
# Python Protocol defines the interface the service expects from persistence.
# Any class that implements these methods satisfies the protocol — no explicit
# inheritance required (structural typing).
#
# This keeps the service independent from SQLAlchemy, asyncpg, Piccolo, etc.
# Swap InMemoryTaskRepository for SqlAlchemyTaskRepository without touching
# the service class.

class TaskRepository(Protocol):
    async def create(self, payload: TaskCreate, *, created_by: UUID) -> TaskRecord: ...
    async def get_by_id(self, task_id: UUID) -> TaskRecord | None: ...
    async def list(self, filters: TaskListFilters) -> list[TaskRecord]: ...
    async def update(self, task_id: UUID, payload: TaskUpdate) -> TaskRecord | None: ...
    async def set_status(self, task_id: UUID, status: TaskStatus) -> TaskRecord | None: ...
    async def assign(self, task_id: UUID, assignee_id: UUID | None) -> TaskRecord | None: ...
    async def delete(self, task_id: UUID) -> bool: ...


# ---------------------------------------------------------------------------
# 7. REPOSITORY — IN-MEMORY IMPLEMENTATION
# ---------------------------------------------------------------------------
# Not for production. Used here for demos, self-tests, and service unit tests
# without requiring a real database.
#
# Replace with:
#   SqlAlchemyTaskRepository   - async SQLAlchemy + PostgreSQL
#   AsyncpgTaskRepository      - raw asyncpg queries
#   PiccoloTaskRepository      - Piccolo ORM

class InMemoryTaskRepository:
    """Thread-unsafe in-memory store for development and testing."""

    def __init__(self) -> None:
        self._tasks: dict[UUID, TaskRecord] = {}

    async def create(self, payload: TaskCreate, *, created_by: UUID) -> TaskRecord:
        now  = datetime.now(timezone.utc)
        task = TaskRecord(
            id=uuid4(),
            title=payload.title,
            description=payload.description,
            project_id=payload.project_id,
            assignee_id=payload.assignee_id,
            status=TaskStatus.TODO,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self._tasks[task.id] = task
        return task

    async def get_by_id(self, task_id: UUID) -> TaskRecord | None:
        return self._tasks.get(task_id)

    async def list(self, filters: TaskListFilters) -> list[TaskRecord]:
        tasks = list(self._tasks.values())
        if filters.project_id  is not None:
            tasks = [t for t in tasks if t.project_id  == filters.project_id]
        if filters.assignee_id is not None:
            tasks = [t for t in tasks if t.assignee_id == filters.assignee_id]
        if filters.status      is not None:
            tasks = [t for t in tasks if t.status      == filters.status]
        return tasks[filters.offset : filters.offset + filters.limit]

    async def update(self, task_id: UUID, payload: TaskUpdate) -> TaskRecord | None:
        task = self._tasks.get(task_id)
        if task is None:
            return None
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(task, field, value)
        task.updated_at = datetime.now(timezone.utc)
        return task

    async def set_status(self, task_id: UUID, status: TaskStatus) -> TaskRecord | None:
        task = self._tasks.get(task_id)
        if task is None:
            return None
        task.status     = status
        task.updated_at = datetime.now(timezone.utc)
        return task

    async def assign(self, task_id: UUID, assignee_id: UUID | None) -> TaskRecord | None:
        task = self._tasks.get(task_id)
        if task is None:
            return None
        task.assignee_id = assignee_id
        task.updated_at  = datetime.now(timezone.utc)
        return task

    async def delete(self, task_id: UUID) -> bool:
        return self._tasks.pop(task_id, None) is not None


# ---------------------------------------------------------------------------
# 8. SERVICE — TASK SERVICE
# ---------------------------------------------------------------------------
# The service layer owns all business rules:
#   - Existence checks
#   - Permission enforcement
#   - State-machine transitions
#   - Orchestration across multiple repository calls
#
# Design rules:
#   ✓  Raise domain exceptions (TaskNotFoundError, PermissionDeniedError…)
#   ✓  Accept and return Pydantic schemas (TaskCreate, TaskRead…)
#   ✗  Never raise HTTPException
#   ✗  Never import FastAPI Request / Response
#   ✗  Never contain database queries
#
# Generic action-method template:
#   1. Load existing entity         → raise NotFoundError if absent
#   2. Check permissions            → raise PermissionDeniedError if denied
#   3. Check business state         → raise domain error if invalid
#   4. Call repository              → persist the change
#   5. Convert to response schema   → return Pydantic model

class TaskService:
    def __init__(self, repository: TaskRepository) -> None:
        self.repository = repository

    # --- CRUD ---

    async def create_task(self, payload: TaskCreate, *, current_user_id: UUID) -> TaskRead:
        task = await self.repository.create(payload, created_by=current_user_id)
        return TaskRead.model_validate(task)

    async def get_task(self, task_id: UUID, *, current_user_id: UUID) -> TaskRead:
        task = await self.repository.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError
        self._ensure_can_view(task, current_user_id=current_user_id)
        return TaskRead.model_validate(task)

    async def list_tasks(
        self,
        filters: TaskListFilters,
        *,
        current_user_id: UUID,
    ) -> list[TaskRead]:
        tasks = await self.repository.list(filters)
        visible = [t for t in tasks if self._can_view(t, current_user_id=current_user_id)]
        return [TaskRead.model_validate(t) for t in visible]

    async def update_task(
        self,
        task_id: UUID,
        payload: TaskUpdate,
        *,
        current_user_id: UUID,
    ) -> TaskRead:
        existing = await self.repository.get_by_id(task_id)
        if existing is None:
            raise TaskNotFoundError
        self._ensure_can_edit(existing, current_user_id=current_user_id)
        self._ensure_not_archived(existing)

        updated = await self.repository.update(task_id, payload)
        if updated is None:
            raise TaskNotFoundError
        return TaskRead.model_validate(updated)

    async def delete_task(self, task_id: UUID, *, current_user_id: UUID) -> None:
        task = await self.repository.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError
        self._ensure_can_edit(task, current_user_id=current_user_id)
        if not await self.repository.delete(task_id):
            raise TaskNotFoundError

    # --- DOMAIN ACTIONS ---
    # Named methods for meaningful business events — not just generic updates.

    async def assign_task(
        self,
        task_id:     UUID,
        assignee_id: UUID | None,
        *,
        current_user_id: UUID,
    ) -> TaskRead:
        """Assign (or unassign) a task to a user."""
        task = await self.repository.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError
        self._ensure_can_edit(task, current_user_id=current_user_id)
        self._ensure_not_archived(task)

        updated = await self.repository.assign(task_id, assignee_id)
        if updated is None:
            raise TaskNotFoundError
        return TaskRead.model_validate(updated)

    async def start_task(self, task_id: UUID, *, current_user_id: UUID) -> TaskRead:
        """Transition a task from TODO → IN_PROGRESS."""
        task = await self.repository.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError
        self._ensure_can_edit(task, current_user_id=current_user_id)
        self._ensure_not_archived(task)
        if task.status == TaskStatus.DONE:
            raise TaskAlreadyCompletedError
        if task.status != TaskStatus.TODO:
            raise InvalidTaskTransitionError(
                f"Cannot start a task that is '{task.status}'"
            )
        updated = await self.repository.set_status(task_id, TaskStatus.IN_PROGRESS)
        if updated is None:
            raise TaskNotFoundError
        return TaskRead.model_validate(updated)

    async def complete_task(self, task_id: UUID, *, current_user_id: UUID) -> TaskRead:
        """Transition a task from TODO or IN_PROGRESS → DONE."""
        task = await self.repository.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError
        self._ensure_can_edit(task, current_user_id=current_user_id)
        self._ensure_not_archived(task)
        if task.status == TaskStatus.DONE:
            raise TaskAlreadyCompletedError
        if task.status not in {TaskStatus.TODO, TaskStatus.IN_PROGRESS}:
            raise InvalidTaskTransitionError(
                f"Cannot complete a task that is '{task.status}'"
            )
        updated = await self.repository.set_status(task_id, TaskStatus.DONE)
        if updated is None:
            raise TaskNotFoundError
        return TaskRead.model_validate(updated)

    async def archive_task(self, task_id: UUID, *, current_user_id: UUID) -> TaskRead:
        """Move a task to ARCHIVED (terminal — no further changes allowed)."""
        task = await self.repository.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError
        self._ensure_can_edit(task, current_user_id=current_user_id)
        updated = await self.repository.set_status(task_id, TaskStatus.ARCHIVED)
        if updated is None:
            raise TaskNotFoundError
        return TaskRead.model_validate(updated)

    # --- PRIVATE HELPERS ---

    def _can_view(self, task: TaskRecord, *, current_user_id: UUID) -> bool:
        """Creator and assignee can view a task."""
        return (
            task.created_by  == current_user_id
            or task.assignee_id == current_user_id
        )

    def _ensure_can_view(self, task: TaskRecord, *, current_user_id: UUID) -> None:
        if not self._can_view(task, current_user_id=current_user_id):
            raise PermissionDeniedError

    def _ensure_can_edit(self, task: TaskRecord, *, current_user_id: UUID) -> None:
        """Only the creator can edit a task."""
        if task.created_by != current_user_id:
            raise PermissionDeniedError

    def _ensure_not_archived(self, task: TaskRecord) -> None:
        if task.status == TaskStatus.ARCHIVED:
            raise TaskArchivedError


# ---------------------------------------------------------------------------
# 9. FASTAPI APP + SECURITY MIDDLEWARE
# ---------------------------------------------------------------------------

SERVER_NAME = "api-example"


class ServerHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next) -> StarletteResponse:
        response = await call_next(request)
        response.headers["server"] = SERVER_NAME
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    # STUB: initialise DB connection pool on startup
    yield
    # STUB: dispose DB connection pool on shutdown


app = FastAPI(
    title="Task API",
    version="1.0.0",
    description="Service-method reference implementation — Project Task API.",
    lifespan=lifespan,
)
app.add_middleware(ServerHeaderMiddleware)


# ---------------------------------------------------------------------------
# 10. ERROR HANDLERS  (converts domain exceptions → structured HTTP responses)
# ---------------------------------------------------------------------------

_HTTP_CODE_MAP: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    500: "INTERNAL_SERVER_ERROR",
}


def _error_body(code: str, message: str, details: list | None = None) -> dict:
    payload: dict = {"code": code, "message": message}
    if details:
        payload["details"] = details
    return {"error": payload}


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: StarletteRequest, exc: StarletteHTTPException) -> JSONResponse:
    code    = _HTTP_CODE_MAP.get(exc.status_code, "HTTP_ERROR")
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    if exc.status_code == 404 and message == "Not Found":
        message = f"{request.method} {request.url.path} is not a valid API path"
        code    = "ROUTE_NOT_FOUND"
    return JSONResponse(status_code=exc.status_code, content=_error_body(code, message))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: StarletteRequest, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"field": " → ".join(str(p) for p in e["loc"]), "message": e["msg"], "type": e["type"]}
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=_error_body("VALIDATION_ERROR", f"{len(details)} validation error(s) in request", details),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: StarletteRequest, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception for %s %s", request.method, request.url)
    return JSONResponse(
        status_code=500,
        content=_error_body("INTERNAL_SERVER_ERROR", "An unexpected error occurred. Please try again later."),
    )


# ---------------------------------------------------------------------------
# 11. DEPENDENCY INJECTION
# ---------------------------------------------------------------------------
# FastAPI resolves the dependency tree per request.
# Swap InMemoryTaskRepository for any class that satisfies TaskRepository Protocol.

_task_repository: InMemoryTaskRepository = InMemoryTaskRepository()


async def get_current_user_id() -> UUID:
    """
    Placeholder auth dependency.

    Replace with real authentication:
      - JWT bearer token   → decode + verify → return user UUID
      - Session cookie     → look up session → return user UUID
      - API key header     → validate key   → return user UUID
      - OAuth2             → exchange token → return user UUID
    """
    return UUID("00000000-0000-0000-0000-000000000001")


async def get_task_repository() -> InMemoryTaskRepository:
    return _task_repository


async def get_task_service(
    repository: Annotated[InMemoryTaskRepository, Depends(get_task_repository)],
) -> TaskService:
    return TaskService(repository)


# Type aliases — cleaner route signatures
CurrentUserId = Annotated[UUID,        Depends(get_current_user_id)]
TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]


# ---------------------------------------------------------------------------
# 12. ROUTES
# ---------------------------------------------------------------------------
# Route handlers do exactly three things:
#   1. Parse and validate input (FastAPI + Pydantic handles this automatically)
#   2. Call the service method
#   3. Map domain exceptions → HTTPException via map_service_error()
#
# No business logic belongs here.

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])


def map_service_error(error: Exception) -> HTTPException:
    """Translate domain exceptions into HTTP responses."""
    if isinstance(error, TaskNotFoundError):
        return HTTPException(status_code=404, detail="Task not found")
    if isinstance(error, PermissionDeniedError):
        return HTTPException(status_code=403, detail="Permission denied")
    if isinstance(error, TaskAlreadyCompletedError):
        return HTTPException(status_code=409, detail="Task is already completed")
    if isinstance(error, TaskArchivedError):
        return HTTPException(status_code=409, detail="Task is archived and cannot be modified")
    if isinstance(error, InvalidTaskTransitionError):
        return HTTPException(status_code=409, detail=f"Invalid status transition: {error}")
    return HTTPException(status_code=500, detail="Internal server error")


@router.post("/", response_model=TaskRead, status_code=status.HTTP_201_CREATED, summary="Create a task")
async def create_task(payload: TaskCreate, service: TaskServiceDep, current_user_id: CurrentUserId) -> TaskRead:
    try:
        return await service.create_task(payload, current_user_id=current_user_id)
    except Exception as e:
        raise map_service_error(e) from e


@router.get("/", response_model=list[TaskRead], summary="List tasks")
async def list_tasks(
    service:        TaskServiceDep,
    current_user_id: CurrentUserId,
    project_id:     UUID | None = None,
    assignee_id:    UUID | None = None,
    task_status:    TaskStatus | None = Query(default=None, alias="status"),
    limit:  int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0,  ge=0),
) -> list[TaskRead]:
    filters = TaskListFilters(
        project_id=project_id, assignee_id=assignee_id,
        status=task_status, limit=limit, offset=offset,
    )
    try:
        return await service.list_tasks(filters, current_user_id=current_user_id)
    except Exception as e:
        raise map_service_error(e) from e


@router.get("/{task_id}", response_model=TaskRead, summary="Get a task")
async def get_task(task_id: UUID, service: TaskServiceDep, current_user_id: CurrentUserId) -> TaskRead:
    try:
        return await service.get_task(task_id, current_user_id=current_user_id)
    except Exception as e:
        raise map_service_error(e) from e


@router.patch("/{task_id}", response_model=TaskRead, summary="Update a task (partial)")
async def update_task(task_id: UUID, payload: TaskUpdate, service: TaskServiceDep, current_user_id: CurrentUserId) -> TaskRead:
    try:
        return await service.update_task(task_id, payload, current_user_id=current_user_id)
    except Exception as e:
        raise map_service_error(e) from e


@router.post("/{task_id}/assign", response_model=TaskRead, summary="Assign a task to a user")
async def assign_task(task_id: UUID, assignee_id: UUID | None, service: TaskServiceDep, current_user_id: CurrentUserId) -> TaskRead:
    try:
        return await service.assign_task(task_id, assignee_id, current_user_id=current_user_id)
    except Exception as e:
        raise map_service_error(e) from e


@router.post("/{task_id}/start", response_model=TaskRead, summary="Start a task (TODO → IN_PROGRESS)")
async def start_task(task_id: UUID, service: TaskServiceDep, current_user_id: CurrentUserId) -> TaskRead:
    try:
        return await service.start_task(task_id, current_user_id=current_user_id)
    except Exception as e:
        raise map_service_error(e) from e


@router.post("/{task_id}/complete", response_model=TaskRead, summary="Complete a task (→ DONE)")
async def complete_task(task_id: UUID, service: TaskServiceDep, current_user_id: CurrentUserId) -> TaskRead:
    try:
        return await service.complete_task(task_id, current_user_id=current_user_id)
    except Exception as e:
        raise map_service_error(e) from e


@router.post("/{task_id}/archive", response_model=TaskRead, summary="Archive a task (terminal)")
async def archive_task(task_id: UUID, service: TaskServiceDep, current_user_id: CurrentUserId) -> TaskRead:
    try:
        return await service.archive_task(task_id, current_user_id=current_user_id)
    except Exception as e:
        raise map_service_error(e) from e


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a task")
async def delete_task(task_id: UUID, service: TaskServiceDep, current_user_id: CurrentUserId) -> None:
    try:
        await service.delete_task(task_id, current_user_id=current_user_id)
    except Exception as e:
        raise map_service_error(e) from e


@app.get("/healthz", tags=["ops"], summary="Liveness probe")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz", tags=["ops"], summary="Readiness probe")
async def readyz() -> dict[str, str]:
    return {"status": "ready"}


app.include_router(router)


# ---------------------------------------------------------------------------
# 13. SELF-TESTS  (run with: python3 service_example.py)
# ---------------------------------------------------------------------------
# These tests run without a server — they call the service class directly,
# which proves the business rules independently of HTTP.

def _sep(title: str) -> None:
    print(f"\n{'─' * 60}\n  {title}\n{'─' * 60}")

def _ok(msg: str)   -> None: print(f"  ✔  {msg}")
def _fail(msg: str) -> None: print(f"  ✘  {msg}")


async def _run_tests() -> None:
    repo    = InMemoryTaskRepository()
    service = TaskService(repo)

    user_a  = uuid4()
    user_b  = uuid4()
    proj_id = uuid4()

    # ---- create ----
    _sep("create_task")
    task = await service.create_task(
        TaskCreate(title="Write tests", project_id=proj_id),
        current_user_id=user_a,
    )
    assert task.title      == "Write tests"
    assert task.status     == TaskStatus.TODO
    assert task.created_by == user_a
    _ok(f"Created task {task.id} — status={task.status}")

    # ---- get ----
    _sep("get_task")
    fetched = await service.get_task(task.id, current_user_id=user_a)
    assert fetched.id == task.id
    _ok("Creator can fetch own task")

    # ---- permission: other user cannot view ----
    _sep("permission — get_task by non-owner")
    try:
        await service.get_task(task.id, current_user_id=user_b)
        _fail("Should have raised PermissionDeniedError")
    except PermissionDeniedError:
        _ok("Non-owner cannot view task")

    # ---- assign ----
    _sep("assign_task")
    assigned = await service.assign_task(task.id, user_b, current_user_id=user_a)
    assert assigned.assignee_id == user_b
    _ok(f"Task assigned to user_b")
    # assignee can now view
    viewed = await service.get_task(task.id, current_user_id=user_b)
    assert viewed.assignee_id == user_b
    _ok("Assignee can now view task")

    # ---- update ----
    _sep("update_task (PATCH)")
    updated = await service.update_task(
        task.id,
        TaskUpdate(title="Write proper tests"),
        current_user_id=user_a,
    )
    assert updated.title == "Write proper tests"
    _ok(f"Title updated: '{updated.title}'")

    # ---- start ----
    _sep("start_task (TODO → IN_PROGRESS)")
    started = await service.start_task(task.id, current_user_id=user_a)
    assert started.status == TaskStatus.IN_PROGRESS
    _ok(f"Status = {started.status}")

    # cannot start again
    try:
        await service.start_task(task.id, current_user_id=user_a)
        _fail("Should have raised InvalidTaskTransitionError")
    except InvalidTaskTransitionError:
        _ok("Cannot start an already in-progress task")

    # ---- complete ----
    _sep("complete_task (IN_PROGRESS → DONE)")
    done = await service.complete_task(task.id, current_user_id=user_a)
    assert done.status == TaskStatus.DONE
    _ok(f"Status = {done.status}")

    # cannot complete again
    try:
        await service.complete_task(task.id, current_user_id=user_a)
        _fail("Should have raised TaskAlreadyCompletedError")
    except TaskAlreadyCompletedError:
        _ok("Cannot complete an already-done task")

    # ---- archive ----
    _sep("archive_task (→ ARCHIVED)")
    archived = await service.archive_task(task.id, current_user_id=user_a)
    assert archived.status == TaskStatus.ARCHIVED
    _ok(f"Status = {archived.status}")

    # cannot edit archived
    try:
        await service.update_task(task.id, TaskUpdate(title="x"), current_user_id=user_a)
        _fail("Should have raised TaskArchivedError")
    except TaskArchivedError:
        _ok("Cannot update archived task")

    # ---- list ----
    _sep("list_tasks")
    task2 = await service.create_task(
        TaskCreate(title="Second task", project_id=proj_id),
        current_user_id=user_a,
    )
    tasks = await service.list_tasks(
        TaskListFilters(project_id=proj_id),
        current_user_id=user_a,
    )
    assert len(tasks) == 2
    _ok(f"list_tasks returned {len(tasks)} tasks for project")

    tasks_todo = await service.list_tasks(
        TaskListFilters(status=TaskStatus.TODO),
        current_user_id=user_a,
    )
    assert all(t.status == TaskStatus.TODO for t in tasks_todo)
    _ok(f"Filtered by status=todo: {len(tasks_todo)} task(s)")

    # ---- delete ----
    _sep("delete_task")
    await service.delete_task(task2.id, current_user_id=user_a)
    try:
        await service.get_task(task2.id, current_user_id=user_a)
        _fail("Should have raised TaskNotFoundError")
    except TaskNotFoundError:
        _ok("Deleted task is gone")

    # ---- not found ----
    _sep("TaskNotFoundError")
    try:
        await service.get_task(uuid4(), current_user_id=user_a)
        _fail("Should have raised TaskNotFoundError")
    except TaskNotFoundError:
        _ok("Unknown task_id raises TaskNotFoundError")

    print("\n  All service tests passed.\n")


if __name__ == "__main__":
    asyncio.run(_run_tests())


# ---------------------------------------------------------------------------
# 14. GENERIC SERVICE METHOD TEMPLATE
# ---------------------------------------------------------------------------
# Copy this template when implementing a new domain action.
#
#   async def action_name(
#       self,
#       entity_id: UUID,
#       payload:   SomePayload,   # omit if no payload needed
#       *,
#       current_user_id: UUID,
#   ) -> EntityRead:
#       # 1. Load entity
#       entity = await self.repository.get_by_id(entity_id)
#       if entity is None:
#           raise EntityNotFoundError
#
#       # 2. Check permissions
#       self._ensure_can_edit(entity, current_user_id=current_user_id)
#
#       # 3. Check business state
#       self._ensure_not_archived(entity)
#       if entity.status not in ALLOWED_STATES:
#           raise InvalidTransitionError
#
#       # 4. Persist
#       updated = await self.repository.some_operation(entity_id, payload)
#       if updated is None:
#           raise EntityNotFoundError
#
#       # 5. Return response schema
#       return EntityRead.model_validate(updated)


# ---------------------------------------------------------------------------
# 15. HOW TO ADAPT TO A DIFFERENT DOMAIN
# ---------------------------------------------------------------------------
# Keep the same file structure; rename domain concepts:
#
#   Tasks         → Invoices        → Devices         → Jobs
#   TaskService   → InvoiceService  → DeviceService   → JobService
#   TaskStatus    → InvoiceStatus   → DeviceStatus    → JobStatus
#   complete_task → mark_paid       → decommission    → mark_succeeded
#   archive_task  → void_invoice    → retire_device   → cancel_job
#   assign_task   → assign_owner    → assign_owner    → assign_worker
#
# Service methods should work unchanged whether called from:
#   - A FastAPI route handler
#   - A CLI command
#   - A background worker / Celery task
#   - A test harness (just pass an InMemory repository)
