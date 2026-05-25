"""
database_example.py
===================
A documented reference implementation for the database layer of a Python REST API,
using the Task API domain.

This file covers:
    - A two-track persistence strategy:
        1. ORM for local development, testing, fixtures, and fast iteration
        2. Raw SQL for production deployments where overhead/control matters
    - SQLAlchemy 2.x async setup for development/test databases
    - Raw SQL repository shape for production implementations
    - Repository Protocol (interface) — keeps the service layer DB-agnostic
    - In-memory repository — used for demos and tests without a real DB
    - Alembic migration notes

Install:
    pip install fastapi uvicorn pydantic sqlalchemy[asyncio] asyncpg alembic

Run the self-tests (no server, no DB required):
    python3 database_example.py

Start the API server (in-memory store):
    python3 -m uvicorn database_example:app --reload --no-server-header

Implementation order (for a full service):
    1. FastAPI app + routers
    2. Pydantic schemas
    3. Service methods
    4. Database models + repository methods    ← this file
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
from typing import Annotated, AsyncGenerator, Protocol
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse

# ---------------------------------------------------------------------------
# STUB: SQLAlchemy 2.x async imports (development/test ORM track)
# ---------------------------------------------------------------------------
# from sqlalchemy import String, Numeric, ForeignKey, func, select, update, delete
# from sqlalchemy.dialects.postgresql import UUID as PG_UUID
# from sqlalchemy.ext.asyncio import (
#     AsyncSession,
#     create_async_engine,
#     async_sessionmaker,
# )
# from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
# ---------------------------------------------------------------------------
#
# STUB: Raw SQL imports (production track)
# ---------------------------------------------------------------------------
# import asyncpg
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 2. DOMAIN — ENUMS
# ---------------------------------------------------------------------------

class TaskStatus(StrEnum):
    TODO        = "todo"
    IN_PROGRESS = "in_progress"
    DONE        = "done"
    ARCHIVED    = "archived"


# ---------------------------------------------------------------------------
# 3. DOMAIN — EXCEPTIONS
# ---------------------------------------------------------------------------

class AppError(Exception):
    """Base application exception. Catch this to handle all domain errors."""

class TaskNotFoundError(AppError):
    """Task does not exist (or is not visible to the current user)."""

class TaskArchivedError(AppError):
    """Cannot modify a task that has been archived."""


# ---------------------------------------------------------------------------
# 4. PYDANTIC SCHEMAS  (API contract layer)
# ---------------------------------------------------------------------------

class TaskCreate(BaseModel):
    """Request body for POST /tasks/."""
    title:       str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2_000)
    project_id:  UUID
    assignee_id: UUID | None = None


class TaskUpdate(BaseModel):
    """PATCH body — all fields optional. Use model_dump(exclude_unset=True) in the repo."""
    title:       str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2_000)
    assignee_id: UUID | None = None


class TaskRead(BaseModel):
    """Response schema returned to API callers."""
    model_config = ConfigDict(from_attributes=True)  # allows ORM → Pydantic directly

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
# 5. DATABASE STRATEGY + ORM MODEL
# ---------------------------------------------------------------------------
# Recommended workflow for this codebase:
#
#   Development / testing:
#       Use SQLAlchemy ORM models. They are excellent for local iteration,
#       fixtures, relationship traversal, and readable test setup.
#
#   Production deployment:
#       Keep the same TaskRepository Protocol, but bind DI to a raw SQL
#       repository implemented with asyncpg or SQLAlchemy Core text queries.
#       This avoids ORM unit-of-work and object hydration overhead on hot paths,
#       while keeping service methods unchanged.
#
# In a real project, ORM-only development models live in db/models.py.
#
# SQLAlchemy 2.x uses the new "mapped_column" API — fully type-annotated.
# The ORM model is separate from the Pydantic schema: never return a raw ORM
# object from a route; always project through a Pydantic Read schema.
#
# Real implementation (uncomment and adapt):
# ---------------------------------------------------------------------------
#
# import uuid
# from decimal import Decimal
# from sqlalchemy import String, func
# from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
# from sqlalchemy.dialects.postgresql import UUID as PG_UUID
#
# class Base(DeclarativeBase):
#     """All ORM models inherit from this shared base."""
#
# class TaskModel(Base):
#     """
#     SQLAlchemy ORM model for the 'tasks' table.
#
#     mapped_column() replaces Column() in SQLAlchemy 2.x.
#     Mapped[T] provides full type annotation — mypy / pyright understand it.
#     """
#     __tablename__ = "tasks"
#
#     # Primary key — use UUID (better than serial INT for distributed systems)
#     id: Mapped[uuid.UUID] = mapped_column(
#         PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
#     )
#
#     title:       Mapped[str]            = mapped_column(String(200), nullable=False)
#     description: Mapped[str | None]     = mapped_column(String(2000), nullable=True)
#     project_id:  Mapped[uuid.UUID]      = mapped_column(PG_UUID(as_uuid=True), nullable=False)
#     assignee_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
#     status:      Mapped[str]            = mapped_column(String(20), default="todo", nullable=False)
#     created_by:  Mapped[uuid.UUID]      = mapped_column(PG_UUID(as_uuid=True), nullable=False)
#
#     # server_default=func.now() sets the timestamp in the database — not in Python.
#     # This is important for consistency in high-concurrency environments.
#     created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
#     updated_at: Mapped[datetime] = mapped_column(
#         server_default=func.now(), onupdate=func.now(), nullable=False
#     )
#
#     def to_record(self) -> "TaskRecord":
#         """Convert ORM model to a plain Python record for service layer use."""
#         return TaskRecord(
#             id=self.id, title=self.title, description=self.description,
#             project_id=self.project_id, assignee_id=self.assignee_id,
#             status=TaskStatus(self.status), created_by=self.created_by,
#             created_at=self.created_at, updated_at=self.updated_at,
#         )
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 6. ASYNC ORM ENGINE + SESSION FACTORY  (development/test track)
# ---------------------------------------------------------------------------
# In a real project, this lives in db/session.py.
#
# create_async_engine() is the async counterpart to create_engine().
# async_sessionmaker() produces individual AsyncSession objects per request.
#
# Connection string format:
#   postgresql+asyncpg://user:password@host:5432/dbname
#
# pool_size and max_overflow tune the connection pool:
#   pool_size=10    — up to 10 persistent connections
#   max_overflow=20 — up to 20 extra connections under burst load
#
# Development/test implementation (uncomment and adapt):
# ---------------------------------------------------------------------------
#
# from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
# from pydantic_settings import BaseSettings
#
# class Settings(BaseSettings):
#     database_url: str = "postgresql+asyncpg://user:pass@localhost/taskdb"
#     db_pool_size: int = 10
#     db_max_overflow: int = 20
#
# settings = Settings()
#
# engine = create_async_engine(
#     settings.database_url,
#     pool_size=settings.db_pool_size,
#     max_overflow=settings.db_max_overflow,
#     echo=False,    # set True to log all SQL statements (useful in development)
# )
#
# AsyncSessionLocal = async_sessionmaker(
#     engine,
#     expire_on_commit=False,  # keep ORM objects usable after commit()
# )
#
# async def get_db() -> AsyncGenerator[AsyncSession, None]:
#     """
#     FastAPI dependency that yields one AsyncSession per request.
#
#     The 'async with' block:
#       - Opens the session on enter
#       - Commits automatically on clean exit
#       - Rolls back automatically on exception
#       - Closes the session on exit (returns connection to pool)
#     """
#     async with AsyncSessionLocal() as session:
#         yield session
#
# DBSession = Annotated[AsyncSession, Depends(get_db)]
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 7. PERSISTENCE RECORD
# ---------------------------------------------------------------------------
# TaskRecord is a plain Python object — the shape returned from the DB layer.
# The service layer works with TaskRecord objects, not raw ORM models.
# This keeps the service portable and independently testable.

