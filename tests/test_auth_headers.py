"""Auth styles, SDK identity headers and constructor guards."""

from __future__ import annotations

import httpx
import pytest
import respx

from bioflow_py import API_KEY_ENV_VAR, USER_AGENT, AsyncBioFlow, BioFlow, BioFlowError
from conftest import TEST_API_KEY, TEST_BASE_URL


def _usage_route(respx_mock: respx.MockRouter) -> respx.Route:
    return respx_mock.get(f"{TEST_BASE_URL}/v1/usage").mock(
        return_value=httpx.Response(200, json={"meters": []})
    )


@respx.mock
def test_bearer_is_the_default_auth_style() -> None:
    route = _usage_route(respx.mock)
    with BioFlow(api_key=TEST_API_KEY, base_url=TEST_BASE_URL) as client:
        client.usage.get()
    request = route.calls.last.request
    assert request.headers["authorization"] == f"Bearer {TEST_API_KEY}"
    assert "x-api-key" not in request.headers


@respx.mock
def test_x_api_key_style_sends_the_key_in_its_own_header_and_no_bearer() -> None:
    route = _usage_route(respx.mock)
    with BioFlow(api_key=TEST_API_KEY, base_url=TEST_BASE_URL, auth_style="x-api-key") as client:
        client.usage.get()
    request = route.calls.last.request
    assert request.headers["x-api-key"] == TEST_API_KEY
    assert "authorization" not in request.headers


@respx.mock
def test_every_request_identifies_the_sdk_and_asks_for_json() -> None:
    route = _usage_route(respx.mock)
    with BioFlow(api_key=TEST_API_KEY, base_url=TEST_BASE_URL) as client:
        client.usage.get()
    request = route.calls.last.request
    assert request.headers["x-bioflow-client"] == USER_AGENT
    assert request.headers["user-agent"] == USER_AGENT
    assert USER_AGENT.startswith("bioflow-sdk/")
    assert request.headers["accept"] == "application/json"


@respx.mock
def test_content_type_is_only_sent_when_there_is_a_body() -> None:
    get_route = _usage_route(respx.mock)
    post_route = respx.mock.post(f"{TEST_BASE_URL}/v1/pages").mock(
        return_value=httpx.Response(201, json={"id": "pg_1"})
    )
    with BioFlow(api_key=TEST_API_KEY, base_url=TEST_BASE_URL) as client:
        client.usage.get()
        client.pages.create({"title": "Hello"})
    assert "content-type" not in get_route.calls.last.request.headers
    assert post_route.calls.last.request.headers["content-type"] == "application/json"


@respx.mock
def test_default_headers_are_merged_and_per_call_headers_win() -> None:
    route = _usage_route(respx.mock)
    with BioFlow(
        api_key=TEST_API_KEY,
        base_url=TEST_BASE_URL,
        default_headers={"X-Tenant": "acme", "X-Trace": "default"},
    ) as client:
        client.usage.get(headers={"X-Trace": "per-call"})
    request = route.calls.last.request
    assert request.headers["x-tenant"] == "acme"
    assert request.headers["x-trace"] == "per-call"


@respx.mock
def test_a_caller_header_can_never_replace_the_api_key() -> None:
    route = _usage_route(respx.mock)
    with BioFlow(api_key=TEST_API_KEY, base_url=TEST_BASE_URL) as client:
        client.usage.get(headers={"Authorization": "Bearer not-your-key"})
    assert route.calls.last.request.headers["authorization"] == f"Bearer {TEST_API_KEY}"


def test_a_missing_api_key_raises_with_actionable_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(API_KEY_ENV_VAR, raising=False)
    with pytest.raises(BioFlowError) as excinfo:
        BioFlow()
    assert "Settings" in str(excinfo.value)
    with pytest.raises(BioFlowError):
        BioFlow(api_key="")


def test_the_api_key_falls_back_to_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(API_KEY_ENV_VAR, TEST_API_KEY)
    with BioFlow(base_url=TEST_BASE_URL) as client:
        assert client.base_url == TEST_BASE_URL


def test_an_unknown_auth_style_is_refused_at_construction() -> None:
    with pytest.raises(BioFlowError):
        BioFlow(api_key=TEST_API_KEY, auth_style="basic")  # type: ignore[arg-type]


def test_a_trailing_slash_on_the_base_url_never_doubles_up() -> None:
    with BioFlow(api_key=TEST_API_KEY, base_url=f"{TEST_BASE_URL}/") as client:
        assert client.base_url == TEST_BASE_URL


@respx.mock
async def test_the_async_client_sends_the_same_auth_and_identity_headers() -> None:
    route = _usage_route(respx.mock)
    async with AsyncBioFlow(api_key=TEST_API_KEY, base_url=TEST_BASE_URL) as client:
        await client.usage.get()
    request = route.calls.last.request
    assert request.headers["authorization"] == f"Bearer {TEST_API_KEY}"
    assert request.headers["x-bioflow-client"] == USER_AGENT


def test_a_caller_supplied_http_client_is_never_closed_by_the_sdk() -> None:
    http_client = httpx.Client()
    with BioFlow(api_key=TEST_API_KEY, base_url=TEST_BASE_URL, http_client=http_client):
        pass
    assert not http_client.is_closed
    http_client.close()
