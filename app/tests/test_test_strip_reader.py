"""Test the test-strip vision reader's parsing + AgentLearningService correction loop.

Mocks the anthropic Vision call so tests don't burn API tokens.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch, MagicMock

import pytest

from src.services.chemistry.test_strip_reader import (
    SUPPORTED_FIELDS,
    TestStripResult,
    read_strip,
)

pytestmark = pytest.mark.asyncio


def _mock_anthropic_response(text: str):
    """Build a mock that mimics the anthropic SDK response shape."""
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    client = MagicMock()
    client.messages.create.return_value = msg
    return client


async def test_read_strip_parses_well_formed_json(db_session, org_a):
    payload = json.dumps({
        "values": {
            "ph": 7.4,
            "free_chlorine": 1.5,
            "total_chlorine": 2.0,
            "alkalinity": 100,
            "calcium_hardness": 250,
            "cyanuric_acid": 40,
        },
        "confidence": 0.85,
        "brand_detected": "AquaChek 7-way",
        "notes": "",
    })
    with patch("anthropic.Anthropic", return_value=_mock_anthropic_response(payload)):
        result = await read_strip(
            db=db_session, org_id=org_a.id,
            image_bytes=b"fake-image-bytes", media_type="image/jpeg",
        )
    assert result.error is None
    assert result.values["ph"] == 7.4
    assert result.values["free_chlorine"] == 1.5
    assert result.values["total_chlorine"] == 2.0
    # combined_chlorine derived (total - free)
    assert result.values["combined_chlorine"] == 0.5
    assert result.confidence == 0.85
    assert result.brand_detected == "AquaChek 7-way"


async def test_read_strip_strips_code_fences(db_session, org_a):
    """Claude sometimes wraps JSON in ```json ... ``` despite instructions."""
    payload = '```json\n{"values": {"ph": 7.6}, "confidence": 0.5}\n```'
    with patch("anthropic.Anthropic", return_value=_mock_anthropic_response(payload)):
        result = await read_strip(
            db=db_session, org_id=org_a.id,
            image_bytes=b"x", media_type="image/jpeg",
        )
    assert result.error is None
    assert result.values["ph"] == 7.6


async def test_read_strip_drops_unsupported_fields(db_session, org_a):
    """Don't trust Claude to invent fields — only the SUPPORTED_FIELDS allow-list lands in DB."""
    payload = json.dumps({
        "values": {
            "ph": 7.4,
            "fake_metal_content": 999,
            "unicorns_per_gallon": 7,
        },
        "confidence": 0.7,
    })
    with patch("anthropic.Anthropic", return_value=_mock_anthropic_response(payload)):
        result = await read_strip(
            db=db_session, org_id=org_a.id, image_bytes=b"x", media_type="image/jpeg",
        )
    assert "fake_metal_content" not in result.values
    assert "unicorns_per_gallon" not in result.values
    assert result.values == {"ph": 7.4}


async def test_read_strip_rejects_non_finite_values(db_session, org_a):
    payload = json.dumps({
        "values": {"ph": "not-a-number", "free_chlorine": None, "alkalinity": 80},
        "confidence": 0.5,
    })
    with patch("anthropic.Anthropic", return_value=_mock_anthropic_response(payload)):
        result = await read_strip(
            db=db_session, org_id=org_a.id, image_bytes=b"x", media_type="image/jpeg",
        )
    assert result.values == {"alkalinity": 80}


async def test_read_strip_handles_bad_json(db_session, org_a):
    """Resilient to Claude returning malformed output."""
    with patch("anthropic.Anthropic", return_value=_mock_anthropic_response("not json at all")):
        result = await read_strip(
            db=db_session, org_id=org_a.id, image_bytes=b"x", media_type="image/jpeg",
        )
    assert result.error is not None
    assert "parse" in result.error.lower()


async def test_read_strip_clamps_confidence(db_session, org_a):
    """Confidence outside [0,1] is clamped, not rejected."""
    payload = json.dumps({"values": {"ph": 7.0}, "confidence": 1.7})
    with patch("anthropic.Anthropic", return_value=_mock_anthropic_response(payload)):
        result = await read_strip(
            db=db_session, org_id=org_a.id, image_bytes=b"x", media_type="image/jpeg",
        )
    assert result.confidence == 1.0


