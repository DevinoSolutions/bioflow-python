"""Cursor pages: envelope parsing, lazy page walking and query carry-over."""

from __future__ import annotations

import httpx
import respx

from conftest import TEST_BASE_URL, make_async_client, make_client

PAGES_URL = f"{TEST_BASE_URL}/v1/pages"


def _page(ids: list[str], next_cursor: str | None) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "data": [{"id": page_id} for page_id in ids],
            "has_more": next_cursor is not None,
            "next_cursor": next_cursor,
        },
        headers={"x-request-id": f"req_{ids[0]}"},
    )


@respx.mock
def test_the_envelope_is_parsed_into_data_has_more_and_next_cursor() -> None:
    respx.mock.get(PAGES_URL).mock(return_value=_page(["pg_1", "pg_2"], "cur_2"))
    with make_client() as client:
        page = client.pages.list()
    assert [item["id"] for item in page.data] == ["pg_1", "pg_2"]
    assert page.has_more is True
    assert page.next_cursor == "cur_2"
    assert page.has_next_page() is True
    assert page.request_id == "req_pg_1"
    assert len(page) == 2


@respx.mock
def test_reading_data_never_triggers_another_request() -> None:
    route = respx.mock.get(PAGES_URL).mock(return_value=_page(["pg_1"], "cur_2"))
    with make_client() as client:
        page = client.pages.list()
        assert len(page.data) == 1
        assert page.data[0]["id"] == "pg_1"
    assert route.call_count == 1


@respx.mock
def test_a_last_page_reports_no_following_page() -> None:
    respx.mock.get(PAGES_URL).mock(return_value=_page(["pg_1"], None))
    with make_client() as client:
        page = client.pages.list()
        assert page.has_next_page() is False
        assert page.next_page() is None


@respx.mock
def test_iterating_walks_every_page_and_stops_on_has_more_false() -> None:
    respx.mock.get(PAGES_URL).mock(
        side_effect=[
            _page(["pg_1", "pg_2"], "cur_2"),
            _page(["pg_3"], "cur_3"),
            _page(["pg_4"], None),
        ]
    )
    with make_client() as client:
        collected = [item["id"] for item in client.pages.list(limit=2)]
    assert collected == ["pg_1", "pg_2", "pg_3", "pg_4"]


@respx.mock
def test_following_pages_carry_the_original_query_plus_the_cursor() -> None:
    route = respx.mock.get(PAGES_URL).mock(
        side_effect=[_page(["pg_1"], "cur_2"), _page(["pg_2"], None)]
    )
    with make_client() as client:
        list(client.pages.list(limit=2))
    first, second = (call.request.url.params for call in route.calls)
    assert dict(first) == {"limit": "2"}
    assert dict(second) == {"limit": "2", "after": "cur_2"}


@respx.mock
def test_delivery_pages_carry_their_status_filter_across_pages() -> None:
    url = f"{TEST_BASE_URL}/v1/webhook-endpoints/we_1/deliveries"
    route = respx.mock.get(url).mock(side_effect=[_page(["wd_1"], "cur_2"), _page(["wd_2"], None)])
    with make_client() as client:
        list(client.webhook_endpoints.deliveries("we_1", status="FAILED"))
    assert dict(route.calls[1].request.url.params) == {"status": "FAILED", "after": "cur_2"}


@respx.mock
def test_next_page_fetches_exactly_one_more_page() -> None:
    route = respx.mock.get(PAGES_URL).mock(
        side_effect=[_page(["pg_1"], "cur_2"), _page(["pg_2"], None)]
    )
    with make_client() as client:
        first = client.pages.list()
        second = first.next_page()
    assert second is not None
    assert [item["id"] for item in second.data] == ["pg_2"]
    assert route.call_count == 2


@respx.mock
def test_an_empty_collection_iterates_zero_times() -> None:
    respx.mock.get(PAGES_URL).mock(
        return_value=httpx.Response(200, json={"data": [], "has_more": False, "next_cursor": None})
    )
    with make_client() as client:
        assert list(client.pages.list()) == []


@respx.mock
def test_limiter_state_is_attached_to_the_page() -> None:
    respx.mock.get(PAGES_URL).mock(
        return_value=httpx.Response(
            200,
            json={"data": [], "has_more": False, "next_cursor": None},
            headers={"ratelimit": '"per-key-minute";r=58;t=30'},
        )
    )
    with make_client() as client:
        page = client.pages.list()
    assert page.rate_limit is not None
    assert page.rate_limit.remaining == 58


@respx.mock
async def test_the_async_page_walks_the_whole_collection_too() -> None:
    respx.mock.get(PAGES_URL).mock(side_effect=[_page(["pg_1"], "cur_2"), _page(["pg_2"], None)])
    async with make_async_client() as client:
        page = await client.pages.list()
        collected = [item["id"] async for item in page]
    assert collected == ["pg_1", "pg_2"]


@respx.mock
async def test_the_async_page_exposes_the_same_envelope_fields() -> None:
    respx.mock.get(PAGES_URL).mock(return_value=_page(["pg_1"], "cur_2"))
    async with make_async_client() as client:
        page = await client.pages.list()
    assert page.has_more is True
    assert page.next_cursor == "cur_2"
    assert page.has_next_page() is True
    assert "has_more=True" in repr(page)
