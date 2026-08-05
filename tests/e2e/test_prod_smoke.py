"""Production smoke tests against https://app.getbioflow.com.

The read-only leg runs on a ``bf_test_`` key and never mutates anything. The write
leg is opt-in (``BIOFLOW_E2E_WRITE=1`` + a ``bf_live_`` key), creates its own data
and cleans up after itself.
"""

from __future__ import annotations

import os
import uuid

import pytest

from bioflow_py import (
    DEFAULT_BASE_URL,
    AuthenticationError,
    BadRequestError,
    BioFlow,
    ConflictError,
    PermissionDeniedError,
)

PROD_BASE_URL = DEFAULT_BASE_URL

READ_SKIP_REASON = (
    "LOUD SKIP: BIOFLOW_TEST_API_KEY is not set, so the prod read-only smoke suite "
    "cannot run. Mint a bf_test_ key on a Creator or Pro workspace "
    "(BioFlow -> Settings -> Developers) and set it to exercise the real /v1 surface "
    f"at {PROD_BASE_URL}."
)
WRITE_SKIP_REASON = (
    "LOUD SKIP: the write leg needs BIOFLOW_E2E_WRITE=1 and a bf_live_ key in "
    "BIOFLOW_API_KEY. It creates and deletes real pages, so it is opt-in and should "
    "point at a throwaway workspace."
)

requires_test_key = pytest.mark.skipif(
    not os.environ.get("BIOFLOW_TEST_API_KEY"), reason=READ_SKIP_REASON
)
requires_write_leg = pytest.mark.skipif(
    not (os.environ.get("BIOFLOW_E2E_WRITE") == "1" and os.environ.get("BIOFLOW_API_KEY")),
    reason=WRITE_SKIP_REASON,
)


# -- read-only leg --------------------------------------------------------


@requires_test_key
def test_usage_reports_the_meter_and_every_transport_header(prod_client: BioFlow) -> None:
    raw = prod_client.request("GET", "/v1/usage")
    assert raw.status == 200

    usage = raw.data
    assert set(usage) >= {"meter", "burst"}
    meter = usage["meter"]
    assert {"limit", "used", "remaining", "reset_at"} <= set(meter)
    assert meter["used"] + meter["remaining"] <= meter["limit"] + 1

    assert raw.request_id, "every response must carry X-Request-Id"
    assert raw.request_id.startswith("req_")
    assert raw.rate_limit is not None, "RateLimit headers must be advertised"
    assert raw.rate_limit.policy
    assert raw.rate_limit.remaining is not None
    print(f"\nGET /v1/usage -> 200 request_id={raw.request_id} limits={raw.rate_limit}")


@requires_test_key
def test_listing_pages_returns_the_documented_envelope(prod_client: BioFlow) -> None:
    raw = prod_client.request("GET", "/v1/pages", query={"limit": 1})
    assert set(raw.data) == {"data", "has_more", "next_cursor"}
    print(f"\nGET /v1/pages -> 200 request_id={raw.request_id}")

    page = prod_client.pages.list(limit=1)
    first_ids = {item["id"] for item in page.data}
    if page.has_next_page():
        following = page.next_page()
        assert following is not None
        assert first_ids.isdisjoint({item["id"] for item in following.data})


@requires_test_key
@pytest.mark.parametrize(
    ("path", "query"),
    [
        ("/v1/contacts", {"limit": 1}),
        ("/v1/files", {"limit": 1}),
        ("/v1/analytics/summary", {}),
        ("/v1/webhook-endpoints", {}),
    ],
)
def test_every_read_endpoint_answers_with_a_json_body(
    prod_client: BioFlow, path: str, query: dict[str, int]
) -> None:
    raw = prod_client.request("GET", path, query=query)
    assert raw.status == 200
    assert raw.data is not None
    print(f"\nGET {path} -> 200 request_id={raw.request_id}")