class TaskRecord:
    """
    Plain Python data container returned by all repository methods.

    Separating this from both the ORM model and the Pydantic schema:
    - Makes the service layer testable without a real DB (InMemoryRepository)
    - Keeps ORM-specific behaviour (lazy loading, sessions) out of the service

    Production code should keep this class and convert raw database rows into
    TaskRecord objects. That keeps service methods independent from both ORM
    models and raw driver row types.
    """

    __slots__ = (
        "id", "title", "description", "project_id", "assignee_id",
        "status", "created_by", "created_at", "updated_at",
    )

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

    def __repr__(self) -> str:
        return f"<TaskRecord id={self.id} title={self.title!r} status={self.status}>"


# ---------------------------------------------------------------------------
# 8. REPOSITORY — PROTOCOL (interface)
# ---------------------------------------------------------------------------
# The Protocol defines the contract the service expects from any storage backend.
#
# Protocol vs ABC:
#   - Protocol uses structural typing — no explicit inheritance needed.
#   - Any class with matching method signatures automatically satisfies the Protocol.
#   - This means you can swap InMemoryTaskRepository for SqlAlchemyTaskRepository
#     in development, or RawSqlTaskRepository in production,
#     in the DI layer without changing a single line of the service class.
#
# Each method accepts and returns data objects (TaskCreate, TaskRecord, etc.)
# NOT raw dicts — this gives static type-checking across layer boundaries.

