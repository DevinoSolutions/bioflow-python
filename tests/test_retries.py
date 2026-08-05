"""The retry matrix: method x problem-code x idempotency-key presence.

Every test here runs against a fake clock (the ``no_sleep`` fixture), so the suite
asserts the *decisions* without ever waiting.
"""

from __future__ import annotations

from email.utils import formatdate
from typing import Any

import httpx
import pytest
import respx

from bioflow_py import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    InternalServerError,
    QuotaExhaustedError,
    RateLimitError,
)
from conftest import TEST_BASE_URL, make_async_client, make_client, problem_body

PAGE_ID = "pg_1"
PAGE_PATH = f"{TEST_BASE_URL}/v1/pages/{PAGE_ID}"


def _client(**kwargs: object) -> Any:
    return make_client(**kwargs)


def _problem_response(status: int, code: str, **headers: str) -> httpx.Response:
    return httpx.Response(
        status,
        json=problem_body(code, status),
        headers={"content-type": "application/problem+json", **headers},
    )


@respx.mock
def test_rate_limited_is_retried_on_a_get_and_eventually_succeeds(
    no_sleep: list[float],
) -> None:
    route = respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(
        side_effect=[
            _problem_response(429, "rate_limited"),
            httpx.Response(200, json={"meter": {"remaining": 10}}),
        ]
    )
    with _client() as client:
        assert client.usage.get()["meter"]["remaining"] == 10
    assert route.call_count == 2
    assert len(no_sleep) == 1


@respx.mock
@pytest.mark.parametrize("method", ["GET", "POST", "PATCH", "DELETE"])
def test_rate_limited_is_retried_for_every_method_because_it_was_refused_upfront(
    method: str, no_sleep: list[float]
) -> None:
    """The burst limiter rejects before executing, so even PATCH/DELETE are safe."""
    route = respx.mock.request(method, PAGE_PATH).mock(
        side_effect=[
            _problem_response(429, "rate_limited"),
            httpx.Response(200, json={"id": PAGE_ID}),
        ]
    )
    with _client() as client:
        client.request(method, f"/v1/pages/{PAGE_ID}")  # type: ignore[arg-type]
    assert route.call_count == 2


@respx.mock
@pytest.mark.parametrize("method", ["GET", "POST", "PATCH", "DELETE"])
def test_quota_exhausted_is_never_retried_for_any_method(
    method: str, no_sleep: list[float]
) -> None:
    """Retry-After points at the monthly period boundary — sleeping is pointless."""
    route = respx.mock.request(method, PAGE_PATH).mock(
        return_value=_problem_response(429, "quota_exhausted", **{"retry-after": "5"})
    )
    with _client() as client, pytest.raises(QuotaExhaustedError) as excinfo:
        client.request(method, f"/v1/pages/{PAGE_ID}")  # type: ignore[arg-type]
    assert route.call_count == 1
    assert no_sleep == []
    assert excinfo.value.retry_after_ms == 5_000


@respx.mock
@pytest.mark.parametrize("status", [408, 500, 502, 503])
def test_transient_statuses_are_retried_on_a_get(status: int, no_sleep: list[float]) -> None:
    route = respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(
        side_effect=[
            _problem_response(status, "internal_error"),
            httpx.Response(200, json={"meter": {}}),
        ]
    )
    with _client() as client:
        client.usage.get()
    assert route.call_count == 2


@respx.mock
def test_a_post_carrying_an_idempotency_key_is_retried_on_a_5xx(
    no_sleep: list[float],
) -> None:
    route = respx.mock.post(f"{TEST_BASE_URL}/v1/pages").mock(
        side_effect=[
            _problem_response(503, "internal_error"),
            httpx.Response(201, json={"id": PAGE_ID}),
        ]
    )
    with _client() as client:
        client.pages.create({"title": "Retry me"})
    assert route.call_count == 2


@respx.mock
def test_a_post_without_an_idempotency_key_is_never_retried_on_a_5xx(
    no_sleep: list[float],
) -> None:
    """Without a ledger key the server could execute the call twice."""
    route = respx.mock.post(f"{TEST_BASE_URL}/v1/pages").mock(
        return_value=_problem_response(503, "internal_error")
    )
    with _client(auto_idempotency_keys=False) as client, pytest.raises(InternalServerError):
        client.pages.create({"title": "Do not duplicate"})
    assert route.call_count == 1


@respx.mock
@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
def test_patch_and_delete_are_never_retried_on_a_5xx(method: str, no_sleep: list[float]) -> None:
    """Their partial effects are ambiguous — the caller must decide."""
    route = respx.mock.request(method, PAGE_PATH).mock(
        return_value=_problem_response(500, "internal_error")
    )
    with _client() as client, pytest.raises(InternalServerError):
        client.request(method, f"/v1/pages/{PAGE_ID}")  # type: ignore[arg-type]
    assert route.call_count == 1


@respx.mock
def test_connection_errors_are_retried_on_a_get(no_sleep: list[float]) -> None:
    route = respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(
        side_effect=[httpx.ConnectError("boom"), httpx.Response(200, json={"meter": {}})]
    )
    with _client() as client:
        client.usage.get()
    assert route.call_count == 2


