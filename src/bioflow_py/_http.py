"""The HTTP core every resource method rides.

Behaviour contract (pinned by ``tests/test_retries.py`` and friends), mirroring
``packages/sdk/src/core/http.ts``:

* auth: ``Authorization: Bearer bf_…`` by default, or the ``x-api-key`` style
* retries (default 2): 429 ``rate_limited`` for ANY method (the server refuses
  those pre-execution); network/timeout/408/5xx only for GETs and for POSTs
  carrying an ``Idempotency-Key``. 429 ``quota_exhausted``, PATCH and DELETE are
  NEVER auto-retried (unsafe or pointless).
* ``Retry-After`` is honoured exactly (delay-seconds or HTTP-date); a wait beyond
  ``max_retry_after`` abandons the retry instead of sleeping for minutes.
* every consequential POST gets an auto-generated ``Idempotency-Key`` (the server
  ledgers all of them) unless the caller supplies one or disables
  ``auto_idempotency_keys``; the SAME key is reused across retries.
* errors: ``application/problem+json`` -> the typed hierarchy in :mod:`bioflow_py.errors`.
* debug logging never emits secrets.

Sync and async share every decision here; only the send loop differs.
"""

from __future__ import annotations

import asyncio
import json as _json
import os
import random
import sys
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar

import httpx

from . import __version__
from ._redact import redact_secrets
from .errors import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    BioFlowError,
    api_error_from_response,
    parse_retry_after_ms,
)
from .operations import HttpMethod

DEFAULT_BASE_URL = "https://app.getbioflow.com"
"""Production API origin. Paths already carry the ``/v1`` prefix."""

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_MAX_RETRY_AFTER = 60.0
API_KEY_ENV_VAR = "BIOFLOW_API_KEY"
USER_AGENT = f"bioflow-sdk/{__version__}"

AuthStyle = Literal["bearer", "x-api-key"]

T = TypeVar("T")


class NotGiven:
    """Sentinel distinguishing "no body at all" from an explicit ``None`` body."""

    _instance: NotGiven | None = None

    def __new__(cls) -> NotGiven:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "NOT_GIVEN"


NOT_GIVEN = NotGiven()


@dataclass(frozen=True)
class RateLimitInfo:
    """Parsed limiter state from a response.

    Combines the IETF draft-11 structured fields (``RateLimit``,
    ``RateLimit-Policy``) with the de-facto ``X-RateLimit-*`` trio.
    """

    policy: str | None
    """Policy name, e.g. ``"per-key-minute"``."""

    limit: int | None
    """Requests allowed per window (``q`` / ``X-RateLimit-Limit``)."""

    remaining: int | None
    """Requests left in this window (``r`` / ``X-RateLimit-Remaining``)."""

    reset_seconds: int | None
    """Seconds until the window resets (``t``)."""

    window_seconds: int | None
    """Window length in seconds (``w``)."""

    reset_at: int | None
    """Unix epoch **seconds** at which the window resets (``X-RateLimit-Reset``)."""

    @classmethod
    def from_headers(cls, headers: Mapping[str, str]) -> RateLimitInfo | None:
        """Parse limiter headers, or return ``None`` when the server sent none."""
        rate_limit = _header(headers, "ratelimit")
        policy_header = _header(headers, "ratelimit-policy")
        legacy_limit = _int_or_none(_header(headers, "x-ratelimit-limit"))
        legacy_remaining = _int_or_none(_header(headers, "x-ratelimit-remaining"))
        legacy_reset = _int_or_none(_header(headers, "x-ratelimit-reset"))
        if (
            rate_limit is None
            and policy_header is None
            and legacy_limit is None
            and legacy_remaining is None
            and legacy_reset is None
        ):
            return None
        policy_name, policy_params = _parse_structured_item(policy_header)
        state_name, state_params = _parse_structured_item(rate_limit)
        return cls(
            policy=policy_name or state_name,
            limit=_int_or_none(policy_params.get("q")) or legacy_limit,
            remaining=_first_int(_int_or_none(state_params.get("r")), legacy_remaining),
            reset_seconds=_int_or_none(state_params.get("t")),
            window_seconds=_int_or_none(policy_params.get("w")),
            reset_at=legacy_reset,
        )


@dataclass(frozen=True)
class RawResult(Generic[T]):
    """A parsed response plus the transport metadata worth surfacing."""

    data: T
    """Decoded JSON body — ``None`` for 204 responses."""

    status: int
    headers: httpx.Headers

    request_id: str | None
    """``X-Request-Id`` — present on every response, including 401/429/500."""

    idempotency_replayed: bool
    """True when the server replayed a ledgered response instead of re-executing."""

    rate_limit: RateLimitInfo | None
    """Parsed limiter state, when the server advertised it."""


