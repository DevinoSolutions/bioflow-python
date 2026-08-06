"""The async client is a true twin: same namespaces, same methods, same results."""

from __future__ import annotations

import inspect
from typing import Any

import httpx
import pytest
import respx

from bioflow_py import AsyncBioFlow, BioFlow
from conftest import TEST_API_KEY, TEST_BASE_URL, make_async_client, make_client
from test_resources import CASES as RESOURCE_CASES

NAMESPACES = ["pages", "contacts", "files", "analytics", "usage", "webhook_endpoints", "webhooks"]


def _public_names(obj: object) -> list[str]:
    return sorted(name for name in dir(obj) if not name.startswith("_"))


def _sync_client() -> BioFlow:
    return make_client()


def _async_client() -> AsyncBioFlow:
    return make_async_client()


def test_both_clients_expose_the_same_namespaces() -> None:
    with _sync_client() as sync_client:
        async_client = _async_client()
        assert _public_names(sync_client) == _public_names(async_client)
    for namespace in NAMESPACES:
        assert hasattr(sync_client, namespace)
        assert hasattr(async_client, namespace)


@pytest.mark.parametrize("namespace", NAMESPACES)
def test_each_namespace_exposes_the_same_method_names(namespace: str) -> None:
    with _sync_client() as sync_client:
        async_client = _async_client()
        assert _public_names(getattr(sync_client, namespace)) == _public_names(
            getattr(async_client, namespace)
        )


@pytest.mark.parametrize("namespace", [n for n in NAMESPACES if n != "webhooks"])
def test_every_async_resource_method_is_awaitable(namespace: str) -> None:
    async_client = _async_client()
    resource = getattr(async_client, namespace)
    for name in _public_names(resource):
        method = getattr(resource, name)
        assert inspect.iscoroutinefunction(method), f"{namespace}.{name} is not awaitable"


@pytest.mark.parametrize("namespace", [n for n in NAMESPACES if n != "webhooks"])
def test_matching_methods_take_the_same_parameters(namespace: str) -> None:
    with _sync_client() as sync_client:
        async_client = _async_client()
        sync_resource = getattr(sync_client, namespace)
        async_resource = getattr(async_client, namespace)
        for name in _public_names(sync_resource):
            sync_signature = inspect.signature(getattr(sync_resource, name))
            async_signature = inspect.signature(getattr(async_resource, name))
            assert list(sync_signature.parameters) == list(async_signature.parameters), name


@respx.mock
async def test_the_async_client_returns_the_same_payload_as_the_sync_one() -> None:
    payload = {
        "meters": [{"name": "api_requests", "limit": 10_000, "used": 12, "remaining": 9_988}]
    }
    respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(return_value=httpx.Response(200, json=payload))
    with _sync_client() as sync_client:
        sync_result = sync_client.usage.get()
    async with _async_client() as async_client:
        async_result = await async_client.usage.get()
    assert sync_result == async_result == payload


@respx.mock
async def test_the_async_escape_hatch_mirrors_the_sync_one() -> None:
    respx.mock.get(f"{TEST_BASE_URL}/v1/anything").mock(
        return_value=httpx.Response(200, json={"ok": True}, headers={"x-request-id": "req_1"})
    )
    with _sync_client() as sync_client:
        sync_raw = sync_client.request("GET", "/v1/anything")
    async with _async_client() as async_client:
        async_raw = await async_client.request("GET", "/v1/anything")
    assert sync_raw.data == async_raw.data
    assert sync_raw.request_id == async_raw.request_id == "req_1"


@respx.mock
async def test_a_204_returns_none_on_both_clients() -> None:
    respx.mock.delete(f"{TEST_BASE_URL}/v1/pages/pg_1").mock(return_value=httpx.Response(204))
    with _sync_client() as sync_client:
        assert sync_client.pages.delete("pg_1") is None
    async with _async_client() as async_client:
        assert await async_client.pages.delete("pg_1") is None