class TaskRepository(Protocol):
    """
    Interface (Protocol) for Task persistence.

    Any class that implements all of these methods satisfies this Protocol.
    """
    async def create(self, payload: TaskCreate, *, created_by: UUID) -> TaskRecord: ...
    async def get_by_id(self, task_id: UUID) -> TaskRecord | None: ...
    async def list(self, filters: TaskListFilters) -> list[TaskRecord]: ...
    async def update(self, task_id: UUID, payload: TaskUpdate) -> TaskRecord | None: ...
    async def set_status(self, task_id: UUID, new_status: TaskStatus) -> TaskRecord | None: ...
    async def delete(self, task_id: UUID) -> bool: ...


# ---------------------------------------------------------------------------
# 9. REPOSITORY — IN-MEMORY IMPLEMENTATION
# ---------------------------------------------------------------------------
# Used for development, demos, and unit tests.
# Not for production — single-process, not thread-safe, not persistent.

class InMemoryTaskRepository:
    """
    In-memory task store backed by a dict.

    Satisfies the TaskRepository Protocol structurally — no need to inherit.
    """

    def __init__(self) -> None:
        self._store: dict[UUID, TaskRecord] = {}

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
        self._store[task.id] = task
        return task

    async def get_by_id(self, task_id: UUID) -> TaskRecord | None:
        return self._store.get(task_id)

    async def list(self, filters: TaskListFilters) -> list[TaskRecord]:
        results = list(self._store.values())
        if filters.project_id  is not None:
            results = [t for t in results if t.project_id  == filters.project_id]
        if filters.assignee_id is not None:
            results = [t for t in results if t.assignee_id == filters.assignee_id]
        if filters.status      is not None:
            results = [t for t in results if t.status      == filters.status]
        return results[filters.offset : filters.offset + filters.limit]

    async def update(self, task_id: UUID, payload: TaskUpdate) -> TaskRecord | None:
        task = self._store.get(task_id)
        if task is None:
            return None
        # exclude_unset=True — only touch the fields the caller actually sent.
        # Without this, sending {"title": "x"} would also null out description.
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(task, field, value)
        task.updated_at = datetime.now(timezone.utc)
        return task

    async def set_status(self, task_id: UUID, new_status: TaskStatus) -> TaskRecord | None:
        task = self._store.get(task_id)
        if task is None:
            return None
        task.status     = new_status
        task.updated_at = datetime.now(timezone.utc)
        return task

    async def delete(self, task_id: UUID) -> bool:
        return self._store.pop(task_id, None) is not None


