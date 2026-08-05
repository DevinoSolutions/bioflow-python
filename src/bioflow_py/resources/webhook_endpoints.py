"""The ``webhook_endpoints`` resource — outbound Standard Webhooks plumbing."""

from __future__ import annotations

from typing import Any, Literal, cast

from bioflow_py._http import AsyncTransport, SyncTransport
from bioflow_py.models import (
    CreateWebhookEndpointRequest,
    CreateWebhookEndpointResponse,
    ReplayWebhooksRequest,
    RotateWebhookSecretResponse,
    UpdateWebhookEndpointRequest,
    WebhookDelivery,
    WebhookEndpoint,
    WebhookEndpointList,
    WebhookReplayResult,
    WebhookTestResult,
)
from bioflow_py.pagination import (
    AsyncCursorPage,
    CursorPage,
    fetch_cursor_page,
    fetch_cursor_page_async,
)

from . import _paths

DeliveryStatus = Literal["PENDING", "SUCCEEDED", "FAILED"]


class WebhookEndpoints:
    """``client.webhook_endpoints`` — manage endpoints, deliveries and secrets."""

    def __init__(self, transport: SyncTransport) -> None:
        self._transport = transport

    def list(self, **options: Any) -> WebhookEndpointList:
        """``GET /v1/webhook-endpoints`` — bounded collection, no cursor."""
        result = self._transport.request("GET", _paths.WEBHOOK_ENDPOINTS, **options)
        return cast(WebhookEndpointList, result.data)

    def create(
        self, body: CreateWebhookEndpointRequest, **options: Any
    ) -> CreateWebhookEndpointResponse:
        """``POST /v1/webhook-endpoints`` (201).

        The URL is SSRF-checked and must answer the signed ``endpoint.test`` event
        with a 2xx before the endpoint is created. The returned ``secret``
        (``whsec_…``) is shown ONCE — store it now.
        """
        result = self._transport.request("POST", _paths.WEBHOOK_ENDPOINTS, body=body, **options)
        return cast(CreateWebhookEndpointResponse, result.data)

    def get(self, endpoint_id: str, **options: Any) -> WebhookEndpoint:
        """``GET /v1/webhook-endpoints/{endpoint_id}``."""
        result = self._transport.request("GET", _paths.webhook_endpoint(endpoint_id), **options)
        return cast(WebhookEndpoint, result.data)

    def update(
        self, endpoint_id: str, body: UpdateWebhookEndpointRequest, **options: Any
    ) -> WebhookEndpoint:
        """``PATCH /v1/webhook-endpoints/{endpoint_id}`` — URL changes re-verify."""
        result = self._transport.request(
            "PATCH", _paths.webhook_endpoint(endpoint_id), body=body, **options
        )
        return cast(WebhookEndpoint, result.data)

    def delete(self, endpoint_id: str, **options: Any) -> None:
        """``DELETE /v1/webhook-endpoints/{endpoint_id}`` — 204, returns ``None``."""
        self._transport.request("DELETE", _paths.webhook_endpoint(endpoint_id), **options)

    def deliveries(
        self,
        endpoint_id: str,
        *,
        limit: int | None = None,
        after: str | None = None,
        status: DeliveryStatus | None = None,
        **options: Any,
    ) -> CursorPage[WebhookDelivery]:
        """``GET …/{endpoint_id}/deliveries`` — cursor-paginated delivery log."""
        return fetch_cursor_page(
            self._transport,
            _paths.webhook_deliveries(endpoint_id),
            {"limit": limit, "after": after, "status": status},
            options,
        )

    def resend_delivery(
        self, endpoint_id: str, delivery_id: str, **options: Any
    ) -> WebhookDelivery:
        """``POST …/deliveries/{delivery_id}/resend``.

        Re-delivers with the SAME ``webhook-id``, so your consumer's dedup key
        still applies.
        """
        result = self._transport.request(
            "POST", _paths.webhook_delivery_resend(endpoint_id, delivery_id), **options
        )
        return cast(WebhookDelivery, result.data)

    def replay(
        self, endpoint_id: str, body: ReplayWebhooksRequest, **options: Any
    ) -> WebhookReplayResult:
        """``POST …/{endpoint_id}/replay`` — re-queues FAILED deliveries since a time."""
        result = self._transport.request(
            "POST", _paths.webhook_replay(endpoint_id), body=body, **options
        )
        return cast(WebhookReplayResult, result.data)

    def rotate_secret(self, endpoint_id: str, **options: Any) -> RotateWebhookSecretResponse:
        """``POST …/{endpoint_id}/rotate-secret`` — returns the NEW secret (once).

        The previous secret keeps signing until ``previous_secret_expires_at``
        (24 h dual-signature overlap), which is why
        :func:`~bioflow_py.webhooks.verify_webhook` accepts any matching entry.
        """
        result = self._transport.request(
            "POST", _paths.webhook_rotate_secret(endpoint_id), **options
        )
        return cast(RotateWebhookSecretResponse, result.data)

    def test(self, endpoint_id: str, **options: Any) -> WebhookTestResult:
        """``POST …/{endpoint_id}/test`` — sends a signed ``endpoint.test`` event."""
        result = self._transport.request("POST", _paths.webhook_test(endpoint_id), **options)
        return cast(WebhookTestResult, result.data)