async def test_a_caller_supplied_async_http_client_is_never_closed_by_the_sdk() -> None:
    http_client = httpx.AsyncClient()
    async with AsyncBioFlow(api_key=TEST_API_KEY, base_url=TEST_BASE_URL, http_client=http_client):
        pass
    assert not http_client.is_closed
    await http_client.aclose()


def test_webhook_verification_is_synchronous_on_both_clients() -> None:
    """Signature checking is CPU-only — making it awaitable would be noise."""
    async_client = _async_client()
    assert not inspect.iscoroutinefunction(async_client.webhooks.verify)


ASYNC_CALLS: dict[str, Any] = {
    "getAnalyticsSummary": lambda c: c.analytics.summary(range_days=7),
    "listContacts": lambda c: c.contacts.list(limit=2),
    "listFiles": lambda c: c.files.list(limit=2),
    "listPages": lambda c: c.pages.list(limit=2, after="cur_1"),
    "createPage": lambda c: c.pages.create({"title": "Hello"}),
    "getPage": lambda c: c.pages.get("pg_1"),
    "updatePage": lambda c: c.pages.update("pg_1", {"expected_updated_at": "t0"}),
    "deletePage": lambda c: c.pages.delete("pg_1"),
    "addBlock": lambda c: c.pages.add_block("pg_1", {"type": "link", "data": {}}),
    "removeBlock": lambda c: c.pages.remove_block("pg_1", "bl_1", expected_updated_at="t0"),
    "publishPage": lambda c: c.pages.publish("pg_1"),
    "getUsage": lambda c: c.usage.get(),
    "listWebhookEndpoints": lambda c: c.webhook_endpoints.list(),
    "createWebhookEndpoint": lambda c: c.webhook_endpoints.create(
        {"url": "https://example.com/hook"}
    ),
    "getWebhookEndpoint": lambda c: c.webhook_endpoints.get("we_1"),
    "updateWebhookEndpoint": lambda c: c.webhook_endpoints.update("we_1", {"enabled": False}),
    "deleteWebhookEndpoint": lambda c: c.webhook_endpoints.delete("we_1"),
    "listWebhookDeliveries": lambda c: c.webhook_endpoints.deliveries(
        "we_1", limit=5, status="FAILED"
    ),
    "resendWebhookDelivery": lambda c: c.webhook_endpoints.resend_delivery("we_1", "wd_1"),
    "replayWebhookDeliveries": lambda c: c.webhook_endpoints.replay(
        "we_1", {"since": "2026-08-01T00:00:00Z"}
    ),
    "rotateWebhookSecret": lambda c: c.webhook_endpoints.rotate_secret("we_1"),
    "testWebhookEndpoint": lambda c: c.webhook_endpoints.test("we_1"),
}


def test_there_is_an_async_call_for_every_operation() -> None:
    assert sorted(ASYNC_CALLS) == sorted(case[0] for case in RESOURCE_CASES)


@pytest.mark.parametrize("case", RESOURCE_CASES, ids=lambda case: str(case[0]))
@respx.mock
async def test_every_async_operation_hits_the_same_url_as_its_sync_twin(case: Any) -> None:
    operation_id, method, path, query, _headers, status, payload, sync_call = case
    route = respx.mock.request(method, f"{TEST_BASE_URL}{path}").mock(
        return_value=(
            httpx.Response(status) if payload is None else httpx.Response(status, json=payload)
        )
    )
    with make_client() as sync_client:
        sync_result = sync_call(sync_client)
    async with make_async_client() as async_client:
        async_result = await ASYNC_CALLS[operation_id](async_client)

    assert route.call_count == 2, operation_id
    sync_request, async_request = (call.request for call in route.calls)
    assert async_request.method == sync_request.method == method
    assert async_request.url.path == sync_request.url.path == path
    assert async_request.url.query.decode() == sync_request.url.query.decode() == query
    if status == 204:
        assert sync_result is None and async_result is None
    elif hasattr(sync_result, "data"):  # a cursor page
        assert async_result.data == sync_result.data
    else:
        assert async_result == sync_result
