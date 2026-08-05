"""Concrete-path builders shared by the sync and async resource classes.

Path parameters are URL-encoded here and nowhere else, so an id containing a
slash or a space can never escape its segment.
"""

from __future__ import annotations

from urllib.parse import quote

from bioflow_py.operations import OPERATIONS


def encode(value: str) -> str:
    """Percent-encode a single path segment (``/`` included)."""
    return quote(str(value), safe="")


PAGES = OPERATIONS["listPages"].path
CONTACTS = OPERATIONS["listContacts"].path
FILES = OPERATIONS["listFiles"].path
ANALYTICS_SUMMARY = OPERATIONS["getAnalyticsSummary"].path
USAGE = OPERATIONS["getUsage"].path
WEBHOOK_ENDPOINTS = OPERATIONS["listWebhookEndpoints"].path


def page(page_id: str) -> str:
    return f"{PAGES}/{encode(page_id)}"


def page_blocks(page_id: str) -> str:
    return f"{page(page_id)}/blocks"


def page_block(page_id: str, block_id: str) -> str:
    return f"{page_blocks(page_id)}/{encode(block_id)}"


def page_publish(page_id: str) -> str:
    return f"{page(page_id)}/publish"


def webhook_endpoint(endpoint_id: str) -> str:
    return f"{WEBHOOK_ENDPOINTS}/{encode(endpoint_id)}"


def webhook_deliveries(endpoint_id: str) -> str:
    return f"{webhook_endpoint(endpoint_id)}/deliveries"


def webhook_delivery_resend(endpoint_id: str, delivery_id: str) -> str:
    return f"{webhook_deliveries(endpoint_id)}/{encode(delivery_id)}/resend"


def webhook_replay(endpoint_id: str) -> str:
    return f"{webhook_endpoint(endpoint_id)}/replay"


def webhook_rotate_secret(endpoint_id: str) -> str:
    return f"{webhook_endpoint(endpoint_id)}/rotate-secret"


def webhook_test(endpoint_id: str) -> str:
    return f"{webhook_endpoint(endpoint_id)}/test"