class AsyncWebhookEndpoints:
    """Awaitable twin of :class:`WebhookEndpoints`."""

    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def list(self, **options: Any) -> WebhookEndpointList:
        """``GET /v1/webhook-endpoints`` — bounded collection, no cursor."""
        result = await self._transport.request("GET", _paths.WEBHOOK_ENDPOINTS, **options)
        return cast(WebhookEndpointList, result.data)

    async def create(
        self, body: CreateWebhookEndpointRequest, **options: Any
    ) -> CreateWebhookEndpointResponse:
        """``POST /v1/webhook-endpoints`` (201)."""
        result = await self._transport.request(
            "POST", _paths.WEBHOOK_ENDPOINTS, body=body, **options
        )
        return cast(CreateWebhookEndpointResponse, result.data)

    async def get(self, endpoint_id: str, **options: Any) -> WebhookEndpoint:
        """``GET /v1/webhook-endpoints/{endpoint_id}``."""
        result = await self._transport.request(
            "GET", _paths.webhook_endpoint(endpoint_id), **options
        )
        return cast(WebhookEndpoint, result.data)

    async def update(
        self, endpoint_id: str, body: UpdateWebhookEndpointRequest, **options: Any
    ) -> WebhookEndpoint:
        """``PATCH /v1/webhook-endpoints/{endpoint_id}``."""
        result = await self._transport.request(
            "PATCH", _paths.webhook_endpoint(endpoint_id), body=body, **options
        )
        return cast(WebhookEndpoint, result.data)

    async def delete(self, endpoint_id: str, **options: Any) -> None:
        """``DELETE /v1/webhook-endpoints/{endpoint_id}`` — 204, returns ``None``."""
        await self._transport.request("DELETE", _paths.webhook_endpoint(endpoint_id), **options)

    async def deliveries(
        self,
        endpoint_id: str,
        *,
        limit: int | None = None,
        after: str | None = None,
        status: DeliveryStatus | None = None,
        **options: Any,
    ) -> AsyncCursorPage[WebhookDelivery]:
        """``GET …/{endpoint_id}/deliveries`` — cursor-paginated delivery log."""
        return await fetch_cursor_page_async(
            self._transport,
            _paths.webhook_deliveries(endpoint_id),
            {"limit": limit, "after": after, "status": status},
            options,
        )

    async def resend_delivery(
        self, endpoint_id: str, delivery_id: str, **options: Any
    ) -> WebhookDelivery:
        """``POST …/deliveries/{delivery_id}/resend``."""
        result = await self._transport.request(
            "POST", _paths.webhook_delivery_resend(endpoint_id, delivery_id), **options
        )
        return cast(WebhookDelivery, result.data)

    async def replay(
        self, endpoint_id: str, body: ReplayWebhooksRequest, **options: Any
    ) -> WebhookReplayResult:
        """``POST …/{endpoint_id}/replay``."""
        result = await self._transport.request(
            "POST", _paths.webhook_replay(endpoint_id), body=body, **options
        )
        return cast(WebhookReplayResult, result.data)

    async def rotate_secret(self, endpoint_id: str, **options: Any) -> RotateWebhookSecretResponse:
        """``POST …/{endpoint_id}/rotate-secret`` — returns the NEW secret (once)."""
        result = await self._transport.request(
            "POST", _paths.webhook_rotate_secret(endpoint_id), **options
        )
        return cast(RotateWebhookSecretResponse, result.data)

    async def test(self, endpoint_id: str, **options: Any) -> WebhookTestResult:
        """``POST …/{endpoint_id}/test`` — sends a signed ``endpoint.test`` event."""
        result = await self._transport.request("POST", _paths.webhook_test(endpoint_id), **options)
        return cast(WebhookTestResult, result.data)


__all__ = ["AsyncWebhookEndpoints", "DeliveryStatus", "WebhookEndpoints"]
