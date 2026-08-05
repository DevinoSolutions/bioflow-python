"""Idempotency-Key generation, propagation and replay surfacing."""

from __future__ import annotations

import re
from typing import Any

import httpx
import respx

from conftest import TEST_BASE_URL, make_client

# The server accepts 1-200 visible ASCII characters.
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[\x21-\x7e]{1,200}$")

PAGES_URL = f"{TEST_BASE_URL}/v1/pages"


def _client(**kwargs: object) -> Any:
    return make_client(**kwargs)


@respx.mock
def test_a_post_gets_an_auto_generated_key_in_the_documented_format() -> None:
    route = respx.mock.post(PAGES_URL).mock(return_value=httpx.Response(201, json={"id": "pg_1"}))
    with _client() as client:
        client.pages.create({"title": "Hi"})
    key = route.calls.last.request.headers["idempotency-key"]
    assert key.startswith("sdk_")
    assert IDEMPOTENCY_KEY_PATTERN.match(key)


@respx.mock
def test_two_posts_get_two_different_keys() -> None:
    route = respx.mock.post(PAGES_URL).mock(return_value=httpx.Response(201, json={"id": "pg_1"}))
    with _client() as client:
        client.pages.create({"title": "One"})
        client.pages.create({"title": "Two"})
    keys = [call.request.headers["idempotency-key"] for call in route.calls]
    assert keys[0] != keys[1]


@respx.mock
def test_get_patch_and_delete_never_carry_an_idempotency_key() -> None:
    get_route = respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(
        return_value=httpx.Response(200, json={})
    )
    patch_route = respx.mock.patch(f"{PAGES_URL}/pg_1").mock(
        return_value=httpx.Response(200, json={"id": "pg_1"})
    )
    delete_route = respx.mock.delete(f"{PAGES_URL}/pg_1").mock(return_value=httpx.Response(204))
    with _client() as client:
        client.usage.get()
        client.pages.update("pg_1", {"expected_updated_at": "t"})
        client.pages.delete("pg_1")
    for route in (get_route, patch_route, delete_route):
        assert "idempotency-key" not in route.calls.last.request.headers


@respx.mock
def test_a_caller_supplied_key_wins_over_the_generated_one() -> None:
    route = respx.mock.post(PAGES_URL).mock(return_value=httpx.Response(201, json={"id": "pg_1"}))
    with _client() as client:
        client.pages.create({"title": "Hi"}, idempotency_key="my-own-key-123")
    assert route.calls.last.request.headers["idempotency-key"] == "my-own-key-123"


@respx.mock
def test_auto_idempotency_keys_can_be_switched_off() -> None:
    route = respx.mock.post(PAGES_URL).mock(return_value=httpx.Response(201, json={"id": "pg_1"}))
    with _client(auto_idempotency_keys=False) as client:
        client.pages.create({"title": "Hi"})
    assert "idempotency-key" not in route.calls.last.request.headers


@respx.mock
def test_an_explicit_key_still_works_when_auto_generation_is_off() -> None:
    route = respx.mock.post(PAGES_URL).mock(return_value=httpx.Response(201, json={"id": "pg_1"}))
    with _client(auto_idempotency_keys=False) as client:
        client.pages.create({"title": "Hi"}, idempotency_key="explicit")
    assert route.calls.last.request.headers["idempotency-key"] == "explicit"


@respx.mock
def test_a_replayed_response_is_flagged_on_the_raw_result() -> None:
    respx.mock.post(PAGES_URL).mock(
        return_value=httpx.Response(
            201, json={"id": "pg_1"}, headers={"idempotency-replayed": "true"}
        )
    )
    with _client() as client:
        result = client.request("POST", "/v1/pages", body={"title": "Hi"})
    assert result.idempotency_replayed is True


@respx.mock
def test_a_fresh_response_is_not_flagged_as_replayed() -> None:
    respx.mock.post(PAGES_URL).mock(return_value=httpx.Response(201, json={"id": "pg_1"}))
    with _client() as client:
        result = client.request("POST", "/v1/pages", body={"title": "Hi"})
    assert result.idempotency_replayed is False


@respx.mock
def test_every_ledgered_operation_sends_a_key() -> None:
    """The registry says which POSTs the server ledgers; all of them must carry one."""
    from bioflow_py import OPERATIONS

    ledgered = [op for op in OPERATIONS.values() if op.idempotent]
    assert len(ledgered) == 8
    for operation in ledgered:
        concrete = operation.path.replace("{page_id}", "pg_1")
        concrete = concrete.replace("{endpoint_id}", "we_1").replace("{delivery_id}", "wd_1")
        route = respx.mock.post(f"{TEST_BASE_URL}{concrete}").mock(
            return_value=httpx.Response(200, json={})
        )
        with _client() as client:
            client.request("POST", concrete, body={})
        assert "idempotency-key" in route.calls.last.request.headers, operation.path
