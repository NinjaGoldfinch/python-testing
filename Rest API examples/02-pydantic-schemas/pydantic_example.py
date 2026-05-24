"""
pydantic_example.py
===================
A documented reference implementation for Pydantic v2 API validation,
following the same layered pattern as the FastAPI example.

Purpose of this file:
    Demonstrate every Pydantic v2 pattern needed to build a production API
    contract layer — schemas, field constraints, custom validators,
    serialization, and integration with the service/repository layers.

Run the self-tests:
    python3 pydantic_example.py

Implementation order (for a full service):
    1. FastAPI app + routers
    2. Pydantic schemas          ← this file
    3. Service methods
    4. Repository / database
    5. Dependency injection
    6. Error handling
    7. Auth / permissions
    8. Tests
    9. Observability + deployment
"""

# ---------------------------------------------------------------------------
# 1. IMPORTS
# ---------------------------------------------------------------------------
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,       # Base class for all schemas
    ConfigDict,      # Model-level configuration (replaces class Config in v1)
    EmailStr,        # Validates email format (requires: pip install pydantic[email])
    Field,           # Attach metadata: default, constraints, description, examples
    field_validator, # Per-field custom validation logic (replaces @validator in v1)
    model_validator, # Cross-field / whole-model validation (replaces @root_validator)
    computed_field,  # Read-only derived properties exposed in the schema
    AliasChoices,    # Accept multiple input key names for one field
    field_serializer,# Custom serialization logic per field
)
from pydantic import ValidationError  # Raised when input fails validation


# ---------------------------------------------------------------------------
# 2. ENUMS
# ---------------------------------------------------------------------------
# Use Python Enum + Pydantic for categorical fields.
# Enum values appear in the OpenAPI schema as allowed constants.

class Category(str, Enum):
    """Valid item categories. Inheriting str makes it JSON-serialisable."""
    hardware = "hardware"
    software = "software"
    service  = "service"


class OrderStatus(str, Enum):
    pending   = "pending"
    confirmed = "confirmed"
    shipped   = "shipped"
    delivered = "delivered"
    cancelled = "cancelled"


# ---------------------------------------------------------------------------
# 3. REUSABLE ANNOTATED TYPES
# ---------------------------------------------------------------------------
# Annotated lets you attach Field constraints to a type alias so you don't
# repeat the same Field(min_length=...) on every model that uses it.

ShortStr   = Annotated[str, Field(min_length=1, max_length=100)]
LongStr    = Annotated[str, Field(min_length=1, max_length=2000)]
PositiveDecimal = Annotated[Decimal, Field(gt=0, decimal_places=2)]


# ---------------------------------------------------------------------------
# 4. REQUEST SCHEMAS (input — sent by the client)
# ---------------------------------------------------------------------------
# Separate Create and Update schemas:
#   - Create: all required fields
#   - Update: all optional fields (for PATCH — only send what changes)
#
# Never use the same schema for both: Create implies presence, Update implies
# optionality. Mixing them forces awkward Optional fields everywhere.

class ItemCreate(BaseModel):
    """
    Validated input for creating an item (POST body).

    All fields are required unless a default is specified.
    Pydantic validates types and constraints before the route handler runs.
    """
    name:     ShortStr
    price:    PositiveDecimal
    category: Category = Category.hardware

    # Field() adds constraints, descriptions, and examples for OpenAPI docs.
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional longer description of the item",
        examples=["A high-quality widget suitable for all uses."],
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Free-form tags for filtering",
    )

    # ----- custom field validator -------------------------------------------
    # @field_validator runs after type coercion.
    # mode="before"  → runs on the raw input value (before type conversion)
    # mode="after"   → runs on the already-typed value (default)

    @field_validator("name", mode="after")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        if v.strip() == "":
            raise ValueError("name must not be blank or whitespace only")
        return v.strip()

    @field_validator("tags", mode="after")
    @classmethod
    def tags_must_be_unique(cls, v: list[str]) -> list[str]:
        seen = set()
        unique = []
        for tag in v:
            normalised = tag.lower().strip()
            if normalised not in seen:
                seen.add(normalised)
                unique.append(tag)
        return unique


class ItemUpdate(BaseModel):
    """
    Partial update schema for PATCH requests.

    All fields are optional — the caller only sends the fields they want to
    change. Use model_dump(exclude_unset=True) in the service layer to get
    only the supplied fields, avoiding accidental nulling of existing data.
    """
    name:        ShortStr | None = None
    price:       PositiveDecimal | None = None
    category:    Category | None = None
    description: str | None = Field(default=None, max_length=2000)
    tags:        list[str] | None = None

    @field_validator("name", mode="after")
    @classmethod
    def name_must_not_be_blank(cls, v: str | None) -> str | None:
        if v is not None and v.strip() == "":
            raise ValueError("name must not be blank")
        return v.strip() if v else v


