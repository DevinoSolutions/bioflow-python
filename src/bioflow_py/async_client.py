"""The asynchronous BioFlow client — the same surface, awaitable."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import TracebackType
from typing import Any

import httpx

from ._http import (
    DEFAULT_BASE_URL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_RETRY_AFTER,
    DEFAULT_TIMEOUT,
    NOT_GIVEN,
    AsyncTransport,
    AuthStyle,
    RawResult,
)
from .operations import HttpMethod
from .resources import (
    AsyncAnalytics,
    AsyncContacts,
    AsyncFiles,
    AsyncPages,
    AsyncUsageResource,
    AsyncWebhookEndpoints,
)
from .webhooks import Webhooks


class AsyncBioFlow:
    """The awaitable twin of :class:`~bioflow_py.client.BioFlow`.

    ```python
    import asyncio
    from bioflow_py import AsyncBioFlow

    async def main() -> None:
        async with AsyncBioFlow(api_key="bf_live_…") as bioflow:
            pages = await bioflow.pages.list()
            async for page in pages:
                print(page["slug"])

    asyncio.run(main())
    ```

    Every constructor argument matches :class:`~bioflow_py.client.BioFlow`, except
    ``http_client``, which takes an :class:`httpx.AsyncClient`.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        max_retry_after: float = DEFAULT_MAX_RETRY_AFTER,
        auth_style: AuthStyle = "bearer",
        auto_idempotency_keys: bool = True,
        default_headers: Mapping[str, str] | None = None,
        debug: bool | Callable[[str], None] = False,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._transport = AsyncTransport(
            api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            max_retry_after=max_retry_after,
            auth_style=auth_style,
            auto_idempotency_keys=auto_idempotency_keys,
            default_headers=default_headers,
            debug=debug,
            http_client=http_client,
        )
        self.pages = AsyncPages(self._transport)
        self.contacts = AsyncContacts(self._transport)
        self.files = AsyncFiles(self._transport)
        self.analytics = AsyncAnalytics(self._transport)
        self.usage = AsyncUsageResource(self._transport)
        self.webhook_endpoints = AsyncWebhookEndpoints(self._transport)
        self.webhooks = Webhooks()
        """Signature verification for received webhooks (synchronous, no API key)."""

    @property
    def base_url(self) -> str:
        """The API origin this client talks to."""
        return self._transport.base_url

    async def request(
        self,
        method: HttpMethod,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        body: Any = NOT_GIVEN,
        **options: Any,
    ) -> RawResult[Any]:
        """Raw escape hatch for endpoints newer than this SDK build."""
        return await self._transport.request(method, path, query=query, body=body, **options)

    async def close(self) -> None:
        """Close the underlying HTTP client (no-op for a caller-supplied one)."""
        await self._transport.aclose()

    async def __aenter__(self) -> AsyncBioFlow:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()


__all__ = ["AsyncBioFlow"]
