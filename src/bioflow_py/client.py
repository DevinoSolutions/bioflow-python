"""The synchronous BioFlow client."""

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
    AuthStyle,
    RawResult,
    SyncTransport,
)
from .operations import HttpMethod
from .resources import Analytics, Contacts, Files, Pages, UsageResource, WebhookEndpoints
from .webhooks import Webhooks


class BioFlow:
    """The BioFlow public-API client.

    ```python
    from bioflow_py import BioFlow

    with BioFlow(api_key="bf_live_…") as bioflow:
        for page in bioflow.pages.list():
            print(page["slug"])
    ```

    Args:
        api_key: A ``bf_live_``/``bf_test_`` secret key. Falls back to the
            ``BIOFLOW_API_KEY`` environment variable. Server-side only.
        base_url: API origin. Defaults to ``https://app.getbioflow.com``; paths
            already carry the ``/v1`` prefix, so do not append it here.
        timeout: Per-request timeout in seconds (default 30).
        max_retries: Retries after the first attempt (default 2).
        max_retry_after: Longest ``Retry-After`` the SDK will sleep for, in
            seconds (default 60). Anything longer raises instead of sleeping.
        auth_style: ``"bearer"`` (default) sends ``Authorization: Bearer …``;
            ``"x-api-key"`` sends the key in the ``x-api-key`` header.
        auto_idempotency_keys: Auto-generate an ``Idempotency-Key`` on POSTs
            (default True) — this is also what makes them safely retryable.
        default_headers: Extra headers merged into every request.
        debug: ``True`` to log to stderr, or a callable sink. Lines are
            secret-redacted.
        http_client: Bring your own :class:`httpx.Client` (proxies, transports,
            test doubles). The SDK never closes a client it did not create.
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
        http_client: httpx.Client | None = None,
    ) -> None:
        self._transport = SyncTransport(
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
        self.pages = Pages(self._transport)
        self.contacts = Contacts(self._transport)
        self.files = Files(self._transport)
        self.analytics = Analytics(self._transport)
        self.usage = UsageResource(self._transport)
        self.webhook_endpoints = WebhookEndpoints(self._transport)
        self.webhooks = Webhooks()
        """Signature verification for received webhooks (no API key needed)."""

    @property
    def base_url(self) -> str:
        """The API origin this client talks to."""
        return self._transport.base_url

    def request(
        self,
        method: HttpMethod,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        body: Any = NOT_GIVEN,
        **options: Any,
    ) -> RawResult[Any]:
        """Raw escape hatch for endpoints newer than this SDK build.

        Same auth, retry, idempotency and error pipeline as the typed methods.
        Returns the parsed body plus ``status``, ``headers``, ``request_id``,
        ``idempotency_replayed`` and ``rate_limit``.
        """
        return self._transport.request(method, path, query=query, body=body, **options)

    def close(self) -> None:
        """Close the underlying HTTP client (no-op for a caller-supplied one)."""
        self._transport.close()

    def __enter__(self) -> BioFlow:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


__all__ = ["BioFlow"]
