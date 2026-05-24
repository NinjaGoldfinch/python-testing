"""
fastapi_example.py
==================
A documented reference implementation for a modern Python REST API using the
recommended 2026 stack:

    FastAPI + Pydantic + SQLAlchemy 2.x (async) + Alembic + PostgreSQL + Uvicorn

Run locally:
    python3 -m uvicorn fastapi_example:app --reload --no-server-header

Interactive docs (auto-generated):
    http://127.0.0.1:8000/docs   (Swagger UI)
    http://127.0.0.1:8000/redoc  (ReDoc)

Project layout (for a real service, split this into modules):
    app/    
      main.py
      api/v1/routes/items.py
      core/config.py
      db/session.py
      db/models.py
      schemas/item.py
      services/items.py
      repositories/items.py
      tests/test_items.py
    alembic/versions/
    pyproject.toml
"""

# ---------------------------------------------------------------------------
# 1. IMPORTS
# ---------------------------------------------------------------------------
# Core FastAPI objects — import only what you use.
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI,       # Main application object
    APIRouter,     # Modular route groups (one per resource)
    Depends,       # Dependency injection: DB sessions, auth, config
    HTTPException, # Raises HTTP error responses with status + detail
    Query,         # Declare query-string parameters with validation
    Path,          # Declare path parameters with validation
    Body,          # Declare body parameters explicitly
    Header,        # Declare HTTP header parameters
    status,        # Named HTTP status code constants (e.g. status.HTTP_201_CREATED)
)

# Pydantic — drives request/response validation and OpenAPI schema generation.
from pydantic import BaseModel, Field, EmailStr, ConfigDict

# Standard library types — Pydantic understands all of these.
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

# ---------------------------------------------------------------------------
# STUB: For a real async DB layer you would also import:
#
#   from sqlalchemy.ext.asyncio import (
#       AsyncSession,
#       create_async_engine,
#       async_sessionmaker,
#   )
#   from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
#   from sqlalchemy import select
#
# And for settings:
#   from pydantic_settings import BaseSettings
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 2. LIFESPAN & APP CREATION
# ---------------------------------------------------------------------------
# Use the lifespan context manager instead of the deprecated @app.on_event.
# Code before `yield` runs on startup; code after `yield` runs on shutdown.

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    # STUB: initialise DB connection pool, warm caches, run health checks, etc.
    #   await engine.connect()
    yield
    # --- shutdown ---
    # STUB: drain connection pools, flush buffers, close clients.
    #   await engine.dispose()


app = FastAPI(
    title="Items API",
    version="1.0.0",
    description="Reference FastAPI service — documented stubs and patterns.",
    lifespan=lifespan,
    # Disable docs in production if needed:
    # docs_url=None, redoc_url=None,
)