def _header(headers: Mapping[str, str], name: str) -> str | None:
    if isinstance(headers, httpx.Headers):
        return headers.get(name)
    for key, value in headers.items():
        if key.lower() == name:
            return value
    return None


def _int_or_none(raw: str | int | None) -> int | None:
    if raw is None:
        return None
    try:
        return int(str(raw).strip().strip('"'))
    except ValueError:
        return None


def _first_int(*candidates: int | None) -> int | None:
    for candidate in candidates:
        if candidate is not None:
            return candidate
    return None


def _parse_structured_item(raw: str | None) -> tuple[str | None, dict[str, str]]:
    """Parse ``"name";k=v;k2=v2`` into ``("name", {"k": "v", "k2": "v2"})``."""
    if raw is None or raw == "":
        return None, {}
    parts = [part.strip() for part in raw.split(";")]
    name = parts[0].strip('"') or None
    params: dict[str, str] = {}
    for part in parts[1:]:
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        params[key.strip()] = value.strip().strip('"')
    return name, params


def _generate_idempotency_key() -> str:
    """``sdk_<uuid4>`` — mirrors the TypeScript SDK's ``sdk_${randomUUID()}``."""
    return f"sdk_{uuid.uuid4()}"


def serialize_query(query: Mapping[str, Any] | None) -> dict[str, str]:
    """Drop ``None`` values and stringify the rest, JSON-style for booleans."""
    if not query:
        return {}
    serialized: dict[str, str] = {}
    for key, value in query.items():
        if value is None:
            continue
        if isinstance(value, bool):
            serialized[key] = "true" if value else "false"
        else:
            serialized[key] = str(value)
    return serialized


@dataclass(frozen=True)
class _Prepared:
    method: HttpMethod
    path: str
    url: str
    params: dict[str, str]
    headers: dict[str, str]
    content: bytes | None
    timeout: float
    max_retries: int
    idempotency_key: str | None