# ---------------------------------------------------------------------------
# 10. REPOSITORY — SQLAlchemy ASYNC IMPLEMENTATION (development/test stub)
# ---------------------------------------------------------------------------
# ORM implementation for development, local integration tests, and fixtures.
# Keep it behind the TaskRepository Protocol so it can be replaced by raw SQL
# at deployment time without changing service logic.
#
# class SqlAlchemyTaskRepository:
#     """
#     Async SQLAlchemy repository — satisfies TaskRepository Protocol.
#
#     Receives an AsyncSession from the DI layer (injected via Depends(get_db)).
#     Never creates its own session — sessions are request-scoped.
#     """
#
#     def __init__(self, session: AsyncSession) -> None:
#         self._session = session
#
#     async def create(self, payload: TaskCreate, *, created_by: UUID) -> TaskRecord:
#         now  = datetime.now(timezone.utc)
#         task = TaskModel(
#             id=uuid4(), title=payload.title, description=payload.description,
#             project_id=payload.project_id, assignee_id=payload.assignee_id,
#             status=TaskStatus.TODO, created_by=created_by,
#             created_at=now, updated_at=now,
#         )
#         self._session.add(task)
#         await self._session.flush()   # writes to DB but defers commit
#         return task.to_record()
#
#     async def get_by_id(self, task_id: UUID) -> TaskRecord | None:
#         # select() builds the query; scalars().first() returns one row or None.
#         result = await self._session.execute(
#             select(TaskModel).where(TaskModel.id == task_id)
#         )
#         task = result.scalars().first()
#         return task.to_record() if task else None
#
#     async def list(self, filters: TaskListFilters) -> list[TaskRecord]:
#         stmt = select(TaskModel)
#         if filters.project_id  is not None:
#             stmt = stmt.where(TaskModel.project_id  == filters.project_id)
#         if filters.assignee_id is not None:
#             stmt = stmt.where(TaskModel.assignee_id == filters.assignee_id)
#         if filters.status      is not None:
#             stmt = stmt.where(TaskModel.status      == filters.status)
#         stmt = stmt.offset(filters.offset).limit(filters.limit)
#         result = await self._session.execute(stmt)
#         return [row.to_record() for row in result.scalars().all()]
#
#     async def update(self, task_id: UUID, payload: TaskUpdate) -> TaskRecord | None:
#         delta = payload.model_dump(exclude_unset=True)
#         if not delta:
#             return await self.get_by_id(task_id)
#         delta["updated_at"] = datetime.now(timezone.utc)
#         await self._session.execute(
#             update(TaskModel).where(TaskModel.id == task_id).values(**delta)
#         )
#         return await self.get_by_id(task_id)
#
#     async def set_status(self, task_id: UUID, new_status: TaskStatus) -> TaskRecord | None:
#         await self._session.execute(
#             update(TaskModel)
#             .where(TaskModel.id == task_id)
#             .values(status=new_status, updated_at=datetime.now(timezone.utc))
#         )
#         return await self.get_by_id(task_id)
#
#     async def delete(self, task_id: UUID) -> bool:
#         result = await self._session.execute(
#             delete(TaskModel).where(TaskModel.id == task_id)
#         )
#         return result.rowcount > 0
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 10a. REPOSITORY — RAW SQL IMPLEMENTATION (production stub)
# ---------------------------------------------------------------------------
# Production implementation pattern. Use a connection pool and explicit SQL.
# This is more verbose than the ORM, but it removes ORM object hydration and
# unit-of-work overhead from hot paths, makes queries visible to review, and
# lets you tune SQL/index usage directly.
#
# class RawSqlTaskRepository:
#     """
#     Raw SQL repository — production implementation of TaskRepository.
#
#     Receives an asyncpg.Pool from the DI layer. A SQLAlchemy Core equivalent
#     using text() is also fine if you want SQLAlchemy-managed pooling without
#     the ORM.
#     """
#
#     def __init__(self, pool: asyncpg.Pool) -> None:
#         self._pool = pool
#
#     def _row_to_record(self, row: asyncpg.Record) -> TaskRecord:
#         return TaskRecord(
#             id=row["id"],
#             title=row["title"],
#             description=row["description"],
#             project_id=row["project_id"],
#             assignee_id=row["assignee_id"],
#             status=TaskStatus(row["status"]),
#             created_by=row["created_by"],
#             created_at=row["created_at"],
#             updated_at=row["updated_at"],
#         )
#
#     async def create(self, payload: TaskCreate, *, created_by: UUID) -> TaskRecord:
#         query = """
#             INSERT INTO tasks (id, title, description, project_id, assignee_id, status, created_by)
#             VALUES ($1, $2, $3, $4, $5, $6, $7)
#             RETURNING id, title, description, project_id, assignee_id, status,
#                       created_by, created_at, updated_at
#         """
#         async with self._pool.acquire() as conn:
#             row = await conn.fetchrow(
#                 query,
#                 uuid4(),
#                 payload.title,
#                 payload.description,
#                 payload.project_id,
#                 payload.assignee_id,
#                 TaskStatus.TODO.value,
#                 created_by,
#             )
#         return self._row_to_record(row)
#
#     async def get_by_id(self, task_id: UUID) -> TaskRecord | None:
#         query = """
#             SELECT id, title, description, project_id, assignee_id, status,
#                    created_by, created_at, updated_at
#             FROM tasks
#             WHERE id = $1
#         """
#         async with self._pool.acquire() as conn:
#             row = await conn.fetchrow(query, task_id)
#         return self._row_to_record(row) if row else None
#
#     async def list(self, filters: TaskListFilters) -> list[TaskRecord]:
#         clauses = []
#         values = []
#         if filters.project_id is not None:
#             values.append(filters.project_id)
#             clauses.append(f"project_id = ${len(values)}")
#         if filters.assignee_id is not None:
#             values.append(filters.assignee_id)
#             clauses.append(f"assignee_id = ${len(values)}")
#         if filters.status is not None:
#             values.append(filters.status.value)
#             clauses.append(f"status = ${len(values)}")
#
#         where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
#         values.extend([filters.limit, filters.offset])
#         limit_param = len(values) - 1
#         offset_param = len(values)
#         query = f"""
#             SELECT id, title, description, project_id, assignee_id, status,
#                    created_by, created_at, updated_at
#             FROM tasks
#             {where_sql}
#             ORDER BY created_at DESC
#             LIMIT ${limit_param} OFFSET ${offset_param}
#         """
#         async with self._pool.acquire() as conn:
#             rows = await conn.fetch(query, *values)
#         return [self._row_to_record(row) for row in rows]
#
#     async def update(self, task_id: UUID, payload: TaskUpdate) -> TaskRecord | None:
#         delta = payload.model_dump(exclude_unset=True)
#         if not delta:
#             return await self.get_by_id(task_id)
#
#         allowed_fields = ["title", "description", "assignee_id"]
#         assignments = []
#         values = []
#         for field in allowed_fields:
#             if field in delta:
#                 values.append(delta[field])
#                 assignments.append(f"{field} = ${len(values)}")
#
#         values.append(task_id)
#         task_id_param = len(values)
#         query = f"""
#             UPDATE tasks
#             SET {', '.join(assignments)}, updated_at = now()
#             WHERE id = ${task_id_param}
#             RETURNING id, title, description, project_id, assignee_id, status,
#                       created_by, created_at, updated_at
#         """
#         async with self._pool.acquire() as conn:
#             row = await conn.fetchrow(query, *values)
#         return self._row_to_record(row) if row else None
#
#     async def set_status(self, task_id: UUID, new_status: TaskStatus) -> TaskRecord | None:
#         query = """
#             UPDATE tasks
#             SET status = $2, updated_at = now()
#             WHERE id = $1
#             RETURNING id, title, description, project_id, assignee_id, status,
#                       created_by, created_at, updated_at
#         """
#         async with self._pool.acquire() as conn:
#             row = await conn.fetchrow(query, task_id, new_status.value)
#         return self._row_to_record(row) if row else None
#
#     async def delete(self, task_id: UUID) -> bool:
#         async with self._pool.acquire() as conn:
#             result = await conn.execute("DELETE FROM tasks WHERE id = $1", task_id)
#         return result == "DELETE 1"
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 11. ALEMBIC MIGRATION NOTES
# ---------------------------------------------------------------------------
# Alembic manages schema migrations — the SQL equivalent of "git for your schema".
#
# Setup:
#   alembic init alembic
#   # In alembic/env.py, set target_metadata = Base.metadata while the ORM
#   # model is the source of truth for schema generation.
#
# Production raw SQL note:
#   Even if deployed code uses RawSqlTaskRepository, keeping ORM models for
#   migration autogeneration can still be useful. The deploy artifact can
#   depend only on asyncpg/raw SQL while development tooling keeps SQLAlchemy.
#
# Workflow:
#   # Generate migration from model changes:
#   alembic revision --autogenerate -m "create tasks table"
#
#   # Apply migrations (run in CI and on deploy):
#   alembic upgrade head
#
#   # Roll back one migration:
#   alembic downgrade -1
#
# Initial migration for the Task model:
#   def upgrade():
#       op.create_table(
#           "tasks",
#           sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
#           sa.Column("title", sa.String(200), nullable=False),
#           sa.Column("description", sa.String(2000), nullable=True),
#           sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
#           sa.Column("assignee_id", postgresql.UUID(as_uuid=True), nullable=True),
#           sa.Column("status", sa.String(20), nullable=False, server_default="todo"),
#           sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
#           sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
#           sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
#       )
#       op.create_index("ix_tasks_project_id", "tasks", ["project_id"])
#       op.create_index("ix_tasks_assignee_id", "tasks", ["assignee_id"])
#       op.create_index("ix_tasks_status", "tasks", ["status"])
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 12. FASTAPI APP  (uses InMemoryTaskRepository)
# ---------------------------------------------------------------------------

