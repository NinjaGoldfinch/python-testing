from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from conftest import load_example


example = load_example("pydantic_schemas_example", "02-pydantic-schemas/pydantic_example.py")


def test_item_create_normalizes_name_and_tags() -> None:
    item = example.ItemCreate(
        name="  Widget  ",
        price="9.99",
        category="hardware",
        tags=["Sale", " sale ", "NEW"],
    )

    assert item.name == "Widget"
    assert item.tags == ["Sale", "NEW"]
    assert item.price == Decimal("9.99")


def test_item_create_and_filters_reject_invalid_input() -> None:
    with pytest.raises(ValidationError):
        example.ItemCreate(name=" ", price="-1.00", category="unknown")

    with pytest.raises(ValidationError, match="min_price"):
        example.ItemFilters(min_price="50.00", max_price="10.00")


def test_item_read_serialization_and_paginated_has_next() -> None:
    item = example.ItemRead(
        id=uuid4(),
        name="Widget",
        price=Decimal("9.90"),
        category=example.Category.hardware,
        description=None,
        tags=[],
        created_at=datetime.now(timezone.utc),
    )
    page = example.ItemListRead(items=[item], total=3, page=1, per_page=1)

    assert item.display_price == "$9.90"
    assert item.model_dump(mode="json")["price"] == "9.90"
    assert page.has_next is True


def test_nested_order_rejects_duplicate_items() -> None:
    item_id = uuid4()
    address = {"line1": "1 High Street", "city": "Wellington", "country": "NZ", "postcode": "6011"}

    with pytest.raises(ValidationError, match="Duplicate item_id"):
        example.OrderCreate(
            items=[{"item_id": item_id, "quantity": 1}, {"item_id": item_id, "quantity": 2}],
            shipping_address=address,
        )


def test_error_envelope_shape_is_explicit() -> None:
    envelope = example.ErrorEnvelope(
        error=example.ErrorResponse(
            code="VALIDATION_ERROR",
            message="Invalid request",
            details=[example.ErrorDetail(field="body.name", message="Required", type="missing")],
        )
    )

    assert envelope.model_dump()["error"]["details"][0]["field"] == "body.name"