class _TransportCore:
    """Everything the sync and async transports agree on."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        max_retry_after: float = DEFAULT_MAX_RETRY_AFTER,
        auth_style: AuthStyle = "bearer",
        auto_idempotency_keys: bool = True,
        default_headers: Mapping[str, str] | None = None,
        debug: bool | Callable[[str], None] = False,
    ) -> None:
        resolved_key = api_key if api_key is not None else os.environ.get(API_KEY_ENV_VAR)
        if not resolved_key:
            raise BioFlowError(
                "Missing API key — pass api_key='bf_live_…' or set the "
                f"{API_KEY_ENV_VAR} environment variable "
                "(create one in BioFlow → Settings)."
            )
        if auth_style not in ("bearer", "x-api-key"):
            raise BioFlowError(
                f"Unknown auth_style {auth_style!r} — expected 'bearer' or 'x-api-key'."
            )
        self._api_key = resolved_key
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._max_retry_after = max_retry_after
        self._auth_style: AuthStyle = auth_style
        self._auto_idempotency_keys = auto_idempotency_keys
        self._default_headers = dict(default_headers or {})
        self._debug = debug

    # -- request assembly -------------------------------------------------

    def _prepare(
        self,
        method: HttpMethod,
        path: str,
        *,
        query: Mapping[str, Any] | None,
        body: Any,
        timeout: float | None,
        max_retries: int | None,
        idempotency_key: str | None,
        headers: Mapping[str, str] | None,
        extra_query: Mapping[str, Any] | None,
    ) -> _Prepared:
        params = serialize_query(query)
        params.update(serialize_query(extra_query))
        resolved_key = idempotency_key
        if resolved_key is None and method == "POST" and self._auto_idempotency_keys:
            resolved_key = _generate_idempotency_key()
        has_body = not isinstance(body, NotGiven)
        request_headers = self._build_headers(has_body, headers, resolved_key)
        content = _json.dumps(body).encode("utf-8") if has_body else None
        return _Prepared(
            method=method,
            path=path,
            url=f"{self.base_url}{path}",
            params=params,
            headers=request_headers,
            content=content,
            timeout=timeout if timeout is not None else self._timeout,
            max_retries=max_retries if max_retries is not None else self._max_retries,
            idempotency_key=resolved_key,
        )

    def _build_headers(
        self,
        has_body: bool,
        headers: Mapping[str, str] | None,
        idempotency_key: str | None,
    ) -> dict[str, str]:
        built: dict[str, str] = {
            "Accept": "application/json",
            "X-Bioflow-Client": USER_AGENT,
            "User-Agent": USER_AGENT,
        }
        built.update(self._default_headers)
        if headers:
            built.update(headers)
        if self._auth_style == "x-api-key":
            built["x-api-key"] = self._api_key
        else:
            built["Authorization"] = f"Bearer {self._api_key}"
        if has_body:
            built["Content-Type"] = "application/json"
        if idempotency_key is not None:
            built["Idempotency-Key"] = idempotency_key
        return built

    # -- response handling ------------------------------------------------

    def _success(self, response: httpx.Response) -> RawResult[Any]:
        return RawResult(
            data=self._parse_success_body(response),
            status=response.status_code,
            headers=response.headers,
            request_id=response.headers.get("x-request-id"),
            idempotency_replayed=_truthy_header(response.headers.get("idempotency-replayed")),
            rate_limit=RateLimitInfo.from_headers(response.headers),
        )

    @staticmethod
    def _parse_success_body(response: httpx.Response) -> Any:
        if response.status_code == 204:
            return None
        content_type = response.headers.get("content-type", "")
        if "json" in content_type:
            try:
                return response.json()
            except ValueError:
                return response.text or None
        return response.text or None

    @staticmethod
    def _parse_error_body(response: httpx.Response) -> Any:
        text = response.text
        if not text:
            return None
        try:
            return _json.loads(text)
        except ValueError:
            return text

    def _error(self, response: httpx.Response) -> APIError:
        return api_error_from_response(
            status=response.status_code,
            body=self._parse_error_body(response),
            request_id=response.headers.get("x-request-id"),
            retry_after_ms=parse_retry_after_ms(response.headers.get("retry-after")),
        )

    # -- retry policy -----------------------------------------------------

    @staticmethod
    def _method_retryable(method: HttpMethod, has_idempotency_key: bool) -> bool:
        """May this method retry on network/timeout/408/5xx failures?"""
        if method == "GET":
            return True
        if method == "POST":
            return has_idempotency_key
        return False  # PATCH/DELETE: ambiguous partial effects — never auto-retry

    def _response_retryable(
        self,
        method: HttpMethod,
        status: int,
        code: str,
        has_idempotency_key: bool,
    ) -> bool:
        if status == 429:
            # rate_limited was refused pre-execution — safe for ANY method.
            # quota_exhausted resets at the period boundary — retrying is wrong.
            return code != "quota_exhausted"
        if status == 408 or status >= 500:
            return self._method_retryable(method, has_idempotency_key)
        return False

    def _backoff_seconds(self, attempt: int, retry_after_ms: float | None) -> float | None:
        """Delay before the next attempt; ``None`` = give up instead of sleeping."""
        if retry_after_ms is not None:
            if retry_after_ms > self._max_retry_after * 1000.0:
                return None
            return retry_after_ms / 1000.0
        base = min(0.5 * (2**attempt), 8.0)
        return base * (0.75 + random.random() * 0.5)

    # -- debug ------------------------------------------------------------

    def _log(self, line: str) -> None:
        if not self._debug:
            return
        message = redact_secrets(f"[bioflow-sdk] {line}")
        if callable(self._debug):
            self._debug(message)
        else:
            print(message, file=sys.stderr)

    def _log_attempt(self, prepared: _Prepared, attempt: int) -> None:
        self._log(
            f"{prepared.method} {prepared.path} attempt {attempt + 1}/{prepared.max_retries + 1}"
        )

    def _connection_error(self, exc: Exception, timeout: float) -> APIConnectionError:
        if isinstance(exc, httpx.TimeoutException):
            return APITimeoutError(f"Request timed out after {timeout}s")
        return APIConnectionError(redact_secrets(f"Connection error: {exc}"))

    def _evaluate(
        self, prepared: _Prepared, response: httpx.Response, attempt: int
    ) -> RawResult[Any] | APIError | float:
        """Decide what happens next: a result to return, an error to raise, or a sleep."""
        request_id = response.headers.get("x-request-id") or "no request id"
        if not response.is_error:
            self._log(f"{prepared.method} {prepared.path} -> {response.status_code} ({request_id})")
            return self._success(response)
        error = self._error(response)
        self._log(
            f"{prepared.method} {prepared.path} -> {response.status_code} "
            f"{error.code} ({request_id})"
        )
        if attempt >= prepared.max_retries or not self._response_retryable(
            prepared.method,
            response.status_code,
            error.code,
            prepared.idempotency_key is not None,
        ):
            return error
        delay = self._backoff_seconds(attempt, error.retry_after_ms)
        if delay is None:  # Retry-After beyond our budget
            return error
        self._log(f"{prepared.method} {prepared.path} retrying in {int(delay * 1000)}ms")
        return delay


def _truthy_header(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() not in ("", "false", "0")


class SyncTransport(_TransportCore):
    """Blocking send loop on top of :class:`httpx.Client`."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        http_client: httpx.Client | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key, **kwargs)
        self._owns_client = http_client is None
        self._client = http_client if http_client is not None else httpx.Client()

    def _sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def close(self) -> None:
        """Close the underlying httpx client, unless the caller supplied it."""
        if self._owns_client:
            self._client.close()

    def request(
        self,
        method: HttpMethod,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        body: Any = NOT_GIVEN,
        timeout: float | None = None,
        max_retries: int | None = None,
        idempotency_key: str | None = None,
        headers: Mapping[str, str] | None = None,
        extra_query: Mapping[str, Any] | None = None,
    ) -> RawResult[Any]:
        prepared = self._prepare(
            method,
            path,
            query=query,
            body=body,
            timeout=timeout,
            max_retries=max_retries,
            idempotency_key=idempotency_key,
            headers=headers,
            extra_query=extra_query,
        )
        attempt = 0
        while True:
            self._log_attempt(prepared, attempt)
            try:
                response = self._client.request(
                    prepared.method,
                    prepared.url,
                    params=prepared.params,
                    headers=prepared.headers,
                    content=prepared.content,
                    timeout=prepared.timeout,
                )
            except httpx.HTTPError as exc:
                error = self._connection_error(exc, prepared.timeout)
                retryable = self._method_retryable(
                    prepared.method, prepared.idempotency_key is not None
                )
                if not retryable or attempt >= prepared.max_retries:
                    raise error from exc
                delay = self._backoff_seconds(attempt, None) or 0.0
                self._log(
                    f"{prepared.method} {prepared.path} connection error — "
                    f"retrying in {int(delay * 1000)}ms"
                )
                self._sleep(delay)
                attempt += 1
                continue

            outcome = self._evaluate(prepared, response, attempt)
            if isinstance(outcome, RawResult):
                return outcome
            if isinstance(outcome, APIError):
                raise outcome
            self._sleep(outcome)
            attempt += 1