@requires_test_key
def test_a_bogus_key_is_rejected_as_an_authentication_error() -> None:
    client = BioFlow(api_key="bf_live_deadbeefdeadbeefdeadbeefdeadbeefdeadbeef_00000000")
    with client, pytest.raises(AuthenticationError) as excinfo:
        client.usage.get()
    error = excinfo.value
    assert error.status == 401
    assert error.code == "invalid_api_key"
    assert error.request_id
    assert error.problem is not None, "the body must be application/problem+json"
    assert error.problem_type
    print(f"\nbad key -> 401 invalid_api_key request_id={error.request_id}")


@requires_test_key
def test_a_cursor_cannot_be_carried_between_operations(prod_client: BioFlow) -> None:
    pages = prod_client.pages.list(limit=1)
    if not pages.has_next_page():
        pytest.skip("LOUD SKIP: the workspace has no second page of pages to mint a cursor")
    with pytest.raises(BadRequestError) as excinfo:
        prod_client.contacts.list(limit=1, after=pages.next_cursor)
    codes = {error["code"] for error in (excinfo.value.errors or [])}
    assert excinfo.value.code == "invalid_request"
    assert "cursor_operation_mismatch" in codes or excinfo.value.status == 400
    print(f"\nreused cursor -> 400 {codes} request_id={excinfo.value.request_id}")


@requires_test_key
def test_a_test_key_cannot_write(prod_client: BioFlow) -> None:
    """Proves the read-only ruling AND the 403 mapping in one shot."""
    with pytest.raises(PermissionDeniedError) as excinfo:
        prod_client.pages.create({"title": f"e2e-should-never-exist-{uuid.uuid4().hex[:8]}"})
    assert excinfo.value.status == 403
    assert excinfo.value.code == "test_key_read_only"
    print(f"\ntest-key write -> 403 test_key_read_only request_id={excinfo.value.request_id}")


@requires_test_key
def test_the_client_talks_to_production_by_default(prod_client: BioFlow) -> None:
    assert prod_client.base_url == PROD_BASE_URL == "https://app.getbioflow.com"


# -- write leg (opt-in) ---------------------------------------------------


@requires_write_leg
def test_replaying_an_idempotency_key_returns_the_same_resource(
    prod_write_client: BioFlow,
) -> None:
    key = f"e2e-{uuid.uuid4()}"
    title = f"bioflow-py e2e {uuid.uuid4().hex[:8]}"
    first = prod_write_client.request(
        "POST", "/v1/pages", body={"title": title}, idempotency_key=key
    )
    assert first.status == 201
    assert first.idempotency_replayed is False
    try:
        second = prod_write_client.request(
            "POST", "/v1/pages", body={"title": title}, idempotency_key=key
        )
        assert second.data["id"] == first.data["id"]
        assert second.idempotency_replayed is True
        print(f"\nidempotent create replayed page {first.data['id']}")
    finally:
        prod_write_client.pages.delete(first.data["id"])


@requires_write_leg
def test_a_page_can_be_built_published_and_deleted(prod_write_client: BioFlow) -> None:
    page = prod_write_client.pages.create({"title": f"bioflow-py e2e {uuid.uuid4().hex[:8]}"})
    page_id = page["id"]
    try:
        with_block = prod_write_client.pages.add_block(
            page_id,
            {"type": "link", "data": {"label": "Docs", "url": "https://getbioflow.com"}},
        )
        assert with_block["draft"]["blocks"]

        prod_write_client.pages.publish(page_id)
        assert prod_write_client.pages.get(page_id)["status"] == "PUBLISHED"
        print(f"\npublished page {page_id}")
    finally:
        assert prod_write_client.pages.delete(page_id) is None


@requires_write_leg
def test_a_stale_concurrency_stamp_is_refused(prod_write_client: BioFlow) -> None:
    page = prod_write_client.pages.create({"title": f"bioflow-py e2e {uuid.uuid4().hex[:8]}"})
    try:
        with pytest.raises(ConflictError) as excinfo:
            prod_write_client.pages.update(
                page["id"],
                {"title": "nope", "expected_updated_at": "1970-01-01T00:00:00.000Z"},
            )
        assert excinfo.value.code == "stale_snapshot"
        print(f"\nstale update -> 409 stale_snapshot request_id={excinfo.value.request_id}")
    finally:
        prod_write_client.pages.delete(page["id"])
