"""The ``pages`` resource — the link-in-bio pages themselves."""

from __future__ import annotations

from typing import Any, cast

from bioflow_py._http import AsyncTransport, SyncTransport
from bioflow_py.models import (
    AddBlockRequest,
    CreatePageRequest,
    Page,
    PageSummary,
    PublishPageRequest,
    PublishResult,
    UpdatePageRequest,
)
from bioflow_py.pagination import (
    AsyncCursorPage,
    CursorPage,
    fetch_cursor_page,
    fetch_cursor_page_async,
)

from . import _paths


class Pages:
    """``client.pages`` — list, create, edit and publish pages.

    Every method accepts the per-call overrides ``timeout``, ``max_retries``,
    ``idempotency_key``, ``headers`` and ``extra_query``.
    """

    def __init__(self, transport: SyncTransport) -> None:
        self._transport = transport

    def list(
        self,
        *,
        limit: int | None = None,
        after: str | None = None,
        **options: Any,
    ) -> CursorPage[PageSummary]:
        """``GET /v1/pages`` — cursor-paginated; iterating walks every page."""
        return fetch_cursor_page(
            self._transport, _paths.PAGES, {"limit": limit, "after": after}, options
        )

    def create(self, body: CreatePageRequest, **options: Any) -> Page:
        """``POST /v1/pages`` — creates a draft page (201)."""
        result = self._transport.request("POST", _paths.PAGES, body=body, **options)
        return cast(Page, result.data)

    def get(self, page_id: str, **options: Any) -> Page:
        """``GET /v1/pages/{page_id}``."""
        result = self._transport.request("GET", _paths.page(page_id), **options)
        return cast(Page, result.data)

    def update(self, page_id: str, body: UpdatePageRequest, **options: Any) -> Page:
        """``PATCH /v1/pages/{page_id}`` — merge-patch of the draft.

        Pass the draft's current ``updated_at`` as ``expected_updated_at``
        (optimistic concurrency); a stale value yields 409 ``stale_snapshot``.
        """
        result = self._transport.request("PATCH", _paths.page(page_id), body=body, **options)
        return cast(Page, result.data)

    def delete(self, page_id: str, **options: Any) -> None:
        """``DELETE /v1/pages/{page_id}`` — 204, returns ``None``."""
        self._transport.request("DELETE", _paths.page(page_id), **options)

    def add_block(self, page_id: str, body: AddBlockRequest, **options: Any) -> Page:
        """``POST /v1/pages/{page_id}/blocks`` — appends a block to the draft (201)."""
        result = self._transport.request("POST", _paths.page_blocks(page_id), body=body, **options)
        return cast(Page, result.data)

    def remove_block(
        self,
        page_id: str,
        block_id: str,
        *,
        expected_updated_at: str,
        **options: Any,
    ) -> Page:
        """``DELETE /v1/pages/{page_id}/blocks/{block_id}``.

        ``expected_updated_at`` is required: it is the draft ``updated_at`` you
        last read, and a mismatch is refused with 409 ``stale_snapshot``.
        """
        result = self._transport.request(
            "DELETE",
            _paths.page_block(page_id, block_id),
            query={"expected_updated_at": expected_updated_at},
            **options,
        )
        return cast(Page, result.data)

    def publish(
        self,
        page_id: str,
        body: PublishPageRequest | None = None,
        **options: Any,
    ) -> PublishResult:
        """``POST /v1/pages/{page_id}/publish`` — immediate, or scheduled via
        ``starts_at``. Requires the ``publish`` scope."""
        result = self._transport.request(
            "POST", _paths.page_publish(page_id), body=body if body is not None else {}, **options
        )
        return cast(PublishResult, result.data)


class AsyncPages:
    """Awaitable twin of :class:`Pages`."""

    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def list(
        self,
        *,
        limit: int | None = None,
        after: str | None = None,
        **options: Any,
    ) -> AsyncCursorPage[PageSummary]:
        """``GET /v1/pages`` — cursor-paginated; ``async for`` walks every page."""
        return await fetch_cursor_page_async(
            self._transport, _paths.PAGES, {"limit": limit, "after": after}, options
        )

    async def create(self, body: CreatePageRequest, **options: Any) -> Page:
        """``POST /v1/pages`` — creates a draft page (201)."""
        result = await self._transport.request("POST", _paths.PAGES, body=body, **options)
        return cast(Page, result.data)

    async def get(self, page_id: str, **options: Any) -> Page:
        """``GET /v1/pages/{page_id}``."""
        result = await self._transport.request("GET", _paths.page(page_id), **options)
        return cast(Page, result.data)

    async def update(self, page_id: str, body: UpdatePageRequest, **options: Any) -> Page:
        """``PATCH /v1/pages/{page_id}`` — merge-patch of the draft."""
        result = await self._transport.request("PATCH", _paths.page(page_id), body=body, **options)
        return cast(Page, result.data)

    async def delete(self, page_id: str, **options: Any) -> None:
        """``DELETE /v1/pages/{page_id}`` — 204, returns ``None``."""
        await self._transport.request("DELETE", _paths.page(page_id), **options)

    async def add_block(self, page_id: str, body: AddBlockRequest, **options: Any) -> Page:
        """``POST /v1/pages/{page_id}/blocks`` — appends a block to the draft (201)."""
        result = await self._transport.request(
            "POST", _paths.page_blocks(page_id), body=body, **options
        )
        return cast(Page, result.data)

    async def remove_block(
        self,
        page_id: str,
        block_id: str,
        *,
        expected_updated_at: str,
        **options: Any,
    ) -> Page:
        """``DELETE /v1/pages/{page_id}/blocks/{block_id}``."""
        result = await self._transport.request(
            "DELETE",
            _paths.page_block(page_id, block_id),
            query={"expected_updated_at": expected_updated_at},
            **options,
        )
        return cast(Page, result.data)

    async def publish(
        self,
        page_id: str,
        body: PublishPageRequest | None = None,
        **options: Any,
    ) -> PublishResult:
        """``POST /v1/pages/{page_id}/publish``."""
        result = await self._transport.request(
            "POST", _paths.page_publish(page_id), body=body if body is not None else {}, **options
        )
        return cast(PublishResult, result.data)


__all__ = ["AsyncPages", "Pages"]
