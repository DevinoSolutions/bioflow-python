"""The SDK's operation registry — one entry per OpenAPI operation, keyed by operationId.

Pinned 1:1 against ``openapi/v1.json`` by ``tests/test_operations_contract.py``
(missing/extra/mismatched entries = red CI), so the client surface can never
silently drift from the spec. Mirrors ``SDK_OPERATIONS`` in the TypeScript SDK
(``packages/sdk/src/operations.ts``).

``idempotent=True`` marks operations the server runs through its Idempotency-Key
ledger (every consequential POST) — the SDK auto-generates a key for those, which
is also what makes them safely retryable.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Literal, NamedTuple

HttpMethod = Literal["GET", "POST", "PATCH", "DELETE"]


class Operation(NamedTuple):
    """A single public-API operation as described by the spec."""

    method: HttpMethod
    """HTTP method, upper-case."""

    path: str
    """Path template with {snake_case} tokens exactly as in the spec."""

    idempotent: bool
    """True when the server ledgers the call under an Idempotency-Key."""


OPERATIONS: Mapping[str, Operation] = MappingProxyType(
    {
        "getAnalyticsSummary": Operation("GET", "/v1/analytics/summary", False),
        "listContacts": Operation("GET", "/v1/contacts", False),
        "listFiles": Operation("GET", "/v1/files", False),
        "listPages": Operation("GET", "/v1/pages", False),
        "createPage": Operation("POST", "/v1/pages", True),
        "deletePage": Operation("DELETE", "/v1/pages/{page_id}", False),
        "getPage": Operation("GET", "/v1/pages/{page_id}", False),
        "updatePage": Operation("PATCH", "/v1/pages/{page_id}", False),
        "addBlock": Operation("POST", "/v1/pages/{page_id}/blocks", True),
        "removeBlock": Operation("DELETE", "/v1/pages/{page_id}/blocks/{block_id}", False),
        "publishPage": Operation("POST", "/v1/pages/{page_id}/publish", True),
        "getUsage": Operation("GET", "/v1/usage", False),
        "listWebhookEndpoints": Operation("GET", "/v1/webhook-endpoints", False),
        "createWebhookEndpoint": Operation("POST", "/v1/webhook-endpoints", True),
        "deleteWebhookEndpoint": Operation("DELETE", "/v1/webhook-endpoints/{endpoint_id}", False),
        "getWebhookEndpoint": Operation("GET", "/v1/webhook-endpoints/{endpoint_id}", False),
        "updateWebhookEndpoint": Operation("PATCH", "/v1/webhook-endpoints/{endpoint_id}", False),
        "listWebhookDeliveries": Operation(
            "GET", "/v1/webhook-endpoints/{endpoint_id}/deliveries", False
        ),
        "resendWebhookDelivery": Operation(
            "POST",
            "/v1/webhook-endpoints/{endpoint_id}/deliveries/{delivery_id}/resend",
            True,
        ),
        "replayWebhookDeliveries": Operation(
            "POST", "/v1/webhook-endpoints/{endpoint_id}/replay", True
        ),
        "rotateWebhookSecret": Operation(
            "POST", "/v1/webhook-endpoints/{endpoint_id}/rotate-secret", True
        ),
        "testWebhookEndpoint": Operation("POST", "/v1/webhook-endpoints/{endpoint_id}/test", True),
    }
)
"""Every ``/v1`` operation, keyed by ``operationId`` (22 entries)."""


__all__ = ["OPERATIONS", "HttpMethod", "Operation"]
