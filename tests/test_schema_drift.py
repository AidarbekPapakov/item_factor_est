"""
Schema drift guard for the CSFloat /history/{name}/sales response.

The fixture (tests/fixtures/csfloat_sales_sample.json) is a real API response
captured from the probe script. This test validates it against our pydantic
models and fails loudly if:
  - a field we depend on is removed or renamed
  - a field's type changes in a way pydantic rejects
  - our required fields are absent

Run without hitting the API:
    pytest tests/test_schema_drift.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.ingest.csfloat_schemas import SaleRow

FIXTURE = Path(__file__).parent / "fixtures" / "csfloat_sales_sample.json"


@pytest.fixture
def sample_rows() -> list[dict]:
    return json.loads(FIXTURE.read_text())


def test_fixture_parses_without_error(sample_rows):
    for raw in sample_rows:
        SaleRow.model_validate(raw)


def test_required_root_fields_present(sample_rows):
    required = {"id", "sold_at", "price", "item", "reference"}
    for raw in sample_rows:
        missing = required - raw.keys()
        assert not missing, f"Missing root fields: {missing}"


def test_required_item_fields_present(sample_rows):
    required = {
        "market_hash_name", "def_index", "paint_index", "paint_seed",
        "float_value", "is_stattrak", "is_souvenir", "rarity", "wear_name",
    }
    for raw in sample_rows:
        missing = required - raw["item"].keys()
        assert not missing, f"Missing item fields: {missing}"


def test_required_reference_fields_present(sample_rows):
    required = {"base_price", "float_factor", "predicted_price", "quantity"}
    for raw in sample_rows:
        missing = required - raw["reference"].keys()
        assert not missing, f"Missing reference fields: {missing}"


def test_sticker_reference_price_is_int(sample_rows):
    for raw in sample_rows:
        for sticker in raw["item"].get("stickers", []):
            ref = sticker.get("reference")
            if ref:
                assert isinstance(ref["price"], int), (
                    f"sticker.reference.price should be int, got {type(ref['price'])}"
                )


def test_missing_required_field_raises(sample_rows):
    """Removing a required field must raise ValidationError."""
    raw = dict(sample_rows[0])
    del raw["sold_at"]
    with pytest.raises(ValidationError):
        SaleRow.model_validate(raw)


def test_keychain_parses_when_present(sample_rows):
    rows_with_keychains = [r for r in sample_rows if r["item"].get("keychains")]
    if not rows_with_keychains:
        pytest.skip("No keychain entries in fixture — add a sample with a charm to cover this path")
    for raw in rows_with_keychains:
        sale = SaleRow.model_validate(raw)
        assert len(sale.item.keychains) > 0
