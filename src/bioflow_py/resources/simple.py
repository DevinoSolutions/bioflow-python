"""The single-call resources: contacts, files, analytics, usage."""

from __future__ import annotations

from typing import Any, cast

from bioflow_py._http import AsyncTransport, SyncTransport
from bioflow_py.models import AnalyticsSummary, Contact, FileObject, Usage
from bioflow_py.pagination import (
    AsyncCursorPage,
    CursorPage,
    fetch_cursor_page,
    fetch_cursor_page_async,
)

from . import _paths


class Contacts:
    """``client.contacts`` — leads captured by page blocks."""

    def __init__(self, transport: SyncTransport) -> None:
        self._transport = transport

    def list(
        self,
        *,
        limit: int | None = None,
        after: str | None = None,
        **options: Any,
    ) -> CursorPage[Contact]:
        """``GET /v1/contacts`` — cursor-paginated."""
        return fetch_cursor_page(
            self._transport, _paths.CONTACTS, {"limit": limit, "after": after}, options
        )


class AsyncContacts:
    """Awaitable twin of :class:`Contacts`."""

    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def list(
        self,
        *,
        limit: int | None = None,
        after: str | None = None,
        **options: Any,
    ) -> AsyncCursorPage[Contact]:
        """``GET /v1/contacts`` — cursor-paginated."""
        return await fetch_cursor_page_async(
            self._transport, _paths.CONTACTS, {"limit": limit, "after": after}, options
        )


class Files:
    """``client.files`` — files uploaded to the workspace."""

    def __init__(self, transport: SyncTransport) -> None:
        self._transport = transport

    def list(
        self,
        *,
        limit: int | None = None,
        after: str | None = None,
        **options: Any,
    ) -> CursorPage[FileObject]:
        """``GET /v1/files`` — cursor-paginated."""
        return fetch_cursor_page(
            self._transport, _paths.FILES, {"limit": limit, "after": after}, options
        )


class AsyncFiles:
    """Awaitable twin of :class:`Files`."""

    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def list(
        self,
        *,
        limit: int | None = None,
        after: str | None = None,
        **options: Any,
    ) -> AsyncCursorPage[FileObject]:
        """``GET /v1/files`` — cursor-paginated."""
        return await fetch_cursor_page_async(
            self._transport, _paths.FILES, {"limit": limit, "after": after}, options
        )


class Analytics:
    """``client.analytics`` — aggregated page performance."""

    def __init__(self, transport: SyncTransport) -> None:
        self._transport = transport

    def summary(self, *, range_days: int | None = None, **options: Any) -> AnalyticsSummary:
        """``GET /v1/analytics/summary`` — totals, top links, referrers and tips."""
        result = self._transport.request(
            "GET", _paths.ANALYTICS_SUMMARY, query={"range_days": range_days}, **options
        )
        return cast(AnalyticsSummary, result.data)


class AsyncAnalytics:
    """Awaitable twin of :class:`Analytics`."""

    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def summary(self, *, range_days: int | None = None, **options: Any) -> AnalyticsSummary:
        """``GET /v1/analytics/summary``."""
        result = await self._transport.request(
            "GET", _paths.ANALYTICS_SUMMARY, query={"range_days": range_days}, **options
        )
        return cast(AnalyticsSummary, result.data)


class UsageResource:
    """``client.usage`` — the workspace's meter and burst limits."""

    def __init__(self, transport: SyncTransport) -> None:
        self._transport = transport

    def get(self, **options: Any) -> Usage:
        """``GET /v1/usage`` — free to call: never consumes quota."""
        result = self._transport.request("GET", _paths.USAGE, **options)
        return cast(Usage, result.data)


class AsyncUsageResource:
    """Awaitable twin of :class:`UsageResource`."""

    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def get(self, **options: Any) -> Usage:
        """``GET /v1/usage`` — free to call: never consumes quota."""
        result = await self._transport.request("GET", _paths.USAGE, **options)
        return cast(Usage, result.data)


__all__ = [
    "Analytics",
    "AsyncAnalytics",
    "AsyncContacts",
    "AsyncFiles",
    "AsyncUsageResource",
    "Contacts",
    "Files",
    "UsageResource",
]