@respx.mock
def test_timeouts_are_retried_on_a_get_and_raise_once_the_budget_is_spent(
    no_sleep: list[float],
) -> None:
    route = respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(side_effect=httpx.ReadTimeout("slow"))
    with _client(max_retries=2) as client, pytest.raises(APITimeoutError):
        client.usage.get()
    assert route.call_count == 3
    assert len(no_sleep) == 2


@respx.mock
def test_connection_errors_are_not_retried_on_a_patch(no_sleep: list[float]) -> None:
    route = respx.mock.patch(PAGE_PATH).mock(side_effect=httpx.ConnectError("boom"))
    with _client() as client, pytest.raises(APIConnectionError):
        client.pages.update(PAGE_ID, {"expected_updated_at": "x"})
    assert route.call_count == 1


@respx.mock
def test_the_same_idempotency_key_rides_every_retry_attempt(no_sleep: list[float]) -> None:
    """Otherwise the server ledger would treat each attempt as a new request."""
    route = respx.mock.post(f"{TEST_BASE_URL}/v1/pages").mock(
        side_effect=[
            _problem_response(503, "internal_error"),
            _problem_response(503, "internal_error"),
            httpx.Response(201, json={"id": PAGE_ID}),
        ]
    )
    with _client(max_retries=2) as client:
        client.pages.create({"title": "Once only"})
    keys = {call.request.headers["idempotency-key"] for call in route.calls}
    assert len(keys) == 1
    assert route.call_count == 3


@respx.mock
def test_retry_after_in_seconds_is_honoured_exactly(no_sleep: list[float]) -> None:
    respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(
        side_effect=[
            _problem_response(429, "rate_limited", **{"retry-after": "7"}),
            httpx.Response(200, json={"meter": {}}),
        ]
    )
    with _client() as client:
        client.usage.get()
    assert no_sleep == [7.0]


@respx.mock
def test_retry_after_as_an_http_date_is_honoured(no_sleep: list[float]) -> None:
    import time as _time

    # 45 s out, so a slow test machine cannot let the deadline pass before the
    # request is made; still inside the default 60 s max_retry_after budget.
    respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(
        side_effect=[
            _problem_response(
                429, "rate_limited", **{"retry-after": formatdate(_time.time() + 45, usegmt=True)}
            ),
            httpx.Response(200, json={"meter": {}}),
        ]
    )
    with _client() as client:
        client.usage.get()
    assert 20.0 <= no_sleep[0] <= 46.0


@respx.mock
def test_a_retry_after_beyond_the_budget_raises_instead_of_sleeping(
    no_sleep: list[float],
) -> None:
    route = respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(
        return_value=_problem_response(429, "rate_limited", **{"retry-after": "3600"})
    )
    with _client(max_retry_after=60.0) as client, pytest.raises(RateLimitError):
        client.usage.get()
    assert route.call_count == 1
    assert no_sleep == []


@respx.mock
def test_max_retries_zero_disables_retrying_entirely(no_sleep: list[float]) -> None:
    route = respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(
        return_value=_problem_response(429, "rate_limited")
    )
    with _client(max_retries=0) as client, pytest.raises(RateLimitError):
        client.usage.get()
    assert route.call_count == 1


@respx.mock
def test_max_retries_can_be_raised_for_a_single_call(no_sleep: list[float]) -> None:
    route = respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(
        side_effect=[
            _problem_response(429, "rate_limited"),
            _problem_response(429, "rate_limited"),
            _problem_response(429, "rate_limited"),
            httpx.Response(200, json={"meter": {}}),
        ]
    )
    with _client(max_retries=0) as client:
        client.usage.get(max_retries=3)
    assert route.call_count == 4


@respx.mock
def test_backoff_grows_and_stays_jittered_within_the_documented_envelope(
    no_sleep: list[float],
) -> None:
    respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(
        side_effect=[
            _problem_response(500, "internal_error"),
            _problem_response(500, "internal_error"),
            httpx.Response(200, json={"meter": {}}),
        ]
    )
    with _client(max_retries=2) as client:
        client.usage.get()
    assert 0.375 <= no_sleep[0] <= 0.625  # 500ms +/- 25%
    assert 0.75 <= no_sleep[1] <= 1.25  # 1000ms +/- 25%


@respx.mock
@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422])
def test_client_errors_are_never_retried(status: int, no_sleep: list[float]) -> None:
    route = respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(
        return_value=_problem_response(status, "invalid_request")
    )
    with _client() as client, pytest.raises(APIError):
        client.usage.get()
    assert route.call_count == 1


@respx.mock
async def test_the_async_client_applies_the_same_retry_matrix(no_sleep: list[float]) -> None:
    route = respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(
        side_effect=[
            _problem_response(429, "rate_limited"),
            httpx.Response(200, json={"meter": {}}),
        ]
    )
    async with make_async_client() as client:
        await client.usage.get()
    assert route.call_count == 2
    assert len(no_sleep) == 1


@respx.mock
async def test_the_async_client_never_retries_quota_exhaustion(no_sleep: list[float]) -> None:
    route = respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(
        return_value=_problem_response(429, "quota_exhausted")
    )
    async with make_async_client() as client:
        with pytest.raises(QuotaExhaustedError):
            await client.usage.get()
    assert route.call_count == 1