SERVER_NAME = "api-example"


class ServerHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next) -> StarletteResponse:
        response = await call_next(request)
        response.headers["server"] = SERVER_NAME
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    # STUB: On startup, create tables / run migrations / warm pool
    # e.g. async with engine.begin() as conn:
    #          await conn.run_sync(Base.metadata.create_all)
    yield
    # STUB: On shutdown, close the engine
    # e.g. await engine.dispose()


app = FastAPI(
    title="Task API — Database Layer",
    version="1.0.0",
    description="Database model and repository reference implementation.",
    lifespan=lifespan,
)
app.add_middleware(ServerHeaderMiddleware)


# ---------------------------------------------------------------------------
# 13. ERROR HANDLERS
# ---------------------------------------------------------------------------

_HTTP_CODE_MAP: dict[int, str] = {
    400: "BAD_REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN",
    404: "NOT_FOUND", 409: "CONFLICT", 422: "VALIDATION_ERROR",
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
        content=_error_body("INTERNAL_SERVER_ERROR", "An unexpected error occurred."),
    )


# ---------------------------------------------------------------------------
# 14. DEPENDENCY INJECTION
# ---------------------------------------------------------------------------

_repository: InMemoryTaskRepository = InMemoryTaskRepository()


async def get_task_repository() -> InMemoryTaskRepository:
    """
    Return the singleton in-memory repository.

    Development/test: swap for SqlAlchemyTaskRepository.
    Production: swap for RawSqlTaskRepository.
    """
    return _repository