# ---------------------------------------------------------------------------
# 5. RESPONSE SCHEMAS (output — sent to the client)
# ---------------------------------------------------------------------------
# Response schemas may include derived fields (computed_field) and should
# never expose internal fields (DB primary keys in different forms, passwords,
# internal flags, etc.).

class ItemRead(BaseModel):
    """
    Response schema for a single item.

    ConfigDict(from_attributes=True) allows Pydantic to read from ORM model
    attributes directly (e.g. SQLAlchemy objects), without manually calling
    model_dump() first. Previously called orm_mode=True in Pydantic v1.
    """
    model_config = ConfigDict(from_attributes=True)

    id:          UUID
    name:        str
    price:       Decimal
    category:    Category
    description: str | None
    tags:        list[str]
    created_at:  datetime

    # computed_field adds a read-only derived property to the schema and docs.
    @computed_field
    @property
    def display_price(self) -> str:
        """Human-friendly price string, e.g. '$9.99'."""
        return f"${self.price:.2f}"

    # field_serializer customises how a specific field is serialised to JSON.
    # Here we ensure Decimal always renders with 2 decimal places.
    @field_serializer("price")
    def serialise_price(self, value: Decimal) -> str:
        return f"{value:.2f}"


class ItemListRead(BaseModel):
    """Paginated list response — wrap collections in an envelope."""
    items:   list[ItemRead]
    total:   int
    page:    int
    per_page: int

    @computed_field
    @property
    def has_next(self) -> bool:
        return (self.page * self.per_page) < self.total


# ---------------------------------------------------------------------------
# 6. QUERY / FILTER SCHEMAS
# ---------------------------------------------------------------------------
# Use a BaseModel for query parameters in FastAPI — it groups related params,
# provides validation, and appears cleanly in OpenAPI docs.
#
#   @router.get("/")
#   async def list_items(filters: Annotated[ItemFilters, Query()]) -> ...:

class ItemFilters(BaseModel):
    """Query parameters for filtering and paginating the items list."""
    model_config = ConfigDict(populate_by_name=True)

    category: Category | None = None
    min_price: PositiveDecimal | None = Field(default=None, alias="minPrice")
    max_price: PositiveDecimal | None = Field(
        default=None,
        # AliasChoices accepts both "maxPrice" and "max_price" from the client.
        validation_alias=AliasChoices("maxPrice", "max_price"),
    )
    page:     int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)

    # ----- cross-field / model-level validator ------------------------------
    # @model_validator runs after all fields are validated.
    # mode="after"  → receives the fully validated model instance
    # mode="before" → receives the raw input dict

    @model_validator(mode="after")
    def price_range_must_be_valid(self) -> ItemFilters:
        if self.min_price is not None and self.max_price is not None:
            if self.min_price > self.max_price:
                raise ValueError("min_price must be less than or equal to max_price")
        return self


# ---------------------------------------------------------------------------
# 7. NESTED SCHEMAS
# ---------------------------------------------------------------------------
# Pydantic models can be nested — they validate and document recursively.

class AddressCreate(BaseModel):
    """Nested address schema used inside OrderCreate."""
    line1:   ShortStr
    line2:   str | None = None
    city:    ShortStr
    country: Annotated[str, Field(min_length=2, max_length=2, description="ISO 3166-1 alpha-2")]
    postcode: ShortStr


class OrderItemCreate(BaseModel):
    item_id:  UUID
    quantity: int = Field(ge=1, le=999)


