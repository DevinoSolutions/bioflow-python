"""One mocked round trip per public operation — 22 of them, no gaps.

Each case asserts the method, the concrete URL, the serialized query string and
the shape the caller gets back, so a typo in any resource method fails here
rather than in production.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
import respx

from bioflow_py import OPERATIONS
from conftest import TEST_BASE_URL, make_client

ENVELOPE = {"data": [{"id": "x_1"}], "has_more": False, "next_cursor": None}

Case = tuple[str, str, str, str, dict[str, str], int, Any, Callable[[Any], Any]]

CASES: list[Case] = [
    (
        "getAnalyticsSummary",
        "GET",
        "/v1/analytics/summary",
        "range_days=7",
        {},
        200,
        {"range_days": 7, "totals": {}},
        lambda c: c.analytics.summary(range_days=7),
    ),
    (
        "listContacts",
        "GET",
        "/v1/contacts",
        "limit=2",
        {},
        200,
        ENVELOPE,
        lambda c: c.contacts.list(limit=2),
    ),
    (
        "listFiles",
        "GET",
        "/v1/files",
        "limit=2",
        {},
        200,
        ENVELOPE,
        lambda c: c.files.list(limit=2),
    ),
    (
        "listPages",
        "GET",
        "/v1/pages",
        "limit=2&after=cur_1",
        {},
        200,
        ENVELOPE,
        lambda c: c.pages.list(limit=2, after="cur_1"),
    ),
    (
        "createPage",
        "POST",
        "/v1/pages",
        "",
        {},
        201,
        {"id": "pg_1"},
        lambda c: c.pages.create({"title": "Hello"}),
    ),
    (
        "getPage",
        "GET",
        "/v1/pages/pg_1",
        "",
        {},
        200,
        {"id": "pg_1"},
        lambda c: c.pages.get("pg_1"),
    ),
    (
        "updatePage",
        "PATCH",
        "/v1/pages/pg_1",
        "",
        {},
        200,
        {"id": "pg_1"},
        lambda c: c.pages.update("pg_1", {"expected_updated_at": "t0"}),
    ),
    (
        "deletePage",
        "DELETE",
        "/v1/pages/pg_1",
        "",
        {},
        204,
        None,
        lambda c: c.pages.delete("pg_1"),
    ),
    (
        "addBlock",
        "POST",
        "/v1/pages/pg_1/blocks",
        "",
        {},
        201,
        {"id": "pg_1"},
        lambda c: c.pages.add_block("pg_1", {"type": "link", "data": {}}),
    ),
    (
        "removeBlock",
        "DELETE",
        "/v1/pages/pg_1/blocks/bl_1",
        "expected_updated_at=t0",
        {},
        200,
        {"id": "pg_1"},
        lambda c: c.pages.remove_block("pg_1", "bl_1", expected_updated_at="t0"),
    ),
    (
        "publishPage",
        "POST",
        "/v1/pages/pg_1/publish",
        "",
        {},
        200,
        {"status": "PUBLISHED"},
        lambda c: c.pages.publish("pg_1"),
    ),
    ("getUsage", "GET", "/v1/usage", "", {}, 200, {"meters": []}, lambda c: c.usage.get()),
    (
        "listWebhookEndpoints",
        "GET",
        "/v1/webhook-endpoints",
        "",
        {},
        200,
        {"data": []},
        lambda c: c.webhook_endpoints.list(),
    ),
    (
        "createWebhookEndpoint",
        "POST",
        "/v1/webhook-endpoints",
        "",
        {},
        201,
        {"id": "we_1", "secret": "whsec_x"},
        lambda c: c.webhook_endpoints.create({"url": "https://example.com/hook"}),
    ),
    (
        "getWebhookEndpoint",
        "GET",
        "/v1/webhook-endpoints/we_1",
        "",
        {},
        200,
        {"id": "we_1"},
        lambda c: c.webhook_endpoints.get("we_1"),
    ),
    (
        "updateWebhookEndpoint",
        "PATCH",
        "/v1/webhook-endpoints/we_1",
        "",
        {},
        200,
        {"id": "we_1"},
        lambda c: c.webhook_endpoints.update("we_1", {"enabled": False}),
    ),
    (
        "deleteWebhookEndpoint",
        "DELETE",
        "/v1/webhook-endpoints/we_1",
        "",
        {},
        204,
        None,
        lambda c: c.webhook_endpoints.delete("we_1"),
    ),
    (
        "listWebhookDeliveries",
        "GET",
        "/v1/webhook-endpoints/we_1/deliveries",
        "limit=5&status=FAILED",
        {},
        200,
        ENVELOPE,
        lambda c: c.webhook_endpoints.deliveries("we_1", limit=5, status="FAILED"),
    ),
    (
        "resendWebhookDelivery",
        "POST",
        "/v1/webhook-endpoints/we_1/deliveries/wd_1/resend",
        "",
        {},
        200,
        {"id": "wd_1"},
        lambda c: c.webhook_endpoints.resend_delivery("we_1", "wd_1"),
    ),
    (
        "replayWebhookDeliveries",
        "POST",
        "/v1/webhook-endpoints/we_1/replay",
        "",
        {},
        200,
        {"queued": 3},
        lambda c: c.webhook_endpoints.replay("we_1", {"since": "2026-08-01T00:00:00Z"}),
    ),
    (
        "rotateWebhookSecret",
        "POST",
        "/v1/webhook-endpoints/we_1/rotate-secret",
        "",
        {},
        200,
        {"secret": "whsec_new"},
        lambda c: c.webhook_endpoints.rotate_secret("we_1"),
    ),
    (
        "testWebhookEndpoint",
        "POST",
        "/v1/webhook-endpoints/we_1/test",
        "",
        {},
        200,
        {"delivered": True},
        lambda c: c.webhook_endpoints.test("we_1"),
    ),
]


def test_there_is_one_case_per_spec_operation() -> None:
    assert sorted(case[0] for case in CASES) == sorted(OPERATIONS)


@pytest.mark.parametrize("case", CASES, ids=lambda case: str(case[0]))
@respx.mock
def test_operation_hits_the_right_method_url_and_query(case: Case) -> None:
    operation_id, method, path, query, _headers, status, payload, call = case
    route = respx.mock.request(method, f"{TEST_BASE_URL}{path}").mock(
        return_value=(
            httpx.Response(status) if payload is None else httpx.Response(status, json=payload)
        )
    )
    with make_client() as client:
        result = call(client)

    assert route.call_count == 1, operation_id
    request = route.calls.last.request
    assert request.method == method
    assert request.url.path == path
    assert request.url.query.decode() == query
    if status == 204:
        assert result is None
    else:
        assert result is not None


@respx.mock
def test_path_parameters_are_url_encoded_so_ids_cannot_escape_their_segment() -> None:
    route = respx.mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, json={}))
    with make_client() as client:
        client.pages.get("pg/../admin 1")
    assert route.calls.last.request.url.raw_path.decode() == "/v1/pages/pg%2F..%2Fadmin%201"


@respx.mock
def test_unset_query_parameters_are_omitted_entirely() -> None:
    route = respx.mock.get(f"{TEST_BASE_URL}/v1/pages").mock(
        return_value=httpx.Response(200, json=ENVELOPE)
    )
    with make_client() as client:
        client.pages.list()
    assert route.calls.last.request.url.query == b""


@respx.mock
def test_extra_query_lets_a_caller_reach_a_parameter_this_build_predates() -> None:
    route = respx.mock.get(f"{TEST_BASE_URL}/v1/pages").mock(
        return_value=httpx.Response(200, json=ENVELOPE)
    )
    with make_client() as client:
        client.pages.list(limit=1, extra_query={"sort": "created_at"})
    assert route.calls.last.request.url.query.decode() == "limit=1&sort=created_at"


@respx.mock
def test_the_raw_escape_hatch_reaches_an_endpoint_the_sdk_does_not_model() -> None:
    route = respx.mock.post(f"{TEST_BASE_URL}/v1/future-thing").mock(
        return_value=httpx.Response(
            200,
            json={"ok": True},
            headers={"x-request-id": "req_raw", "ratelimit": '"per-key-minute";r=41;t=17'},
        )
    )
    with make_client() as client:
        result = client.request("POST", "/v1/future-thing", body={"hello": "world"})
    assert result.data == {"ok": True}
    assert result.status == 200
    assert result.request_id == "req_raw"
    assert result.rate_limit is not None
    assert result.rate_limit.remaining == 41
    assert result.rate_limit.reset_seconds == 17
    assert "idempotency-key" in route.calls.last.request.headers


@respx.mock
def test_rate_limit_headers_are_parsed_from_both_the_draft_and_legacy_forms() -> None:
    respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(
        return_value=httpx.Response(
            200,
            json={},
            headers={
                "ratelimit-policy": '"per-key-minute";q=60;w=60',
                "ratelimit": '"per-key-minute";r=59;t=42',
                "x-ratelimit-limit": "60",
                "x-ratelimit-remaining": "59",
                "x-ratelimit-reset": "1767225600",
            },
        )
    )
    with make_client() as client:
        limits = client.request("GET", "/v1/usage").rate_limit
    assert limits is not None
    assert limits.policy == "per-key-minute"
    assert limits.limit == 60
    assert limits.remaining == 59
    assert limits.reset_seconds == 42
    assert limits.window_seconds == 60
    assert limits.reset_at == 1767225600


@respx.mock
def test_a_response_without_limiter_headers_reports_no_rate_limit_state() -> None:
    respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(return_value=httpx.Response(200, json={}))
    with make_client() as client:
        assert client.request("GET", "/v1/usage").rate_limit is None


@respx.mock
def test_publish_sends_an_empty_object_when_no_body_is_supplied() -> None:
    route = respx.mock.post(f"{TEST_BASE_URL}/v1/pages/pg_1/publish").mock(
        return_value=httpx.Response(200, json={})
    )
    with make_client() as client:
        client.pages.publish("pg_1")
    assert route.calls.last.request.content == b"{}"
