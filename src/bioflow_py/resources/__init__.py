"""Resource namespaces hung off :class:`~bioflow_py.client.BioFlow`."""

from __future__ import annotations

from .pages import AsyncPages, Pages
from .simple import (
    Analytics,
    AsyncAnalytics,
    AsyncContacts,
    AsyncFiles,
    AsyncUsageResource,
    Contacts,
    Files,
    UsageResource,
)
from .webhook_endpoints import AsyncWebhookEndpoints, DeliveryStatus, WebhookEndpoints

__all__ = [
    "Analytics",
    "AsyncAnalytics",
    "AsyncContacts",
    "AsyncFiles",
    "AsyncPages",
    "AsyncUsageResource",
    "AsyncWebhookEndpoints",
    "Contacts",
    "DeliveryStatus",
    "Files",
    "Pages",
    "UsageResource",
    "WebhookEndpoints",
]