# ---------------------------------------------------------------------------
# 2a. SERVER HEADER  (security hardening — hide implementation details)
# ---------------------------------------------------------------------------
# Exposing "server: uvicorn" (or "nginx/1.x.x", "gunicorn/x.x") tells
# attackers exactly what software you run and which CVEs to target.
# Best practice: replace it with a neutral, opaque identifier.
#
# Strategy depends on where TLS terminates and which process is public-facing:
#
#  ┌──────────────────┬──────────────────────────────────────────────────────┐
#  │ Layer            │ How to override the Server header                    │
#  ├──────────────────┼──────────────────────────────────────────────────────┤
#  │ FastAPI/         │ Middleware below — always runs regardless of what    │
#  │ Starlette        │ sits in front (catches the header at ASGI layer).    │
#  ├──────────────────┼──────────────────────────────────────────────────────┤
#  │ Uvicorn          │ --no-server-header MUST be set — without it uvicorn  │
#  │ (direct)         │ injects its own "Server: uvicorn" at the transport   │
#  │                  │ level before the ASGI middleware can act, producing  │
#  │                  │ two Server headers. Suppress it with:                │
#  │                  │   uvicorn fastapi_example:app --no-server-header     │
#  │                  │ Or in code: uvicorn.run(app, server_header=False)    │
#  ├──────────────────┼──────────────────────────────────────────────────────┤
#  │ Gunicorn +       │ Use --no-server-header flag (Gunicorn ≥ 22) and let │
#  │ uvicorn workers  │ the middleware below set yours.                      │
#  ├──────────────────┼──────────────────────────────────────────────────────┤
#  │ Nginx            │ Requires ngx_headers_more module for full control:   │
#  │                  │   server_tokens off;         # removes version info  │
#  │                  │   more_set_headers "Server: api-example";            │
#  │                  │ Without that module, use proxy directives instead:   │
#  │                  │   location / {                                       │
#  │                  │       proxy_pass http://127.0.0.1:8000;              │
#  │                  │       proxy_hide_header Server;                      │
#  │                  │       add_header Server "api-example" always;        │
#  │                  │   }                                                  │
#  ├──────────────────┼──────────────────────────────────────────────────────┤
#  │ Caddy            │ Caddy strips its own Server header by default;       │
#  │                  │ set a custom one in your Caddyfile:                  │
#  │                  │   header Server "api-example"                        │
#  ├──────────────────┼──────────────────────────────────────────────────────┤
#  │ AWS ALB /        │ ALB does not expose or allow customising the Server  │
#  │ CloudFront       │ header — rely on the FastAPI middleware layer.       │
#  └──────────────────┴──────────────────────────────────────────────────────┘
#
# The middleware below is the safest cross-layer solution: it always fires
# regardless of proxy configuration, and works in development too.

SERVER_NAME = "api-example"  # change per deployment, e.g. "api-1", "api-prod"

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse


class ServerHeaderMiddleware(BaseHTTPMiddleware):
    """Replace the Server response header with a neutral, opaque value."""

    async def dispatch(self, request: StarletteRequest, call_next) -> StarletteResponse:
        response = await call_next(request)
        response.headers["server"] = SERVER_NAME
        return response


app.add_middleware(ServerHeaderMiddleware)

# STUB: Add other middleware here, e.g. CORS, compression, trusted-host.
#
#   from fastapi.middleware.cors import CORSMiddleware
#   app.add_middleware(
#       CORSMiddleware,
#       allow_origins=["https://yourfrontend.com"],
#       allow_methods=["*"],
#       allow_headers=["*"],
#   )


# ---------------------------------------------------------------------------
# 3. ERROR RESPONSE SCHEMA & HANDLERS
# ---------------------------------------------------------------------------
# FastAPI's default error body is {"detail": "..."}  — fine for development
# but too thin for production clients. A consistent envelope gives callers
# a predictable structure to parse regardless of error type.
#
# Envelope shape:
#   {
#     "error": {
#       "code":    "NOT_FOUND",          # machine-readable constant
#       "message": "Item not found",     # human-readable description
#       "details": [...]                 # optional list (used by validation errors)
#     }
#   }

import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

# Map HTTP status codes to short machine-readable codes used in "code" field.
_HTTP_CODE_MAP: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",        # resource not found (raised explicitly in routes)
    # 404 from routing → overridden to ROUTE_NOT_FOUND in the handler below
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "TOO_MANY_REQUESTS",
    500: "INTERNAL_SERVER_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