async def test_read_strip_rejects_empty_image(db_session, org_a):
    result = await read_strip(
        db=db_session, org_id=org_a.id, image_bytes=b"", media_type="image/jpeg",
    )
    assert result.error == "empty image"


async def test_read_strip_uses_chart_when_brand_matches(db_session, org_a):
    """When a TestStripBrand exists, identify-pass returns it and the read prompt
    gets chart-injected. Result should reflect chart_used=True."""
    from src.models.test_strip_brand import TestStripBrand, TestStripPad
    brand = TestStripBrand(
        id=str(uuid.uuid4()),
        name="AquaChek 7-way Pool",
        manufacturer="AquaChek",
        num_pads=2,
        aliases=["aquachek"],
    )
    db_session.add(brand)
    await db_session.flush()
    db_session.add_all([
        TestStripPad(
            id=str(uuid.uuid4()), brand_id=brand.id, pad_index=0,
            chemistry_field="ph", unit="",
            color_scale=[{"value": 6.8, "hex": "#FFA500"}, {"value": 7.4, "hex": "#FF4040"}, {"value": 8.4, "hex": "#A02080"}],
        ),
        TestStripPad(
            id=str(uuid.uuid4()), brand_id=brand.id, pad_index=1,
            chemistry_field="free_chlorine", unit="ppm",
            color_scale=[{"value": 0, "hex": "#FFFFCC"}, {"value": 5, "hex": "#FF66AA"}],
        ),
    ])
    await db_session.commit()

    # Mock: identify call returns this brand_id; read call returns values.
    identify_resp = MagicMock()
    identify_resp.content = [MagicMock(text=json.dumps({
        "brand_id": brand.id, "brand_name": "AquaChek 7-way Pool", "confidence": 0.95,
    }))]
    read_resp = MagicMock()
    read_resp.content = [MagicMock(text=json.dumps({
        "values": {"ph": 7.4, "free_chlorine": 1.0},
        "confidence": 0.9, "chart_followed": True, "notes": "",
    }))]
    client = MagicMock()
    client.messages.create.side_effect = [identify_resp, read_resp]

    with patch("anthropic.Anthropic", return_value=client):
        result = await read_strip(
            db=db_session, org_id=org_a.id, image_bytes=b"x", media_type="image/jpeg",
        )

    assert result.error is None
    assert result.brand_id == brand.id
    assert result.chart_used is True
    assert result.values["ph"] == 7.4
    assert result.values["free_chlorine"] == 1.0


async def test_brand_hint_short_circuits_identify(db_session, org_a):
    """Passing brand_hint matching a known brand skips the identify Vision call."""
    from src.models.test_strip_brand import TestStripBrand, TestStripPad
    brand = TestStripBrand(
        id=str(uuid.uuid4()),
        name="Industrial Test Systems WaterWorks",
        manufacturer="Industrial Test Systems",
        num_pads=1,
        aliases=["WaterWorks", "IT Systems"],
    )
    db_session.add(brand)
    await db_session.flush()
    db_session.add(TestStripPad(
        id=str(uuid.uuid4()), brand_id=brand.id, pad_index=0,
        chemistry_field="ph", unit="",
        color_scale=[{"value": 7.0, "hex": "#FF0000"}],
    ))
    await db_session.commit()

    # Only ONE call expected (the read), since hint matches.
    read_resp = MagicMock()
    read_resp.content = [MagicMock(text=json.dumps({
        "values": {"ph": 7.0}, "confidence": 0.8, "chart_followed": True,
    }))]
    client = MagicMock()
    client.messages.create.return_value = read_resp

    with patch("anthropic.Anthropic", return_value=client):
        result = await read_strip(
            db=db_session, org_id=org_a.id,
            image_bytes=b"x", media_type="image/jpeg",
            brand_hint="WaterWorks",
        )

    assert client.messages.create.call_count == 1  # identify skipped
    assert result.brand_id == brand.id
    assert result.chart_used is True
