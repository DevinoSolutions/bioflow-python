"""Shared fixtures and helpers for the unit suite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "openapi" / "v1.json"

TEST_BASE_URL = "https://api.test"
TEST_API_KEY = "bf_live_" + "a" * 43 + "_deadbeef"


def load_spec() -> dict[str, Any]:
    """The vendored OpenAPI document — the contract tests' source of truth."""
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def spec_operations() -> list[dict[str, Any]]:
    """Flatten the spec into ``{operation_id, method, path, idempotent}`` records."""
    spec = load_spec()
    operations: list[dict[str, Any]] = []
    for path, methods in spec["paths"].items():
        for method, operation in methods.items():
            if method.upper() not in ("GET", "POST", "PATCH", "PUT", "DELETE"):
                continue
            operations.append(
                {
                    "operation_id": operation["operationId"],
                    "method": method.upper(),
                    "path": path,
                    "idempotent": bool(operation.get("x-idempotent", False)),
                }
            )
    return operations


def problem_body(
    code: str,
    status: int,
    *,
    detail: str | None = None,
    title: str = "Something went wrong",
    request_id: str = "req_test",
    errors: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """A realistic RFC 9457 body for the given problem code."""
    body: dict[str, Any] = {
        "type": f"https://getbioflow.com/docs/api/errors/{code.replace('_', '-')}",
        "title": title,
        "status": status,
        "instance": f"urn:request:{request_id}",
        "code": code,
        "request_id": request_id,
    }
    if detail is not None:
        body["detail"] = detail
    if errors is not None:
        body["errors"] = errors
    return body


@pytest.fixture
def client() -> Any:
    """A sync client pointed at the respx-mocked base URL."""
    from bioflow_py import BioFlow

    with BioFlow(api_key=TEST_API_KEY, base_url=TEST_BASE_URL) as bioflow:
        yield bioflow


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record retry sleeps instead of performing them — the suite never waits."""
    slept: list[float] = []

    def fake_sleep(self: Any, seconds: float) -> None:
        slept.append(seconds)

    async def fake_async_sleep(self: Any, seconds: float) -> None:
        slept.append(seconds)

    from bioflow_py import _http

    monkeypatch.setattr(_http.SyncTransport, "_sleep", fake_sleep)
    monkeypatch.setattr(_http.AsyncTransport, "_sleep", fake_async_sleep)
    return slept