def _error_body(code: str, message: str, details: list | None = None) -> dict:
    payload: dict = {"code": code, "message": message}
    if details:
        payload["details"] = details
    return {"error": payload}


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Convert HTTPException into the structured error envelope."""
    code = _HTTP_CODE_MAP.get(exc.status_code, "HTTP_ERROR")
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)

    # Starlette emits a generic "Not Found" when no route matches the path.
    # Replace it with a message that includes the method and path so the caller
    # can immediately see what they got wrong.
    if exc.status_code == 404 and message == "Not Found":
        message = f"{request.method} {request.url.path} is not a valid API path"
        code = "ROUTE_NOT_FOUND"

    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(code, message),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Convert Pydantic validation failures into structured errors with per-field details."""
    details = [
        {
            "field": " → ".join(str(p) for p in err["loc"]),
            "message": err["msg"],
            "type": err["type"],
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=_error_body(
            "VALIDATION_ERROR",
            f"{len(details)} validation error(s) in request",
            details,
        ),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: log the full traceback, return a safe 500 to the client."""
    logger.exception("Unhandled exception for %s %s", request.method, request.url)
    return JSONResponse(
        status_code=500,
        content=_error_body(
            "INTERNAL_SERVER_ERROR",
            "An unexpected error occurred. Please try again later.",
        ),
    )


# ---------------------------------------------------------------------------
# 4. PYDANTIC SCHEMAS  (live in schemas/*.py in a real project)
# ---------------------------------------------------------------------------
# Keep request schemas (Create/Update) separate from response schemas (Read).
# Never expose raw DB model objects directly to the API layer.

class ItemCreate(BaseModel):
    """Validated input for creating an item. Used as POST body."""
    name: str = Field(min_length=1, max_length=100, examples=["Widget"])
    price: Decimal = Field(gt=0, decimal_places=2, examples=["9.99"])
    # Literal constrains to a fixed set of string values.
    category: Literal["hardware", "software", "service"] = "hardware"


class ItemUpdate(BaseModel):
    """Partial update schema (PATCH). All fields are optional."""
    name: str | None = Field(default=None, min_length=1, max_length=100)
    price: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    category: Literal["hardware", "software", "service"] | None = None


class ItemRead(BaseModel):
    """Response schema returned to API callers."""
    # ConfigDict(from_attributes=True) lets Pydantic read from ORM model
    # attributes directly (previously called orm_mode=True in v1).
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    price: Decimal
    category: str
    created_at: datetime


# STUB: A more complete schema set would also include:
#
#   class ItemList(BaseModel):
#       items: list[ItemRead]
#       total: int
#       page: int
#       page_size: int
#
#   class ErrorDetail(BaseModel):
#       code: str
#       message: str


# ---------------------------------------------------------------------------
# 4. FAKE IN-MEMORY DATABASE
# ---------------------------------------------------------------------------
# Replace this with an async SQLAlchemy session in a real service.
# See section 5 (Dependency Injection) for the DB session pattern.

_fake_db: dict[UUID, ItemRead] = {}


# ---------------------------------------------------------------------------
# 5. DEPENDENCY INJECTION  (live in core/ or db/ in a real project)
# ---------------------------------------------------------------------------
# Depends() is FastAPI's DI mechanism — use it for DB sessions, auth, config.

# STUB: Real async DB session dependency (requires SQLAlchemy + asyncpg):
#
#   engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/db")
#   AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
#
#   async def get_db() -> AsyncGenerator[AsyncSession, None]:
#       async with AsyncSessionLocal() as session:
#           yield session
#
#   DBSession = Annotated[AsyncSession, Depends(get_db)]
#
# Then in a route:
#   async def create_item(payload: ItemCreate, db: DBSession): ...

# STUB: Auth dependency (JWT bearer token):
#
#   from fastapi.security import OAuth2PasswordBearer
#   oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/token")
#
#   async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserRead:
#       payload = verify_jwt(token)  # raises 401 on failure
#       return await user_repo.get(payload["sub"])
#
#   CurrentUser = Annotated[UserRead, Depends(get_current_user)]


# ---------------------------------------------------------------------------
# 6. ROUTER  (live in api/v1/routes/items.py in a real project)
# ---------------------------------------------------------------------------
# APIRouter groups related routes. The main app includes them with a prefix.
# Tags group routes in the Swagger UI.

router = APIRouter(prefix="/v1/items", tags=["items"])


# GET /v1/items  —  list resources
@router.get(
    "/",
    response_model=list[ItemRead],
    summary="List all items",
)
async def list_items(
    # Query parameters with validation via Query()
    limit: int = Query(default=20, ge=1, le=100, description="Max items to return"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
    # STUB: add category filter:
    # category: str | None = Query(default=None),
) -> list[ItemRead]:
    """Return a paginated list of items."""
    items = list(_fake_db.values())
    return items[offset : offset + limit]


# POST /v1/items  —  create resource
@router.post(
    "/",
    response_model=ItemRead,
    status_code=status.HTTP_201_CREATED,  # 201 Created, not 200
    summary="Create a new item",
)
async def create_item(
    payload: ItemCreate,
    # STUB: add auth dependency:
    # current_user: CurrentUser,
    # STUB: add DB session dependency:
    # db: DBSession,
) -> ItemRead:
    """
    Create an item. Returns 201 with the created resource.

    In a real service this would:
      1. Call a service function (services/items.py)
      2. Which calls a repository function (repositories/items.py)
      3. Which executes: session.add(item); await session.commit()
    """
    item = ItemRead(
        id=uuid4(),
        created_at=datetime.utcnow(),
        **payload.model_dump(),
    )
    _fake_db[item.id] = item
    return item


# GET /v1/items/{item_id}  —  retrieve one resource
@router.get(
    "/{item_id}",
    response_model=ItemRead,
    summary="Get a single item by ID",
    responses={
        404: {
            "description": "Item not found",
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "code": "NOT_FOUND",
                            "message": "Item not found",
                        }
                    }
                }
            },
        },
    },
)
async def get_item(
    # Path() lets you add validation and docs to path parameters.
    item_id: UUID = Path(description="The UUID of the item"),
) -> ItemRead:
    """Fetch a single item. Raises 404 if it does not exist."""
    item = _fake_db.get(item_id)
    if item is None:
        # HTTPException is caught by http_exception_handler → structured error envelope
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return item


# PUT /v1/items/{item_id}  —  full replacement
@router.put(
    "/{item_id}",
    response_model=ItemRead,
    summary="Replace an item (full update)",
)
async def replace_item(item_id: UUID, payload: ItemCreate) -> ItemRead:
    """Replace all fields of an existing item. Raises 404 if absent."""
    if item_id not in _fake_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    item = ItemRead(id=item_id, created_at=_fake_db[item_id].created_at, **payload.model_dump())
    _fake_db[item_id] = item
    return item


# PATCH /v1/items/{item_id}  —  partial update
@router.patch(
    "/{item_id}",
    response_model=ItemRead,
    summary="Partially update an item",
)
async def update_item(item_id: UUID, payload: ItemUpdate) -> ItemRead:
    """
    Apply a partial update. Only provided fields are changed.

    Pattern: model_dump(exclude_unset=True) drops fields the caller
    didn't include — avoids accidentally nulling out existing values.
    """
    existing = _fake_db.get(item_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    updated_data = existing.model_dump()
    updated_data.update(payload.model_dump(exclude_unset=True))
    item = ItemRead(**updated_data)
    _fake_db[item_id] = item
    return item


# DELETE /v1/items/{item_id}  —  delete resource
@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,  # 204 = success, no body
    summary="Delete an item",
)
async def delete_item(item_id: UUID) -> None:
    """Delete an item. Returns 204 No Content on success."""
    if item_id not in _fake_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    del _fake_db[item_id]


# ---------------------------------------------------------------------------
# 7. HEALTH / READINESS ENDPOINTS  (required for production)
# ---------------------------------------------------------------------------

@app.get("/healthz", tags=["ops"], summary="Liveness probe")
async def healthz() -> dict[str, str]:
    """Returns 200 OK if the process is alive. Used by load balancers."""
    return {"status": "ok"}


@app.get("/readyz", tags=["ops"], summary="Readiness probe")
async def readyz() -> dict[str, str]:
    """
    Returns 200 OK if the service is ready to accept traffic.

    STUB: In production, also check DB connectivity:
      try:
          await db.execute(select(1))
      except Exception:
          raise HTTPException(status_code=503, detail="DB unavailable")
    """
    return {"status": "ready"}


# ---------------------------------------------------------------------------
# 8. INCLUDE ROUTER
# ---------------------------------------------------------------------------
# In a bigger app, you'd include multiple routers here.

app.include_router(router)

# STUB: add more routers as the API grows:
#   from app.api.v1.routes import users, orders
#   app.include_router(users.router)
#   app.include_router(orders.router)


# ---------------------------------------------------------------------------
# 9. STARTUP / SHUTDOWN EVENTS
# ---------------------------------------------------------------------------
# Handled via the `lifespan` context manager defined at the top of this file.
# See section 2 for the startup/shutdown stubs.


# ---------------------------------------------------------------------------
# 10. TESTING STUBS  (live in tests/ in a real project)
# ---------------------------------------------------------------------------
# FastAPI tests use either TestClient (sync) or httpx.AsyncClient (async).
#
#   # tests/test_items.py
#   import pytest
#   from fastapi.testclient import TestClient
#   from fastapi_example import app
#
#   client = TestClient(app)
#
#   def test_create_and_fetch_item():
#       response = client.post(
#           "/v1/items/",
#           json={"name": "Widget", "price": "9.99", "category": "hardware"},
#       )
#       assert response.status_code == 201
#       item_id = response.json()["id"]
#
#       response = client.get(f"/v1/items/{item_id}")
#       assert response.status_code == 200
#       assert response.json()["name"] == "Widget"
#
#   def test_get_missing_item_returns_404():
#       response = client.get("/v1/items/00000000-0000-0000-0000-000000000000")
#       assert response.status_code == 404
#
# For async tests with pytest-asyncio + httpx:
#
#   @pytest.mark.asyncio
#   async def test_list_items():
#       async with httpx.AsyncClient(
#           transport=httpx.ASGITransport(app=app), base_url="http://test"
#       ) as ac:
#           r = await ac.get("/v1/items/")
#       assert r.status_code == 200


# ---------------------------------------------------------------------------
# 11. DATABASE STUBS  (live in db/ in a real project)
# ---------------------------------------------------------------------------
#
# db/session.py
# -------------
#   from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
#
#   DATABASE_URL = "postgresql+asyncpg://user:pass@localhost/db"
#   engine = create_async_engine(DATABASE_URL, pool_size=10, max_overflow=20)
#   AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
#
# db/models.py
# ------------
#   from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
#   from sqlalchemy import func
#   import uuid
#
#   class Base(DeclarativeBase):
#       pass
#
#   class Item(Base):
#       __tablename__ = "items"
#
#       id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
#       name: Mapped[str]
#       price: Mapped[Decimal]
#       category: Mapped[str]
#       created_at: Mapped[datetime] = mapped_column(server_default=func.now())
#
# Alembic migrations:
#   alembic revision --autogenerate -m "create items table"
#   alembic upgrade head


# ---------------------------------------------------------------------------
# 12. HTTP STATUS CODE REFERENCE
# ---------------------------------------------------------------------------
# 200 OK                  — successful read / update
# 201 Created             — successful creation (POST)
# 204 No Content          — successful delete (no response body)
# 400 Bad Request         — malformed input
# 401 Unauthorized        — missing / invalid auth token
# 403 Forbidden           — authenticated but not allowed
# 404 Not Found           — resource absent
# 409 Conflict            — duplicate / invalid state transition
# 422 Unprocessable Entity — Pydantic validation failure (automatic)
# 500 Internal Server Error — unexpected server failure


# ---------------------------------------------------------------------------
# 13. PRODUCTION CHECKLIST
# ---------------------------------------------------------------------------
# [ ] OpenAPI docs reviewed
# [ ] Request/response schemas separated from DB models
# [ ] Alembic migrations in CI
# [ ] Structured logging (structlog)
# [ ] Health endpoint: /healthz
# [ ] Readiness endpoint: /readyz
# [ ] Auth and authorization tests
# [ ] CORS configured explicitly
# [ ] Rate limiting if public
# [ ] Timeouts on outbound HTTP calls
# [ ] Database connection pooling
# [ ] Error handling middleware
# [ ] Dependency scanning
# [ ] Container image with non-root user
# [ ] Uvicorn/Gunicorn worker config tested
# [ ] Observability: logs, metrics, traces
