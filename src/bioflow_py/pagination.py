"""Cursor pagination over the ``/v1`` list envelope ``{data, has_more, next_cursor}``.

Every list method returns a :class:`CursorPage` (or :class:`AsyncCursorPage`):
use ``.data`` for the single page (escape hatch) or iterate the page object to
walk the **whole** collection — following pages are fetched lazily with the same
query.

Cursors are opaque and bound to the operation that minted them: reusing one on a
different query is a 400 ``invalid_request`` (``cursor_operation_mismatch``), so
the SDK never carries a cursor between methods.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping
from typing import Any, Generic, TypeVar

from ._http import AsyncTransport, RateLimitInfo, RawResult, SyncTransport

Item = TypeVar("Item")


class _PageBase(Generic[Item]):
    """The envelope fields both page flavours expose."""

    def __init__(self, result: RawResult[Any]) -> None:
        envelope = result.data if isinstance(result.data, dict) else {}
        self.data: list[Item] = list(envelope.get("data") or [])
        """Items on THIS page. Reading it never triggers another request."""

        self.has_more: bool = bool(envelope.get("has_more"))
        """True when the server holds more items after this page."""

        self.next_cursor: str | None = envelope.get("next_cursor")
        """Opaque cursor for the following page, or ``None``."""

        self.request_id: str | None = result.request_id
        """``X-Request-Id`` of the response that produced this page."""

        self.rate_limit: RateLimitInfo | None = result.rate_limit
        """Limiter state reported alongside this page."""

        self.status: int = result.status

    def has_next_page(self) -> bool:
        """True when :meth:`next_page` would fetch something."""
        return self.has_more and self.next_cursor is not None

    def __len__(self) -> int:
        return len(self.data)

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} items={len(self.data)} "
            f"has_more={self.has_more} request_id={self.request_id!r}>"
        )


class CursorPage(_PageBase[Item]):
    """A page of results; iterating it walks every following page too."""

    def __init__(
        self,
        result: RawResult[Any],
        fetch_after: Callable[[str], CursorPage[Item]],
    ) -> None:
        super().__init__(result)
        self._fetch_after = fetch_after

    def next_page(self) -> CursorPage[Item] | None:
        """Fetch the following page, or ``None`` when this is the last one."""
        if not self.has_next_page():
            return None
        assert self.next_cursor is not None
        return self._fetch_after(self.next_cursor)

    def __iter__(self) -> Iterator[Item]:
        page: CursorPage[Item] = self
        while True:
            yield from page.data
            following = page.next_page()
            if following is None:
                return
            page = following


class AsyncCursorPage(_PageBase[Item]):
    """The awaitable twin of :class:`CursorPage`."""

    def __init__(
        self,
        result: RawResult[Any],
        fetch_after: Callable[[str], Awaitable[AsyncCursorPage[Item]]],
    ) -> None:
        super().__init__(result)
        self._fetch_after = fetch_after

    async def next_page(self) -> AsyncCursorPage[Item] | None:
        """Fetch the following page, or ``None`` when this is the last one."""
        if not self.has_next_page():
            return None
        assert self.next_cursor is not None
        return await self._fetch_after(self.next_cursor)

    async def __aiter__(self) -> AsyncIterator[Item]:
        page: AsyncCursorPage[Item] = self
        while True:
            for item in page.data:
                yield item
            following = await page.next_page()
            if following is None:
                return
            page = following


def fetch_cursor_page(
    transport: SyncTransport,
    path: str,
    query: Mapping[str, Any],
    options: Mapping[str, Any],
) -> CursorPage[Any]:
    """GET ``path`` and wrap the envelope in a self-advancing :class:`CursorPage`."""
    result = transport.request("GET", path, query=query, **options)

    def fetch_after(after: str) -> CursorPage[Any]:
        return fetch_cursor_page(transport, path, {**query, "after": after}, options)

    return CursorPage(result, fetch_after)


async def fetch_cursor_page_async(
    transport: AsyncTransport,
    path: str,
    query: Mapping[str, Any],
    options: Mapping[str, Any],
) -> AsyncCursorPage[Any]:
    """Awaitable twin of :func:`fetch_cursor_page`."""
    result = await transport.request("GET", path, query=query, **options)

    async def fetch_after(after: str) -> AsyncCursorPage[Any]:
        return await fetch_cursor_page_async(transport, path, {**query, "after": after}, options)

    return AsyncCursorPage(result, fetch_after)


__all__ = [
    "AsyncCursorPage",
    "CursorPage",
    "fetch_cursor_page",
    "fetch_cursor_page_async",
]
