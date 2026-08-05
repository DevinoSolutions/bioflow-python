"""Public wire types — every name resolves into :mod:`bioflow_py._generated.models`,
which is machine-generated from ``openapi/v1.json`` (never hand-edited).

Forward compatibility: treat server-sent string unions (statuses, event types, ...)
as **open sets** — new values may appear without a major version. The SDK performs
no runtime narrowing of responses, so these are ``TypedDict``s over plain ``dict``
payloads: zero runtime cost, and a new server field never breaks a call.

``File`` is re-exported as :data:`FileObject`, mirroring the TypeScript SDK's alias
and avoiding the clash with the builtin name.
"""

from __future__ import annotations

from ._generated.models import (
    AddBlockRequest,
    AnalyticsSummary,
    BlockUpdate,
    Burst,
    Contact,
    ContactList,
    CreatePageRequest,
    CreateWebhookEndpointRequest,
    CreateWebhookEndpointResponse,
    Draft,
    Error,
    File,
    FileList,
    Meter,
    Page,
    PageBlockRef,
    PageList,
    PageSummary,
    Problem,
    Published,
    PublishPageRequest,
    PublishResult,
    ReplayWebhooksRequest,
    RotateWebhookSecretResponse,
    Theme,
    Tips,
    TopLink,
    TopReferrer,
    Totals,
    UpdatePageRequest,
    UpdateWebhookEndpointRequest,
    Usage,
    WebhookAttempt,
    WebhookDelivery,
    WebhookDeliveryList,
    WebhookEndpoint,
    WebhookEndpointList,
    WebhookReplayResult,
    WebhookTestResult,
)

FileObject = File
"""A stored file. Named ``FileObject`` so it never shadows the ``file`` builtin."""

ProblemFieldError = Error
"""A single field-level validation error inside a :data:`Problem` document."""

__all__ = [
    "AddBlockRequest",
    "AnalyticsSummary",
    "BlockUpdate",
    "Burst",
    "Contact",
    "ContactList",
    "CreatePageRequest",
    "CreateWebhookEndpointRequest",
    "CreateWebhookEndpointResponse",
    "Draft",
    "File",
    "FileList",
    "FileObject",
    "Meter",
    "Page",
    "PageBlockRef",
    "PageList",
    "PageSummary",
    "Problem",
    "ProblemFieldError",
    "PublishPageRequest",
    "PublishResult",
    "Published",
    "ReplayWebhooksRequest",
    "RotateWebhookSecretResponse",
    "Theme",
    "Tips",
    "TopLink",
    "TopReferrer",
    "Totals",
    "UpdatePageRequest",
    "UpdateWebhookEndpointRequest",
    "Usage",
    "WebhookAttempt",
    "WebhookDelivery",
    "WebhookDeliveryList",
    "WebhookEndpoint",
    "WebhookEndpointList",
    "WebhookReplayResult",
    "WebhookTestResult",
]
