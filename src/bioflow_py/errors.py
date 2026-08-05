"""Typed RFC 9457 error hierarchy mirroring the ``/v1`` problem-code registry.

The ``code`` string is the FINITE stable switch value — ``title``/``detail`` are
for humans and must never be parsed. Unknown codes stay forward-compatible: the
class falls back to the HTTP status family and ``code`` is preserved verbatim.

Mirrors ``packages/sdk/src/core/errors.ts`` in the TypeScript SDK.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from email.utils import parsedate_to_datetime
from typing import Any, TypedDict

__all__ = [
    "APIConnectionError",
    "APIError",
    "APITimeoutError",
    "APIUserAbortError",
    "AuthenticationError",
    "BadRequestError",
    "BioFlowError",
    "ConflictError",
    "InternalServerError",
    "NotFoundError",
    "PROBLEM_CODE_ERROR_CLASSES",
    "PermissionDeniedError",
    "ProblemDocument",
    "ProblemFieldError",
    "QuotaExhaustedError",
    "RateLimitError",
    "UnprocessableEntityError",
    "WebhookVerificationError",
    "api_error_from_response",
    "parse_retry_after_ms",
]


class ProblemFieldError(TypedDict):
    """A single field-level validation error inside a problem document."""

    pointer: str
    """JSON Pointer to the offending field, e.g. ``"/title"``."""

    code: str
    message: str


class ProblemDocument(TypedDict, total=False):
    """Raw ``application/problem+json`` document as received."""

    type: str
    title: str
    status: int
    detail: str
    instance: str
    code: str
    request_id: str
    errors: list[ProblemFieldError]


class BioFlowError(Exception):
    """Base class for every error raised by this SDK."""


class APIUserAbortError(BioFlowError):
    """The caller cancelled the request — never retried."""


class APIConnectionError(BioFlowError):
    """The request never produced an HTTP response (DNS, TLS, socket, ...)."""


class APITimeoutError(APIConnectionError):
    """The per-request timeout elapsed before a response arrived."""


class WebhookVerificationError(BioFlowError):
    """Webhook signature verification failed — treat the payload as untrusted."""


class APIError(BioFlowError):
    """An ``application/problem+json`` error response from the API."""

    def __init__(
        self,
        *,
        status: int,
        code: str,
        message: str,
        problem_type: str | None = None,
        title: str | None = None,
        detail: str | None = None,
        request_id: str | None = None,
        errors: Sequence[ProblemFieldError] | None = None,
        retry_after_ms: float | None = None,
        problem: ProblemDocument | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        """HTTP status code."""

        self.code = code
        """Stable machine code from the problem registry, or ``"unknown"``."""

        self.problem_type = problem_type
        """The problem ``type`` URI — resolves to a docs page."""

        self.title = title
        self.detail = detail

        self.request_id = request_id
        """``X-Request-Id`` — quote it in support requests."""

        self.errors = list(errors) if errors is not None else None
        """Per-field validation errors (JSON-Pointer addressed)."""

        self.retry_after_ms = retry_after_ms
        """Parsed ``Retry-After``, in milliseconds, when the server sent one."""

        self.problem = problem
        """The raw problem document."""


class BadRequestError(APIError):
    """400 — the request itself was malformed or failed validation."""


class AuthenticationError(APIError):
    """401 — the API key is missing, malformed, revoked or unknown."""


class PermissionDeniedError(APIError):
    """403 — authenticated but not allowed (scope, plan, or test-key ruling)."""


class NotFoundError(APIError):
    """404 — no such resource in this workspace."""


class ConflictError(APIError):
    """409 — optimistic-concurrency or in-flight idempotency conflict."""


class UnprocessableEntityError(APIError):
    """422 — semantically rejected (idempotency reuse, endpoint limits, ...)."""


class RateLimitError(APIError):
    """429 — the burst limiter refused the call; safe to retry after a wait."""


class QuotaExhaustedError(RateLimitError):
    """429 ``quota_exhausted`` — the monthly plan quota is consumed.

    Subclasses :class:`RateLimitError` so broad ``except`` blocks still work, but
    the SDK NEVER auto-retries it: ``Retry-After`` points at the period reset, not
    a burst window.
    """


class InternalServerError(APIError):
    """5xx — a BioFlow-side failure; retry idempotent calls."""


PROBLEM_CODE_ERROR_CLASSES: Mapping[str, type[APIError]] = {
    "invalid_request": BadRequestError,
    "invalid_api_key": AuthenticationError,
    "insufficient_scope": PermissionDeniedError,
    "feature_not_enabled": PermissionDeniedError,
    "test_key_read_only": PermissionDeniedError,
    "resource_not_found": NotFoundError,
    "stale_snapshot": ConflictError,
    "idempotency_in_progress": ConflictError,
    "idempotency_key_reused": UnprocessableEntityError,
    "endpoint_verification_failed": UnprocessableEntityError,
    "endpoint_limit_reached": UnprocessableEntityError,
    "rate_limited": RateLimitError,
    "quota_exhausted": QuotaExhaustedError,
    "internal_error": InternalServerError,
}
"""Problem ``code`` -> exception class. One entry per registry code."""


def _class_for_status(status: int) -> type[APIError]:
    if status == 400:
        return BadRequestError
    if status == 401:
        return AuthenticationError
    if status == 403:
        return PermissionDeniedError
    if status == 404:
        return NotFoundError
    if status == 409:
        return ConflictError
    if status == 422:
        return UnprocessableEntityError
    if status == 429:
        return RateLimitError
    if status >= 500:
        return InternalServerError
    return APIError


def parse_retry_after_ms(header_value: str | None, *, now: float | None = None) -> float | None:
    """Parse a ``Retry-After`` header into milliseconds.

    Accepts both delay-seconds (``"12"``) and an HTTP-date. Returns ``None`` when
    the header is absent or unparseable; never returns a negative delay.
    """
    if header_value is None or header_value == "":
        return None
    try:
        seconds = float(header_value)
    except ValueError:
        pass
    else:
        return max(seconds * 1000.0, 0.0)
    try:
        target = parsedate_to_datetime(header_value)
    except (TypeError, ValueError):
        return None
    if target is None:
        return None
    import datetime as _datetime

    if target.tzinfo is None:
        target = target.replace(tzinfo=_datetime.timezone.utc)
    reference = (
        now if now is not None else _datetime.datetime.now(tz=_datetime.timezone.utc).timestamp()
    )
    return max((target.timestamp() - reference) * 1000.0, 0.0)


def api_error_from_response(
    *,
    status: int,
    body: Any,
    request_id: str | None,
    retry_after_ms: float | None,
) -> APIError:
    """Build the right :class:`APIError` subclass from a problem response."""
    problem: ProblemDocument | None = body if isinstance(body, dict) else None
    raw_code = problem.get("code") if problem is not None else None
    code = raw_code if isinstance(raw_code, str) else "unknown"
    raw_title = problem.get("title") if problem is not None else None
    title = raw_title if isinstance(raw_title, str) else None
    raw_detail = problem.get("detail") if problem is not None else None
    detail = raw_detail if isinstance(raw_detail, str) else None
    raw_errors = problem.get("errors") if problem is not None else None
    errors = raw_errors if isinstance(raw_errors, list) else None
    raw_type = problem.get("type") if problem is not None else None
    problem_type = raw_type if isinstance(raw_type, str) else None
    body_request_id = problem.get("request_id") if problem is not None else None
    resolved_request_id = request_id or (
        body_request_id if isinstance(body_request_id, str) else None
    )
    error_class = PROBLEM_CODE_ERROR_CLASSES.get(code) or _class_for_status(status)
    return error_class(
        status=status,
        code=code,
        message=f"{status} {code}: {detail or title or 'request failed'}",
        problem_type=problem_type,
        title=title,
        detail=detail,
        request_id=resolved_request_id,
        errors=errors,
        retry_after_ms=retry_after_ms,
        problem=problem,
    )
