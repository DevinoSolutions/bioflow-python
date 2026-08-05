"""Standard Webhooks v1 signature verification.

The consumer-side mirror of ``packages/api/src/webhooks/signing.ts``:

* HMAC-SHA256 over ``f"{id}.{timestamp}.{raw_body}"``
* key = the base64-decoded body of the ``whsec_…`` secret
* headers ``webhook-id`` / ``webhook-timestamp`` / ``webhook-signature``
* the signature header holds **space-separated** ``v1,<base64>`` entries —
  during a secret rotation BioFlow sends two, and any match verifies
* timestamp tolerance 300 s, constant-time comparison
* verification runs over the RAW bytes; JSON is parsed only afterwards

Verification needs no API key, so :func:`verify_webhook` is importable on its own.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections.abc import Mapping, Sequence
from typing import Any, TypedDict

from .errors import WebhookVerificationError

WEBHOOK_ID_HEADER = "webhook-id"
WEBHOOK_TIMESTAMP_HEADER = "webhook-timestamp"
WEBHOOK_SIGNATURE_HEADER = "webhook-signature"
WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS = 300

_SIGNATURE_PREFIX = "v1,"
_SECRET_PREFIX = "whsec_"


class WebhookEventBase(TypedDict):
    """Fields present on every delivery envelope."""

    id: str
    """``whmsg_…`` — STABLE across retries; use it as your dedup key."""

    created_at: str
    type: str
    data: Any


class ContactCreatedEvent(WebhookEventBase):
    """``contact.created`` — a lead was captured by a page block."""


class PagePublishedEvent(WebhookEventBase):
    """``page.published`` — a page went live."""


class SalePaidEvent(WebhookEventBase):
    """``sale.paid`` — a purchase or tip settled."""


class SaleRefundedEvent(WebhookEventBase):
    """``sale.refunded`` — a settled sale was refunded."""


class EndpointTestEvent(WebhookEventBase):
    """``endpoint.test`` — sent at endpoint creation/URL change and ``POST …/test``."""


class UnknownWebhookEvent(WebhookEventBase):
    """Any event type this SDK build does not know about.

    Forward compatibility: new event types ship WITHOUT a major SDK bump, so at
    runtime ``type`` can hold values outside :data:`KNOWN_EVENT_TYPES` — the
    verifier never rejects them. Always give your dispatch a default branch.
    """


WebhookEvent = WebhookEventBase
"""The verified envelope. Branch on ``event["type"]`` and keep a default branch."""

KNOWN_EVENT_TYPES: tuple[str, ...] = (
    "contact.created",
    "page.published",
    "sale.paid",
    "sale.refunded",
    "endpoint.test",
)
"""Event types this build knows about — an OPEN set, never an exhaustive one."""


def _header_value(
    headers: Mapping[str, Any] | Any,
    name: str,
) -> str | None:
    """Read a header case-insensitively from a mapping or any ``.get()`` object."""
    getter = getattr(headers, "get", None)
    if getter is not None and not isinstance(headers, dict):
        value = getter(name)
        if value is not None:
            return value[0] if isinstance(value, (list, tuple)) else str(value)
    if isinstance(headers, Mapping):
        for key, value in headers.items():
            if str(key).lower() == name:
                if isinstance(value, (list, tuple)):
                    return str(value[0]) if value else None
                return None if value is None else str(value)
    return None


def _secret_bytes(secret: str) -> bytes:
    raw = secret[len(_SECRET_PREFIX) :] if secret.startswith(_SECRET_PREFIX) else secret
    try:
        return base64.b64decode(raw, validate=False)
    except (ValueError, TypeError) as exc:  # pragma: no cover - defensive
        raise WebhookVerificationError("Malformed whsec_ signing secret") from exc


def _candidate_signatures(header: str) -> Sequence[str]:
    return [part for part in header.split(" ") if part.startswith(_SIGNATURE_PREFIX)]


def verify_webhook(
    payload: str | bytes | bytearray,
    headers: Mapping[str, Any] | Any,
    secret: str,
    *,
    tolerance_seconds: int = WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS,
    now: float | None = None,
) -> WebhookEvent:
    """Verify a delivery and return the parsed event.

    Raises :class:`~bioflow_py.errors.WebhookVerificationError` on ANY failure —
    treat such payloads as untrusted and answer with a 400.

    Args:
        payload: The RAW request body — bytes or the exact string, never
            re-serialized JSON.
        headers: The delivery's HTTP headers. Accepts a plain dict, a Flask/
            Django/Starlette headers object, or anything with a ``.get()``.
        secret: The endpoint's ``whsec_…`` signing secret.
        tolerance_seconds: Maximum accepted clock skew. Defaults to 300 s.
        now: Override "now" (unix seconds) — tests only.
    """
    message_id = _header_value(headers, WEBHOOK_ID_HEADER)
    timestamp_header = _header_value(headers, WEBHOOK_TIMESTAMP_HEADER)
    signature_header = _header_value(headers, WEBHOOK_SIGNATURE_HEADER)
    if not message_id:
        raise WebhookVerificationError(f"Missing {WEBHOOK_ID_HEADER} header")
    if timestamp_header is None:
        raise WebhookVerificationError(f"Missing {WEBHOOK_TIMESTAMP_HEADER} header")
    if signature_header is None:
        raise WebhookVerificationError(f"Missing {WEBHOOK_SIGNATURE_HEADER} header")

    try:
        timestamp_seconds = int(timestamp_header)
    except ValueError as exc:
        raise WebhookVerificationError(f"Malformed {WEBHOOK_TIMESTAMP_HEADER} header") from exc

    now_seconds = int(now if now is not None else time.time())
    if abs(now_seconds - timestamp_seconds) > tolerance_seconds:
        raise WebhookVerificationError(
            f"{WEBHOOK_TIMESTAMP_HEADER} outside tolerance — replayed or badly delayed delivery"
        )

    body = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
    signed = f"{message_id}.{timestamp_seconds}.".encode() + body
    expected = hmac.new(_secret_bytes(secret), signed, hashlib.sha256).digest()

    matched = False
    for candidate in _candidate_signatures(signature_header):
        try:
            provided = base64.b64decode(candidate[len(_SIGNATURE_PREFIX) :], validate=False)
        except (ValueError, TypeError):
            continue
        if hmac.compare_digest(provided, expected):
            matched = True
            break
    if not matched:
        raise WebhookVerificationError(
            f"No {WEBHOOK_SIGNATURE_HEADER} entry matches this payload and secret"
        )

    try:
        parsed = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise WebhookVerificationError("Verified payload is not valid JSON") from exc
    if (
        not isinstance(parsed, dict)
        or not isinstance(parsed.get("id"), str)
        or not isinstance(parsed.get("type"), str)
    ):
        raise WebhookVerificationError("Verified payload is not a BioFlow webhook event envelope")
    return parsed


class Webhooks:
    """``client.webhooks`` facade — verification needs no API key."""

    def verify(
        self,
        payload: str | bytes | bytearray,
        headers: Mapping[str, Any] | Any,
        secret: str,
        *,
        tolerance_seconds: int = WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS,
        now: float | None = None,
    ) -> WebhookEvent:
        """See :func:`verify_webhook`."""
        return verify_webhook(
            payload,
            headers,
            secret,
            tolerance_seconds=tolerance_seconds,
            now=now,
        )


__all__ = [
    "KNOWN_EVENT_TYPES",
    "WEBHOOK_ID_HEADER",
    "WEBHOOK_SIGNATURE_HEADER",
    "WEBHOOK_TIMESTAMP_HEADER",
    "WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS",
    "ContactCreatedEvent",
    "EndpointTestEvent",
    "PagePublishedEvent",
    "SalePaidEvent",
    "SaleRefundedEvent",
    "UnknownWebhookEvent",
    "WebhookEvent",
    "WebhookEventBase",
    "Webhooks",
    "verify_webhook",
]