async def get_current_user_id() -> UUID:
    """Placeholder — replace with real JWT auth in production."""
    return UUID("00000000-0000-0000-0000-000000000001")


RepoDep       = Annotated[InMemoryTaskRepository, Depends(get_task_repository)]
CurrentUserId = Annotated[UUID,                   Depends(get_current_user_id)]


# ---------------------------------------------------------------------------
# 15. ROUTES
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Task not found")


@router.post("/", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload:         TaskCreate,
    repo:            RepoDep,
    current_user_id: CurrentUserId,
) -> TaskRead:
    task = await repo.create(payload, created_by=current_user_id)
    return TaskRead.model_validate(task)


@router.get("/", response_model=list[TaskRead])
async def list_tasks(repo: RepoDep, current_user_id: CurrentUserId) -> list[TaskRead]:
    tasks = await repo.list(TaskListFilters())
    return [TaskRead.model_validate(t) for t in tasks]


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(task_id: UUID, repo: RepoDep) -> TaskRead:
    task = await repo.get_by_id(task_id)
    if task is None:
        raise _not_found()
    return TaskRead.model_validate(task)


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(task_id: UUID, payload: TaskUpdate, repo: RepoDep) -> TaskRead:
    task = await repo.update(task_id, payload)
    if task is None:
        raise _not_found()
    return TaskRead.model_validate(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: UUID, repo: RepoDep) -> None:
    if not await repo.delete(task_id):
        raise _not_found()


