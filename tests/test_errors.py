"""RFC 9457 problem documents map onto the typed exception hierarchy."""

from __future__ import annotations

import httpx
import pytest
import respx

from bioflow_py import (
    PROBLEM_CODE_ERROR_CLASSES,
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    BioFlowError,
    ConflictError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    QuotaExhaustedError,
    RateLimitError,
    UnprocessableEntityError,
    parse_retry_after_ms,
)
from conftest import TEST_BASE_URL, make_client, problem_body

CODE_EXPECTATIONS: list[tuple[str, int, type[APIError]]] = [
    ("invalid_request", 400, BadRequestError),
    ("invalid_api_key", 401, AuthenticationError),
    ("insufficient_scope", 403, PermissionDeniedError),
    ("feature_not_enabled", 403, PermissionDeniedError),
    ("test_key_read_only", 403, PermissionDeniedError),
    ("resource_not_found", 404, NotFoundError),
    ("stale_snapshot", 409, ConflictError),
    ("idempotency_in_progress", 409, ConflictError),
    ("idempotency_key_reused", 422, UnprocessableEntityError),
    ("endpoint_verification_failed", 422, UnprocessableEntityError),
    ("endpoint_limit_reached", 422, UnprocessableEntityError),
    ("rate_limited", 429, RateLimitError),
    ("quota_exhausted", 429, QuotaExhaustedError),
    ("internal_error", 500, InternalServerError),
]


@pytest.mark.parametrize(("code", "status", "expected"), CODE_EXPECTATIONS)
@respx.mock
def test_each_problem_code_raises_its_own_exception_class(
    code: str, status: int, expected: type[APIError]
) -> None:
    respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(
        return_value=httpx.Response(
            status,
            json=problem_body(code, status, detail="because reasons"),
            headers={"content-type": "application/problem+json", "x-request-id": "req_abc"},
        )
    )
    with make_client(max_retries=0) as client, pytest.raises(expected) as excinfo:
        client.usage.get()
    error = excinfo.value
    assert type(error) is expected
    assert error.status == status
    assert error.code == code
    assert error.request_id == "req_abc"
    assert error.problem_type is not None
    assert error.problem_type.startswith("https://getbioflow.com/docs/api/errors/")
    assert str(error) == f"{status} {code}: because reasons"


def test_the_registry_covers_exactly_the_codes_the_spec_documents() -> None:
    assert sorted(PROBLEM_CODE_ERROR_CLASSES) == sorted(code for code, _, _ in CODE_EXPECTATIONS)


def test_quota_exhausted_is_a_rate_limit_error_so_broad_catches_still_work() -> None:
    assert issubclass(QuotaExhaustedError, RateLimitError)
    assert PROBLEM_CODE_ERROR_CLASSES["rate_limited"] is RateLimitError
    assert PROBLEM_CODE_ERROR_CLASSES["quota_exhausted"] is QuotaExhaustedError


def test_every_api_error_is_catchable_as_the_sdk_base_error() -> None:
    for error_class in PROBLEM_CODE_ERROR_CLASSES.values():
        assert issubclass(error_class, APIError)
        assert issubclass(error_class, BioFlowError)
    assert issubclass(APITimeoutError, APIConnectionError)
    assert issubclass(APIConnectionError, BioFlowError)


@respx.mock
def test_field_level_validation_errors_are_surfaced_verbatim() -> None:
    respx.mock.post(f"{TEST_BASE_URL}/v1/pages").mock(
        return_value=httpx.Response(
            400,
            json=problem_body(
                "invalid_request",
                400,
                detail="title is required",
                errors=[{"pointer": "/title", "code": "required", "message": "Required"}],
            ),
            headers={"content-type": "application/problem+json"},
        )
    )
    with make_client(max_retries=0) as client, pytest.raises(BadRequestError) as excinfo:
        client.pages.create({"title": ""})
    assert excinfo.value.errors == [
        {"pointer": "/title", "code": "required", "message": "Required"}
    ]
    assert excinfo.value.request_id == "req_test"


@respx.mock
def test_an_unknown_problem_code_falls_back_to_the_status_family_and_keeps_the_code() -> None:
    respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(
        return_value=httpx.Response(
            403,
            json=problem_body("some_code_shipped_after_this_sdk", 403, detail="nope"),
            headers={"content-type": "application/problem+json"},
        )
    )
    with make_client(max_retries=0) as client, pytest.raises(PermissionDeniedError) as excinfo:
        client.usage.get()
    assert excinfo.value.code == "some_code_shipped_after_this_sdk"


@respx.mock
def test_a_non_json_error_body_still_raises_a_typed_error_instead_of_crashing() -> None:
    respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(
        return_value=httpx.Response(502, text="<html>bad gateway</html>")
    )
    with make_client(max_retries=0) as client, pytest.raises(InternalServerError) as excinfo:
        client.usage.get()
    assert excinfo.value.code == "unknown"
    assert excinfo.value.problem is None
    assert str(excinfo.value) == "502 unknown: request failed"


@respx.mock
def test_an_empty_error_body_still_raises_a_typed_error() -> None:
    respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(return_value=httpx.Response(418))
    with make_client(max_retries=0) as client, pytest.raises(APIError) as excinfo:
        client.usage.get()
    assert type(excinfo.value) is APIError
    assert excinfo.value.status == 418


@respx.mock
def test_the_request_id_falls_back_to_the_problem_body_when_the_header_is_missing() -> None:
    respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(
        return_value=httpx.Response(
            404,
            json=problem_body("resource_not_found", 404, request_id="req_from_body"),
            headers={"content-type": "application/problem+json"},
        )
    )
    with make_client(max_retries=0) as client, pytest.raises(NotFoundError) as excinfo:
        client.usage.get()
    assert excinfo.value.request_id == "req_from_body"


@respx.mock
def test_a_transport_failure_becomes_a_connection_error() -> None:
    respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(side_effect=httpx.ConnectError("nope"))
    with make_client(max_retries=0) as client, pytest.raises(APIConnectionError):
        client.usage.get()


@respx.mock
def test_a_timeout_becomes_an_api_timeout_error() -> None:
    respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(side_effect=httpx.ReadTimeout("too slow"))
    with make_client(max_retries=0) as client, pytest.raises(APITimeoutError):
        client.usage.get()


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, None),
        ("", None),
        ("0", 0.0),
        ("12", 12_000.0),
        ("1.5", 1_500.0),
        ("not-a-date", None),
    ],
)
def test_retry_after_parses_delay_seconds_and_rejects_nonsense(
    header: str | None, expected: float | None
) -> None:
    assert parse_retry_after_ms(header) == expected


def test_retry_after_parses_an_http_date_relative_to_now() -> None:
    # Thu, 01 Jan 2026 00:00:30 GMT, evaluated 30 s earlier.
    reference = 1_767_225_600.0
    parsed = parse_retry_after_ms("Thu, 01 Jan 2026 00:00:30 GMT", now=reference)
    assert parsed == pytest.approx(30_000.0)


def test_an_http_date_in_the_past_never_yields_a_negative_wait() -> None:
    reference = 1_767_225_600.0
    assert parse_retry_after_ms("Thu, 01 Jan 2026 00:00:00 GMT", now=reference + 60) == 0.0