class AsyncTransport(_TransportCore):
    """Awaitable send loop on top of :class:`httpx.AsyncClient`."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key, **kwargs)
        self._owns_client = http_client is None
        self._client = http_client if http_client is not None else httpx.AsyncClient()

    async def _sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    async def aclose(self) -> None:
        """Close the underlying httpx client, unless the caller supplied it."""
        if self._owns_client:
            await self._client.aclose()

    async def request(
        self,
        method: HttpMethod,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        body: Any = NOT_GIVEN,
        timeout: float | None = None,
        max_retries: int | None = None,
        idempotency_key: str | None = None,
        headers: Mapping[str, str] | None = None,
        extra_query: Mapping[str, Any] | None = None,
    ) -> RawResult[Any]:
        prepared = self._prepare(
            method,
            path,
            query=query,
            body=body,
            timeout=timeout,
            max_retries=max_retries,
            idempotency_key=idempotency_key,
            headers=headers,
            extra_query=extra_query,
        )
        attempt = 0
        while True:
            self._log_attempt(prepared, attempt)
            try:
                response = await self._client.request(
                    prepared.method,
                    prepared.url,
                    params=prepared.params,
                    headers=prepared.headers,
                    content=prepared.content,
                    timeout=prepared.timeout,
                )
            except httpx.HTTPError as exc:
                error = self._connection_error(exc, prepared.timeout)
                retryable = self._method_retryable(
                    prepared.method, prepared.idempotency_key is not None
                )
                if not retryable or attempt >= prepared.max_retries:
                    raise error from exc
                delay = self._backoff_seconds(attempt, None) or 0.0
                self._log(
                    f"{prepared.method} {prepared.path} connection error — "
                    f"retrying in {int(delay * 1000)}ms"
                )
                await self._sleep(delay)
                attempt += 1
                continue

            outcome = self._evaluate(prepared, response, attempt)
            if isinstance(outcome, RawResult):
                return outcome
            if isinstance(outcome, APIError):
                raise outcome
            await self._sleep(outcome)
            attempt += 1


__all__ = [
    "API_KEY_ENV_VAR",
    "DEFAULT_BASE_URL",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_MAX_RETRY_AFTER",
    "DEFAULT_TIMEOUT",
    "NOT_GIVEN",
    "USER_AGENT",
    "AsyncTransport",
    "AuthStyle",
    "NotGiven",
    "RateLimitInfo",
    "RawResult",
    "SyncTransport",
    "serialize_query",
]