@app.get("/healthz", tags=["ops"])
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz", tags=["ops"])
async def readyz() -> dict[str, str]:
    # STUB: In production, also check DB connectivity:
    #   await session.execute(text("SELECT 1"))
    return {"status": "ready"}


app.include_router(router)


# ---------------------------------------------------------------------------
# 16. SELF-TESTS  (run with: python3 database_example.py)
# ---------------------------------------------------------------------------

def _sep(title: str) -> None:
    print(f"\n{'─' * 60}\n  {title}\n{'─' * 60}")

def _ok(msg: str)   -> None: print(f"  ✔  {msg}")
def _fail(msg: str) -> None: print(f"  ✘  {msg}")


async def _run_tests() -> None:
    repo    = InMemoryTaskRepository()
    user_id = uuid4()
    proj_id = uuid4()

    # ---- create ----
    _sep("create")
    payload = TaskCreate(title="Implement DB layer", project_id=proj_id)
    task    = await repo.create(payload, created_by=user_id)
    assert task.title      == "Implement DB layer"
    assert task.status     == TaskStatus.TODO
    assert task.created_by == user_id
    _ok(f"Created task {str(task.id)[:8]}...  status={task.status}")

    # ---- get_by_id ----
    _sep("get_by_id")
    fetched = await repo.get_by_id(task.id)
    assert fetched is not None
    assert fetched.id == task.id
    _ok("get_by_id returned correct task")

    missing = await repo.get_by_id(uuid4())
    assert missing is None
    _ok("get_by_id returns None for unknown UUID")

    # ---- update — only changed fields ----
    _sep("update (exclude_unset=True)")
    updated = await repo.update(task.id, TaskUpdate(title="New title"))
    assert updated is not None
    assert updated.title       == "New title"
    assert updated.description == task.description  # unchanged
    _ok(f"Title updated; description untouched: {updated.description!r}")

    # ---- set_status ----
    _sep("set_status")
    started = await repo.set_status(task.id, TaskStatus.IN_PROGRESS)
    assert started is not None
    assert started.status == TaskStatus.IN_PROGRESS
    _ok(f"Status set to {started.status}")

    # ---- list with filters ----
    _sep("list with filters")
    task2 = await repo.create(
        TaskCreate(title="Another task", project_id=proj_id),
        created_by=user_id,
    )
    all_tasks = await repo.list(TaskListFilters())
    assert len(all_tasks) == 2
    _ok(f"List all: {len(all_tasks)} tasks")

    proj_tasks = await repo.list(TaskListFilters(project_id=proj_id))
    assert len(proj_tasks) == 2
    _ok(f"Filter by project_id: {len(proj_tasks)} tasks")

    todo_tasks = await repo.list(TaskListFilters(status=TaskStatus.TODO))
    assert len(todo_tasks) == 1
    assert todo_tasks[0].id == task2.id
    _ok(f"Filter by status=TODO: {len(todo_tasks)} task(s)")

    # ---- pagination ----
    _sep("pagination (limit/offset)")
    page1 = await repo.list(TaskListFilters(limit=1, offset=0))
    page2 = await repo.list(TaskListFilters(limit=1, offset=1))
    assert len(page1) == 1
    assert len(page2) == 1
    assert page1[0].id != page2[0].id
    _ok("Pagination: limit=1 offset=0 and offset=1 return different tasks")

    # ---- delete ----
    _sep("delete")
    deleted = await repo.delete(task2.id)
    assert deleted is True
    assert await repo.get_by_id(task2.id) is None
    _ok("Task deleted and no longer retrievable")

    not_deleted = await repo.delete(uuid4())
    assert not_deleted is False
    _ok("Deleting unknown UUID returns False")

    # ---- __slots__ check ----
    _sep("TaskRecord __slots__")
    assert hasattr(task, "__slots__")
    _ok(f"TaskRecord uses __slots__: {task.__slots__}")

    print("\n  All repository tests passed.\n")


if __name__ == "__main__":
    asyncio.run(_run_tests())
