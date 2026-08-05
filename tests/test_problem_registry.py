"""The exception map covers exactly the problem codes the spec documents.

The Python mirror of the ``sdk-mirror`` half of the TypeScript contract suite:
a code the server can emit but the SDK does not map would silently degrade to a
status-family fallback, and a code the SDK maps but the server never emits is
dead weight that hides a rename.
"""

from __future__ import annotations

import pytest

from bioflow_py import PROBLEM_CODE_ERROR_CLASSES, APIError
from conftest import load_spec

SPEC_PROBLEM_CODES: list[str] = load_spec()["components"]["schemas"]["Problem"]["properties"][
    "code"
]["enum"]

# The status each code is documented under, mirroring problems.ts.
EXPECTED_STATUSES = {
    "invalid_request": 400,
    "invalid_api_key": 401,
    "insufficient_scope": 403,
    "feature_not_enabled": 403,
    "test_key_read_only": 403,
    "resource_not_found": 404,
    "stale_snapshot": 409,
    "idempotency_in_progress": 409,
    "idempotency_key_reused": 422,
    "endpoint_verification_failed": 422,
    "endpoint_limit_reached": 422,
    "rate_limited": 429,
    "quota_exhausted": 429,
    "internal_error": 500,
}


def test_the_spec_still_enumerates_fourteen_problem_codes() -> None:
    assert len(SPEC_PROBLEM_CODES) == 14


def test_the_exception_map_has_no_missing_and_no_extra_codes() -> None:
    assert sorted(PROBLEM_CODE_ERROR_CLASSES) == sorted(SPEC_PROBLEM_CODES)


@pytest.mark.parametrize("code", SPEC_PROBLEM_CODES)
def test_every_spec_code_maps_to_an_api_error_subclass(code: str) -> None:
    assert issubclass(PROBLEM_CODE_ERROR_CLASSES[code], APIError)


def test_the_documented_status_for_each_code_has_not_drifted() -> None:
    assert sorted(EXPECTED_STATUSES) == sorted(SPEC_PROBLEM_CODES)