class OrderCreate(BaseModel):
    """Order with nested line-items and a shipping address."""
    items:            list[OrderItemCreate] = Field(min_length=1)
    shipping_address: AddressCreate
    notes:            str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def no_duplicate_items(self) -> OrderCreate:
        ids = [i.item_id for i in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate item_id entries in order")
        return self


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:               UUID
    items:            list[OrderItemCreate]
    shipping_address: AddressCreate
    status:           OrderStatus
    notes:            str | None
    created_at:       datetime


# ---------------------------------------------------------------------------
# 8. ERROR RESPONSE SCHEMA
# ---------------------------------------------------------------------------
# Having a Pydantic model for errors means the error shape is validated and
# appears correctly in the OpenAPI schema.

class ErrorDetail(BaseModel):
    """One validation error for a specific field."""
    field:   str
    message: str
    type:    str


class ErrorResponse(BaseModel):
    """Standard error envelope returned by all error handlers."""
    code:    str
    message: str
    details: list[ErrorDetail] = []


class ErrorEnvelope(BaseModel):
    """Top-level wrapper — matches the {'error': {...}} shape."""
    error: ErrorResponse


# ---------------------------------------------------------------------------
# 9. KEY PYDANTIC v2 METHODS
# ---------------------------------------------------------------------------
# model_dump()                → dict (Python-native types)
# model_dump_json()           → JSON string
# model_dump(exclude_unset=True)    → only fields the caller provided (PATCH)
# model_dump(exclude_none=True)     → drop null fields from output
# model_dump(mode="json")           → dict with JSON-safe types (UUIDs as str, etc.)
# Model.model_validate(obj)         → parse from dict or ORM object
# Model.model_validate_json(s)      → parse from JSON string
# Model.model_json_schema()         → OpenAPI-compatible JSON Schema dict
#
# See section 10 for live examples.


# ---------------------------------------------------------------------------
# 10. SELF-TESTS  (run with: python3 pydantic_example.py)
# ---------------------------------------------------------------------------

def _separator(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print('─' * 60)


def demo_item_create() -> None:
    _separator("ItemCreate — valid input")
    item = ItemCreate(
        name="  Widget  ",          # whitespace stripped by validator
        price="9.99",
        category="hardware",
        tags=["sale", "SALE", "new"],  # duplicates removed by validator
    )
    print("  model_dump():", item.model_dump())
    print("  tags (deduped):", item.tags)
    print("  name (stripped):", repr(item.name))


def demo_item_create_invalid() -> None:
    _separator("ItemCreate — validation errors")
    try:
        ItemCreate(name="", price="-5.00", category="unknown")
    except ValidationError as exc:
        for err in exc.errors():
            loc = " → ".join(str(p) for p in err["loc"])
            print(f"  [{loc}] {err['msg']}  (type: {err['type']})")


def demo_item_update_patch() -> None:
    _separator("ItemUpdate — PATCH (exclude_unset=True)")
    patch = ItemUpdate(price="14.99")
    full  = patch.model_dump()
    delta = patch.model_dump(exclude_unset=True)
    print("  model_dump()            :", full)
    print("  model_dump(exclude_unset):", delta)
    print("  → only 'price' would be updated in the DB")


def demo_item_read_computed() -> None:
    _separator("ItemRead — computed_field + field_serializer")
    read = ItemRead(
        id=uuid4(),
        name="Widget",
        price=Decimal("9.99"),
        category=Category.hardware,
        description=None,
        tags=["sale"],
        created_at=datetime.now(timezone.utc),
    )
    print("  display_price:", read.display_price)
    print("  model_dump_json():", read.model_dump_json(indent=2))


def demo_filters_validation() -> None:
    _separator("ItemFilters — model_validator (cross-field)")
    # valid
    f = ItemFilters(min_price="5.00", max_price="50.00", page=2)
    print("  Valid filters:", f.model_dump(exclude_none=True))

    # invalid — min > max
    try:
        ItemFilters(min_price="100.00", max_price="10.00")
    except ValidationError as exc:
        print("  Error:", exc.errors()[0]["msg"])


def demo_nested_order() -> None:
    _separator("OrderCreate — nested schemas + model_validator")
    order = OrderCreate(
        items=[
            {"item_id": str(uuid4()), "quantity": 2},
            {"item_id": str(uuid4()), "quantity": 1},
        ],
        shipping_address={
            "line1": "1 High Street",
            "city": "Wellington",
            "country": "NZ",
            "postcode": "6011",
        },
    )
    print("  Order items:", len(order.items))
    print("  Country:", order.shipping_address.country)

    # duplicate item_id → model_validator raises
    try:
        same_id = str(uuid4())
        OrderCreate(
            items=[
                {"item_id": same_id, "quantity": 1},
                {"item_id": same_id, "quantity": 3},
            ],
            shipping_address={
                "line1": "1 High Street", "city": "Wellington",
                "country": "NZ", "postcode": "6011",
            },
        )
    except ValidationError as exc:
        print("  Duplicate error:", exc.errors()[0]["msg"])


def demo_model_validate_orm() -> None:
    _separator("model_validate — ORM / dict round-trip")

    # Simulates reading a SQLAlchemy row (attribute-style object).
    class FakeOrmRow:
        id          = uuid4()
        name        = "Widget"
        price       = Decimal("9.99")
        category    = Category.hardware
        description = None
        tags        = []
        created_at  = datetime.now(timezone.utc)

    read = ItemRead.model_validate(FakeOrmRow())
    print("  Parsed from ORM object:", read.name, read.display_price)


def demo_json_schema() -> None:
    _separator("JSON Schema — OpenAPI docs generation")
    schema = ItemCreate.model_json_schema()
    print("  Title:", schema.get("title"))
    print("  Required fields:", schema.get("required"))
    print("  Properties:", list(schema.get("properties", {}).keys()))


def demo_error_envelope() -> None:
    _separator("ErrorEnvelope — structured error output")
    env = ErrorEnvelope(
        error=ErrorResponse(
            code="VALIDATION_ERROR",
            message="2 validation error(s) in request",
            details=[
                ErrorDetail(field="body → price", message="Input should be greater than 0", type="greater_than"),
                ErrorDetail(field="body → category", message="Input should be 'hardware', 'software' or 'service'", type="literal_error"),
            ],
        )
    )
    print(env.model_dump_json(indent=2))


if __name__ == "__main__":
    demo_item_create()
    demo_item_create_invalid()
    demo_item_update_patch()
    demo_item_read_computed()
    demo_filters_validation()
    demo_nested_order()
    demo_model_validate_orm()
    demo_json_schema()
    demo_error_envelope()
    print("\n  All demos complete.\n")


# ---------------------------------------------------------------------------
# 11. FASTAPI WIRING STUB
# ---------------------------------------------------------------------------
# Drop these into your FastAPI router once schemas are defined.
#
#   from fastapi import APIRouter, Query, status
#   from typing import Annotated
#
#   router = APIRouter(prefix="/v1/items", tags=["items"])
#
#   @router.get("/", response_model=ItemListRead)
#   async def list_items(
#       filters: Annotated[ItemFilters, Query()],
#   ) -> ItemListRead:
#       ...
#
#   @router.post("/", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
#   async def create_item(payload: ItemCreate) -> ItemRead:
#       ...
#
#   @router.get("/{item_id}", response_model=ItemRead)
#   async def get_item(item_id: UUID) -> ItemRead:
#       ...
#
#   @router.patch("/{item_id}", response_model=ItemRead)
#   async def update_item(item_id: UUID, payload: ItemUpdate) -> ItemRead:
#       # Only apply fields the client sent:
#       delta = payload.model_dump(exclude_unset=True)
#       ...
#
#   @router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
#   async def delete_item(item_id: UUID) -> None:
#       ...


# ---------------------------------------------------------------------------
# 12. SERVICE LAYER STUB
# ---------------------------------------------------------------------------
# Schemas flow into a service class — never put DB queries in route handlers.
#
#   class ItemService:
#       async def create_item(self, payload: ItemCreate) -> ItemRead:
#           data = payload.model_dump()
#           db_item = await item_repo.create(data)
#           return ItemRead.model_validate(db_item)
#
#       async def update_item(self, item_id: UUID, payload: ItemUpdate) -> ItemRead:
#           delta = payload.model_dump(exclude_unset=True)
#           db_item = await item_repo.update(item_id, delta)
#           return ItemRead.model_validate(db_item)
#
#       async def list_items(self, filters: ItemFilters) -> ItemListRead:
#           items, total = await item_repo.list(
#               category=filters.category,
#               min_price=filters.min_price,
#               max_price=filters.max_price,
#               offset=(filters.page - 1) * filters.per_page,
#               limit=filters.per_page,
#           )
#           return ItemListRead(
#               items=[ItemRead.model_validate(i) for i in items],
#               total=total,
#               page=filters.page,
#               per_page=filters.per_page,
#           )


# ---------------------------------------------------------------------------
# 13. PYDANTIC v2 QUICK REFERENCE
# ---------------------------------------------------------------------------
#
# Serialisation:
#   .model_dump()                         → dict (native Python types)
#   .model_dump_json()                    → JSON string
#   .model_dump(exclude_unset=True)       → only fields the caller sent (PATCH)
#   .model_dump(exclude_none=True)        → drop null fields from response
#   .model_dump(mode="json")              → dict with JSON-safe types
#
# Parsing:
#   Model.model_validate(dict_or_obj)     → parse from dict or ORM object
#   Model.model_validate_json(json_str)   → parse from JSON string
#
# Schema:
#   Model.model_json_schema()             → OpenAPI-compatible JSON Schema
#
# Validators (v2 names):
#   @field_validator("field")             → was @validator in v1
#   @model_validator(mode="after")        → was @root_validator in v1
#   @computed_field                       → derived read-only property
#   @field_serializer("field")            → custom JSON serialisation
#
# Config (v2):
#   model_config = ConfigDict(...)        → was class Config: in v1
#   from_attributes=True                  → was orm_mode=True in v1
#   populate_by_name=True                 → accept both field name and alias
