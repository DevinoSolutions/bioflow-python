"""Standard Webhooks v1 verification, including cross-implementation fixtures.

``tests/fixtures/webhook_signatures.json`` was produced by the BioFlow server's
own TypeScript signer (``packages/api/src/webhooks/signing.ts``), so these cases
prove the Python verifier agrees with the producer byte for byte — not merely
with itself.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

import pytest

from bioflow_py import (
    KNOWN_EVENT_TYPES,
    WEBHOOK_ID_HEADER,
    WEBHOOK_SIGNATURE_HEADER,
    WEBHOOK_TIMESTAMP_HEADER,
    WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS,
    Webhooks,
    WebhookVerificationError,
    verify_webhook,
)

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "webhook_signatures.json").read_text(encoding="utf-8")
)
CASES: list[dict[str, Any]] = FIXTURES["cases"]

SECRET = "whsec_c2VjcmV0LW9uZS1mb3ItYmlvZmxvdy10ZXN0cw=="
PAYLOAD = json.dumps(
    {"id": "whmsg_1", "type": "endpoint.test", "created_at": "2026-01-01T00:00:00Z", "data": {}}
)
NOW = 1_767_225_600


def _sign(payload: str, message_id: str, timestamp: int, secret: str) -> str:
    key = base64.b64decode(secret.removeprefix("whsec_"))
    signed = f"{message_id}.{timestamp}.{payload}".encode()
    return "v1," + base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()


def _headers(message_id: str, timestamp: int, signature: str) -> dict[str, str]:
    return {
        WEBHOOK_ID_HEADER: message_id,
        WEBHOOK_TIMESTAMP_HEADER: str(timestamp),
        WEBHOOK_SIGNATURE_HEADER: signature,
    }


def _valid_headers(payload: str = PAYLOAD, secret: str = SECRET) -> dict[str, str]:
    return _headers("whmsg_1", NOW, _sign(payload, "whmsg_1", NOW, secret))


# -- cross-implementation fixtures ---------------------------------------


def test_the_fixtures_were_generated_by_the_typescript_signer() -> None:
    assert "signing.ts" in FIXTURES["generated_by"]
    assert len(CASES) == 9


@pytest.mark.parametrize("case", CASES, ids=lambda case: str(case["name"]))
def test_python_agrees_with_the_typescript_signer(case: dict[str, Any]) -> None:
    headers = _headers(case["id"], case["timestamp"], case["signature_header"])
    if case["valid"]:
        event = verify_webhook(case["payload"], headers, case["secret"], now=case["timestamp"] + 1)
        assert event["type"] in KNOWN_EVENT_TYPES
    else:
        with pytest.raises(WebhookVerificationError):
            verify_webhook(case["payload"], headers, case["secret"], now=case["timestamp"] + 1)


def test_a_rotation_fixture_really_carries_two_signatures() -> None:
    rotation = next(c for c in CASES if c["name"] == "valid_during_rotation_new_secret_first")
    assert len(rotation["signature_header"].split(" ")) == 2


# -- verification behaviour ----------------------------------------------


def test_a_valid_delivery_returns_the_parsed_event() -> None:
    event = verify_webhook(PAYLOAD, _valid_headers(), SECRET, now=NOW)
    assert event["id"] == "whmsg_1"
    assert event["type"] == "endpoint.test"


def test_bytes_and_str_payloads_verify_identically() -> None:
    headers = _valid_headers()
    from_str = verify_webhook(PAYLOAD, headers, SECRET, now=NOW)
    from_bytes = verify_webhook(PAYLOAD.encode(), headers, SECRET, now=NOW)
    from_bytearray = verify_webhook(bytearray(PAYLOAD.encode()), headers, SECRET, now=NOW)
    assert from_str == from_bytes == from_bytearray


def test_a_secret_without_the_whsec_prefix_still_works() -> None:
    bare = SECRET.removeprefix("whsec_")
    assert verify_webhook(PAYLOAD, _valid_headers(secret=bare), bare, now=NOW)


def test_a_tampered_body_is_rejected() -> None:
    headers = _valid_headers()
    with pytest.raises(WebhookVerificationError):
        verify_webhook(PAYLOAD.replace("endpoint.test", "sale.paid"), headers, SECRET, now=NOW)


def test_a_signature_from_a_different_secret_is_rejected() -> None:
    other = "whsec_YW4tZW50aXJlbHktZGlmZmVyZW50LXNlY3JldA=="
    with pytest.raises(WebhookVerificationError):
        verify_webhook(PAYLOAD, _valid_headers(secret=other), SECRET, now=NOW)


@pytest.mark.parametrize("skew", [301, -301, 100_000])
def test_a_timestamp_outside_the_tolerance_is_rejected(skew: int) -> None:
    with pytest.raises(WebhookVerificationError, match="tolerance"):
        verify_webhook(PAYLOAD, _valid_headers(), SECRET, now=NOW + skew)


@pytest.mark.parametrize("skew", [0, 299, -299])
def test_a_timestamp_inside_the_tolerance_is_accepted(skew: int) -> None:
    assert verify_webhook(PAYLOAD, _valid_headers(), SECRET, now=NOW + skew)


def test_the_tolerance_default_matches_the_standard_webhooks_contract() -> None:
    assert WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS == 300


def test_the_tolerance_can_be_widened_for_a_badly_skewed_consumer() -> None:
    assert verify_webhook(
        PAYLOAD, _valid_headers(), SECRET, tolerance_seconds=100_000, now=NOW + 4_000
    )


@pytest.mark.parametrize(
    "missing", [WEBHOOK_ID_HEADER, WEBHOOK_TIMESTAMP_HEADER, WEBHOOK_SIGNATURE_HEADER]
)
def test_a_missing_header_is_rejected(missing: str) -> None:
    headers = _valid_headers()
    del headers[missing]
    with pytest.raises(WebhookVerificationError, match="Missing"):
        verify_webhook(PAYLOAD, headers, SECRET, now=NOW)


def test_a_malformed_timestamp_header_is_rejected() -> None:
    headers = _valid_headers()
    headers[WEBHOOK_TIMESTAMP_HEADER] = "not-a-number"
    with pytest.raises(WebhookVerificationError, match="Malformed"):
        verify_webhook(PAYLOAD, headers, SECRET, now=NOW)


def test_an_empty_signature_header_is_rejected() -> None:
    headers = _valid_headers()
    headers[WEBHOOK_SIGNATURE_HEADER] = ""
    with pytest.raises(WebhookVerificationError):
        verify_webhook(PAYLOAD, headers, SECRET, now=NOW)


def test_headers_are_read_case_insensitively() -> None:
    headers = {key.upper(): value for key, value in _valid_headers().items()}
    assert verify_webhook(PAYLOAD, headers, SECRET, now=NOW)


def test_a_framework_headers_object_with_a_get_method_is_accepted() -> None:
    class FrameworkHeaders:
        def __init__(self, values: dict[str, str]) -> None:
            self._values = {key.lower(): value for key, value in values.items()}

        def get(self, name: str) -> str | None:
            return self._values.get(name.lower())

    assert verify_webhook(PAYLOAD, FrameworkHeaders(_valid_headers()), SECRET, now=NOW)


def test_multi_valued_headers_use_the_first_entry() -> None:
    headers: dict[str, Any] = dict(_valid_headers())
    headers[WEBHOOK_ID_HEADER] = ["whmsg_1", "whmsg_ignored"]
    assert verify_webhook(PAYLOAD, headers, SECRET, now=NOW)


def test_a_verified_payload_that_is_not_json_is_rejected() -> None:
    payload = "not json at all"
    with pytest.raises(WebhookVerificationError, match="not valid JSON"):
        verify_webhook(payload, _valid_headers(payload), SECRET, now=NOW)


def test_a_verified_payload_that_is_not_an_event_envelope_is_rejected() -> None:
    payload = json.dumps({"hello": "world"})
    with pytest.raises(WebhookVerificationError, match="envelope"):
        verify_webhook(payload, _valid_headers(payload), SECRET, now=NOW)


def test_an_unknown_event_type_is_still_delivered_to_the_consumer() -> None:
    """New event types ship without a major SDK bump — verification must not gate them."""
    payload = json.dumps(
        {
            "id": "whmsg_2",
            "type": "invented.later",
            "created_at": "2026-01-01T00:00:00Z",
            "data": {},
        }
    )
    event = verify_webhook(payload, _valid_headers(payload), SECRET, now=NOW)
    assert event["type"] == "invented.later"
    assert event["type"] not in KNOWN_EVENT_TYPES


def test_the_known_event_types_are_the_five_documented_ones() -> None:
    assert set(KNOWN_EVENT_TYPES) == {
        "contact.created",
        "page.published",
        "sale.paid",
        "sale.refunded",
        "endpoint.test",
    }


def test_the_client_facade_verifies_without_an_api_key() -> None:
    assert Webhooks().verify(PAYLOAD, _valid_headers(), SECRET, now=NOW)["id"] == "whmsg_1"


def test_the_client_exposes_the_same_verifier() -> None:
    from conftest import make_client

    with make_client() as bioflow:
        assert bioflow.webhooks.verify(PAYLOAD, _valid_headers(), SECRET, now=NOW)


def test_the_header_names_match_the_standard_webhooks_spec() -> None:
    assert WEBHOOK_ID_HEADER == "webhook-id"
    assert WEBHOOK_TIMESTAMP_HEADER == "webhook-timestamp"
    assert WEBHOOK_SIGNATURE_HEADER == "webhook-signature"
